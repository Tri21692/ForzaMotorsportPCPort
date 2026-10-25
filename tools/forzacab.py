"""Forza Motorsport's .cab archives (media/cabs/car_*.cab and others).

Not Microsoft CABs. Layout, as read from the disc's files:

  0x00  u32 magic 0xC0C0AAAA
  0x04  u32 version (15)
  0x08  u32 entry count
  0x0C  u32 1
  0x10  u32 file size
  0x14  u32 total unpacked size (a little over the entries' sum)
  0x18  u32, u32 (equal; meaning unknown)
  ...   zeros up to 0x12E
  0x12E entries, 24 bytes each, sorted by hash:
          u32 hash of the name, u32 offset of the data in the file,
          u32 packed size, u32 unpacked size, u32 name offset, u32 0
  then  u32 (unknown), the names (NUL-terminated, backslashes), and the
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
TABLE = 0x12E
ENTRY = 24


def read(path):
    d = open(path, 'rb').read()
    magic, version, count = struct.unpack_from('<3I', d, 0)
    if magic != MAGIC:
        raise SystemExit('%s: not a Forza cab (magic %08x)' % (path, magic))
    names_at = TABLE + ENTRY * count + 4
    entries = []
    for i in range(count):
        h, off, packed, size, name_off, _ = struct.unpack_from('<6I', d, TABLE + ENTRY * i)
        end = d.index(b'\0', names_at + name_off)
        entries.append({'hash': h, 'offset': off, 'packed': packed, 'size': size,
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
