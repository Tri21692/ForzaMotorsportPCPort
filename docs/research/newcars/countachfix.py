"""countachfix.py <in car.carbin> <out car.carbin>: the converted Countach (its source's glass crumpled, dropped; its
arches open into the shell) given glass panes in its window openings (the shell's open edge loops: the side and quarter
windows as fans; the windscreen lofted between its lower and upper edges) and black liners over its four wheels."""
import sys, os, struct, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars'); sys.path.insert(0, r'E:\xbrt_scr\carfix')
import numpy as np, carbin
from nfsu2forza import strip_tris, strip, WINDOW
import loops as LP
U = 4096 * 1.602
src, dst = sys.argv[1:3]
c = carbin.read(open(src, 'rb').read())
part = {p['name']: p for p in c['parts']}
body = part['bumperF_LOD1']
L = LP.loops(c)
PAINT_UV = (1625, 29945)  # build.log's "paint: texel at u, v = 0.025, 0.457" (the body's plain paint vertices have it)

def glass(name, pts, nrms, tris):
    """pts (metres), their outward normals, triangles over them: drawn from both sides. (11 Nov, the user's "striped
    pattern on the glass": first the template glass's texture coordinates by nearest vertex drew the livery atlas across
    the panes; a Most Wanted car's glass is drawn from the livery's paint texel, as the converter's. Then each
    triangle's own normal: a pane's edge is a few mm off flat, and the glass's reflection showed every wedge of the fan
    lighter or darker. One normal a pane, the windscreen's smooth across it.)"""
    p = part[name]
    verts = [tuple(int(round(x * U)) for x in q) + tuple(int(round(x * 32767)) for x in n) + (215, 205, 0, 0) + PAINT_UV for q, n in zip(pts, nrms)]
    tm = p['subparts'][0]
    ids = [s['id'] for s in p['subparts']]
    p['verts'] = verts
    both = [t for a_, b_, c_ in tris for t in ((a_, b_, c_), (a_, c_, b_))]
    p['subparts'] = [{'version': tm['version'], 'id': i, 'material': WINDOW, 'prim': 6, 'extra': bytes(16), 'indices': strip(both), 'tail': b''} for i in ids]
    print(name, len(tris), 'triangles')

def fan(name, Q, inset=0.004):
    c0 = Q.mean(0)
    n = np.linalg.svd(Q - c0)[2][2]
    if n[0] * c0[0] < 0: n = -n  # outward: away from the car's middle
    Q = Q - (Q - c0) @ n[:, None] * n - n * inset  # flat on its best plane, a little inside the frame
    k = len(Q)
    glass(name, [c0 - n * inset] + list(Q), [n] * (k + 1), [(0, 1 + i, 1 + (i + 1) % k) for i in range(k)])

def pick(test):
    got = [Q for perim, closed, Q in L if test(perim, closed, Q.mean(0), Q.max(0) - Q.min(0))]
    assert len(got) == 1, len(got)
    return got[0]
for nm, sg in (('L', -1), ('R', 1)):
    fan('glass%sF_LOD1' % nm, pick(lambda pe, cl, m, b: cl and sg * m[0] > 0.5 and m[1] > 0.8 and abs(m[2] - 0.07) < 0.1 and b[2] > 1.0))
    fan('glass%sR_LOD1' % nm, pick(lambda pe, cl, m, b: cl and sg * m[0] > 0.5 and m[1] > 0.8 and abs(m[2] + 0.57) < 0.1 and 0.25 < b[2] < 0.5))
# the windscreen: its lower edge (an open chain at y 0.69, z 1.05) and upper edge (y 0.99, z 0.22), each mirrored
lo = pick(lambda pe, cl, m, b: not cl and abs(m[1] - 0.69) < 0.03 and abs(m[2] - 1.05) < 0.05 and b[0] > 1.0)
hi = pick(lambda pe, cl, m, b: not cl and abs(m[1] - 0.99) < 0.02 and abs(m[2] - 0.22) < 0.05 and b[0] > 0.5)
def edge(Q, n=13):
    Q = np.vstack([Q, Q * [-1, 1, 1]]); Q = Q[np.argsort(Q[:, 0])]
    w = np.abs(Q[:, 0]).max()
    xs = np.linspace(-w, w, n)
    y, z = np.interp(xs, Q[:, 0], Q[:, 1]), np.interp(xs, Q[:, 0], Q[:, 2])
    cy, cz = np.polyfit(xs, y, 2), np.polyfit(xs, z, 2)  # a smooth bow, not the edge's every step
    return np.stack([xs, np.polyval(cy, xs), np.polyval(cz, xs)], 1)
A, B = edge(lo), edge(hi)
print('windscreen: lower edge half width %.2f at y %.2f z %.2f, upper %.2f at y %.2f z %.2f' % (A[-1, 0], A[:, 1].mean(), A[:, 2].mean(), B[-1, 0], B[:, 1].mean(), B[:, 2].mean()))
N = []
for i in range(len(A)):
    j0, j1 = max(0, i - 1), min(len(A) - 1, i + 1)
    n = np.cross(A[j1] - A[j0], B[i] - A[i]); n /= np.linalg.norm(n)
    N.append(n if n[1] > 0 else -n)
N = np.array(N)
k = len(A)
glass('glassF_LOD1', list(A - N * 0.004) + list(B - N * 0.004), list(N) + list(N),
      [t for i in range(k - 1) for t in ((i, i + 1, k + i + 1), (i, k + i + 1, k + i))])

# the arch liners
import tyrecheck
wb, zc, rf, rr, df, dr = tyrecheck.data('NCLamborghiniCountach'); hf, hr = tyrecheck.hubs_of(c, wb, zc)
V = np.array(body['verts'], float)
Pm = V[:, :3] / U
black = [s for s in body['subparts'] if s['id'] == 1 and s['material'] == 1][0]
bt = [t for t in strip_tris(black['indices']) if len(set(t)) == 3]
bv = body['verts'][bt[0][0]]  # a black vertex: its shading and the black texel
new, ntris = [], []
def add(q, n):
    new.append(tuple(int(round(x * U)) for x in q) + tuple(int(round(x * 32767)) for x in n) + tuple(bv[6:12]))
    return len(body['verts']) + len(new) - 1
for nm, hz, ride, dia in (('front', hf / 1.602, rf, df), ('rear', hr / 1.602, rr, dr)):
    hy = dia / 2 - ride
    dy, dz = Pm[:, 1] - hy, Pm[:, 2] - hz
    r = np.hypot(dy, dz); ang = np.degrees(np.arctan2(dy, dz))  # 0 towards the nose, 90 up
    for sg in (-1, 1):
        A_ = np.arange(-25, 206, 11)
        ring = []
        for a in A_:
            near = (np.abs((ang - a + 180) % 360 - 180) < 8) & (sg * Pm[:, 0] > 0.6) & (r > 0.30) & (r < 0.62)
            lip = near & (sg * Pm[:, 0] > 0.78)
            R = 0.42
            if lip.any(): R = min(R, max(0.375, np.percentile(r[lip], 3) + 0.02))
            top = near & (sg * Pm[:, 0] < 0.78)
            if top.any(): R = min(R, max(0.36, r[top].min() - 0.02))
            xo = (np.percentile(np.abs(Pm[lip, 0]), 50) if lip.any() else 0.9) - 0.05
            ring.append((R, xo))
        Rs = np.array([x[0] for x in ring]); xs = np.array([x[1] for x in ring])
        xs = np.minimum(xs, np.convolve(np.pad(xs, 1, mode='edge'), np.ones(3) / 3, 'valid'))
        print('%s %s liner: radius %.2f..%.2f, outer edge %.2f..%.2f' % (nm, 'LR'[sg > 0], Rs.min(), Rs.max(), xs.min(), xs.max()))
        xin = 0.50
        o, i_ = [], []
        for a, R, xo in zip(np.radians(A_), Rs, xs):
            d = np.array([0, np.sin(a), np.cos(a)]); q = np.array([0, hy, hz]) + R * d
            o.append(add(q + [sg * xo, 0, 0], -d)); i_.append(add(q + [sg * xin, 0, 0], -d))
        hub = add(np.array([sg * xin, hy, hz]), (sg, 0, 0))
        for k in range(len(A_) - 1):
            for t in ((o[k], i_[k], i_[k + 1]), (o[k], i_[k + 1], o[k + 1]), (hub, i_[k + 1], i_[k])):
                ntris += [t, (t[0], t[2], t[1])]  # both sides: black from within the shell too
body['verts'] = list(body['verts']) + new
cnt = struct.unpack_from('<I', body['Damage'][1])[0]
assert cnt == len(body['verts']) - len(new) and len(body['Damage'][1]) == 4 + 12 * cnt
body['Damage'] = (body['Damage'][0], struct.pack('<I', len(body['verts'])) + body['Damage'][1][4:] + b''.join(struct.pack('<6h', *v[:6]) for v in new))
s = list(black['indices']); t = strip(ntris)
s += [s[-1], t[0]]
if len(s) % 2: s.append(t[0])
black['indices'] = s + t
print('liners:', len(new), 'vertices,', len(ntris) // 2, 'triangles; body part', len(body['verts']), 'vertices')
open(dst, 'wb').write(carbin.write(c))
