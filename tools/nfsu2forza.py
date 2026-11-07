"""Put a Need for Speed Underground car's body on a Forza car.

Takes a Forza car's car.carbin as the template (its handling, sounds,
interior, glass, driver, brakes and hinges stay) and replaces the geometry
of its body parts with the NFSU car's stock (KIT00, finest detail) parts:

  body      <- BODY + ROOF          hood      <- HOOD      trunk <- TRUNK
  bumperF*  <- FRONT_BUMPER         bumperR*  <- REAR_BUMPER
  skirtL* / skirtR*                 <- SKIRT, its left and right halves
  headlightL/R, taillightL/R        <- HEADLIGHT, BRAKELIGHT halves
  mirrorL/R <- LEFT/RIGHT_SIDE_MIRROR   wing* (every one) <- SPOILER

NFSU is x forward, y left, z up in metres; Forza is x right, y up, z
forward. The NFSU car is scaled and moved so its body's length and its
front, back and bottom match the template body's (the template's
interior, cage and steering wheel are then squashed to fit under the new
roof, which they otherwise stuck out of); the axis swap mirrors
it, which Forza's opposite winding cancels (turning them round put every
panel inside out in the game). Each NFSU material group becomes a
subpart (a triangle strip): the generated skin becomes Body (the livery's
paint), and the rest take a material from their texture's name. Texture
coordinates all point at a white spot of the template's livery atlas for
now, so parts are flat-coloured. Damage shapes are the undamaged shape
(no dents yet).

Usage:
  python tools/nfsu2forza.py <template car.carbin> <NFSU car folder> <out car.carbin> [--keep-glass] [--badges <folder>] [--liveries <template .liveries.bin>] [--no-stock-wing]

The NFSU car's windows are holes in its body: they are filled with glass
(window_panes), put in the template's glass parts. --keep-glass keeps the
template's own windows instead (they stand out of a lower roof).
--badges: a folder with logo.* (the maker's emblem, on the nose) and
model.* (the model's lettering, on the tail), any image ffmpeg
reads, used instead of the NFSU badge sheet's small ones. Your own files:
trademarks, so they stay out of anything shared.
--no-stock-wing: a Most Wanted car whose stock version has no wing (the
Gallardo): its own spoiler is a shop choice instead.
--liveries: the template's media/cars/<car>.liveries.bin; writes the
paint shop's copy of the new livery to liveries.bin beside the output
(addcar.py --liveries), or every repaint takes the new lamps' texture.
--vinyl NAME:base[,swatch[,colour]]: a Most Wanted vinyl of the car's own
VINYLS.BIN (the Hero's M3 GTR: PSRTEST:b7b7b7, its preset's vinyl on its
silver) baked into a second livery, liveries/standard/livery1*.xpr, for a
.livery with texture="livery1" and a white override (as the disc's AC
Cobra's stripes): the paint under it, and optionally the colour for its
swatch (pure red) and for the rest. The car's painted parts take Most
Wanted's own vinyl layout, so the shop's vinyls do not fit it.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carbin
import nfsu

WHITE_UV = (int(0.55 * 65536), int(0.55 * 65536))  # blank (paint) area of the livery atlas
BODY, WINDOW, TAILLIGHTS, HEADLIGHTS, BLACKGLASS, CHROME, BLACK, REDGLASS = 1, 2, 3, 4, 6, 7, 9, 16
WINDOWS = -1  # the converter's own: Body material on an opaque black texel
PLASTIC, BADGE, HEADLIGHTGLASS = 20, 26, 30
BADGE_UV = 32768  # Badge's texture coordinates count double: u16 / 32768 into the atlas (at / 65536 the decals drew the sheet squeezed, and the nose emblem the marker lamps beside it)
# ATLAS_UV: so do the other materials' (the Civic's own lamps and paint are
# all under 32768 and land on its lamp pictures and white read so). A Most
# Wanted car's lamps placed at / 65536 drew plain grey discs; they and the
# kept template parts' texel boxes count / 32768 now. (The 240SX's are left
# as they were.)
DECAL = BADGE  # 26: draws the atlas as it is, clear texels too (25, the Civic's badges', drew nothing of these; as Body they drew a plain patch)
INSET = int(0.02 * 4096)  # how far a panel's black inside sits in from it, carbin units (about a centimetre)
CABIN_SHADE = 0.4  # the cabin's shading bytes scaled by this
CABIN = ('interior', 'bands', 'cage', 'steering_wheel')  # template parts fitted under the new roof


def bhash(s, h=0xFFFFFFFF):
    for c in s.encode('latin-1'):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


# NFSU shaders (by name hash) -> Forza materials. Two have no known name: on
# the 240SX 12c9453c is the rubber round the windows, the B pillar and the
# trim strips, 010cb64a the inside of the wheel arches, 52bf4c34 the floor pan; all black (WINDOWS:
# Forza's own black trim drew clear). The windows themselves are holes (see
# window_panes).
SHADERS = {bhash('CARSKIN'): BODY, bhash('WINDSHIELD'): WINDOW, 0x12C9453C: WINDOWS, 0x010CB64A: WINDOWS,
           0x52BF4C34: WINDOWS,  # the floor pan: as Black (its texture is not in the car's pack) it drew clear and the cabin's floor was see-through
           0xA7366AE6: BODY,  # Underground 2's skirts and lower door skins (shader and texture both this hash, in no car's pack): paint; as Black the Silvia's and Neon's sills came out black
           bhash('DULLPLASTIC'): PLASTIC, bhash('CHROME'): CHROME, bhash('HEADLIGHTGLASS'): HEADLIGHTGLASS,
           bhash('BRAKELIGHTGLASS'): REDGLASS, bhash('DECAL'): BADGE, bhash('HEADLIGHT'): HEADLIGHTS,
           bhash('BRAKELIGHT'): TAILLIGHTS, bhash('RUBBER'): BLACK, bhash('ENGINE'): BLACK,
           bhash('MIRROR'): CHROME,  # the mirrors' glass, as the Civic's (as paint it was a flat blue slab)
           0x8E3305A7: TAILLIGHTS}  # Underground 2's (name unknown): the Celica GT-Four's red tail lamp lenses, black as Black
LAMP_GLASS = {0x9DAE417A}  # Underground 2's (name unknown), in a lamp part: the Celica GT-Four's grey see-through headlight covers


MW_HOODS = (4, 21, 2, 7, 10, 16, 26, 31, 13, 20, 3, 5)  # a Most Wanted car's STYLE<n>_HOOD for the shop's other hoods, the first the car has
MW_SPOILERS = (44, 5, 13, 6, 1, 3, 9, 26, 30, 2, 15)  # CARS/SPOILER's STYLE<n> as the other wings, the first there are
# The shop's slots: parts the template has (the Civic: hooda, f, g; wingb, c, d, g,
# raceA-C), and more made as copies of one of them. A part's id is a hash of its
# name in which the name's last letter counts 0x30000 apiece (hooda 0xa3dd3101,
# hoodf 0xa3ec3101, wingraceA 0xbbbbdb01, wingraceB 0xbbbedb01), so a copy named
# hoodb has the id the game looks for (tooldata's lists name the parts).
HOOD_SLOTS = 'fgbcde'
WING_SLOTS = ('wingc', 'wingd', 'wingg', 'wingraceA', 'wingraceB', 'wingraceC', 'winga', 'winge', 'wingf')
SLOT_LIKE = {'hoodb': 'hoodf', 'hoodc': 'hoodf', 'hoodd': 'hoodf', 'hoode': 'hoodf',
             'winga': 'wingc', 'winge': 'wingc', 'wingf': 'wingc'}


# Vinyls (the paint shop's custom layers) are drawn into a region of the
# livery atlas for each view: left, right, top, front, back, each the car
# seen from that side (the masks in <car>.liveries.bin, left.tga 915 x 260,
# are those silhouettes). The car shows them through its painted
# triangles' texture coordinates, a projection of each side into its
# region (the Civic: its left side along the atlas's bottom, its right
# across the middle, the roof in the centre, the hood to the left, the
# bumpers along the top). A converted body on one paint texel showed no
# vinyl at all. It takes the template's layout instead: each painted
# triangle, by the side it faces, the coordinates the template's own
# painted surface has at the same place seen from that side (the bodies
# are fitted to the same length and height).
PAINTED = {n + '_LOD1' for n in ('body', 'hooda', 'hood', 'bumperFa', 'bumperF', 'bumperRa', 'bumperR', 'trunk', 'skirtLa', 'skirtL',
                                 'skirtRa', 'skirtR', 'mirrorL', 'mirrorR', 'mirrorLa', 'mirrorRa')}  # each stock choice, by the Civic's names or a race car's
LIVERY_DECAL = 15  # a race car's sponsors, cut out of its body: the body's surface too (its texels are livery)
PROJ = {'left': (2, 1), 'right': (2, 1), 'top': (2, 0), 'front': (0, 1), 'back': (0, 1)}  # the plane each view sees: Forza x right, y up, z forward
CELL = 0.02  # the layout's lookup grid, carbin units / 4096


def uv_raster(mask, q, grow=0.02):
    """Mark in mask (N x N) the texels a triangle covers: q its corners in
    texels (3 x 2), a little beyond its edges (barycentric grow)."""
    import numpy as np
    n = mask.shape[0]
    x0, y0 = np.floor(q.min(0)).astype(int); x1, y1 = np.ceil(q.max(0)).astype(int)
    ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
    (ax, ay), (bx, by), (cx, cy) = q
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(den) < 1e-9:
        mask[int(ay) % n, int(ax) % n] = True
        return
    l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
    l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
    m = (l0 >= -grow) & (l1 >= -grow) & (1 - l0 - l1 >= -grow)
    mask[(ys[m] - 0.5).astype(int) % n, (xs[m] - 0.5).astype(int) % n] = True


def strip_tris(ix):
    """A strip's triangles, each wound as the first (strips alternate)."""
    return [(ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
            for k in range(len(ix) - 2) if len({ix[k], ix[k + 1], ix[k + 2]}) == 3]


def orient_normals(part):
    """Each vertex normal turned to the side its triangles face (Forza's: against
    the usual cross product of the strip's winding); returns how many were turned.
    The game lights and reflects by these normals, and the converter turns faces
    (outer skins away from the middle, black insides in) without their normals:
    on the MX-5's body a quarter of them, on its base nearly half, pointed in,
    dark patches all over silver paint. A vertex both sides use (two-sided glass)
    is left as it is. The damage shape's normals follow (a copy of the vertices)."""
    import numpy as np
    V = np.array([v[:3] for v in part['verts']], float)
    if not len(V): return 0
    acc = np.zeros_like(V)
    for sp in part['subparts']:
        t = np.array(strip_tris(sp['indices']), int).reshape(-1, 3)
        if not len(t): continue
        f = -np.cross(V[t[:, 1]] - V[t[:, 0]], V[t[:, 2]] - V[t[:, 0]])
        f /= np.maximum(np.linalg.norm(f, axis=1), 1e-9)[:, None]
        for j in range(3): np.add.at(acc, t[:, j], f)
    N = np.array([v[3:6] for v in part['verts']], float)
    turn = ((acc * N).sum(1) < 0) & (np.linalg.norm(acc, axis=1) > 0.5)
    if not turn.any(): return 0
    part['verts'] = [tuple(v[:3]) + tuple(-c for c in v[3:6]) + tuple(v[6:]) if turn[i] else v for i, v in enumerate(part['verts'])]
    dmg = part['Damage'][1]
    if len(dmg) >= 4 and struct.unpack_from('<I', dmg)[0] == len(part['verts']):
        part['Damage'] = (part['Damage'][0], struct.pack('<I', len(part['verts'])) + b''.join(struct.pack('<6h', *v[:6]) for v in part['verts']))
    return int(turn.sum())


# A vertex's first two shading bytes (+6, +7) on the disc's cars follow how much the surface faces the sky
# and how high it is (correlation 0.88 with the normal's up, 0.75 with height; the two 0.95 with each
# other): baked occlusion, the second the reflection's. Fitted over six cars' painted panels
# (R^2 0.84 and 0.68): 1, up, max(up, 0), height (0 floor .. 1 roof), height^2, |side|.
SHADE_FIT = ((91.6, 85.6, -13.4, 93.8, -6.2, 6.4), (80.6, 93.8, -31.4, 81.9, 18.1, 14.2))


def shade_vertices(parts):
    """The shading bytes of converted parts from SHADE_FIT. They were the template's nearest vertex's,
    patchy on another shape: the MX-5's trunk lid took 255 between panels at 0, and its silver
    reflected the studio there as a white slab. Returns the vertices set."""
    import numpy as np
    ys = [v[1] for p in parts for v in p['verts']]
    if not ys: return 0
    y0, y1 = min(ys), max(ys)
    n = 0
    for p in parts:
        out = []
        for v in p['verts']:
            ln = max(1.0, (v[3] * v[3] + v[4] * v[4] + v[5] * v[5]) ** 0.5)
            up, side, h = v[4] / ln, abs(v[3]) / ln, (v[1] - y0) / max(1, y1 - y0)
            x = (1, up, max(up, 0), h, h * h, side)
            b = [int(min(255, max(0, round(sum(a * c for a, c in zip(x, f)))))) for f in SHADE_FIT]
            out.append(tuple(v[:6]) + (b[0], b[1]) + tuple(v[8:]))
        p['verts'] = out
        n += len(out)
    return n


def smooth_normals(part, angle=50.0):
    """Each vertex normal made again from the triangles round its position (every
    vertex there, so seams in the texture do not crease the shading), those within
    `angle` degrees of its own triangles' (a sharper edge stays sharp), area-weighted,
    Forza's winding. For a part thinned in Blender (cartoolkit's plan "decimate"):
    it kept the dense model's normals over a coarser surface, 34% of the MX-5's body
    over 20 degrees off (the disc's cars: 1%), and its silver paint reflected in
    blotches. The damage shape's normals follow. Returns the vertices changed."""
    import numpy as np
    from collections import defaultdict
    V = np.array([v[:3] for v in part['verts']], float)
    if not len(V): return 0
    tris = np.array([t for sp in part['subparts'] for t in strip_tris(sp['indices'])], int).reshape(-1, 3)
    if not len(tris): return 0
    fn = -np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]])
    fu = fn / np.maximum(np.linalg.norm(fn, axis=1), 1e-9)[:, None]
    own = defaultdict(set)
    for f, t in enumerate(tris):
        for i in t: own[int(i)].add(f)
    at = defaultdict(set)  # faces round each position
    for i, fs in own.items(): at[tuple(V[i])] |= fs
    cos = np.cos(np.radians(angle))
    out, changed = list(part['verts']), 0
    for i, fs in own.items():
        ref = fn[list(fs)].sum(0)
        if np.linalg.norm(ref) == 0: continue
        ref /= np.linalg.norm(ref)
        near = [f for f in at[tuple(V[i])] if fu[f] @ ref > cos]
        n = fn[near].sum(0)
        if np.linalg.norm(n) == 0: continue
        n = tuple(int(round(c)) for c in n / np.linalg.norm(n) * 32767)
        if n != tuple(out[i][3:6]):
            out[i] = tuple(out[i][:3]) + n + tuple(out[i][6:]); changed += 1
    part['verts'] = out
    dmg = part['Damage'][1]
    if len(dmg) >= 4 and struct.unpack_from('<I', dmg)[0] == len(out):
        part['Damage'] = (part['Damage'][0], struct.pack('<I', len(out)) + b''.join(struct.pack('<6h', *v[:6]) for v in out))
    return changed


def facing(A):
    """The view a triangle (3 x 3 positions) faces: Forza winds triangles
    against the usual cross product. Undersides go to the side or end they
    lean to."""
    import numpy as np
    n = -np.cross(A[1] - A[0], A[2] - A[0])
    order = np.argsort(-np.abs(n))
    a = order[0] if not (order[0] == 1 and n[1] < 0) else order[1]
    return {0: ('left', 'right'), 1: ('top', 'top'), 2: ('back', 'front')}[a][1 if n[a] > 0 else 0]


def outward(view, c):
    return {'left': -c[0], 'right': c[0], 'top': c[1], 'front': c[2], 'back': -c[2]}[view]


def template_layout(car):
    """The template's painted exterior (PAINTED parts, finest level, Body
    material) by view: for each, a grid over the plane that view sees
    holding the outermost triangle over each cell, and each triangle's map
    from that plane to texture coordinates (u16, as the vertices have
    them) and its island (triangles joined by shared vertices: one
    continuous stretch of the atlas). Also the texels they cover (1024 x
    1024, u16 / 32768)."""
    import numpy as np
    tris = {v: [] for v in PROJ}
    cover = np.zeros((1024, 1024), bool)
    up = {}
    def root(x):
        while up.setdefault(x, x) != x:
            up[x] = up[up[x]]; x = up[x]
        return x
    found = []
    for p in car['parts']:
        if p['name'] not in PAINTED: continue
        V = p['verts']
        for sp in p['subparts']:
            if sp['id'] != 1 or sp['material'] not in (BODY, LIVERY_DECAL): continue
            for t in strip_tris(sp['indices']):
                A = np.array([V[i][:3] for i in t], float) / 4096
                UV = np.array([V[i][10:12] for i in t], float)
                if np.ptp(UV, 0).max() > 16384: continue  # (wrapped)
                view = facing(A)
                a, b = PROJ[view]
                P = A[:, [a, b]]
                M = np.c_[P, np.ones(3)]
                if abs(np.linalg.det(M)) < 1e-8: continue
                d = UV[1:] - UV[0]
                found.append((view, P, M, UV, A, p['name'], t, abs(d[0, 0] * d[1, 1] - d[0, 1] * d[1, 0]) / abs(np.linalg.det(M))))
    # Triangles whose texture coordinates collapse (a few texels, or one point, for
    # a hand's width of body: the Civic's seams, on its dashboard's dark texels)
    # are left out; mapped onto the new body they made black patches (the
    # Gallardo's front wings)
    least = 0.1 * np.median([f[-1] for f in found]) if found else 0
    for view, P, M, UV, A, name, t, density in found:
        if density < least: continue
        tris[view].append((P, np.linalg.solve(M, UV), outward(view, A.mean(0)), (name, t[0])))
        for i in t[1:]: up[root((name, i))] = root((name, t[0]))
        q = UV / 32768 % 1 * 1024
        x0, y0 = np.floor(q.min(0)).astype(int); x1, y1 = np.ceil(q.max(0)).astype(int)
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        (ax, ay), (bx, by), (cx, cy) = q
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9: continue
        l0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        m = (l0 >= -0.02) & (l1 >= -0.02) & (1 - l0 - l1 >= -0.02)
        cover[(ys[m] - 0.5).astype(int) % 1024, (xs[m] - 0.5).astype(int) % 1024] = True
    layout = {}
    for view, ts in tris.items():
        if not ts: continue
        P = np.array([t[0] for t in ts]); lo = P.reshape(-1, 2).min(0) - CELL; hi = P.reshape(-1, 2).max(0) + CELL
        shape = tuple(np.ceil((hi - lo) / CELL).astype(int))
        grid = np.full(shape, -1, np.int32); best = np.full(shape, -np.inf)
        for k, (Pk, _, out, _) in enumerate(ts):
            g0 = np.floor((Pk.min(0) - lo) / CELL).astype(int); g1 = np.ceil((Pk.max(0) - lo) / CELL).astype(int)
            gx, gy = np.mgrid[g0[0]:g1[0] + 1, g0[1]:g1[1] + 1]
            cx_, cy_ = lo[0] + (gx + 0.5) * CELL, lo[1] + (gy + 0.5) * CELL
            (ax, ay), (bx, by), (cx, cy) = Pk
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            l0 = ((by - cy) * (cx_ - cx) + (cx - bx) * (cy_ - cy)) / den
            l1 = ((cy - ay) * (cx_ - cx) + (ax - cx) * (cy_ - cy)) / den
            m = (l0 >= 0) & (l1 >= 0) & (1 - l0 - l1 >= 0) & (gx < shape[0]) & (gy < shape[1])
            gx, gy = gx[m], gy[m]
            take = out > best[gx, gy]
            grid[gx[take], gy[take]] = k; best[gx[take], gy[take]] = out
        isl = np.array([hash(root(t[3])) for t in ts])
        layout[view] = (lo, grid, [t[1] for t in ts], np.array([t[0].mean(0) for t in ts]), isl, P)
    return layout, cover


def apply_layout(car, layout, paint):
    """Every painted triangle on the one paint texel (the converted parts)
    given the template's layout (see template_layout): seen from the side it
    faces, the template's island under its middle; each vertex the map of
    that island's triangle under it (or the nearest), so neighbours on one
    island share their vertices (copied where islands meet: copied for
    every map, the Cobalt's strips grew from 232,000 indices to 402,000)."""
    import numpy as np
    changed = 0
    for p in car['parts']:
        V = p['verts']
        dmg = p['Damage'][1]
        nd = struct.unpack_from('<I', dmg)[0]
        extra, src, copies = [], [], {}
        for sp in p['subparts']:
            if sp['material'] != BODY: continue
            out = []
            for t in strip_tris(sp['indices']):
                if any(tuple(V[i][10:12]) != tuple(paint) for i in t):
                    out.append(t); continue
                A = np.array([V[i][:3] for i in t], float) / 4096
                view = facing(A)
                if view not in layout: out.append(t); continue
                lo, grid, maps, mids, isl, Ps = layout[view]
                a, b = PROJ[view]
                def under(c, island=None):
                    g = np.floor((c - lo) / CELL).astype(int)
                    k = grid[g[0], g[1]] if 0 <= g[0] < grid.shape[0] and 0 <= g[1] < grid.shape[1] else -1
                    if k >= 0 and (island is None or isl[k] == island): return k
                    d = ((mids - c) ** 2).sum(1)
                    if island is not None: d = np.where(isl == island, d, np.inf)
                    return int(d.argmin())
                island = isl[under(A.mean(0)[[a, b]])]
                nt = []
                for i in t:
                    key = (i, view, island)
                    if key not in copies:
                        q = A[t.index(i)][[a, b]]
                        k = under(q, island)
                        # within that triangle: off its edge the map ran on far outside the
                        # template's paint (a wing above the tail landed on the packed lamps)
                        bary = np.linalg.solve(np.r_[Ps[k].T, np.ones((1, 3))], np.r_[q, 1])
                        bary = np.clip(bary, 0, None); bary /= bary.sum()
                        uv = bary @ (np.c_[Ps[k], np.ones(3)] @ maps[k])
                        copies[key] = len(V) + len(extra)
                        extra.append(tuple(V[i][:10]) + tuple(int(min(65535, max(0, round(x)))) for x in uv))
                        src.append(i)
                    nt.append(copies[key])
                out.append(tuple(nt))
                changed += 1
            sp['indices'] = strip(out) if out else [0, 0, 0]
        if extra:
            if nd == len(V):
                p['Damage'] = (p['Damage'][0], struct.pack('<I', len(V) + len(extra)) + dmg[4:4 + 12 * nd]
                               + b''.join(dmg[4 + 12 * i:16 + 12 * i] for i in src) + dmg[4 + 12 * nd:])
            p['verts'] = V + extra
            assert len(p['verts']) < 65536, p['name']
    print('vinyls: %d painted triangles on the template\'s layout' % changed)


DRIVER_SCALE = 0.606  # carbin units (/4096) to the Driver chunk's metres: the Civic's steering wheel at 1.04 high, its grip point at 0.628


def fit_driver(car, droof, dwheel):
    """The Driver chunk (after Attribs): five float3s in metres, the hip,
    the left and right hands, two angles, and the steering wheel's grip.
    The driver stands on the hip, so a roof lower than the template's
    (droof, carbin units) lowers it as much, or the helmet stuck out
    through the Gallardo's roof; the hands and grip follow the steering
    wheel as the cabin fit moved it (dwheel)."""
    h = car['head'][1]
    _, _, name, p = carbin._chunk_head(h, 0)
    assert name == 'Driver' and len(h) - p == 60, (name, len(h) - p)
    f = list(struct.unpack_from('<15f', h, p))
    if droof < 0: f[1] += droof * DRIVER_SCALE
    for i in (4, 7, 13): f[i] += dwheel * DRIVER_SCALE
    car['head'][1] = h[:p] + struct.pack('<15f', *f)
    print('driver: hip %+.3f m, hands %+.3f m' % (min(droof, 0) * DRIVER_SCALE, dwheel * DRIVER_SCALE))


def slot_id(like_id, like, name):
    """The part id of `name` from that of `like`, a name differing only in its last letter."""
    assert len(like) == len(name) and like[:-1] == name[:-1], (like, name)
    return (like_id + (ord(name[-1]) - ord(like[-1])) * 0x30000) & 0xFFFFFFFF


def add_slots(car, names):
    """Copies of template parts for the shop slots it lacks (SLOT_LIKE), next to the part copied."""
    import copy
    have = {p['name'] for p in car['parts']}
    for name in names:
        if name + '_LOD1' in have or name not in SLOT_LIKE: continue
        like = SLOT_LIKE[name]
        hit = [(i, p) for i, p in enumerate(car['parts']) if p['name'] == like + '_LOD1']
        if not hit: continue  # (a template without the Civic's slots)
        i, p = hit[0]
        q = copy.deepcopy(p)
        q['name'], q['id'] = name + '_LOD1', slot_id(p['id'], like, name)
        car['parts'].insert(i + 1, q)
        have.add(q['name'])


def write_upgrades(path, kits, hoods, spoilers, stock_wing=True):
    """The shop's body parts for a Most Wanted car (tooldata.xml's
    FrontBumper, RearBumper, SideSkirt, Hood and Wing; addcar.py --upgrades
    puts them in): each front bumper is a whole body kit, the rear bumpers
    and skirts keep only their stock choice (the kits bring them). hoods
    and spoilers: (slot, style) pairs. stock_wing: the car's own spoiler
    is its stock wing (else a choice, the stock car having none)."""
    def opt(i, name, price, parts, extra=''):
        ps = ' '.join('P%d="%s_LOD"' % (k, p) for k, p in enumerate(parts))
        inner = '\n\t\t\t\t<Parts %s/>' % ps if parts else ''
        return '\t\t\t<P%d Name="%s" Price="%d" MassDiff="0"%s>%s\n\t\t\t</P%d>\n' % (i, name, price, extra, inner, i)
    aero = ' WindInstabilityScale="0.97" DragScale="0.997"'
    x = '\t\t<FrontBumper>\n' + opt(0, 'Stock', 0, ['bumperFa'], ' DragScale="1.0"')
    for i, n in enumerate(kits, 1):
        x += opt(i, 'Body Kit %d' % n, 1500 + 500 * i, ['bumperF' + 'bcdef'[n - 1]], aero)
    x += '\t\t</FrontBumper>\n\t\t<RearBumper>\n' + opt(0, 'Stock', 0, [], ' DragScale="1.0"') + '\t\t</RearBumper>\n'
    x += '\t\t<SideSkirt>\n' + opt(0, 'Stock', 0, [], ' DragScale="1.0"') + '\t\t</SideSkirt>\n'
    x += '\t\t<Hood>\n' + opt(0, 'Stock', 0, ['hooda'], ' DragScale="1.0"')
    for i, (slot, n) in enumerate(hoods, 1):
        x += opt(i, 'Hood %d' % n, 900 + 100 * i, ['hood' + slot], ' DragScale="1.0"')
    x += '\t\t</Hood>\n\t\t<Wing>\n'
    if stock_wing:
        x += opt(0, 'Stock', 0, ['wingb'], ' DragScale="1.0"')
    else:  # the stock car has none: its own spoiler is a choice
        x += opt(0, 'Stock', 0, [], ' DragScale="1.0"') + opt(1, 'Factory Wing', 750, ['wingb'], aero)
    k = 1 if stock_wing else 2
    for i, (slot, n) in enumerate(spoilers, k):
        x += opt(i, 'Wing %d' % n, 750 + 250 * i, [slot], aero)
    if stock_wing:
        x += opt(len(spoilers) + 1, 'No Wing', 0, [], ' DragScale="0.998"')
    x += '\t\t</Wing>\n'
    open(path, 'w').write(x)
    print('upgrades: %d body kits, %d hoods, %d wings (%s)' % (len(kits), len(hoods), len(spoilers) + (0 if stock_wing else 1), path))


def mw_material(name):
    """A Most Wanted group's material name -> Forza's; None leaves it out."""
    n = name.upper()
    if n.startswith('WINDOW'): return WINDOWS if n.endswith('_MASK') else WINDOW  # the masks are the black frit round the glass
    if n == 'REAR_DEFROSTER': return WINDOW  # (the rear glass, by its heater lines' role texture)
    if 'HEADLIGHT' in n:
        if n.endswith('GLASS'): return None  # the cover: Forza's headlight glass (30) is not on the template, so it took a stray texel and drew a white shell over the lamp
        if n.endswith('BULB'): return HEADLIGHTS
        if 'CHROME' in n: return CHROME
        if 'PLASTIC' in n: return PLASTIC
        return WINDOWS
    if 'BRAKELIGHT' in n: return TAILLIGHTS
    if n.startswith(('DOORLINE', 'LICENSE', 'DECAL', 'DRIVER', 'TIRE', 'RIM', 'BRAKE_')): return None  # seams drawn as strips, plates, vinyl slots, the parts Forza has its own of
    if 'BADGING' in n: return BADGE
    if 'CHROME' in n or 'ALUMINUM' in n or 'SILVER' in n: return CHROME
    if 'DULL_PLASTIC' in n: return PLASTIC
    if n.startswith('BODY') and not any(k in n for k in ('MOLDING', 'PLAINNOTHING', 'BLACK')): return BODY
    return WINDOWS  # mouldings, the underside, untextured bits: black


def paint_ready(img):
    """A see-through decal (RGBA) for Body, which draws paint times the texel
    where alpha is 0 and the texel where it is 255: the opaque texels as they
    are, the rest laid over white and made clear, so the paint shows through
    them darkened by the decal (a door handle's shading, a marker's rim)."""
    import numpy as np
    a = img[..., 3:4].astype(float) / 255
    out = img.copy()
    out[..., :3] = np.round(img[..., :3] * a + 255 * (1 - a)).astype(np.uint8)
    solid = img[..., 3] >= 240
    out[..., :3][solid] = img[..., :3][solid]
    out[..., 3] = np.where(solid, 255, 0)
    return out


def material_for(texname, shader=0):
    if shader in SHADERS: return SHADERS[shader]
    t = texname.upper()
    if t.endswith('SKIN1') or 'SKIN' in t: return BODY
    if 'HEADLIGHT' in t: return HEADLIGHTS
    if 'BRAKELIGHT' in t or 'TAILLIGHT' in t: return TAILLIGHTS
    if 'BADGING' in t or 'BADGE' in t: return BADGE
    if 'WINDOW' in t or 'GLASS' in t: return WINDOW
    if 'CHROME' in t: return CHROME
    return BLACK


def strip(tris):
    """Triangle list -> one strip, joined with degenerate triangles; each
    real triangle starts at an even position so it keeps its winding."""
    s = []
    for a, b, c in tris:
        if s:
            s += [s[-1], a]
            if len(s) % 2: s.append(a)
        s += [a, b, c]
    return s


def strip_long(tris):
    """Triangle list -> one strip as strip() makes, but each piece goes on
    through the next triangle sharing its last edge the right way round
    (greedy), so most triangles cost one index instead of about six. The
    game sends a car's indices through the push buffer every frame: the
    Cobalt's body, one triangle a piece, was 60,000 indices a pass."""
    import collections
    tris = [t for t in tris if len(set(t)) == 3]
    by_edge = collections.defaultdict(list)  # directed edge -> triangles holding it that way round
    for n, (a, b, c) in enumerate(tris):
        for e, x in (((a, b), c), ((b, c), a), ((c, a), b)):
            by_edge[e].append((n, x))
    used = [False] * len(tris)
    pieces = []
    for n0, t0 in enumerate(tris):
        if used[n0]: continue
        used[n0] = True
        p = list(t0)
        while True:
            # the next triangle at position len(p)-2: (p[-2], p[-1], x) on an even one, (p[-1], p[-2], x) on an odd
            e = (p[-2], p[-1]) if (len(p) - 2) % 2 == 0 else (p[-1], p[-2])
            nxt = next(((n, x) for n, x in by_edge.get(e, ()) if not used[n]), None)
            if nxt is None: break
            used[nxt[0]] = True
            p.append(nxt[1])
        pieces.append(p)
    s = []
    for p in pieces:
        if s:
            s += [s[-1], p[0]]
            if len(s) % 2: s.append(p[0])
        s += p
    return s


def strip_triangles(s):
    """A strip's real triangles, each in its winding (for checking strip_long)."""
    out = []
    for i in range(len(s) - 2):
        a, b, c = s[i:i + 3]
        if len({a, b, c}) < 3: continue
        t = (a, b, c) if i % 2 == 0 else (b, a, c)
        k = t.index(min(t))
        out.append(t[k:] + t[:k])
    return sorted(out)


def window_panes(parts):
    """Glass for an NFSU car, whose windows are holes: the stock parts are
    welded by position and each large closed hole high on the car (the
    windshield, the rear glass, the side windows) is filled with a fan from
    its middle. Returns (middle, ring) per pane, NFSU positions; the
    lights' and handles' holes are left alone."""
    import collections
    import numpy as np
    key, P, edges = {}, [], collections.Counter()
    for p in parts:
        ids = []
        for v in p['verts']:
            k = (round(v[0] / 0.004), round(v[1] / 0.004), round(v[2] / 0.004))
            if k not in key: key[k] = len(P); P.append(v[:3])
            ids.append(key[k])
        for t in p['tris']:
            if max(t) >= len(ids): continue
            a, b, c = (ids[i] for i in t)
            if len({a, b, c}) == 3:
                for e in ((a, b), (b, c), (c, a)): edges[tuple(sorted(e))] += 1
    P = np.array(P)
    adj = collections.defaultdict(list)
    for (a, b), n in edges.items():
        if n == 1: adj[a].append(b); adj[b].append(a)
    length, top = P[:, 0].max() - P[:, 0].min(), P[:, 2].max()
    seen, panes = set(), []
    for s in list(adj):
        if s in seen: continue
        ring, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nx = [n for n in adj[cur] if n != prev and n not in seen]
            if not nx: break
            prev, cur = cur, nx[0]
            ring.append(cur); seen.add(cur)
        Q = P[ring]
        perim = np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1).sum()
        if s in adj[ring[-1]] and len(ring) >= 8 and perim > 0.4 * length and Q[:, 2].mean() > 0.6 * top:  # a 4-point opening under the 240SX's roof skin is not a window
            panes.append((Q.mean(0), Q))
    return panes


def pack_atlas(images, livery_dir, out_dir, keep=(), pad=4, protect=(), cover=None, clear_rest=False, protect_mask=None):
    """Put NFSU textures ({hash: RGBA}) into free (fully clear) room of the
    template's livery atlas: livery0nc.xpr and livery0.xpr (512x512, both
    slices, clean and damaged) and livery0hi.xpr (1024x1024, every mip
    level), writing the three to out_dir. Only the 4x4 blocks touched are
    encoded again. Each texture gets `pad` texels of its own edge round it
    (filtering and mip levels would blend in the clear room). Returns
    {hash: (u0, v0, u1, v1)}, the texel centres of its corners in 0..1.
    keep: (u, v) spots (u16) that must stay as they are, such as the paint
    texel, which is clear too. protect: (u0, v0, u1, v1) boxes (0..1) that
    must stay too: the template parts still drawn (a Most Wanted car keeps
    the Civic's interior, whose texels are clear as well). cover: the
    texels (1024 x 1024) the new body's paint takes (template_layout):
    nothing is packed there, and they become plain paint (white, clear;
    the template's badges and dark trim lines there showed on the new body),
    but for the kept parts' boxes and the keep spots."""
    import numpy as np
    import forzaxpr as fx
    names = ('livery0nc.xpr', 'livery0.xpr', 'livery0hi.xpr')
    files = {n: bytearray(open(os.path.join(livery_dir, n), 'rb').read()) for n in names}
    nc = fx.textures(files['livery0nc.xpr'])[0]
    vol = fx.textures(files['livery0.xpr'])[0]
    hi = fx.textures(files['livery0hi.xpr'])[0]
    W, H, D = nc['w'], nc['h'], nc['d']
    assert (vol['w'], vol['h'], vol['d'], vol['format'], nc['format'], hi['format']) == (W, H, D, 0x0F, 0x06, 0x0F)
    assert hi['w'] == 2 * W and hi['h'] == 2 * H
    sw = fx.unswizzle_index(W, H, D)
    raw = np.frombuffer(bytes(files['livery0nc.xpr'][nc['start']:nc['start'] + W * H * D * 4]), np.uint8).reshape(-1, 4).copy()
    ncimg = raw[sw][..., [2, 1, 0, 3]]  # D, H, W, RGBA
    n = (W // 4) * (H // 4)
    vblocks = np.frombuffer(bytes(files['livery0.xpr'][vol['start']:vol['start'] + n * D * 16]), np.uint8).reshape(n, D, 16).copy()
    volimg = np.stack([fx.dxt(vblocks[:, z].tobytes(), W, H, 5) for z in range(D)])
    hiimg = fx.dxt(bytes(files['livery0hi.xpr'][hi['start']:]), 2 * W, 2 * H, 5).copy()
    # Free room: clear in the clean slice and the hi atlas. The damaged
    # slice is scratches laid out for the template's own body, which the
    # new body does not follow (it takes one paint texel), so it may go.
    used = (ncimg[0, ..., 3] > 0) | (volimg[0, ..., 3] > 0) | (hiimg[..., 3].reshape(H, 2, W, 2) > 0).any((1, 3))
    for u, v in keep:
        x, y = u * W // 65536, v * H // 65536
        used[max(0, y - 8):y + 8, max(0, x - 8):x + 8] = True
    if protect_mask is not None:  # the kept parts' own texels, two round (their boxes left a race car's atlas no room for a vinyl canvas)
        pm = protect_mask.copy()
        for d_ in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            pm |= np.roll(protect_mask, d_, (0, 1))
        used |= pm.reshape(H, 2, W, 2).any((1, 3))
    else:
        for u0, v0, u1, v1 in protect:
            used[max(0, int(v0 * H) - 2):int(v1 * H) + 3, max(0, int(u0 * W) - 2):int(u1 * W) + 3] = True
    rects, where = {}, {}
    def unprotect(m, outside_first=False):
        """m (1024) without the kept parts' texels: their own (protect_mask,
        two texels round) or else their boxes. outside_first: where the body's
        paint shares texels with them (a race car's interior took some of its
        door's, and the old livery's red showed there), the paint keeps them."""
        if protect_mask is not None:
            pm = protect_mask.copy()
            for d_ in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)): pm |= np.roll(protect_mask, d_, (0, 1))
            if outside_first: pm &= ~cover
            m &= ~pm
        else:
            for u0, v0, u1, v1 in protect:
                m[int(v0 * 2 * H):int(v1 * 2 * H) + 1, int(u0 * 2 * W):int(u1 * 2 * W) + 1] = False
    if clear_rest:  # the template's own livery art (a race car's sponsors and number) gone but for the kept parts' boxes
        rest = np.ones((2 * H, 2 * W), bool)
        unprotect(rest)
        for u, v in keep:  # (the black texel stays, a few texels round it; the paint texel is made white anyway)
            x, y = u * 2 * W // 65536, v * 2 * H // 65536
            if hiimg[min(2 * H - 1, y), min(2 * W - 1, x), :3].max() < 128:
                rest[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = False
        lo_ = rest.reshape(H, 2, W, 2).all((1, 3))
        white = np.array([255, 255, 255, 0], np.uint8)
        hiimg[rest] = white
        for z in range(D):
            ncimg[z][lo_] = white; volimg[z][lo_] = white
        used &= ~lo_
        rects['__paint__'] = (0, 0, W, H)
        print('atlas: the template\'s livery cleared (%d texels kept for its other parts)' % (~rest).sum())
    if cover is not None:
        grow = cover.copy()
        for d_ in ((1, 0), (-1, 0), (0, 1), (0, -1)): grow |= np.roll(cover, d_, (0, 1))
        unprotect(grow, outside_first=True)
        for u, v in keep:
            x, y = u * 2 * W // 65536, v * 2 * H // 65536
            if hiimg[min(2 * H - 1, y), min(2 * W - 1, x), :3].max() < 128:  # (the black texel stays)
                grow[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = False
        lo_ = grow.reshape(H, 2, W, 2).any((1, 3))
        used |= cover.reshape(H, 2, W, 2).any((1, 3))
        white = np.array([255, 255, 255, 0], np.uint8)
        hiimg[grow] = white
        badge = lo_ & (ncimg[0, ..., 3] > 0)
        ncimg[0][lo_] = white; volimg[0][lo_] = white
        for z in range(1, D):
            ncimg[z][badge] = white; volimg[z][badge] = white
        rects['__paint__'] = (0, 0, W, H)
        print('atlas: %d texels made plain paint for the body (vinyls)' % grow.sum())
    for h in sorted(images, key=lambda h: -images[h].shape[0] * images[h].shape[1]):
        # The image itself goes into the 1024 atlas, half of it into the
        # 512 ones (doubled into the 1024 one, a texture took four times the
        # room for the same detail)
        half = lambda im: im.reshape(im.shape[0] // 2, 2, im.shape[1] // 2, 2, 4).mean((1, 3)).astype(np.uint8)
        hiimg_, pd = images[h], pad
        while True:  # a narrower edge, then halved, until it fits (the body's paint regions leave less room)
            img = half(hiimg_) if hiimg_.shape[0] % 2 == 0 and hiimg_.shape[1] % 2 == 0 and min(hiimg_.shape[:2]) >= 8 else hiimg_
            th, tw = img.shape[0] + 2 * pd, img.shape[1] + 2 * pd
            th, tw = (th + 3) // 4 * 4, (tw + 3) // 4 * 4
            spot = next(((x, y) for y in range(0, H - th + 1, 4) for x in range(0, W - tw + 1, 4)
                         if not used[y:y + th, x:x + tw].any()), None)
            if spot is not None or min(hiimg_.shape[:2]) <= 16: break
            if pd > 2:
                pd = 2; continue
            print('atlas: no room for %dx%d, halved' % hiimg_.shape[:2])
            hiimg_, pd = half(hiimg_), pad
        if spot is None: raise SystemExit('no room in the livery atlas for a %dx%d texture' % img.shape[:2])
        x, y = spot
        used[y:y + th, x:x + tw] = True
        big = np.pad(img, ((pd, th - img.shape[0] - pd), (pd, tw - img.shape[1] - pd), (0, 0)), mode='edge')
        ncimg[:, y:y + th, x:x + tw] = big
        volimg[:, y:y + th, x:x + tw] = big
        if hiimg_ is img:
            hiimg[2 * y:2 * (y + th), 2 * x:2 * (x + tw)] = big.repeat(2, 0).repeat(2, 1)
        else:
            hiimg[2 * y:2 * (y + th), 2 * x:2 * (x + tw)] = np.pad(hiimg_, ((2 * pd, 2 * (th - img.shape[0] - pd)), (2 * pd, 2 * (tw - img.shape[1] - pd)), (0, 0)), mode='edge')
        rects[h] = (x, y, tw, th)
        ih, iw = img.shape[:2]
        where[h] = ((x + pd + 0.5) / W, (y + pd + 0.5) / H, (x + pd + iw - 0.5) / W, (y + pd + ih - 0.5) / H)
    # livery0nc: swizzled BGRA, every slice
    raw[sw.reshape(-1)] = ncimg[..., [2, 1, 0, 3]].reshape(-1, 4)
    files['livery0nc.xpr'][nc['start']:nc['start'] + raw.size] = raw.tobytes()
    # livery0: DXT5, each block's slices together
    for x, y, tw, th in rects.values():
        for z in range(D):
            enc = np.frombuffer(fx.encode_dxt5(np.ascontiguousarray(volimg[z, y:y + th, x:x + tw])), np.uint8).reshape(th // 4, tw // 4, 16)
            for by in range(th // 4):
                b0 = (y // 4 + by) * (W // 4) + x // 4
                vblocks[b0:b0 + tw // 4, z] = enc[by]
    files['livery0.xpr'][vol['start']:vol['start'] + vblocks.size] = vblocks.tobytes()
    # livery0hi: DXT5 with its mip levels, made again by halving where the textures went
    level, off, s = hiimg.astype(np.float32), hi['start'], 2 * W
    for lv in range(hi['mips']):
        bs = max(1, s // 4)
        if lv:
            level = level.reshape(s, 2, s, 2, 4).mean((1, 3))
        img = np.clip(level + 0.5, 0, 255).astype(np.uint8)
        if s < 4: img = np.pad(img, ((0, 4 - s), (0, 4 - s), (0, 0)), mode='edge')
        for x, y, tw, th in rects.values():
            k = s / W  # this level's texels per 512-texel
            bx0, by0 = int(x * k) // 4, int(y * k) // 4
            bx1, by1 = min(bs, -(-int((x + tw) * k) // 4)), min(bs, -(-int((y + th) * k) // 4))
            bx1, by1 = max(bx1, bx0 + 1), max(by1, by0 + 1)
            enc = fx.encode_dxt5(np.ascontiguousarray(img[4 * by0:4 * by1, 4 * bx0:4 * bx1]))
            for by in range(by1 - by0):
                row = enc[16 * (bx1 - bx0) * by:16 * (bx1 - bx0) * (by + 1)]
                o = off + 16 * ((by0 + by) * bs + bx0)
                files['livery0hi.xpr'][o:o + len(row)] = row
        off += bs * bs * 16
        s = max(1, s // 2)
    os.makedirs(out_dir, exist_ok=True)
    for name, data in files.items():
        open(os.path.join(out_dir, name), 'wb').write(bytes(data))
    return where


def nfsu_rgba(t):
    """An NFSU texture's top level as RGBA."""
    import numpy as np
    import forzaxpr as fx
    w, h = t['width'], t['height']
    if t['fourcc'] in ('DXT1', 'DXT3', 'DXT5'):
        return fx.dxt(t['data'], w, h, int(t['fourcc'][3]))
    return np.frombuffer(t['data'][:w * h * 4], np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]]


def lamp_texture(role, side):
    """A lamp's picture made here, as an NFSU texture (64 x 64, BGRA): Underground 2's shared HEADLIGHT_<side>
    and BRAKELIGHT_<side> are in its global files, not in an add-on car's pack. A headlight's reflector white
    in the middle to a cool grey at the rim, with a ring; a tail light red, brighter in the middle. Alpha as
    Forza's own lamp texels: 0 the headlights, 25 the tail lights."""
    import numpy as np
    y, x = np.mgrid[0:64, 0:64].astype(float)
    r = np.clip(np.hypot(x - 31.5, y - 31.5) / 32, 0, 1)[..., None]
    if role == 'HEADLIGHT':
        rgb = (1 - r ** 1.5) * np.array([255, 252, 245]) + r ** 1.5 * np.array([170, 180, 196])
        rgb *= 1 - 0.12 * np.exp(-((r - 0.55) / 0.06) ** 2)  # (the reflector's ring)
        a = 0
    else:
        rgb = (1 - r) * np.array([255, 72, 56]) + r * np.array([150, 12, 14])
        a = 25
    img = np.concatenate([rgb[..., ::-1], np.full((64, 64, 1), a)], -1).clip(0, 255).astype(np.uint8)  # (BGRA)
    return {'name': '%s_%s (made)' % (role, side), 'width': 64, 'height': 64, 'fourcc': 'BGRA', 'data': img.tobytes()}


def dark_uv(xpr_path):
    """An opaque black texel of the template's livery atlas (slice 0), in
    the middle of a black patch, as u16 u, v. Body material blends paint and
    the atlas by its alpha, so this one shows black."""
    import numpy as np
    import forzaxpr
    d = open(xpr_path, 'rb').read()
    fmt = struct.unpack_from('<I', d, 12 + 12)[0]
    w, h, dd = 1 << ((fmt >> 20) & 15), 1 << ((fmt >> 24) & 15), (1 << ((fmt >> 28) & 15)) if ((fmt >> 4) & 15) == 3 else 1
    hdr = struct.unpack_from('<I', d, 8)[0]
    px = np.frombuffer(d[hdr:hdr + w * h * dd * 4], np.uint8).reshape(-1, 4)
    img = px[forzaxpr.unswizzle_index(w, h, dd)][0]  # BGRA, slice 0
    ok = (img[..., :3].max(-1) < 24) & (img[..., 3] > 250)
    k = 3  # want the 7x7 around it black too
    best = None
    for y in range(k, h - k, 2):
        for x in range(k, w - k, 2):
            if ok[y - k:y + k + 1, x - k:x + k + 1].all():
                best = (x, y); break
        if best: break
    if not best:
        ys, xs = np.nonzero(ok)
        best = (int(xs[0]), int(ys[0])) if len(xs) else (0, 0)
    return (int((best[0] + 0.5) / w * 65536), int((best[1] + 0.5) / h * 65536))


def part_prefix(nparts, folder):
    """The car's name before its parts' (CHIRON_KIT00_BODY_A): the folder's, unless no part has it, as for an add-on in
    another car's folder (CARS_REPLACE/GALLARDO holding the Huracan's parts) or one named apart (the Senna's A_...);
    then the commonest before _KITnn_ or _BASE."""
    import collections
    if any(p['name'].startswith(folder + '_') for p in nparts): return folder
    c = collections.Counter(m.group(1) for p in nparts for m in [re.match(r'(.+?)_(?:KIT\d\d|BASE)', p['name'])] if m)
    return c.most_common(1)[0][0] if c else folder


def lamp_lens(name, tex=None, dark=True):
    """Whether a lamp's sheet is its lens (glass): GLASS in its name, also cut short at 24 letters (_G, _GL, _GLA,
    _GLAS: the nfs.com.ru pack's BMWM2_KIT00_HEADLIGHT_G), or a sheet a lamp's name has that is small (32 at most:
    a tint, 4 x 4 to 16 x 16 at 80-93% opaque) or mostly clear. Drawn as lamps they covered the lamps as dark or
    grey shells (the M2's, 335i's, RS5's, 4C's, Chiron's headlights, 6 Nov)."""
    n = name.upper()
    if 'LIGHT' not in n: return False
    if 'GLASS' in n or re.search(r'LIGHT_G(L(A(S)?)?)?$', n): return True
    if tex and str(tex.get('name', '')).endswith('(made)'): return False  # (a lamp picture made here: clear by design, as Forza's own lamp texels)
    if tex and tex.get('data') and n.endswith(('_ON', '_OFF', '_O', '_OF')) is False:
        try:
            img = nfsu_rgba(tex)
        except Exception:
            return False
        if max(img.shape[:2]) <= 32: return True
        if img[..., :3].reshape(-1, 3).std(0).mean() < 4 and img[..., :3].mean() < 90: return True  # (one flat dark tint: the Brera's 64 x 32 grey over its tail lights, 6 Nov)
        if dark and img[..., :3].max(-1).mean() < 40: return True  # (near black throughout: the Eclipse's carbon SIDELIGHT strip over its headlights; not at draw time, where the same sheet is its splitter and diffuser)
        if (img[..., 3] < 128).mean() > 0.6: return True
    return False


def auto_materials(nparts, textures, prefix):
    """Groups named only "Material" (the nfs.com.ru pack's cars, made in ZModeler: nothing then read as paint and the
    whole body came out black trim, the BMW M2 of 5 Nov) named from their texture: the car's SKIN1 (made at run time)
    paint, its other SKINs black trim, BADGING and MISC decals, the lamp sheets head or brake lights by the group's
    end of the car, the interior's sheet drawn as it is; Most Wanted's shared role textures (windows, lamps) by name."""
    import struct as st
    names = {h: t['name'] for h, t in textures.items()}
    roles = ['WINDOW_FRONT', 'WINDOW_REAR', 'WINDOW_LEFT_FRONT', 'WINDOW_RIGHT_FRONT', 'WINDOW_LEFT_REAR', 'WINDOW_RIGHT_REAR',
             'HEADLIGHT_LEFT', 'HEADLIGHT_RIGHT', 'BRAKELIGHT_LEFT', 'BRAKELIGHT_RIGHT', 'HEADLIGHT_GLASS_LEFT',
             'HEADLIGHT_GLASS_RIGHT', 'BRAKELIGHT_GLASS_LEFT', 'BRAKELIGHT_GLASS_RIGHT', 'DOORLINE', 'LICENSEPLATE',
             'BLACK', 'CHROME', 'GRILL', 'INTERIOR', 'DRIVER', 'TIRE', 'REAR_DEFROSTER', prefix + '_SKIN1']
    for r in roles: names.setdefault(bhash(r), r)
    renamed = 0
    for p in nparts:
        if not p['materials'] or not all(re.match(r'(Material|$)', m) for m in p['materials']): continue
        idx = [i for t in p['tris'] for i in t]
        for gi, g in enumerate(p['groups']):
            ti, si = st.unpack_from('<II', g, 0x1C)
            n = names.get(p['textures'][ti] if ti < len(p['textures']) else 0, '').upper()
            n = re.sub(r'(HEAD|BRAKE|SIDE)LI(G(H)?)?$', r'\1LIGHT', n)  # (a sheet's name cut short at 24 letters: BMW335E92_KIT00_HEADLIG)
            cnt, = st.unpack_from('<I', g, 12); first, = st.unpack_from('<I', g, 0x34)
            xs = [p['verts'][i][0] for i in idx[first:first + cnt] if i < len(p['verts'])]
            front = bool(xs) and sum(xs) / len(xs) > 0
            if n.endswith('_SKIN1') or n == 'SKIN1': m = 'BODY'
            elif re.search(r'_SKIN\d', n): m = 'BODY_BLACK'
            elif 'BADGING' in n or n.endswith('_MISC') or 'LOGO' in n: m = 'BADGING'
            elif 'INTERIOR' in n: m = 'BADGING'
            elif 'DRIVER' in n: m = 'DRIVER'
            elif 'TIRE' in n or 'RIM' in n: m = 'TIRE'
            elif 'WINDOW' in n or n == 'REAR_DEFROSTER': m = 'WINDOW_FRONT'  # (the rear glass's role texture, its heater lines: as black trim, the LF-A's, M2's, 190E's rear window was a hole, 6 Nov)
            elif ('HEADLIGHT' in n or 'BRAKELIGHT' in n or 'SIDELIGHT' in n) and lamp_lens(n, textures.get(p['textures'][ti]) if ti < len(p['textures']) else None):
                m = 'LEFT_HEADLIGHT_GLASS' if front else 'DECAL_BRAKELIGHT_LENS'  # (both left out: mw_material)
            elif 'HEADLIGHT' in n or 'BRAKELIGHT' in n or 'LIGHT' in n: m = 'LEFT_HEADLIGHT_BULB' if front else 'BRAKELIGHT'
            elif n in ('DOORLINE', 'LICENSEPLATE'): m = n
            elif 'CHROME' in n: m = 'CHROME'
            else: continue
            # (its own material entry: a group names its material by its own index at 0x20, not its place in the list;
            # renamed by place, the 335i's roof gave its brake-light sheet "headlight glass" and its headlights black, 6 Nov)
            p['materials'].append(m)
            p['shaders'].append(bhash(m))
            g2 = bytearray(g); st.pack_into('<I', g2, 0x20, len(p['materials']) - 1); p['groups'][gi] = bytes(g2)
            renamed += 1
    if renamed: print('materials: %d groups named only "Material" named by their textures' % renamed)


def sliver(p, t, base):
    """A triangle over 15 cm long and under 1 cm high."""
    import numpy as np
    V = np.array([p['verts'][i - base][:3] for i in t], float)
    e = [np.linalg.norm(V[b] - V[a]) for a, b in ((0, 1), (1, 2), (2, 0))]
    area = np.linalg.norm(np.cross(V[1] - V[0], V[2] - V[0])) / 2
    return max(e) > 0.15 and 2 * area / max(max(e), 1e-9) < 0.01


def two_sided(p, tris, base):
    """A glass group modelled with its inside (the Countach's, from CSR2): most triangles have another straight across
    (within 5 cm) on a parallel plane 2 to 20 mm away, the glass's thickness. Then only its outer layer, the triangles
    with their twin on the cabin's side, as triangles to keep; else None."""
    import numpy as np
    if len(tris) < 8: return None
    V = np.array([p['verts'][i - base][:3] for t in tris for i in t], float).reshape(-1, 3, 3)
    C = V.mean(1)
    n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    ok = np.linalg.norm(n, axis=1) > 1e-9  # (the Countach's glass: 732 of its 1,726 triangles have no area)
    tris, V, C, n = [t for t, k in zip(tris, ok) if k], V[ok], C[ok], n[ok]
    if len(tris) < 8: return None
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    mid = C.mean(0)
    u = n * np.sign(np.einsum('ij,ij->i', n, C - mid))[:, None]  # (each normal turned away from the cabin's middle)
    has, inner = np.zeros(len(C), bool), np.zeros(len(C), bool)
    for i in range(len(C)):
        d = C - C[i]
        off = d @ u[i]
        side = np.linalg.norm(d - off[:, None] * u[i], axis=1)  # (straight across: on curved glass a neighbour 10 cm along sits a few mm off its plane)
        m = (side < 0.05) & (np.abs(n @ n[i]) > 0.95) & (np.abs(off) > 0.002) & (np.abs(off) < 0.02)
        if m.any():
            has[i] = True
            inner[i] = (off[m] > 0).mean() > 0.5  # (its twin further out: this one is the inside)
    if has.mean() <= 0.4: return None  # (the Countach's glass 0.72, the other cars' 0.11 at most)
    return [t for t, k in zip(tris, inner) if not k]


def convert(template_path, nfsu_dir, out_path, keep_glass=False, badges=None, liveries=None, stock_wing=True, clear_livery=False, vinyl=None):
    import numpy as np
    car = carbin.read(open(template_path, 'rb').read())
    tlayout, tcover = template_layout(car)  # (before its parts are replaced)
    nparts = nfsu.read(os.path.join(nfsu_dir, 'GEOMETRY.BIN'))
    textures = nfsu.read_textures(os.path.join(nfsu_dir, 'TEXTURES.BIN'))
    prefix = part_prefix(nparts, os.path.basename(os.path.normpath(nfsu_dir)).upper())
    names = {bhash(prefix + '_SKIN1'): prefix + '_SKIN1'}
    names.update({h: t['name'] for h, t in textures.items()})
    # Underground 2's shared lamp textures (its global files, not an add-on car's pack: the Neon's). Missing,
    # the lamps drew from whatever template texels their coordinates found: the headlights' reflectors dark
    # (Chrome by their shader), their glass a white shell, the tail lights under glass drawn opaque black.
    # The glass covers are left out, and the lamps get pictures made here (lamp_texture), packed as the car's own.
    # The same pictures for every lit lamp face of an Underground 2 car's KIT00 lamps (made_pic): the Celica
    # GT-Four's lamps are drawn from its door-handle and interior sheets, grey and dark red, black as Black.
    made_lamps, no_glass, made_pic = {}, set(), {}
    mw_ = any(p['materials'] for p in nparts)  # (as mw, below: a Most Wanted car finds its own lamps there)
    used_tex = {th for p in nparts for th in p['textures']}
    for role in ('HEADLIGHT', 'BRAKELIGHT'):
        for side in ('LEFT', 'RIGHT'):
            h, g = bhash('%s_%s' % (role, side)), bhash('%s_GLASS_%s' % (role, side))
            lamp_part = any('_KIT00_' + role in p['name'] for p in nparts)
            if not (h in used_tex or g in used_tex or (lamp_part and side == 'LEFT' and not mw_)): continue  # (a Most Wanted car's too, when it uses the shared sheets: the 335i's, Huracan's, ZR1's lamps drew black, 6 Nov)
            if g in used_tex and not (g in textures and textures[g]['data']): no_glass.add(g)
            if not (h in textures and textures[h]['data']):
                textures[h] = lamp_texture(role, side)
                names[h] = '%s_%s' % (role, side)
                made_lamps[h] = HEADLIGHTS if role == 'HEADLIGHT' else TAILLIGHTS
            if side == 'LEFT' and lamp_part and h in made_lamps and not mw_: made_pic[role] = h  # (a Most Wanted car's lamp parts keep their own sheets' faces)
    if made_lamps:  # (both ends' pictures, as a group takes its end's: the 335i's headlights are on BRAKELIGHT_RIGHT)
        for role, m_ in (('HEADLIGHT', HEADLIGHTS), ('BRAKELIGHT', TAILLIGHTS)):
            h = bhash('%s_LEFT' % role)
            if h not in textures or not textures[h].get('data'):
                textures[h] = lamp_texture(role, 'LEFT'); names[h] = '%s_LEFT' % role; made_lamps[h] = m_
    if made_lamps or no_glass:
        print('lamps: %d pictures made (%s), %d glass covers left out' % (len(made_lamps), ', '.join(sorted(names[h] for h in made_lamps)), len(no_glass)))

    def find(suffix):
        """The stock part's detail levels, finest first (_A to _D; some
        names are cut short, so ordered by size). Most Wanted's damage
        shapes and far body (_E) are left out."""
        found = [p for p in nparts if p['name'].startswith(prefix + '_KIT00_' + suffix) and 'DAMAGE' not in p['name']
                 and not p['name'].endswith('_E')]
        return sorted(found, key=lambda p: -len(p['verts']))

    # Most Wanted (nfsu.read gives its parts in Underground's shape): whole
    # bodies with bumpers and skirts in, windows and lights as parts of their
    # own, and materials named per group (see mw_material)
    mw = any(p['materials'] for p in nparts)
    if mw:
        auto_materials(nparts, textures, prefix)
        for p in nparts:
            for name in p['materials']: SHADERS.setdefault(bhash(name), mw_material(name))
        # Its parts name textures by role, resolved to the car's own at run time:
        # the lit lamps (_ON; the unlit _OFF read as dark grey and dull red in the game, the Brera's, Evora's and
        # Eclipse's, 6 Nov: Forza's own lamp texels are the lit colours), else the largest of the role's
        for role, own in (('HEADLIGHT', '_KIT00_HEADLIGH'), ('BRAKELIGHT', '_KIT00_BRAKELIG')):
            hit = next((h for h in (bhash('%s_KIT00_%s_%s' % (prefix, role, s)) for s in ('ON', 'OFF'))
                        if h in textures and textures[h]['data']), None)
            if hit is None:
                hit = max((h for h, t in textures.items() if t['name'].startswith(prefix + own) and t['data']),
                          key=lambda h: (textures[h]['width'] * textures[h]['height'], float(nfsu_rgba(textures[h])[..., :3].mean())),
                          default=None)  # (of two the same size, the brighter: the lit one, the Brera's _ON under a cut-short name)
            for side in ('LEFT', 'RIGHT'):
                if hit is not None: textures[bhash('%s_%s' % (role, side))] = textures[hit]
        names.update({h: t['name'] for h, t in textures.items()})
        print('Most Wanted car: %d parts, %d textures' % (len(nparts), len(textures)))
    # NFSU_COVERS=1 (newcars.py COVERS): a Most Wanted port's lamps under shells of another sheet (the RS5's, its MISC
    # sheet's dark glass over the lamps, in other parts than theirs, 6 Nov): what is not lamp and lies within a couple of
    # centimetres of the lamps' surfaces, all three corners, is left out. Cells of 2.5 cm round every lamp vertex (the RS5's
    # covers stand up to 6 cm off).
    COVER_CELLS = None
    if mw and os.environ.get('NFSU_COVERS'):
        COVER_CELLS = set()
        def is_lamp(th):
            n = names.get(th, '').upper()
            return th in made_lamps or (('HEADLIG' in n or 'BRAKELIG' in n or n.endswith(('_HEAD', '_BRAK'))) and not lamp_lens(n, textures.get(th), dark=False))
        for p_ in nparts:
            if 'DAMAGE' in p_['name']: continue
            idx_ = [i for t in p_['tris'] for i in t]
            for g in p_['groups']:
                cnt_, = struct.unpack_from('<I', g, 12); first_, = struct.unpack_from('<I', g, 0x34); ti_, = struct.unpack_from('<I', g, 0x1C)
                if ti_ < len(p_['textures']) and is_lamp(p_['textures'][ti_]):
                    for i in idx_[first_:first_ + cnt_]:
                        if i < len(p_['verts']):
                            x, y, z = p_['verts'][i][:3]
                            COVER_CELLS.add((int(np.floor(x / 0.025)), int(np.floor(y / 0.025)), int(np.floor(z / 0.025))))
        print('covers: %d lamp cells' % len(COVER_CELLS))
    def near_lamp(v):
        cx, cy, cz = (int(np.floor(c / 0.025)) for c in v[:3])
        return any((cx + a, cy + b, cz + c) in COVER_CELLS for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1))

    # the fit: template body vs NFSU body (+ roof)
    tbody = next(p for p in car['parts'] if p['name'].startswith('body'))
    tz = [v[2] / 4096 for v in tbody['verts']]; ty = [v[1] / 4096 for v in tbody['verts']]
    # Most Wanted's roof (with a copy of each window) is <CAR>_BASE_A to _D
    base = sorted([p for p in nparts if p['name'].startswith(prefix + '_BASE_')], key=lambda p: -len(p['verts'])) if mw else []
    nb = find('BODY')[0]['verts'] + (find('ROOF')[0]['verts'] if find('ROOF') else []) + (base[0]['verts'] if base else [])
    nx = [v[0] for v in nb]; nz = [v[2] for v in nb]
    k = (max(tz) - min(tz)) / (max(nx) - min(nx))
    if FIT_WIDTH:  # as wide as the template (cartoolkit's plan "fit": "width"): fitted to the shorter Bentley's length the SC63
        tx = [v[0] / 4096 for v in tbody['verts']]  # came out 9% narrower and lower than its wheels; its length then follows the hubs
        k = (max(tx) - min(tx)) / (max(v[1] for v in nb) - min(v[1] for v in nb))
    k *= SCALE  # (the plan's correction: an Underground 2 add-on's body, its bumpers apart, against the template's whole
                # one: the Silvia S15 Spec-R came out 5% longer and 12% wider than Forza's own S15, the audit of 5 Nov)
    dz = (max(tz) + min(tz)) / 2 - k * (max(nx) + min(nx)) / 2
    dy = min(ty) - k * min(nz) - LOWER
    floor = min(nz)  # (the finest body's lowest point: nothing hangs below it)
    kx = 1.0
    if FIT_TRACK:  # its width then the template's (plan "fit": "track"): the wheels are the template's, at its track, and
        tx = [v[0] / 4096 for v in tbody['verts']]  # the Neon, fitted by length 8% wider than the SRT-4, had them 6-9 cm inside its fenders
        kx = (max(tx) - min(tx)) / (k * (max(v[1] for v in nb) - min(v[1] for v in nb)))
    kx *= WIDEN  # (the plan's "widen": the body's width alone scaled, over the template's wheels at its track)
    print('fit: scale %.3f, forward offset %.3f, up offset %.3f%s' % (k, dz, dy, ', width x%.3f' % kx if kx != 1 else ''))

    dark = dark_uv(os.path.join(os.path.dirname(template_path), 'liveries', 'standard', 'livery0nc.xpr'))
    # The paint texel: the one the template body's door uses (its Body
    # vertex nearest the middle of the car's side at half height).
    tb = [v for sp in tbody['subparts'] if sp['id'] == 1 and sp['material'] == BODY for v in (tbody['verts'][i] for i in sp['indices'])]
    xs = max(v[0] for v in tb); ym = (max(v[1] for v in tb) + min(v[1] for v in tb)) / 2
    door = min(tb, key=lambda v: (v[0] - xs) ** 2 + (v[1] - ym * 0.8) ** 2 + v[2] ** 2)
    paint = (door[10], door[11])
    if mw:
        # A light one: the game multiplies the paint colour by the texel, and
        # on a dark one every colour came out black. Of the template body's
        # paint texels, the brightest whose surroundings (16 texels round, for
        # the smaller mip levels) are as light. Light both where 65536 spans
        # the atlas once and where 32768 does (the Civic's paint coordinates
        # are all under 32768 and land on white read so; the lamps' read as
        # 65536 a span): the earlier pick was white one way, black the other,
        # and the car came out black.
        import forzaxpr as fx
        d = open(os.path.join(os.path.dirname(template_path), 'liveries', 'standard', 'livery0hi.xpr'), 'rb').read()
        t = fx.textures(bytearray(d))[0]
        hi = fx.dxt(d[t['start']:], t['w'], t['h'], 5)[:t['h']].astype(float)
        def light(u, v, span):
            x, y = int(u / span * t['w']) % t['w'], int(v / span * t['h']) % t['h']
            if not (16 <= x < t['w'] - 16 and 16 <= y < t['h'] - 16): return None
            around = hi[y - 16:y + 17, x - 16:x + 17]
            if (around[..., 3] > 0).any(): return None
            return around[..., :3].mean() - around[..., :3].std(), hi[y, x, :3]
        best = None
        for v in tb:
            both = [light(v[10], v[11], span) for span in (65536, 32768)]
            if None in both: continue
            score = min(s for s, _ in both)
            if best is None or score > best[0]: best = (score, (v[10], v[11]), [c.astype(int).tolist() for _, c in both])
        if best:
            paint = best[1]
            print('paint: the lightest clear texel of the template body, %s read either way' % best[2])
    print('paint: texel at u, v = %.3f, %.3f' % (paint[0] / 65536, paint[1] / 65536))
    print('windows: black texel at u, v = %.3f, %.3f' % (dark[0] / 65536, dark[1] / 65536))
    # as the game reads it (see ATLAS_UV): a Most Wanted car's coordinates count 32768 across the atlas,
    # and the texel found at 65536 a span drew from twice as far in (the SC63's black came out green)
    dark_read = (dark[0] // 2, dark[1] // 2) if mw or UV32 else dark
    # The NFSU car's own textures (lights, badges) go into the livery atlas,
    # written beside the output (liveries/standard).
    own = {th for key in ('BODY', 'ROOF', 'HOOD', 'TRUNK', 'FRONT_BUMPER', 'REAR_BUMPER', 'SKIRT', 'HEADLIGHT', 'BRAKELIGHT', 'LEFT_SIDE_MIRRO', 'RIGHT_SIDE_MIRR')
                                + (('LEFT_HEADLIGHT', 'RIGHT_HEADLIGHT', 'LEFT_BRAKELIGHT', 'RIGHT_BRAKELIGHT', 'SPOILER') if mw else ())
           for p in find(key) for th in p['textures'] if th in textures and textures[th]['data']}
    if mw:  # only what is drawn from its texture (badges, lamps): the atlas has little room, and trim takes Forza's own
        # (each group's material by its own index at 0x20, not its place in the list; the roof (BASE) too: the 335i's
        # lamps and badges are there, and none of its sheets was packed, 6 Nov)
        def drawn_from(p):
            for g in p['groups']:
                ti, si = struct.unpack_from('<II', g, 0x1C)
                if ti < len(p['textures']) and si < len(p['materials']) and mw_material(p['materials'][si]) in (BADGE, HEADLIGHTS, TAILLIGHTS):
                    yield p['textures'][ti]
        own = {th for p in nparts if ('_KIT00_' in p['name'] or '_BASE' in p['name']) and p['materials']
               for th in drawn_from(p) if th in textures and textures[th]['data']}
    own |= set(made_pic.values())  # (packed though no part names them: the Celica GT-Four's lamps)
    if mw:  # (a Most Wanted car's lamp faces all draw their end's _LEFT sheet, below (a made picture, or the car's own
        # lamp sheet put in its place): packed though no group names it; the Evora's, naming only BRAKELIGHT_RIGHT, read
        # blank atlas and came out grey-white, 6 Nov)
        own |= {h for h in made_lamps if textures.get(h, {}).get('data')}
    livery_dir = os.path.join(os.path.dirname(template_path), 'liveries', 'standard')
    images = {h: nfsu_rgba(textures[h]) for h in own}
    if mw:  # halved to 128 at most: the atlas's free room is small
        for h, img in images.items():
            while max(img.shape[:2]) > 128:
                img = img.reshape(img.shape[0] // 2, 2, img.shape[1] // 2, 2, 4).mean((1, 3)).astype(np.uint8)
            if any(k in textures[h]['name'] for k in ('HEADLIGH', 'BRAKELIG')):
                # Forza's lamp texels have alpha 0 (the template's lamps, reverse
                # lights and paint: 0, the taillights 25 on average); Most Wanted's
                # lamp textures are opaque, and drawn so the lamps came out white
                img = img.copy()
                img[..., 3] = 0
                rgb_ = img[..., :3].reshape(-1, 3).astype(float).mean(0)
                if any(k in textures[h]['name'] for k in ('BRAKELIG', '_BRAK')) or names.get(h, '').startswith('BRAKELIGHT') or rgb_[0] > 1.5 * max(rgb_[1], rgb_[2]):  # (or red throughout: the RS5's tail art is on its HEADLIGHT sheet)
                    # (Most Wanted's tail-light sheets are dull red under its own glow: drawn as they are the Brera's,
                    # Evora's read dark in the game, 6 Nov. Lifted, as a lit lamp's red.)
                    f = img[..., :3].astype(float)
                    red = f[..., 0] > 1.3 * np.maximum(f[..., 1], f[..., 2]) + 8  # (the lenses: red lifted to a lit lamp's, the rest a little)
                    f[red, 0] *= 2.2; f[red, 1:] *= 1.2; f[~red] = 255 * (f[~red] / 255) ** 0.8
                    img[..., :3] = np.clip(f, 0, 255).astype(np.uint8)
            images[h] = img
    extra = badge_images(badges)  # the --badges folder's, by name
    for h in images:
        if textures[h]['name'].endswith('_BADGING'):
            # The lettering is mid grey, which NFSU tinted; here it is drawn as is,
            # and on grey paint it could not be read. Greys become silver.
            img = images[h].astype(int)
            grey = (img[..., :3].max(-1) - img[..., :3].min(-1) < 24) & (img[..., 3] > 0)
            img[grey, :3] = np.clip(img[grey, :3] * 2.1, 0, 235)
            if 'logo' in extra:  # the nose emblem (the sheet's top left) becomes the given logo
                x0, y0, x1, y1 = SHEET_BADGES['logo']
                logo = load_image(os.path.join(badges, next(f for f in os.listdir(badges) if os.path.splitext(f)[0].lower() == 'logo')),
                                  (x1 - x0 + 1, y1 - y0 + 1))
                img[y0:y1 + 1, x0:x1 + 1] = logo
            images[h] = img.astype(np.uint8)
    ready = set()  # decal sheets made ready for Body
    if UV32 or mw:  # an Underground 2 car's decal sheets, drawn as Body (see UV32 and BADGE in the parts); a Most Wanted car's BADGING sheet too (the Charger's door handles and fuel flap were dark boxes, 6 Nov)
        uses = {}
        for p in nparts:
            for g in p['groups']:
                ti, si = struct.unpack_from('<II', g, 0x1C)
                if ti < len(p['textures']) and si < len(p['shaders']):
                    th = p['textures'][ti]
                    uses.setdefault(th, set()).add(material_for(names.get(th, ''), p['shaders'][si]))
        for h in images:
            if uses.get(h) == {BADGE} and (UV32 or 'BADGING' in str(textures.get(h, {}).get('name', '')).upper()):
                images[h] = paint_ready(images[h]); ready.add(h)
    images.update(extra)
    bands = canvas_bands(nparts) if vinyl or SKIN else []
    for j, (r0, r1, c0, c1) in enumerate(bands):  # (not k: the fit's scale)
        images[(CANVAS, j)] = np.tile(np.array([255, 255, 255, 0], np.uint8), (r1 - r0, c1 - c0, 1))
    protect = []
    keep_mask = np.zeros((1024, 1024), bool)  # the same, texel by texel (a race car's interior boxes covered most of its atlas)
    if mw:  # the template parts that stay (interior, steering wheel, brakes, driver): each triangle's texel box
        replaced = ('body', 'glass', 'headlight', 'taillight', 'bumper', 'skirt', 'hood', 'wing', 'trunk', 'mirror', 'exhaust', 'BADGE', 'bands', 'lampglass',
                    'driver')  # (a race car's driver01 is drawn from all of its livery, as paint)
        for p in car['parts']:
            if p['name'].startswith(replaced): continue
            for sp in p['subparts']:
                ix = sp['indices']
                for j in range(len(ix) - 2):  # (not k: that is the fit's scale, which pos() reads; as k this moved every vertex to the edge of the range, and the car vanished)
                    tri = [p['verts'][i] for i in ix[j:j + 3]]
                    if len(set(ix[j:j + 3])) < 3 or len(tri[0]) < 12: continue
                    us, vs = [v[10] / BADGE_UV % 1 for v in tri], [v[11] / BADGE_UV % 1 for v in tri]  # (see ATLAS_UV)
                    if max(us) - min(us) < 0.5 and max(vs) - min(vs) < 0.5:  # (wrapped ones left out)
                        protect.append((min(us), min(vs), max(us), max(vs)))
                        uv_raster(keep_mask, np.array([us, vs]).T * 1024)
    atlas = pack_atlas(images, livery_dir,
                       os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'),
                       keep=[paint, dark] + ([(paint[0] * 2 % 65536, paint[1] * 2 % 65536)] if mw else []),  # (both readings: see the paint texel)
                       protect=protect, cover=None if vinyl or SKIN else tcover, clear_rest=clear_livery, protect_mask=keep_mask if mw else None)
    if liveries:
        paint_shop(liveries, os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries.bin'),
                   os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'), [r for h, r in atlas.items() if not (isinstance(h, tuple) and h[0] == CANVAS)],
                   paint=tcover)
    if vinyl:
        bake_vinyl(os.path.join(nfsu_dir, 'VINYLS.BIN'), prefix, *vinyl, [(atlas[(CANVAS, k)], b) for k, b in enumerate(bands)],
                   os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'))
    if SKIN:
        th = next(h for h, t in textures.items() if t['name'] == SKIN[0] and t['data'])
        img = nfsu_rgba(textures[th])[..., :3].astype(float)
        while img.shape[0] >= 2 * CANVAS_SIZE:  # halved while it can be, then to the size by its nearest texels' blend
            img = img.reshape(img.shape[0] // 2, 2, img.shape[1] // 2, 2, 3).mean((1, 3))
        if img.shape[0] != CANVAS_SIZE:
            c = (np.arange(CANVAS_SIZE) + 0.5) * img.shape[0] / CANVAS_SIZE - 0.5
            i0 = np.clip(np.floor(c).astype(int), 0, img.shape[0] - 2); w = np.clip(c - i0, 0, 1)[:, None]
            img = img[i0] * (1 - w[..., None]) + img[i0 + 1] * w[..., None]
            img = img[:, i0] * (1 - w[None]) + img[:, i0 + 1] * w[None]
        # the plain paint elsewhere: the sheet's commonest colour (the SC63's green)
        q = (img // 16).astype(int)
        q = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
        plain = img[q == np.bincount(q.ravel()).argmax()].mean(0)  # (not base: the roof's parts)
        bake_canvas(img, plain, [(atlas[(CANVAS, k)], b) for k, b in enumerate(bands)],
                    os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'))
        print('skin: %s baked into livery1 (%d bands at %d texels; the rest of the paint %s)' % (SKIN[0], len(bands), CANVAS_SIZE, plain.round().astype(int).tolist()))
    print('atlas: %s' % ', '.join('%s at %.3f, %.3f' % (h if isinstance(h, (str, tuple)) else textures[h]['name'], r[0], r[1]) for h, r in atlas.items()))

    # Wheels: the template's hubs (its brake rotors) stay where its physics
    # puts them, so the NFSU body is stretched between its wheel arches
    # (the middles of their liners, 010cb64a) to put each arch over its
    # hub; ahead of the front arch and behind the rear one it keeps the
    # scale k. Scaled evenly, the S13's shorter wheelbase left the rear
    # wheels standing behind their arches.
    hubs = [(min(v[2] for v in p['verts']) + max(v[2] for v in p['verts'])) / 2 / 4096
            for p in car['parts'] if p['name'].startswith('rotor') or '_rotor' in p['name']]  # (a race car's: 14_rotor_steelLF)
    if not hubs:  # a template with no brake rotors in its model (the Enzo, the Zonda, the DB9, the 996 GT2...): its hubs
        # from its physics, the wheelbase about its middle (maxdata.xml: Wheelbase, BottomCenterWheelbasePos z, metres), at
        # 1.602 model units a metre (the street cars with rotors, the C32 to the SLR, to a few mm; the 5 Nov audit)
        mx = os.path.join(os.path.dirname(template_path), 'physics', 'maxdata.xml')
        if os.path.exists(mx):
            t = open(mx, encoding='latin-1').read()
            wb, zc = re.search(r'Wheelbase="([^"]+)"', t), re.search(r'BottomCenterWheelbasePos[^>]*z="([^"]+)"', t)
            if wb and zc:
                wb, zc = float(wb.group(1)), float(zc.group(1))
                hubs = [(zc + wb / 2) * 1.602, (zc - wb / 2) * 1.602]
                print('wheels: the template hubs from its physics: %.3f, %.3f' % tuple(hubs))
    nbody = find('BODY')[0]
    nidx = [i for t in nbody['tris'] for i in t]
    liner = [nbody['verts'][i][0] for g in nbody['groups'] if nbody['shaders'][struct.unpack_from('<I', g, 0x20)[0]] == 0x010CB64A
             for i in nidx[struct.unpack_from('<I', g, 0x34)[0]:struct.unpack_from('<I', g, 0x34)[0] + struct.unpack_from('<I', g, 12)[0]]]
    if mw:
        # No arch liners, and the brakes and tyres sit at the origin (placed
        # at run time): the wheel openings are where the lower edge of the
        # body's sides rises well above the sill.
        V = np.array([v[:3] for v in nbody['verts']], float)
        side = V[np.abs(V[:, 1]) > 0.8 * np.abs(V[:, 1]).max()]
        bins = {}
        for x, _, z in side: bins.setdefault(int(np.floor(x / 0.05)), []).append(z)
        low = {b: min(zs) for b, zs in bins.items()}
        sill = float(np.percentile(list(low.values()), 10))
        liner = []
        for sign in (1, -1):  # the longest run of raised bins on each half (by the doors, handles and trim read high too)
            run, best = [], []
            for b in sorted(low, key=lambda b: sign * b):
                if sign * b < 0: continue
                if low[b] > sill + 0.25 and (not run or abs(b - run[-1]) == 1): run.append(b)
                else: run = [b] if low[b] > sill + 0.25 else []
                if len(run) > len(best): best = list(run)
            liner += [(b + 0.5) * 0.05 for b in best]
    if hubs and any(z > 0 for z in hubs) and any(z < 0 for z in hubs) and any(x > 0 for x in liner) and any(x < 0 for x in liner):
        hf = sum(z for z in hubs if z > 0) / sum(1 for z in hubs if z > 0)
        hr = sum(z for z in hubs if z < 0) / sum(1 for z in hubs if z < 0)
        af = (min(x for x in liner if x > 0) + max(x for x in liner if x > 0)) / 2
        ar = (min(x for x in liner if x < 0) + max(x for x in liner if x < 0)) / 2
        print('wheels: arches at %.3f, %.3f go to the hubs at %.3f, %.3f (between them x%.3f)' % (k * af + dz, k * ar + dz, hf, hr, (hf - hr) / (af - ar)))
    else:
        af = ar = None
    if af is not None and af != ar and not 0.85 < (hf - hr) / (af - ar) / k < 1.15:
        # (an arch read wrongly, a body spread over other parts or a door's trim taken for one: the Impala's 1.3 and -0.1
        # asked a stretch of x5; past 15% of the fit's scale it is not trusted, the length fit kept)
        print('wheels: the arches read (%.3f, %.3f) are not trusted (x%.3f against the fit\'s %.3f): not stretched' % (k * af + dz, k * ar + dz, (hf - hr) / (af - ar), k))
        af = ar = None
    if os.environ.get('NFSU_ARCHES'):  # (as the plan's "arches": the car's arch middles as the fit puts them, and the hubs')
        ARCHES_ = [float(x) for x in os.environ['NFSU_ARCHES'].split(',')]
        if len(ARCHES_) == 2 and hubs: ARCHES_ += [max(hubs), min(hubs)]
    else:
        ARCHES_ = ARCHES
    if ARCHES_:
        # The plan's arches (an Underground 2 add-on: no liners, and its sides' lower edge read badly by rule): its
        # own arch middles as the length fit puts them, and the template body's (over the hubs its physics has),
        # both read off the side's lower edge in the template's units. The user's of 5 Nov: the Neon's rear wheel
        # stood ahead of its arch, the Silvia's front behind it.
        cf, cr, hf, hr = ARCHES_
        af, ar = (cf - dz) / k, (cr - dz) / k
        print('wheels: the plan\'s arches at %.3f, %.3f go to the template\'s at %.3f, %.3f (between them x%.3f)' % (cf, cr, hf, hr, (hf - hr) / (af - ar)))

    def along(x):
        if af is None: return k * x + dz
        if x > af: return hf + k * (x - af)
        if x < ar: return hr + k * (x - ar)
        return hr + (x - ar) * (hf - hr) / (af - ar)

    def pos(v):
        x, y, z = -k * kx * v[1], k * v[2] + dy, along(v[0])
        return [max(-32768, min(32767, int(round(c * 4096)))) for c in (x, y, z)]

    def nrm(v):
        x, y, z = -v[4], v[5], v[3]
        if kx != 1:  # (a surface squeezed across: its normals lean further out)
            x /= kx
            n = (x * x + y * y + z * z) ** 0.5 / max(1.0, (v[3] ** 2 + v[4] ** 2 + v[5] ** 2) ** 0.5) or 1
            x, y, z = x / n, y / n, z / n
        return [max(-32767, min(32767, int(round(c * 32767)))) for c in (x, y, z)]  # (symmetric: the black insides negate them, and the Celica's normals, longer than 1, hit -32768)

    arches = []
    CARSKIN_HASH = bhash('CARSKIN')
    _shell = [v[:3] for key in ('BODY', 'ROOF', 'TRUNK') for lv in find(key)[:1] for v in lv['verts']]
    shell_mid = [sum(v[k] for v in _shell) / len(_shell) for k in range(3)]
    shell_mid[2] = min(v[2] for v in _shell) + 0.45 * (max(v[2] for v in _shell) - min(v[2] for v in _shell))
    rgbas = {}

    def rgba_of(th):
        if th not in rgbas: rgbas[th] = nfsu_rgba(textures[th])
        return rgbas[th]

    _stock = [lv for key in ('BODY', 'ROOF', 'TRUNK', 'HOOD', 'FRONT_BUMPER', 'REAR_BUMPER', 'SKIRT') for lv in find(key)[:1]]
    _panes = window_panes(_stock) if not mw else []  # Most Wanted's windows are parts of their own
    rims = np.concatenate([r for _, r in _panes]) if _panes else None  # the window holes' edges, NFSU metres

    mid_f = pos(shell_mid)  # the shell's middle, carbin units

    def build(sources, side=0, glass=None, inner=False):
        """Forza vertices and subparts from NFSU parts (lists of detail
        levels, finest first); side -1/+1 keeps the triangles on the car's
        left/right (Forza x < 0 / > 0) only. A subpart's id is its detail
        level, 1 the finest: numbered otherwise, most of them were never
        drawn up close. glass=False leaves the windows out, glass=True keeps
        only them (as Window). inner=True gives the panels a black inside
        (copies facing in): drawn from outside only, the far side of the
        body was missing through the windows, and the studio showed
        through the 240SX's empty hatch area. inner=2: the black inside only,
        the panels left facing as they are (the bumpers' intakes face in)."""
        verts, subs, same = [], [], {}
        for lod, p in [(i + 1, lv) for src in sources for i, lv in enumerate(src[:4])]:
            # A level the same as a finer one (an Underground 2 car's levels are copies of
            # its first): its triangles again on the same vertices. Copied, the Celica's
            # body took four times the vertices, past the 65536 a part holds.
            key = (len(p['verts']), hash(tuple(p['verts'])), hash(tuple(map(tuple, p['tris']))), tuple(p['groups']))
            if key in same:
                subs += [(lod, m, s) for l, m, s in subs if l == same[key]]
                continue
            same[key] = lod
            base = len(verts)
            for v in p['verts']:
                verts.append(tuple(pos(v) + nrm(v) + [0xFF, 0xFF, 0, 0] + list(WHITE_UV)))
            idx = [i for t in p['tris'] for i in t]
            for gi, g in enumerate(p['groups']):
                cnt, = struct.unpack_from('<I', g, 12)
                first, = struct.unpack_from('<I', g, 0x34)
                ti, si = struct.unpack_from('<II', g, 0x1C)
                th = p['textures'][ti] if ti < len(p['textures']) else 0
                sh = p['shaders'][si] if si < len(p['shaders']) else 0
                tris = []
                for j in range(first, first + cnt - 2, 3):
                    a, b, c = idx[j:j + 3]
                    if max(a, b, c) >= len(p['verts']): continue
                    if side:
                        cx = sum(-p['verts'][i][1] for i in (a, b, c))
                        if (cx < 0) != (side < 0): continue
                    va, vb, vc = (p['verts'][i] for i in (a, b, c))
                    if sh == 0x010CB64A and max(va[2], vb[2], vc[2]) < 0.15:
                        continue  # the arch liner's bottom: it hung below the body behind the front wheels
                    if min(va[2], vb[2], vc[2]) < floor - 0.03:
                        continue  # below the body: the Neon's far detail level closed each wheel opening with a flat panel to 0.35 under the ground, over the wheels
                    e1 = [vb[k] - va[k] for k in range(3)]; e2 = [vc[k] - va[k] for k in range(3)]
                    g = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    if inner is True and sh != bhash('WINDSHIELD'):
                        # the outer skin faces away from the car's middle: its normals are wrong
                        # in places (19 roof triangles; on the hatch lid's trim, wedges by the
                        # spoiler faced in, and their black insides showed)
                        cen = [(va[k] + vb[k] + vc[k]) / 3 - shell_mid[k] for k in range(3)]
                        if sum(g[k] * cen[k] for k in range(3)) < 0: b, c = c, b
                    elif sum(g[k] * (va[3 + k] + vb[3 + k] + vc[3 + k]) for k in range(3)) < 0:
                        b, c = c, b  # wound against its normals: NFSU drew them anyway; here they were holes, and their black insides stood out
                    tris.append((base + a, base + b, base + c))  # the axis swap mirrors them and Forza's strips wind the other way: the two cancel
                if sh == 0x010CB64A and lod == 1:  # the inside of the wheel arches: what the cabin must stay above (fit_cabin)
                    arches.extend(tuple(pos(p['verts'][i - base]) for i in t) for t in tris)
                m = material_for(names.get(th, ''), sh)
                if m is None: continue  # (mw_material: left out)
                if mw and m in (HEADLIGHTS, TAILLIGHTS) and th in textures and th not in made_lamps and lamp_lens(names.get(th, ''), textures[th], dark=False):
                    continue  # (a lens sheet in a part of mixed materials, which auto_materials leaves be: the Brera's grey tint over its tail lights)
                if COVER_CELLS and tris and m not in (HEADLIGHTS, TAILLIGHTS) and not (th in made_lamps):
                    n_ = names.get(th, '').upper()
                    if not ('HEADLIG' in n_ or 'BRAKELIG' in n_):
                        tris = [t for t in tris if not all(near_lamp(p['verts'][i - base]) for i in t)]  # (NFSU_COVERS: see COVER_CELLS)
                if th in no_glass: continue  # (a shared lamp's glass cover: see made_lamps)
                if th in made_lamps and m != WINDOWS:  # (the reflector, Chrome by its shader, lit as the lamp; the black housing stays)
                    if mw and tris and str(textures[th].get('name', '')).endswith('(made)'):  # (a Most Wanted car: the picture for its end of the car, whichever shared sheet it named; not when the role is the car's own sheet, which its coordinates were made on: the RS5's rear lamps are on its HEADLIGHT sheet, and drawn from the brake sheet came out dark, 6 Nov)
                        fwd = np.mean([p['verts'][i - base][0] for t in tris for i in t]) > 0
                        th = bhash('HEADLIGHT_LEFT' if fwd else 'BRAKELIGHT_LEFT')
                    m = made_lamps[th]
                if mw and tris and m in (HEADLIGHTS, TAILLIGHTS):
                    # (a lamp's material by its end of the car: the RS5's rear lamps are on its HEADLIGHT sheet, drawn
                    # as headlights at the back)
                    m = HEADLIGHTS if np.mean([p['verts'][i - base][0] for t in tris for i in t]) > 0 else TAILLIGHTS
                role = next((r for r in ('HEADLIGHT', 'BRAKELIGHT') if '_KIT00_' + r in p['name']), None)
                if role and sh in LAMP_GLASS: continue  # (a lamp's see-through cover)
                if mw and tris and th in textures and textures[th].get('data') and th not in made_lamps and (role or 'LIGHT' in names.get(th, '').upper()):
                    # A Most Wanted lamp's lens on a shared sheet (the RS5's headlight part: its MISC sheet's clear
                    # texels, a shell over the lamp drawn opaque dark, 6 Nov): what its corners take mostly clear
                    img = rgba_of(th)
                    hh, ww = img.shape[:2]
                    vs = {i for t in tris for i in t}
                    al = [img[min(hh - 1, int(min(max(p['verts'][i - base][8], 0), 1) * hh)), min(ww - 1, int(min(max(p['verts'][i - base][7], 0), 1) * ww)), 3] for i in vs]
                    if al and np.mean(np.array(al) < 128) > 0.6: continue
                if role in made_pic and m in (HEADLIGHTS, TAILLIGHTS):  # a lit face: the lamp's own colour, its made picture
                    m, th = (HEADLIGHTS, made_pic[role]) if role == 'HEADLIGHT' else (TAILLIGHTS, made_pic[role])
                if (UV32 or th in ready) and m == BADGE:
                    # An Underground 2 car's decals (door handles, side markers, badges) are see-through
                    # overlays on the paint; Badge drew their clear texels black, as black boxes. As
                    # Body, on their sheet made ready for it (paint_ready), the paint shows through.
                    m = BODY
                if sh == 0x12C9453C and p['name'].startswith(prefix + '_KIT00_TRUNK'):
                    # On the hatch lid this group is the black border round the rear glass and
                    # the tail panel. The border's bottom edge widens into wedges by the
                    # spoiler that stood out as black; that edge (on the lid's top, behind the
                    # glass: NFSU x < -1.4 m, above 0.7 m) is painted, on its own copies of the
                    # corners (shared, paint and black speckled the glass's edge).
                    far = [t for t in tris if np.mean([p['verts'][i - base][0] for i in t]) < -1.4
                           and np.mean([p['verts'][i - base][2] for i in t]) > 0.7]
                    if far:
                        copy = {}
                        for t in far:
                            for i in t:
                                if i not in copy: copy[i] = len(verts); verts.append(verts[i])
                        subs.append((lod, BODY, strip([tuple(copy[i] for i in t) for t in far])))
                        tris = [t for t in tris if t not in far]
                is_glass = m in (WINDOW, BLACKGLASS)
                if glass is None and is_glass:
                    # Windows become black paint for now (WINDOWS, see
                    # dark_uv): as glass, or as black trim, the game drew
                    # them fully clear, and the S13's roof is mostly this
                    # shader.
                    m = WINDOWS
                if glass is not None and is_glass != glass: continue
                if glass:  # windows drawn from both sides: NFSU's face either way
                    m = WINDOW
                    # (no window has a side over 1.8 m: the Countach's glass held spikes to 4 m, from bad indices)
                    tris = [t for t in tris if max(sum((p['verts'][t[a] - base][c] - p['verts'][t[b] - base][c]) ** 2 for c in range(3)) for a, b in ((0, 1), (1, 2), (0, 2))) < 1.8 ** 2]
                    outer = two_sided(p, tris, base)  # (glass modelled with its inside already, the Countach's: its outer layer only,
                    if outer is not None: tris = [t for t in outer if not sliver(p, t, base)]  # doubled as the rest; all four layers
                    # fought as crumpled shards, and its slivers, a metre long and millimetres high, crossed the windows as streaks)
                    tris = tris + [(x, z, y) for x, y, z in tris]
                if tris and m == TAILLIGHTS and th in textures:
                    # Lamp triangles on black texels (the S13's centre garnish between
                    # the lamps) are black trim: Forza's lamp material lit them pale.
                    img = rgba_of(th)
                    def dark(t):
                        h, w = img.shape[:2]
                        return all(img[min(h - 1, int(min(max(p['verts'][i - base][8], 0), 1) * h)),
                                       min(w - 1, int(min(max(p['verts'][i - base][7], 0), 1) * w)), :3].max() < 24 for i in t)
                    trim = [t for t in tris if dark(t)]
                    if len(trim) > 0.9 * len(tris): trim = list(tris)  # (a dark sheet all but a few: all trim; the Eclipse's carbon left lit flecks)
                    if trim:
                        tris = [t for t in tris if t not in set(trim)]
                        # (on their own copies of the corners they share with the lamp: a vertex takes the material of
                        # the first piece naming it, and the lamps' edges drew the black texel, the Brera's and Evora's
                        # tail lights dark smears, 6 Nov)
                        lit = {i for t in tris for i in t}
                        copy = {}
                        for t in trim:
                            for i in t:
                                if i in lit and i not in copy: copy[i] = len(verts); verts.append(verts[i])
                        subs.append((lod, WINDOWS, strip([tuple(copy.get(i, i) for i in t) for t in trim])))
                if tris and th in atlas and not (m == WINDOW and th == bhash('REAR_DEFROSTER')):  # its texture is in the livery atlas: its own coordinates, moved there (not the rear glass's heater lines: stretched, two orange streaks over the LF-A's)
                    u0, v0, u1, v1 = atlas[th]
                    one = BADGE_UV if m == BADGE or mw or UV32 else 65536  # (see BADGE_UV and ATLAS_UV)
                    for i in {i for t in tris for i in t}:
                        nv = p['verts'][i - base]
                        u = min(max(nv[7], 0.0), 1.0); v = min(max(nv[8], 0.0), 1.0)
                        verts[i] = verts[i][:10] + (int((u0 + u * (u1 - u0)) * one), int((v0 + v * (v1 - v0)) * one), 'atlas')
                if tris and m == BODY and bands and gi < len(p['materials']) and p['materials'][gi] in VINYL_CANVAS:
                    # Most Wanted's own vinyl layout, its bands packed into the atlas (see bake_vinyl)
                    for i in {i for t in tris for i in t}:
                        nv = p['verts'][i - base]
                        u = min(max(nv[7], 0.0), 1.0); v = min(max(nv[8], 0.0), 1.0)
                        if ISLANDS is not None:  # a livery sheet's island (canvas_islands): the nearest within 4 texels
                            y_, x_ = min(CANVAS_SIZE - 1, int(v * CANVAS_SIZE)), min(CANVAS_SIZE - 1, int(u * CANVAS_SIZE))
                            win = ISLANDS[max(0, y_ - 4):y_ + 5, max(0, x_ - 4):x_ + 5]
                            kb = int(ISLANDS[y_, x_]) if ISLANDS[y_, x_] >= 0 else int(win.max()) if (win >= 0).any() else 0
                        else:
                            kb = next((j for j, b in enumerate(bands) if b[0] <= v * CANVAS_SIZE <= b[1]), 0)  # (not k: the fit's scale, which pos() reads)
                        verts[i] = verts[i][:10] + canvas_uv(atlas[(CANVAS, kb)], bands[kb], u, v) + ('atlas',)
                if tris:
                    subs.append((lod, m, strip(tris)))
                if tris and inner and m != WINDOW:
                    flip = {}
                    for i in sorted({i for t in tris for i in t}):
                        v = verts[i]
                        flip[i] = len(verts)
                        # set in along the normal: on the panel itself it fought it in
                        # the shadow map and speckled the paint black
                        # towards the car's middle (along the vertex normal, where a normal
                        # pointed out of the panel the black copy ended up outside it, as a
                        # black wedge at the hatch's corners)
                        d = [v[k] - mid_f[k] for k in range(3)]
                        if inner == 2:  # (the bumpers: straight through the panel, the normal's way out: towards the middle the copy
                            n = v[3:6]  # slid along the arches' lips and left their edges bare, the pale line still there)
                            d = [c if sum(x * y for x, y in zip(n, d)) > 0 else -c for c in n]
                        l = max(1e-6, sum(x * x for x in d) ** 0.5)
                        verts.append(tuple(int(round(v[k] - d[k] / l * INSET)) for k in range(3))
                                     + tuple(-c for c in v[3:6]) + tuple(v[6:12]))
                    subs.append((lod, WINDOWS, strip([(flip[a], flip[c], flip[b]) for a, b, c in tris])))
        # drop vertices no triangle uses, so mirrored halves stay small
        used = sorted({i for _, _, s in subs for i in s})
        remap = {o: n for n, o in enumerate(used)}
        # One subpart per detail level and material, as Forza's own: with
        # several of a material in a level, only some of them were drawn.
        merged = {}
        for lod, m, s in subs:
            t = [remap[i] for i in s]
            if (lod, m) in merged:
                acc = merged[(lod, m)]
                acc += [acc[-1], t[0]]
                if len(acc) % 2: acc.append(t[0])
                acc += t
            else:
                merged[(lod, m)] = t
        return [verts[i] for i in used], sorted((lod, m, s) for (lod, m), s in merged.items())

    def put(part, verts, subs):
        assert len(verts) < 65536, part['name']
        # Texture coordinates and shading from the template part's nearest
        # vertex: one fixed white spot drew the paint black (the atlas the
        # game samples there is not the plain livery), while the template's
        # own coordinates land on paint, lights and trim where they should.
        # Matched within the same material where the template has it (paint
        # to paint, lights to lights): matched to any vertex, paint picked up
        # black trim in patches and Civic shapes on the hood.
        old = part['verts']
        if old:
            import numpy as np
            old_mat = {}
            for sp in part['subparts']:
                if sp['id'] == 1:
                    for i in sp['indices']: old_mat.setdefault(i, sp['material'])
            new_mat = {}
            for lod, m, s in subs:
                for i in s: new_mat.setdefault(i, m)
            P = np.array([v[:3] for v in old], np.float32)
            Pm = np.array([old_mat.get(i, -1) for i in range(len(old))])
            Q = np.array([v[:3] for v in verts], np.float32)
            Qm = np.array([new_mat.get(i, -1) for i in range(len(verts))])
            near = np.empty(len(Q), np.int64)
            for m in set(Qm.tolist()):
                qi = np.nonzero(Qm == m)[0]
                pi = np.nonzero(Pm == m)[0]
                if len(pi) == 0: pi = np.nonzero(Pm == BODY)[0] if m in (BLACKGLASS, WINDOW) and (Pm == BODY).any() else np.arange(len(P))
                for a in range(0, len(qi), 512):
                    q = qi[a:a + 512]
                    d2 = ((Q[q, None, :] - P[None, pi, :]) ** 2).sum(-1)
                    near[q] = pi[d2.argmin(1)]
            def tex(i, j):
                if Qm[i] == WINDOWS: return tuple(old[j][6:10]) + dark_read
                if Qm[i] == WINDOW and clear_livery:  # a race car's glass is drawn from its livery (a banner), cleared and then free room: a lamp packed there showed on the side windows
                    return tuple(old[j][6:10]) + paint
                if Qm[i] == BODY and mw:
                    # Shading as the Civic's paint has it (fitted: brighter facing up and
                    # higher on the car); at full shading everywhere the Cobalt glowed
                    # against the other cars at dusk
                    # The race's vertex program: diffuse is the light times the first
                    # byte, how much of the environment shows (diffuse alpha) the second.
                    # Fitted alone they gave the Cobalt 0.78 of the Civic's diffuse and
                    # 0.67 of its reflection (flat, the user saw); scaled to match (run
                    # through the program on both cars' paint vertices).
                    ny, h = verts[i][4] / 32767, verts[i][1] / 4096 / max(ty)
                    return (int(min(255, max(0, 1.28 * (102.4 + 74.9 * ny + 74.4 * h)))),
                            int(min(255, max(0, 1.48 * (89.4 + 76.5 * ny + 79.6 * h)))), 0, 0) + (
                        verts[i][10:12] if verts[i][12:13] == ('atlas',) else paint)  # (on the vinyl canvas: see bake_vinyl)
                if Qm[i] == BODY: return (255, 255, 0, 0) + paint  # one known paint texel, full shading: copied, panels near the template's windows came out black or clear
                if mw and verts[i][12:13] != ('atlas',) and Qm[i] in (CHROME, PLASTIC):  # untextured trim: the template's nearest texel was often its red lamps (a grille in red stripes)
                    return tuple(old[j][6:10]) + (paint if Qm[i] == CHROME else dark_read)
                if verts[i][12:13] == ('atlas',): return tuple(old[j][6:10]) + verts[i][10:12]  # its own texture, packed into the atlas
                return tuple(old[j][6:12])
            verts = [v[:6] + tex(i, j) for i, (v, j) in enumerate(zip(verts, near))]
        part['verts'] = [v[:12] for v in verts]
        # A part that had a damage shape keeps one, the same as the car
        # undamaged (so no dents yet): left empty, the game drew those parts
        # black and partly see-through, as if it lights them from it.
        if struct.unpack_from('<I', part['Damage'][1])[0]:
            part['Damage'] = (part['Damage'][0], struct.pack('<I', len(verts)) + b''.join(struct.pack('<6h', *v[:6]) for v in verts))
        tmpl = part['subparts'][0]
        part['subparts'] = [{'version': tmpl['version'], 'id': lod, 'material': BODY if m == WINDOWS else m, 'prim': 6,
                             'extra': bytes(16), 'indices': s, 'tail': b''} for lod, m, s in subs]

    def roof(verts, cell=0.15):
        """The highest body vertex over each cell of the ground plan, in
        carbin units (x, z cells of `cell`)."""
        top = {}
        for v in verts:
            c = (int(v[0] / 4096 // cell), int(v[2] / 4096 // cell))
            top[c] = max(top.get(c, -1e9), v[1] / 4096)
        return top, cell

    def height(top, x, z):
        hm, cell = top
        cx, cz = int(x // cell), int(z // cell)
        for r in range(8):  # the nearest cell with a vertex, rings outwards
            hs = [hm[(cx + i, cz + j)] for i in range(-r, r + 1) for j in range(-r, r + 1)
                  if max(abs(i), abs(j)) == r and (cx + i, cz + j) in hm]
            if hs: return max(hs)
        return None

    def sides(verts, cell=0.15):
        """The widest shell vertex (|x|) in each cell of the car's side view
        (y, z cells of `cell`), in carbin units."""
        top = {}
        for v in verts:
            c = (int(v[1] / 4096 // cell), int(v[2] / 4096 // cell))
            top[c] = max(top.get(c, -1e9), abs(v[0]) / 4096)
        return top, cell

    def shell_parts():
        """The outside of the car the cabin must fit in: the body, hood and
        trunk, and the glass that is drawn."""
        for p in car['parts']:
            n = p['name']
            body = (n.startswith(('body', 'hood', 'trunk')) or mw and n.startswith('bumperFa')) and n.endswith('_LOD1')  # (bumperFa: a Most Wanted car's stock body)
            glass = n.startswith('glass') and 'HL_' not in n and any(sp['indices'] != [0, 0, 0] for sp in p['subparts'])
            if body or glass: yield p

    def shell():
        return [v for p in shell_parts() for v in p['verts']]

    def plan_heights(tris, cell=0.03):
        """Every height of these triangles (carbin units) over each cell of
        the ground plan, sampled at the cell's middle."""
        out = {}
        for A, B, C in tris:
            A, B, C = ([c / 4096 for c in q] for q in (A, B, C))
            d = (B[2] - C[2]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[2] - C[2])
            if abs(d) < 1e-12: continue
            xs, zs = (A[0], B[0], C[0]), (A[2], B[2], C[2])
            for cx in range(int(min(xs) // cell), int(max(xs) // cell) + 1):
                for cz in range(int(min(zs) // cell), int(max(zs) // cell) + 1):
                    x, z = (cx + 0.5) * cell, (cz + 0.5) * cell
                    l1 = ((B[2] - C[2]) * (x - C[0]) + (C[0] - B[0]) * (z - C[2])) / d
                    l2 = ((C[2] - A[2]) * (x - C[0]) + (A[0] - C[0]) * (z - C[2])) / d
                    if min(l1, l2, 1 - l1 - l2) >= 0:
                        out.setdefault((cx, cz), []).append(l1 * A[1] + l2 * B[1] + (1 - l1 - l2) * C[1])
        return out, cell

    def cover():
        """The shell's finest triangles' heights over the ground plan: what
        is above a point of the cabin."""
        tris = []
        for p in shell_parts():
            for sp in p['subparts']:
                if sp['id'] != 1: continue
                ix = sp['indices']
                tris += [tuple(p['verts'][i][:3] for i in ix[k:k + 3]) for k in range(len(ix) - 2) if len(set(ix[k:k + 3])) == 3]
        return plan_heights(tris)

    def fit_cabin(part, old, new, floor, margin=0.03):
        """Squash a template part inside the cabin (the interior, the cage)
        into the new shell: each vertex keeps its share of the height between
        the floor and the roof (or glass) above it, then of the width at
        that height. Triangles still outside after that are dropped: with
        nothing of the shell over them, wider than it, or down in a wheel arch (pulling their
        corners in instead stretched them across the glass). The Civic's
        black headliner stood out of the 240SX's lower roof and covered it,
        and its wider, longer cabin poked through the S13's pillars, roof
        edge, rear glass and rear arches."""
        (old_roof, old_side), (new_roof, new_side, above, arch_top) = old, new
        def move(v):
            x, y, z = v[0] / 4096, v[1] / 4096, v[2] / 4096
            if y <= floor: return v
            t, n = height(old_roof, x, z), height(new_roof, x, z)
            ny = floor + (y - floor) * (n - floor) / (t - floor) if t is not None and n is not None and n < t else y
            wo, wn = height(old_side, y, z), height(new_side, ny, z)
            nx = x * wn / wo if wo and wn is not None and 0 < wn < wo else x
            return (int(round(nx * 4096)), int(round(ny * 4096))) + tuple(v[2:])
        def outside(v):
            x, y, z = v[0] / 4096, v[1] / 4096, v[2] / 4096
            # nothing of the shell over it, nor within 6 cm (between the roof's edge and
            # the steep side glass, plan view has gaps over points well inside)
            cx, cz = int(x // above[1]), int(z // above[1])
            hs = [h for i in range(-2, 3) for j in range(-2, 3) for h in above[0].get((cx + i, cz + j), ())]
            if hs and not any(h > y + margin for h in hs): return True
            a = arch_top[0].get((int(x // arch_top[1]), int(z // arch_top[1])))  # the arch liner over it, if any
            return a is not None and y < max(a) + margin
        part['verts'] = [move(v) for v in part['verts']]
        for sp in part['subparts']:
            if sp['material'] in (TAILLIGHTS, HEADLIGHTS):  # the Civic's third brake light, on its parcel shelf: a grey slab under the hatch glass
                sp['indices'] = [0, 0, 0]
        def tuck(v):
            # a corner through the glass or roof, brought down just under the shell
            # above it (the triangles it belongs to stay, so nothing tears)
            x, y, z = v[0] / 4096, v[1] / 4096, v[2] / 4096
            # only the roof, glass and panels well up off the floor: a Most Wanted car's stock body
            # (bumperFa) has its underside too, and tucked under that the dashboard and steering wheel lay flat on the floor
            hs = [h for h in above[0].get((int(x // above[1]), int(z // above[1])), ()) if h > floor + 0.3]
            if hs and y > min(hs) - margin:
                return (v[0], int(round((min(hs) - margin) * 4096))) + tuple(v[2:])
            return v
        part['verts'] = [tuck(v) for v in part['verts']]
        # darker: the Civic's cabin squashed under a lower roof has flattened panels
        # that caught the light through the glass as pale patches and brown bits
        part['verts'] = [tuple(v[:6]) + (int(v[6] * CABIN_SHADE), int(v[7] * CABIN_SHADE)) + tuple(v[8:]) for v in part['verts']]
        out = [outside(v) for v in part['verts']]
        for sp in part['subparts']:
            ix, tris = sp['indices'], []
            for k in range(len(ix) - 2):
                a, b, c = (ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
                # only what is wholly outside goes: dropping any triangle with a corner
                # out tore the dashboard and seats apart
                if len({a, b, c}) < 3 or (out[a] and out[b] and out[c]): continue
                tris.append((a, b, c))
            sp['indices'] = strip(tris) if tris else [0, 0, 0]
        cnt = struct.unpack_from('<I', part['Damage'][1])[0]
        if cnt == len(part['verts']):  # its damage shape too
            dv = [move(struct.unpack_from('<6h', part['Damage'][1], 4 + 12 * i)) for i in range(cnt)]
            part['Damage'] = (part['Damage'][0], struct.pack('<I', cnt) + b''.join(struct.pack('<6h', *v) for v in dv) + part['Damage'][1][4 + 12 * cnt:])

    def fit_glass():
        """The NFSU car's window holes filled (window_panes), each pane put
        in the template glass part nearest it, with that part's texture
        coordinates and shading (the glass texture is not the livery), from
        both sides. Template glass parts with no pane stay hidden."""
        import numpy as np
        glass = [p for p in car['parts'] if p['name'].startswith('glass') and 'HL_' not in p['name'] and p['verts']]
        centre = {p['name']: np.mean([v[:3] for v in p['verts']], 0) for p in glass}
        stock = [lv for key in ('BODY', 'ROOF', 'TRUNK', 'HOOD', 'FRONT_BUMPER', 'REAR_BUMPER', 'SKIRT') for lv in find(key)[:1]]
        mid_car = np.mean([pos(v) for p in stock for v in p['verts']], 0)
        got = {}
        for mid, ring in window_panes(stock):
            pm = np.array(pos(mid))
            name = min(centre, key=lambda n: np.linalg.norm(centre[n] - pm))
            got.setdefault(name, []).append((mid, ring))
        for p in glass:
            if p['name'] not in got: continue
            old = np.array([v[:3] for v in p['verts']], np.float32)
            verts, tris = [], []
            for mid, ring in got[p['name']]:
                R = np.array([pos(q) for q in ring], float)
                c0 = R.mean(0)
                # outward: the normal of the pane's best plane, away from the car's middle
                e = np.linalg.svd(R - c0)[2]
                n = e[2] if np.dot(e[2], c0 - mid_car) >= 0 else -e[2]
                # The glass is curved (the S13's hatch strongly): a fan from the rim's
                # middle sagged under it and the cage showed through. Its middle is lifted
                # onto a quadric fitted to the rim's heights over the pane's plane.
                uv = (R - c0) @ e[:2].T
                hgt = (R - c0) @ n
                A = np.c_[np.ones(len(uv)), uv, uv[:, :1] ** 2, uv[:, :1] * uv[:, 1:], uv[:, 1:] ** 2]
                co = np.linalg.lstsq(A, hgt, rcond=None)[0]
                def surf(u, v):
                    return c0 + u * e[0] + v * e[1] + n * (co[0] + co[1] * u + co[2] * v + co[3] * u * u + co[4] * u * v + co[5] * v * v)
                k = len(ring)
                # the middle on the fitted curve, the rings on straight lines from it to
                # the rim: on the curve itself they bulged out past the C pillars near the
                # rim and showed there as pale slivers
                mid = surf(0.0, 0.0)
                rings = [[mid]] + [[mid + t * (R[i] - mid) for i in range(k)] for t in (1 / 3, 2 / 3)] + [list(R)]
                nn = [int(round(c * 32767)) for c in n / np.linalg.norm(n)]
                base = len(verts)
                for q in [q for r in rings for q in r]:
                    j = int(((old - q) ** 2).sum(1).argmin())
                    verts.append(tuple(int(round(c)) for c in q) + tuple(nn) + tuple(p['verts'][j][6:12]))
                for i in range(k):  # the fan round the middle, then the bands out to the rim
                    a, b = base + 1 + i, base + 1 + (i + 1) % k
                    tris += [(base, a, b), (base, b, a)]
                for r in range(2):
                    s0, s1 = base + 1 + r * k, base + 1 + (r + 1) * k
                    for i in range(k):
                        i1 = (i + 1) % k
                        for t in ((s0 + i, s1 + i, s1 + i1), (s0 + i, s1 + i1, s0 + i1)):
                            tris += [t, (t[0], t[2], t[1])]
            ids = sorted({sp['id'] for sp in p['subparts']})
            tmpl = p['subparts'][0]
            p['verts'] = verts
            p['subparts'] = [{'version': tmpl['version'], 'id': i, 'material': WINDOW, 'prim': 6, 'extra': bytes(16),
                              'indices': strip(tris), 'tail': b''} for i in ids]
            done.append(p['name'] + '(%d panes)' % len(got[p['name']]))

    old_shell = shell()
    old_fit = roof(old_shell), sides(old_shell)
    floor = min(ty)

    def on_trunk(levels):
        """An Underground 2 spoiler on the trunk lid: its parts stand at the origin (the game puts them on at run
        time), so as they were they sat inside the car, unseen (the Silvia's own, the Neon's shop ones, 5 Nov). Its
        back to the lid's back edge, its foot on the lid's top there. Spoilers already in place are left."""
        trunk = find('TRUNK')
        if not levels or not trunk: return levels
        V0 = np.array([v[:3] for v in levels[0]['verts']])
        if not (abs((V0[:, 0].min() + V0[:, 0].max()) / 2) < 0.6 and V0[:, 2].min() > -0.2 and V0[:, 2].max() < 0.7):
            return levels
        T = np.array([v[:3] for v in trunk[0]['verts']])
        back, depth = T[:, 0].min(), np.ptp(V0[:, 0])
        near = T[(T[:, 0] < back + max(depth, 0.15)) & (np.abs(T[:, 1]) < 0.35)]
        top = near[:, 2].max() if len(near) else T[:, 2].max()
        dx, dz = back + 0.02 - V0[:, 0].min(), top - 0.01 - V0[:, 2].min()
        out = []
        for lv in levels:
            q = dict(lv)
            q['verts'] = [(v[0] + dx, v[1], v[2] + dz) + tuple(v[3:]) for v in lv['verts']]
            out.append(q)
        print('spoiler on the trunk: %+.2f forward, %+.2f up' % (dx, dz))
        return out

    plan = {
        # (the roof where the car has one of its own: the Celica GT-Four has none, and without it
        # the slot was skipped and the template's body stayed under the new bumpers)
        'body': ([find('BODY')] + [r for r in [find('ROOF')] if r], 0, None, True), 'hood': ([find('HOOD')], 0), 'trunk': ([find('TRUNK')], 0, None, True),
        # (the bumpers' black insides without the panels turned: from behind, at the wheel arches'
        # ends, the Neon's bumper skins showed their backs lit as their fronts, a pale line)
        'bumperF': ([find('FRONT_BUMPER')], 0, None, 2), 'bumperR': ([find('REAR_BUMPER')], 0, None, 2),
        'skirtL': ([find('SKIRT')], -1), 'skirtR': ([find('SKIRT')], 1),
        'headlightL': ([find('HEADLIGHT')], -1), 'headlightR': ([find('HEADLIGHT')], 1),
        'taillightL': ([find('BRAKELIGHT')], -1), 'taillightR': ([find('BRAKELIGHT')], 1),
        'mirrorL': ([find('LEFT_SIDE_MIRRO')], 0), 'mirrorR': ([find('RIGHT_SIDE_MIRR')], 0),
        # every wing the template offers becomes the NFSU car's own spoiler: left
        # as they were, the Civic's floated behind the hatch where its trunk was
        # (faced away from the car's middle with a black underside: wound as they came, the Celica GT-Four's wing drew
        # its two end plates and no top in the game, floating, 6 Nov)
        'wing': ([on_trunk(find('SPOILER')) if UV32 else find('SPOILER')], 0, None, True),
    }
    if not mw and find('BRAKELIGHT') and not any(p['name'].startswith('taillight') for p in car['parts']):
        # A template with its lamps in its body (the S15): the tail lights go in the body,
        # matched to its lamp texels; with no slot of their own they were left out, as holes
        plan['body'] = (plan['body'][0] + [find('BRAKELIGHT')],) + plan['body'][1:]
    if not mw and find('HEADLIGHT') and not any(p['name'].startswith('headlight') for p in car['parts']):
        # The same for the headlights (the SRT-4 and Celica GTS have no headlight part, their lamps painted on):
        # into the front bumper, or the body without one. Left out, the Neon's and Celica GT-Four's lamps were
        # their empty housings, dark ovals.
        to = 'bumperF' if any(p['name'].startswith('bumperF') for p in car['parts']) else 'body'
        plan[to] = (plan[to][0] + [find('HEADLIGHT')],) + plan[to][1:]
    if mw:
        def find(suffix, _find=find):  # exactly that part's levels: LEFT_HEADLIGHT also began LEFT_HEADLIGHT_GLASS, mixed in as its levels
            return [p for p in _find(suffix) if re.fullmatch(re.escape(prefix + '_KIT00_' + suffix) + '_[A-D]', p['name'])]
        def kit(n, suffix):  # body kit n's levels (KIT01-05 hold whole bodies, as KIT00)
            return sorted([p for p in nparts if re.fullmatch(re.escape(prefix + '_KIT%02d_' % n + suffix) + '_[A-D]', p['name'])],
                          key=lambda p: -len(p['verts']))

        def rear_width():
            """The stock body's width across the tail where the car's own
            spoiler stands, a little in from its sides: how wide the shared
            spoilers are made (Most Wanted spans them across the car's
            back; as wide as the Gallardo's narrow lip they were stubs)."""
            S = np.array([v[:3] for v in find('SPOILER')[0]['verts']])
            B_ = np.array([v[:3] for p in find('BODY')[:1] for v in p['verts']])
            fx, fz = (S[:, 0].min() + S[:, 0].max()) / 2, S[:, 2].min()
            near = B_[(np.abs(B_[:, 0] - fx) < 0.12) & (B_[:, 2] > fz - 0.2) & (B_[:, 2] < fz + 0.05)]
            return max(np.ptp(S[:, 1]), 0.94 * np.ptp(near[:, 1]) if len(near) else 0)

        def style(name, levels):
            """Parts of another file placed on this car: Most Wanted's shared
            spoilers (CARS/SPOILER) stand at the origin, their foot at z 0;
            stood where the car's own spoiler is, as wide as the tail there."""
            own = find('SPOILER')[0]
            S = np.array([v[:3] for v in own['verts']])
            foot = S[S[:, 2] < S[:, 2].min() + 0.03]
            width = rear_width()
            out = []
            for p in levels:
                V = np.array([v[:3] for v in p['verts']])
                sy = width / max(np.ptp(V[:, 1]), 1e-6)
                dx = foot[:, 0].mean() - (V[:, 0].min() + V[:, 0].max()) / 2
                q = dict(p)
                q['verts'] = [(v[0] + dx, v[1] * sy, v[2] + S[:, 2].min()) + tuple(v[3:]) for v in p['verts']]
                out.append(q)
            return out
        spoilers = {}
        shared =os.path.join(os.path.dirname(os.path.normpath(nfsu_dir)), 'SPOILER', 'GEOMETRY.BIN')
        if os.path.exists(shared):
            for p in nfsu.read(shared):
                spoilers.setdefault(re.sub(r'_[A-D]$', '', p['name']), []).append(p)
        def spoiler(n):
            got = sorted(spoilers.get('SPOILER_STYLE%02d' % n, []), key=lambda p: -len(p['verts']))
            return style('SPOILER_STYLE%02d' % n, got) if got else []
        def hood(n):
            return [p for p in nparts if p['name'].startswith('%s_STYLE%02d_HOOD_' % (prefix, n))]
        hoods = list(zip(HOOD_SLOTS, [n for n in MW_HOODS if hood(n)]))
        wings = list(zip(WING_SLOTS, [n for n in MW_SPOILERS if spoilers.get('SPOILER_STYLE%02d' % n)])) if find('SPOILER') else []  # (stood where the car's own is)
        add_slots(car, ['hood' + s for s, _ in hoods] + [s for s, _ in wings])
        for _, n in wings:
            for lv in spoilers.get('SPOILER_STYLE%02d' % n, []):
                for name in lv['materials']: SHADERS.setdefault(bhash(name), mw_material(name))

        # The shop (upgrades.xml, beside the output, for addcar.py --upgrades):
        # the body kits are whole bodies, from the bumpers to the wheel arches
        # and sills, so the always-drawn body is only what all kits share (the
        # roof and pillars, BASE), and each front bumper is a whole kit's body
        # (stock, then KIT01-05; the extra kits with two levels and no black
        # insides, to keep the car small). The rear bumpers and skirts are
        # left with their stock choice only: the front bumper brings them.
        # Two of the car's own hoods and four of the shared spoilers; the
        # car's own spoiler is the stock wing.
        # The windows go into the template's glass parts by name (the more
        # specific names first: a part takes the first key it starts with),
        # each light into the template's light of that side.
        plan = {
            'body': ([base], 0, False, True),  # no glass: the windows' own parts have it
            'bumperFa': ([find('BODY')], 0, False, True),
            **{'bumperF' + 'bcdef'[n - 1]: ([kit(n, 'BODY')[:2] + find('BODY')[2:4]], 0, False, False) for n in range(1, 6)},  # far off, the stock body's levels
            'hooda': ([find('HOOD')], 0),
            **{'hood' + slot: ([hood(n)], 0) for slot, n in hoods},
            'wingb': ([find('SPOILER')], 0),
            **{slot: ([spoiler(n)], 0) for slot, n in wings},
            'glassLF': ([find('FRONT_LEFT_WINDOW')], 0, True), 'glassRF': ([find('FRONT_RIGHT_WINDOW')], 0, True),
            'glassLR': ([find('REAR_LEFT_WINDOW')], 0, True), 'glassRR': ([find('REAR_RIGHT_WINDOW')], 0, True),
            'glassF': ([find('FRONT_WINDOW')], 0, True), 'glassR': ([find('REAR_WINDOW')], 0, True),
            # (the cover only where there is one: the SC63 has none, and its lamps were hidden)
            'headlightL': ([find('LEFT_HEADLIGHT')] + [g for g in [find('LEFT_HEADLIGHT_GLASS')] if g], 0),
            'headlightR': ([find('RIGHT_HEADLIGHT')] + [g for g in [find('RIGHT_HEADLIGHT_GLASS')] if g], 0),
            'taillightL': ([find('LEFT_BRAKELIGHT')], 0), 'taillightR': ([find('RIGHT_BRAKELIGHT')], 0),
            'mirrorL': ([find('LEFT_SIDE_MIRROR')], 0), 'mirrorR': ([find('RIGHT_SIDE_MIRROR')], 0),
            **({'interior': ([find('INTERIOR')], 0)} if OWN_INTERIOR else {}),
        }
        write_upgrades(os.path.join(os.path.dirname(os.path.abspath(out_path)), 'upgrades.xml'),
                       [n for n in range(1, 6) if kit(n, 'BODY') and (KITS is None or n in KITS)], hoods, wings, stock_wing)
        # Another template than the Civic (a race car: bumperF, hood, wing, no
        # tail lights of its own): its slots by its names, the tail lights in its
        # rear bumper
        names_ = {p['name'] for p in car['parts']}
        for mine, theirs in (('bumperFa', 'bumperF'), ('hooda', 'hood'), ('wingb', 'wing')):
            if mine + '_LOD1' not in names_ and theirs + '_LOD1' in names_: plan[theirs + '_LOD1'] = plan.pop(mine)
        if not any(n.startswith('taillight') for n in names_) and 'bumperR_LOD1' in names_:
            plan['bumperR_LOD1'] = ([find('LEFT_BRAKELIGHT'), find('RIGHT_BRAKELIGHT')], 0)
        elif not any(n.startswith('taillight') for n in names_):  # (no tail lights and no plain rear bumper either, the
            # Eclipse GTS's bumperRa-f: the lamps in the always-drawn body; left out, its tail lights were holes, 6 Nov)
            plan['body'] = (plan['body'][0] + [lv for lv in (find('LEFT_BRAKELIGHT'), find('RIGHT_BRAKELIGHT')) if lv],) + plan['body'][1:]
        if not any(n.startswith('headlight') for n in names_):  # (the headlights too: the Eclipse GTS has no headlight parts)
            plan['body'] = (plan['body'][0] + [lv for lv in (find('LEFT_HEADLIGHT'), find('RIGHT_HEADLIGHT')) if lv],) + plan['body'][1:]
    if SHOP and not mw:
        # The shop's other choices (cartoolkit.py's plan "shop": {slot: [part, side]}): an Underground 2 car's body
        # kits, hoods and spoilers in the template's slots that its lists already name (Bumper 1 -> bumperFb ...),
        # each slot by its own name ahead of the stock part's (a part takes the first key it starts with). The
        # user's, 5 Nov: "if the recent custom cars had any body kits/hoods/spoilers... add those. Choose a few".
        def shop_part(src):
            full = prefix + '_' + src
            hit = [p for p in nparts if p['name'] in {(full + s)[:27] for s in ('_A', '_B', '_C', '_D', '')}
                   and 'DAMAGE' not in p['name']]
            return sorted(hit, key=lambda p: -len(p['verts']))
        shop_plan = {}
        for slot, (src, side) in SHOP.items():
            got = shop_part(src)
            if 'SPOILER' in src: got = on_trunk(got)
            if not got:
                print('shop: %s: no %s in the car' % (slot, src))
                continue
            inner = 2 if slot.startswith('bumper') else True if 'SPOILER' in src else None  # (a spoiler: see 'wing')
            shop_plan[slot] = ([got], side, None, inner) if inner else ([got], side)
            print('shop: %s <- %s (%d levels)' % (slot, src, len(got)))
        plan = {**shop_plan, **plan}
    if mw:
        # The template's glass by its own names: the Enzo's, Elise's and Carrera GT's are glass_F, glass_LF ...
        # (glassF matched none of them: the Chiron, Senna, Terzo, SVJ, 4C, Huayra kept the template's windows,
        # their own left out, 6 Nov)
        names_ = {p_['name'] for p_ in car['parts']}
        for key in [k for k in plan if re.match(r'[a-z]+[A-Z]+$', k)]:  # (the Elise's and Carrera GT's lamps too: headlight_L)
            alt = re.sub(r'^([a-z]+)([A-Z]+)$', r'\1_\2', key)
            if key + '_LOD1' not in names_ and alt + '_LOD1' in names_: plan[alt] = plan.pop(key)
        def pos_sig(q):  # a part's shape regardless of its vertices' order (cartoolkit's merged cars reorder them)
            return np.sort(np.array([v_[:3] for v_ in q['verts']], float), axis=0)
        def seen_in(sig, seen):  # (within a millimetre: the Huracan's two copies differ in the seventh place)
            return any(o.shape == sig.shape and np.abs(o - sig).max() < 1e-3 for o in seen)
        gkeys = [k for k in plan if re.match(r'glass_?(F|R|LF|RF|LR|RR)$', k)]
        # A window part the same as one already placed (the nfs.com.ru pack's FRONT_WINDOW and REAR_WINDOW are
        # each the whole greenhouse): its slot left empty (hidden), not the glass drawn twice over, darker
        seen = []
        for key in gkeys:
            src = plan[key][0][0]
            if not src: continue
            sig = pos_sig(src[0])  # (positions: the parts' other vertex data differ)
            if seen_in(sig, seen): plan[key] = ([[]], 0, True); print('glass: %s the same as another window part, left empty' % key)
            seen.append(sig)
        # The rest of the window parts: the porters' (past a part's size) engine bays, tail-light bars, trims, the
        # Chiron's, M2's, Impala's, RS5's, GTX1's, SVJ's, Civic's of 6 Nov (16,000 to 34,000 triangles each). The
        # window slots keep only glass, so it was left out: the Chiron's engine cover a jagged hole. Their other
        # groups (not the cabin's, unless the car has its own) go in a template part the car has no use for.
        def not_glass(q):
            idx = [i_ for t_ in q['tris'] for i_ in t_]
            tris_, groups_ = [], []
            for g in q['groups']:
                cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
                ti, si = struct.unpack_from('<II', g, 0x1C)
                th = q['textures'][ti] if ti < len(q['textures']) else 0
                sh = q['shaders'][si] if si < len(q['shaders']) else 0
                if material_for(names.get(th, ''), sh) in (WINDOW, BLACKGLASS, None): continue
                tn = str(textures.get(th, {}).get('name', '')).upper()
                if lamp_lens(tn, textures.get(th)) or (si < len(q.get('materials', [])) and str(q['materials'][si]).upper().endswith('GLASS')):
                    continue  # (a lamp's cover, by its sheet's name, cut short at 24 letters: left out, as in the lamps' own parts; the Countach's 2,076 drew as black)
                if 'INTERIOR' in str(textures.get(th, {}).get('name', '')).upper() and not OWN_INTERIOR: continue
                keep = [idx[k_:k_ + 3] for k_ in range(first, first + cnt - 2, 3) if max(idx[k_:k_ + 3]) < len(q['verts'])]
                keep = [t_ for t_ in keep if max(sum((q['verts'][t_[a]][c] - q['verts'][t_[b]][c]) ** 2 for c in range(3)) for a, b in ((0, 1), (1, 2), (0, 2))) < 1.8 ** 2]  # (the Countach's spikes)
                if not keep: continue
                g2 = bytearray(g); struct.pack_into('<I', g2, 12, 3 * len(keep)); struct.pack_into('<I', g2, 0x34, 3 * len(tris_))
                groups_.append(bytes(g2)); tris_ += keep
            return dict(q, tris=tris_, groups=groups_) if tris_ else None
        def slot_is(name, key):
            rest_ = name[len(key):] if name.startswith(key) else None
            return rest_ is not None and not rest_[:1].isupper()
        rest, sigs = [], []
        for wk in ('FRONT_WINDOW', 'REAR_WINDOW', 'FRONT_LEFT_WINDOW', 'FRONT_RIGHT_WINDOW', 'REAR_LEFT_WINDOW', 'REAR_RIGHT_WINDOW', 'DRIVER'):  # (not k: the fit's scale; the driver part's other groups too: lamps the porters kept there, the 335i's, F8's, Chiron's, 6 Nov)
            lv = find(wk)
            if not lv: continue
            sig = pos_sig(lv[0])
            if seen_in(sig, sigs): continue
            sigs.append(sig)
            got = [q for q in (not_glass(q) for q in lv) if q]
            if got and sum(len(q['tris']) for q in got[:1]) >= 8:
                rest.append(got)
                print('windows: %d triangles of %s that are not glass' % (len(got[0]['tris']), lv[0]['name']))
        if rest:
            # (a stock choice only on a Most Wanted car, so drawn whatever the shop: the trunk, else a rear bumper or skirt,
            # by the template's own name, the Civic's bumperRa)
            spare = sorted((n[:-5] for n in names_ if re.match(r'(trunk|bumperR|skirt[LR])[a-z]?_LOD1$', n)), key=lambda n: (not n.startswith('trunk'), not n.startswith('bumperR'), n))
            slot = next((n for n in spare if not any(slot_is(n + '_LOD1', k) or slot_is(k, n) for k in plan)), None)
            if slot: plan[slot] = (rest, 0, False, False); print('windows: those in %s' % slot)
            else: print('windows: no spare part for them')
        # Glass only the body has (the porters': the 335i's, Brera's and Eclipse's windows all in the roof part
        # BASE, the XK's and ZR1's rear glass, the SLR's screen in its kit bodies): the body slots are built without
        # glass, so they were holes. Its triangles that no window part has (centroids 3 cm apart) go with the
        # windscreen's slot, the finest level only.
        def glass_tris(q):
            idx = [i_ for t_ in q['tris'] for i_ in t_]
            for g in q['groups']:
                cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
                ti, si = struct.unpack_from('<II', g, 0x1C)
                th = q['textures'][ti] if ti < len(q['textures']) else 0
                sh = q['shaders'][si] if si < len(q['shaders']) else 0
                if material_for(names.get(th, ''), sh) in (WINDOW, BLACKGLASS):
                    yield g, [idx[k_:k_ + 3] for k_ in range(first, first + cnt - 2, 3) if max(idx[k_:k_ + 3]) < len(q['verts'])]
        def tri_mid(q, t_): return np.mean([q['verts'][i_][:3] for i_ in t_], axis=0)
        win_cent = [tri_mid(q[0], t_) for k in ('FRONT_WINDOW', 'REAR_WINDOW', 'FRONT_LEFT_WINDOW', 'FRONT_RIGHT_WINDOW', 'REAR_LEFT_WINDOW', 'REAR_RIGHT_WINDOW')
                 for q in [find(k)] if q for _, ts in glass_tris(q[0]) for t_ in ts]
        win_cent = np.array(win_cent) if win_cent else np.zeros((0, 3))
        body_glass = []
        for q in [lv[0] for lv in ([base] + [find('BODY')]) if lv]:
            tris_, groups_ = [], []
            for g, ts in glass_tris(q):
                keep = [t_ for t_ in ts if not len(win_cent) or np.min(np.linalg.norm(win_cent - tri_mid(q, t_), axis=1)) > 0.03]
                if keep: win_cent = np.concatenate([win_cent, np.array([tri_mid(q, t_) for t_ in keep])])  # (the same glass in BASE and the body, the ZR1's: once)
                if not keep: continue
                g2 = bytearray(g); struct.pack_into('<I', g2, 12, 3 * len(keep)); struct.pack_into('<I', g2, 0x34, 3 * len(tris_))
                groups_.append(bytes(g2)); tris_ += keep
            if tris_:
                body_glass.append(dict(q, tris=tris_, groups=groups_))
                print('glass: %d triangles only in %s, with the windscreen' % (len(tris_), q['name']))
        if body_glass:
            fkey = next((k for k in gkeys if k.endswith('F') and len(k) <= 7 and k != 'glassRF' and k != 'glassLF'), None)
            if fkey is None: print('glass: no windscreen slot for them')
            elif plan[fkey][0][0]: plan[fkey] = (plan[fkey][0] + [[q] for q in body_glass],) + tuple(plan[fkey][1:])
            else: plan[fkey] = ([[q] for q in body_glass], 0, True)
    plan = {k: v + (None, False)[len(v) - 2:] for k, v in plan.items()}
    built = {}
    done = []
    def slot_is(name, key):  # the slot's own part or its shop variants (bumperF: bumperFa_LOD1), not another slot that starts the same (glassR: glassRF, glassRHL, glassRM)
        rest = name[len(key):] if name.startswith(key) else None
        return rest is not None and not (rest[:1].isupper())
    # A slot the Most Wanted car has nothing for (the M3 GTR's hood, wing and
    # mirrors are in its body): the template's part hidden, not left as it was
    empty = tuple(k for k, v in plan.items() if not all(v[0])) if mw else ()
    filled = tuple(k for k, v in plan.items() if all(v[0]))
    for part in car['parts']:
        if (part['name'].startswith('glass') and (not keep_glass or 'HL_' in part['name']) and not mw  # the template's glass stood out of a lower NFSU roof; its headlight glass never fits
                or mw and re.match(r'glass[LR](HL|TL|M)_', part['name'])  # Most Wanted: the template's lamp covers and mirror glass where its own lamps and mirrors were (glassR's slot took the right ones, the left stood as they were, 6 Nov)
                or mw and part['name'].startswith(('glassT', 'bumperR', 'bumperFg', 'bumperFrace', 'skirt', 'trunk', 'wingraceB', 'wingraceC', 'lampglass'))  # Most Wanted: in the kits, or none (a race car's lamp covers too)
                and not part['name'].startswith(filled)  # (unless a shop slot, or the tail lights' place)
                or any(slot_is(part['name'], k) for k in empty) and part['name'].endswith('_LOD1')
                or HIDE and part['name'].startswith(HIDE) and part['name'].endswith('_LOD1') and not (SHOP and part['name'].startswith(tuple(SHOP)))  # (the plan's: a template part the car has nothing for, the SRT-4's wing on the Neon)
                or part['name'].startswith(('BADGE', 'bands', 'exhaust', 'cagerace'))):  # (the race cage too: not on a stock car, and its bars showed through the glass)  # the template's badges floated where its own trunk and flanks were; its bands (under the rear glass, across the trunk) showed as dark strips over the hatch; its tailpipe hung out under the S13's bumper (the NFSU exhaust has no place of its own on the car)
            for sp in part['subparts']:
                sp['indices'] = [0, 0, 0]
            done.append(part['name'] + '(hidden)')
            continue
        for key, (src, side, glass, inner) in plan.items():
            if slot_is(part['name'], key) and part['name'].endswith('_LOD1') and all(src):
                if key not in built:
                    # (a Forza part holds 65536 vertices: a dense body's levels together, doubled for their black
                    # insides and split along the vinyl layout's seams, ran past it, the BMW M2's 24,000 of 5 Nov.
                    # Its second-finest levels left out until it fits: the finest near, the coarse ones far)
                    cap = 21000 if inner else 42000
                    src = [list(lv) for lv in src]
                    for lv in src:
                        while len(lv) > 1 and sum(len(q['verts']) for q in lv) > cap: del lv[1]
                    if inner and sum(len(lv[0]['verts']) for lv in src if lv) > 26000:
                        inner = False  # (the finest level alone too big to double: no black insides, the Impala's merged body)
                    built[key] = build(src, side, glass, inner)
                put(part, *built[key])
                done.append(part['name'])
                break
    if not keep_glass and not mw:
        fit_glass()
    # The side skirts' ends by the wheels, below the sill: stretched to the template's
    # wheelbase, the front ones hung down behind the front wheels as black flaps
    rotors_ = [sum(v[1] for v in p['verts']) / len(p['verts']) for p in car['parts'] if p['name'].startswith('rotor') or '_rotor' in p['name']]
    hub_y = min(rotors_) / 4096 if hubs and rotors_ else None  # (hubs from the physics have no rotors to give their height)
    for part in car['parts']:
        if hub_y is None or not part['name'].startswith('skirt') or not part['name'].endswith('_LOD1'): continue
        V = [(v[0] / 4096, v[1] / 4096, v[2] / 4096) for v in part['verts']]
        for sp in part['subparts']:
            ix, tris = sp['indices'], []
            for k in range(len(ix) - 2):
                a, b, c = (ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
                if len({a, b, c}) < 3: continue
                low = min(V[i][1] for i in (a, b, c)) < hub_y - 0.25  # reaches below the sill
                near = any(abs(sum(V[i][2] for i in (a, b, c)) / 3 - h) < 0.75 for h in hubs)
                if not (low and near): tris.append((a, b, c))
            sp['indices'] = strip(tris) if tris else [0, 0, 0]
    if not mw and not UV32:  # (Most Wanted's badges are in its body, from its own texture; so are Underground 2's, and
        # the boxes add_badges cuts from an Underground sheet fell on its door handle there, as black squares on the tail)
        add_badges(car, textures, atlas, {k: (v.shape[1], v.shape[0]) for k, v in extra.items()})
    new_shell = shell()
    new_fit = roof(new_shell), sides(new_shell), cover(), plan_heights(arches)
    def wheel_y():
        sw = [v[1] for p in car['parts'] if p['name'] == 'steering_wheel' for v in p['verts']]
        return (min(sw) + max(sw)) / 2 / 4096 if sw else None
    wheel0 = wheel_y()
    for part in car['parts']:
        if part['name'].startswith(CABIN) and not (OWN_INTERIOR and part['name'].startswith('interior')):  # (the car's own: already its shape)
            fit_cabin(part, old_fit, new_fit, floor)
            done.append(part['name'] + '(fitted)')
    fit_driver(car, (max(v[1] for v in new_shell) - max(v[1] for v in old_shell)) / 4096,
               wheel_y() - wheel0 if wheel0 is not None else 0.0)
    # A cargo floor: black, both faces, across the hatch just under its lip,
    # from inside the tail to behind the rear seats. The S13's hatch area is
    # empty (the Civic's cabin ends at its seats), and through the rear glass
    # the inside of the body showed untextured.
    cargo = next((p for p in car['parts'] if p['name'].startswith('trunk') and p['name'].endswith('_LOD1')), None)
    rear = next((p for p in car['parts'] if p['name'].startswith('glassR_') and any(sp['indices'] != [0, 0, 0] for sp in p['subparts'])), None)
    if cargo and rear and not mw:  # (Most Wanted: its trunk is in the body)
        G = np.array([v[:3] for v in rear['verts']], float) / 4096
        B = np.array([v[:3] for v in tbody['verts'] + cargo['verts']], float) / 4096
        y = G[:, 1].min() - 0.06                                   # under the glass's lower edge
        # only under the glass: further back, past it, the floor's corners came up
        # through the hatch lid as it slopes down to its lip (black wedges by the spoiler)
        z0 = G[:, 2].min() + 0.02
        z1 = G[:, 2].max() - 0.45                                  # short of the rear seats
        half = abs(G[:, 0]).max()                                  # as wide as the glass
        corners = [(-half, y, z0), (half, y, z0), (half, y, z1), (-half, y, z1)]
        base = len(cargo['verts'])
        for x_, y_, z_ in corners:
            cargo['verts'].append((int(round(x_ * 4096)), int(round(y_ * 4096)), int(round(z_ * 4096)), 0, 32767, 0, 255, 255, 0, 0) + dark)
        quad = [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        quad += [(a, c, b) for a, b, c in quad]
        if struct.unpack_from('<I', cargo['Damage'][1])[0]:
            cargo['Damage'] = (cargo['Damage'][0], struct.pack('<I', len(cargo['verts'])) + b''.join(struct.pack('<6h', *v[:6]) for v in cargo['verts']))
        tmpl = cargo['subparts'][0]
        cargo['subparts'] += [{'version': tmpl['version'], 'id': lod, 'material': BODY, 'prim': 6, 'extra': bytes(16),
                               'indices': strip(quad), 'tail': b''} for lod in sorted({sp['id'] for sp in cargo['subparts']})[:2]]
        done.append('cargo floor at %.2f' % y)
    # The template's panel seams (Line chunks after the parts: polylines on its
    # body, drawn as thin blended lines) followed the Civic's hood, doors and
    # trunk lid, and floated off the new body as grey lines and bands; the
    # NFSU body has its gaps modelled. Its two Flare chunks stay.
    t, o, kept = car['tail'], 0, b''
    while o + 8 <= len(t) and struct.unpack_from('<I', t, o)[0] >= 8:
        size = struct.unpack_from('<I', t, o)[0]
        if t[o + 8:t.index(b'\0', o + 8)] != b'Line': kept += t[o:o + size]
        o += size
    car['tail'] = kept + t[o:]
    apply_layout(car, tlayout, paint)
    mine = {d for d in done if '(' not in d} | {d.split('(')[0] for d in done if 'panes)' in d}
    turned = sum(orient_normals(p) for p in car['parts'] if p['name'] in mine)
    print('normals: %d turned to their faces' % turned)
    if SMOOTH:  # (a part thinned in Blender: see smooth_normals)
        print('normals: %d made again from the surface' % sum(smooth_normals(p) for p in car['parts'] if p['name'] in mine))
    print('shading: %d vertices from their height and facing' % shade_vertices([p for p in car['parts'] if p['name'] in mine and not p['name'].startswith(CABIN)]))
    if mw:  # long strips (see strip_long): the same triangles, a third of the indices
        before = after = 0
        for p in car['parts']:
            # identical vertices (and damage shape) as one, so neighbours share an edge
            dmg = p['Damage'][1]
            nd = struct.unpack_from('<I', dmg)[0] if len(dmg) >= 4 else 0
            first = {}
            same = [first.setdefault((tuple(v), dmg[4 + 12 * i:16 + 12 * i] if nd else b''), i) for i, v in enumerate(p['verts'])]
            for sp in p['subparts']:
                if sp['prim'] != 6 or len(sp['indices']) < 6: continue
                tris = strip_triangles([same[i] for i in sp['indices']])
                s = strip_long(tris)
                before += len(sp['indices'])
                if len(s) < len(sp['indices']) and strip_triangles(s) == tris: sp['indices'] = s
                after += len(sp['indices'])
        print('strips: %d indices, were %d' % (after, before))
    open(out_path, 'wb').write(carbin.write(car))
    print('replaced %d parts: %s' % (len(done), ' '.join(done)))


# Badges put on the car as flat decals where a ray from outside first meets
# the body: the image (the NFSU badge sheet, <CAR>_BADGING, or one from the
# --badges folder) and its rectangle in texels (x0, y0, x1, y1; None, all
# of it), the centre (x, y, z), the direction it is seen from, width and
# height (and optionally how far off the panel), all in carbin units / 4096
# (about 1.6 a metre). Forza: x right, y up, z forward. The NFSU model
# itself uses only the sheet's nose emblem.
# Each goes in the bumpers at its end of the car (every variant): in the
# body part the decals drew the whole sheet squeezed into them (the body's
# texture coordinates are not taken as they are), as the nose emblem, in
# the front bumper, never did.
BADGES = [
    ('model', None, (0.0, 0.895, None), (0, 0, -1), 0.46, 0.038),     # centred on the panel between the tail lights (y 0.76 to 1.03)
    # amber markers on the front bumper's corners, red at the rear. Lifted
    # further off: the fender's end lies under the bumper's corner there, and at
    # the usual lift its paint fought the marker's lower half through
    ('sheet', (62, 24, 92, 44), (None, 0.52, 2.77), (1, 0, 0), 0.15, 0.10, 0.012),
    ('sheet', (62, 24, 92, 44), (None, 0.52, 2.77), (-1, 0, 0), 0.15, 0.10, 0.012),
    ('sheet', (62, 3, 92, 23), (None, 0.58, -2.80), (1, 0, 0), 0.15, 0.10, 0.012),
    ('sheet', (62, 3, 92, 23), (None, 0.58, -2.80), (-1, 0, 0), 0.15, 0.10, 0.012),
]
# Without a --badges folder the sheet's own lettering stands in
SHEET_BADGES = {'logo': (0, 0, 59, 38), 'model': (0, 39, 61, 48)}


def load_image(path, size):
    """An image file (PNG, WebP, JPEG: anything ffmpeg reads) as RGBA,
    cropped to what is not clear and fitted into `size` (w, h; multiples of
    4) on a clear background. ffmpeg: XBRT_FFMPEG, or on the PATH."""
    import subprocess
    import numpy as np
    ff = os.environ.get('XBRT_FFMPEG') or 'ffmpeg'
    fp = os.path.join(os.path.dirname(ff), os.path.basename(ff).replace('ffmpeg', 'ffprobe'))
    probe = subprocess.run([fp, '-v', 'error', '-show_entries', 'stream=width,height',
                            '-of', 'csv=p=0', path], capture_output=True, text=True, check=True)
    w, h = (int(x) for x in probe.stdout.split()[0].split(','))
    raw = subprocess.run([ff, '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], capture_output=True, check=True).stdout
    img = np.frombuffer(raw[:w * h * 4], np.uint8).reshape(h, w, 4)
    ys, xs = np.nonzero(img[..., 3] > 16)
    img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    W, H = size
    k = min(W / img.shape[1], H / img.shape[0])
    tw, th = max(1, int(img.shape[1] * k)), max(1, int(img.shape[0] * k))
    # box filter down to the target size (area averaging, colour weighted by alpha)
    yi = (np.arange(img.shape[0]) * th // img.shape[0]); xi = (np.arange(img.shape[1]) * tw // img.shape[1])
    acc = np.zeros((th, tw, 4)); cnt = np.zeros((th, tw, 1))
    a = img[..., 3:4] / 255
    np.add.at(acc, (yi[:, None], xi[None, :]), np.concatenate([img[..., :3] * a, img[..., 3:4]], -1))
    np.add.at(cnt, (yi[:, None], xi[None, :]), 1)
    out = np.zeros((H, W, 4), np.uint8)
    rgb = acc[..., :3] / np.maximum(acc[..., 3:4] / 255, 1e-6)
    al = acc[..., 3:4] / cnt
    oy, ox = (H - th) // 2, (W - tw) // 2
    out[oy:oy + th, ox:ox + tw] = np.clip(np.concatenate([rgb, al], -1), 0, 255).astype(np.uint8)
    return out


def badge_images(folder):
    """The --badges folder's logo.* (the maker's emblem, for the nose and the
    tail) and model.* (the model's lettering), as atlas images."""
    out = {}
    for key, size in (('logo', (64, 56)), ('model', (160, 16))):
        found = [f for f in os.listdir(folder) if os.path.splitext(f)[0].lower() == key] if folder else []
        if found: out[key] = load_image(os.path.join(folder, found[0]), size)
    return out


def add_badges(car, textures, atlas, sizes={}, lift=0.004):  # lift: off the surface
    """The BADGES on the converted car, as Badge subparts of the bumpers at
    their first two detail levels. Images missing from the atlas are left
    out (or stood in for from the sheet, SHEET_BADGES)."""
    import numpy as np
    sheet = next((h for h, t in textures.items() if t['name'].endswith('_BADGING') and h in atlas), None)
    tris = []
    for p in car['parts']:
        n = p['name']
        if not n.endswith('_LOD1') or not n.startswith(('body', 'trunk', 'bumperFa', 'bumperRa', 'taillightL', 'taillightR', 'skirtLa', 'skirtRa', 'hood')): continue
        if n.startswith(('taillightLb', 'taillightRb')): continue
        V = np.array([v[:3] for v in p['verts']], float) / 4096
        for sp in p['subparts']:
            if sp['id'] != 1: continue
            ix = sp['indices']
            for k in range(len(ix) - 2):
                if len(set(ix[k:k + 3])) == 3:
                    tris.append(V[ix[k:k + 3]])
    T = np.array(tris)
    def hit(origin, d):
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        pv = np.cross(d, e2); det = (e1 * pv).sum(1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
        tv = origin - T[:, 0]; u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1); v = (qv * d).sum(1) * inv; t = (qv * e2).sum(1) * inv
        good = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        if not good.any(): return None, None
        i = np.where(good, t, np.inf).argmin()
        # the face's own normal: the panels' smoothed vertex normals point well off
        # it on the tail garnish, and decals set by them lay flat, seen edge on
        n = np.cross(e1[i], e2[i]); n /= np.linalg.norm(n)
        if np.dot(n, d) > 0: n = -n
        return origin + t[i] * d, n
    made = {True: [], False: []}  # four corners per decal, by end of the car (front: True)
    for source, rect, centre, seen, w, h, *off in BADGES:
        off = off[0] if off else lift
        if source in sizes:
            key, (W, H) = source, sizes[source]
            rect = rect or (0, 0, W, H)
        elif sheet is not None and (source == 'sheet' or source in SHEET_BADGES):
            key, W, H = sheet, textures[sheet]['width'], textures[sheet]['height']
            rect = rect if source == 'sheet' else SHEET_BADGES[source]
        else:
            continue
        x0, y0, x1, y1 = rect
        u0, v0, u1, v1 = atlas[key]
        look = -np.array(seen, float)  # the ray goes from where it is seen towards the car
        o = np.array([c if c is not None else s * 4.0 for c, s in zip(centre, seen)], float)  # out where it is seen from
        p, n = hit(o, look)
        if p is None:
            print('badge %s: missed the body' % source); continue
        up = np.array([0, 1.0, 0]) - n * n[1]; up /= np.linalg.norm(up)
        right = np.cross(n, up)  # as seen from outside, to the viewer's right (up x n mirrored the lettering)
        tu = lambda px: int((u0 + (px / W) * (u1 - u0) * W / (W - 1)) * BADGE_UV)
        tv = lambda py: int((v0 + (py / H) * (v1 - v0) * H / (H - 1)) * BADGE_UV)
        # A grid over the decal, each point dropped onto the panel along the
        # decal's normal and set `lift` off it: flat, set off far enough to
        # clear the curve, they stood off the tail's corners.
        nx, ny = max(2, int(w / 0.02) + 1), max(2, int(h / 0.02) + 1)
        grid, tris = [], []
        for j in range(ny):
            for i in range(nx):
                fx, fy = i / (nx - 1), j / (ny - 1)
                q = p + right * (fx - 0.5) * w + up * (0.5 - fy) * h
                at, an = hit(q + n * 0.3, -n)
                # (a point that fell onto another panel, one facing well away, as the
                # fender's edge under the bumper's corner, folded the decal over it)
                if at is None or np.linalg.norm(at - q) > 0.25 or np.dot(an, n) < 0.7: at, an = q, n
                q = at + an * off
                px = x0 + 0.5 + fx * (x1 - x0 - 1); py = y0 + 0.5 + fy * (y1 - y0 - 1)
                grid.append(tuple(int(round(c * 4096)) for c in q) + tuple(int(round(c * 32767)) for c in an)
                            + (255, 255, 0, 0, tu(px), tv(py)))
        for j in range(ny - 1):
            for i in range(nx - 1):
                a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i
                tris += [(a, c, b), (a, d, c)]  # wound as the body's outsides
        made[bool(p[2] > 0)].append((grid, tris))
    for front, decals in made.items():
        for part in (p for p in car['parts'] if p['name'].startswith('bumperF' if front else 'bumperR') and p['name'].endswith('_LOD1')):
            if not decals: break
            quads, add = [], []
            for grid, tris in decals:
                base = len(part['verts']) + len(add)
                quads += [tuple(base + k for k in t) for t in tris]
                add += grid
            part['verts'] = part['verts'] + add
            if struct.unpack_from('<I', part['Damage'][1])[0]:
                part['Damage'] = (part['Damage'][0], struct.pack('<I', len(part['verts'])) + b''.join(struct.pack('<6h', *v[:6]) for v in part['verts']))
            tmpl = part['subparts'][0]
            part['subparts'] += [{'version': tmpl['version'], 'id': lod, 'material': DECAL, 'prim': 6, 'extra': bytes(16),
                                  'indices': strip(quads), 'tail': b''} for lod in sorted({sp['id'] for sp in part['subparts']})[:2]]
    print('badges: %d decals' % sum(len(d) for d in made.values()))


RIM = 11       # a Forza wheel's spokes and rim face, textured from the top-left quarter of wheel.xpr
RIM_GROUP = 0x22719FA9  # the NFSU wheel's rim (its tyre is 78743ca1)


def convert_wheel(tire_path, xpr_path, nfsu_dir, out_tire, out_xpr):
    """The NFSU car's stock wheel (KIT00_WHEEL) on a Forza wheel set
    (tires\\art\\<car>\\tire.carbin and wheel.xpr, in mega.cab and
    megaxpr.cab): its rim replaces the template's spokes (material 11,
    detail levels 1 and 2); the template's tyre, barrel and spinning disc
    stay. NFSU's wheel has its axle along y and its outer face at the low y;
    Forza's along x, outer face at its lowest x. Scaled so the rims' radii
    match. wheel.xpr becomes 128x128: the template's, scaled up, with the
    NFSU wheel texture (tyre, rim, centre cap) in the top-left quarter the
    rim samples."""
    import numpy as np
    import forzaxpr as fx
    tire = carbin.read(open(tire_path, 'rb').read())
    part = tire['parts'][0]
    nparts = nfsu.read(os.path.join(nfsu_dir, 'GEOMETRY.BIN'))
    textures = nfsu.read_textures(os.path.join(nfsu_dir, 'TEXTURES.BIN'))
    prefix = part_prefix(nparts, os.path.basename(os.path.normpath(nfsu_dir)).upper())
    levels = sorted([p for p in nparts if p['name'].startswith(prefix + '_KIT00_WHEEL')], key=lambda p: -len(p['verts']))
    if not levels:  # Most Wanted: the rim is in the tyre part, its groups RIM_KIT00_SILVER, _BLACK, ...
        levels = sorted([p for p in nparts if re.fullmatch(re.escape(prefix) + '_KIT00_FRONT_TIRE_[A-D]', p['name'])], key=lambda p: -len(p['verts']))
    def is_rim(p, si):
        if p.get('materials'): return si < len(p['materials']) and p['materials'][si].upper().startswith('RIM')
        return p['shaders'][si] == RIM_GROUP
    V = np.array([v[:3] for v in part['verts']], float) / 4096
    rim_ix = sorted({i for sp in part['subparts'] if sp['material'] == RIM for i in sp['indices']})
    R = V[rim_ix]
    face, rim_r = R[:, 0].min(), np.sqrt(R[:, 1] ** 2 + R[:, 2] ** 2).max()
    shade = tuple(part['verts'][rim_ix[0]][6:10])
    out_verts, subs, tex = list(part['verts']), [], None
    for lod, p in enumerate(levels[:2], 1):
        idx = [i for t in p['tris'] for i in t]
        # one scale and depth for the whole rim: per group, Most Wanted's centre cap (3 cm) grew
        # to the rim's size and covered its spokes as a flat grey disc
        rim = [p['verts'][i] for g in p['groups'] if is_rim(p, struct.unpack_from('<II', g, 0x1C)[1])
               for i in idx[struct.unpack_from('<I', g, 0x34)[0]:struct.unpack_from('<I', g, 0x34)[0] + struct.unpack_from('<I', g, 12)[0]]
               if i < len(p['verts'])]
        if not rim: continue
        k = rim_r / max(np.hypot(v[0], v[2]) for v in rim)
        y0 = min(v[1] for v in rim)
        for g in p['groups']:
            cnt, = struct.unpack_from('<I', g, 12)
            first, = struct.unpack_from('<I', g, 0x34)
            ti, si = struct.unpack_from('<II', g, 0x1C)
            if not is_rim(p, si): continue
            tex = p['textures'][ti]
            used = sorted({i for i in idx[first:first + cnt] if i < len(p['verts'])})
            remap = {}
            for i in used:
                x, y, z, nx, ny, nz, _, u, v = p['verts'][i]
                remap[i] = len(out_verts)
                pos3 = (face + (y - y0) * k, x * k, z * k)
                out_verts.append(tuple(int(round(c * 4096)) for c in pos3)
                                 + tuple(int(round(c * 32767)) for c in (ny, nx, nz)) + shade
                                 + (int(min(max(u, 0), 1) * 0.5 * 65535), int(min(max(v, 0), 1) * 0.5 * 65535)))
            tris = []
            for j in range(first, first + cnt - 2, 3):
                a, b, c = idx[j:j + 3]
                if max(a, b, c) >= len(p['verts']): continue
                va, vb, vc = (p['verts'][i] for i in (a, b, c))
                e1 = [vb[n] - va[n] for n in range(3)]; e2 = [vc[n] - va[n] for n in range(3)]
                gn = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                if sum(gn[n] * (va[3 + n] + vb[3 + n] + vc[3 + n]) for n in range(3)) < 0: b, c = c, b
                tris.append((remap[a], remap[b], remap[c]))  # the axis swap mirrors them, as the body's: Forza's strips wind the other way
            subs.append((lod, strip(tris)))
    if not subs or tex is None:
        raise SystemExit('%s: no stock wheel rim' % nfsu_dir)
    tmpl = next(sp for sp in part['subparts'] if sp['material'] == RIM)
    part['subparts'] = [sp for sp in part['subparts'] if sp['material'] != RIM] + \
        [{'version': tmpl['version'], 'id': lod, 'material': RIM, 'prim': 6, 'extra': tmpl['extra'], 'indices': s, 'tail': b''}
         for lod, s in subs]
    part['verts'] = out_verts
    assert len(out_verts) < 65536
    if struct.unpack_from('<I', part['Damage'][1])[0]:
        part['Damage'] = (part['Damage'][0], struct.pack('<I', len(out_verts)) + b''.join(struct.pack('<6h', *v[:6]) for v in out_verts))
    open(out_tire, 'wb').write(carbin.write(tire))
    # wheel.xpr: the template's at twice the quarter's size, the NFSU wheel texture in the top-left quarter:
    # 64 for an NFSU wheel, 128 for a Most Wanted one (its spokes are painted on a flat face: at 64 they blurred away)
    src = nfsu_rgba(textures[tex]).astype(np.float32)
    sh, sw = src.shape[:2]
    q = 128 if sh >= 256 and nparts and nparts[0].get('materials') else 64
    xd = open(xpr_path, 'rb').read()
    t = fx.textures(xd)[0]
    old = fx.dxt(xd[t['start']:], t['w'], t['h'], 5)
    img = np.ascontiguousarray(old.repeat(2 * q // t['w'], 0).repeat(2 * q // t['h'], 1))
    small = src.reshape(q, sh // q, q, sw // q, 4).mean((1, 3)) if sh >= q else src.repeat(q // sh, 0).repeat(q // sw, 1)
    img[:q, :q] = np.clip(small + 0.5, 0, 255).astype(np.uint8)
    img[:q, :q, 3] = 255
    open(out_xpr, 'wb').write(fx.write_dxt5(xd, img))
    print('wheel: %d rim triangles in %d levels, scale %.3f' % (sum(len(s) for _, s in subs), len(subs), rim_r / 0.223))


VINYL_CANVAS = ('BODY', 'BODY_LEFT', 'BODY_RIGHT', 'BODY_TOP', 'BODY_REAR')  # Most Wanted's painted groups, laid out on its vinyl canvas
CANVAS = '__canvas__'  # the canvas's rooms in the atlas: pack_atlas images (CANVAS, k), white (plain paint)
CANVAS_SIZE = 512  # Most Wanted's vinyl canvas, texels
SKIN = None  # (texture name, canvas size): a livery sheet the BODY groups are drawn from, as a vinyl canvas (cartoolkit.py sets it)
WIDEN = 1.0  # the body's width alone scaled by this (cartoolkit's plan "widen": the user's 6 Nov, tyres poking out past the arches)
FIT_TRACK = False  # its width scaled apart to the template body's (cartoolkit.py's plan "fit": "track")
FIT_WIDTH = False  # scaled to the template body's width, not its length (cartoolkit.py's plan "fit": "width")
KITS = None  # the body kits the shop offers (cartoolkit.py's plan "kits"; None, all the car has): the MX-5 add-on's are
# rear halves that need bumpers of their own (its kit 1 had no nose, kit 2 came out black)
HIDE = ()  # template parts hidden by name (cartoolkit.py's plan "hide": ["wing"])
SCALE = 1.0  # the fit's scale times this (cartoolkit.py's plan "scale")
ARCHES = None  # [the car's front and rear arch middles as the length fit puts them, the template body's] (cartoolkit.py's plan "arches")
SHOP = {}  # the shop's other choices: {template slot: [the car's part less its prefix, side -1/0/1]} (cartoolkit.py's plan "shop")
SMOOTH = False  # the converted parts' normals made again from their surface (cartoolkit.py sets it for a plan that decimates)
OWN_INTERIOR = False  # a Most Wanted add-on's KIT00_INTERIOR as the cabin, not the template's fitted in (cartoolkit.py's plan
                      # "interior": true): under the roadster MX-5's open top the NB's interior was squashed into black spikes
UV32 = False  # every packed texel and the windows' black at the game's reading (32768 across the atlas), as a Most Wanted
              # car's: an Underground 2 car's (cartoolkit.py) windows came out white and red at 65536 (the 240SX keeps its own)
LOWER = 0.0  # carbin units (/4096) the body sits below the template's floor (plan "lower"): the lowest points meet, and
             # the SC63's is its middle plank: its sills rode 0.10 above the Bentley's


def canvas_bands(nparts):
    """The stretches of Most Wanted's vinyl canvas its painted triangles
    use: rows no triangle crosses cut it into bands (the car's two sides,
    the roof, hood and trunk, the tail), each cut to the columns used, as
    (row0, row1, col0, col1) in canvas texels, two round. Packed whole, the
    canvas took a 512 square the race car's atlas did not have, and halved
    the stripes came out in steps."""
    import numpy as np
    spans, corners = [], []
    for p in nparts:
        idx = [i for t in p['tris'] for i in t]
        for g, name in zip(p['groups'], p['materials']):
            if name not in VINYL_CANVAS: continue
            cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
            for j in range(first, first + cnt - 2, 3):
                t = idx[j:j + 3]
                if max(t) >= len(p['verts']): continue
                us = [min(max(p['verts'][i][7], 0.0), 1.0) for i in t]; vs = [min(max(p['verts'][i][8], 0.0), 1.0) for i in t]
                spans.append((min(vs), max(vs), min(us), max(us)))
                corners.append(list(zip(us, vs)))
    if SKIN: return canvas_islands(corners)
    bands = []
    for v0, v1, u0, u1 in sorted(spans):
        if bands and v0 <= bands[-1][1]:
            b = bands[-1]; bands[-1] = [b[0], max(b[1], v1), min(b[2], u0), max(b[3], u1)]
        else:
            bands.append([v0, v1, u0, u1])
    n = CANVAS_SIZE
    out = []
    for v0, v1, u0, u1 in bands:
        r0, r1 = max(0, int(v0 * n) - 2), min(n, int(np.ceil(v1 * n)) + 2)
        c0, c1 = max(0, int(u0 * n) - 2), min(n, int(np.ceil(u1 * n)) + 2)
        r1, c1 = r0 + (r1 - r0 + 3) // 4 * 4, c0 + (c1 - c0 + 3) // 4 * 4  # (whole DXT blocks once halved)
        out.append((r0, r1, c0, c1))
    return out


ISLANDS = None  # canvas_islands' map: each canvas texel's island (its index in the list, -1 none)


def canvas_islands(corners):
    """A livery sheet (SKIN) cut into its islands instead of bands: its rows are all used (the
    SC63's panels stand all over it), and whole it needs a square the race template's atlas does
    not have. The texels the painted triangles cover (corners: each one's three (u, v)), grown by
    two, in connected pieces, each its own rectangle (as canvas_bands' (row0, row1, col0, col1));
    ISLANDS says which texel belongs to which. (By the triangles' boxes, long thin ones bridged
    the sheet and it came out one piece.)"""
    import numpy as np
    global ISLANDS
    n = CANVAS_SIZE
    mask = np.zeros((n, n), bool)
    for c in corners:
        uv_raster(mask, np.array(c) * n)
    for _ in range(2):
        grown = mask.copy()
        grown[1:] |= mask[:-1]; grown[:-1] |= mask[1:]; grown[:, 1:] |= mask[:, :-1]; grown[:, :-1] |= mask[:, 1:]
        mask = grown
    lab = np.where(mask, np.arange(n * n).reshape(n, n), -1)
    while True:  # each piece takes its highest texel number
        new = lab.copy()
        new[1:] = np.maximum(new[1:], lab[:-1]); new[:-1] = np.maximum(new[:-1], lab[1:])
        new[:, 1:] = np.maximum(new[:, 1:], lab[:, :-1]); new[:, :-1] = np.maximum(new[:, :-1], lab[:, 1:])
        new[~mask] = -1
        if (new == lab).all(): break
        lab = new
    ids = sorted(set(lab[mask].tolist()))
    rects, ISLANDS = [], np.full((n, n), -1)
    for k, i in enumerate(ids):
        ys, xs = np.nonzero(lab == i)
        r0, c0 = ys.min(), xs.min()
        r1, c1 = r0 + (ys.max() + 1 - r0 + 3) // 4 * 4, c0 + (xs.max() + 1 - c0 + 3) // 4 * 4  # (whole DXT blocks)
        if r1 > n: r0, r1 = r0 - (r1 - n), n
        if c1 > n: c0, c1 = c0 - (c1 - n), n
        rects.append((int(r0), int(r1), int(c0), int(c1)))
        ISLANDS[lab == i] = k
    return rects


def canvas_uv(rect, band, u, v):
    """A canvas coordinate's place in the atlas (u16, as the vertices have
    it): band (row0, row1, col0, col1) packed at rect (pack_atlas's texel
    centres of its corners, 512 texels)."""
    r0, r1, c0, c1 = band
    u0, v0, u1, v1 = rect
    au = u0 - 0.5 / 512 + (u * CANVAS_SIZE - c0) / (c1 - c0) * (u1 - u0 + 1 / 512)
    av = v0 - 0.5 / 512 + (v * CANVAS_SIZE - r0) / (r1 - r0) * (v1 - v0 + 1 / 512)
    return int(au * BADGE_UV), int(av * BADGE_UV)


def bake_vinyl(vinyls_bin, prefix, name, colours, rooms, livery_dir):
    """A Most Wanted vinyl (VINYLS.BIN: 512 x 512, 8-bit palette, and a
    _MASK of where it is) baked into a second livery, livery1*.xpr beside
    livery0*.xpr: the painted triangles take Most Wanted's own canvas
    coordinates, its bands' rooms in the atlas (rooms: (rect as pack_atlas
    gives it, band as canvas_bands does)) plain paint in livery0; here they
    are the vinyl over the base colour, and the
    rest of the plain paint (clear white texels) the base colour, for a
    .livery with a white override. The vinyl's colours are its own (the
    Hero's preset vinyl, PSRTEST, is its navy and white); given a swatch,
    its pure reds take it (as the shop's vinyls, BMW_24's edging), and given
    a colour, the rest take that. Baked into the template's vinyl layout
    instead, the race car's sides shared texels and one took the other's
    stripes."""
    import numpy as np
    import forzaxpr as fx
    base = np.array(colours[0], float)
    swatch = np.array(colours[1], float) if len(colours) > 1 else None
    other = np.array(colours[2], float) if len(colours) > 2 else None
    tex = nfsu.read_textures(vinyls_bin)
    def image(n):
        t = next(x for x in tex.values() if x['data'] and x['name'] == (prefix + '_' + n)[:23])
        d, w, h = t['data'], t['width'], t['height']
        pal = np.frombuffer(d[w * h:w * h + 1024], np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]].astype(float)
        return pal[np.frombuffer(d[:w * h], np.uint8).reshape(h, w)]
    art, mask = image(name), image(name + '_MASK')
    cov = np.minimum(art[..., 3:4] / 101, mask[..., :1] / 255)  # (its palette's alpha: the clear grey round it blended in as specks)
    col = art[..., :3] if other is None else np.broadcast_to(other, art[..., :3].shape)
    if swatch is not None:
        col = np.where((art[..., 0] > 2 * art[..., 1:3].max(-1))[..., None], swatch, col)
    bake_canvas(base * (1 - cov) + col * cov, base, rooms, livery_dir)  # 512 x 512
    print('vinyl: %s baked into livery1 (%d bands of its canvas)' % (name, len(rooms)))


def bake_canvas(vinyl, base, rooms, livery_dir):
    """livery1*.xpr: livery0*.xpr with the canvas's bands (vinyl, CANVAS_SIZE square, RGB) in their
    rooms and the rest of the plain paint (clear white texels) the base colour."""
    import numpy as np
    import forzaxpr as fx
    names = ('livery0nc.xpr', 'livery0.xpr', 'livery0hi.xpr')
    files = {n: bytearray(open(os.path.join(livery_dir, n), 'rb').read()) for n in names}
    nc, vol, hi = (fx.textures(files[n])[0] for n in names)
    W, H, D = nc['w'], nc['h'], nc['d']
    def put(img, size):  # each band into an atlas of that size, at its rect (texel centres) and the edge round it
        for (u0, v0, u1, v1), (r0, r1, c0, c1) in rooms:
            part = vinyl[r0:r1, c0:c1]
            x0, y0 = int(round(u0 * size - 0.5 * size / W)), int(round(v0 * size - 0.5 * size / W))
            x1, y1 = int(round(u1 * size + 0.5 * size / W)), int(round(v1 * size + 0.5 * size / W))
            f = part.shape[0] // (y1 - y0)
            if f > 1:
                v = part.reshape(part.shape[0] // f, f, part.shape[1] // f, f, 3).mean((1, 3))
            else:
                ys = ((np.arange(y0, y1) - y0 + 0.5) / (y1 - y0) * part.shape[0]).astype(int)
                xs = ((np.arange(x0, x1) - x0 + 0.5) / (x1 - x0) * part.shape[1]).astype(int)
                v = part[ys][:, xs]
            e = 2 * size // W  # (the packed edge, at least two texels)
            img[y0 - e:y1 + e, x0 - e:x1 + e, :3] = np.pad(v, ((e, e), (e, e), (0, 0)), mode='edge')
    def recolour(img):  # plain paint (clear white) as the base, then the vinyl
        plain = (img[..., 3] < 8) & (img[..., :3].min(-1) > 240)
        img[plain, :3] = base
        put(img, img.shape[0])
    hiimg = fx.dxt(bytes(files['livery0hi.xpr'][hi['start']:]), 2 * W, 2 * H, 5).astype(float)
    recolour(hiimg)
    level, off, sz = hiimg, hi['start'], 2 * W
    for lv in range(hi['mips']):
        if lv: level = level.reshape(sz, 2, sz, 2, 4).mean((1, 3))
        img = np.clip(level + 0.5, 0, 255).astype(np.uint8)
        if sz < 4: img = np.pad(img, ((0, 4 - sz), (0, 4 - sz), (0, 0)), mode='edge')
        enc = fx.encode_dxt5(np.ascontiguousarray(img))
        files['livery0hi.xpr'][off:off + len(enc)] = enc
        off += max(1, sz // 4) ** 2 * 16
        sz = max(1, sz // 2)
    sw = fx.unswizzle_index(W, H, D)
    raw = np.frombuffer(bytes(files['livery0nc.xpr'][nc['start']:nc['start'] + W * H * D * 4]), np.uint8).reshape(-1, 4).copy()
    ncimg = raw[sw][..., [2, 1, 0, 3]].astype(float)
    n = (W // 4) * (H // 4)
    vblocks = np.frombuffer(bytes(files['livery0.xpr'][vol['start']:vol['start'] + n * D * 16]), np.uint8).reshape(n, D, 16).copy()
    for z in range(D):  # the clean slice and the damaged one alike
        recolour(ncimg[z])
        vimg = fx.dxt(vblocks[:, z].tobytes(), W, H, 5).astype(float)
        recolour(vimg)
        vblocks[:, z] = np.frombuffer(fx.encode_dxt5(np.ascontiguousarray(np.clip(vimg + 0.5, 0, 255).astype(np.uint8))), np.uint8).reshape(n, 16)
    raw[sw.reshape(-1)] = np.clip(ncimg + 0.5, 0, 255).astype(np.uint8)[..., [2, 1, 0, 3]].reshape(-1, 4)
    files['livery0nc.xpr'][nc['start']:nc['start'] + raw.size] = raw.tobytes()
    files['livery0.xpr'][vol['start']:vol['start'] + vblocks.size] = vblocks.tobytes()
    for n_ in names:
        open(os.path.join(livery_dir, n_.replace('livery0', 'livery1')), 'wb').write(files[n_])


def paint_shop(template_bin, out_bin, livery_dir, boxes, pad=4, paint=None):
    """The paint shop's copy of the livery: <car>.liveries.bin (zlib) holds,
    after a 1136-byte header of D3D texture headers, the car's views for the
    vinyl editor, 'damage' and 'detail': 1024x1024 8-bit indices (linear)
    into 256 BGRA colours. A repaint draws detail over the paint into the
    livery the car then wears; its alpha is opaque where paint must not go
    (lamps, badges, the cabin). The template's, kept, drew the Civic's
    atlas over the new car's lamps (packed where the Civic is paint): every
    repaint took their texture. Here detail is the new atlas (livery0hi)
    in 256 colours, its alpha the template's with the packed textures'
    boxes (0..1) opaque."""
    import zlib
    import numpy as np
    import forzaxpr as fx
    d = bytearray(zlib.decompress(open(template_bin, 'rb').read()))
    head = 1136
    idx_at = pal_at = None
    for o in range(0, head - 20, 4):  # detail's texture headers: indices (format 0x1B) then the palette
        com, data, _, fmt, _ = struct.unpack_from('<5I', d, o)
        if com == 0x00040001 and (fmt >> 8) & 0xFF == 0x1B and b'detail' in d[max(0, o - 120):o]:
            idx_at = head + data
            pal_at = head + struct.unpack_from('<I', d, o + 24)[0]
            break
    assert idx_at, 'no detail texture in %s' % template_bin
    old_i = np.frombuffer(bytes(d[idx_at:idx_at + (1 << 20)]), np.uint8).reshape(1024, 1024)
    old_p = np.frombuffer(bytes(d[pal_at:pal_at + 1024]), np.uint8).reshape(256, 4)
    alpha = old_p[old_i][..., 3].copy()
    if paint is not None: alpha[paint] = 0  # the body's paint (see pack_atlas's cover): repaints reach it
    for u0, v0, u1, v1 in boxes:
        alpha[max(0, int(v0 * 1024) - pad):int(v1 * 1024) + pad + 1, max(0, int(u0 * 1024) - pad):int(u1 * 1024) + pad + 1] = 255
    hd = open(os.path.join(livery_dir, 'livery0hi.xpr'), 'rb').read()
    t = fx.textures(hd)[0]
    img = fx.dxt(hd[t['start']:], 1024, 1024, 5)[..., :3].astype(np.float32)
    px = np.concatenate([img.reshape(-1, 3), alpha.reshape(-1, 1).astype(np.float32)], 1)  # RGBA
    # 256 colours: k-means from a spread of the pixels
    rng = np.random.default_rng(0)
    cent = px[rng.choice(len(px), 256, replace=False)].copy()
    for _ in range(8):
        lab = np.empty(len(px), np.int64)
        cc = (cent ** 2).sum(1)
        for a in range(0, len(px), 32768):
            q = px[a:a + 32768]
            lab[a:a + 32768] = (cc[None] - 2 * q @ cent.T).argmin(1)
        for k in range(256):
            m = lab == k
            if m.any(): cent[k] = px[m].mean(0)
    # In order of alpha, then brightness, as the template's: the game blends
    # neighbouring entries (unsorted, the lamps came out speckled grey)
    order = np.lexsort((-(cent[:, :3] @ np.array([0.299, 0.587, 0.114], np.float32)), cent[:, 3]))
    cent = cent[order]
    lab = np.argsort(order)[lab]
    pal = np.clip(cent + 0.5, 0, 255).astype(np.uint8)[:, [2, 1, 0, 3]]  # BGRA
    d[idx_at:idx_at + (1 << 20)] = lab.astype(np.uint8).tobytes()
    d[pal_at:pal_at + 1024] = pal.tobytes()
    open(out_bin, 'wb').write(zlib.compress(bytes(d), 9))
    err = np.abs(cent[lab] - px).mean(0)
    print('paint shop: detail in 256 colours (mean error %s), %d boxes opaque (%s)' % (err.round(1).tolist(), len(boxes), out_bin))


def main(argv):
    if len(argv) == 7 and argv[1] == '--wheel':
        convert_wheel(*argv[2:])
        raise SystemExit
    args = [a for a in argv[1:] if a not in ('--keep-glass', '--no-stock-wing', '--clear-livery')]
    badges = None
    if '--badges' in args:
        i = args.index('--badges')
        badges = args[i + 1]
        del args[i:i + 2]
    liveries = None
    if '--liveries' in args:  # the template's <car>.liveries.bin: writes liveries.bin beside the output (see paint_shop)
        i = args.index('--liveries')
        liveries = args[i + 1]
        del args[i:i + 2]
    vinyl = None
    if '--vinyl' in args:  # NAME:base[,swatch[,colour]] (see bake_vinyl)
        i = args.index('--vinyl')
        name, _, cols = args[i + 1].partition(':')
        vinyl = (name, [tuple(int(c[k:k + 2], 16) for k in (0, 2, 4)) for c in cols.split(',') if c])
        del args[i:i + 2]
    if len(args) != 3:
        raise SystemExit(__doc__)
    convert(*args, keep_glass='--keep-glass' in argv, badges=badges, liveries=liveries, stock_wing='--no-stock-wing' not in argv,
            clear_livery='--clear-livery' in argv, vinyl=vinyl)


if __name__ == '__main__':
    main(sys.argv)
