"""Fuji in the game (fuji_forza.npz's centre line) against OpenStreetMap's Fuji Speedway raceway way: the best
similarity fit (turn, scale, shift; with and without a mirror), the distances between the two lines, a picture, and
the real pit lane in the game's lap terms."""
import json, sys
import numpy as np
from PIL import Image, ImageDraw

build = sys.argv[1] if len(sys.argv) > 1 else r'E:\xbrt_scr\fuji_build_u'
F = np.load(build + r'\fuji_forza.npz')
C = F['centre'][:, [0, 2]].astype(float)
d = json.load(open(r'E:\xbrt_scr\osm\fuji_osm.json', encoding='utf-8'))
way = {e['id']: e for e in d['elements']}
lat0 = 35.3717


def metres(e):
    g = e['geometry']
    return np.array([[(p['lon'] - 138.927) * 111320 * np.cos(np.radians(lat0)), (p['lat'] - lat0) * 110940] for p in g])


def resample(P, n, closed=True):
    Q = np.vstack([P, P[:1]]) if closed else P
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    t = np.linspace(0, s[-1], n, endpoint=not closed)
    return np.stack([np.interp(t, s, Q[:, 0]), np.interp(t, s, Q[:, 1])], 1), s[-1]


def fit(A, B, mirror):
    """Similarity taking A onto B (rows paired): scale, R, t."""
    A0, B0 = A - A.mean(0), B - B.mean(0)
    U, S, Vt = np.linalg.svd(A0.T @ B0)
    D = np.diag([1, -1 if (np.linalg.det(U @ Vt) < 0) != mirror else 1])
    R = (U @ D @ Vt).T
    sc = np.trace(np.diag(S) @ D) / (A0 ** 2).sum()
    return sc, R, B.mean(0) - sc * A.mean(0) @ R.T


def nearest(P, Q):
    dd = np.hypot(P[:, None, 0] - Q[None, :, 0], P[:, None, 1] - Q[None, :, 1])
    return dd.argmin(1), dd.min(1)


real = metres(way[148622740])
if (real[0] == real[-1]).all(): real = real[:-1]
N = 1500
R_, Lr = resample(real, N)
G_, Lg = resample(C, N)
print('lengths: OpenStreetMap %.0f m, the game %.0f m' % (Lr, Lg))
best = {}
for mirror in (False, True):
    res = None
    for rev in (False, True):
        Gs = G_[::-1] if rev else G_
        for sh in range(0, N, 10):
            A = np.roll(Gs, sh, 0)
            sc, R, t = fit(A, R_, mirror)
            err = np.sqrt((((sc * A @ R.T + t) - R_) ** 2).sum(1).mean())
            if res is None or err < res[0]: res = (err, sc, R, t, rev, sh)
    err, sc, R, t, rev, sh = res
    for _ in range(30):  # refined on nearest points (the two lines' points need not pair by arc length)
        M = sc * G_ @ R.T + t
        j, dist = nearest(M, R_)
        sc, R, t = fit(G_, R_[j], mirror)
    M = sc * G_ @ R.T + t
    j, dist = nearest(M, R_)
    j2, dist2 = nearest(R_, M)
    both = np.concatenate([dist, dist2])
    best[mirror] = (np.sqrt((both ** 2).mean()), sc, R, t, both)
    print('%s: scale %.4f, the lines apart %.1f m on average (rms %.1f), 95%% within %.1f m, at most %.1f m' %
          ('mirrored' if mirror else 'as it is', sc, both.mean(), np.sqrt((both ** 2).mean()), np.percentile(both, 95), both.max()))
mirror = min(best, key=lambda m: best[m][0])
_, sc, R, t, both = best[mirror]
print('best: %s' % ('MIRRORED' if mirror else 'not mirrored'))
M = sc * C @ R.T + t
# picture
allp = np.vstack([M, real])
lo, hi = allp.min(0) - 60, allp.max(0) + 60
S = 1.4
W, H = int((hi[0] - lo[0]) * S), int((hi[1] - lo[1]) * S)
im = Image.new('RGB', (W, H), (250, 250, 250)); dr = ImageDraw.Draw(im)
px = lambda P: [((p[0] - lo[0]) * S, H - (p[1] - lo[1]) * S) for p in P]
for e in way.values():
    if e['id'] in (148622740,): continue
    if e.get('tags', {}).get('name') == 'Pit lane': dr.line(px(metres(e)), fill=(40, 160, 40), width=3)
dr.line(px(np.vstack([real, real[:1]])), fill=(30, 90, 220), width=5)
dr.line(px(np.vstack([M, M[:1]])), fill=(230, 40, 40), width=2)
dr.text((20, 16), 'blue: the real Fuji Speedway (OpenStreetMap)   red: the game   green: the real pit lane', fill=(0, 0, 0))
im.save(r'E:\xbrt_scr\osm\fuji_overlay.png')
# the real pit lane on the game's lap: where it leaves and rejoins, which side, how far from the centre line
pit = metres(way[148621414])
P_, _ = resample(pit, 200, closed=False)
inv = lambda Q: ((Q - t) @ R) / sc  # (to the game's x, z)
Pg = inv(P_)
j, dist = nearest(Pg, C)
n = len(C)
inner = F['inner'][:, [0, 2]] - C if 'inner' in F.files else None
tg = np.roll(C, -1, 0) - np.roll(C, 1, 0); tg /= np.linalg.norm(tg, axis=1, keepdims=True)
left = np.stack([-tg[:, 1], tg[:, 0]], 1)
side = np.einsum('ij,ij->i', Pg - C[j], left[j])
print('pit lane: %.0f m long; from lap %.3f to %.3f; off the centre line %.1f m at its middle (median %.1f), side %s of travel' %
      (np.linalg.norm(np.diff(pit, axis=0), axis=1).sum(), j[0] / n, j[-1] / n, dist[len(dist) // 2], np.median(dist), 'left' if np.median(side) > 0 else 'right'))
for k in range(0, 200, 20): print('   lap %.3f  %.1f m off' % (j[k] / n, dist[k]))
np.savez(r'E:\xbrt_scr\osm\fuji_pit_real.npz', pit=Pg, share=j / n, off=dist, sc=sc, R=R, t=t, mirror=mirror)
