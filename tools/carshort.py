"""Cars' short names (the narrow menus' name) set in place: carlist.xml's shortName and IDS_Model_<ordinal>_ShortName
in every language's CarDataStrings.str. The 4 Nov audit: four add-on D-Specs had short names of 17-21 characters
(the disc's longest is 15: 'WingsWest Civic'), cut off in the narrow lists.

  python tools/carshort.py <disc> <mods folder> <car>=<short name> ...
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'
LIMIT = 15


def main(disc, mods, pairs):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = 'cars' + B + 'carlist.xml'
    xml = mega.files[key].decode('latin-1')
    want = {}
    for car, short in pairs:
        if len(short) > LIMIT: raise SystemExit('%s: %r is over %d characters' % (car, short, LIMIT))
        o = addcar.ordinal_of(xml, car)
        blk = addcar.car_block(xml, car)
        head = re.sub(r'shortName="[^"]*"', 'shortName="%s"' % short, blk.group(0), count=1)
        xml = xml[:blk.start()] + head + xml[blk.end():]
        want['IDS_Model_%d_ShortName' % o] = short
        print('%s (%d): %s' % (car, o, short))
    mega.files[key] = xml.encode('latin-1')
    mega.check(); mega.write()
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'CarDataStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()  # (read before the file is opened to write: that empties it)
        ids = addcar.string_ids(d)
        ch = {ids[n]: s for n, s in want.items() if n in ids}
        open(mp, 'wb').write(addcar.replace_strings(d, ch))
        print(lang, '%d short names' % len(ch))


if __name__ == '__main__':
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], [a.split('=', 1) for a in sys.argv[3:]])
