"""Rear-Engine Rebellion's own logo (the user's, 15 Nov: "Make custom event icons like you did before for the
other events"): it showed the Class S tile, the small strip having been full on 1 Nov. In the layout tiles' manner
(FF, FR, MR: a chassis plan behind the letters) in a rebel's red: the chassis seen from above, nose to the left,
its engine lit behind the rear axle; REAR-ENGINE and REBELLION lettered as the official logos are
(amateurseries.logo). Tile 59 of ico_events_lg/sm in every language, and the series' Icon pointed at it, in
place (tools/proseries.py, run again, would give the series new ordinals). Idempotent.

  python tools/rearlogo.py <disc> <mods folder> [<preview png>]      (mods "-": the preview only)
"""
import os
import re
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import amateurseries as A

TILE = 59
NAME = 'Rear-Engine Rebellion'
CAPTIONS = [('REAR-ENGINE', 3, 25, 'category'), ('REBELLION', 90, 20, 'chrome')]


def art():
    """210 x 117 RGBA floats: the red panel and the chassis plan."""
    w, h = addseries.LG[:2]
    K = 4
    W, H = w * K, h * K
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    # the panel: the layout tiles' bands (a lighter middle, darker top and foot) in crimson, a sweep of light from the right
    band = np.where(np.abs(yy / H - 0.5) < 0.25, 1.0, 0.72)
    base = np.array((150, 14, 22.0)) * band[..., None]
    glow = np.clip(1 - np.hypot((xx - W * 0.80) / (W * 0.5), (yy - H * 0.52) / (H * 0.7)), 0, 1)[..., None]
    base = base + np.array((105, 55, 10.0)) * glow ** 1.5
    base *= (0.86 + 0.14 * np.sin(yy / H * np.pi))[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert('RGBA')
    # the chassis plan, a lighter tint of the panel, as the layout tiles': wheels, axles, the spine, the cabin's cage
    plan = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(plan)
    tint = (235, 120, 110, 150)
    cy = H * 0.50
    fx, rx = W * 0.20, W * 0.74            # the axles: front (left), rear
    half = H * 0.20                        # the track's half width
    tw, tl = H * 0.075, W * 0.10          # a tyre: width, length
    for ax, wide in ((fx, 1.0), (rx, 1.25)):
        for s in (-1, 1):
            y = cy + s * half
            d.rounded_rectangle((ax - tl / 2, y - tw * wide / 2, ax + tl / 2, y + tw * wide / 2), radius=tw * 0.3, fill=tint)
            d.line((ax, y, ax, cy + s * H * 0.06), fill=tint, width=int(H * 0.022))                      # the half shaft
    d.line((fx, cy, rx, cy), fill=tint, width=int(H * 0.03))                                             # the spine
    d.rounded_rectangle((W * 0.34, cy - H * 0.13, W * 0.60, cy + H * 0.13), radius=H * 0.05, outline=tint, width=int(H * 0.018))  # the cabin
    d.line((W * 0.44, cy - H * 0.13, W * 0.44, cy + H * 0.13), fill=tint, width=int(H * 0.012))
    # the engine, behind the rear axle and lit: a flat six, three pots a side, and its gearbox ahead of it
    hot = (255, 214, 120, 255)
    ex0, ex1 = rx + W * 0.035, rx + W * 0.165
    d.rounded_rectangle((rx - W * 0.075, cy - H * 0.05, rx + W * 0.04, cy + H * 0.05), radius=H * 0.02, fill=(255, 170, 110, 220))
    d.rounded_rectangle((ex0, cy - H * 0.075, ex1, cy + H * 0.075), radius=H * 0.02, fill=hot)
    for i in range(3):
        x = ex0 + (ex1 - ex0) * (i + 0.5) / 3
        for s in (-1, 1):
            d.rounded_rectangle((x - W * 0.016, cy + s * H * 0.085 - H * 0.03, x + W * 0.016, cy + s * H * 0.085 + H * 0.085 * 0.6), radius=H * 0.012, fill=hot) if s > 0 else \
                d.rounded_rectangle((x - W * 0.016, cy - H * 0.085 - H * 0.085 * 0.6, x + W * 0.016, cy - H * 0.085 + H * 0.03), radius=H * 0.012, fill=hot)
    halo = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((rx - W * 0.02, cy - H * 0.24, ex1 + W * 0.09, cy + H * 0.24), fill=(255, 150, 40, 120))
    img = Image.alpha_composite(img, halo.filter(ImageFilter.GaussianBlur(H * 0.07)))
    img = Image.alpha_composite(img, plan)
    return np.asarray(img.resize((w, h), Image.LANCZOS), float).copy()


def logos(disc, mods):
    with tempfile.TemporaryDirectory() as tmp:
        lg = np.asarray(Image.open(A.logo(disc, mods, dict(image=art()), CAPTIONS, tmp)).convert('RGBA')).copy()
    sm = np.asarray(Image.fromarray(lg).resize(addseries.SM[:2], Image.LANCZOS)).copy()
    lg[..., 3] = sm[..., 3] = 255
    return lg, sm


def main(disc, mods, preview=None):
    lg, sm = logos(disc, None if mods == '-' else mods)
    if preview:
        Image.fromarray(lg).resize((lg.shape[1] * 3, lg.shape[0] * 3), Image.LANCZOS).save(preview)
        Image.fromarray(sm).save(preview[:-4] + '_sm.png')
        print(preview)
    if mods == '-': return
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    k = next(k for k, v in mega.files.items() if k.lower().startswith('events' + chr(92)) and ('displayname="%s"' % NAME).encode() in v[:400])
    x = mega.files[k].decode('latin-1')
    x = re.sub(r'(<series [^>]*Icon=")\d+(")', lambda m: '%s%d%s' % (m.group(1), TILE, m.group(2)), x, count=1)
    mega.files[k] = x.encode('latin-1')
    mega.check(); mega.write()
    print(k, 'logo', TILE)
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    n = 0
    for k in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
        if not m: continue
        big = m.group(1).lower() == 'lg'
        size = addseries.LG if big else addseries.SM
        while addseries.tiles_in(xpr.files[k], size) <= TILE: xpr.files[k] = addseries.grow(xpr.files[k], size)
        xpr.files[k] = addseries.put_tile(xpr.files[k], TILE, lg if big else sm, size)
        n += 1
    xpr.check(); xpr.write()
    print('logo: tile %d in %d strips' % (TILE, n))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    main(*sys.argv[1:])
