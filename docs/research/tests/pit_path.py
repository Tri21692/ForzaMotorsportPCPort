"""pit_path.py <build folder> <out.txt>: Fuji's pitin spline as "x z" lines (XBRT_AUTODRIVE_PATH), and a picture of all
its pit splines on the track's edges."""
import sys, numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import xb2
from PIL import Image, ImageDraw
b = sys.argv[1]
res = open(b + r'\roadatlanta.res', 'rb').read(); names, _ = xb2.resources(res)
sp = {}
for r in names:
    if r[0].startswith('vbuff_quickpreview_splines_'):
        n = (r[4] + 4) // 16
        sp[r[0][len('vbuff_quickpreview_splines_'):-4]] = np.frombuffer(res, '<f4', count=3 * n, offset=r[3]).reshape(-1, 3).astype(float)
P = sp['pitin']
open(sys.argv[2], 'w').write(''.join('%.3f %.3f\n' % (p[0], p[2]) for p in P))
print('pitin: %d points from (%.0f, %.0f) to (%.0f, %.0f); y %.1f..%.1f' % (len(P), P[0][0], P[0][2], P[-1][0], P[-1][2], P[:, 1].min(), P[:, 1].max()))
pts = np.vstack([sp[k] for k in sp if k.startswith('pit') or k.endswith('spline')])
lo, hi = pts[:, [0, 2]].min(0) - 40, pts[:, [0, 2]].max(0) + 40
S = 2.2
im = Image.new('RGB', (int((hi[1] - lo[1]) * S), int((hi[0] - lo[0]) * S * 3)), (20, 20, 20)); dr = ImageDraw.Draw(im)
px = lambda Q: [((p[2] - lo[1]) * S, (p[0] - lo[0]) * S * 3) for p in Q]   # (across the lane stretched 3 times)
for k in ('roadinner', 'roadouter'): dr.line(px(np.vstack([sp[k], sp[k][:1]])), fill=(130, 130, 130))
cols = {'pitin': (0, 255, 0), 'pitout': (255, 80, 80), 'pitabort': (255, 255, 0), 'entrancespline': (255, 255, 255), 'exitspline': (255, 0, 255)}
for k, Q in sp.items():
    c = (0, 160, 255) if k.startswith('pitparkin') else (255, 160, 0) if k.startswith('pitparkout') else cols.get(k)
    if c: dr.line(px(Q), fill=c, width=2)
im.save(sys.argv[2].replace('.txt', '.png'))
print(im.size)
