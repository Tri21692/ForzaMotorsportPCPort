"""The add-on cars' own wheels (tires\\art\\<car>\\tire.carbin in the mods folder's Mega.ca2, made by
nfsu2forza.convert_wheel before 17 Nov 2026) with their rim's picture mapped as the game reads it, in place.

A wheel's texture coordinates count double (u16 / 32768, as Badge's): the game's own rims run to half of 65535 and
span the whole of wheel.xpr. convert_wheel wrote the rim's coordinates to half of 65535 too, meaning its picture's
quarter of the sheet (the top-left), so the rim's face was drawn with the whole sheet: the picture in a corner of
it, the template's hub caps and shading round it (the user's screenshots of 17 Nov: the 190E's hubcap among grey
blocks, a donor's yellow cap on other rims). Here every corner of the rim (material 11) of a wheel the disc does
not have is halved, unless it is within a quarter already (a wheel made since, or this run before).

  python tools/wheeluvfix.py <disc> <mods folder> [--dry] [car ...]

Writes only into the mods folder, never the saves.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin

B = chr(92)
RIM = 11


def main(disc, mods, only=(), dry=False):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    have = {k.lower() for k in mega.disc}
    n = 0
    for k in sorted(mega.files):
        kl = k.lower()
        if not (kl.startswith('tires' + B + 'art' + B) and kl.endswith(B + 'tire.carbin')) or kl in have: continue
        car = kl.split(B)[2]
        if only and car not in [o.lower() for o in only]: continue
        t = carbin.read(bytes(mega.files[k]))
        p = t['parts'][0]
        rim = sorted({i for sp in p['subparts'] if sp['material'] == RIM for i in sp['indices']})
        rest = {i for sp in p['subparts'] if sp['material'] != RIM for i in sp['indices']}
        rim = [i for i in rim if i not in rest]
        if not rim: print('%-28s no rim of its own' % car); continue
        top = max(max(p['verts'][i][10], p['verts'][i][11]) for i in rim)
        if top <= 0.26 * 65535:
            print('%-28s within a quarter already (to %.3f)' % (car, top / 65535)); continue
        verts = list(p['verts'])
        for i in rim:
            v = verts[i]
            verts[i] = tuple(v[:10]) + (v[10] // 2, v[11] // 2) + tuple(v[12:])
        p['verts'] = verts
        print('%-28s %5d rim corners halved (they ran to %.3f)' % (car, len(rim), top / 65535))
        if not dry: mega.files[k] = carbin.write(t)
        n += 1
    if n and not dry:
        mega.check(); mega.write()
    print('%d wheels%s' % (n, ' (dry run)' if dry else ''))


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if len(a) < 2: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(a[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % a[1])
    main(a[0], a[1], a[2:], '--dry' in sys.argv)
