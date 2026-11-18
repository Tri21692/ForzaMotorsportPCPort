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
STRIP_OPEN, STRIP_OPEN_SIDE = 25.0, -1  # m of the strip from the junction left open on its north-east side (-1: right of the way round)
JUNCTION_CORNER = (-455.0, -236.0, -437.5, -228.0)  # x0, z0, x1, z1: the course's kerb wall round the junction's north-east corner
STRIP = [(-462, -232), (-636, -114), (-655, -104)]  # straight: warehouse 14 to its south-west, the long green
# building to its north-east; the junction's low walls on it are hidden and cut

# the course's branches the loop does not take, closed by walls across them
CLOSED = (553, 596)  # (509, 20 m west of the hairpin's apex, closed the old road there: its wall read as a ledge across the hairpin, and is gone)
# and the course south-east of the junction closed a metre past the crosswalk there (lines_road_final_09's
# quad, (-434, -262) to (-425, -248)), not at 566 60 m on: the road looked open up to an invisible wall
KERB_SPOTS, KERB_R = [(-445.0, -224.0)], 35.0  # the course's kerbs walled round these (x, z): the junction's sidewalk, the user's shot
CLOSED_AT = [((-434.3, -263.3), (-423.2, -246.9))]

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
    pts += [(x, z, ground_y(sp, x, z)) for x, z in STRIP[:-1]]
    # its end at the old road's height where it joins it (the nearest course point was down the old
    # road's slope west, 0.4 m lower: the strip's end sank under the old road, a step at the hairpin)
    pts.append((*STRIP[-1], c[OLD_ROAD][1]))
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


def drawn_heights(res, centre, off, blend=None):
    """The loop's centre with its height, off the course, taken from the drawn ground under it (a
    side road, lot or sidewalk: the road there is drawn lower than the course, and sloping), and
    where nothing is drawn (the gap, the strip) or at the points `blend` (a mask) blended along the
    loop from either side."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - 10, centre[:, [0, 2]].max(0) + 10
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: nm.startswith(GROUND) and 'lines_' not in nm, (*lo, *hi))
            if facing_up(t)]  # any slope: side road 39's triangles fall 1.8 m along their 250 m
    bb = np.array([[t[:, 0].min(), t[:, 0].max(), t[:, 2].min(), t[:, 2].max()] for t in tris])
    y = centre[:, 1].copy()
    known = ~off.copy()
    for i in np.nonzero(off & (True if blend is None else ~blend))[0]:
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


def sidewalk_edges(res, centre, half, dist, hidden=(), reach=8.0, rise=(0.06, 0.6)):
    """For the (side, point)s of `dist`, where the drawn ground first steps up a sidewalk's height
    (`rise`) going out from the road's edge, short of the wall there (or, with no drawn boundary at
    half + WIDE, within `reach` m past it): the wall at that kerb, so a car keeps off the sidewalk
    (a guardrail across the asphalt short of one was a fence in the road; a wall at the building
    behind one let cars drive along it). {(side, i): distance}."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = centre[:, [0, 2]].min(0) - reach - 10, centre[:, [0, 2]].max(0) + reach + 10
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: True, (*lo, *hi)) if i not in hidden and facing_up(t)]
    cells = {}
    for k, t in enumerate(tris):
        for gx in range(int(np.floor(t[:, 0].min() / 5)), int(np.floor(t[:, 0].max() / 5)) + 1):
            for gz in range(int(np.floor(t[:, 2].min() / 5)), int(np.floor(t[:, 2].max() / 5)) + 1):
                cells.setdefault((gx, gz), []).append(k)
    def height(x, z, y):
        """The drawn ground's height at (x, z): the highest within a metre of y, or None."""
        best = None
        for k in cells.get((int(np.floor(x / 5)), int(np.floor(z / 5))), ()):
            a, b, c = tris[k]
            m = np.array([[b[0] - a[0], c[0] - a[0]], [b[2] - a[2], c[2] - a[2]]])
            if abs(np.linalg.det(m)) < 1e-9: continue
            u, v = np.linalg.solve(m, [x - a[0], z - a[2]])
            if u < -1e-4 or v < -1e-4 or u + v > 1 + 1e-4: continue
            h = a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])
            if abs(h - y) < 1.0 and (best is None or h > best): best = h
        return best
    left, _ = frame(centre)
    out = {}
    for (side, i), d in dist.items():
        # from a metre inside the road's edge outward: where nothing is drawn at the edge, past the
        # old wall as far as `reach`; where something is (a building or fence behind a sidewalk), up
        # to it. The kerb is a step up of a sidewalk's height within a quarter metre (a slope or the
        # road's camber is no step), and the wall stands on it: the sidewalk is not road.
        bare = abs(d - (half[i] + WIDE)) < 1e-6
        prev = None
        for u in np.arange(max(half[i] - 1.0, 1.0), half[i] + reach if bare else d - 0.3, 0.25):
            p = centre[i][[0, 2]] + left[i] * side * u
            h = height(p[0], p[1], centre[i][1] if prev is None else prev)
            if h is not None and rise[0] < h - (centre[i][1] if prev is None else prev) < rise[1]:  # (with
                # nothing drawn before it, the first ground a sidewalk's height over the road: by the strip
                # the void lay between its road and the sidewalk, and the wall went on behind it)
                out[(side, i)] = float(u) - 0.2
                break
            if h is not None: prev = h
    # only runs of 6 points or more (a lone point's kerb was a lamp's plinth or a step)
    keep = {}
    for side in (1, -1):
        idx = sorted(i for s, i in out if s == side)
        run = []
        for i in idx + [None]:
            if i is not None and (not run or i == run[-1] + 1): run.append(i); continue
            if len(run) >= 6: keep.update({(side, j): out[(side, j)] for j in run})
            run = [i] if i is not None else []
    return keep


def boundary_collision(col, centre, half, run, dist, sp, no_ground=None, no_wall=None):
    """Along an off-course run: walls (both faces, 4 m high from below the road) on the drawn
    boundary each side (`dist`, as boundaries()) where they stand off the course's road (at the
    joins the course's own walls) but at the (side, point)s `no_wall`, and ground out to them and
    a metre over."""
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
            if np.all(L.off_course([a, b], sp)) and np.all(into_road(centre, half, span) < -0.5) and not (no_wall and ((side, i) in no_wall or (side, j) in no_wall)):
                wall([a + (0, -1, 0), b + (0, -1, 0), b + (0, 3, 0), a + (0, 3, 0)])
        if no_ground is not None and (no_ground[i] or no_ground[j]): continue  # not here (the hairpin: flat quads over the old road made a ledge)
        g = lambda side, k: min(dist[(side, k)], half[k] + 8) + 1  # no wider: over the course it made bumps
        q = [centre[i] + L3[i] * g(1, i), centre[i] - L3[i] * g(-1, i),
             centre[j] - L3[j] * g(-1, j), centre[j] + L3[j] * g(1, j)]
        col.add_ground(0, [q[0], q[1], q[2]]); col.add_ground(0, [q[2], q[3], q[0]])  # (one faced down: a car fell through it)
        for side in (1, -1):  # and on to 3 m behind the wall, off the course (a car put through a wall fell)
            a0, b0 = g(side, i), g(side, j)
            a1, b1 = dist[(side, i)] + 3.0, dist[(side, j)] + 3.0
            if a1 <= a0 and b1 <= b0: continue
            p = [centre[i] + L3[i] * side * a0, centre[j] + L3[j] * side * b0, centre[j] + L3[j] * side * max(b1, b0), centre[i] + L3[i] * side * max(a1, a0)]
            if not np.all(L.off_course(p, sp)): continue
            for tri in ([p[0], p[1], p[2]], [p[2], p[3], p[0]]):
                nrm = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                col.add(0, tri if nrm[1] > 0 else [tri[0], tri[2], tri[1]])  # facing up


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


BRICK = 178          # wall03_vb0: barrier_brickwall_01 (texture 310), 75 a metre along, 153 up
OLD_ROAD_END = 509   # the old road west of the hairpin closed here, 17 m from the loop, by a brick wall
                     # (it led on where the sprint went; a low concrete one here read as a ledge, a brick
                     # wall at 506, 34 m out, was too far to tell)
BRICK_H = 3.0
CORNER, CORNER_R, CORNER_SIDE = (-58.0, -376.0), 24.0, 1  # the corner from side road 04 onto 31: a brick wall all round its
                                                          # outside (+1) on the walls' line (the road looked to go on ahead)


BRICK_ENDS = []  # every brick wall's (a, b) feet, for join_bricks


def brick_wall(a, b, height=BRICK_H):
    """A brick wall from a to b ((x, y, z), its foot), both faces, half a metre into the ground: as
    kerb_strips' faces. Only where no brick wall stands on its line yet (BRICK_SAME): the turns'
    barriers, the void's, the invisible walls', fill_bricks' and join_bricks' walls were laid over
    one another along side road 04 (the audit of 17 Nov: the same bricks twice or three times in one
    plane, or 8 cm apart, to flicker); what is left of it in pieces, [] when all of it stands."""
    a, b = np.array(a, float), np.array(b, float)
    d = b - a; d[1] = 0; L_ = np.linalg.norm(d)
    if L_ < 1e-6: return []
    d /= L_
    n = np.array([-d[2], 0.0, d[0]])
    keep = [(0.0, L_)]
    for p, q in BRICK_ENDS:
        e = q - p; e[1] = 0; le = np.linalg.norm(e)
        if le < 1e-6 or abs(np.dot(e / le, n)) > 0.2: continue                 # (not along it)
        t0, t1 = sorted((float(np.dot(p - a, d)), float(np.dot(q - a, d))))
        t0, t1 = max(t0, 0.0), min(t1, L_)
        if t1 - t0 < 0.02: continue
        # the stretch they share, in quarter metres: each where the other is within BRICK_SAME of this
        # wall's plane, its foot at this one's height (two chords of one wall's line cross at a small
        # angle: the same plane at the crossing, 20 cm apart at an end)
        ts = np.linspace(t0, t1, max(2, int((t1 - t0) / 0.25) + 1))
        same = []
        for t in ts:
            o = p + (q - p) * np.clip(np.dot(a + d * t - p, e) / le ** 2, 0, 1)
            same.append(abs(float(np.dot(o - a, n))) <= BRICK_SAME and abs(a[1] + (b[1] - a[1]) * t / L_ - o[1]) <= 0.4)
        k = 0
        while k < len(ts):
            if not same[k]: k += 1; continue
            j = k
            while j + 1 < len(ts) and same[j + 1]: j += 1
            c0, c1 = ts[k], ts[j]
            if j > k: keep = [(u0, u1) for k0, k1 in keep for u0, u1 in ((k0, min(k1, c0)), (max(k0, c1), k1)) if u1 - u0 > 0.02]
            k = j + 1
    faces = []
    for k0, k1 in keep:
        pa, pb = a + (b - a) * k0 / L_, a + (b - a) * k1 / L_
        BRICK_ENDS.append((pa, pb))
        for nn in (n, -n):
            pairs = []
            for u in np.linspace(k0, k1, max(2, int((k1 - k0) / 4) + 1)):
                p = a + (b - a) * u / L_
                s = -32768 + 75 * u
                pairs.append(((p + (0, height, 0), nn, s, -32768), (p + (0, -0.5, 0), nn, s, -32768 + 153 * (height + 0.5))))
            a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
            if np.dot(np.cross(b0 - a0, a1 - a0), nn) > 0: pairs = [(q, p) for p, q in pairs]
            faces.append([v for pr in pairs for v in pr])
    return faces


BRICK_SAME = 0.12  # a brick wall within this of another's plane is the same wall (m)


BRICK_AREA = (-160.0, -4.5, -80.0, 60.0)  # garage (u0, u1, v0, v1): east of the shop (to its east wall: past it bricks stood inside, between the tin), side road 04 to its corner with 31 and the
                                         # yard's east end, where the edges have brick walls, not guardrails (they looked rough
                                         # there; a 3 m wall hides what lay past them)


def fill_bricks(centre, dist, points, sp):
    """In BRICK_AREA, brick walls along the walls' line wherever none stands yet (the bricks are the
    guardrails' there, and none stood where a guardrail was left out: through turns, by kerbs; the
    user saw past the gaps). Each run of bare stretches between neighbouring points is walled. [faces]."""
    left, _ = frame(centre)
    segs = [(a[[0, 2]], b[[0, 2]]) for a, b in BRICK_ENDS]
    def near(a, b, p):
        t = np.clip((p - a) @ (b - a) / max((b - a) @ (b - a), 1e-9), 0, 1)
        return np.hypot(*(a + (b - a) * t - p)) < 0.6
    def covered(p, q):  # one brick along the stretch p-q: its ends and middle by the same brick (one
        # across a jog's middle at an angle had the jog counted covered)
        return any(near(a, b, p) and near(a, b, q) and near(a, b, (p + q) / 2) for a, b in segs)
    out = []
    for side in (1, -1):
        feet = {}
        for i in points:
            if (side, i) not in dist: continue
            F = centre[i] + np.array([left[i][0], 0, left[i][1]]) * side * dist[(side, i)]
            u, v = garage.to_uv(F[[0, 2]])
            if BRICK_AREA[0] < u < BRICK_AREA[1] and BRICK_AREA[2] < v < BRICK_AREA[3]: feet[i] = F  # (on the course's road too: the wall stands there all the same, and was bare where side road 04 meets it)
        # each stretch between neighbouring points with no brick at its middle (a jog between two
        # points by bricks was a gap: by points alone it counted covered)
        bare = [i for i in sorted(feet) if i + 1 in feet and not covered(feet[i][[0, 2]], feet[i + 1][[0, 2]])]
        runs_ = []
        for i in bare:
            if runs_ and i == runs_[-1][-1]: runs_[-1].append(i + 1)
            else: runs_.append([i, i + 1])
        for r in runs_:
            F_ = np.array([feet[i] for i in r])
            for a, b in zip(*(lambda k: (k[:-1], k[1:]))(chords(F_, 0.5))):
                if np.hypot(*(F_[b] - F_[a])[[0, 2]]) > 0.3: out.append(brick_wall(tuple(F_[a]), tuple(F_[b])))
    return out


def join_bricks(centre, half, reach=12.0):
    """Brick walls closing the gaps between brick walls (where the walls' line jogged or one run of
    them ended and the next began, the ground past them showed): each end joined to the nearest end
    of another within `reach` m, where the join keeps off the road. [faces]."""
    ends = [(k, e, seg[e]) for k, seg in enumerate(BRICK_ENDS) for e in (0, 1)]
    out, done = [], set()
    for k, e, p in ends:
        best = None
        for k2, e2, q in ends:
            if k2 == k: continue
            d = np.hypot(*(q - p)[[0, 2]])
            if d < 0.3: best = None; break  # already meets one
            if d < reach and (best is None or d < best[0]): best = (d, k2, e2, q)
        if best is None or frozenset(((k, e), best[1:3])) in done: continue
        q = best[3]
        line = np.array([p[[0, 2]] + (q - p)[[0, 2]] * t for t in np.linspace(0, 1, 9)])
        if np.any(into_road(centre, half, line) > -0.5): continue
        done.add(frozenset(((k, e), best[1:3])))
        out.append(brick_wall(tuple(p), tuple(q)))
    return out


def barrier(a, b, road):
    """A guardrail from a to b ((x, y, z) feet, facing `road`), or in BRICK_AREA a brick wall:
    [(faces, material)]."""
    u, v = garage.to_uv(((np.asarray(a, float) + np.asarray(b, float)) / 2)[[0, 2]])
    if BRICK_AREA[0] < u < BRICK_AREA[1] and BRICK_AREA[2] < v < BRICK_AREA[3]:
        return [(brick_wall(a, b), BRICK)]
    beam, posts = guard_strips(a, b, road)
    return [(beam, GUARD), (posts, POST)]


GUARD, POST = 1895, 1084  # guardrail09 (barrier_guardrail_rusty_01) and guardrailposts25 (wood): the turns' guardrail
GUARD_Y = (0.25, 0.50)     # its beam, from and to (m over the ground)
POST_EVERY = 16.0  # (every 8 m was more than the borrowed meshes hold once every invisible wall had a guardrail; the beam reads the same)
ROAD_PLAIN = 535           # sidewalk22_vb0: road__cs_road_plain_01 (texture 867), the side roads' concrete; the garage's road
ROAD_PLAIN_S, ROAD_PLAIN_T = 20.0, 22.0  # its texture a metre across and along (as the side roads have it, about)
RETEXTURE = {GUARD: POST,  # the guardrail's texture drawn the posts' way (its own, a primitive 13's, drew black as strips)
             ROAD_PLAIN: L.DONOR}  # and the side roads' drawn the asphalt's way (theirs take 28-byte vertices)


def guard_strips(a, b, road, every=None):
    """A guardrail from a to b ((x, y, z), its foot) as the turns have, facing `road` (x, z): the
    beam (its texture across the beam's profile, along it 242 a metre) and a post every POST_EVERY m
    behind it, each a quad (one face: both, and posts every 4 m, were more than the borrowed meshes
    hold; `every` m apart if given). (beam faces, post faces) as kerb_strips' faces."""
    every = every or POST_EVERY
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
    for k in range(int(L_ / every) + 1):
        p = np.add(a, d * min(k * every, L_)) - n * 0.12  # behind the beam
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


def wide_tris(res, hidden, lo, hi):
    """The level triangles ((3, 3)) of the meshes mesh_tris does not read, within the box lo, hi (x, z):
    the course's roads and the side roads (28-byte vertices; blender_export reads them)."""
    import struct
    import xb2
    import blender_export
    names, _ = xb2.resources(bytes(res))
    out = []
    for i in range(struct.unpack_from('<I', res, L.MODEL)[0]):
        if i in hidden: continue
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * i)[0]
        fl, _, _, vbytes, vb, stride, prim = struct.unpack_from('<IIIIHHH', res, L.MODEL + a)
        if not (9 <= vb < len(names) + 9) or stride != 6 or not vbytes or not (fl & 0x1004 or vbytes % 24): continue
        g = blender_export.mesh_geometry(res, names, i)
        if g is None: continue
        v = g[0]
        if v[:, 0].max() < lo[0] or v[:, 0].min() > hi[0] or v[:, 2].max() < lo[1] or v[:, 2].min() > hi[1]: continue
        out += [v[k] for k in g[2] if facing_up(v[k])]
    return out


def ground_test(res, hidden, lo, hi, wide=False):
    """drawn(x, z, y): whether the scenery (but the meshes `hidden`) draws ground at (x, z) near
    height y (from 3 m under it to 1.5 m over: a roof is no ground), within the box lo, hi (x, z).
    `wide`: the side roads' and the course's own road meshes counted too (wide_tris): without them
    edge_ground laid 870 m2 of asphalt on the strip's side road, level with its concrete to 14 mm,
    to flicker (the audit of 17 Nov)."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: True, (*lo, *hi)) if i not in hidden and facing_up(t)]
    if wide: tris += wide_tris(res, hidden, lo, hi)
    cells = {}
    for k, t in enumerate(tris):
        for gx in range(int(np.floor(t[:, 0].min() / 5)), int(np.floor(t[:, 0].max() / 5)) + 1):
            for gz in range(int(np.floor(t[:, 2].min() / 5)), int(np.floor(t[:, 2].max() / 5)) + 1):
                cells.setdefault((gx, gz), []).append(k)
    def drawn(x, z, y):
        for k in cells.get((int(np.floor(x / 5)), int(np.floor(z / 5))), ()):
            if y - 3 < tris[k][:, 1].mean() < y + 1.5 and L.in_quad((x, z), [(q[0], q[2]) for q in tris[k]]): return True
        return False
    return drawn


def void_ground(res, centre, half, dist, where, hidden, out=40.0):
    """Ground (strip faces) beside the loop points `where` wherever nothing is drawn: from the wall
    (`dist`) out `out` m, a little under the road, each side, in runs; drawn ground anywhere across
    that keeps a point out of them. [(side, its loop points, face)], the face a pair of vertices a
    point."""
    lo, hi = centre[:, [0, 2]].min(0) - out - 10, centre[:, [0, 2]].max(0) + out + 10
    drawn = ground_test(res, hidden, lo, hi)
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
                faces.append((side, run, [v for pr in pairs for v in pr]))
            run = []
    return faces


def edge_ground(drawn, centre, half, dist, where, sp, past=12.0, reach=22.0, skip=()):
    """Ground (strip faces, asphalt) at the road's edge beside the loop points `where` wherever
    nothing is drawn between the edge and `past` m beyond the wall (no more than `reach` m from the
    edge), out to the last bare probe: void_ground looks 13 m out and more, and the void showed in
    slivers between the side roads and the lots beside them (outside the corner onto side road 04 a
    wedge past the wall). Not over the course's road (drawn, in meshes too wide for mesh_tris)."""
    left, _ = frame(centre)
    up = np.array([0.0, 1.0, 0.0])
    faces = []
    for side in (1, -1):
        run = []
        for i in list(where) + [None]:
            if i is not None and (side, i) not in skip:
                out = min(dist.get((side, i), half[i] + WIDE) + past, half[i] + reach)
                us = np.arange(half[i] - 2.5, out + 1e-6, 1.0)  # (from inside the half: side road 04's concrete ends 1.2 m short of it, and 2 m lay bare before its brick wall, 18 Nov)
                l2 = left[i] * side
                pts = [centre[i][[0, 2]] + l2 * u for u in us]
                bare = [u for u, p in zip(us, pts) if not drawn(p[0], p[1], centre[i][1])]
                if bare and np.all(L.off_course([(p[0], centre[i][1], p[1]) for p in pts], sp, margin=0.0)):
                    # (from just inside the first bare probe, not the road's edge: laid from the edge it lay on
                    # the strip's drawn side road as far as the bare ground past it, level with it, 17 Nov)
                    run.append((i, max(bare) + 0.5, max(min(bare) - 1.0, half[i] - 3.0))); continue
            if len(run) >= 2:
                pairs = []
                for j, w, w0 in run:
                    l3 = np.array([left[j][0], 0, left[j][1]]) * side
                    a = centre[j] + l3 * w0 + (0, -0.03, 0)
                    b = centre[j] + l3 * w + (0, -0.03, 0)
                    pairs.append(((a, up, -32000 + 53.0 * (a[0] % 600), -32000 + 51.7 * (a[2] % 600)),
                                  (b, up, -32000 + 53.0 * (b[0] % 600), -32000 + 51.7 * (b[2] % 600))))
                a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
                if np.dot(np.cross(b0 - a0, a1 - a0), up) > 0: pairs = [(q, p) for p, q in pairs]
                faces.append([v for pr in pairs for v in pr])
            run = []
    return faces


HAIRPIN_OUT = (-690.0, -146.0, -658.0, -103.0)  # x0, z0, x1, z1: outside the hairpin, between the strip's asphalt and the old
# road's sidewalk west of it, nothing was drawn ((-662..-676, -105..-115) and (-666..-686, -115..-144): the audit of 17 Nov)


def bare_ground(res, hidden, centre, box, sp, cell=2.0, under=0.06):
    """Ground (strip faces, asphalt) over every `cell` m square of `box` (x0, z0, x1, z1) where nothing
    is drawn at its middle or a corner: in rows, their corners shared, each at the height of what is
    drawn within 3 m of it (the old road's sidewalk falls away west) or else the loop's there, `under`
    m under it; not over the course's road (drawn, in meshes mesh_tris does not read). void_ground and
    edge_ground leave the hairpin out (its edges fan apart)."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    lo, hi = np.array(box[:2]) - 6, np.array(box[2:]) + 6
    tris = [t for i, nm, t in mesh_tris(res, names, lambda nm: True, (*lo, *hi)) if i not in hidden and facing_up(t)]
    drawn = GroundMap(tris + wide_tris(res, hidden, lo, hi))
    xs, zs = np.arange(box[0], box[2] + 1e-6, cell), np.arange(box[1], box[3] + 1e-6, cell)
    c2 = centre[:, [0, 2]]
    Y = np.zeros((len(zs), len(xs))); seen = np.zeros((len(zs), len(xs)), bool)
    for a, z in enumerate(zs):
        for b, x in enumerate(xs):
            y = centre[int(np.argmin(np.hypot(c2[:, 0] - x, c2[:, 1] - z)))][1]
            h = drawn.top(x, z, y, under=3.0)
            seen[a, b] = h is not None
            if h is None:
                for r in (1.5, 3.0):
                    hs = [v for v in (drawn.top(x + dx * r, z + dz * r, y, under=3.0) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7))) if v is not None]
                    if hs: h = float(np.mean(hs)); break
            Y[a, b] = (y if h is None else h) - under
    up = np.array([0.0, 1.0, 0.0])
    mids = [(xs[b] + cell / 2, 0.0, zs[a] + cell / 2) for a in range(len(zs) - 1) for b in range(len(xs) - 1)]
    clear = L.off_course(mids, sp, margin=0.5).reshape(len(zs) - 1, len(xs) - 1)
    faces = []
    for a in range(len(zs) - 1):
        bare = [bool(clear[a, b]) and not (seen[a:a + 2, b:b + 2].all() and drawn.top(xs[b] + cell / 2, zs[a] + cell / 2, Y[a, b], under=3.0) is not None) for b in range(len(xs) - 1)]
        b = 0
        while b < len(bare):
            if not bare[b]: b += 1; continue
            e = b
            while e < len(bare) and bare[e]: e += 1
            pairs = []
            for k in range(b, e + 1):
                p, q = np.array([xs[k], Y[a, k], zs[a]]), np.array([xs[k], Y[a + 1, k], zs[a + 1]])
                pairs.append(((p, up, -32000 + 53.0 * (p[0] % 600), -32000 + 51.7 * (p[2] % 600)),
                              (q, up, -32000 + 53.0 * (q[0] % 600), -32000 + 51.7 * (q[2] % 600))))
            a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
            if np.dot(np.cross(b0 - a0, a1 - a0), up) > 0: pairs = [(q, p) for p, q in pairs]
            faces.append([v for pr in pairs for v in pr])
            b = e
    return faces


def standing_test(res, hidden, faces, lo, hi):
    """seen(x, z, y): whether anything drawn stands within a metre of (x, z), from a kerb's height
    over y to a car's roof: the scenery's upright faces (but the meshes `hidden`) and the new
    `faces` (lists of (position, ...) vertices) with height to them."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    pts = []
    for i, nm, t in mesh_tris(res, names, lambda nm: True, (*lo, *hi)):
        if i in hidden or facing_up(t): continue
        if garage.inside(t.mean(0)[[0, 2]], pad=3.0): continue  # moved out of the garage after (clear_tunnel)
        a, b = footprint(t)
        for u in np.linspace(0, 1, max(2, int(np.hypot(*(b - a)) / 0.5) + 1)):
            pts.append((*(a + (b - a) * u), t[:, 1].min(), t[:, 1].max()))
    for f in faces:
        q = np.array([v[0] for v in f], float)
        if np.ptp(q[:, 1]) < 0.3: continue
        for k in range(0, len(q) - 1):
            pts.append((q[k][0], q[k][2], q[:, 1].min(), q[:, 1].max()))
    P = np.array(pts)
    cells = {}
    for k, key in enumerate(map(tuple, np.floor(P[:, :2] / 2).astype(int))): cells.setdefault(key, []).append(k)
    def seen(x, z, y):
        gx, gz = int(np.floor(x / 2)), int(np.floor(z / 2))
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for k in cells.get((gx + dx, gz + dz), ()):
                    if np.hypot(P[k, 0] - x, P[k, 1] - z) < 1.0 and P[k, 2] < y + 1.5 and P[k, 3] > y + 0.1: return True
        return False
    return seen


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


def chords(F, tol):
    """The indices of points F (n x 3) to keep so the line through them is within `tol` of all of
    them (a chord cut into a bend where it strays further)."""
    keep, stack = {0, len(F) - 1}, [(0, len(F) - 1)]
    while stack:
        a0, b0 = stack.pop()
        if b0 - a0 < 2: continue
        d = (F[b0] - F[a0])[[0, 2]]; rel = (F[a0 + 1:b0] - F[a0])[:, [0, 2]]
        off = np.linalg.norm(rel - np.outer(rel @ d / max(d @ d, 1e-12), d), axis=1)
        k = int(np.argmax(off))
        if off[k] > tol: keep.add(a0 + 1 + k); stack += [(a0, a0 + 1 + k), (a0 + 1 + k, b0)]
    return sorted(keep)


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
    src = SIDEWALK if material is None else material
    sa = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * RETEXTURE.get(src, src))[0]
    sfl, _, _, _, _, _, _, st0, st1, ssh = struct.unpack_from('<IIIIHHHHHH', res, L.MODEL + sa)
    if src in RETEXTURE:  # another mesh's way of drawing, this one's texture
        st0 = struct.unpack_from('<H', res, L.MODEL + struct.unpack_from('<I', res, L.MODEL + 4 + 4 * src)[0] + 22)[0]
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
TURN2_EXIT = (-156.0, -342.0)  # where the loop leaves the course at Turn 2 for side road 31
TURN2_GAP = ((-150.6, -329.5), (-148.2, -333.0))  # between the end of the course's wall there and side road 31's: a
                                                  # car's way behind both, onto ground that ends in the void
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
EDGE_PAD, EDGE_MORE = 0.5, 6.0   # on the new road and round the hairpin: the edges out to the walls, this far short, at most this past the half
EDGE_WIDE = 12.0   # and at most this past the half at the joins with the course (17 Nov)
FLOOR_MORE, FLOOR_LAST = 1.6, 14   # the garage floor's last cross-sections (4 m apart, the last few 2 m) wider by this, m a side
FLOOR_ON = 4   # points (2 m each) the floor goes on past the door onto side road 39 (a void 1 m2 each side of the line there)
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
    fk += list(range(idx[-1] + 1, min(len(centre), idx[-1] + 1 + FLOOR_ON)))  # (and on out of the door onto side road 39: 17 Nov)
    PF, LF = centre[fk], np.stack([left[fk][:, 0], np.zeros(len(fk)), left[fk][:, 1]], 1)
    WF = (half[fk] + out)[:, None]
    # its last 40 m to the door onto side road 39 wider by FLOOR_MORE each side: that road's raised
    # sidewalk, moved out of the garage (clear_tunnel), left a metre of nothing between it and the floor
    # for 35 m, (-259, -693) to (-271, -722), 1.4 m from the line (the audit of 17 Nov); under the sidewalk
    WF = WF + (FLOOR_MORE * np.clip((np.arange(len(fk)) - (len(fk) - 1 - FLOOR_LAST)) / 2.0, 0, 1))[:, None]
    fl, fr = PF + LF * WF + (0, 0.03, 0), PF - LF * WF + (0, 0.03, 0)
    # in the side roads' concrete, along the road as theirs (the asphalt met them at both doors, a
    # different road)
    along = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(PF[:, [0, 2]], axis=0), axis=1))])
    tf = -32000 + ROAD_PLAIN_T * along
    floor = face(fl, fr, up, np.full(len(fk), -32000.0), tf, -32000 + ROAD_PLAIN_S * 2 * WF[:, 0], tf)
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


def lay_squares(col, squares, cell=0.25, tol=0.04, most=8.0, top=True):
    """Ground squares ((x, z, half width, y)) into the collision as few rectangles: put on a grid
    `cell` apart (the highest where they overlap, as the car found them laid one by one; the
    lowest without `top`), merged where within `tol` of a height, at most
    `most` metres a side, each at the lowest height in it. One triangle pair per square was 6,000
    triangles and 480 KB in the hairpin's block, where the game let cars fall through (the disc's
    blocks are under 20 KB). Returns rectangles laid."""
    if not squares: return 0
    S = np.array(squares, float)
    lo = (S[:, :2] - S[:, 2:3]).min(0)
    nx, nz = (np.ceil(((S[:, :2] + S[:, 2:3]).max(0) - lo) / cell)).astype(int) + 1
    H = np.full((nz, nx), -np.inf if top else np.inf)
    pick = np.maximum if top else np.minimum
    for x, z, w, y in S:  # every cell the square overlaps
        j0, j1 = int((x - w - lo[0]) / cell), int(np.ceil((x + w - lo[0]) / cell))
        i0, i1 = int((z - w - lo[1]) / cell), int(np.ceil((z + w - lo[1]) / cell))
        H[i0:i1, j0:j1] = pick(H[i0:i1, j0:j1], y)
    free = np.isfinite(H)
    span = int(most / cell)
    laid = 0
    for i in range(nz):
        for j in range(nx):
            if not free[i, j]: continue
            h0 = H[i, j]
            j1 = j + 1
            while j1 < nx and j1 - j < span and free[i, j1] and abs(H[i, j1] - h0) <= tol: j1 += 1
            i1 = i + 1
            while i1 < nz and i1 - i < span and free[i1, j:j1].all() and (np.abs(H[i1, j:j1] - h0) <= tol).all(): i1 += 1
            free[i:i1, j:j1] = False
            y = H[i:i1, j:j1].min()
            x0, x1, z0, z1 = lo[0] + j * cell, lo[0] + j1 * cell, lo[1] + i * cell, lo[1] + i1 * cell
            q = [(x1, y, z1), (x0, y, z1), (x0, y, z0), (x1, y, z0)]
            col.add(0, [q[0], q[2], q[1]]); col.add(0, [q[2], q[0], q[3]])  # facing up, as the disc's ground
            laid += 1
    return laid


def shop_floor(col, centre, step=0.5):
    """Floor in the garage wherever its box has no ground within 30 cm of the drawn floor (its north
    corners, by the parked vehicles, had none: the road's ground stops short of them). Returns the
    squares laid (lay_squares merges them)."""
    tris = []
    for _, pts, nrm, _ in col.triangles():
        q = np.array(pts, float)
        if abs(nrm[1]) > 0.7 and garage.inside(q[:, [0, 2]], pad=1.0).any(): tris.append(q)
    us, vs = np.arange(garage.U0 + step / 2, garage.U1, step), np.arange(garage.V0 + step / 2, garage.V1, step)
    uv = np.stack(np.meshgrid(us, vs), -1).reshape(-1, 2)
    fy = garage.floor_y(centre, uv)
    w = garage.to_world(uv, 0.0)[:, [0, 2]]
    found = np.zeros(len(uv), bool)
    for a, b, c in tris:
        m = np.array([[b[0] - a[0], c[0] - a[0]], [b[2] - a[2], c[2] - a[2]]])
        if abs(np.linalg.det(m)) < 1e-9: continue
        k = np.nonzero((w[:, 0] >= min(a[0], b[0], c[0])) & (w[:, 0] <= max(a[0], b[0], c[0])) & (w[:, 1] >= min(a[2], b[2], c[2])) & (w[:, 1] <= max(a[2], b[2], c[2])))[0]
        if not len(k): continue
        u, v = np.linalg.solve(m, (w[k] - a[[0, 2]]).T)
        h = a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])
        found[k[(u >= -1e-4) & (v >= -1e-4) & (u + v <= 1 + 1e-4) & (np.abs(h - fy[k]) < 0.3)]] = True
    # squares in world x/z round each bare point, as wide as the point's spacing on the diagonal
    squares = [(p[0], p[1], step * 0.75, y) for p, y in zip(w[~found], fy[~found])]
    lay_squares(col, squares, tol=0.02)
    return len(squares)


def fill_ground(col, centre, half, dist, where, step=1.0, margin=15, under=0.0):
    """Ground where the collision has none, out to the walls (`dist`) beside loop points `where`
    and `margin` points either side, at the height of the ground found round it: at the hairpin,
    between its road and the walls out on what is drawn, the car fell through. Looked for on a
    grid `step` apart (rays out from each point fanned apart round the hairpin and left strips
    between them), each gap a square half as wide again, and along each road edge a quarter metre
    apart out to 3 m (a strip at the edge narrower than the grid, on the inside of the apex, was
    the hole). Half a metre's grid was 21,000 squares, the collision twice its size: textures were
    let go. With `under`, a sheet of ground that much under all of it, out to the walls (2 m squares,
    each under the lowest ground found at its corners, merged): a car's wheel that found a
    crack between the course's road and the ground put beside it sank, or the car fell through.
    Returns the squares added."""
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
    lone = []  # the squares with no ground found round them, their heights settled at the end
    def square(p, y, w_):
        nonlocal added
        h = None
        for r in (0.75, 1.5, 3.0):
            hs = [height(p[0] + dx, p[1] + dz, y) for dx, dz in ((r, 0), (-r, 0), (0, r), (0, -r))]
            hs = [x for x in hs if x is not None]
            if hs: h = float(min(hs)); break  # the lowest round it: a kerb's height beside it made a bump
        dc = np.hypot(c2[:, 0] - p[0], c2[:, 1] - p[1])
        k_ = int(np.argmin(dc))
        cap = centre[k_][1] if dc[k_] < half[k_] + 1.5 else np.inf  # by the road never over it
        if h is None: lone.append((len(squares), y - 0.05, cap)); h = y - 0.05
        squares.append((p[0], p[1], w_, min(h, cap)))  # laid at the end, merged (lay_squares)
        added += 1
    def filled(p):
        return any(abs(p[0] - x) <= w and abs(p[1] - z) <= w for x, z, w, _ in squares[-400:])
    def settle():
        """The squares with no ground within 3 m: at the height of the squares beside them that found
        some, ring by ring out from those, then evened out (each the mean of those within 1.6 m), not
        at the loop's own height: west of the hairpin's apex the old road falls away, and squares at
        the loop's height stood 0.3 to 1.0 m over the ground they met, ledges (the audit of 17 Nov)."""
        if not lone or len(lone) == len(squares): return
        P = np.array([s[:2] for s in squares], float)
        Hh = np.array([s[3] for s in squares], float)
        free = np.zeros(len(squares), bool); free[[k for k, _, _ in lone]] = True
        known = ~free
        for _ in range(200):
            fu, fk = np.flatnonzero(~known), np.flatnonzero(known)
            if not len(fu): break
            d = np.hypot(P[fu, None, 0] - P[None, fk, 0], P[fu, None, 1] - P[None, fk, 1])
            hit = d < 1.6
            got = hit.any(1)
            if not got.any(): break
            Hh[fu[got]] = (np.where(hit, Hh[fk][None, :], 0).sum(1) / np.maximum(hit.sum(1), 1))[got]
            known[fu[got]] = True
        fu = np.flatnonzero(free & known)
        if len(fu):
            d = np.hypot(P[fu, None, 0] - P[None, :, 0], P[fu, None, 1] - P[None, :, 1]) < 1.6
            for _ in range(20): Hh[fu] = (d * Hh[None, :]).sum(1) / d.sum(1)
        for k, _, cap in lone:
            if known[k]: squares[k] = squares[k][:3] + (float(min(Hh[k], cap)),)
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
    settle()
    lay_squares(col, squares)
    if under:
        run = [i for i in near if (i - 1) % n in near_set]  # consecutive pairs (i - 1, i)
        corner = {}
        def at(i, u):
            if (i, u) not in corner:  # (a corner in a hole: the lowest ground round it, else the road's height)
                q = c2[i] + left[i] * u
                h = height(q[0], q[1], centre[i][1])
                for r in (0.5, 1.0, 2.0):
                    if h is not None: break
                    hs = [x for x in (height(q[0] + dx, q[1] + dz, centre[i][1]) for dx, dz in ((r, 0), (-r, 0), (0, r), (0, -r))) if x is not None]
                    h = min(hs) if hs else None
                corner[(i, u)] = np.array([q[0], (centre[i][1] if h is None else h) - under, q[1]])
            return corner[(i, u)]
        sheet = []  # each 2 m quad as a square round it at its lowest corner, merged (the quads, laid
        # as they were, overlapped four deep round the hairpin: 200 triangles in a 10 m square)
        for i in run:
            j = (i - 1) % n
            w = max(dist.get((sd, k), half[k] + 8.0) for k in (i, j) for sd in (1, -1)) + 1.0
            us = np.arange(-np.ceil(w / 2) * 2, np.ceil(w / 2) * 2 + 0.1, 2.0)
            for u0, u1 in zip(us[:-1], us[1:]):
                q = np.array([at(j, u0), at(j, u1), at(i, u1), at(i, u0)])
                m = q.mean(0)
                sheet.append((m[0], m[2], np.abs(q[:, [0, 2]] - m[[0, 2]]).max(), q[:, 1].min()))
        lay_squares(col, sheet, cell=0.5, tol=0.05, top=False)
    return added


def tri_key(surface, pts):
    """A collision triangle's name: its surface and corners to the centimetre (the disc's own told from ours)."""
    return (surface, tuple(tuple(round(float(c), 2) for c in p) for p in pts))


class GroundMap:
    """Ground triangles ((3, 3) arrays) to ask heights of: top(x, z, y) the highest under (x, z) from 2 m
    under y to 1.5 m over it, or None."""
    def __init__(self, tris):
        self.tris, self.cells = tris, {}
        for k, t in enumerate(tris):
            for gx in range(int(np.floor(t[:, 0].min() / 5)), int(np.floor(t[:, 0].max() / 5)) + 1):
                for gz in range(int(np.floor(t[:, 2].min() / 5)), int(np.floor(t[:, 2].max() / 5)) + 1):
                    self.cells.setdefault((gx, gz), []).append(k)

    def top(self, x, z, y, under=2.0, over=1.5):
        best = None
        for k in self.cells.get((int(np.floor(x / 5)), int(np.floor(z / 5))), ()):
            a, b, c = self.tris[k]
            det = (b[0] - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (b[2] - a[2])
            if abs(det) < 1e-9: continue
            u = ((x - a[0]) * (c[2] - a[2]) - (c[0] - a[0]) * (z - a[2])) / det
            v = ((b[0] - a[0]) * (z - a[2]) - (x - a[0]) * (b[2] - a[2])) / det
            if u < -1e-4 or v < -1e-4 or u + v > 1 + 1e-4: continue
            h = a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])
            if y - under < h < y + over and (best is None or h > best): best = h
        return best


def hairpin_ground(col, stock, centre, half, dist, where, cell=2.0, margin=15, band=4.0, floats=0.04):
    """The hairpin's ground made one surface (the audit of 17 Nov: ledges of 0.3 to 1.0 m west of its
    apex, where the old road falls away west under the link's flat ground and the squares put beside it
    at the loop's height). Round loop points `where` and `margin` either side, inside the walls (`dist`):

      our ground standing more than `floats` m over the course's own (`stock`: the disc's triangles'
      names, tri_key) is taken out, the course's road the surface there;
      where no ground is left, ground on a grid `cell` m apart, its corners shared: on what ground
      there is at its height, else at the loop's height there, sloping to it over `band` m from the
      ground it meets; level cells merged (lay_squares' way).

    fill_ground after it finds only what this leaves. Returns (triangles taken out, cells laid, triangles)."""
    n = len(centre)
    near = sorted({(i + k) % n for i in where for k in range(-margin, margin + 1)})
    near_set = set(near)
    left, _ = frame(centre)
    c2 = centre[:, [0, 2]]
    reach = max(dist.get((sd, i), half[i] + 8.0) for i in near for sd in (1, -1)) + 3.0
    glo, ghi = c2[near].min(0) - reach, c2[near].max(0) + reach
    def where_at(p):
        """(inside the walls round the hairpin, the loop's height there) for (x, z): fill_ground's test."""
        d = np.hypot(c2[:, 0] - p[0], c2[:, 1] - p[1])
        i = int(np.argmin(d))
        if i not in near_set: return False, centre[i][1]
        lat = (p - c2[i]) @ left[i]
        side = 1 if lat > 0 else -1
        other = np.abs((np.arange(n) - i + n // 2) % n - n // 2) > 25
        between = d[other].min() < half[np.argmin(np.where(other, d, 1e9))] + 15 and d[i] < half[i] + 15
        return bool(abs(lat) <= dist.get((side, i), half[i] + 8.0) + 2.5 or between), centre[i][1]
    def ground_tris(want):
        out = []
        for s, pts, nrm, _ in col.triangles():
            q = np.array(pts, float)
            if abs(nrm[1]) <= 0.7 or q[:, 0].max() < glo[0] - 20 or q[:, 0].min() > ghi[0] + 20 or q[:, 2].max() < glo[1] - 20 or q[:, 2].min() > ghi[1] + 20: continue
            if want is None or (tri_key(s, pts) in stock) == want: out.append((tri_key(s, pts), q))
        return out
    course = GroundMap([q for _, q in ground_tris(True)])
    floating = set()
    for key, q in ground_tris(False):
        m = q.mean(0)
        if not where_at(m[[0, 2]])[0]: continue
        k = int(max(np.hypot(*(q[1] - q[0])[[0, 2]]), np.hypot(*(q[2] - q[0])[[0, 2]])) / 1.0) + 2
        for a in range(k + 1):  # a metre apart over it, a little inside its edges
            for b in range(k + 1 - a):
                p = m + ((q[0] + (q[1] - q[0]) * a / k + (q[2] - q[0]) * b / k) - m) * 0.97
                h = course.top(p[0], p[2], p[1])
                if h is not None and p[1] - h > floats: floating.add(key); break
            if key in floating: break
    gone = col.remove(lambda s, pts: tri_key(s, pts) not in floating) if floating else 0
    known = GroundMap([q for _, q in ground_tris(None)])
    xs = np.arange(np.floor(glo[0] / cell) * cell, ghi[0] + cell, cell)
    zs = np.arange(np.floor(glo[1] / cell) * cell, ghi[1] + cell, cell)
    ins = np.zeros((len(zs), len(xs)), bool); ref = np.zeros((len(zs), len(xs))); kh = np.full((len(zs), len(xs)), np.nan)
    for a, z in enumerate(zs):
        for b, x in enumerate(xs):
            ins[a, b], ref[a, b] = where_at(np.array([x, z]))
            h = known.top(x, z, ref[a, b])
            if h is not None: kh[a, b] = h
    lay = np.zeros((len(zs) - 1, len(xs) - 1), bool)
    for a in range(len(zs) - 1):
        for b in range(len(xs) - 1):
            if not (ins[a:a + 2, b:b + 2].any() or where_at(np.array([xs[b] + cell / 2, zs[a] + cell / 2]))[0]): continue
            if not np.isnan(kh[a:a + 2, b:b + 2]).any() and known.top(xs[b] + cell / 2, zs[a] + cell / 2, ref[a, b]) is not None: continue  # ground there already
            lay[a, b] = True
    # the corners' heights: on ground, its own; else the loop's (to the centimetre: level cells merge),
    # sloping to the nearest corner on ground over `band` m
    Hc = np.round(ref, 2)
    ka, kb = np.nonzero(~np.isnan(kh))
    KP, KH = np.stack([xs[kb], zs[ka]], 1), kh[ka, kb]
    used = np.zeros_like(ins)
    for a, b in zip(*np.nonzero(lay)): used[a:a + 2, b:b + 2] = True
    for a, b in zip(*np.nonzero(used)):
        if not np.isnan(kh[a, b]): Hc[a, b] = kh[a, b]; continue
        if not len(KP): continue
        d = np.hypot(KP[:, 0] - xs[b], KP[:, 1] - zs[a])
        j = int(np.argmin(d))
        if d[j] < band: Hc[a, b] = round(float(KH[j] + (Hc[a, b] - KH[j]) * d[j] / band), 3)
    level = np.zeros_like(lay)
    for a, b in zip(*np.nonzero(lay)): level[a, b] = np.ptp(Hc[a:a + 2, b:b + 2]) < 1e-6
    tris, free = 0, lay.copy()
    span = int(8.0 / cell)
    for a in range(lay.shape[0]):
        for b in range(lay.shape[1]):
            if not free[a, b]: continue
            a1, b1 = a + 1, b + 1
            if level[a, b]:  # level cells at one height, in one rectangle
                h0 = Hc[a, b]
                same = lambda a_, b_: free[a_, b_] and level[a_, b_] and abs(Hc[a_, b_] - h0) < 1e-6
                while b1 < lay.shape[1] and b1 - b < span and same(a, b1): b1 += 1
                while a1 < lay.shape[0] and a1 - a < span and all(same(a1, b_) for b_ in range(b, b1)): a1 += 1
            free[a:a1, b:b1] = False
            q = [(xs[b], Hc[a, b], zs[a]), (xs[b1], Hc[a, b1], zs[a]), (xs[b1], Hc[a1, b1], zs[a1]), (xs[b], Hc[a1, b], zs[a1])]
            col.add_ground(0, [q[0], q[1], q[2]]); col.add_ground(0, [q[2], q[3], q[0]])
            tris += 2
    return gone, int(lay.sum()), tris


def object_of(name):
    """A mesh's object: its resource name without the buffer number (_vbN) and the second copy's b."""
    import re
    base = re.sub(r'_vb\d+$', '', name.replace('vbuff_quickpreview_', ''))
    return base[:-1] if base.endswith('b') else base


def donor_pool(res, used, ppw, allowed, records=None):
    """Meshes of model_quickpreview to rewrite: stride 6 strips the loop's visibility never shows
    (`used`: so their own place is never seen from it either), whose vertex buffer is in `allowed`
    and whose bounding sphere is found in the ppw; largest first, as (pairs of vertices they hold,
    mesh, its sphere's offset). `records`: the ppw's sphere records' offsets, one a mesh
    (fujitrack.ppw_records), for the meshes whose sphere is not found by its value (not their vertices'
    box): more donors, so each can hold one place's faces only (17 Nov: 146 of 151 were in use, their
    faces 80 m and more from each donor's first, 15 donors' spread over 80 to 236 m)."""
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
        if at is None and records is not None and i < len(records): at = records[i]
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


TEX_REACH = 100.0  # a cell streams in the textures of what is drawn within this of its stretch


def near_textures(pvs, res, ring, reach=TEX_REACH, keep=()):
    """The visibility `pvs` with each cell's textures (its second list) cut to those of the meshes it
    draws within `reach` m of its stretch of the loop and the stretches either side (`ring`: the
    loop's points in driving order, the cells equal stretches of it from the lap line), the textures
    of meshes with no positions to go by, and those no mesh of the model takes. Every cell listed
    all 562 textures the cells together show (the original's take 327 at most): the game could not
    keep them all, and dropped some for the stx's 32-texel copies (the garage's tin a blur for a
    while, the guardrails black). The textures `keep` stay in every cell (the new faces' and the
    parked vehicles': cut by stretch the garage's tin was still the stx's copy in the garage, the
    game's cell there not the stretch's this counts)."""
    import struct
    import xb2
    names, _ = xb2.resources(bytes(res))
    head, cells, tail = L.parse_pvs(pvs)
    n = struct.unpack_from('<I', res, L.MODEL)[0]
    P = np.asarray(ring, float)
    P = P[:, [0, 2]] if P.shape[1] == 3 else P
    texs = {struct.unpack_from('<H', e)[0] for c in cells for e in c[1]}
    box, tex_of = {}, {}
    for m in {struct.unpack_from('<H', e)[0] for c in cells for e in c[0]}:
        if m >= n: continue
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
        _, _, _, vbytes, vb, stride, _, t0, t1 = struct.unpack_from('<IIIIHHHHH', res, L.MODEL + a)
        tex_of[m] = {t for t in (t0, t1) if t in texs}
        if 9 <= vb < len(names) + 9 and stride == 6 and vbytes and vbytes % 24 == 0:
            v = np.frombuffer(bytes(res[names[vb - 9][3]:names[vb - 9][3] + vbytes]), '<f4').reshape(-1, 6)[:, [0, 2]]
            if np.all(np.isfinite(v)): box[m] = (v.min(0), v.max(0))
    always = (texs - set().union(*tex_of.values())) | (set(keep) & texs)
    for m in set(tex_of) - set(box): always |= tex_of[m]
    out, N, nc = [], len(P), len(cells)
    for k, lists in enumerate(cells):
        Q = P[[j % N for j in range((k - 1) * N // nc, (k + 2) * N // nc)]]
        lo, hi = Q.min(0) - reach, Q.max(0) + reach
        keep = set(always)
        for m, (bl, bh) in box.items():
            if bh[0] < lo[0] or bl[0] > hi[0] or bh[1] < lo[1] or bl[1] > hi[1] or tex_of[m] <= keep: continue
            if np.min(np.hypot(*(np.clip(Q, bl, bh) - Q).T)) < reach: keep |= tex_of[m]
        lists = [lists[0], [e for e in lists[1] if struct.unpack_from('<H', e)[0] in keep], lists[2]]
        out.append(b''.join(struct.pack('<I', len(l)) + b''.join(l) for l in lists))
    new = head + struct.pack('<I', nc) + b''.join(out) + tail
    sizes = [len(c[1]) for c in L.parse_pvs(new)[1]]
    print('textures streamed per cell: %d to %d of the %d listed' % (min(sizes), max(sizes), len(texs)))
    return new


PICK_REACH = 100.0  # what a cell draws now within this of its stretch, its picked cells must cover


def pick_cells(cells_in, res, ring, hide, first=8, reach=PICK_REACH, most=6):
    """For each of the loop's cells, the cells of Pacific Shipyards II's visibility it draws, and the
    meshes (with their textures and vertex buffers) to add to them: of what Pacific Shipyards II's
    cells 0 to `first` together draw (what every cell drew until now), those within `reach` m of the
    cell's stretch and the stretches either side (`ring`: the loop's points in driving order, the
    cells equal stretches of it from the lap line) are covered by the fewest of its cells (at most
    `most`), and what those leave out is added (no cells found: cells 0 to `first`). Every cell drew
    those 8 cells' 1,840 meshes (the disc's take 200 to 1,065): the strip and the hairpin road dropped
    frames. (Covering what all 24 draw near each stretch took 5 or 6 cells, 1,700 to 3,200 meshes
    and 480 textures a cell.) Its later cells hold
    what Pacific Shipyards II saw from further round (the buildings by the north-east corner drew
    only their stand-ins). ([cells for each], [(meshes, textures, buffers) for each])."""
    import struct
    import xb2
    import blender_export
    names, _ = xb2.resources(bytes(res))
    ids = lambda l: {struct.unpack_from('<H', e)[0] for e in l}
    cell_meshes = [ids(c[0]) - set(hide) for c in cells_in]
    base = set().union(*cell_meshes[:first])
    box, rec = {}, {}
    for m in base:
        g = blender_export.mesh_geometry(res, names, m)
        if g is not None: box[m] = (g[0][:, [0, 2]].min(0), g[0][:, [0, 2]].max(0))
        a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
        _, _, _, _, vb, _, _, t0, t1 = struct.unpack_from('<IIIIHHHHH', res, L.MODEL + a)
        rec[m] = (vb, {t for t in (t0, t1) if t >= 9})
    P = np.asarray(ring, float)
    P = P[:, [0, 2]] if P.shape[1] == 3 else P
    N, nc = len(P), len(cells_in)
    use, per = [], []
    for k in range(nc):
        Q = P[[j % N for j in range((k - 1) * N // nc, (k + 2) * N // nc)]]
        near = {m for m, (bl, bh) in box.items() if np.min(np.hypot(*(np.clip(Q, bl, bh) - Q).T)) < reach}
        picked, got = [], set()
        for c in sorted(range(nc), key=lambda c: -len(near & cell_meshes[c])):
            if len(near & got) >= 0.97 * len(near) or len(picked) >= most: break
            if near & cell_meshes[c] - got: picked.append(c); got |= cell_meshes[c]
        left = near - got
        use.append(picked or list(range(first)))
        per.append((sorted(left), sorted({t for m in left for t in rec[m][1]}), sorted({rec[m][0] for m in left})))
    return use, per


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


def cut_long(face, most=40.0):
    """A strip face in pieces no longer than `most` m (their pairs' middles), a pair put in wherever two
    are further apart than that (simplify makes one quad of a straight 200 to 300 m long, and a donor
    holding one had its bounding sphere 170 m wide: 15 donors over the 80 m the game is known to draw
    whole, the audit of 17 Nov). The pieces overlap by a pair. [faces]."""
    pairs = [face[i:i + 2] for i in range(0, len(face), 2)]
    mid = lambda pr: (np.asarray(pr[0][0], float) + np.asarray(pr[1][0], float))[[0, 2]] / 2
    dense = [pairs[0]]
    for pr in pairs[1:]:
        a = dense[-1]
        k = int(np.ceil(np.hypot(*(mid(pr) - mid(a))) / most))
        for j in range(1, k):
            u = j / k
            dense.append([(np.asarray(va[0], float) + (np.asarray(vb[0], float) - np.asarray(va[0], float)) * u, va[1],
                           va[2] + (vb[2] - va[2]) * u, va[3] + (vb[3] - va[3]) * u) for va, vb in zip(a, pr)])
        dense.append(pr)
    out, cur = [], [dense[0]]
    for pr in dense[1:]:
        if np.hypot(*(mid(pr) - mid(cur[0]))) > most + 1e-6:
            out.append(cur); cur = [cur[-1]]
        cur.append(pr)
    out.append(cur)
    return [[v for pr in piece for v in pr] for piece in out]


def pack(faces, pool, mats, reach=40.0, most_reach=2000.0):
    """Faces gathered by material into the donors (popped from `pool`, as donor_pool, the largest
    left first), as many to each as fit (write_strips joins them), one too long for what is left
    cut, its pieces overlapping by a pair: [(mesh, sphere offset, [pieces], material)]. Each donor
    takes faces within `reach` m of its first only (nearest first), so its bounding sphere stays on
    them: one sphere over faces 500 m apart, the game left some out (the garage's tin over its south
    door, bricks on side road 04, drawn in Blender); with too few donors for that, `reach` grows by a
    quarter. A face is within `reach` when its farthest corner is (17 Nov: by its middle, a long face
    reached far past it), so a donor's faces spread over twice `reach` at most."""
    pool0 = list(pool)
    print('donors: %d, room for %d pairs; needed %s' % (len(pool), sum(r[0] for r in pool), {str(m_): sum(len(f) // 2 for f, mm in zip(faces, mats) if mm == m_) for m_ in set(mats)}))
    while True:
        pool = list(pool0)
        out, short = [], False
        by = {}
        for f, m in zip(faces, mats): by.setdefault(m, []).append([f[i:i + 2] for i in range(0, len(f), 2)])
        mid = lambda pr: np.mean([p_[0][0] for p_ in pr], 0)[[0, 2]]
        for m, queue in by.items():
            queue.sort(key=lambda pr: tuple(mid(pr)))  # (west to east: a seed at one end of what is left)
            while queue and not short:
                if not pool: short = True; break
                _, mesh, at, nv, nidx = pool.pop(0)
                seed = mid(queue[0])
                far = lambda pr: max(np.hypot(*(np.asarray(q[0], float)[[0, 2]] - seed)) for p_ in pr for q in p_)
                queue.sort(key=far)
                pieces, v, ix = [], 0, 0
                while queue:
                    pr = queue[0]
                    if pieces and far(pr) > reach: break
                    join = 3 if pieces else 0
                    k = min(nv - v, nidx - ix - join) // 2  # the pairs there is room for
                    if k >= len(pr): take = len(pr); queue.pop(0)
                    elif k >= 2 and (not pieces or k >= 8): take = k; queue[0] = pr[k - 1:]
                    else: break
                    pieces.append([q for p_ in pr[:take] for q in p_])
                    v += 2 * take; ix += 2 * take + join
                out.append((mesh, at, pieces, m))
                queue.sort(key=lambda pr: tuple(mid(pr)))
        if not short: break
        if reach > most_reach: raise SystemExit('out of donor meshes: %d faces' % len(faces))
        reach *= 1.25
    print('faces packed by place: the faces of each donor within %.0f m of the middle of its first, %d donors' % (reach, len(out)))
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


def edges(centre, half, right=None):
    """The six edge splines: the even ones on the left of the way round (half out), the odd on the
    right (right out, else half), as the first layout had them (the course's, run backwards as
    Pacific Shipyards II runs them)."""
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0)
    left = np.stack([-t[:, 2], np.zeros(len(t)), t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    right = half if right is None else right
    return [centre + left * (-right if k % 2 else half)[:, None] for k in range(6)]


def wall_reach(col, centre, most=40.0, feet_only=False):
    """Per side of the loop (+1 the left, -1 the right) and point, how far out along its normal the
    first wall that stops a car stands in the collision (`most` with none): {side: distances}; or, with
    `feet_only`, those walls' feet (their ends A, B: (n, 2) each)."""
    left, _ = frame(centre)
    c2 = centre[:, [0, 2]]
    lo, hi = c2.min(0) - most, c2.max(0) + most
    feet = {}
    for s, pts, n, _ in col.triangles():
        if abs(n[1]) > 0.7: continue
        q = np.array(pts, float)
        if q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 2].max() < lo[1] or q[:, 2].min() > hi[1]: continue
        a, b = footprint(q)
        m = (a + b) / 2
        y0 = centre[int(np.argmin(np.hypot(c2[:, 0] - m[0], c2[:, 1] - m[1])))][1]
        if q[:, 1].min() < y0 + 1.2 and q[:, 1].max() > y0 + 0.3: feet[(tuple(np.round(a, 2)), tuple(np.round(b, 2)))] = (a, b)
    A, Bv = np.array([f[0] for f in feet.values()]), np.array([f[1] for f in feet.values()])
    if feet_only: return A, Bv
    return {side: ray_reach(c2, left * side, A, Bv, most) for side in (1, -1)}


def ray_reach(O, D, A, B, most):
    """From each point O[i] along the unit vector D[i] (x, z), how far to the first of the segments A to
    B (`most` with none)."""
    E = B - A
    out = np.full(len(O), float(most))
    for i in range(len(O)):
        den = D[i, 0] * E[:, 1] - D[i, 1] * E[:, 0]
        ok = np.abs(den) > 1e-9
        w = A - O[i]
        t = np.where(ok, (w[:, 0] * E[:, 1] - w[:, 1] * E[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (w[:, 0] * D[i, 1] - w[:, 1] * D[i, 0]) / np.where(ok, den, 1), -1)
        hit = ok & (t > 0.05) & (t < most) & (u >= -0.02) & (u <= 1.02)
        if hit.any(): out[i] = t[hit].min()
    return out


def unfold(E, fwd, window=110):
    """An edge line (closed, point for point with the loop's centre; `fwd` the centre's way round at
    each, (x, z)) with its loops cut out: where it crosses itself (inside a bend tighter than the edge is
    far from the centre, it runs back on itself and round), the points between the crossing's two legs
    all at the crossing; and no point behind the one before it. The track's edges folded so at the corner
    from side road 31 onto 04 and at the hairpin (10 points stepping backwards, the audit of 17 Nov)."""
    n = len(E)
    P = E[:, [0, 2]]
    out = E.copy()
    def cross(p, q, r, s_):
        d1, d2 = q - p, s_ - r
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12: return None
        t = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
        u = ((r[0] - p[0]) * d1[1] - (r[1] - p[1]) * d1[0]) / den
        return p + d1 * t if 0 <= t <= 1 and 0 <= u <= 1 else None
    i = 0
    while i < n:
        best = None
        for j in range(i + 2, i + window):
            x = cross(P[i], P[(i + 1) % n], P[j % n], P[(j + 1) % n])
            if x is not None: best = (j, x)
        if best is not None:
            # (not quite all at the crossing: spread a little along the edge up to it and away from it, each a
            # short step on from the last, so no two of the game's edge points are one)
            m = best[0] - i
            a_, b_ = P[i], P[(best[0] + 1) % n]
            for q, k in enumerate(range(i + 1, best[0] + 1)):
                u = (q + 1) / (m + 1)
                at = a_ + (best[1] - a_) * (0.85 + 0.3 * u) if u < 0.5 else best[1] + (b_ - best[1]) * (0.3 * u - 0.15)
                out[k % n, 0], out[k % n, 2] = at
            i = best[0] + 1
        else: i += 1
    for _ in range(2):  # (twice round: the first pass's start may itself be moved)
        for i in range(n):
            a, b = out[i - 1], out[i]
            if (b[0] - a[0]) * fwd[i][0] + (b[2] - a[2]) * fwd[i][1] < 0: out[i, 0], out[i, 2] = a[0], a[2]
    return out


def track_edges(centre, EL, ER, col, short=0.2):
    """The track's edges for the game from the edge lines wanted (EL, ER: left and right, point for point
    with the centre, not crossing themselves: unfold), each point the weighted mean of the five round it
    (inside a tight bend the unfolded edge is one point for many of the centre's, a corner the others'
    lines fan out from: rounded a little, so no two are quite the same point), their height the
    collision's ground under the middle between them (round the hairpin that runs 6 m outside the centre
    line, where the old road falls away west). The game's waypoints are those middles and its normals
    half the lines across from edge to edge (aitrack.geometry's `edges`): where the half width, 8 and
    14 m, was over the centre line's radius, 3 to 6 m, normals square to the centre line crossed inside
    the edges, and the suggested line laid along them was knotted, points 0.3 m apart (the audit of 17
    Nov). (left edge, right edge)."""
    n = len(centre)
    w = np.array([1, 4, 6, 4, 1], float) / 16
    EL = sum(w[j] * np.roll(EL, 2 - j, 0) for j in range(5))
    ER = sum(w[j] * np.roll(ER, 2 - j, 0) for j in range(5))
    mid = (EL + ER) / 2
    ground = GroundMap([np.array(pts, float) for _, pts, nrm, _ in col.triangles() if abs(nrm[1]) > 0.7])
    y = np.array([centre[i][1] if (g := ground.top(mid[i, 0], mid[i, 2], centre[i][1], under=1.5, over=1.0)) is None else g for i in range(n)])
    y = sum(w[j] * np.roll(y, 2 - j) for j in range(5))
    EL[:, 1] = ER[:, 1] = y
    # and neither past a wall along the line from the middle to it (the lines wanted are held to the
    # walls along the centre line's normals; round a corner the line across leans, and met a wall's end
    # the normals passed: 1.2 m past it at the corner onto the start road), `short` m short of it
    A, Bv = wall_reach(col, centre, feet_only=True)
    across = (EL - ER)[:, [0, 2]]
    hw = np.linalg.norm(across, axis=1) / 2
    u = across / np.maximum(2 * hw, 1e-6)[:, None]
    for E, sg in ((EL, 1), (ER, -1)):
        d = ray_reach(mid[:, [0, 2]], u * sg, A, Bv, 60.0)
        d = np.minimum(d, np.minimum(np.roll(d, 1), np.roll(d, -1)))   # (a wall's end between two points' lines)
        k = np.minimum(hw, np.maximum(d - short, 1.0))
        E[:, 0], E[:, 2] = mid[:, 0] + sg * u[:, 0] * k, mid[:, 2] + sg * u[:, 1] * k
    return EL, ER


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


def one_face(col, centre, boxes=(), reach=40.0):
    """Each wall laid with both faces keeps one, as the disc's walls have (none of its 3,800 has a
    twin): the one facing the nearest loop point, or out of a parked vehicle's box. With both, a car
    pushed into a wall was pushed on out of its far side (the strip, the hairpin, the garage's north
    wall), and fell. Walls farther than `reach` from the loop keep both. Returns faces dropped."""
    c2 = centre[:, [0, 2]]
    edges = [(np.array(a, float), np.array(b, float), np.mean(corners, 0)) for corners, _ in boxes for a, b in zip(corners, corners[1:] + corners[:1])]
    count = {}
    for s, pts, nrm, _ in col.triangles():
        if abs(nrm[1]) <= 0.7: k = (s, frozenset(tuple(round(v, 3) for v in p) for p in pts)); count[k] = count.get(k, 0) + 1
    def keep(surface, pts):
        q = np.array(pts, float)
        n_ = np.cross(q[1] - q[0], q[2] - q[0])
        if abs(n_[1]) > 0.7 * np.linalg.norm(n_): return True
        if count.get((surface, frozenset(tuple(round(v, 3) for v in p) for p in pts)), 0) < 2: return True
        m = q.mean(0)[[0, 2]]
        for a, b, mid in edges:  # a parked vehicle's side: facing out of it
            t = np.clip((m - a) @ (b - a) / max((b - a) @ (b - a), 1e-9), 0, 1)
            if np.hypot(*(a + (b - a) * t - m)) < 0.05: return n_[[0, 2]] @ (m - mid) > 0
        d = np.hypot(c2[:, 0] - m[0], c2[:, 1] - m[1])
        k = int(np.argmin(d))
        if d[k] > reach: return True
        return n_[[0, 2]] @ (c2[k] - m) > 0
    return col.remove(keep)


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
    # in the garage blended between its doors (the old lots hidden under it took its floor up 0.4 m
    # over both ends: a ramp in at each door)
    centre, drawn, total = drawn_heights(res, centre, off, garage.inside(centre[:, [0, 2]], pad=6.0))
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
    # (on the course's own road, ten points or more from a new stretch, its full width: there the
    # course's lamp posts and kerbs drew the edges in to 7 m of a 10 m half, and the turn by the main
    # road counted a car on its asphalt as off it)
    near_new = np.zeros(len(centre), bool)
    for i in np.nonzero(off)[0]: near_new[[(i + k) % len(centre) for k in range(-10, 11)]] = True
    cap = np.array([min(half[i], bd[(1, i)] - MARGIN, bd[(-1, i)] - MARGIN) if near_new[i] else half[i] for i in range(len(centre))])  # a car's width and more short of it
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
    if os.environ.get('CIRCUIT_EDGES'):  # debugging: the widths round the hairpin
        for i in range(len(centre)):
            dh = np.hypot(centre[i][0] - HAIRPIN[0], centre[i][2] - HAIRPIN[1])
            if dh < HAIRPIN_R + 25:
                print('  edge %4d (%.0f, %.0f) %4.0f m from the hairpin: half %.1f, boundary left %.1f right %.1f, edge %.1f%s'
                      % (i, centre[i][0], centre[i][2], dh, half[i], bd[(1, i)], bd[(-1, i)], cap[i], ' new road' if off[i] else ''))
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
    stock = {tri_key(s, pts) for s, pts, _, _ in col.triangles()}  # the disc's own triangles (hairpin_ground)
    walls = [L.across(sp, i) for i in CLOSED] + [tuple((x, z, ground_y(sp, x, z)) for x, z in w) for w in CLOSED_AT]
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
        if in_gap_strict[i]: dist[(side, i)] = min(garage.lateral(centre, half, i, side, left_c), half[i] + 8)  # in the garage: its walls (the parked vehicles solid; a wall a metre past the road had a guardrail on it that did not belong), no further than its ground (where the walls were missed, 25 m out: the car fell through)
    # with nothing standing by an edge, the road open out to a sidewalk drawn within 8 m, the wall
    # at its kerb; the ground over the void still laid from the old line (dist0)
    dist0 = dict(dist)
    at_corner = np.hypot(centre[:, 0] - CORNER[0], centre[:, 2] - CORNER[1]) < CORNER_R  # (its brick wall wraps to the ledge)
    kerbed = sidewalk_edges(res, centre, half, {k: d for k, d in dist.items() if not (at_hairpin[k[1]] or in_gap[k[1]] or by_concrete[k[1]] or (k[0] == CORNER_SIDE and at_corner[k[1]]))}, hidden=hide)
    dist.update(kerbed)
    print('walls out at a sidewalk\'s kerb: %d points' % len(kerbed))
    # the garage's south lane (the yard's fence to its south door): its walls at the door's width,
    # where its tin walls stand (garage.lane_faces)
    in_lane = np.zeros(len(centre), bool); in_lane[garage.south_lane(centre)] = True
    for (side, i) in list(dist):
        if in_lane[i]: dist[(side, i)] = half[i] + garage.OPEN_PAD
    # the strip's walls at its drawn road's edge (HALF + 2), not out at what stands past its sidewalks
    # and lots (the user drove onto the sidewalk by the green container, 11-13 m out)
    sa, sb = np.array(STRIP[0], float), np.array(STRIP[1], float)
    tt = np.clip((centre[:, [0, 2]] - sa) @ (sb - sa) / ((sb - sa) @ (sb - sa)), 0, 1)
    on_strip = off & ~at_hairpin & (np.hypot(*(centre[:, [0, 2]] - (sa + tt[:, None] * (sb - sa))).T) < 3.0)
    # a sidewalk's kerb looked for on past the boundary found (its kerb face was taken for that boundary
    # by the hairpin, and the search stopped short of it: the wall stood 3 m out in the lot's asphalt)
    strip_kerb = sidewalk_edges(res, centre, half, {(side, i): dist0[(side, i)] + 1.0 for (side, i) in dist0 if on_strip[i]}, hidden=hide)
    capped, at_kerb, kept = 0, 0, 0
    for (side, i), d in list(dist.items()):
        if not on_strip[i]: continue
        k_ = strip_kerb.get((side, i), kerbed.get((side, i)))
        if k_ is not None and k_ < HALF + 8.0: dist[(side, i)] = k_; at_kerb += 1  # (the user: "the edge of that sidewalk")
        elif d <= HALF + 4.0: kept += 1  # a boundary close by: its wall stays there
        else: dist[(side, i)] = HALF + 2.0; capped += 1
    print('the strip\'s walls: %d points at a sidewalk\'s kerb, %d at a boundary close by, %d at its road\'s edge' % (at_kerb, kept, capped))
    # each side's walls the middle of five points' (a point or two found nearer or farther than
    # those round it stood the wall out in a V or a notch: on the strip a car in one went through)
    smoothed = 0
    for r in runs(off):
        for side in (1, -1):
            ks = [i for i in r if (side, i) in dist]
            d = np.array([dist[(side, i)] for i in ks])
            for k, i in enumerate(ks):
                m = float(np.median(d[max(0, k - 2):k + 3]))
                if abs(m - d[k]) > 0.5: dist[(side, i)] = m; smoothed += 1
    print('walls in line: %d points moved to their neighbours\' line' % smoothed)
    near = sum(1 for (side, i), d in dist.items() if d < half[i] + WIDE - 0.2)
    print('walls beside the new road: %d of %d on a drawn fence, wall or building' % (near, len(dist)))
    cut = clear_road(col, centre, half)
    # the walls beside the new road after the cut (the tunnel's railings stand inside the road's
    # width, and were cut away), no ground of theirs at the hairpin
    # the strip's first 25 m from the junction open on its north-east side: no walls, guardrails or
    # ground of ours (the junction's asphalt and its sidewalk are there, the course's walls past
    # them; a wall and a guardrail stood across it). Its south-west side ends in the void.
    near_end = off & (np.hypot(centre[:, 0] - STRIP[0][0], centre[:, 2] - STRIP[0][1]) < STRIP_OPEN)
    open_end = {(STRIP_OPEN_SIDE, i) for i in np.nonzero(near_end)[0]}
    corner_pts = [i for i in range(len(centre)) if off[i] and np.hypot(centre[i][0] - CORNER[0], centre[i][2] - CORNER[1]) < CORNER_R]
    no_rail = open_end | {(CORNER_SIDE, i) for i in corner_pts}  # (the corner has its own brick wall)
    for r in runs(off): boundary_collision(col, centre, half, r, dist, sp, at_hairpin, open_end)
    # and the course's own kerb wall round the junction's north-east corner, between it and the
    # strip's open side (an invisible wall across what reads as one lot of asphalt)
    def not_corner(surface, pts):
        q = np.array(pts, float)
        n_ = np.cross(q[1] - q[0], q[2] - q[0])
        if abs(n_[1]) > 0.7 * np.linalg.norm(n_): return True
        m = q.mean(0)
        return not (JUNCTION_CORNER[0] <= m[0] <= JUNCTION_CORNER[2] and JUNCTION_CORNER[1] <= m[2] <= JUNCTION_CORNER[3])
    print('junction corner: %d wall triangles removed' % col.remove(not_corner))
    # the hairpin's ground one surface with the old road's (the audit of 17 Nov: ledges west of its apex)
    print('hairpin: %d triangles of our ground standing over the course\'s taken out; %d cells of ground laid where none was, %d triangles'
          % hairpin_ground(col, stock, centre, half, dist, [i for i in range(len(centre)) if at_hairpin[i]]))
    print('hairpin: %d squares of ground where there was none, and a sheet under it all' % fill_ground(col, centre, half, dist, [i for i in range(len(centre)) if at_hairpin[i]], under=0.15))
    # and at Turn 2's exit onto side road 31 (a collision audit found the ground ending a metre short
    # of the wall there for 19 m: a gap to drive into)
    t2 = np.hypot(centre[:, 0] - TURN2_EXIT[0], centre[:, 2] - TURN2_EXIT[1]) < 25
    print('Turn 2\'s exit: %d squares of ground where there was none' % fill_ground(col, centre, half, dist, [i for i in range(len(centre)) if t2[i]], margin=3))
    (gx0, gz0), (gx1, gz1) = TURN2_GAP
    gy0, gy1 = ground_y(sp, gx0, gz0), ground_y(sp, gx1, gz1)
    q = [(gx0, gy0 - 1, gz0), (gx1, gy1 - 1, gz1), (gx1, gy1 + 3, gz1), (gx0, gy0 + 3, gz0)]
    for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
        col.add(0x900, tri)
    holes, blocked = check(col, centre, half)
    print('walls cut back off the road: %d triangles' % cut)
    for what, items in (('no ground', holes), ('wall on the road', blocked)):
        print('  %s at %d points%s' % (what, len(items), ': ' + ', '.join('(%.0f, %.0f)' % (centre[i][0], centre[i][2]) for i, _ in items[:12]) if items else ''))
    # the track's edges, each side its own, out to its wall on the new road and round the hairpin
    # (the user drew a time penalty on the strip's asphalt by the sidewalk: the edges were its 7 m
    # half, the kerb's wall 12 m out), EDGE_PAD short of the wall and no more than EDGE_MORE past
    # the half, never nearer than before
    side_cap = {1: cap.copy(), -1: cap.copy()}
    for i in range(len(centre)):
        if not (off[i] or at_hairpin[i]) or in_lane[i] or in_gap_strict[i]: continue
        for side in (1, -1):
            if (side, i) in dist: side_cap[side][i] = max(cap[i], min(dist[(side, i)] - EDGE_PAD, half[i] + EDGE_MORE))
    ks_ = np.arange(-3, 4); ws_ = np.exp(-0.5 * (ks_ / 1.5) ** 2); ws_ /= ws_.sum()  # (k_ and w_ are taken by then)
    for side in (1, -1):  # no spikes: each point no wider than its neighbours' weighted mean
        side_cap[side] = np.minimum(side_cap[side], sum(ws_[j] * np.roll(side_cap[side], -ks_[j]) for j in range(len(ks_))))
        side_cap[side] = np.maximum(side_cap[side], cap)
    print('track edges out to the walls: %d points on the left, %d on the right' % tuple(int(np.sum(side_cap[s] > cap + 0.05)) for s in (1, -1)))
    if os.environ.get('CIRCUIT_EDGES'):
        for i in range(len(centre)):
            if np.hypot(centre[i][0] - HAIRPIN[0], centre[i][2] - HAIRPIN[1]) < HAIRPIN_R + 25 and i % 3 == 0:
                print('  edge %4d: left %.1f (wall %s), right %.1f (wall %s)' % (i, side_cap[1][i], '%.1f' % dist[(1, i)] if (1, i) in dist else '-',
                                                                               side_cap[-1][i], '%.1f' % dist[(-1, i)] if (-1, i) in dist else '-'))
    e = edges(centre, side_cap[1], side_cap[-1])
    if reverse:
        loop, length = L.resample([e[k ^ 1] for k in range(6)], centre, START)
    else:
        loop, length = L.resample([x[::-1] for x in e], centre[::-1], START)
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
    # a low guardrail wherever the road's edge has nothing drawn (kerbs and sidewalks were ledges),
    # but none on the strip (the user: an invisible wall at its sidewalks' edge instead)
    BRICK_ENDS.clear()
    stretches = []
    by_shop = garage.inside(centre[:, [0, 2]], pad=12.0)  # in the garage and up to its doors
    # and none through a turn: over 20 m either side the road turns more than 20 degrees (a kerb at a
    # junction's corner was where cars cut in and stopped)
    head_ = np.arctan2(*(np.roll(centre, -1, 0) - np.roll(centre, 1, 0))[:, [2, 0]].T)
    turning = np.abs((np.roll(head_, -10) - np.roll(head_, 10) + np.pi) % (2 * np.pi) - np.pi) > np.radians(20)
    # nor on the course's own road, wider than the loop's (on Pacific Shipyards II's start road one
    # stood 4 m inside its edge, a fence across the asphalt)
    lf_, _ = frame(centre)
    on_course = {side: ~L.off_course([centre[i] + np.array([lf_[i][0], 0, lf_[i][1]]) * side * dist.get((side, i), half[i] + 0.8) for i in range(len(centre))], sp, margin=0.0)
                 for side in (1, -1)}
    for side, idx in bare_edges(res_bytes, centre, half, hidden=hide):  # none in the tunnel or by the concrete
        run = []
        for i in idx + [None]:
            if i is not None and not (in_gap[i] or by_concrete[i] or at_hairpin[i] or by_shop[i] or on_strip[i] or in_lane[i] or turning[i] or (side, i) in kerbed or on_course[side][i] or (side, i) in no_rail): run.append(i); continue
            if len(run) >= 12: stretches.append((side, run))  # 24 m or more: short stubs were ledges in odd places
            run = []
    # each on the walls' line where the new stretches have one, else just off the road, in straight
    # pieces (the line within half a metre), solid a metre high
    rails = []
    left_, _ = frame(centre)
    for side, idx in stretches:
        F = np.array([centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * side * dist.get((side, i), half[i] + 0.8) for i in idx])
        for a, b in zip(*(lambda k: (k[:-1], k[1:]))(chords(F, 0.5))):
            rails += barrier(tuple(F[a]), tuple(F[b]), centre[idx[(a + b) // 2]][[0, 2]])
            q = [F[a] + (0, -0.5, 0), F[b] + (0, -0.5, 0), F[b] + (0, 1.0, 0), F[a] + (0, 1.0, 0)]
            for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                col.add(0x900, tri)
    print('guardrails at the bare edges: %d pieces over %d stretches' % (len(rails) // 2, len(stretches)))
    kerbs = []
    print('garage: %d collision triangles, its yard fence %d' % (garage.collision(col, centre, half), garage.yard_collision(col, centre, half)))
    print('garage: floor laid at %d bare points' % shop_floor(col, centre))
    # its parked vehicles solid, each a box round its footprint (they are moved in after: park())
    import xb2
    import fujitrack
    sphere_recs = fujitrack.ppw_records(bytes(ppw))   # (one a mesh: for the parked vehicle whose sphere is not found by value)
    boxes = garage.parked_boxes(res_bytes, centre, xb2.resources(bytes(res_bytes))[0], L.MODEL, ppw, sphere_at, sphere_recs)
    for corners, fy in boxes:
        for a, b in zip(corners, corners[1:] + corners[:1]):
            q = [(a[0], fy - 0.5, a[1]), (b[0], fy - 0.5, b[1]), (b[0], fy + 1.8, b[1]), (a[0], fy + 1.8, a[1])]
            for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                col.add(0x900, tri)
    print('garage: %d parked vehicles solid' % len(boxes))
    # the old road west of the hairpin closed by a brick wall between its kerbs (the guardrails along
    # them keep cars off its sidewalks; a metre over each edge it stood on them), solid to half a
    # metre past them, into the guardrails
    (bx0, bz0, by0), (bx1, bz1, by1) = L.across(sp, OLD_ROAD_END, extra=-0.3)
    (cx0, cz0, cy0), (cx1, cz1, cy1) = L.across(sp, OLD_ROAD_END, extra=0.5)
    q = [(cx0, cy0 - 1, cz0), (cx1, cy1 - 1, cz1), (cx1, cy1 + 3, cz1), (cx0, cy0 + 3, cz0)]
    for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
        col.add(0x900, tri)
    import collision_audit
    # walls on the course's own kerbs at the junction (the user: "along the edge of that sidewalk";
    # the course lets a car up onto it, its walls out at the fence)
    near_k = [i for i in range(len(centre)) if any(np.hypot(centre[i][0] - x, centre[i][2] - z) < KERB_R for x, z in KERB_SPOTS)]
    kerb_k = sidewalk_edges(res_bytes, centre, half, {(side, i): half[i] + 14.0 for i in near_k for side in (1, -1)}, hidden=hide)
    lf3 = np.stack([left_[:, 0], np.zeros(len(left_)), left_[:, 1]], 1)
    for side in (1, -1):
        idx = sorted(i for s, i in kerb_k if s == side)
        for i, j in zip(idx[:-1], idx[1:]):
            if j != i + 1: continue
            a, b = centre[i] + lf3[i] * side * kerb_k[(side, i)], centre[j] + lf3[j] * side * kerb_k[(side, j)]
            q = [a + (0, -1, 0), b + (0, -1, 0), b + (0, 3, 0), a + (0, 3, 0)]
            for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                col.add(0x900, tri)  # (one_face keeps the road's side)
    print('walls on the junction\'s kerbs: %d points' % len(kerb_k))
    # the openings between walls' ends closed (the audit of 17 Nov: 24 of them, up to 2.1 m, onto the
    # ground behind the walls, its own edges unwalled), before the open edges are looked for (a car's
    # flood through one sealed the edges of ground no car should reach) and again after (those walls'
    # ends against the others')
    def off_road(pts, end=None):  # (a join of walls' ends: never across the road, nor further into it than the end joined is)
        return bool(np.all(into_road(centre, half, pts) < (-0.5 if end is None else min(into_road(centre, half, end)[0] + 0.05, 0.3))))
    gaps = collision_audit.seal_gaps(col, centre)
    # and every edge of the ground a car reaches that ends with no wall (as the collision audit finds
    # them: past the hairpin two walls' ends jogged 4 m apart and a car went through and fell), after
    # the junction's kerb walls (the flood went over that sidewalk and on down the bypassed course
    # road, sealed for 1.3 km), each with its one face toward the ground it seals (17 Nov: one_face's
    # "toward the nearest loop point" faced 12 m of them at the hairpin's infield toward the void)
    sealed = []
    print('open edges sealed: %.0f m of wall' % collision_audit.seal_open_edges(col, centre, one_face=True, made=sealed))
    print('walls one-faced: %d back faces dropped' % one_face(col, centre, boxes))
    gaps += collision_audit.seal_gaps(col, centre, ends=off_road)
    gaps += collision_audit.seal_gaps(col, centre, clear=1.75, deep=3.5, ends=off_road)
    # (and the open edges once more: the walls across the openings change a little what a car reaches; 2 m of
    # edge at Turn 2's exit, (-141, -308), was left open after them)
    again = collision_audit.seal_open_edges(col, centre, one_face=True, made=sealed)
    if again: print('open edges sealed after the openings: %.1f m more' % again)
    print('openings between walls\' ends closed: %d%s' % (len(gaps), ': ' + ', '.join('(%.0f, %.0f) %.1f m' % g for g in gaps[:40]) if gaps else ''))
    # every wall facing the ground a car reaches; the pieces of cut walls left standing alone in the
    # hairpin's ground out; the sealing walls no car comes near dropped (the blocks' size)
    def lone_ours(surface, pts):
        m = np.mean(pts, 0)
        return tri_key(surface, pts) not in stock and np.hypot(m[0] - HAIRPIN[0], m[2] - HAIRPIN[1]) < HAIRPIN_R + 30
    print('walls turned to the ground a car reaches: %d triangles; pieces standing alone at the hairpin taken out: %d; sealing walls far from it dropped: %d'
          % collision_audit.face_walls(col, centre, islands=lone_ours, far=sealed))
    down = sum(1 for _, pts, nrm, _ in col.triangles() if nrm[1] < -0.7 and np.hypot(*(centre[:, [0, 2]] - np.mean(pts, 0)[[0, 2]]).T).min() < 60)
    print('ground facing down near the loop: %d triangles%s' % (down, ' (the game takes them for ceilings: cars fall through)' if down else ''))
    col_bytes = col.to_bytes()
    # the track's edges again, now the walls stand (the audit of 17 Nov): each side out to the wall the
    # collision really has there, EDGE_PAD short of it (round the hairpin's outside they were 1.3 to 2.5 m
    # past it: `dist` is what is drawn, the wall the old road's own), on the new road, round the hairpin
    # and at the joins with the course (the corner from side road 39 onto the start road, the strip's
    # end: the edges were well inside the asphalt a car runs wide on there, a time penalty on the road),
    # but not at the junction (its width is held to 11 m on purpose: a fence the line cut through), and
    # nowhere past a wall; then unfolded and laid about a middle line whose normals do not cross
    reach_w = wall_reach(col, centre)
    at_junction = np.hypot(centre[:, 0] - STRIP[0][0], centre[:, 2] - STRIP[0][1]) < 45.0
    # (where a car runs wide onto more asphalt, further: at the joins the course's own road lies past the
    # edge, 26 m of it outside the corner onto the start road)
    roomy = ~off   # (not the strip's end into the hairpin as well: its edge 12 m out leant the normals round the hairpin 50 degrees, the disc's lean 30 at most)
    for side in (1, -1):
        wd = side_cap[side].copy()
        rw = np.minimum(reach_w[side], np.minimum(np.roll(reach_w[side], 1), np.roll(reach_w[side], -1)))
        for i in range(len(centre)):
            ours = (side, i) in dist
            if ours and not (in_lane[i] or in_gap_strict[i] or at_junction[i]):
                wd[i] = max(wd[i], min(rw[i] - EDGE_PAD, half[i] + (EDGE_WIDE if roomy[i] else EDGE_MORE)))
            wd[i] = min(wd[i], max(rw[i] - (EDGE_PAD if ours else 0.05), 3.0))
        side_cap[side] = np.minimum(wd, sum(ws_[j] * np.roll(wd, -ks_[j]) for j in range(len(ks_))))
    lf3_ = np.stack([left_c[:, 0], np.zeros(len(centre)), left_c[:, 1]], 1)
    _, fwd_c = frame(centre)
    EL = unfold(centre + lf3_ * side_cap[1][:, None], fwd_c)
    ER = unfold(centre - lf3_ * side_cap[-1][:, None], fwd_c)
    if os.environ.get('CIRCUIT_DUMP'):  # debugging: what the edges are made from
        np.savez(os.environ['CIRCUIT_DUMP'], centre=centre, half=half, cap_l=side_cap[1], cap_r=side_cap[-1], EL=EL, ER=ER, reach_l=reach_w[1], reach_r=reach_w[-1])
        open(os.environ['CIRCUIT_DUMP'] + '.col', 'wb').write(col_bytes)
    EL, ER = track_edges(centre, EL, ER, col)
    mid = (EL + ER) / 2
    e = [EL if k % 2 == 0 else ER for k in range(6)]
    if reverse:
        loop, length = L.resample([e[k ^ 1] for k in range(6)], centre, START, by=mid)
    else:
        loop, length = L.resample([x[::-1] for x in e], centre[::-1], START, by=mid[::-1])
    back = [int(np.sum(((np.roll(loop[k], -1, 0) - loop[k]) * (np.roll(loop[4] + loop[5], -1, 0) - np.roll(loop[4] + loop[5], 1, 0))).sum(1) < 0)) for k in (4, 5)]
    print('track edges on the walls that stand: half widths %.1f to %.1f m, the middle line %.0f m round; edge points stepping backwards: %d left, %d right'
          % (np.linalg.norm(loop[4] - loop[5], axis=1).min() / 2, np.linalg.norm(loop[4] - loop[5], axis=1).max() / 2, length, *back))
    res_bytes = L.write_splines(res_bytes, loop)
    # and a concrete wall to be seen on each invisible one closing a branch of the course
    kerbs += [wall_strips((x0, y0, z0), (x1, y1, z1)) for (x0, z0, y0), (x1, z1, y1) in walls]
    mats = [None] * len(kerbs)
    kerbs.append(brick_wall((bx0, by0, bz0), (bx1, by1, bz1))); mats.append(BRICK)
    # the corner's, on its walls' line at the loop's height there (the course's, 1.5 m over the side
    # roads, stood it in the air)
    Fc = np.array([centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * CORNER_SIDE * dist.get((CORNER_SIDE, i), half[i] + WIDE) for i in corner_pts])
    for a, b in zip(*(lambda k: (k[:-1], k[1:]))(chords(Fc, 0.5))):
        if np.hypot(*(Fc[b] - Fc[a])[[0, 2]]) > 0.5: kerbs.append(brick_wall(tuple(Fc[a]), tuple(Fc[b]))); mats.append(BRICK)
    kerbs += [f for f, _ in rails]; mats += [m for _, m in rails]
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
        floor = tunnel_faces(centre, half, gap)[0]  # the road through it
        kerbs.append(floor); mats.append(ROAD_PLAIN)
        yu0, yu1, yv0, yv1 = garage.YARD_GROUND
        corners = garage.to_world(np.array([[yu0, yv0], [yu0, yv1], [yu1, yv0], [yu1, yv1]]), 0.0)[:, [0, 2]]
        drawn = ground_test(res_bytes, hide, corners.min(0) - 5, corners.max(0) + 5)
        for fs, mat in garage.faces(centre, half) + garage.yard_faces(centre, half, drawn):  # the shop, its yard, fence and warehouses
            if fs: kerbs.append(fs); mats.append(mat)
        print('garage: %.0f m by %.0f m, %.1f m high, its road %.0f m' % (garage.U1 - garage.U0, garage.V1 - garage.V0, garage.TOP, 2 * len(gap)))
    # ground where nothing is drawn beside the new stretches (the void showed past the edges)
    found = void_ground(res_bytes, centre, half, dist0, sorted({i for r in runs(off) for i in r}), hide)
    def other_leg(q, own=25, reach=12.0):  # within `reach` of the road of a part of the loop not its own
        d = np.hypot(centre[:, 0] - q[0], centre[:, 2] - q[2])
        k, n = int(np.argmin(d)), len(centre)
        apart = np.abs((np.arange(n) - k + n // 2) % n - n // 2)
        return bool(np.any((apart > own) & (d < half + reach)))
    def foot(side, i):  # where the ground over the void starts, by the road
        return centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * side * dist0.get((side, i), half[i] + WIDE)
    # each run's points at the hairpin, by another part of the loop, in the garage or its yard (the
    # yard lays its own) or by the course's road (drawn, in meshes too wide for mesh_tris: at Turn
    # 2's exit a guardrail stood on it) left out, the rest kept in pieces (a run touching the garage
    # was dropped whole: the void showed beside side road 04 up to the yard)
    def by_course(side, i):
        out = np.array([left_[i][0], 0, left_[i][1]]) * side
        return not np.all(L.off_course([foot(side, i) + out * u for u in (1.0, 5.0)], sp, margin=0.0))
    skirts = []
    for side, run, f in found:
        ok = [not (np.hypot(*(foot(side, i)[[0, 2]] - HAIRPIN)) < HAIRPIN_R + 25 or other_leg(foot(side, i)) or by_course(side, i) or (side, i) in open_end
                   or garage.inside(foot(side, i)[[0, 2]], pad=3.0) or garage.in_yard(foot(side, i)[[0, 2]], pad=1.0)) for i in run]
        k = 0
        while k < len(run):
            if not ok[k]: k += 1; continue
            e = k
            while e < len(run) and ok[e]: e += 1
            if e - k >= 3: skirts.append((side, run[k:e], f[2 * k:2 * e]))
            k = e
    kerbs += [[f] for _, _, f in skirts]
    mats += [ASPHALT] * len(skirts)
    # and along each, on the old line, a guardrail where the edge has none and no sidewalk (the 3 m
    # concrete was everywhere); by the yard the yard's tin fence too, 1.5 m behind it, to hide the
    # buildings past it standing over nothing
    railed = {(side, i) for side, idx in stretches for i in idx} | set(kerbed) | no_rail
    masks = fences = 0
    for side, run, f in skirts:
        F = np.array([foot(side, i) for i in run])
        keep, stack = {0, len(F) - 1}, [(0, len(F) - 1)]  # the line within 1 m (a chord cut into a bend)
        while stack:
            a0, b0 = stack.pop()
            if b0 - a0 < 2: continue
            d = (F[b0] - F[a0])[[0, 2]]; rel = (F[a0 + 1:b0] - F[a0])[:, [0, 2]]
            off_ = np.linalg.norm(rel - np.outer(rel @ d / max(d @ d, 1e-12), d), axis=1)
            k = int(np.argmax(off_))
            if off_[k] > 1.0: keep.add(a0 + 1 + k); stack += [(a0, a0 + 1 + k), (a0 + 1 + k, b0)]
        ks = sorted(keep)
        for ka, kb in zip(ks[:-1], ks[1:]):
            a, b = F[ka], F[kb]
            if np.hypot(*(b - a)[[0, 2]]) <= 1: continue
            i_mid = run[(ka + kb) // 2]
            road = centre[i_mid][[0, 2]]
            if on_strip[i_mid] or in_lane[i_mid]: continue  # (the strip's walls invisible, the lane's tin)
            if not all((side, run[k]) in railed for k in (ka, kb)):
                for fs, m_ in barrier(tuple(a + (0, 0.06, 0)), tuple(b + (0, 0.06, 0)), road): kerbs.append(fs); mats.append(m_)
                masks += 1
            if garage.in_yard((a[[0, 2]] + b[[0, 2]]) / 2, pad=90.0) and not any((side, run[k]) in kerbed for k in (ka, kb)):
                out = np.array(left_[i_mid]) * side
                kerbs.append(garage.fence_faces(a[[0, 2]] + out * 1.5, b[[0, 2]] + out * 1.5, out, centre[i_mid][1]))
                mats.append(garage.TIN); fences += 1
    print('ground over the void beside the road: %d pieces of %d stretches; guardrails on it %d, fences %d' % (len(skirts), len(found), masks, fences))
    # and at the road's very edge, where it is bare short of what is drawn (outside the garage, and
    # off the concrete walls' stretch)
    drawn_ = ground_test(res_bytes, hide, centre[:, [0, 2]].min(0) - 20, centre[:, [0, 2]].max(0) + 20, wide=True)
    edges_ = edge_ground(drawn_, centre, half, dist, [i for i in sorted({i for r in runs(off) for i in r}) if not (in_gap_strict[i] or by_concrete[i])], sp, skip=open_end)
    kerbs += [[f] for f in edges_]; mats += [ASPHALT] * len(edges_)
    print('ground at the road\'s bare edges: %d stretches, %d points' % (len(edges_), sum(len(f) // 2 for f in edges_)))
    outside = bare_ground(res_bytes, hide, centre, HAIRPIN_OUT, sp)
    kerbs += [[f] for f in outside]; mats += [ASPHALT] * len(outside)
    print('ground outside the hairpin where nothing is drawn: %d rows, %d points' % (len(outside), sum(len(f) // 2 for f in outside)))
    # and a guardrail on every invisible wall left: the walls beside the new stretches with nothing
    # drawn standing on or by them (through turns, by the garage's parked row, round the hairpin: a
    # collision audit of the installed build found 700 m of them), the shorter stretches too
    seen = standing_test(res_bytes, hide, [f for fs in kerbs for f in fs], centre[:, [0, 2]].min(0) - 40, centre[:, [0, 2]].max(0) + 40)
    added = 0
    for side in (1, -1):
        bare = []  # (point, the wall's foot) where it stands unseen
        for i in sorted({i for r in runs(off) for i in r}):
            if (side, i) not in dist or by_concrete[i] or in_gap_strict[i] or on_strip[i] or in_lane[i] or (side, i) in no_rail: continue  # (none in the garage: its walls are the edge; none on the strip or the south lane: the user wanted them invisible there, or tin)
            F = centre[i] + np.array([left_[i][0], 0, left_[i][1]]) * side * dist[(side, i)]
            if L.off_course([F], sp, margin=0.0)[0] and not seen(F[0], F[2], centre[i][1]): bare.append((i, F))
        groups = []
        for i, F in bare:  # in runs of neighbouring points
            if groups and i == groups[-1][-1][0] + 1: groups[-1].append((i, F))
            else: groups.append([(i, F)])
        for run in groups:
            if len(run) < 2: continue
            F_ = np.array([f for _, f in run])
            for a, b in zip(*(lambda k: (k[:-1], k[1:]))(chords(F_, 0.5))):
                if np.hypot(*(F_[b] - F_[a])[[0, 2]]) < 1.0: continue
                for fs, m_ in barrier(tuple(F_[a]), tuple(F_[b]), centre[run[(a + b) // 2][0]][[0, 2]]): kerbs.append(fs); mats.append(m_)
                added += 1
    print('guardrails on invisible walls: %d pieces' % added)
    filled = fill_bricks(centre, dist, sorted({i for r in runs(off) for i in r}), sp)
    kerbs += filled; mats += [BRICK] * len(filled)
    print('brick walls where the walls had none in the brick area: %d' % len(filled))
    joins = join_bricks(centre, half)
    kerbs += joins; mats += [BRICK] * len(joins)
    print('brick walls joined across their gaps: %d' % len(joins))
    # each face simplified, then in pieces the size of buffers the scenery keeps loaded (the svb's):
    # larger ones stream in with their own part of the track only, and were never drawn here
    # (and the long ones cut, as short as the donors have room for: cut_long)
    plain = [(f if mat == HEAD else simplify(f), mat) for fs, mat in zip(kerbs, mats) for f in fs]
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
    # the meshes whose textures the new faces take: never borrowed themselves (their textures are
    # streamed in by near_textures; drawn where they stand to load them, a piece of a building far
    # off floated in the sky)
    sources = {int(m) for _, m in plain if m is not None} | {SIDEWALK}
    pool = donor_pool(res_bytes, shown | near | {L.DONOR} | sources, ppw, set(svb), sphere_recs)
    have = len(pool)
    room = sum(r[0] for r in pool)
    placed = None
    for most in (60.0, 80.0, 100.0, 140.0, 200.0, 1e9):  # (as short as the donors hold, each donor one place's)
        faces, fmats = [], []
        for f, mat in plain:
            for piece in ([f] if mat == HEAD else cut_long(f, most)): faces.append(piece); fmats.append(mat)
        if most < 1e9 and (sum(len(f) for f in faces) // 2 > 0.8 * room or len(faces) > 6 * len(pool)): continue
        try: placed = pack(faces, pool, fmats, most_reach=most if most < 1e9 else 2000.0)
        except SystemExit: continue
        break
    if placed is None: raise SystemExit('out of donor meshes: %d faces' % len(faces))
    print('long faces cut to %.0f m: %d faces, %d vertex pairs of the %d the donors hold' % (most, len(faces), sum(len(f) for f in faces) // 2, room))
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
    lights = {ASPHALT: road_light, ROAD_PLAIN: road_light, LAMP: lamp_light, RAIL: rail_light, HEAD: head_light, GUARD: post_light, POST: post_light}
    for (mesh, at), fs, mat in zip(picked, kerbs, mats):
        c1, r1 = write_strips(res_bytes, mesh, fs, material=mat, light=lights[mat] if mat in lights else (-32724, -32645) if mat is None else lightmap_st(res, mat))
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
    parked, ppw = garage.park(res_bytes, centre, svb, svb_raw, ppw, xb2.resources(bytes(res_bytes))[0], L.MODEL, pack_normal, unpack_normal, sphere_at, sphere_recs)
    hide -= set(parked)
    print('garage: %d parked vehicle meshes' % len(parked))
    # every cell streams in the textures (and lightmaps) the new faces take and the parked
    # vehicles' textures and vertex buffers
    streamed = (set(), set())
    for m in sorted(sources) + parked:
        a_ = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
        _, _, _, _, vb_, _, _, t0_, t1_ = struct.unpack_from('<IIIIHHHHH', res, L.MODEL + a_)
        streamed[0].update(t for t in (t0_, t1_) if t >= 9)
        if m in parked: streamed[1].add(vb_)
    print('streamed in every cell: %d textures, %d vertex buffers' % (len(streamed[0]), len(streamed[1])))
    # Every cell draws the same: what Pacific Shipyards II's cells 0 to 7 draw. pick_cells gave each
    # cell its own, by its stretch of the loop, and the road went black on whole stretches (cells
    # 8-13 and 18-20 of Circuit II): the cell the game shows at a place is not the one this counts
    # for it (not found yet how the game picks it), and the frame rate was no better (40 fps by the
    # garage and before the lap line, as before). CIRCUIT_PICK=1 builds that way, to look into it.
    if os.environ.get('CIRCUIT_PICK') == '1':
        use, per = pick_cells(cells_in, res_bytes, (loop[4] + loop[5]) / 2, hide)
        print('visibility: each cell draws %d to %d of Pacific Shipyards II\'s cells, and %d to %d meshes more' % (
            min(len(u) for u in use), max(len(u) for u in use), min(len(p_[0]) for p_ in per), max(len(p_[0]) for p_ in per)))
    else:
        use, per = [list(range(0, 8))] * n_cells, None
    # the meshes drawn as well whose vertex buffers nothing loads (not the svb's, not in Pacific
    # Shipyards II's cells' lists: 179 of them were in the draw lists and never drawn, the audit of 17
    # Nov): those within 60 m of the loop have their buffers and textures streamed in every cell (concrete
    # pipes and a dumpster by the start road), the rest (parts of landmarks 150 to 900 m off, 2 MB of
    # buffers) are left out of the lists
    loaded = set(svb) | {struct.unpack_from('<H', e_)[0] for c_ in cells_in[:8] for e_ in c_[2]}
    def buffer_of(m):
        return struct.unpack_from('<H', res_bytes, L.MODEL + struct.unpack_from('<I', res_bytes, L.MODEL + 4 + 4 * m)[0] + 16)[0]
    unloaded = {m for m in near - shown - dark if buffer_of(m) not in loaded}
    close = near_meshes(res_bytes, centre, 60.0) & unloaded
    for m in close:
        a_ = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
        _, _, _, _, vb_, _, _, t0_, t1_ = struct.unpack_from('<IIIIHHHHH', res, L.MODEL + a_)
        streamed[0].update(t for t in (t0_, t1_) if t >= 9); streamed[1].add(vb_)
    near -= unloaded - close
    print('drawn as well but never loaded: %d meshes; %d within 60 m streamed in, %d left out' % (len(unloaded), len(close), len(unloaded - close)))
    pvs, sizes = L.loop_pvs(pvs_in, use, per_cell=per, extra=[L.DONOR] + [m for m, _ in picked] + [g for (g, _), _ in glowed] + sorted(near - shown - dark) + parked, hide=hide,
                            textures=sorted(streamed[0]), buffers=sorted(streamed[1]))
    print('road: %d cross-sections on the strip; %d meshes hidden; visibility %d to %d meshes a cell' % (len(left), len(hide), min(sizes), max(sizes)))
    pvs = near_textures(pvs, res_bytes, (loop[4] + loop[5]) / 2, keep=streamed[0])
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
    import spherefix  # every mesh's sphere holding its vertices (sphere_at's search by value missed some donors' records:
    ppw, fixed = spherefix.fix(res_bytes, ppw, L.MODEL, quiet=True)  # the garage went at some angles, 4 Nov)
    print('bounding spheres: %d fixed by the mesh\'s own record' % len(fixed))
    import cellstream  # every cell one texture list, the textures nearest the loop (walls by the road blurred, 4 Nov)
    tex, info = cellstream.plan(res_bytes, pvs, ppw, L.MODEL)
    pvs = cellstream.apply(pvs, tex)
    print('textures: ' + info[1])
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
    # (17 Nov: the waypoints rounded off, the lap cut as the disc's are, and a line that uses the road)
    wps, nseg, sounds = aitrack.install(mega, L.TAG, ring, np.linalg.norm(loop[4] - loop[5], axis=1) / 2, line=aitrack.racing_line_wide(), stock_like=True, edges=(loop[4], loop[5]))
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
    only = os.environ.get('CIRCUIT_ONLY')  # testing: 'I' or 'II' alone
    if only != 'II': build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    if only == 'I': raise SystemExit
    # and the reverse, as Pacific Shipyards II is Pacific Shipyards': its own track, Hot Lap entry,
    # map tile (46), Pacific Shipyards II's logo and loading screen
    L.NAME, L.TAG = 'Pacific Shipyards Circuit II', 'VancouverLoopReverse'
    L.MAP_TILE, L.LOGO, L.LOAD_IMAGE = 46, 20, 'Load_Shipyards_II.xpr'
    build(sys.argv[1], sys.argv[2], None, reverse=True)
