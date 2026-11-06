"""A car exported by NFS-CarToolkit for Most Wanted (a 2024 add-on car, such as a port from another
game) put on a Forza car with nfsu2forza.py. Such a GEOMETRY.BIN packs each part on its own (nfsu.read
unpacks them), names none of them (only the name's hash) and its material groups have no names,
and the model need not follow Most Wanted's layout: the body may be spread over the lamp slots and
textured from a full livery sheet. A plan (JSON) says which groups make which Most Wanted part,
with what material name (nfsu2forza.mw_material), detail level by level; Blender thins out the
dense ones (a port from a newer game is several times a Most Wanted car's triangles, and a Forza
part holds 65536 vertices).

  python tools/cartoolkit.py <plan.json> <template car.carbin> <car folder> <out car.carbin> [nfsu2forza options]
  python tools/cartoolkit.py <plan.json> --wheel <tire.carbin> <wheel.xpr> <car folder> <out tire.carbin> <out wheel.xpr>
      (nfsu2forza's wheel: the plan gives KIT00_FRONT_TIRE, its rim groups named RIM...)

The plan:
  {"names_from": "<Most Wanted's CARS folder>",          the part names, recovered by hash
   "skin": ["SC63_SKIN2", 512],                          a livery sheet: the BODY groups keep their own
                                                         coordinates on it, packed into the atlas at that
                                                         size and baked into livery1 (nfsu2forza's canvas)
   "parts": {"BASE": [level, ...], ...}}                 Most Wanted's part (no car prefix, no _A-_D): its
                                                         detail levels, finest first, each
     {"from": [[part, texture or "*", material, side], ...], "keep": 0.4}
       part: a source part's full name less the car prefix (KIT00_LEFT_HEADLIGHT_A); texture: the
       group's texture name, "*" every group, or a number, that group; material: the name the group takes; side: "L" or
       "R" keeps the triangles on that side only (optional); keep: the share of triangles Blender
       keeps (optional; 1 keeps them all).
  "aliases": {"KIT00_BODY": "BASE"}                      a second name for a part's levels
  "fit": "width"                                         scaled to the template's width, not its length (the
                                                         wheel arches still go to its hubs)
  "fit": "track"                                         fitted by length, then narrowed (or widened) to the
                                                         template's width: the template's wheels sit flush
  "lower": 0.06                                          the body set that much (carbin units / 4096) below
                                                         the template's floor (the lowest points meet)
"""
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfsu
import nfsu2forza

BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'


def recover_names(geometry, prefix, names_from):
    """{hash: name} for the parts of a geometry whose header names none: Most Wanted's part names
    (every car's under names_from, the car's own name changed to prefix) hashed."""
    import glob
    suffixes = set()
    for g in glob.glob(os.path.join(names_from, '*', 'GEOMETRY.BIN')):
        car = os.path.basename(os.path.dirname(g))
        try:
            for p in nfsu.read(g):
                if p['name'].startswith(car + '_'): suffixes.add(p['name'][len(car) + 1:])
        except Exception:
            continue
    return {nfsu.bhash(prefix + '_' + s): prefix + '_' + s for s in suffixes}


def source_parts(path, names):
    """Every part as nfsu.read gives it, named, with each group's texture hash and triangles."""
    d = open(path, 'rb').read()
    out = {}
    for b, po, ps in nfsu.solids(d):
        part = {'textures': [], 'verts': [], 'idx': (), 'groups': []}
        for sid, so, ss in nfsu.chunks(b, po, po + ps):
            if sid == 0x00134011: part['hash'] = struct.unpack_from('<I', b, so + 0x10)[0]
            elif sid == 0x00134012: part['textures'] = list(struct.unpack_from('<%dI' % (ss // 4), b, so)[::2])
            elif sid == 0x80134100:
                for mid, mo, ms in nfsu.chunks(b, so, so + ss):
                    a, e = nfsu.unpadded(b, mo, ms)
                    if mid == 0x00134b01: part['verts'] = [struct.unpack_from('<6fI2f', b, a + 36 * k) for k in range((e - a) // 36)]
                    elif mid == 0x00134b03: part['idx'] = struct.unpack_from('<%dH' % ((e - a) // 2), b, a)
                    elif mid == 0x00134b02: raw = b[a:e]
        for g in range(len(raw) // 104):  # Most Wanted's 104-byte groups: texture index at 0x18, triangles and first index at 0x40
            r = raw[104 * g:104 * (g + 1)]
            tris, first = struct.unpack_from('<II', r, 0x40)
            part['groups'].append((r[0x18], first, tris))
        out[names.get(part['hash'], '%08x' % part['hash'])] = part
    return out


def gather(parts, texnames, prefix, spec):
    """A level's triangles: [(material, texture hash, [(v, v, v)] with vertices as nfsu tuples)]."""
    got = []
    for src, tex, material, *side in spec:
        p = parts[prefix + '_' + src]
        for gi, (ti, first, n) in enumerate(p['groups']):
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            if isinstance(tex, int) and gi != tex or isinstance(tex, str) and tex != '*' and texnames.get(th) != tex: continue
            tris = []
            for j in range(first, first + 3 * n, 3):
                t = [p['verts'][i] for i in p['idx'][j:j + 3]]
                if len(t) < 3: continue
                if side and (sum(v[1] for v in t) > 0) != (side[0] == 'L'): continue  # (NFS y is left)
                tris.append(t)
            if tris: got.append((material, th, tris))
    return got


DECIMATE = r'''
import bpy, sys
argv = sys.argv[sys.argv.index('--') + 1:]
src, dst, keep = argv[0], argv[1], float(argv[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.obj(filepath=src, axis_forward='Y', axis_up='Z', split_mode='OFF')
for o in bpy.context.scene.objects:
    if o.type != 'MESH': continue
    bpy.context.view_layer.objects.active = o
    m = o.modifiers.new('d', 'DECIMATE')
    m.decimate_type, m.ratio, m.use_collapse_triangulate = 'COLLAPSE', keep, True
    bpy.ops.object.modifier_apply(modifier='d')
bpy.ops.export_scene.obj(filepath=dst, axis_forward='Y', axis_up='Z', use_materials=True, use_normals=True, use_uvs=True,
                         use_triangles=True, keep_vertex_order=False, use_selection=False)
'''


def decimate(groups, keep, work):
    """The level's triangles thinned by Blender's collapse decimation to `keep` of them, as one mesh
    (so the groups keep their shared edges), each group still its material (an OBJ material a group)."""
    src, dst, script = (os.path.join(work, n) for n in ('in.obj', 'out.obj', 'decimate.py'))
    lines, base = [], 1
    for k, (_, _, tris) in enumerate(groups):
        lines.append('usemtl g%d' % k)
        for t in tris:
            for v in t:
                lines.append('v %.6f %.6f %.6f' % v[:3])
                lines.append('vt %.6f %.6f' % (v[7], 1 - v[8]))
                lines.append('vn %.6f %.6f %.6f' % v[3:6])
            lines.append('f %d/%d/%d %d/%d/%d %d/%d/%d' % tuple(base + i for i in (0, 0, 0, 1, 1, 1, 2, 2, 2)))
            base += 3
    open(src, 'w').write('\n'.join(lines) + '\n')
    open(script, 'w').write(DECIMATE)
    # (the corners come in unshared, as written; Blender's import merges none, so weld them first)
    weld(src)
    subprocess.run([BLENDER, '-b', '--python', script, '--', src, dst, str(keep)], check=True, capture_output=True)
    return read_obj(dst, groups)


def weld(path):
    """The OBJ's identical corners (position, coordinate and normal) as one vertex, so Blender sees
    the surface whole."""
    v, vt, vn, out, seen = [], [], [], [], {}
    fs = []
    for line in open(path):
        if line.startswith('v '): v.append(line)
        elif line.startswith('vt '): vt.append(line)
        elif line.startswith('vn '): vn.append(line)
        elif line.startswith('f '): fs.append(line)
        else: fs.append(line)
    pos, pmap = [], {}
    for k, line in enumerate(v):
        key = line.strip()
        if key not in pmap: pmap[key] = len(pos) + 1; pos.append(line)
        seen[k + 1] = pmap[key]
    tmap, tl = {}, []
    tidx = {}
    for k, line in enumerate(vt):
        key = line.strip()
        if key not in tmap: tmap[key] = len(tl) + 1; tl.append(line)
        tidx[k + 1] = tmap[key]
    nmap, nl, nidx = {}, [], {}
    for k, line in enumerate(vn):
        key = line.strip()
        if key not in nmap: nmap[key] = len(nl) + 1; nl.append(line)
        nidx[k + 1] = nmap[key]
    for line in fs:
        if line.startswith('f '):
            corners = [c.split('/') for c in line.split()[1:]]
            line = 'f ' + ' '.join('%d/%d/%d' % (seen[int(a)], tidx[int(b)], nidx[int(c)]) for a, b, c in corners) + '\n'
        out.append(line)
    open(path, 'w').write(''.join(pos + tl + nl + out))


def read_obj(path, groups):
    """An OBJ's triangles back as the groups' (material, texture, [(v, v, v)]), nfsu vertex tuples."""
    v, vt, vn, cur = [], [], [], None
    got = {k: [] for k in range(len(groups))}
    for line in open(path):
        w = line.split()
        if not w: continue
        if w[0] == 'v': v.append(tuple(map(float, w[1:4])))
        elif w[0] == 'vt': vt.append(tuple(map(float, w[1:3])))
        elif w[0] == 'vn': vn.append(tuple(map(float, w[1:4])))
        elif w[0] == 'usemtl': cur = int(w[1].split('_')[0][1:]) if w[1].startswith('g') else None
        elif w[0] == 'f' and cur is not None:
            t = []
            for c in w[1:4]:
                a, b, n = (int(x) - 1 for x in c.split('/'))
                t.append(v[a] + vn[n] + (0xFFFFFFFF, vt[b][0], 1 - vt[b][1]))
            got[cur].append(tuple(t))
    return [(m, th, got[k]) for k, (m, th, _) in enumerate(groups) if got[k]]


def as_part(name, groups):
    """One detail level as nfsu.read gives a Most Wanted part (groups in Underground's shape, a
    material name a group)."""
    verts, index, tris, gl, textures, mats = [], {}, [], [], [], []
    for material, th, ts in groups:
        if th not in textures: textures.append(th)
        first = len(tris) * 3
        for t in ts:
            tri = []
            for vtx in t:
                key = tuple(round(c, 5) for c in vtx[:6]) + (round(vtx[7], 5), round(vtx[8], 5))
                if key not in index: index[key] = len(verts); verts.append(vtx)
                tri.append(index[key])
            tris.append(tuple(tri))
        g = bytearray(0x3C)
        struct.pack_into('<I', g, 12, 3 * len(ts))
        struct.pack_into('<II', g, 0x1C, textures.index(th), len(mats))
        struct.pack_into('<I', g, 0x34, first)
        gl.append(bytes(g))
        mats.append(material)
    return {'name': name, 'textures': textures, 'shaders': [nfsu.bhash(m) for m in mats], 'mw_shaders': [], 'verts': verts,
            'tris': tris, 'groups': gl, 'materials': mats}


def join_parts(ps):
    """Underground-shaped parts as one: vertices and triangles after each other, each group's texture,
    shader and first index renumbered."""
    m = {'name': '', 'textures': [], 'shaders': [], 'verts': [], 'tris': [], 'groups': [], 'materials': []}
    for p in ps:
        base, first = len(m['verts']), 3 * len(m['tris'])
        m['verts'] += p['verts']
        m['tris'] += [tuple(i + base for i in t) for t in p['tris']]
        for grp in p['groups']:
            r = bytearray(grp)
            ti, si = struct.unpack_from('<II', r, 0x1C)
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            sh = p['shaders'][si] if si < len(p['shaders']) else 0
            if th not in m['textures']: m['textures'].append(th)
            if sh not in m['shaders']: m['shaders'].append(sh)
            struct.pack_into('<II', r, 0x1C, m['textures'].index(th), m['shaders'].index(sh))
            struct.pack_into('<I', r, 0x34, struct.unpack_from('<I', r, 0x34)[0] + first)
            m['groups'].append(bytes(r))
    return m


def merge(parts, prefix, plan):
    """An Underground 2 car's panels as Underground's parts (plan "merge": {target: [source, ...]}, names
    less the car's prefix and level): its body is fenders, quarters, doors and sills, its lamps a part a
    side, where the converter takes one body and one lamp part. Each target's level L is every source's
    level L (or its last), joined; the sources leave the list. Long names are cut at 27 characters and
    lose their level letter: those levels go by size."""
    def levels(src):
        pairs = src.endswith('*2')  # both sides cut to one name (the Celica's HEADLIGHT_): a level is the next two by size
        full = prefix + '_' + src.rstrip('*2')
        hit = [p for p in parts if any((full + s)[:27] == p['name'] for s in ('_A', '_B', '_C', '_D', ''))]
        lettered = all(re.search(r'_[A-D]$', p['name']) for p in hit)
        lv = sorted(hit, key=(lambda p: p['name']) if lettered else (lambda p: -len(p['verts'])))
        if pairs:
            lv = [join_parts([lv[k], lv[k + 1]]) if k + 1 < len(lv) else lv[k] for k in range(0, len(lv), 2)]
        return lv, hit
    gone, out = set(), []
    for target, sources in plan.items():
        got = []
        for s in sources:
            lv, hit = levels(s)
            gone |= {id(p) for p in hit}
            if lv: got.append(lv)
        if not got: continue
        for L in range(min(4, max(len(g) for g in got))):
            m = join_parts([g[min(L, len(g) - 1)] for g in got])
            m['name'] = '%s_%s_%s' % (prefix, target, 'ABCD'[L])
            out.append(m)
        print('%s_%s: %s, %d levels' % (prefix, target, ' + '.join(sources), min(4, max(len(g) for g in got))))
    return [p for p in parts if id(p) not in gone] + out


def thin(parts, prefix, plan):
    """A Most Wanted car's dense parts thinned (plan "decimate": {part: [share kept at level A, B, ...]}, names
    less the prefix and level; 1 keeps a level as it is): its groups keep their own material names. The
    MX-5's body, 20,000 vertices at both A and B, was more than a Forza part holds with its insides."""
    out = []
    with tempfile.TemporaryDirectory() as work:
        for p in parts:
            m = re.fullmatch(re.escape(prefix) + r'_(.+)_([A-D])', p['name'])
            keep = plan.get(m.group(1)) if m else None
            k = keep['ABCD'.index(m.group(2))] if keep and 'ABCD'.index(m.group(2)) < len(keep) else 1
            if k >= 1 or not p['materials']:
                out.append(p)
                continue
            idx = [i for t in p['tris'] for i in t]
            groups = []
            for gi, g in enumerate(p['groups']):
                n, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34); ti, _ = struct.unpack_from('<II', g, 0x1C)
                tris = [[p['verts'][i] for i in idx[j:j + 3]] for j in range(first, first + n - 2, 3) if max(idx[j:j + 3]) < len(p['verts'])]
                if tris: groups.append((p['materials'][gi], p['textures'][ti] if ti < len(p['textures']) else 0, tris))
            q = as_part(p['name'], decimate(groups, k, work))
            print('%s: %d triangles of %d, %d vertices' % (p['name'], len(q['tris']), len(p['tris']), len(q['verts'])))
            out.append(q)
    return out


def by_texture(parts, car_dir, plan):
    """Each group's material name from its texture (plan "materials": {texture name or hash: material, or
    {"front": .., "rear": ..} by the group's middle, NFS x, or {part: .., "*": ..} by the part's name less
    prefix and level}), where an add-on's names say nothing (the MX-5's are all "Material"); textures not
    listed keep the group's. (The MX-5's d947f346 is its tail lamps on the body and the dash in its
    interior: as brake light there the cockpit would glow.)"""
    names = {h: t['name'] for h, t in nfsu.read_textures(os.path.join(car_dir, 'TEXTURES.BIN')).items()}
    prefix = os.path.basename(os.path.normpath(car_dir)).upper()
    names[nfsu.bhash(prefix + '_SKIN1')] = prefix + '_SKIN1'  # (the paint: made at run time, not in the file)
    for p in parts:
        idx = [i for t in p['tris'] for i in t]
        for gi, g in enumerate(p['groups']):
            if gi >= len(p['materials']): break
            ti, _ = struct.unpack_from('<II', g, 0x1C)
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            want = plan.get(names.get(th, '%08x' % th))
            if isinstance(want, dict) and 'front' not in want:
                want = want.get(re.sub(r'_[A-D]$', '', p['name'][len(prefix) + 1:]), want.get('*'))
            if isinstance(want, dict):
                n, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
                xs = [p['verts'][i][0] for i in idx[first:first + n] if i < len(p['verts'])]
                want = want['front' if xs and sum(xs) / len(xs) > 0 else 'rear']
            if want:
                p['materials'][gi] = want
                p['shaders'][gi] = nfsu.bhash(want)
    return parts


def retexture(parts, car_dir, plan):
    """Groups drawn from a texture the car's pack lacks given one it has, all at one spot (plan
    "retexture": {texture name or hash: [texture name, u, v]}): the MX-5 add-on's tail lamps are a
    shared texture of the game it was made for (d947f346, in no Most Wanted file), and as lamp
    material on the template's nearest texel they came out dark; on the red of its own brake lamp
    texture they are red, and glow when braking."""
    names = {h: t['name'] for h, t in nfsu.read_textures(os.path.join(car_dir, 'TEXTURES.BIN')).items()}
    by_name = {n: h for h, n in names.items()}
    for p in parts:
        idx = [i for t in p['tris'] for i in t]
        for gi, g in enumerate(p['groups']):
            ti, _ = struct.unpack_from('<II', g, 0x1C)
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            want = plan.get(names.get(th, '%08x' % th))
            if not want: continue
            new, u, v = by_name[want[0]], float(want[1]), float(want[2])
            if new not in p['textures']: p['textures'].append(new)
            g = bytearray(g)
            struct.pack_into('<I', g, 0x1C, p['textures'].index(new))
            p['groups'][gi] = bytes(g)
            n, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
            for i in set(idx[first:first + n]):
                if i < len(p['verts']): p['verts'][i] = tuple(p['verts'][i][:7]) + (u, v) + tuple(p['verts'][i][9:])
    return parts


def build(plan, car_dir):
    if 'merge' in plan:  # an Underground 2 car: its own names and groups, joined as the converter takes them
        prefix = os.path.basename(os.path.normpath(car_dir)).upper()
        return merge(nfsu.read(os.path.join(car_dir, 'GEOMETRY.BIN')), prefix, plan['merge'])
    if 'decimate' in plan:  # a Most Wanted car as it is, its dense parts thinned (after its materials are named)
        prefix = os.path.basename(os.path.normpath(car_dir)).upper()
        parts = nfsu.read(os.path.join(car_dir, 'GEOMETRY.BIN'))
        if plan.get('retexture'): parts = retexture(parts, car_dir, plan['retexture'])
        if plan.get('materials'): parts = by_texture(parts, car_dir, plan['materials'])
        return thin(parts, prefix, plan['decimate'])
    prefix = os.path.basename(os.path.normpath(car_dir)).upper()
    geo = os.path.join(car_dir, 'GEOMETRY.BIN')
    names = recover_names(geo, prefix, plan['names_from'])
    parts = source_parts(geo, names)
    texnames = {h: t['name'] for h, t in nfsu.read_textures(os.path.join(car_dir, 'TEXTURES.BIN')).items()}
    out = []
    with tempfile.TemporaryDirectory() as work:
        for name, levels in plan['parts'].items():
            for lv, level in enumerate(levels):
                groups = gather(parts, texnames, prefix, level['from'])
                keep = level.get('keep', 1)
                n0 = sum(len(t) for _, _, t in groups)
                if keep < 1: groups = decimate(groups, keep, work)
                p = as_part('%s_%s_%s' % (prefix, name, 'ABCD'[lv]), groups)
                print('%s: %d triangles%s, %d vertices' % (p['name'], len(p['tris']), ' (of %d)' % n0 if keep < 1 else '', len(p['verts'])))
                out.append(p)
    for alias, name in plan.get('aliases', {}).items():
        for p in [p for p in out if p['name'].startswith('%s_%s_' % (prefix, name))]:
            out.append(dict(p, name=p['name'].replace('_%s_' % name, '_%s_' % alias, 1)))
    return out


if __name__ == '__main__':
    if len(sys.argv) < 5: raise SystemExit(__doc__)
    plan = json.load(open(sys.argv[1]))
    car_dir = next(a for a in sys.argv[2:] if os.path.isfile(os.path.join(a, 'GEOMETRY.BIN')))  # (--wheel takes it third)
    made = build(plan, car_dir)
    nfsu.read = lambda path, _real=nfsu.read: made if os.path.normcase(os.path.dirname(os.path.abspath(path))) == \
        os.path.normcase(os.path.abspath(car_dir)) else _real(path)
    if plan.get('skin'): nfsu2forza.SKIN, nfsu2forza.CANVAS_SIZE = tuple(plan['skin']), plan['skin'][1]
    nfsu2forza.FIT_WIDTH = plan.get('fit') == 'width'
    nfsu2forza.FIT_TRACK = plan.get('fit') == 'track'
    nfsu2forza.LOWER = plan.get('lower', 0.0)
    nfsu2forza.KITS = plan.get('kits')
    nfsu2forza.HIDE = tuple(plan.get('hide', ()))
    nfsu2forza.SHOP = dict(plan.get('shop', {}))
    nfsu2forza.ARCHES = plan.get('arches')
    nfsu2forza.OWN_INTERIOR = bool(plan.get('interior'))
    nfsu2forza.SMOOTH = 'decimate' in plan  # (thinned: the dense model's normals no longer fit)
    nfsu2forza.UV32 = 'merge' in plan  # (an Underground 2 car's texels at the game's reading)
    nfsu2forza.main([sys.argv[0]] + sys.argv[2:])
