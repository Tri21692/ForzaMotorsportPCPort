"""The driver's seat height in the add-on cars, and the Custom Coupe's views (the user's, 16 Nov: "Check drivatar
height for lower to the ground/smaller cars (audit)", "Fix the Custom Coupe camera height (too low)").

The driver is one model for every car, stood on the hip point of the car's model (car.carbin's Driver chunk: 15
floats in metres, the second the hip's height; the hands and the wheel's grip the 5th, 8th and 14th). The audit
(E:/xbrt_scr/driver_audit, 285 cars): from the hip to the roof's skin over the head the disc's closed cars have
0.85 to 1.07 m, 0.905 in the middle. Under 0.85 the helmet is at or through the roof; far over it the driver sits
under the seat. HIP gives each car found outside that its hip's new height; the hands and grip move with it.

The Custom Coupe besides: its converter measured the roof on the part that holds its seats, so the driver went
0.35 m down and with it the in-car view and the mirror's (nontooldata.xml DriverPosition, RearViewPosition: 0.39
under the template's), put back; and its box for the physics and the chase camera (maxdata.xml MaxY, with
nontooldata's PhysOBBOffsetMax taking the template's wing back off: 0.42, a wing the Coupe does not have above its
roof) ended 0.5 m under its roof: MaxY the roof's 1.30, the offset none.

  python tools/driverfix.py <disc> <mods folder>

A car's cab not in the mods folder is left alone. Run again, it changes nothing more. Never the saves.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin
import forzacab

B = chr(92)
# the car: its hip's height (m). The first four sat with the helmet at the roof; the Coupe's driver under its seat.
# (The Gallardo and the Lotus Evora measured as sunk too, 1.1 m under their roofs, and raised to 0.22 and 0.13: the
# Gallardo's helmet came out through its roof in the test, its roof's measure taken over the engine cover's scoops.
# Left as they were. The Coupe's 0.25 keeps a metre and more under its roof for the same doubt.)
HIP = {'NCLamborghiniEgoista': 0.06, 'NCLamborghiniDiabloSV': 0.03, 'NCPaganiHuayraBC': 0.15, 'NCAlfaRomeo4C': 0.07,
       'BurnoutCustomCoupe': 0.25}
VIEWS = {'BurnoutCustomCoupe': dict(DriverPosition=1.11, RearViewPosition=1.33, PhysOBBOffsetMax=0.0, MaxY=1.30)}


def set_hip(blob, hip):
    car = carbin.read(blob)
    h = car['head'][1]
    _, _, name, p = carbin._chunk_head(h, 0)
    assert name == 'Driver' and len(h) - p == 60, (name, len(h) - p)
    f = list(struct.unpack_from('<15f', h, p))
    d = hip - f[1]
    if abs(d) < 0.005: return None, f[1]
    f[1] = hip
    for i in (4, 7, 13): f[i] += d
    car['head'][1] = h[:p] + struct.pack('<15f', *f)
    return carbin.write(car), hip - d


def set_y(xml, tag, y):
    def sub(m):
        return re.sub(r'\by\s*=\s*"[^"]*"', 'y="%.2f"' % y, m.group(0), count=1)
    return re.subn(r'<%s\b[^>]*>' % tag, sub, xml, count=1)


def main(disc, mods):
    for name, hip in HIP.items():
        cab = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % name)
        if not os.path.exists(cab):
            print('%s: no cab of its own in the mods folder, left' % name)
            continue
        files, root = addcar.cab_files(open(cab, 'rb').read())
        key = next(k for k in files if k.lower().endswith('car.carbin'))
        new, was = set_hip(files[key], hip)
        if new is None:
            print('%s: hip at %.3f m already' % (name, was))
            continue
        files[key] = new
        open(cab, 'wb').write(forzacab.pack(files, root))
        print('%s: hip %.3f -> %.3f m' % (name, was, hip))
    cars = addcar.Archive(disc, mods, 'Cars.ca2')
    low = {k.lower(): k for k in cars.files}
    changed = 0
    for name, v in VIEWS.items():
        k = low.get('cars' + B + name.lower() + B + 'nontooldata.xml')
        if k:
            x = cars.files[k].decode('latin-1')
            for tag in ('DriverPosition', 'RearViewPosition', 'PhysOBBOffsetMax'):
                x2, n = set_y(x, tag, v[tag])
                if n and x2 != x: x, changed = x2, changed + 1
            cars.files[k] = x.encode('latin-1')
        k = low.get('cars' + B + name.lower() + B + 'physics' + B + 'maxdata.xml')
        if k:
            x = cars.files[k].decode('latin-1')
            x2 = re.sub(r'(<BoundingBox [^>]*\bMaxY=")[^"]*(")', lambda m: m.group(1) + '%.6f' % v['MaxY'] + m.group(2), x, count=1)
            if x2 != x: changed += 1
            cars.files[k] = x2.encode('latin-1')
        print('%s: views and box set (%d fields changed so far)' % (name, changed))
    if changed:
        cars.check()
        cars.write()


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    main(sys.argv[1], sys.argv[2])
