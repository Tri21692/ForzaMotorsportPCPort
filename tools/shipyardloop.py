"""The Pacific Shipyards Loop: a short circuit made from Pacific Shipyards.

After Pacific Shipyards II's start the course wraps a paved truck lot: a
lower road out to a far corner, an upper road back. A link of ~150 m across
the lot, from the upper road's kink to the lower road's corner, closes it.
This builds, from the disc's Vancouver files:

  - the loop's edge splines (the six of MODEL_QuickPreview_Splines: curbing,
    driveable and road, inner and outer; 624 points each, then the index
    pairs 0-1 ... 622-623, in the same buffers), in Pacific Shipyards II's
    direction, the lap line at point 0;
  - its collision: the link as road, the walls across its two ends removed,
    and walls across the old course where it leaves the loop.

  python tools/shipyardloop.py <disc> <mods folder> [preview.png]
"""
import os
import re
import struct
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coledit

SPLINES = 0x504200  # in the unpacked QuickPreview1.xb2: six buffers, 0x2800 apart
STEP = 0x2800
POINTS = 624
KINK = (-495.0, -77.5)   # the upper road's kink
TIP = (-455.0, -222.5)   # the lower road's corner
LINK_WIDTH = 14.0        # metres, edge to edge
START = tuple(float(v) for v in os.environ['LOOP_START'].split(',')) if os.environ.get('LOOP_START') else (-365.0, -296.0)  # the lap line: on the lower road, 70 m on from where the link joins it


def unpack_xb2(path):
    d = open(path, 'rb').read()
    out, off = bytearray(), 0
    while off < len(d) and d[off] == 0x78:
        o = zlib.decompressobj()
        out += o.decompress(d[off:])
        off = (off + len(d) - off - len(o.unused_data) + 2047) & ~2047
    return out


def read_splines(res):
    return [np.frombuffer(res, '<f4', count=3 * POINTS, offset=SPLINES + k * STEP).reshape(-1, 3).astype(float) for k in range(6)]


def nearest(c, p):
    return int(np.argmin(np.hypot(c[:, 0] - p[0], c[:, 2] - p[1])))


def hermite(p0, t0, p1, t1, n):
    s = np.linspace(0, 1, n)[:, None]
    h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
    return h00 * p0 + h10 * t0 + h01 * p1 + h11 * t1


def loop_edges(sp, back=1, ahead=0):
    """The loop's six edges in Pacific Shipyards II's direction (the reverse of the buffers'), as
    lists of points with a shared parameter: the course from the lower road's corner round the
    lot to the upper road's kink, then the link back."""
    c = (sp[4] + sp[5]) / 2
    ik, it = nearest(c, KINK), nearest(c, TIP)
    assert ik < it, (ik, it)
    a, b = ik + ahead, it - back  # where the link leaves the course and joins it again (forward order)
    # forward order: ... kink -> far corner -> corner ...; the loop (forward) is c[a..b], then the link b -> a
    tan = lambda i: (c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)]) / np.linalg.norm(c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)])
    p0, p1 = c[b], c[a]
    d = np.linalg.norm(p1 - p0)
    link_c = hermite(p0, tan(b) * d * 1.2, p1, tan(a) * d * 1.2, 60)[1:-1]
    edges = []
    for k in range(6):
        e = sp[k]
        side = 1 if k % 2 else -1
        half = [np.linalg.norm(sp[k][i] - c[i]) for i in (b, a)]
        # the link's edge: the centre line moved sideways, its half width going from the course's to the link's
        t = np.gradient(link_c, axis=0)
        nrm = np.stack([t[:, 2], np.zeros(len(t)), -t[:, 0]], 1)
        nrm /= np.linalg.norm(nrm, axis=1)[:, None]
        # which way is this edge? as the course has it at b
        tb = tan(b)
        nb = np.array([tb[2], 0, -tb[0]]) / np.hypot(tb[0], tb[2])
        sgn = np.sign(np.dot(sp[k][b] - c[b], nb)) or side
        w = np.interp(np.linspace(0, 1, len(link_c)), [0, 0.3, 0.7, 1], [half[0], LINK_WIDTH / 2, LINK_WIDTH / 2, half[1]])
        link_e = link_c + nrm * (sgn * w)[:, None]
        fwd = np.concatenate([e[a:b + 1], link_e])  # forward: lot loop then the link back to a
        edges.append(fwd)
    centre = np.concatenate([c[a:b + 1], link_c])
    return edges, centre, (a, b), np.vstack([c[b], link_c, c[a]])


def resample(edges, centre, start, n=POINTS):
    """n points on each edge at equal steps of the centre line, the loop reversed (II's direction)
    and starting nearest the point `start` (x, z)."""
    edges = [e[::-1] for e in edges]
    centre = centre[::-1]
    i = nearest(centre, start)
    edges = [np.roll(e, -i, axis=0) for e in edges]
    centre = np.roll(centre, -i, axis=0)
    closed = np.vstack([centre, centre[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
    length = s[-1]
    want = np.linspace(0, length, n, endpoint=False)
    out = []
    for e in edges:
        ec = np.vstack([e, e[:1]])
        out.append(np.stack([np.interp(want, s, ec[:, j]) for j in range(3)], 1))
    return out, length


def write_splines(res, edges):
    res = bytearray(res)
    for k, e in enumerate(edges):
        o = SPLINES + k * STEP
        res[o:o + 12 * POINTS] = e.astype('<f4').tobytes()
    return res


def preview(path, sp, loop, centre, col=None):
    import forzaxpr
    lo, hi = loop[4].min(0) - 60, loop[4].max(0) + 60
    s = 2.0
    x0, z1 = lo[0], hi[2]
    W, H = int((hi[0] - lo[0]) * s), int((hi[2] - lo[2]) * s)
    img = np.zeros((H, W, 4), np.uint8); img[..., 3] = 255
    def put(p, col):
        px, py = int((p[0] - x0) * s), int((z1 - p[2]) * s)
        if 0 <= px < W and 0 <= py < H: img[py, px, :3] = col
    def line(pts, col):
        for a, b in zip(pts[:-1], pts[1:]):
            for t in np.linspace(0, 1, int(np.linalg.norm(b - a) * s) + 2): put(a + (b - a) * t, col)
    for k in (4, 5): line(sp[k], (90, 90, 90))
    if col:
        for surface, pts, n, words in col.triangles():
            p = np.array(pts)
            if p[:, 0].max() < lo[0] or p[:, 0].min() > hi[0] or p[:, 2].max() < lo[2] or p[:, 2].min() > hi[2]: continue
            if abs(n[1]) > 0.7: continue
            line(np.vstack([p, p[:1]]), (255, 60, 60))
    for k in (4, 5): line(np.vstack([loop[k], loop[k][:1]]), (80, 220, 255))
    line(centre[:40], (255, 230, 0))  # the first 40 points: the direction of travel from the lap line
    for q in loop[4][:1]: [put(q + np.array([dx, 0, dz]), (255, 40, 40)) for dx in range(-3, 4) for dz in range(-3, 4)]
    forzaxpr.png(path, img)


def strip(centre, width):
    """A strip `width` wide along a centre line, as quads (four (x, y, z))."""
    t = np.gradient(centre, axis=0)
    n = np.stack([t[:, 2], np.zeros(len(t)), -t[:, 0]], 1)
    n /= np.linalg.norm(n, axis=1)[:, None]
    left, right = centre + n * width / 2, centre - n * width / 2
    return [(left[i], right[i], right[i + 1], left[i + 1]) for i in range(len(centre) - 1)]


def segments_cross(p, q, r, s):
    d = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return d(p, q, r) * d(p, q, s) < 0 and d(r, s, p) * d(r, s, q) < 0


def in_quad(pt, quad):
    sgn = [np.sign((b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])) for a, b in zip(quad, quad[1:] + quad[:1])]
    return all(s >= 0 for s in sgn) or all(s <= 0 for s in sgn)


def ground_word(col):
    """The marker a driveable vertex carries, as the course has it."""
    return next(w for b in col.blocks for v in b.verts for w in [v[3]] if w >> 24 == 0x7f)


def make_collision(col, link, link_width, walls):
    """The link as road, the walls across it removed (a strip a metre narrower each side, so the
    course's far walls at the two ends stay), and invisible walls (pairs of points (x, z), 3 m high
    above y) across the old course."""
    cut = [[(q[0], q[2]) for q in quad] for quad in strip(link, link_width - 2)]
    def keep(surface, pts):
        xz = [(p[0], p[2]) for p in pts]
        n = np.cross(np.subtract(pts[1], pts[0]), np.subtract(pts[2], pts[0]))
        if abs(n[1]) > 0.7 * np.linalg.norm(n): return True  # ground: kept (the link lies on top of it, if any)
        for quad in cut:
            if any(in_quad(p, quad) for p in xz): return False
            for e0, e1 in ((xz[0], xz[1]), (xz[1], xz[2]), (xz[2], xz[0])):
                if any(segments_cross(e0, e1, q0, q1) for q0, q1 in zip(quad, quad[1:] + quad[:1])): return False
        return True
    gone = col.remove(keep)
    word = ground_word(col)
    quads = strip(link, link_width + 4)  # 2 m over each edge onto the lot
    for q in quads:
        col.add(0, [q[0], q[1], q[2]], word)
        col.add(0, [q[2], q[3], q[0]], word)
    for (x0, z0, y0), (x1, z1, y1) in walls:
        p = [(x0, y0 - 1, z0), (x1, y1 - 1, z1), (x1, y1 + 3, z1), (x0, y0 + 3, z0)]
        col.add(0x900, [p[0], p[1], p[2]], 0)
        col.add(0x900, [p[2], p[3], p[0]], 0)
    return gone, 2 * len(quads)


def off_course(points, sp, margin=1.0):
    """For each point, whether it is off the course's road: further from the centre line than the
    road's half width there (its edge splines) and `margin`."""
    c = (sp[4] + sp[5]) / 2
    half = np.linalg.norm(sp[4] - sp[5], axis=1) / 2
    dense, dh = [], []
    for i in range(len(c) - 1):
        for t in np.linspace(0, 1, 20):
            dense.append(c[i] + (c[i + 1] - c[i]) * t); dh.append(half[i] + (half[i + 1] - half[i]) * t)
    dense, dh = np.array(dense), np.array(dh)
    out = []
    for p in points:
        d = np.hypot(dense[:, 0] - p[0], dense[:, 2] - p[2])
        out.append(bool(np.all(d > dh + margin)))
    return np.array(out)


def link_walls(link, width, sp):
    """Walls along both edges of the link, `width` / 2 + 2 m out, where it is off the course's road."""
    out = []
    for side in (1, -1):
        quads = strip(link, width + 4)
        edge = [q[0] if side > 0 else q[1] for q in quads] + [quads[-1][3] if side > 0 else quads[-1][2]]
        clear = off_course(edge, sp)
        for p, q, cp, cq in zip(edge[:-1], edge[1:], clear[:-1], clear[1:]):
            if cp and cq: out.append(((p[0], p[2], p[1]), (q[0], q[2], q[1])))
    return out


def across(c, i, extra=4.0):
    """A line across the course at point i, from edge to edge and `extra` beyond: ((x, z, y), (x, z, y))."""
    t = c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)]
    n = np.array([t[2], 0, -t[0]]) / np.hypot(t[0], t[2])
    return tuple((p[0], p[2], p[1]) for p in (c[i] + n * 20, c[i] - n * 20))


def parse_pvs(d):
    """QuickPreview1.pvs (version 0x131f0cf): '3SVP', u32 version, u32, a 16-byte id, u32 cells; per
    cell three lists, each a u32 count and its entries: 4 bytes (u16 object, u16 mask), 8 bytes (u16
    object, u16 mask, u32), 4 bytes (u16 object, u16 mask); then 6 bytes. A cell is a stretch of the
    course in the order it is driven (Pacific Shipyards II's are Pacific Shipyards' backwards), the
    mask which of its 16 steps the object is seen from; the game picks the cell by the car's
    progress round the course."""
    assert d[:4] == b'3SVP'
    n = struct.unpack_from('<I', d, 0x1c)[0]
    o, cells = 0x20, []
    for _ in range(n):
        lists = []
        for size in (4, 8, 4):
            k = struct.unpack_from('<I', d, o)[0]
            lists.append([d[o + 4 + size * j:o + 4 + size * (j + 1)] for j in range(k)])
            o += 4 + size * k
        cells.append(lists)
    return d[:0x1c], cells, d[o:]


def loop_pvs(d, use, extra=(), hide=()):
    """A visibility file for the loop: every cell the same, everything the cells `use` (Pacific
    Shipyards II's that cover the lot) show, seen from every step; so whichever cell the game takes
    the loop's progress for, the lot's scenery is there. Meshes in `hide` are left out."""
    head, cells, tail = parse_pvs(d)
    merged = []
    for li in range(3):
        objs = {}
        for c in use:
            for e in cells[c][li]:
                obj = struct.unpack_from('<H', e)[0]
                if obj in hide: continue
                rest = e[4:]
                old = objs.get(obj)
                objs[obj] = rest if old is None else bytes(a | b for a, b in zip(old, rest))
        if li == 0:
            for obj in extra: objs.setdefault(obj, b'')
        merged.append([struct.pack('<HH', obj, 0xFFFF) + rest for obj, rest in sorted(objs.items())])
    body = b''.join(b''.join(struct.pack('<I', len(l)) + b''.join(l) for l in merged) for _ in cells)
    return head + struct.pack('<I', len(cells)) + body + tail, [len(l) for l in merged]


MODEL = 0x4e0600  # model_quickpreview in the unpacked bundle
DONOR = 714       # its mesh sidewalk01 (asphalt, 407 vertices), by Pacific Shipyards' far end: the link's road


def mesh(res, i):
    """Mesh i of model_quickpreview (a 28-byte record): (record offset, index count, vertex bytes,
    vertex buffer resource)."""
    n = struct.unpack_from('<I', res, MODEL)[0]
    a = struct.unpack_from('<I', res, MODEL + 4 + 4 * i)[0]
    fl, ab, nidx, vbytes, vb, stride, prim, t0, t1, sh = struct.unpack_from('<IIIIHHHHHH', res, MODEL + a)
    assert stride == 6 and prim == 6, (stride, prim)
    return MODEL + a, nidx, vbytes, vb


def vb_offset(res, vb):
    """The data offset of resource vb (numbered from 9) in the unpacked bundle."""
    return struct.unpack_from('<I', res, 0x202 + 24 * (vb - 9) + 8)[0]


def road_strip(link, width, sp, step=1.5):
    """The link's visible road: cross-sections every `step` metres where its centre is off the
    course's road (reaching a metre onto it at each end), `width` wide, as (left, right) points."""
    clear = off_course(link, sp, margin=-1.0)
    i0, i1 = np.argmax(clear), len(link) - 1 - np.argmax(clear[::-1])
    seg = link[i0:i1 + 1]
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
    want = np.arange(0, s[-1] + 1e-6, step)
    c = np.stack([np.interp(want, s, seg[:, j]) for j in range(3)], 1)
    t = np.gradient(c, axis=0)
    nrm = np.stack([t[:, 2], np.zeros(len(t)), -t[:, 0]], 1)
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    return c + nrm * width / 2, c - nrm * width / 2


def write_road(res, left, right):
    """The donor mesh's vertices and strip rewritten as the road: its vertex format (f32 x, y, z,
    u32 normal, s16 texture s, t, lightmap s, t), the asphalt mapped as the donor maps it (53 a
    metre along x, -52 along z), the lightmap at the donor's middling value; spare vertices and
    indices repeat the last. Returns the road's bounding sphere."""
    rec, nidx, vbytes, vb = mesh(res, DONOR)
    o = vb_offset(res, vb)
    nv = vbytes // 24
    old = np.frombuffer(bytes(res[o:o + vbytes]), dtype=np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)]))
    oldidx = np.frombuffer(bytes(res[o + vbytes:o + vbytes + 2 * nidx]), '<u2')
    k = 2 * len(left)
    assert k <= nv and k <= nidx, (k, nv, nidx)
    pts = np.empty((k, 3)); pts[0::2] = left; pts[1::2] = right
    # the donor's facing: its first triangle's normal points up or down; the strip's first likewise
    a, b, c = (old['p'][j].astype(float) for j in oldidx[:3])
    up = np.sign(np.cross(b - a, c - a)[1])
    if np.sign(np.cross(pts[1] - pts[0], pts[2] - pts[0])[1]) != up:
        pts[0::2], pts[1::2] = right, left.copy()
    new = old.copy()
    vals, counts = np.unique(old['n'], return_counts=True)
    normal = vals[np.argmax(counts)]
    cx, cz = pts[:, 0].mean(), pts[:, 2].mean()
    med = np.median(old['st'].astype(float), axis=0)
    for j in range(nv):
        p = pts[min(j, k - 1)]
        new['p'][j] = p + (0, 0.02, 0)
        new['n'][j] = normal
        new['st'][j] = (int(round(med[0] + 53.0 * (p[0] - cx))), int(round(med[1] - 51.7 * (p[2] - cz))), int(med[2]), int(med[3]))
    res[o:o + vbytes] = new.tobytes()
    idx = np.minimum(np.arange(nidx), k - 1).astype('<u2')
    res[o + vbytes:o + vbytes + 2 * nidx] = idx.tobytes()
    centre = (pts.min(0) + pts.max(0)) / 2
    return centre, float(np.max(np.linalg.norm(pts - centre, axis=1)))


def move_sphere(ppw, old_centre, old_radius, centre, radius):
    """QuickPreview1.pvs.ppw: per mesh a 21-byte record (f32 radius, centre; 5 bytes), some with
    more after them; the donor's found by its sphere and moved to the road."""
    best = None
    for o in range(0x14, len(ppw) - 16):
        r, x, y, z = struct.unpack_from('<4f', ppw, o)
        if not (0 < r < 5000): continue
        e = abs(r - old_radius) + np.linalg.norm(np.subtract((x, y, z), old_centre))
        if best is None or e < best[0]: best = (e, o)
    assert best[0] < 2.0, best
    ppw = bytearray(ppw)
    struct.pack_into('<4f', ppw, best[1], radius, *centre)
    return bytes(ppw)


# what the link has to clear: warehouse 13 (it stands where the link crosses the lot), and at its two
# ends the construction barricades, road-closed and detour signs and the steamroller closing the lot off
HIDE = ('building_warehouse13', 'constructionbarricade', 'barrier_construction_08', 'sign_roadclosed05',
        'signturnplywood02', 'steamroller_02')


def mesh_vertices(res, names, i):
    """Mesh i's vertex positions (any record with a vertex buffer of whole vertices), or None."""
    n = struct.unpack_from('<I', res, MODEL)[0]
    a = struct.unpack_from('<I', res, MODEL + 4 + 4 * i)[0]
    b = struct.unpack_from('<I', res, MODEL + 4 + 4 * (i + 1))[0] if i + 1 < n else None
    vbytes = struct.unpack_from('<I', res, MODEL + a + 12)[0]
    vb, stride = struct.unpack_from('<HH', res, MODEL + a + 16)
    if not (1 <= stride <= 16) or vbytes % (4 * stride) or vb < 9 or vb - 9 >= len(names): return None
    o = names[vb - 9][3]
    v = np.frombuffer(bytes(res[o:o + vbytes]), '<f4').reshape(-1, stride)[:, :3]
    return v if np.all(np.isfinite(v)) and np.abs(v).max() < 5000 else None


def hidden_meshes(res, link):
    """The meshes named in HIDE that have a vertex within 30 m of the link."""
    import xb2
    names, _ = xb2.resources(bytes(res))
    out = []
    for i in range(struct.unpack_from('<I', res, MODEL)[0]):
        a = struct.unpack_from('<I', res, MODEL + 4 + 4 * i)[0]
        vb = struct.unpack_from('<H', res, MODEL + a + 16)[0]
        if not (9 <= vb < len(names) + 9) or not any(h in names[vb - 9][0] for h in HIDE): continue
        v = mesh_vertices(res, names, i)
        if v is None: continue
        d = np.min(np.hypot(v[:, None, 0] - link[None, :, 0], v[:, None, 2] - link[None, :, 2]))
        if d < 30: out.append(i)
    return out


def clear_boxes(cbx, link, width):
    """quickpreview1.xbp.cbx (zlib-packed on the disc), unpacked: u32 1, a 16-byte id, u32 boxes, per box f32 min x, y, z, max x, y, z: the
    solid props (barricades, kerbs); the boxes the link's road crosses dropped."""
    n = struct.unpack_from('<I', cbx, 0x14)[0]
    boxes = np.frombuffer(cbx, '<f4', count=6 * n, offset=0x18).reshape(n, 6)
    quads = [[(q[0], q[2]) for q in quad] for quad in strip(link, width)]
    keep = []
    for bx in boxes:
        hit = any(coledit.overlaps(q[:3], (bx[0], bx[2], bx[3], bx[5])) or coledit.overlaps([q[0], q[2], q[3]], (bx[0], bx[2], bx[3], bx[5])) for q in quads)
        if not hit: keep.append(bx)
    out = cbx[:0x14] + struct.pack('<I', len(keep)) + np.array(keep, '<f4').tobytes()
    return out + bytes(len(cbx) - len(out)), n - len(keep)


PVS_CELLS = range(2, 6)  # Pacific Shipyards II's cells round the lot (0 and 1: its start road; more did not fit in memory)

MAP_TILE = 45   # frontend\gfx_trackmaps.xpr: 128 x 128 tiles, 4 a row; the disc uses 0-44
LOGO = 19       # ico_tracklogo_*: Pacific Shipyards' own logo (Pacific Shipyards II's is 20)


def trackmap(centre, size=128, ss=4):
    """The track select screen's map of the circuit, as the game draws them: north up, a white line
    with a dark edge on a clear ground, a red arrow and dot at the lap line pointing the way round.
    Drawn at `ss` times the size and averaged down. RGBA rows."""
    S = size * ss
    p = centre[:, [0, 2]].astype(float)
    p[:, 1] = -p[:, 1]  # north (+z) up
    lo, hi = p.min(0), p.max(0)
    scale = (S * 0.78) / max(hi - lo)
    q = (p - (lo + hi) / 2) * scale + S / 2
    yy, xx = np.mgrid[0:S, 0:S].astype(float) + 0.5
    def dist(pts):
        d = np.full((S, S), 1e9)
        for a, b in zip(pts, np.roll(pts, -1, 0)):
            v = b - a
            t = np.clip(((xx - a[0]) * v[0] + (yy - a[1]) * v[1]) / max(v @ v, 1e-9), 0, 1)
            d = np.minimum(d, np.hypot(xx - a[0] - t * v[0], yy - a[1] - t * v[1]))
        return d
    d = dist(q[::2])
    white, edge = d < 1.2 * ss, d < 2.2 * ss
    # the arrow: just before the line, pointing the way round
    fwd = q[3] - q[0]; fwd /= np.linalg.norm(fwd)
    side = np.array([-fwd[1], fwd[0]])
    tip, base = q[0] + fwd * 3 * ss, q[0] - fwd * 9 * ss
    tri = [tip, base + side * 5 * ss, base - side * 5 * ss]
    def inside(t):
        s = [np.sign((b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0])) for a, b in zip(t, t[1:] + t[:1])]
        return ((s[0] >= 0) & (s[1] >= 0) & (s[2] >= 0)) | ((s[0] <= 0) & (s[1] <= 0) & (s[2] <= 0))
    dot_c = q[0] - fwd * 12 * ss
    red = inside(tri) | (np.hypot(xx - dot_c[0], yy - dot_c[1]) < 2.4 * ss)
    red_edge = np.zeros_like(red)
    for dy in range(-ss, ss + 1, max(1, ss // 2)):
        for dx in range(-ss, ss + 1, max(1, ss // 2)):
            red_edge |= np.roll(np.roll(red, dy, 0), dx, 1)
    img = np.zeros((S, S, 4), float)
    img[edge | red_edge] = (0, 0, 0, 255)
    img[white] = (240, 240, 240, 255)
    img[red] = (200, 30, 30, 255)
    img = img.reshape(size, ss, size, ss, 4).mean((1, 3))
    rgb = img[..., :3] / np.maximum(img[..., 3:], 1e-6) * 255  # colour not darkened by the averaged alpha
    return np.concatenate([np.clip(rgb, 0, 255), img[..., 3:]], -1).round().astype(np.uint8)


NAME, TAG = 'Pacific Shipyards Circuit', 'VancouverLoop'
B = '\\'


def grid(loop):
    """quickpreview.xml's start grid: eight cars in two staggered rows behind the lap line, facing
    the way round; and the unit vector of that way."""
    c = (loop[4] + loop[5]) / 2
    fwd = c[1] - c[-1]
    fwd /= np.linalg.norm(fwd)
    side = np.array([fwd[2], 0, -fwd[0]]) / np.hypot(fwd[0], fwd[2])
    # back along the loop from point 0
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c[::-1], axis=0), axis=1))])
    back = c[::-1]
    pts = []
    for pos in range(1, 9):
        dist = 6 + 5.25 * (pos - 1)
        p = np.array([np.interp(dist, s, back[:, j]) for j in range(3)])
        p += side * (2.6 if pos % 2 else -2.6)
        pts.append((pos, p))
    return pts, fwd


def quickpreview(src, loop):
    pts, fwd = grid(loop)
    s = re.sub(r'<orientation[^>]*/>', '<orientation x=%.3f y=%.3f z=%.3f />' % tuple(fwd), src, count=1)
    s = re.sub(r'[ \t]*<startpoint[^>]*/>[ \t]*\r?\n?', '', s)
    rows = ''.join('\t<startpoint pos="%d"  x="%.3f"  \ty="%.2f"  \tz="%.3f" />\r\n' % (n, p[0], p[1], p[2]) for n, p in pts)
    s = re.sub(r'(<orientation[^>]*/>\r?\n)', lambda m: m.group(1) + '\t\r\n' + rows, s, count=1)
    s = re.sub(r'<splits>.*?</splits>', '<splits>\r\n\t\t<split point="0.25" />\r\n\t\t<split point="0.5" />\r\n\t\t<split point="0.75" />\r\n\t</splits>', s, flags=re.S)
    s = re.sub(r'<SplinePatches>.*?</SplinePatches>', '<SplinePatches>\r\n\t</SplinePatches>', s, flags=re.S)  # by the old spline's points
    return s


def track_entry(tracklist, name_id, length):
    """tracklist.xml with the circuit's entry added after Pacific Shipyards II's (a copy of it): its
    own data folder and collision, Pacific Shipyards' scenery and Pacific Shipyards II's visibility
    (both of them replaced while it loads), a circuit for Hot Lap (no start, end or p2pordinal), no AI."""
    m = re.search(r'<track\s[^>]*name="VancouverReverse".*?/>', tracklist, re.S)
    e = m.group(0)
    recs = re.findall(r'<track\s.*?/>', tracklist, re.S)
    ordinal = max(int(x) for r in recs for x in re.findall(r'\bOrdinal="(\d+)"', r)) + 1
    hotlap = max(int(x) for r in recs for x in re.findall(r'\bhotlapordinal="(\d+)"', r)) + 1
    def attr(e, k, v):
        e2, n = re.subn(r'\b%s="[^"]*"' % k, lambda m: '%s="%s"' % (k, v), e, count=1)
        return e2 if n else e.replace(' />', ' %s="%s" />' % (k, v))
    folder = 'd:\\media\\tracks\\' + TAG + '\\'
    for k, v in (('RosettaName', NAME), ('name', TAG), ('trackIdentifier', TAG), ('tracknameid', name_id),
                 ('trackSegCamsFile', folder + 'TrackSegCams.xml'), ('pitCamsFile', folder + 'PitCams.xml'),
                 ('dataFile', folder + 'QuickPreview.xml'), ('collisionFile', folder + 'QuickPreview1.col'),
                 ('reverseSplines', 'false'), ('swapInnerOuter', 'false'), ('aiReady', 'false'),
                 ('Ordinal', ordinal), ('length', int(round(length))),
                 ('minimap', MAP_TILE), ('icon', LOGO), ('Image', 'Load_Shipyards.xpr')):
        e = attr(e, k, v)
    e = re.sub(r'\s(p2pordinal|start|end)="[^"]*"', '', e)
    e = e.replace(' Ordinal="%d"' % ordinal, ' Ordinal="%d" hotlapordinal="%d"' % (ordinal, hotlap))
    return tracklist[:m.end()] + '\r\n\r\n\t' + e + tracklist[m.end():], ordinal, hotlap


def install(disc, mods, loop, col_bytes, res_bytes, pvs_bytes, ppw_bytes, cbx_bytes, length):
    """Into the mods folder: the track list entry, its data folder (Mega.ca2), its name in every
    language, its folder on the disc (media\tracks\VancouverLoop: the collision, Pacific Shipyards
    II's audio spline, lightmap and glass reflection), and under track\VancouverLoop\ (what the
    runtime opens in place of the real files while this track loads) its copy of the scenery,
    hdd\Partition4\vancouver.res, and of Pacific Shipyards II's visibility files, which only load
    from that folder."""
    import addcar
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    files = {k.lower(): k for k in mega.files}
    tl_key = files['forzadb' + B + 'tracklist.xml']
    tracklist = mega.files[tl_key].decode('latin-1')
    if 'name="%s"' % TAG in tracklist: raise SystemExit('%s: %s is in the track list already' % (mods, TAG))
    # its name, in every language (English text)
    loc = addcar.disc_file(disc, 'media', 'Loc')
    nid = None
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'TrackStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'TrackStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        new = addcar.write_strings(base, [('IDS_Track_Name_' + TAG, NAME)])
        i = addcar.string_ids(new)['IDS_Track_Name_' + TAG]
        if nid not in (None, i): raise SystemExit('track name ids differ between languages')
        nid = i
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(new)
    tracklist, ordinal, hotlap = track_entry(tracklist, nid, length)
    mega.files[tl_key] = tracklist.encode('latin-1')
    src = 'tracks' + B + 'vancouverreverse' + B
    for k in list(mega.files):
        if k.lower().startswith(src):
            v = mega.files[k]
            if k.lower().endswith('quickpreview.xml'): v = quickpreview(v.decode('latin-1'), loop).encode('latin-1')
            mega.files['tracks' + B + TAG.lower() + B + k[len(src):]] = v
    # its map on the track select screen
    import addseries
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    key = next(k for k in xpr.files if k.lower() == 'frontend' + B + 'gfx_trackmaps.xpr')
    xpr.files[key] = addseries.put_tile(xpr.files[key], MAP_TILE, trackmap((loop[4] + loop[5]) / 2), (128, 128, 4))
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    d = os.path.join(mods, 'media', 'tracks', TAG)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'QuickPreview1.col'), 'wb').write(col_bytes)
    rev = addcar.disc_file(disc, 'media', 'tracks', 'VancouverReverse')
    for f in os.listdir(rev):
        if not f.lower().startswith('quickpreview1.pvs'):
            open(os.path.join(d, f), 'wb').write(open(os.path.join(rev, f), 'rb').read())
    t = os.path.join(mods, 'track', TAG)
    for rel, data in ((('hdd', 'Partition4', 'vancouver.res'), res_bytes),
                      (('media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs'), pvs_bytes),
                      (('media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs.ppw'), ppw_bytes),
                      (('media', 'tracks', 'Vancouver', 'quickpreview1.xbp.cbx'), cbx_bytes)):
        os.makedirs(os.path.join(t, *rel[:-1]), exist_ok=True)
        open(os.path.join(t, *rel), 'wb').write(data)
    print('"%s": track %d, Hot Lap %d, name string %d' % (NAME, ordinal, hotlap, nid))


if __name__ == '__main__':
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    disc, mods = sys.argv[1], sys.argv[2]
    preview_png = sys.argv[3] if len(sys.argv) > 3 else None
    folder = os.path.join(disc, 'media', 'tracks', 'Vancouver')
    res = unpack_xb2(os.path.join(folder, 'QuickPreview1.xb2'))
    sp = read_splines(res)
    edges, centre, (a, b), link = loop_edges(sp)
    loop, length = resample(edges, centre, START)
    print('loop %.0f m (%.2f mi); link from course point %d to %d' % (length, length / 1609.344, b, a))
    col = coledit.Col(open(os.path.join(folder, 'QuickPreview1.col'), 'rb').read())
    c = (sp[4] + sp[5]) / 2
    # the old course where it leaves the loop: towards Pacific Shipyards II's start, and west of the kink
    walls = [across(c, nearest(c, (-484.1, -300.7))), across(c, nearest(c, (-533.4, -95.9)))]
    walls += link_walls(link, LINK_WIDTH, sp)
    gone, added = make_collision(col, link, LINK_WIDTH, walls)
    col_bytes, res_bytes = col.to_bytes(), write_splines(res, loop)
    print('collision: %d wall triangles removed, %d road triangles added, %d wall pieces added' % (gone, added, len(walls)))
    # the link's road, drawn: the donor mesh rewritten, its bounding sphere moved, in every visibility cell
    rec, nidx, vbytes, vb = mesh(res_bytes, DONOR)
    o = vb_offset(res_bytes, vb)
    donor = np.frombuffer(bytes(res_bytes[o:o + vbytes]), '<f4').reshape(-1, 6)[:, :3].astype(float)
    dc = (donor.min(0) + donor.max(0)) / 2
    left, right = road_strip(link, LINK_WIDTH + 4, sp)
    centre_r, radius = write_road(res_bytes, left, right)
    rev = os.path.join(disc, 'media', 'tracks', 'VancouverReverse')
    ppw = open(os.path.join(rev, 'QuickPreview1.pvs.ppw'), 'rb').read()  # the donor's sphere: not found yet (see move_sphere)
    hide = hidden_meshes(res_bytes, link)
    pvs, sizes = loop_pvs(open(os.path.join(rev, 'QuickPreview1.pvs'), 'rb').read(), PVS_CELLS, extra=[DONOR], hide=set(hide))
    print('road: %d cross-sections in mesh %d; visibility: %s meshes in every cell, %d hidden' % (len(left), DONOR, sizes, len(hide)))
    cbx, dropped = clear_boxes(zlib.decompress(open(os.path.join(folder, 'quickpreview1.xbp.cbx'), 'rb').read()), link, LINK_WIDTH + 4)
    cbx = zlib.compress(cbx, 9)  # the game reads it packed, as the disc has it
    print('solid props: %d boxes on the link dropped' % dropped)
    if preview_png: preview(preview_png, sp, loop, np.mean([loop[4], loop[5]], 0), col)
    install(disc, mods, loop, col_bytes, res_bytes, pvs, ppw, cbx, length)
