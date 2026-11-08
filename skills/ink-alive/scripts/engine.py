"""Configurable mechanics extracted from the accepted Panna GIF production."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, GifImagePlugin


def palette_image(data):
    image = Image.new('P', (1, 1))
    image.putpalette(data)
    return image


def color_ids(rgb, palette):
    lookup = {tuple(c): i for i, c in enumerate(np.array(palette).reshape(-1, 3).tolist())}
    unique, inverse = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    try:
        indices = np.array([lookup[tuple(c)] for c in unique.tolist()], dtype='uint8')
    except KeyError as exc:
        raise ValueError('Input colors do not share the global palette; use source PNGs') from exc
    return indices[inverse].reshape(rgb.shape[:2])


def quantize(rgb, palette):
    return np.array(Image.fromarray(rgb).quantize(palette=palette_image(palette), dither=Image.Dither.NONE))


def rgb_from_ids(indices, palette):
    return np.asarray(palette, dtype='uint8').reshape(-1, 3)[indices]


def read_gif(path):
    frames, times, methods, rectangles = [], [], [], []
    with Image.open(path) as gif:
        if gif.format != 'GIF':
            raise ValueError('Expected GIF input')
        palette = gif.getpalette()
        loop = gif.info.get('loop') == 0
        background = gif.info.get('background', 0)
        transparency = False
        for i in range(gif.n_frames):
            gif.seek(i)
            rectangles.append(list(gif.tile[0][1]) if gif.tile else None)
            times.append(gif.info.get('duration', 0))
            methods.append(gif.disposal_method)
            transparency |= 'transparency' in gif.info
            frames.append(np.array(gif.convert('RGB')))
    if not frames or not palette:
        raise ValueError('Empty GIF or missing global palette')
    return np.stack(frames), times, palette, {
        'loop': loop, 'background_index': background, 'disposal_methods': methods,
        'frame_rectangles': rectangles, 'transparency': transparency}


def load_source(recipe, root):
    cfg = recipe['source']
    path = root / cfg['path']
    if cfg['kind'] == 'gif':
        frames, times, palette, _ = read_gif(path)
        for frame in frames:
            color_ids(frame, palette)
        return frames, times, palette, None, None
    with Image.open(path) as im:
        sheet = im.convert('RGB')
    cols, rows = cfg['grid']
    cells = cfg.get('cells', list(range(cols * rows)))
    trim = cfg.get('edge_trim', 2)
    if not isinstance(trim, int) or trim < 0 or 2 * trim >= min(sheet.width // cols, sheet.height // rows):
        raise ValueError('Cell edge trim leaves invalid or out-of-bounds geometry')
    boxes, frames = [], []
    for i in cells:
        x = round(i % cols * sheet.width / cols)
        y = round(i // cols * sheet.height / rows)
        box = (x + trim, y + trim, x + sheet.width // cols - trim, y + sheet.height // rows - trim)
        boxes.append(box)
        frames.append(np.array(sheet.crop(box)))
    palette = sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT).getpalette()
    frames = np.stack([rgb_from_ids(quantize(f, palette), palette) for f in frames])
    return frames, cfg['durations_ms'], palette, boxes, sheet.size


def alpha_sheet(path, boxes, canvas_size):
    with Image.open(path) as im:
        if im.size != canvas_size:
            raise ValueError(f'Matte canvas mismatch: {path}')
        if im.mode == 'RGBA':
            matte = im.getchannel('A')
        elif im.mode == 'L':
            matte = im.copy()
        else:
            raise ValueError('Matte must be grayscale alpha or RGBA; RGB is not inferred')
    return [np.array(matte.crop(box)) for box in boxes]


def repair_background(frames, palette, raw_masks, cfg):
    colors = np.asarray(palette, dtype='uint8').reshape(-1, 3)
    bg_index = int(np.argmin(np.sum((colors.astype(float) - cfg['target_rgb']) ** 2, axis=1)))
    bg = colors[bg_index]
    low, high = cfg.get('alpha_clip', [100, 200])
    result, masks = [], []
    for original, raw in zip(frames, raw_masks):
        alpha = np.rint(np.clip((raw.astype('float32') - low) / (high - low), 0, 1) * 255).astype('uint8')
        if cfg.get('ink_support'):
            ink = cfg['ink_support']
            red_low, red_high = ink['red_range']
            support = np.rint(np.clip((red_high - original[:, :, 0].astype(float)) / (red_high - red_low), 0, 1) * 255).astype('uint8')
            near = np.array(Image.fromarray((raw > low).astype('uint8') * 255).filter(ImageFilter.MaxFilter(ink['radius'] * 2 + 1))) > 0
            support[~near] = 0
            alpha = np.maximum(alpha, support)
        weight = alpha[:, :, None].astype(float) / 255
        composed = np.rint(original * weight + bg * (1 - weight)).astype('uint8')
        ids = quantize(composed, palette)
        ids[alpha == 255] = color_ids(original, palette)[alpha == 255]
        ids[alpha == 0] = bg_index
        result.append(rgb_from_ids(ids, palette))
        masks.append(alpha)
    return np.stack(result), np.stack(masks), bg


def ellipse_mask(x, y, values):
    cx, cy, rx, ry = values
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def stabilize(frames, palette, whole, raw_heads, cfg, bg, loop):
    n, height, width, _ = frames.shape
    yy, xx = np.mgrid[:height, :width]
    master = cfg.get('master', 0)
    heads = []
    for i, raw in enumerate(raw_heads):
        low, high = cfg.get('head_alpha_clip', [100, 200])
        head = np.clip((raw.astype(float) - low) / (high - low), 0, 1)
        if cfg.get('head_ink_support'):
            support = cfg['head_ink_support']
            near = np.array(Image.fromarray((head > .5).astype('uint8') * 255).filter(ImageFilter.MaxFilter(support['radius'] * 2 + 1))) > 0
            red_low, red_high = support['red_range']
            ink = np.clip((red_high - frames[i, :, :, 0].astype(float)) / (red_high - red_low), 0, 1)
            ink[~near | (yy >= cfg['ink_max_y'])] = 0
            head = np.maximum(head, ink)
        head = np.minimum(head, whole[i] / 255)
        head[yy >= cfg['head_clip_y']] = 0
        heads.append(head)
    heads = np.stack(heads)
    start, end = cfg['torso_transition_y']
    upper_dynamic = 1 - np.clip((yy - start) / (end - start), 0, 1)
    protect = np.zeros((height, width), dtype=bool)
    for values in cfg['protected_ellipses']:
        protect |= ellipse_mask(xx, yy, values)
    hair = cfg['hair_region']
    hair_region = (yy < hair['upper_y']) | (((xx < hair['left_x']) | (xx > hair['right_x'])) & (yy < hair['lower_y']))
    gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    estimator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    estimator.setUseSpatialPropagation(True)
    cache = {}
    def field(i, j):
        if (i, j) not in cache:
            cache[i, j] = estimator.calc(gray[i], gray[j], None)
        return cache[i, j]
    x, y = xx.astype('float32'), yy.astype('float32')
    def remap(a, mx, my):
        return cv2.remap(a, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    result, changes = [], []
    bg_index = {tuple(c): i for i, c in enumerate(np.array(palette).reshape(-1, 3).tolist())}[tuple(bg.tolist())]
    for i in range(n):
        total, weights = frames[i].astype(float).copy(), np.ones((height, width))
        for offset in [-2, -1, 1, 2]:
            j = (i + offset) % n if loop else min(max(i + offset, 0), n - 1)
            f, b = field(i, j), field(j, i)
            mx, my = x + f[:, :, 0], y + f[:, :, 1]
            warped = remap(frames[j], mx, my).astype(float)
            error = np.linalg.norm(f + remap(b, mx, my), axis=2)
            delta = np.mean((warped - frames[i].astype(float)) ** 2, axis=2)
            reliability = np.exp(-delta / (2 * 20 ** 2)) * np.clip(1 - error / .8, 0, 1)
            reliability *= .85 if abs(offset) == 1 else .5
            reliability *= (heads[i] > .95) & ~protect
            total += warped * reliability[:, :, None]
            weights += reliability
        filtered = total / weights[:, :, None]
        strength = cfg.get('reference_strength', 0)
        if strength:
            f, b = field(i, master), field(master, i)
            mx, my = x + f[:, :, 0], y + f[:, :, 1]
            anchored = remap(frames[master], mx, my).astype(float)
            anchor_head = remap(heads[master].astype('float32'), mx, my)
            error = np.linalg.norm(f + remap(b, mx, my), axis=2)
            stable = (heads[i] > .99) & (anchor_head > .99) & ~protect & hair_region
            alpha = strength * np.clip(1 - error / .8, 0, 1) * stable
            filtered = filtered * (1 - alpha[:, :, None]) + anchored * alpha[:, :, None]
        filtered[protect] = frames[i][protect]
        dynamic = np.maximum(heads[i], upper_dynamic)
        composed = np.rint(filtered * dynamic[:, :, None] + frames[master] * (1 - dynamic[:, :, None])).clip(0, 255).astype('uint8')
        ids = quantize(composed, palette)
        ids[protect] = color_ids(frames[i], palette)[protect]
        ids[(whole[i] == 0) & (whole[master] == 0)] = bg_index
        rgb = rgb_from_ids(ids, palette)
        core = protect & (heads[i] > .95)
        changes.append(int(np.count_nonzero(np.any(rgb[core] != frames[i][core], axis=1))))
        result.append(rgb)
    if any(changes):
        raise ValueError('Protected original expression pixels changed')
    return np.stack(result), {'protected_expression_changed_pixels': changes}


def interpolate(frames, durations, cfg, loop):
    n, height, width, _ = frames.shape
    pts = np.r_[0, np.cumsum(durations[:-1])].astype(int)
    period, step = sum(durations), cfg['step_ms']
    if period % step or np.any(pts % step):
        raise ValueError('Output interval must divide total duration and every source-key timestamp; no hidden retiming')
    static = np.all(frames == frames[0], axis=(0, 3))
    y, x = np.mgrid[:height, :width].astype('float32')
    estimator = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    estimator.setFinestScale(0)
    estimator.setUseSpatialPropagation(True)
    estimator.setVariationalRefinementIterations(10)
    gray, cache = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames], {}
    def field(i, j):
        if (i, j) not in cache:
            cache[i, j] = estimator.calc(gray[i], gray[j], None)
        return cache[i, j]
    def inverse(flow, amount):
        mx, my = x.copy(), y.copy()
        for _ in range(5):
            f = cv2.remap(flow, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
            mx, my = x - amount * f[:, :, 0], y - amount * f[:, :, 1]
        return mx, my
    eyes = cfg.get('eyes', [])
    masks = [cv2.GaussianBlur(ellipse_mask(x, y, e['ellipse']).astype('float32'), (0, 0), e.get('feather_px', 1.2)) for e in eyes]
    def white(frame, box):
        x0, y0, x1, y1 = box
        p = frame[y0:y1, x0:x1].astype(int)
        return int(np.count_nonzero((p[:, :, 2] > 174) & (p[:, :, 0] - p[:, :, 1] < 30) & (p[:, :, 1] > 205)))
    result, provenance = [], []
    for tick in range(0, period, step):
        i = int(np.searchsorted(pts, tick, side='right') - 1)
        j = (i + 1) % n if loop else min(i + 1, n - 1)
        amount = (tick - int(pts[i])) / durations[i]
        if amount == 0 or i == j:
            f = frames[i].copy()
        else:
            ab, ba = field(i, j), field(j, i)
            ax, ay = inverse(ab, amount)
            bx, by = inverse(ba, 1 - amount)
            wa = cv2.remap(frames[i], ax, ay, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101).astype(float)
            wb = cv2.remap(frames[j], bx, by, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101).astype(float)
            out = (wa if amount < .5 else wb).copy()
            for mask, eye in zip(masks, eyes):
                av, bv = white(frames[i], eye['white_box']), white(frames[j], eye['white_box'])
                patch = (wa if amount < .5 else wb) if abs(av - bv) < 4 else (wa if av > bv else wb)
                out = out * (1 - mask[:, :, None]) + patch * mask[:, :, None]
            f = np.rint(out).clip(0, 255).astype('uint8')
        f[static] = frames[0, static]
        result.append(f)
        provenance.append({'time_ms': tick, 'from_key': i, 'to_key': j, 'fraction': amount})
    return np.stack(result), [step] * len(result), pts, static, provenance


def encode(path, frames, times, palette, loop, background_index, keys=None, static=None):
    encoded = []
    for i, frame in enumerate(frames):
        indices = quantize(frame, palette)
        if static is not None:
            indices[static] = color_ids(keys[0], palette)[static]
        if keys is not None and i in keys:
            indices = color_ids(keys[i], palette)
        im = Image.fromarray(indices).convert('P')
        im.putpalette(palette)
        encoded.append(im)
    info = {'background': int(background_index), 'optimize': False}
    if loop:
        info['loop'] = 0
    header, _ = GifImagePlugin.getheader(encoded[0], palette=bytes(palette), info=info)
    with Path(path).open('xb') as stream:
        for block in header:
            stream.write(block)
        for frame, duration in zip(encoded, times):
            for block in GifImagePlugin.getdata(frame, duration=duration, disposal=1, include_color_table=False, optimize=False):
                stream.write(block)
        stream.write(b';')


def save_frames(directory, frames):
    directory.mkdir()
    for i, frame in enumerate(frames):
        Image.fromarray(frame).save(directory / f'{i:04}.png')


def contact_sheets(directory, frames, times, prefix='frames'):
    directory.mkdir(exist_ok=True)
    h, w = frames.shape[1:3]
    tile = min(w, 256)
    tile_height = round(h * tile / w)
    pts = np.r_[0, np.cumsum(times[:-1])]
    files = []
    for start in range(0, len(frames), 25):
        count = min(25, len(frames) - start)
        image = Image.new('RGB', (tile * 5, (tile_height + 20) * ((count + 4) // 5)), '#fbefdd')
        for j, i in enumerate(range(start, start + count)):
            thumb = Image.fromarray(frames[i]).resize((tile, tile_height), Image.Resampling.LANCZOS)
            x, y = j % 5 * tile, j // 5 * (tile_height + 20)
            image.paste(thumb, (x, y))
            ImageDraw.Draw(image).text((x + 4, y + tile_height + 2), f'{i:03} | {pts[i]/1000:.2f}s', fill='black')
        target = directory / f'{prefix}-{start//25+1:02}.png'
        image.save(target)
        files.append(target)
    return files
