r"""Forza Motorsport's .cab archives (media/cabs/car_*.cab and others).

Not Microsoft CABs. Layout, as read from the disc's files:

  0x00  u32 magic 0xC0C0AAAA
  0x04  u32 version (15)
  0x08  u32 entry count
  0x0C  u32 1
  0x10  u32 file size
  0x14  u32 total unpacked size (a little over the entries' sum)
  0x18  u32, u32 (equal; meaning unknown)
  0x30  u16 1
  0x32  the archive's root path, NUL-terminated: empty in car cabs,
        engines\eng_c5r427\ in a shared engine cab (names are relative to it)
  ...   zeros up to 0x132
  0x132 entries, 24 bytes each, sorted by hash:
          u32 offset of the data in the file, u32 packed size, u32
          unpacked size, u32 name offset, u32 0, u32 hash of the name
          (name_hash below)
  then  the names (NUL-terminated, backslashes), and the
        data: one zlib stream per entry, or the bytes as they are when the
        packed size equals the unpacked size.

media/cabs/Cars.ca2 is one of these, zlib-compressed whole; the installer
unpacks it to the cache partition as cars.cab (hdd/Partition4): every
car's physics, engine, liveries and config as XML.

Usage:
  python tools/forzacab.py list <file.cab>
  python tools/forzacab.py unpack <file.cab> <folder>
"""
import os
import struct
import sys
import zlib

MAGIC = 0xC0C0AAAA
TABLE = 0x132
ENTRY = 24


def name_hash(name):
    """Bob Jenkins' lookup2 (initial value 0) of the root path and name,
    lower-cased, backslashes kept, as the game's cab lookup (0x103630)
    computes it."""
    k = name.lower().encode('latin-1')
    M = 0xFFFFFFFF

    def mix(a, b, c):
        a = (a - b - c) & M; a ^= c >> 13
        b = (b - c - a) & M; b ^= (a << 8) & M
        c = (c - a - b) & M; c ^= b >> 13
        a = (a - b - c) & M; a ^= c >> 12
        b = (b - c - a) & M; b ^= (a << 16) & M
        c = (c - a - b) & M; c ^= b >> 5
        a = (a - b - c) & M; a ^= c >> 3
        b = (b - c - a) & M; b ^= (a << 10) & M
        c = (c - a - b) & M; c ^= b >> 15
        return a, b, c
    a = b = 0x9E3779B9
    c = 0
    i = 0
    while len(k) - i >= 12:
        a = (a + int.from_bytes(k[i:i + 4], 'little')) & M
        b = (b + int.from_bytes(k[i + 4:i + 8], 'little')) & M
        c = (c + int.from_bytes(k[i + 8:i + 12], 'little')) & M
        a, b, c = mix(a, b, c)
        i += 12
    c = (c + len(k)) & M
    for j, ch in enumerate(k[i:]):
        if j >= 8: c = (c + (ch << (8 * (j - 7)))) & M
        elif j >= 4: b = (b + (ch << (8 * (j - 4)))) & M
        else: a = (a + (ch << (8 * j))) & M
    return mix(a, b, c)[2]


def read(path):
    d = open(path, 'rb').read()
    magic, version, count = struct.unpack_from('<3I', d, 0)
    if magic != MAGIC:
        raise SystemExit('%s: not a Forza cab (magic %08x)' % (path, magic))
    names_at = TABLE + ENTRY * count
    root = d[0x32:d.index(b'\0', 0x32)].decode('latin-1')
    entries = []
    for i in range(count):
        off, packed, size, name_off, _, h = struct.unpack_from('<6I', d, TABLE + ENTRY * i)
        end = d.index(b'\0', names_at + name_off)
        entries.append({'hash': h, 'offset': off, 'packed': packed, 'size': size, 'root': root,
                        'name': d[names_at + name_off:end].decode('latin-1')})
    return d, version, entries


def data(d, e):
    raw = d[e['offset']:e['offset'] + e['packed']]
    if e['packed'] == e['size']:  # stored: small files that zlib would not shrink
        return raw
    u = zlib.decompress(raw)
    if len(u) != e['size']:
        raise ValueError('%s: %d bytes unpacked, expected %d' % (e['name'], len(u), e['size']))
    return u


def main(argv):
    if len(argv) < 3 or argv[1] not in ('list', 'unpack'):
        raise SystemExit(__doc__)
    d, version, entries = read(argv[2])
    if argv[1] == 'list':
        print('version %d, %d entries' % (version, len(entries)))
        for e in sorted(entries, key=lambda e: e['name']):
            print('%08x %9d %9d  %s' % (e['hash'], e['size'], e['packed'], e['name']))
        return
    out = argv[3]
    for e in entries:
        path = os.path.join(out, *e['name'].split('\\'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data(d, e))
    print('%d files into %s' % (len(entries), out))


if __name__ == '__main__':
    main(sys.argv)
