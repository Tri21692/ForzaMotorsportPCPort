"""Gran Turismo 4's GT4.VOL: its file list and files (the layout as GT4FS reads it, github.com/Razer2015/GT4FS).

  python tools/gt4vol.py <GT4.VOL> list [<filter>]            every file: path, size, packed size
  python tools/gt4vol.py <GT4.VOL> extract <out dir> <path or prefix>...

The table of contents ("RoFS" 3.1, its magic XOR-ed when encrypted) sits on a 0x800 page boundary somewhere
in the first pages: a 0x40-byte header (version, compressed TOC length, page count, page length, entry count),
then entry count + 1 offsets (each XOR-ed with 0x14ac327a x its index + 1 when encrypted) bounding raw-deflate
compressed B-tree pages (XOR 0x55 when encrypted). A record page (flag 0) holds its records' slots at its end,
8 bytes each from the last: name offset, name length, info offset, info length; a name is a big-endian parent
node id and the name's bytes; the info is a type byte (0 directory: node id; 1 file: page, time, size;
2 compressed: page, time, packed size, size). File data is at the TOC's base + page count x page length + the
file's page x page length; a packed file starts C5 EE F7 FF and a negated size, then raw deflate.
"""
import os
import struct
import sys
import zlib

PAGE = 0x800
MAGIC_ENC = 0xAD90B9AC  # -0x526f4654 big-endian: "RoFS" XOR-ed
MAGIC = 0x526F4653      # "RoFS"
VERSION = 0x00030001


def xor_key(data, key):
    k = (key * (len(data) // len(key) + 1))[:len(data)]
    return bytes(a ^ b for a, b in zip(data, k))


class Volume:
    def __init__(self, path):
        self.f = open(path, 'rb')
        self.base = self.find_toc()
        f = self.f
        f.seek(self.base)
        magic = struct.unpack('>I', f.read(4))[0]
        self.encrypted = magic == MAGIC_ENC
        self.version, self.toc_len, self.page_count = struct.unpack('<IiI', f.read(12))
        self.page_len, self.entry_count = struct.unpack('<HH', f.read(4))
        self.data_offset = self.base + self.page_count * self.page_len
        f.seek(self.base + 0x40)
        offs = []
        for i in range(self.entry_count + 1):
            b = f.read(4)
            if self.encrypted: b = xor_key(b, struct.pack('<I', (0x14AC327A * (i + 1)) & 0xFFFFFFFF))
            offs.append(struct.unpack('<i', b)[0])
        self.pages = [(self.base + a, b - a) for a, b in zip(offs, offs[1:])]
        self.records = []
        for off, n in self.pages:
            f.seek(off)
            d = zlib.decompressobj(-15).decompress(f.read(n))  # (no final block marker: a one-shot decompress refuses it)
            if self.encrypted: d = bytes(x ^ 0x55 for x in d)
            self.read_page(d)
        self.dirs = {r['node']: r for r in self.records if r['type'] == 0}
        self.files = {}
        for r in self.records:
            if r['type'] in (1, 2) and r['name'] != '.': self.files[self.path_of(r)] = r

    def find_toc(self):
        for i in range(10000):
            self.f.seek(i * PAGE)
            h = self.f.read(8)
            if len(h) < 8: break
            m, v = struct.unpack('>I', h[:4])[0], struct.unpack('<I', h[4:])[0]
            if m in (MAGIC_ENC, MAGIC) and v == VERSION: return i * PAGE
        raise SystemExit('no RoFS 3.1 table of contents in the first pages')

    def read_page(self, d):
        flag, count = struct.unpack_from('<hh', d, 0)
        if flag != 0: return
        for i in range(count // 2):
            no, nl, io, il = struct.unpack_from('<hhhh', d, len(d) - (i * 8 + 8))
            parent = struct.unpack_from('>i', d, no)[0]
            name = d[no + 4:no + nl].decode('latin-1')
            t = d[io]
            r = {'name': name, 'parent': parent, 'type': t}
            if t == 0: r['node'] = struct.unpack_from('<i', d, io + 1)[0]
            elif t == 1: r['page'], r['time'], r['size'] = struct.unpack_from('<iIi', d, io + 1); r['packed'] = r['size']
            elif t == 2: r['page'], r['time'], r['packed'], r['size'] = struct.unpack_from('<iIii', d, io + 1)
            self.records.append(r)

    def path_of(self, r):
        parts = [r['name']]
        p = r['parent']
        while p and p in self.dirs and self.dirs[p]['parent'] != 0 and self.dirs[p]['name'] != '.':
            parts.append(self.dirs[p]['name'])
            p = self.dirs[p]['parent']
        return '/'.join(reversed(parts))

    def read(self, path):
        r = self.files[path]
        self.f.seek(self.data_offset + r['page'] * self.page_len)
        d = self.f.read(r['packed'])
        if len(d) > 8 and d[:4] == b'\xc5\xee\xf7\xff': d = zlib.decompressobj(-15).decompress(d[8:])
        return d


def main(argv):
    if len(argv) < 2: raise SystemExit(__doc__)
    v = Volume(argv[0])
    if argv[1] == 'list':
        want = argv[2].lower() if len(argv) > 2 else ''
        for p, r in sorted(v.files.items()):
            if want in p.lower(): print('%10d %10d  %s' % (r['size'], r['packed'], p))
        print('%d files' % len(v.files), file=sys.stderr)
    elif argv[1] == 'extract':
        out, wants = argv[2], [w.replace(chr(92), '/') for w in argv[3:]]
        n = 0
        for p in sorted(v.files):
            if not any(p == w or p.startswith(w.rstrip('/') + '/') for w in wants): continue
            dst = os.path.join(out, *p.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(v.read(p))
            n += 1
        print('%d files to %s' % (n, out))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
