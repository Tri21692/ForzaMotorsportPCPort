"""Road Atlanta's pit splines against its track: for each, its points, where its ends lie on the lap (share, metres
off the centre line, side), its length; and a picture."""
import os, sys, numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import xb2, addcar
from PIL import Image, ImageDraw
D = r"C:/Users/maste/Downloads/extract-xiso-win32-release/Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso"
track = sys.argv[1] if len(sys.argv) > 1 else 'RoadAtlanta'
folder = addcar.disc_file(D, 'media', 'tracks', track)
files = {f.lower(): os.path.join(folder, f) for f in os.listdir(folder)}
res = bytes(xb2.unpack(files['quickpreview1.xb2'])); names, _ = xb2.resources(res)
sp = {}
for r in names:
    if r[0].startswith('vbuff_quickpreview_splines_'):
        n = (r[4] + 4) // 16
        sp[r[0][len('vbuff_quickpreview_splines_'):-4]] = np.frombuffer(res, '<f4', count=3 * n, offset=r[3]).reshape(-1, 3).astype(float)
        tail = np.frombuffer(res, '<f4', count=(r[4] - 12 * n) // 4, offset=r[3] + 12 * n) if r[4] > 12 * n else []
ri, ro = sp['roadinner'], sp['roadouter']
C = (ri + ro) / 2
n = len(C)
seg = np.linalg.norm(np.diff(np.vstack([C, C[:1]])[:, [0, 2]], axis=0), axis=1)
print('lap %.0f m, %d points; road width median %.1f' % (seg.sum(), n, np.median(np.linalg.norm((ri - ro)[:, [0, 2]], axis=1))))
tg = np.roll(C, -1, 0) - np.roll(C, 1, 0); tg = tg[:, [0, 2]] / np.linalg.norm(tg[:, [0, 2]], axis=1, keepdims=True)
inw = (ri - C)[:, [0, 2]]; inw /= np.linalg.norm(inw, axis=1, keepdims=True)


def where(p):
    d = np.hypot(C[:, 0] - p[0], C[:, 2] - p[2]); j = int(d.argmin())
    return j / n, float((p[[0, 2]] - C[j, [0, 2]]) @ inw[j]), float(p[1] - C[j, 1])


for k in sorted(sp):
    if k in ('roadinner', 'roadouter', 'drivableinner', 'drivableouter', 'curbinginner', 'curbingouter'): continue
    P = sp[k]
    L = np.linalg.norm(np.diff(P[:, [0, 2]], axis=0), axis=1).sum()
    a, b = where(P[0]), where(P[-1])
    mid = where(P[len(P) // 2])
    st = np.linalg.norm(np.diff(P[:, [0, 2]], axis=0), axis=1) if len(P) > 1 else np.zeros(1)
    print('%-14s %3d pts %6.1f m  from lap %.3f (%+6.1f m in, y %+.1f)  mid %.3f (%+6.1f)  to lap %.3f (%+6.1f m in, y %+.1f)  step %.1f..%.1f' %
          (k, len(P), L, a[0], a[1], a[2], mid[0], mid[1], b[0], b[1], b[2], st.min(), st.max()))
# picture round the pits
pts = np.vstack([sp[k] for k in sp if k.startswith('pit') or k.endswith('spline')])
lo, hi = pts[:, [0, 2]].min(0) - 30, pts[:, [0, 2]].max(0) + 30
S = 1800 / max(hi - lo)
im = Image.new('RGB', (int((hi[0] - lo[0]) * S), int((hi[1] - lo[1]) * S)), (20, 20, 20)); dr = ImageDraw.Draw(im)
px = lambda P: [((p[0] - lo[0]) * S, (p[2] - lo[1]) * S) for p in P]
dr.line(px(np.vstack([ri, ri[:1]])), fill=(120, 120, 120)); dr.line(px(np.vstack([ro, ro[:1]])), fill=(120, 120, 120))
cols = {'pitin': (0, 255, 0), 'pitout': (255, 80, 80), 'pitabort': (255, 255, 0), 'entrancespline': (255, 255, 255), 'exitspline': (255, 0, 255)}
for k, P in sp.items():
    if k.startswith('pitparkin'): c = (0, 160, 255)
    elif k.startswith('pitparkout'): c = (255, 160, 0)
    elif k in cols: c = cols[k]
    else: continue
    dr.line(px(P), fill=c, width=2)
    x, y = px(P[-1:])[0]; dr.ellipse((x - 3, y - 3, x + 3, y + 3), fill=c)
    dr.text((x + 4, y), k.replace('pitpark', ''), fill=c)
im.save(r'E:\xbrt_scr\pit_splines_%s.png' % track)
np.savez(r'E:\xbrt_scr\pit_splines_%s.npz' % track, **sp)
print(im.size)
