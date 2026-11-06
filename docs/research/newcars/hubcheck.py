"""For each template: hubs from rotors (if any), from the physics formula, and the template body's own arch spans
(sides' lower edge, 0.1 bins, raised past 45% of the way from sill to arch top)."""
import sys, os, re, glob
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import carbin, forzacab, addcar
import numpy as np
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
cars = addcar.Archive(DISC, r'E:\Forza Motorsport Remastered\run\mods_track', 'Cars.ca2')


def spans(V):
    s = V[np.abs(V[:, 0]) > 0.75 * np.abs(V[:, 0]).max()]
    L = np.ptp(s[:, 2]); mid = (s[:, 2].min() + s[:, 2].max()) / 2
    edges = np.arange(s[:, 2].min(), s[:, 2].max(), 0.1)
    low = np.array([s[(s[:, 2] >= e) & (s[:, 2] < e + 0.1)][:, 1].min() if ((s[:, 2] >= e) & (s[:, 2] < e + 0.1)).any() else np.nan for e in edges])
    c = edges + 0.05
    sill = np.nanmedian(low[np.abs(c - mid) < L / 6])
    res = []
    for sign in (1, -1):
        win = [i for i in range(len(c)) if 0.12 * L < sign * (c[i] - mid) < 0.49 * L and np.isfinite(low[i]) and low[i] < sill + 1.2]
        if not win: res.append(None); continue
        top = np.nanmax([low[i] for i in win])
        cut = sill + 0.45 * (top - sill)
        hit = sorted(i for i in win if low[i] > cut)
        runs, run = [], []
        for i in hit:
            if run and i - run[-1] > 2: runs.append(run); run = []
            run.append(i)
        if run: runs.append(run)
        if not runs: res.append(None); continue
        b = max(runs, key=len)
        res.append((round(c[b[0]] - 0.05, 2), round(c[b[-1]] + 0.05, 2), round((c[b[0]] + c[b[-1]]) / 2, 2)))
    return res


def main(ts):
    for t in ts:
        try:
            d, v, es = forzacab.read(os.path.join(DISC, 'media', 'cabs', 'car_%s.cab' % t))
        except Exception as e:
            print(t, 'no cab', e); continue
        e = next(e for e in es if e['name'].lower().endswith('car.carbin'))
        c = carbin.read(forzacab.data(d, e))
        V = np.array([v[:3] for p in c['parts'] if p['name'].endswith('_LOD1') and re.match(r'(body|bumperFa?_|bumperRa?_|bumperFa_|bumperRa_)', p['name']) for v in p['verts']]) / 4096
        rot = sorted({round((min(v[2] for v in q['verts']) + max(v[2] for v in q['verts'])) / 2 / 4096, 3) for q in c['parts'] if 'rotor' in q['name'].lower()})
        k = next((k for k in cars.files if k.lower() == 'cars' + B + t.lower() + B + 'physics' + B + 'maxdata.xml'), None)
        md = bytes(cars.files[k]).decode('latin-1')
        wb = float(re.search(r'Wheelbase="([^"]+)"', md).group(1)); zc = float(re.search(r'BottomCenterWheelbasePos[^>]*z="([^"]+)"', md).group(1))
        phys = ((zc + wb / 2) * 1.602, (zc - wb / 2) * 1.602)
        print('%-16s rotors %-16s physics %.2f %.2f  body arches %s' % (t, rot and '%.2f %.2f' % (max(rot), min(rot)), *phys, spans(V)))


if __name__ == '__main__':
    main(sys.argv[1:])
