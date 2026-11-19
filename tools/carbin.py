"""Forza Motorsport's car.carbin (the model in a car's cab): read it into
parts and write it back. See docs/research/cars.md.

  Car (chunk: u32 size, u32 version, name, contents)
    Attribs, Driver chunks (kept as bytes)
    u32 part count, Part chunks:
      u32 id, u32 name length, name
      Verts chunk (version 0): u32 count, 20-byte vertices
      Damage chunk: u32 count (0 or the vertex count), 12 bytes each
      Pivots chunk: u32 count (0 or 1), hinges
      Attributes chunk: three floats
      u32 subpart count, Subpart chunks (version 2): u32 id, u32 material,
        u32 primitive (6, triangle strip), u32 index count, 16 bytes,
        u16 indices
    the rest (Flare chunks) kept as bytes

Usage: python tools/carbin.py check <car.carbin>   (parse, rebuild, compare)
"""
import struct
import sys

VERT = struct.Struct('<3h3h4B2H')


def _chunk_head(d, o):
    size, ver = struct.unpack_from('<II', d, o)
    end = d.index(b'\0', o + 8)
    return size, ver, d[o + 8:end].decode('latin-1'), end + 1


def _chunk(name, ver, body):
    n = name.encode('latin-1') + b'\0'
    return struct.pack('<II', 8 + len(n) + len(body), ver) + n + body


def read(d):
    size, ver, name, p = _chunk_head(d, 0)
    assert name == 'Car', name
    car = {'version': ver, 'head': [], 'parts': []}
    for _ in range(2):  # Attribs, Driver
        s = _chunk_head(d, p)[0]
        car['head'].append(d[p:p + s])
        p += s
    nparts = struct.unpack_from('<I', d, p)[0]
    p += 4
    for _ in range(nparts):
        s, pver, pn, q = _chunk_head(d, p)
        assert pn == 'Part', pn
        pid, ln = struct.unpack_from('<II', d, q)
        part = {'version': pver, 'id': pid, 'name': d[q + 8:q + 8 + ln].decode('latin-1')}
        r = q + 8 + ln
        vs, vv, vn, vq = _chunk_head(d, r)
        assert vn == 'Verts', vn
        nv = struct.unpack_from('<I', d, vq)[0]
        part['verts'] = [VERT.unpack_from(d, vq + 4 + 20 * k) for k in range(nv)]
        part['verts_tail'] = d[vq + 4 + 20 * nv:r + vs]
        r += vs
        for key in ('Damage', 'Pivots', 'Attributes'):
            cs, cv, cn, cq = _chunk_head(d, r)
            assert cn == key, (part['name'], cn)
            part[key] = (cv, d[cq:r + cs])
            r += cs
        nsub = struct.unpack_from('<I', d, r)[0]
        r += 4
        part['subparts'] = []
        for _ in range(nsub):
            ss, sv, sn, sq = _chunk_head(d, r)
            assert sn == 'Subpart', sn
            sid, mat, prim, ni = struct.unpack_from('<4I', d, sq)
            extra = d[sq + 16:sq + 32]
            idx = list(struct.unpack_from('<%dH' % ni, d, sq + 32))
            tail = d[sq + 32 + 2 * ni:r + ss]
            part['subparts'].append({'version': sv, 'id': sid, 'material': mat, 'prim': prim, 'extra': extra, 'indices': idx, 'tail': tail})
            r += ss
        part['tail'] = d[r:p + s]
        car['parts'].append(part)
        p += s
    car['tail'] = d[p:size]
    return car


def write(car):
    out = [b''.join(car['head']), struct.pack('<I', len(car['parts']))]
    for part in car['parts']:
        nm = part['name'].encode('latin-1')
        verts = struct.pack('<I', len(part['verts'])) + b''.join(VERT.pack(*v) for v in part['verts']) + part['verts_tail']
        body = struct.pack('<II', part['id'], len(nm)) + nm + _chunk('Verts', 0, verts)
        for key in ('Damage', 'Pivots', 'Attributes'):
            body += _chunk(key, part[key][0], part[key][1])
        body += struct.pack('<I', len(part['subparts']))
        for sp in part['subparts']:
            sb = struct.pack('<4I', sp['id'], sp['material'], sp['prim'], len(sp['indices'])) + sp['extra'] + \
                struct.pack('<%dH' % len(sp['indices']), *sp['indices']) + sp['tail']
            body += _chunk('Subpart', sp['version'], sb)
        body += part['tail']
        out.append(_chunk('Part', part['version'], body))
    out.append(car['tail'])
    return _chunk('Car', car['version'], b''.join(out))


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != 'check':
        raise SystemExit(__doc__)
    d = open(sys.argv[2], 'rb').read()
    car = read(d)
    w = write(car)
    tails = sum(1 for p in car['parts'] if p['tail'] or p['verts_tail']) + sum(1 for p in car['parts'] for s in p['subparts'] if s['tail'])
    print('%d parts, %d bytes; rebuilt %s; %d leftovers' % (len(car['parts']), len(d), 'identical' if w == d else 'DIFFERENT (%d bytes)' % len(w), tails))
