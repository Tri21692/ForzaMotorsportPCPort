"""A consistency audit of every car the mods folder's car list holds (7 Nov, the user: "audit mods and confirm they
work"): each car's
  - cab (media\\cabs\\car_<name>.cab in the mods folder or on the disc), and its car.carbin inside;
  - physics and shop files in Cars.ca2 (cars\\<name>\\tooldata.xml, physics\\maxdata.xml, weight\\l0.xml);
  - engine (tooldata's E0 File: engines\\<engine>\\physics\\base.xml);
  - wheel model (tooldata's WheelStyle File: tires\\art\\<style>\\tire.carbin in Mega.ca2);
  - rows in model.dat and gamecars.dat, its name string, and (an add-on) its unlock in addon_cars.txt.
Prints what it finds, and "no problems" when nothing.   python tools/carsaudit.py <disc> <mods folder>"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import forzacab

B = '\\'


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    cars = addcar.Archive(disc, mods, 'Cars.ca2')
    mk = {k.lower(): k for k in mega.files}
    ck = {k.lower(): k for k in cars.files}
    xml = bytes(mega.files[mk['cars\\carlist.xml']]).decode('latin-1')
    dxml = bytes(mega.disc[next(k for k in mega.disc if k.lower() == 'cars\\carlist.xml')]).decode('latin-1')
    disc_names = set(re.findall(r'<car name="([^"]*)"', dxml))
    model = addcar.table_rows(mega.files[mk['forzadb\\cardb\\model.dat']], 104)
    games = addcar.table_rows(mega.files[mk['forzadb\\cardb\\gamecars.dat']], 176)
    addon = set()
    ap = os.path.join(mods, 'addon_cars.txt')
    if os.path.exists(ap):
        for line in open(ap, encoding='latin-1'):
            for w in line.split():
                if w.isdigit(): addon.add(int(w))
    problems, n = [], 0
    for name, o in re.findall(r'<car name="([^"]*)"[^>]*?Ordinal="(\d+)"', xml):
        o, n = int(o), n + 1
        say = lambda m: problems.append('%s (%d): %s' % (name, o, m))
        cab = None
        for base in (os.path.join(mods, 'media', 'cabs'), addcar.disc_file(disc, 'media', 'cabs')):
            if base and os.path.exists(os.path.join(base, 'car_%s.cab' % name)): cab = os.path.join(base, 'car_%s.cab' % name); break
        if not cab:
            for base in (os.path.join(mods, 'media', 'cabs'), addcar.disc_file(disc, 'media', 'cabs')):  # (the disc's names differ in case)
                if base and os.path.isdir(base):
                    hit = [f for f in os.listdir(base) if f.lower() == ('car_%s.cab' % name).lower()]
                    if hit: cab = os.path.join(base, hit[0]); break
        if not cab: say('no cab')
        else:
            try:
                dd, ver, es = forzacab.read(cab)
                if not any(e['name'].lower().replace('/', B).endswith(B + 'car.carbin') for e in es): say('cab has no car.carbin')
            except Exception as ex:
                say('cab unreadable: %s' % ex)
        td = ck.get(('cars' + B + name + B + 'tooldata.xml').lower())
        if not td: say('no tooldata.xml'); continue
        t = bytes(cars.files[td]).decode('latin-1')
        for rel in ('physics\\maxdata.xml', 'physics\\weight\\l0.xml'):
            if ('cars' + B + name + B + rel).lower() not in ck: say('no %s' % rel)
        e0 = re.search(r'<E0 [^>]*File="([^"]*)"', t)
        if not e0: say('no engine in tooldata')
        elif ('engines' + B + e0.group(1) + B + 'physics' + B + 'base.xml').lower() not in ck: say('engine %s has no physics' % e0.group(1))
        ws = re.search(r'<WheelStyle>.*?File="([^"]+)"', t, re.S)
        if not ws: say('no wheel style')
        elif ('tires' + B + 'art' + B + ws.group(1) + B + 'tire.carbin').lower() not in mk: say('wheel style %s has no tire.carbin' % ws.group(1))
        try:
            mr = addcar.row_of(model, o); addcar.row_of(games, o)
        except Exception:
            say('no model.dat / gamecars.dat row'); continue
        if name not in disc_names and addon and o not in addon: say('an add-on not in addon_cars.txt (Free Run and Arcade lock it)')
    print('%d cars, %d add-ons listed in addon_cars.txt' % (n, len(addon)))
    for p in problems: print('PROBLEM', p)
    if not problems: print('no problems')


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
