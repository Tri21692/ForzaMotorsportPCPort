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
           bhash('DULLPLASTIC'): PLASTIC, bhash('CHROME'): CHROME, bhash('HEADLIGHTGLASS'): HEADLIGHTGLASS,
           bhash('BRAKELIGHTGLASS'): REDGLASS, bhash('DECAL'): BADGE, bhash('HEADLIGHT'): HEADLIGHTS,
           bhash('BRAKELIGHT'): TAILLIGHTS, bhash('RUBBER'): BLACK, bhash('ENGINE'): BLACK,
           bhash('MIRROR'): CHROME}  # the mirrors' glass, as the Civic's (as paint it was a flat blue slab)


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
PAINTED = ('body', 'hooda', 'bumperFa', 'bumperRa', 'trunk', 'skirtLa', 'skirtRa', 'mirrorL', 'mirrorR')
PROJ = {'left': (2, 1), 'right': (2, 1), 'top': (2, 0), 'front': (0, 1), 'back': (0, 1)}  # the plane each view sees: Forza x right, y up, z forward
CELL = 0.02  # the layout's lookup grid, carbin units / 4096


def strip_tris(ix):
    """A strip's triangles, each wound as the first (strips alternate)."""
    return [(ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
            for k in range(len(ix) - 2) if len({ix[k], ix[k + 1], ix[k + 2]}) == 3]


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
    for p in car['parts']:
        if not (p['name'].startswith(PAINTED) and p['name'].endswith('_LOD1')): continue
        V = p['verts']
        for sp in p['subparts']:
            if sp['id'] != 1 or sp['material'] != BODY: continue
            for t in strip_tris(sp['indices']):
                A = np.array([V[i][:3] for i in t], float) / 4096
                UV = np.array([V[i][10:12] for i in t], float)
                if np.ptp(UV, 0).max() > 16384: continue  # (wrapped)
                view = facing(A)
                a, b = PROJ[view]
                P = A[:, [a, b]]
                M = np.c_[P, np.ones(3)]
                if abs(np.linalg.det(M)) < 1e-8: continue
                tris[view].append((P, np.linalg.solve(M, UV), outward(view, A.mean(0)), (p['name'], t[0])))
                for i in t[1:]: up[root((p['name'], i))] = root((p['name'], t[0]))
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
        layout[view] = (lo, grid, [t[1] for t in ts], np.array([t[0].mean(0) for t in ts]), isl)
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
                lo, grid, maps, mids, isl = layout[view]
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
                        uv = np.r_[q, 1] @ maps[under(q, island)]
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
        i, p = next((i, p) for i, p in enumerate(car['parts']) if p['name'] == like + '_LOD1')
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


def pack_atlas(images, livery_dir, out_dir, keep=(), pad=4, protect=(), cover=None):
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
    for u0, v0, u1, v1 in protect:
        used[max(0, int(v0 * H) - 2):int(v1 * H) + 3, max(0, int(u0 * W) - 2):int(u1 * W) + 3] = True
    rects, where = {}, {}
    if cover is not None:
        grow = cover.copy()
        for d_ in ((1, 0), (-1, 0), (0, 1), (0, -1)): grow |= np.roll(cover, d_, (0, 1))
        for u0, v0, u1, v1 in protect:
            grow[int(v0 * 2 * H):int(v1 * 2 * H) + 1, int(u0 * 2 * W):int(u1 * 2 * W) + 1] = False
        for u, v in keep:
            x, y = u * 2 * W // 65536, v * 2 * H // 65536
            if hiimg[min(2 * H - 1, y), min(2 * W - 1, x), :3].max() < 128:  # (the black texel stays)
                grow[max(0, y - 16):y + 16, max(0, x - 16):x + 16] = False
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


def convert(template_path, nfsu_dir, out_path, keep_glass=False, badges=None, liveries=None, stock_wing=True):
    import numpy as np
    car = carbin.read(open(template_path, 'rb').read())
    tlayout, tcover = template_layout(car)  # (before its parts are replaced)
    nparts = nfsu.read(os.path.join(nfsu_dir, 'GEOMETRY.BIN'))
    textures = nfsu.read_textures(os.path.join(nfsu_dir, 'TEXTURES.BIN'))
    prefix = os.path.basename(os.path.normpath(nfsu_dir)).upper()
    names = {bhash(prefix + '_SKIN1'): prefix + '_SKIN1'}
    names.update({h: t['name'] for h, t in textures.items()})

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
        for p in nparts:
            for name in p['materials']: SHADERS.setdefault(bhash(name), mw_material(name))
        # Its parts name textures by role, resolved to the car's own at run time
        for role, own in (('HEADLIGHT', '_KIT00_HEADLIGH'), ('BRAKELIGHT', '_KIT00_BRAKELIG')):
            hit = next((h for h, t in textures.items() if t['name'].startswith(prefix + own) and t['data']), None)
            for side in ('LEFT', 'RIGHT'):
                if hit is not None: textures[bhash('%s_%s' % (role, side))] = textures[hit]
        names.update({h: t['name'] for h, t in textures.items()})
        print('Most Wanted car: %d parts, %d textures' % (len(nparts), len(textures)))

    # the fit: template body vs NFSU body (+ roof)
    tbody = next(p for p in car['parts'] if p['name'].startswith('body'))
    tz = [v[2] / 4096 for v in tbody['verts']]; ty = [v[1] / 4096 for v in tbody['verts']]
    # Most Wanted's roof (with a copy of each window) is <CAR>_BASE_A to _D
    base = sorted([p for p in nparts if p['name'].startswith(prefix + '_BASE_')], key=lambda p: -len(p['verts'])) if mw else []
    nb = find('BODY')[0]['verts'] + (find('ROOF')[0]['verts'] if find('ROOF') else []) + (base[0]['verts'] if base else [])
    nx = [v[0] for v in nb]; nz = [v[2] for v in nb]
    k = (max(tz) - min(tz)) / (max(nx) - min(nx))
    dz = (max(tz) + min(tz)) / 2 - k * (max(nx) + min(nx)) / 2
    dy = min(ty) - k * min(nz)
    print('fit: scale %.3f, forward offset %.3f, up offset %.3f' % (k, dz, dy))

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
    # The NFSU car's own textures (lights, badges) go into the livery atlas,
    # written beside the output (liveries/standard).
    own = {th for key in ('BODY', 'ROOF', 'HOOD', 'TRUNK', 'FRONT_BUMPER', 'REAR_BUMPER', 'SKIRT', 'HEADLIGHT', 'BRAKELIGHT', 'LEFT_SIDE_MIRRO', 'RIGHT_SIDE_MIRR')
                                + (('LEFT_HEADLIGHT', 'RIGHT_HEADLIGHT', 'LEFT_BRAKELIGHT', 'RIGHT_BRAKELIGHT', 'SPOILER') if mw else ())
           for p in find(key) for th in p['textures'] if th in textures and textures[th]['data']}
    if mw:  # only what is drawn from its texture (badges, lamps): the atlas has little room, and trim takes Forza's own
        own = {p['textures'][g[0x1C]] for p in nparts if '_KIT00_' in p['name'] and p['materials']
               for g, name in zip(p['groups'], p['materials'])
               if mw_material(name) in (BADGE, HEADLIGHTS, TAILLIGHTS) and g[0x1C] < len(p['textures'])
               and p['textures'][g[0x1C]] in textures and textures[p['textures'][g[0x1C]]]['data']}
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
    images.update(extra)
    protect = []
    if mw:  # the template parts that stay (interior, steering wheel, brakes, driver): each triangle's texel box
        replaced = ('body', 'glass', 'headlight', 'taillight', 'bumper', 'skirt', 'hood', 'wing', 'trunk', 'mirror', 'exhaust', 'BADGE', 'bands')
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
    atlas = pack_atlas(images, livery_dir,
                       os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'),
                       keep=[paint, dark] + ([(paint[0] * 2 % 65536, paint[1] * 2 % 65536)] if mw else []),  # (both readings: see the paint texel)
                       protect=protect, cover=tcover)
    if liveries:
        paint_shop(liveries, os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries.bin'),
                   os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'), list(atlas.values()),
                   paint=tcover)
    print('atlas: %s' % ', '.join('%s at %.3f, %.3f' % (h if isinstance(h, str) else textures[h]['name'], r[0], r[1]) for h, r in atlas.items()))

    # Wheels: the template's hubs (its brake rotors) stay where its physics
    # puts them, so the NFSU body is stretched between its wheel arches
    # (the middles of their liners, 010cb64a) to put each arch over its
    # hub; ahead of the front arch and behind the rear one it keeps the
    # scale k. Scaled evenly, the S13's shorter wheelbase left the rear
    # wheels standing behind their arches.
    hubs = [(min(v[2] for v in p['verts']) + max(v[2] for v in p['verts'])) / 2 / 4096
            for p in car['parts'] if p['name'].startswith('rotor')]
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

    def along(x):
        if af is None: return k * x + dz
        if x > af: return hf + k * (x - af)
        if x < ar: return hr + k * (x - ar)
        return hr + (x - ar) * (hf - hr) / (af - ar)

    def pos(v):
        x, y, z = -k * v[1], k * v[2] + dy, along(v[0])
        return [max(-32768, min(32767, int(round(c * 4096)))) for c in (x, y, z)]

    def nrm(v):
        x, y, z = -v[4], v[5], v[3]
        return [max(-32768, min(32767, int(round(c * 32767)))) for c in (x, y, z)]

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
        through the 240SX's empty hatch area."""
        verts, subs = [], []
        for lod, p in [(i + 1, lv) for src in sources for i, lv in enumerate(src[:4])]:
            base = len(verts)
            for v in p['verts']:
                verts.append(tuple(pos(v) + nrm(v) + [0xFF, 0xFF, 0, 0] + list(WHITE_UV)))
            idx = [i for t in p['tris'] for i in t]
            for g in p['groups']:
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
                    e1 = [vb[k] - va[k] for k in range(3)]; e2 = [vc[k] - va[k] for k in range(3)]
                    g = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    if inner and sh != bhash('WINDSHIELD'):
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
                    if trim:
                        tris = [t for t in tris if not dark(t)]
                        subs.append((lod, WINDOWS, strip(trim)))
                if tris and th in atlas:  # its texture is in the livery atlas: its own coordinates, moved there
                    u0, v0, u1, v1 = atlas[th]
                    one = BADGE_UV if m == BADGE or mw else 65536  # (see BADGE_UV and ATLAS_UV)
                    for i in {i for t in tris for i in t}:
                        nv = p['verts'][i - base]
                        u = min(max(nv[7], 0.0), 1.0); v = min(max(nv[8], 0.0), 1.0)
                        verts[i] = verts[i][:10] + (int((u0 + u * (u1 - u0)) * one), int((v0 + v * (v1 - v0)) * one), 'atlas')
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
                if Qm[i] == WINDOWS: return tuple(old[j][6:10]) + dark
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
                            int(min(255, max(0, 1.48 * (89.4 + 76.5 * ny + 79.6 * h)))), 0, 0) + paint
                if Qm[i] == BODY: return (255, 255, 0, 0) + paint  # one known paint texel, full shading: copied, panels near the template's windows came out black or clear
                if mw and len(verts[i]) <= 12 and Qm[i] in (CHROME, PLASTIC):  # untextured trim: the template's nearest texel was often its red lamps (a grille in red stripes)
                    return tuple(old[j][6:10]) + (paint if Qm[i] == CHROME else dark)
                if len(verts[i]) > 12: return tuple(old[j][6:10]) + verts[i][10:12]  # its own texture, packed into the atlas
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

    plan = {
        'body': ([find('BODY'), find('ROOF')], 0, None, True), 'hood': ([find('HOOD')], 0), 'trunk': ([find('TRUNK')], 0, None, True),
        'bumperF': ([find('FRONT_BUMPER')], 0), 'bumperR': ([find('REAR_BUMPER')], 0),
        'skirtL': ([find('SKIRT')], -1), 'skirtR': ([find('SKIRT')], 1),
        'headlightL': ([find('HEADLIGHT')], -1), 'headlightR': ([find('HEADLIGHT')], 1),
        'taillightL': ([find('BRAKELIGHT')], -1), 'taillightR': ([find('BRAKELIGHT')], 1),
        'mirrorL': ([find('LEFT_SIDE_MIRRO')], 0), 'mirrorR': ([find('RIGHT_SIDE_MIRR')], 0),
        # every wing the template offers becomes the NFSU car's own spoiler: left
        # as they were, the Civic's floated behind the hatch where its trunk was
        'wing': ([find('SPOILER')], 0),
    }
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
        wings = list(zip(WING_SLOTS, [n for n in MW_SPOILERS if spoilers.get('SPOILER_STYLE%02d' % n)]))
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
            'headlightL': ([find('LEFT_HEADLIGHT'), find('LEFT_HEADLIGHT_GLASS')], 0),
            'headlightR': ([find('RIGHT_HEADLIGHT'), find('RIGHT_HEADLIGHT_GLASS')], 0),
            'taillightL': ([find('LEFT_BRAKELIGHT')], 0), 'taillightR': ([find('RIGHT_BRAKELIGHT')], 0),
            'mirrorL': ([find('LEFT_SIDE_MIRROR')], 0), 'mirrorR': ([find('RIGHT_SIDE_MIRROR')], 0),
        }
        write_upgrades(os.path.join(os.path.dirname(os.path.abspath(out_path)), 'upgrades.xml'),
                       [n for n in range(1, 6) if kit(n, 'BODY')], hoods, wings, stock_wing)
    plan = {k: v + (None, False)[len(v) - 2:] for k, v in plan.items()}
    built = {}
    done = []
    for part in car['parts']:
        if (part['name'].startswith('glass') and (not keep_glass or 'HL_' in part['name']) and not mw  # the template's glass stood out of a lower NFSU roof; its headlight glass never fits
                or mw and part['name'].startswith(('glassT', 'bumperR', 'bumperFg', 'bumperFrace', 'skirt', 'trunk', 'wingraceB', 'wingraceC'))  # Most Wanted: in the kits, or none
                and not part['name'].startswith(tuple(k for k in plan if k.startswith('wingrace')))  # (unless a shop slot)
                or part['name'].startswith(('BADGE', 'bands', 'exhaust', 'cagerace'))):  # (the race cage too: not on a stock car, and its bars showed through the glass)  # the template's badges floated where its own trunk and flanks were; its bands (under the rear glass, across the trunk) showed as dark strips over the hatch; its tailpipe hung out under the S13's bumper (the NFSU exhaust has no place of its own on the car)
            for sp in part['subparts']:
                sp['indices'] = [0, 0, 0]
            done.append(part['name'] + '(hidden)')
            continue
        for key, (src, side, glass, inner) in plan.items():
            if part['name'].startswith(key) and part['name'].endswith('_LOD1') and all(src):
                if key not in built: built[key] = build(src, side, glass, inner)
                put(part, *built[key])
                done.append(part['name'])
                break
    if not keep_glass and not mw:
        fit_glass()
    # The side skirts' ends by the wheels, below the sill: stretched to the template's
    # wheelbase, the front ones hung down behind the front wheels as black flaps
    hub_y = min(sum(v[1] for v in p['verts']) / len(p['verts']) for p in car['parts'] if p['name'].startswith('rotor')) / 4096 if hubs else None
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
    if not mw:  # (Most Wanted's badges are in its body, from its own texture)
        add_badges(car, textures, atlas, {k: (v.shape[1], v.shape[0]) for k, v in extra.items()})
    new_shell = shell()
    new_fit = roof(new_shell), sides(new_shell), cover(), plan_heights(arches)
    def wheel_y():
        sw = [v[1] for p in car['parts'] if p['name'] == 'steering_wheel' for v in p['verts']]
        return (min(sw) + max(sw)) / 2 / 4096 if sw else None
    wheel0 = wheel_y()
    for part in car['parts']:
        if part['name'].startswith(CABIN):
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
    prefix = os.path.basename(os.path.normpath(nfsu_dir)).upper()
    levels = sorted([p for p in nparts if p['name'].startswith(prefix + '_KIT00_WHEEL')], key=lambda p: -len(p['verts']))
    V = np.array([v[:3] for v in part['verts']], float) / 4096
    rim_ix = sorted({i for sp in part['subparts'] if sp['material'] == RIM for i in sp['indices']})
    R = V[rim_ix]
    face, rim_r = R[:, 0].min(), np.sqrt(R[:, 1] ** 2 + R[:, 2] ** 2).max()
    shade = tuple(part['verts'][rim_ix[0]][6:10])
    out_verts, subs, tex = list(part['verts']), [], None
    for lod, p in enumerate(levels[:2], 1):
        idx = [i for t in p['tris'] for i in t]
        for g in p['groups']:
            cnt, = struct.unpack_from('<I', g, 12)
            first, = struct.unpack_from('<I', g, 0x34)
            ti, si = struct.unpack_from('<II', g, 0x1C)
            if p['shaders'][si] != RIM_GROUP: continue
            tex = p['textures'][ti]
            used = sorted({i for i in idx[first:first + cnt] if i < len(p['verts'])})
            P = np.array([p['verts'][i][:3] for i in used])
            k = rim_r / np.sqrt(P[:, 0] ** 2 + P[:, 2] ** 2).max()
            y0 = P[:, 1].min()
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
    # wheel.xpr: the template's at 128x128, the NFSU wheel texture in the top-left quarter
    xd = open(xpr_path, 'rb').read()
    t = fx.textures(xd)[0]
    old = fx.dxt(xd[t['start']:], t['w'], t['h'], 5)
    img = np.ascontiguousarray(old.repeat(128 // t['w'], 0).repeat(128 // t['h'], 1))
    src = nfsu_rgba(textures[tex]).astype(np.float32)
    sh, sw = src.shape[:2]
    small = src.reshape(64, sh // 64, 64, sw // 64, 4).mean((1, 3)) if sh >= 64 else src.repeat(64 // sh, 0).repeat(64 // sw, 1)
    img[:64, :64] = np.clip(small + 0.5, 0, 255).astype(np.uint8)
    img[:64, :64, 3] = 255
    open(out_xpr, 'wb').write(fx.write_dxt5(xd, img))
    print('wheel: %d rim triangles in %d levels, scale %.3f' % (sum(len(s) for _, s in subs), len(subs), rim_r / 0.223))


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


if __name__ == '__main__':
    if len(sys.argv) == 7 and sys.argv[1] == '--wheel':
        convert_wheel(*sys.argv[2:])
        raise SystemExit
    args = [a for a in sys.argv[1:] if a not in ('--keep-glass', '--no-stock-wing')]
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
    if len(args) != 3:
        raise SystemExit(__doc__)
    convert(*args, keep_glass='--keep-glass' in sys.argv, badges=badges, liveries=liveries, stock_wing='--no-stock-wing' not in sys.argv)
