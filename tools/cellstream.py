"""The Pacific Shipyards Circuit's visibility cells all given one texture list, the textures nearest the loop, in place.

Every cell draws the same ~1,900 meshes (shipyardcircuit: Pacific Shipyards II's cells 0-7 for all; how the game picks
its cell is not known, and per-cell lists by place left the road black), which use 961 textures; each cell streamed
221-339 of them, picked with mesh positions that failed for about 1,100 meshes, and the rest drew from the stx's
32-texel copies: blurred walls a few metres from the road (the 4 Nov audit: the brick wall's end, the warehouse
windows, the green shed). Now each texture's distance is its nearest drawn mesh's bounding sphere (the ppw record,
walked; tools/spherefix.py first) to the loop's centre line, and every cell streams: the textures every cell streamed
already (the new faces' own), then the nearest, until the count or the bytes reach the most a cell streamed before
(the game blurred some past ~340; the disc's own cells stream 332 and 12.4 MB at most). Vertex buffer lists as they were.

  python tools/cellstream.py <mods folder> <tag> [--dry]
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fujitrack
import shipyardloop as L
import xb2


def plan(res, pvs, ppw, model=None):
    """(the texture list for every cell, info lines)"""
    names, _ = xb2.resources(bytes(res))
    model = model or L.MODEL
    head, cells, tail = L.parse_pvs(pvs)
    sp = L.read_splines(bytearray(res))
    ring = (sp[4] + sp[5]) / 2
    offs = fujitrack.ppw_records(bytes(ppw))
    drawn = sorted({struct.unpack_from('<H', e)[0] for c in cells for e in c[0]})
    streamed = [[struct.unpack_from('<H', e)[0] for e in c[1]] for c in cells]
    size = lambda t: names[t - 9][4] if 9 <= t < len(names) + 9 else 0
    near = {}
    for m in drawn:
        try: info = fujitrack.mesh_info(res, names, model, m)
        except Exception: continue
        if not info or m >= len(offs): continue
        r, cx, cy, cz = struct.unpack_from('<4f', ppw, offs[m])
        if not np.isfinite([r, cx, cz]).all(): continue
        d = max(0.0, float(np.min(np.hypot(ring[:, 0] - cx, ring[:, 2] - cz))) - r)
        vb, nidx, vbytes, vsize = info[:4]
        if vsize == 24 and vbytes:  # (its nearest vertex, where the vertices are plain: a building's sphere reaches the road)
            o = names[vb - 9][3]
            p = np.frombuffer(bytes(res[o:o + vbytes]), np.dtype([('p', '<f4', 3), ('r', 'V12')]))['p'].astype(float)
            if len(p) and np.isfinite(p).all() and np.abs(p).max() < 5000:
                q = p[:: max(1, len(p) // 400)]
                dd = np.hypot(q[:, None, 0] - ring[None, ::4, 0], q[:, None, 2] - ring[None, ::4, 2])
                d = float(dd.min())
        for t in info[4]:
            if 9 <= t < len(names) + 9 and names[t - 9][0].startswith('tex_'): near[t] = min(near.get(t, 1e9), d)
    count_cap = max(len(s) for s in streamed)
    byte_cap = max(sum(size(t) for t in s) for s in streamed)
    core = set.intersection(*[set(s) for s in streamed])
    out = sorted(core, key=lambda t: near.get(t, 1e9))
    total = sum(size(t) for t in out)
    for t in sorted(near, key=lambda t: near[t]):
        if t in core: continue
        if len(out) >= count_cap or total + size(t) > byte_cap: break
        out.append(t); total += size(t)
    reach = max((near[t] for t in out if t in near and t not in core), default=0)
    info = ['cells %d; before: %d-%d textures, %.1f-%.1f MB; core (every cell) %d' % (
        len(cells), min(map(len, streamed)), count_cap, min(sum(size(t) for t in s) for s in streamed) / 2**20, byte_cap / 2**20, len(core)),
        'now: %d textures, %.1f MB, every cell; all used within %.0f m of the loop' % (len(out), total / 2**20, reach)]
    return out, info


def apply(pvs, tex):
    head, cells, tail = L.parse_pvs(pvs)
    out = bytearray(head) + struct.pack('<I', len(cells))
    for drawn, _, bufs in cells:
        out += struct.pack('<I', len(drawn)) + b''.join(drawn)
        out += struct.pack('<I', len(tex)) + b''.join(struct.pack('<HHI', t, 0xFFFF, 0) for t in tex)  # (8 bytes: the u32 is 0 in every entry)
        out += struct.pack('<I', len(bufs)) + b''.join(bufs)
    return bytes(out + tail)


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if len(a) != 2: raise SystemExit(__doc__)
    T = os.path.join(a[0], 'track', a[1])
    res = open(os.path.join(T, 'hdd', 'Partition4', 'vancouver.res'), 'rb').read()
    pp = os.path.join(T, 'media', 'tracks', 'VancouverReverse', 'QuickPreview1.pvs')
    pvs = open(pp, 'rb').read()
    ppw = open(pp + '.ppw', 'rb').read()
    tex, info = plan(res, pvs, ppw)
    print('\n'.join(info))
    if '--dry' not in sys.argv:
        new = apply(pvs, tex)
        assert L.parse_pvs(new)[1][0][0] == L.parse_pvs(pvs)[1][0][0]
        open(pp, 'wb').write(new)
        print(pp)
