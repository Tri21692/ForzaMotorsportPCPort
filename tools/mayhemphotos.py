"""The Mayhem Moments' photographs (the user's: "a render of each Mayhem Moment as a photograph", after their
reference: a tilted instant photo, clipped on with a paperclip, the Moment's name handwritten under the picture;
"with a Forza twist": the track's name in smaller hand under it, and a red FORZA-style date stamp in the corner).
Each from a picture of the game at the Moment's place (the runtime's XBRT_MM_PHOTO run saves them, mm<i>_<k>.ppm;
the best one picked by hand), the middle of it kept (the game's HUD in the corners), one sheet for F1's Mayhem
Moments page (runtime/glover.c), a tile each in the Moments' order (<mods>/mayhem.txt), four a row, with alpha.

  python tools/mayhemphotos.py <mods folder> <picture for Moment 0> <picture for Moment 1> ...
      -> <mods>/moments/photos.rgba ("MMPH", u32 width, height, columns, rows, 0, then RGBA rows), photos.png beside it
"""
import math
import os
import random
import re
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

T = 256          # a tile (square: the photo tilted inside it, with its shadow)
COLS = 4
PW, PH = 196, 232           # the instant photo's card
IW, IH = 172, 150           # its picture, 12 in from the sides and top
CROP = (0.18, 0.10, 0.82, 0.62)  # the part of the game's picture kept (its HUD sits in the corners)
HAND = r'C:\Windows\Fonts\Inkfree.ttf'
TRACKS = {17: 'Tokyo', 20: 'Pacific Shipyards', 10: 'Fujimi Kaido', 18: 'New York', 9: 'Road Atlanta',
          25: 'Rio de Janeiro', 5: 'Sunset Peninsula', 3: 'Maple Valley'}


def picture(path):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    l, t, r, b = CROP
    box = [w * l, h * t, w * r, h * b]
    want = IW / IH
    cw, ch = box[2] - box[0], box[3] - box[1]
    if cw / ch > want: d = (cw - ch * want) / 2; box[0] += d; box[2] -= d
    else: d = (ch - cw / want) / 2; box[1] += d; box[3] -= d
    a = np.asarray(im.crop(tuple(int(round(v)) for v in box)).resize((IW, IH), Image.LANCZOS), float) / 255
    a = a * np.array([1.05, 1.0, 0.9]) + np.array([0.03, 0.015, 0.0])   # an instant film's warmth
    a = 0.05 + a * 0.9                                                    # its faded blacks
    yy, xx = np.mgrid[0:IH, 0:IW]
    r2 = ((xx - IW / 2) / (IW / 2)) ** 2 + ((yy - IH / 2) / (IH / 2)) ** 2
    a *= (1 - 0.3 * np.clip(r2 - 0.4, 0, 1))[..., None]
    return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8))


def fit_font(draw, text, width, size):
    while size > 10:
        f = ImageFont.truetype(HAND, size)
        if draw.textlength(text, font=f) <= width: return f
        size -= 1
    return ImageFont.truetype(HAND, size)


def card(path, name, track, seed):
    rnd = random.Random(seed)
    K = 3  # drawn three times as big, then down (smooth edges and lettering)
    c = Image.new('RGBA', (PW * K, PH * K), (246, 244, 236, 255))
    c.paste(picture(path).resize((IW * K, IH * K), Image.LANCZOS), (12 * K, 12 * K))
    d = ImageDraw.Draw(c)
    d.rectangle([12 * K, 12 * K, (12 + IW) * K - 1, (12 + IH) * K - 1], outline=(70, 66, 60, 255), width=K)
    ink = (28, 30, 38, 255)
    f = fit_font(d, name.upper(), (PW - 24) * K, 30 * K)
    d.text((PW * K / 2, (12 + IH + 26) * K), name.upper(), font=f, fill=ink, anchor='mm')
    d.text((PW * K / 2, (12 + IH + 54) * K), track, font=ImageFont.truetype(HAND, 14 * K), fill=(60, 64, 80, 255), anchor='mm')
    # the Forza touch: a red rubber stamp in the picture's top right corner
    st = Image.new('RGBA', (84 * K, 28 * K), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    red = (200, 30, 24, 210)
    sd.rounded_rectangle([2 * K, 2 * K, 82 * K, 26 * K], radius=4 * K, outline=red, width=2 * K)
    sd.text((42 * K, 14 * K), 'MAYHEM', font=ImageFont.truetype(r'C:\Windows\Fonts\impact.ttf', 16 * K), fill=red, anchor='mm')
    st = st.rotate(rnd.uniform(8, 14), resample=Image.BICUBIC, expand=True)
    c.alpha_composite(st, ((12 + IW) * K - st.width - 6 * K, 16 * K))
    c = c.resize((PW, PH), Image.LANCZOS)
    # tilted, with a soft shadow, on a clear tile; a paperclip over the top edge
    ang = rnd.uniform(-7, 7)
    tile = Image.new('RGBA', (T, T), (0, 0, 0, 0))
    rot = c.rotate(ang, resample=Image.BICUBIC, expand=True)
    sh = Image.new('RGBA', rot.size, (0, 0, 0, 0))
    sh.putalpha(rot.getchannel('A').point(lambda v: v * 0.45))
    sh = sh.filter(ImageFilter.GaussianBlur(4))
    ox, oy = (T - rot.width) // 2, (T - rot.height) // 2
    tile.alpha_composite(sh, (ox + 4, oy + 5))
    tile.alpha_composite(rot, (ox, oy))
    clip = Image.new('RGBA', (40 * K, 80 * K), (0, 0, 0, 0))
    cd = ImageDraw.Draw(clip)
    steel = (150, 156, 166, 255)
    for (x0, y0, x1, y1) in ((4, 4, 34, 76), (10, 14, 28, 62)):  # the wire's two loops
        cd.rounded_rectangle([x0 * K, y0 * K, x1 * K, y1 * K], radius=(x1 - x0) // 2 * K, outline=steel, width=3 * K)
    cd.rectangle([0, 40 * K, 40 * K, 46 * K], fill=(0, 0, 0, 0))  # (its lower half behind the card: cut)
    clip = clip.resize((40, 80), Image.LANCZOS).rotate(ang + rnd.uniform(-10, 4), resample=Image.BICUBIC, expand=True)
    tile.alpha_composite(clip, (int(T * 0.24), 2))
    return np.asarray(tile)


def main(mods, pictures):
    lines = [l for l in open(os.path.join(mods, 'mayhem.txt')).read().splitlines() if l.startswith('moment ')]
    order = []
    for l in lines:
        m = re.match(r'moment (\d+) \S+ \S+ \S+ \S+ ([^|]*)\|', l)
        if m and m.group(2) not in [n for n, _ in order]: order.append((m.group(2), int(m.group(1))))
    rows = (len(pictures) + COLS - 1) // COLS
    sheet = np.zeros((rows * T, COLS * T, 4), np.uint8)
    for i, p in enumerate(pictures):
        name, track = order[i]
        y, x = i // COLS * T, i % COLS * T
        sheet[y:y + T, x:x + T] = card(p, name, TRACKS.get(track, ''), i)
    out = os.path.join(mods, 'moments')
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'photos.rgba'), 'wb') as f:
        f.write(b'MMPH' + struct.pack('<5I', COLS * T, rows * T, COLS, rows, 0) + sheet.tobytes())
    Image.fromarray(sheet).save(os.path.join(out, 'photos.png'))
    print(os.path.join(out, 'photos.rgba'), sheet.shape)


if __name__ == '__main__':
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
