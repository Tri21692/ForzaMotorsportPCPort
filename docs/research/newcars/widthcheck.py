"""Each add-on's body half-width over its wheels against its template's (whose own wheels, the same ones the game
draws on the add-on, fit it): the outermost body skin within a tyre's radius of each hub along the car, between the
hub's height and 15 cm above the tyre's top. Below 1 = the add-on is narrower there and the game's tyres stick out
past its sides (the user's 6 Nov screenshots).   python widthcheck.py [key ...]"""
import sys, os, re, importlib.util, json
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIN = re.compile(r'^(body|bumperF|bumperR|bumperFa|bumperRa|skirt[LR]a?|skirt[LR]|hood|hooda|trunk|fender)_LOD1$')


def halfwidths(c, hubs, rides, dias):
    parts = [p for p in c['parts'] if SKIN.match(p['name']) and p['verts']]
    V = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in parts]) / 4096 / 1.6
    out = []
    for h, ride, dia in zip(hubs, rides, dias):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        sel = V[(np.abs(V[:, 2] - z) < r) & (V[:, 1] > y) & (V[:, 1] < y + r + 0.15)]
        out.append(float(np.abs(sel[:, 0]).max()) if len(sel) else float('nan'))
    return out


def check(key, path=None):
    tp, _ = nc.template_files(nc.CARS[key][9])
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key])
    c = carbin.read(open(path or os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    t = carbin.read(open(tp, 'rb').read())
    hubs = tyrecheck.hubs_of(c, wb, zc)
    mine = halfwidths(c, hubs, (rf, rr), (df, dr))
    theirs = halfwidths(t, tyrecheck.hubs_of(t, wb, zc), (rf, rr), (df, dr))
    return mine, theirs


if __name__ == '__main__':
    res = {}
    for k in sys.argv[1:] or sorted(nc.CARS):
        try:
            m, t = check(k)
        except Exception as e:
            print(k, '?', e); continue
        res[k] = (m, t)
        print('%-9s half-width over the wheels: front %.3f (template %.3f) x%.3f   rear %.3f (template %.3f) x%.3f%s' % (
            k, m[0], t[0], m[0] / t[0], m[1], t[1], m[1] / t[1], '   <-- tyres stick out' if min(m[0] - t[0], m[1] - t[1]) < -0.015 else ''), flush=True)
    json.dump(res, open(os.path.join(W, 'widthcheck.json'), 'w'), indent=1)
