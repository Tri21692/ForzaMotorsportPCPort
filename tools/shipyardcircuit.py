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
(tools/shipyardloop.py, whose pieces this reuses). It is run in the early evening (tools/evening.py):
the lightmaps lifted, the sky an evening's, the street lamps dark but for the tunnel's.

  python tools/shipyardcircuit.py <disc> <mods folder> [preview.png]
"""
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coledit
import evening
import garage
import shipyardloop as L

L.TIME_OF_DAY, L.TRACK_INI = evening.TIME, evening.track_ini

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
CLOSED = (553, 596, 566)  # (509, 20 m west of the hairpin's apex, closed the old road there: its wall read as a ledge across the hairpin, and is gone)

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


def obstacles(res, centre, half, where, inside=1.0, low=0.4, high=3.5, deep_inside=2.5):
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
    shallow, deep = grid(inside), grid(deep_inside)
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


def boundary_collision(col, centre, half, run, dist, sp, no_ground=None):
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
            span = np.array([a + (b - a) * t for t in np.linspace(0, 1, 6)])[:, [0, 2]]
            # not across another part of the loop (at the hairpin, 25 m out from one leg was the other)
            if np.all(L.off_course([a, b], sp)) and np.all(into_road(centre, half, span) < -0.5):
                wall([a + (0, -1, 0), b + (0, -1, 0), b + (0, 3, 0), a + (0, 3, 0)])
        if no_ground is not None and (no_ground[i] or no_ground[j]): continue  # not here (the hairpin: flat quads over the old road made a ledge)
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


GUARD, POST = 1895, 1084   # guardrail09 (barrier_guardrail_rusty_01) and guardrailposts25 (wood): the turns' guardrail
GUARD_Y = (0.25, 0.50)     # its beam, from and to (m over the ground)
POST_EVERY = 8.0


def guard_strips(a, b, road):
    """A guardrail from a to b ((x, y, z), its foot) as the turns have, facing `road` (x, z): the
    beam (its texture across the beam's profile, along it 242 a metre) and a post every POST_EVERY m
    behind it, each a quad (one face: both, and posts every 4 m, were more than the borrowed meshes
    hold). (beam faces, post faces) as kerb_strips' faces."""
    d = np.subtract(b, a); d[1] = 0; L_ = np.linalg.norm(d); d /= L_
    n = np.array([-d[2], 0.0, d[0]])
    if (road[0] - a[0]) * n[0] + (road[1] - a[2]) * n[2] < 0: n = -n
    steps = np.linspace(0, 1, max(2, int(L_ / 4) + 1))
    up = np.array([0.0, 1, 0])
    def face(pairs):
        a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
        if np.dot(np.cross(b0 - a0, a1 - a0), pairs[0][0][1]) > 0:
            pairs = [(q, p) for p, q in pairs]
        return [v for pr in pairs for v in pr]
    beam = []
    for nn in (n,):
        pairs = []
        for u in steps:
            p = np.add(a, np.subtract(b, a) * u)
            t = -32000 + 242 * L_ * u
            pairs.append(((p + up * GUARD_Y[0], nn, -32768, t), (p + up * GUARD_Y[1], nn, -32224, t)))
        beam.append(face(pairs))
    posts = []
    for k in range(int(L_ / POST_EVERY) + 1):
        p = np.add(a, d * min(k * POST_EVERY, L_)) - n * 0.12  # behind the beam
        for nn in (n,):
            pairs = [((p - d * 0.08, nn, -32636, -32518), (p - d * 0.08 + up * 0.43, nn, -32351, -32518)),
                     ((p + d * 0.08, nn, -32636, -32551), (p + d * 0.08 + up * 0.43, nn, -32351, -32551))]
            posts.append(face(pairs))
    return beam, posts


def lightmap_st(res, mesh):
    """Mesh `mesh`'s middling lightmap coordinates (any primitive with 24-byte vertices)."""
    import struct
    a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * mesh)[0]
    _, _, _, vbytes, vb = struct.unpack_from('<IIIIH', res, L.MODEL + a)
    st = np.frombuffer(bytes(res[L.vb_offset(res, vb):][:vbytes]), '<i2').reshape(-1, 12)[:, 10:12]
    return tuple(int(v) for v in np.median(st, axis=0))


def mesh_extent(res, i):
    """A strip mesh's size across the ground (its bounding box's larger side), 0 if not one."""
    import struct
    import xb2
    names = mesh_extent.names = getattr(mesh_extent, 'names', None) or xb2.resources(bytes(res))[0]
    a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
    vbytes, vb, stride = struct.unpack_from('<IHH', res, L.MODEL + a + 12)
    if not (9 <= vb < len(names) + 9) or stride != 6 or vbytes % 24: return 0.0
    o = names[vb - 9][3]
    v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6)[:, [0, 2]]
    if not len(v) or not np.all(np.isfinite(v)): return 0.0
    e = float(np.max(np.ptp(v, 0)))
    return e if e < 800 else 0.0


def object_parts(res, meshes):
    """Every mesh of model_quickpreview of the same objects (object_of) as `meshes`, near them in the
    model (an object's parts are numbered together)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, L.MODEL)[0]
    def obj(i):
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        vb = struct.unpack_from('<H', res, L.MODEL + a + 16)[0]
        return object_of(names[vb - 9][0]) if 9 <= vb < len(names) + 9 else None
    out = set()
    for i in meshes:
        if i >= n: continue
        o = obj(i)
        if o is None: continue
        for j in range(max(0, i - 12), min(n, i + 13)):
            if obj(j) == o: out.add(j)
    return out


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


def kerb_collision(col, centre, half, side, idx):
    """Collision for kerb_strips' kerb and sidewalk at loop points idx: the kerb a ramp from the
    road's edge up to KERB over 0.3 m (as ground: a car mounts it), the sidewalk's top flat out to
    WIDE. Returns the triangles added."""
    left, _ = frame(centre)
    added = 0
    for i, j in zip(idx[:-1], idx[1:]):
        rows = []
        for k in (i, j):
            out = np.array([left[k][0], 0, left[k][1]]) * side
            edge = centre[k] + out * half[k]
            rows.append((edge + (0, -0.02, 0), edge + out * 0.3 + (0, KERB, 0), edge + out * WIDE + (0, KERB, 0)))
        for a in range(2):
            p0, p1, q0, q1 = rows[0][a], rows[0][a + 1], rows[1][a], rows[1][a + 1]
            for tri in ([p0, p1, q1], [q1, q0, p0]):
                n = np.cross(np.subtract(tri[1], tri[0]), np.subtract(tri[2], tri[0]))
                col.add(0, tri if n[1] > 0 else tri[::-1])  # facing up, as the disc's ground
                added += 1
    return added


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
RAIL = 2297       # jw_blackrail_barrier01b: a black rail (texture 1673); the tunnel walkways' railings
WALKWAY, WALKWAY_H = 1.2, 0.25   # the tunnel's walkways: their width in from its walls, their height
RAILS = ((0.50, 0.60), (0.88, 1.00))  # the railing's two bars, from and to (m over the walkway)
PORTAL_TOP = 3.0   # and this far over the roof (higher, close up it hid the HUD's map)
CONCRETE = [(-490, -575), (-262, -726)]   # side road 39 from the start road to the tunnel: concrete walls both sides, in front of its fences
CONCRETE_H = 2.4


HEAD, HEAD_GLOW = 2158, 2159   # pole_streetlight154's head (its strip, and its foot's plate) and its glow: the tunnel's lamps
LAMP_EVERY = 32.0  # m between the tunnel's lamps, each wall in turn
MARGIN = 2.0       # the track's edges (the suggested line) this far short of any wall
TUNNEL_LEAD = 12   # points (2 m each) the tunnel reaches back along side road 39, round the corner into the gap


def tunnel_points(centre):
    """The loop points under a roof: inside the garage (tools/garage.py) over the gap."""
    return garage.points(centre)


WALK_IN, WALK_RAMP = 3, 6   # points (2 m each): the walkways begin this far into the straight, and grow over this many

def walkway_width(n):
    """The walkways' width at each of n points: nothing for the first and last WALK_IN (cars cutting
    the corner at each mouth ran onto them), then growing over WALK_RAMP (a step read as a ledge,
    a short wedge was clipped)."""
    k = np.arange(n)
    return WALKWAY * np.clip((np.minimum(k, n - 1 - k) - WALK_IN) / WALK_RAMP, 0, 1)


def tunnel_walk(centre, idx):
    """The walkways' width at each of the tunnel's points idx: only where it runs straight along the
    gap (round the corner into it they showed in the turn), growing from nothing at each end."""
    g0, g1 = np.array(GAP[0], float), np.array(GAP[1], float)
    gd = g1 - g0
    u = ((centre[:, [0, 2]] - g0) @ gd) / (gd @ gd)
    across = np.abs(((centre[:, [0, 2]] - g0) @ np.array([-gd[1], gd[0]])) / np.linalg.norm(gd))
    _, fwd = frame(centre)
    along = np.abs(fwd @ (gd / np.linalg.norm(gd)))
    straight = [k for k, i in enumerate(idx) if 0.04 < u[i] < 0.96 and across[i] < 6 and along[i] > np.cos(np.radians(8))]
    w = np.zeros(len(idx))
    if straight:
        a, b = straight[0], straight[-1]
        w[a:b + 1] = walkway_width(b - a + 1)
    return w


def lamp_faces(res, foot, facing, y_top):
    """The street light HEAD as faces (its strip's runs, not to be simplified), its pole's foot
    moved to `foot` (x, z), its arm turned along `facing` (x, z, unit), its top at y_top; and its
    glow's vertices (HEAD_GLOW, 20 bytes each) moved the same: (faces, glow bytes, glow indices)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    def raw(i):
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        _, _, nidx, vbytes, vb = struct.unpack_from('<IIIIH', res, L.MODEL + a)
        o = names[vb - 9][3]
        return bytes(res[o:o + vbytes]), np.frombuffer(bytes(res[o + vbytes:o + vbytes + 2 * nidx]), '<u2')
    vb, idx = raw(HEAD)
    v = np.frombuffer(vb, np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)]))
    p = v['p'].astype(float)
    high = p[:, 1] > 4.0           # the head (its foot's plate is low)
    base = p[~high][:, [0, 2]].mean(0)
    d = p[high][:, [0, 2]].mean(0) - base
    ang = np.arctan2(facing[1], facing[0]) - np.arctan2(d[1], d[0])
    c_, s_ = np.cos(ang), np.sin(ang)
    top = p[high][:, 1].max()
    def move(q):
        x, z = q[..., 0] - base[0], q[..., 2] - base[1]
        return np.stack([foot[0] + c_ * x - s_ * z, q[..., 1] - top + y_top, foot[1] + s_ * x + c_ * z], -1)
    def turn(n):
        return np.array([c_ * n[0] - s_ * n[2], n[1], s_ * n[0] + c_ * n[2]])
    P = move(p)
    vert = lambda k: (P[k], turn(unpack_normal(int(v['n'][k]))), int(v['st'][k][0]), int(v['st'][k][1]))
    faces, run = [], []
    for k in list(range(len(idx))) + [None]:  # runs of the strip through the head alone
        if k is not None and high[idx[k]]:
            run.append(k); continue
        if len(run) >= 3:
            f = ([run[0]] if run[0] % 2 else []) + run  # its first triangle as odd as it was
            if len(f) % 2: f.append(f[-1])
            faces.append([vert(idx[j]) for j in f])
        run = []
    g, gi = raw(HEAD_GLOW)
    gv = np.frombuffer(g, np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<u4')])).copy()
    gv['p'] = move(gv['p'].astype(float))
    gv['n'] = [pack_normal(turn(unpack_normal(int(w)))) for w in gv['n']]
    return faces, gv.tobytes(), gi


def unpack_normal(w):
    """pack_normal's word as a vector."""
    x, y, z = w & 0x7ff, (w >> 11) & 0x7ff, (w >> 22) & 0x3ff
    x, y, z = x - 0x800 * (x >= 0x400), y - 0x800 * (y >= 0x400), z - 0x400 * (z >= 0x200)
    return np.array([x / 1023, y / 1023, z / 511])


def glow_pool(res, used, ppw, allowed, vbytes_, nidx_):
    """Glows (prim 15, 20-byte vertices) to move: in `allowed` (the svb's), not in `used`, nor part
    of anything used, holding vbytes_ and nidx_, their sphere found: [(mesh, sphere offset)]."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n_mesh = struct.unpack_from('<I', res, L.MODEL)[0]
    def rec(i):
        return struct.unpack_from('<IIIIHHH', res, L.MODEL + struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0])
    nm = lambda vb: names[vb - 9][0] if 9 <= vb < len(names) + 9 else ''
    seen = {object_of(nm(rec(i)[4])) for i in used if i < n_mesh}
    out = []
    for i in range(n_mesh):
        fl, ab, nidx, vbytes, vb, stride, prim = rec(i)
        if i in used or prim != 15 or vb not in allowed or vbytes < vbytes_ or nidx < nidx_ or vbytes % 20: continue
        if object_of(nm(vb)) in seen: continue
        o = names[vb - 9][3]
        q = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 5)[:, :3].astype(float)
        if not np.all(np.isfinite(q)): continue
        c = (q.min(0) + q.max(0)) / 2
        at = sphere_at(ppw, c, float(np.max(np.linalg.norm(q - c, axis=1))))
        if at is not None: out.append((i, at))
    return out


def write_glow(res, mesh, data, idx):
    """Glow `mesh` rewritten as HEAD_GLOW's vertices `data` and indices (its spare ones repeating the
    last), with HEAD_GLOW's texture and shader. Returns its bounding sphere."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * mesh)[0]
    _, _, nidx, vbytes, vb = struct.unpack_from('<IIIIH', res, L.MODEL + a)
    ga = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * HEAD_GLOW)[0]
    gfl = struct.unpack_from('<I', res, L.MODEL + ga)[0]
    gt = struct.unpack_from('<HHH', res, L.MODEL + ga + 22)
    o = names[vb - 9][3]
    nv = vbytes // 20
    d = data + data[-20:] * (nv - len(data) // 20)
    res[o:o + vbytes] = d
    res[o + vbytes:o + vbytes + 2 * nidx] = np.array(list(idx) + [idx[-1]] * (nidx - len(idx)), '<u2').tobytes()
    struct.pack_into('<HHH', res, L.MODEL + a + 22, *gt)
    struct.pack_into('<I', res, L.MODEL + a, gfl)
    q = np.frombuffer(data, '<f4').reshape(-1, 5)[:, :3].astype(float)
    c = (q.min(0) + q.max(0)) / 2
    return c, float(np.max(np.linalg.norm(q - c, axis=1)))


def tunnel_faces(centre, half, idx, out=0.6, apron=6):
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
    # the floor, and on out of the mouth at the gap's start (the side road's drawn end falls short
    # of it: the void showed past the mouth)
    fk = list(range(max(0, idx[0] - apron), idx[0])) + keep
    PF, LF = centre[fk], np.stack([left[fk][:, 0], np.zeros(len(fk)), left[fk][:, 1]], 1)
    WF = (half[fk] + out)[:, None]
    fl, fr = PF + LF * WF + (0, 0.03, 0), PF - LF * WF + (0, 0.03, 0)
    floor = face(fl, fr, up, s_of(fl), t_of(fl), s_of(fr), t_of(fr))
    sd = -32000 + 162 * dist
    lo_t, hi_t = np.full(len(P), -32369.0), np.full(len(P), -32268.0)
    walls = [face(P + L3 * w, P + L3 * w + up * TUNNEL_H, -L3, sd, lo_t, sd, hi_t),   # the left wall, facing in
             face(P - L3 * w, P - L3 * w + up * TUNNEL_H, L3, sd, lo_t, sd, hi_t),    # the right wall
             face(P + L3 * w + up * TUNNEL_H, P - L3 * w + up * TUNNEL_H, -up, sd, np.full(len(P), -32255.0), sd, np.full(len(P), -32485.0)),  # the roof, from below
             face(P - L3 * w + up * (TUNNEL_H + 0.3), P + L3 * w + up * (TUNNEL_H + 0.3), up, sd, np.full(len(P), -32255.0), sd, np.full(len(P), -32485.0))]  # and above
    ww_all = tunnel_walk(centre, idx)
    ww_ = ww_all[[idx.index(i) for i in keep]][:, None]
    # street lamps under the roof along the walkways, each wall in turn: where they are lamps go
    lights = []  # (foot (x, z), facing (x, z), top y)
    full = [i for i, ww in zip(idx, ww_all) if ww >= WALKWAY - 1e-6]
    if full:
        run_ = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(centre[full][:, [0, 2]], axis=0), axis=1))])
        side, nxt = 1, LAMP_EVERY / 2
        for i, d_ in zip(full, run_):
            if d_ < nxt: continue
            l2 = np.array(left[i]) * side
            foot = centre[i][[0, 2]] + l2 * (half[i] + out)
            lights.append((foot, -l2, centre[i][1] + TUNNEL_H - 0.02))
            side, nxt = -side, nxt + LAMP_EVERY
    # a raised walkway along each wall, its kerb, its end at each mouth, and a two-bar railing at its
    # edge (the tunnel at Tokyo's way)
    walkways, railings = [], []
    on = np.nonzero(ww_[:, 0] > 0)[0]
    span = slice(max(0, on[0] - 1), min(len(P), on[-1] + 2)) if len(on) else slice(0, 0)
    for side in (1, -1):
        if not len(on): break
        edge = P + L3 * side * (w - ww_)
        wall = P + L3 * side * w
        out_ = L3 * side
        edge, wall, out_, sd_, lo_ = edge[span], wall[span], out_[span], sd[span], lo_t[span]
        m_ = len(edge)
        walkways.append(face(edge, edge + up * WALKWAY_H, -out_, sd_, lo_, sd_, np.full(m_, -32369.0 + 101 * WALKWAY_H / 0.9)))  # the kerb
        walkways.append(face(edge + up * WALKWAY_H, wall + up * WALKWAY_H, up, sd_, np.full(m_, -32255.0), sd_, np.full(m_, -32255.0 - 115 * WALKWAY)))  # its top
        for y0, y1 in RAILS:
            for facing in (-1, 1):  # both sides of each bar
                railings.append(face(edge + up * (WALKWAY_H + y0), edge + up * (WALKWAY_H + y1), out_ * facing, -32765 + 162 * dist[span], np.full(m_, -32517.0), -32765 + 162 * dist[span], np.full(m_, -32260.0)))
    # each mouth a face of concrete round its opening, so nothing past the tunnel's sides or roof
    # shows through: beside it PORTAL m each way, and above it up to PORTAL m over the roof
    portals = []
    for end in (0, len(P) - 1):
        c, l3, ww = P[end], L3[end], float(w[end][0])
        d = P[0] - P[1] if end == 0 else P[-1] - P[-2]
        n = np.array([d[0], 0.0, d[2]]) / np.hypot(d[0], d[2])  # facing out of the tunnel
        top = TUNNEL_H + PORTAL_TOP
        panels = [(ww, ww + PORTAL, -1.0, top), (-ww - PORTAL, -ww, -1.0, top), (-ww, ww, TUNNEL_H, top)]
        if end == len(P) - 1:  # round the corner: the panel on the turn's outside stood alone, flat, by nothing
            inside = np.sign(l3 @ (P[len(P) // 2] - c))
            panels = [q for q in panels if not (q[0] * inside < 0 and q[1] * inside < 0)]
        for lo_, hi_, y0, y1 in panels:
            a = np.array([c + l3 * lo_ + up * y0, c + l3 * hi_ + up * y0])
            b = np.array([c + l3 * lo_ + up * y1, c + l3 * hi_ + up * y1])
            ss = np.array([-32000.0, -32000.0 + 162 * (hi_ - lo_)])
            portals.append(face(a, b, n, ss, np.full(2, -32369.0), ss, np.full(2, -32369.0 + 101 * (y1 - y0) / 0.9)))
    return [floor], walls, lights, portals, walkways, railings


def concrete_mask(centre):
    """The loop points along side road 39 between the start road and the tunnel (CONCRETE)."""
    c0, c1 = np.array(CONCRETE[0], float), np.array(CONCRETE[1], float)
    cd = c1 - c0
    cu = ((centre[:, [0, 2]] - c0) @ cd) / (cd @ cd)
    return (cu > 0) & (cu < 1) & (np.abs(((centre[:, [0, 2]] - c0) @ np.array([-cd[1], cd[0]])) / np.linalg.norm(cd)) < 10)


def fill_ground(col, centre, half, dist, where, step=1.0, margin=15):
    """Ground where the collision has none, out to the walls (`dist`) beside loop points `where`
    and `margin` points either side, at the height of the ground found round it: at the hairpin,
    between its road and the walls out on what is drawn, the car fell through. Looked for on a
    grid `step` apart (rays out from each point fanned apart round the hairpin and left strips
    between them), each gap a square half as wide again, and along each road edge a quarter metre
    apart out to 3 m (a strip at the edge narrower than the grid, on the inside of the apex, was
    the hole). Half a metre's grid was 21,000 squares, the collision twice its size: textures were
    let go. Returns the squares added."""
    n = len(centre)
    near = sorted({(i + k) % n for i in where for k in range(-margin, margin + 1)})
    left, fwd = frame(centre)
    lo, hi = centre[near][:, [0, 2]].min(0) - 40, centre[near][:, [0, 2]].max(0) + 40
    tris = []
    for _, pts, nrm, _ in col.triangles():
        q = np.array(pts, float)
        if abs(nrm[1]) <= 0.7 or q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 2].max() < lo[1] or q[:, 2].min() > hi[1]: continue
        tris.append(q)
    cells = {}
    for k, t in enumerate(tris):
        for gx in range(int(np.floor(t[:, 0].min() / 5)), int(np.floor(t[:, 0].max() / 5)) + 1):
            for gz in range(int(np.floor(t[:, 2].min() / 5)), int(np.floor(t[:, 2].max() / 5)) + 1):
                cells.setdefault((gx, gz), []).append(k)
    def height(x, z, y):
        for k in cells.get((int(np.floor(x / 5)), int(np.floor(z / 5))), ()):
            a, b, c = tris[k]
            m = np.array([[b[0] - a[0], c[0] - a[0]], [b[2] - a[2], c[2] - a[2]]])
            if abs(np.linalg.det(m)) < 1e-9: continue
            u, v = np.linalg.solve(m, [x - a[0], z - a[2]])
            if u < -1e-4 or v < -1e-4 or u + v > 1 + 1e-4: continue
            h = a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])
            if y - 2.0 < h < y + 1.5: return h
        return None
    # the grid: points whose nearest loop point is one of `near` and which lie inside its walls
    reach = max(dist.get((sd, i), half[i] + 8.0) for i in near for sd in (1, -1)) + 3.0
    glo = centre[near][:, [0, 2]].min(0) - reach
    ghi = centre[near][:, [0, 2]].max(0) + reach
    xs, zs = np.arange(glo[0], ghi[0], step), np.arange(glo[1], ghi[1], step)
    gx, gz = np.meshgrid(xs, zs)
    pts = np.stack([gx.ravel(), gz.ravel()], 1)
    c2 = centre[:, [0, 2]]
    added = 0
    near_set = set(near)
    squares = []
    def square(p, y, w_):
        nonlocal added
        h = None
        for r in (0.75, 1.5, 3.0):
            hs = [height(p[0] + dx, p[1] + dz, y) for dx, dz in ((r, 0), (-r, 0), (0, r), (0, -r))]
            hs = [x for x in hs if x is not None]
            if hs: h = float(np.mean(hs)); break
        Q = np.array([p[0], y - 0.05 if h is None else h, p[1]])
        sq = [Q + (w_, 0, w_), Q + (-w_, 0, w_), Q + (-w_, 0, -w_), Q + (w_, 0, -w_)]
        col.add(0, [sq[0], sq[2], sq[1]]); col.add(0, [sq[2], sq[0], sq[3]])  # facing up, as the disc's ground
        squares.append((p[0], p[1], w_))
        added += 1
    def filled(p):
        return any(abs(p[0] - x) <= w and abs(p[1] - z) <= w for x, z, w in squares[-400:])
    for i in near:  # the edges first, finely
        for side in (1, -1):
            for u in np.arange(half[i] - 0.25, half[i] + 3.0, 0.25):
                p = c2[i] + left[i] * side * u
                if height(p[0], p[1], centre[i][1]) is None and not filled(p): square(p, centre[i][1], 0.3)
    for chunk in range(0, len(pts), 4096):
        P = pts[chunk:chunk + 4096]
        d = np.hypot(P[:, None, 0] - c2[None, :, 0], P[:, None, 1] - c2[None, :, 1])
        nearest = d.argmin(1)
        for p, i, di in zip(P, nearest, d):
            if i not in near_set: continue
            lat = (p - c2[i]) @ left[i]
            side = 1 if lat > 0 else -1
            # between the hairpin's legs (its walls there taken away): near another leg as well
            other = np.abs((np.arange(n) - i + n // 2) % n - n // 2) > 25
            between = di[other].min() < half[np.argmin(np.where(other, di, 1e9))] + 15 and di[i] < half[i] + 15
            if abs(lat) > dist.get((side, i), half[i] + 8.0) + 2.5 and not between: continue  # past the walls a little (the old road's were taken away); no wall found: 8 m on
            y = centre[i][1]
            if height(p[0], p[1], y) is not None: continue
            square(p, y, step * 0.75)
    return added


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
        if at is not None: pool.append((pairs, i, at, vbytes // 24, nidx))
    return sorted(pool, key=lambda r: -r[0])


def clear_tunnel(res, centre, half, idx, svb, svb_raw, keep=()):
    """The scenery's vertices inside the garage (tools/garage.py's box) and not under its floor,
    moved out past its nearest wall: side road 39's raised sidewalk (sidewalk_79) ran on into it.
    In the bundle and the svb's copies. Returns the vertices moved."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, L.MODEL)[0]
    moved = 0
    for m in range(n):
        if m in keep: continue
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
        _, _, nidx, vbytes, vb, stride, prim = struct.unpack_from('<IIIIHHH', res, L.MODEL + a)
        if stride != 6 or prim != 6 or vbytes % 24 or not (9 <= vb < len(names) + 9): continue
        o = names[vb - 9][3]
        v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, 6).copy()
        ins = garage.inside(v[:, [0, 2]])
        if not ins.any(): continue
        uv = garage.to_uv(v[:, [0, 2]])
        ins &= v[:, 1] > garage.floor_y(centre, uv) - 0.05
        if not ins.any(): continue
        q = uv[ins]
        gaps = np.stack([q[:, 0] - garage.U0, garage.U1 - q[:, 0], q[:, 1] - garage.V0, garage.V1 - q[:, 1]], 1)
        k = gaps.argmin(1)
        q[k == 0, 0] = garage.U0 - 0.3; q[k == 1, 0] = garage.U1 + 0.3
        q[k == 2, 1] = garage.V0 - 0.3; q[k == 3, 1] = garage.V1 + 0.3
        w = garage.to_world(q, 0.0)
        v[ins, 0], v[ins, 2] = w[:, 0], w[:, 2]
        res[o:o + vbytes] = v.astype('<f4').tobytes()
        if vb in svb:
            so, _ = svb[vb]
            svb_raw[so:so + vbytes] = res[o:o + vbytes]
        moved += int(ins.sum())
    return moved


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


def pack(faces, pool, mats):
    """Faces gathered by material into the donors (popped from `pool`, as donor_pool, the largest
    left first), as many to each as fit (write_strips joins them), one too long for what is left
    cut, its pieces overlapping by a pair: [(mesh, sphere offset, [pieces], material)]."""
    out = []
    print('donors: %d, room for %d pairs; needed %s' % (len(pool), sum(r[0] for r in pool), {str(m_): sum(len(f) // 2 for f, mm in zip(faces, mats) if mm == m_) for m_ in set(mats)}))
    by = {}
    for f, m in zip(faces, mats): by.setdefault(m, []).append([f[i:i + 2] for i in range(0, len(f), 2)])
    for m, queue in by.items():
        while queue:
            if not pool: raise SystemExit('out of donor meshes: %d faces; left %s' % (len(faces), {str(m_): sum(len(q) for q in qq) for m_, qq in by.items() if qq}))
            _, mesh, at, nv, nidx = pool.pop(0)
            pieces, v, ix = [], 0, 0
            while queue:
                pr = queue[0]
                join = 3 if pieces else 0
                k = min(nv - v, nidx - ix - join) // 2  # the pairs there is room for
                if k >= len(pr): take = len(pr); queue.pop(0)
                elif k >= 2 and (not pieces or k >= 8): take = k; queue[0] = pr[k - 1:]
                else: break
                pieces.append([q for p_ in pr[:take] for q in p_])
                v += 2 * take; ix += 2 * take + join
            out.append((mesh, at, pieces, m))
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
    # and between the concrete walls up to the tunnel and in it, everything up to the walls (a lamp
    # post stood in the road there)
    walled = sorted(set(np.nonzero(concrete_mask(centre))[0]) | set(tunnel_points(centre)))
    inside_walls = obstacles(res, centre, half, walled, inside=-0.3, deep_inside=-0.3)
    print('between the concrete walls, hidden: %s' % ', '.join(sorted({nm for nm in inside_walls.values()})))
    hide |= set(inside_walls)
    in_shop = garage.meshes_inside(res, centre)
    print('inside the garage, hidden: %d meshes' % len(in_shop))
    hide |= in_shop
    hide = whole_objects(res, hide)
    hide.discard(L.DONOR)
    # the track's edges (what the game measures it by, and draws the suggested line within) half a
    # metre short of any fence, wall or building inside them: at the strip's junction the line went
    # through a fence
    bd = boundaries(res, centre, half, range(len(centre)), hidden=hide, reach=0.5, inner=2.0)
    cap = np.array([min(half[i], bd[(1, i)] - MARGIN, bd[(-1, i)] - MARGIN) for i in range(len(centre))])  # a car's width and more short of it
    g0c, g1c = np.array(GAP[0], float), np.array(GAP[1], float)
    gdc = g1c - g0c
    guc = ((centre[:, [0, 2]] - g0c) @ gdc) / (gdc @ gdc)
    tunnel_idx = tunnel_points(centre)
    left_c, _ = frame(centre)
    shop_wall = {(side, i): min(garage.lateral(centre, half, i, side, left_c), half[i] + 1.0) for i in tunnel_idx for side in (1, -1)}
    for i in tunnel_idx:  # off the garage's walls and its parked vehicles
        cap[i] = min(cap[i], shop_wall[(1, i)] - MARGIN, shop_wall[(-1, i)] - MARGIN)
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
    by_concrete = concrete_mask(centre)
    for (side, i) in list(dist):
        if by_concrete[i]: dist[(side, i)] = half[i] + 0.6
    g0_, g1_ = np.array(GAP[0], float), np.array(GAP[1], float)
    gd_ = g1_ - g0_
    gu = ((centre[:, [0, 2]] - g0_) @ gd_) / (gd_ @ gd_)
    tunnel_idx = tunnel_points(centre)
    in_gap_strict = np.zeros(len(centre), bool); in_gap_strict[tunnel_idx] = True
    by_concrete &= ~in_gap_strict  # the concrete walls end where the tunnel's begin, on the same line
    in_gap = (gu > -10 / np.linalg.norm(gd_)) & (gu < 1 + 10 / np.linalg.norm(gd_)) & \
             (np.abs(((centre[:, [0, 2]] - g0_) @ np.array([-gd_[1], gd_[0]])) / np.linalg.norm(gd_)) < 12)
    for (side, i) in list(dist):
        if in_gap_strict[i]: dist[(side, i)] = shop_wall[(side, i)]  # in the garage: its walls, or a metre past the road by the parked row
    near = sum(1 for (side, i), d in dist.items() if d < half[i] + WIDE - 0.2)
    print('walls beside the new road: %d of %d on a drawn fence, wall or building' % (near, len(dist)))
    cut = clear_road(col, centre, half)
    # the walls beside the new road after the cut (the tunnel's railings stand inside the road's
    # width, and were cut away), no ground of theirs at the hairpin
    for r in runs(off): boundary_collision(col, centre, half, r, dist, sp, at_hairpin)
    print('hairpin: %d squares of ground where there was none' % fill_ground(col, centre, half, dist, [i for i in range(len(centre)) if at_hairpin[i]]))
    holes, blocked = check(col, centre, half)
    print('walls cut back off the road: %d triangles' % cut)
    for what, items in (('no ground', holes), ('wall on the road', blocked)):
        print('  %s at %d points%s' % (what, len(items), ': ' + ', '.join('(%.0f, %.0f)' % (centre[i][0], centre[i][2]) for i, _ in items[:12]) if items else ''))
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
    sl = np.frombuffer(bytes(res[L.vb_offset(res, L.mesh(res, RAIL)[3]):][:L.mesh(res, RAIL)[2]]), '<i2').reshape(-1, 12)[:, 8:12]
    rail_light = tuple(int(v) for v in np.median(sl[:, 2:4], axis=0))
    sl = np.frombuffer(bytes(res[L.vb_offset(res, L.mesh(res, HEAD)[3]):][:L.mesh(res, HEAD)[2]]), '<i2').reshape(-1, 12)[:, 8:12]
    head_light = tuple(int(v) for v in np.median(sl[:, 2:4], axis=0))
    guard_light, post_light = lightmap_st(res, GUARD), lightmap_st(res, POST)
    rev = os.path.join(disc, 'media', 'tracks', 'VancouverReverse')
    ppw = open(os.path.join(rev, 'QuickPreview1.pvs.ppw'), 'rb').read()
    pvs_in = open(os.path.join(rev, 'QuickPreview1.pvs'), 'rb').read()
    import struct
    head, cells_in, tail = L.parse_pvs(pvs_in)
    shown = {struct.unpack_from('<H', e)[0] for c in cells_in[:8] for l in c for e in l}
    # a kerb and sidewalk wherever a new stretch's edge has nothing drawn, each in a mesh from
    # far off that this layout never shows, its bounding sphere moved with it
    stretches = []
    by_shop = garage.inside(centre[:, [0, 2]], pad=12.0)  # in the garage and up to its doors
    for side, idx in bare_edges(res_bytes, centre, half, hidden=hide):  # none in the tunnel or by the concrete
        run = []
        for i in idx + [None]:
            if i is not None and not (in_gap[i] or by_concrete[i] or at_hairpin[i] or by_shop[i]): run.append(i); continue
            if len(run) >= 3: stretches.append((side, run))
            run = []
    kerbs = [kerb_strips(centre, half, side, idx) for side, idx in stretches]
    # and the kerbs and sidewalks solid: the car rode through them at the road's level
    print('kerbs solid: %d triangles' % sum(kerb_collision(col, centre, half, side, idx) for side, idx in stretches))
    print('garage: %d collision triangles, its yard fence %d' % (garage.collision(col, centre, half), garage.yard_collision(col, centre, half)))
    col_bytes = col.to_bytes()
    # and a concrete wall to be seen on each invisible one closing a branch of the course
    kerbs += [wall_strips((x0, y0, z0), (x1, y1, z1)) for (x0, z0, y0), (x1, z1, y1) in walls]
    mats = [None] * len(kerbs)
    # guardrails along side road 39 to the tunnel, in front of its fences, the collision's line (it
    # was concrete: too much of it)
    left_, _ = frame(centre)
    for side in (1, -1):
        run = [i for i in range(len(centre)) if by_concrete[i]]
        if len(run) < 2: continue
        pts = [centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * side * dist.get((side, i), half[i] + 0.6) for i in run]
        keep = [pts[0], pts[len(pts) // 2], pts[-1]]  # the road runs straight there
        for a, b in zip(keep[:-1], keep[1:]):
            beam, posts = guard_strips(tuple(a), tuple(b), centre[run[len(run) // 2]][[0, 2]])
            kerbs += [beam, posts]; mats += [GUARD, POST]
    # the tunnel over the gap, where nothing is drawn: its floor in asphalt, its walls and roof in concrete
    g0, g1 = np.array(GAP[0], float), np.array(GAP[1], float)
    gd = g1 - g0; gl = np.linalg.norm(gd)
    u = ((centre[:, [0, 2]] - g0) @ gd) / gl ** 2
    across_ = np.abs(((centre[:, [0, 2]] - g0) @ np.array([-gd[1], gd[0]])) / gl)
    gap = tunnel_points(centre)
    glows = []
    if gap:
        floor = tunnel_faces(centre, half, gap)[0]  # the road's asphalt through it
        kerbs.append(floor); mats.append(ASPHALT)
        for fs, mat in garage.faces(centre, half) + garage.yard_faces(centre, half):  # the shop, its yard, fence and warehouses
            if fs: kerbs.append(fs); mats.append(mat)
        print('garage: %.0f m by %.0f m, %.1f m high, its road %.0f m' % (garage.U1 - garage.U0, garage.V1 - garage.V0, garage.TOP, 2 * len(gap)))
    # ground where nothing is drawn beside the new stretches (the void showed past the edges)
    skirts = void_ground(res_bytes, centre, half, dist, sorted({i for r in runs(off) for i in r}), hide)
    def other_leg(q, own=25, reach=12.0):  # within `reach` of the road of a part of the loop not its own
        d = np.hypot(centre[:, 0] - q[0], centre[:, 2] - q[2])
        k, n = int(np.argmin(d)), len(centre)
        apart = np.abs((np.arange(n) - k + n // 2) % n - n // 2)
        return bool(np.any((apart > own) & (d < half + reach)))
    def foot_of(f, k):
        return min((np.asarray(f[k][0], float), np.asarray(f[k + 1][0], float)), key=lambda q: np.min(np.hypot(centre[:, 0] - q[0], centre[:, 2] - q[2])))
    n_sk = len(skirts)
    skirts = [f for f in skirts if not any(np.hypot(foot_of(f, k)[0] - HAIRPIN[0], foot_of(f, k)[2] - HAIRPIN[1]) < HAIRPIN_R + 25 or other_leg(foot_of(f, k))
                                           or garage.inside(foot_of(f, k)[[0, 2]], pad=3.0) for k in range(0, len(f), 2))]
    print('ground over the void: %d of %d stretches dropped (at the hairpin, or by another part of the loop)' % (n_sk - len(skirts), n_sk))
    kerbs += [[f] for f in skirts]
    mats += [ASPHALT] * len(skirts)
    # and a concrete wall along each, on the barrier's line, to hide what lies past it
    masks = 0
    for f in skirts:
        # each pair's end nearer the road: the wall's foot
        feet = [foot_of(f, k) for k in range(0, len(f), 2)]
        keep, stack = {0, len(feet) - 1}, [(0, len(feet) - 1)]  # the line within 1 m (a chord cut into a bend)
        F = np.array(feet)
        while stack:
            a0, b0 = stack.pop()
            if b0 - a0 < 2: continue
            d = F[b0] - F[a0]; rel = F[a0 + 1:b0] - F[a0]
            off_ = np.linalg.norm(rel - np.outer(rel @ d / max(d @ d, 1e-12), d), axis=1)
            k = int(np.argmax(off_))
            if off_[k] > 1.0: keep.add(a0 + 1 + k); stack += [(a0, a0 + 1 + k), (a0 + 1 + k, b0)]
        pts = [F[k] for k in sorted(keep)]
        for a, b in zip(pts[:-1], pts[1:]):
            if np.hypot(*(b - a)[[0, 2]]) > 1:
                mid = (a + b) / 2
                road = centre[int(np.argmin(np.hypot(centre[:, 0] - mid[0], centre[:, 2] - mid[2])))][[0, 2]]
                beam, posts = guard_strips(tuple(a + (0, 0.06, 0)), tuple(b + (0, 0.06, 0)), road)
                kerbs += [beam, posts]; mats += [GUARD, POST]; masks += 1  # a guardrail: the 3 m concrete was everywhere
    print('walls hiding bare ground: %d' % masks)
    print('ground over the void beside the road: %d stretches' % len(skirts))
    # each face simplified, then in pieces the size of buffers the scenery keeps loaded (the svb's):
    # larger ones stream in with their own part of the track only, and were never drawn here
    faces, fmats = [], []
    for fs, mat in zip(kerbs, mats):
        for f in fs: faces.append(f if mat == HEAD else simplify(f)); fmats.append(mat)
    svb_raw = bytearray(zlib.decompress(open(os.path.join(folder, 'quickpreview1.xbp.svb'), 'rb').read()))
    svb = read_svb(svb_raw)
    print('scenery moved out of the garage: %d vertices' % clear_tunnel(res_bytes, centre, half, tunnel_points(centre), svb, svb_raw, keep={L.DONOR}))
    near = near_meshes(res_bytes, centre[sorted({i for r in runs(off) for i in r})], 50.0) - hide
    # every part of each object it shows at all (a landmark drawn in part, its rest left out: the
    # cells' lists were made for Pacific Shipyards II's course)
    whole = {i for i in object_parts(res_bytes, shown | near) - hide - shown - near if mesh_extent(res_bytes, i) > 8.0}  # landmarks' pieces
    print('drawn whole: %d parts of objects shown in part' % len(whole))
    near |= whole
    print('drawn as well, within 50 m of the new stretches: %d meshes' % len(near - shown))
    # the meshes whose textures the new faces take: drawn where they are, so their textures are
    # loaded in full (else only the stx's 32-texel copies: the garage's tin was a blur), and never
    # borrowed themselves
    sources = {int(m) for m in fmats if m is not None} | {SIDEWALK}
    pool = donor_pool(res_bytes, shown | near | {L.DONOR} | sources, ppw, set(svb))
    have = len(pool)
    placed = pack(faces, pool, fmats)
    print('pieces: %d faces, %d vertex pairs, in %d of %d loaded meshes' % (len(faces), sum(len(f) for f in faces) // 2, len(placed), have))
    picked = [(mesh, at) for mesh, at, _, _ in placed]
    kerbs = [pieces for _, _, pieces, _ in placed]
    mats = [m for _, _, _, m in placed]
    # the lamps' glows, each in a glow from far off moved to its lamp
    gpool = glow_pool(res_bytes, shown | near | hide, ppw, set(svb), len(glows[0][0]) if glows else 0, len(glows[0][1]) if glows else 0) if gap else []
    print('lamp glows: %d of %d spare glows' % (min(len(glows), len(gpool)), len(gpool)))
    glowed = list(zip(gpool, glows))
    ppw = bytearray(ppw)
    at = sphere_at(bytes(ppw), *road_was)  # the strip's road: its sphere where the donor was, moved too
    if at is None: print('  the strip road: bounding sphere not found, it may be culled')
    else: struct.pack_into('<4f', ppw, at, road_now[1], *road_now[0])
    for (mesh, at), fs, mat in zip(picked, kerbs, mats):
        c1, r1 = write_strips(res_bytes, mesh, fs, material=mat, light={ASPHALT: road_light, LAMP: lamp_light, RAIL: rail_light, HEAD: head_light, GUARD: guard_light, POST: post_light}.get(mat, (-32724, -32645) if mat is None else lightmap_st(res, mat)))
        struct.pack_into('<4f', ppw, at, r1, *c1)
    for (mesh, at), (gdata, gidx) in glowed:
        c1, r1 = write_glow(res_bytes, mesh, gdata, gidx)
        struct.pack_into('<4f', ppw, at, r1, *c1)
    ppw = bytes(ppw)
    for mesh, _ in picked + [g for g, _ in glowed]:  # the svb's copies of the rewritten buffers too
        a_ = struct.unpack_from('<I', res_bytes, L.MODEL + 4 + 4 * mesh)[0]
        _, _, nidx, vbytes, vb = struct.unpack_from('<IIIIH', res_bytes, L.MODEL + a_)
        o, sz = svb[vb]
        ro = L.vb_offset(res_bytes, vb)
        assert sz == vbytes + 2 * nidx, (mesh, sz, vbytes, nidx)
        svb_raw[o:o + sz] = res_bytes[ro:ro + sz]
    print('kerbs: %d stretches, %.0f m of edge; %d walls across the course; in meshes %s' % (
        len(stretches), sum(2 * len(i) for _, i in stretches), len(walls), [m for m, _ in picked]))
    for side, idx in stretches:
        print('  %s edge, %3.0f m from (%.0f, %.0f) to (%.0f, %.0f)' % ('left' if side > 0 else 'right', 2 * len(idx), centre[idx[0]][0], centre[idx[0]][2], centre[idx[-1]][0], centre[idx[-1]][2]))
    # the evening: the street lamps' glows off (the tunnel's own kept), the lightmaps and sky
    dark = evening.lamp_glows(res_bytes, L.MODEL) - {g for (g, _), _ in glowed}
    hide |= dark
    lifted, sky = evening.apply(res_bytes)
    print('evening: %d lightmaps lifted, %d sky texels, %d lamp glows off' % (lifted, sky, len(dark)))
    n_cells = len(cells_in)
    # the garage's parked vehicles, moved in from far off
    import xb2
    parked, ppw = garage.park(res_bytes, centre, svb, svb_raw, ppw, xb2.resources(bytes(res_bytes))[0], L.MODEL, pack_normal, unpack_normal, sphere_at)
    hide -= set(parked)
    print('garage: %d parked vehicle meshes' % len(parked))
    pvs, sizes = L.loop_pvs(pvs_in, [list(range(0, 8))] * n_cells, extra=[L.DONOR] + [m for m, _ in picked] + [g for (g, _), _ in glowed] + sorted(near - shown - dark) + parked + sorted(sources - hide), hide=hide)
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
    # the scenery's low-resolution textures (drawn while the full ones are not loaded) the evening's too
    import xb2
    rev_stx = os.path.join(disc, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs.stx')
    stx, lms, sky_ = evening.stx(open(rev_stx, 'rb').read(), xb2.resources(bytes(res_bytes))[0])
    open(os.path.join(mods, 'track', L.TAG, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs.stx'), 'wb').write(stx)
    print('evening: %d low-resolution lightmaps lifted, %d sky texels' % (lms, sky_))
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
