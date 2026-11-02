"""Gran Turismo 4's Tex1 texture sets (.img and the textures inside courses and models) to PNG.

  python tools/gt4tex.py <file> <out dir> [<offset of the Tex1 in the file, hex>]

A Tex1 set holds GS uploads (transfers: data written into the PS2's GS memory at a block pointer, in a
pixel format, often a set's textures swizzled together as 32-bit) and its textures as the GS registers
that draw them (TEX0: base block, buffer width, format, size; the palette's block and offset; CLAMP: the
used size). So the set is read by doing what the console does: write every transfer into a 4 MB GS
memory, then read each texture out of it in its own format. The layout and tables are PDTools'
(github.com/Nenkai/PDTools, PDTools.Files/Textures/PS2: TextureSet1, GSMemory, PSMT8, PSMT4).

Header (little-endian): "Tex1", relocation pointer, 0, the set's size; at 0x10 the base block (0), the
blocks used, the texture count, the transfer count, then the offsets of the textures (0x28 bytes each:
TEX0, TEX1, MIPTBP1, MIPTBP2, CLAMP as 64-bit registers), of the transfers (0x0C each: data offset, block
pointer u16, buffer width u8, format u8, width u16, height u16) and of the palette patches.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forzaxpr

PSMCT32, PSMCT24, PSMCT16, PSMT8, PSMT4 = 0, 1, 2, 19, 20
PSMCT32_BLOCKLAYOUT = [0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23, 8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31]
PSMCT32_COLUMNWORD = [0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15]
PSMCT16_BLOCK = [0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15, 16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31]
PSMCT16_COLUMNWORD = [0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15]
PSMCT16_COLUMNHALF = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1]
PSMT8_BLOCKLAYOUT = [0, 1, 4, 5, 16, 17, 20, 21, 2, 3, 6, 7, 18, 19, 22, 23, 8, 9, 12, 13, 24, 25, 28, 29, 10, 11, 14, 15, 26, 27, 30, 31]
PSMT8_COLUMNWORD8 = [0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7,
                     8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15]
PSMT8_COLUMNBYTE8 = [0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3]
PSMT4_BLOCKLAYOUT = [0, 2, 8, 10, 1, 3, 9, 11, 4, 6, 12, 14, 5, 7, 13, 15, 16, 18, 24, 26, 17, 19, 25, 27, 20, 22, 28, 30, 21, 23, 29, 31]
PSMT4_COLUMNWORD4 = [0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15,
                     8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7,
                     8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7,
                     0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 0, 1, 4, 5, 8, 9, 12, 13, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15, 2, 3, 6, 7, 10, 11, 14, 15]
PSMT4_COLUMNBYTE4 = [0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 6, 6, 6, 6, 6, 6, 6, 6, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4, 4, 4, 6, 6, 6, 6, 6, 6, 6, 6,
                     1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 5, 5, 5, 5, 5, 5, 5, 5, 7, 7, 7, 7, 7, 7, 7, 7, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 5, 5, 5, 5, 5, 5, 5, 5, 7, 7, 7, 7, 7, 7, 7, 7]
T = {k: np.array(v, np.int64) for k, v in globals().items() if k.startswith('PSM') and isinstance(v, list)}


def bits_per_pixel(psm):
    return {PSMCT32: 32, PSMCT24: 24, PSMCT16: 16, PSMT8: 8, PSMT4: 4}[psm]


def addresses(psm, bp, bw, w, h):
    """For a w x h rectangle at (0, 0) of a buffer at block bp and width bw (64-pixel units), each pixel's address
    in GS memory: a 32-bit word index (CT32), a byte index (T8), a 16-bit index (CT16) or a nibble index (T4)."""
    y, x = np.mgrid[0:h, 0:w]
    base = bp * 64
    if psm in (PSMCT32, PSMCT24):
        page = x // 64 + (y // 32) * bw
        px, py = x % 64, y % 32
        block = T['PSMCT32_BLOCKLAYOUT'][px // 8 + (py // 8) * 8]
        bx, by = px % 8, py % 8
        return base + page * 2048 + block * 64 + (by // 2) * 16 + T['PSMCT32_COLUMNWORD'][bx + (by % 2) * 8]
    if psm == PSMCT16:
        page = x // 64 + (y // 64) * bw
        px, py = x % 64, y % 64
        block = T['PSMCT16_BLOCK'][px // 16 + (py // 8) * 4]
        bx, by = px % 16, py % 8
        i = bx + (by % 2) * 16
        word = base + page * 2048 + block * 64 + (by // 2) * 16 + T['PSMCT16_COLUMNWORD'][i]
        return word * 2 + T['PSMCT16_COLUMNHALF'][i]
    if psm == PSMT8:
        page = x // 128 + (y // 64) * (bw >> 1)
        px, py = x % 128, y % 64
        block = T['PSMT8_BLOCKLAYOUT'][px // 16 + (py // 16) * 8]
        bx, by = px % 16, py % 16
        column = by // 4
        i = bx + (by % 4) * 16
        word = base + page * 2048 + block * 64 + column * 16 + T['PSMT8_COLUMNWORD8'][(column & 1) * 64 + i]
        return word * 4 + T['PSMT8_COLUMNBYTE8'][i]
    if psm == PSMT4:
        page = x // 128 + (y // 128) * (bw >> 1)
        px, py = x % 128, y % 128
        block = T['PSMT4_BLOCKLAYOUT'][px // 32 + (py // 16) * 4]
        bx, by = px % 32, py % 16
        column = by // 4
        i = bx + (by % 4) * 32
        word = base + page * 2048 + block * 64 + column * 16 + T['PSMT4_COLUMNWORD4'][(column & 1) * 128 + i]
        return word * 8 + T['PSMT4_COLUMNBYTE4'][i]
    raise NotImplementedError('pixel format %d' % psm)


class GS:
    """The GS's 4 MB of local memory, as 32-bit words."""

    def __init__(self):
        self.mem = np.zeros(1 << 20, np.uint32)

    def write(self, psm, bp, bw, w, h, data):
        a = addresses(psm, bp, bw, w, h).ravel()
        if psm == PSMCT32:
            self.mem[a] = np.frombuffer(data, np.uint32, w * h)
        elif psm == PSMCT24:
            px = np.frombuffer(data, np.uint8, w * h * 3).reshape(-1, 3).astype(np.uint32)
            self.mem[a] = px[:, 0] | px[:, 1] << 8 | px[:, 2] << 16 | 0x80 << 24
        elif psm == PSMCT16:
            self.mem.view(np.uint16)[a] = np.frombuffer(data, np.uint16, w * h)
        elif psm == PSMT8:
            self.mem.view(np.uint8)[a] = np.frombuffer(data, np.uint8, w * h)
        elif psm == PSMT4:
            b = np.frombuffer(data, np.uint8, (w * h + 1) // 2)
            nib = np.empty(b.size * 2, np.uint8)
            nib[0::2], nib[1::2] = b & 15, b >> 4  # (the first pixel in the low nibble)
            nib = nib[:w * h]
            mb = self.mem.view(np.uint8)
            byte, hi = a >> 1, (a & 1).astype(bool)
            mb[byte[~hi]] = (mb[byte[~hi]] & 0xF0) | nib[~hi]
            mb[byte[hi]] = (mb[byte[hi]] & 0x0F) | (nib[hi] << 4)
        else:
            raise NotImplementedError('transfer format %d' % psm)

    def read(self, psm, bp, bw, w, h):
        a = addresses(psm, bp, bw, w, h)
        if psm in (PSMCT32, PSMCT24): return self.mem[a]
        if psm == PSMCT16: return self.mem.view(np.uint16)[a]
        if psm == PSMT8: return self.mem.view(np.uint8)[a]
        if psm == PSMT4:
            b = self.mem.view(np.uint8)[a >> 1]
            return np.where(a & 1, b >> 4, b & 15).astype(np.uint8)
        raise NotImplementedError('texture format %d' % psm)


def rgba32(words, ct24=False):
    c = np.stack([(words >> s) & 255 for s in (0, 8, 16, 24)], -1).astype(np.uint16)
    c[..., 3] = 255 if ct24 else np.minimum(c[..., 3] * 255 // 128, 255)  # (the PS2's alpha: 0x80 is opaque)
    return c.astype(np.uint8)


def rgba16(h):
    h = h.astype(np.uint32)
    c = np.stack([(h & 31) << 3, ((h >> 5) & 31) << 3, ((h >> 10) & 31) << 3, np.where(h & 0x8000, 255, 0)], -1)
    return c.astype(np.uint8)


def reg_bits(v, lo, n):
    return (v >> lo) & ((1 << n) - 1)


class TextureSet:
    def __init__(self, d, base=0):
        assert d[base:base + 4] == b'Tex1', d[base:base + 4]
        self.base = base
        size = struct.unpack_from('<I', d, base + 12)[0]
        _, self.blocks, ntex, ntr, tex_off, tr_off, patch_off = struct.unpack_from('<hHHHIII', d, base + 0x10)
        self.textures = []
        for i in range(ntex):
            tex0, tex1, mip1, mip2, clamp = struct.unpack_from('<5Q', d, base + tex_off + i * 0x28)
            self.textures.append({
                'tbp': reg_bits(tex0, 0, 14), 'tbw': reg_bits(tex0, 14, 6), 'psm': reg_bits(tex0, 20, 6),
                'tw': reg_bits(tex0, 26, 4), 'th': reg_bits(tex0, 30, 4), 'tcc': reg_bits(tex0, 34, 1),
                'cbp': reg_bits(tex0, 37, 14), 'cpsm': reg_bits(tex0, 51, 4), 'csm': reg_bits(tex0, 55, 1),
                'csa': reg_bits(tex0, 56, 5), 'wms': reg_bits(clamp, 0, 2), 'wmt': reg_bits(clamp, 2, 2),
                'maxu': reg_bits(clamp, 14, 10), 'maxv': reg_bits(clamp, 34, 10)})
        self.gs = GS()
        self.transfers = []
        for i in range(ntr):
            off, bp, bw, psm, w, h = struct.unpack_from('<IHBBHH', d, base + tr_off + i * 0x0C)
            n = (w * h * bits_per_pixel(psm) + 7) // 8
            self.transfers.append((bp, bw, psm, w, h))
            self.gs.write(psm, bp, bw, w, h, d[base + off:base + off + n])

    def image(self, i):
        """Texture i as RGBA (h, w, 4), cropped to its used size."""
        t = self.textures[i]
        w, h = 1 << t['tw'], 1 << t['th']
        px = self.gs.read(t['psm'], t['tbp'], t['tbw'], w, h)
        if t['psm'] in (PSMCT32, PSMCT24):
            img = rgba32(px, t['psm'] == PSMCT24)
        elif t['psm'] in (PSMT8, PSMT4):
            pw, ph = (16, 16) if t['psm'] == PSMT8 else (8, 2)
            if t['cpsm'] == PSMCT16:
                pal = rgba16(self.gs.read(PSMCT16, t['cbp'], 1, pw, ph).ravel())
            else:
                words = self.gs.mem[(addresses(PSMCT32, t['cbp'], 1, pw, ph) + t['csa'] * 8).ravel()]  # (CSA: PDTools' csa x 32 bytes)
                pal = rgba32(words)
            if t['psm'] == PSMT8:  # CSM1: the 256 entries in 8 x 2 tiles
                tiled = np.empty_like(pal)
                i_ = 0
                for ty in range(8):
                    for tx in range(2):
                        for y in range(2):
                            for x in range(8):
                                tiled[(ty * 2 + y) * 16 + tx * 8 + x] = pal[i_]; i_ += 1
                pal = tiled
            img = pal[px]
        elif t['psm'] == PSMCT16:
            img = rgba16(px)
        else:
            raise NotImplementedError('texture format %d' % t['psm'])
        return img[:t['maxv'] + 1, :t['maxu'] + 1]


def save_png(path, rgba):
    forzaxpr.png(path, np.ascontiguousarray(rgba))


def main(argv):
    if len(argv) < 2: raise SystemExit(__doc__)
    d = open(argv[0], 'rb').read()
    base = int(argv[2], 16) if len(argv) > 2 else d.find(b'Tex1')
    ts = TextureSet(d, base)
    os.makedirs(argv[1], exist_ok=True)
    stem = os.path.splitext(os.path.basename(argv[0]))[0]
    for i, t in enumerate(ts.textures):
        img = ts.image(i)
        p = os.path.join(argv[1], '%s_%d.png' % (stem, i))
        save_png(p, img)
        print('%s: %dx%d format %d (palette at block %d, offset %d)' % (p, img.shape[1], img.shape[0], t['psm'], t['cbp'], t['csa']))


if __name__ == '__main__':
    main(sys.argv[1:])
