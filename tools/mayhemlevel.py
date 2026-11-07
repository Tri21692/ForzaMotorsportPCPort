"""The Mayhem Tour's level set in place (the user's, 7 Nov: "Mayhem Category unlocks at 15, and so does the event
inside"). The category's lowest level is its series' (the Go Race list works it out), and the series' races have no
level of their own, so events\\Mayhem\\Ser*.xml's Level="" is the one gate. In place: the series keeps its ordinal
(re-running mayhemseries.py would renumber it; see the Mayhem notes).

  python tools/mayhemlevel.py <disc> <mods folder> <level>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar


def main(disc, mods, level):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    n = 0
    for k in sorted(mega.files):
        if not re.match(r'(?i)events\\mayhem\\ser\d+\.xml$', k): continue
        t = bytes(mega.files[k]).decode('latin-1')
        t2, c = re.subn(r'(<series\b[^>]*\bLevel=")\d+"', lambda g: g.group(1) + '%d"' % level, t, count=1)
        if c:
            mega.files[k] = t2.encode('latin-1')
            n += 1
            print('%s: level %d' % (k, level))
    if not n: raise SystemExit('no Mayhem series found')
    mega.check(); mega.write()


if __name__ == '__main__':
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
