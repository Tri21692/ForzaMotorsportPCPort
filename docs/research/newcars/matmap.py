"""Which material is outermost where: a converted car seen straight from behind (or the front), each pixel the
material of the nearest face (a z-buffer over the LOD1 triangles), coloured with a key; to find a dark shell over a
lamp.   python matmap.py key rear|front out.png"""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, carbin
from PIL import Image, ImageDraw
from nfsu2forza import strip_tris
k, end, out = sys.argv[1:4]
c = carbin.read(open(os.path.join(r'E:\xbrt_scr\newcars\out', k, 'car.carbin'), 'rb').read())
PX = 300; Wd, Ht = int(2.4 * PX), int(1.5 * PX)
zb = np.full((Ht, Wd), -1e9); mb = np.full((Ht, Wd), -99, int); pb = np.full((Ht, Wd), -1, int)
sg = -1 if end == 'rear' else 1
pnames = []
for p in c['parts']:
    if not p['name'].endswith('_LOD1') or not p['verts']: continue
    pi = len(pnames); pnames.append(p['name'])
    V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
    for sp in p['subparts']:
        for t in strip_tris(sp['indices']):
            if max(t) >= len(V) or len(set(t)) < 3: continue
            P = V[list(t)]
            X = Wd / 2 + sg * -P[:, 0] * PX if end == 'front' else Wd / 2 + P[:, 0] * PX
            X = Wd / 2 - P[:, 0] * PX * sg
            Y = Ht * 0.85 - P[:, 1] * PX
            D = sg * P[:, 2]
            x0, x1 = int(max(0, X.min())), int(min(Wd - 1, X.max())); y0, y1 = int(max(0, Y.min())), int(min(Ht - 1, Y.max()))
            if x1 < x0 or y1 < y0: continue
            den = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
            if abs(den) < 1e-9: continue
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            a = ((Y[1] - Y[2]) * (xx - X[2]) + (X[2] - X[1]) * (yy - Y[2])) / den
            b = ((Y[2] - Y[0]) * (xx - X[2]) + (X[0] - X[2]) * (yy - Y[2])) / den
            cc = 1 - a - b
            ins = (a >= 0) & (b >= 0) & (cc >= 0)
            d = a * D[0] + b * D[1] + cc * D[2]
            win = zb[y0:y1 + 1, x0:x1 + 1]
            upd = ins & (d > win)
            win[upd] = d[upd]
            mb[y0:y1 + 1, x0:x1 + 1][upd] = sp['material']
            pb[y0:y1 + 1, x0:x1 + 1][upd] = pi
cols = {1: (230, 150, 150), 2: (120, 170, 230), 3: (255, 0, 0), 4: (255, 255, 0), 6: (40, 40, 120), 7: (200, 200, 200), 9: (30, 30, 30), 16: (180, 0, 90), 26: (0, 200, 0), 14: (140, 90, 40), 28: (0, 255, 255), 30: (255, 128, 0)}
img = np.full((Ht, Wd, 3), 255, np.uint8)
for m in np.unique(mb):
    if m == -99: continue
    img[mb == m] = cols.get(int(m), (128, 0, 255))
im = Image.fromarray(img); d = ImageDraw.Draw(im)
for i, m in enumerate(sorted(set(np.unique(mb)) - {-99})):
    d.rectangle((4, 4 + 14 * i, 14, 14 + 14 * i), fill=cols.get(int(m), (128, 0, 255))); d.text((18, 4 + 14 * i), 'mat %d (%d px)' % (m, (mb == m).sum()), fill='black')
im.save(out)
