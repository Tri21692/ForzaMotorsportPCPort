"""The Drift category's icon for the career's Race Type list, as the disc's eight are drawn
(media/Events/Events_LG.xpr 210 x 117, Events.xpr 108 x 60): a white striped arc on the left, a
coloured band, a dark gradient with faint line art, and a white object outlined in black. The object
is the user's drifting car (a white car with speed lines on a light grey disc: what is near white
is the car, the grey inside it its windows).

  python tools/drifticon.py <car icon image> <out folder>   -> drift_cat_lg.png, drift_cat_sm.png
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addseries
import forzaxpr

BAND, DEEP = np.array([214, 40, 32]), np.array([40, 6, 8])  # red: no other category has it


def car_masks(path, w, h):
    """(fill, windows) coverage of the car fitted into w x h, from the icon's near-white."""
    src = addseries.image(path, 2 * w, 2 * h).astype(float)
    lum = src[..., :3].mean(-1)
    yy, xx = np.mgrid[0:src.shape[0], 0:src.shape[1]]
    lum[np.hypot((xx - src.shape[1] / 2) / src.shape[1], (yy - src.shape[0] / 2) / src.shape[0]) > 0.4] = 0  # (not the disc's rim)
    fill = np.clip((lum - 236) / 14, 0, 1)
    ys, xs = np.nonzero(fill > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    # the windows: grey holes inside the car's box, under the white
    box = lum[y0:y1, x0:x1]
    f = fill[y0:y1, x0:x1]
    inner = np.zeros_like(f, bool)
    for r in range(f.shape[0]):  # grey between white on the same row
        on = np.nonzero(f[r] > 0.5)[0]
        if len(on) > 1: inner[r, on[0]:on[-1]] = True
    win = (inner & (f < 0.5) & (box < 236)).astype(float)
    k = min(w / f.shape[1], h / f.shape[0])
    nw, nh = int(f.shape[1] * k), int(f.shape[0] * k)
    def down(m):
        ey = np.linspace(0, m.shape[0], nh + 1).astype(int)[:-1]
        ex = np.linspace(0, m.shape[1], nw + 1).astype(int)[:-1]
        s = np.add.reduceat(np.add.reduceat(m, ey, 0), ex, 1)
        return s / np.outer(np.diff(np.r_[ey, m.shape[0]]), np.diff(np.r_[ex, m.shape[1]]))
    return down(f), down(win)


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx <= r * r: out = np.maximum(out, np.roll(np.roll(m, dy, 0), dx, 1))
    return out


def tile(icon, w, h, k=4):
    """The tile, drawn k times as big and each k x k block averaged: smooth edges (drawn at size, the
    outline and the speed lines came out ragged, the user's 'scuffed')."""
    big = draw(icon, w * k, h * k).astype(float)
    return big.reshape(h, k, w, k, 4).mean((1, 3)).round().astype(np.uint8)


def draw(icon, w, h):
    s = w / 210.0
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    # the dark gradient, lighter low on the left
    t = np.clip(xx / w * 0.8 + yy / h * 0.2, 0, 1)[..., None]
    img = BAND * 0.55 * (1 - t) + DEEP * t
    # faint line art: arcs like a skid's curves, about a point off to the right
    rr = np.hypot(xx - w * 1.05, yy - h * 1.3)
    for r0 in (0.55, 0.75, 0.95, 1.15):
        img += 70 * np.clip(1 - np.abs(rr - r0 * w) / (1.2 * s), 0, 1)[..., None] * np.array([1.0, 0.45, 0.4]) * 0.35
    # the coloured band and the white arc with stripes, two circles off the left edge
    c1 = np.hypot(xx + w * 1.9, yy - h * 0.5)
    band = c1 < w * 2.36
    img[band] = BAND * (0.85 + 0.15 * (1 - yy[band] / h))[:, None]
    arc = c1 < w * 2.02
    stripe = ((xx + yy) // (7 * s)) % 2 == 0
    img[arc] = np.where(stripe[arc][:, None], 250, 228)
    # the car, outlined: within 84% of the tile, a little right of centre as the others
    fill, win = car_masks(icon, int(w * 0.66), int(h * 0.8))
    m = np.zeros((h, w)); wm = np.zeros((h, w))
    oy, ox = int((h - fill.shape[0]) / 2), int(w * 0.24 + (w * 0.66 - fill.shape[1]) / 2)
    m[oy:oy + fill.shape[0], ox:ox + fill.shape[1]] = fill
    wm[oy:oy + fill.shape[0], ox:ox + fill.shape[1]] = win
    edge = dilate(np.maximum(m, wm), max(1, int(round(2.5 * s))))
    img = img * (1 - edge[..., None])                            # black outline
    img = img * (1 - m[..., None]) + 255 * m[..., None]           # white body
    img = img * (1 - wm[..., None]) + np.array([118, 118, 124]) * wm[..., None]  # grey windows, as the helmets' visors
    return np.dstack([np.clip(img, 0, 255).astype(np.uint8), np.full((h, w), 255, np.uint8)])


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    os.makedirs(sys.argv[2], exist_ok=True)
    for name, (w, h) in (('drift_cat_lg', (210, 117)), ('drift_cat_sm', (108, 60))):
        p = os.path.join(sys.argv[2], name + '.png')
        forzaxpr.png(p, np.ascontiguousarray(tile(sys.argv[1], w, h)))
        print(p)
