"""A career category's level set in place: the user's, 7 Nov: "Mayhem Category unlocks at 15, and so does the event
inside"; then "Maybe make drift level 5". The category's lowest level is its series' (the Go Race list works it out),
and the series' races have no level of their own, so events\\<folder>\\Ser*.xml's Level="" is the one gate (added to
the series' head when it has none, as the Drift Championship's). In place: the series keep their ordinals (re-running
mayhemseries.py would renumber them; see the Mayhem notes).

  python tools/mayhemlevel.py <disc> <mods folder> <level> [<category folder>, Mayhem if none]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar


def main(disc, mods, level, folder='Mayhem'):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    n = 0
    for k in sorted(mega.files):
        if not re.match(r'(?i)events\\%s\\ser\d+\.xml$' % re.escape(folder), k): continue
        t = bytes(mega.files[k]).decode('latin-1')
        t2, c = re.subn(r'(<series\b[^>]*\bLevel=")\d+"', lambda g: g.group(1) + '%d"' % level, t, count=1)
        if not c: t2, c = re.subn(r'(<series\b[^>]*?)(\s*/?>)', lambda g: g.group(1) + ' Level="%d"' % level + g.group(2), t, count=1)
        if c:
            mega.files[k] = t2.encode('latin-1')
            n += 1
            print('%s: level %d' % (k, level))
    if not n: raise SystemExit('no %s series found' % folder)
    mega.check(); mega.write()


if __name__ == '__main__':
    if len(sys.argv) not in (4, 5): raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), *sys.argv[4:])
