"""A car exported by NFS-CarToolkit for Most Wanted (a 2024 add-on car, such as a port from another
game) put on a Forza car with nfsu2forza.py. Such a GEOMETRY.BIN packs each part on its own (nfsu.read
unpacks them), names none of them (only the name's hash) and its material groups have no names,
and the model need not follow Most Wanted's layout: the body may be spread over the lamp slots and
textured from a full livery sheet. A plan (JSON) says which groups make which Most Wanted part,
with what material name (nfsu2forza.mw_material), detail level by level; Blender thins out the
dense ones (a port from a newer game is several times a Most Wanted car's triangles, and a Forza
part holds 65536 vertices).

  python tools/cartoolkit.py <plan.json> <template car.carbin> <car folder> <out car.carbin> [nfsu2forza options]

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
"""
import json
import os
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


def build(plan, car_dir):
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
    made = build(plan, sys.argv[3])
    nfsu.read = lambda path, _real=nfsu.read: made if os.path.normcase(os.path.dirname(os.path.abspath(path))) == \
        os.path.normcase(os.path.abspath(sys.argv[3])) else _real(path)
    if plan.get('skin'): nfsu2forza.SKIN, nfsu2forza.CANVAS_SIZE = tuple(plan['skin']), plan['skin'][1]
    nfsu2forza.main([sys.argv[0]] + sys.argv[2:])
