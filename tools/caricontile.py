"""Add-on cars' car-select tiles put in the disc's form, in place (media\\caricons<n>.xpr in the mods folder; 64 tiles
of 128 x 64, DXT5). The disc's tiles: alpha 127 all over, the car on grey (125, 126, 125), a black line round the
edge. The 4 Nov audit: the Gallardo's was a cut-out (alpha 0 or 255, no grey, the car to the edges), six others
(the M3 GTR MW's, SC63's, the Neons' and Celicas') had no edge line, and the D-Specs' were their base cars' tiles
over again. Options a car (by ordinal):

  --form        the disc's form: a cut-out laid on the grey (and the car fitted inside the edge), the edge line, alpha 127
  --badge       a small D-SPEC badge in the top left corner (the D-Specs: else the same tile as their base car's)

  python tools/caricontile.py <disc> <mods folder> [--preview <png>] <ordinal>[:form][:badge] ...
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import forzaxpr as fx

GREY = np.array([125, 126, 125])
TW, TH = 128, 64


def pack_path(disc, mods, o):
    n = 'caricons%d.xpr' % (o // 64 + 1)
    mp = os.path.join(mods, 'media', n)
    return (mp if os.path.exists(mp) else addcar.disc_file(disc, 'media', n)), mp


def form(t):
    """The tile in the disc's form."""
    t = t.astype(float)
    a = t[..., 3:4] / 255
    if np.unique(t[..., 3]).size > 2 or t[..., 3].min() < 100:  # (a cut-out: the car laid on the grey, fitted inside)
        rgb = t[..., :3] * a + GREY * (1 - a)
        on = np.nonzero(t[..., 3] > 40)
        if len(on[0]):
            y0, y1, x0, x1 = on[0].min(), on[0].max() + 1, on[1].min(), on[1].max() + 1
            car = Image.fromarray(np.clip(t[y0:y1, x0:x1], 0, 255).astype(np.uint8), 'RGBA')
            k = min((TW - 14) / car.width, (TH - 8) / car.height, 1.0)
            car = car.resize((max(1, int(car.width * k)), max(1, int(car.height * k))), Image.LANCZOS)
            base = Image.new('RGBA', (TW, TH), tuple(int(x) for x in GREY) + (255,))
            base.alpha_composite(car, ((TW - car.width) // 2, (TH - car.height) // 2 + 1))
            rgb = np.asarray(base, float)[..., :3]
    else:
        rgb = t[..., :3]
    out = np.dstack([rgb, np.full((TH, TW), 127.0)])
    out[0, :, :3] = out[-1, :, :3] = 0
    out[:, 0, :3] = out[:, -1, :3] = 0
    return np.clip(out, 0, 255).astype(np.uint8)


def badge(t):
    """A D-SPEC badge, top left, inside the edge."""
    K = 4
    im = Image.new('RGBA', (TW * K, TH * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(r'C:\Windows\Fonts\ariblk.ttf', 8 * K)
    w = d.textlength('D-SPEC', font=f)
    d.rounded_rectangle([3 * K, 3 * K, 3 * K + w + 6 * K, 3 * K + 11 * K], radius=2 * K, fill=(200, 30, 24, 255), outline=(255, 255, 255, 255), width=K)
    d.text((6 * K, 3 * K + 5.5 * K), 'D-SPEC', font=f, fill=(255, 255, 255, 255), anchor='lm')
    b = np.asarray(im.resize((TW, TH), Image.LANCZOS), float)
    a = b[..., 3:4] / 255
    out = t.astype(float)
    out[..., :3] = out[..., :3] * (1 - a) + b[..., :3] * a
    return np.clip(out, 0, 255).astype(np.uint8)


def main(disc, mods, specs, preview=None):
    packs, shown = {}, []
    for spec in specs:
        o, *ops = spec.split(':')
        o = int(o)
        src, dst = pack_path(disc, mods, o)
        if dst not in packs:
            d = bytearray(open(src, 'rb').read())
            t = fx.textures(d)[0]
            assert (t['w'], t['h'], t['format']) == (128, 4096, 0x0F), t
            packs[dst] = (d, t, fx.dxt(bytes(d[t['start']:]), t['w'], t['h'], 5).copy())
        d, t, img = packs[dst]
        tile = img[(o % 64) * TH:(o % 64 + 1) * TH].copy()
        if 'form' in ops: tile = form(tile)
        if 'badge' in ops: tile = badge(tile)
        img[(o % 64) * TH:(o % 64 + 1) * TH] = tile
        enc = fx.encode_dxt5(np.ascontiguousarray(tile))
        assert len(enc) == addcar.TILE
        off = t['start'] + (o % 64) * addcar.TILE
        d[off:off + addcar.TILE] = enc
        shown.append(fx.dxt(bytes(enc), TW, TH, 5))
        print('%d: %s' % (o, ', '.join(ops) or 'as it was'))
    if preview:
        Image.fromarray(np.hstack(shown)).save(preview)
        print(preview)
        return
    for dst, (d, _, _) in packs.items():
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(bytes(d))
        print(dst)


if __name__ == '__main__':
    a = sys.argv[1:]
    prev = None
    if '--preview' in a:
        i = a.index('--preview'); prev = a[i + 1]; del a[i:i + 2]
    if len(a) < 3: raise SystemExit(__doc__)
    main(a[0], a[1], a[2:], prev)
