"""The Drift category's icon for the career's Race Type list, drawn as the disc's eight are
(media/Events/Events_LG.xpr 210 x 117, Events.xpr 108 x 60).

The disc's icons share one layout: clear on the left, a white striped arc, a coloured band the menu
shows through (alpha 217), a dark gradient with thin glowing line art, a white line along the top and
bottom, and a light grey object outlined in black. The layout here is the disc's own: each pixel the
median of the eight icons over those where it is not part of their object (coloured, or see-through),
recoloured red. On it: glowing skid-mark curves, and the car (tools/caricon.py's render of a
Silvia, a drift car) with tyre smoke, in the objects' grey and black.

  blender -b --python tools/caricon.py -- <car.carbin> car.png 840 468 35 14
  python tools/drifticon.py <disc> car.png <out folder>   -> drift_cat_lg.png, drift_cat_sm.png

The first icon (1 Nov) was drawn from scratch: solid where the others are see-through, its bands
straight and its car traced from a picture, the user's "scuffed" and not like the others.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import forzaxpr

HUE = 0.0  # red: no disc category has it
K = 4      # drawn K times as big, each K x K block averaged


def disc_tiles(disc, name, w, h):
    d = open(addcar.disc_file(disc, 'media', 'Events', name), 'rb').read()
    hdr, sw, sh, pitch = addseries.linear(d)
    px = np.frombuffer(d[hdr:hdr + pitch * sh], np.uint8).reshape(sh, pitch // 4, 4)[:, :sw][..., [2, 1, 0, 3]]
    return np.stack([px[i * h:(i + 1) * h, :w] for i in range(8)]).astype(float)  # the disc's eight


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    return mx, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)


def from_hsv(h, s, v):
    i = np.floor(h * 6) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r = np.choose(i.astype(int), [v, q, p, p, t, v])
    g = np.choose(i.astype(int), [t, v, v, q, p, p])
    b = np.choose(i.astype(int), [p, p, t, v, v, q])
    return np.stack([r, g, b], -1)


def layout(tiles):
    """The layout, (value, saturation, alpha) a pixel, from the eight icons where their objects are not.

    A pixel is the median of the icons that show background there (coloured, or see-through, or the
    white arc and lines). Where fewer than three do (the middle, under most objects), the band and the
    gradient are filled in from their profile across the circle they curve about: fitted to the band's
    edge, the profile is the known pixels' median at each distance from its centre."""
    n, h, w = tiles.shape[:3]
    v, s = hsv(tiles[..., :3] / 255)
    a = tiles[..., 3] / 255
    xx = np.broadcast_to(np.arange(w), (h, w))
    yy = np.broadcast_to(np.arange(h)[:, None], (h, w))
    edge_rows = (yy < 3) | (yy >= h - 3)
    bg = (s > 0.3) | (a < 0.99) | ((v > 0.95) & (s < 0.06) & ((xx < w * 0.3) | edge_rows)) | ((v < 0.06) & edge_rows)
    # not near an object either: its soft shadow takes the band's colour
    obj = ~bg & ~edge_rows
    near = obj.copy()
    rad = max(2, w // 50)
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            if dy * dy + dx * dx <= rad * rad: near |= shift(obj, dy, dx, 1, 2)
    bg &= ~near | edge_rows
    bg |= xx < w * 0.24  # (no object reaches the left quarter: the arc and its stripes as they are)
    # their own line art out (thin bright lines on the dark): the least value over a small disc
    soft = v.copy()
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            soft = np.minimum(soft, shift(v, dy, dx, 1, 2))
    dark = (a > 0.99) & (xx > w * 0.3)  # (the lines are coloured or white)
    v = np.where(dark, soft, v)
    # each icon's brightness and colour scaled to the first's, from where all show the band
    band = bg.all(0) & (s > 0.3).all(0) & (v > 0.5).all(0)
    ref = 6  # the stopwatch's (blue: a mid brightness)
    for t in range(n):
        if band.any():
            v[t] *= np.median(v[ref][band]) / max(np.median(v[t][band]), 1e-3)
            s[t] = np.clip(s[t] * np.median(s[ref][band]) / max(np.median(s[t][band]), 1e-3), 0, 1)
    # each pixel from the first icon (in this order) that shows background there
    V, S, A = v[ref].copy(), s[ref].copy(), a[ref].copy()
    have = bg[ref].copy()
    for t in (7, 1, 3, 0, 2, 5, 4):
        take = ~have & bg[t]
        V[take], S[take], A[take] = v[t][take], s[t][take], a[t][take]
        have |= take
    # the middle, under every icon's object: filled smoothly from around it (the car covers most of it)
    hole = ~have
    for X in (V, S, A):
        X[hole] = np.mean(X[~hole])
        for _ in range(400):
            avg = (shift(X, 1, 0) + shift(X, -1, 0) + shift(X, 0, 1) + shift(X, 0, -1)) / 4
            X[hole] = avg[hole]
    return np.clip(V, 0, 1), S, A


def shift(m, dy, dx, ay=0, ax=1):
    """m moved dy along axis ay and dx along ax, the edges held (np.roll wraps them round)."""
    h, w = m.shape[ay], m.shape[ax]
    iy = np.clip(np.arange(h) - dy, 0, h - 1)
    ix = np.clip(np.arange(w) - dx, 0, w - 1)
    return np.take(np.take(m, iy, ay), ix, ax)


def up(m, k):
    return np.repeat(np.repeat(m, k, 0), k, 1)


def glow_line(img, pts, width, colour, strength):
    """A thin glowing polyline (pts in pixels) added onto img (h x w x 3, 0-1)."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    d = np.full((h, w), 1e9)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
        d = np.minimum(d, np.hypot(xx - x0 - t * dx, yy - y0 - t * dy))
    core = np.clip(1 - d / width, 0, 1)
    halo = np.exp(-(d / (width * 4)) ** 2) * 0.45
    img += (core + halo)[..., None] * np.array(colour) * strength


def curve(w, h, x0, y0, x1, y1, bend, n=40):
    """A smooth arc from (x0, y0) to (x1, y1), its middle pushed `bend` (of the length) to one side."""
    t = np.linspace(0, 1, n)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), x1 - x0
    cx, cy = mx + nx * bend, my + ny * bend
    return list(zip((1 - t) ** 2 * x0 + 2 * t * (1 - t) * cx + t ** 2 * x1, (1 - t) ** 2 * y0 + 2 * t * (1 - t) * cy + t ** 2 * y1))


def puff(alpha_out, grey_out, cx, cy, r, edge):
    """A smoke puff: a light grey disc, outlined (drawn into the object's layers)."""
    h, w = grey_out.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    d = np.hypot(xx - cx, yy - cy)
    inside = np.clip(r - d + 0.5, 0, 1)
    ring = np.clip(r + edge - d + 0.5, 0, 1)
    shade = 0.80 + 0.17 * np.clip((cy - yy) / r, -1, 1)  # lighter on top, as the objects
    grey_out[:] = np.where(ring > alpha_out, np.where(inside > 0, shade, 0.0), grey_out)
    grey_out[:] = np.where(inside > 0, shade * inside + grey_out * (1 - inside), grey_out)
    alpha_out[:] = np.maximum(alpha_out, ring)


def draw(disc, strip, w, h, car_png):
    v, s, a = layout(disc_tiles(disc, strip, w, h))
    W, H = w * K, h * K
    v, s, a = up(v, K), up(s, K), up(a, K)
    rgb = from_hsv(np.full_like(v, HUE), s, v)
    # the line art: skid marks sweeping through the dark part, as the others' glowing outlines
    dark = np.clip((1 - v) * 1.4, 0, 1)[..., None] * (a[..., None] > 0.99)
    art = np.zeros((H, W, 3))
    lw = max(1.0, W / 210 * 0.9)
    for off in (0, 0.07):
        glow_line(art, curve(W, H, W * 0.42, H * (1.05 + off), W * 1.05, H * (0.12 + off), -0.28), lw, (1.0, 0.35, 0.3), 0.55)
    glow_line(art, curve(W, H, W * 0.62, H * 1.1, W * 1.1, H * 0.55, 0.18), lw, (1.0, 0.35, 0.3), 0.4)
    rgb = np.clip(rgb + art * dark, 0, 1)
    out = np.dstack([rgb, a])
    # the car and its smoke, as one object: grey, outlined, a soft shadow under it
    car = addseries.image(car_png, int(W * 0.66), int(H * 0.66)).astype(float) / 255
    ch, cw = car.shape[:2]
    ox, oy = int(W * 0.30), int(H * 0.20)
    obj = np.zeros((H, W, 4))
    obj[oy:oy + ch, ox:ox + cw] = car
    # smoke behind the rear wheels (the car's right in the picture, a front three-quarter view)
    sa, sg = np.zeros((H, W)), np.zeros((H, W))
    e = W / 210 * 1.6
    for fx, fy, fr in ((0.83, 0.70, 0.085), (0.92, 0.60, 0.07), (0.90, 0.80, 0.075), (0.98, 0.70, 0.06)):
        puff(sa, sg, W * fx, H * fy, W * fr, e)
    smoke = np.dstack([sg, sg, sg, sa])
    # the smoke behind the car: car over smoke
    oa = obj[..., 3:4]
    obj = np.dstack([obj[..., :3] * oa + smoke[..., :3] * smoke[..., 3:4] * (1 - oa), oa + smoke[..., 3:4] * (1 - oa)])
    obj[..., :3] = np.where(obj[..., 3:4] > 0, obj[..., :3] / np.maximum(obj[..., 3:4], 1e-6), 0)
    # the shadow: the object's coverage, blurred, down and right
    sh = np.zeros((H, W))
    dy, dx = int(H * 0.025), int(W * 0.012)
    sh[dy:, dx:] = obj[:-dy, :-dx, 3]
    for _ in range(3):
        sh = (sh + shift(sh, 2 * K, 0) + shift(sh, -2 * K, 0) + shift(sh, 0, 2 * K) + shift(sh, 0, -2 * K)) / 5
    out[..., :3] *= 1 - 0.55 * sh[..., None]
    out[..., 3] = np.maximum(out[..., 3], 0.55 * sh)
    oa = obj[..., 3:4]
    out[..., :3] = out[..., :3] * (1 - oa) + obj[..., :3] * oa
    out[..., 3] = np.maximum(out[..., 3], oa[..., 0])
    small = out.reshape(h, K, w, K, 4).mean((1, 3))
    return np.clip(small * 255 + 0.5, 0, 255).astype(np.uint8)


if __name__ == '__main__':
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    disc, car_png, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    for name, strip, (w, h) in (('drift_cat_lg', 'Events_LG.xpr', (210, 117)), ('drift_cat_sm', 'Events.xpr', (108, 60))):
        p = os.path.join(out, name + '.png')
        forzaxpr.png(p, np.ascontiguousarray(draw(disc, strip, w, h, car_png)))
        print(p)
