"""Local single-shot comic GIF production and SHA-bound review CLI."""
import argparse
import hashlib
import json
import platform
import shutil
import struct
import sys
from pathlib import Path
import cv2
import numpy as np
import PIL
from PIL import Image
import engine

SKILL = Path(__file__).resolve().parent.parent
REFERENCE = SKILL / 'assets/reference/panna-approved.gif'
APPROVAL = SKILL / 'assets/reference/approval.json'
VERSION = '1.0.0'
REQUIRED_REVIEWS = ['identity_anatomy', 'stability', 'expression_action', 'edges_props', 'loop_join']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def new_directory(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def validate_recipe(cfg, root):
    if cfg.get('schema_version') != 1 or not cfg.get('id'):
        raise ValueError('Require schema_version1 and a nonempty id')
    source = cfg['source']
    if source['kind'] not in ['sheet', 'gif']:
        raise ValueError('source.kind must be sheet or gif')
    paths = [root / source['path']]
    bg, stable = cfg.get('background', {'mode': 'preserve'}), cfg.get('stabilize', {})
    if bg.get('mode', 'preserve') not in ['fixed', 'preserve']:
        raise ValueError('Unknown background mode')
    if bg.get('mode') == 'fixed':
        paths.append(root / bg['matte'])
        if source['kind'] != 'sheet':
            raise ValueError('Fixed matte processing requires sheet input')
        if len(bg['target_rgb']) != 3 or any(not 0 <= x <= 255 for x in bg['target_rgb']):
            raise ValueError('Invalid target RGB')
        low, high = bg.get('alpha_clip', [100, 200])
        if not 0 <= low < high <= 255:
            raise ValueError('Invalid alpha clipping range')
    if stable.get('enabled'):
        required = ['head_matte', 'coordinate_size', 'head_clip_y', 'ink_max_y', 'torso_transition_y', 'protected_ellipses', 'hair_region']
        absent = [key for key in required if key not in stable]
        if absent:
            raise ValueError('Missing inspected stabilization profile fields: ' + ', '.join(absent))
        if not stable.get('torso_idle') or bg.get('mode') != 'fixed':
            raise ValueError('Stabilization requires an explicitly idle torso and fixed-foreground matte')
        paths.append(root / stable['head_matte'])
        low, high = stable.get('head_alpha_clip', [100, 200])
        if not 0 <= low < high <= 255:
            raise ValueError('Invalid head alpha clipping range')
    for support in [bg.get('ink_support'), stable.get('head_ink_support')]:
        if support:
            lo, hi = support['red_range']
            if not 0 <= lo < hi <= 255 or not isinstance(support['radius'], int) or support['radius'] < 0:
                raise ValueError('Invalid source-specific ink support')
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError('Missing inputs: ' + ', '.join(missing))
    if source['kind'] == 'sheet':
        cols, rows = source['grid']
        if not all(isinstance(x, int) and x > 0 for x in [cols, rows]):
            raise ValueError('Grid dimensions must be positive integers')
        cells = source.get('cells', list(range(cols * rows)))
        if not cells or any(not isinstance(x, int) or not 0 <= x < cols * rows for x in cells):
            raise ValueError('Invalid selected cells')
        if len(source['durations_ms']) != len(cells):
            raise ValueError('One duration is required per selected cell')
    if sha(REFERENCE) != read(APPROVAL)['artifact_sha256']:
        raise ValueError('Approved benchmark bytes changed')
    return paths


def validate_media(cfg, frames, times):
    n, h, w, _ = frames.shape
    if min(h, w) < 8 or any(not isinstance(t, int) or t < 20 or t % 10 for t in times):
        raise ValueError('Native dimensions and centisecond durations>=20ms required')
    stable = cfg.get('stabilize', {})
    if stable.get('enabled'):
        if stable['coordinate_size'] != [w, h]:
            raise ValueError('Stabilization coordinates do not match the extracted image; inspect/reconfigure')
        a, b = stable['torso_transition_y']
        if not 0 <= a < b <= h or not 0 <= stable.get('master', 0) < n:
            raise ValueError('Invalid torso transition/master')
        if not 0 <= stable.get('reference_strength', 0) <= 1:
            raise ValueError('Invalid reference strength')
        for key in ['head_clip_y', 'ink_max_y']:
            if not 0 <= stable[key] <= h:
                raise ValueError('Invalid head processing boundary')
        hair = stable['hair_region']
        if not 0 <= hair['left_x'] < hair['right_x'] <= w or not 0 <= hair['upper_y'] <= hair['lower_y'] <= h:
            raise ValueError('Invalid hair processing region')
    transition = cfg.get('interpolate', {})
    if transition.get('enabled'):
        step = transition['step_ms']
        pts = np.r_[0, np.cumsum(times[:-1])]
        if not isinstance(step, int) or step < 20 or step % 10 or sum(times) % step or np.any(pts % step):
            raise ValueError('Output step>=20ms must divide duration and all source-key times')
    ellipses = stable.get('protected_ellipses', []) + [e['ellipse'] for e in transition.get('eyes', [])]
    for cx, cy, rx, ry in ellipses:
        if not 0 <= cx < w or not 0 <= cy < h or rx <= 0 or ry <= 0:
            raise ValueError('Invalid expression/eye ellipse')
    for eye in transition.get('eyes', []):
        x0, y0, x1, y1 = eye['white_box']
        if not 0 <= x0 < x1 <= w or not 0 <= y0 < y1 <= h:
            raise ValueError('Invalid eye sampling box')


def gif_structure(path):
    data = Path(path).read_bytes()
    pos = 13 + (3 * 2 ** ((data[10] & 7) + 1) if data[10] & 128 else 0)
    local_tables, rectangles = 0, []
    while pos < len(data) and data[pos] != 0x3B:
        if data[pos] == 0x21:
            pos += 2
        elif data[pos] == 0x2C:
            rectangles.append(list(struct.unpack('<HHHH', data[pos + 1:pos + 9])))
            packed = data[pos + 9]
            pos += 10
            if packed & 128:
                local_tables += 1
                pos += 3 * 2 ** ((packed & 7) + 1)
            pos += 1
        else:
            raise ValueError('Unexpected GIF container block')
        while data[pos]:
            pos += data[pos] + 1
        pos += 1
    return {'local_color_tables': local_tables, 'full_frame_rectangles': rectangles}


def mechanical(run):
    check = read(run / 'checks.json')
    frames, times, _, info = engine.read_gif(run / 'preview.gif')
    keys = np.stack([np.array(Image.open(p).convert('RGB')) for p in sorted((run / 'keys-processed').glob('*.png'))])
    static = np.array(Image.open(run / 'static-mask.png')) > 0
    key_changes = [int(np.count_nonzero(np.any(frames[j] != keys[i], axis=2))) for i, j in enumerate(check['key_output_indices'])]
    static_changes = int(np.count_nonzero(np.any(frames[:, static] != keys[0, static], axis=2)))
    structure = gif_structure(run / 'preview.gif')
    h, w = frames.shape[1:3]
    ok = (times == check['durations_ms'] and not any(key_changes) and static_changes == 0
          and info['loop'] == check['loop'] and not info['transparency']
          and all(m == 1 for m in info['disposal_methods']) and structure['local_color_tables'] == 0
          and all(r == [0, 0, w, h] for r in structure['full_frame_rectangles']))
    return {'passed': ok, 'full_decode': True, 'frames': len(frames), 'duration_ms': sum(times),
            'key_changed_pixels': key_changes, 'static_changed_pixels': static_changes,
            'structure': structure, **info}


def render(args):
    recipe = Path(args.recipe).resolve()
    cfg, root = read(recipe), recipe.parent
    inputs = validate_recipe(cfg, root)
    frames, times, palette, boxes, canvas = engine.load_source(cfg, root)
    validate_media(cfg, frames, times)
    bg_cfg, stable_cfg = cfg.get('background', {}), cfg.get('stabilize', {})
    raw_whole = engine.alpha_sheet(root / bg_cfg['matte'], boxes, canvas) if bg_cfg.get('mode') == 'fixed' else None
    raw_heads = engine.alpha_sheet(root / stable_cfg['head_matte'], boxes, canvas) if stable_cfg.get('enabled') else None
    out = new_directory(args.out)
    write(out / 'recipe-used.json', cfg)
    engine.save_frames(out / 'keys-source', frames)
    stages = {}
    if cfg['source']['kind'] == 'gif':
        with Image.open(root / cfg['source']['path']) as source_gif:
            bg = np.asarray(palette, dtype='uint8').reshape(-1, 3)[source_gif.info.get('background', 0)]
    else:
        bg = frames[0, 0, 0]
    if raw_whole is not None:
        frames, whole, bg = engine.repair_background(frames, palette, raw_whole, bg_cfg)
        engine.save_frames(out / 'keys-background', frames)
        engine.save_frames(out / 'foreground-mattes', whole)
        stages['background_rgb'] = bg.tolist()
    if stable_cfg.get('enabled'):
        frames, stats = engine.stabilize(frames, palette, whole, raw_heads, stable_cfg, bg, cfg.get('loop', True))
        stages['stabilize'] = stats
    keys, key_times = frames.copy(), times.copy()
    pts = np.r_[0, np.cumsum(times[:-1])].astype(int)
    static = np.all(keys == keys[0], axis=(0, 3))
    transition = cfg.get('interpolate', {})
    if transition.get('enabled'):
        frames, times, pts, static, provenance = engine.interpolate(keys, key_times, transition, cfg.get('loop', True))
        key_indices = (pts // transition['step_ms']).astype(int).tolist()
    else:
        key_indices, provenance = list(range(len(keys))), []
    engine.save_frames(out / 'keys-processed', keys)
    Image.fromarray(static.astype('uint8') * 255).save(out / 'static-mask.png')
    key_map = {index: keys[i] for i, index in enumerate(key_indices)}
    bg_index = {tuple(c): i for i, c in enumerate(np.array(palette).reshape(-1, 3).tolist())}[tuple(bg.tolist())]
    engine.encode(out / 'preview.gif', frames, times, palette, cfg.get('loop', True), bg_index, key_map, static)
    decoded, observed, _, _ = engine.read_gif(out / 'preview.gif')
    engine.save_frames(out / 'frames-decoded', decoded)
    contacts = engine.contact_sheets(out / 'review', decoded, observed)
    engine.contact_sheets(out / 'review', keys, key_times, 'processed-keys')
    shutil.copy2(REFERENCE, out / 'reference.gif')
    shutil.copy2(APPROVAL, out / 'reference-approval.json')
    check = {'tool_version': VERSION, 'artifact_sha256': sha(out / 'preview.gif'), 'id': cfg['id'],
             'size': [decoded.shape[2], decoded.shape[1]], 'durations_ms': times, 'loop': cfg.get('loop', True),
             'drawn_source_keys': len(keys), 'source_key_pts_ms': pts.tolist(), 'key_output_indices': key_indices,
             'unique_encoded_images': len({hashlib.sha256(f.tobytes()).hexdigest() for f in decoded}),
             'static_pixel_count': int(static.sum()), 'stages': stages, 'frame_provenance': provenance,
             'visual_review': 'pending', 'playback_review': 'pending', 'user_acceptance': 'not_inferred',
             'versions': {'python': platform.python_version(), 'pillow': PIL.__version__, 'numpy': np.__version__, 'opencv': cv2.__version__},
             'limits': 'Mechanical invariants and an approved reference do not prove new visual quality.'}
    write(out / 'checks.json', check)
    check['mechanical'] = mechanical(out)
    write(out / 'checks.json', check)
    if not check['mechanical']['passed']:
        raise ValueError(f'Actual output invariants failed: {out}')
    template = {'artifact_sha256': check['artifact_sha256'], 'reviewer': '',
                'checks': {name: {'status': 'pending', 'note': ''} for name in REQUIRED_REVIEWS},
                'playback': {'status': 'not_performed', 'note': ''},
                'evidence': [str(p.relative_to(out)) for p in contacts]}
    write(out / 'review-template.json', template)
    (out / 'preview.html').write_text('<!doctype html><meta charset="utf-8"><title>GIF review</title><style>body{background:#eee5d3;font:16px sans-serif}main{display:flex;gap:24px}img{image-rendering:auto}h2{font-size:18px}</style><h1>New GIF and approved effect reference</h1><main><section><h2>Preview</h2><img src="preview.gif"></section><section><h2>Effect reference</h2><img src="reference.gif"></section></main>', encoding='utf-8')
    critical = [out / 'preview.gif', out / 'recipe-used.json', out / 'static-mask.png', out / 'reference.gif', out / 'reference-approval.json'] + sorted((out / 'keys-processed').glob('*.png'))
    write(out / 'manifest.json', {'tool_version': VERSION, 'recipe_sha256': sha(recipe),
          'inputs': [{'path': str(p.resolve()), 'sha256': sha(p)} for p in inputs],
          'files': {str(p.relative_to(out)): sha(p) for p in critical}})
    print(json.dumps({'run': str(out), 'preview': str(out / 'preview.gif'), 'frames': len(decoded), 'duration_ms': sum(times), 'mechanical': True, 'visual_review': 'pending'}))


def inspect(args):
    path = Path(args.gif).resolve()
    frames, times, _, info = engine.read_gif(path)
    out = new_directory(args.out)
    engine.save_frames(out / 'frames', frames)
    contacts = engine.contact_sheets(out, frames, times)
    report = {'artifact_sha256': sha(path), 'frames': len(frames), 'duration_ms': sum(times),
              'durations_ms': times, 'size': [frames.shape[2], frames.shape[1]], **info,
              'structure': gif_structure(path), 'review_sheets': [p.name for p in contacts], 'visual_review': 'pending'}
    write(out / 'inspection.json', report)
    print(json.dumps({'inspection': str(out), 'frames': len(frames), 'duration_ms': sum(times)}))


def verify_manifest(run):
    for name, expected in read(run / 'manifest.json')['files'].items():
        if sha(run / name) != expected:
            raise ValueError(f'Output changed since render: {name}')
    if not mechanical(run)['passed']:
        raise ValueError('Current actual GIF failed mechanical checks')


def review(args):
    run = Path(args.run).resolve()
    verify_manifest(run)
    record = read(args.record)
    if record.get('artifact_sha256') != sha(run / 'preview.gif') or not record.get('reviewer'):
        raise ValueError('Review must identify the exact artifact and reviewer')
    for name in REQUIRED_REVIEWS:
        entry = record.get('checks', {}).get(name, {})
        if entry.get('status') not in ['pending', 'failed', 'passed'] or not entry.get('note'):
            raise ValueError(f'Located review note/status required: {name}')
    if record.get('playback', {}).get('status') not in ['observed', 'unavailable', 'not_performed'] or not record.get('playback', {}).get('note'):
        raise ValueError('Explicit playback status and actual-scope note required')
    evidence = record.get('evidence', [])
    if not evidence:
        raise ValueError('Inspected output evidence paths required')
    record['evidence_sha256'] = {name: sha((run / name).resolve()) for name in evidence}
    target = run / 'review-record.json'
    if target.exists():
        raise FileExistsError('Review already recorded; keep a versioned run for a changed result')
    write(target, record)
    print(json.dumps({'review_record': str(target), 'all_frame_checks_passed': all(record['checks'][n]['status'] == 'passed' for n in REQUIRED_REVIEWS)}))


def finalize(args):
    run = Path(args.run).resolve()
    verify_manifest(run)
    record = read(run / 'review-record.json')
    digest = sha(run / 'preview.gif')
    if record['artifact_sha256'] != digest or any(record['checks'][n]['status'] != 'passed' for n in REQUIRED_REVIEWS):
        raise ValueError('Exact-artifact visual review incomplete')
    for name, expected in record['evidence_sha256'].items():
        if sha((run / name).resolve()) != expected:
            raise ValueError(f'Inspected evidence changed: {name}')
    acceptance = record.get('user_acceptance', {})
    user_accepted = acceptance.get('confirmed') is True and acceptance.get('artifact_sha256') == digest and bool(acceptance.get('statement'))
    if record['playback']['status'] != 'observed' and not user_accepted:
        raise ValueError('Normal-speed viewing or explicit exact-artifact user acceptance is still missing; keep as preview')
    if sha(run / 'reference.gif') != read(APPROVAL)['artifact_sha256']:
        raise ValueError('Reference benchmark mismatch')
    out = new_directory(args.out)
    for name in ['preview.gif', 'checks.json', 'manifest.json', 'review-record.json', 'recipe-used.json']:
        shutil.copy2(run / name, out / name)
    write(out / 'selection.json', {'artifact_sha256': digest, 'reference_sha256': sha(REFERENCE),
          'basis': 'explicit_user_acceptance' if user_accepted else 'agent_visual_and_playback_review',
          'notice': 'Review attestations are not automated artistic approval or publishing authorization.'})
    print(json.dumps({'selected': str(out / 'preview.gif'), 'artifact_sha256': digest}))


def initialize(args):
    if args.columns <= 0 or args.rows <= 0 or args.duration_ms <= 0 or args.step_ms < 20 or args.step_ms % 10:
        raise ValueError('Positive grid/duration and centisecond step>=20ms required')
    count = args.columns * args.rows
    ticks, remainder = divmod(args.duration_ms, args.step_ms)
    if remainder or ticks < count or args.step_ms < 20 or args.step_ms % 10:
        raise ValueError('Use a centisecond step>=20ms dividing duration with at least one step per key')
    base, extra = divmod(ticks, count)
    times = [base * args.step_ms] * count
    for i in np.linspace(0, count - 1, extra, dtype=int):
        times[int(i)] += args.step_ms
    out = new_directory(args.directory)
    write(out / 'project.json', {'schema_version': 1, 'id': args.name, 'loop': True,
          'source': {'kind': 'sheet', 'path': 'source-sheet.png', 'grid': [args.columns, args.rows], 'edge_trim': 2, 'durations_ms': times},
          'background': {'mode': 'preserve'}, 'stabilize': {'enabled': False},
          'interpolate': {'enabled': False, 'step_ms': args.step_ms, 'eyes': []}})
    write(out / 'production-brief.json', {'status': 'awaiting_source_art_and_inspected_profile',
          'action': args.name, 'identity_reference': '', 'moving_regions': [], 'idle_regions': [],
          'art_note': 'Generate source-sheet.png with native imagegen, inspect every cell, then configure only justified processing stages.'})
    print(json.dumps({'project': str(out / 'project.json'), 'source_keys': count, 'duration_ms': sum(times)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='Create a new one-shot project; no art generation')
    p.add_argument('directory'); p.add_argument('--name', required=True)
    p.add_argument('--columns', type=int, default=6); p.add_argument('--rows', type=int, default=4)
    p.add_argument('--duration-ms', type=int, default=2000); p.add_argument('--step-ms', type=int, default=40)
    p.set_defaults(func=initialize)
    p = sub.add_parser('render', help='Run a recipe into a new version directory')
    p.add_argument('recipe'); p.add_argument('--out', required=True); p.set_defaults(func=render)
    p = sub.add_parser('inspect', help='Decode actual GIF and generate review sheets')
    p.add_argument('gif'); p.add_argument('--out', required=True); p.set_defaults(func=inspect)
    p = sub.add_parser('record-review', help='Bind actual visual-review notes/evidence to a run')
    p.add_argument('run'); p.add_argument('--record', required=True); p.set_defaults(func=review)
    p = sub.add_parser('finalize', help='Copy an artifact whose checks and review are complete')
    p.add_argument('run'); p.add_argument('--out', required=True); p.set_defaults(func=finalize)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, FileExistsError, KeyError, IndexError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
