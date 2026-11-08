"""A Mayhem series' race laps, in place (the user's, 7 Nov: "Make the lapped races slightly longer so we can catchup,
at least on Mayhem Championship": the rivals start spread round the lap ahead, and in 2 laps there was no catching
them). Each race's prize is worked out again from its new distance (mayhemmerge.prizes, the series' CR a km).

  python tools/mayhemlaps.py <disc> <mods folder> <series file, e.g. Ser00003.xml> <CR a km> <event ordinal>=<laps>...
  python tools/mayhemlaps.py <disc> <mods folder> --list      (every Mayhem race's laps)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import mayhemmerge

B = '\\'


def main(disc, mods, ser, *rest):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    keys = sorted(k for k in mega.files if k.lower().startswith('events' + B + 'mayhem' + B) and k.lower().endswith('.xml'))
    if ser == '--list':
        for k in keys:
            x = mega.files[k].decode('latin-1')
            print(k, re.search(r'<series [^>]*displayname="([^"]*)"', x).group(1))
            for e in re.findall(r'<event\b.*?</event>', x, re.S):
                print('  %s %-24s track %s, %s laps' % (re.search(r'eventordinal="(\d+)"', e).group(1), re.search(r'displayname="([^"]*)"', e).group(1),
                                                     re.search(r'<track Ordinal="(\d+)"', e).group(1), re.search(r'<laps count="(\d+)"', e).group(1)))
        return
    k = next(k for k in keys if k.lower().endswith(ser.lower()))
    want = dict(map(int, a.split('=')) for a in rest[1:])
    x = mega.files[k].decode('latin-1')

    def one(m):
        e = m.group(0)
        o = int(re.search(r'eventordinal="(\d+)"', e).group(1))
        return re.sub(r'<laps count="\d+"', '<laps count="%d"' % want.pop(o), e) if o in want else e
    mega.files[k] = re.sub(r'<event\b.*?</event>', one, x, flags=re.S).encode('latin-1')
    if want: raise SystemExit('no such events in %s: %s' % (k, sorted(want)))
    mayhemmerge.CR_PER_KM = int(rest[0])
    print(k)
    mayhemmerge.prizes(mega, k)
    mega.check(); mega.write()


if __name__ == '__main__':
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    main(*sys.argv[1:])
