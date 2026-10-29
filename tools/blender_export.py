"""An installed custom track (tools/shipyardcircuit.py's) as an OBJ for Blender: what the game draws
round the loop, textured, and its collision.

Reads what the runtime loads (the mods folder's track\\<tag>\\: the scenery, hdd\\Partition4\\vancouver.res;
its visibility, whose cells' first lists are the meshes drawn; and its collision cache), so it shows
the build as installed, not as the build meant it. Objects:

  scenery_<mesh>      each drawn mesh within `reach` m of the loop (its material: its texture)
  collision_ground    the collision's ground (faces within 45 degrees of level)
  collision_walls     and its walls
  loop                the AI line's two edges, as a thin ribbon

Coordinates are the game's (y up) with x turned round (its world is left-handed: as they were,
Blender showed it mirrored), each face's winding with it; Blender's OBJ import turns y up into its
z up.
Textures: DXT1/DXT5 from the scenery bundle, their shape from the stx's 32-texel copies, as PNG in
<out>\\tex\\; texture coordinates (s16) are (s + 32768) / 512 a repeat.

  python tools/blender_export.py <disc> <mods folder> <out folder> [tag] [reach]
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coledit
import forzaxpr
import shipyardloop as L
import xb2

ST = 512.0  # s16 texture coordinate units a repeat (a stop sign's face spans -32768 to -32256)


def texture_png(res, names, stx, t, path):
    """Texture resource t as a PNG at path, if it is DXT1/DXT5 of a size that resolves; its shape
    (w / h) from its stx copy's. Returns whether it was written."""
    size, slots, _, nres = struct.unpack_from('<4I', stx, 20)
    table = np.frombuffer(stx, '<i4', nres, 36)
    if not (9 <= t < len(names) + 9) or t >= nres or table[t] < 0: return False
    fmt = struct.unpack_from('<5I', stx, 36 + 4 * nres + 20 * int(table[t]))[3]
    f, lu, lv = (fmt >> 8) & 0xFF, (fmt >> 20) & 0xF, (fmt >> 24) & 0xF
    kind, bs = {0x0C: (1, 8), 0x0E: (5, 16), 0x0F: (5, 16)}.get(f, (None, None))
    if kind is None: return False
    r = names[t - 9]
    for a in range(2, 12):
        w, h = 1 << a, 1 << max(a - (lu - lv), 0)
        tot, ww, hh = 0, w, h
        while True:
            tot += max(ww // 4, 1) * max(hh // 4, 1) * bs
            if ww == 1 and hh == 1: break
            ww, hh = max(ww // 2, 1), max(hh // 2, 1)
        if tot == r[4] or w * h * bs // 16 == r[4]:  # with its mips, or without
            img = forzaxpr.dxt(res[r[3]:r[3] + r[4]], w, h, kind)
            forzaxpr.png(path, np.ascontiguousarray(img))
            return True
    return False


def mesh_geometry(res, names, m):
    """Mesh m's vertices (n x 3), texture coordinates (n x 2, in repeats) and triangles (k x 3,
    from its strip, the degenerate ones dropped), its texture, or None."""
    a = struct.unpack_from('<I', res, L.MODEL + 4 + 4 * m)[0]
    _, _, nidx, vbytes, vb, stride, _, t0, _ = struct.unpack_from('<IIIIHHHHH', res, L.MODEL + a)
    if not (9 <= vb < len(names) + 9) or stride != 6 or not vbytes or vbytes % 24: return None
    o = names[vb - 9][3]
    v = np.frombuffer(bytes(res[o:o + vbytes]), dtype=np.dtype([('p', '<f4', 3), ('n', '<u4'), ('st', '<i2', 4)]))
    idx = np.frombuffer(bytes(res[o + vbytes:o + vbytes + 2 * nidx]), '<u2').astype(int)
    p = v['p'].astype(float)
    # (a few, retaining walls and stretches of the course's road, are in another layout: read as
    # this one they reach to the origin and 1e38 m up)
    if not len(idx) or idx.max() >= len(p) or not np.all(np.isfinite(p)) or np.ptp(p[:, 0]) > 800: return None
    uv = (v['st'][:, :2].astype(float) + 32768.0) / ST
    tris = np.stack([idx[:-2], idx[1:-1], idx[2:]], 1)
    tris[1::2] = tris[1::2][:, [1, 0, 2]]  # a strip's every other triangle turned round
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])]
    return p, uv, tris, t0


def export(disc, mods, out, tag='VancouverLoop', reach=150.0):
    t = os.path.join(mods, 'track', tag)
    res = open(os.path.join(t, 'hdd', 'Partition4', 'vancouver.res'), 'rb').read()
    names, _ = xb2.resources(res)
    pvs = open(os.path.join(t, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs'), 'rb').read()
    stx_p = os.path.join(t, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs.stx')
    stx = open(stx_p if os.path.exists(stx_p) else os.path.join(disc, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs.stx'), 'rb').read()
    col = coledit.Col(open(os.path.join(t, 'hdd', 'Partition4', tag + '.col'), 'rb').read())
    sp = L.read_splines(bytearray(res))
    ring = (sp[4] + sp[5]) / 2
    lo, hi = ring[:, [0, 2]].min(0) - reach, ring[:, [0, 2]].max(0) + reach
    _, cells, _ = L.parse_pvs(pvs)
    drawn = sorted({struct.unpack_from('<H', e)[0] for c in cells for e in c[0]})
    os.makedirs(os.path.join(out, 'tex'), exist_ok=True)
    obj = open(os.path.join(out, tag + '.obj'), 'w')
    mtl = open(os.path.join(out, tag + '.mtl'), 'w')
    obj.write('mtllib %s.mtl\n' % tag)
    have, nv, nt, meshes = {}, 0, 0, 0
    def material(name, png=None, colour=(0.6, 0.6, 0.6)):
        if name in have: return
        have[name] = 1
        mtl.write('newmtl %s\nKd %.3f %.3f %.3f\n' % (name, *colour) + ('map_Kd tex/%s\n' % png if png else '') + '\n')
    for m in drawn:
        g = mesh_geometry(res, names, m)
        if g is None: continue
        p, uv, tris, t0 = g
        if not len(tris) or p[:, 0].max() < lo[0] or p[:, 0].min() > hi[0] or p[:, 2].max() < lo[1] or p[:, 2].min() > hi[1]: continue
        name = 'tex%d' % t0
        if name not in have:
            png = name + '.png'
            material(name, png if texture_png(res, names, stx, t0, os.path.join(out, 'tex', png)) else None)
        obj.write('o scenery_%d\nusemtl %s\n' % (m, name))
        obj.write(''.join('v %.3f %.3f %.3f\n' % (-q[0], q[1], q[2]) for q in p))
        obj.write(''.join('vt %.4f %.4f\n' % (u, 1.0 - v) for u, v in uv))
        obj.write(''.join('f %d/%d %d/%d %d/%d\n' % (a + nv + 1, a + nv + 1, c + nv + 1, c + nv + 1, b + nv + 1, b + nv + 1) for a, b, c in tris))
        nv += len(p); nt += len(tris); meshes += 1
    # the collision: ground and walls, untextured
    ground, walls = [], []
    for s, pts, n, w in col.triangles():
        q = np.array(pts, float)
        if q[:, 0].max() < lo[0] or q[:, 0].min() > hi[0] or q[:, 2].max() < lo[1] or q[:, 2].min() > hi[1]: continue
        (ground if abs(n[1]) > 0.7 else walls).append(q)
    for name, tris_, colour in (('collision_ground', ground, (0.2, 0.8, 0.3)), ('collision_walls', walls, (1.0, 0.1, 0.1))):
        material(name, colour=colour)
        obj.write('o %s\nusemtl %s\n' % (name, name))
        for q in tris_:
            obj.write(''.join('v %.3f %.3f %.3f\n' % (-v[0], v[1], v[2]) for v in q))
            obj.write('f %d %d %d\n' % (nv + 1, nv + 3, nv + 2))
            nv += 3
    # the AI line's edges, a ribbon 0.3 m wide a little over the road
    material('loop', colour=(0.1, 0.8, 1.0))
    obj.write('o loop\nusemtl loop\n')
    for k in (4, 5):
        e = sp[k]
        for i in range(len(e)):
            a, b = e[i], e[(i + 1) % len(e)]
            obj.write('v %.3f %.3f %.3f\nv %.3f %.3f %.3f\nv %.3f %.3f %.3f\nv %.3f %.3f %.3f\n' % (-a[0], a[1] + 0.05, a[2], -b[0], b[1] + 0.05, b[2], -b[0], b[1] + 0.35, b[2], -a[0], a[1] + 0.35, a[2]))
            obj.write('f %d %d %d %d\n' % (nv + 1, nv + 2, nv + 3, nv + 4))
            nv += 4
    obj.close(); mtl.close()
    print('%s: %d meshes, %d triangles, %d textures; collision %d ground, %d wall triangles' % (os.path.join(out, tag + '.obj'), meshes, nt, sum(1 for k in have if k.startswith('tex')), len(ground), len(walls)))


if __name__ == '__main__':
    a = sys.argv[1:]
    export(a[0], a[1], a[2], *(a[3:4] or ['VancouverLoop']), *([float(a[4])] if len(a) > 4 else []))
