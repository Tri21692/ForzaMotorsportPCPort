"""Change the physics, upgrade lists and spec-screen figures of a car
already in the mods folder (one addcar.py added), as addcar.py's options do.

  python tools/tunecar.py <disc folder> <mods folder> <car>
                          [--physics-like <car>:<part>[,<part>...]]... [--tooldata-like <car>:<Section>[,...]]...
                          [--tires <front>,<rear>] [--final-drive <ratio>] [--mass <kg>]
                          [--performance <0-60 s>,<0-100 mph s>,<top km/h>] [--power <hp>]
  e.g.  <disc>  run/mods_lambo  ChevyCobaltSS  --tires 205/45R18,205/45R18  --final-drive 3.85

See addcar.py for what each does. Writes only into the mods folder, never the saves.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def main(disc, mods, car, physics_like=None, tooldata_like=None, tires=None, final_drive=None, mass=None, performance=None, power=None):
    mega, cars = addcar.Archive(disc, mods, 'Mega.ca2'), addcar.Archive(disc, mods, 'Cars.ca2')
    key = 'cars' + B + 'carlist.xml'
    xml = mega.files[key].decode('latin-1')
    entry = addcar.car_block(xml, car).group(0)
    o = addcar.ordinal_of(xml, car)
    mk, gk = B.join(('forzadb', 'cardb', 'model.dat')), B.join(('forzadb', 'cardb', 'gamecars.dat'))
    model, games = addcar.table_rows(mega.files[mk], 104), addcar.table_rows(mega.files[gk], 176)
    mrow, grow = bytearray(addcar.row_of(model, o)), bytearray(addcar.row_of(games, o))
    cdst = B.join(('cars', car.lower())) + B
    tk = cdst + 'tooldata.xml'
    ctx = {'files': cars.files, 'xml': xml, 'entry': entry, 'model': model, 'mrow': mrow, 'cdst': cdst, 'tool': cars.files[tk].decode('latin-1')}
    addcar.tune(ctx, physics_like, tooldata_like, tires, final_drive, mass)
    cars.files[tk] = ctx['tool'].encode('latin-1')
    if performance:
        t60, t100, vmax = performance
        struct.pack_into('<3f', mrow, 80, t60, t100, vmax / 3.6)
        struct.pack_into('<2f', grow, 48, t60, t100)
        struct.pack_into('<f', grow, 64, vmax / 3.6)
        print('spec screen: 0-60 mph %.1f s, 0-100 mph %.1f s, %.0f km/h' % performance)
    if power:  # the menus' power figure (gamecars.dat, tenths of a kilowatt); the engine itself is as it was
        struct.pack_into('<f', grow, 12, power * 0.745699872 * 10)
        print('menus: %.0f hp' % power)
    mega.files[key] = ctx['xml'].encode('latin-1')
    mega.files[mk] = addcar.put_row(model, bytes(mrow))
    mega.files[gk] = addcar.put_row(games, bytes(grow))
    for a in (mega, cars): a.check()
    for a in (mega, cars): a.write()


if __name__ == '__main__':
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a in ('--physics-like', '--tooldata-like'): opts.setdefault(a[2:].replace('-', '_'), []).append(next(it))
        elif a in ('--tires', '--final-drive', '--mass', '--performance', '--power'): opts[a[2:].replace('-', '_')] = next(it)
        else: args.append(a)
    if len(args) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, physics_like=opts.get('physics_like'), tooldata_like=opts.get('tooldata_like'), tires=opts.get('tires'),
         final_drive=float(opts['final_drive']) if 'final_drive' in opts else None,
         mass=float(opts['mass']) if 'mass' in opts else None,
         performance=tuple(float(x) for x in opts['performance'].split(',')) if 'performance' in opts else None,
         power=float(opts['power']) if 'power' in opts else None)
