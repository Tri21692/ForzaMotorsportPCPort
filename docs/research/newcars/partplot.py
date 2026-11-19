"""A converted car's LOD1 parts drawn from the side (orthographic, nose left), each its own colour with a key, to
tell which part holds a stray piece.   python partplot.py key out.png [part ...]"""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, carbin
from PIL import Image, ImageDraw
from nfsu2forza import strip_tris
k, out = sys.argv[1], sys.argv[2]
only = set(sys.argv[3:])
c = carbin.read(open(os.path.join(r'E:\xbrt_scr\newcars\out', k, 'car.carbin'), 'rb').read())
PX = 200
im = Image.new('RGB', (int(5.4 * PX), int(1.9 * PX)), 'white'); d = ImageDraw.Draw(im)
P = lambda z, y: (im.width / 2 - z * PX, im.height * 0.75 - y * PX)
cols = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (128, 128, 0), (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128), (128, 128, 128)]
parts = [p for p in c['parts'] if p['name'].endswith('_LOD1') and p['verts'] and (not only or p['name'][:-5] in only)]
parts.sort(key=lambda p: -len(p['verts']))
for n, p in enumerate(parts):
    V = np.array([v[:3] for v in p['verts']], float) / 4096 / 1.6
    col = cols[n % len(cols)]
    for t in (t for sp in p['subparts'] for t in strip_tris(sp['indices'])):
        if max(t) < len(V): d.polygon([P(V[i][2], V[i][1]) for i in t], fill=col)
    d.text((6, 4 + 12 * n), p['name'], fill=col)
im.save(out)
