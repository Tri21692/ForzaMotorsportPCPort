"""The gap from each tyre's top to its arch's lip (the outer skin's lowest point straight over the hub, within a
fifth of the tyre's radius along the car), metres; - = the lip covers the tyre's top (the user's 6 Nov screenshots:
tyres tucked under the fenders).   python gapcheck.py [key ...]"""
import sys, os, re, importlib.util
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIP = re.compile(r'(tire|tyre|rim|wheel|rotor|caliper|shadow|interior|cage|susp|glass|exhaust|bumper[FR][b-z]|skirt[LR][b-z]|hood[b-z]|wing)', re.I)


def gaps(key, path=None):
    c = carbin.read(open(path or os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key]); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    V = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in c['parts'] if p['name'].endswith('_LOD1') and p['verts'] and not SKIP.search(p['name'])]) / 4096 / 1.6
    out = []
    for h, ride, dia in ((hf, rf, df), (hr, rr, dr)):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        xs = np.abs(V[(np.abs(V[:, 2] - z) < r)][:, 0]).max()
        sel = V[(np.abs(V[:, 2] - z) < 0.2 * r) & (np.abs(V[:, 0]) > xs - 0.12) & (V[:, 1] > y)]
        out.append(sel[:, 1].min() - (y + r) if len(sel) else np.nan)
    return out


if __name__ == '__main__':
    for k in sys.argv[1:] or sorted(nc.CARS):
        f, r = gaps(k)
        print('%-9s tyre top to arch lip: front %+.3f m, rear %+.3f m' % (k, f, r))
