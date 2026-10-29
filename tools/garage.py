"""The Pacific Shipyards Circuit's garage: an auto shop over the gap in place of a tunnel.

A box of corrugated tin over the gap (shipyardcircuit.GAP, where nothing is
drawn), laid out in the gap's frame: u along it from its east end (GAP[0])
west, v across (+v north of the road). The road comes in from side road 04
through a door in the east wall, runs the length of the shop and turns south
inside it, out through a door in the south wall onto side road 39. Each door
is where the road crosses a wall, as wide as the road and a little more, a
roll-up shutter's bottom showing under its lintel. Inside: a concrete floor,
the road's asphalt down the middle, service bays (shutter doors) along the
walls, strip lights under the roof, and on the north side a row of parked
vehicles (scenery meshes from far off that the circuit never shows, moved
here: they cost no borrowed meshes).

Faces are kerb_strips' form (lists of (position, normal, s, t) in strip
order) with the scenery mesh whose texture, lightmap and shader they take.
"""
import struct

import numpy as np

GAP = [(-129, -560), (-262, -726)]
U0, U1 = -4.0, 224.0       # the box along the gap: 14 m past the old tunnel's east mouth (the void showed past it), and just past side road 39's far edge
V0, V1 = -8.2, 15.0        # across: a metre past the road's south edge; to the north room for a row of parked vehicles
TOP = 7.2                  # the roof (world y)
BASE = -1.2                # the walls' feet, under the ground
DOOR_H = 4.8               # the doors' opening over the road
SHUTTER_H = 0.9            # the raised shutter showing under each lintel
OPEN_PAD = 0.6             # each door this much wider than the road each side

TIN = 2984      # building_steelmill_trailer_vb3: building_wall_tin (27 a metre across, 99 up)
SHUTTER = 2871  # building_warehouse_green_00_vb3: building_garagedoor_02, a roll-up shutter 3.6 m wide, 4.45 m high
BAY = 1118      # prop_propanestand04_vb2: building_garagedoor_01, a shutter with a door beside it
LAMP = 1359     # light_box07: a strip light (the glow texture)
BAY_EVERY = 14.0
LIGHT_EVERY, LIGHT_LEN = 12.0, 3.0

# vehicles moved in: (its meshes, u, v, heading in degrees from +u), parked on the floor nose in, across the bays
PARKED = [((2600,), 30.0, 11.8, 90), ((2591,), 52.0, 11.8, 90), ((2542, 2543), 76.0, 11.8, 90),
          ((2595,), 104.0, 11.8, 90), ((2602,), 128.0, 11.8, 90), ((2592,), 152.0, 11.8, 90), ((2601,), 176.0, 11.8, 90)]


def basis():
    g0, g1 = np.array(GAP[0], float), np.array(GAP[1], float)
    u = (g1 - g0) / np.linalg.norm(g1 - g0)
    return g0, u, np.array([-u[1], u[0]])


def to_uv(p):
    """World (x, z) points to the box's (u, v)."""
    g0, u, v = basis()
    p = np.asarray(p, float) - g0
    return np.stack([p @ u, p @ v], -1)


def to_world(uv, y):
    g0, u, v = basis()
    uv = np.asarray(uv, float)
    xz = g0 + uv[..., :1] * u + uv[..., 1:2] * v
    return np.stack([xz[..., 0], np.broadcast_to(y, xz[..., 0].shape), xz[..., 1]], -1)


def inside(xz, pad=0.0):
    q = to_uv(xz)
    return (q[..., 0] > U0 - pad) & (q[..., 0] < U1 + pad) & (q[..., 1] > V0 - pad) & (q[..., 1] < V1 + pad)


def points(centre):
    """The loop points inside the box."""
    return [i for i in range(len(centre)) if inside(centre[i][[0, 2]])]


def floor_y(centre, uv):
    """The road's height nearest each (u, v) (the floor follows it)."""
    w = to_world(uv, 0.0)[..., [0, 2]].reshape(-1, 2)
    d = np.hypot(w[:, None, 0] - centre[None, :, 0], w[:, None, 1] - centre[None, :, 2])
    return centre[d.argmin(1), 1].reshape(np.shape(uv)[:-1])


WALLS = [  # (from (u, v), to (u, v), its outward normal in (u, v))
    ((U0, V1), (U0, V0), (-1, 0)),   # east
    ((U0, V0), (U1, V0), (0, -1)),   # south
    ((U1, V0), (U1, V1), (1, 0)),    # west
    ((U1, V1), (U0, V1), (0, 1)),    # north
]


def rect_walls(u0, u1, v0, v1):
    """A box's walls as WALLS has them (from, to, outward normal)."""
    return [((u0, v1), (u0, v0), (-1, 0)), ((u0, v0), (u1, v0), (0, -1)), ((u1, v0), (u1, v1), (1, 0)), ((u1, v1), (u0, v1), (0, 1))]


def openings(centre, half, walls=WALLS, pad=None):
    """Per wall, the stretches (from, to: metres along it) where the road crosses it, `pad` (OPEN_PAD)
    wider each side."""
    pad = OPEN_PAD if pad is None else pad
    out = []
    c = to_uv(centre[:, [0, 2]])
    for a, b, _ in walls:
        a, b = np.array(a), np.array(b)
        L_ = np.linalg.norm(b - a)
        s = np.arange(0, L_ + 1e-9, 0.25)
        pts = a + (b - a) / L_ * s[:, None]
        d = np.hypot(pts[:, None, 0] - c[None, :, 0], pts[:, None, 1] - c[None, :, 1])
        k = d.argmin(1)
        hit = d[np.arange(len(s)), k] < half[k] + pad
        runs, start = [], None
        for j, h in enumerate(hit):
            if h and start is None: start = s[j]
            if not h and start is not None: runs.append((start, s[j - 1])); start = None
        if start is not None: runs.append((start, s[-1]))
        out.append(runs)
    return out


def _face(a, b, n, sa, ta, sb, tb):
    """A strip face from polylines a (one edge) and b (the other), normal n, as kerb_strips' faces."""
    pairs = [((a[k], n, sa[k], ta[k]), (b[k], n, sb[k], tb[k])) for k in range(len(a))]
    a0, b0, a1 = pairs[0][0][0], pairs[0][1][0], pairs[1][0][0]
    if np.dot(np.cross(b0 - a0, a1 - a0), n) > 0: pairs = [(q, p) for p, q in pairs]
    return [v for pr in pairs for v in pr]


def _wall(a, b, n, y0, y1, s0, inward=False, every=6.0, tex=(27, 99, None)):
    """A wall face from (u, v) a to b between heights y0 and y1 (arrays along it or numbers), its
    texture (tex: s a metre along, t a metre down from height tex[2], TOP if None; tin's by
    default) from s0 along it; facing out (n) or in."""
    a, b = np.array(a, float), np.array(b, float)
    L_ = np.linalg.norm(b - a)
    k = np.linspace(0, 1, max(2, int(np.ceil(L_ / every)) + 1))
    uv = a + (b - a) * k[:, None]
    y0 = np.broadcast_to(y0, k.shape) if np.ndim(y0) == 0 else y0
    y1 = np.broadcast_to(y1, k.shape) if np.ndim(y1) == 0 else y1
    lo, hi = to_world(uv, 0.0), to_world(uv, 0.0)
    lo[:, 1], hi[:, 1] = y0, y1
    g0, u, v = basis()
    nw = n[0] * u + n[1] * v
    nn = np.array([nw[0], 0.0, nw[1]]) * (-1 if inward else 1)
    s = -32768 + tex[0] * (s0 + L_ * k)
    top = TOP if tex[2] is None else tex[2]
    return _face(lo, hi, nn, s, -32768 + tex[1] * (top - lo[:, 1]), s, -32768 + tex[1] * (top - hi[:, 1]))


def faces(centre, half):
    """The shop's faces: [(faces, material)], material a mesh number or None (the sidewalk's
    concrete), 'ASPHALT' (the road's)."""
    out = []
    up = np.array([0.0, 1, 0])
    opens = openings(centre, half)
    road_y = lambda uv: floor_y(centre, np.array(uv, float)[None])[0]
    for (a, b, n), runs in zip(WALLS, opens):
        a, b = np.array(a, float), np.array(b, float)
        L_ = np.linalg.norm(b - a)
        d = (b - a) / L_
        cuts = [0.0]
        for r0, r1 in runs: cuts += [r0, r1]
        cuts.append(L_)
        tin = []
        for j in range(0, len(cuts), 2):  # the solid stretches, floor to roof, both faces
            s0, s1 = cuts[j], cuts[j + 1]
            if s1 - s0 < 0.05: continue
            for inward in (False, True):
                tin.append(_wall(a + d * s0, a + d * s1, n, BASE, TOP, s0, inward))
        shutters = []
        for r0, r1 in runs:  # over each door: its lintel, and the shutter's bottom under it
            ys = road_y(a + d * (r0 + r1) / 2) + DOOR_H
            for inward in (False, True):
                tin.append(_wall(a + d * r0, a + d * r1, n, ys, TOP, r0, inward))
                f = _wall(a + d * r0, a + d * r1, n, ys - SHUTTER_H, ys, 0.0, inward)
                # the shutter's texture (141 a metre across, 115 a metre down from its top): its
                # slats from 2 m down, the rolled-up door's bottom
                along = lambda p: np.linalg.norm(to_uv(p[[0, 2]]) - (a + d * r0))
                shutters.append([(p, nn, -32767 + 141 * along(p), -32767 + 115 * (2.0 + ys - p[1])) for p, nn, _, _ in f])
        out += [(tin, TIN), (shutters, SHUTTER)]
    # the roof, its underside and top
    k = np.linspace(U0, U1, int((U1 - U0) / 8) + 1)
    roof = []
    for y, nn in ((TOP, -up), (TOP + 0.05, up)):
        a_, b_ = to_world(np.stack([k, np.full(len(k), V0)], 1), y), to_world(np.stack([k, np.full(len(k), V1)], 1), y)
        roof.append(_face(a_, b_, nn, -32768 + 27 * (k - U0), np.full(len(k), -32768.0), -32768 + 27 * (k - U0), np.full(len(k), -32768 + 99 * (V1 - V0))))
    out.append((roof, TIN))
    # the floor: concrete over the whole box, under the road's asphalt
    rows = np.linspace(V0, V1, 5)
    k = np.linspace(U0, U1, int((U1 - U0) / 4) + 1)
    floor = []
    for v0_, v1_ in zip(rows[:-1], rows[1:]):
        uva, uvb = np.stack([k, np.full(len(k), v0_)], 1), np.stack([k, np.full(len(k), v1_)], 1)
        a_, b_ = to_world(uva, floor_y(centre, uva) - 0.02), to_world(uvb, floor_y(centre, uvb) - 0.02)
        floor.append(_face(a_, b_, up, -32000 + 53 * (k - U0), np.full(len(k), -32000 + 51.7 * (v0_ - V0)), -32000 + 53 * (k - U0), np.full(len(k), -32000 + 51.7 * (v1_ - V0))))
    out.append((floor, None))
    # service bays along the inside of the long walls, where nothing crosses them
    bays = []
    for (a, b, n), runs in zip(WALLS, opens):
        a, b = np.array(a, float), np.array(b, float)
        L_ = np.linalg.norm(b - a)
        if L_ < 30: continue
        d = (b - a) / L_
        for s in np.arange(BAY_EVERY / 2, L_ - 4, BAY_EVERY):
            if any(r0 - 4 < s < r1 + 4 for r0, r1 in runs): continue
            p0, p1 = a + d * (s - 1.8) - np.array(n) * 0.03, a + d * (s + 1.8) - np.array(n) * 0.03
            y = road_y((p0 + p1) / 2)
            f = _wall(p0, p1, n, y, y + 4.45, 0.0, inward=True, every=4.0)
            bays.append([(p, nn, -32767 + 512 * np.linalg.norm(to_uv(p[[0, 2]]) - p0) / 3.6, -32767 + 115 * (y + 4.45 - p[1])) for p, nn, _, _ in f])
    out.append((bays, BAY))
    # strip lights under the roof, a short fitting every LIGHT_EVERY m in rows along the shop (one
    # light the shop's length was a band across the roof)
    lights = []
    for v_ in (-3.0, 4.0, 11.0):
        for u_ in np.arange(U0 + LIGHT_EVERY / 2, U1 - 2, LIGHT_EVERY):
            kk = np.array([u_ - LIGHT_LEN / 2, u_ + LIGHT_LEN / 2])
            a_, b_ = to_world(np.stack([kk, np.full(2, v_)], 1), TOP - 0.05), to_world(np.stack([kk, np.full(2, v_ + 0.5)], 1), TOP - 0.05)
            lights.append(_face(a_, b_, -up, np.full(2, -6000.0), np.full(2, -6000.0), np.full(2, 6000.0), np.full(2, 6000.0)))
    out.append((lights, LAMP))
    return out


def lateral(centre, half, i, side, left):
    """How far from loop point i the box's wall stands to its `side` (+1 left), straight out."""
    c = to_uv(centre[i][[0, 2]])
    g0, u, v = basis()
    l = np.array(left[i]) * side
    du = np.array([l @ u, l @ v])
    best = half[i] + 25.0
    for a, b, n in WALLS:
        a, b = np.array(a, float), np.array(b, float)
        m = np.array([du, a - b]).T
        if abs(np.linalg.det(m)) < 1e-9: continue
        t, w = np.linalg.solve(m, a - c)
        if t > 0 and 0 <= w <= 1: best = min(best, t)
    return best


def meshes_inside(res, centre, model=0x4e0600, share=0.6):
    """The scenery meshes standing in the shop: most of their vertices (`share`) inside the box,
    and reaching 0.3 m over its floor (ground under it, and a sidewalk only running into it, are
    left: clear_tunnel moves those vertices out)."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, model)[0]
    out = set()
    for m in range(n):
        a = struct.unpack_from('<I', res, model + 4 + 4 * m)[0]
        _, _, _, vbytes, vb, stride = struct.unpack_from('<IIIIHH', res, model + a)
        if stride != 6 or vbytes % 24 or not vbytes or not (9 <= vb < len(names) + 9): continue
        v = np.frombuffer(bytes(res[names[vb - 9][3]:names[vb - 9][3] + vbytes]), '<f4').reshape(-1, 6)[:, :3]
        if not np.all(np.isfinite(v)): continue
        ins = inside(v[:, [0, 2]])
        if ins.mean() < share: continue
        if v[ins, 1].max() > floor_y(centre, to_uv(v[ins][:, [0, 2]])).min() + 0.3: out.add(m)
    return out


def collision(col, centre, half):
    """The box's walls (both faces, BASE to 4 m over the road) where no door is. No floor of its
    own: the road's ground runs through (a second ground at nearly its height made the doors
    bumpy). Returns triangles added."""
    added = 0
    up = np.array([0.0, 1, 0])
    for (a, b, n), runs in zip(WALLS, openings(centre, half)):
        a, b = np.array(a, float), np.array(b, float)
        L_ = np.linalg.norm(b - a)
        d = (b - a) / L_
        cuts = [0.0] + [x for r in runs for x in r] + [L_]
        for j in range(0, len(cuts), 2):
            s0, s1 = cuts[j], cuts[j + 1]
            if s1 - s0 < 0.05: continue
            p0, p1 = to_world(a + d * s0, BASE), to_world(a + d * s1, BASE)
            q = [p0, p1, p1 + up * (4.0 - BASE + 1), p0 + up * (4.0 - BASE + 1)]
            for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                col.add(0x900, tri); added += 1
    return added


def parked_boxes(res, centre, names, model, ppw, sphere_at):
    """Where park() sets the PARKED vehicles: each one's footprint, four (x, z) corners in order,
    and the floor's height under it, for their collision (before they are moved: the collision is
    written first); none for one park() leaves (a mesh's bounding sphere not found)."""
    dt = np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)])
    g0, u, _ = basis()
    out = []
    for meshes, u_, v_, heading in PARKED:
        ps = []
        for mesh in meshes:
            a = struct.unpack_from('<I', res, model + 4 + 4 * mesh)[0]
            _, _, _, vbytes, vb = struct.unpack_from('<IIIIH', res, model + a)
            if vbytes % 24: break
            o = names[vb - 9][3]
            p = np.frombuffer(bytes(res[o:o + vbytes]), dt)['p'].astype(float)
            c = (p.min(0) + p.max(0)) / 2
            if sphere_at(bytes(ppw), c, float(np.max(np.linalg.norm(p - c, axis=1)))) is None: break
            ps.append(p)
        if len(ps) != len(meshes): continue
        allp = np.concatenate(ps)
        lo, hi = allp.min(0), allp.max(0)
        own = 0.0 if hi[0] - lo[0] >= hi[2] - lo[2] else 90.0  # as park()
        ang = np.radians(heading) + np.arctan2(u[1], u[0]) - np.radians(own)
        R = np.array([[np.cos(ang), 0, -np.sin(ang)], [0, 1, 0], [np.sin(ang), 0, np.cos(ang)]])
        base = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
        y = floor_y(centre, np.array([[u_, v_]]))[0]
        target = to_world(np.array([u_, v_]), y)
        corners = [np.array([x, lo[1], z]) for x, z in ((lo[0], lo[2]), (hi[0], lo[2]), (hi[0], hi[2]), (lo[0], hi[2]))]
        out.append(([((q - base) @ R.T + target)[[0, 2]] for q in corners], y))
    return out


def park(res, centre, svb, svb_raw, ppw, names, model, pack_normal, unpack_normal, sphere_at):
    """The PARKED vehicles moved into the shop, each one's meshes together: turned to its heading
    (from the long side of its footprint) and set on the floor; their svb copies and bounding
    spheres (ppw) too. Returns ([meshes moved], ppw)."""
    ppw = bytearray(ppw)
    moved = []
    dt = np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)])
    g0, u, _ = basis()
    for meshes, u_, v_, heading in PARKED:
        parts = []
        for mesh in meshes:
            a = struct.unpack_from('<I', res, model + 4 + 4 * mesh)[0]
            _, _, _, vbytes, vb = struct.unpack_from('<IIIIH', res, model + a)
            if vbytes % 24: break
            o = names[vb - 9][3]
            v = np.frombuffer(bytes(res[o:o + vbytes]), dt).copy()
            p = v['p'].astype(float)
            c = (p.min(0) + p.max(0)) / 2
            at = sphere_at(bytes(ppw), c, float(np.max(np.linalg.norm(p - c, axis=1))))
            if at is None: break
            parts.append((mesh, vb, o, vbytes, v, at))
        if len(parts) != len(meshes):
            print('  parked %s: a mesh or its bounding sphere not found, left' % (meshes,)); continue
        allp = np.concatenate([q[4]['p'] for q in parts]).astype(float)
        lo, hi = allp.min(0), allp.max(0)
        own = 0.0 if hi[0] - lo[0] >= hi[2] - lo[2] else 90.0  # its long side along x or z
        ang = np.radians(heading) + np.arctan2(u[1], u[0]) - np.radians(own)
        R = np.array([[np.cos(ang), 0, -np.sin(ang)], [0, 1, 0], [np.sin(ang), 0, np.cos(ang)]])
        base = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])  # its footprint's middle, at its wheels
        target = to_world(np.array([u_, v_]), floor_y(centre, np.array([[u_, v_]]))[0])
        for mesh, vb, o, vbytes, v, at in parts:
            p2 = (v['p'].astype(float) - base) @ R.T + target
            n2 = np.array([unpack_normal(int(x)) for x in v['n']]) @ R.T
            v['p'] = p2.astype('<f4')
            v['n'] = [pack_normal(x) for x in n2]
            res[o:o + vbytes] = v.tobytes()
            if vb in svb:
                so, _ = svb[vb]
                svb_raw[so:so + vbytes] = res[o:o + vbytes]
            c2 = (p2.min(0) + p2.max(0)) / 2
            struct.pack_into('<4f', ppw, at, float(np.max(np.linalg.norm(p2 - c2, axis=1))), *c2)
            moved.append(mesh)
    return moved, bytes(ppw)


# the yard round the shop: concrete over the void, inside a tin fence; warehouses on its empty lots
YARD = (-45.0, 262.0, -50.0, 55.0)   # u0, u1, v0, v1
YARD_GROUND = (-77.0, 262.0, -66.0, 55.0)  # its ground over the void, reaching past its east fence's south end (a
                                          # wedge of void showed beside side road 04 there)
WEDGE_CORNER = (-132.9, -466.9)      # parkinglot_12's north-east corner, 8 m off side road 04 (x, z)
YARD_DROP = 0.12                    # under the road and the drawn ground (they cover it where they are)
YARD_CELL = 4.0                      # its ground in squares this size, laid where none is drawn
SKIRT = 1.5                          # its edges' drop
FENCE_H = 5.0
FENCE_OPEN = 25.0   # the fence ends this far from the road each side where the loop crosses it (cut at
                    # the road's edge its ends stood by it, random slabs)
WAREHOUSE = 3787  # building_federal_00_vb2: building_warehouse_03, concrete with rows of windows (51 a metre across, 18 up)
WAREHOUSES = [  # (u0, u1, v0, v1, height): on the yard's empty lots, clear of the road
    (10.0, 110.0, 24.0, 46.0, 11.0), (125.0, 215.0, 24.0, 46.0, 9.0),   # north of the shop
    (100.0, 158.0, -48.0, -20.0, 10.0),                                 # south, between the two buildings
    (236.0, 258.0, -40.0, 40.0, 9.0),                                   # west, past side road 39
    (-40.0, -12.0, 20.0, 50.0, 8.0)]                                    # by the shop's east door


def yard_void(centre, drawn):
    """Which YARD_CELL squares of YARD_GROUND have no ground drawn (drawn(x, z, y) as
    shipyardcircuit.ground_test's, at the road's height): a bool array [v row, u column]."""
    u0, u1, v0, v1 = YARD_GROUND
    us, vs = np.arange(u0, u1, YARD_CELL), np.arange(v0, v1, YARD_CELL)
    void = np.zeros((len(vs), len(us)), bool)
    for r, v_ in enumerate(vs):
        for c, u_ in enumerate(us):
            # its middle and four points in from its corners
            q = np.array([[u_ + a * YARD_CELL, v_ + b * YARD_CELL] for a, b in ((0.5, 0.5), (0.12, 0.12), (0.88, 0.12), (0.12, 0.88), (0.88, 0.88))])
            y = floor_y(centre, q[:1])[0]
            w = to_world(q, 0.0)
            void[r, c] = sum(not drawn(p[0], p[2], y) for p in w) >= 4
    return void


def yard_faces(centre, half, drawn=None):
    """The yard's faces: its ground (concrete, a face a run of squares along u) where none is drawn
    (all of it if `drawn` is None), each run's sides dropping SKIRT m where it ends by drawn ground or
    the yard's edge (it lay over the drawn ground, steps and ledges, and the void showed black under
    its edges); the fence (tin, both faces, open where the loop crosses it) and the warehouses (their
    outsides). [(faces, material)]."""
    u0, u1, v0, v1 = YARD_GROUND
    up = np.array([0.0, 1, 0])
    us, vs = np.arange(u0, u1, YARD_CELL), np.arange(v0, v1, YARD_CELL)
    void = yard_void(centre, drawn) if drawn is not None else np.ones((len(vs), len(us)), bool)
    gy = lambda uv: floor_y(centre, uv) - YARD_DROP
    st = lambda d: -32000 + 53 * (d % 500)  # the concrete's texture, 53 a metre
    ground, skirts = [], []
    def skirt(a, b, n):  # a vertical face from (u, v) a to b at the ground's edge, down SKIRT m
        k = np.linspace(0, 1, max(2, int(np.linalg.norm(np.subtract(b, a)) / YARD_CELL) + 1))
        uv = np.asarray(a, float) + np.subtract(b, a) * k[:, None]
        top = to_world(uv, gy(uv))
        bot = top.copy(); bot[:, 1] -= SKIRT
        g0, u, v = basis()
        nw = n[0] * u + n[1] * v
        along = np.linalg.norm(np.subtract(b, a)) * k
        skirts.append(_face(top, bot, np.array([nw[0], 0.0, nw[1]]), st(along), np.full(len(k), -32000.0), st(along), np.full(len(k), -32000 + 53 * SKIRT)))
    for r, v_ in enumerate(vs):
        va, vb_ = v_, min(v_ + YARD_CELL, v1)
        c = 0
        while c < len(us):
            if not void[r, c]: c += 1; continue
            e = c
            while e < len(us) and void[r, e]: e += 1
            k = np.append(us[c:e], min(us[e - 1] + YARD_CELL, u1))
            A, B = np.stack([k, np.full(len(k), va)], 1), np.stack([k, np.full(len(k), vb_)], 1)
            ground.append(_face(to_world(A, gy(A)), to_world(B, gy(B)), up, st(k - u0), np.full(len(k), st(va - v0)), st(k - u0), np.full(len(k), st(vb_ - v0))))
            skirt((k[0], va), (k[0], vb_), (-1, 0))
            skirt((k[-1], va), (k[-1], vb_), (1, 0))
            for rr, vv, n in ((r - 1, va, (0, -1)), (r + 1, vb_, (0, 1))):  # along its long sides where the next row has no ground of ours
                j = c
                while j < e:
                    if 0 <= rr < len(vs) and void[rr, j]: j += 1; continue
                    m_ = j
                    while m_ < e and not (0 <= rr < len(vs) and void[rr, m_]): m_ += 1
                    skirt((us[j], vv), (min(us[m_ - 1] + YARD_CELL, u1), vv), n)
                    j = m_
            c = e
    fence = []
    walls = rect_walls(*YARD)
    for (a, b, n), runs in zip(walls, openings(centre, half, walls, FENCE_OPEN)):
        a, b = np.array(a, float), np.array(b, float)
        L_ = np.linalg.norm(b - a)
        d = (b - a) / L_
        cuts = [0.0] + [x for r in runs for x in r] + [L_]
        for j in range(0, len(cuts), 2):
            s0, s1 = cuts[j], cuts[j + 1]
            if s1 - s0 < 0.5: continue
            y = floor_y(centre, np.array([a + d * (s0 + s1) / 2]))[0]
            for inward in (False, True):
                fence.append(_wall(a + d * s0, a + d * s1, n, y - 1.0, y + FENCE_H, s0, inward, every=12.0, tex=(27, 99, y + FENCE_H)))
    sheds = []
    for w0, w1, x0, x1, h in WAREHOUSES:
        for a, b, n in rect_walls(w0, w1, x0, x1):
            a, b = np.array(a, float), np.array(b, float)
            y = floor_y(centre, np.array([(a + b) / 2]))[0]
            sheds.append(_wall(a, b, n, y - 1.0, y + h, 0.0, every=12.0, tex=(51, 18, y + h + 8)))
    # and the fence on from its south-east corner to the lot's corner by side road 04, across the
    # wedge between the road and the lot (parkinglot_12, its edge at an angle to the ground's squares
    # and 1.3 m under the road: the void showed in teeth along it)
    a = to_world(np.array([YARD[0], YARD[2]]), 0.0)[[0, 2]]
    b = np.array(WEDGE_CORNER)
    d = (b - a) / np.linalg.norm(b - a)
    out = np.array([-d[1], d[0]])
    road = centre[np.argmin(np.hypot(centre[:, 0] - (a[0] + b[0]) / 2, centre[:, 2] - (a[1] + b[1]) / 2))][[0, 2]]
    if out @ (road - (a + b) / 2) > 0: out = -out
    fence += fence_faces(a, b, out, floor_y(centre, to_uv((a + b) / 2)[None])[0])
    return [(ground + skirts, None), (fence, TIN), (sheds, WAREHOUSE)]


def in_yard(xz, pad=0.0):
    q = to_uv(xz)
    u0, u1, v0, v1 = YARD
    return (q[..., 0] > u0 - pad) & (q[..., 0] < u1 + pad) & (q[..., 1] > v0 - pad) & (q[..., 1] < v1 + pad)


def fence_faces(a, b, out, y):
    """A stretch of the yard's fence (tin, both faces) from world (x, z) a to b, `out` the unit
    (x, z) away from the road, its foot at height y."""
    g0, u, v = basis()
    n = (float(np.dot(out, u)), float(np.dot(out, v)))
    A, B = to_uv(np.asarray(a, float)), to_uv(np.asarray(b, float))
    return [_wall(A, B, n, y - 1.0, y + FENCE_H, 0.0, inward, every=12.0, tex=(27, 99, y + FENCE_H)) for inward in (False, True)]


def yard_collision(col, centre, half):
    """The fence's walls (both faces, 4 m) where the loop does not cross it. Returns triangles."""
    added = 0
    up = np.array([0.0, 1, 0])
    walls = rect_walls(*YARD)
    for (a, b, n), runs in zip(walls, openings(centre, half, walls, FENCE_OPEN)):
        a, b = np.array(a, float), np.array(b, float)
        L_ = np.linalg.norm(b - a)
        d = (b - a) / L_
        cuts = [0.0] + [x for r in runs for x in r] + [L_]
        for j in range(0, len(cuts), 2):
            s0, s1 = cuts[j], cuts[j + 1]
            if s1 - s0 < 0.5: continue
            p0, p1 = to_world(a + d * s0, -2.0), to_world(a + d * s1, -2.0)
            q = [p0, p1, p1 + up * 6.5, p0 + up * 6.5]
            for tri in ([q[0], q[1], q[2]], [q[2], q[3], q[0]], [q[2], q[1], q[0]], [q[0], q[3], q[2]]):
                col.add(0x900, tri); added += 1
    return added
