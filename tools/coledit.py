"""Read, change and write a track's collision (QuickPreview1.col).

The file, as Forza reads it:

  0x00  u32 columns, rows (of 100 m cells over the track)
  0x08  f32 min x, min z, max x, max z
  0x18  f32 cell width, depth (100); f32 their inverses (0.01)
  0x28  u32 the file's size; u32 2; u32 0xABCD1234
  0x34  f32 100, 100 (cell size again), 8, 8 (each cell's margin),
        10, 10 (sub-cell size)
  0x4c  u32 cells with a block; u32 0x54
  0x54  u32 the first block's offset
  0x58  per cell with a block, 6 u32: its index in this table, the cell
        (row * columns + column), the block's offset, its size, 0, the next
        block's offset (0 for the last)

Blocks start at multiples of 0x200 (zero padded). A block covers its cell
and 8 m around it:

  0x00  u32 vertex count, triangle count, vertex offset, triangle offset
  0x10  u32 12, 12: the sub-grid (10 m sub-cells from the block's minimum)
  0x18  f32 min x, min z, max x, max z (the cell's bounds, margin included)
  0x28  f32 10, 10, 0.1, 0.1
  0x38  u32 the sub-grid's offset; u32 0
  vertices: 16 bytes, f32 x, y, z, u32 the triangle's unit normal packed:
            x in bits 0-10, z in 11-21 (signed, 1023 = 1), y in 22-31
            (signed, 511 = 1); ground 0x7f8xxxxx. A wall whose words are 0
            (no normal) does not stop a car.
  triangles: 28 bytes, u32 surface (0 road, 0x500 and 0xa00 other ground;
            0x300, 0x400, 0x900, 0xe00, 0xf00, 0x1000 walls), three u32
            vertex offsets from the block, f32 normal
  sub-grid: 144 u32, per sub-cell the offset (from the block) of a list of
            the triangles over it (0 for none): u16 count, u16 triangle
            indices, padded to 4 bytes

  python tools/coledit.py <in.col> <out.col>   reads and writes it again
"""
import struct
import sys

import numpy as np

SUB = 12


def pack_normal(n):
    """A unit normal as a vertex's word: x and z in 11 bits (1023 = 1), y in the top 10 (511 = 1)."""
    x, y, z = (int(float(v) * m) for v, m in zip(n, (1023, 511, 1023)))  # truncated, as the file has them
    return (x & 0x7ff) | (z & 0x7ff) << 11 | (y & 0x3ff) << 22


def overlaps(tri, box):
    """Whether a triangle ((x, z) x 3) and a box (x0, z0, x1, z1) overlap: no separating axis among
    the box's two and the triangle's three edge normals. A wall seen from above is a line, and
    lines count."""
    bx = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
        e = (b[0] - a[0], b[1] - a[1])
        if e != (0, 0): axes.append((-e[1], e[0]))
    for ax in axes:
        tp = [ax[0] * q[0] + ax[1] * q[1] for q in tri]
        bp = [ax[0] * q[0] + ax[1] * q[1] for q in bx]
        if max(tp) < min(bp) or max(bp) < min(tp): return False
    return True


class Block:
    def __init__(self, cell, bounds, verts, tris):
        self.cell = cell          # row * columns + column
        self.bounds = bounds      # min x, min z, max x, max z
        self.verts = verts        # [(x, y, z, word)]
        self.tris = tris          # [(surface, (i, j, k), (nx, ny, nz))]

    def grid(self, eps=0.0):
        """Per sub-cell, the triangles that overlap it seen from above (x, z)."""
        x0, z0 = self.bounds[0], self.bounds[1]
        cells = [[] for _ in range(SUB * SUB)]
        for t, (s, ijk, n) in enumerate(self.tris):
            p = [(self.verts[i][0], self.verts[i][2]) for i in ijk]
            xs, zs = [q[0] for q in p], [q[1] for q in p]
            c0, c1 = int(np.floor((min(xs) - x0) / 10)), int(np.floor((max(xs) - x0) / 10))
            r0, r1 = int(np.floor((min(zs) - z0) / 10)), int(np.floor((max(zs) - z0) / 10))
            for r in range(max(r0, 0), min(r1, SUB - 1) + 1):
                for c in range(max(c0, 0), min(c1, SUB - 1) + 1):
                    sx, sz = x0 + 10 * c, z0 + 10 * r
                    if overlaps(p, (sx - eps, sz - eps, sx + 10 + eps, sz + 10 + eps)):
                        cells[r * SUB + c].append(t)
        return cells


class Col:
    def __init__(self, data):
        d = data
        self.cols, self.rows = struct.unpack_from('<II', d, 0)
        self.box = struct.unpack_from('<4f', d, 8)
        self.head = d[0x18:0x4c]  # cell sizes and the rest, kept as they are (the size at 0x28 rewritten)
        n = struct.unpack_from('<I', d, 0x4c)[0]
        self.blocks = []
        self.raw_grids = []
        for i in range(n):
            _, cell, off, size, _, end = struct.unpack_from('<6I', d, 0x58 + 24 * i)
            nv, nt, vo, to = struct.unpack_from('<4I', d, off)
            bounds = struct.unpack_from('<4f', d, off + 0x18)
            verts = [struct.unpack_from('<3fI', d, off + vo + 16 * v) for v in range(nv)]
            tris = []
            for t in range(nt):
                s, a, b, c = struct.unpack_from('<4I', d, off + to + 28 * t)
                tris.append((s, ((a - vo) // 16, (b - vo) // 16, (c - vo) // 16), struct.unpack_from('<3f', d, off + to + 28 * t + 16)))
            self.blocks.append(Block(cell, bounds, verts, tris))
            go = struct.unpack_from('<I', d, off + 0x38)[0]
            grid = []
            for g in struct.unpack_from('<%dI' % (SUB * SUB), d, off + go):
                if not g: grid.append([]); continue
                k = struct.unpack_from('<H', d, off + g)[0]
                grid.append(list(struct.unpack_from('<%dH' % k, d, off + g + 2)))
            self.raw_grids.append(grid)

    def block_bytes(self, b):
        nv, nt = len(b.verts), len(b.tris)
        vo, to = 0x40, 0x40 + 16 * nv
        go = to + 28 * nt
        out = bytearray(struct.pack('<4I2I4f4f2I', nv, nt, vo, to, SUB, SUB, *b.bounds, 10.0, 10.0, 0.1, 0.1, go, 0))
        for v in b.verts: out += struct.pack('<3fI', *v)
        for s, (i, j, k), n in b.tris: out += struct.pack('<4I3f', s, vo + 16 * i, vo + 16 * j, vo + 16 * k, *n)
        at, body = [], bytearray()
        start = go + 4 * SUB * SUB
        for cell in b.grid():
            if not cell: at.append(0); continue
            at.append(start + len(body))
            body += struct.pack('<H%dH' % len(cell), len(cell), *cell)
            body += b'\0' * (-len(body) % 4)
        out += struct.pack('<%dI' % (SUB * SUB), *at) + body
        out += b'\0' * (-len(out) % 0x200)
        return bytes(out)

    def to_bytes(self):
        blocks = sorted(self.blocks, key=lambda b: b.cell)
        table = 0x58 + 24 * len(blocks)
        first = (table + 0x1ff) & ~0x1ff
        body, recs = bytearray(), []
        for i, b in enumerate(blocks):
            raw = self.block_bytes(b)
            off = first + len(body)
            recs.append(struct.pack('<6I', i, b.cell, off, len(raw), 0, off + len(raw) if i + 1 < len(blocks) else 0))
            body += raw
        size = first + len(body)
        head = bytearray(self.head)
        struct.pack_into('<I', head, 0x28 - 0x18, size)
        out = struct.pack('<II4f', self.cols, self.rows, *self.box) + bytes(head) + struct.pack('<III', len(blocks), 0x54, first)
        out += b''.join(recs)
        out += b'\0' * (first - len(out))
        return out + bytes(body)

    def cell_bounds(self, cell):
        c, r = cell % self.cols, cell // self.cols
        x0, z0 = self.box[0] + 100 * c, self.box[1] + 100 * r
        return (x0 - 8, z0 - 8, x0 + 108, z0 + 108)

    def block(self, cell):
        for b in self.blocks:
            if b.cell == cell: return b
        b = Block(cell, self.cell_bounds(cell), [], [])
        self.blocks.append(b)
        return b

    def triangles(self):
        """Every triangle once (a triangle near a cell's edge is in each block it reaches), as
        (surface, three points, normal)."""
        seen, out = set(), []
        for b in self.blocks:
            for s, ijk, n in b.tris:
                p = tuple(tuple(round(c, 3) for c in b.verts[i][:3]) for i in ijk)
                if (s, p) in seen: continue
                seen.add((s, p))
                out.append((s, [b.verts[i][:3] for i in ijk], n, [b.verts[i][3] for i in ijk]))
        return out

    def add(self, surface, pts, word=None):
        """A triangle (three (x, y, z)) into every block whose bounds its bounding box overlaps; its
        vertices' word its packed normal unless given."""
        p = np.array(pts, float)
        n = np.cross(p[1] - p[0], p[2] - p[0])
        n = n / (np.linalg.norm(n) or 1)
        if word is None: word = pack_normal(n)
        lo, hi = p.min(0), p.max(0)
        for cell in range(self.cols * self.rows):
            bx0, bz0, bx1, bz1 = self.cell_bounds(cell)
            if hi[0] < bx0 or lo[0] > bx1 or hi[2] < bz0 or lo[2] > bz1: continue
            b = self.block(cell)
            base = len(b.verts)
            b.verts += [(float(q[0]), float(q[1]), float(q[2]), word) for q in p]
            b.tris.append((surface, (base, base + 1, base + 2), tuple(float(c) for c in n)))

    def remove(self, keep):
        """Drops every triangle for which keep(surface, points) is false."""
        gone = 0
        for b in self.blocks:
            tris = [t for t in b.tris if keep(t[0], [b.verts[i][:3] for i in t[1]])]
            gone += len(b.tris) - len(tris)
            used = sorted({i for t in tris for i in t[1]})
            remap = {o: k for k, o in enumerate(used)}
            b.verts = [b.verts[i] for i in used]
            b.tris = [(s, tuple(remap[i] for i in ijk), n) for s, ijk, n in tris]
        return gone


if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read()
    col = Col(src)
    same = sum(b.grid() == g for b, g in zip(col.blocks, col.raw_grids))
    print('%d blocks; %d of them have the sub-grid this script would build' % (len(col.blocks), same))
    out = col.to_bytes()
    print('%d bytes in, %d out, %s' % (len(src), len(out), 'identical' if out == src else 'different'))
    open(sys.argv[2], 'wb').write(out)
