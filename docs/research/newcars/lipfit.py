"""The body's half-width at each arch's lip (outer body skin within 0.35 of a tyre radius of the hub along the car,
from 4 cm below the tyre's top to 10 cm above it) against the template's there: the template wears the same tyres
at the same track, so where the add-on's lip is narrower its tyres poke out, wider and they sit sunk in. Suggests a
WIDEN (the body's width alone) for each car: the lips' mean matched to the template's, neither end left more than
1.5 cm narrower than the template's (poking out).   python lipfit.py [key ...]  -> lipfit.json"""
import sys, os, re, json, importlib.util
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIN = re.compile(r'^(body|bumperF|bumperR|bumperFa|bumperRa|skirt[LR]a?|hood|hooda|trunk|fender)_LOD1$')


def lips(c, hubs, rides, dias):
    V = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in c['parts'] if SKIN.match(p['name']) and p['verts']]) / 4096 / 1.6
    out = []
    for h, ride, dia in zip(hubs, rides, dias):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        top = y + r
        sel = V[(np.abs(V[:, 2] - z) < 0.35 * r) & (V[:, 1] > top - 0.04) & (V[:, 1] < top + 0.10)]
        out.append(float(np.abs(sel[:, 0]).max()) if len(sel) else float('nan'))
    return out


def sides(c, hubs, rides, dias):
    """The body's half-width beside each wheel at the hub's height (+-8 cm), from 1.1 to 1.8 tyre radii ahead and
    behind its hub: what the tyre's flank is seen against from a three-quarter view."""
    V = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in c['parts'] if SKIN.match(p['name']) and p['verts']]) / 4096 / 1.6
    out = []
    for h, ride, dia in zip(hubs, rides, dias):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        dz = np.abs(V[:, 2] - z)
        sel = V[(dz > 1.1 * r) & (dz < 1.8 * r) & (np.abs(V[:, 1] - y) < 0.08)]
        out.append(float(np.percentile(np.abs(sel[:, 0]), 90)) if len(sel) > 5 else float('nan'))
    return out


def check(key):
    tp, _ = nc.template_files(nc.CARS[key][9])
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key])
    c = carbin.read(open(os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    t = carbin.read(open(tp, 'rb').read())
    hc, ht = tyrecheck.hubs_of(c, wb, zc), tyrecheck.hubs_of(t, wb, zc)
    M = lips(c, hc, (rf, rr), (df, dr)) + sides(c, hc, (rf, rr), (df, dr))
    T = lips(t, ht, (rf, rr), (df, dr)) + sides(t, ht, (rf, rr), (df, dr))
    ok = [i for i in range(4) if np.isfinite(M[i]) and np.isfinite(T[i])]
    f = float(np.mean([T[i] / M[i] for i in ok]))
    f = max(f, max((T[i] - 0.015) / M[i] for i in (0, 1) if i in ok), max([(T[i] - 0.03) / M[i] for i in (2, 3) if i in ok] or [0]))
    return M, T, f


if __name__ == '__main__':
    res = {}
    for k in sys.argv[1:] or sorted(nc.CARS):
        M, T, f = check(k)
        cur = nc.WIDEN.get(k, 1.0)
        new = round(cur * f, 3) if abs(f - 1) > 0.015 else cur
        res[k] = dict(M=M, T=T, f=f, cur=cur, new=new)
        print('%-9s lip %+.3f %+.3f  beside %+.3f %+.3f (vs template, m)   widen %.3f -> %.3f%s' % (
            k, M[0] - T[0], M[1] - T[1], M[2] - T[2], M[3] - T[3], cur, new, '  <--' if new != cur else ''), flush=True)
    json.dump(res, open(os.path.join(W, 'lipfit.json'), 'w'), indent=1)
