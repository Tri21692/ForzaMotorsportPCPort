"""Put a converted body (nfsu2forza.py's output) into a car already added
with addcar.py, keeping the rest of it (engine, sound, physics, paints).

  python tools/updatecar.py <disc folder> <mods folder> <car> <converter output folder> [--upgrades]
  e.g.  <disc>  run/mods_lambo  ChevyCobaltSS  scr/cobalt_out  --upgrades

From the output folder (car.carbin, liveries/standard/livery0*.xpr,
liveries.bin, upgrades.xml):

  car_<car>.cab                    cars\\<car>\\car.carbin and the three livery atlases
  media/cars/<car>.liveries.bin    the paint shop's copy, if there is one
  Cars.ca2                         --upgrades: tooldata.xml's FrontBumper, RearBumper,
                                   SideSkirt, Hood and Wing lists from upgrades.xml

Writes only into the mods folder, never the saves.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import forzacab

B = '\\'


def main(disc, mods, car, out, upgrades=False):
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
    args = [a for a in sys.argv[1:] if a != '--upgrades']
    if len(args) != 4: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, upgrades='--upgrades' in sys.argv)
