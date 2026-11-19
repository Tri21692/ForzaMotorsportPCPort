"""The drift series' logo (the user's DRIFT art, 1 Nov) as the series list draws its logos: a tile of
the large strip (210 x 117) and of the small one (108 x 60), the art in white with a dark shadow on a
red-orange panel with a lighter slash, as the disc's coloured logos are.

  python tools/driftlogo.py <art image (dark on light)> <out folder>   -> drift_lg.png, drift_sm.png
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addseries
import forzaxpr


def tile(art_path, w, h):
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    t = np.clip((xx / w * 0.7 + yy / h * 0.3), 0, 1)[..., None]
    bg = np.array([150, 18, 12]) * (1 - t) + np.array([245, 120, 20]) * t           # deep red to orange
    slash = np.clip(1 - np.abs((xx - w * 0.62) - (h - yy) * 0.5) / (w * 0.06), 0, 1)[..., None]
    bg = bg * (1 - 0.25 * slash) + 255 * 0.25 * slash
    bg *= (0.72 + 0.28 * (1 - yy / h))[..., None]                                       # darker at the foot
    # the art fitted in 90% of the tile, its darkness as coverage
    src = addseries.image(art_path, 4 * w, 4 * h)                                    # (big, then boxed down)
    cov = 1 - src[..., :3].mean(-1) / 255.0
    cov = np.where(src[..., 3] > 0, cov, 0)
    ys, xs = np.nonzero(cov > 0.3)
    cov = cov[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    k = min(0.9 * w / cov.shape[1], 0.86 * h / cov.shape[0])
    nw, nh = max(1, int(cov.shape[1] * k)), max(1, int(cov.shape[0] * k))
    ey = np.linspace(0, cov.shape[0], nh + 1).astype(int)[:-1]  # each texel the mean of its block (smooth edges)
    ex = np.linspace(0, cov.shape[1], nw + 1).astype(int)[:-1]
    small = np.add.reduceat(np.add.reduceat(cov, ey, 0), ex, 1)
    small /= np.outer(np.diff(np.r_[ey, cov.shape[0]]), np.diff(np.r_[ex, cov.shape[1]]))
    a = np.zeros((h, w))
    oy, ox = (h - nh) // 2, (w - nw) // 2
    a[oy:oy + nh, ox:ox + nw] = small
    off = max(1, w // 105)
    sh = np.roll(np.roll(a, off, 0), off, 1)
    out = bg * (1 - 0.7 * sh[..., None])
    out = out * (1 - a[..., None]) + 255 * a[..., None]
    return np.dstack([np.clip(out, 0, 255).astype(np.uint8), np.full((h, w), 255, np.uint8)])


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    os.makedirs(sys.argv[2], exist_ok=True)
    for name, (w, h) in (('drift_lg', addseries.LG[:2]), ('drift_sm', addseries.SM[:2])):
        p = os.path.join(sys.argv[2], name + '.png')
        forzaxpr.png(p, np.ascontiguousarray(tile(sys.argv[1], w, h)))
        print(p)
