"""A copy of the extracted disc with a mods folder's files in it, for another port or an emulator
that has no mods folder (this port's XBRT_MODS).

    python tools/moddisc.py <disc folder> <mods folder> <out folder> [--zone-lead N]

The mods folder's media\\ files go over the disc's. For each .ca2 replaced, default.xbe's installer
table (the BKGDINST section: a SHA-1 record per 4 MB stream, which the game checks) is rewritten to
describe the mod's archive, and the section's digest in the image header made anew, as file.c does
in memory. An archive with more streams than the disc's cannot be described there (the table has no
room): it is refused. Left out, as this port does them and others do not: hdd\\ (cache overrides),
track\\ (a track's own files), *.replaced, and XBRT_CAREER_TIMETRIAL's Time Trial category (the
runtime changes the game's code for it). --zone-lead N puts XBRT_ZONE_LEAD's setting in
tracklist.xml itself (every track's ZoneWindowLeadCount, 1 on the disc), in Mega.ca2.
"""
import hashlib
import os
import re
import shutil
import struct
import sys
import zlib

CHUNK = 4 << 20
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def streams(path):
    """(offset, packed length, SHA-1 of the unpacked data) per zlib stream, and the last one's size."""
    d, out, off, last = open(path, 'rb').read(), [], 0, 0
    while off + 2 <= len(d) and d[off] == 0x78:
        z = zlib.decompressobj()
        raw = z.decompress(d[off:])
        used = len(d) - off - len(z.unused_data)
        out.append(struct.pack('<II', off, used) + hashlib.sha1(raw).digest())
        last = len(raw)
        off = (off + used + 2047) & ~2047
    if any(d[off:]):
        raise SystemExit('%s: not an installer archive (data after the streams)' % path)
    return out, last


def sections(xbe):
    base = struct.unpack_from('<I', xbe, 0x104)[0]
    n, at = struct.unpack_from('<II', xbe, 0x11C)
    for i in range(n):
        h = at - base + i * 0x38
        name = struct.unpack_from('<I', xbe, h + 0x14)[0] - base
        yield xbe[name:xbe.index(b'\0', name)].decode('latin-1'), h


def patch_xbe(xbe, disc_ca2, mod_ca2):
    want, _ = streams(disc_ca2)
    have, last = streams(mod_ca2)
    if len(have) != len(want):
        raise SystemExit('%s: %d streams of 4 MB, the disc\'s %d: only this port takes a different count'
                         % (mod_ca2, len(have), len(want)))
    h = dict(sections(xbe))['BKGDINST']
    raw, size = struct.unpack_from('<II', xbe, h + 0x0C)
    n, nrec = struct.unpack_from('<II', xbe, raw + 8)
    recs = raw + 20 + 20 * n
    for i in range(n):
        e = raw + 20 + 20 * i
        first, count = struct.unpack_from('<II', xbe, e + 8)
        if count == len(want) and bytes(xbe[recs + 28 * first:recs + 28 * (first + count)]) == b''.join(want):
            xbe[recs + 28 * first:recs + 28 * (first + count)] = b''.join(have)
            struct.pack_into('<I', xbe, e + 16, last)
            xbe[h + 0x24:h + 0x38] = hashlib.sha1(struct.pack('<I', size) + bytes(xbe[raw:raw + size])).digest()
            return
    raise SystemExit('%s: the installer has no records of the disc\'s archive' % disc_ca2)


def zone_lead(path, n):
    """Mega.ca2 at path with every track's ZoneWindowLeadCount set to n."""
    import addcar
    import forzacab
    files, root = addcar.cab_files(addcar.unpack_ca2(path))
    key = next(k for k in files if k.lower() == 'forzadb\\tracklist.xml')
    files[key], count = re.subn(rb'ZoneWindowLeadCount="\d"', b'ZoneWindowLeadCount="%d"' % n, files[key])
    open(path, 'wb').write(forzacab.ca2(forzacab.pack(files, root)))
    print('  zone lead %d for %d tracks, in Mega.ca2' % (n, count))


def main(disc, mods, out, lead=None):
    if os.path.exists(out):
        raise SystemExit('%s exists; give a new folder' % out)
    print('copying the disc to', out)
    shutil.copytree(disc, out)
    xbe = bytearray(open(os.path.join(out, 'default.xbe'), 'rb').read())
    for root, _, files in os.walk(os.path.join(mods, 'media')):
        for f in files:
            if f.endswith('.replaced'): continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, mods)
            dst = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    if lead: zone_lead(os.path.join(out, 'media', 'cabs', 'Mega.ca2'), lead)
    cabs = os.path.join(out, 'media', 'cabs')
    for f in os.listdir(cabs):
        rel = os.path.join('media', 'cabs', f)
        if f.lower().endswith('.ca2') and open(os.path.join(out, rel), 'rb').read() != open(os.path.join(disc, rel), 'rb').read():
            patch_xbe(xbe, os.path.join(disc, rel), os.path.join(out, rel))
            print('  %s, and its records in default.xbe' % rel)
    open(os.path.join(out, 'default.xbe'), 'wb').write(xbe)
    for skipped in ('hdd', 'track'):
        if os.path.isdir(os.path.join(mods, skipped)):
            print('left out: %s\\ (this port only)' % skipped)


if __name__ == '__main__':
    a, lead = sys.argv[1:], None
    if '--zone-lead' in a:
        i = a.index('--zone-lead')
        lead = int(a[i + 1])
        del a[i:i + 2]
        if not 1 <= lead <= 8: raise SystemExit('--zone-lead takes 1 to 8')
    if len(a) != 3: raise SystemExit(__doc__)
    main(*a, lead=lead)
