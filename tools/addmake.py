"""Add a car maker to Forza: a dealer of its own, with its name and logo,
for cars added with addcar.py --make <maker>.

  python tools/addmake.py <disc folder> <mods folder> <name> --like <maker>
                          --logo <image> [--dealer <image>] [--id N]
  e.g.  <disc>  run/mods_lambo  Lamborghini  --like Ferrari  --logo crest.png

<name> is the maker's name as the menus show it (and its dealer's
background is found by it: frontend\\bkgd_dealership\\bkgd_<name>.xpr).
--like: a maker already there whose country (and so dealer region) the
new one takes, and whose dealer background stands in without --dealer.
--logo: the maker's emblem (any image ffmpeg reads; cropped to what is not
clear and fitted in 108 x 60). --dealer: the dealer's background, 512 x 512
(the disc's are a car close up in the left 418 x 480, black round it).
--id: the maker's number (by default the lowest no maker has, from 1).

What the game reads, in the mods folder's copy of each file if there is
one, else the disc's (26 Oct, from the executable):

  Mega.ca2     forzadb\\cardb\\make.dat: 28-byte rows in id order: u32 id,
               u32 country (location.dat; 4 Italy), u16 name string id,
               u16 logo slot, the English name (16 bytes, NUL-padded).
               The disc's ids run 2-63 with gaps; new ones stay below 64.
  MegaXPR.ca2  frontend\\ico_carlogo.xpr and gfx_carlogodisplay.xpr: the
               logos, one 108 x 60 slot each in a linear A8R8G8B8 strip
               108 wide (62 slots on the disc, all used). The widget's slot
               count is the strip's height / 60 (0x145490), so the strip
               grows by one slot (a linear texture may be 4096 high).
               frontend\\bkgd_dealership\\bkgd_<name>.xpr: the dealer's
               background (0x374076 builds the path from the name).
  media/Loc/*/CarDataStrings.str   IDS_Make_<id>_Name, in every language

The .ca2 archives keep at least as many 4 MB streams as the disc's (addcar.py).
Writes only into the mods folder, never the saves.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'
ROW = 28
LOGO_W, LOGO_H = 108, 60
MAX_ID = 63
STRIPS = ('ico_carlogo.xpr', 'gfx_carlogodisplay.xpr')


def makes(blob):
    """make.dat's rows: (id, country, string id, logo slot, name)."""
    out = []
    for o in range(0, len(blob), ROW):
        i, country, sid, logo = struct.unpack_from('<IIHH', blob, o)
        out.append((i, country, sid, logo, blob[o + 12:o + ROW].split(b'\0')[0].decode('latin-1')))
    return out


def make_row(i, country, sid, logo, name):
    if len(name) >= ROW - 12: raise SystemExit('%s: make.dat keeps names in %d bytes' % (name, ROW - 12 - 1))
    return struct.pack('<IIHH', i, country, sid, logo) + name.encode('latin-1').ljust(ROW - 12, b'\0')


def strip_size(d):
    """A linear texture's width, height and pitch, from its size word."""
    size = struct.unpack_from('<I', d, 12 + 16)[0]
    return (size & 0xFFF) + 1, ((size >> 12) & 0xFFF) + 1, ((size >> 24) + 1) * 64


def grow_strip(d, img):
    """The XPR0 strip `d` with one more slot at the bottom, holding `img`
    (60 x 108 RGBA); its size word, data and file size set to match."""
    hdr = struct.unpack_from('<I', d, 8)[0]
    fmt = struct.unpack_from('<I', d, 12 + 12)[0]
    if (fmt >> 8) & 0xFF != 0x12: raise SystemExit('logo strip: format %02x, not linear A8R8G8B8' % ((fmt >> 8) & 0xFF))
    w, h, pitch = strip_size(d)
    if (w, h % LOGO_H) != (LOGO_W, 0): raise SystemExit('logo strip: %d x %d, not slots of %d x %d' % (w, h, LOGO_W, LOGO_H))
    if h + LOGO_H > 4096: raise SystemExit('logo strip: %d slots, as many as a linear texture holds' % (h // LOGO_H))
    data = bytearray(d[hdr:hdr + pitch * h])
    slot = bytearray(pitch * LOGO_H)
    for y in range(LOGO_H):
        slot[y * pitch:y * pitch + LOGO_W * 4] = img[y][:, [2, 1, 0, 3]].tobytes()  # BGRA
    data += slot
    data += bytes(-len(data) % 2048)  # the disc's packs pad the data to 2 KB
    head = bytearray(d[:hdr])
    size = struct.unpack_from('<I', head, 12 + 16)[0]
    struct.pack_into('<I', head, 12 + 16, (size & ~(0xFFF << 12)) | ((h + LOGO_H - 1) << 12))
    struct.pack_into('<I', head, 4, len(head) + len(data))
    return bytes(head) + bytes(data), h // LOGO_H


def dealer_image(path):
    import numpy as np
    import nfsu2forza
    img = nfsu2forza.load_image(path, (512, 512))
    img = img.copy()
    img[..., 3] = 255  # the disc's backgrounds are opaque
    return np.ascontiguousarray(img)


def main(disc, mods, name, like, logo, dealer=None, mid=None):
    import nfsu2forza
    import forzaxpr
    mega, xpr = addcar.Archive(disc, mods, 'Mega.ca2'), addcar.Archive(disc, mods, 'MegaXPR.ca2')
    key = B.join(('forzadb', 'cardb', 'make.dat'))
    rows = makes(mega.files[key])
    by_name = {r[4].lower(): r for r in rows}
    if name.lower() in by_name: raise SystemExit('make.dat: %s is there already (id %d)' % (name, by_name[name.lower()][0]))
    if like.lower() not in by_name: raise SystemExit('make.dat: no maker named %s (%s)' % (like, ', '.join(r[4] for r in rows)))
    theirs = by_name[like.lower()]
    used = {r[0] for r in rows}
    if mid is None: mid = next((i for i in range(1, MAX_ID + 1) if i not in used), None)
    if mid is None or not 0 < mid <= MAX_ID or mid in used: raise SystemExit('make id %s: taken, or not 1-%d' % (mid, MAX_ID))

    # the logo, in both strips: the next slot
    img = nfsu2forza.load_image(logo, (LOGO_W, LOGO_H))
    slots = set()
    for s in STRIPS:
        k = B.join(('frontend', s))
        xpr.files[k], n = grow_strip(xpr.files[k], img)
        slots.add(n)
    if len(slots) != 1: raise SystemExit('the logo strips hold different numbers of slots: %s' % sorted(slots))
    slot = slots.pop()
    # the dealer's background
    bk = B.join(('frontend', 'bkgd_dealership', 'bkgd_%s.xpr' % theirs[4].lower()))
    mine = B.join(('frontend', 'bkgd_dealership', 'bkgd_%s.xpr' % name.lower()))
    xpr.files[mine] = forzaxpr.write_dxt5(xpr.files[bk], dealer_image(dealer)) if dealer else xpr.files[bk]

    # the name, in every language: the same id in each
    loc = addcar.disc_file(disc, 'media', 'Loc')
    sid, strings = None, {}
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'CarDataStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'CarDataStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        want = 'IDS_Make_%d_Name' % mid
        if want in addcar.string_ids(base): raise SystemExit('%s: %s is there already' % (lang, want))
        out = addcar.write_strings(base, [(want, name)])
        got = addcar.string_ids(out)[want]
        if sid not in (None, got): raise SystemExit('%s: the new string id differs between languages' % lang)
        sid, strings[mp] = got, out
    rows.append((mid, theirs[1], sid, slot, name))
    mega.files[key] = b''.join(make_row(*r) for r in sorted(rows))
    print('make.dat: %s, id %d, country %d (as %s), name string %d, logo slot %d; %d makers'
          % (name, mid, theirs[1], theirs[4], sid, slot, len(rows)))
    print('dealer: %s, %s' % (mine, 'from ' + dealer if dealer else "%s's" % theirs[4]))
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    for mp, out in strings.items():
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(out)


if __name__ == '__main__':
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a in ('--like', '--logo', '--dealer', '--id'): opts[a[2:]] = next(it)
        else: args.append(a)
    if len(args) != 3 or 'like' not in opts or 'logo' not in opts: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, like=opts['like'], logo=opts['logo'], dealer=opts.get('dealer'), mid=int(opts['id']) if 'id' in opts else None)
