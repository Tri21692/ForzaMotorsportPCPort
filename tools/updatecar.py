"""Put a converted body (nfsu2forza.py's output) into a car already added
with addcar.py, keeping the rest of it (engine, sound, physics, paints).

  python tools/updatecar.py <disc folder> <mods folder> <car> <converter output folder> [--upgrades]
                           [--wheel <tire.carbin>,<wheel.xpr>]
  e.g.  <disc>  run/mods_lambo  ChevyCobaltSS  scr/cobalt_out  --upgrades

From the output folder (car.carbin, liveries/standard/livery0*.xpr,
liveries.bin, upgrades.xml):

  car_<car>.cab                    cars\\<car>\\car.carbin and the three livery atlases
  media/cars/<car>.liveries.bin    the paint shop's copy, if there is one
  Cars.ca2                         --upgrades: tooldata.xml's FrontBumper, RearBumper,
                                   SideSkirt, Hood and Wing lists from upgrades.xml
  --wheel                          its own wheel (nfsu2forza.py --wheel's files) in
                                   tires\\art\\<car>\\, its stock WheelStyle naming it

Writes only into the mods folder, never the saves.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import forzacab

B = '\\'


def main(disc, mods, car, out, upgrades=False, wheel=None):
    cab = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % car)
    files, root = addcar.cab_files(open(cab, 'rb').read())
    pre = B.join(('cars', car.lower())) + B
    new = {'car.carbin': os.path.join(out, 'car.carbin')}
    for n in ('livery0.xpr', 'livery0hi.xpr', 'livery0nc.xpr'):
        new[B.join(('liveries', 'standard', n))] = os.path.join(out, 'liveries', 'standard', n)
    for rel, src in new.items():
        k = next((k for k in files if k.lower() == (pre + rel).lower()), None)
        if k is None: raise SystemExit('%s: no %s' % (cab, pre + rel))
        files[k] = open(src, 'rb').read()
    open(cab, 'wb').write(forzacab.pack(files, root))
    print('car_%s.cab: car.carbin and the livery atlases from %s' % (car, out))
    lb = os.path.join(out, 'liveries.bin')
    if os.path.exists(lb):
        open(os.path.join(mods, 'media', 'cars', '%s.liveries.bin' % car), 'wb').write(open(lb, 'rb').read())
        print('media/cars/%s.liveries.bin from %s' % (car, lb))
    if wheel:  # its own wheel (nfsu2forza.py --wheel): tires\art\<car>\ in Mega.ca2 (tire.carbin) and MegaXPR.ca2
        # (wheel.xpr; wheel_vol.xpr, the spinning blur, the old wheel's), tooldata's stock WheelStyle naming it
        tire, wx = wheel.split(',')
        mega, xpr, cars = addcar.Archive(disc, mods, 'Mega.ca2'), addcar.Archive(disc, mods, 'MegaXPR.ca2'), addcar.Archive(disc, mods, 'Cars.ca2')
        tk = pre + 'tooldata.xml'
        tool = cars.files[tk].decode('latin-1')
        old = re.search(r'<WheelStyle>\s*<P0 [^>]*File="([^"]*)"', tool).group(1)
        art, mine = B.join(('tires', 'art', old.lower())) + B, B.join(('tires', 'art', car.lower())) + B
        mega.files[mine + 'tire.carbin'] = open(tire, 'rb').read()
        xpr.files[mine + 'wheel.xpr'] = open(wx, 'rb').read()
        vol = next((v for k, v in xpr.files.items() if k.lower() == (art + 'wheel_vol.xpr').lower()), None)
        if vol: xpr.files[mine + 'wheel_vol.xpr'] = vol
        tool = re.sub(r'(<WheelStyle>\s*<P0 [^>]*File=")[^"]*"', lambda g: g.group(1) + car + '"', tool, count=1)
        cars.files[tk] = tool.encode('latin-1')
        for a in (mega, xpr, cars): a.check()
        for a in (mega, xpr, cars): a.write()
        print('wheel: tires\\art\\%s (was %s\'s)' % (car.lower(), old))
    if upgrades:
        cars = addcar.Archive(disc, mods, 'Cars.ca2')
        tk = pre + 'tooldata.xml'
        tool = cars.files[tk].decode('latin-1')
        u = open(os.path.join(out, 'upgrades.xml')).read()
        for tag in ('FrontBumper', 'RearBumper', 'SideSkirt', 'Hood', 'Wing'):
            mine = re.search(r'\t*<%s>.*?</%s>\n?' % (tag, tag), u, re.S)
            if mine: tool = re.sub(r'\t*<%s>.*?</%s>\n?' % (tag, tag), lambda _: mine.group(0), tool, count=1, flags=re.S)
        cars.files[tk] = tool.encode('latin-1')
        cars.check()
        cars.write()
        print('tooldata: the shop\'s body parts from upgrades.xml')


if __name__ == '__main__':
    args, wheel, it = [], None, iter(sys.argv[1:])
    for a in it:
        if a == '--wheel': wheel = next(it)
        elif a != '--upgrades': args.append(a)
    if len(args) != 4: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, upgrades='--upgrades' in sys.argv, wheel=wheel)
