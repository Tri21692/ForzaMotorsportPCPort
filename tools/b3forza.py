"""A Burnout 3: Takedown car (tools/b3car.py's OBJ of the intact car) as a Forza add-on body, through
nfsu2forza.py: the OBJ's groups are made into the Most Wanted-shaped parts the converter takes (as
cartoolkit.py does for NFS-CarToolkit cars), with textures cut from the car's one atlas.

  python tools/b3forza.py template <disc> <car> <folder>
      the template's cab folder (car.carbin, liveries), physics/maxdata.xml, tooldata.xml and its stock
      wheel (tire.carbin, wheel.xpr) from the disc, into <folder>
  python tools/b3forza.py convert <car.obj> <template car.carbin> <out car.carbin> [--fit length|width] [--canvas N]
                         [--lower M] [--widen F] [--scale F] [--arches cf,cr[,hf,hr]] [nfsu2forza options]
      the body; with --liveries <template .liveries.bin> the paint shop's copy too (liveries.bin). The arches go to
      the template's hubs from the OBJ's _wheels.txt, and the body's height puts the Burnout hubs at the template's
      (its tyres and ride height, from the template folder's tooldata.xml and maxdata.xml) unless --lower is given.
      --fit width: scaled to the template body's width (a longer race template), else to its length
  python tools/b3forza.py wheel <car.obj> <tire.carbin> <wheel.xpr> <out tire.carbin> <out wheel.xpr>
      the Burnout wheel's rim on the template's wheel (nfsu2forza --wheel), from b3car --parts' wheelmesh7
      (the modelled spokes) when it is beside the OBJ in parts/, else the placed front-left wheel
  python tools/b3forza.py pack <template cab> <out folder> <out cab> [colours] [--no-engine-audio]
      a copy of the template's cab with the new car.carbin, both livery atlases (livery0: plain paint,
      livery1: the Burnout scheme) and stock liveries; colours: "scheme:r,g,b" (livery1, its graphics
      over that paint) or "r,g,b" (plain), comma-joined with ";", the first the car's own; or "fixed:r,g,b" alone: a
      race car's one look (it has no paint shop): the scheme's atlases as livery0, no livery1, that paint under it.
      --no-engine-audio: the template's engine sound left out (for addcar.py --engine-like, which adds the donor's)

The OBJ (b3car.py): metres, +y up, +z forward, +x the car's left; one group per material: body_paint, body_trim,
body_under, body_headlight, body_brakelight, body_taillight, body_reverselight, body_indicator_l/_r,
body_glass (and wheel_* groups, not used for the body). Burnout's paint is in its texture (Car21: green, with
blue pixel-art graphics), one 512 x 256 atlas for everything.

What goes where (Most Wanted's names, which nfsu2forza.py maps to the template's slots):
  KIT00_BODY      the shell: the paint groups, its black trim and underside (on the template's black
                  texel) and its textured trim (grilles, vents, door cards, dashboard, indicators), each
                  piece of the atlas it uses cut out and packed into the livery atlas (BADGING: drawn as it is)
  BASE            the Burnout car's seats (pieces of their own in the cabin): the template's interior is
                  not fitted in (nfsu2forza OWN_INTERIOR), the car keeps its own; its steering wheel (a piece
                  of the underside group in the cabin) is left out for the template's
  KIT00_SPOILER   the wing: pieces at the tail above the boot (the stock wing; the shop's "No Wing" drops it)
  KIT00_LEFT/RIGHT_SIDE_MIRROR   the mirrors: small pieces at the car's widest, by the A pillars
  KIT00_FRONT/REAR_WINDOW, KIT00_FRONT/REAR_LEFT/RIGHT_WINDOW   the glass, by facing and piece
  KIT00_LEFT/RIGHT_HEADLIGHT     headlights (lit as Forza's headlights)
  KIT00_LEFT/RIGHT_BRAKELIGHT    brake, tail and reverse lights
  Every part at all four detail levels (the same mesh: a Burnout car is a few thousand triangles).

The livery: the paint groups keep their own coordinates on the atlas, a livery sheet (nfsu2forza SKIN, the
atlas in the sheet's top half), cut into islands packed into the template's atlas. livery0 is the plain car:
there the sheet's green is paint, its darker texels the paint darkened (vents, shut lines, shadows), its
graphics gone. livery1 is the Burnout scheme: the same, with the graphics (blue and their dark edges) opaque,
so they stay blue whatever the paint; with the green as the paint it is the car as Burnout draws it.
"""
import collections
import os
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cartoolkit
import nfsu
import nfsu2forza

PREFIX = 'BURNOUT'  # the parts' and textures' names (the staged folder's name)
SKIN_NAME = PREFIX + '_SKIN2'
LIFT = 1.5  # metres every part is raised before the converter takes it (see convert)
B = '\\'


# ---- the OBJ

def read_obj(path):
    """Positions, texture coordinates, normals and {group: [(corner, corner, corner)]}, a corner (p, t, n) indices."""
    P, T, N, groups, cur = [], [], [], {}, None
    for line in open(path):
        w = line.split()
        if not w: continue
        if w[0] == 'v': P.append(tuple(map(float, w[1:4])))
        elif w[0] == 'vt': T.append(tuple(map(float, w[1:3])))
        elif w[0] == 'vn': N.append(tuple(map(float, w[1:4])))
        elif w[0] == 'g': cur = w[1]; groups.setdefault(cur, [])
        elif w[0] == 'f':
            cs = [tuple(int(x) - 1 if x else -1 for x in (c.split('/') + ['', ''])[:3]) for c in w[1:]]
            for k in range(1, len(cs) - 1): groups[cur].append((cs[0], cs[k], cs[k + 1]))
    return np.array(P, float), np.array(T, float), np.array(N, float), groups


class Car:
    def __init__(self, obj):
        self.P, self.T, self.N, self.groups = read_obj(obj)
        self.atlas_path = os.path.splitext(obj)[0] + '_opaque.png'
        from PIL import Image
        self.A = np.asarray(Image.open(self.atlas_path).convert('RGB'))  # 256 x 512 (rows, columns)
        self.H, self.W = self.A.shape[:2]

    def corner(self, c, uv=None):
        """A corner as Most Wanted's vertex (nfsu): x forward, y left, z up; u, v (v down the image)."""
        p, t, n = c
        x, y, z = self.P[p]
        nx, ny, nz = self.N[n] if n >= 0 else (0.0, 1.0, 0.0)
        u, v = uv if uv is not None else (self.T[t][0], 1 - self.T[t][1])
        return (z, x, y, nz, nx, ny, 0xFFFFFFFF, float(u), float(v))

    def uv_px(self, c):
        """A corner's place on the atlas in texels (x, y)."""
        u, v = self.T[c[1]]
        return u * self.W, (1 - v) * self.H


def pieces(car, names):
    """The triangles of these groups, as (group, triangle), and their connected pieces (welded by position, 1 mm),
    largest first, each a list of indices into the first."""
    tris = [(g, t) for g in names for t in car.groups.get(g, ())]
    key, wid = {}, []
    for p in car.P:
        wid.append(key.setdefault(tuple(np.round(p / 0.001).astype(int)), len(key)))
    par = list(range(len(key)))
    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    for _, t in tris:
        a, b, c = (find(wid[q[0]]) for q in t)
        par[b] = a; par[find(c)] = a
    comp = collections.defaultdict(list)
    for k, (_, t) in enumerate(tris): comp[find(wid[t[0][0]])].append(k)
    return tris, sorted(comp.values(), key=len, reverse=True)


def classify(car):
    """Each body triangle's place: (part, group, triangle) for the parts above, the dropped ones left out."""
    groups = [g for g in car.groups if g.startswith('body_')]
    tris, comps = pieces(car, groups)
    allp = car.P[[q[0] for _, t in tris for q in t]]
    xmax, ymax = np.abs(allp[:, 0]).max(), allp[:, 1].max()
    zmin, zmax = allp[:, 2].min(), allp[:, 2].max()
    where = {}
    for ci, ks in enumerate(comps):
        Q = car.P[[q[0] for k in ks for q in tris[k][1]]]
        gs = {tris[k][0] for k in ks}
        what = 'body'
        if ci == 0: pass
        elif Q[:, 2].max() < zmin + 0.5 and Q[:, 1].min() > 0.6 * ymax:
            what = 'spoiler'
        elif np.abs(Q[:, 0]).max() > 0.9 * xmax and len(ks) < 120 and np.abs(Q[:, 2]).max() < 1.0 and Q[:, 1].min() > 0.4 * ymax:
            what = 'mirrorL' if Q[:, 0].mean() > 0 else 'mirrorR'
        elif (gs <= {'body_trim', 'body_under'} and np.abs(Q[:, 0]).max() < 0.85 * xmax and Q[:, 1].min() > -0.05
              and Q[:, 1].max() < 0.92 * ymax and Q[:, 2].min() > zmin + 0.8 and Q[:, 2].max() < zmax - 1.1):
            what = 'drop' if gs == {'body_under'} else 'cabin'  # (Car21: its steering wheel and column, of the underside's texture)
        for k in ks: where[k] = (what, ci)
        if ci and what != 'body':
            print('piece %d: %d triangles, %s (x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f)' % (ci, len(ks), what, Q[:, 0].min(), Q[:, 0].max(),
                                                                                       Q[:, 1].min(), Q[:, 1].max(), Q[:, 2].min(), Q[:, 2].max()))
    out = []
    for k, (g, t) in enumerate(tris):
        what, ci = where[k]
        if what == 'drop': continue
        c = car.P[[q[0] for q in t]].mean(0)
        if g == 'body_glass':
            n = car.N[[q[2] for q in t]].mean(0) if t[0][2] >= 0 else np.zeros(3)
            side = 'LEFT' if c[0] > 0 else 'RIGHT'
            if abs(n[0]) > 0.55 * np.linalg.norm(n):  # side glass: the door's (in the shell) or a rear quarter's (a piece of its own)
                part = ('FRONT_%s_WINDOW' if ci == 0 else 'REAR_%s_WINDOW') % side
            else:
                part = 'FRONT_WINDOW' if c[2] > 0 else 'REAR_WINDOW'
        elif g == 'body_headlight':
            part = 'LEFT_HEADLIGHT' if c[0] > 0 else 'RIGHT_HEADLIGHT'
        elif g in ('body_brakelight', 'body_taillight', 'body_reverselight'):
            part = 'LEFT_BRAKELIGHT' if c[0] > 0 else 'RIGHT_BRAKELIGHT'
        else:
            part = {'body': 'BODY', 'cabin': 'BASE', 'spoiler': 'SPOILER', 'mirrorL': 'LEFT_SIDE_MIRROR', 'mirrorR': 'RIGHT_SIDE_MIRROR'}[what]
        out.append((part, g, t))
    return out


# ---- textures cut from the atlas

def label(mask):
    """4-connected pieces of a boolean image: an int image, -1 outside."""
    lab = np.full(mask.shape, -1, int)
    n = 0
    H, W = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0] >= 0: continue
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and lab[yy, xx] < 0:
                    lab[yy, xx] = n; stack.append((yy, xx))
        n += 1
    return lab


def raster(car, tris, grow=2):
    """The atlas texels these triangles cover, grown by `grow`."""
    sq = np.zeros((car.W, car.W), bool)  # (uv_raster wants a square)
    for t in tris:
        q = np.array([car.uv_px(c) for c in t])
        nfsu2forza.uv_raster(sq, q)
        for x, y in np.vstack([q, q.mean(0, keepdims=True)]):  # (its corners and middle too: a sliver covers no texel's centre)
            sq[min(car.H - 1, int(y)), min(car.W - 1, int(x))] = True
    mask = sq[:car.H].copy()
    for _ in range(grow):
        g = mask.copy()
        g[1:] |= mask[:-1]; g[:-1] |= mask[1:]; g[:, 1:] |= mask[:, :-1]; g[:, :-1] |= mask[:, 1:]
        mask = g
    return mask


def crop_texture(car, box, name, minimum=0, gain=1.0, floor=0):
    """The atlas's texels in box (x0, y0, x1, y1), even-sized, at least 8 (and `minimum` at its longest side: a lamp
    sheet of 32 or less is taken for its glass), as an nfsu texture (BGRA, opaque), and the map from atlas texels to its
    u, v (the converter puts u 0..1 on its first to last texel centre in the 1024 atlas, where it lands 1:1). gain:
    the texels brightened (Burnout's lamp texels are dark, lit when drawn; Forza's lamp texels are the lit colours).
    floor: none darker (nfsu2forza makes a tail-light triangle whose corners are all near black (under 24) black trim:
    Car21's lamp quads have their corners on the black frame round each segment of its lamp strip)."""
    x0, y0, x1, y1 = box
    f = 1
    while max(x1 - x0, y1 - y0) * f <= minimum: f += 1
    step = 2
    while max(x1 - x0, y1 - y0) * f > 128 * step // 2: step *= 2  # (the converter halves a sheet over 128 until it is not: even each time)
    def widen(a, b, size, lim):
        while b - a < size or (b - a) * f % step:
            if b < lim: b += 1
            elif a > 0: a -= 1
            else: break
        return a, b
    x0, x1 = widen(x0, x1, 8, car.W)
    y0, y1 = widen(y0, y1, 8, car.H)
    img = np.clip(car.A[y0:y1, x0:x1] * gain, floor, 255).astype(np.uint8)
    img = img.repeat(f, 0).repeat(f, 1)
    h, w = img.shape[:2]
    bgra = np.concatenate([img[..., ::-1], np.full((h, w, 1), 255, np.uint8)], -1)
    tex = {'name': name, 'width': w, 'height': h, 'fourcc': 'BGRA', 'data': np.ascontiguousarray(bgra).tobytes()}
    def to_uv(px, py):
        return (f * (px - x0) - 1) / (w - 2), (f * (py - y0) - 1) / (h - 2)
    return tex, to_uv


def dark(car, t, limit=30):
    """Whether a triangle's texels (its corners, middle and edge middles) are all near black."""
    q = np.array([car.uv_px(c) for c in t])
    pts = np.vstack([q, q.mean(0, keepdims=True), (q + np.roll(q, 1, 0)) / 2])
    xs = np.clip(pts[:, 0].astype(int), 0, car.W - 1); ys = np.clip(pts[:, 1].astype(int), 0, car.H - 1)
    return car.A[ys, xs].max() < limit


# ---- the parts

def build_parts(car):
    """The Most Wanted-shaped parts (cartoolkit.as_part) and their textures ({hash: nfsu texture})."""
    placed = classify(car)
    textures = {}
    # the livery sheet: the atlas in its top half, the rest its commonest colour (the paint)
    px = np.array([car.uv_px(c) for p, g, t in placed if g == 'body_paint' for c in t]).astype(int)
    texels = car.A[np.clip(px[:, 1], 0, car.H - 1), np.clip(px[:, 0], 0, car.W - 1)]  # (what the paint's corners take: Car21's green)
    q = (texels // 16).astype(int)
    q = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
    plain = texels[q == np.bincount(q.ravel()).argmax()].mean(0)
    print('paint: the plain colour of the sheet %s' % np.round(plain).astype(int).tolist())
    sheet = np.tile(np.round(plain).astype(np.uint8), (car.W, car.W, 1))
    sheet[:car.H] = car.A
    textures[nfsu.bhash(SKIN_NAME)] = {'name': SKIN_NAME, 'width': car.W, 'height': car.W, 'fourcc': 'BGRA',
                                       'data': np.concatenate([sheet[..., ::-1], np.full((car.W, car.W, 1), 255, np.uint8)], -1).tobytes()}
    skin = nfsu.bhash(SKIN_NAME)

    # textured trim: the atlas's pieces it covers, each a texture
    lamp_groups = ('body_headlight', 'body_brakelight', 'body_taillight', 'body_reverselight')
    trim = [(p, g, t) for p, g, t in placed if g in ('body_trim', 'body_under')]
    black = [(p, g, t) for p, g, t in trim if dark(car, t)]
    shown = []  # (part, triangle, texture, its u, v)
    for key, items, gain in (('T', [x for x in trim if not dark(car, x[2])], 1.0),
                             ('I', [x for x in placed if x[1] in ('body_indicator_l', 'body_indicator_r')], 2.2)):
        lab = label(raster(car, [t for _, _, t in items]))
        cuts = {}
        for i in range(lab.max() + 1):
            ys, xs = np.nonzero(lab == i)
            name = '%s_BADGING_%s%02d' % (PREFIX, key, i)
            tex, to_uv = crop_texture(car, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), name, gain=gain)
            textures[nfsu.bhash(name)] = tex
            cuts[i] = (nfsu.bhash(name), to_uv)
        for p, g, t in items:
            q = np.array([car.uv_px(c) for c in t]).mean(0)
            x, y = min(car.W - 1, int(q[0])), min(car.H - 1, int(q[1]))
            win = lab[max(0, y - 3):y + 4, max(0, x - 3):x + 4]
            shown.append((p, t) + cuts[int(lab[y, x]) if lab[y, x] >= 0 else int(win.max())])
        print('%s: %d triangles drawn from %d pieces of the atlas' % ('trim' if key == 'T' else 'indicators', len(items), len(cuts)))
    print('trim: %d triangles black' % len(black))

    # lamps: one sheet each kind, the box of its triangles' texels, brightened to a lit lamp's (Car21's brake lights
    # are 82, 47, 51 at their brightest twentieth: drawn so they were dark smoked shells); the indicators (above) are
    # drawn as they are (BADGING, unlit), brightened as well
    lamps = {}
    for kind, gs, mat, gain in (('HEADLIGHT', ('body_headlight',), 'LEFT_HEADLIGHT_BULB', 1.6),
                                ('BRAKELIGHT', ('body_brakelight', 'body_taillight', 'body_reverselight'), 'BRAKELIGHT', 2.0)):
        ts = [t for p, g, t in placed if g in gs]
        if not ts: continue
        m = raster(car, ts, grow=1)
        ys, xs = np.nonzero(m)
        name = '%s_KIT00_%s_ON' % (PREFIX, kind)
        tex, to_uv = crop_texture(car, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), name, minimum=40, gain=gain, floor=30)
        textures[nfsu.bhash(name)] = tex
        lamps[gs] = (mat, nfsu.bhash(name), to_uv)

    groups = collections.defaultdict(list)  # part -> [(material, texture, triangle as nfsu vertices)]
    for p, g, t in placed:
        if g == 'body_paint':
            tri = tuple(car.corner(c, (car.T[c[1]][0], (1 - car.T[c[1]][1]) * car.H / car.W)) for c in t)  # (on the sheet: the atlas its top half)
            groups[p].append(('BODY', skin, tri))
        elif g == 'body_glass':
            groups[p].append(('WINDOW_FRONT', 0, tuple(car.corner(c, (0.5, 0.5)) for c in t)))
        elif g in lamp_groups:
            mat, th, to_uv = next(v for k, v in lamps.items() if g in k)
            groups[p].append((mat, th, tuple(car.corner(c, to_uv(*car.uv_px(c))) for c in t)))
    for p, t, th, to_uv in shown:
        groups[p].append(('BADGING', th, tuple(car.corner(c, to_uv(*car.uv_px(c))) for c in t)))
    for p, g, t in black:
        groups[p].append(('BODY_BLACK', 0, tuple(car.corner(c, (0.5, 0.5)) for c in t)))

    parts = []
    for p, items in sorted(groups.items()):
        merged = collections.OrderedDict()  # one group a material and texture
        for mat, th, tri in items: merged.setdefault((mat, th), []).append(tri)
        name = '%s_%s' % (PREFIX, p if p == 'BASE' else 'KIT00_' + p)
        part = cartoolkit.as_part(name + '_A', [(m, th, ts) for (m, th), ts in merged.items()])
        print('%s: %d triangles, %d vertices, %s' % (name, len(part['tris']), len(part['verts']),
                                                     ', '.join('%s %d' % (m, len(ts)) for (m, _), ts in merged.items())))
        for k, lv in enumerate('ABCD'):  # (every detail level the same mesh: the converter shares its vertices)
            q = dict(part, name=name + '_' + lv)
            if k and (p == 'BASE' or p.endswith('LIGHT')):
                # (but for the parts that share a slot with others, the template's body (with the TT the seats and
                # every lamp): there a level the same as the first copies all of that slot's first level, and the
                # far levels drew the lamps and seats up to five times over. A level of their own: an unused vertex
                # more, dropped when built)
                q['verts'] = part['verts'] + [part['verts'][0]] * k
            parts.append(q)
    return parts, textures


# ---- the two liveries (nfsu2forza.bake_canvas's place)

def sheets(vinyl, plain):
    """The livery sheet (canvas size, RGB float) as livery0's and livery1's rooms (RGBA): the paint's shade
    (texel brightness over the paint colour's, grey, clear) everywhere; livery1 with the graphics (blue and its
    dark edging) opaque, livery0 with them and their edging made plain paint."""
    lum = vinyl @ np.array([0.299, 0.587, 0.114])
    shade = np.clip(lum / max(1.0, float(np.dot(plain, [0.299, 0.587, 0.114]))), 0, 1) * 255
    r, g, b = vinyl[..., 0], vinyl[..., 1], vinyl[..., 2]
    blue = (b > r + 30) & (b > g - 10) & (b > 40)
    def grow(m, n):
        for _ in range(n):
            m2 = m.copy(); m2[1:] |= m[:-1]; m2[:-1] |= m[1:]; m2[:, 1:] |= m[:, :-1]; m2[:, :-1] |= m[:, 1:]; m = m2
        return m
    edge = (b > r + 8) & (b >= g) & grow(blue, 2)  # (the graphics' dark blue drop shadow)
    art = blue | edge
    s0 = np.zeros(vinyl.shape[:2] + (4,)); s0[..., :3] = shade[..., None]
    s1 = s0.copy()
    s0[grow(blue, 3), :3] = 255
    s1[art, :3] = vinyl[art]; s1[art, 3] = 255
    print('liveries: %d texels of graphics (livery1), the paint shaded elsewhere' % art.sum())
    return s0, s1


def bake_rooms(sheet, rooms, livery_dir, src, dst):
    """bake_canvas with alpha: the rooms of livery <src>'s three atlases (rect, band as canvas_bands gives them) given
    the sheet's texels (RGBA, canvas size), written as livery <dst>."""
    import forzaxpr as fx
    names = ('nc', '', 'hi')
    files = {n: bytearray(open(os.path.join(livery_dir, '%s%s.xpr' % (src, n)), 'rb').read()) for n in names}
    nc, vol, hi = (fx.textures(files[n])[0] for n in names)
    W, H, D = nc['w'], nc['h'], nc['d']
    def put(img, size):
        for (u0, v0, u1, v1), (r0, r1, c0, c1) in rooms:
            part = sheet[r0:r1, c0:c1]
            x0, y0 = int(round(u0 * size - 0.5 * size / W)), int(round(v0 * size - 0.5 * size / W))
            x1, y1 = int(round(u1 * size + 0.5 * size / W)), int(round(v1 * size + 0.5 * size / W))
            f = part.shape[0] // (y1 - y0)
            if f > 1:
                v = part.reshape(part.shape[0] // f, f, part.shape[1] // f, f, 4).mean((1, 3))
            else:
                ys = ((np.arange(y0, y1) - y0 + 0.5) / (y1 - y0) * part.shape[0]).astype(int)
                xs = ((np.arange(x0, x1) - x0 + 0.5) / (x1 - x0) * part.shape[1]).astype(int)
                v = part[ys][:, xs]
            e = 2 * size // W
            img[y0 - e:y1 + e, x0 - e:x1 + e] = np.pad(v, ((e, e), (e, e), (0, 0)), mode='edge')
    hiimg = fx.dxt(bytes(files['hi'][hi['start']:]), 2 * W, 2 * H, 5).astype(float)
    put(hiimg, 2 * W)
    level, off, sz = hiimg, hi['start'], 2 * W
    for lv in range(hi['mips']):
        if lv: level = level.reshape(sz, 2, sz, 2, 4).mean((1, 3))
        img = np.clip(level + 0.5, 0, 255).astype(np.uint8)
        if sz < 4: img = np.pad(img, ((0, 4 - sz), (0, 4 - sz), (0, 0)), mode='edge')
        enc = fx.encode_dxt5(np.ascontiguousarray(img))
        files['hi'][off:off + len(enc)] = enc
        off += max(1, sz // 4) ** 2 * 16
        sz = max(1, sz // 2)
    sw = fx.unswizzle_index(W, H, D)
    raw = np.frombuffer(bytes(files['nc'][nc['start']:nc['start'] + W * H * D * 4]), np.uint8).reshape(-1, 4).copy()
    ncimg = raw[sw][..., [2, 1, 0, 3]].astype(float)
    n = (W // 4) * (H // 4)
    vblocks = np.frombuffer(bytes(files[''][vol['start']:vol['start'] + n * D * 16]), np.uint8).reshape(n, D, 16).copy()
    for z in range(D):  # the clean slice and the damaged one alike
        put(ncimg[z], W)
        vimg = fx.dxt(vblocks[:, z].tobytes(), W, H, 5).astype(float)
        put(vimg, W)
        vblocks[:, z] = np.frombuffer(fx.encode_dxt5(np.ascontiguousarray(np.clip(vimg + 0.5, 0, 255).astype(np.uint8))), np.uint8).reshape(n, 16)
    raw[sw.reshape(-1)] = np.clip(ncimg + 0.5, 0, 255).astype(np.uint8)[..., [2, 1, 0, 3]].reshape(-1, 4)
    files['nc'][nc['start']:nc['start'] + raw.size] = raw.tobytes()
    files[''][vol['start']:vol['start'] + vblocks.size] = vblocks.tobytes()
    for n_ in names:
        open(os.path.join(livery_dir, '%s%s.xpr' % (dst, n_)), 'wb').write(files[n_])


def hook_liveries():
    """nfsu2forza's SKIN bake replaced: livery0's rooms shaded (then the paint shop's copy made from it, its rooms
    paint), livery1 the scheme."""
    later = {}
    real_shop = nfsu2forza.paint_shop
    def paint_shop(*a, **k):
        later['shop'] = (a, k)
    def bake(vinyl, base, rooms, livery_dir):
        s0, s1 = sheets(np.asarray(vinyl, float), np.asarray(base, float))
        bake_rooms(s0, rooms, livery_dir, 'livery0', 'livery0')
        if 'shop' in later:
            a, k = later['shop']
            paint = k.get('paint')
            mask = np.zeros((1024, 1024), bool) if paint is None else np.array(paint, bool)
            for (u0, v0, u1, v1), _ in rooms:  # (the rooms are paint: a repaint reaches them)
                mask[int(v0 * 1024):int(np.ceil(v1 * 1024)) + 1, int(u0 * 1024):int(np.ceil(u1 * 1024)) + 1] = True
            real_shop(*a, **dict(k, paint=mask))
        bake_rooms(s1, rooms, livery_dir, 'livery0', 'livery1')
    nfsu2forza.paint_shop = paint_shop
    nfsu2forza.bake_canvas = bake


# ---- commands

def stage(made, textures, folder):
    """nfsu.read and read_textures give these for the staged folder (no files are read there)."""
    os.makedirs(folder, exist_ok=True)
    for n in ('GEOMETRY.BIN', 'TEXTURES.BIN'):
        open(os.path.join(folder, n), 'wb').close()
    here = os.path.normcase(os.path.abspath(folder))
    real_read, real_tex = nfsu.read, nfsu.read_textures
    nfsu.read = lambda path: made if os.path.normcase(os.path.dirname(os.path.abspath(path))) == here else real_read(path)
    nfsu.read_textures = lambda path: dict(textures) if os.path.normcase(os.path.dirname(os.path.abspath(path))) == here else real_tex(path)


def convert(argv):
    obj, template, out = argv[:3]
    rest = list(argv[3:])
    def opt(name, conv, default):
        if name in rest:
            i = rest.index(name); v = rest[i + 1]; del rest[i:i + 2]; return conv(v)
        return default
    canvas = opt('--canvas', int, 512)
    lower = opt('--lower', float, None)
    nfsu2forza.WIDEN = opt('--widen', float, 1.0)
    nfsu2forza.SCALE = opt('--scale', float, 1.0)
    fit = opt('--fit', str, 'length')
    nfsu2forza.FIT_WIDTH = fit == 'width'
    arches = opt('--arches', lambda s: [float(x) for x in s.split(',')], None)
    if arches: os.environ['NFSU_ARCHES'] = ','.join(map(str, arches))
    car = Car(obj)
    made, textures = build_parts(car)
    # Everything lifted LIFT m (the fit takes the lowest point, so nothing moves): nfsu2forza.convert's build() drops a
    # triangle lower than `floor` - 0.03, meant as the source body's lowest point, but by the time build() runs
    # `floor` has been set again to the template body's lowest point in carbin units (its fit_cabin's floor). On the
    # race TT (lowest point 0.24) that cut the Burnout car's lower front bumper and intakes away, on the street TT its
    # bottom 6 cm. Lifted, no source point is under any template's floor. (Not fixed in the converter: it would change
    # the cars already converted.)
    for p in made:
        p['verts'] = [tuple(v[:2]) + (v[2] + LIFT,) + tuple(v[3:]) for v in p['verts']]
    # The fit as the converter makes it (its scale k, forward and up offsets), for the arches and the ride height
    import carbin
    tb = next(p for p in carbin.read(open(template, 'rb').read())['parts'] if p['name'].startswith('body'))
    tx, ty, tz = ([v[i] / 4096 for v in tb['verts']] for i in range(3))
    nb = [v for p in made if p['name'] in (PREFIX + '_KIT00_BODY_A', PREFIX + '_BASE_A') for v in p['verts']]
    nx, ny, nz = ([v[i] for v in nb] for i in range(3))
    if fit == 'width':  # (a race template longer than the Burnout car: its width, the length following the hubs)
        k = (max(tx) - min(tx)) / (max(ny) - min(ny))
    else:
        k = (max(tz) - min(tz)) / (max(nx) - min(nx))
    k *= nfsu2forza.SCALE
    dz = (max(tz) + min(tz)) / 2 - k * (max(nx) + min(nx)) / 2
    hubs_txt = os.path.splitext(obj)[0] + '_wheels.txt'
    hz = {}
    if os.path.exists(hubs_txt):
        for line in open(hubs_txt):
            w = line.split()
            if len(w) > 4 and w[1] == 'centre': hz.setdefault(w[0][0], []).append(float(w[4]))
    if not arches and hz:
        # The arches where the Burnout wheels' hubs are (b3car's _wheels.txt), as the fit puts them: read off the
        # sides' lower edge they came out 0.2 m long at each end (the kit's flared arches), and the wheelbase was
        # squeezed 13%
        arches = [k * np.mean(hz['F']) + dz, k * np.mean(hz['R']) + dz]
        os.environ['NFSU_ARCHES'] = ','.join('%.4f' % a for a in arches)
        print('wheels: the Burnout hubs at %.3f, %.3f m, %.3f, %.3f as fitted' % (np.mean(hz['F']), np.mean(hz['R']), *arches))
    tdir = os.path.dirname(os.path.abspath(template))
    mx, td = os.path.join(tdir, 'physics', 'maxdata.xml'), os.path.join(tdir, 'tooldata.xml')
    if lower is None and hz and os.path.exists(mx) and os.path.exists(td):
        # The body as high as puts the Burnout hubs (its model's y 0) at the template's (its stock tyres' radius
        # over its stock ride height): the converter sets the lowest points level, the template's floor
        md, t = open(mx, encoding='latin-1').read(), open(td, encoding='latin-1').read()
        ride = np.mean([float(re.search(r'%sStockRideHeight="([^"]+)"' % e, md).group(1)) for e in ('Front', 'Rear')])
        lvl = int(re.search(r'<Tire StockLevel="(\d+)"', t).group(1))
        blk = re.search(r'<Tire StockLevel.*?<L%d[^>]*>(.*?)</L%d>' % (lvl, lvl), t, re.S).group(1)
        def dia(which):
            a_ = dict(re.findall(r'(\w+)="([^"]+)"', re.search(r'<%s ([^>]*)/>' % which, blk).group(1)))
            return (float(a_['WheelDiameter']) * 25.4 + 2 * float(a_['TireWidth']) * float(a_['TireRatio']) / 100) / 1000
        hub = (np.mean([dia('Fronts'), dia('Rears')]) / 2 - ride) * 1.602
        lower = (min(ty) - k * min(nz)) - (hub - k * LIFT)  # (the Burnout hubs at y 0, lifted)
        print('ride: the template hubs %.3f up (tyres %.3f, %.3f m, ride %.3f m): the body %.3f lower than its floor' % (hub, dia('Fronts'), dia('Rears'), ride, lower))
    nfsu2forza.LOWER = lower or 0.0
    folder = os.path.join(os.path.dirname(os.path.abspath(out)), 'src', PREFIX)
    stage(made, textures, folder)
    nfsu2forza.SKIN, nfsu2forza.CANVAS_SIZE = (SKIN_NAME, canvas), canvas
    nfsu2forza.OWN_INTERIOR = True  # (the Burnout car's own cabin in its body; the template's interior slot left empty)
    hook_liveries()
    if '--clear-livery' not in rest: rest.append('--clear-livery')
    nfsu2forza.main([sys.argv[0], template, folder, out] + rest)


def wheel(argv):
    """The Burnout wheel's rim (the spokes inside the tyre's bead, on the outer side) as Most Wanted's KIT00_FRONT_TIRE
    with RIM groups, its texture the atlas's box of them squared to 256, for nfsu2forza.convert_wheel."""
    obj, tire, xpr, out_tire, out_xpr = argv[:5]
    parts_obj = os.path.join(os.path.dirname(obj), 'parts', os.path.basename(obj))
    car = Car(obj)
    src = Car(parts_obj) if os.path.exists(parts_obj) else None
    if src and src.groups.get('wheelmesh7_trim'):
        c, tris, centre = src, src.groups['wheelmesh7_trim'], np.zeros(3)
    else:
        c, tris = car, car.groups['wheel_FL_trim']
        centre = car.P[[q[0] for t in tris for q in t]].mean(0)
    V = c.P - centre
    r = np.hypot(V[:, 1], V[:, 2])
    out_side = V[[q[0] for t in tris for q in t], 0].min()  # (b3car: the hub face on -x)
    R = r[[q[0] for t in tris for q in t]].max()
    rim = [t for t in tris if max(r[q[0]] for q in t) < 0.76 * R and min(V[q[0], 0] for q in t) < out_side + 0.6 * (0 - out_side)]
    print('wheel: %d of %d triangles are the rim (inside %.3f m of the hub, radius %.3f)' % (len(rim), len(tris), 0.76 * R, R))
    pts = np.array([c.uv_px(q) for t in rim for q in t])
    x0, y0 = np.floor(pts.min(0)).astype(int); x1, y1 = np.ceil(pts.max(0)).astype(int)
    from PIL import Image
    img = np.asarray(Image.fromarray(c.A[y0:y1, x0:x1]).resize((256, 256), Image.LANCZOS))
    name = PREFIX + '_RIM'
    tex = {'name': name, 'width': 256, 'height': 256, 'fourcc': 'BGRA',
           'data': np.concatenate([img[..., ::-1], np.full((256, 256, 1), 255, np.uint8)], -1).tobytes()}
    def corner(q):
        px, py = c.uv_px(q)
        x, y, z = V[q[0]]
        n = c.N[q[2]] if q[2] >= 0 else np.array([-1.0, 0, 0])
        return (z, x, y, n[2], n[0], n[1], 0xFFFFFFFF, (px - x0) / (x1 - x0), (py - y0) / (y1 - y0))  # (nfsu: axle along y, outer face low y)
    part = cartoolkit.as_part(PREFIX + '_KIT00_FRONT_TIRE_A', [('RIM_KIT00_SILVER', nfsu.bhash(name), [tuple(corner(q) for q in t) for t in rim])])
    folder = os.path.join(os.path.dirname(os.path.abspath(out_tire)), 'src', PREFIX)
    stage([part], {nfsu.bhash(name): tex}, folder)
    nfsu2forza.convert_wheel(tire, xpr, folder, out_tire, out_xpr)


def template(argv):
    """The template car's files from the disc: its cab's cars\\<car>\\ folder, physics\\maxdata.xml (Cars.ca2) and stock
    wheel (tires\\art\\<File>\\tire.carbin in Mega.ca2, wheel.xpr in MegaXPR.ca2)."""
    import addcar, forzacab
    disc, name, folder = argv[:3]
    d, _, es = forzacab.read(os.path.join(disc, 'media', 'cabs', 'car_%s.cab' % name.lower()))
    pre = 'cars' + B + name.lower() + B
    n = 0
    for e in es:
        k = e['name'].replace('/', B)
        if not k.lower().startswith(pre): continue
        p = os.path.join(folder, *k[len(pre):].split(B))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(forzacab.data(d, e)); n += 1
    nomods = os.path.join(folder, '_no_mods_')  # (the disc's archives only)
    cars = addcar.Archive(disc, nomods, 'Cars.ca2')
    def get(files, rel):
        k = next((k for k in files if k.lower() == rel.lower()), None)
        return bytes(files[k]) if k else None
    mx = get(cars.files, pre + 'physics' + B + 'maxdata.xml')
    os.makedirs(os.path.join(folder, 'physics'), exist_ok=True)
    open(os.path.join(folder, 'physics', 'maxdata.xml'), 'wb').write(mx)
    open(os.path.join(folder, 'tooldata.xml'), 'wb').write(get(cars.files, pre + 'tooldata.xml'))  # (its tyres: the ride height)
    td = get(cars.files, pre + 'tooldata.xml').decode('latin-1')
    wf = re.search(r'<WheelStyle>\s*<P0 [^>]*File="([^"]*)"', td).group(1)
    mega, megax = addcar.Archive(disc, nomods, 'Mega.ca2'), addcar.Archive(disc, nomods, 'MegaXPR.ca2')
    os.makedirs(os.path.join(folder, 'wheel'), exist_ok=True)
    for files, f in ((mega.files, 'tire.carbin'), (megax.files, 'wheel.xpr')):
        open(os.path.join(folder, 'wheel', f), 'wb').write(get(files, B.join(('tires', 'art', wf, f))))
    print('%s: %d cab files, maxdata.xml, wheel %s into %s' % (name, n, wf, folder))


LIVERY = ('<livery>\r\n    <override red=%d green=%d blue=%d texture="%s"/>\r\n    <shaders name="ShaderSettings\\%s.xml"/>\r\n'
          '    <paint>\r\n      <RedAverage value=%d/>\r\n      <GreenAverage value=%d/>\r\n      <BlueAverage value=%d/>\r\n    </paint>\r\n</livery>\r\n')


def pack(argv):
    """The template's cab with the converted body, livery0 and livery1 atlases and the stock liveries."""
    import addcar, forzacab
    tcab, out, dst = argv[:3]
    spec = argv[3] if len(argv) > 3 and not argv[3].startswith('--') else 'scheme:47,98,0;47,98,0;20,70,140;235,235,235;14,14,16;scheme:215,170,10'
    files, root = addcar.cab_files(open(tcab, 'rb').read())
    if '--no-engine-audio' in argv:  # (the template's engine sound out: addcar --engine-like brings the donor's, and two
        # engines' sounds in one cab are a suspect in the M3 GTR MW's "car is damaged", docs/research/cars.md)
        files = {k: v for k, v in files.items() if not k.lower().startswith('engines' + B)}
    pre = next(k for k in files if k.lower().endswith(B + 'car.carbin'))[:-len('car.carbin')]
    std = pre + B.join(('liveries', 'standard')) + B
    files[pre + 'car.carbin'] = open(os.path.join(out, 'car.carbin'), 'rb').read()
    fixed = spec.startswith('fixed:')
    for n in ('livery0.xpr', 'livery0hi.xpr', 'livery0nc.xpr', 'livery1.xpr', 'livery1hi.xpr', 'livery1nc.xpr'):
        if fixed and n.startswith('livery1'): continue
        src = n.replace('livery0', 'livery1') if fixed else n  # (fixed: the scheme is the car's own livery0 atlas)
        files[std + n] = open(os.path.join(out, 'liveries', 'standard', src), 'rb').read()
    old = sorted(k for k in files if k.startswith(std) and k.endswith('.livery'))
    shader = 'metallic'
    if old:  # (the template's own first paint's shader: the TT's metallic, the race TT's nonmetallic)
        m = re.search(r'ShaderSettings\\([A-Za-z]+)\.xml', files[old[0]].decode('latin-1'), re.I)
        if m: shader = m.group(1).lower()
    for k in old:
        del files[k]
    for i, item in enumerate(spec.split(';')):
        scheme = item.startswith(('scheme:', 'fixed:'))
        r, g, b = (int(x) for x in item.split(':')[-1].split(','))
        avg = (r, g, b) if not scheme else tuple(int(0.75 * c + 0.25 * a) for c, a in zip((r, g, b), (20, 70, 140)))  # (its graphics a quarter of it)
        tex = 'livery1' if item.startswith('scheme:') else 'livery0'
        files[std + 'livery%d.livery' % i] = (LIVERY % ((r, g, b, tex, shader) + avg)).encode('latin-1')
    open(dst, 'wb').write(forzacab.pack(files, root))
    print('%s: %d files, liveries %s' % (dst, len(files), spec))


if __name__ == '__main__':
    cmds = {'convert': convert, 'wheel': wheel, 'template': template, 'pack': pack}
    if len(sys.argv) < 3 or sys.argv[1] not in cmds: raise SystemExit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])
