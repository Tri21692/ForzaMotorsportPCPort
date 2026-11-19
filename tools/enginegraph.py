"""An engine's power graph scale set in place: Cars.ca2 engines\\<engine>\\physics\\base.xml's GraphingMaxPower (hp:
the M3 GTR MW's was still 444, the M3 GTR's own, at 800 hp; the SC63's 600 at 700 hp: their graphs ran off the top,
the 4 Nov audit). At most 1000, the disc's most (2027 once went with a profile the game called damaged, 2 Nov).

  python tools/enginegraph.py <disc> <mods folder> <engine>=<max hp> ...
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def main(disc, mods, pairs):
    cars = addcar.Archive(disc, mods, 'Cars.ca2')
    for eng, hp in pairs:
        if not 0 < int(hp) <= 1000: raise SystemExit('%s: %s is outside 1..1000, the disc engines\' range' % (eng, hp))
        k = B.join(('engines', eng.lower(), 'physics', 'base.xml'))
        if k not in cars.files: raise SystemExit('no %s' % k)
        x, n = re.subn(rb'GraphingMaxPower="[\d.]+"', b'GraphingMaxPower="%d"' % int(hp), cars.files[k])
        if not n: raise SystemExit('%s has no GraphingMaxPower' % k)
        cars.files[k] = x
        print('%s: GraphingMaxPower %s' % (eng, hp))
    cars.check(); cars.write()


if __name__ == '__main__':
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], [a.split('=', 1) for a in sys.argv[3:]])
