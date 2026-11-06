"""Each add-on car's store figures as the game would have them (6 Nov, the user: "fix the stats issues for every car
so it's on the correct power level when buying from the store"). gamecars.dat only (Mega.ca2), nothing in the
physics, so the class the game works out for a car in the shop stays as it was:
  100 the listed class and 120 the performance figure, from classcalc (forza.exe's own formula), but the race
      classes (GT, GTS, P1) stay: they are set, not worked out;
  the new cars (newcars.py) also: 20 torque and 36 weight as given to addcar (they were the template's), 44 power to
      weight, 56 the quarter mile and the Speed and Accel bars (124, 128) from their real 0-60, 0-100 mph and top
      speed (fits over the disc's cars); Brake and Corner stay (the template's brakes and tyres, which they drive on).
  python classfix.py [--dry]"""
import sys, os, re, struct, json, math, importlib.util, subprocess
sys.path.insert(0, r'E:\xbrt_scr\newcars')
from perfmodel import *

calc = json.load(open(r'E:\xbrt_scr\newcars\classcalc_before.json'))
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
NEW = {nc.NAME[k]: v for k, v in nc.CARS.items()}
mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
gk = B.join(('forzadb', 'cardb', 'gamecars.dat'))
games = addcar.table_rows(mega.files[gk], 176)
clamp = lambda v, lo, hi: max(lo, min(hi, v))
for name, r in sorted(calc.items(), key=lambda kv: kv[1]['ordinal']):
    g = bytearray(addcar.row_of(games, r['ordinal']))
    was = struct.unpack_from('<I', g, 100)[0]
    notes = []
    if was <= 20:  # (GT, GTS, P1: a race class, kept)
        struct.pack_into('<I', g, 100, r['subclass'])
        struct.pack_into('<f', g, 120, r['perf'])
        notes.append('class %s -> %s' % (SUBS[was - 1], r['name_class']))
    if name in NEW:
        v = NEW[name]
        hp, tq, kg, (t60, t100, vmax) = v[6], v[7], v[8], v[12]
        struct.pack_into('<f', g, 20, tq / 73.69197082519531)
        struct.pack_into('<f', g, 36, kg / 100)
        struct.pack_into('<f', g, 44, hp * 0.745699872 / kg * 1000)
        qm = 2.28218 * math.log(t60) + 2.77313 * math.log(t100) + 2.93049
        struct.pack_into('<f', g, 56, qm)
        sp = clamp(0.09907 * vmax / 3.6 - 1.16736, 4.0, 9.9)
        ac = clamp(131.98697 / qm - 3.87, 4.0, 9.9)
        struct.pack_into('<2f', g, 124, sp, ac)
        notes.append('%d lb-ft %d lbs, 1/4 mile %.1f s, bars speed %.1f accel %.1f' % (tq, round(kg * 2.20462), qm, sp, ac))
    if notes: print('%3d %-28s %s' % (r['ordinal'], name, '; '.join(notes)))
    games = addcar.table_rows(addcar.put_row(games, bytes(g)), 176)
if '--dry' in sys.argv: raise SystemExit('dry run: nothing written')
mega.files[gk] = b''.join(games) if isinstance(games, list) else games
mega.check(); mega.write()
print('written')
