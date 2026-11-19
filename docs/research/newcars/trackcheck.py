"""Each add-on's tyres against its body's sides: the physics' outer track (maxdata FrontTrackOuter / RearTrackOuter,
the tyres' outer faces) against the body's half-width over each hub (body parts, LOD1, within a tyre's radius of
the hub along the car and above the tyre's middle). + = the tyre sticks out past the body (the user's 6 Nov
screenshots: tyres drawn over the arch lips).   python trackcheck.py [key ...]"""
import sys, os, re, importlib.util
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck, addcar
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
B = chr(92)
SKIN = re.compile(r'^(body|bumper|skirt|hood|trunk|fender)', re.I)


def track(name):
    k = next(k for k in tyrecheck.cars.files if k.lower() == ('cars' + B + name + B + 'physics' + B + 'maxdata.xml').lower())
    t = bytes(tyrecheck.cars.files[k]).decode('latin-1')
    return float(re.search(r'FrontTrackOuter="([^"]+)"', t).group(1)), float(re.search(r'RearTrackOuter="([^"]+)"', t).group(1))


def check(key, path=None):
    c = carbin.read(open(path or os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key]); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    tf, tr = track(nc.NAME[key])
    parts = [p for p in c['parts'] if p['name'].endswith('_LOD1') and p['verts'] and SKIN.match(p['name']) and not re.match(r'bumper[FR][b-z]|skirt[LR][b-z]|hood[b-z]', p['name'])]
    V = np.concatenate([np.array([v[:3] for v in p['verts']], float) for p in parts]) / 4096 / 1.6
    out = []
    for h, ride, dia, tw in ((hf, rf, df, tf), (hr, rr, dr, tr)):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        sel = V[(np.abs(V[:, 2] - z) < r) & (V[:, 1] > y) & (V[:, 1] < y + r * 1.4)]
        half = np.abs(sel[:, 0]).max() if len(sel) else np.nan
        out.append(tw / 2 - half)
    return out, tf, tr


if __name__ == '__main__':
    for k in sys.argv[1:] or sorted(nc.CARS):
        (f, r), tf, tr = check(k)
        flag = '  <-- sticks out' if max(f, r) > 0.005 else ''
        print('%-9s track %.2f/%.2f  tyre past the body: front %+.3f m, rear %+.3f m%s' % (k, tf, tr, f, r, flag))
