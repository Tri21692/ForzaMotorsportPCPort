"""The Eclipse GT add-on made the "Eclipse Custom" (the user's, 7 Nov: "rename the Eclipse to the Eclipse Custom and
make it A-Class ... disable the store upgrades on it besides tire and windshields"). Run after
  tunecar.py <disc> <mods> NCMitsubishiEclipseGT --own-engine NCMitsubishiEclipseGT --power 390 --mass 1450 ...
and topspeed.py (newcars.py's CARS has its new figures). This does the rest, in the mods folder only:
  the name and short name (carlist.xml, IDS_Model_<o>_Name/_ShortName in every language, its engine's shop name);
  the store's figures from newcars.CARS (gamecars.dat 20 torque, 36 weight, 44 power to weight, 56 the quarter mile,
      124/128 the Speed and Accel bars, as classfix.py) and its class (100) and performance figure (120) as
      forza.exe works them out (perfmodel, classcalc.py), so the list and the shop agree;
  every upgrade the shop sells marked not for sale (Price -1, as the game marks its own) but the tyres and the
      window tint: the car's and its engine's levels L1-L3 and the body parts past P0 (Body Kit 1, No Wing, the cage).
      The lists keep their entries, so a car saved with one fitted still loads.
python eclipsecustom.py [--dry]"""
import sys, os, re, struct, math, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\Forza Motorsport Remastered\docs\research\newcars')
import addcar
from perfmodel import base, subclass, NAMES, DISC, MODS, B

CAR, NAME, SHORT = 'NCMitsubishiEclipseGT', 'Eclipse Custom', 'Eclipse Custom'
OPEN = ('Tire', 'WindowTint', 'WheelStyle', 'Assists')  # (the shop's own lists left as they are)
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
v = nc.CARS['eclipse']
hp, tq, kg, (t60, t100, vmax) = v[6], v[7], v[8], v[12]


def lock(xml):
    """Every upgrade list but OPEN's: levels L1-L3 and parts P1.. Price -1."""
    n = 0
    def item(g):
        nonlocal n
        n += 1
        return re.sub(r'\bPrice="[^"]*"', 'Price="-1"', g.group(0), count=1)
    # (each upgrade list: a tag whose first child is its L0 or P0)
    for tag in dict.fromkeys(re.findall(r'<(\w+)\b[^>/]*>\s*<(?:L0|P0)\b', xml)):
        if tag in OPEN: continue
        m = re.search(r'<%s\b[^>/]*>.*?</%s>' % (tag, tag), xml, re.S)
        xml = xml[:m.start()] + re.sub(r'<(?:L[1-9]|P[1-9]\d*)\b[^>]*?Price="[^"]*"', item, m.group(0)) + xml[m.end():]
    return xml, n


mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
cars = addcar.Archive(DISC, MODS, 'Cars.ca2')
lk = {k.lower(): k for k in cars.files}
# the name
key = 'cars' + B + 'carlist.xml'
xml = mega.files[key].decode('latin-1')
o = addcar.ordinal_of(xml, CAR)
blk = addcar.car_block(xml, CAR)
head = re.sub(r'displayName="[^"]*"', 'displayName="%s"' % NAME, blk.group(0), count=1)
head = re.sub(r'shortName="[^"]*"', 'shortName="%s"' % SHORT, head, count=1)
xml = xml[:blk.start()] + head + xml[blk.end():]
mega.files[key] = xml.encode('latin-1')
# the upgrades
for k in ('cars' + B + CAR + B + 'tooldata.xml', 'engines' + B + CAR + B + 'tooldata.xml'):
    k = lk[k.lower()]
    t = bytes(cars.files[k]).decode('latin-1')
    t2, n = lock(t)
    if k.lower().startswith('cars'):
        t2 = re.sub(r'(<E0 [^>]*Name=")[^"]*"', lambda g: g.group(1) + NAME + '"', t2, count=1)
    cars.files[k] = t2.encode('latin-1')
    print('%s: %d upgrades not for sale' % (k, n))
# the store's figures and the class
td = bytes(cars.files[lk[('cars' + B + CAR + B + 'tooldata.xml').lower()]]).decode('latin-1')
mass = float(re.search(r' Mass="([0-9.]+)"', bytes(cars.files[lk[('cars' + B + CAR + B + 'physics' + B + 'weight' + B + 'l0.xml').lower()]]).decode('latin-1')).group(1))
blk0 = re.search(r'<Tire StockLevel="0".*?<L0[^>]*>(.*?)</L0>', td, re.S).group(1)
w = max(float(x) for x in re.findall(r'TireWidth="([^"]+)"', blk0)) / 1000
gk = B.join(('forzadb', 'cardb', 'gamecars.dat')); mk = B.join(('forzadb', 'cardb', 'model.dat'))
games = addcar.table_rows(mega.files[gk], 176); model = addcar.table_rows(mega.files[mk], 104)
g = bytearray(addcar.row_of(games, o)); mr = addcar.row_of(model, o)
adj = struct.unpack_from('<f', mr, 100)[0]
power = struct.unpack_from('<f', g, 12)[0] * 0.1341022104024887
p = round(base(power, tq, mass * 2.2046226501464844) + 0.125 * (w - 0.15) / 0.29, 3) + adj
s = subclass(p)
clamp = lambda x, lo, hi: max(lo, min(hi, x))
struct.pack_into('<f', g, 20, tq / 73.69197082519531)
struct.pack_into('<f', g, 36, mass / 100)
struct.pack_into('<f', g, 44, power * 0.745699872 / mass * 1000)
qm = 2.28218 * math.log(t60) + 2.77313 * math.log(t100) + 2.93049
struct.pack_into('<f', g, 56, qm)
sp, ac = clamp(0.09907 * vmax / 3.6 - 1.16736, 4.0, 9.9), clamp(131.98697 / qm - 3.87, 4.0, 9.9)
struct.pack_into('<2f', g, 124, sp, ac)
struct.pack_into('<I', g, 100, s)
struct.pack_into('<f', g, 120, p)
mega.files[gk] = addcar.put_row(games, bytes(g))
print('%s (%d) "%s": %.0f hp %d lb-ft %.0f kg tyre %.3f adj %+.3f -> figure %.3f, class %s; 1/4 mile %.1f s, bars speed %.1f accel %.1f'
      % (CAR, o, NAME, power, tq, mass, w, adj, p, NAMES[s], qm, sp, ac))
if '--dry' in sys.argv: raise SystemExit('dry run: nothing written')
mega.check(); cars.check(); mega.write(); cars.write()
loc = os.path.join(MODS, 'media', 'Loc')
want = {'IDS_Model_%d_Name' % o: NAME, 'IDS_Model_%d_ShortName' % o: SHORT}
for lang in sorted(os.listdir(loc)):
    mp = os.path.join(loc, lang, 'CarDataStrings.str')
    if not os.path.exists(mp): continue
    d = open(mp, 'rb').read()
    ids = addcar.string_ids(d)
    ch = {ids[n]: t for n, t in want.items() if n in ids}
    open(mp, 'wb').write(addcar.replace_strings(d, ch))
    print(lang, '%d names' % len(ch))
