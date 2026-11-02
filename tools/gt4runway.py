"""Gran Turismo 4's course runway (RNW4, at the course file's header offset 0xDC): the layout a track is
rebuilt from. Writes <out>/layout.json (each checkpoint's left edge, centre, right edge and distance along
the lap, metres) and <out>/road.obj (the drivable surface, a group per surface flag value).

  python tools/gt4runway.py <course file> <out dir>

The layout is PDTools' (github.com/Nenkai/PDTools: Courses/PS2/Runway/RunwayData, RunwayCheckpoint,
RunwayRoadVert, RunwayRoadTri): little-endian; at 0x14 the lap length ("track V"), the start and goal V,
the bounds; at 0x38 the counts (checkpoint lists, ?, checkpoints, lookup indices, ?, gadgets, road
vertices, road triangles, clusters); at 0x60 the offsets of the checkpoints (0x28: left, middle and right
xyz, V), lookups, light sets, ?, gadgets, road vertices (0x10: xyz, u16, two bytes), road triangles (0x0C:
three u16 indices, two bytes, u32 flags) and clusters. Coordinates are the course model's at 1/512.
"""
import json
import os
import struct
import sys
from collections import Counter


def read(d, base):
    assert d[base:base + 4] == b'RNW4', d[base:base + 4]
    v_len, v_start, v_goal = struct.unpack_from('<3f', d, base + 0x14)
    bounds = struct.unpack_from('<6f', d, base + 0x20)
    (lists, _, ncp, nlook, _, ngad, nverts, ntris, nclus) = struct.unpack_from('<4hi4h', d, base + 0x38)
    (cp_off, look_off, light_off, _, gad_off, vert_off, tri_off, clus_off, trav_off) = struct.unpack_from('<9i', d, base + 0x60)
    cps = []
    for i in range(ncp):
        f = struct.unpack_from('<10f', d, base + cp_off + i * 0x28)
        cps.append({'left': f[0:3], 'mid': f[3:6], 'right': f[6:9], 'v': f[9]})
    verts = [struct.unpack_from('<3f', d, base + vert_off + i * 0x10) for i in range(nverts)]
    tris = []
    for i in range(ntris):
        a, b, c, ub, u, flags = struct.unpack_from('<3HBBI', d, base + tri_off + i * 0x0C)
        tris.append((a, b, c, ub, u, flags))
    return {'length': v_len, 'start_v': v_start, 'goal_v': v_goal, 'bounds': bounds, 'checkpoints': cps,
            'verts': verts, 'tris': tris}


def main(path, out):
    d = open(path, 'rb').read()
    r = read(d, struct.unpack_from('<I', d, 0xDC)[0])
    os.makedirs(out, exist_ok=True)
    json.dump({k: r[k] for k in ('length', 'start_v', 'goal_v', 'bounds', 'checkpoints')}, open(os.path.join(out, 'layout.json'), 'w'), indent=1)
    groups = {}
    for a, b, c, ub, u, flags in r['tris']:
        groups.setdefault((ub, u, flags), []).append((a, b, c))
    lines = ['v %.3f %.3f %.3f' % v for v in r['verts']]
    for (ub, u, flags), fs in sorted(groups.items()):
        lines.append('g s%02x_%02x_%08x' % (ub, u, flags))
        lines += ['f %d %d %d' % (a + 1, b + 1, c + 1) for a, b, c in fs]
    open(os.path.join(out, 'road.obj'), 'w').write('\n'.join(lines) + '\n')
    print('lap %.1f m (start %.1f, goal %.1f), %d checkpoints, %d road vertices, %d triangles in %d surface groups'
          % (r['length'], r['start_v'], r['goal_v'], len(r['checkpoints']), len(r['verts']), len(r['tris']), len(groups)))
    for k, n in Counter((ub, u, flags) for a, b, c, ub, u, flags in r['tris']).most_common(12):
        print('  surface %02x %02x %08x: %d triangles' % (k[0], k[1], k[2], n))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
