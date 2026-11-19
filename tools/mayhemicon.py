"""The Mayhem category's icon for the career's Race Type list and the Mayhem series' logo (the user's
Mayhem career category, 3 Nov), drawn as tools/drifticon.py and tools/driftlogo.py draw the Drift ones.

The category icon: the disc icons' shared layout (drifticon.layout) in orange, glowing impact lines
bursting from the middle as the others' line art, and a car (tools/caricon.py's render) tipped over as if
thrown, with debris puffs, in the objects' grey and black. The series logo: MAYHEM in heavy white
letters on driftlogo's red-orange panel.

  blender -b --python tools/caricon.py -- <car.carbin> car.png 840 468 -40 22
  python tools/mayhemicon.py <disc> car.png <out folder>
      -> mayhem_cat_lg.png, mayhem_cat_sm.png (Events_LG.xpr / Events.xpr), mayhem_lg.png, mayhem_sm.png
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addseries
import drifticon as D
import driftlogo
import forzaxpr

HUE = 0.075  # orange: the disc's categories and Drift's red have none
TILT = 24    # degrees the car is tipped (thrown, about to roll)


def draw(disc, strip, w, h, car_png):
    K = D.K
    v, s, a = D.layout(D.disc_tiles(disc, strip, w, h))
    W, H = w * K, h * K
    v, s, a = D.up(v, K), D.up(s, K), D.up(a, K)
    rgb = D.from_hsv(np.full_like(v, HUE), s, v)
    # the line art: impact lines bursting from behind the car, through the dark part
    dark = np.clip((1 - v) * 1.4, 0, 1)[..., None] * (a[..., None] > 0.99)
    art = np.zeros((H, W, 3))
    lw = max(1.0, W / 210 * 0.9)
    cx, cy = W * 0.66, H * 0.5
    for k in range(11):
        t = -1.25 + k * 0.25
        r0, r1 = W * 0.16, W * (0.55 if k % 2 else 0.42)
        D.glow_line(art, [(cx + r0 * math.cos(t), cy + r0 * math.sin(t)), (cx + r1 * math.cos(t), cy + r1 * math.sin(t))],
                    lw, (1.0, 0.6, 0.25), 0.55)
    rgb = np.clip(rgb + art * dark, 0, 1)
    out = np.dstack([rgb, a])
    # the car, tipped, and debris puffs about it, as one object (drifticon's way)
    img = Image.open(car_png).convert('RGBA').rotate(TILT, resample=Image.BICUBIC, expand=True)
    img = img.crop(img.getbbox())
    tmp = os.path.join(os.path.dirname(os.path.abspath(car_png)), '_tipped.png')
    img.save(tmp)
    cw0 = int(W * 0.58)
    car = addseries.image(tmp, cw0, int(cw0 * img.height / img.width)).astype(float) / 255
    ch, cw = car.shape[:2]
    ch = min(ch, int(H * 0.92))
    car = car[:ch]
    ox, oy = int(W * 0.36), int(H * 0.04)
    obj = np.zeros((H, W, 4))
    obj[oy:oy + ch, ox:ox + cw] = car[:H - oy, :W - ox]
    sa, sg = np.zeros((H, W)), np.zeros((H, W))
    e = W / 210 * 1.6
    for fx, fy, fr in ((0.40, 0.80, 0.06), (0.47, 0.88, 0.05), (0.93, 0.30, 0.05), (0.97, 0.45, 0.04), (0.88, 0.86, 0.045)):
        D.puff(sa, sg, W * fx, H * fy, W * fr, e)
    smoke = np.dstack([sg, sg, sg, sa])
    oa = obj[..., 3:4]
    obj = np.dstack([obj[..., :3] * oa + smoke[..., :3] * smoke[..., 3:4] * (1 - oa), oa + smoke[..., 3:4] * (1 - oa)])
    obj[..., :3] = np.where(obj[..., 3:4] > 0, obj[..., :3] / np.maximum(obj[..., 3:4], 1e-6), 0)
    sh = np.zeros((H, W))
    dy, dx = int(H * 0.025), int(W * 0.012)
    sh[dy:, dx:] = obj[:-dy, :-dx, 3]
    for _ in range(3):
        sh = (sh + D.shift(sh, 2 * K, 0) + D.shift(sh, -2 * K, 0) + D.shift(sh, 0, 2 * K) + D.shift(sh, 0, -2 * K)) / 5
    out[..., :3] *= 1 - 0.55 * sh[..., None]
    out[..., 3] = np.maximum(out[..., 3], 0.55 * sh)
    oa = obj[..., 3:4]
    out[..., :3] = out[..., :3] * (1 - oa) + obj[..., :3] * oa
    out[..., 3] = np.maximum(out[..., 3], oa[..., 0])
    small = out.reshape(h, K, w, K, 4).mean((1, 3))
    return np.clip(small * 255 + 0.5, 0, 255).astype(np.uint8)


def word_art(path):
    """MAYHEM, dark on light, slanted, for driftlogo.tile."""
    im = Image.new('L', (1200, 400), 255)
    f = ImageFont.truetype(r'C:\Windows\Fonts\impact.ttf', 300)
    ImageDraw.Draw(im).text((600, 200), 'MAYHEM', font=f, fill=0, anchor='mm')
    im = im.transform(im.size, Image.AFFINE, (1, 0.22, -40, 0, 1, 0), resample=Image.BICUBIC, fillcolor=255)
    im = im.crop(Image.eval(im, lambda p: 255 - p).getbbox())
    im.save(path)


if __name__ == '__main__':
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    disc, car_png, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    for name, strip, (w, h) in (('mayhem_cat_lg', 'Events_LG.xpr', (210, 117)), ('mayhem_cat_sm', 'Events.xpr', (108, 60))):
        p = os.path.join(out, name + '.png')
        forzaxpr.png(p, np.ascontiguousarray(draw(disc, strip, w, h, car_png)))
        print(p)
    art = os.path.join(out, 'mayhem_word.png')
    word_art(art)
    for name, (w, h) in (('mayhem_lg', addseries.LG[:2]), ('mayhem_sm', addseries.SM[:2])):
        p = os.path.join(out, name + '.png')
        forzaxpr.png(p, np.ascontiguousarray(driftlogo.tile(art, w, h)))
        print(p)
