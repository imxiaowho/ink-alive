"""Render native RGB PNG keys and a separate palette-reduced GIF review."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, GifImagePlugin

import engine
import gif_tool as legacy

VERSION = '1.1.0'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))


def render(recipe, output):
    recipe = Path(recipe).resolve()
    cfg = json.loads(recipe.read_text(encoding='utf-8-sig'))
    root = recipe.parent
    paths = [root / name for name in cfg['frames']]
    times = cfg['durations_ms']
    if not paths or len(paths) != len(times) or any(not isinstance(t,int) or t<20 or t%10 for t in times):
        raise ValueError('Require ordered PNG keys and one centisecond duration>=20ms per key')
    evidence = [root / name for name in cfg['provenance_evidence']]
    if not evidence or any(not p.is_file() for p in paths+evidence):
        raise ValueError('Missing explicit source PNGs or native-detail evidence')
    loaded = []
    for path in paths:
        with Image.open(path) as im:
            if im.format != 'PNG' or im.mode not in ['RGB','RGBA']:
                raise ValueError('Use native RGB/opaque RGBA PNGs; precompose alpha with the fixed plate')
            if im.mode == 'RGBA' and im.getchannel('A').getextrema() != (255,255):
                raise ValueError('Source alpha is not opaque; precompose the intended fixed background')
            loaded.append(np.array(im.convert('RGB')))
    if len({f.shape for f in loaded}) != 1:
        raise ValueError('All PNG canvases must have exactly the same size')
    keys = np.stack(loaded)
    _, height, width, _ = keys.shape
    minimum = cfg['minimum_source_size']
    if len(minimum)!=2 or any(not isinstance(v,int) or v<8 for v in minimum) or width<minimum[0] or height<minimum[1]:
        raise ValueError('Actual source canvases are below the declared pixel budget; no upscaling is performed')
    x0,y0,x1,y1 = cfg['moving_roi']
    if not all(isinstance(v,int) for v in [x0,y0,x1,y1]) or not 0<=x0<x1<=width or not 0<=y0<y1<=height:
        raise ValueError('Invalid inspected moving ROI')
    outside = np.ones((height,width),bool); outside[y0:y1,x0:x1] = False
    if np.any(keys[:,outside] != keys[0,outside]):
        raise ValueError('Background/body outside the moving ROI changes between source PNGs')
    transition = cfg['interpolate']
    step = transition['step_ms']
    pts = np.r_[0,np.cumsum(times[:-1])].astype(int)
    if not isinstance(step,int) or step<20 or step%10 or sum(times)%step or np.any(pts%step):
        raise ValueError('Output step must divide every key time and total duration without retiming')
    for eye in transition.get('eyes',[]):
        cx,cy,rx,ry = eye['ellipse']; a,b,c,d = eye['white_box']
        if not 0<=cx<x1-x0 or not 0<=cy<y1-y0 or min(rx,ry)<=0 or not 0<=a<c<=x1-x0 or not 0<=b<d<=y1-y0:
            raise ValueError('Eye coordinates must be inspected crop-local pixels')
    eye_states=cfg.get('eye_opening_states')
    if eye_states is not None:
        if len(eye_states)!=len(keys): raise ValueError('One inspected eye-opening state is required per source key')
        if not transition.get('eyes'): raise ValueError('Drawn-eye mode needs inspected eye guides')
        for eye in transition.get('eyes',[]):
            if len(eye.get('centers',[]))!=len(keys): raise ValueError('Drawn-eye mode needs crop-local centers per key')
            if any(len(c)!=2 or not 0<=c[0]<x1-x0 or not 0<=c[1]<y1-y0 for c in eye['centers']):
                raise ValueError('Invalid crop-local drawn-eye center')
    group=cfg.get('occlusion_face_patch')
    if group and (eye_states is None or len(group)!=4 or min(group[2:])<=0 or not 0<=group[0]<x1-x0 or not 0<=group[1]<y1-y0):
        raise ValueError('Face occlusion patch requires inspected states and a valid crop-local ellipse')
    estimated = (sum(times)//step)*(y1-y0)*(x1-x0)*3
    if estimated > cfg.get('max_crop_bytes',512*1024*1024):
        raise ValueError('Moving-crop frame buffer exceeds the declared memory budget; reduce action length or ROI')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new version directory')
    # Only the moving crop enters flow; full frames are composed and written one at a time.
    crop_keys=keys[:,y0:y1,x0:x1]
    flow_config=dict(transition)
    if eye_states is not None: flow_config['eyes']=[]
    crops, clock, _, _, provenance = engine.interpolate(crop_keys,times,flow_config,cfg.get('loop',True))
    if eye_states is not None:
        yy,xx=np.mgrid[:y1-y0,:x1-x0].astype('float32')
        crop_static=np.all(crop_keys==crop_keys[0],axis=(0,3))
        for index, phase in enumerate(provenance):
            a,b,t=phase['from_key'],phase['to_key'],phase['fraction']
            if eye_states[a]==eye_states[b] or t==0: continue
            chosen=a if t<.5 else b
            guides=transition.get('eyes',[])
            group=cfg.get('occlusion_face_patch')
            if group:
                centers=np.mean([e['centers'] for e in guides],axis=0)
                desired=centers[a]*(1-t)+centers[b]*t
                shift=desired-centers[chosen]
                patch=cv2.warpAffine(crop_keys[chosen],np.float32([[1,0,shift[0]],[0,1,shift[1]]]),(x1-x0,y1-y0),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT101)
                cx,cy,rx,ry=group
                mask=(((xx-cx-shift[0])/rx)**2+((yy-cy-shift[1])/ry)**2<=1).astype('float32')
                mask=cv2.GaussianBlur(mask,(0,0),5)[:,:,None]
                crops[index]=np.rint(crops[index]*(1-mask)+patch*mask).clip(0,255).astype('uint8')
                crops[index,crop_static]=crop_keys[0,crop_static]
                continue
            for eye in guides:
                centers=np.asarray(eye['centers'],float)
                desired=centers[a]*(1-t)+centers[b]*t
                shift=desired-centers[chosen]
                transform=np.float32([[1,0,shift[0]],[0,1,shift[1]]])
                patch=cv2.warpAffine(crop_keys[chosen],transform,(x1-x0,y1-y0),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT101)
                rx,ry=eye['ellipse'][2:]
                mask=(((xx-desired[0])/rx)**2+((yy-desired[1])/ry)**2<=1).astype('float32')
                mask=cv2.GaussianBlur(mask,(0,0),eye.get('feather_px',4))[:,:,None]
                crops[index]=np.rint(crops[index]*(1-mask)+patch*mask).clip(0,255).astype('uint8')
            crops[index,crop_static]=crop_keys[0,crop_static]
    output.mkdir(parents=True)
    native = output/'frames-native'; native.mkdir()
    source_dir = output/'keys-native'; source_dir.mkdir()
    for i,frame in enumerate(keys): Image.fromarray(frame).save(source_dir/f'{i:04}.png')
    samples = Image.new('RGB',(512,288*len(keys)))
    for i,key in enumerate(keys):
        thumb=Image.fromarray(key); thumb.thumbnail((512,288),Image.Resampling.LANCZOS)
        samples.paste(thumb,(0,288*i))
    palette=samples.quantize(colors=256,method=Image.Quantize.MEDIANCUT).getpalette()
    palette_ref=engine.palette_image(palette)
    def indexed(frame):
        return np.array(Image.fromarray(frame).quantize(palette=palette_ref,dither=Image.Dither.NONE))
    static=np.all(keys==keys[0],axis=(0,3))
    static_ids=indexed(keys[0])
    key_indices=(pts//step).astype(int).tolist()
    key_ids={index:indexed(keys[i]) for i,index in enumerate(key_indices)}
    source_keys={index:keys[i] for i,index in enumerate(key_indices)}
    background_index=int(static_ids[0,0])
    key_errors=[]; static_errors=0; native_files=[]
    preview=output/'preview.gif'
    with preview.open('xb') as stream:
        first=Image.fromarray(static_ids).convert('P'); first.putpalette(palette)
        info={'background':background_index,'optimize':False}
        if cfg.get('loop',True): info['loop']=0
        header,_=GifImagePlugin.getheader(first,palette=bytes(palette),info=info)
        for block in header: stream.write(block)
        for i,crop in enumerate(crops):
            frame=keys[0].copy(); frame[y0:y1,x0:x1]=crop
            frame[static]=keys[0,static]
            if i in source_keys: key_errors.append(int(np.count_nonzero(np.any(frame!=source_keys[i],axis=2))))
            static_errors+=int(np.count_nonzero(np.any(frame[static]!=keys[0,static],axis=1)))
            path=native/f'{i:04}.png'; Image.fromarray(frame).save(path)
            native_files.append({'path':str(path.relative_to(output)),'sha256':digest(path)})
            ids=key_ids[i].copy() if i in key_ids else indexed(frame)
            ids[static]=static_ids[static]
            encoded=Image.fromarray(ids).convert('P'); encoded.putpalette(palette)
            for block in GifImagePlugin.getdata(encoded,duration=clock[i],disposal=1,include_color_table=False,optimize=False): stream.write(block)
            if i%10==0: print(f'Wrote native frame {i+1}/{len(crops)}',flush=True)
        stream.write(b';')
    decoded,observed,_,info=engine.read_gif(preview)
    gif_key_errors=[int(np.count_nonzero(np.any(decoded[j]!=engine.rgb_from_ids(key_ids[j],palette),axis=2))) for j in key_indices]
    gif_static_errors=int(np.count_nonzero(np.any(decoded[:,static]!=decoded[0,static],axis=2)))
    if any(key_errors) or static_errors or any(gif_key_errors) or gif_static_errors or observed!=clock:
        raise ValueError('Actual native/GIF key, clock or static invariants failed')
    contacts=engine.contact_sheets(output/'review',decoded,observed)
    engine.contact_sheets(output/'review',keys,times,'native-keys')
    Image.fromarray(static.astype('uint8')*255).save(output/'static-mask.png')
    write(output/'recipe-used.json',cfg)
    result={'tool_version':VERSION,'size':[width,height],'minimum_source_size':minimum,'source_resize_performed':False,
            'native_detail_claim':'Canvas dimensions and supplied provenance are checked; this is not an automatic detector of previously upscaled art.',
            'source_key_states':len(keys),'unique_source_pngs':len(set(paths)),'frames':len(clock),'duration_ms':sum(clock),
            'moving_roi':[x0,y0,x1,y1],'background_body_outside_roi_fixed':True,'native_key_changed_pixels':key_errors,
            'eye_occlusion_handling':('nearest actual drawn face with rigid translation' if cfg.get('occlusion_face_patch') else 'nearest actual drawn eye with interpolated translation') if eye_states is not None else 'dense flow',
            'native_static_changed_pixels':static_errors,'gif_key_changed_pixels_vs_quantized_sources':gif_key_errors,
            'gif_static_changed_pixels':gif_static_errors,'native_rgb_masters':True,'gif_shared_palette_colors':256,
            'artifact_sha256':digest(preview),'visual_review':'pending','playback_review':'pending','user_acceptance':'not_inferred',
            'source_key_pts_ms':pts.tolist(),'key_output_indices':key_indices,'durations_ms':clock,'frame_provenance':provenance,
            'source_inputs':[{'path':str(p.resolve()),'sha256':digest(p)} for p in paths],
            'provenance_evidence':[{'path':str(p.resolve()),'sha256':digest(p)} for p in evidence],
            'native_frames':native_files,'review_sheets':[str(p.relative_to(output)) for p in contacts],
            'limits':'Only this supplied action/ROI is exercised; GIF loses colors relative to native PNG. No artistic approval is automatic.'}
    write(output/'checks.json',result)
    (output/'preview.html').write_text('<!doctype html><meta charset="utf-8"><title>Native PNG GIF review</title><h1>HD action preview — visual review pending</h1><img style="max-width:100%" src="preview.gif">',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['size','frames','duration_ms','artifact_sha256','visual_review']},ensure_ascii=False),flush=True)


def prepare_review(run):
    run=Path(run).resolve()
    checks=json.loads((run/'checks.json').read_text(encoding='utf-8'))
    if (run/'manifest.json').exists(): raise FileExistsError('Audit already prepared; preserve its manifest')
    if digest(run/'preview.gif')!=checks['artifact_sha256']: raise ValueError('Rendered GIF changed')
    for item in checks['native_frames']:
        if digest(run/item['path'])!=item['sha256']: raise ValueError('Native RGB frame changed')
    recipe=json.loads((run/'recipe-used.json').read_text(encoding='utf-8'))
    with Image.open(run/'preview.gif') as gif: palette=gif.getpalette()
    processed=run/'keys-processed'; processed.mkdir()
    native_keys=sorted((run/'keys-native').glob('*.png'))
    for i,path in enumerate(native_keys):
        with Image.open(path) as image: rgb=np.array(image.convert('RGB'))
        encoded=engine.rgb_from_ids(engine.quantize(rgb,palette),palette)
        Image.fromarray(encoded).save(processed/f'{i:04}.png')
        with Image.open(run/'frames-native'/f"{checks['key_output_indices'][i]:04}.png") as image:
            if not np.array_equal(np.array(image.convert('RGB')),rgb): raise ValueError('Actual native source-key RGB differs')
    checks['loop']=recipe.get('loop',True)
    write(run/'checks.json',checks)
    checks['mechanical']=legacy.mechanical(run)
    if not checks['mechanical']['passed']: raise ValueError('Actual GIF audit failed')
    write(run/'checks.json',checks)
    shutil.copy2(legacy.REFERENCE,run/'reference.gif'); shutil.copy2(legacy.APPROVAL,run/'reference-approval.json')
    critical=[run/name for name in ['preview.gif','checks.json','recipe-used.json','static-mask.png','reference.gif','reference-approval.json']]
    critical+=list((run/'frames-native').glob('*.png'))+native_keys+list(processed.glob('*.png'))
    write(run/'manifest.json',{'tool_version':VERSION,'files':{str(p.relative_to(run)):digest(p) for p in critical}})
    names=legacy.REQUIRED_REVIEWS+['native_detail']
    write(run/'review-template.json',{'artifact_sha256':checks['artifact_sha256'],'reviewer':'',
          'checks':{name:{'status':'pending','note':''} for name in names},
          'playback':{'status':'not_performed','note':''},'evidence':checks['review_sheets']})
    print(json.dumps({'audit_prepared':str(run),'native_frame_hashes':len(checks['native_frames']),'mechanical':True}))


def record_review(args):
    record=json.loads(Path(args.record).read_text(encoding='utf-8'))
    detail=record.get('checks',{}).get('native_detail',{})
    if detail.get('status') not in ['pending','failed','passed'] or not detail.get('note'):
        raise ValueError('Actual native-detail review status/note required')
    run=Path(args.run).resolve()
    if any(not (run/name).resolve().is_relative_to(run) for name in record.get('evidence',[])):
        raise ValueError('Keep native review evidence inside the inspected run')
    legacy.review(args)
    saved=json.loads((run/'review-record.json').read_text(encoding='utf-8'))
    saved['native_manifest_sha256']=digest(run/'manifest.json')
    write(run/'review-record.json',saved)


def finalize(args):
    run=Path(args.run).resolve()
    record=json.loads((run/'review-record.json').read_text(encoding='utf-8'))
    if record['checks']['native_detail']['status']!='passed' or record['native_manifest_sha256']!=digest(run/'manifest.json'):
        raise ValueError('Native master audit incomplete or changed')
    files=json.loads((run/'manifest.json').read_text(encoding='utf-8'))['files']
    files.update(record['evidence_sha256'])
    for name,expected in files.items():
        source=(run/name).resolve()
        if not source.is_relative_to(run) or digest(source)!=expected: raise ValueError('Bound native/evidence file changed')
    legacy.finalize(args)
    out=Path(args.out).resolve()
    for name,expected in files.items():
        source=(run/name).resolve()
        target=out/source.relative_to(run); target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if digest(target)!=expected: raise ValueError('Selected copy differs')
        else: shutil.copy2(source,target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('render'); p.add_argument('recipe'); p.add_argument('--out',required=True)
    p=commands.add_parser('prepare-review'); p.add_argument('run')
    p=commands.add_parser('record-review'); p.add_argument('run'); p.add_argument('--record',required=True)
    p=commands.add_parser('finalize'); p.add_argument('run'); p.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='render': render(args.recipe,args.out)
    elif args.command=='prepare-review': prepare_review(args.run)
    elif args.command=='record-review': record_review(args)
    else: finalize(args)
