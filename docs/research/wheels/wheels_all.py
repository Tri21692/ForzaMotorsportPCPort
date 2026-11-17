"""Each add-on car's own wheel (the user's, 15 Nov: "The Lambo has Ferrari wheels. Be sure to give each DLC car its
assigned wheel"): the 5 Nov batch's cars wore their templates' wheels (a Lamborghini on the Enzo's body, the Enzo's
rims). Each source has its stock rim (KIT00_FRONT_TIRE's RIM groups): nfsu2forza.convert_wheel puts it on the
template wheel's tyre, as the M3 GTR's, Gallardo's and Cobalt's were.

  python wheels_all.py convert [keys]        out/<key>/tire.carbin, wheel.xpr (from the wheel the car has now)
  python wheels_all.py install <mods> [keys] tires\\art\\<car>\\ in Mega.ca2 / MegaXPR.ca2, tooldata's WheelStyle
"""
import importlib.util, os, re, sys, traceback
T = r'E:\Forza Motorsport Remastered\tools'
sys.path.insert(0, T); sys.path.insert(0, r'E:\xbrt_scr\newcars')
argv = sys.argv[:]
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
sys.argv = ['x']; spec.loader.exec_module(nc)
import addcar, nfsu2forza
B = chr(92)
W = r'E:\xbrt_scr\wheels\out'
MODS0 = r'E:\Forza Motorsport Remastered\run\mods_next'


def style_of(cars, car):
    tk = next(k for k in cars.files if k.lower() == B.join(('cars', car.lower(), 'tooldata.xml')))
    return tk, re.search(r'<WheelStyle>\s*<P0 [^>]*File="([^"]*)"', bytes(cars.files[tk]).decode('latin-1')).group(1)


def get(arc, path):
    return bytes(next(v for k, v in arc.files.items() if k.lower() == path.lower()))


def convert(keys, mods=MODS0):
    mega, xpr, cars = (addcar.Archive(nc.DISC, mods, n) for n in ('Mega.ca2', 'MegaXPR.ca2', 'Cars.ca2'))
    for k in keys:
        car = nc.NAME[k]
        od = os.path.join(W, k); os.makedirs(od, exist_ok=True)
        try:
            _, st = style_of(cars, car)
            if st.lower() == car.lower():   # (already its own: start again from what it was made from)
                st = open(os.path.join(od, 'from.txt')).read().strip()
            open(os.path.join(od, 'from.txt'), 'w').write(st)
            art = B.join(('tires', 'art', st.lower())) + B
            open(os.path.join(od, 't_tire.carbin'), 'wb').write(get(mega, art + 'tire.carbin'))
            open(os.path.join(od, 't_wheel.xpr'), 'wb').write(get(xpr, art + 'wheel.xpr'))
            sd = nc.stage(nc.CARS[k][0], k)
            print('%-10s %-28s on %s:' % (k, car, st), end=' ', flush=True)
            # (16 Nov, the wheel audit: nfsu2forza's WHEEL_CROP / WHEEL_LIP, for the cars they suit)
            fix = {'impala': ('crop', 'lip'), 'maloo': ('crop',), 'civicfn2': ('crop',)}.get(k, ())
            nfsu2forza.WHEEL_CROP, nfsu2forza.WHEEL_LIP = 'crop' in fix, 'lip' in fix
            nfsu2forza.convert_wheel(os.path.join(od, 't_tire.carbin'), os.path.join(od, 't_wheel.xpr'), sd,
                                     os.path.join(od, 'tire.carbin'), os.path.join(od, 'wheel.xpr'))
        except (SystemExit, Exception) as e:
            print('%-10s FAILED: %r' % (k, e)); pass
            for f in ('tire.carbin', 'wheel.xpr'):
                if os.path.exists(os.path.join(od, f)): os.remove(os.path.join(od, f))


def install(mods, keys):
    mega, xpr, cars = (addcar.Archive(nc.DISC, mods, n) for n in ('Mega.ca2', 'MegaXPR.ca2', 'Cars.ca2'))
    n = 0
    for k in keys:
        car = nc.NAME[k]; od = os.path.join(W, k)
        if not os.path.exists(os.path.join(od, 'tire.carbin')): print(k, 'no wheel made: left'); continue
        tk, st = style_of(cars, car)
        old = open(os.path.join(od, 'from.txt')).read().strip()
        art, mine = B.join(('tires', 'art', old.lower())) + B, B.join(('tires', 'art', car.lower())) + B
        mega.files[mine + 'tire.carbin'] = open(os.path.join(od, 'tire.carbin'), 'rb').read()
        xpr.files[mine + 'wheel.xpr'] = open(os.path.join(od, 'wheel.xpr'), 'rb').read()
        xpr.files[mine + 'wheel_vol.xpr'] = get(xpr, art + 'wheel_vol.xpr')
        tool = bytes(cars.files[tk]).decode('latin-1')
        cars.files[tk] = re.sub(r'(<WheelStyle>\s*<P0 [^>]*File=")[^"]*"', lambda g: g.group(1) + car + '"', tool, count=1).encode('latin-1')
        n += 1
    for a in (mega, xpr, cars): a.check()
    for a in (mega, xpr, cars): a.write()
    print('%d cars on their own wheels in %s' % (n, mods))


if __name__ == '__main__':
    if argv[1] == 'convert': convert(argv[2:] or list(nc.CARS))
    elif argv[1] == 'install': install(argv[2], argv[3:] or list(nc.CARS))
