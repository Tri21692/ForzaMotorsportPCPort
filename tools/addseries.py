"""Add a career series (an event series in the career's Club, Spec,
Pro Series, Endurance or Point-to-Point list) to the game.

  python tools/addseries.py <disc folder> <mods folder> <kind> <series.xml>
                            --name <text> --desc <text> [--event-name <text>]
                            [--logo <210x117 image>,<108x60 image>]
  e.g.  <disc>  run/mods_lambo  club  forced_induction.xml  --name "Forced Induction Cup"
        --desc "Open to turbocharged and supercharged cars in Class B."  --logo fi_lg.png,fi_sm.png

A series is events\\<kind>\\Ser<NNNNN>.xml in Mega.ca2: the game reads
Ser00001 up to the first number missing, so the new one is the next. The
given XML is that file with these left to fill in: {SERIES_NAME_ID},
{SERIES_DESC_ID}, {EVENT_NAME_ID}, {EVENT_DESC_ID} (strings, added to
media\\Loc\\<language>\\EventStrings.str, in English in every language) and
{ICON} (its logo's place).

The series list draws a series' logo from frontend\\<language>\\ico_events_lg.xpr
(210 x 117 tiles, 15 a row) and ico_events_sm.xpr (108 x 60 tiles, 25 a
row) in MegaXPR.ca2, by the series' Icon. The large strip has room past its
50 tiles, the small one none, and growing it in every language does not
fit in MegaXPR.ca2; so --logo takes the highest tile no series uses (the
disc's has seven, the art of series that were cut) in every language.

Restrictions (who may enter) name a car database field, as the executable's
lookup by name has them (0x170720): carid, power, torque, redline, gears,
weight, weightdist, pwr, perfclass, perfsubclass, value, minupgrade,
maxupgrade, aspiration, speed, acceleration, braking, handling, rarity,
make, family, location, region, year, drivetrain, engineplacement, body,
chassis and others; Func is =, <>, <, <=, >, >=; restrictions at the top
level must all hold, those in an <or> any one of them. String fields take
the names in forzadb\\cardb\\<field>.dat (aspiration: na, turbo,
twin_turbo, positive_super, cent_super).

Writes only into the mods folder, never the saves.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'
KINDS = ('club', 'spec', 'proseries', 'endurance', 'pointtopoint', 'onlinecareer')
LG, SM = (210, 117, 15), (108, 60, 25)  # tile width, height, tiles a row


def series_files(mega, kind):
    pre = B.join(('events', kind)) + B
    return {int(m.group(1)): k for k in mega.files for m in [re.match(re.escape(pre) + r'ser(\d{5})\.xml$', k, re.I)] if m}


def used_icons(mega):
    return {int(i) for k, v in mega.files.items() if k.lower().startswith(('events' + B, 'arcade' + B)) and k.lower().endswith('.xml')
            for i in re.findall(rb'\bIcon="(\d+)"', v)}


def linear(d):
    """A one-texture linear A8R8G8B8 XPR0 pack: (header size, width, height, pitch)."""
    hdr = struct.unpack_from('<I', d, 8)[0]
    fmt, size = struct.unpack_from('<II', d, 12 + 12)
    if (fmt >> 8) & 0xFF != 0x12: raise SystemExit('logo strip: format %02x, not linear A8R8G8B8' % ((fmt >> 8) & 0xFF))
    return hdr, (size & 0xFFF) + 1, ((size >> 12) & 0xFFF) + 1, ((size >> 24) + 1) * 64


def put_tile(d, index, img, tile):
    """The strip d with tile `index` (tile = width, height, a row) replaced by img (RGBA)."""
    hdr, w, h, pitch = linear(d)
    tw, th, per = tile
    x, y = index % per * tw, index // per * th
    if y + th > h or x + tw > w: raise SystemExit('logo strip %d x %d: no tile %d' % (w, h, index))
    d = bytearray(d)
    for r in range(th):
        o = hdr + (y + r) * pitch + x * 4
        d[o:o + tw * 4] = img[r][:, [2, 1, 0, 3]].tobytes()  # BGRA
    return bytes(d)


def tiles_in(d, tile):
    hdr, w, h, pitch = linear(d)
    return (w // tile[0]) * (h // tile[1])


def image(path, w, h):
    """An image file (anything ffmpeg reads) as RGBA, scaled to w x h. ffmpeg: XBRT_FFMPEG, or on the PATH."""
    import subprocess
    import numpy as np
    ff = os.environ.get('XBRT_FFMPEG') or 'ffmpeg'
    raw = subprocess.run([ff, '-v', 'error', '-i', path, '-vf', 'scale=%d:%d:flags=area' % (w, h), '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 4)


def add_strings(disc, mods, texts):
    """texts [(name, text)] added to EventStrings.str in every language; their ids."""
    loc = addcar.disc_file(disc, 'media', 'Loc')
    ids, out = None, {}
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'EventStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'EventStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        have = addcar.string_ids(base)
        if any(n in have for n, _ in texts): raise SystemExit('%s: %s is there already' % (mp, texts[0][0]))
        new = addcar.write_strings(base, texts)
        got = addcar.string_ids(new)
        these = tuple(got[n] for n, _ in texts)
        if ids not in (None, these): raise SystemExit('%s: the new string ids differ between languages' % lang)
        ids, out[mp] = these, new
    return ids, out


def main(disc, mods, kind, xml_path, name, desc, event_name=None, logo=None):
    if kind not in KINDS: raise SystemExit('kind: one of %s' % ', '.join(KINDS))
    mega, xpr = addcar.Archive(disc, mods, 'Mega.ca2'), addcar.Archive(disc, mods, 'MegaXPR.ca2')
    have = series_files(mega, kind)
    n = 1
    while n in have: n += 1
    key = B.join(('events', kind, 'Ser%05u.xml' % n))
    tag = re.sub(r'\W', '', name)
    ids, strings = add_strings(disc, mods, [('IDS_Mod_%s_Name' % tag, name), ('IDS_Mod_%s_Desc' % tag, desc),
                                            ('IDS_Mod_%s_EventName' % tag, event_name or name), ('IDS_Mod_%s_EventDesc' % tag, event_name or name)])
    icon = None
    if logo:
        lg_img, sm_img = (image(p, *size) for p, size in zip(logo.split(','), ((LG[0], LG[1]), (SM[0], SM[1]))))
        strips = sorted(k for k in xpr.files if re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I))
        room = min(tiles_in(xpr.files[k], LG if k.lower().endswith('lg.xpr') else SM) for k in strips)
        used = used_icons(mega)
        icon = max(i for i in range(room) if i not in used)
        for k in strips:
            lg = k.lower().endswith('lg.xpr')
            xpr.files[k] = put_tile(xpr.files[k], icon, (lg_img if lg else sm_img), LG if lg else SM)
        print('logo: tile %d of %d strips (no series used it)' % (icon, len(strips)))
    x = open(xml_path, encoding='latin-1').read()
    for k, v in (('{SERIES_NAME_ID}', ids[0]), ('{SERIES_DESC_ID}', ids[1]), ('{EVENT_NAME_ID}', ids[2]), ('{EVENT_DESC_ID}', ids[3]),
                 ('{ICON}', icon if icon is not None else 0)):
        x = x.replace(k, str(v))
    if '{' in x: raise SystemExit('%s: %s left to fill in' % (xml_path, re.search(r'\{\w+\}', x).group(0)))
    mega.files[key] = x.replace('\r\n', '\n').replace('\n', '\r\n').encode('latin-1')
    for a in (mega, xpr): a.check()
    for a in (mega, xpr): a.write()
    for mp, d in strings.items():
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(d)
    print('%s: "%s", strings %s' % (key, name, ids))


if __name__ == '__main__':
    args, opts, it = [], {}, iter(sys.argv[1:])
    for a in it:
        if a in ('--name', '--desc', '--event-name', '--logo'): opts[a[2:].replace('-', '_')] = next(it)
        else: args.append(a)
    if len(args) != 4 or 'name' not in opts or 'desc' not in opts: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, **opts)
