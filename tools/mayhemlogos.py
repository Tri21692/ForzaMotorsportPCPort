"""Each Mayhem series its own logo (the 4 Nov audit: all eight showed the same MAYHEM tile, so the series' strip
in Event Select was eight identical tiles): MAYHEM over the series' name in heavy slanted letters, on a panel of
its own colour (driftlogo's gradient and slash), tiles FIRST.. of ico_events_lg/sm in every language, and each
series' Icon pointed at its tile, in place (tools/mayhemseries.py, run again, would give the series new ordinals).
Idempotent.

  python tools/mayhemlogos.py <disc> <mods folder> [<preview png>]
"""
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import mayhemseries

FIRST = 51  # (51 the shared one before: the first series keeps it)
IMPACT = r'C:\Windows\Fonts\impact.ttf'
# a panel colour pair (dark, light) per series, in mayhemseries.SERIES' order
COLOURS = [((40, 30, 90), (230, 150, 30)),    # Tunnel Vision: night blue to tunnel-lamp amber
           ((20, 60, 90), (40, 170, 200)),    # Dockyard Demolition: harbour blue
           ((30, 70, 30), (150, 200, 60)),    # Mountain Wreckage: forest green
           ((90, 10, 60), (240, 60, 120)),    # Big Apple Brawl: magenta
           ((150, 18, 12), (245, 120, 20)),   # Peach State Pileup: the red-orange of before
           ((10, 90, 60), (250, 210, 40)),    # Rio Rumble: green and gold
           ((110, 40, 10), (250, 170, 60)),   # Infield Insanity: sunset orange
           ((60, 20, 20), (200, 40, 40))]     # Valley of Carnage: deep red


def logo(name, colours, w, h):
    K = 4
    W, H = w * K, h * K
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    t = np.clip(xx / W * 0.7 + yy / H * 0.3, 0, 1)[..., None]
    bg = np.array(colours[0]) * (1 - t) + np.array(colours[1]) * t
    slash = np.clip(1 - np.abs((xx - W * 0.62) - (H - yy) * 0.5) / (W * 0.06), 0, 1)[..., None]
    bg = bg * (1 - 0.25 * slash) + 255 * 0.25 * slash
    bg *= (0.72 + 0.28 * (1 - yy / H))[..., None]
    # the letters: MAYHEM a band at the top, the name under it (one line, or two if long), as coverage
    cov = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(cov)
    def fit(text, width, height):
        s = int(height)
        while s > 6:
            f = ImageFont.truetype(IMPACT, s)
            l, tp, r, b = d.textbbox((0, 0), text, font=f)
            if r - l <= width and b - tp <= height: return f, (l, tp, r, b)
            s -= 1
        return ImageFont.truetype(IMPACT, s), d.textbbox((0, 0), text, font=ImageFont.truetype(IMPACT, s))
    words = name.upper().split()
    lines = [' '.join(words)] if len(name) <= 12 or len(words) == 1 else [' '.join(words[:len(words) // 2 + len(words) % 2 - (1 if len(words) == 3 else 0)]), ' '.join(words[len(words) // 2 + len(words) % 2 - (1 if len(words) == 3 else 0):])]
    # (the user's: MAYHEM in italics, the series' name upright; the name's lines one size, the block centred)
    fm, (ml, mt, mr, mb) = fit('MAYHEM', W * 0.56, H * 0.22)
    gap, lgap = H * 0.05, H * 0.03
    room = H * 0.86 - (mb - mt) - gap
    each = (room - lgap * (len(lines) - 1)) / len(lines)
    fs = [fit(ln, W * 0.84, each) for ln in lines]
    fn = min((f for f, _ in fs), key=lambda f: f.size)  # (the smaller of the lines' fits for both)
    boxes = [d.textbbox((0, 0), ln, font=fn) for ln in lines]
    lh = max(b - tp for _, tp, _, b in boxes)
    total = (mb - mt) + gap + lh * len(lines) + lgap * (len(lines) - 1)
    y0 = (H - total) / 2
    my = Image.new('L', (W, H), 0)  # MAYHEM on its own layer, slanted about its own middle (stays centred)
    ImageDraw.Draw(my).text((W / 2 - (ml + mr) / 2, y0 - mt), 'MAYHEM', font=fm, fill=255)
    cy = y0 + (mb - mt) / 2
    my = my.transform(my.size, Image.AFFINE, (1, 0.2, -0.2 * cy, 0, 1, 0), resample=Image.BICUBIC)
    y = y0 + (mb - mt) + gap
    for ln, (l, tp, r, b) in zip(lines, boxes):
        d.text((W / 2 - (l + r) / 2, y + (lh - (b - tp)) / 2 - tp), ln, font=fn, fill=255)
        y += lh + lgap
    cov = Image.fromarray(np.maximum(np.asarray(cov), np.asarray(my)))
    a = np.asarray(cov.resize((w, h), Image.LANCZOS), float) / 255
    bgs = np.asarray(Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).resize((w, h), Image.LANCZOS), float)
    off = max(1, w // 105)
    sh = np.roll(np.roll(a, off, 0), off, 1)
    out = bgs * (1 - 0.7 * sh[..., None])
    out = out * (1 - a[..., None]) + 255 * a[..., None]
    return np.dstack([np.clip(out, 0, 255).astype(np.uint8), np.full((h, w), 255, np.uint8)])


def main(disc, mods, preview=None):
    names = [s[0] for s in mayhemseries.SERIES]
    tiles = {n: (logo(n, COLOURS[i], *addseries.LG[:2]), logo(n, COLOURS[i], *addseries.SM[:2])) for i, n in enumerate(names)}
    if preview:
        Image.fromarray(np.vstack([np.hstack([tiles[n][0] for n in names[:4]]), np.hstack([tiles[n][0] for n in names[4:]])])).save(preview)
        print(preview)
        if mods == '-': return
    # the series' Icon, by its name, in place
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    for i, n in enumerate(names):
        k = next(k for k, v in mega.files.items() if k.lower().startswith('events\\mayhem\\') and ('displayname="%s"' % n).encode() in v[:400])
        x = mega.files[k].decode('latin-1')
        x = re.sub(r'(<series [^>]*Icon=")\d+(")', lambda m: '%s%d%s' % (m.group(1), FIRST + i, m.group(2)), x, count=1)
        mega.files[k] = x.encode('latin-1')
        print(k, n, 'logo', FIRST + i)
    mega.check(); mega.write()
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    for k in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
        if not m: continue
        lg = m.group(1).lower() == 'lg'
        size = addseries.LG if lg else addseries.SM
        while addseries.tiles_in(xpr.files[k], size) <= FIRST + len(names) - 1: xpr.files[k] = addseries.grow(xpr.files[k], size)
        for i, n in enumerate(names):
            xpr.files[k] = addseries.put_tile(xpr.files[k], FIRST + i, tiles[n][0 if lg else 1], size)
    xpr.check(); xpr.write()
    print('logos: tiles %d-%d' % (FIRST, FIRST + len(names) - 1))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    main(*sys.argv[1:])
