"""Decode Xbox XPR0 texture packs (A8R8G8B8 and DXT1/3/5, 2D and volume, swizzled) to PNGs.

Usage: python tools/forzaxpr.py <out folder> <file.xpr>...
"""
import struct, sys, zlib, os
import numpy as np


def png(path, rgba):
    h, w, _ = rgba.shape
    raw = b''.join(b'\0' + rgba[r].tobytes() for r in range(h))
    ch = lambda t, b: struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw, 6)) + ch(b'IEND', b''))


def unswizzle_index(w, h, dd):
    """For each (z, y, x), its offset in Morton order (x, y, z bits in turn)."""
    idx = np.zeros((dd, h, w), np.int64)
    zs, ys, xs = np.meshgrid(np.arange(dd), np.arange(h), np.arange(w), indexing='ij')
    bit = 0
    s = 1
    while s < w or s < h or s < dd:
        if s < w: idx |= ((xs & s) != 0).astype(np.int64) << bit; bit += 1
        if s < h: idx |= ((ys & s) != 0).astype(np.int64) << bit; bit += 1
        if s < dd: idx |= ((zs & s) != 0).astype(np.int64) << bit; bit += 1
        s <<= 1
    return idx


def rgb565(c):
    r = (c >> 11) & 31; g = (c >> 5) & 63; b = c & 31
    return np.stack([r * 255 // 31, g * 255 // 63, b * 255 // 31], -1)


def dxt(data, w, h, kind):
    bw, bh = (w + 3) // 4, (h + 3) // 4
    bs = 8 if kind == 1 else 16
    out = np.zeros((bh * 4, bw * 4, 4), np.uint8)
    b = np.frombuffer(data[:bw * bh * bs], np.uint8).reshape(bh * bw, bs)
    col = b[:, -8:]
    c0 = col[:, 0].astype(np.int32) | col[:, 1].astype(np.int32) << 8
    c1 = col[:, 2].astype(np.int32) | col[:, 3].astype(np.int32) << 8
    bits = col[:, 4].astype(np.int64) | col[:, 5].astype(np.int64) << 8 | col[:, 6].astype(np.int64) << 16 | col[:, 7].astype(np.int64) << 24
    p0, p1 = rgb565(c0).astype(np.int32), rgb565(c1).astype(np.int32)
    four = (c0 > c1) | (kind != 1)
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)  # n,4,3
    sel = np.stack([(bits >> (2 * i)) & 3 for i in range(16)], 1)  # n,16
    rgb = np.take_along_axis(pal, sel[:, :, None].repeat(3, 2), 1)  # n,16,3
    alpha = np.full((len(b), 16), 255, np.int32)
    if kind == 1:
        alpha = np.where((~four[:, None]) & (sel == 3), 0, 255)
    elif kind == 3:
        a = b[:, :8]
        av = np.stack([(a[:, i // 2] >> (4 * (i & 1))) & 15 for i in range(16)], 1).astype(np.int32)
        alpha = av * 17
    elif kind == 5:
        a0 = b[:, 0].astype(np.int32); a1 = b[:, 1].astype(np.int32)
        ab = sum(b[:, 2 + i].astype(np.int64) << (8 * i) for i in range(6))
        asel = np.stack([(ab >> (3 * i)) & 7 for i in range(16)], 1)
        ap = [a0, a1]
        for i in range(2, 8):
            ap.append(np.where(a0 > a1, ((8 - i) * a0 + (i - 1) * a1) // 7,
                               np.where(i < 6, ((6 - i) * a0 + (i - 1) * a1) // 5, 0 if i == 6 else 255)))
        ap = np.stack(ap, 1)
        alpha = np.take_along_axis(ap, asel.astype(np.int64), 1)
    px = np.concatenate([rgb, alpha[:, :, None]], 2).astype(np.uint8).reshape(bh, bw, 4, 4, 4)
    out = px.transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return out[:h, :w]


def encode_dxt5(img):
    """RGBA (h, w, 4), sides multiples of 4 -> DXT5 blocks, row by row: the
    colours' bounding box as end points (four-colour mode), alpha from its
    minimum to maximum in eight steps."""
    h, w, _ = img.shape
    px = img.reshape(h // 4, 4, w // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.int32)
    out = np.zeros((len(px), 16), np.uint8)
    a = px[:, :, 3]
    a0, a1 = a.max(1), a.min(1)
    ap = np.stack([a0, a1] + [((8 - i) * a0 + (i - 1) * a1) // 7 for i in range(2, 8)], 1)
    asel = np.abs(a[:, :, None] - ap[:, None, :]).argmin(2).astype(np.int64)
    asel[a0 == a1] = 0
    out[:, 0], out[:, 1] = a0, a1
    ab = sum(asel[:, i] << (3 * i) for i in range(16))
    for i in range(6): out[:, 2 + i] = (ab >> (8 * i)) & 255
    rgb = px[:, :, :3]
    hi, lo = rgb.max(1), rgb.min(1)
    q = lambda c: (c[:, 0] * 31 // 255) << 11 | (c[:, 1] * 63 // 255) << 5 | (c[:, 2] * 31 // 255)
    c0, c1 = q(hi), q(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = rgb565(c0).astype(np.int32), rgb565(c1).astype(np.int32)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)
    sel = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3).argmin(2).astype(np.int64)
    sel[c0 == c1] = 0
    out[:, 8], out[:, 9], out[:, 10], out[:, 11] = c0 & 255, c0 >> 8, c1 & 255, c1 >> 8
    bits = sum(sel[:, i] << (2 * i) for i in range(16))
    for i in range(4): out[:, 12 + i] = (bits >> (8 * i)) & 255
    return out.tobytes()


def textures(d):
    """The texture resources of an XPR0 pack: dicts of width, height,
    depth, format byte, mip levels and the data's offset in the file."""
    hdr = struct.unpack_from('<I', d, 8)[0]
    out, o = [], 12
    while struct.unpack_from('<I', d, o)[0] != 0xFFFFFFFF:
        common, data, _, fmt, _ = struct.unpack_from('<5I', d, o)
        if (common >> 16) & 7 == 4:
            dims = (fmt >> 4) & 15
            out.append({'w': 1 << ((fmt >> 20) & 15), 'h': 1 << ((fmt >> 24) & 15),
                        'd': 1 << ((fmt >> 28) & 15) if dims == 3 else 1, 'format': (fmt >> 8) & 0xFF,
                        'mips': (fmt >> 16) & 15, 'start': hdr + data})
        o += 20
    return out


def decode(path, outdir):
    d = open(path, 'rb').read()
    magic, total, hdr = struct.unpack_from('<4sII', d, 0)
    assert magic == b'XPR0', magic
    o = 12
    k = 0
    while True:
        common = struct.unpack_from('<I', d, o)[0]
        if common == 0xFFFFFFFF: break
        typ = (common >> 16) & 7
        if typ not in (4,):  # texture resources only (common type 4 = texture)
            print('resource type', typ, 'at', hex(o)); o += 20; continue
        _, data, lock, fmt, size = struct.unpack_from('<5I', d, o)
        dims = (fmt >> 4) & 15; f = (fmt >> 8) & 0xFF; mips = (fmt >> 16) & 15
        w = 1 << ((fmt >> 20) & 15); h = 1 << ((fmt >> 24) & 15); dd = 1 << ((fmt >> 28) & 15) if dims == 3 else 1
        start = hdr + data
        name = os.path.splitext(os.path.basename(path))[0] + ('_%d' % k if k else '')
        print('%s: %dx%d x%d fmt %02x mips %d data %x' % (name, w, h, dd, f, mips, start))
        if f == 0x06:  # A8R8G8B8 swizzled
            px = np.frombuffer(d[start:start + w * h * dd * 4], np.uint8).reshape(-1, 4)
            idx = unswizzle_index(w, h, dd)
            img = px[idx]  # dd,h,w,4  BGRA
            img = img[..., [2, 1, 0, 3]]
            for z in range(dd): png(os.path.join(outdir, '%s_z%d.png' % (name, z)), np.ascontiguousarray(img[z]))
        elif f in (0x0C, 0x0E, 0x0F):
            kind = {0x0C: 1, 0x0E: 3, 0x0F: 5}[f]
            bs = 8 if kind == 1 else 16
            # volumes keep each 4x4 block's slices together (up to four)
            if dd > 1:
                n = (w // 4) * (h // 4)
                raw = np.frombuffer(d[start:start + n * bs * dd], np.uint8).reshape(n, dd, bs)
                for z in range(dd): png(os.path.join(outdir, '%s_z%d.png' % (name, z)), dxt(raw[:, z].tobytes(), w, h, kind))
            else:
                png(os.path.join(outdir, name + '.png'), dxt(d[start:], w, h, kind))
        else:
            print('  format %02x not decoded' % f)
        o += 20; k += 1


if __name__ == '__main__':
    for p in sys.argv[2:]:
        decode(p, sys.argv[1])
