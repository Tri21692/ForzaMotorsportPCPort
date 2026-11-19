"""Add-on cars' cabs (media\\cabs\\car_<car>.cab) without the engine sounds they do not use, in place: the 4 Nov audit
found whole sound sets of the cars they were made from left in them (the Civic Si's in the Cobalt, Gallardo and
240SX SE, the SRT-4's in the Neons, the Bentley Speed 8's in the SC63, the Celica GT-S's in the Celicas), 1.4-2.2 MB
each. A car's engine is its tooldata.xml's <E0 File>; an engine folder another is kept if any file of the used
engine's names it. --dry: only says.

  python tools/cabclean.py <disc> <mods folder> [--dry] [car ...]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import forzacab

B = '\\'


def main(disc, mods, cars=None, dry=False):
    ca = addcar.Archive(disc, mods, 'Cars.ca2')
    d = os.path.join(mods, 'media', 'cabs')
    for f in sorted(os.listdir(d)):
        if not (f.lower().startswith('car_') and f.lower().endswith('.cab')): continue
        car = f[4:-4]
        if cars and car.lower() not in [c.lower() for c in cars]: continue
        tk = 'cars' + B + car.lower() + B + 'tooldata.xml'
        if tk not in ca.files: print('%s: not a car in Cars.ca2, left' % f); continue
        use = re.search(r'<E0 [^>]*File="([^"]*)"', ca.files[tk].decode('latin-1')).group(1).lower()
        p = os.path.join(d, f)
        files, root = addcar.cab_files(open(p, 'rb').read())
        engs = {}
        for k in files:
            g = re.match(r'engines[\\/]([^\\/]+)[\\/]', k, re.I)
            if g: engs.setdefault(g.group(1).lower(), []).append(k)
        if use not in engs: print('%s: its engine %s has no sound here, left' % (f, use)); continue
        mine = b''.join(files[k] for k in engs[use]).lower()
        drop = [e for e in engs if e != use and e.encode() not in mine]
        if not drop: print('%s: clean' % f); continue
        size = sum(len(files[k]) for e in drop for k in engs[e])
        print('%s: engine %s; drops %s (%.1f MB)' % (f, use, ', '.join(drop), size / 2 ** 20))
        if dry: continue
        for e in drop:
            for k in engs[e]: del files[k]
        open(p, 'wb').write(forzacab.pack(files, root))


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if len(a) < 2: raise SystemExit(__doc__)
    main(a[0], a[1], a[2:] or None, dry='--dry' in sys.argv)
