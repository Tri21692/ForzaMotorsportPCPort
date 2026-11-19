"""A career category's video of our own (the user's, 15 Nov: "custom, cool video renders for the time trial, drift,
and Mayhem categories"): a montage of cuts from recorded pictures (XBRT_PRESENT_SHOT at 66 ms: a replay's cameras,
a Mayhem run's takedowns), packed as the .clip runtime/hle_clip.c paints over media/Events/<category>.bik (the
disc's are 486 x 364, 900 frames at 29.97 a second: 450 clip frames, each shown for two).

  python tools/catclip.py <out.clip> <folder>:<first>:<count> [<folder>:<first>:<count> ...]

Each cut is count pictures of its folder from picture number first (p_<n>.ppm); the cuts are joined with a
short cross-fade, and the last fades into the first, since the movie loops. CLIP_CROP=x0,y0,x1,y1 crops every
picture first (fractions). The file: makeclip.py's ("FZCL", width, height, frames, repeat, offsets, zlib RGB565).
A preview strip is written beside it as <out>.jpg.
"""
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image

W, H, REPEAT, FADE = 324, 243, 2, 5
CROP = tuple(float(x) for x in os.environ['CLIP_CROP'].split(',')) if os.environ.get('CLIP_CROP') else (0.0, 0.0, 1.0, 1.0)


def picture(folder, n):
    for name in ('p_%d.ppm' % n, 'p_%03d.ppm' % n, 'p_%04d.ppm' % n):
        f = os.path.join(folder, name)
        if os.path.exists(f):
            im = Image.open(f).convert('RGB')
            w, h = im.size
            im = im.crop((int(CROP[0] * w), int(CROP[1] * h), int(CROP[2] * w), int(CROP[3] * h))).resize((W, H), Image.LANCZOS)
            return np.asarray(im).astype(np.float32)
    raise SystemExit('no picture %d in %s' % (n, folder))


def main(out, *cuts):
    segs = []
    for c in cuts:
        folder, first, count = c.rsplit(':', 2)
        segs.append([picture(folder, int(first) + i) for i in range(int(count))])
    frames = []
    for k, s in enumerate(segs):
        nxt = segs[(k + 1) % len(segs)]
        body = s[:-FADE] if len(s) > 2 * FADE else s
        if k == 0: body = body[FADE:] if len(segs) > 1 else body  # (its first pictures are the last cut's fade-in)
        else: body = body[FADE:]
        frames += body
        if len(s) > 2 * FADE and len(nxt) > 2 * FADE:
            for i in range(FADE):
                t = (i + 1) / (FADE + 1)
                frames.append(s[len(s) - FADE + i] * (1 - t) + nxt[i] * t)
    blobs = []
    for a in frames:
        a = np.clip(a, 0, 255).astype(np.uint16)
        px = (a[..., 0] >> 3) << 11 | (a[..., 1] >> 2) << 5 | a[..., 2] >> 3
        blobs.append(zlib.compress(px.astype('<u2').tobytes(), 9))
    n = len(blobs)
    off, at = [], 20 + 4 * (n + 1)
    for b in blobs: off.append(at); at += len(b)
    off.append(at)
    with open(out, 'wb') as f:
        f.write(b'FZCL' + struct.pack('<4I', W, H, n, REPEAT) + struct.pack('<%dI' % (n + 1), *off) + b''.join(blobs))
    print('%s: %d frames (%.1f s) of %d x %d, %.1f MB' % (out, n, n * REPEAT / 29.97, W, H, at / 2 ** 20))
    pick = frames[::max(1, n // 24)][:24]
    sheet = Image.new('RGB', (W * 6, H * 4))
    for i, a in enumerate(pick): sheet.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), ((i % 6) * W, (i // 6) * H))
    sheet.save(out + '.jpg', quality=85)


if __name__ == '__main__':
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    main(sys.argv[1], *sys.argv[2:])
