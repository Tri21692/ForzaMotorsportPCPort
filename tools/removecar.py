"""Take an added car out of the game (tools/addcar.py's): its carlist.xml entry and its model.dat and
gamecars.dat rows, so no menu, dealer or event lists it. Its files stay in the mods folder
(car_<name>.cab, cars\\<name>\\ in Cars.ca2, its liveries, icon tile and name strings), so addcar.py
can put it back later; an event that names it (a carid restriction or a CareerCarUnlock prize) is
refused, nothing written: take it out of the event first.

  python tools/removecar.py <disc> <mods folder> <car>...

Writes only into the mods folder, never the saves.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def remove(disc, mods, names):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = 'cars' + B + 'carlist.xml'
    xml = mega.files[key].decode('latin-1')
    disc_xml = next(v for k, v in mega.disc.items() if k.lower() == key).decode('latin-1')
    gone = {}
    for n in names:
        if re.search(r'<car name="%s"' % re.escape(n), disc_xml, re.I): raise SystemExit("%s is one of the disc's cars; nothing written" % n)
        m = addcar.car_block(xml, n)
        gone[n] = addcar.ordinal_of(xml, n)
        xml = xml[:m.start()] + xml[m.end():]
    # (not aicarmodelid: an AI car model is 100 + the ordinal, addcar.free_ordinal)
    named = re.compile(rb'(?i)(?:carid"\s+Func="="\s+Value|(?<!ai)carmodelid|careercarunlock|careercargift)="(%s)"'
                       % b'|'.join(str(o).encode() for o in gone.values()))
    users = sorted(k for k, v in mega.files.items() if k.lower().endswith('.xml') and k != key and named.search(v))
    if users: raise SystemExit('still named by %s; nothing written' % ', '.join(users))
    mega.files[key] = xml.encode('latin-1')
    for table, size in (('model.dat', 104), ('gamecars.dat', 176)):
        k = B.join(('forzadb', 'cardb', table))
        rows = addcar.table_rows(mega.files[k], size)
        mega.files[k] = b''.join(r for r in rows if struct.unpack_from('<I', r)[0] not in gone.values())
        print('%s: %d rows, %d before' % (table, len(mega.files[k]) // size, len(rows)))
    mega.check(); mega.write()
    for n, o in gone.items(): print('%s (ordinal %d): out of carlist.xml, model.dat and gamecars.dat' % (n, o))


if __name__ == '__main__':
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    remove(sys.argv[1], sys.argv[2], sys.argv[3:])
