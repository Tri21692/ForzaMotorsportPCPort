"""Exact side outlines of converted add-on cars (out/<key>/car.carbin, LOD1 parts, orthographic) with the game's
wheels drawn where its physics puts them (tyrecheck.data: the hubs, ride heights and stock tyre sizes), to see a wheel
out of its arch without the perspective of a render.   python sideplot.py out.png key [key ...]"""
import sys, os, re, importlib.util
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck
from nfsu2forza import strip_tris
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SKIP = re.compile(r'(tire|tyre|rim|wheel|rotor|caliper|shadow)', re.I)
PX = 160  # pixels a metre


def plot(key, src=None):
    c = carbin.read(open(src or os.path.join(W, 'out', key, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[key])
    hf, hr = tyrecheck.hubs_of(c, wb, zc)
    im = Image.new('RGB', (int(6.4 * PX), int(2.0 * PX)), 'white')
    d = ImageDraw.Draw(im)
    ox, oy = im.width / 2, im.height * 0.62
    P = lambda z, y: (ox - z * PX, oy - y * PX)  # (the nose to the left)
    xs = max(abs(v[0]) for p in c['parts'] if p['name'].endswith('_LOD1') and not SKIP.search(p['name']) for v in p['verts']) / 4096 / 1.6
    for p in c['parts']:
        if not p['name'].endswith('_LOD1') or SKIP.search(p['name']) or not p['verts']: continue
        V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
        for t in (t for sp in p['subparts'] for t in strip_tris(sp['indices'])):
            if (V[t[0]][0] + V[t[1]][0] + V[t[2]][0]) / 3 > 0.72 * xs:  # (one side's outer skin: the arch openings show)
                d.polygon([P(V[i][2], V[i][1]) for i in t], fill=(150, 150, 160))
    body = np.array(im.convert('L')) < 250
    offs = []
    for h, ride, dia in ((hf, rf, df), (hr, rr, dr)):  # the arch opening across the hub, a third of a tyre above its middle
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        best = None
        for f in (0.33, 0.5, 0.15, 0.65, 0.0, 0.8):  # (the first height where the hub's column is open)
            cx, cy = P(z, y + r * f)
            row = body[int(cy)]
            near = [i for i in range(int(cx - 0.5 * r * PX), int(cx + 0.5 * r * PX)) if not row[i]]
            if not near: continue
            a = b = min(near, key=lambda i: abs(i - cx))
            while a > 0 and not row[a - 1] and cx - a < 1.3 * r * PX: a -= 1
            while b < len(row) - 1 and not row[b + 1] and b - cx < 1.3 * r * PX: b += 1
            if (b - a) / PX > 0.6 * r: best = (round(-((a + b) / 2 - cx) / PX, 3), f); break
        offs.append(best)
    plot.offs = offs
    for h, ride, dia, col in ((hf, rf, df, 'red'), (hr, rr, dr, 'blue')):
        z, y, r = h / 1.6, -ride + dia / 2, dia / 2
        x0, y0 = P(z + r, y + r); x1, y1 = P(z - r, y - r)
        d.ellipse((x0, y0, x1, y1), outline=col, width=3)
        cx, cy = P(z, y); d.line((cx, cy - r * PX - 30, cx, cy + r * PX), fill=col)
    d.text((6, 4), '%s  hubs %.2f %.2f m  tyres %.2f %.2f m  arches ahead by %s m' % (key, hf / 1.6, hr / 1.6, df, dr, offs), fill='black')
    return im


if __name__ == '__main__':
    ims = []
    for k in sys.argv[2:]:
        ims.append(plot(k)); print('%-9s arches ahead of the wheels by (m): front %s, rear %s' % (k, *plot.offs), flush=True)
    s = Image.new('RGB', (ims[0].width * 2, ims[0].height * ((len(ims) + 1) // 2)), 'white')
    for i, im in enumerate(ims): s.paste(im, ((i % 2) * im.width, (i // 2) * im.height))
    s.save(sys.argv[1])
