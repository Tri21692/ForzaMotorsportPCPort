"""Each converted add-on's wheel arches measured against its wheels where the game puts them (tyrecheck: hubs, ride
heights, stock tyres), from a depth render of its side: every LOD1 body triangle drawn orthographically from the
car's +x side into a z-buffer keeping the outermost surface. Where the outermost surface lies well inside the
body's local side (the wheel well, seen through the arch) or there is none, that is the arch's opening; the lip is
where the outer skin begins above the hub. A circle fitted to the lip gives the arch's middle and top.

Prints per car: how far each arch's middle is ahead of its wheel, and the gap from the tyre's top to the lip's
(+ = clear, - = the tyre's top under the lip), and writes zfit.json and zfit_<key>.png (the depth map, the
opening, the fitted arch in green, the tyre in red/blue).   python zfit.py [key ...]"""
import sys, os, re, json, importlib.util
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
from nfsu2forza import strip_tris
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIP = re.compile(r'(tire|tyre|rim|wheel|rotor|caliper|shadow|interior|cage|susp|exhaust|bumper[FR][b-z]|skirt[LR][b-z]|hood[b-z]|wing|steer|driver|seat|bands|engine|mirror)', re.I)
PX = 250  # pixels a metre
DEEP = 0.03  # a surface this far inside the body's local side is the wheel well, seen through the opening


def depth_map(c, side=1):
    parts = [p for p in c['parts'] if p['name'].endswith('_LOD1') and p['verts'] and not SKIP.search(p['name'])]
    Wd, Ht = int(6.4 * PX), int(2.2 * PX)
    zb = np.full((Ht, Wd), -9.0)
    ox, oy = Wd / 2, Ht * 0.75
    for p in parts:
        V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
        T = np.array([t for sp in p['subparts'] for t in strip_tris(sp['indices']) if max(t) < len(V) and len(set(t)) == 3], int)
        if not len(T): continue
        X = ox - V[:, 2] * PX; Y = oy - V[:, 1] * PX; D = side * V[:, 0]
        for t in T:
            xs, ys, ds = X[t], Y[t], D[t]
            x0, x1 = int(max(0, np.floor(xs.min()))), int(min(Wd - 1, np.ceil(xs.max())))
            y0, y1 = int(max(0, np.floor(ys.min()))), int(min(Ht - 1, np.ceil(ys.max())))
            if x1 < x0 or y1 < y0: continue
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-9: continue
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
            a = ((ys[1] - ys[2]) * (xx - xs[2]) + (xs[2] - xs[1]) * (yy - ys[2])) / den
            b = ((ys[2] - ys[0]) * (xx - xs[2]) + (xs[0] - xs[2]) * (yy - ys[2])) / den
            cc = 1 - a - b
            ins = (a >= -0.01) & (b >= -0.01) & (cc >= -0.01)
            d = a * ds[0] + b * ds[1] + cc * ds[2]
            win = zb[y0:y1 + 1, x0:x1 + 1]
            up = ins & (d > win)
            win[up] = d[up]
    return zb, (lambda z, y: (ox - z * PX, oy - y * PX)), (lambda px, py: ((ox - px) / PX, (oy - py) / PX))


def measure(key, path=None):
    c = carbin.read(open(path or os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key]); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    zb, P, inv = depth_map(c)
    Ht, Wd = zb.shape
    # the body's local side: the outermost depth within 15 cm along the car, over the height band above the hubs
    colmax = zb.max(0)
    k = int(0.15 * PX)
    local = np.array([colmax[max(0, i - k):i + k + 1].max() for i in range(Wd)])
    skin = (zb > -8) & (zb >= local[None, :] - DEEP)
    res = []
    for h, ride, dia in ((hf, rf, df), (hr, rr, dr)):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        cx, cy = P(z, y)
        pts = []
        for f in np.linspace(-0.9, 0.9, 41):
            px = int(round(cx + f * r * PX))
            if not 0 <= px < Wd: continue
            col = skin[:int(cy) + 1, px]
            hit = np.nonzero(col)[0]
            if len(hit):
                py = hit.max()  # (the lowest outer-skin pixel above the hub: the lip)
                if (cy - py) / PX < 2.2 * r: pts.append(inv(px, py))
        if len(pts) < 10: res.append(None); continue
        A = np.array(pts)
        M = np.c_[A[:, 0], A[:, 1], np.ones(len(A))]; bb = -(A[:, 0] ** 2 + A[:, 1] ** 2)
        Dc, Ec, Fc = np.linalg.lstsq(M, bb, rcond=None)[0]
        az, ay = -Dc / 2, -Ec / 2; R = float(np.sqrt(max(az * az + ay * ay - Fc, 0)))
        mid = A[np.abs(A[:, 0] - z) < 0.25 * r]
        lip_top = float(mid[:, 1].min()) if len(mid) else ay + R  # (the lip straight over the hub, as measured)
        res.append(dict(ahead=float(az - z), gap=lip_top - (y + r), R=R, r=r, z=z, y=y, az=float(az), ay=float(ay), pts=A.tolist()))
    return res, zb, skin, P


def picture(key, res, zb, skin, P, path):
    img = np.zeros(zb.shape + (3,), np.uint8)
    img[zb > -8] = (90, 90, 100); img[skin] = (200, 200, 210)
    im = Image.fromarray(img); d = ImageDraw.Draw(im)
    for q, col in zip(res, ('red', 'blue')):
        if q is None: continue
        x0, y0 = P(q['z'] + q['r'], q['y'] + q['r']); x1, y1 = P(q['z'] - q['r'], q['y'] - q['r']); d.ellipse((x0, y0, x1, y1), outline=col, width=3)
        x0, y0 = P(q['az'] + q['R'], q['ay'] + q['R']); x1, y1 = P(q['az'] - q['R'], q['ay'] - q['R']); d.ellipse((x0, y0, x1, y1), outline='lime', width=2)
        for pz, py in q['pts']: d.point(P(pz, py), fill='yellow')
    d.text((6, 4), key + '  ' + '  '.join('?' if q is None else 'ahead %+.3f gap %+.3f' % (q['ahead'], q['gap']) for q in res), fill='white')
    im.save(path)


if __name__ == '__main__':
    keys = sys.argv[1:] or sorted(nc.CARS)
    out = json.load(open(os.path.join(W, 'zfit.json'))) if os.path.exists(os.path.join(W, 'zfit.json')) else {}
    os.makedirs(os.path.join(W, 'zfit'), exist_ok=True)
    for k in keys:
        res, zb, skin, P = measure(k)
        out[k] = [None if q is None else {kk: vv for kk, vv in q.items() if kk != 'pts'} for q in res]
        picture(k, res, zb, skin, P, os.path.join(W, 'zfit', k + '.png'))
        print('%-9s %s' % (k, '   '.join('%s ?' % e if q is None else '%s ahead %+.3f gap %+.3f' % (e, q['ahead'], q['gap']) for e, q in zip(('front', 'rear'), res))), flush=True)
    json.dump(out, open(os.path.join(W, 'zfit.json'), 'w'), indent=1)
