"""Gran Turismo 4's course files (crs/<course>): the world model set's shapes as Wavefront OBJ with their textures.

  python tools/gt4course.py <course file> <out dir> [info]

The layout is PDTools' (github.com/Nenkai/PDTools: Courses/PS2/CourseDataFileGT4, Models/PS2/ModelSet/ModelSet2,
PGLUshape, VIFPacket, VIFCommand). A course file is used in place: a 0x100-byte header of offsets (0x04 the
world ModelSet2, 0x54 the sky, 0x58 the far scenery, 0x70 the runway). A ModelSet2 ("MDLS") has its models,
shapes, materials and texture sets by offset; a shape (pgluShape) is VIF packets, each an index into the
set's textures and materials and the UNPACKs that fill VU memory: positions, texture coordinates, colours and
the strip restarts. Each packet's vertices form one triangle strip, restarted where the restart list says.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gt4tex

HEADER = {'world': 0x04, 'env': 0x14, 'reflection': 0x24, 'after': 0x44, 'sky': 0x54, 'far': 0x58,
          'envsky': 0x5C, 'mirror_sky': 0x60, 'runway': 0x70, 'minimap': 0x84}


def u32(d, o): return struct.unpack_from('<I', d, o)[0]


def read_vif(d, off, qwc):
    """A VIF packet's commands: (vu address, num, opcode, data, stmod, row)."""
    end, cmds, row, mode = off + qwc * 16, [], (0, 0, 0, 0), 0
    while off < end:
        addr, num, op = struct.unpack_from('<HBB', d, off)
        op &= 0x7F
        off += 4
        if addr == 0xC0C0 and (op & 0x60) != 0x60:  # (a GIF tag: 16 bytes)
            off += 16
            continue
        if op == 0x30:  # STROW: the row registers, added to unpacked data in offset mode
            row = struct.unpack_from('<4i', d, off); off += 16
        elif op == 0x31:  # STCOL
            off += 16
        elif op == 0x05:  # STMOD: its mode in the immediate (the num byte's low bits)
            mode = num & 3
        elif op == 0x20:  # STMASK
            off += 4
        elif op & 0x60 == 0x60:  # UNPACK: num elements of (vn + 1) components of 32, 16 or 8 bits
            vl, vn = op & 3, (op >> 2) & 3
            size = {0: 4, 1: 2, 2: 1}.get(vl)
            if size is None:  # (V4-5: 16-bit colours)
                n = num * 2
                data = np.frombuffer(d, np.uint16, num, off); off += n
            else:
                comps = vn + 1
                dt = {4: np.int32, 2: np.int16, 1: np.uint8 if addr & 0x4000 else np.int8}[size]  # (8-bit: sign-extended unless the address's USN bit)
                data = np.frombuffer(d, dt, num * comps, off).reshape(num, comps); off += num * comps * size
            cmds.append((addr & 0x3FF if addr < 0x8000 else addr, num, op, data, mode, row, addr))
        off = (off + 3) & ~3
    return cmds


class ModelSet2:
    def __init__(self, d, base):
        assert d[base:base + 4] == b'MDLS', d[base:base + 4]
        self.d, self.base = d, base
        h = struct.unpack_from('<4sIIII BBHHHHHHHHHHH BBH', d, base)
        (_, _, _, _, self.size, _, self.flags, self.nmodels, self.nshapes, self.nmaterials, self.ntexsets,
         self.ncolors, *_rest) = h
        (self.models_off, self.shapes_off, self.materials_off, self.texsets_off) = struct.unpack_from('<4I', d, base + 0x38)

    def shape_offsets(self):
        return [self.base + u32(self.d, self.base + self.shapes_off + 4 * i) for i in range(self.nshapes)]

    def texture_sets(self):
        """The texture sets of the first colour list (each a Tex1 at its offset)."""
        out = []
        for c in range(max(self.ncolors, 1)):
            entries = self.base + u32(self.d, self.base + self.texsets_off + 4 * c)
            lst = []
            for j in range(self.ntexsets):
                lst.append(self.base + u32(self.d, entries + 4 * j))
            out.append(lst)
        return out


def read_shape(d, off):
    """A shape's packets: [(texture index, material index, commands)]."""
    nchunks, total_verts, ntris = struct.unpack_from('<HHH', d, off + 10)
    out = []
    for i in range(nchunks):
        voff, qwc, flags = struct.unpack_from('<IHH', d, off + 16 + i * 8)
        out.append((flags & 0x1FF, (flags >> 9) & 0x7F, read_vif(d, off + voff, qwc)))
    return out, total_verts, ntris


def packet_mesh(cmds):
    """A packet's vertices (positions in the course's units, uv, rgba) and triangles (index triples).

    Positions: the row register (STROW, the packet's first vertex) plus a running sum of the deltas the
    position UNPACKs hold (V3-16 normally, V3-8 for a short step and V3-32 for a long one, at VU addresses 0x00-0x3F with the
    address the vertex index). Strips: the S-8 list at 0xC040 is its own length, then a strip each of
    (entry + 6) / 3 vertices."""
    pos = np.zeros((0, 3), np.int64)
    parts, row, uv, col, restarts = [], None, None, None, None
    for addr, num, op, data, mode, r, raw in cmds:
        if raw & 0xC000 == 0x8000 and (raw & 0x3FF) < 0x40 and op in (0x68, 0x69, 0x6A):
            parts.append((raw & 0x3FF, data.astype(np.int64)))
            row = r
        elif raw == 0x8040 and op == 0x65:
            uv = data.astype(np.float64) / 4096
        elif raw == 0xC080 and op == 0x6E:
            col = data
        elif raw == 0xC040 and op == 0x72:
            restarts = data.ravel()
    if not parts or restarts is None: return None
    n = max(a + len(v) for a, v in parts)
    delta = np.zeros((n, 3), np.int64)
    for a, v in parts: delta[a:a + len(v)] = v
    pos = np.cumsum(delta, 0) + np.array(row[:3], np.int64)
    tris, start = [], 0
    for e in restarts[1:1 + restarts[0]]:
        k = (int(e) + 6) // 3
        for i in range(k - 2):
            a, b, c = start + i, start + i + 1, start + i + 2
            tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
        start += k
    return pos, uv, col, np.array(tris, np.int64).reshape(-1, 3)


OPERANDS = {0: 0, 2: 1, 3: 2, 4: 1, 5: 2, 8: 1, 9: 2, 11: 0, 12: 0, 13: 0, 14: 1, 15: 64, 16: 64, 17: 12, 18: 12, 19: 16,
            20: 4, 21: 4, 22: 4, 23: 0, 24: 0, 25: 1, 26: 0, 27: 0, 28: 2, 29: 0, 30: 0, 31: 1, 32: 2, 33: 4, 34: 0, 35: 0,
            36: 4, 37: 0, 38: 0, 39: 4, 41: 1, 42: 1, 43: 1, 44: 2, 45: 0, 46: 0, 47: 1, 50: 4, 51: 16, 53: 4, 54: 4, 55: 16,
            67: 0, 69: 2, 72: 2, 76: 2, 78: 0, 79: 0, 80: 0, 81: 0, 82: 16, 83: 16, 84: 8, 85: 8, 86: 0, 87: 0, 88: 0, 89: 1, 90: 2}


def model_draws(d, base, model_off):
    """The (shape, texture table) pairs a model draws at its most detailed level: its command stream walked
    with the first branch of each LOD select and model callback taken (PDTools' Cmd_LODSelect, Cmd_BBoxRender,
    Cmd_CallModelCallback layouts)."""
    commands = base + u32(d, model_off + 0x18)
    draws, state = [], {'tex': 0}

    def walk(p, end):
        while p < end:
            op = d[p]; p += 1
            if op == 0: return p
            if op in (4, 5):
                shape = d[p] if op == 4 else struct.unpack_from('<H', d, p)[0]
                draws.append((shape, state['tex']))
            elif op in (43, 44):
                state['tex'] = d[p] if op == 43 else struct.unpack_from('<H', d, p)[0]
            if op == 7:  # LOD select: centre, radius, count, jump table; the first level, to its next entry
                n = d[p + 16]
                table = p + 17
                jumps = struct.unpack_from('<%dH' % n, d, table)
                start = table + jumps[0]
                stop = table + 2 + jumps[1] if n > 1 else end
                walk(start, stop)
                return None  # (the levels jump past each other: the model's draws end here)
            if op == 10:  # bounding-box render: a box, then the commands drawn when it is visible
                n = d[p]
                q = p + 1 + 12 * n
                skip = struct.unpack_from('<H', d, q)[0]
                walk(q + 2, q + skip)
                p = q + skip
                continue
            if op == 6:  # model callback: parameter, branches; the default commands, then the first branch
                n = d[p + 2]
                table = p + 3
                jumps = struct.unpack_from('<%dH' % n, d, table) if n else ()
                if n:
                    walk(table + 2 * n, table + jumps[0])
                    walk(table + jumps[0], table + 2 + jumps[1] if n > 1 else end)
                return None
            if op == 77:  # VM branch: u16, count, s16 offsets
                n = d[p + 2]; p += 3 + 2 * n
                continue
            if op in (8, 9):  # jump: forward by its offset
                j = d[p] if op == 8 else struct.unpack_from('<H', d, p)[0]
                p = p + j
                continue
            if op not in OPERANDS: raise ValueError('model command %d at 0x%X' % (op, p - 1))
            p += OPERANDS[op]
        return p

    walk(commands, len(d))
    return draws


def export(path, out, scale=1 / 512.0, which='world', colour=0):
    """The model set's most detailed shapes as out/<which>.obj (metres, y up as the course has it) with
    out/<which>.mtl and the textures as out/textures/<set>_<index>.png."""
    d = open(path, 'rb').read()
    ms = ModelSet2(d, u32(d, HEADER[which]))
    os.makedirs(os.path.join(out, 'textures'), exist_ok=True)
    shapes = ms.shape_offsets()
    draws = set()
    for i in range(ms.nmodels):
        try:
            draws.update(model_draws(d, ms.base, ms.base + ms.models_off + i * 0x28))
        except (ValueError, struct.error, IndexError) as e:
            print('model %d: %s' % (i, e))
    used_tex = set()
    obj, mtl = [], []
    nv = 0
    for shape, table in sorted(draws):
        packets, _, _ = read_shape(d, shapes[shape])
        for tex, mat, cmds in packets:
            m = packet_mesh(cmds)
            if m is None: continue
            pos, uv, col, tris = m
            name = 'notex' if tex in (0, 511) else 't%d_%d' % (table, tex - 1)
            if tex not in (0, 511): used_tex.add((table, tex - 1))
            obj.append('o s%d_p\nusemtl %s' % (shape, name))
            p = pos * scale
            for i, v in enumerate(p):
                c = col[i] if col is not None and i < len(col) else (128, 128, 128, 128)
                obj.append('v %.4f %.4f %.4f %.3f %.3f %.3f' % (v[0], v[1], v[2], c[0] / 128, c[1] / 128, c[2] / 128))
            for i in range(len(p)):
                t = uv[i] if uv is not None and i < len(uv) else (0, 0)
                obj.append('vt %.5f %.5f' % (t[0], 1 - t[1]))
            for a, b, c in tris + nv + 1:
                obj.append('f %d/%d %d/%d %d/%d' % (a, a, b, b, c, c))
            nv += len(p)
    sets = ms.texture_sets()[colour]
    for table, idx in sorted(used_tex):
        png = 'textures/%d_%d.png' % (table, idx)
        mtl.append('newmtl t%d_%d\nmap_Kd %s' % (table, idx, png))
        try:
            ts = gt4tex.TextureSet(d, sets[table])
            gt4tex.save_png(os.path.join(out, png), ts.image(idx))
        except Exception as e:
            print('texture %d_%d: %s' % (table, idx, e))
    mtl.append('newmtl notex\nKd 0.6 0.6 0.6')
    open(os.path.join(out, which + '.obj'), 'w').write('mtllib %s.mtl\n' % which + '\n'.join(obj) + '\n')
    open(os.path.join(out, which + '.mtl'), 'w').write('\n'.join(mtl) + '\n')
    print('%s: %d shapes drawn, %d vertices, %d textures' % (which, len({s for s, _ in draws}), nv, len(used_tex)))


def info(path):
    d = open(path, 'rb').read()
    for k, o in HEADER.items():
        print('%-11s 0x%02X -> 0x%08X' % (k, o, u32(d, o)))
    ms = ModelSet2(d, u32(d, 0x04))
    print('world: %d models, %d shapes, %d materials, %d texture sets x %d colours, flags %d'
          % (ms.nmodels, ms.nshapes, ms.nmaterials, ms.ntexsets, ms.ncolors, ms.flags))
    kinds = {}
    for so in ms.shape_offsets()[:400]:
        packets, tv, nt = read_shape(d, so)
        for tex, mat, cmds in packets:
            for addr, num, op, data, mode, row, raw in cmds:
                k = (raw, op, mode)
                kinds.setdefault(k, [0, None, None, row])
                kinds[k][0] += 1
                if data.dtype != np.uint16 and data.size:
                    lo, hi = data.min(0), data.max(0)
                    kinds[k][1] = lo if kinds[k][1] is None else np.minimum(kinds[k][1], lo)
                    kinds[k][2] = hi if kinds[k][2] is None else np.maximum(kinds[k][2], hi)
    for k, (n, lo, hi, row) in sorted(kinds.items()):
        print('addr %04X op %02X mode %d: %5d unpacks, min %s max %s, a row %s' % (k[0], k[1], k[2], n, lo, hi, row))


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[-1] == 'info':
        info(sys.argv[1])
    elif len(sys.argv) >= 3:
        export(sys.argv[1], sys.argv[2], which=sys.argv[3] if len(sys.argv) > 3 else 'world')
    else:
        raise SystemExit(__doc__)
