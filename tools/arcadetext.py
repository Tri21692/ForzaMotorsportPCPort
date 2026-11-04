"""Cars' Arcade unlock text cleared in place (model.dat's u16 at 78 set to 1, none), for add-on cars that copied a
disc car's ("Finish Arcade Series 9 in at least third place to unlock this car.": the disc Silvia's, which that
series' prize list unlocks, arcade\\ser00009.xml) though no Arcade series names them: the 4 Nov audit.

  python tools/arcadetext.py <disc> <mods folder> <car> ...
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def main(disc, mods, cars):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    xml = mega.files['cars' + B + 'carlist.xml'].decode('latin-1')
    mk = B.join(('forzadb', 'cardb', 'model.dat'))
    for car in cars:
        o = addcar.ordinal_of(xml, car)
        model = addcar.table_rows(mega.files[mk], 104)
        row = bytearray(addcar.row_of(model, o))
        was = struct.unpack_from('<H', row, 78)[0]
        struct.pack_into('<H', row, 78, 1)
        mega.files[mk] = addcar.put_row(model, bytes(row))
        print('%s (%d): Arcade text %d -> none' % (car, o, was))
    mega.check(); mega.write()


if __name__ == '__main__':
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
