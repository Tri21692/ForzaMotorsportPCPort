"""Read a track's scenery bundle (QuickPreview1.xb2, unpacked: the cache's
<track>.res).

The xb2 is zlib streams of 4 MB, each padded to 2048 bytes; unpacked:

  0x00  u32 0xc0c0aaaa, 15, resource count, 0; u32 the size twice; u32 the
        index's size twice; 0, 0; u32 the names' size twice; u32 0x200
  0x202 per resource 24 bytes: u32 its header's offset (in the headers),
        u32 its name's hash, u32 its data's place, u32 its size twice, u32
        its name's offset (from the names)
  then the names (NUL-terminated)

  python tools/xb2.py <xb2 or res> [name filter]   lists the resources
"""
import struct
import sys
import zlib

INDEX = 0x202


def unpack(path):
    d = open(path, 'rb').read()
    if d[:4] == b'\xaa\xaa\xc0\xc0': return d
    out, off = bytearray(), 0
    while off < len(d) and d[off] == 0x78:
        o = zlib.decompressobj()
        out += o.decompress(d[off:])
        off = (off + len(d) - off - len(o.unused_data) + 2047) & ~2047
    return bytes(out)


def resources(d):
    """[(name, header offset, hash, data word, size, size2, record offset)]"""
    base = d.index(b'resnametable\0', INDEX)  # the names: the bundle's own nine first
    out = []
    for i in range((base - INDEX) // 24):
        o = INDEX + 24 * i
        out.append(struct.unpack_from('<6I', d, o) + (o,))
    res = []
    for hdr, h, data, s1, s2, name, o in out:
        e = d.index(b'\0', base + name)
        res.append((d[base + name:e].decode('latin-1'), hdr, h, data, s1, s2, o))
    return res, base


if __name__ == '__main__':
    d = unpack(sys.argv[1])
    res, base = resources(d)
    print('%d resources, names at %#x' % (len(res), base))
    for r in res:
        if len(sys.argv) < 3 or sys.argv[2].lower() in r[0].lower():
            print('%-70s hdr %6x hash %08x data %08x size %8x %8x' % r[:6])
