"""The tyre model the game draws on each add-on (Mega.ca2 tires/art\<WheelStyle file>\tire.carbin) times the car's
config.ini Front/RearTireScale: its radius and width, metres, against the physics' stock tyre size (tyrecheck).
python tyremodel.py [key ...]"""
import sys, os, re, importlib.util
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, addcar, tyrecheck
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
B = chr(92)
mega = addcar.Archive(nc.DISC, nc.MODS, 'Mega.ca2')
cars = tyrecheck.cars
lk = {k.lower(): k for k in mega.files}
ck = {k.lower(): k for k in cars.files}


def model(key):
    name = nc.NAME[key]
    td = bytes(cars.files[ck[('cars' + B + name + B + 'tooldata.xml').lower()]]).decode('latin-1')
    style = re.search(r'<WheelStyle>.*?File="([^"]+)"', td, re.S).group(1)
    cfg = bytes(cars.files[ck[('cars' + B + name + B + 'config.ini').lower()]]).decode('latin-1')
    fs = float(re.search(r'FrontTireScale\s+([\d.]+)', cfg).group(1)); rs = float(re.search(r'RearTireScale\s+([\d.]+)', cfg).group(1))
    k = lk.get(('tires' + B + 'art' + B + style + B + 'tire.carbin').lower())
    if not k: return style, fs, rs, None
    c = carbin.read(bytes(mega.files[k]))
    out = {}
    for p in c['parts']:
        if not p['verts']: continue
        V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
        out[p['name']] = (np.ptp(V[:, 1]) / 2, np.ptp(V[:, 0]), V[:, 0].min(), V[:, 0].max(), np.ptp(V[:, 2]) / 2)
    return style, fs, rs, out


if __name__ == '__main__':
    for key in sys.argv[1:] or sorted(nc.CARS):
        style, fs, rs, out = model(key)
        wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key])
        print('%-9s style %-16s scale %.2f/%.2f  physics dia %.3f/%.3f' % (key, style, fs, rs, df, dr))
        for n, (ry, w, x0, x1, rz) in (out or {}).items():
            if 'LOD1' in n or len(out) < 4: print('    %-24s radius %.3f (x scale %.3f / %.3f)  width %.3f  x %.3f..%.3f' % (n, ry, ry * fs, ry * rs, w, x0, x1))
