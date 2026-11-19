"""Each add-on's arch openings against its wheels where the game puts them (tyrecheck: hubs, ride heights, stock
tyres): the body's outward-facing skin of one side drawn from the side (orthographic, 200 px a metre), the arch lip
traced up from each hub over the tyre's width, a circle fitted to it. Prints how far each arch's middle is ahead of
its wheel and how far the tyre's top is below the lip (- = tucked under it: the user's 6 Nov screenshots), and the
corrections: the arch middles for newcars ARCHES and the body's height change for HEIGHT.
  python archfit.py [key ...]        (sheet: archfit.jpg)"""
import sys, os, re, json, importlib.util
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
from nfsu2forza import strip_tris
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIP = re.compile(r'(tire|tyre|rim|wheel|rotor|caliper|shadow|interior|cage|susp|glass|exhaust|bumper[FR][b-z]|skirt[LR][b-z]|hood[b-z]|wing|lamp|light|mirror|steer|driver|seat|bands|engine)', re.I)
PX = 200


def skin(c):
    """The silhouette of the right side's outward-facing skin, as a boolean image, and the mapping."""
    parts = [p for p in c['parts'] if p['name'].endswith('_LOD1') and p['verts'] and not SKIP.search(p['name'])]
    allv = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in parts]) / 4096 / 1.6
    zb = np.floor(allv[:, 2] / 0.05).astype(int); lo = zb.min()
    wmax = np.zeros(zb.max() - lo + 1)
    np.maximum.at(wmax, zb - lo, np.abs(allv[:, 0]))
    wloc = np.array([wmax[max(0, i - 2):i + 3].max() for i in range(len(wmax))])  # (the body's half-width within 10 cm along the car)
    local = lambda z: wloc[min(len(wloc) - 1, max(0, int(np.floor(z / 0.05)) - lo))]
    im = Image.new('L', (int(6.4 * PX), int(2.2 * PX)), 0); d = ImageDraw.Draw(im)
    ox, oy = im.width / 2, im.height * 0.7
    P = lambda z, y: (ox - z * PX, oy - y * PX)
    for p in parts:
        V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
        for t in (t for sp in p['subparts'] for t in strip_tris(sp['indices'])):
            if max(t) >= len(V) or len(set(t)) < 3: continue
            a, b, cc = V[t[0]], V[t[1]], V[t[2]]
            if (a[0] + b[0] + cc[0]) / 3 < local((a[2] + b[2] + cc[2]) / 3) - 0.07: continue  # (the outer 7 cm there: not the wheel wells' inner walls, which face out too)
            n = np.cross(b - a, cc - a); ln = np.linalg.norm(n)
            if ln < 1e-12: continue
            if abs(n[0] / ln) < 0.25: continue  # (facing up or down: the sills' and liners' horizontal faces)
            d.polygon([P(a[2], a[1]), P(b[2], b[1]), P(cc[2], cc[1])], fill=255)
    return np.array(im) > 0, P, im


def fit(key):
    c = carbin.read(open(os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key]); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    S, P, im = skin(c)
    res = []
    for h, ride, dia in ((hf, rf, df), (hr, rr, dr)):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        pts = []
        for dz in np.linspace(-0.85 * r, 0.85 * r, 35):
            cx, cy = P(z + dz, y)
            col = S[:int(cy), int(cx)] if 0 <= int(cx) < S.shape[1] else []
            hit = np.nonzero(col)[0]
            if len(hit):  # (the lowest body pixel above the hub: the lip)
                yy = hit.max()
                pts.append((z + dz, (P(0, 0)[1] - yy) / PX))
        if len(pts) < 8: res.append(None); continue
        A = np.array(pts)
        # circle through the lip: z^2 + y^2 + D z + E y + F = 0
        M = np.c_[A[:, 0], A[:, 1], np.ones(len(A))]; b = -(A[:, 0] ** 2 + A[:, 1] ** 2)
        D, E, F = np.linalg.lstsq(M, b, rcond=None)[0]
        az, ay = -D / 2, -E / 2; R = np.sqrt(max(az * az + ay * ay - F, 0))
        top = ay + R
        res.append(dict(ahead=az - z, gap=top - (y + r), R=R, r=r, z=z, y=y, az=az, ay=ay, pts=A))
    return res, im, P, (hf, hr)


if __name__ == '__main__':
    keys = sys.argv[1:] or sorted(nc.CARS)
    out = {}; tiles = []
    for k in keys:
        res, im, P, hubs = fit(k)
        out[k] = [None if q is None else {kk: float(vv) for kk, vv in q.items() if kk != 'pts'} for q in res]
        txt = []
        rgb = im.convert('RGB'); d = ImageDraw.Draw(rgb)
        for q, col in zip(res, ('red', 'blue')):
            if q is None: txt.append('?'); continue
            x0, y0 = P(q['z'] + q['r'], q['y'] + q['r']); x1, y1 = P(q['z'] - q['r'], q['y'] - q['r']); d.ellipse((x0, y0, x1, y1), outline=col, width=3)
            x0, y0 = P(q['az'] + q['R'], q['ay'] + q['R']); x1, y1 = P(q['az'] - q['R'], q['ay'] - q['R']); d.ellipse((x0, y0, x1, y1), outline='lime', width=2)
            for pz, py in q['pts']: d.point(P(pz, py), fill='yellow')
            txt.append('ahead %+.3f gap %+.3f' % (q['ahead'], q['gap']))
        d.text((6, 4), '%s  front %s  rear %s' % (k, *txt), fill='white')
        tiles.append(rgb.resize((rgb.width // 2, rgb.height // 2)))
        print('%-9s front %-28s rear %s' % (k, *txt), flush=True)
    json.dump(out, open(os.path.join(W, 'archfit.json'), 'w'), indent=1)
    cols = 2; sh = Image.new('RGB', (tiles[0].width * cols, tiles[0].height * ((len(tiles) + cols - 1) // cols)))
    for i, t in enumerate(tiles): sh.paste(t, ((i % cols) * t.width, (i // cols) * t.height))
    sh.save(os.path.join(W, 'archfit.jpg'), quality=85)
