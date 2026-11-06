"""Every add-on car's class as the game works it out (perfmodel: forza.exe f_0016CFF0 and the bounds at 0x52ca00):
from its installed physics (weight l0 Mass, the stock tyres' wider width), its engine power and torque (the menus'
power figure, which addcar scaled the engine to; the torque as given to addcar, else the dealer's figure), and
model.dat's per-car offset at 100. Prints the listed class beside it.

  python classcalc.py [--json out.json]"""
import sys, os, re, struct, json, importlib.util
sys.path.insert(0, r'E:\xbrt_scr\newcars')
from perfmodel import *

mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
cars = addcar.Archive(DISC, MODS, 'Cars.ca2')
xml = mega.files['cars' + B + 'carlist.xml'].decode('latin-1')
dxml = mega.disc['cars' + B + 'carlist.xml'].decode('latin-1')
disc_names = set(re.findall(r'<car name="([^"]*)"', dxml))
games = addcar.table_rows(mega.files[B.join(('forzadb', 'cardb', 'gamecars.dat'))], 176)
model = addcar.table_rows(mega.files[B.join(('forzadb', 'cardb', 'model.dat'))], 104)
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
TORQUE = {nc.NAME[k]: v[7] for k, v in nc.CARS.items()}  # lb-ft as given to addcar
MASS = {nc.NAME[k]: v[8] for k, v in nc.CARS.items()}
lk = {k.lower(): k for k in cars.files}


def physics(name):
    def f(rel):
        k = lk.get(('cars' + B + name + B + rel).lower())
        return bytes(cars.files[k]).decode('latin-1') if k else None
    w = f('physics' + B + 'weight' + B + 'l0.xml')
    mass = float(re.search(r' Mass="([0-9.]+)"', w).group(1)) if w else None
    td = f('tooldata.xml')
    lvl = int(re.search(r'<Tire StockLevel="(\d+)"', td).group(1))
    blk = re.search(r'<Tire StockLevel.*?<L%d[^>]*>(.*?)</L%d>' % (lvl, lvl), td, re.S).group(1)
    wf = float(re.search(r'<Fronts [^>]*TireWidth="([^"]+)"', blk).group(1)); wr = float(re.search(r'<Rears [^>]*TireWidth="([^"]+)"', blk).group(1))
    return mass, max(wf, wr) / 1000


out = {}
for name, o in re.findall(r'<car name="([^"]*)"[^>]*?Ordinal="(\d+)"', xml):
    if name in disc_names: continue
    o = int(o)
    try: g, mr = addcar.row_of(games, o), addcar.row_of(model, o)
    except Exception: continue
    f = lambda i: struct.unpack_from('<f', g, i)[0]
    hp = f(12) * 0.1341022104024887
    tq = TORQUE.get(name, f(20) * 73.69197082519531)
    mass, rw = physics(name)
    kg = mass if mass else f(36) * 100
    adj = struct.unpack_from('<f', mr, 100)[0]
    p = round(base(hp, tq, kg * 2.2046226501464844) + 0.125 * (rw - 0.15) / 0.29, 3) + adj
    s = subclass(p)
    listed = struct.unpack_from('<I', g, 100)[0]
    out[name] = dict(ordinal=o, hp=round(hp), ftlb=round(tq), kg=round(kg), rear_tyre=rw, adj=round(adj, 4), perf=round(p, 4),
                     subclass=s, name_class=SUBS[s - 1], listed=listed, listed_class=SUBS[listed - 1] if listed <= 20 else ('GT', 'GTS', 'P1')[listed - 21])
    r = out[name]
    print('%3d %-28s %4d hp %4d lb-ft %5d kg rear %.3f adj %+.3f  perf %.3f -> %-3s  (listed %s)%s' % (
        o, name, r['hp'], r['ftlb'], r['kg'], rw, adj, p, r['name_class'], r['listed_class'], '' if r['name_class'] == r['listed_class'] else '  *'))
if '--json' in sys.argv: json.dump(out, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
