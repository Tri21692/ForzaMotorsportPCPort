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
import shutil
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
TREE = 0x63  # (drawn only: GT4's tree cards)
FOREST = 0x64  # (drawn only: the woods' canopy)
ARMCO, FENCE = 0x65, 0x66  # (drawn only: along the walls)
FAR_KIND = 0x70  # (drawn only: GT4's far ring, a kind for each of its pictures from here)


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


RACING_LINES = (1, 6)   # GT4's autodrive file's lines taken as the racing line (2 an alternate, 4 the pit lane's)
LINE_SMOOTH = 45        # waypoints (2 m) the suggested line is smoothed over
LINE_LIMIT = 0.7        # its reach across the road (chi), each side
LINE_ROUNDS = 3000      # its straightening passes


def ai_lines(runway_dir, which):
    """GT4's autodrive lines `which` (indices), each a list of (x, z) in GT4's frame (x turned round, as ai_points)."""
    import glob
    ads = glob.glob(os.path.join(runway_dir, '*.ad'))
    if not ads: return []
    d = open(ads[0], 'rb').read()
    b = 0x80
    n_lines, aoff = struct.unpack_from('<ii', d, b + 20)
    out = []
    for i in which:
        if i >= n_lines: continue
        io = b + struct.unpack_from('<i', d, b + aoff + 4 * i)[0]
        n = struct.unpack_from('<i', d, io)[0]
        out.append(np.array([struct.unpack_from('<2f', d, io + 0x40 + k * 0x40 + 4) for k in range(n)], float).reshape(-1, 2) * (-1, 1))
    return out


def racing_line(runway_dir=None):
    """The suggested line (aitrack's `line`): the shortest, least bent path round the lap within LINE_LIMIT of the
    edges (the waypoints' points pulled toward their neighbours' middle, LINE_ROUNDS times, each kept inside the
    road), then its place across the road smoothed over LINE_SMOOTH waypoints: no jumps. (GT4's autodrive lines,
    two disagreeing, swung the line across the straights and off it.)"""
    def line(p, h, left):
        c = p[:, [0, 2]]
        chi = np.zeros(len(c))
        for r in range(LINE_ROUNDS):
            k = 2 + r % 6  # (several reaches: tight bends and long ones)
            x = c + left * (h * chi)[:, None]
            mid = (np.roll(x, k, 0) + np.roll(x, -k, 0)) / 2
            chi = np.clip(np.einsum('ij,ij->i', mid - c, left) / h, -LINE_LIMIT, LINE_LIMIT)
        # smoothed where it lies, not across the road: the centre wanders on the wide straights (chi swinging to keep
        # the line straight), and smoothing chi gave that wander back, the arrows weaving down the pit straight
        x = c + left * (h * chi)[:, None]
        w = np.hanning(LINE_SMOOTH + 2)[1:-1]; w /= w.sum()
        ext = np.vstack([x[-LINE_SMOOTH:], x, x[:LINE_SMOOTH]])
        x = np.stack([np.convolve(ext[:, j], w, 'same')[LINE_SMOOTH:-LINE_SMOOTH] for j in range(2)], 1)
        chi = np.clip(np.einsum('ij,ij->i', x - c, left) / h, -LINE_LIMIT, LINE_LIMIT)
        print('suggested line: chi %.2f to %.2f, largest step %.3f a waypoint' % (chi.min(), chi.max(), np.abs(np.diff(chi)).max()))
        return chi
    return line


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
MATERIALS = {TARMAC: (64, None, 8.0), KERB: (64, 497, 4.0), GRASS: (83, None, 24.0), GRAVEL: (64, 508, 10.0), LINE: (64, 2180, 4.0),
             TREE: (5628, None, 1.0),     # the trees: foliagefacade01's card material, its texture GT4's trees (TREE_TEX)
             FOREST: (83, 430, 40.0),     # the woods: terrain_hillside_distantbrush_001
             ARMCO: (130, 107, 1.0),      # guardrail_white_001 and racedeco catchfence_001 on a railing's material
             FENCE: (130, 319, 1.0)}      # (24-byte vertices, cut out; their own meshes take 20-byte ones)
MATERIALS.update({FAR_KIND + i: (5628, None, 1.0) for i in range(11)})  # (GT4's far cards: their textures FAR_SLOTS)
# a lightmap texel each material samples (lightmap coordinates are (s + 32768) / 512 across the lightmap): a
# mid-lit one, ~85 of 255 (the templates' own median texels were 106, the road looked washed out, and for the grass
# a black, clear texel at the lightmap's edge)
LIGHT = {101: (-32615, -32406), 137: (-32439, -32451)}
# ...but Road Atlanta's lightmaps are baked sunlight, warm tan where lit and blue in shade, and both of those tinted the
# grey asphalt olive in the game: every surface samples instead the most neutral well-lit texel found in any of its
# lightmaps, innerterrainfs_03's (resource 437, texel (138, 192) of 256 x 256: 112, 112, 112)
LIGHTMAP = (437, int(138 / 255 * 512) - 32768, int(192 / 255 * 512) - 32768)
FOREST_LIGHT = (int(83 / 255 * 512) - 32768, int(127 / 255 * 512) - 32768)  # the woods' texel: 0.57 of the grey
TARMAC_LIGHT = (int(128 / 255 * 512) - 32768, int(134 / 255 * 512) - 32768)  # the asphalt's texel: 0.78 of the grey
GRASS_LIGHT = (int(127 / 255 * 512) - 32768, int(144 / 255 * 512) - 32768)  # the grass's texel of it: 0.85 of that grey,
                                                                          # flat round (the user's: grass a little darker)
# The ground lit (the runway's grass and asphalt, the ground beyond, the woods; the user's: "the other tracks look
# better"): Road Atlanta's are baked, ours sampled one texel a kind and every hill read flat. Each vertex samples
# instead a grey on a ramp written over RAMP_ROWS of the lightmap (texel x grey x): its kind's grey (SHADE_BASE)
# times its face's light from SUN (toward it brighter, away darker, flat ground 1; SUN_GAIN) and patches of
# value noise (SHADE_PATCHES: (m across, amount) each) breaking up the textures' repeats.
RAMP_ROWS = (0, 64)
SUN = (-0.45, 0.70, 0.55)
SUN_GAIN = 0.9
SHADE_BASE = {GRASS: 95.0, FOREST: 64.0, TARMAC: 72.0}   # (the asphalt darker than its texel's 87: it read pale)
SHADE_PATCHES = {GRASS: ((70.0, 0.12), (18.0, 0.07)), FOREST: ((50.0, 0.16), (12.0, 0.10)), TARMAC: ((45.0, 0.06), (9.0, 0.04))}
COLLISION = {TARMAC: 0x0000, LINE: 0x0000, KERB: 0x0600, GRASS: 0x0200, GRAVEL: 0x1B00}  # Road Atlanta's codes for them
WALL, WALL_H = 0x0400, 2.0      # round the runway's outside: a tyre wall's code, this high
ASPHALT = (32.0, 10.0)          # m along and across the track a repeat of the asphalt's strip texture (1024 x 256)
KERB_W = 1.2                    # m across a kerb's texture (its stripes along the track)
REACH = 120.0                   # m: a donor's faces within this of its first
GRASS_REACH = 30.0              # m: grass drawn this near the centre line only (all of it solid): the small buffers ran out
SLIVER = 0.02                   # m2: thinner triangles not drawn
# The woods (the user's photo of Fuji: forest beyond a grass belt round the track, a wooded block inside the lap):
# the ground FOREST_FROM m or more beyond the runway raised into a canopy CANOPY_H m high (a bumpy top), over
# FOREST_RAMP m, drawn with the woods' material; none in the clearings (the pits, paddock and grandstand: CLEARINGS,
# (from and to as shares of the lap, side, metres beyond the runway kept clear)). Trees line its edge.
FOREST_FROM, FOREST_RAMP, CANOPY_H, CANOPY_BUMPS = 50.0, 14.0, 13.0, 3.0
CLEARINGS = [(0.88, 0.06, 'in', 170.0), (0.88, 0.06, 'out', 70.0)]
# GT4 Fuji's grandstands by the corners (its world model's stands: from and to as shares of the lap, side), each
# filled with copies of Road Atlanta's stands (STAND_CLONES, end to end, its front to the track) STAND_GAP m beyond
# the runway; the woods kept off them.
STAND_SITES = [(0.029, 0.119, 'out'), (0.168, 0.232, 'in'), (0.316, 0.445, 'out'), (0.427, 0.458, 'in'),
               (0.615, 0.642, 'out'), (0.633, 0.673, 'in'), (0.719, 0.748, 'out'), (0.791, 0.863, 'out')]
STAND_CLONES = ['seatsarea_02', 'outerpitstands01', 'seatsarea']
STAND_GAP = 3.0
STAND_PUSH = (0.0, 4.0, 10.0, 20.0, 35.0)  # m further out tried (a long straight stand by a bend)
CLEARINGS += [(a, b, side, 75.0) for a, b, side in STAND_SITES]
# The walls dressed (the user's photo: armco and catch fence round the track): on each wall (its line along the
# runway's outline) an armco rail ARMCO_H m and a catch fence FENCE_H m (from, to over the edge), a texture repeat
# every RAIL_REPEAT m along, both faces.
ARMCO_H, FENCE_H, RAIL_REPEAT = (-0.5, 0.8), (0.8, 3.8), 4.0   # (the armco's foot in the grass, 0.3 m under the runway)
FENCE_NEAR = 35.0   # m from the centre line: the outline dressed only this near the track
FENCE_RISE = 3.0    # m: and no higher or lower than the track there (up the embankment by the last bend it stood in the sky)
RAIL_SMOOTH, RAIL_STEP = 5, 8.0   # the dressing's line: the walls' outline smoothed over this many points, a point every RAIL_STEP m
GROUND_REACH = 300.0             # m: a ground, tree or fence donor's faces within this of its first (fewer, bigger donors:
                                 # each is a draw in every cell; 2,000 small ones cost frames)
STAND_KEEP = 24                  # the biggest spare donors kept for the stands' copies
CLONE_DONOR = 2000               # vertices: the largest streamed donor kept for the stands' copies
# Shortcuts blocked (the user's "Forza touches"): armco and a wall to the cars wherever crossing the runway's
# run-off or grass from one part of the lap to another saves SHORTCUT_SAVE m or more, kept SHORTCUT_CLEAR m off
# the asphalt (shortcut_barriers).
SHORTCUT_SAVE, SHORTCUT_CLEAR = 25.0, 1.5  # (the most anywhere at Fuji: 29 m, across the hairpin's grass)
# More kerbs (the user's "add some more curbs"): Forza's red and white at the corners (curvature over KERB_TURN a
# metre, a radius under 200 m) where GT4 has none: on the inside edge round the apex (KERB_APEX m each side) and the
# outside edge on the way out (KERB_EXIT m past the apex), KERB_W wide from KERB_IN m over the asphalt, KERB_LIFT m
# over the runway; none within KERB_SKIP m of GT4's own.
KERB_TURN, KERB_APEX, KERB_EXIT, KERB_IN, KERB_LIFT, KERB_SKIP = 1 / 200.0, 25.0, (5.0, 45.0), 0.3, 0.03, 3.0
STREAMED_DONOR = 600            # vertices: the largest donor whose buffer is streamed (the svb's small ones ran out)
TERRAIN_CELL = 16.0            # m: the ground beyond the runway, drawn as a grid of this
TERRAIN_REACH = 110.0           # m: that far beyond the runway (the forest cards stand 45-90 m beyond it)
TERRAIN_DROP = 0.3              # m: and this far under it (under the runway at its crests too: the lowest runway near)
GROUND_FLAT = 0.5               # GT4's world model's triangles taken as ground: |normal y| over this
GROUND_SLOPE = 0.4              # the ground's steepest rise (m a metre) off the runway
FAR_CELL, FAR_REACH, FAR_DROP = 48.0, 1000.0, 1.0   # the far ground: a coarser grid out to FAR_REACH m (the map's
                                                  # edge showed past the near one), FAR_DROP m under the near grid
GROUND_NEAR = 3000.0           # m: and their middles this near the runway's middle (the far hills are its own model)
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
    kinds = F[:, 3].copy()  # (the painted lines drawn as lines: LINE_PAINT; tarmac to the cars, COLLISION)
    kinds = np.where(np.isin(kinds, list(MATERIALS)), kinds, GRASS)

    # what is drawn: all but far grass and slivers (the collision keeps every triangle)
    E = np.load(os.path.join(runway_dir if os.path.exists(os.path.join(runway_dir, 'layout_edges.npz')) else out, 'layout_edges.npz'))
    cen_g = E['centre'][:, [0, 2]]
    cent = V[F[:, :3]].mean(1)[:, [0, 2]]
    dist = np.array([np.min(np.hypot(*(cen_g - p).T)) for p in cent])
    area = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1) / 2
    drawn = (area >= SLIVER) & ~((kinds == GRASS) & (dist > GRASS_REACH))
    print('drawn: %d of %d triangles (grass beyond %.0f m and slivers left out)' % (drawn.sum(), len(T), GRASS_REACH))
    walls = outside_walls(Vf, T, F)
    # and the ground beyond, drawn only: Vd and Td the drawn vertices and faces (the runway's first)
    cf = to_forza(E['centre'])
    reach = runway_reach(Vf, F, cf, sides(cf)[1])
    clear = clearings(cf, sides(cf)[1], reach[:, 0], reach[:, 1])
    Vt, Tt, ground_at, Kt, top_near = terrain(Vf, F, drawn, cf, read_ground(runway_dir), clear)
    Va, Ta = apron(cf, sides(cf)[1], reach[:, 0], *PIT_APRON, ground_at)
    Vfar, Tfar, Kfar, top_far = far_terrain(Vf, F, cf, read_ground(runway_dir), clear)
    Vtr, Ttr, UVtr = trees(runway_dir, cf, sides(cf)[1], reach[:, 0], reach[:, 1], ground_at, clear, (top_near, top_far))
    Vw, Tw, UVw, Kw = dressing(walls, cf)
    rast = Raster(Vf, F, res=0.5)
    lef_f, rig_f = to_forza(E['left']), to_forza(E['right'])
    half = np.linalg.norm((lef_f - rig_f)[:, [0, 2]], axis=1) / 2
    Vb, Tb, UVb, Kb, bwalls = barrier_geometry(shortcut_barriers(cf, half, rast, ground_at))
    Tw, Vw = np.vstack([Tw.reshape(-1, 3), Tb + len(Vw)]), np.vstack([Vw.reshape(-1, 3), Vb])
    UVw, Kw = np.vstack([UVw.reshape(-1, 2), UVb]), np.concatenate([Kw, Kb])
    Vk, Tk, UVk = more_kerbs(cf, lef_f, rig_f, rast, Vf[T[kinds == KERB]].mean(1) if (kinds == KERB).any() else np.zeros((0, 3)))
    Vr, Tr, UVr, Kr = far_ring(runway_dir)
    Vd = np.vstack([Vf, Vt, Va, Vfar, Vtr, Vw, Vr, Vk])
    o_a, o_f = len(Vf) + len(Vt), len(Vf) + len(Vt) + len(Va)
    o_t = o_f + len(Vfar)
    o_w = o_t + len(Vtr)
    o_r = o_w + len(Vw)
    o_k = o_r + len(Vr)
    Td = np.vstack([T[drawn], Tt + len(Vf), Ta + o_a, Tfar + o_f, Ttr + o_t, Tw + o_w, Tr + o_r, Tk + o_k])
    kinds_d = np.concatenate([kinds[drawn], Kt, np.full(len(Ta), TARMAC), Kfar, np.full(len(Ttr), TREE), Kw, Kr, np.full(len(Tk), KERB)])
    given_uv = {o_t + i: (u, v) for i, (u, v) in enumerate(UVtr)}  # (the trees': on the sheet; repeats, set per donor)
    given_uv.update({o_w + i: (u, v) for i, (u, v) in enumerate(UVw)})  # (the rails and fences)
    given_uv.update({o_r + i: (u, v) for i, (u, v) in enumerate(UVr)})  # (the far ring)
    given_uv.update({o_k + i: (u, v) for i, (u, v) in enumerate(UVk)})  # (the kerbs added)
    print('walls dressed: %d armco and fence quads' % (len(Tw) // 4))
    print('terrain: %d vertices, %d triangles' % (len(Vt), len(Tt)))

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

    # the donors: small stride-6 strips of 24-byte vertices, in the svb or streamed, a buffer each, with a ppw sphere found
    nmesh = struct.unpack_from('<I', res, model)[0]
    pool = []
    import re
    prop = re.compile(r'vbuff_quickpreview_(%s)(_vb\d+)?$' % '|'.join(['(?:%s)' % p_[0].rstrip('$') for p_ in SCATTER] + [re.escape(x_) for r_ in ROWS if isinstance(r_[0], list) for x_ in r_[0]] + [r_[0][0].rstrip('$') for r_ in ROWS if not isinstance(r_[0], list)]))
    props = {k + 9 for k, r in enumerate(names) if prop.match(r[0])}  # (props to place: not donors)
    from collections import Counter
    sharing = Counter(record(res, model, i)[1][4] for i in range(nmesh))
    for i in range(nmesh):
        at, (fl, ab, nidx, vbytes, vb, stride, prim, t0, t1, sh) = record(res, model, i)
        if stride != 6 or prim != 6 or vbytes % 24 or nidx < 8 or vbytes < 24 * 4 or sharing[vb] > 1: continue
        if vb not in svb and vbytes > 24 * CLONE_DONOR: continue  # (a streamed buffer: loaded from the xb2 in each cell listing it)
        if i in {m for m, _, _ in MATERIALS.values()} or vb in props: continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, :3].astype(float)
        if not np.all(np.isfinite(v)): continue
        c = (v.min(0) + v.max(0)) / 2
        sp = sphere_offset(ppw, i, c, float(np.max(np.linalg.norm(v - c, axis=1))))
        if sp is None: continue
        pool.append([vbytes // 24, nidx, i, sp, vb])
    pool.sort(key=lambda r: -r[0])
    print('donors: %d small meshes, room for %d vertices and %d indices' % (len(pool), sum(r[0] for r in pool), sum(r[1] for r in pool)))

    # strips per surface, then packed by place into donors
    jobs = []
    nrun = int(drawn.sum())
    for k in sorted(set(kinds_d.tolist())):
        tk = Td[:nrun][kinds_d[:nrun] == k]
        for s in strips_of([tuple(t) for t in tk]):
            jobs.append((k, s))
    # the ground in blocks of 8 x 8 squares (a grid row's strip ran kilometres: past s16's texture coordinates)
    ground = []
    for k_, tris, bsize in ((GRASS, (Tt + len(Vf))[Kt == GRASS], 8 * TERRAIN_CELL), (FOREST, (Tt + len(Vf))[Kt == FOREST], 8 * TERRAIN_CELL),
                            (TARMAC, Ta + o_a, 8 * TERRAIN_CELL), (GRASS, (Tfar + o_f)[Kfar == GRASS], 8 * FAR_CELL),
                            (FOREST, (Tfar + o_f)[Kfar == FOREST], 8 * FAR_CELL), (TREE, Ttr + o_t, 8 * TERRAIN_CELL),
                            (ARMCO, (Tw + o_w)[Kw == ARMCO], 8 * TERRAIN_CELL), (FENCE, (Tw + o_w)[Kw == FENCE], 8 * TERRAIN_CELL),
                            (KERB, Tk + o_k, 4 * TERRAIN_CELL)) + \
                           tuple((k_r, (Tr + o_r)[Kr == k_r], 1e6) for k_r in sorted(set(Kr.tolist()))):  # (the woods, the apron, the far ground, the trees)
        if not len(tris): continue
        block = np.floor(Vd[tris].mean(1)[:, [0, 2]] / bsize).astype(int)
        for bk in sorted({tuple(b) for b in block}):
            for s in strips_of([tuple(t) for t in tris[(block == bk).all(1)]]):
                ground.append((k_, s))
    nstrip_idx = sum(len(s) + 3 for _, s in jobs + ground)
    print('surface: %d triangles in %d strips, the ground %d triangles in %d (~%d indices with the joins)' % (nrun, len(jobs), len(Tt), len(ground), nstrip_idx))
    # the biggest donors first (each a draw in every cell: 2,000 small ones cost frames): the runway's, its strips
    # short and its donors' faces near (texture coordinates stay in s16's range: a kerb repeats every 4 m), then the
    # ground's; some 900-2,000-vertex ones kept for the stands' copies
    keep_ = {p_[2] for p_ in sorted((p_ for p_ in pool if p_[4] not in svb and 900 <= p_[0] <= 2000), key=lambda p_: p_[0])[:STAND_KEEP]}
    placed, left = pack_strips(jobs, Vd, [p_ for p_ in pool if p_[2] not in keep_], reach={KERB: 50.0, None: 120.0}, longest={KERB: 60.0, None: 100.0})
    if left: raise SystemExit('out of donor meshes: %d strips left over' % left)
    taken = {p_[0] for p_ in placed}
    more, left = pack_strips(ground, Vd, [p_ for p_ in pool if p_[2] not in taken and p_[2] not in keep_],
                             reach={TARMAC: 150.0, ARMCO: 100.0, FENCE: 100.0, KERB: 50.0, None: GROUND_REACH, **{FAR_KIND + i: 1e6 for i in range(len(FAR_TEX))}},
                             longest={ARMCO: 100.0, FENCE: 100.0, KERB: 60.0, None: 150.0, **{FAR_KIND + i: 1e6 for i in range(len(FAR_TEX))}})
    if left: raise SystemExit('out of donor meshes for the ground: %d strips left over' % left)
    placed += more
    from collections import Counter as _C
    print('donors by surface:', dict(_C(x[3] for x in placed)))
    spare = [p_ for p_ in pool if p_[2] not in {x[0] for x in placed}]  # (for the stands' copies)

    # the ground's light per vertex (SUN, SHADE_PATCHES): its faces' normals, area weighted
    nrm = np.zeros_like(Vd)
    fn = np.cross(Vd[Td[:, 1]] - Vd[Td[:, 0]], Vd[Td[:, 2]] - Vd[Td[:, 0]])
    fn *= np.where(fn[:, 1] < 0, -1.0, 1.0)[:, None]
    for j in range(3): np.add.at(nrm, Td[:, j], fn)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    sun = np.array(SUN) / np.linalg.norm(SUN)
    sunlit = np.clip(1.0 + SUN_GAIN * (nrm @ sun - sun[1]), 0.45, 1.35)
    ramp_t = (RAMP_ROWS[0] + RAMP_ROWS[1]) - 32768  # (the band's middle row: (row + 0.5) * 2)

    def shade(k, vi):
        g = SHADE_BASE[k] * sunlit[vi]
        for m, amt in SHADE_PATCHES[k]: g *= 1.0 + amt * value_noise(Vd[vi, [0, 2]], m, int(m))
        return int(round((np.clip(g, 6, 248) + 0.5) * 2)) - 32768, ramp_t

    # each donor rewritten: its material's texture, lightmap, shader, flags; planar texture coordinates
    tex_used, vbs_used, meshes = set(), set(), []
    for mesh, sp, vb, k, strips in placed:
        mat, tex, metres = MATERIALS[k]
        if k == TREE: tex = TREE_SHEET
        if FAR_KIND <= k < FAR_KIND + len(FAR_SLOTS): tex = FAR_SLOTS[k - FAR_KIND]
        mat_at, (mfl, _, _, _, _, _, _, mt0, mt1, msh) = record(res, model, mat)
        mt0 = tex or mt0
        mt1, light = LIGHTMAP[0], {GRASS: GRASS_LIGHT, FOREST: FOREST_LIGHT, TARMAC: TARMAC_LIGHT}.get(k, LIGHTMAP[1:])
        at, (fl, ab, nidx, vbytes, vbr, stride, prim, t0, t1, sh) = record(res, model, mesh)
        pts = np.vstack([Vd[s] for s in strips])
        org = np.floor(pts.min(0) / metres) * metres  # (texture coordinates from a whole repeat near the faces: s16 holds +-64 repeats)
        uv = {}  # (texture coordinates set per vertex: kerbs, the runway's asphalt, lines; else planar)
        if k == KERB and max(vi for s in strips for vi in s) < len(Vf):  # along the track (its stripes across it): s across, `metres` a repeat along
            ids_all = sorted({vi for s in strips for vi in s})
            al = along[ids_all]
            if al.max() - al.min() > lap / 2: al = np.where(al < lap / 2, al + lap, al)  # (a donor over the lap line)
            a0 = np.floor(al.min() / metres) * metres
            s0 = np.floor(side[ids_all].min() / KERB_W) * KERB_W
            uv = {vi: (int((side[vi] - s0) / KERB_W * 512) - 32768, int((a - a0) / metres * 512) - 32768) for vi, a in zip(ids_all, al)}
        elif k == TARMAC and max(vi for s in strips for vi in s) < len(Vf):  # the runway's asphalt: its strip texture
            ids_all = sorted({vi for s in strips for vi in s})                 # along the track (road08completemap)
            al = along[ids_all]
            if al.max() - al.min() > lap / 2: al = np.where(al < lap / 2, al + lap, al)
            a0 = np.floor(al.min() / ASPHALT[0]) * ASPHALT[0]
            s0 = np.floor(side[ids_all].min() / ASPHALT[1]) * ASPHALT[1]
            uv = {vi: (int((a - a0) / ASPHALT[0] * 512) - 32768, int((side[vi] - s0) / ASPHALT[1] * 512) - 32768) for vi, a in zip(ids_all, al)}
        elif k == LINE:
            uv = {vi: (256 - 32768, 256 - 32768) for s in strips for vi in s}  # (the line texture's white middle: solid paint)
        elif strips and strips[0][0] in given_uv:  # (trees, rails, fences: theirs, shifted by whole repeats to start near 0)
            ids_all = {vi for s in strips for vi in s}
            u0 = np.floor(min(given_uv[vi][0] for vi in ids_all)); v0 = np.floor(min(given_uv[vi][1] for vi in ids_all))
            uv = {vi: (int((given_uv[vi][0] - u0) * 512) - 32768, int((given_uv[vi][1] - v0) * 512) - 32768) for vi in ids_all}
        verts, order, local = [], [], {}  # (a vertex once a donor, its strips indexing it)
        for s in strips:
            ids = []
            for vi in s:
                if vi not in local:
                    local[vi] = len(verts)
                    p = Vd[vi]
                    if vi in uv: verts.append((p,) + uv[vi])
                    else: verts.append((p, int((p[0] - org[0]) / metres * 512) - 32768, int((p[2] - org[2]) / metres * 512) - 32768))
                    verts[-1] += shade(k, vi) if k in SHADE_BASE else tuple(light)
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
            p, s_, t_, ls_, lt_ = verts[min(j, len(verts) - 1)]
            buf['p'][j] = p
            buf['n'][j] = sc.pack_normal((0.0, 1.0, 0.0))
            if not (-32768 <= s_ <= 32767 and -32768 <= t_ <= 32767):
                raise SystemExit('texture coordinates past s16: surface %s, donor %d, %d strips, s %d t %d' % (k, mesh, len(strips), s_, t_))
            buf['st'][j] = (s_, t_, ls_, lt_)
        o = names[vbr - 9][3]
        data = buf.tobytes() + np.array(order + [order[-1]] * (nidx - len(order)), '<u2').tobytes()
        res[o:o + len(data)] = data
        if vbr in svb:
            so, ssz = svb[vbr]
            assert ssz >= len(data), (mesh, ssz, len(data))
            svb_out[so:so + len(data)] = data
        struct.pack_into('<HHH', res, at + 22, mt0, mt1, msh)
        res[at + 21] = res[mat_at + 21]  # (the format's second byte: 1 for the forest cards, their alpha cut out)
        struct.pack_into('<I', res, at, mfl)
        struct.pack_into('<I', res, at + 8, len(order))  # (the indices it uses: the padding's degenerate triangles cost frames)
        c = (pts.min(0) + pts.max(0)) / 2
        struct.pack_into('<4f', ppw, sp, float(np.max(np.linalg.norm(pts - c, axis=1))) + 0.5, *c)
        tex_used |= {mt0, mt1}
        vbs_used.add(vbr)
        meshes.append(mesh)
    print('drawn: %d donor meshes; textures %s' % (len(meshes), sorted(tex_used)))

    # GT4's art on Road Atlanta's signs
    stx_p = files['quickpreview1.pvs.stx']
    stx = xb2.unpack(stx_p) if open(stx_p, 'rb').read(1) == b'\x78' else open(stx_p, 'rb').read()
    retexture(res, names, stx, os.path.join(runway_dir, 'art'))
    tree_sheet(res, names, stx, os.path.join(runway_dir, 'trees'))
    far_pictures(res, names, stx, os.path.join(runway_dir, 'far', 'textures'))
    kerb_colour(res, names, stx)
    light_ramp(res, names, stx)
    line_paint(res, names, stx)

    # Road Atlanta's buildings, stands and props set round Fuji (ROWS, SCATTER), drawn in every cell with their
    # buffers streamed in
    sm, st_, sv = scatter(res, names, model, ppw, svb, svb_out, cf, reach[:, 0], reach[:, 1], set(), ground_at, spare=spare)
    meshes += sm; tex_used |= st_; vbs_used |= sv

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
    for t_ in Tk:
        col.add_ground(COLLISION[KERB], Vk[t_])
    for q in walls + bwalls:
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
    for f in ('fuji_logo.png', LOAD_PHOTO, 'new_fisco.ad'):  # (the menus' art and GT4's racing lines, for install)
        shutil.copy(os.path.join(runway_dir, f), os.path.join(out, f))
    build_png(placed, Vd, os.path.join(out, 'build_check.png'))


# Road Atlanta's buildings and stands in rows along Fuji, where GT4's Fuji has its own: (the instances (a list of
# names, or a pattern and how many), from and to (shares of the lap from the lap line, the way round), the side
# ('in': the inside of the loop; 'out'), metres beyond the runway's edge, metres between them). Each is laid end to
# end the way round, its long side along the track and its front (the way it faced Road Atlanta's track) to Fuji's,
# on the ground; one that would reach over the runway goes further out (ROW_PUSH), or is left out.
# GT4's pit building (348 m long, 14 m high) stands on the main straight's inside from 94% of the lap to 2%, its
# main grandstand opposite (92% to 2%), the paddock behind the pits (its buildings 40 to 120 m from the straight).
ROWS = [
    (['hangar01', 'hangar02', 'hangar03', 'garages01', 'pirellabuilding'], 0.935, 0.02, 'in', 17.0, 4.0),
    (['seatsarea', 'outerpitstands01', 'seatsarea_02'], 0.92, 0.03, 'out', 3.0, 3.0),
    (['fuelstation01', 'restroom01', 'restroom02', 'restroom03', 'truckcambody01k_284', 'truckcambody02k_285'], 0.93, 0.02, 'in', 50.0, 12.0),
    ((r'(broadcast_trailer|semitrailer|trailerlarge)\w*$', 53), 0.93, 0.02, 'in', 72.0, 4.0),
    ((r'rvlarge\w*$', 60), 0.93, 0.02, 'in', 92.0, 5.0),
    ((r'rvlarge\w*$', 60), 0.93, 0.02, 'in', 110.0, 5.0),
    (['4signs'], 0.03, 0.05, 'out', 4.0, 0.0),
    (['sunocosign'], 0.075, 0.1, 'out', 10.0, 0.0),
]
ROW_PUSH = (0.0, 3.0, 8.0, 16.0)   # m further out tried when a row's piece would reach over the runway
PIT_APRON = (0.935, 0.02, [(-0.3, False), (15.0, False), (30.0, True), (55.0, True), (80.0, True), (105.0, True), (130.0, True)])
                                   # the pit lane's apron and the paddock behind it (tarmac, drawn only; the user's photo:
                                   # all paved): from and to (shares of the lap), its columns (apron) beyond the runway's
                                   # inside edge (GT4's runway has no pit lane), the pit building on it
# GT4's art on Road Atlanta's signs (the user's: GT4's models only for what identifies the track): (texture
# resource, image in run\gt4_fuji\art, times across). GT4 keeps colours at half (its vertex colours double them):
# brightened by ART_GAIN. The Sunoco sign (256 x 128) takes Fuji's big logo, the four ad walls (512 x 64) its wall
# banner twice.
BANNERS = [(16, 'fuji_logo_wall.png', 1), (87, 'fuji_banner_wall.png', 2)]
ART_GAIN = 1.8
# GT4 Fuji's trees (the user's: "Try GT4's trees"): its world model's tree cards (169 trees by the track, crossed
# cards of its tree pictures) where GT4 has them, and more of its trees in clusters off the track, each two crossed
# cards. The pictures (run/gt4_fuji/trees, GT4's texture names) side by side in Road Atlanta's forest card texture
# (1024 x 256 DXT5, eight 128 x 256 cells), drawn with the forest cards' material.
# GT4 Fuji's far scenery (its course file's far model set: panorama cards round the circuit some 40 km out, Mt Fuji
# among them; its clouds left out, Forza has its own sky): scaled about the circuit's middle to FAR_RING m (every
# angle as GT4's), each picture on a spare texture of Road Atlanta's (its road overlays, 512 x 256), drawn with the
# forest cards' cut-out material.
FAR_TEX_ALL = ['1_0', '2_0', '2_1', '3_0', '3_1', '4_0', '4_1', '4_2', '5_0', '5_1', '5_2']
FAR_TEX = []   # (off: at 2.5 km the cards stood as brown cliffs on the skyline, and fog left the rest a haze)
FAR_SLOTS = [2827, 2830, 2833, 2836, 2839, 2842, 2845, 2848, 2851, 2859, 2862]
FAR_RING = 2500.0
FAR_BASE = -40.0   # m: the ring's foot (under the hills round the circuit)
TREE_TEX = ['1_53', '1_54', '1_59', '1_60', '1_33']   # cells 0-4; GT4 materials t<name> (its 7_13, a black
                                                      # silhouette, and 0_34, a door, are not trees)
TREE_SHEET = 7564          # tree_cardpage_realforrest_tile: the sheet
TREE_TALL = [0, 1, 2, 3]  # the cells holding a whole tree (the generated trees')
TREE_CLUSTERS = 520        # generated clusters, each 3 to 9 trees within 6 to 22 m
TREE_BAND = (FOREST_FROM - 14.0, FOREST_FROM + 6.0)   # m beyond the runway: along the woods' edge (its ramp hidden)
TREE_H = (12.0, 20.0)      # m high (the canopy 13)
WOOD_FILL = (20.0, 300.0)  # trees through the woods (the user's: "like we're in the middle of a forest"): one about every
                           # 20 m (jittered), out to 300 m beyond the runway, crowns over the canopy




def ppw_records(ppw):
    """The offsets of QuickPreview1.pvs.ppw's records, one a mesh in model_quickpreview's order: after a u32 version
    and a 16-byte id, 21 bytes each (f32 radius, centre x, y, z, a u32 of flags, a byte), a record whose flags have
    512 followed by a u32 count and that many u16 (edges: pairs of corners). (Road Atlanta's: 8,029, its meshes'.)"""
    o, offs = 20, []
    while o + 21 <= len(ppw):
        offs.append(o)
        w = struct.unpack_from('<I', ppw, o + 16)[0]
        o += 21
        if w & 512: o += 4 + 2 * struct.unpack_from('<I', ppw, o)[0]
    return offs


_PPW_RECORDS = {}


def sphere_offset(ppw, i, centre, radius):
    """Mesh i's bounding sphere's offset in the ppw (ppw_records), if that record's centre is near the mesh's (a
    building's or a tree's sphere is not its vertices' box: the search by value missed them); else
    shipyardcircuit.sphere_at's search by value (exact); else None. (Indexing every mesh at 20 + 21 i, the lists
    not walked, wrote the donors' spheres over other meshes' and the road vanished.)"""
    import shipyardcircuit as sc
    key = (id(ppw), len(ppw))
    if key not in _PPW_RECORDS: _PPW_RECORDS[key] = ppw_records(bytes(ppw))
    offs = _PPW_RECORDS[key]
    if i < len(offs):
        o = offs[i]
        r, cx, cy, cz = struct.unpack_from('<4f', ppw, o)
        if np.isfinite([r, cx, cy, cz]).all() and np.linalg.norm(np.array([cx, cy, cz]) - centre) < 0.5 * radius + 5: return o
    return sc.sphere_at(ppw, centre, radius)


def mesh_info(res, names, model, i):
    """Mesh i's (vertex buffer, index count, vertex bytes, vertex size, textures): records of 24, 28, 32 or 44 bytes
    share flags, a u32, the index count, the vertex bytes, the buffer (u16), a u16 (6), a format byte; then u16
    resource numbers (the textures, lightmap, shader). The vertex size is the one whose count the strip's highest
    index just fits (the 24-byte records' meshes have 20-byte vertices: their u16 of 6 is not a stride)."""
    n = struct.unpack_from('<I', res, model)[0]
    a = struct.unpack_from('<I', res, model + 4 + 4 * i)[0]
    end = min([struct.unpack_from('<I', res, model + 4 + 4 * j)[0] for j in range(n) if struct.unpack_from('<I', res, model + 4 + 4 * j)[0] > a] or [a + 28])
    fl, ab, nidx, vbytes, vb = struct.unpack_from('<IIIIH', res, model + a)
    ids = struct.unpack_from('<%dH' % ((end - a - 22) // 2), res, model + a + 22)
    texs = {t for t in ids if 9 <= t < len(names) + 9 and names[t - 9][0].startswith('tex_')}
    if not (9 <= vb < len(names) + 9) or not vbytes: return vb, nidx, vbytes, 0, texs
    o = names[vb - 9][3]
    top = int(np.frombuffer(bytes(res[o + vbytes:o + vbytes + 2 * nidx]), '<u2').max()) if nidx else 0
    known = VERTEX_SIZE.get(res[model + a + 20])  # the format byte first: a padded strip (the donors') does not reach its last vertex
    if known and vbytes % known == 0: return vb, nidx, vbytes, known, texs
    fits = [sz for sz in (24, 20, 28, 32, 16, 36) if vbytes % sz == 0 and top < vbytes // sz]
    exact = [sz for sz in fits if vbytes // sz == top + 1]
    return vb, nidx, vbytes, (exact or fits or [0])[0], texs


VERTEX_SIZE = {6: 24, 14: 24, 1: 20}  # a mesh record's format byte (at 20): its vertices' bytes


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


def instance_geometry(res, names, model, ms):
    """An object's vertex buffers {buffer: (vertex size in dwords, vertices)} (a buffer is its vertices, then the meshes'
    u16 strip indices: moved as vertices, those scrambled every triangle, smeared stripes in the game) and its sane
    vertices' positions."""
    bufs = {}
    for i, at, f in ms:
        vb_, nidx_, vbytes_, vsize, _ = mesh_info(res, names, model, i)
        if not vsize: continue
        bufs[vb_] = (vsize // 4, max(vbytes_ // vsize, bufs.get(vb_, (0, 0))[1]))
    allp = []
    for vb, (stride, n) in bufs.items():
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + n * 4 * stride]), '<f4').reshape(n, stride)[:, :3].astype(float)
        ok = np.all(np.isfinite(v), 1) & (np.abs(v).max(1) < 5000)
        allp.append(v[ok])
    return bufs, (np.vstack(allp) if allp else np.zeros((0, 3)))


def place_instance(res, names, model, ppw, svb, svb_out, ms, bufs, mid, R, target, lift):
    """An object's vertices turned by R (2 x 2, on x and z) about `mid` onto `target`, raised by `lift`, normals
    turned with them, the svb copies and the ppw spheres (a mesh whose sphere is not found is left out) moved.
    Returns (meshes, textures, vertex buffers) to show and stream in every cell."""
    import shipyardcircuit as sc
    meshes, texs, vbs = [], set(), set()
    for vb, (stride, n) in bufs.items():
        o = names[vb - 9][3]
        raw = np.frombuffer(bytes(res[o:o + n * 4 * stride]), '<u4').reshape(n, stride).copy()
        v = raw[:, :3].view('<f4').astype(float)
        xz = (v[:, [0, 2]] - mid[[0, 2]]) @ R.T + target[[0, 2]]
        v[:, 0], v[:, 2], v[:, 1] = xz[:, 0], xz[:, 1], v[:, 1] + lift
        raw[:, :3] = v.astype('<f4').view('<u4')
        if stride >= 4:  # its normals (the word after the position) turned the same way
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
    for i, at, f in ms:
        vb, nidx, vbytes, vsize, mtex = mesh_info(res, names, model, i)
        if not vsize or vb not in bufs: continue
        o, n, stride = names[vb - 9][3], vbytes // vsize, vsize // 4
        now = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(n, stride)[:, :3].astype(float)
        was = np.frombuffer(bytes(ORIG_RES[o:o + vbytes]), '<f4').reshape(n, stride)[:, :3].astype(float)
        if not (np.isfinite(was).all() and np.isfinite(now).all()): continue
        c0 = (was.min(0) + was.max(0)) / 2
        sp = sphere_offset(ppw, i, c0, float(np.max(np.linalg.norm(was - c0, axis=1))))
        if sp is None: continue
        c1 = (now.min(0) + now.max(0)) / 2
        struct.pack_into('<4f', ppw, sp, float(np.max(np.linalg.norm(now - c1, axis=1))) + 0.5, *c1)
        meshes.append(i); texs |= mtex
    return meshes, texs, vbs


def clone_instance(res, names, model, ppw, svb, svb_out, ms, mid, R, target, lift, spare):
    """A copy of an object's meshes (as the disc has them: ORIG_RES) in spare donors (rows [vertices, indices, mesh,
    sphere, buffer], taken from `spare`, each the smallest that fits), turned by R about `mid` onto `target` and
    raised by `lift` as place_instance's, with the mesh's own material (flags, format, textures, shader) and
    lightmap coordinates. Only 24-byte-vertex meshes. Returns (meshes, textures, vertex buffers)."""
    import shipyardcircuit as sc
    meshes, texs, vbs = [], set(), set()
    plan = []  # (a donor for every mesh, or no copy)
    for i, at, f in ms:
        vb, nidx, vbytes, vsize, mtex = mesh_info(ORIG_RES, names, model, i)
        if vsize != 24: continue
        fits = [p_ for p_ in spare if p_[0] >= vbytes // 24 and p_[1] >= nidx and p_ not in [q_[1] for q_ in plan]]
        if not fits: return [], set(), set()
        plan.append((i, min(fits, key=lambda p_: (p_[0], p_[1]))))
    for i, donor in plan:
        vb, nidx, vbytes, vsize, mtex = mesh_info(ORIG_RES, names, model, i)
        nv = vbytes // 24
        spare.remove(donor)
        dnv, dnidx, dmesh, dsp, dvb = donor
        o = names[vb - 9][3]
        raw = np.frombuffer(bytes(ORIG_RES[o:o + vbytes]), '<u4').reshape(nv, 6).copy()
        idx = np.frombuffer(bytes(ORIG_RES[o + vbytes:o + vbytes + 2 * nidx]), '<u2').copy()
        v = raw[:, :3].view('<f4').astype(float)
        xz = (v[:, [0, 2]] - mid[[0, 2]]) @ R.T + target[[0, 2]]
        v[:, 0], v[:, 2], v[:, 1] = xz[:, 0], xz[:, 1], v[:, 1] + lift
        raw[:, :3] = v.astype('<f4').view('<u4')
        for j in range(nv):
            nv_ = sc.unpack_normal(int(raw[j, 3]))
            nxz = R @ nv_[[0, 2]]
            raw[j, 3] = sc.pack_normal((nxz[0], nv_[1], nxz[1]))
        full = np.vstack([raw, np.repeat(raw[-1:], dnv - nv, 0)])
        order = np.concatenate([idx, np.full(dnidx - nidx, idx[-1], '<u2')])
        data = full.astype('<u4').tobytes() + order.astype('<u2').tobytes()
        do = names[dvb - 9][3]
        res[do:do + len(data)] = data
        if dvb in svb:
            so, ssz = svb[dvb]
            svb_out[so:so + min(ssz, len(data))] = data[:ssz]
        dat, _ = record(res, model, dmesh)
        sat, sf = record(ORIG_RES, model, i)
        res[dat:dat + 4] = ORIG_RES[sat:sat + 4]          # flags
        struct.pack_into('<I', res, dat + 8, nidx)          # its own index count (a big donor's padding cost frames)
        res[dat + 20:dat + 22] = ORIG_RES[sat + 20:sat + 22]  # format and its second byte
        res[dat + 22:dat + 28] = ORIG_RES[sat + 22:sat + 28]  # textures, lightmap, shader
        c = (v.min(0) + v.max(0)) / 2
        struct.pack_into('<4f', ppw, dsp, float(np.max(np.linalg.norm(v - c, axis=1))) + 0.5, *c)
        meshes.append(dmesh); texs |= mtex | {sf[7], sf[8]}; vbs.add(dvb)
    return meshes, texs, vbs


def turn(a):
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])  # (x, z) turned by a


def facing(mid):
    """The way an object at mid faced Road Atlanta's track (radians, on x and z)."""
    near = RA_CENTRE[np.argmin(np.hypot(*(RA_CENTRE[:, [0, 2]] - mid[[0, 2]]).T))]
    return np.arctan2(near[2] - mid[2], near[0] - mid[0])


# Road Atlanta's many props spread round Fuji by rule: (instance name pattern, how many at most, where, metres beyond
# the runway's edge (a range: drawn at random), how it is turned). Where: 'corners' (the outside of each corner's
# apex, a few metres apart when several), 'fast' (the straights and fast bends, end to end, the two sides in turn),
# 'pits' (the pit straight's pit side, the garages'), 'out' (anywhere, the outer side), 'backdrop' (evenly round the
# lap, the two sides in turn). Turned: 'face' (the way it faced Road Atlanta's track, to Fuji's) or 'along' (its long
# side along the track). Each prop stands just beyond the runway, behind its walls: no collision of its own; one
# that would reach over the runway anywhere is left out. A sixth field: the longest prop of the rule (MAX_PROP).
# (Road Atlanta's trees are trunks alone: the canopies are other meshes, many to a buffer, of packed vertices. Its
# forest cards (foliagefacade, tree_wall) ended in hard vertical edges by the track: the user's 'out of place'; none.)
SCATTER = [
    (r'workerstand\d*$', 14, 'corners', (4.0, 4.0), 'face'),
    # (no tyre walls: Road Atlanta's are whole stacks, 70-150 KB each; 20 of them were a third of the streamed
    # memory, over the stock track's busiest cell, and parts of the woods went unloaded)
    (r'catchfence\d+$', 60, 'fast', (1.0, 1.0), 'along'),
    (r'barrierblock\d+$', 24, 'pits', (0.5, 0.5), 'along'),
    (r'pole_streetlight\d+$', 12, 'pits', (13.0, 13.0), 'face'),
    (r'(shack|restroom|tvcart_base|racecart_base)\d*$', 20, 'out', (12.0, 30.0), 'face'),
]
MAX_PROP = 90.0   # m: props longer than this left out (a fence round a whole bend of Road Atlanta's would cross Fuji's track)
CARD_SINK = 0.35  # the share of a forest card's height sunk into the ground
TRIES = 6         # places tried for a prop before it is left out


def sides(centre):
    """Per centre line point: the unit tangent and the unit way across to the loop's inside (both on x and z)."""
    n = len(centre)
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0); t[:, 1] = 0; t /= np.linalg.norm(t, axis=1, keepdims=True)
    inner = np.stack([t[:, 2], np.zeros(n), -t[:, 0]], 1)
    if np.mean(np.einsum('ij,ij->i', inner[:, [0, 2]], (centre.mean(0) - centre)[:, [0, 2]])) < 0: inner = -inner
    return t, inner


def runway_reach(V, F, centre, inner):
    """For each point of the centre line (Forza's), how far the runway (any surface; V Forza's) reaches each side:
    (inner, outer) m from the centre line, its edge being where it stops for more than 3 m."""
    r = Raster(V, F, res=0.5)
    c = centre[:, [0, 2]]
    nrm = inner[:, [0, 2]]
    offs = np.arange(0, 250, 0.5)
    out = np.zeros((len(c), 2))
    for side, sgn in ((0, 1), (1, -1)):
        k = r.at(c[:, None, :] + sgn * offs[None, :, None] * nrm[:, None, :]) >= 0
        for i in range(len(c)):
            row, last, gap = k[i], 0, 0
            for j in range(len(row)):
                if row[j]: last, gap = j, 0
                else:
                    gap += 1
                    if gap > 6 and last: break
            out[i, side] = offs[last]
    return out


def inside(p, poly):
    """Which of the points p (..., 2) are inside the closed polygon poly (n, 2) (even-odd)."""
    x, z = p[..., 0][..., None], p[..., 1][..., None]
    a, b = poly, np.roll(poly, -1, 0)
    cross = ((a[:, 1] > z) != (b[:, 1] > z)) & (x < a[:, 0] + (z - a[:, 1]) * (b[:, 0] - a[:, 0]) / np.where(b[:, 1] == a[:, 1], 1e-9, b[:, 1] - a[:, 1]))
    return cross.sum(-1) % 2 == 1


def read_ground(runway_dir):
    """GT4's world model's ground near the track (run/gt4_fuji/world.obj, tools/gt4course.py's, in the runway's
    frame): its triangles facing up (|normal y| over GROUND_FLAT: walls, cards and fences left out), within
    GROUND_NEAR m of the runway's middle, in Forza's world. (vertices, triangles), or None without the file.
    Cached beside it as world_ground.npz."""
    src = os.path.join(runway_dir, 'world.obj')
    cache = os.path.join(runway_dir, 'world_ground.npz')
    if os.path.exists(cache) and (not os.path.exists(src) or os.path.getmtime(cache) >= os.path.getmtime(src)):
        z = np.load(cache)
        if 'near' in z and float(z['near']) == GROUND_NEAR and 'green' in z: return z['V'], z['T']
    if not os.path.exists(src): return None
    green = green_materials(runway_dir)
    V, T, M, cur = [], [], [], None
    for l in open(src):
        if l.startswith('v '): V.append(list(map(float, l.split()[1:4])))
        elif l.startswith('usemtl '): cur = l.split()[1]
        elif l.startswith('f '): T.append([int(x.split('/')[0]) - 1 for x in l.split()[1:4]]); M.append(cur in green)
    V, T, M = np.array(V), np.array(T), np.array(M, bool)
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    ln = np.linalg.norm(n, axis=1)
    mid = V[T].mean(1)
    keep = (ln > 1e-9) & (np.abs(n[:, 1]) > GROUND_FLAT * np.maximum(ln, 1e-9)) & M & \
           (np.hypot(mid[:, 0] - GT4_MIDDLE[0], mid[:, 2] - GT4_MIDDLE[1]) < GROUND_NEAR)
    T = T[keep]
    used = np.unique(T)
    remap = np.full(len(V), -1); remap[used] = np.arange(len(used))
    V, T = to_forza(V[used]), remap[T]
    np.savez(cache, V=V, T=T, near=GROUND_NEAR, green=True)
    return V, T


def green_materials(runway_dir):
    """GT4's world model's materials whose texture is green (grass, woods: its ground), from world.mtl and the
    textures beside it: its grandstands', buildings' and paving's flat faces are not the ground (a hill rose where
    its main grandstand stands, ours sunk in it)."""
    out = set()
    mtl = os.path.join(runway_dir, 'world.mtl')
    if not os.path.exists(mtl): return out
    cur = None
    for l in open(mtl):
        if l.startswith('newmtl '): cur = l.split()[1]
        elif l.startswith('map_Kd ') and cur:
            p_ = os.path.join(runway_dir, l.split(None, 1)[1].strip())
            if not os.path.exists(p_): continue
            a = read_png(p_).astype(float)
            if a.shape[2] == 4: a = a[a[..., 3] > 64]
            else: a = a.reshape(-1, 3)
            if not len(a): continue
            r, g, b = a[:, :3].mean(0)
            if g > r * 1.05 and g > b * 1.05: out.add(cur)
    return out


def ground_raster(Gv, Gt, lo, shape, g):
    """The lowest of the ground triangles' heights in each cell of a raster (lo, shape, g m cells), NaN where none
    (the lowest: a roof or a stand over the ground is not the ground)."""
    out = np.full(shape, np.inf)
    P = (Gv[:, [0, 2]] - lo) / g
    for a, b, c in Gt:
        t = P[[a, b, c]]
        lo_ = np.maximum(np.floor(t.min(0)).astype(int), 0); hi_ = np.minimum(np.ceil(t.max(0)).astype(int), [shape[1] - 1, shape[0] - 1])
        if (hi_ < lo_).any(): continue
        xx, zz = np.meshgrid(np.arange(lo_[0], hi_[0] + 1), np.arange(lo_[1], hi_[1] + 1))
        v0, v1 = t[1] - t[0], t[2] - t[0]
        det = v0[0] * v1[1] - v0[1] * v1[0]
        if abs(det) < 1e-12: continue
        qx, qz = xx + 0.5 - t[0][0], zz + 0.5 - t[0][1]
        u = (qx * v1[1] - qz * v1[0]) / det
        w = (v0[0] * qz - v0[1] * qx) / det
        m = (u >= -1e-6) & (w >= -1e-6) & (u + w <= 1 + 1e-6)
        ys = Gv[[a, b, c], 1]
        np.minimum.at(out, (zz[m], xx[m]), ys[0] + u[m] * (ys[1] - ys[0]) + w[m] * (ys[2] - ys[0]))
    return np.where(np.isfinite(out), out, np.nan)


def box_axes(xz):
    """The sides of the smallest rectangle round the points (x, z): (the long side's direction, the short's)."""
    best = None
    for deg in np.arange(0, 90, 0.5):
        u = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))]); v = np.array([-u[1], u[0]])
        a_, b_ = np.ptp(xz @ u), np.ptp(xz @ v)
        if best is None or a_ * b_ < best[0]: best = (a_ * b_, (u, v) if a_ >= b_ else (v, u))
    return best[1]


def apron(centre, inner, reach_in, s0, s1, cols, ground_at=None):
    """A paved area beyond the runway's inside edge from s0 to s1 (shares of the lap), in columns `cols` (metres
    beyond the edge, and whether on the ground (ground_at's, a little over it) or at the centre line's height,
    the pit lane's): (vertices, triangles wound as the runway's)."""
    n = len(centre)
    a, b = int(s0 * n), int(s1 * n) + (n if s1 < s0 else 0)
    m = len(cols)
    V, T = [], []
    for k, j in enumerate(range(a, b + 1, 2)):
        i = j % n
        for off, on_ground in cols:
            q = centre[i] + inner[i] * (reach_in[i] + off)
            q[1] = float(ground_at(q[None, [0, 2]])[0]) + 0.15 if on_ground and ground_at else centre[i][1] + 0.02
            V.append(q)
        if k:
            for c in range(m - 1):
                p0, p1 = m * (k - 1) + c, m * k + c
                T += [(p0, p0 + 1, p1 + 1), (p0, p1 + 1, p1)]
    V, T = np.array(V, float), np.array(T, int)
    nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    flip = nrm[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    return V, T


def grid_sampler(Hg, lo, cell):
    """A grid's heights (corners every `cell` m from `lo`) at points (..., 2), blended between its corners."""
    nz, nx = Hg.shape

    def at(xz):
        f = (np.asarray(xz, float) - lo) / cell
        i0 = np.clip(np.floor(f).astype(int), 0, [nx - 2, nz - 2])
        t = np.clip(f - i0, 0, 1)
        a, b = i0[..., 0], i0[..., 1]
        return (Hg[b, a] * (1 - t[..., 0]) + Hg[b, a + 1] * t[..., 0]) * (1 - t[..., 1]) + \
               (Hg[b + 1, a] * (1 - t[..., 0]) + Hg[b + 1, a + 1] * t[..., 0]) * t[..., 1]
    return at


def spread(y, it=600):
    """The raster y's NaN cells filled from their filled neighbours, a ring at a time: (y, how many rings away)."""
    filled = np.isfinite(y)
    away = np.where(filled, 0, -1)
    nb = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dz or dx]
    for k in range(1, it):
        y0 = np.where(filled, y, 0.0)
        acc = sum(np.roll(np.roll(y0, dz, 0), dx, 1) for dz, dx in nb)
        cnt = sum(np.roll(np.roll(filled, dz, 0), dx, 1).astype(int) for dz, dx in nb)
        new = ~filled & (cnt > 0)
        if not new.any(): break
        y[new] = acc[new] / cnt[new]; away[new] = k; filled |= new
    return y, away


def canopy(xz, away, clear):
    """The woods' height over the ground at points (..., 2) `away` m beyond the runway: 0 within FOREST_FROM and in
    the clearings (clear: a function of the points, True where none), rising over FOREST_RAMP m to CANOPY_H, bumpy."""
    xz = np.asarray(xz, float)
    bumps = CANOPY_BUMPS * (np.sin(xz[..., 0] * 0.071 + 1.3) * np.cos(xz[..., 1] * 0.053) + 0.6 * np.sin((xz[..., 0] + xz[..., 1]) * 0.11))
    c = np.clip((away - FOREST_FROM) / FOREST_RAMP, 0, 1) * (CANOPY_H + bumps)
    return np.where(clear(xz), 0.0, np.maximum(c, 0))


def clearings(centre, inner, reach_in, reach_out):
    """CLEARINGS as a function of points (..., 2): True in them."""
    n = len(centre)
    c2 = centre[:, [0, 2]]

    def clear(xz):
        q = np.asarray(xz, float).reshape(-1, 2)
        out = np.zeros(len(q), bool)
        for a in range(0, len(q), 4000):
            d = np.hypot(q[a:a + 4000, None, 0] - c2[None, :, 0], q[a:a + 4000, None, 1] - c2[None, :, 1])
            j = d.argmin(1); dist = d[np.arange(len(j)), j]
            side_in = np.einsum('ij,ij->i', q[a:a + 4000] - c2[j], inner[j][:, [0, 2]]) > 0
            share = j / n
            for s0, s1, side, keep in CLEARINGS:
                on = (share >= s0) | (share <= s1) if s1 < s0 else (share >= s0) & (share <= s1)
                beyond = dist - np.where(side_in, reach_in[j], reach_out[j])
                out[a:a + 4000] |= on & (side_in == (side == 'in')) & (beyond < keep)
        return out.reshape(np.asarray(xz).shape[:-1])
    return clear


def far_terrain(Vf, F, loop, ground, clear=None, cell=FAR_CELL, reach=FAR_REACH, near=TERRAIN_REACH, drop=TERRAIN_DROP + FAR_DROP):
    """The ground from the near grid's edge (terrain's) out to `reach` m beyond the runway, outside the loop: a grid of
    `cell` m squares at GT4's ground's height (its far hills too) where it has some, else the runway's spread
    outward; no steeper than GROUND_SLOPE; `drop` m down (the near grid draws over it where they overlap).
    (vertices, triangles wound as the runway's)."""
    g = 8.0
    r = Raster(Vf, F, res=g, pad=reach + 2 * cell)
    y = r.y.astype(float).copy()
    on = np.isfinite(y)
    _, away = spread(y.copy())
    away = away * g
    if ground is not None:
        gr = ground_raster(ground[0], ground[1], r.lo, r.shape, g)
        stack = np.stack([np.roll(np.roll(gr, dz, 0), dx, 1) for dz in range(-2, 3) for dx in range(-2, 3)])
        with np.errstate(all='ignore'):
            med = np.nanmedian(stack, 0)
        gr[np.abs(gr - med) > 6.0] = np.nan
        use = np.isfinite(gr) & ~on
        y[use] = gr[use]
    y, _ = spread(y)
    nb = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dz or dx]
    rise = GROUND_SLOPE * g
    for _ in range(60):
        lo_n = np.minimum.reduce([np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb])
        hi_n = np.maximum.reduce([np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb])
        y2 = np.where(on, y, np.clip(y, hi_n - rise * 1.5, lo_n + rise))
        if np.allclose(y2, y): break
        y = y2
    for _ in range(2):
        m = sum(np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb + [(0, 0)]) / 9
        y[~on] = m[~on]
    lo = r.lo + cell
    nx = int((r.shape[1] * g - 2 * cell) / cell) + 1
    nz = int((r.shape[0] * g - 2 * cell) / cell) + 1
    gx, gz = np.meshgrid(lo[0] + cell * np.arange(nx), lo[1] + cell * np.arange(nz))
    corner = np.stack([gx, gz], -1)
    ij = np.clip(np.floor((corner - r.lo) / g).astype(int), 0, [r.shape[1] - 1, r.shape[0] - 1])
    zi, xi = ij[..., 1], ij[..., 0]
    a_ = away[zi, xi]
    keep = (a_ <= reach) & ~inside(corner, loop[:, [0, 2]])
    deep = a_ < near - 2 * TERRAIN_CELL  # (well inside the near grid)
    can = canopy(corner, a_, clear) if clear else np.zeros(gx.shape)
    vid = -np.ones(gx.shape, int)
    V, T, K = [], [], []
    for a in range(nz - 1):
        for b in range(nx - 1):
            q4 = ((a, b), (a, b + 1), (a + 1, b + 1), (a + 1, b))
            if not all(keep[u, v] for u, v in q4) or all(deep[u, v] for u, v in q4): continue
            q = []
            for u, v in q4:
                if vid[u, v] < 0:
                    vid[u, v] = len(V); V.append((gx[u, v], y[zi[u, v], xi[u, v]] - drop + can[u, v], gz[u, v]))
                q.append(vid[u, v])
            T += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
            K += [FOREST if max(can[u, v] for u, v in q4) > 1.0 else GRASS] * 2
    V, T, K = np.array(V, float), np.array(T, int), np.array(K, int)
    nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    flip = nrm[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    print('far ground: %d vertices, %d triangles (%d woods), %.0f to %.0f m high' % (len(V), len(T), (K == FOREST).sum(), V[:, 1].min(), V[:, 1].max()))
    return V, T, K, grid_sampler(y[zi, xi] - drop + can, lo, cell)


def terrain(Vf, F, drawn, loop, ground=None, clear=None, cell=TERRAIN_CELL, reach=TERRAIN_REACH, drop=TERRAIN_DROP):
    """The ground round the runway (Forza's, V; F all its faces, `drawn` those drawn; loop the centre line): a
    grid of `cell` m squares out to `reach` m beyond the runway and over all the loop's middle, each corner at
    GT4's ground's height there (read_ground; its hills) where it has some, else at the runway's height spread outward (the nearest runway's,
    smoothed), `drop` m under it, and under the lowest drawn runway within a cell of it; squares the drawn
    runway covers left out. Returns (vertices, triangles: wound as the runway's) for the grass, visual only (the
    runway's walls keep the cars off it)."""
    g = 2.0
    r = Raster(Vf, F, res=g, pad=reach + 2 * cell)
    rd = Raster(Vf, F[drawn], res=g, pad=reach + 2 * cell)
    y = r.y.astype(float).copy()
    filled = np.isfinite(y)
    away = np.where(filled, 0.0, np.inf)
    nb = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dz or dx]
    for it in range(1, 400):  # spread outward a ring at a time, over the whole raster: each new cell the mean of its filled neighbours
        y0 = np.where(filled, y, 0.0)
        acc = sum(np.roll(np.roll(y0, dz, 0), dx, 1) for dz, dx in nb)
        cnt = sum(np.roll(np.roll(filled, dz, 0), dx, 1).astype(int) for dz, dx in nb)
        new = ~filled & (cnt > 0)
        if not new.any(): break
        y[new] = acc[new] / cnt[new]; away[new] = it * g; filled |= new
    if ground is not None:  # GT4's ground off the runway where it has some, the rest spread again from it and the runway
        gr = ground_raster(ground[0], ground[1], r.lo, r.shape, g)
        # spikes out (a stand's or a roof's top where no ground is under it): cells 3 m off their 10 m median
        stack = np.stack([np.roll(np.roll(gr, dz, 0), dx, 1) for dz in range(-2, 3) for dx in range(-2, 3)])
        with np.errstate(all='ignore'):
            med = np.nanmedian(stack, 0)
        gr[np.abs(gr - med) > 3.0] = np.nan
        use = np.isfinite(gr) & (away > 0)
        y = r.y.astype(float).copy()
        y[use] = gr[use]
        filled = np.isfinite(y)
        for it in range(1, 400):
            y0 = np.where(filled, y, 0.0)
            acc = sum(np.roll(np.roll(y0, dz, 0), dx, 1) for dz, dx in nb)
            cnt = sum(np.roll(np.roll(filled, dz, 0), dx, 1).astype(int) for dz, dx in nb)
            new = ~filled & (cnt > 0)
            if not new.any(): break
            y[new] = acc[new] / cnt[new]; filled |= new
        off = away > 0
        rise = GROUND_SLOPE * g
        for _ in range(60):  # no steeper than GROUND_SLOPE off the runway: a block (a stand with no ground under it) a hill
            lo_n = np.minimum.reduce([np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb])
            hi_n = np.maximum.reduce([np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb])
            y2 = np.where(off, np.clip(y, hi_n - rise * 1.5, lo_n + rise), y)
            if np.allclose(y2, y): break
            y = y2
        for _ in range(3):  # smoothed off the runway (2 m cells of the lowest triangle: steps)
            m = sum(np.roll(np.roll(y, dz, 0), dx, 1) for dz, dx in nb + [(0, 0)]) / 9
            y[off] = m[off]
        print('terrain: GT4 ground under %.0f%% of the cells off the runway, %.0f to %.0f m high' %
              (100 * use.sum() / max(1, (away > 0).sum()), np.nanmin(gr), np.nanmax(gr)))
    ydraw = np.where(np.isfinite(rd.y), rd.y, np.inf).astype(float)
    low = ydraw.copy()
    for _ in range(int(cell / g)):  # the lowest drawn runway within a cell
        low = np.minimum.reduce([np.roll(np.roll(low, dz, 0), dx, 1) for dz, dx in nb + [(0, 0)]])
    hgt = np.minimum(y, low) - drop

    def at(xz):
        ij = np.clip(np.floor((xz - r.lo) / g).astype(int), 0, [r.shape[1] - 1, r.shape[0] - 1])
        return ij[..., 1], ij[..., 0]
    lo = r.lo + cell
    nx = int((r.shape[1] * g - 2 * cell) / cell) + 1
    nz = int((r.shape[0] * g - 2 * cell) / cell) + 1
    gx, gz = np.meshgrid(lo[0] + cell * np.arange(nx), lo[1] + cell * np.arange(nz))
    corner = np.stack([gx, gz], -1)
    zi, xi = at(corner)
    near = (away[zi, xi] <= reach) | inside(corner, loop[:, [0, 2]])  # (and all the loop's middle)
    can = canopy(corner, away[zi, xi], clear) if clear else np.zeros(gx.shape)
    vid = -np.ones(gx.shape, int)
    V, T, K = [], [], []
    for a in range(nz - 1):
        for b in range(nx - 1):  # (under the runway too: GT4's runway has cracks at its seams and T-junctions, holes
            if not (near[a, b] and near[a + 1, b] and near[a, b + 1] and near[a + 1, b + 1]): continue  # to the sky)
            q = []
            for (u, v) in ((a, b), (a, b + 1), (a + 1, b + 1), (a + 1, b)):
                if vid[u, v] < 0:
                    vid[u, v] = len(V); V.append((gx[u, v], hgt[zi[u, v], xi[u, v]] + can[u, v], gz[u, v]))
                q.append(vid[u, v])
            T += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
            K += [FOREST if max(can[u_, v_] for u_, v_ in ((a, b), (a, b + 1), (a + 1, b + 1), (a + 1, b))) > 1.0 else GRASS] * 2
    V, T, K = np.array(V, float), np.array(T, int), np.array(K, int)
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    flip = n[:, 1] > 0
    T[flip] = T[flip][:, [0, 2, 1]]
    H = hgt[zi, xi]
    print('terrain: %d of %d triangles woods' % ((K == FOREST).sum(), len(K)))
    # the ground's height (the grass) and the woods' top (the canopy over it), at points (..., 2)
    return V, T, grid_sampler(H, lo, cell), K, grid_sampler(H + can, lo, cell)


def scatter(res, names, model, ppw, svb, svb_out, centre, reach_in, reach_out, used, ground_at=None, seed=7, spare=None):
    """SCATTER's props placed round Fuji (centre: Forza's, a point every STEP m; reach_in/out: how far the runway
    reaches each side of it there, the inside of the loop and the outside: runway_reach). Returns (meshes,
    textures, vertex buffers). Each stands on the ground (ground_at: terrain's), its lowest point under its foot."""
    import re
    from collections import Counter
    rng = np.random.default_rng(seed)
    n = len(centre)
    t, inner_dir = sides(centre)
    k = 15  # (30 m each way)
    turnrate = np.array([np.arctan2(t[i - k][0] * t[(i + k) % n][2] - t[i - k][2] * t[(i + k) % n][0],
                                    t[i - k][[0, 2]] @ t[(i + k) % n][[0, 2]]) for i in range(n)])

    def clear(p):  # a placed prop's points (x, z) all beyond the runway, on whichever side each is
        d = np.hypot(*(centre[None, :, [0, 2]] - p[:, None, :]).transpose(2, 0, 1))
        j = d.argmin(1)
        inside = np.einsum('ij,ij->i', p - centre[j][:, [0, 2]], inner_dir[j][:, [0, 2]]) > 0
        return bool(np.all(d[np.arange(len(p)), j] >= np.where(inside, reach_in[j], reach_out[j]) + 0.25))
    corners = []
    for i in range(n):
        tr = abs(turnrate[i])
        if tr > 0.6 and tr >= abs(turnrate[(i - 8) % n]) and tr >= abs(turnrate[(i + 8) % n]):
            if not corners or min(abs(i - corners[-1]), n - abs(i - corners[-1])) > 40: corners.append(i)
    fast = [i for i in range(n) if abs(turnrate[i]) < 0.15]
    pits = [i for i in range(n) if (i < n * 0.04 or i > n * 0.86) and abs(turnrate[i]) < 0.15]

    def outside(i):  # a corner's outside: away from where it turns
        bend = t[(i + k) % n] - t[i - k]
        return 'in' if bend[[0, 2]] @ inner_dir[i][[0, 2]] < 0 else 'out'
    meshes, texs, vbs = [], set(), set()
    inst_names = sorted({re.sub(r'_vb\d+$', '', r[0][len('vbuff_quickpreview_'):]) for r in names
                         if r[0].startswith('vbuff_quickpreview_') and 'splines' not in r[0]})
    print('scatter: %d corners, %d fast points, %d pit-straight points' % (len(corners), len(fast), len(pits)))
    seg = np.linalg.norm(np.diff(np.vstack([centre, centre[:1]])[:, [0, 2]], axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)])
    lap = arc[-1]
    for stems_, s0, s1, side, gap_, spacing in ROWS:
        if isinstance(stems_, list): stems = [x for x in stems_ if x in inst_names and x not in used]
        else:
            pat = re.compile(stems_[0])
            stems = [x for x in inst_names if pat.match(x) and x not in used][:stems_[1]]
        at = s0 * lap
        end = s1 * lap + (lap if s1 < s0 else 0)
        placed = 0
        for stem in stems:
            ms = object_meshes(res, names, model, stem)
            if not ms: continue
            bufs, allp = instance_geometry(res, names, model, ms)
            if len(allp) < 3: continue
            mid = (allp.min(0) + allp.max(0)) / 2
            xz = allp[:, [0, 2]] - mid[[0, 2]]
            long_axis, short_axis = box_axes(xz)
            length = float(np.ptp(xz @ long_axis))
            if at + length > end: break
            i0 = int(np.searchsorted(arc, (at + length / 2) % lap)) % n
            at += length + spacing
            d = inner_dir[i0] if side == 'in' else -inner_dir[i0]
            reach = reach_in[i0] if side == 'in' else reach_out[i0]
            base = np.arctan2(t[i0][2], t[i0][0]) - np.arctan2(long_axis[1], long_axis[0])
            f0 = facing(mid)
            square = length < 1.4 * float(np.ptp(xz @ short_axis))  # (its long side no guide: any right angle)
            a = max([base + k_ * np.pi / (2 if square else 1) for k_ in range(4 if square else 2)],
                    key=lambda a_: np.cos(f0 + a_) * -d[0] + np.sin(f0 + a_) * -d[2])  # its front to the track
            R = turn(a)
            near_side = (xz @ R.T @ d[[0, 2]]).min()
            for push in ROW_PUSH:
                target = centre[i0] + d * (reach + gap_ + push - near_side)
                if clear(xz @ R.T + target[[0, 2]]): break
            else: continue
            foot = ground_at(xz @ R.T + target[[0, 2]]).min() if ground_at else centre[i0][1]
            m_, t_, v_ = place_instance(res, names, model, ppw, svb, svb_out, ms, bufs, mid, R, target, foot - allp[:, 1].min())
            if m_: placed += 1
            meshes += m_; texs |= t_; vbs |= v_
            used.add(stem)
        print('row %-30s %3d placed of %3d, %s %.0f m out, %.0f%% to %.0f%%' % (str(stems_[0])[:30], placed, len(stems), side, gap_, 100 * s0, 100 * s1))
    # GT4's stands: copies (from the disc's geometry, ORIG_RES) end to end at each site
    if spare is not None:
        src = {}
        for stem in STAND_CLONES:
            ms = object_meshes(ORIG_RES, names, model, stem)
            bufs, allp = instance_geometry(ORIG_RES, names, model, ms)
            if len(allp) < 3: continue
            mid = (allp.min(0) + allp.max(0)) / 2
            xz = allp[:, [0, 2]] - mid[[0, 2]]
            la, sa = box_axes(xz)
            src[stem] = (ms, allp, mid, xz, la, sa)
        copies = 0
        for s0, s1, side in STAND_SITES:
            at, end, k_ = s0 * lap, s1 * lap, 0
            why = Counter()
            while True:  # (the next in turn that fits what is left of the site)
                fit = [st_ for st_ in (STAND_CLONES[(k_ + q_) % len(STAND_CLONES)] for q_ in range(len(STAND_CLONES)))
                       if st_ in src and at + float(np.ptp(src[st_][3] @ src[st_][4])) <= end]
                if not fit: break
                stem = fit[0]; k_ = STAND_CLONES.index(stem) + 1
                ms, allp, mid, xz, long_axis, short_axis = src[stem]
                length = float(np.ptp(xz @ long_axis))
                i0 = int(np.searchsorted(arc, (at + length / 2) % lap)) % n
                at += length + 4.0
                d = inner_dir[i0] if side == 'in' else -inner_dir[i0]
                reach = reach_in[i0] if side == 'in' else reach_out[i0]
                base = np.arctan2(t[i0][2], t[i0][0]) - np.arctan2(long_axis[1], long_axis[0])
                f0 = facing(mid)
                a = max((base, base + np.pi), key=lambda a_: np.cos(f0 + a_) * -d[0] + np.sin(f0 + a_) * -d[2])
                R = turn(a)
                near_side = (xz @ R.T @ d[[0, 2]]).min()
                for push in STAND_PUSH:
                    target = centre[i0] + d * (reach + STAND_GAP + push - near_side)
                    if clear(xz @ R.T + target[[0, 2]]): break
                else: why['over the runway'] += 1; continue
                foot = ground_at(xz @ R.T + target[[0, 2]]).min() if ground_at else centre[i0][1]
                m_, t_, v_ = clone_instance(res, names, model, ppw, svb, svb_out, ms, mid, R, target, foot - allp[:, 1].min(), spare)
                if m_: copies += 1; why['copied'] += 1
                else: why['no donors'] += 1
                meshes += m_; texs |= t_; vbs |= v_
            print('stands %.0f%%-%.0f%% %s: %s' % (100 * s0, 100 * s1, side, dict(why)))
        print('stands: %d copies at GT4\'s %d sites (%d spare donors left)' % (copies, len(STAND_SITES), len(spare)))
    for pattern, most, where, gap, align, *longest in SCATTER:
        pat = re.compile(pattern)
        stems = [s_ for s_ in inst_names if pat.match(s_) and s_ not in used][:most]
        slot, placed, fast_at, crossing = 0, 0, 0, 0
        for stem in stems:
            ms = object_meshes(res, names, model, stem)
            if not ms: continue
            bufs, allp = instance_geometry(res, names, model, ms)
            if len(allp) < 3: continue
            mid = (allp.min(0) + allp.max(0)) / 2
            xz = allp[:, [0, 2]] - mid[[0, 2]]
            ev, evec = np.linalg.eigh(np.cov(xz.T))
            long_axis = evec[:, -1]
            length = 2 * np.abs(xz @ long_axis).max()
            if length > (longest[0] if longest else MAX_PROP): continue
            # a few tries: the next place along, a curved prop the other way round, a metre further out each time
            ok, used_up = False, False
            for attempt in range(TRIES):
                if where == 'corners':
                    if not corners: used_up = True; break
                    c_ = corners[slot % len(corners)]; i0 = (c_ + 4 * (slot // len(corners))) % n; side = outside(c_)
                elif where == 'fast':
                    if fast_at >= len(fast): used_up = True; break
                    i0 = fast[fast_at]; side = 'out' if slot % 2 == 0 else 'in'
                    if side == 'in': fast_at += max(1, int(length / STEP) + 1)
                elif where == 'pits':
                    at_ = slot * max(1, int(length / STEP) + 2)
                    if at_ >= len(pits): used_up = True; break
                    i0 = pits[at_]; side = 'in'
                elif where == 'out':
                    i0 = int(rng.integers(n)); side = 'out'
                else:
                    i0 = (slot * n // max(1, len(stems)) + int(rng.integers(8))) % n; side = 'in' if slot % 2 else 'out'
                slot += 1
                d = inner_dir[i0] if side == 'in' else -inner_dir[i0]
                reach = reach_in[i0] if side == 'in' else reach_out[i0]
                g = (gap[0] if gap[0] == gap[1] else rng.uniform(*gap)) + attempt
                if align == 'along':
                    a = np.arctan2(t[i0][2], t[i0][0]) - np.arctan2(long_axis[1], long_axis[0]) + np.pi * (attempt % 2)
                else:
                    a = np.arctan2(-d[2], -d[0]) - facing(mid)
                R = turn(a)
                near_side = (xz @ R.T @ d[[0, 2]]).min()
                target = centre[i0] + d * (reach + g - near_side)
                if clear(xz @ R.T + target[[0, 2]]): ok = True; break
            if used_up: break
            if not ok: crossing += 1; continue
            foot = ground_at(xz @ R.T + target[[0, 2]]).min() if ground_at else centre[i0][1]
            if where == 'backdrop': foot -= CARD_SINK * np.ptp(allp[:, 1])  # (a forest card 50 m high: a wall)
            m_, t_, v_ = place_instance(res, names, model, ppw, svb, svb_out, ms, bufs, mid, R, target, foot - allp[:, 1].min())
            if m_: placed += 1
            meshes += m_; texs |= t_; vbs |= v_
            used.add(stem)
        print('scatter %-26s %3d placed of %3d, %s (%d over the runway, left out)' % (pattern[:26], placed, len(stems), where, crossing))
    return meshes, texs, vbs


def texture_shape(res, names, stx, t):
    """Texture resource t's (width, height, kind: 1 DXT1, 5 DXT5): its format from the stx copy's record, its
    size the one whose mip chain fills the resource (as blender_export.texture_png finds it)."""
    size, slots, _, nres = struct.unpack_from('<4I', stx, 20)
    table = np.frombuffer(stx, '<i4', nres, 36)
    fmt = struct.unpack_from('<5I', stx, 36 + 4 * nres + 20 * int(table[t]))[3]
    f, lu, lv = (fmt >> 8) & 0xFF, (fmt >> 20) & 0xF, (fmt >> 24) & 0xF
    kind, bs = {0x0C: (1, 8), 0x0E: (5, 16), 0x0F: (5, 16)}[f]
    nbytes = names[t - 9][4]
    for a in range(2, 12):
        w, h = 1 << a, 1 << max(a - (lu - lv), 0)
        tot, ww, hh = 0, w, h
        while True:
            tot += max(ww // 4, 1) * max(hh // 4, 1) * bs
            if ww == 1 and hh == 1: break
            ww, hh = max(ww // 2, 1), max(hh // 2, 1)
        if tot == nbytes or w * h * bs // 16 == nbytes: return w, h, kind
    raise ValueError('texture %d: no size fits %d bytes' % (t, nbytes))


def retexture(res, names, stx, art_dir):
    """BANNERS' images written over their textures, each at the texture's size and format with its mips."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for t, name, across in BANNERS:
        w, h, kind = texture_shape(res, names, stx, t)
        img = read_png(os.path.join(art_dir, name)).astype(np.float32)
        img = np.concatenate([img] * across, 1)
        ys = (np.arange(h) * img.shape[0] / h).astype(int); xs = (np.arange(w) * img.shape[1] / w).astype(int)
        img = img[ys][:, xs]
        img[..., :3] = np.clip(img[..., :3] * ART_GAIN, 0, 255)
        img[..., 3] = 255
        o, n = names[t - 9][3], names[t - 9][4]
        res[o:o + n] = forzaxpr.encode_with_mips(img.astype(np.uint8), kind, n)
        print('texture %d (%s): %s at %d x %d, DXT%d' % (t, names[t - 9][0][-40:], name, w, h, kind))


def line_paint(res, names, stx, t=2180, white=232.0):
    """Road Atlanta's road line texture (roadline_whole: worn light grey) as fresh white paint for GT4's painted
    lines (the grid, the start line): its brightness scaled to `white`, its wear kept."""
    w, h, kind = texture_shape(res, names, stx, t)
    o, n = names[t - 9][3], names[t - 9][4]
    img = np.asarray(forzaxpr.dxt(bytes(res[o:o + n]), w, h, kind)).astype(np.float32)
    img[..., :3] *= white / max(1.0, img[..., :3].mean())
    img[..., 3] = 255
    res[o:o + n] = forzaxpr.encode_with_mips(img.clip(0, 255).astype(np.uint8), kind, n)
    print('lines: texture %d painted white' % t)


def light_ramp(res, names, stx, t=LIGHTMAP[0]):
    """The grey ramp the ground's light samples (texel x grey x) over RAMP_ROWS of the lightmap, its other rows (the
    texels the trees, rails and props sample) kept."""
    w, h, kind = texture_shape(res, names, stx, t)
    o, n = names[t - 9][3], names[t - 9][4]
    img = np.asarray(forzaxpr.dxt(bytes(res[o:o + n]), w, h, kind)).astype(np.float32).copy()
    r0, r1 = (np.array(RAMP_ROWS) * h // 256)
    img[r0:r1, :, :3] = (np.arange(w) * 256.0 / w)[None, :, None]
    res[o:o + n] = forzaxpr.encode_with_mips(img.clip(0, 255).astype(np.uint8), kind, n)
    print('light: a grey ramp on lightmap %d rows %d-%d (%d x %d)' % (t, r0, r1, w, h))


def value_noise(xz, scale, seed):
    """Smooth noise (-1..1) at a point (x, z): random values on a grid `scale` m apart, blended (smoothstep)."""
    f = np.asarray(xz, float) / scale
    i0 = np.floor(f).astype(np.int64); t = f - i0
    t = t * t * (3 - 2 * t)

    def r(a, b):
        hsh = (a * 73856093) ^ (b * 19349663) ^ (seed * 83492791)
        return ((hsh * 2654435761) % 1000003) / 500001.5 - 1.0
    a, b = int(i0[0]), int(i0[1])
    return (r(a, b) * (1 - t[0]) + r(a + 1, b) * t[0]) * (1 - t[1]) + (r(a, b + 1) * (1 - t[0]) + r(a + 1, b + 1) * t[0]) * t[1]


def kerb_colour(res, names, stx, t=497):
    """Road Atlanta's kerb texture (road_curbing_standard_001: green and white stripes) red and white as Fuji's:
    its red and green swapped (white stays white), written back with its mips."""
    w, h, kind = texture_shape(res, names, stx, t)
    o, n = names[t - 9][3], names[t - 9][4]
    img = np.asarray(forzaxpr.dxt(bytes(res[o:o + n]), w, h, kind)).copy()
    img[..., [0, 1]] = img[..., [1, 0]]
    f = img.astype(np.float32)
    red = (f[..., 0] - f[..., 1]) > 12  # (the stripes: brighter, redder)
    f[red, 0] = np.minimum(f[red, 0] * 1.35 + 20, 255); f[red, 1:3] *= 0.7
    img = f.clip(0, 255)
    img[..., 3] = 255
    res[o:o + n] = forzaxpr.encode_with_mips(img.astype(np.uint8), kind, n)
    print('kerbs: texture %d red and white' % t)


def far_pictures(res, names, stx, folder):
    """GT4's far pictures (FAR_TEX) each over its FAR_SLOTS texture, at that texture's size, colours doubled."""
    for name, t in zip(FAR_TEX, FAR_SLOTS):
        p_ = os.path.join(folder, name + '.png')
        if not os.path.exists(p_): continue
        w, h, kind = texture_shape(res, names, stx, t)
        img = read_png(p_).astype(np.float32)
        if img.shape[2] == 3: img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.float32)], 2)
        ys = (np.arange(h) * img.shape[0] / h).astype(int); xs = (np.arange(w) * img.shape[1] / w).astype(int)
        img = img[ys][:, xs]
        img[..., :3] = np.clip(img[..., :3] * ART_GAIN, 0, 255)
        o, n = names[t - 9][3], names[t - 9][4]
        res[o:o + n] = forzaxpr.encode_with_mips(img.clip(0, 255).astype(np.uint8), kind, n)
    print('far: %d pictures on textures %s' % (len(FAR_TEX), FAR_SLOTS))


def far_ring(runway_dir):
    """GT4's far cards (FAR_TEX's materials in far/far.obj) in Forza's frame, scaled about the circuit's middle so
    their median distance is FAR_RING m: (vertices, triangles both faces, texture coordinates (v down), kinds)."""
    src = os.path.join(runway_dir, 'far', 'far.obj')
    if not os.path.exists(src): return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 2)), np.zeros(0, int)
    mats = {'t' + t: i for i, t in enumerate(FAR_TEX)}
    V, VT, P, UV, K, cur = [], [], [], [], [], None
    for l in open(src):
        if l.startswith('v '): V.append(list(map(float, l.split()[1:4])))
        elif l.startswith('vt '): VT.append(list(map(float, l.split()[1:3])))
        elif l.startswith('usemtl '): cur = mats.get(l.split()[1])
        elif l.startswith('f ') and cur is not None:
            ps = [x.split('/') for x in l.split()[1:4]]
            P.append([V[int(a) - 1] for a, b in ps]); UV.append([(VT[int(b) - 1][0], 1 - VT[int(b) - 1][1]) for a, b in ps]); K.append(FAR_KIND + cur)
    if not P: return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 2)), np.zeros(0, int)
    P = to_forza(np.array(P, float).reshape(-1, 3))
    mid = np.array([RA_MIDDLE[0], 0.0, RA_MIDDLE[1]])
    # each point pulled in to FAR_RING m along its own direction, its height kept as the angle it is seen at (GT4's
    # cards run from 1 to 60 km: scaled as one, the near ends stood among the trees)
    d = np.hypot(P[:, 0] - mid[0], P[:, 2] - mid[2])
    f = FAR_RING / np.maximum(d, 1.0)
    P = np.stack([mid[0] + (P[:, 0] - mid[0]) * f, P[:, 1] * f + FAR_BASE, mid[2] + (P[:, 2] - mid[2]) * f], 1)
    sc_ = float(np.median(f))
    n = len(P) // 3
    T = np.arange(3 * n).reshape(n, 3)
    T = np.vstack([T, T[:, [0, 2, 1]]])
    K = np.array(K + K, int)
    print('far: %d cards\' triangles, scaled by %.3f, %.0f to %.0f m high' % (n, sc_, P[:, 1].min(), P[:, 1].max()))
    return P, T, np.array(UV, float).reshape(-1, 2), K


def tree_sheet(res, names, stx, folder):
    """GT4's tree pictures (TREE_TEX) side by side over the TREE_SHEET texture, each in its cell, colours doubled
    as GT4's (ART_GAIN), its alpha doubled where GT4's runs to 128."""
    w, h, kind = texture_shape(res, names, stx, TREE_SHEET)
    cw = w // 8
    sheet = np.zeros((h, w, 4), np.float32)
    for i, t in enumerate(TREE_TEX):
        img = read_png(os.path.join(folder, t + '.png')).astype(np.float32)
        if img.shape[2] == 3: img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.float32)], 2)
        if img[..., 3].max() <= 128: img[..., 3] = np.minimum(img[..., 3] * 2, 255)
        ys = (np.arange(h) * img.shape[0] / h).astype(int); xs = (np.arange(cw) * img.shape[1] / cw).astype(int)
        cell = img[ys][:, xs]
        cell[..., :3] = np.clip(cell[..., :3] * ART_GAIN, 0, 255)
        sheet[:, i * cw:(i + 1) * cw] = cell
    o, n = names[TREE_SHEET - 9][3], names[TREE_SHEET - 9][4]
    res[o:o + n] = forzaxpr.encode_with_mips(np.clip(sheet, 0, 255).astype(np.uint8), kind, n)
    print('trees: %d pictures on texture %d (%d x %d)' % (len(TREE_TEX), TREE_SHEET, w, h))


def read_gt4_trees(runway_dir):
    """GT4's tree faces from world.obj (materials t<TREE_TEX>): (positions (n, 3, 3) in Forza's frame, texture
    coordinates (n, 3, 2) GT4's (v down), the cell of each). Cached as world_trees.npz."""
    src, cache = os.path.join(runway_dir, 'world.obj'), os.path.join(runway_dir, 'world_trees.npz')
    if os.path.exists(cache) and (not os.path.exists(src) or os.path.getmtime(cache) >= os.path.getmtime(src)):
        z = np.load(cache)
        return z['P'], z['UV'], z['C']
    if not os.path.exists(src): return np.zeros((0, 3, 3)), np.zeros((0, 3, 2)), np.zeros(0, int)
    mats = {'t' + t: i for i, t in enumerate(TREE_TEX)}
    V, VT, P, UV, C, cur = [], [], [], [], [], None
    for l in open(src):
        if l.startswith('v '): V.append(list(map(float, l.split()[1:4])))
        elif l.startswith('vt '): VT.append(list(map(float, l.split()[1:3])))
        elif l.startswith('usemtl '): cur = mats.get(l.split()[1])
        elif l.startswith('f ') and cur is not None:
            ps = [x.split('/') for x in l.split()[1:4]]
            P.append([V[int(a) - 1] for a, b in ps]); UV.append([VT[int(b) - 1] for a, b in ps]); C.append(cur)
    P, UV, C = to_forza(np.array(P, float)), np.array(UV, float), np.array(C, int)
    UV[..., 1] = 1 - UV[..., 1]  # (the OBJ's v up)
    np.savez(cache, P=P, UV=UV, C=C)
    return P, UV, C


def trees(runway_dir, centre, inner, reach_in, reach_out, ground_at, clear=None, tops=None, seed=11):
    """The trees: GT4's where GT4 has them (each tree's faces joined by shared corners, set on our ground; none
    wider than 25 m), and TREE_CLUSTERS clusters of two crossed cards each, off the runway (TREE_BAND), not in the
    pits and paddock or the main grandstand's strip; every face both ways round. (vertices, triangles, texture
    coordinates on the sheet (u across all eight cells, v down))."""
    rng = np.random.default_rng(seed)
    V, T, UV = [], [], []

    def add(quad_p, quad_uv):  # a quad (4 corners round), both faces
        b = len(V)
        V.extend(quad_p); UV.extend(quad_uv)
        T.extend([(b, b + 1, b + 2), (b, b + 2, b + 3), (b, b + 2, b + 1), (b, b + 3, b + 2)])
    P, G, C = read_gt4_trees(runway_dir)
    if len(P):
        key = {}
        parent = list(range(len(P)))
        def find(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        for i, tri in enumerate(P):
            for q in tri:
                k = tuple(np.round(q, 1))
                if k in key: parent[find(i)] = find(key[k])
                else: key[k] = i
        groups = {}
        for i in range(len(P)): groups.setdefault(find(i), []).append(i)
        kept = 0
        for g in groups.values():
            pts = P[g].reshape(-1, 3)
            if max(np.ptp(pts[:, 0]), np.ptp(pts[:, 2])) > 25: continue
            if clear and clear(pts[:, [0, 2]].mean(0)[None])[0]: continue  # (the paved paddock)
            dy = ground_at(pts[:, [0, 2]]).min() - 0.3 - pts[:, 1].min()
            for i in g:
                b = len(V)
                V.extend(P[i] + (0, dy, 0))
                UV.extend([((C[i] + np.clip(u, 0, 1)) / 8, np.clip(v, 0, 1)) for u, v in G[i]])
                T.extend([(b, b + 1, b + 2), (b, b + 2, b + 1)])
            kept += 1
        print('trees: GT4\'s %d of %d' % (kept, len(groups)))
    n = len(centre)
    clear_of = lambda q, i, side: np.hypot(*(centre[:, [0, 2]] - q).T).min() >= (reach_in if side == 'in' else reach_out)[i] + 4.0
    planted = 0
    for _ in range(TREE_CLUSTERS):
        i0 = int(rng.integers(n)); share = i0 / n
        side = 'in' if rng.random() < 0.5 else 'out'
        d = inner[i0] if side == 'in' else -inner[i0]
        reach = (reach_in if side == 'in' else reach_out)[i0]
        off = rng.uniform(*TREE_BAND)
        if (share > 0.9 or share < 0.05) and (side == 'in' and off < 150 or side == 'out' and off < 30): continue  # (pits, paddock, grandstand)
        mid = centre[i0][[0, 2]] + d[[0, 2]] * (reach + off)
        rad = rng.uniform(6, 22)
        for _ in range(int(rng.integers(3, 10))):
            q = mid + rng.normal(0, rad / 2, 2)
            # the nearest point's side and reach: the tree stays off the runway by 4 m
            j = int(np.argmin(np.hypot(*(centre[:, [0, 2]] - q).T)))
            sd = 'in' if (q - centre[j][[0, 2]]) @ inner[j][[0, 2]] > 0 else 'out'
            if not clear_of(q, j, sd) or (clear and clear(q[None])[0]): continue
            h = rng.uniform(*TREE_H); w = h / 2
            cell = TREE_TALL[int(rng.integers(len(TREE_TALL)))]
            y0 = float(ground_at(q[None])[0]) - 0.3
            a = rng.uniform(0, np.pi)
            for ang in (a, a + np.pi / 2):
                e = np.array([np.cos(ang), np.sin(ang)]) * w / 2
                quad = [(q[0] - e[0], y0 + h, q[1] - e[1]), (q[0] + e[0], y0 + h, q[1] + e[1]), (q[0] + e[0], y0, q[1] + e[1]), (q[0] - e[0], y0, q[1] - e[1])]
                add(quad, [(cell / 8, 0), ((cell + 1) / 8, 0), ((cell + 1) / 8, 1), (cell / 8, 1)])
            planted += 1
    print('trees: %d planted in clusters' % planted)
    if tops is not None:  # through the woods: WOOD_FILL
        step, far = WOOD_FILL
        lo, hi = centre[:, [0, 2]].min(0) - far, centre[:, [0, 2]].max(0) + far
        gx, gz = np.meshgrid(np.arange(lo[0], hi[0], step), np.arange(lo[1], hi[1], step))
        q = np.stack([gx.ravel(), gz.ravel()], 1) + rng.uniform(-step * 0.4, step * 0.4, (gx.size, 2))
        c2 = centre[:, [0, 2]]
        away = np.empty(len(q))
        for a in range(0, len(q), 3000):
            d = np.hypot(q[a:a + 3000, None, 0] - c2[None, :, 0], q[a:a + 3000, None, 1] - c2[None, :, 1])
            j = d.argmin(1); dist = d[np.arange(len(j)), j]
            side_in = np.einsum('ij,ij->i', q[a:a + 3000] - c2[j], inner[j][:, [0, 2]]) > 0
            away[a:a + 3000] = dist - np.where(side_in, reach_in[j], reach_out[j])
        keep = (away > FOREST_FROM + 8) & (away < far)
        q, away = q[keep], away[keep]
        can = canopy(q, away, clear) if clear else np.zeros(len(q))
        q, away = q[can > CANOPY_H * 0.6], away[can > CANOPY_H * 0.6]
        near_grid = away < TERRAIN_REACH - 2 * TERRAIN_CELL
        top = np.where(near_grid, tops[0](q), tops[1](q))
        filled = 0
        for qq, tp in zip(q, top):
            h = rng.uniform(*TREE_H); w = h / 2
            cell = TREE_TALL[int(rng.integers(len(TREE_TALL)))]
            y0 = tp - 0.5 * h  # (its lower half in the canopy)
            a = rng.uniform(0, np.pi)
            for ang in (a, a + np.pi / 2):
                e = np.array([np.cos(ang), np.sin(ang)]) * w / 2
                quad = [(qq[0] - e[0], y0 + h, qq[1] - e[1]), (qq[0] + e[0], y0 + h, qq[1] + e[1]), (qq[0] + e[0], y0, qq[1] + e[1]), (qq[0] - e[0], y0, qq[1] - e[1])]
                add(quad, [(cell / 8, 0), ((cell + 1) / 8, 0), ((cell + 1) / 8, 1), (cell / 8, 1)])
            filled += 1
        print('trees: %d through the woods' % filled)
    return np.array(V, float), np.array(T, int), np.array(UV, float)


def read_png(path):
    """An RGBA PNG (forzaxpr.png's: 8-bit, unfiltered or filtered) as an array."""
    import zlib as _z
    d = open(path, 'rb').read()
    i, idat, w, h, ct = 8, b'', 0, 0, 6
    while i < len(d):
        n, t = struct.unpack('>I4s', d[i:i + 8]); b = d[i + 8:i + 8 + n]
        if t == b'IHDR': w, h = struct.unpack('>II', b[:8]); ct = b[9]
        if t == b'IDAT': idat += b
        i += 12 + n
    ch = 4 if ct == 6 else 3
    raw = np.frombuffer(_z.decompress(idat), np.uint8).reshape(h, 1 + w * ch)
    out = np.zeros((h, w * ch), np.int32)
    for y in range(h):  # (PNG's row filters undone)
        f, row = raw[y, 0], raw[y, 1:].astype(np.int32)
        prev = out[y - 1] if y else np.zeros(w * ch, np.int32)
        if f == 0: out[y] = row
        elif f == 2: out[y] = (row + prev) & 255
        else:
            for x in range(w * ch):
                a_ = out[y, x - ch] if x >= ch else 0
                b_ = prev[x]; c_ = prev[x - ch] if x >= ch else 0
                if f == 1: pr = a_
                elif f == 3: pr = (a_ + b_) // 2
                else:
                    pa, pb, pc = abs(b_ - c_), abs(a_ - c_), abs(a_ + b_ - 2 * c_)
                    pr = a_ if pa <= pb and pa <= pc else (b_ if pb <= pc else c_)
                out[y, x] = (row[x] + pr) & 255
    img = out.reshape(h, w, ch).astype(np.uint8)
    return img if ch == 4 else np.concatenate([img, np.full((h, w, 1), 255, np.uint8)], 2)


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


def pack_strips(jobs, Vf, pool, reach=REACH, longest=None):
    """Strips (surface, vertex indices) into donors (pool rows: [vertices, indices, mesh, sphere, buffer]),
    one surface a donor: from the west, a seed strip and the strips within `reach` m of it (or {surface: m,
    None: otherwise}), nearest first, while they fit (vertices shared by a donor's strips count once; joins cost
    2 or 3 indices); a seed too long for the largest donor left is cut to fit it, and strips longer than
    `longest` m ({surface: m, None: m}) cut first. Returns ([(mesh, sphere, buffer, surface, [strips])], strips
    left over)."""
    pool = sorted(pool, key=lambda r: -min(r[0], r[1] - 3))
    mid = lambda s: Vf[s][:, [0, 2]].mean(0)
    out = []
    by = {}
    for k, s in jobs: by.setdefault(k, []).append(s)
    for k in sorted(by, key=lambda k_: -len(by[k_])):
        q = list(by[k])
        lim = longest.get(k, longest.get(None)) if longest else None
        if lim:
            q2 = []
            for s in q:
                pv = Vf[s][:, [0, 2]]  # (its length along: a loop's box is short)
                span = max(np.ptp(pv, axis=0).max(), np.linalg.norm(np.diff(pv[::2], axis=0), axis=1).sum())
                q2 += cut(s, max(4, int(len(s) / np.ceil(span / lim)) + 2)) if span > lim else [s]
            q = q2
        reach_k = reach.get(k, reach.get(None)) if isinstance(reach, dict) else reach
        cen = [mid(s) for s in q]
        alive = [True] * len(q)
        while any(alive):
            if not pool: return out, sum(alive) + sum(len(by[k_]) for k_ in by if k_ != k and not any(o[3] == k_ for o in out))
            live = [i for i, a in enumerate(alive) if a]
            seed = min(live, key=lambda i: (cen[i][0], cen[i][1]))
            # the smallest donor that holds every strip near the seed (the biggest, if none does): a big one spent
            # on a few kerb strips left the trees hundreds of small ones
            near = [i for i in live if np.hypot(cen[i][0] - cen[seed][0], cen[i][1] - cen[seed][1]) <= reach_k]
            need_v = len(set().union(*[set(q[i]) for i in near]))
            need_i = sum(len(q[i]) + 3 for i in near)
            fit = [j for j in range(len(pool)) if pool[j][0] >= need_v and pool[j][1] >= need_i]
            nv, nidx, mesh, sp, vb = pool.pop(fit[-1] if fit else 0)
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
                if took and np.hypot(cen[i][0] - c0[0], cen[i][1] - c0[1]) > reach_k: break
                s = q[i]
                join = (2 + ((ix + 2) % 2)) if took else 0
                if len(have | set(s)) > nv or ix + join + len(s) > nidx: continue
                took.append(s); have |= set(s); ix += join + len(s); alive[i] = False
            if took: out.append((mesh, sp, vb, k, took))
    return out, 0


def outline_runs(walls, centre):
    """The walls' bottom edges joined end to end into runs (polylines), each smoothed (RAIL_SMOOTH points; GT4's
    runway outline steps through the grass like a staircase) and resampled every RAIL_STEP m; a smoothed point that
    comes nearer the track than its own is put back (never over the runway)."""
    from collections import defaultdict
    key = lambda p: (round(p[0], 2), round(p[2], 2))
    nxt, prv = {}, {}
    pts = {}
    for q in walls:
        a, b = key(q[0]), key(q[1]); pts[a] = q[0]; pts[b] = q[1]
        nxt[a] = b; prv[b] = a
    seen, runs = set(), []
    for start in list(nxt):
        if start in seen: continue
        s0 = start  # (back to the run's beginning, or once round a loop)
        while s0 in prv and prv[s0] not in seen and prv[s0] != start: s0 = prv[s0]
        run, k = [], s0
        while k is not None and k not in seen:
            seen.add(k); run.append(pts[k]); k = nxt.get(k)
        closed = k == s0
        if len(run) >= 2: runs.append((np.array(run), closed))
    c2 = centre[:, [0, 2]]
    out = []
    for run, closed in runs:
        p = run.copy()
        if len(p) > RAIL_SMOOTH:
            w = np.ones(RAIL_SMOOTH) / RAIL_SMOOTH
            pad = RAIL_SMOOTH // 2
            ext = np.vstack([p[-pad:], p, p[:pad]]) if closed else np.vstack([np.repeat(p[:1], pad, 0), p, np.repeat(p[-1:], pad, 0)])
            sm = np.stack([np.convolve(ext[:, j], w, 'valid') for j in range(3)], 1)
            d0 = np.array([np.hypot(*(c2 - q[[0, 2]]).T).min() for q in p])
            d1 = np.array([np.hypot(*(c2 - q[[0, 2]]).T).min() for q in sm])
            p = np.where((d1 < d0 - 0.3)[:, None], p, sm)
        q = np.vstack([p, p[:1]]) if closed else p
        sarc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q[:, [0, 2]], axis=0), axis=1))])
        m = max(2, int(sarc[-1] / RAIL_STEP) + 1)
        tt = np.linspace(0, sarc[-1], m)
        out.append(np.stack([np.interp(tt, sarc, q[:, j]) for j in range(3)], 1))
    return out


def lap_arc(centre):
    """Metres round the closed loop to each point, and the lap's length."""
    seg = np.linalg.norm(np.diff(np.vstack([centre, centre[:1]])[:, [0, 2]], axis=0), axis=1)
    return np.concatenate([[0], np.cumsum(seg)[:-1]]), seg.sum()


def shortcut_barriers(centre, half, rast, ground_at, cell=1.0):
    """The shortcuts' barriers (SHORTCUT_*): polylines (n x 3) every RAIL_STEP m, on the runway (or the ground).
    Every drivable spot of the runway (a `cell` m grid) takes the lap position of the track nearest it; where two
    side by side take parts of the lap whose distance round it, less their distances off the track, is SHORTCUT_SAVE
    m or more, a car could cut across there (GT4's wide run-off round the Dunlop loop), and a barrier stands on that
    seam, kept SHORTCUT_CLEAR m off the asphalt; the run-off on each side stays."""
    c = centre[:, [0, 2]]
    arc, lap = lap_arc(centre)
    lo = c.min(0) - 150
    nz, nx = (np.ceil((c.max(0) + 150 - lo) / cell).astype(int))[::-1]
    g = lo + (np.stack(np.meshgrid(np.arange(nx), np.arange(nz)), -1) + 0.5) * cell
    drive = rast.at(g) >= 0
    near = np.full((nz, nx), -1, int); clear = np.zeros((nz, nx), bool); off = np.zeros((nz, nx))
    zi, xi = np.nonzero(drive)
    for a in range(0, len(zi), 4000):
        q = g[zi[a:a + 4000], xi[a:a + 4000]]
        d = np.hypot(q[:, None, 0] - c[None, :, 0], q[:, None, 1] - c[None, :, 1])
        j = d.argmin(1)
        near[zi[a:a + 4000], xi[a:a + 4000]] = j
        off[zi[a:a + 4000], xi[a:a + 4000]] = d[np.arange(len(j)), j]
        clear[zi[a:a + 4000], xi[a:a + 4000]] = (d - half[None]).min(1) > SHORTCUT_CLEAR
    seam, hit = np.zeros((nz, nx), bool), np.zeros((nz, nx), bool)  # (a cut at all; one saving SHORTCUT_SAVE)
    for dz, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a_ = near[max(0, -dz):nz - max(0, dz), max(0, -dx):nx - max(0, dx)]
        b_ = near[max(0, dz):, max(0, dx):][:a_.shape[0], :a_.shape[1]]
        both = (a_ >= 0) & (b_ >= 0)
        la = np.abs(arc[a_] - arc[b_]); la = np.minimum(la, lap - la)
        oa = off[max(0, -dz):nz - max(0, dz), max(0, -dx):nx - max(0, dx)]
        ob = off[max(0, dz):, max(0, dx):][:a_.shape[0], :a_.shape[1]]
        seam[max(0, -dz):nz - max(0, dz), max(0, -dx):nx - max(0, dx)] |= both & (la - oa - ob > 0)
        hit[max(0, -dz):nz - max(0, dz), max(0, -dx):nx - max(0, dx)] |= both & (la - oa - ob >= SHORTCUT_SAVE)
    seam &= clear
    pts = list(map(tuple, np.argwhere(seam)))
    left, runs = set(pts), []
    while left:  # chained: from a run's end, the nearest seam cell within 2 cells, again and again
        start = left.pop(); run = [start]
        for direction in (0, 1):
            cur = run[-1] if direction == 0 else run[0]
            while True:
                nb = [(cur[0] + dz, cur[1] + dx) for dz in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2) if (cur[0] + dz, cur[1] + dx) in left]
                if not nb: break
                cur = min(nb, key=lambda p_: (p_[0] - cur[0]) ** 2 + (p_[1] - cur[1]) ** 2)
                left.discard(cur)
                for dz in (-1, 0, 1):  # (the seam is a cell or two thick: its neighbours across taken too)
                    for dx in (-1, 0, 1): left.discard((cur[0] + dz, cur[1] + dx))
                if direction == 0: run.append(cur)
                else: run.insert(0, cur)
        if len(run) * cell >= 6 and any(hit[max(0, a - 2):a + 3, max(0, b - 2):b + 3].any() for a, b in run):
            runs.append(g[tuple(np.array(run).T)])
    out = []
    for r in runs:
        if len(r) > 5: r = np.stack([np.convolve(np.pad(r[:, k], 2, mode='edge'), np.ones(5) / 5, 'valid') for k in range(2)], 1)
        sarc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(r, axis=0), axis=1))])
        tt = np.linspace(0, sarc[-1], max(2, int(sarc[-1] / RAIL_STEP) + 1))
        xz = np.stack([np.interp(tt, sarc, r[:, k]) for k in range(2)], 1)
        k_ = rast.at(xz); y = np.full(len(xz), np.nan)
        ij = np.floor((xz - rast.lo) / rast.res).astype(int)
        on = k_ >= 0
        y[on] = rast.y[ij[on, 1], ij[on, 0]]
        y = np.where(np.isfinite(y), y, ground_at(xz))
        out.append(np.stack([xz[:, 0], y, xz[:, 1]], 1))
    print('shortcuts: %d barriers, %.0f m' % (len(out), sum(np.linalg.norm(np.diff(r, axis=0), axis=1).sum() for r in out)))
    return out


def barrier_geometry(runs):
    """Armco along the shortcuts' barriers (both faces) and their walls for the collision (both faces):
    (vertices, triangles, texture coordinates, kinds, wall quads)."""
    V, T, UV, K, quads = [], [], [], [], []
    for r in runs:
        u = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(r[:, [0, 2]], axis=0), axis=1))]) / RAIL_REPEAT
        b = len(V)
        for p_, uu in zip(r, u):
            V += [p_ + (0, ARMCO_H[0], 0), p_ + (0, ARMCO_H[1], 0)]; UV += [(uu, 1), (uu, 0)]
        for i in range(len(r) - 1):
            a0, a1, c0, c1 = b + 2 * i, b + 2 * i + 2, b + 2 * i + 1, b + 2 * i + 3
            T += [(a0, a1, c1), (a0, c1, c0), (a0, c1, a1), (a0, c0, c1)]
            K += [ARMCO] * 4
            q = np.array([r[i], r[i + 1], r[i + 1] + (0, WALL_H, 0), r[i] + (0, WALL_H, 0)])
            quads += [q, q[[1, 0, 3, 2]]]
    return np.array(V, float).reshape(-1, 3), np.array(T, int).reshape(-1, 3), np.array(UV, float).reshape(-1, 2), np.array(K, int), quads


def more_kerbs(centre, left, right, rast, gt4_kerbs):
    """Kerbs at the corners (KERB_*): (vertices, triangles, texture coordinates: across 0-1, along in repeats)."""
    c = centre[:, [0, 2]]
    n = len(c)
    arc, lap = lap_arc(centre)
    t = np.roll(c, -3, 0) - np.roll(c, 3, 0); t /= np.linalg.norm(t, axis=1, keepdims=True)
    ang = np.arctan2(t[:, 1], t[:, 0])
    k = np.angle(np.exp(1j * (np.roll(ang, -3) - np.roll(ang, 3)))) / (np.roll(arc, -3) - np.roll(arc, 3) + np.where(np.roll(arc, -3) < np.roll(arc, 3), lap, 0))
    k = np.convolve(np.concatenate([k[-7:], k, k[:7]]), np.ones(15) / 15, 'valid')
    bent = np.abs(k) > KERB_TURN
    lft = np.stack([-t[:, 1], t[:, 0]], 1)
    near_gt4 = np.zeros(n, bool)
    if len(gt4_kerbs):
        for side in (left, right):
            e = side[:, [0, 2]]
            for a in range(0, n, 500):
                d = np.hypot(e[a:a + 500, None, 0] - gt4_kerbs[None, :, 0], e[a:a + 500, None, 1] - gt4_kerbs[None, :, 2])
                near_gt4[a:a + 500] |= d.min(1) < KERB_SKIP
    want = []  # (indices along the edge, the edge)
    i = 0
    while i < n:
        if not bent[i]: i += 1; continue
        j = i
        while j < n and bent[j]: j += 1
        apex = i + int(np.argmax(np.abs(k[i:j])))
        turn_left = k[apex] > 0
        inside, outside = (left, right) if turn_left else (right, left)
        # (which of the layout's edges is the inside: the one the bend's centre is on)
        if np.dot(inside[apex, [0, 2]] - c[apex], lft[apex]) * (1 if turn_left else -1) < 0: inside, outside = outside, inside
        step = np.mean(np.diff(arc[:50]))
        a_ = int(KERB_APEX / step)
        want.append(([q % n for q in range(apex - a_, apex + a_ + 1)], inside))
        want.append(([q % n for q in range(apex + int(KERB_EXIT[0] / step), apex + int(KERB_EXIT[1] / step) + 1)], outside))
        i = j
    V, T, UV = [], [], []
    made = 0
    for idx, edge in want:
        run = []
        for q in idx + [None]:
            if q is not None and not near_gt4[q]: run.append(q); continue
            if len(run) >= 4:
                b = len(V)
                for m_, q_ in enumerate(run):
                    e = edge[q_]
                    o = e[[0, 2]] - c[q_]; o /= max(np.linalg.norm(o), 1e-9)
                    for f, u in ((-KERB_IN, 0.0), (KERB_W - KERB_IN, 1.0)):
                        xz = e[[0, 2]] + o * f
                        ij = np.floor((xz - rast.lo) / rast.res).astype(int)
                        y = rast.y[ij[1], ij[0]] if 0 <= ij[0] < rast.shape[1] and 0 <= ij[1] < rast.shape[0] else np.nan
                        V.append((xz[0], (y if np.isfinite(y) else e[1]) + KERB_LIFT, xz[1])); UV.append((u, (arc[q_] - arc[run[0]]) % lap / 4.0))
                for m_ in range(len(run) - 1):
                    a0, a1, c0, c1 = b + 2 * m_, b + 2 * m_ + 2, b + 2 * m_ + 1, b + 2 * m_ + 3
                    T += [(a0, a1, c1), (a0, c1, c0)]
                made += 1
            run = []
    V, T = np.array(V, float).reshape(-1, 3), np.array(T, int).reshape(-1, 3)
    if len(T):  # wound face up (the game's way: as the runway's)
        nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        flip = nrm[:, 1] > 0
        T[flip] = T[flip][:, [0, 2, 1]]
    print('kerbs: %d added at the corners, %d triangles' % (made, len(T)))
    return V, T, np.array(UV, float).reshape(-1, 2)


def dressing(walls, centre=None):
    """Armco and catch fence along the walls (on outline_runs' smoothed line): (vertices, triangles, texture
    coordinates, kinds per triangle), each quad both faces."""
    V, T, UV, K = [], [], [], []
    if centre is not None:  # (a run's quads share their corners: half the vertices, long strips)
        runs = []
        c2 = centre[:, [0, 2]]
        split = []
        for r in outline_runs(walls, centre):  # only where the outline runs near the track: GT4's runway's grass runs up
            jn = [int(np.argmin(np.hypot(*(c2 - q[[0, 2]]).T))) for q in r]  # the embankments, its fence
            near = np.array([np.hypot(*(c2[j] - q[[0, 2]])) <= FENCE_NEAR and abs(q[1] - centre[j, 1]) <= FENCE_RISE for q, j in zip(r, jn)])
            cur = []                                                                     # floated over the hills
            for q, ok in zip(r, near):
                if ok: cur.append(q)
                elif len(cur) >= 2: split.append(np.array(cur)); cur = []
                else: cur = []
            if len(cur) >= 2: split.append(np.array(cur))
        for r in split:  # (pieces of at most 200 m, each its texture from 0: a loop's two ends
            k_ = max(1, int(200 / RAIL_STEP))   # meet, a donor holding both ran past s16's coordinates)
            runs += [r[i:i + k_ + 1] for i in range(0, len(r) - 1, k_)]
        for r in runs:
            u = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(r[:, [0, 2]], axis=0), axis=1))]) / RAIL_REPEAT
            for kind, (y0, y1) in ((ARMCO, ARMCO_H), (FENCE, FENCE_H)):
                b = len(V)
                for p_, uu in zip(r, u):
                    V += [p_ + (0, y0, 0), p_ + (0, y1, 0)]; UV += [(uu, 1), (uu, 0)]
                for i in range(len(r) - 1):
                    a0, a1, c0, c1 = b + 2 * i, b + 2 * i + 2, b + 2 * i + 1, b + 2 * i + 3
                    T += [(a0, a1, c1), (a0, c1, c0), (a0, c1, a1), (a0, c0, c1)]
                    K += [kind] * 4
        return np.array(V, float), np.array(T, int), np.array(UV, float), np.array(K, int)
    segs = [(q[0], q[1]) for q in walls]
    for p0, p1 in segs:
        ln = float(np.linalg.norm((p1 - p0)[[0, 2]]))
        for kind, (y0, y1) in ((ARMCO, ARMCO_H), (FENCE, FENCE_H)):
            b = len(V)
            V += [p0 + (0, y0, 0), p1 + (0, y0, 0), p1 + (0, y1, 0), p0 + (0, y1, 0)]
            u1 = ln / RAIL_REPEAT
            UV += [(0, 1), (u1, 1), (u1, 0), (0, 0)]
            T += [(b, b + 1, b + 2), (b, b + 2, b + 3), (b, b + 2, b + 1), (b, b + 3, b + 2)]
            K += [kind] * 4
    return np.array(V, float), np.array(T, int), np.array(UV, float), np.array(K, int)


def outside_walls(Vf, T, F=None, h=WALL_H):
    """Quads standing on the surface's outline, each facing the surface (the game's walls have one face, toward
    the drivable side: shipyardcircuit's lesson): edges with one triangle whose other side is bare ground (the
    runway rastered at 0.5 m, gaps under a metre closed). GT4's runway repeats vertices along its seams (where
    tarmac meets kerb or grass) and has T-junctions: by the edges alone, 1,752 walls stood inside the track."""
    from collections import defaultdict
    owner = defaultdict(list)
    for a, b, c in T:
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)): owner[(min(u, v), max(u, v))].append(w)
    cover = None
    if F is not None:
        r = Raster(Vf, F, res=0.5)
        k = r.k >= 0
        for _ in range(2):  # closed: grown a cell, twice, then shrunk as much
            k = k | np.roll(k, 1, 0) | np.roll(k, -1, 0) | np.roll(k, 1, 1) | np.roll(k, -1, 1)
        for _ in range(2):
            k = k & np.roll(k, 1, 0) & np.roll(k, -1, 0) & np.roll(k, 1, 1) & np.roll(k, -1, 1)
        cover = lambda xz: k[tuple(np.clip(np.floor((xz - r.lo) / 0.5).astype(int), 0, [k.shape[1] - 1, k.shape[0] - 1])[..., ::-1].T)]
    quads, inner_seams = [], 0
    for (u, v), ws in owner.items():
        if len(ws) != 1: continue
        p, q, inside = Vf[u], Vf[v], Vf[ws[0]]
        if cover is not None:
            e = (q - p)[[0, 2]]; ln = np.linalg.norm(e)
            if ln < 1e-6: continue
            nrm = np.array([-e[1], e[0]]) / ln
            if nrm @ (inside - p)[[0, 2]] > 0: nrm = -nrm  # (away from its triangle)
            beyond = np.array([p[[0, 2]] + (q - p)[[0, 2]] * f + nrm * dd for f in (0.25, 0.5, 0.75) for dd in (0.6, 1.2)])
            if cover(beyond).mean() > 0.5: inner_seams += 1; continue
        quad = np.array([p, q, q + (0, h, 0), p + (0, h, 0)])
        nrm = np.cross(quad[1] - quad[0], quad[2] - quad[0])
        if np.dot(nrm, inside - p) < 0: quad = quad[[1, 0, 3, 2]]
        quads.append(quad)
    if cover is not None: print('walls: %d on the outline, %d edges with ground beyond left open (seams, cracks)' % (len(quads), inner_seams))
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
LOGO = 47       # ico_tracklogo_sm and _lg (15 a row): the disc uses 0-46; the small strip's 47-59 are unused dark copies
LOGO_SM, LOGO_LG = (108, 60, 15), (210, 117, 15)
LOAD_IMAGE = None   # media\FrontEnd\Loading_Track_bkgd: loading_screen makes Fuji's (Road Atlanta's frame, Fuji's map,
                    # photo and logo), but the game showed "a problem with the disc" at the race's load for any name the
                    # disc lacks (Load_Fuji.xpr, Load_FujiSpeedway.xpr), never opening it, and the folder isn't listed;
                    # with no Image the loading screen has no picture and the race loads
LOAD_PHOTO = 'fuji_load_photo.png'   # a bumper-camera frame of Fuji's pit straight (in run/gt4_fuji)


def logo_tile(d, index, logo, tile):
    """The logo strip d with tile `index` Fuji's logo (RGBA, scaled to fit with a margin) over the strip's own
    ground (the small strip's tiles stand on a grey of alpha 102: its tile 46's corner; the large one's clear)."""
    import addseries
    hdr, w, h, pitch = addseries.linear(d)
    tw, th, per = tile
    px = np.frombuffer(d[hdr:hdr + pitch * h], np.uint8).reshape(h, pitch // 4, 4)[:, :, [2, 1, 0, 3]]
    x46, y46 = 46 % per * tw, 46 // per * th
    ground = px[y46 + 1, x46 + 1].astype(float)
    s = min((tw - 8) / logo.shape[1], (th - 6) / logo.shape[0])
    lw, lh = int(logo.shape[1] * s), int(logo.shape[0] * s)
    ys = np.minimum((np.arange(lh * 4) / 4 / s).astype(int), logo.shape[0] - 1)
    xs = np.minimum((np.arange(lw * 4) / 4 / s).astype(int), logo.shape[1] - 1)
    big = logo[ys][:, xs].astype(float)
    big[..., :3] *= big[..., 3:] / 255  # (premultiplied, then averaged 4 x 4 down)
    small = big.reshape(lh, 4, lw, 4, 4).mean((1, 3))
    img = np.tile(ground, (th, tw, 1))
    y0, x0 = (th - lh) // 2, (tw - lw) // 2
    a = small[..., 3:] / 255
    img[y0:y0 + lh, x0:x0 + lw, :3] = small[..., :3] + img[y0:y0 + lh, x0:x0 + lw, :3] * (1 - a)
    img[y0:y0 + lh, x0:x0 + lw, 3:] = small[..., 3:] + img[y0:y0 + lh, x0:x0 + lw, 3:] * (1 - a)
    return addseries.put_tile(d, index, np.clip(img + 0.5, 0, 255).astype(np.uint8), tile)


def loading_screen(disc, centre, art_dir):
    """Fuji's loading screen (1024 x 512 DXT5, the picture in its top-left 640 x 480 as the disc's): Road
    Atlanta's, its map taken out (each pixel the lighter of Road Atlanta's and Road Atlanta Short's: their maps
    differ), Fuji's map in its place, Fuji's photo in its picture's disc (the pixels the two screens' pictures
    differ in, a row's from its first past x 250) and Fuji's logo over it."""
    import addcar
    import forzaxpr
    import shipyardloop as sl
    folder = addcar.disc_file(disc, 'media', 'FrontEnd', 'Loading_Track_bkgd')
    raw = {f.lower(): open(os.path.join(folder, f), 'rb').read() for f in os.listdir(folder) if f.lower() in ('load_rdatlanta.xpr', 'load_rdatlantashort.xpr')}
    template = raw['load_rdatlanta.xpr']
    a, b = (np.asarray(forzaxpr.dxt(raw[k][2048:2048 + 1024 * 512], 1024, 512, 5)).astype(float) for k in ('load_rdatlanta.xpr', 'load_rdatlantashort.xpr'))
    out = a.copy()
    differ = np.abs(a - b)[..., :3].sum(-1) > 30
    # the map's panel, its map gone: each of the maps' pixels (where the two differ, grown 3 pixels) taken from
    # along the panel's diagonal stripes, from the nearest pixel neither map covers
    panel = np.zeros(differ.shape, bool); panel[60:420, 20:260] = True
    gone = differ & panel
    for _ in range(3): gone = gone | np.roll(gone, 1, 0) | np.roll(gone, -1, 0) | np.roll(gone, 1, 1) | np.roll(gone, -1, 1)
    gone &= panel
    clean = panel & ~gone
    best = None
    for deg in range(0, 180):
        v = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))]) * 12
        dy, dx = int(round(v[1])), int(round(v[0]))
        sh = np.roll(np.roll(a, -dy, 0), -dx, 1)
        ok = clean & np.roll(np.roll(clean, -dy, 0), -dx, 1)
        e = np.abs(a - sh)[..., :3].sum(-1)[ok].mean()
        if best is None or e < best[0]: best = (e, np.radians(deg))
    u = np.array([np.cos(best[1]), np.sin(best[1])])
    for y, x in zip(*np.nonzero(gone)):
        for k in range(1, 300):
            got = False
            for sg in (1, -1):
                xx, yy = int(round(x + sg * k * u[0])), int(round(y + sg * k * u[1]))
                if 0 <= yy < 512 and 0 <= xx < 1024 and clean[yy, xx]: out[y, x] = a[yy, xx]; got = True; break
            if got: break
    # the picture's disc: per row from its left edge (the 10th-lowest differing x past 250, smoothed) to 640
    left = np.full(512, 9999.0)
    for y in range(63, 417):
        xs = np.nonzero(differ[y, 250:640])[0] + 250
        if len(xs) > 20: left[y] = np.sort(xs)[10]
    rows = np.arange(63, 417)
    k_ = left[rows] < 9999
    left[rows] = np.interp(rows, rows[k_], np.convolve(np.pad(left[rows][k_], 7, mode='edge'), np.ones(15) / 15, 'valid'))
    photo = read_png(os.path.join(art_dir, LOAD_PHOTO)).astype(float)
    ph = 417 - 63
    s = ph / photo.shape[0]
    pw = int(photo.shape[1] * s)
    ys = np.minimum((np.arange(ph) / s).astype(int), photo.shape[0] - 1); xs = np.minimum((np.arange(pw) / s).astype(int), photo.shape[1] - 1)
    big = photo[ys][:, xs]
    x0 = 640 - pw
    for y in rows:
        l_ = int(left[y])
        for x in range(max(l_, x0), 640):
            t = min(1.0, (x - l_ + 1) / 4.0)  # (a 4-pixel blend into Road Atlanta's ring)
            out[y, x, :3] = big[y - 63, x - x0, :3] * t + out[y, x, :3] * (1 - t)
    # the map: north up, as the track select screen's, in the panel
    m = sl.trackmap(centre, size=256).astype(float)
    my, mx = 240 - 128, 150 - 128
    al = m[..., 3:] / 255
    out[my:my + 256, mx:mx + 256, :3] = m[..., :3] * al + out[my:my + 256, mx:mx + 256, :3] * (1 - al)
    # the logo over the picture's top
    logo = read_png(os.path.join(art_dir, 'fuji_logo.png')).astype(float)
    s = 190 / logo.shape[1]
    lw, lh = int(logo.shape[1] * s), int(logo.shape[0] * s)
    ys = np.minimum((np.arange(lh) / s).astype(int), logo.shape[0] - 1); xs = np.minimum((np.arange(lw) / s).astype(int), logo.shape[1] - 1)
    lg = logo[ys][:, xs]
    ly, lx = 80, 420
    al = lg[..., 3:] / 255
    out[ly:ly + lh, lx:lx + lw, :3] = lg[..., :3] * al + out[ly:ly + lh, lx:lx + lw, :3] * (1 - al)
    out[..., 3] = 255
    img = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    return forzaxpr.write_dxt5(template, img), img
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
                 ('length', int(round(length))), ('minimap', MAP_TILE), ('NumberOfTurns', 16),
                 ('icon', LOGO)) + ((('Image', LOAD_IMAGE),) if LOAD_IMAGE else ()):
        e = attr(e, k, v)
    e = re.sub(r'\s(p2pordinal|start|end)="[^"]*"', '', e)
    if not LOAD_IMAGE: e = re.sub(r'\sImage="[^"]*"', '', e)  # (no picture on the loading screen: the game skips it)
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
    art_dir = build_dir
    logo = read_png(os.path.join(art_dir, 'fuji_logo.png')).astype(np.uint8)
    for name, tile in (('ico_tracklogo_sm', LOGO_SM), ('ico_tracklogo_lg', LOGO_LG)):
        key = next(k for k in xpr.files if k.lower() == 'frontend' + B + name + '.xpr')
        xpr.files[key] = logo_tile(xpr.files[key], LOGO, logo, tile)
    # its AI files: what the game counts laps and progress by (and its AI drivers race by), along the
    # track's edges; the audio spline one record per waypoint (written below)
    import aitrack
    half = np.linalg.norm(E['inner'] - E['outer'], axis=1) / 2
    wps, nseg, sounds = aitrack.install(mega, TAG, (E['inner'] + E['outer']) / 2, half, line=racing_line(build_dir))
    print('AI files: %d waypoints, %d segments; sounds kept %s' % (len(wps), nseg, sounds))
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    if LOAD_IMAGE:
        screen, _ = loading_screen(disc, centre, build_dir)
        ld = os.path.join(mods, 'media', 'FrontEnd', 'Loading_Track_bkgd')
        os.makedirs(ld, exist_ok=True)
        open(os.path.join(ld, LOAD_IMAGE), 'wb').write(screen)
    d = os.path.join(mods, 'media', 'tracks', TAG)
    os.makedirs(d, exist_ok=True)
    col = open(os.path.join(build_dir, 'QuickPreview1.col'), 'rb').read()
    open(os.path.join(d, 'QuickPreview1.col'), 'wb').write(col)
    ra = addcar.disc_file(disc, 'media', 'tracks', DONOR_TRACK)
    for f in os.listdir(ra):
        if f.lower() in ('tracklightmap.dat', 'fog.bin', 'flythrough.bik'):
            open(os.path.join(d, f), 'wb').write(open(os.path.join(ra, f), 'rb').read())
        if f.lower() == 'audiospline.bin':  # Road Atlanta's sounds, a record per Fuji waypoint (the nearest's)
            ref = mega.files['ai' + B + 'drivatarv2' + B + DONOR_TRACK.lower() + 'geometry.bin']
            open(os.path.join(d, 'AudioSpline.bin'), 'wb').write(aitrack.audio_spline(wps, ref, open(os.path.join(ra, f), 'rb').read()))
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
