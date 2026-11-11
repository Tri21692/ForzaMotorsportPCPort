"""Where a car can go on an installed custom track (tools/shipyardcircuit.py's), and what its edges
are: the collision's ground and walls laid on a grid, filled from the loop's road outward.

  invisible walls  walls at the reachable ground's edge with nothing drawn standing there (a fence,
                   wall, rail, building, kerb a car could read as the edge)
  open edges       reachable ground ending with no wall: the car drives off into the void
  edge cameras     points along the reachable edge, looking out, for blender_render.py's cams:

Reads what the runtime loads (the mods folder's track\\<tag>\\): the collision cache, the scenery and
its visibility (what is drawn), the loop's splines. Writes <out>\\audit.png (top down, north up:
reachable green, walls white where drawn, red where invisible, open edges yellow, the loop cyan),
<out>\\audit.txt and <out>\\edge_cams.json.

  python tools/collision_audit.py <mods folder> <out folder> [tag]
"""
import collections
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_export as E
import coledit
import forzaxpr
import shipyardloop as L
import xb2

CELL = 0.5     # m a grid cell
MARGIN = 60.0  # m round the loop the grid reaches


def grid_of(lo, hi):
    W, H = int((hi[0] - lo[0]) / CELL) + 1, int((hi[1] - lo[1]) / CELL) + 1
    return W, H


def raster_tri(t, lo, W, H):
    """The grid cells (rows, cols) a triangle's footprint (x, z) covers, and its height at each."""
    xs, zs = t[:, 0], t[:, 2]
    c0, c1 = max(int((xs.min() - lo[0]) / CELL), 0), min(int((xs.max() - lo[0]) / CELL) + 1, W - 1)
    r0, r1 = max(int((zs.min() - lo[1]) / CELL), 0), min(int((zs.max() - lo[1]) / CELL) + 1, H - 1)
    if c1 < c0 or r1 < r0: return None
    rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]
    px, pz = lo[0] + (cc + 0.5) * CELL, lo[1] + (rr + 0.5) * CELL
    a, b, c = t[0], t[1], t[2]
    det = (b[0] - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (b[2] - a[2])
    if abs(det) < 1e-9: return None
    u = ((px - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (pz - a[2])) / det
    v = ((b[0] - a[0]) * (pz - a[2]) - (px - a[0]) * (b[2] - a[2])) / det
    m = (u >= -0.02) & (v >= -0.02) & (u + v <= 1.02)
    return rr[m], cc[m], a[1] + u[m] * (b[1] - a[1]) + v[m] * (c[1] - a[1])


def raster_seg(a, b, lo, W, H):
    """The cells along a footprint from a to b (x, z)."""
    n = max(2, int(np.hypot(*(np.subtract(b, a))) / (CELL / 2)) + 1)
    p = np.linspace(a, b, n)
    c = ((p[:, 0] - lo[0]) / CELL).astype(int); r = ((p[:, 1] - lo[1]) / CELL).astype(int)
    k = (c >= 0) & (c < W) & (r >= 0) & (r < H)
    return r[k], c[k]


def footprint(t):
    """An upright triangle's footprint: its two furthest corners in (x, z)."""
    i, j = max(((0, 1), (1, 2), (0, 2)), key=lambda e: np.hypot(*(t[e[0]][[0, 2]] - t[e[1]][[0, 2]])))
    return t[i][[0, 2]], t[j][[0, 2]]


def clusters(mask):
    """Connected groups of True cells (8-way): [list of (r, c)]."""
    seen = np.zeros_like(mask)
    out = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]: continue
        q, grp = collections.deque([(r0, c0)]), []
        seen[r0, c0] = True
        while q:
            r, c = q.popleft(); grp.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1] and mask[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True; q.append((rr, cc))
        out.append(grp)
    return out


def collision_grids(col, ring, lo, W, H, local=False):
    """The collision laid on the grid: ground within 3 m of the loop's height near it (not an
    overpass's), and walls high enough to stop a car and not overhead. (ground, wall, near_y).
    local: a course with no overpass whose ground runs far from its loop and metres above or under
    it (Fuji's run-off: by the loop's height 1 km of its edge's rails read as buried, and the walls
    sealing its open edges stood at the loop's height, not the ground's): all its ground, and near_y
    the ground's own height there (the nearest ground within 4 m, else the loop's)."""
    ring_y = lambda p: ring[int(np.argmin(np.hypot(ring[:, 0] - p[0], ring[:, 2] - p[2]))), 1]
    near_y = ring_y
    hi = (lo[0] + W * CELL, lo[1] + H * CELL)
    ground = np.zeros((H, W), bool)
    wall = np.zeros((H, W), bool)
    tris_ = list(col.triangles())
    if local:
        Yg = np.full((H, W), np.nan)
        for s, pts, n, w in tris_:
            q = np.array(pts, float)
            if abs(n[1]) <= 0.7 or q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 2].max() < lo[1] or q[:, 2].min() > hi[1]: continue
            g = raster_tri(q, lo, W, H)
            if g: Yg[g[0], g[1]] = q[:, 1].mean()
        for _ in range(8):  # spread 4 m past the ground's edge
            holes = np.isnan(Yg)
            if not holes.any(): break
            best = np.full((H, W), np.nan)
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                r_ = np.roll(np.roll(Yg, dr, 0), dc, 1)
                best = np.where(np.isnan(best), r_, best)
            Yg = np.where(holes, best, Yg)
        def near_y(p):
            c, r = int((p[0] - lo[0]) / CELL), int((p[2] - lo[1]) / CELL)
            if 0 <= r < H and 0 <= c < W and not np.isnan(Yg[r, c]): return float(Yg[r, c])
            return ring_y(p)
    for s, pts, n, w in tris_:
        q = np.array(pts, float)
        if q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 2].max() < lo[1] or q[:, 2].min() > hi[1]: continue
        y0 = near_y(q.mean(0))
        if abs(n[1]) > 0.7:
            if abs(q[:, 1].mean() - y0) > 3 and not local: continue
            g = raster_tri(q, lo, W, H)
            if g: ground[g[0], g[1]] = True
        elif q[:, 1].min() < y0 + 1.2 and q[:, 1].max() > y0 + 0.3:  # high enough to stop a car, not overhead
            r, c = raster_seg(*footprint(q), lo, W, H)
            wall[r, c] = True
    return ground, wall, near_y


def grow(m, k):
    """m and the cells within k of it."""
    g = m.copy()
    for dr in range(-k, k + 1):
        for dc in range(-k, k + 1):
            g |= np.roll(np.roll(m, dr, 0), dc, 1)
    return g


def nb(m):
    return np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)


def flood(ground, wall, ring, lo):
    """The ground a car reaches from the loop's road, keeping a car's half width (a metre) off any
    wall (it squeezed through gaps between walls' ends, and behind the course's walls through
    openings)."""
    H, W = ground.shape
    near_wall = grow(wall, 2)
    reach = np.zeros((H, W), bool)
    q = collections.deque()
    for p in ring:
        c, r = int((p[0] - lo[0]) / CELL), int((p[2] - lo[1]) / CELL)
        if 0 <= r < H and 0 <= c < W and ground[r, c] and not near_wall[r, c] and not reach[r, c]: reach[r, c] = True; q.append((r, c))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and not reach[rr, cc] and ground[rr, cc] and not near_wall[rr, cc]:
                reach[rr, cc] = True; q.append((rr, cc))
    return reach


def behind_wall(pts, ring, wall, lo):
    """Whether most of the cells' points (x, z) have a wall between them and the loop's nearest
    point (the ground past the course's own walls, reached through a gap at some end of them)."""
    H, W = wall.shape
    sample = pts[::max(1, len(pts) // 20)]
    behind = 0
    for p in sample:
        k = int(np.argmin(np.hypot(ring[:, 0] - p[0], ring[:, 2] - p[1])))
        d = np.hypot(ring[k, 0] - p[0], ring[k, 2] - p[1])
        if d < 2.5: continue
        r_, c_ = raster_seg(ring[k, [0, 2]], p - (p - ring[k, [0, 2]]) / d * 1.5, lo, W, H)
        behind += bool(wall[r_, c_].any())
    return behind > len(sample) / 2


def seal_open_edges(col, ring, least=2, near=25.0, margin=MARGIN, one_face=False, lines=None, local=False):
    """Walls (both faces, from a metre under the road to 3 m over it) along every edge of the ground a
    car reaches from the loop where it ends with no wall (the void past it): where two walls' ends
    jogged 4 m apart past the hairpin a car went through and fell. Not those behind a wall (the
    course's own ground past its walls), unless some of it is within `near` m of the loop (by Turn
    2's exit short walls between the loop and an edge had it counted behind them, and the edge was
    left open). Returns the metres of wall added."""
    ring = np.asarray(ring, float)
    lo, hi = ring[:, [0, 2]].min(0) - margin, ring[:, [0, 2]].max(0) + margin
    W, H = grid_of(lo, hi)
    ground, wall, near_y = collision_grids(col, ring, lo, W, H, local)
    reach = flood(ground, wall, ring, lo)
    open_edge = reach & nb(~ground)
    xz = lambda r, c: (lo[0] + (c + 0.5) * CELL, lo[1] + (r + 0.5) * CELL)
    segs = {}  # (axis, line, row or column) -> cell positions along it: merged into runs below
    for grp in clusters(open_edge):
        pts = np.array([xz(r, c) for r, c in grp])
        close = min(np.hypot(ring[:, 0] - p[0], ring[:, 2] - p[1]).min() for p in pts[::max(1, len(pts) // 50)]) < near
        if len(grp) < least or (not close and behind_wall(pts, ring, wall, lo)): continue
        for r, c in grp:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < H and 0 <= cc < W) or ground[rr, cc]: continue
                if dr: segs.setdefault(('z', r + (dr > 0), dr), []).append(c)   # a side at z = lo + line * CELL
                else: segs.setdefault(('x', c + (dc > 0), dc), []).append(r)    # a side at x = lo + line * CELL
    added = 0.0
    for (axis, line, out), at in segs.items():  # (out: which way the void lies, +1 or -1 along the axis)
        at = sorted(set(at))
        runs, start = [], at[0]
        for a, b in zip(at, at[1:] + [None]):
            if b != a + 1: runs.append((start, a + 1)); start = b
        for a, b in runs:
            if axis == 'z': p0, p1 = (lo[0] + a * CELL, lo[1] + line * CELL), (lo[0] + b * CELL, lo[1] + line * CELL)
            else: p0, p1 = (lo[0] + line * CELL, lo[1] + a * CELL), (lo[0] + line * CELL, lo[1] + b * CELL)
            y0, y1 = near_y((p0[0], 0, p0[1])), near_y((p1[0], 0, p1[1]))
            if lines is not None:  # (the walls' foot lines, each with the ground on its left as it runs: they join end to
                # end round the edge, for drawing something along them, fujitrack's armco)
                g = np.array([-out, 0.0] if axis == 'x' else [0.0, -out])
                d = np.array(p1) - np.array(p0)
                a3, b3 = np.array([p0[0], y0, p0[1]]), np.array([p1[0], y1, p1[1]])
                lines.append((a3, b3) if d[0] * g[1] - d[1] * g[0] > 0 else (b3, a3))
            q = [(p0[0], y0 - 1, p0[1]), (p1[0], y1 - 1, p1[1]), (p1[0], y1 + 3, p1[1]), (p0[0], y0 + 3, p0[1])]
            tris = [[q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]]
            if one_face:  # (one face, toward the ground the car is on: the game's walls have one; with both, cars were
                # pushed out through them, shipyardcircuit's lesson)
                t0 = np.array(tris[0], float)
                n = np.cross(t0[1] - t0[0], t0[2] - t0[0])
                toward = np.array([-out, 0, 0] if axis == 'x' else [0, 0, -out], float)
                tris = tris[:2] if n @ toward > 0 else tris[2:]
            for tri in tris:
                col.add(0x900, tri)
            added += (b - a) * CELL
    return added


def track_files(mods, tag):
    """(scenery .res bytes, collision, visibility path) of an installed custom track, found by kind (the Pacific
    Shipyards Circuit's on vancouver.res and media\\tracks\\VancouverReverse, Fuji's on RoadAtlanta's)."""
    t = os.path.join(mods, 'track', tag)
    p4 = os.path.join(t, 'hdd', 'Partition4')
    res = open(os.path.join(p4, next(f for f in os.listdir(p4) if f.lower().endswith('.res'))), 'rb').read()
    col = open(os.path.join(p4, tag + '.col'), 'rb').read()
    pvs = next(os.path.join(r, f) for r, _, fs in os.walk(os.path.join(t, 'media', 'tracks')) for f in fs if f == 'QuickPreview1.pvs')
    return res, col, pvs


def edge_splines(res, names):
    """The six edge splines (road, drivable, curbing; inner and outer), by their buffers' names (Fuji's are as long
    as Road Atlanta's), else at shipyardloop.SPLINES (the Pacific Shipyards Circuit's)."""
    out = []
    for nm in ('roadinner', 'roadouter', 'drivableinner', 'drivableouter', 'curbinginner', 'curbingouter'):
        r = next((r for r in names if r[0] == 'vbuff_quickpreview_splines_%s_vb0' % nm), None)
        if r is None: return L.read_splines(bytearray(res))
        npt = (r[4] + 4) // 16  # (fujitrack: 12 bytes a point; the buffer is sized 16 a point less 4)
        out.append(np.frombuffer(res, '<f4', count=3 * npt, offset=r[3]).reshape(-1, 3).astype(float))
    return out


def audit(mods, out, tag='VancouverLoop'):
    res, col_bytes, pvs_path = track_files(mods, tag)
    names, _ = xb2.resources(res)
    L.MODEL = next(r[3] for r in names if r[0] == 'model_quickpreview')  # (blender_export's mesh_geometry reads it)
    col = coledit.Col(col_bytes)
    _, cells, _ = L.parse_pvs(open(pvs_path, 'rb').read())
    sp = edge_splines(res, names)
    if len(sp[4]) == len(sp[5]): ring = (sp[4] + sp[5]) / 2
    else:  # (Fuji's edges have their own counts: each inner point with the outer nearest it)
        j = np.argmin(np.hypot(sp[4][:, None, 0] - sp[5][None, :, 0], sp[4][:, None, 2] - sp[5][None, :, 2]), axis=1)
        ring = (sp[4] + sp[5][j]) / 2
    margin = MARGIN if len(sp[4]) == len(sp[5]) else 160.0  # (Fuji: paved run-off and grass 100 m and more off its line)
    lo, hi = ring[:, [0, 2]].min(0) - margin, ring[:, [0, 2]].max(0) + margin
    W, H = grid_of(lo, hi)
    ground, wall, near_y = collision_grids(col, ring, lo, W, H, local=len(sp[4]) != len(sp[5]))
    # what is drawn standing: any upright face from a kerb's height to a car's roof
    seen = np.zeros((H, W), bool)
    off = np.full((H, W), 1e9)  # an upright face not counted: its foot over the collision's ground there, m
    drawn = sorted({struct.unpack_from('<H', e)[0] for c in cells for e in c[0]})
    for m in drawn:
        g = E.mesh_geometry(res, names, m)
        if g is None: continue
        p, uv, tris, t0 = g
        if p[:, 0].max() < lo[0] or p[:, 0].min() > hi[0] or p[:, 2].max() < lo[1] or p[:, 2].min() > hi[1]: continue
        for k in tris:
            q = p[k]
            nrm = np.cross(q[1] - q[0], q[2] - q[0])
            if np.linalg.norm(nrm) < 1e-9 or abs(nrm[1]) > 0.7 * np.linalg.norm(nrm): continue
            y0 = near_y(q.mean(0))
            r, c = raster_seg(*footprint(q), lo, W, H)
            if q[:, 1].min() < y0 + 1.5 and q[:, 1].max() > y0 + 0.1:
                seen[r, c] = True
            else:  # (kept for the report: an upright face there, but under the ground or over a car's roof)
                off[r, c] = np.where(np.abs(off[r, c]) < abs(q[:, 1].min() - y0), off[r, c], q[:, 1].min() - y0)
    # a metre's slack round what is drawn (a wall a little behind a fence is behind it)
    s2 = seen.copy()
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            s2 |= np.roll(np.roll(seen, dr, 0), dc, 1)
    # filled from the loop's road: ground, a car's half width off any wall
    reach = flood(ground, wall, ring, lo)
    edge_wall = wall & grow(reach, 3)
    invisible = edge_wall & ~s2
    open_edge = reach & nb(~ground)
    xz = lambda r, c: (lo[0] + (c + 0.5) * CELL, lo[1] + (r + 0.5) * CELL)
    report, behind_cells = [], []
    for what, mask, least in (('invisible wall', invisible, 6), ('open edge', open_edge, 4)):
        for grp in clusters(mask):
            if len(grp) < least: continue
            pts = np.array([xz(r, c) for r, c in grp])
            i = int(np.argmin(np.hypot(ring[:, 0] - pts[:, 0].mean(), ring[:, 2] - pts[:, 1].mean())))
            kind = what + (' (behind a wall)' if behind_wall(pts, ring, wall, lo) else '')
            if 'behind' in kind: behind_cells += grp
            report.append((kind, len(grp) * CELL, pts.mean(0), pts.min(0), pts.max(0), i))
    report.sort(key=lambda e: -e[1])
    with open(os.path.join(out, 'audit.txt'), 'w') as f:
        f.write('reachable %.0f m2; walls at its edge %.0f m, %.0f m of them invisible; open edges %.0f m\n' % (
            reach.sum() * CELL * CELL, edge_wall.sum() * CELL, invisible.sum() * CELL, open_edge.sum() * CELL))
        for what, length, c, a, b, i in report:
            f.write('%-30s %5.0f m  at (%.0f, %.0f)  x %.0f..%.0f z %.0f..%.0f  loop point %d\n' % (what, length, c[0], c[1], a[0], b[0], a[1], b[1], i))
    # the map: north (+z) up, east (+x) right as the game shows it (its x mirrored)
    img = np.zeros((H, W, 4), np.uint8); img[..., 3] = 255
    img[ground] = (40, 40, 40, 255)
    img[reach] = (40, 110, 40, 255)
    img[wall] = (200, 200, 200, 255)
    img[invisible] = (255, 30, 30, 255)
    img[open_edge] = (255, 220, 0, 255)
    for r, c in behind_cells: img[r, c] = (90, 80, 30, 255)  # behind a wall: muted
    for p in ring:
        c, r = int((p[0] - lo[0]) / CELL), int((p[2] - lo[1]) / CELL)
        img[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = (0, 220, 255, 255)
    forzaxpr.png(os.path.join(out, 'audit.png'), np.ascontiguousarray(img[::-1, ::-1]))
    np.savez_compressed(os.path.join(out, 'audit.npz'), img=img, lo=lo, off=off, invisible=invisible, seen=seen)  # for close-ups (zoom())
    # cameras along the reachable edge, every 20 m or so of it, 1.6 m up, looking out
    edge = reach & nb(~reach)
    pts = np.array([xz(r, c) for r, c in zip(*np.nonzero(edge))])
    cams, taken = [], []
    for k in np.random.default_rng(0).permutation(len(pts)):
        p = pts[k]
        if taken and np.min(np.hypot(*(np.array(taken) - p).T)) < 20: continue
        taken.append(p)
        r, c = int((p[1] - lo[1]) / CELL), int((p[0] - lo[0]) / CELL)
        # out: away from the reachable ground round it
        rr, cc = np.mgrid[max(r - 8, 0):min(r + 9, H), max(c - 8, 0):min(c + 9, W)]  # (held in the grid: a point on its border)
        inside = reach[rr, cc]
        d = np.array([(cc[inside] - c).mean(), (rr[inside] - r).mean()])
        d = -d / (np.linalg.norm(d) or 1)
        y = near_y((p[0], 0, p[1])) + 1.6
        # stood 3 m back inside, looking out over the edge
        cams.append(['e%03d' % len(cams), [float(p[0] - d[0] * 3), float(y), float(p[1] - d[1] * 3)], [float(d[0]), -0.08, float(d[1])]])
    json.dump(cams, open(os.path.join(out, 'edge_cams.json'), 'w'))
    print(open(os.path.join(out, 'audit.txt')).read().splitlines()[0])
    print('%d findings, %d edge cameras' % (len(report), len(cams)))


def zoom(out, x, z, r, scale=4):
    """A close-up of the audit's map round (x, z), r m each way: <out>\\zoom_x_z.png."""
    d = np.load(os.path.join(out, 'audit.npz'))
    img, lo = d['img'], d['lo']
    c0, r0 = int((x - r - lo[0]) / CELL), int((z - r - lo[1]) / CELL)
    n = int(2 * r / CELL)
    part = img[max(r0, 0):r0 + n, max(c0, 0):c0 + n][::-1, ::-1]
    part = np.repeat(np.repeat(part, scale, 0), scale, 1)
    forzaxpr.png(os.path.join(out, 'zoom_%d_%d.png' % (x, z)), np.ascontiguousarray(part))


if __name__ == '__main__':
    if sys.argv[1] == 'zoom':
        zoom(sys.argv[2], *map(float, sys.argv[3:6])); sys.exit()
    os.makedirs(sys.argv[2], exist_ok=True)
    audit(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or ['VancouverLoop']))
