"""Fuji Speedway in Forza, from Gran Turismo 4's layout and Road Atlanta's scenery (the user's, 2 Nov 2026:
build it from Forza's own models; GT4's only for what identifies the track).

  python tools/fujitrack.py layout <gt4 runway folder (tools/gt4runway.py's)> <out folder>
  python tools/fujitrack.py build <disc> <gt4 runway folder> <out folder>

layout: the track's centre line and edges, a point every STEP m round the lap in the driving direction,
from the GT4 runway's surface (gt4runway.py's road.obj: a group per surface, the first byte 0 tarmac,
1 kerb, 2 grass, 3 gravel, 0x0a painted line). The surface is rasterised at RES m; a first line through
the checkpoint gates' middles is moved, a few times over, to the middle of the tarmac across it, the
tarmac being bounded by the first other surface each side (the thin edge lines, kerbs and grass strips
that part the track from its paved run-off). Writes layout_edges.npz (centre, left, right: GT4
coordinates, metres) and layout_check.png (the surface with the edges drawn).

build: Fuji's surface drawn and solid in Road Atlanta's world (the disc's media\\tracks\\RoadAtlanta):
  - GT4's right-handed coordinates into Forza's left-handed world, a reflection (GT4 x along Forza z, GT4 z
    along Forza x), Fuji's middle on Road Atlanta's (its collision's): to_forza;
  - the runway's triangles as strips (Forza's ground faces have cross(p1 - p0, p2 - p0).y < 0 at an even
    place in the strip, Road Atlanta's own), by surface, written into small vertex buffers (those of
    quickpreview1.xbp.svb, loaded with the scenery and kept: the only ones a mesh moved far from its own
    place is drawn from) with the material of a Road Atlanta mesh of that surface (MATERIALS: texture,
    lightmap, shader, flags), packed by place as shipyardcircuit.pack does; their bounding spheres in the
    visibility's ppw moved onto them;
  - a visibility file whose every cell shows those meshes and streams their textures, and nothing of Road
    Atlanta's;
  - the collision: the runway's surface (ROAD/KERB/GRASS/GRAVEL codes as Road Atlanta's), walls round its
    outside, in a grid of 100 m cells grown to hold it (Fuji runs ~240 m longer than Road Atlanta);
  - the lap: Road Atlanta's six edge splines (road, drivable, curbing; inner and outer) through Fuji's
    edges, each as many points as it had, point 0 on GT4's start line.
Writes out\\roadatlanta.res (the scenery, the cache's name), QuickPreview1.col, QuickPreview1.pvs,
QuickPreview1.pvs.ppw, quickpreview1.xbp.svb, fuji_forza.npz (the edges in Forza's world) and build_check.png.
"""
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forzaxpr

RES = 0.25         # m a raster cell
STEP = 2.0         # m between the line's points
SEARCH = 70.0      # m each side the cross-section looks
MAX_HALF = 11.0    # m: a side's edge at most this far from the line (where run-off tarmac carries on)
GROW = 2           # cells the edge surfaces are thickened by: drawn at RES, the thin edge strips broke into dots and the tarmac leaked through
TARMAC, KERB, GRASS, GRAVEL, LINE = 0, 1, 2, 3, 0x0A


def read_runway_obj(path):
    V, F, g = [], [], 0
    for l in open(path):
        if l.startswith('v '): V.append(list(map(float, l.split()[1:4])))
        elif l.startswith('g '): g = int(l.split()[1][1:3], 16)
        elif l.startswith('f '): F.append([int(x) - 1 for x in l.split()[1:4]] + [g])
    return np.array(V), np.array(F)


class Raster:
    """The surface types from above: x across, z down the array's rows (-1 where nothing)."""

    def __init__(self, V, F, res=RES, pad=5.0):
        self.res = res
        self.lo = V[:, [0, 2]].min(0) - pad
        hi = V[:, [0, 2]].max(0) + pad
        self.shape = (int((hi[1] - self.lo[1]) / res) + 1, int((hi[0] - self.lo[0]) / res) + 1)
        self.k = np.full(self.shape, -1, np.int16)
        self.y = np.full(self.shape, np.nan, np.float32)
        P = (V[:, [0, 2]] - self.lo) / res
        order = np.argsort([0 if k == TARMAC else 1 for k in F[:, 3]], kind='stable')  # the thin surfaces drawn last, over tarmac
        for a, b, c, k in F[order]:
            t = P[[a, b, c]]
            lo = np.floor(t.min(0)).astype(int); hi = np.ceil(t.max(0)).astype(int)
            lo = np.maximum(lo, 0); hi = np.minimum(hi, [self.shape[1] - 1, self.shape[0] - 1])
            if (hi < lo).any(): continue
            xx, zz = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
            v0, v1 = t[1] - t[0], t[2] - t[0]
            det = v0[0] * v1[1] - v0[1] * v1[0]
            if abs(det) < 1e-12: continue
            qx, qz = xx + 0.5 - t[0][0], zz + 0.5 - t[0][1]
            u = (qx * v1[1] - qz * v1[0]) / det
            w = (v0[0] * qz - v0[1] * qx) / det
            m = (u >= -1e-6) & (w >= -1e-6) & (u + w <= 1 + 1e-6)
            self.k[zz[m], xx[m]] = k
            ys = V[[a, b, c], 1]
            self.y[zz[m], xx[m]] = ys[0] + u[m] * (ys[1] - ys[0]) + w[m] * (ys[2] - ys[0])

    def grow_edges(self, n=GROW):
        """The kerbs, lines and grass thickened by n cells over tarmac, so a thin strip stays a closed edge."""
        edge = (self.k != TARMAC) & (self.k >= 0)
        g = edge.copy()
        for dz in range(-n, n + 1):
            for dx in range(-n, n + 1):
                if dx * dx + dz * dz <= n * n: g |= np.roll(np.roll(edge, dz, 0), dx, 1)
        self.k[g & (self.k == TARMAC)] = GRASS

    def at(self, xz):
        ij = np.floor((xz - self.lo) / self.res).astype(int)
        ok = (ij[..., 0] >= 0) & (ij[..., 1] >= 0) & (ij[..., 0] < self.shape[1]) & (ij[..., 1] < self.shape[0])
        out = np.full(xz.shape[:-1], -1, np.int16)
        out[ok] = self.k[ij[..., 1][ok], ij[..., 0][ok]]
        return out


def closed_resample(p, step):
    """The closed polyline p (n x 2) as points `step` apart."""
    q = np.vstack([p, p[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    t = np.arange(0, s[-1], step)
    return np.stack([np.interp(t, s, q[:, j]) for j in range(q.shape[1])], 1)


def smooth_closed(p, n):
    if n < 2: return p
    k = np.ones(n) / n
    ext = np.vstack([p[-n:], p, p[:n]])
    return np.stack([np.convolve(ext[:, j], k, 'same')[n:-n] for j in range(p.shape[1])], 1)


def cross_sections(r, c):
    """For each point of the closed line c (n x 2): its left and right offsets to the track's edges
    (positive left), or nan where no tarmac is found near it."""
    t = np.roll(c, -1, 0) - np.roll(c, 1, 0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    nrm = np.stack([-t[:, 1], t[:, 0]], 1)  # left of the way round (x right, z down the raster)
    offs = np.arange(-SEARCH, SEARCH + RES, RES)
    pts = c[:, None, :] + offs[None, :, None] * nrm[:, None, :]
    k = r.at(pts)
    zero = len(offs) // 2
    left, right = np.full(len(c), np.nan), np.full(len(c), np.nan)
    for i in range(len(c)):
        row = k[i] == TARMAC
        if not row.any(): continue
        if not row[zero]:  # the line is off the tarmac here: the nearest tarmac across it
            j = np.flatnonzero(row)
            zi = j[np.argmin(np.abs(j - zero))]
        else:
            zi = zero
        a = zi
        while a > 0 and row[a - 1]: a -= 1
        b = zi
        while b < len(row) - 1 and row[b + 1]: b += 1
        lo, hi = offs[a], offs[b]
        mid = offs[zi]
        right[i] = max(lo, mid - MAX_HALF)
        left[i] = min(hi, mid + MAX_HALF)
    return left, right, nrm


def ai_points(runway_dir):
    """The AI racing lines' points (x, z) from the course's autodrive file (<runway folder>/*.ad: PDTools'
    Courses/Autodrive layout: 'ADLN' at 0x80, its lines' records 0x40 bytes from 0x40 into each, x and z at +4)."""
    import glob
    ads = glob.glob(os.path.join(runway_dir, '*.ad'))
    if not ads: return np.zeros((0, 2))
    d = open(ads[0], 'rb').read()
    b = 0x80
    if d[b:b + 4] != b'ADLN': return np.zeros((0, 2))
    n_lines, aoff = struct.unpack_from('<ii', d, b + 20)
    pts = []
    for i in range(n_lines):
        io = b + struct.unpack_from('<i', d, b + aoff + 4 * i)[0]
        n = struct.unpack_from('<i', d, io)[0]
        pts += [struct.unpack_from('<2f', d, io + 0x40 + k * 0x40 + 4) for k in range(n)]
    return np.array(pts, float).reshape(-1, 2) * (-1, 1)  # (x turned round: as read, 155 of Fuji's 229 lay off the runway; turned, all on it)


def layout(runway_dir, out):
    V, F = read_runway_obj(os.path.join(runway_dir, 'road.obj'))
    L = json.load(open(os.path.join(runway_dir, 'layout.json')))
    cps = sorted(L['checkpoints'], key=lambda c: c['v'])
    r = Raster(V, F)
    r.grow_edges()
    print('raster %d x %d at %.2f m' % (r.shape[1], r.shape[0], RES))
    c = closed_resample(np.array([[cp['mid'][0], cp['mid'][2]] for cp in cps]), STEP)
    ai = ai_points(runway_dir)
    if len(ai):  # the AI's racing lines lie on the track proper (the gates' middles ran through paved run-off at
        # the hairpin): ordered round the lap by the gates' line, they are the first line, then re-centred
        at = np.array([np.argmin(np.hypot(*(c - p).T)) for p in ai])
        bins = (at // 10).astype(int)  # (the lines run side by side: averaged a 20 m stretch, not interleaved)
        mids = np.array([ai[bins == k].mean(0) for k in np.unique(bins)])
        c = closed_resample(smooth_closed(closed_resample(mids, STEP), 9), STEP)
        print('first line: %d AI points' % len(ai))
    for it in range(8):
        left, right, nrm = cross_sections(r, c)
        ok = np.isfinite(left)
        mid = np.where(ok, (left + right) / 2, 0.0)
        mid = smooth_closed(mid[:, None], 11)[:, 0]  # (the offsets smoothed first: raw, the line zigzagged and the lap read 20% long)
        c = c + nrm * mid[:, None]
        c = closed_resample(smooth_closed(c, 9), STEP)
        w = (left - right)[ok]
        print('pass %d: %d points, %d without tarmac, width median %.1f m (%.1f..%.1f)' % (it, len(c), (~ok).sum(), np.median(w), w.min(), w.max()))
    left, right, nrm = cross_sections(r, c)
    for a in (left, right):  # gaps (no tarmac found): the neighbours' offsets
        bad = ~np.isfinite(a)
        if bad.any(): a[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), a[~bad], period=len(a))
    left, right = smooth_closed(left[:, None], 9)[:, 0], smooth_closed(right[:, None], 9)[:, 0]
    L3 = lambda off: np.stack([c[:, 0] + nrm[:, 0] * off, np.zeros(len(c)), c[:, 1] + nrm[:, 1] * off], 1)
    lp, rp, cp3 = L3(left), L3(right), L3(np.zeros(len(c)))
    for p in (lp, rp, cp3):  # heights: the surface's under each point
        ij = np.floor((p[:, [0, 2]] - r.lo) / r.res).astype(int)
        ij = np.clip(ij, 0, [r.shape[1] - 1, r.shape[0] - 1])
        p[:, 1] = r.y[ij[:, 1], ij[:, 0]]
        bad = ~np.isfinite(p[:, 1])
        if bad.any(): p[bad, 1] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), p[~bad, 1], period=len(p))
    os.makedirs(out, exist_ok=True)
    np.savez(os.path.join(out, 'layout_edges.npz'), centre=cp3, left=lp, right=rp)
    length = np.linalg.norm(np.diff(np.vstack([cp3, cp3[:1]]), axis=0), axis=1).sum()
    print('lap %.0f m, %d points; width median %.1f m, %.1f..%.1f' % (length, len(c), np.median(left - right), (left - right).min(), (left - right).max()))
    check_png(r, [lp, rp, cp3], os.path.join(out, 'layout_check.png'))


def check_png(r, lines, path, px=2400):
    pal = np.array([(90, 90, 95), (220, 40, 40), (60, 150, 60), (220, 200, 120)] + [(40, 40, 40)] * 6 + [(60, 120, 230)], np.uint8)
    sx = max(r.shape) / px
    ys = (np.arange(int(r.shape[0] / sx)) * sx).astype(int)
    xs = (np.arange(int(r.shape[1] / sx)) * sx).astype(int)
    k = r.k[ys][:, xs]
    img = np.zeros(k.shape + (4,), np.uint8); img[..., 3] = 255; img[..., :3] = 25
    m = k >= 0
    img[m, :3] = pal[np.clip(k[m], 0, len(pal) - 1)]
    for p, col in zip(lines, ((255, 255, 255), (255, 255, 0), (255, 0, 255))):
        q = ((p[:, [0, 2]] - r.lo) / r.res / sx).astype(int)
        q = q[(q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < img.shape[1]) & (q[:, 1] < img.shape[0])]
        img[q[:, 1], q[:, 0], :3] = col
    forzaxpr.png(path, img)


# ---- build: Road Atlanta's data

DONOR_TRACK = 'RoadAtlanta'
RA_MIDDLE = (-398.5, 473.5)     # Road Atlanta's collision's middle (x, z): x -870..73, z -317..1264
GT4_MIDDLE = (111.4, 106.7)     # the Fuji runway's (x, z): x -797..1020, z -195..408
# the materials: a Road Atlanta mesh of plain 24-byte vertices whose way of drawing it takes (flags, lightmap,
# shader 13407, a lit diffuse), the texture (None: that mesh's own) and the metres a repeat. Road Atlanta's kerbs
# and gravel traps have richer vertices (flags 0x2000), so their textures are drawn the tarmac's way.
MATERIALS = {TARMAC: (64, None, 8.0), KERB: (64, 497, 4.0), GRASS: (83, None, 24.0), GRAVEL: (64, 508, 10.0), LINE: (64, None, 8.0)}
# a lightmap texel each material samples (lightmap coordinates are (s + 32768) / 512 across the lightmap): a
# mid-lit one, ~85 of 255 (the templates' own median texels were 106, the road looked washed out, and for the grass
# a black, clear texel at the lightmap's edge)
LIGHT = {101: (-32615, -32406), 137: (-32439, -32451)}
COLLISION = {TARMAC: 0x0000, LINE: 0x0000, KERB: 0x0600, GRASS: 0x0200, GRAVEL: 0x1B00}  # Road Atlanta's codes for them
WALL, WALL_H = 0x0400, 2.0      # round the runway's outside: a tyre wall's code, this high
KERB_W = 1.2                    # m across a kerb's texture (its stripes along the track)
REACH = 120.0                   # m: a donor's faces within this of its first
GRASS_REACH = 30.0              # m: grass drawn this near the centre line only (all of it solid): the small buffers ran out
SLIVER = 0.02                   # m2: thinner triangles not drawn
SPLINES = ('roadinner', 'roadouter', 'drivableinner', 'drivableouter', 'curbinginner', 'curbingouter')


def to_forza(p):
    """GT4 (x, y, z) to Forza's world: a reflection (right- to left-handed) with Fuji's long axis along
    Road Atlanta's: Forza x from GT4 z, Forza z from GT4 x, the middles laid on each other."""
    p = np.asarray(p, float)
    out = np.empty_like(p)
    out[..., 0] = p[..., 2] - GT4_MIDDLE[1] + RA_MIDDLE[0]
    out[..., 1] = p[..., 1]
    out[..., 2] = p[..., 0] - GT4_MIDDLE[0] + RA_MIDDLE[1]
    return out


def model_offset(res, names):
    return next(r[3] for r in names if r[0] == 'model_quickpreview')


def record(res, model, i):
    a = struct.unpack_from('<I', res, model + 4 + 4 * i)[0]
    return model + a, struct.unpack_from('<IIIIHHHHHH', res, model + a)


def strips_of(tris):
    """Triangles (k x 3 vertex indices, each wound as Forza's ground: cross.y < 0) as strips, greedily: each
    strip starts at a free triangle with the fewest free neighbours (the classic choice: ends of runs first)
    from whichever of its three rotations goes furthest, and runs on across the edge its last two vertices
    make while a neighbour shares it the strip's way. Each strip's triangle at an even place keeps the
    triangles' winding. Returns lists of vertex indices."""
    from collections import defaultdict
    edge = defaultdict(list)
    for t, (a, b, c) in enumerate(tris):
        for u, v in ((a, b), (b, c), (c, a)): edge[(u, v)].append(t)
    nbrs = [[t2 for u, v in ((a, b), (b, c), (c, a)) for t2 in edge.get((v, u), ()) if t2 != t] for t, (a, b, c) in enumerate(tris)]
    used = np.zeros(len(tris), bool)

    def run(start, s0):
        s, taken = list(s0), [start]
        seen = {start}
        while True:
            # the next triangle, at place len(s) - 2, is drawn (s[-1], s[-2], w) at an odd place and
            # (s[-2], s[-1], w) at an even one: the neighbour wound as ours holds that directed edge
            u, v = (s[-1], s[-2]) if (len(s) - 2) % 2 == 1 else (s[-2], s[-1])
            nxt = next((t for t in edge.get((u, v), ()) if not used[t] and t not in seen), None)
            if nxt is None: break
            w = [x for x in tris[nxt] if x not in (u, v)]
            if len(w) != 1: break
            seen.add(nxt); taken.append(nxt); s.append(w[0])
        return s, taken

    import heapq
    heap = [(len(nb), t) for t, nb in enumerate(nbrs)]
    heapq.heapify(heap)
    out = []
    while heap:
        _, t0 = heapq.heappop(heap)
        if used[t0]: continue
        free = sum(not used[t] for t in nbrs[t0])
        if heap and free > heap[0][0]:  # (its count went down since it was pushed: pushed again as it is now)
            heapq.heappush(heap, (free, t0)); continue
        a, b, c = tris[t0]
        best = max((run(t0, r) for r in ((a, b, c), (b, c, a), (c, a, b))), key=lambda st: len(st[1]))
        for t in best[1]:
            used[t] = True
            for t2 in nbrs[t]:
                if not used[t2]: heapq.heappush(heap, (sum(not used[x] for x in nbrs[t2]), t2))
        out.append(best[0])
    return out


def build(disc, runway_dir, out):
    import xb2
    import coledit
    import shipyardcircuit as sc
    import addcar
    folder = addcar.disc_file(disc, 'media', 'tracks', DONOR_TRACK)
    files = {f.lower(): os.path.join(folder, f) for f in os.listdir(folder)}
    res = bytearray(xb2.unpack(files['quickpreview1.xb2']))
    names, _ = xb2.resources(bytes(res))
    model = model_offset(res, names)
    global ORIG_RES, RA_CENTRE
    ORIG_RES = bytes(res)
    RA_CENTRE = np.mean([np.frombuffer(bytes(res[r[3]:r[3] + 12 * ((r[4] + 4) // 16)]), '<f4').reshape(-1, 3).astype(float)
                         for r in names if r[0] in ('vbuff_quickpreview_splines_roadinner_vb0', 'vbuff_quickpreview_splines_roadouter_vb0')], 0)
    svb_raw = xb2.unpack(files['quickpreview1.xbp.svb'])
    svb = sc.read_svb(svb_raw)
    svb_out = bytearray(svb_raw)
    ppw = bytearray(open(files['quickpreview1.pvs.ppw'], 'rb').read())
    pvs_in = open(files['quickpreview1.pvs'], 'rb').read()

    # the surface, in Forza's world, each triangle wound face-up the game's way
    V, F = read_runway_obj(os.path.join(runway_dir, 'road.obj'))
    Vf = to_forza(V)
    T = F[:, :3].copy()
    n = np.cross(Vf[T[:, 1]] - Vf[T[:, 0]], Vf[T[:, 2]] - Vf[T[:, 0]])
    flip = n[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    kinds = np.where(F[:, 3] == LINE, TARMAC, F[:, 3])
    kinds = np.where(np.isin(kinds, list(MATERIALS)), kinds, GRASS)

    # what is drawn: all but far grass and slivers (the collision keeps every triangle)
    E = np.load(os.path.join(runway_dir if os.path.exists(os.path.join(runway_dir, 'layout_edges.npz')) else out, 'layout_edges.npz'))
    cen_g = E['centre'][:, [0, 2]]
    cent = V[F[:, :3]].mean(1)[:, [0, 2]]
    dist = np.array([np.min(np.hypot(*(cen_g - p).T)) for p in cent])
    area = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1) / 2
    drawn = (area >= SLIVER) & ~((kinds == GRASS) & (dist > GRASS_REACH))
    print('drawn: %d of %d triangles (grass beyond %.0f m and slivers left out)' % (drawn.sum(), len(T), GRASS_REACH))

    # each vertex's place along the lap (m from the lap line) and across it (m left of the centre line): the
    # kerbs' texture follows the track
    cl = to_forza(E['centre'])[:, [0, 2]]
    seg = np.linalg.norm(np.diff(np.vstack([cl, cl[:1]]), axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)[:-1]])
    lap = seg.sum()
    tang = np.roll(cl, -1, 0) - np.roll(cl, 1, 0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    along, side = np.zeros(len(Vf)), np.zeros(len(Vf))
    for i0 in range(0, len(Vf), 2000):
        q = Vf[i0:i0 + 2000, [0, 2]]
        j = np.argmin(((q[:, None, :] - cl[None]) ** 2).sum(2), axis=1)
        dvec = q - cl[j]
        along[i0:i0 + 2000] = arc[j] + (dvec * tang[j]).sum(1)
        side[i0:i0 + 2000] = dvec[:, 0] * -tang[j, 1] + dvec[:, 1] * tang[j, 0]

    # the donors: small stride-6 strips of 24-byte vertices in the svb, with a ppw sphere found
    nmesh = struct.unpack_from('<I', res, model)[0]
    pool = []
    for i in range(nmesh):
        at, (fl, ab, nidx, vbytes, vb, stride, prim, t0, t1, sh) = record(res, model, i)
        if stride != 6 or prim != 6 or vbytes % 24 or vb not in svb or nidx < 8 or vbytes < 24 * 4: continue
        if i in {m for m, _, _ in MATERIALS.values()}: continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, :3].astype(float)
        if not np.all(np.isfinite(v)): continue
        pool.append([vbytes // 24, nidx, i, sphere_offset(i), vb])
    pool.sort(key=lambda r: -r[0])
    print('donors: %d small meshes, room for %d vertices and %d indices' % (len(pool), sum(r[0] for r in pool), sum(r[1] for r in pool)))

    # strips per surface, then packed by place into donors
    jobs = []
    for k in sorted(set(kinds.tolist())):
        tk = T[(kinds == k) & drawn]
        for s in strips_of([tuple(t) for t in tk]):
            jobs.append((k, s))
    nstrip_idx = sum(len(s) + 3 for _, s in jobs)
    print('surface: %d triangles in %d strips (~%d indices with the joins)' % (len(T), len(jobs), nstrip_idx))
    placed, left = pack_strips(jobs, Vf, pool)
    if left: raise SystemExit('out of donor meshes: %d strips left over' % left)

    # each donor rewritten: its material's texture, lightmap, shader, flags; planar texture coordinates
    tex_used, vbs_used, meshes = set(), set(), []
    for mesh, sp, vb, k, strips in placed:
        mat, tex, metres = MATERIALS[k]
        _, (mfl, _, _, _, _, _, _, mt0, mt1, msh) = record(res, model, mat)
        mt0 = tex or mt0
        mo = names[record(res, model, mat)[1][4] - 9][3]
        mst = np.frombuffer(bytes(res[mo:mo + 24 * record(res, model, mat)[1][3] // 24]), '<i2').reshape(-1, 12)[:, 8:12]
        light = LIGHT.get(mt1) or tuple(int(x) for x in np.median(mst[:, 2:4], 0))
        at, (fl, ab, nidx, vbytes, vbr, stride, prim, t0, t1, sh) = record(res, model, mesh)
        pts = np.vstack([Vf[s] for s in strips])
        org = np.floor(pts.min(0) / metres) * metres  # (texture coordinates from a whole repeat near the faces: s16 holds +-64 repeats)
        if k == KERB:  # along the track (its stripes across it): s across, `metres` a repeat along
            ids_all = sorted({vi for s in strips for vi in s})
            al = along[ids_all]
            if al.max() - al.min() > lap / 2: al = np.where(al < lap / 2, al + lap, al)  # (a donor over the lap line)
            a0 = np.floor(al.min() / metres) * metres
            s0 = np.floor(side[ids_all].min() / KERB_W) * KERB_W
            uv = {vi: (int((side[vi] - s0) / KERB_W * 512) - 32768, int((a - a0) / metres * 512) - 32768) for vi, a in zip(ids_all, al)}
        verts, order, local = [], [], {}  # (a vertex once a donor, its strips indexing it)
        for s in strips:
            ids = []
            for vi in s:
                if vi not in local:
                    local[vi] = len(verts)
                    p = Vf[vi]
                    if k == KERB: verts.append((p,) + uv[vi])
                    else: verts.append((p, int((p[0] - org[0]) / metres * 512) - 32768, int((p[2] - org[2]) / metres * 512) - 32768))
                ids.append(local[vi])
            if order:
                order += [order[-1], ids[0]]
                if len(order) % 2: order.append(ids[0])
            order += ids
        nv = vbytes // 24
        assert len(verts) <= nv and len(order) <= nidx, (mesh, len(verts), nv, len(order), nidx)
        dt = np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)])
        buf = np.zeros(nv, dt)
        for j in range(nv):
            p, s_, t_ = verts[min(j, len(verts) - 1)]
            buf['p'][j] = p
            buf['n'][j] = sc.pack_normal((0.0, 1.0, 0.0))
            buf['st'][j] = (s_, t_, light[0], light[1])
        o = names[vbr - 9][3]
        data = buf.tobytes() + np.array(order + [order[-1]] * (nidx - len(order)), '<u2').tobytes()
        res[o:o + len(data)] = data
        so, ssz = svb[vbr]
        assert ssz >= len(data), (mesh, ssz, len(data))
        svb_out[so:so + len(data)] = data
        struct.pack_into('<HHH', res, at + 22, mt0, mt1, msh)
        struct.pack_into('<I', res, at, mfl)
        c = (pts.min(0) + pts.max(0)) / 2
        struct.pack_into('<4f', ppw, sp, float(np.max(np.linalg.norm(pts - c, axis=1))) + 0.5, *c)
        tex_used |= {mt0, mt1}
        vbs_used.add(vbr)
        meshes.append(mesh)
    print('drawn: %d donor meshes; textures %s' % (len(meshes), sorted(tex_used)))

    # Road Atlanta's own objects moved beside Fuji (OBJECTS), drawn in every cell with their buffers streamed in
    om, ot, ov = move_objects(res, names, model, ppw, svb, svb_out, to_forza(E['centre']), to_forza(E['right']), to_forza(E['left']))
    meshes += om; tex_used |= ot; vbs_used |= ov

    # the visibility: every cell the same, Fuji's meshes only
    import shipyardloop as sl
    head, cells, tail = sl.parse_pvs(pvs_in)
    cell = []
    for li, objs, rest in ((0, sorted(meshes), b''), (1, sorted(tex_used), bytes(4)), (2, sorted(vbs_used), b'')):
        cell.append(struct.pack('<I', len(objs)) + b''.join(struct.pack('<HH', o_, 0xFFFF) + rest for o_ in objs))
    pvs = head + struct.pack('<I', len(cells)) + b''.join(cell) * len(cells) + tail

    # the collision: Road Atlanta's file emptied, its grid grown over Fuji
    col = coledit.Col(open(files['quickpreview1.col'], 'rb').read())
    lo = np.floor((Vf[:, [0, 2]].min(0) - 30) / 100) * 100
    hi = np.ceil((Vf[:, [0, 2]].max(0) + 30) / 100) * 100
    col.cols, col.rows = int((hi[0] - lo[0]) // 100), int((hi[1] - lo[1]) // 100)
    col.box = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
    col.blocks = []
    for (a, b, c_), k in zip(T, kinds):
        col.add_ground(COLLISION.get(int(k), 0x0200), Vf[[a, b, c_]])
    walls = outside_walls(Vf, T)
    for q in walls:
        col.add(WALL, q[:3]); col.add(WALL, q[[0, 2, 3]])
    col_bytes = col.to_bytes()
    big = max(len(col.block_bytes(b)) for b in col.blocks)
    print('collision: grid %d x %d, %d blocks, the largest %d KB; %d wall quads' % (col.cols, col.rows, len(col.blocks), big >> 10, len(walls)))

    # the lap: Fuji's edges into the six edge splines
    cen, lef, rig = to_forza(E['centre']), to_forza(E['left']), to_forza(E['right'])
    area = 0.5 * np.sum(cen[:-1, 0] * cen[1:, 2] - cen[1:, 0] * cen[:-1, 2])
    inner, outer = (rig, lef) if area < 0 else (lef, rig)  # (round a clockwise loop, the right edge is inside)
    print('lap: signed area %.0f (Road Atlanta\'s negative: %s)' % (area, 'same way round' if area < 0 else 'REVERSED'))
    for nm in SPLINES:
        r = next(r for r in names if r[0] == 'vbuff_quickpreview_splines_%s_vb0' % nm)
        npt = (r[4] + 4) // 16
        e = inner if nm.endswith('inner') else outer
        res[r[3]:r[3] + 12 * npt] = open_lap(e, npt).astype('<f4').tobytes()

    os.makedirs(out, exist_ok=True)
    for name, data in (('roadatlanta.res', res), ('QuickPreview1.col', col_bytes), ('QuickPreview1.pvs', pvs),
                       ('QuickPreview1.pvs.ppw', ppw), ('quickpreview1.xbp.svb', zlib_like(files['quickpreview1.xbp.svb'], svb_out))):
        open(os.path.join(out, name), 'wb').write(bytes(data))
    np.savez(os.path.join(out, 'fuji_forza.npz'), centre=cen, inner=inner, outer=outer)
    build_png(placed, Vf, os.path.join(out, 'build_check.png'))


# Road Atlanta objects set beside Fuji: (its vertex buffers' name stem, where along the lap (a share of it), which
# side ('pit': the inside of the loop, the right going round; 'out': the outside), metres out from the track's edge).
# The pit building and pit stands along the main straight's pit side, the grandstands across from them.
OBJECTS = [('pirellabuilding', 0.10, 'pit', 30.0), ('garages01', 0.16, 'pit', 30.0), ('outerpitstands01', 0.05, 'out', 12.0)]


def sphere_offset(i):
    """Mesh i's bounding sphere in QuickPreview1.pvs.ppw: after a u32 version and a 16-byte id, a 21-byte record a
    mesh in model_quickpreview's order (f32 radius, centre x, y, z, u32, a byte). (Searched for by value before,
    shipyardcircuit.sphere_at; a building's sphere is the mesh's own but not its vertices' box, and was missed.)"""
    return 20 + 21 * i


def object_meshes(res, names, model, stem):
    """The meshes of model_quickpreview whose vertex buffer is vbuff_quickpreview_<stem>[_vbN]: [(mesh, record
    offset, fields)]."""
    import re
    pat = re.compile(r'vbuff_quickpreview_%s(_vb\d+)?$' % re.escape(stem))
    out = []
    for i in range(struct.unpack_from('<I', res, model)[0]):
        at, f = record(res, model, i)
        vb = f[4]
        if 9 <= vb < len(names) + 9 and pat.match(names[vb - 9][0]): out.append((i, at, f))
    return out


def move_objects(res, names, model, ppw, svb, svb_out, centre, right, left):
    """Each of OBJECTS' meshes turned and moved to its place by Fuji: turned so the way it faced Road Atlanta's
    track (from its middle to the nearest point of Road Atlanta's centre line) faces Fuji's, its feet on the
    track's height there; normals turned with it; bounding spheres in the ppw moved (a mesh whose sphere is not
    found is left out). Returns (meshes, textures, vertex buffers) to show and stream in every cell."""
    import shipyardcircuit as sc
    meshes, texs, vbs = [], set(), set()
    seg = np.linalg.norm(np.diff(np.vstack([centre, centre[:1]]), axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)])
    for stem, share, side, out in OBJECTS:
        ms = object_meshes(res, names, model, stem)
        if not ms: print('object %s: no meshes' % stem); continue
        bufs = {}
        for i, at, f in ms: bufs[f[4]] = f[5]  # vertex buffer: stride (dwords)
        allp = []
        for vb, stride in bufs.items():
            o, size = names[vb - 9][3], names[vb - 9][4]
            n = size // (4 * stride)
            v = np.frombuffer(bytes(res[o:o + n * 4 * stride]), '<f4').reshape(n, stride)[:, :3].astype(float)
            ok = np.all(np.isfinite(v), 1) & (np.abs(v).max(1) < 5000)
            allp.append(v[ok])
        allp = np.vstack(allp)
        mid = (allp.min(0) + allp.max(0)) / 2
        foot = allp[:, 1].min()
        near = RA_CENTRE[np.argmin(np.hypot(*(RA_CENTRE[:, [0, 2]] - mid[[0, 2]]).T))]
        face_from = np.arctan2(near[2] - mid[2], near[0] - mid[0])
        # its place: `share` round Fuji's lap, `out` m beyond that side's edge
        i0 = int(np.searchsorted(arc, share * arc[-1])) % len(centre)
        edge = right[i0] if side == 'pit' else left[i0]
        away = edge - centre[i0]; away[1] = 0; away /= np.linalg.norm(away)
        target = edge + away * out
        face_to = np.arctan2(-away[2], -away[0])
        a = face_to - face_from
        R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])  # (x, z) turned by a
        lift = centre[i0][1] - foot
        for vb, stride in bufs.items():
            o, size = names[vb - 9][3], names[vb - 9][4]
            n = size // (4 * stride)
            raw = np.frombuffer(bytes(res[o:o + n * 4 * stride]), '<u4').reshape(n, stride).copy()
            v = raw[:, :3].view('<f4').astype(float)
            xz = (v[:, [0, 2]] - mid[[0, 2]]) @ R.T + target[[0, 2]]
            v[:, 0], v[:, 2], v[:, 1] = xz[:, 0], xz[:, 1], v[:, 1] + lift
            raw[:, :3] = v.astype('<f4').view('<u4')
            if stride >= 5:  # its normals turned the same way
                for j in range(n):
                    nv_ = sc.unpack_normal(int(raw[j, 3]))
                    nxz = R @ nv_[[0, 2]]
                    raw[j, 3] = sc.pack_normal((nxz[0], nv_[1], nxz[1]))
            data = raw.tobytes()
            res[o:o + len(data)] = data
            if vb in svb:
                so, ssz = svb[vb]
                svb_out[so:so + min(ssz, len(data))] = data[:ssz]
            vbs.add(vb)
        shown = 0
        for i, at, f in ms:
            fl, ab, nidx, vbytes, vb, stride, prim, t0, t1, sh = f
            o = names[vb - 9][3]
            n = vbytes // (4 * stride) if stride else 0
            if not n: continue
            now = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(n, stride)[:, :3].astype(float)
            sp = sphere_offset(i)
            c1 = (now.min(0) + now.max(0)) / 2
            struct.pack_into('<4f', ppw, sp, float(np.max(np.linalg.norm(now - c1, axis=1))) + 0.5, *c1)
            meshes.append(i); texs |= {t0, t1}; shown += 1
        print('object %s: %d meshes (%d shown), %d buffers, at %.0f%% of the lap, %s side, turned %.0f degrees' % (stem, len(ms), shown, len(bufs), 100 * share, side, np.degrees(a)))
    return meshes, texs, vbs


def zlib_like(src_path, data):
    """data packed as the disc's file at src_path is (zlib when it is)."""
    import zlib
    return zlib.compress(bytes(data), 9) if open(src_path, 'rb').read(1) == b'\x78' else bytes(data)


def cut(s, size):
    """Strip s as pieces of at most `size` vertices, cut at even places (each keeps the winding), each
    starting on its predecessor's last two vertices."""
    size -= size % 2
    if len(s) <= size: return [s]
    out, i = [], 0
    while i < len(s) - 2:
        j = min(i + size, len(s))
        out.append(s[i:j])
        i = j - 2
    return out


def pack_strips(jobs, Vf, pool, reach=REACH):
    """Strips (surface, vertex indices) into donors (pool rows: [vertices, indices, mesh, sphere, buffer]),
    one surface a donor: from the west, a seed strip and the strips within `reach` m of it, nearest first,
    while they fit (vertices shared by a donor's strips count once; joins cost 2 or 3 indices); a seed too
    long for the largest donor left is cut to fit it. Returns ([(mesh, sphere, buffer, surface, [strips])],
    strips left over)."""
    pool = sorted(pool, key=lambda r: -min(r[0], r[1] - 3))
    mid = lambda s: Vf[s][:, [0, 2]].mean(0)
    out = []
    by = {}
    for k, s in jobs: by.setdefault(k, []).append(s)
    for k in sorted(by, key=lambda k_: -len(by[k_])):
        q = list(by[k])
        cen = [mid(s) for s in q]
        alive = [True] * len(q)
        while any(alive):
            if not pool: return out, sum(alive) + sum(len(by[k_]) for k_ in by if k_ != k and not any(o[3] == k_ for o in out))
            nv, nidx, mesh, sp, vb = pool.pop(0)
            live = [i for i, a in enumerate(alive) if a]
            seed = min(live, key=lambda i: (cen[i][0], cen[i][1]))
            room = min(nv, nidx)
            if len(q[seed]) > room:  # cut to this donor's size: the rest go back in the queue
                parts = cut(q[seed], room)
                alive[seed] = False
                for pc in parts:
                    q.append(pc); cen.append(mid(pc)); alive.append(True)
                seed = len(q) - len(parts)
                live = [i for i, a in enumerate(alive) if a]
            c0 = cen[seed]
            live.sort(key=lambda i: (i != seed, np.hypot(cen[i][0] - c0[0], cen[i][1] - c0[1])))
            took, have, ix = [], set(), 0
            for i in live:
                if took and np.hypot(cen[i][0] - c0[0], cen[i][1] - c0[1]) > reach: break
                s = q[i]
                join = (2 + ((ix + 2) % 2)) if took else 0
                if len(have | set(s)) > nv or ix + join + len(s) > nidx: continue
                took.append(s); have |= set(s); ix += join + len(s); alive[i] = False
            if took: out.append((mesh, sp, vb, k, took))
    return out, 0


def outside_walls(Vf, T, h=WALL_H):
    """Quads standing on the surface's boundary (edges with one triangle), each facing the surface (the
    game's walls have one face, toward the drivable side: shipyardcircuit's lesson)."""
    from collections import defaultdict
    owner = defaultdict(list)
    for a, b, c in T:
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)): owner[(min(u, v), max(u, v))].append(w)
    quads = []
    for (u, v), ws in owner.items():
        if len(ws) != 1: continue
        p, q, inside = Vf[u], Vf[v], Vf[ws[0]]
        quad = np.array([p, q, q + (0, h, 0), p + (0, h, 0)])
        nrm = np.cross(quad[1] - quad[0], quad[2] - quad[0])
        if np.dot(nrm, inside - p) < 0: quad = quad[[1, 0, 3, 2]]
        quads.append(quad)
    return quads


def open_lap(e, n):
    """The closed loop e as n points round it from its first, the last one step short of the first (as
    the disc's edge splines, open polylines)."""
    q = np.vstack([e, e[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    t = np.arange(n) * s[-1] / n
    return np.stack([np.interp(t, s, q[:, j]) for j in range(3)], 1)


def build_png(placed, Vf, path, px=2000):
    pal = {TARMAC: (90, 90, 95), KERB: (220, 40, 40), GRASS: (60, 150, 60), GRAVEL: (220, 200, 120)}
    lo, hi = Vf[:, [0, 2]].min(0) - 10, Vf[:, [0, 2]].max(0) + 10
    s = px / max(hi - lo)
    img = np.zeros((int((hi[1] - lo[1]) * s) + 1, int((hi[0] - lo[0]) * s) + 1, 4), np.uint8); img[..., 3] = 255
    for mesh, sp, vb, k, strips in placed:
        col = np.array(pal.get(k, (200, 200, 200))) * (0.75 + 0.25 * ((mesh * 7919) % 5) / 4)
        for st in strips:
            for i in range(len(st) - 2):
                t = (Vf[st[i:i + 3]][:, [0, 2]] - lo) * s
                l0 = np.floor(t.min(0)).astype(int); h0 = np.ceil(t.max(0)).astype(int)
                yy, xx = np.mgrid[l0[1]:h0[1] + 1, l0[0]:h0[0] + 1]
                v0, v1 = t[1] - t[0], t[2] - t[0]; det = v0[0] * v1[1] - v0[1] * v1[0]
                if abs(det) < 1e-9: continue
                qx, qz = xx + .5 - t[0][0], yy + .5 - t[0][1]
                u = (qx * v1[1] - qz * v1[0]) / det; w = (v0[0] * qz - v0[1] * qx) / det
                m = (u >= 0) & (w >= 0) & (u + w <= 1)
                m &= (yy >= 0) & (xx >= 0) & (yy < img.shape[0]) & (xx < img.shape[1])
                img[img.shape[0] - 1 - yy[m], xx[m], :3] = col.astype(np.uint8)  # (z up)
    forzaxpr.png(path, img)


# ---- install: a track of its own on Road Atlanta's data

NAME, TAG = 'Fuji Speedway', 'FujiSpeedway'
MAP_TILE = 46   # frontend\gfx_trackmaps.xpr: the disc uses 0-44, the Pacific Shipyards Circuit 45
B = '\\'


def pack_xb2(data):
    """An unpacked scenery bundle as the disc keeps it: zlib streams of 4 MB, each padded to 2048 bytes."""
    import zlib
    out = bytearray()
    for i in range(0, len(data), 4 << 20):
        out += zlib.compress(bytes(data[i:i + (4 << 20)]), 9)
        out += bytes(-len(out) % 2048)
    return bytes(out)


def grid_points(centre):
    """quickpreview.xml's start grid: eight cars in two staggered rows behind the lap line (point 0 of the
    centre line, in the driving direction), facing the way round; and that way."""
    fwd = centre[1] - centre[0]
    fwd = fwd / np.linalg.norm(fwd)
    side = np.array([fwd[2], 0, -fwd[0]]) / np.hypot(fwd[0], fwd[2])
    back = np.vstack([centre[:1], centre[::-1][:-1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(back, axis=0), axis=1))])
    pts = []
    for pos in range(1, 9):
        dist = 8 + 6.0 * (pos - 1)
        p = np.array([np.interp(dist, s, back[:, j]) for j in range(3)])
        p += side * (3.0 if pos % 2 else -3.0)
        p[1] += 0.3
        pts.append((pos, p))
    return pts, fwd


def quickpreview_xml(src, centre):
    import re
    pts, fwd = grid_points(centre)
    s = re.sub(r'<orientation[^>]*/>', '<orientation x=%.3f y=%.3f z=%.3f />' % tuple(fwd), src, count=1)
    s = re.sub(r'[ \t]*<startpoint[^>]*/>[ \t]*\r?\n?', '', s)
    rows = ''.join('\t<startpoint pos="%d"  x="%.3f"  \ty="%.2f"  \tz="%.3f" />\r\n' % (n, p[0], p[1], p[2]) for n, p in pts)
    s = re.sub(r'(<orientation[^>]*/>\r?\n)', lambda m: m.group(1) + '\t\r\n' + rows, s, count=1)
    s = re.sub(r'<splits>.*?</splits>', '<splits>\r\n\t\t<split point="0.33" />\r\n\t\t<split point="0.66" />\r\n\t</splits>', s, flags=re.S)
    s = re.sub(r'<SplinePatches>.*?</SplinePatches>', '<SplinePatches>\r\n\t</SplinePatches>', s, flags=re.S)
    return s


def track_entry(tracklist, name_id, length):
    """tracklist.xml with Fuji's entry after Road Atlanta Short's: a copy of Road Atlanta's with its own name,
    data folder, collision and objects, Road Atlanta's scenery and visibility (replaced while it loads)."""
    import re
    m = re.search(r'<track\s[^>]*name="RoadAtlantaShort".*?/>', tracklist, re.S)
    e = re.search(r'<track\s[^>]*name="RoadAtlanta".*?/>', tracklist, re.S).group(0)
    recs = re.findall(r'<track\s.*?/>', tracklist, re.S)
    ordinal = max(int(x) for r in recs for x in re.findall(r'\bOrdinal="(\d+)"', r)) + 1
    hotlap = max(int(x) for r in recs for x in re.findall(r'\bhotlapordinal="(\d+)"', r)) + 1
    def attr(e, k, v):
        e2, n = re.subn(r'\b%s="[^"]*"' % k, lambda m_: '%s="%s"' % (k, v), e, count=1)
        return e2 if n else e.replace(' />', ' %s="%s" />' % (k, v))
    folder = 'd:\\media\\tracks\\' + TAG + '\\'
    for k, v in (('RosettaName', NAME), ('name', TAG), ('trackIdentifier', TAG), ('tracknameid', name_id),
                 ('trackSegCamsFile', folder + 'TrackSegCams.xml'), ('pitCamsFile', folder + 'PitCams.xml'),
                 ('dataFile', folder + 'QuickPreview.xml'), ('collisionFile', folder + 'QuickPreview1.col'),
                 ('collObjsFile', folder + 'CollObjs.xml'), ('Ordinal', ordinal), ('hotlapordinal', hotlap),
                 ('length', int(round(length))), ('minimap', MAP_TILE), ('NumberOfTurns', 16)):
        e = attr(e, k, v)
    e = re.sub(r'\s(p2pordinal|start|end)="[^"]*"', '', e)
    return tracklist[:m.end()] + '\r\n\r\n\t' + e + tracklist[m.end():], ordinal, hotlap


def install(disc, build_dir, mods):
    """Into the mods folder: Fuji's track list entry, name, data folder (a copy of Road Atlanta's, its grid
    Fuji's and its collision objects none), map tile, its folder on the disc (collision; Road Atlanta's audio
    spline, lightmap, fog and fly-through), and under track\\FujiSpeedway\\ (opened in place of the real files
    while it loads, runtime/file.c) the scenery (as the disc's xb2 and as the cache's res), its collision
    cache, and Road Atlanta's visibility, small buffers and solid-prop boxes (none) as Fuji's."""
    import re
    import zlib
    import addcar
    import addseries
    import shipyardloop as sl
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    files = {k.lower(): k for k in mega.files}
    tl_key = files['forzadb' + B + 'tracklist.xml']
    tracklist = mega.files[tl_key].decode('latin-1')
    if 'name="%s"' % TAG in tracklist: raise SystemExit('%s: %s is in the track list already' % (mods, TAG))
    E = np.load(os.path.join(build_dir, 'fuji_forza.npz'))
    centre = E['centre']
    length = np.linalg.norm(np.diff(np.vstack([centre, centre[:1]]), axis=0), axis=1).sum()
    loc = addcar.disc_file(disc, 'media', 'Loc')
    nid = None
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'TrackStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'TrackStrings.str')
        new = addcar.write_strings(open(mp if os.path.exists(mp) else p, 'rb').read(), [('IDS_Track_Name_' + TAG, NAME)])
        i = addcar.string_ids(new)['IDS_Track_Name_' + TAG]
        if nid not in (None, i): raise SystemExit('track name ids differ between languages')
        nid = i
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(new)
    tracklist, ordinal, hotlap = track_entry(tracklist, nid, length)
    mega.files[tl_key] = tracklist.encode('latin-1')
    src = 'tracks' + B + DONOR_TRACK.lower() + B
    for k in list(mega.files):
        if not k.lower().startswith(src): continue
        v = mega.files[k]
        low = k.lower()
        if low.endswith('quickpreview.xml'): v = quickpreview_xml(v.decode('latin-1'), centre).encode('latin-1')
        if low.endswith('collobjs.xml'):  # Road Atlanta's solid objects would stand invisible on Fuji
            v = re.sub(rb'(<[A-Za-z]+[^>]*>).*(</[A-Za-z]+>\s*)$', lambda m_: m_.group(1) + b'\r\n' + m_.group(2), v, flags=re.S)
        if low.endswith(('drift1.xml', 'specialzones.xml')): continue  # (Road Atlanta's places)
        mega.files['tracks' + B + TAG.lower() + B + k[len(src):]] = v
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    key = next(k for k in xpr.files if k.lower() == 'frontend' + B + 'gfx_trackmaps.xpr')
    north_up = centre.copy()
    xpr.files[key] = addseries.put_tile(xpr.files[key], MAP_TILE, sl.trackmap(north_up), (128, 128, 4))
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    d = os.path.join(mods, 'media', 'tracks', TAG)
    os.makedirs(d, exist_ok=True)
    col = open(os.path.join(build_dir, 'QuickPreview1.col'), 'rb').read()
    open(os.path.join(d, 'QuickPreview1.col'), 'wb').write(col)
    ra = addcar.disc_file(disc, 'media', 'tracks', DONOR_TRACK)
    for f in os.listdir(ra):
        if f.lower() in ('audiospline.bin', 'tracklightmap.dat', 'fog.bin', 'flythrough.bik'):
            open(os.path.join(d, f), 'wb').write(open(os.path.join(ra, f), 'rb').read())
    res = open(os.path.join(build_dir, 'roadatlanta.res'), 'rb').read()
    cbx_disc = next(os.path.join(ra, f) for f in os.listdir(ra) if f.lower() == 'quickpreview1.xbp.cbx')
    cbx = zlib.decompress(open(cbx_disc, 'rb').read())
    cbx = zlib.compress(cbx[:0x14] + struct.pack('<I', 0) + bytes(len(cbx) - 0x18), 9)  # no solid props
    t = os.path.join(mods, 'track', TAG)
    for rel, data in ((('hdd', 'Partition4', 'RoadAtlanta.res'), res),
                      (('hdd', 'Partition4', TAG + '.col'), col),
                      (('media', 'tracks', DONOR_TRACK, 'QuickPreview1.xb2'), pack_xb2(res)),
                      (('media', 'tracks', DONOR_TRACK, 'QuickPreview1.pvs'), open(os.path.join(build_dir, 'QuickPreview1.pvs'), 'rb').read()),
                      (('media', 'tracks', DONOR_TRACK, 'QuickPreview1.pvs.ppw'), open(os.path.join(build_dir, 'QuickPreview1.pvs.ppw'), 'rb').read()),
                      (('media', 'tracks', DONOR_TRACK, 'quickpreview1.xbp.svb'), open(os.path.join(build_dir, 'quickpreview1.xbp.svb'), 'rb').read()),
                      (('media', 'tracks', DONOR_TRACK, 'quickpreview1.xbp.cbx'), cbx)):
        os.makedirs(os.path.join(t, *rel[:-1]), exist_ok=True)
        open(os.path.join(t, *rel), 'wb').write(data)
    print('"%s": track %d, Hot Lap %d, name string %d, %.0f m' % (NAME, ordinal, hotlap, nid, length))


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'layout':
        layout(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 5 and sys.argv[1] == 'build':
        build(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) >= 5 and sys.argv[1] == 'install':
        if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[4]).split(os.sep)):
            raise SystemExit('%s: a save folder' % sys.argv[4])
        install(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
