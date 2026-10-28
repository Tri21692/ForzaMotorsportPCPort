"""The Pacific Shipyards Circuit, long layout (the user's): ~2 km round Pacific Shipyards' lots.

From the lap line on the upper road (west of Turn 2), the forward way round:

  1. the upper road south-east to Turn 2, and on out of it along side road 31;
  2. right onto side road 04, south-west then south;
  3. across the gap south of it to side road 39's east end (nothing is drawn there: a tunnel
     is to hide that);
  4. side road 39 west to Pacific Shipyards II's start road, and up it north to the junction;
  5. the strip north-west from the junction between the lots to the old road by the concrete
     barricade;
  6. a hairpin right onto the old road, east to the kink and the upper road.

The side roads, the gap and the strip are off the course: drawn only (the strip and the gap not
even that), so they get road, walls and visibility here, as the first layout's link did
(tools/shipyardloop.py, whose pieces this reuses).

  python tools/shipyardcircuit.py <disc> <mods folder> [preview.png]
"""
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coledit
import shipyardloop as L

START = (-343.0, -185.0)   # the lap line: on the upper road, the user's green circle
HALF = 7.0                 # off the course, the road's half width (metres)

# the course points the loop runs between (forward order of the buffers)
OLD_ROAD = 514     # the old road by the concrete barricade: the hairpin from the strip comes onto it here
TURN2 = 550        # Turn 2, where the loop leaves the upper road for side road 31
START_ROAD = 593   # Pacific Shipyards II's start road, where side road 39 meets it
JUNCTION = 571     # the junction at the start road's top (36 m across), where the strip leaves: at its top
                   # point (569) the loop turned 120 degrees back onto the strip, a 2 m corner whose edges crossed

# side road 31 to its end, the right-angle corner onto side road 04 (the drawn roads' centres meet at
# (-63, -377): the corner point is 2 m beyond it, as the smoothing cuts a corner by about that), down 04
SIDE_ROADS = [(-140, -326), (-100, -348), (-75, -368), (-61, -376), (-71, -390), (-85, -410), (-114, -454), (-120, -475), (-128, -560)]  # past the green
# metal building to the west at (-129, -487) with a metre to spare
GAP = [(-129, -560), (-262, -726)]       # where the tunnel is to go
ROAD39 = [(-262, -726), (-385, -646), (-503, -566)]
STRIP = [(-462, -232), (-636, -114), (-655, -104)]  # straight: warehouse 14 to its south-west, the long green
# building to its north-east; the junction's low walls on it are hidden and cut

# the course's branches the loop does not take, closed by walls across them
CLOSED = (553, 596, 566, 509)  # 509: 20 m west of the hairpin's apex (at 512 the smoothed hairpin met it)

# what closes the side roads and the strip off from the course: at Turn 2 the barricades and
# detour, turn and road-closed signs; at the strip's end the concrete barricade and a chevron sign
L.HIDE = L.HIDE + ('barrier_construction_305', 'sign_detour05', 'signturnplywood01', 'sign_roadclosed01',
                   'barrier_cementthin', 'chevsign')


def course_part(c, i, j):
    """Course points i to j (either way round), as (x, z, y)."""
    idx = range(i, j + 1) if j >= i else range(i, j - 1, -1)
    return [(c[k][0], c[k][2], c[k][1]) for k in idx]


def ground_y(sp, x, z):
    c = (sp[4] + sp[5]) / 2
    return c[L.nearest(c, (x, z))][1]


def centre_line(sp):
    """The loop's centre, forward way round, as points (x, y, z) every 2 m, smoothed so the
    joins between the course and the off-course pieces round off."""
    c = (sp[4] + sp[5]) / 2
    pts = course_part(c, OLD_ROAD, TURN2)
    for part in (SIDE_ROADS, GAP[1:], ROAD39[1:]):
        pts += [(x, z, ground_y(sp, x, z)) for x, z in part]
    pts += course_part(c, START_ROAD, JUNCTION)
    pts += [(x, z, ground_y(sp, x, z)) for x, z in STRIP]
    p = np.array([(x, y, z) for x, z, y in pts], float)
    # every 2 m, then a Gaussian of 5 m round the closed loop
    seg = np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    want = np.arange(0, s[-1], 2.0)
    closed = np.vstack([p, p[:1]])
    d = np.stack([np.interp(want, s, closed[:, k]) for k in range(3)], 1)
    k = np.arange(-8, 9)
    w = np.exp(-0.5 * (k * 2.0 / 5.0) ** 2); w /= w.sum()
    return np.stack([sum(w[j] * np.roll(d[:, a], -k[j]) for j in range(len(k))) for a in range(3)], 1)


GROUND = ('sideroad', 'parkinglot', 'sidewalk', 'road', 'ground')


def mesh_tris(res, names, want, box):
    """The triangles (3 x (x, y, z)) of model_quickpreview's meshes whose resource name passes
    `want`, within box (min x, min z, max x, max z), with each one's mesh index."""
    import struct
    out = []
    for i in range(struct.unpack_from('<I', res, L.MODEL)[0]):
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        fl, ab, nidx, vbytes, vb, stride, prim = struct.unpack_from('<IIIIHHH', res, L.MODEL + a)
        if not (9 <= vb < len(names) + 9) or stride != 6 or prim != 6 or vbytes % 24: continue
        nm = names[vb - 9][0].replace('vbuff_quickpreview_', '')
        if not want(nm): continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, :3]
        idx = np.frombuffer(bytes(res[o + vbytes:o + vbytes + 2 * nidx]), '<u2')
        if not np.all(np.isfinite(v)) or idx.size == 0 or idx.max() >= len(v): continue
        if v[:, 0].max() < box[0] or v[:, 0].min() > box[2] or v[:, 2].max() < box[1] or v[:, 2].min() > box[3]: continue
        if v[:, 0].max() - v[:, 0].min() > 800: continue  # a few meshes reach out to the origin: not real
        for k in range(len(idx) - 2):
            t = idx[k:k + 3]
            if len(set(t)) == 3: out.append((i, nm, v[t].astype(float)))
    return out


def facing_up(t):
    """Whether a triangle is ground: its normal within 15 degrees of straight up."""
    n = np.cross(t[1] - t[0], t[2] - t[0])
    return np.linalg.norm(n) > 1e-9 and abs(n[1]) > 0.966 * np.linalg.norm(n)


def drawn_heights(res, centre, off):
    """The loop's centre with its height, off the course, taken from the drawn ground under it (a
    side road, lot or sidewalk: the road there is drawn lower than the course, and sloping), and
    where nothing is drawn (the gap, the strip) blended along the loop from either side."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - 10, centre[:, [0, 2]].max(0) + 10
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: nm.startswith(GROUND) and 'lines_' not in nm, (*lo, *hi))
            if facing_up(t)]  # any slope: side road 39's triangles fall 1.8 m along their 250 m
    bb = np.array([[t[:, 0].min(), t[:, 0].max(), t[:, 2].min(), t[:, 2].max()] for t in tris])
    y = centre[:, 1].copy()
    known = ~off.copy()
    for i in np.nonzero(off)[0]:
        x, z = centre[i][0], centre[i][2]
        hits = []
        for k in np.nonzero((bb[:, 0] <= x) & (bb[:, 1] >= x) & (bb[:, 2] <= z) & (bb[:, 3] >= z))[0]:
            t = tris[k]
            a, b, c = t[0][[0, 2]], t[1][[0, 2]], t[2][[0, 2]]
            m = np.array([b - a, c - a]).T
            if abs(np.linalg.det(m)) < 1e-9: continue
            u, v = np.linalg.solve(m, np.array([x, z]) - a)
            if u >= 0 and v >= 0 and u + v <= 1: hits.append(t[0][1] + u * (t[1][1] - t[0][1]) + v * (t[2][1] - t[0][1]))
        if hits: y[i], known[i] = max(hits), True
    idx = np.arange(len(y))
    kk = np.nonzero(known)[0]
    y[~known] = np.interp(idx[~known], np.concatenate([kk - len(y), kk, kk + len(y)]), np.concatenate([y[kk]] * 3))
    k = np.arange(-3, 4); w = np.exp(-0.5 * (k / 1.5) ** 2); w /= w.sum()
    out = centre.copy()
    out[:, 1] = sum(w[j] * np.roll(y, -k[j]) for j in range(len(k)))
    return out, int(known[off].sum()), int(off.sum())


def obstacles(res, centre, half, where, inside=1.0, low=0.4, high=3.5):
    """The meshes drawn standing on the loop's road at the points `where` (the off-course stretches
    and their joins: on the course, its own rails and posts stand at the road's edge and stay):
    any triangle with a point more than `inside` m inside the road, between `low` and `high` m
    above it (not the ground, not overhead: a signal's arm passes). Returns {mesh index: name}."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - 20, centre[:, [0, 2]].max(0) + 20
    W, H = int(hi[0] - lo[0]) + 1, int(hi[1] - lo[1]) + 1
    def grid(inside):  # the road's height in each 1 m cell more than `inside` m in from its edges
        road = np.full((H, W), np.nan)
        for i in where:
            p = centre[i]
            r = half[i] - inside
            cx, cz = p[0] - lo[0], p[2] - lo[1]
            x0, x1, z0, z1 = int(max(cx - r, 0)), int(min(cx + r + 1, W)), int(max(cz - r, 0)), int(min(cz + r + 1, H))
            zz, xx = np.mgrid[z0:z1, x0:x1]
            m = (xx + 0.5 - cx) ** 2 + (zz + 0.5 - cz) ** 2 <= r * r
            road[z0:z1, x0:x1][m] = p[1]
        return road
    # lamp posts (a row of them is one mesh, its lamps' glows another) only well inside: on the side
    # roads' sidewalks, inside this wider road's edge, a row went and left its glows in the air
    shallow, deep = grid(inside), grid(2.5)
    flat = lambda nm: nm.startswith(GROUND + ('curb', 'shadow', 'line', 'parkinglot')) or 'lines_' in nm
    found = {}
    for i, nm, t in mesh_tris(res, names, lambda nm: not flat(nm), (*lo, *hi)):
        if i in found: continue
        road = deep if nm.startswith(('pole_', 'streetlight', 'trafficsignal')) else shallow
        pts = [t[0], t[1], t[2], t.mean(0)]
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            n = int(np.hypot(*(b - a)[[0, 2]]))
            pts += [a + (b - a) * u for u in np.linspace(0, 1, n + 2)[1:-1]]
        for p in pts:
            q, r = int(p[0] - lo[0]), int(p[2] - lo[1])
            if not (0 <= q < W and 0 <= r < H) or np.isnan(road[r, q]): continue
            if road[r, q] + low < p[1] < road[r, q] + high or (t[:, 1].min() < road[r, q] + high and t[:, 1].max() > road[r, q] + low and np.ptp(t[:, 1]) > high):
                found[i] = nm
                break
    return found


EDGE = ('curb', 'sidewalk', 'fence', 'guardrail', 'wall', 'barrier', 'building', 'rail', 'cementblock', 'bollard')


def bare_edges(res, centre, half, hidden=(), min_len=3):
    """Where the road's edges round the whole loop have nothing drawn defining them: nothing
    standing 0.12 to 6 m above the road (a kerb, sidewalk's edge, fence, rail, wall, building)
    within 3 m outside the edge; flat ground and sidewalks at the road's level do not count, nor
    do the meshes hidden. [(side, [loop indices])], side +1 the left edge, -1 the right, each
    stretch at least `min_len` points."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - 20, centre[:, [0, 2]].max(0) + 20
    flat = ('road', 'parkinglot', 'ground', 'sideroad', 'shadow', 'line', 'terrain')
    pts = []
    for i, nm, t in mesh_tris(res, names, lambda nm: not nm.startswith(flat) and 'lines_' not in nm, (*lo, *hi)):
        if i in hidden: continue
        pts += [t[0], t[1], t[2], t.mean(0)]
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            n = int(np.hypot(*(b - a)[[0, 2]]) / 1.5)
            pts += [a + (b - a) * u for u in np.linspace(0, 1, n + 2)[1:-1]]
    P = np.array(pts)
    cells = {}
    for k, key in enumerate(map(tuple, np.floor(P[:, [0, 2]] / 5).astype(int))): cells.setdefault(key, []).append(k)
    left, fwd = frame(centre)
    out = []
    for side in (1, -1):
        bare = []
        for i, c in enumerate(centre):
            gx, gz = int(np.floor(c[0] / 5)), int(np.floor(c[2] / 5))
            r = int(np.ceil((half[i] + 4) / 5))
            ks = [k for dx in range(-r, r + 1) for dz in range(-r, r + 1) for k in cells.get((gx + dx, gz + dz), ())]
            Q = P[ks] if ks else np.zeros((0, 3))
            rel = Q[:, [0, 2]] - c[[0, 2]]
            near = (np.abs(rel @ fwd[i]) < 1.5) & (Q[:, 1] > c[1] + 0.12) & (Q[:, 1] < c[1] + 6)
            lat = rel[near] @ left[i] * side
            bare.append(not np.any((lat > half[i] - 1) & (lat < half[i] + 3)))
        n, i = len(centre), 0
        while i < n:
            if bare[i]:
                j = i
                while j + 1 < n and bare[j + 1]: j += 1
                if j - i + 1 >= min_len: out.append((side, list(range(i, j + 1))))
                i = j + 1
            else: i += 1
    return out


BOUNDARY = ('fence', 'guardrail', 'wall', 'barrier', 'building', 'rail', 'cementblock', 'bridge_wall', 'sidewalk_fence')


def boundaries(res, centre, half, where, hidden=(), reach=8.0, inner=None):
    """For the loop points `where`, per side, how far from the centre the drawn boundary stands: the
    nearest fence, wall, rail or building face rising 0.5 m or more above the road, from 0.3 m
    inside the edge to `reach` m outside it; where there is none, the back of the sidewalk the
    kerbs draw (KERB's WIDE m out). {(side, i): distance}, side +1 the left."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - 20, centre[:, [0, 2]].max(0) + 20
    pts = []  # (x, z, lowest, highest): each upright face's footprint every 0.5 m, with its heights
    for i, nm, t in mesh_tris(res, names, lambda nm: nm.startswith(BOUNDARY) and 'lines_' not in nm, (*lo, *hi)):
        if i in hidden or facing_up(t) or np.ptp(t[:, 1]) < 0.5: continue
        a, b = footprint(t)
        n = int(np.hypot(*(b - a)) / 0.5)
        pts += [(*(a + (b - a) * u), t[:, 1].min(), t[:, 1].max()) for u in np.linspace(0, 1, n + 2)]
    P = np.array(pts)
    cells = {}
    for k, key in enumerate(map(tuple, np.floor(P[:, :2] / 5).astype(int))): cells.setdefault(key, []).append(k)
    left, fwd = frame(centre)
    out = {}
    for i in where:
        c = centre[i]
        gx, gz = int(np.floor(c[0] / 5)), int(np.floor(c[2] / 5))
        r = int(np.ceil((half[i] + reach) / 5))
        ks = [k for dx in range(-r, r + 1) for dz in range(-r, r + 1) for k in cells.get((gx + dx, gz + dz), ())]
        Q = P[ks] if ks else np.zeros((0, 4))
        rel = Q[:, :2] - c[[0, 2]]
        # a face reaching from below a car's roof to above its sills
        near = (np.abs(rel @ fwd[i]) < 1.2) & (Q[:, 2] < c[1] + 1.2) & (Q[:, 3] > c[1] + 0.5)
        for side in (1, -1):
            lat = rel[near] @ left[i] * side
            lat = lat[(lat > (half[i] - 0.3 if inner is None else inner)) & (lat < half[i] + reach)]
            out[(side, i)] = float(lat.min()) - 0.15 if len(lat) else half[i] + WIDE
    return out


def boundary_collision(col, centre, half, run, dist, sp):
    """Along an off-course run: walls (both faces, 4 m high from below the road) on the drawn
    boundary each side (`dist`, as boundaries()) where they stand off the course's road (at the
    joins the course's own walls), and ground out to them and a metre over."""
    left, _ = frame(centre)
    L3 = np.stack([left[:, 0], np.zeros(len(left)), left[:, 1]], 1)
    def wall(q):
        for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
            col.add(0x900, tri)
    for i, j in zip(run[:-1], run[1:]):
        for side in (1, -1):
            a, b = centre[i] + L3[i] * side * dist[(side, i)], centre[j] + L3[j] * side * dist[(side, j)]
            if np.all(L.off_course([a, b], sp)): wall([a + (0, -1, 0), b + (0, -1, 0), b + (0, 3, 0), a + (0, 3, 0)])
        g = lambda side, k: min(dist[(side, k)], half[k] + 8) + 1  # no wider: over the course it made bumps
        q = [centre[i] + L3[i] * g(1, i), centre[i] - L3[i] * g(-1, i),
             centre[j] - L3[j] * g(-1, j), centre[j] + L3[j] * g(1, j)]
        col.add(0, [q[0], q[1], q[2]]); col.add(0, [q[2], q[3], q[0]])


def wall_strips(a, b, height=0.9, thick=0.4):
    """A concrete wall from a to b ((x, y, z), its foot): both faces and its top, as kerb_strips'
    faces."""
    d = np.subtract(b, a); d[1] = 0; L_ = np.linalg.norm(d); d /= L_
    n = np.array([-d[2], 0.0, d[0]])
    steps = np.linspace(0, 1, max(2, int(L_ / 2) + 1))
    faces = []
    for face in ('front', 'back', 'top'):
        pairs = []
        for u in steps:
            p = np.add(a, np.subtract(b, a) * u)
            s = -32000 + 162 * L_ * u
            if face == 'front':
                q0, q1, nn, ta, tb = p + n * thick / 2 + (0, -0.1, 0), p + n * thick / 2 + (0, height, 0), n, -32369, -32268
            elif face == 'back':
                q0, q1, nn, ta, tb = p - n * thick / 2 + (0, -0.1, 0), p - n * thick / 2 + (0, height, 0), -n, -32369, -32268
            else:
                q0, q1, nn, ta, tb = p + n * thick / 2 + (0, height, 0), p - n * thick / 2 + (0, height, 0), np.array([0.0, 1, 0]), -32255, -32300
            pairs.append(((q0, nn, s, ta), (q1, nn, s, tb)))
        a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
        if np.dot(np.cross(b0 - a0, a1 - a0), pairs[0][0][1]) > 0:
            pairs = [(q, p) for p, q in pairs]
        faces.append([v for pr in pairs for v in pr])
    return faces


def near_meshes(res, points, reach):
    """The meshes of model_quickpreview with a vertex within `reach` m (across the ground) of any of
    `points`, and their parts in other formats beside them in the model (a lamp's glow)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, L.MODEL)[0]
    P = points[:, [0, 2]]
    lo, hi = P.min(0) - reach, P.max(0) + reach
    out, objs = set(), {}
    for i in range(n):
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        vbytes, vb, stride = struct.unpack_from('<IHH', res, L.MODEL + a + 12)
        if not (9 <= vb < len(names) + 9): continue
        objs[i] = object_of(names[vb - 9][0])
        if stride != 6 or vbytes % 24: continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, [0, 2]]
        if not len(v) or not np.all(np.isfinite(v)) or np.ptp(v[:, 0]) > 800: continue
        if v[:, 0].max() < lo[0] or v[:, 0].min() > hi[0] or v[:, 1].max() < lo[1] or v[:, 1].min() > hi[1]: continue
        step = max(1, len(v) // 64)
        d = np.hypot(v[::step, None, 0] - P[None, :, 0], v[::step, None, 1] - P[None, :, 1])
        if d.min() < reach: out.add(i)
    for i in list(out):
        for j in range(max(0, i - 6), min(n, i + 7)):
            if objs.get(j) == objs.get(i): out.add(j)
    return out


def whole_objects(res, hide, near=20.0):
    """The meshes `hide` and every other part of the same objects (object_of) within `near` m: a
    pole whose base stood on the road went, its arm and lights stayed in the air."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, L.MODEL)[0]
    info = {}
    for i in range(n):
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        vbytes, vb, stride = struct.unpack_from('<IHH', res, L.MODEL + a + 12)
        if not (9 <= vb < len(names) + 9) or stride != 6 or vbytes % 24: continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, :3]
        if not len(v) or not np.all(np.isfinite(v)): continue
        info[i] = (object_of(names[vb - 9][0]), (v.min(0) + v.max(0)) / 2)
    out = set(hide)
    for h in hide:
        if h not in info: continue
        o, c = info[h]
        out |= {i for i, (oi, ci) in info.items() if oi == o and np.hypot(*(ci - c)[[0, 2]]) < near}
    # and its parts in other formats beside it in the model (a lamp's glow, 0x0F, after its pole):
    # their vertices are not positions to go by
    for h in list(out):
        if h not in info: continue
        for i in range(max(0, h - 6), min(n, h + 7)):
            a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
            vb = struct.unpack_from('<H', res, L.MODEL + a + 16)[0]
            if 9 <= vb < len(names) + 9 and object_of(names[vb - 9][0]) == info[h][0]: out.add(i)  # its positions may be no positions
    return out


def void_ground(res, centre, half, dist, where, hidden, out=40.0):
    """Ground (strip faces) beside the loop points `where` wherever nothing is drawn: from the wall
    (`dist`) out `out` m, a little under the road, each side, in runs; drawn ground anywhere across
    that keeps a point out of them."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - out - 10, centre[:, [0, 2]].max(0) + out + 10
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: True, (*lo, *hi)) if i not in hidden and facing_up(t)]
    cells = {}
    for k, t in enumerate(tris):
        for gx in range(int(np.floor(t[:, 0].min() / 5)), int(np.floor(t[:, 0].max() / 5)) + 1):
            for gz in range(int(np.floor(t[:, 2].min() / 5)), int(np.floor(t[:, 2].max() / 5)) + 1):
                cells.setdefault((gx, gz), []).append(k)
    def drawn(x, z, y):  # ground near the road's level (a roof is no ground)
        for k in cells.get((int(np.floor(x / 5)), int(np.floor(z / 5))), ()):
            if y - 3 < tris[k][:, 1].mean() < y + 1.5 and L.in_quad((x, z), [(q[0], q[2]) for q in tris[k]]): return True
        return False
    left, _ = frame(centre)
    up = np.array([0.0, 1.0, 0.0])
    faces = []
    for side in (1, -1):
        run = []
        for i in list(where) + [None]:
            if i is not None:
                d0 = dist.get((side, i), half[i] + WIDE)
                l2 = left[i] * side
                if sum(not drawn(*(centre[i][[0, 2]] + l2 * (d0 + u)), centre[i][1]) for u in (out / 3, 2 * out / 3, out)) >= 2:
                    run.append(i); continue
            if len(run) >= 3:
                pairs = []
                for j in run:
                    l3 = np.array([left[j][0], 0, left[j][1]]) * side
                    a = centre[j] + l3 * dist.get((side, j), half[j] + WIDE) + (0, -0.06, 0)
                    b = a + l3 * out
                    pairs.append(((a, up, -32000 + 53.0 * (a[0] % 600), -32000 + 51.7 * (a[2] % 600)),
                                  (b, up, -32000 + 53.0 * (b[0] % 600), -32000 + 51.7 * (b[2] % 600))))
                a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
                if np.dot(np.cross(b0 - a0, a1 - a0), up) > 0: pairs = [(q, p) for p, q in pairs]
                faces.append([v for pr in pairs for v in pr])
            run = []
    return faces


def frame(centre):
    """Per loop point the unit vectors (x, z) to the left of the way round and along it."""
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0)
    fwd = np.stack([t[:, 0], t[:, 2]], 1); fwd /= np.linalg.norm(fwd, axis=1)[:, None]
    return np.stack([-fwd[:, 1], fwd[:, 0]], 1), fwd


SIDEWALK = 1   # mesh 1, sidewalk_67: the scenery's concrete sidewalk (texture 12, lightmap 13, shader 3838)
KERB, WIDE = 0.18, 2.0   # the kerb's height and the sidewalk's width out to the invisible wall


def pack_normal(n):
    """A vertex's normal word in the scenery's vertex buffers: x and y in 11 bits (1023 = 1), z in
    the top 10 (511 = 1)."""
    x, y, z = (int(round(float(v) * m)) for v, m in zip(n, (1023, 1023, 511)))
    return (x & 0x7ff) | (y & 0x7ff) << 11 | (z & 0x3ff) << 22


def kerb_strips(centre, half, side, idx):
    """A kerb and sidewalk along the road's edge at loop points idx: two faces, the kerb (facing
    the road) and the top, as lists of (position, normal, s, t) in strip order, each face's pairs
    ordered so its first triangle faces the right way (the strips' convention: cross(b - a, c - a)
    of an even triangle points away from its visible side)."""
    left, fwd = frame(centre)
    keep = idx[::2] if len(idx) > 60 else idx
    if keep[-1] != idx[-1]: keep = list(keep) + [idx[-1]]
    faces = []
    dist = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(centre[keep][:, [0, 2]], axis=0), axis=1))])
    for face in ('kerb', 'top'):
        pairs = []
        for k, i in enumerate(keep):
            out = np.array([left[i][0], 0, left[i][1]]) * side
            edge = centre[i] + out * half[i]
            s = -32000 + 162 * dist[k]
            if face == 'kerb':
                a, b = edge + (0, -0.05, 0), edge + (0, KERB, 0)
                n = -out; ta, tb = -32291, -32268
            else:
                a, b = edge + (0, KERB, 0), edge + out * WIDE + (0, KERB, 0)
                n = np.array([0.0, 1.0, 0.0]); ta, tb = -32255, -32485
            pairs.append(((a, n, s, ta), (b, n, s, tb)))
        a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
        if np.dot(np.cross(b0 - a0, a1 - a0), pairs[0][0][1]) > 0:  # facing away: swap each pair
            pairs = [(q, p) for p, q in pairs]
        faces.append([v for pr in pairs for v in pr])
    return faces


def write_strips(res, mesh, faces, light=(-32724, -32645), material=None):
    """Mesh `mesh` of model_quickpreview rewritten as the strips `faces` with the texture, lightmap
    and shader of mesh `material` (the sidewalk's unless given); its spare vertices and indices
    repeat the last. Returns its bounding sphere (centre, radius)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * mesh)[0]
    fl, ab, nidx, vbytes, vb, stride, prim, t0, t1, sh = struct.unpack_from('<IIIIHHHHHH', res, L.MODEL + a)
    sa = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * (SIDEWALK if material is None else material))[0]
    sfl, _, _, _, _, _, _, st0, st1, ssh = struct.unpack_from('<IIIIHHHHHH', res, L.MODEL + sa)
    verts = [v for f in faces for v in f]
    order, base = [], 0
    for f in faces:
        if order:
            order += [order[-1], base]
            if len(order) % 2: order.append(base)
        order += list(range(base, base + len(f)))
        base += len(f)
    nv = vbytes // 24
    assert len(verts) <= nv and len(order) <= nidx, (mesh, len(verts), nv, len(order), nidx)
    o = names[vb - 9][3]
    dt = np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)])
    buf = np.zeros(nv, dt)
    for j in range(nv):
        p, n, s, t = verts[min(j, len(verts) - 1)]
        buf['p'][j] = p
        buf['n'][j] = pack_normal(n)
        buf['st'][j] = (int(s), int(t), light[0], light[1])
    res[o:o + vbytes] = buf.tobytes()
    res[o + vbytes:o + vbytes + 2 * nidx] = np.array(order + [order[-1]] * (nidx - len(order)), '<u2').tobytes()
    struct.pack_into('<HHH', res, L.MODEL + a + 22, st0, st1, ssh)
    struct.pack_into('<I', res, L.MODEL + a, sfl)
    pts = np.array([v[0] for v in verts])
    c = (pts.min(0) + pts.max(0)) / 2
    return c, float(np.max(np.linalg.norm(pts - c, axis=1)))


def sphere_at(ppw, centre, radius):
    """The offset of the bounding sphere (f32 radius, centre) in the visibility's ppw that matches,
    or None (its records are 21 bytes, some followed by more: not walked, searched)."""
    f = np.frombuffer(ppw[:len(ppw) // 4 * 4], '<f4')
    best = None
    for shift in range(4):
        g = np.frombuffer(ppw[shift:shift + (len(ppw) - shift) // 4 * 4], '<f4').astype(float)
        if len(g) < 4: continue
        e = np.abs(g[:-3] - radius) + np.sqrt((g[1:-2] - centre[0]) ** 2 + (g[2:-1] - centre[1]) ** 2 + (g[3:] - centre[2]) ** 2)
        e[~np.isfinite(e)] = 1e9
        k = int(np.argmin(e))
        if best is None or e[k] < best[0]: best = (e[k], shift + 4 * k)
    return best[1] if best[0] < 1.0 else None


TUNNEL_H = 5.5   # the tunnel's roof above the road
ASPHALT = L.DONOR  # mesh 714's material (texture 553: asphalt) for the tunnel's floor; it is read before being rewritten
LAMP = 1359        # light_box07: a strip light (texture 264, the lamps' glow); the tunnel's lights
LAMP_ST = ((-6000, -6000), (6000, 6000))  # the glow's middle (the light box's own corner of it drew nothing in the tunnel)
HAIRPIN = (-648.0, -100.0)   # the hairpin from the strip onto the old road: open, no kerbs, its walls out on what is drawn
HAIRPIN_R = 32.0
PORTAL = 14.0      # a tunnel mouth's face: this far beyond each wall
PORTAL_TOP = 3.0   # and this far over the roof (higher, close up it hid the HUD's map)
CONCRETE = [(-490, -575), (-262, -726)]   # side road 39 from the start road to the tunnel: concrete walls both sides, in front of its fences
CONCRETE_H = 2.4


def tunnel_faces(centre, half, idx, out=0.6):
    """Over loop points idx (the gap, where nothing is drawn): a floor of road, walls `out` m outside
    each edge (on the invisible walls' line) up to the roof, and the roof, its underside facing down
    and its top up. Returns ([floor face], [concrete faces]) in kerb_strips' form."""
    left, fwd = frame(centre)
    keep = list(idx[::2]) if len(idx) > 60 else list(idx)
    if keep[-1] != idx[-1]: keep.append(idx[-1])
    P = centre[keep]
    L3 = np.stack([left[keep][:, 0], np.zeros(len(keep)), left[keep][:, 1]], 1)
    w = (half[keep] + out)[:, None]
    dist = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P[:, [0, 2]], axis=0), axis=1))])
    x0, z0 = P[:, 0].min() - 20, P[:, 2].min() - 20  # the texture's origin: everything above it stays in s16
    up = np.array([0.0, 1.0, 0.0])
    def face(a, b, n, sa, ta, sb, tb):
        pairs = [((a[k], n if np.ndim(n) == 1 else n[k], sa[k], ta[k]), (b[k], n if np.ndim(n) == 1 else n[k], sb[k], tb[k])) for k in range(len(a))]
        a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
        n0 = pairs[0][0][1]
        if np.dot(np.cross(b0 - a0, a1 - a0), n0) > 0: pairs = [(q, p) for p, q in pairs]
        return [v for pr in pairs for v in pr]
    s_of = lambda pts: -32000 + 53.0 * (pts[:, 0] - x0)
    t_of = lambda pts: -32000 + 51.7 * (pts[:, 2] - z0)
    fl, fr = P + L3 * w + (0, 0.03, 0), P - L3 * w + (0, 0.03, 0)
    floor = face(fl, fr, up, s_of(fl), t_of(fl), s_of(fr), t_of(fr))
    sd = -32000 + 162 * dist
    lo_t, hi_t = np.full(len(P), -32369.0), np.full(len(P), -32268.0)
    walls = [face(P + L3 * w, P + L3 * w + up * TUNNEL_H, -L3, sd, lo_t, sd, hi_t),   # the left wall, facing in
             face(P - L3 * w, P - L3 * w + up * TUNNEL_H, L3, sd, lo_t, sd, hi_t),    # the right wall
             face(P + L3 * w + up * TUNNEL_H, P - L3 * w + up * TUNNEL_H, -up, sd, np.full(len(P), -32255.0), sd, np.full(len(P), -32485.0)),  # the roof, from below
             face(P - L3 * w + up * (TUNNEL_H + 0.3), P + L3 * w + up * (TUNNEL_H + 0.3), up, sd, np.full(len(P), -32255.0), sd, np.full(len(P), -32485.0))]  # and above
    # two strip lights along the roof, from a metre in from each wall, facing down
    (s0, t0), (s1, t1) = LAMP_ST
    lights = []
    for side in (1, -1):
        a = P + L3 * side * (w - 1.0) + up * (TUNNEL_H - 0.05)
        b = P + L3 * side * (w - 2.0) + up * (TUNNEL_H - 0.05)  # a metre wide: half that was not seen
        lights.append(face(a, b, -up, np.full(len(P), float(s0)), np.full(len(P), float(t0)), np.full(len(P), float(s1)), np.full(len(P), float(t1))))
    # each mouth a face of concrete round its opening, so nothing past the tunnel's sides or roof
    # shows through: beside it PORTAL m each way, and above it up to PORTAL m over the roof
    portals = []
    for end in (0, len(P) - 1):
        c, l3, ww = P[end], L3[end], float(w[end][0])
        d = P[0] - P[1] if end == 0 else P[-1] - P[-2]
        n = np.array([d[0], 0.0, d[2]]) / np.hypot(d[0], d[2])  # facing out of the tunnel
        top = TUNNEL_H + PORTAL_TOP
        for lo_, hi_, y0, y1 in ((ww, ww + PORTAL, -1.0, top), (-ww - PORTAL, -ww, -1.0, top), (-ww, ww, TUNNEL_H, top)):
            a = np.array([c + l3 * lo_ + up * y0, c + l3 * hi_ + up * y0])
            b = np.array([c + l3 * lo_ + up * y1, c + l3 * hi_ + up * y1])
            ss = np.array([-32000.0, -32000.0 + 162 * (hi_ - lo_)])
            portals.append(face(a, b, n, ss, np.full(2, -32369.0), ss, np.full(2, -32369.0 + 101 * (y1 - y0) / 0.9)))
    return [floor], walls, lights, portals


def object_of(name):
    """A mesh's object: its resource name without the buffer number (_vbN) and the second copy's b."""
    import re
    base = re.sub(r'_vb\d+$', '', name.replace('vbuff_quickpreview_', ''))
    return base[:-1] if base.endswith('b') else base


def donor_pool(res, used, ppw, allowed):
    """Meshes of model_quickpreview to rewrite: stride 6 strips the loop's visibility never shows
    (`used`: so their own place is never seen from it either), whose vertex buffer is in `allowed`
    and whose bounding sphere is found in the ppw; largest first, as (pairs of vertices they hold,
    mesh, its sphere's offset)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n_mesh = struct.unpack_from('<I', res, L.MODEL)[0]
    def name_of(i):
        vb = struct.unpack_from('<H', res, L.MODEL + struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0] + 16)[0]
        return names[vb - 9][0] if 9 <= vb < len(names) + 9 else ''
    # nor a part of anything shown (a traffic signal's base taken left its lights in the air)
    seen = {object_of(name_of(i)) for i in used if i < n_mesh}
    pool = []
    for i in range(n_mesh):
        if i in used: continue
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        fl, ab, nidx, vbytes, vb, stride, prim = struct.unpack_from('<IIIIHHH', res, L.MODEL + a)
        if stride != 6 or prim != 6 or vbytes % 24 or not (9 <= vb < len(names) + 9) or vb not in allowed: continue
        if object_of(names[vb - 9][0]) in seen: continue
        pairs = min(vbytes // 24, nidx - 4) // 2
        if pairs < 2: continue
        v = L.mesh_vertices(res, names, i)
        if v is None: continue
        c = (v.min(0) + v.max(0)) / 2
        at = sphere_at(ppw, c, float(np.max(np.linalg.norm(v - c, axis=1))))
        if at is not None: pool.append((pairs, i, at))
    return sorted(pool, key=lambda r: -r[0])


def read_svb(d):
    """quickpreview1.xbp.svb, unpacked: u32 1, a 16-byte id, u32 count, then per buffer u32 resource,
    u32 size and its bytes, the same as the bundle's (vertices, then indices). The small buffers,
    loaded with the scenery and kept: {resource: (data offset, size)}."""
    import struct
    n = struct.unpack_from('<I', d, 0x14)[0]
    o, out = 0x18, {}
    for _ in range(n):
        r, sz = struct.unpack_from('<II', d, o)
        out[r] = (o + 8, sz)
        o += 8 + sz
    return out


def simplify(face, tol=0.1):
    """A strip face (pairs of vertices) without the pairs whose middle lies within `tol` m of the
    straight line between those kept either side (Douglas-Peucker): a straight stretch is one quad."""
    pairs = [face[i:i + 2] for i in range(0, len(face), 2)]
    mid = np.array([(np.asarray(a[0], float) + np.asarray(b[0], float)) / 2 for a, b in pairs])
    keep = {0, len(pairs) - 1}
    stack = [(0, len(pairs) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2: continue
        d = mid[b] - mid[a]
        L_ = np.linalg.norm(d)
        rel = mid[a + 1:b] - mid[a]
        off = np.linalg.norm(rel - np.outer(rel @ d / max(L_ ** 2, 1e-12), d), axis=1)
        k = int(np.argmax(off))
        if off[k] > tol:
            keep.add(a + 1 + k)
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return [v for i in sorted(keep) for v in pairs[i]]


def pack(faces, pool):
    """Faces cut into pieces, each the size of the largest donor left (popped from `pool`, as
    donor_pool), the pieces overlapping by a pair: [(mesh, sphere offset, piece, face index)]."""
    out = []
    for fi, face in enumerate(faces):
        pairs = [face[i:i + 2] for i in range(0, len(face), 2)]
        i = 0
        while i < len(pairs) - 1:
            if not pool: raise SystemExit('out of donor meshes: %d faces, at %d' % (len(faces), fi))
            n, mesh, at = pool.pop(0)
            out.append((mesh, at, [v for pr in pairs[i:i + n] for v in pr], fi))
            i += n - 1
    return out


def half_widths(centre, sp):
    """The road's half width along the loop: the course's own where on it, HALF off it."""
    c = (sp[4] + sp[5]) / 2
    half = np.linalg.norm(sp[4] - sp[5], axis=1) / 2
    off = L.off_course(centre, sp, margin=1.0)
    h = np.array([HALF if off[i] else half[L.nearest(c, (p[0], p[2]))] for i, p in enumerate(centre)])
    h = np.minimum(h, 11.0)  # the course is 21 m across; its junction at the strip 36 m, past a fence the line then cut through
    k = np.arange(-5, 6); w = np.exp(-0.5 * (k / 2.5) ** 2); w /= w.sum()
    return sum(w[j] * np.roll(h, -k[j]) for j in range(len(k))), off


def edges(centre, half):
    """The six edge splines: the even ones on the left of the way round, the odd on the right, as
    the first layout had them (the course's, run backwards as Pacific Shipyards II runs them)."""
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0)
    left = np.stack([-t[:, 2], np.zeros(len(t)), t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    return [centre + left * (half * (-1 if k % 2 else 1))[:, None] for k in range(6)]


def runs(off):
    """The off-course stretches, as index ranges round the loop, each with eight points (16 m) of
    course either side, so their ground and the walls cut overlap the course at the joins."""
    n = len(off)
    starts = [i for i in range(n) if off[i] and not off[i - 1]]
    out = []
    for s in starts:
        e = s
        while off[(e + 1) % n]: e += 1
        out.append([(i % n) for i in range(s - 8, e + 9)])
    return out


def footprint(p):
    """A wall triangle seen from above: its two furthest corners (x, z)."""
    i, j = max(((0, 1), (1, 2), (0, 2)), key=lambda e: np.hypot(*(p[e[0]][[0, 2]] - p[e[1]][[0, 2]])))
    return p[i][[0, 2]], p[j][[0, 2]]


def into_road(centre, half, pts):
    """For points (x, z): how far each is inside the loop's road (half width less the distance to
    the nearest centre point; negative outside)."""
    d = np.hypot(pts[:, None, 0] - centre[None, :, 0], pts[:, None, 1] - centre[None, :, 2])
    k = np.argmin(d, axis=1)
    return half[k] - d[np.arange(len(pts)), k]


def clear_road(col, centre, half, reach=0.5, keep_in=0.0):
    """Every wall reaching more than `reach` m into the loop's road, from either edge (the course's
    walls where the loop leaves or joins it at an angle, the walls put back beside an off-course
    stretch, those along it on the inside of a tight bend), cut back: its parts more than `keep_in`
    m inside the road removed, the rest put back with both faces. Returns the triangles removed."""
    lo, hi = centre[:, [0, 2]].min(0) - 30, centre[:, [0, 2]].max(0) + 30
    removed = []
    def keep(surface, pts):
        p = np.array(pts, float)
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if abs(n[1]) > 0.7 * np.linalg.norm(n): return True
        a, b = footprint(p)
        if max(a[0], b[0]) < lo[0] or min(a[0], b[0]) > hi[0] or max(a[1], b[1]) < lo[1] or min(a[1], b[1]) > hi[1]: return True
        s = np.array([a + (b - a) * t for t in np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / 0.5) + 1))])
        if np.any(into_road(centre, half, s) > reach):
            removed.append((surface, p))
            return False
        return True
    col.remove(keep)
    for surface, p in removed:
        a, b = footprint(p)
        y0, y1 = p[:, 1].min(), p[:, 1].max()
        ts = np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / 0.5) + 1))
        s = np.array([a + (b - a) * t for t in ts])
        out = into_road(centre, half, s) <= keep_in
        for k in range(len(ts) - 1):
            if out[k] and out[k + 1]:
                q = [(s[k][0], y0, s[k][1]), (s[k + 1][0], y0, s[k + 1][1]), (s[k + 1][0], y1, s[k + 1][1]), (s[k][0], y1, s[k][1])]
                for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                    col.add(surface, tri)
    return len(removed)


def clear_loop_boxes(cbx, centre, half, reach=0.5):
    """The solid props' boxes (quickpreview1.xbp.cbx, unpacked, as L.clear_boxes) reaching more than
    `reach` m into the loop's road anywhere round it dropped: a prop whose mesh is hidden (the
    concrete barricade at the hairpin, Turn 2's barricades) kept its box, an invisible wall."""
    import struct
    n = struct.unpack_from('<I', cbx, 0x14)[0]
    boxes = np.frombuffer(cbx, '<f4', count=6 * n, offset=0x18).reshape(n, 6)
    keep = []
    for b in boxes:
        xs, zs = np.linspace(b[0], b[3], max(2, int((b[3] - b[0]) / 0.5) + 1)), np.linspace(b[2], b[5], max(2, int((b[5] - b[2]) / 0.5) + 1))
        g = np.stack(np.meshgrid(xs, zs), -1).reshape(-1, 2)
        if np.any(into_road(centre, half, g) > reach): continue
        keep.append(b)
    out = cbx[:0x14] + struct.pack('<I', len(keep)) + np.array(keep, '<f4').tobytes()
    return out + bytes(len(cbx) - len(out)), n - len(keep)


def check(col, centre, half):
    """Round the loop every 2 m: walls on the road (nearer the centre than the half width less 1 m)
    and road with no ground under it (the centre and 1 m inside each edge)."""
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0)
    left = np.stack([-t[:, 2], t[:, 0]], 1); left /= np.linalg.norm(left, axis=1)[:, None]
    tris = [(np.array(p, float), n) for s, p, n, w in col.triangles()]
    lo, hi = centre[:, [0, 2]].min(0) - 20, centre[:, [0, 2]].max(0) + 20
    ground, walls = [], []
    for p, n in tris:
        if p[:, 0].max() < lo[0] or p[:, 0].min() > hi[0] or p[:, 2].max() < lo[1] or p[:, 2].min() > hi[1]: continue
        (ground if abs(n[1]) > 0.7 else walls).append(p)
    gb = np.array([[p[:, 0].min(), p[:, 0].max(), p[:, 2].min(), p[:, 2].max()] for p in ground])
    holes, blocked = [], []
    for i, c in enumerate(centre):
        for off in (0, half[i] - 1, -(half[i] - 1)):
            q = c[[0, 2]] + left[i] * off
            cand = np.nonzero((gb[:, 0] <= q[0]) & (gb[:, 1] >= q[0]) & (gb[:, 2] <= q[1]) & (gb[:, 3] >= q[1]))[0]
            if not any(L.in_quad(tuple(q), [(v[0], v[2]) for v in ground[k]]) for k in cand): holes.append((i, off))
    wpts = []
    for p in walls:
        a, b = footprint(p)
        for t_ in np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / 1.0) + 1)): wpts.append(a + (b - a) * t_)
    wpts = np.array(wpts)
    for i in range(0, len(centre)):
        d = np.hypot(wpts[:, 0] - centre[i][0], wpts[:, 1] - centre[i][2]).min()
        if d < half[i] - 1: blocked.append((i, d))
    return holes, blocked


def build(disc, mods, preview_png=None, reverse=False):
    folder = os.path.join(disc, 'media', 'tracks', 'Vancouver')
    res = L.unpack_xb2(os.path.join(folder, 'QuickPreview1.xb2'))
    sp = L.read_splines(res)
    c = (sp[4] + sp[5]) / 2
    centre = centre_line(sp)
    half, off = half_widths(centre, sp)
    centre, drawn, total = drawn_heights(res, centre, off)
    print('heights off the course: %d of %d points over drawn ground, the rest blended' % (drawn, total))
    links = [centre[r] for r in runs(off)]
    # what stands on the new road is hidden (and is no boundary): found first, the walls go by it
    hide = set()
    for link in links: hide |= set(L.hidden_meshes(res, link, sp))
    on_road = obstacles(res, centre, half, sorted({i for r in runs(off) for i in r}))
    print('standing on the road, hidden: %s' % ', '.join(sorted({nm for nm in on_road.values()})))
    hide |= set(on_road)
    hide = whole_objects(res, hide)
    hide.discard(L.DONOR)
    # the track's edges (what the game measures it by, and draws the suggested line within) half a
    # metre short of any fence, wall or building inside them: at the strip's junction the line went
    # through a fence
    bd = boundaries(res, centre, half, range(len(centre)), hidden=hide, reach=0.5, inner=2.0)
    cap = np.array([min(half[i], bd[(1, i)] - 1.5, bd[(-1, i)] - 1.5) for i in range(len(centre))])  # a car's width short of it
    cap = np.maximum(cap, 4.0)
    k_ = np.arange(-3, 4); w_ = np.exp(-0.5 * (k_ / 1.5) ** 2); w_ /= w_.sum()
    cap = np.minimum(cap, sum(w_[j] * np.roll(cap, -k_[j]) for j in range(len(k_))))
    print('track edges kept off what is drawn at %d points' % int(np.sum(cap < half - 0.05)))
    e = edges(centre, cap)
    # L.resample turns the loop round (the first layout was built in the buffers' order): given it
    # backwards, so the way round comes out as built, south-east first along the upper road
    if reverse:  # the other way round: north-west from the lap line, the even edges on the new left
        loop, length = L.resample([e[k ^ 1] for k in range(6)], centre, START)
    else:
        loop, length = L.resample([x[::-1] for x in e], centre[::-1], START)
    print('loop %.0f m (%.2f mi); off-course stretches of %s m' % (length, length / 1609.344, [2 * len(r) for r in runs(off)]))
    col = coledit.Col(open(os.path.join(folder, 'QuickPreview1.col'), 'rb').read())
    walls = [L.across(sp, i) for i in CLOSED]
    for (x0, z0, _), (x1, z1, _) in walls:
        seg = np.array([[x0 + (x1 - x0) * t, z0 + (z1 - z0) * t] for t in np.linspace(0, 1, 50)])
        dmin = np.min(np.hypot(seg[:, None, 0] - centre[None, :, 0], seg[:, None, 1] - centre[None, :, 2]))
        print('  wall across the course at (%.0f, %.0f): %.1f m from the loop' % ((x0 + x1) / 2, (z0 + z1) / 2, dmin))
    gone = added = 0
    links = [centre[r] for r in runs(off)]
    for k, link in enumerate(links):
        g, a = L.make_collision(col, link, 2 * HALF, walls if k == 0 else [], sp)
        gone += g; added += a
    # the old road's south walls inside the hairpin: its inside crosses them (the link's cut, as wide
    # as the road, missed them at so tight a turn, and cutting the apex met them)
    def open_hairpin(surface, pts):
        q = np.array(pts, float)
        n = np.cross(q[1] - q[0], q[2] - q[0])
        if abs(n[1]) > 0.7 * np.linalg.norm(n): return True
        m = q.mean(0)
        return not (np.hypot(m[0] - HAIRPIN[0], m[2] - HAIRPIN[1]) < HAIRPIN_R and m[2] < HAIRPIN[1] + 6 and m[0] > HAIRPIN[0] - 14)  # not the wall closing the old road west of it
    print('hairpin: %d of the old road\'s wall triangles on its inside removed' % col.remove(open_hairpin))
    # the walls beside the off-course stretches on what is drawn there (a fence, wall or building
    # face near the edge: the car stops at it, not through it or short of it), else at the back of
    # the sidewalk the kerbs draw; ground out to them
    dist = boundaries(res, centre, half, sorted({i for r in runs(off) for i in r}), hidden=hide)
    # the hairpin open to what is drawn round it, as wide as that is
    at_hairpin = np.hypot(centre[:, 0] - HAIRPIN[0], centre[:, 2] - HAIRPIN[1]) < HAIRPIN_R
    wide = boundaries(res, centre, half, [i for i in range(len(centre)) if at_hairpin[i]], hidden=hide, reach=25.0)
    for (side, i), d in wide.items():
        if (side, i) in dist: dist[(side, i)] = d if d < half[i] + WIDE else half[i] + 25.0
    c0, c1 = np.array(CONCRETE[0], float), np.array(CONCRETE[1], float)
    cd = c1 - c0
    cu = ((centre[:, [0, 2]] - c0) @ cd) / (cd @ cd)
    by_concrete = (cu > 0) & (cu < 1) & (np.abs(((centre[:, [0, 2]] - c0) @ np.array([-cd[1], cd[0]])) / np.linalg.norm(cd)) < 10)
    for (side, i) in list(dist):
        if by_concrete[i]: dist[(side, i)] = half[i] + 0.6
    g0_, g1_ = np.array(GAP[0], float), np.array(GAP[1], float)
    gd_ = g1_ - g0_
    gu = ((centre[:, [0, 2]] - g0_) @ gd_) / (gd_ @ gd_)
    in_gap_strict = (gu > 0.04) & (gu < 0.96) & (np.abs(((centre[:, [0, 2]] - g0_) @ np.array([-gd_[1], gd_[0]])) / np.linalg.norm(gd_)) < 10)
    in_gap = (gu > -10 / np.linalg.norm(gd_)) & (gu < 1 + 10 / np.linalg.norm(gd_)) & \
             (np.abs(((centre[:, [0, 2]] - g0_) @ np.array([-gd_[1], gd_[0]])) / np.linalg.norm(gd_)) < 12)
    for (side, i) in list(dist):
        if in_gap_strict[i]: dist[(side, i)] = half[i] + 0.6  # the tunnel's walls, on the concrete's line
    for r in runs(off): boundary_collision(col, centre, half, r, dist, sp)
    near = sum(1 for (side, i), d in dist.items() if d < half[i] + WIDE - 0.2)
    print('walls beside the new road: %d of %d on a drawn fence, wall or building' % (near, len(dist)))
    cut = clear_road(col, centre, half)
    holes, blocked = check(col, centre, half)
    print('walls cut back off the road: %d triangles' % cut)
    for what, items in (('no ground', holes), ('wall on the road', blocked)):
        print('  %s at %d points%s' % (what, len(items), ': ' + ', '.join('(%.0f, %.0f)' % (centre[i][0], centre[i][2]) for i, _ in items[:12]) if items else ''))
    col_bytes = col.to_bytes()
    res_bytes = L.write_splines(res, loop)
    print('collision: %d wall triangles removed, %d road triangles added' % (gone, added))
    # the strip has nothing drawn: the donor mesh as its road
    strip = max(links, key=lambda l: -np.min(np.hypot(l[:, 0] + 560, l[:, 2] + 170)))
    left, right = L.road_strip(strip, 2 * HALF + 4, sp)
    import xb2
    v0 = L.mesh_vertices(res, xb2.resources(bytes(res))[0], L.DONOR)
    road_was = ((v0.min(0) + v0.max(0)) / 2, float(np.max(np.linalg.norm(v0 - (v0.min(0) + v0.max(0)) / 2, axis=1))))
    st0 = np.frombuffer(bytes(res[L.vb_offset(res, L.mesh(res, L.DONOR)[3]):][:L.mesh(res, L.DONOR)[2]]), '<i2').reshape(-1, 12)[:, 8:12]
    road_light = tuple(int(v) for v in np.median(st0[:, 2:4], axis=0))  # the asphalt's lightmap where the donor has it
    road_now = L.write_road(res_bytes, left, right)
    sl = np.frombuffer(bytes(res[L.vb_offset(res, L.mesh(res, LAMP)[3]):][:L.mesh(res, LAMP)[2]]), '<i2').reshape(-1, 12)[:, 8:12]
    lamp_light = tuple(int(v) for v in np.median(sl[:, 2:4], axis=0))
    rev = os.path.join(disc, 'media', 'tracks', 'VancouverReverse')
    ppw = open(os.path.join(rev, 'QuickPreview1.pvs.ppw'), 'rb').read()
    pvs_in = open(os.path.join(rev, 'QuickPreview1.pvs'), 'rb').read()
    import struct
    head, cells_in, tail = L.parse_pvs(pvs_in)
    shown = {struct.unpack_from('<H', e)[0] for c in cells_in[:8] for l in c for e in l}
    # a kerb and sidewalk wherever a new stretch's edge has nothing drawn, each in a mesh from
    # far off that this layout never shows, its bounding sphere moved with it
    stretches = []
    for side, idx in bare_edges(res_bytes, centre, half, hidden=hide):  # none at the hairpin, in the tunnel or by the concrete
        run = []
        for i in idx + [None]:
            if i is not None and not (at_hairpin[i] or in_gap[i] or by_concrete[i]): run.append(i); continue
            if len(run) >= 3: stretches.append((side, run))
            run = []
    kerbs = [kerb_strips(centre, half, side, idx) for side, idx in stretches]
    # and a concrete wall to be seen on each invisible one closing a branch of the course
    kerbs += [wall_strips((x0, y0, z0), (x1, y1, z1)) for (x0, z0, y0), (x1, z1, y1) in walls]
    # concrete walls along side road 39 to the tunnel, in front of its fences, the collision's line
    left_, _ = frame(centre)
    for side in (1, -1):
        run = [i for i in range(len(centre)) if by_concrete[i]]
        if len(run) < 2: continue
        pts = [centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * side * dist.get((side, i), half[i] + 0.6) for i in run]
        keep = [pts[0], pts[len(pts) // 2], pts[-1]]  # the road runs straight there
        for a, b in zip(keep[:-1], keep[1:]):
            kerbs.append(wall_strips(tuple(a), tuple(b), height=CONCRETE_H))
    mats = [None] * len(kerbs)
    # the tunnel over the gap, where nothing is drawn: its floor in asphalt, its walls and roof in concrete
    g0, g1 = np.array(GAP[0], float), np.array(GAP[1], float)
    gd = g1 - g0; gl = np.linalg.norm(gd)
    u = ((centre[:, [0, 2]] - g0) @ gd) / gl ** 2
    across_ = np.abs(((centre[:, [0, 2]] - g0) @ np.array([-gd[1], gd[0]])) / gl)
    gap = [i for i in range(len(centre)) if 0.04 < u[i] < 0.96 and across_[i] < 10]
    if gap:
        floor, concrete, lights, portals = tunnel_faces(centre, half, gap)
        kerbs += [floor] + [[f] for f in concrete] + [[f] for f in lights] + [[f] for f in portals]
        mats += [ASPHALT] + [None] * len(concrete) + [LAMP] * len(lights) + [None] * len(portals)
        print('tunnel: %.0f m over the gap, %.1f m high, two strip lights, a face round each mouth' % (2 * len(gap), TUNNEL_H))
    # ground where nothing is drawn beside the new stretches (the void showed past the edges)
    skirts = void_ground(res_bytes, centre, half, dist, sorted({i for r in runs(off) for i in r}), hide)
    kerbs += [[f] for f in skirts]
    mats += [ASPHALT] * len(skirts)
    print('ground over the void beside the road: %d stretches' % len(skirts))
    # each face simplified, then in pieces the size of buffers the scenery keeps loaded (the svb's):
    # larger ones stream in with their own part of the track only, and were never drawn here
    faces, fmats = [], []
    for fs, mat in zip(kerbs, mats):
        for f in fs: faces.append(simplify(f)); fmats.append(mat)
    svb_raw = bytearray(zlib.decompress(open(os.path.join(folder, 'quickpreview1.xbp.svb'), 'rb').read()))
    svb = read_svb(svb_raw)
    near = near_meshes(res_bytes, centre[sorted({i for r in runs(off) for i in r})], 50.0) - hide
    print('drawn as well, within 50 m of the new stretches: %d meshes' % len(near - shown))
    pool = donor_pool(res_bytes, shown | near | {L.DONOR}, ppw, set(svb))
    have = len(pool)
    placed = pack(faces, pool)
    print('pieces: %d faces, %d vertex pairs, in %d of %d loaded meshes' % (len(faces), sum(len(f) for f in faces) // 2, len(placed), have))
    picked = [(mesh, at) for mesh, at, _, _ in placed]
    kerbs = [[piece] for _, _, piece, _ in placed]
    mats = [fmats[fi] for _, _, _, fi in placed]
    ppw = bytearray(ppw)
    at = sphere_at(bytes(ppw), *road_was)  # the strip's road: its sphere where the donor was, moved too
    if at is None: print('  the strip road: bounding sphere not found, it may be culled')
    else: struct.pack_into('<4f', ppw, at, road_now[1], *road_now[0])
    for (mesh, at), fs, mat in zip(picked, kerbs, mats):
        c1, r1 = write_strips(res_bytes, mesh, fs, material=mat, light={ASPHALT: road_light, LAMP: lamp_light}.get(mat, (-32724, -32645)))
        struct.pack_into('<4f', ppw, at, r1, *c1)
    ppw = bytes(ppw)
    for mesh, _ in picked:  # the svb's copies of the rewritten buffers too
        rec, nidx, vbytes, vb = L.mesh(res_bytes, mesh)
        o, sz = svb[vb]
        ro = L.vb_offset(res_bytes, vb)
        assert sz == vbytes + 2 * nidx, (mesh, sz, vbytes, nidx)
        svb_raw[o:o + sz] = res_bytes[ro:ro + sz]
    print('kerbs: %d stretches, %.0f m of edge; %d walls across the course; in meshes %s' % (
        len(stretches), sum(2 * len(i) for _, i in stretches), len(walls), [m for m, _ in picked]))
    for side, idx in stretches:
        print('  %s edge, %3.0f m from (%.0f, %.0f) to (%.0f, %.0f)' % ('left' if side > 0 else 'right', 2 * len(idx), centre[idx[0]][0], centre[idx[0]][2], centre[idx[-1]][0], centre[idx[-1]][2]))
    n_cells = len(cells_in)
    pvs, sizes = L.loop_pvs(pvs_in, [list(range(0, 8))] * n_cells, extra=[L.DONOR] + [m for m, _ in picked] + sorted(near - shown), hide=hide)
    print('road: %d cross-sections on the strip; %d meshes hidden; visibility %d meshes' % (len(left), len(hide), sizes[0]))
    cbx = zlib.decompress(open(os.path.join(folder, 'quickpreview1.xbp.cbx'), 'rb').read())
    dropped = 0
    for link in links:
        cbx, d = L.clear_boxes(cbx, link, 2 * HALF + 4)
        dropped += d
    cbx, d = clear_loop_boxes(cbx, centre, half)
    dropped += d
    cbx = zlib.compress(cbx, 9)
    print('solid props: %d boxes on the off-course road dropped' % dropped)
    if preview_png: L.preview(preview_png, sp, loop, np.mean([loop[4], loop[5]], 0), col)
    L.install(disc, mods, loop, col_bytes, res_bytes, pvs, ppw, cbx, length)
    t = os.path.join(mods, 'track', L.TAG, 'media', 'tracks', 'Vancouver')
    open(os.path.join(t, 'quickpreview1.xbp.svb'), 'wb').write(zlib.compress(bytes(svb_raw), 9))
    # its AI files: what the game counts laps and progress by
    import addcar, aitrack
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    ring = (loop[4] + loop[5]) / 2
    wps, nseg, sounds = aitrack.install(mega, L.TAG, ring, np.linalg.norm(loop[4] - loop[5], axis=1) / 2)
    mega.check(); mega.write()
    # its audio spline, one record per AI waypoint (Pacific Shipyards II's has one per II's: the
    # audio engine walked off its end and called through nothing at the start)
    ai = 'ai' + chr(92) + 'drivatarv2' + chr(92)
    audio = aitrack.audio_spline(wps, mega.files[ai + 'vancouverreversegeometry.bin'], open(os.path.join(rev, 'AudioSpline.bin'), 'rb').read())
    open(os.path.join(mods, 'media', 'tracks', L.TAG, 'AudioSpline.bin'), 'wb').write(audio)
    print('AI files: %d waypoints, %d segments; audio spline %d bytes; sounds kept %s' % (len(wps), nseg, len(audio), sounds))


if __name__ == '__main__':
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    # and the reverse, as Pacific Shipyards II is Pacific Shipyards': its own track, Hot Lap entry,
    # map tile (46), Pacific Shipyards II's logo and loading screen
    L.NAME, L.TAG = 'Pacific Shipyards Circuit II', 'VancouverLoopReverse'
    L.MAP_TILE, L.LOGO, L.LOAD_IMAGE = 46, 20, 'Load_Shipyards_II.xpr'
    build(sys.argv[1], sys.argv[2], None, reverse=True)
