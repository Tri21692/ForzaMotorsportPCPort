"""What a converted car's lamp faces (Taillights 3, Headlights 4, and Body/Badge near the ends) draw from its atlas:
each LOD1 subpart near an end of the car, its material, triangles, and the mean colour and alpha of the atlas
texels at its vertices (u, v / 32768).   python lampsample.py key  (after lampview.py, for the decoded atlas)"""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, carbin
from PIL import Image
from nfsu2forza import strip_tris
k = sys.argv[1]
W = r'E:\xbrt_scr\newcars'
c = carbin.read(open(os.path.join(W, 'out', k, 'car.carbin'), 'rb').read())
A = np.array(Image.open(os.path.join(W, 'lampview', k, 'livery0hi.png')).convert('RGBA'))
H, Wd = A.shape[:2]
zs = [v[2] for p in c['parts'] if p['name'].endswith('_LOD1') for v in p['verts']]
lo, hi = min(zs), max(zs)
for p in c['parts']:
    if not p['name'].endswith('_LOD1') or not p['verts']: continue
    for sp in p['subparts']:
        T = strip_tris(sp['indices'])
        vs = sorted({i for t in T for i in t if i < len(p['verts'])})
        vs = [i for i in vs if p['verts'][i][2] > hi - 0.18 * (hi - lo) or p['verts'][i][2] < lo + 0.18 * (hi - lo)]
        if not vs: continue
        z = np.mean([p['verts'][i][2] for i in vs])
        if sp['material'] not in (3, 4, 16, 30): continue
        uv = np.array([p['verts'][i][-2:] for i in vs], float) / 32768
        px = A[np.clip((uv[:, 1] * H).astype(int), 0, H - 1), np.clip((uv[:, 0] * Wd).astype(int), 0, Wd - 1)]
        print('%-22s %s mat %2d tris %5d  x %+.2f  uv %.3f..%.3f  rgb %3d %3d %3d a %3d' % (p['name'], 'front' if z > 0 else 'rear ', sp['material'], len(T),
              np.mean([p['verts'][i][0] for i in vs]) / 4096, uv[:, 0].min(), uv[:, 0].max(), *px[:, :3].mean(0), px[:, 3].mean()))
