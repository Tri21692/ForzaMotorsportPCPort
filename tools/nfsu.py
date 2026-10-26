"""Need for Speed Underground (PC) car geometry: CARS/<car>/GEOMETRY.BIN.

EA's chunk format: u32 id, u32 size, then the body; ids with bit 31 set
hold more chunks. Chunks whose data must be aligned start with 0x11
padding bytes. In a car's GEOMETRY.BIN:

  80134000 the car
    80134001 header: 00134002 (the file's path), 00134003, 00134004
    80134010 one part, 400 on the 240SX
      00134011 part header, 176 bytes; the name at 0x94 (240SX_KIT00_BODY_A)
      00134012 texture hashes, 8 bytes each (u32 hash, u32 0); a group's u32 at 0x1C picks one
      00134013 shader hashes, 8 bytes each; a group's u32 at 0x20 picks one
      80134100 mesh
        00134900 descriptor: after 0x11 padding, ... u32 triangles at
                 +0x30, u32 vertices at +0x40 (from the chunk body)
        00134b01 vertices, 36 bytes: float3 position (x forward, y left,
                 z up, metres), float3 normal, u32 colour, float2 u, v
        00134b02 groups: one per material, 0x3C bytes after the padding: float3 min, u32 index count, float3 max, u32, ..., u32 first index
        00134b03 u16 indices, triangle lists
  80034020 (not decoded)

Part names: <CAR>_KIT00_* is the stock car, KIT01-15 body kits (bumpers,
skirts), STYLE01-20 hoods, spoilers and roofs; _A to _D are detail levels,
_A the finest.

Usage: python tools/nfsu.py list <GEOMETRY.BIN>
"""
import struct
import sys

PAD = 0x11111111


def chunks(d, o, end):
    while o + 8 <= end:
        cid, size = struct.unpack_from('<II', d, o)
        yield cid, o + 8, size
        o += 8 + size


def unpadded(d, o, size):
    """The body of a chunk after its 0x11 alignment padding."""
    end = o + size
    while o + 4 <= end and struct.unpack_from('<I', d, o)[0] == PAD:
        o += 4
    return o, end


def read(path):
    d = open(path, 'rb').read()
    parts = []
    for cid, o, size in chunks(d, 0, len(d)):
        if cid != 0x80134000:
            continue
        for pid, po, psize in chunks(d, o, o + size):
            if pid != 0x80134010:
                continue
            part = {'name': '', 'textures': [], 'shaders': [], 'verts': [], 'tris': [], 'groups': [], 'materials': []}
            head, raw_groups = None, b''
            for sid, so, ssize in chunks(d, po, po + psize):
                if sid == 0x00134011:
                    head = so
                elif sid == 0x00134012:
                    part['textures'] = list(struct.unpack_from('<%dI' % (ssize // 4), d, so)[::2])
                elif sid == 0x00134013:
                    part['shaders'] = list(struct.unpack_from('<%dI' % (ssize // 4), d, so)[::2])
                elif sid == 0x80134100:
                    for mid, mo, msize in chunks(d, so, so + ssize):
                        if mid == 0x00134b01:
                            a, end = unpadded(d, mo, msize)
                            n = (end - a) // 36
                            part['verts'] = [struct.unpack_from('<6fI2f', d, a + 36 * k) for k in range(n)]
                        elif mid == 0x00134b03:
                            a, end = unpadded(d, mo, msize)
                            idx = struct.unpack_from('<%dH' % ((end - a) // 2), d, a)
                            part['tris'] = [idx[k:k + 3] for k in range(0, len(idx) - 2, 3)]
                        elif mid == 0x00134b02:
                            a, end = unpadded(d, mo, msize)
                            raw_groups = d[a:end]
                        elif mid == 0x00134c02:  # Most Wanted: a group's material name, one per group in order
                            part['materials'].append(d[mo:d.index(b'\0', mo)].decode('latin-1'))
            mw = bool(part['materials'])
            if head is not None:
                at = head + (0xA0 if mw else 0x94)
                part['name'] = d[at:d.index(b'\0', at)].decode('latin-1')
            if not mw:
                part['groups'] = [raw_groups[k:k + 0x3C] for k in range(0, len(raw_groups) - 0x3B, 0x3C)]
            else:
                # Most Wanted's groups are 104 bytes: float3 min, float3 max, the
                # texture index in the bytes at 0x18, u32 vertices at 0x3C, u32
                # triangles at 0x40, u32 first index at 0x44. They are given here
                # as Underground's (index count at 12, texture and shader indexes
                # at 0x1C and 0x20, first index at 0x34); the "shaders" are the
                # groups' material names (bhash), one per group.
                part['mw_shaders'] = part['shaders']
                part['shaders'] = [bhash(m) for m in part['materials']]
                for g in range(len(raw_groups) // 104):
                    r = raw_groups[104 * g:104 * (g + 1)]
                    tris, first = struct.unpack_from('<II', r, 0x40)
                    out = bytearray(0x3C)
                    out[0:12], out[16:28] = r[0:12], r[12:24]
                    struct.pack_into('<I', out, 12, 3 * tris)
                    struct.pack_into('<II', out, 0x1C, r[0x18], g)
                    struct.pack_into('<I', out, 0x34, first)
                    part['groups'].append(bytes(out))
            parts.append(part)
    return parts


def bhash(s, h=0xFFFFFFFF):
    """EA's name hash (as the shaders' and textures' ids)."""
    for c in s.encode('latin-1'):
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


def jdlz(src):
    """EA's JDLZ: 'JDLZ', 0x02, 0x10, u16 0, u32 unpacked size, u32 packed
    size, then LZ with two flag streams (literal or match; short or long
    match)."""
    assert src[:4] == b'JDLZ', src[:4]
    size = struct.unpack_from('<I', src, 8)[0]
    out = bytearray(size)
    i, o, f1, f2 = 16, 0, 1, 1
    while i < len(src) and o < size:
        if f1 == 1:
            f1 = src[i] | 0x100; i += 1
        if f2 == 1:
            f2 = src[i] | 0x100; i += 1
        if f1 & 1:
            if f2 & 1:
                length = (src[i + 1] | ((src[i] & 0xF0) << 4)) + 3
                back = (src[i] & 0x0F) + 1
            else:
                back = (src[i + 1] | ((src[i] & 0xE0) << 3)) + 17
                length = (src[i] & 0x1F) + 3
            i += 2
            for k in range(min(length, size - o)):
                out[o + k] = out[o + k - back]
            o += length
            f2 >>= 1
        else:
            out[o] = src[i]; i += 1; o += 1
        f1 >>= 1
    return bytes(out)


def read_textures(path):
    """TEXTURES.BIN, a texture pack: b3300000 holding b3310000 (33310002
    hashes, 33310004 headers, 33310005 32-byte format entries) and b3320000
    (33320002 the pixels). 33310003 gives each texture's hash, file offset
    and packed size: each is JDLZ-compressed on its own. A header, 124
    bytes: the name at 0x0C (24 bytes, cut short), u32 hash at 0x24, u32
    class, u32, u32 start and u32 end (in the unpacked whole) at 0x30, u32
    top level's size, u16 width and height at 0x44.
    A format entry: the FourCC at
    0x14 (DXT1, DXT3, DXT5) or 0 for 32-bit BGRA. Not swizzled."""
    d = open(path, 'rb').read()
    heads, fmts, packed = b'', b'', b''
    for cid, o, size in chunks(d, 0, len(d)):
        if cid != 0xB3300000:
            continue
        for sid, so, ssize in chunks(d, o, o + size):
            for tid, to, tsize in chunks(d, so, so + ssize):
                if tid == 0x33310003: packed = d[to:to + tsize]
                elif tid == 0x33310004: heads = d[to:to + tsize]
                elif tid == 0x33310005: fmts = d[to:to + tsize]
    where = {}
    for k in range(len(packed) // 20):  # 33310003: u32 hash, u32 file offset, u32 packed size, u32 0x100, u32 0
        th, off, psize = struct.unpack_from('<3I', packed, 20 * k)
        where[th] = (off, psize)
    out = {}
    for k in range(len(heads) // 124):
        h = heads[124 * k:124 * (k + 1)]
        name = h[0x0C:0x24].split(b'\0')[0].decode('latin-1')
        thash, _, _, start, end, top = struct.unpack_from('<6I', h, 0x24)
        w, hh = struct.unpack_from('<HH', h, 0x44)
        fourcc = fmts[32 * k + 0x14:32 * k + 0x18]
        data = b''
        if thash in where:
            off, psize = where[thash]
            data = jdlz(d[off:off + psize])
        out[thash] = {'name': name, 'width': w, 'height': hh, 'fourcc': fourcc.rstrip(b'\0').decode('latin-1'),
                      'size': end - start, 'top': top, 'data': data}
    if not heads:
        # Most Wanted: no header chunks. 33310003 entries are 24 bytes (u32
        # hash, u32 file offset, u32 packed size, u32 unpacked size, u32
        # flags, u32 0); each texture unpacks to its top level's pixels and
        # then a 0x9C-byte header: the name at 0x0C, u32 hash at 0x24, u16
        # width and height at 0x44, the FourCC at 0x90. JDLZ or HUFF (not
        # decoded: those textures come back without data).
        for k in range(len(packed) // 24):
            th, off, psize, usize = struct.unpack_from('<4I', packed, 24 * k)
            blob = d[off:off + psize]
            if blob[:4] != b'JDLZ':
                out[th] = {'name': '', 'width': 0, 'height': 0, 'fourcc': '', 'size': 0, 'top': 0, 'data': b'',
                           'packing': blob[:4].decode('latin-1')}
                continue
            u = jdlz(blob)
            h = u[-0x9C:]
            w, hh = struct.unpack_from('<HH', h, 0x44)
            out[th] = {'name': h[0x0C:0x24].split(b'\0')[0].decode('latin-1'), 'width': w, 'height': hh,
                       'fourcc': h[0x90:0x94].rstrip(b'\0').decode('latin-1'), 'size': len(u) - 0x9C, 'top': len(u) - 0x9C,
                       'data': u[:-0x9C]}
    return out


def main(argv):
    if len(argv) >= 3 and argv[1] == 'textures':
        for h, t in sorted(read_textures(argv[2]).items(), key=lambda kv: kv[1]['name']):
            print('%08x %-28s %4dx%-4d %-4s %d bytes' % (h, t['name'], t['width'], t['height'], t['fourcc'] or 'BGRA', len(t['data'])))
        return
    if len(argv) < 3 or argv[1] != 'list':
        raise SystemExit(__doc__)
    for p in read(argv[2]):
        print('%-40s %5d verts %5d tris %d groups, textures %s' % (
            p['name'], len(p['verts']), len(p['tris']), len(p['groups']), ' '.join('%08x' % t for t in p['textures'])))


if __name__ == '__main__':
    main(sys.argv)
