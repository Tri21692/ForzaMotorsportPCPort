"""Put a Need for Speed Underground car's body on a Forza car.

Takes a Forza car's car.carbin as the template (its handling, sounds,
interior, glass, driver, brakes and hinges stay) and replaces the geometry
of its body parts with the NFSU car's stock (KIT00, finest detail) parts:

  body      <- BODY + ROOF          hood      <- HOOD      trunk <- TRUNK
  bumperF*  <- FRONT_BUMPER         bumperR*  <- REAR_BUMPER
  skirtL* / skirtR*                 <- SKIRT, its left and right halves
  headlightL/R, taillightL/R        <- HEADLIGHT, BRAKELIGHT halves
  mirrorL/R <- LEFT/RIGHT_SIDE_MIRROR

NFSU is x forward, y left, z up in metres; Forza is x right, y up, z
forward. The NFSU car is scaled and moved so its body's length and its
front, back and bottom match the template body's; the axis swap mirrors
it, which Forza's opposite winding cancels (turning them round put every
panel inside out in the game). Each NFSU material group becomes a
subpart (a triangle strip): the generated skin becomes Body (the livery's
paint), and the rest take a material from their texture's name. Texture
coordinates all point at a white spot of the template's livery atlas for
now, so parts are flat-coloured. Damage shapes are the undamaged shape
(no dents yet).

Usage:
  python tools/nfsu2forza.py <template car.carbin> <NFSU car folder> <out car.carbin> [--keep-glass]

--keep-glass keeps the template's windows (the NFSU car's side windows are
holes); otherwise they are hidden, as they stand out of a lower roof.
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


def bhash(s, h=0xFFFFFFFF):
    for c in s.encode('latin-1'):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


# NFSU shaders (by name hash) -> Forza materials. 12c9453c has no known name:
# on the 240SX it is the roof, the pillars and window frames, the hatch and
# trim on the bumpers (the side windows are holes, not glass), so it is paint.
SHADERS = {bhash('CARSKIN'): BODY, bhash('WINDSHIELD'): WINDOW, 0x12C9453C: BODY,
           bhash('DULLPLASTIC'): PLASTIC, bhash('CHROME'): CHROME, bhash('HEADLIGHTGLASS'): HEADLIGHTGLASS,
           bhash('BRAKELIGHTGLASS'): REDGLASS, bhash('DECAL'): BADGE, bhash('HEADLIGHT'): HEADLIGHTS,
           bhash('BRAKELIGHT'): TAILLIGHTS, bhash('RUBBER'): BLACK, bhash('ENGINE'): BLACK}


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


def convert(template_path, nfsu_dir, out_path, keep_glass=False):
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
    print('windows: black texel at u, v = %.3f, %.3f' % (dark[0] / 65536, dark[1] / 65536))

    def pos(v):
        x, y, z = -k * v[1], k * v[2] + dy, k * v[0] + dz
        return [max(-32768, min(32767, int(round(c * 4096)))) for c in (x, y, z)]

    def nrm(v):
        x, y, z = -v[4], v[5], v[3]
        return [max(-32768, min(32767, int(round(c * 32767)))) for c in (x, y, z)]

    def build(sources, side=0, glass=None):
        """Forza vertices and subparts from NFSU parts (lists of detail
        levels, finest first); side -1/+1 keeps the triangles on the car's
        left/right (Forza x < 0 / > 0) only. A subpart's id is its detail
        level, 1 the finest: numbered otherwise, most of them were never
        drawn up close. glass=False leaves the windows out, glass=True keeps
        only them (as Window)."""
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
                    tris.append((base + a, base + b, base + c))  # the axis swap mirrors them and Forza's strips wind the other way: the two cancel
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
                if tris:
                    subs.append((lod, m, strip(tris)))
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
            verts = [v[:6] + (tuple(old[j][6:10]) + dark if Qm[i] == WINDOWS else tuple(old[j][6:12]))
                     for i, (v, j) in enumerate(zip(verts, near))]
        part['verts'] = verts
        # A part that had a damage shape keeps one, the same as the car
        # undamaged (so no dents yet): left empty, the game drew those parts
        # black and partly see-through, as if it lights them from it.
        if struct.unpack_from('<I', part['Damage'][1])[0]:
            part['Damage'] = (part['Damage'][0], struct.pack('<I', len(verts)) + b''.join(struct.pack('<6h', *v[:6]) for v in verts))
        tmpl = part['subparts'][0]
        part['subparts'] = [{'version': tmpl['version'], 'id': lod, 'material': BODY if m == WINDOWS else m, 'prim': 6,
                             'extra': bytes(16), 'indices': s, 'tail': b''} for lod, m, s in subs]

    plan = {
        'body': ([find('BODY'), find('ROOF')], 0), 'hood': ([find('HOOD')], 0), 'trunk': ([find('TRUNK')], 0),
        'bumperF': ([find('FRONT_BUMPER')], 0), 'bumperR': ([find('REAR_BUMPER')], 0),
        'skirtL': ([find('SKIRT')], -1), 'skirtR': ([find('SKIRT')], 1),
        'headlightL': ([find('HEADLIGHT')], -1), 'headlightR': ([find('HEADLIGHT')], 1),
        'taillightL': ([find('BRAKELIGHT')], -1), 'taillightR': ([find('BRAKELIGHT')], 1),
        'mirrorL': ([find('LEFT_SIDE_MIRRO')], 0), 'mirrorR': ([find('RIGHT_SIDE_MIRR')], 0),
    }
    plan = {k: v if len(v) == 3 else v + (None,) for k, v in plan.items()}
    built = {}
    done = []
    for part in car['parts']:
        if part['name'].startswith('glass') and (not keep_glass or 'HL_' in part['name']):  # the template's glass stood out of a lower NFSU roof; its headlight glass never fits
            for sp in part['subparts']:
                sp['indices'] = [0, 0, 0]
            done.append(part['name'] + '(hidden)')
            continue
        for key, (src, side, glass) in plan.items():
            if part['name'].startswith(key) and part['name'].endswith('_LOD1') and all(src):
                if key not in built: built[key] = build(src, side, glass)
                put(part, *built[key])
                done.append(part['name'])
                break
    open(out_path, 'wb').write(carbin.write(car))
    print('replaced %d parts: %s' % (len(done), ' '.join(done)))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--keep-glass']
    if len(args) != 3:
        raise SystemExit(__doc__)
    convert(*args, keep_glass='--keep-glass' in sys.argv)
