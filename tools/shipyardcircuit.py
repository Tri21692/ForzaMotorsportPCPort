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
OLD_ROAD = 515     # the old road by the concrete barricade, where the strip comes in
TURN2 = 550        # Turn 2, where the loop leaves the upper road for side road 31
START_ROAD = 593   # Pacific Shipyards II's start road, where side road 39 meets it
JUNCTION = 569     # the junction at the start road's top, where the strip leaves

SIDE_ROADS = [(-140, -326), (-100, -350), (-74, -368), (-90, -410), (-114, -454), (-123, -473), (-129, -560)]
GAP = [(-129, -560), (-262, -726)]       # where the tunnel is to go
ROAD39 = [(-262, -726), (-385, -646), (-503, -566)]
STRIP = [(-447, -253), (-470, -240), (-492, -224), (-650, -103)]

# the course's branches the loop does not take, closed by walls across them
CLOSED = (553, 596, 566, 512)

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


def half_widths(centre, sp):
    """The road's half width along the loop: the course's own where on it, HALF off it."""
    c = (sp[4] + sp[5]) / 2
    half = np.linalg.norm(sp[4] - sp[5], axis=1) / 2
    off = L.off_course(centre, sp, margin=1.0)
    h = np.array([HALF if off[i] else half[L.nearest(c, (p[0], p[2]))] for i, p in enumerate(centre)])
    k = np.arange(-5, 6); w = np.exp(-0.5 * (k / 2.5) ** 2); w /= w.sum()
    return sum(w[j] * np.roll(h, -k[j]) for j in range(len(k))), off


def edges(centre, half):
    """The six edge splines (even ones on the right, odd on the left, as the course has them)."""
    t = np.roll(centre, -1, 0) - np.roll(centre, 1, 0)
    left = np.stack([-t[:, 2], np.zeros(len(t)), t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    return [centre + left * (half * (1 if k % 2 else -1))[:, None] for k in range(6)]


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


def clear_road(col, centre, half, reach=1.5, keep_in=0.5):
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


def build(disc, mods, preview_png=None):
    folder = os.path.join(disc, 'media', 'tracks', 'Vancouver')
    res = L.unpack_xb2(os.path.join(folder, 'QuickPreview1.xb2'))
    sp = L.read_splines(res)
    c = (sp[4] + sp[5]) / 2
    centre = centre_line(sp)
    half, off = half_widths(centre, sp)
    e = edges(centre, half)
    loop, length = L.resample(e, centre, START)
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
        w = L.link_walls(link, 2 * HALF, sp) + (walls if k == 0 else [])
        g, a = L.make_collision(col, link, 2 * HALF, w, sp)
        gone += g; added += a
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
    L.write_road(res_bytes, left, right)
    hide = set()
    for link in links: hide |= set(L.hidden_meshes(res_bytes, link, sp))
    rev = os.path.join(disc, 'media', 'tracks', 'VancouverReverse')
    ppw = open(os.path.join(rev, 'QuickPreview1.pvs.ppw'), 'rb').read()
    pvs_in = open(os.path.join(rev, 'QuickPreview1.pvs'), 'rb').read()
    n_cells = len(L.parse_pvs(pvs_in)[1])
    pvs, sizes = L.loop_pvs(pvs_in, [list(range(0, 8))] * n_cells, extra=[L.DONOR], hide=hide)
    print('road: %d cross-sections on the strip; %d meshes hidden; visibility %d meshes' % (len(left), len(hide), sizes[0]))
    cbx = zlib.decompress(open(os.path.join(folder, 'quickpreview1.xbp.cbx'), 'rb').read())
    dropped = 0
    for link in links:
        cbx, d = L.clear_boxes(cbx, link, 2 * HALF + 4)
        dropped += d
    cbx = zlib.compress(cbx, 9)
    print('solid props: %d boxes on the off-course road dropped' % dropped)
    if preview_png: L.preview(preview_png, sp, loop, np.mean([loop[4], loop[5]], 0), col)
    L.install(disc, mods, loop, col_bytes, res_bytes, pvs, ppw, cbx, length)


if __name__ == '__main__':
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
