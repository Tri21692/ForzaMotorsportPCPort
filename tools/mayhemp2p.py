"""Mayhem's races on point-to-point tracks made point-to-point races (the user's, 7 Nov: on Pacific and Fujimi "it's
showing lap instead of percentage", and the positions and restarts were wrong): tools/mayhemseries.py wrote every
Mayhem race type="Single" (a lap race), and a lap race on a road that doesn't loop has no line to finish a lap at.
Each Mayhem event whose track has a point-to-point race on the disc (events\\pointtopoint) gets the disc's type
("Point to Point") and its <stopatend /> (the cars stop at the road's end). In place: the series keeps its ordinals.

  python tools/mayhemp2p.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    txt = lambda k: bytes(mega.files[k]).decode('latin-1')
    p2p = set()
    for k in mega.files:
        if re.match(r'(?i)events\\pointtopoint\\ser\d+\.xml$', k):
            for e in re.findall(r'<event\b[^>]*type="Point to Point".*?</event>', txt(k), re.S):
                p2p.update(int(t) for t in re.findall(r'<track Ordinal="(\d+)"', e))
    print('point-to-point tracks: %s' % sorted(p2p))
    n = 0
    for k in sorted(mega.files):
        if not re.match(r'(?i)events\\mayhem\\ser\d+\.xml$', k): continue
        t = txt(k)

        def fix(m):
            e = m.group(0)
            tr = re.search(r'<track Ordinal="(\d+)"', e)
            if not tr or int(tr.group(1)) not in p2p: return e
            e2 = re.sub(r'type="[^"]*"', 'type="Point to Point"', e, count=1)
            if '<stopatend' not in e2: e2 = re.sub(r'(<pitting nopitting\s*/>)', r'\1 <stopatend />', e2, count=1)
            if e2 != e:
                print('%s: %s (track %s) made point to point' % (k, re.search(r'displayname="([^"]*)"', e).group(1), tr.group(1)))
            return e2
        t2 = re.sub(r'<event\b.*?</event>', fix, t, flags=re.S)
        if t2 != t:
            mega.files[k] = t2.encode('latin-1')
            n += 1
    if not n:
        print('nothing to change')
        return
    mega.check(); mega.write()


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
