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
  python tools/nfsu2forza.py <template car.carbin> <NFSU car folder> <out car.carbin> [--keep-glass] [--badges <folder>]

The NFSU car's windows are holes in its body: they are filled with glass
(window_panes), put in the template's glass parts. --keep-glass keeps the
template's own windows instead (they stand out of a lower roof).
--badges: a folder with logo.* (the maker's emblem, on the nose) and
model.* (the model's lettering, on the tail), any image ffmpeg
reads, used instead of the NFSU badge sheet's small ones. Your own files:
trademarks, so they stay out of anything shared.
"""
import os
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
DECAL = BADGE  # 26: draws the atlas as it is, clear texels too (25, the Civic's badges', drew nothing of these; as Body they drew a plain patch)
INSET = int(0.02 * 4096)  # how far a panel's black inside sits in from it, carbin units (about a centimetre)
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


def pack_atlas(images, livery_dir, out_dir, keep=(), pad=4):
    """Put NFSU textures ({hash: RGBA}) into free (fully clear) room of the
    template's livery atlas: livery0nc.xpr and livery0.xpr (512x512, both
    slices, clean and damaged) and livery0hi.xpr (1024x1024, every mip
    level), writing the three to out_dir. Only the 4x4 blocks touched are
    encoded again. Each texture gets `pad` texels of its own edge round it
    (filtering and mip levels would blend in the clear room). Returns
    {hash: (u0, v0, u1, v1)}, the texel centres of its corners in 0..1.
    keep: (u, v) spots (u16) that must stay as they are, such as the paint
    texel, which is clear too."""
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
    rects, where = {}, {}
    for h in sorted(images, key=lambda h: -images[h].shape[0] * images[h].shape[1]):
        img = images[h]
        th, tw = img.shape[0] + 2 * pad, img.shape[1] + 2 * pad
        th, tw = (th + 3) // 4 * 4, (tw + 3) // 4 * 4
        spot = next(((x, y) for y in range(0, H - th + 1, 4) for x in range(0, W - tw + 1, 4)
                     if not used[y:y + th, x:x + tw].any()), None)
        if spot is None: raise SystemExit('no room in the livery atlas for a %dx%d texture' % img.shape[:2])
        x, y = spot
        used[y:y + th, x:x + tw] = True
        big = np.pad(img, ((pad, th - img.shape[0] - pad), (pad, tw - img.shape[1] - pad), (0, 0)), mode='edge')
        ncimg[:, y:y + th, x:x + tw] = big
        volimg[:, y:y + th, x:x + tw] = big
        hiimg[2 * y:2 * (y + th), 2 * x:2 * (x + tw)] = big.repeat(2, 0).repeat(2, 1)
        rects[h] = (x, y, tw, th)
        ih, iw = img.shape[:2]
        where[h] = ((x + pad + 0.5) / W, (y + pad + 0.5) / H, (x + pad + iw - 0.5) / W, (y + pad + ih - 0.5) / H)
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


def convert(template_path, nfsu_dir, out_path, keep_glass=False, badges=None):
    import numpy as np
    car = carbin.read(open(template_path, 'rb').read())
    nparts = nfsu.read(os.path.join(nfsu_dir, 'GEOMETRY.BIN'))
    textures = nfsu.read_textures(os.path.join(nfsu_dir, 'TEXTURES.BIN'))
    prefix = os.path.basename(os.path.normpath(nfsu_dir)).upper()
    names = {bhash(prefix + '_SKIN1'): prefix + '_SKIN1'}
    names.update({h: t['name'] for h, t in textures.items()})

    def find(suffix):
        """The stock part's detail levels, finest first (_A to _D; some
        names are cut short, so ordered by size)."""
        found = [p for p in nparts if p['name'].startswith(prefix + '_KIT00_' + suffix)]
        return sorted(found, key=lambda p: -len(p['verts']))

    # the fit: template body vs NFSU body (+ roof)
    tbody = next(p for p in car['parts'] if p['name'].startswith('body'))
    tz = [v[2] / 4096 for v in tbody['verts']]; ty = [v[1] / 4096 for v in tbody['verts']]
    nb = find('BODY')[0]['verts'] + find('ROOF')[0]['verts']
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
    print('paint: texel at u, v = %.3f, %.3f' % (paint[0] / 65536, paint[1] / 65536))
    print('windows: black texel at u, v = %.3f, %.3f' % (dark[0] / 65536, dark[1] / 65536))
    # The NFSU car's own textures (lights, badges) go into the livery atlas,
    # written beside the output (liveries/standard).
    own = {th for key in ('BODY', 'ROOF', 'HOOD', 'TRUNK', 'FRONT_BUMPER', 'REAR_BUMPER', 'SKIRT', 'HEADLIGHT', 'BRAKELIGHT', 'LEFT_SIDE_MIRRO', 'RIGHT_SIDE_MIRR')
           for p in find(key) for th in p['textures'] if th in textures}
    livery_dir = os.path.join(os.path.dirname(template_path), 'liveries', 'standard')
    images = {h: nfsu_rgba(textures[h]) for h in own}
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
    atlas = pack_atlas(images, livery_dir,
                       os.path.join(os.path.dirname(os.path.abspath(out_path)), 'liveries', 'standard'), keep=[paint, dark])
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
    rgbas = {}

    def rgba_of(th):
        if th not in rgbas: rgbas[th] = nfsu_rgba(textures[th])
        return rgbas[th]

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
                    e1 = [vb[k] - va[k] for k in range(3)]; e2 = [vc[k] - va[k] for k in range(3)]
                    g = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                    if sum(g[k] * (va[3 + k] + vb[3 + k] + vc[3 + k]) for k in range(3)) < 0:
                        b, c = c, b  # wound against its normals (19 on the 240SX's roof): NFSU drew them anyway; here they were holes, and their black insides stood out
                    tris.append((base + a, base + b, base + c))  # the axis swap mirrors them and Forza's strips wind the other way: the two cancel
                if sh == 0x010CB64A and lod == 1:  # the inside of the wheel arches: what the cabin must stay above (fit_cabin)
                    arches.extend(tuple(pos(p['verts'][i - base]) for i in t) for t in tris)
                m = material_for(names.get(th, ''), sh)
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
                    one = 65536 if m != BADGE else BADGE_UV  # (see BADGE_UV)
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
                        verts.append(tuple(int(round(q - c * INSET / 32767)) for q, c in zip(v[:3], v[3:6]))
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
                if Qm[i] == BODY: return (255, 255, 0, 0) + paint  # one known paint texel, full shading: copied, panels near the template's windows came out black or clear
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
            body = n.startswith(('body', 'hood', 'trunk')) and n.endswith('_LOD1')
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
            hs = above[0].get((int(x // above[1]), int(z // above[1])), ())
            if hs and y > min(hs) - margin:
                return (v[0], int(round((min(hs) - margin) * 4096))) + tuple(v[2:])
            return v
        part['verts'] = [tuck(v) for v in part['verts']]
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
    plan = {k: v + (None, False)[len(v) - 2:] for k, v in plan.items()}
    built = {}
    done = []
    for part in car['parts']:
        if (part['name'].startswith('glass') and (not keep_glass or 'HL_' in part['name'])  # the template's glass stood out of a lower NFSU roof; its headlight glass never fits
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
    if not keep_glass:
        fit_glass()
    add_badges(car, textures, atlas, {k: (v.shape[1], v.shape[0]) for k, v in extra.items()})
    new_shell = shell()
    new_fit = roof(new_shell), sides(new_shell), cover(), plan_heights(arches)
    for part in car['parts']:
        if part['name'].startswith(CABIN):
            fit_cabin(part, old_fit, new_fit, floor)
            done.append(part['name'] + '(fitted)')
    # A cargo floor: black, both faces, across the hatch just under its lip,
    # from inside the tail to behind the rear seats. The S13's hatch area is
    # empty (the Civic's cabin ends at its seats), and through the rear glass
    # the inside of the body showed untextured.
    cargo = next((p for p in car['parts'] if p['name'].startswith('trunk') and p['name'].endswith('_LOD1')), None)
    rear = next((p for p in car['parts'] if p['name'].startswith('glassR_') and any(sp['indices'] != [0, 0, 0] for sp in p['subparts'])), None)
    if cargo and rear:
        G = np.array([v[:3] for v in rear['verts']], float) / 4096
        B = np.array([v[:3] for v in tbody['verts'] + cargo['verts']], float) / 4096
        y = G[:, 1].min() - 0.03                                   # under the glass's lower edge
        band = B[abs(B[:, 1] - y) < 0.05]                          # the shell at that height
        z0 = band[:, 2].min() + 0.10                               # inside the hatch's lip
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
    open(out_path, 'wb').write(carbin.write(car))
    print('replaced %d parts: %s' % (len(done), ' '.join(done)))


# Badges put on the car as flat decals where a ray from outside first meets
# the body: the image (the NFSU badge sheet, <CAR>_BADGING, or one from the
# --badges folder) and its rectangle in texels (x0, y0, x1, y1; None, all
# of it), the centre (x, y, z), the direction it is seen from, width and
# height, all in carbin units / 4096 (about 1.6 a metre). Forza: x right,
# y up, z forward. The NFSU model itself uses only the sheet's nose emblem.
# Each goes in the bumpers at its end of the car (every variant): in the
# body part the decals drew the whole sheet squeezed into them (the body's
# texture coordinates are not taken as they are), as the nose emblem, in
# the front bumper, never did.
BADGES = [
    ('model', None, (0.0, 0.895, None), (0, 0, -1), 0.46, 0.038),     # centred on the panel between the tail lights (y 0.76 to 1.03)
    ('sheet', (62, 24, 92, 44), (None, 0.52, 2.72), (1, 0, 0), 0.15, 0.10),   # amber markers behind the front bumper's corners
    ('sheet', (62, 24, 92, 44), (None, 0.52, 2.72), (-1, 0, 0), 0.15, 0.10),
    ('sheet', (62, 3, 92, 23), (None, 0.58, -2.80), (1, 0, 0), 0.15, 0.10),   # red, at the rear
    ('sheet', (62, 3, 92, 23), (None, 0.58, -2.80), (-1, 0, 0), 0.15, 0.10),
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
    for source, rect, centre, seen, w, h in BADGES:
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
        nx, ny = max(2, int(w / 0.04) + 1), max(2, int(h / 0.04) + 1)
        grid, tris = [], []
        for j in range(ny):
            for i in range(nx):
                fx, fy = i / (nx - 1), j / (ny - 1)
                q = p + right * (fx - 0.5) * w + up * (0.5 - fy) * h
                at, an = hit(q + n * 0.3, -n)
                if at is None or np.linalg.norm(at - q) > 0.25: at, an = q, n
                q = at + an * lift
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


if __name__ == '__main__':
    if len(sys.argv) == 7 and sys.argv[1] == '--wheel':
        convert_wheel(*sys.argv[2:])
        raise SystemExit
    args = [a for a in sys.argv[1:] if a != '--keep-glass']
    badges = None
    if '--badges' in args:
        i = args.index('--badges')
        badges = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        raise SystemExit(__doc__)
    convert(*args, keep_glass='--keep-glass' in sys.argv, badges=badges)
