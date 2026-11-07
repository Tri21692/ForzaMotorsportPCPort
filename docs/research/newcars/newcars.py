"""The 5 Nov batch of add-on cars (the user's four folders): each Most Wanted car converted on a Forza template
(tools/nfsu2forza.py), packed into the template's cab, added as a car of its own (tools/addcar.py, the next free
ordinal), its car-select tile rendered (carlit ICON=1) and put in the disc's form with the DLC badge, and previews
drawn for checking.

  python newcars.py convert [key ...]   the bodies (no install)
  python newcars.py install [key ...]   add them to run/mods_track (the game closed)
  python newcars.py preview [key ...]   lit previews of the converted bodies
"""
import json, os, re, shutil, subprocess, sys

G = r'E:\Forza Motorsport Remastered'
T = os.path.join(G, 'tools')
sys.path.insert(0, T)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = os.path.join(G, 'run', 'mods_track')
W = r'E:\xbrt_scr\newcars'
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
PACK = r'C:\Users\maste\Downloads\nfs.com.ru_addon_car_pack_mw\Addon car Pack\main files\CARS'
DL = r'C:\Users\maste\Downloads'

# key: (source folder, display name, short, maker, year, price, hp, lb-ft, kg, template, engine donor,
#       [physics-like ...], (0-60 s, 0-100 mph s, top km/h), credit)
CARS = {
 'chiron':   (PACK + r'\CHIRON', 'Chiron', 'Chiron', 'Bugatti', 2016, 3000000, 1479, 1180, 1995, 'FerrariEnzo', 'FerrariEnzo', ['AudiRS6:drivetraindiff'], (2.4, 4.9, 420)),
 'lfa':      (PACK + r'\LFA', 'LF-A Concept', 'LF-A', 'Lexus', 2007, 375000, 552, 354, 1480, 'AMDB9', 'PorscheCarreraGT', [], (3.7, 7.9, 325)),
 'm2':       (PACK + r'\BMWM2', 'M2 Coupe', 'M2', 'BMW', 2016, 60000, 365, 343, 1495, 'MercedesC32AMG', 'ToyotaSupra', [], (4.2, 9.5, 250)),
 '190e':     (PACK + r'\190E', '190E 2.5-16 Evolution II', '190E Evo II', 'Mercedes', 1990, 60000, 235, 181, 1340, 'MercedesC32AMG', 'HondaS2000', [], (7.1, 18.0, 250)),
 'gt2rs':    (PACK + r'\991GT2RS', '911 GT2 RS', '911 GT2 RS', 'Porsche', 2018, 300000, 690, 553, 1470, 'Porsche911GT2', 'Porsche911GT2', [], (2.7, 6.0, 340)),
 'xk':       (PACK + r'\JAGUARXK', 'XK', 'XK', 'Jaguar', 2007, 85000, 300, 310, 1595, 'AMDB9', 'MercedesCLK55', [], (5.9, 13.5, 250)),
 'huayra':   (PACK + r'\HUAYRABC', 'Huayra BC', 'Huayra BC', 'Pagani', 2016, 2600000, 789, 811, 1218, 'PorscheCarreraGT', 'PaganiZonda', [], (2.8, 6.2, 370)),
 'impala':   (PACK + r'\IMPALASS', 'Impala SS', 'Impala SS', 'Chevrolet', 1964, 55000, 300, 360, 1660, 'PontiacGTO68', 'PontiacGTO68', [], (7.0, 17.0, 200)),
 'rs5':      (PACK + r'\RS5', 'RS 5 Coupe', 'RS 5', 'Audi', 2018, 75000, 444, 443, 1655, 'AudiRS6', 'AudiRS6', [], (3.9, 9.0, 280)),
 'gtx1':     (PACK + r'\FORDGTX1', 'GTX1', 'GTX1', 'Ford', 2006, 400000, 550, 500, 1500, 'FordGT', 'FordGT', [], (3.6, 7.6, 330)),
 'jesko':    (PACK + r'\JESKO', 'Jesko', 'Jesko', 'Koenigsegg', 2020, 3000000, 1603, 1106, 1420, 'Koenigsegg', 'Koenigsegg', [], (2.5, 5.0, 440)),
 'terzo':    (PACK + r'\TERZO', 'Terzo Millennio', 'Terzo', 'Lamborghini', 2017, 2000000, 900, 700, 1700, 'FerrariEnzo', 'FerrariEnzo', ['AudiRS6:drivetraindiff'], (2.5, 5.5, 350)),
 'maloo':    (PACK + r'\MALOO', 'HSV Maloo R8', 'Maloo', 'Holden', 2006, 50000, 402, 405, 1800, 'gto', 'gto', [], (5.0, 11.5, 250)),
 'm8gte':    (PACK + r'\BMWM8GTE', 'M8 GTE', 'M8 GTE', 'BMW', 2018, 1000000, 500, 380, 1220, 'BMWM3GTR42', 'BMWM3GTR42', [], (3.2, 7.0, 300)),
 'sesto':    (PACK + r'\LAMBOSESTO', 'Sesto Elemento', 'Sesto', 'Lamborghini', 2010, 2500000, 562, 398, 999, 'Ferrari360', 'LamborghiniGallardo', ['AudiRS6:drivetraindiff'], (2.5, 5.8, 330)),
 'f8':       (PACK + r'\F8', 'F8 Tributo', 'F8 Tributo', 'Ferrari', 2019, 300000, 710, 568, 1435, 'Ferrari360', 'Ferrari360', [], (2.9, 6.4, 340)),
 'svj':      (PACK + r'\SVJ', 'Aventador SVJ', 'Aventador SVJ', 'Lamborghini', 2018, 520000, 759, 531, 1525, 'FerrariEnzo', 'FerrariEnzo', ['AudiRS6:drivetraindiff'], (2.8, 6.0, 350)),
 'eclipse':  (PACK + r'\ECLIPSEELITE', 'Eclipse GT', 'Eclipse GT', 'Mitsubishi', 2006, 30000, 263, 260, 1590, 'MitsuEclipseGTS', 'MitsuEclipseGTS', [], (6.0, 15.0, 240)),
 'civicfn2': (PACK + r'\CIVICFN2', 'Civic Type R (FN2)', 'Civic Type R', 'Honda', 2007, 32000, 198, 142, 1267, 'Honda_CivicR', 'Honda_CivicR', [], (6.6, 17.0, 225)),
 'charger':  (PACK + r'\CHARGER06', 'Charger SRT8', 'Charger SRT8', 'Dodge', 2006, 45000, 425, 420, 1890, 'CadillacCTS', 'DodgeChallenger', [], (5.0, 12.0, 270)),
 'evora':    (PACK + r'\EVORA', 'Evora', 'Evora', 'Lotus', 2009, 75000, 276, 258, 1382, 'LotusEsprit', 'Nissan350Z', [], (4.9, 11.5, 260)),
 '335i':     (PACK + r'\BMW335E92', '335i Coupe', '335i', 'BMW', 2007, 45000, 300, 300, 1600, 'MercedesC32AMG', 'ToyotaSupra', [], (5.4, 12.5, 250)),
 'fordgt17': (PACK + r'\FORDGT17', 'GT (2017)', 'GT 2017', 'Ford', 2017, 450000, 647, 550, 1385, 'FordGT', 'FordGT', [], (2.9, 6.6, 348)),
 'slrmoss':  (PACK + r'\SLRMOSS', 'SLR Stirling Moss', 'SLR Moss', 'Mercedes', 2009, 1500000, 641, 605, 1551, 'MercedesSLR', 'MercedesSLR', [], (3.4, 7.2, 350)),
 'brera':    (PACK + r'\BRERA', 'Brera 3.2 Q4', 'Brera', 'Alfa Romeo', 2006, 40000, 256, 237, 1630, 'Audi_TT', 'Nissan350Z', [], (6.8, 16.0, 240)),
 '4c':       (PACK + r'\4C', '4C Competizione', '4C', 'Alfa Romeo', 2014, 70000, 237, 258, 895, 'LotusElise', 'LotusExige', [], (4.5, 10.5, 258)),
 'zr1':      (PACK + r'\CORVETTEZR1C7', 'Corvette ZR1 (C7)', 'ZR1 C7', 'Chevrolet', 2019, 150000, 755, 715, 1615, 'CorvetteC6', 'CorvetteC6', [], (2.9, 6.4, 343)),
 'egoista':  (PACK + r'\EGOISTA', 'Egoista', 'Egoista', 'Lamborghini', 2013, 2000000, 591, 413, 1500, 'Ferrari360', 'LamborghiniGallardo', ['AudiRS6:drivetraindiff'], (3.2, 7.0, 320)),
 'senna':    (PACK + r'\SENNA', 'Senna', 'Senna', 'McLaren', 2018, 1000000, 789, 590, 1198, 'FerrariEnzo', 'Ferrari360', [], (2.8, 5.8, 340)),
 'huracan':  (DL + r'\1513c6-nfs.com.ru_lamborghini_huracan_performante_mw\ADDONS\CARS_REPLACE\GALLARDO', 'Huracan Performante', 'Huracan Perf.', 'Lamborghini', 2018, 280000, 631, 442, 1382, 'Ferrari360', 'LamborghiniGallardo', ['AudiRS6:drivetraindiff'], (2.9, 6.4, 325)),
 'countach': (DL + r'\ec6dec-_Lamborghini_Countach_LP_5000_QV\Lamborghini Countach LP 5000 QV\Lamborghini Countach LP 5000 QV\ADDONS\CARS_REPLACE\ELISE', 'Countach LP 5000 QV', 'Countach', 'Lamborghini', 1985, 450000, 449, 369, 1490, 'Ferrari512TR', 'Ferrari512TR', [], (4.9, 11.0, 295)),
 'diablo':   (DL + r'\f0dbce-Lamborghini_Diablo_SV\_setup\car', 'Diablo SV', 'Diablo SV', 'Lamborghini', 1997, 300000, 523, 428, 1530, 'FerrariF50', 'FerrariF50', [], (4.0, 9.0, 320)),
}
CLEAN = [172, 175, 223, 231, 244, 245, 246, 247, 248, 249, 251, 252, 253, 254, 255, 256, 257, 258, 260, 261, 262, 264, 266, 267,
         268, 269, 270, 271, 273, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 289, 290]  # free, no stale strings (165, 288: the MX-5's)
ORD = dict(zip(CARS, CLEAN))
NAME = {k: 'NC' + re.sub(r'[^A-Za-z0-9]', '', v[3]) + re.sub(r'[^A-Za-z0-9]', '', v[2]) for k, v in CARS.items()}  # the car's internal name


def run(cmd, log, env=None):
    with open(log, 'a', encoding='utf-8') as f:
        f.write('\n$ %s\n' % ' '.join('"%s"' % c if ' ' in c else c for c in cmd)); f.flush()
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=G, env=env)
    return r.returncode


def template_files(t):
    """The template's car.carbin (from its disc cab) and the disc's paint-shop livery copy."""
    import forzacab
    d = os.path.join(W, 'templates', t)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, 'car.carbin')
    if not os.path.exists(out):  # (the car's whole folder: the converter reads its liveries beside the model)
        dd, ver, es = forzacab.read(os.path.join(DISC, 'media', 'cabs', 'car_%s.cab' % t))
        pre = 'cars\\%s\\' % t.lower()
        for e in es:
            n = e['name'].replace('/', '\\')
            if not n.lower().startswith(pre): continue
            p = os.path.join(d, *n[len(pre):].split('\\'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(forzacab.data(dd, e))
    mx = os.path.join(d, 'physics', 'maxdata.xml')
    if not os.path.exists(mx):  # (the wheelbase for the hubs, when the model has no rotors: Cars.ca2's copy)
        import addcar
        cars = addcar.Archive(DISC, MODS, 'Cars.ca2')
        k = next((k for k in cars.files if k.lower() == 'cars\\%s\\physics\\maxdata.xml' % t.lower()), None)
        if k:
            os.makedirs(os.path.dirname(mx), exist_ok=True)
            open(mx, 'wb').write(bytes(cars.files[k]))
    lv = os.path.join(DISC, 'media', 'cars', '%s.liveries.bin' % t)
    return out, (lv if os.path.exists(lv) else None)


MERGE = {  # bodies spread over other parts (a port's way past a part's size): joined into KIT00_BODY first
 # (where the paint is, by paintsurvey.py: a part holding the car's SKIN1 triangles is body, whatever its name)
 'impala':  ['KIT00_BODY', 'KIT00_LEFT_SIDE_MIRROR', 'KIT00_RIGHT_SIDE_MIRROR', 'KIT00_FRONT_WINDOW', 'KIT00_LEFT_HEADLIGHT'],
 'rs5':     ['KIT00_BODY', 'KIT00_FRONT_WINDOW', 'KIT00_LEFT_HEADLIGHT'],
 'jesko':   ['KIT00_BODY', 'KIT00_LEFT_SIDE_MIRROR', 'KIT00_RIGHT_SIDE_MIRROR', 'KIT00_FRONT_WINDOW', 'KIT00_INTERIOR'],
 'f8':      ['KIT00_BODY', 'KIT00_FRONT_WINDOW', 'KIT00_INTERIOR'],
 '4c':      ['KIT00_BODY', 'KIT00_FRONT_WINDOW'],
 'zr1':     ['KIT00_BODY', 'KIT00_FRONT_WINDOW', 'KIT00_INTERIOR'],
 'egoista': ['KIT00_BODY', 'KIT00_FRONT_WINDOW', 'KIT00_RIGHT_SIDE_MIRROR'],
 'senna':   ['KIT00_BODY', 'KIT00_FRONT_WINDOW', 'KIT00_LEFT_BRAKELIGHT', 'KIT00_RIGHT_BRAKELIGHT', 'KIT00_RIGHT_SIDE_MIRROR', 'KIT00_LEFT_HEADLIGHT', 'KIT00_RIGHT_HEADLIGHT'],
 'huracan': ['KIT00_BODY', 'BASE'],
 'gt2rs':   ['KIT00_BODY', 'KIT00_INTERIOR'],
 'huayra':  ['KIT00_BODY', 'KIT00_REAR_WINDOW', 'KIT00_FRONT_WINDOW', 'KIT00_LEFT_HEADLIGHT', 'KIT00_RIGHT_HEADLIGHT'],
 'terzo':   ['KIT00_BODY', 'KIT00_LEFT_SIDE_MIRROR'],
}
# parts left out (merged into a name the converter never takes): the Countach's (from CSR2) chassis frame in its lamp
# glass parts and its engine in the rear window and right lamp, 80,000 vertices under the body at every level
DROP = {'countach': ['KIT00_REAR_WINDOW', 'KIT00_RIGHT_HEADLIGHT', 'KIT00_LEFT_HEADLIGHT_GLASS', 'KIT00_RIGHT_HEADLIGHT_GLASS',
                     'BASE', 'BASE_E', 'KIT00_FRONT_WINDOW'],  # (tried back 6 Nov: still crumpled shards; the open frames kept)
        'diablo': ['KIT00_LEFT_HEADLIGHT', 'KIT00_RIGHT_HEADLIGHT', 'KIT00_LEFT_HEADLIGHT_GLASS', 'KIT00_RIGHT_HEADLIGHT_GLASS']}  # (its pop-up lamps, modelled raised: two boxes on its nose that read as wing pieces, the user's 6 Nov; closed, as parked)  # (6 Nov: BASE and the glass read as scattered spikes and shards, in the game too; KIT00_BODY has the whole shell)
# the car's own cabin (merged into the body above): the template's interior not fitted in as well
OWN_CABIN = {'jesko', 'zr1', 'gt2rs', 'f8', 'slrmoss', '335i', '190e', 'brera', 'chiron', 'fordgt17', 'huracan'}  # (the SLR Stirling Moss: no roof, and the coupe template's headliner fitted under none stood over its cockpit in black)
HEIGHT = {  # the body moved up (+) or down (-), metres, from the store's side views (the user's 6 Nov: "fix the heights")
 'huracan': -0.06, 'jesko': +0.04, 'maloo': -0.03, 'impala': +0.10, '190e': +0.03, 'zr1': +0.03, 'diablo': +0.09, 'rs5': -0.05, 'chiron': -0.05, 'huayra': +0.02}  # (the evening's: the Impala's tyres were under its body, the others' fronts tucked under their lips)
WIDEN = {'jesko': 1.17, 'senna': 1.08, '190e': 1.05, 'terzo': 1.03, 'chiron': 1.03, 'impala': 1.14, 'rs5': 1.03, 'maloo': 1.065}  # the body's width alone scaled (plan "widen"), where the game's tyres poke out past the arches
COVERS = {'rs5'}  # lamps under another sheet's shells: those left out (nfsu2forza NFSU_COVERS)
THIN = {}  # dense ports whose levels are all one mesh, thinned (cartoolkit "decimate"; its levels then share no vertices)
ARCHES = {  # (6 Nov evening: refined from the store's side views and sideplot.py, the GT2 RS to the Terzo) the arch middles as the length fit puts them, where the converter's own read is off (NFSU_ARCHES); from
  # sideplot.py's measure of each arch against its wheel (the user's 6 Nov screenshots: the M8 GTE's rear wheel behind its arch)
 'm8gte': [2.089, -2.084], 'senna': [1.932, -2.413], '190e': [2.562, -1.659], 'eclipse': [1.875, -1.912],
 'charger': [2.464, -2.182], 'brera': [1.925, -1.81], 'lfa': [2.172, -2.197], 'xk': [2.294, -1.996], '4c': [1.649, -1.87],
 'countach': [2.0, -2.149, 1.834, -2.277], 'gt2rs': [1.794, -1.91], 'gtx1': [1.88, -2.353, 1.983, -2.353], 'huayra': [1.947, -2.383], 'zr1': [2.059, -2.093], 'maloo': [2.409, -2.008, 2.265, -2.208], 'rs5': [2.335, -2.157, 2.255, -2.157], 'fordgt17': [1.977, -2.228], 'chiron': [2.195, -2.257], 'terzo': [2.14, -2.216], 'impala': [2.849, -2.21, 2.503, -2.21]}  # (its template's rotors: the front pair only, so its hubs given)
PAINT = {'chiron': '0.08,0.16,0.5', 'lfa': '0.85,0.85,0.88', 'm2': '0.1,0.35,0.75', '190e': '0.05,0.05,0.06', 'gt2rs': '0.6,0.6,0.62',
         'xk': '0.12,0.25,0.15', 'huayra': '0.7,0.7,0.72', 'impala': '0.55,0.05,0.05', 'rs5': '0.12,0.3,0.12', 'gtx1': '0.9,0.9,0.92',
         'jesko': '0.85,0.85,0.88', 'terzo': '0.05,0.05,0.06', 'maloo': '0.85,0.45,0.05', 'm8gte': '0.1,0.15,0.4', 'sesto': '0.2,0.2,0.22',
         'f8': '0.7,0.02,0.02', 'svj': '0.25,0.6,0.1', 'eclipse': '0.75,0.05,0.05', 'civicfn2': '0.9,0.9,0.92', 'charger': '0.05,0.05,0.06',
         'evora': '0.95,0.6,0.05', '335i': '0.6,0.6,0.62', 'fordgt17': '0.1,0.25,0.65', 'slrmoss': '0.6,0.6,0.62', 'brera': '0.6,0.02,0.02',
         '4c': '0.7,0.02,0.02', 'zr1': '0.95,0.75,0.05', 'egoista': '0.25,0.27,0.28', 'senna': '0.95,0.45,0.05', 'huracan': '0.25,0.6,0.1',
         'countach': '0.7,0.02,0.02', 'diablo': '0.85,0.65,0.05'}


def stage(src, key):
    """A copy of the car's folder under its parts' own prefix (the converter and the merge take the folder's name; the
    Senna's are SENNA_, in a folder SENNA: one in CARS_REPLACE/GALLARDO keeps GALLARDO), its texture pack TEXTURES.BIN."""
    import nfsu, nfsu2forza
    pre = nfsu2forza.part_prefix(nfsu.read(os.path.join(src, 'GEOMETRY.BIN')), os.path.basename(os.path.normpath(src)).upper())
    d = os.path.join(W, 'src', key, pre)
    if not os.path.exists(d):
        os.makedirs(d)
        for f in os.listdir(src):
            low = f.lower()
            if low in ('geometry.bin', 'textures.bin', 'vinyls.bin') or low.endswith('textures.bin'):
                to = 'TEXTURES.BIN' if low.endswith('textures.bin') and not low.startswith('xsd') else f.upper()
                if low == 'xsdtextures.bin': continue  # (the Diablo's SD pack: the HD one taken)
                if low == 'xhdtextures.bin': to = 'TEXTURES.BIN'
                shutil.copy(os.path.join(src, f), os.path.join(d, to))
    return d


def convert(key):
    src, name, short, make, year, price, hp, tq, kg, tmpl, eng, phys, perf = CARS[key]
    out = os.path.join(W, 'out', key)
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, 'build.log'); open(log, 'w').close()
    carbin_t, lv = template_files(tmpl)
    sd = stage(src, key)
    if key in MERGE or key in DROP or key in OWN_CABIN or key in HEIGHT or key in WIDEN:
        plan = os.path.join(out, 'plan.json')
        json.dump({'merge': {'KIT00_BODY': MERGE.get(key, ['KIT00_BODY']), **({'UNUSED': DROP[key]} if key in DROP else {})}, 'most_wanted': True,
                   **({'interior': True} if key in OWN_CABIN else {}), **({'lower': -HEIGHT[key] * 1.6} if key in HEIGHT else {}), **({'widen': WIDEN[key]} if key in WIDEN else {})}, open(plan, 'w'))
        cmd = [sys.executable, '-W', 'ignore', os.path.join(T, 'cartoolkit.py'), plan, carbin_t, sd, os.path.join(out, 'car.carbin')]
    elif key in THIN:
        plan = os.path.join(out, 'plan.json')
        json.dump({'decimate': THIN[key], 'most_wanted': True}, open(plan, 'w'))
        cmd = [sys.executable, '-W', 'ignore', os.path.join(T, 'cartoolkit.py'), plan, carbin_t, sd, os.path.join(out, 'car.carbin')]
    else:
        cmd = [sys.executable, '-W', 'ignore', os.path.join(T, 'nfsu2forza.py'), carbin_t, sd, os.path.join(out, 'car.carbin')]
    if lv: cmd += ['--liveries', lv]
    if tmpl in ('BMWM3GTR42',): cmd += ['--no-stock-wing']
    cmd += ['--clear-livery']  # (the template's own badges and lamps out of the atlas, but for the parts it keeps: they left the car's lamps a few texels, dark blobs, 6 Nov)
    env = dict(os.environ, **({'NFSU_ARCHES': ','.join(map(str, ARCHES[key]))} if key in ARCHES else {}))
    if key in COVERS: env['NFSU_COVERS'] = '1'
    rc = run(cmd, log, env)
    print('%-9s convert %s' % (key, 'ok' if rc == 0 and os.path.exists(os.path.join(out, 'car.carbin')) else 'FAILED (see %s)' % log), flush=True)
    return rc == 0


def preview(key, views='fside,rear,left'):
    import forzaxpr
    out = os.path.join(W, 'out', key)
    if not os.path.exists(os.path.join(out, 'livery0hi.png')):
        forzaxpr.decode(os.path.join(out, 'liveries', 'standard', 'livery0hi.xpr'), out)
    env = dict(os.environ, VIEWS=views)
    run([BLENDER, '-b', '--python', os.path.join(T, 'carlit.py'), '--', os.path.join(out, 'car.carbin'),
         os.path.join(out, 'livery0hi.png'), os.path.join(out, 'r')], os.path.join(out, 'preview.log'), env)


def icon(key):
    """The tile's render with the wheels where the game puts them (iconfix.py: the template's hubs, ride heights and
    tyres), not where carlit's arch guess put them."""
    import iconfix
    out = os.path.join(W, 'out', key)
    if not os.path.exists(os.path.join(out, 'livery0hi.png')):
        import forzaxpr
        forzaxpr.decode(os.path.join(out, 'liveries', 'standard', 'livery0hi.xpr'), out)
    return iconfix.render(os.path.join(out, 'car.carbin'), os.path.join(out, 'livery0hi.png'), CARS[key][9],
                          PAINT.get(key, '0.7,0.05,0.05'), os.path.join(out, 'i'))


def place_icon(key):
    """The rendered tile (carlit ICON=1, 512 x 256, a clear background) as a cut-out at the car's tile, then the disc's
    form and the DLC badge (tools/caricontile.py)."""
    import numpy as np
    from PIL import Image
    import addcar, caricontile, forzaxpr as fx
    o = ORD[key]
    png = icon(key)
    im = Image.open(png).convert('RGBA')
    box = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    if box: im = im.crop(box)
    im.thumbnail((124, 60), Image.LANCZOS)
    tile = Image.new('RGBA', (128, 64), (0, 0, 0, 0))
    tile.paste(im, ((128 - im.size[0]) // 2, (64 - im.size[1]) // 2 + 1), im)
    src, dst = caricontile.pack_path(DISC, MODS, o)
    d = bytearray(open(src, 'rb').read())
    t = fx.textures(d)[0]
    enc = fx.encode_dxt5(np.ascontiguousarray(np.asarray(tile, np.uint8)))
    off = t['start'] + (o % 64) * addcar.TILE
    d[off:off + addcar.TILE] = enc
    open(dst, 'wb').write(bytes(d))
    caricontile.main(DISC, MODS, ['%d:form:dlc' % o])


def install(key):
    import forzacab
    src, name, short, make, year, price, hp, tq, kg, tmpl, eng, phys, perf = CARS[key]
    out = os.path.join(W, 'out', key)
    log = os.path.join(out, 'install.log')
    cab = os.path.join(out, 'car_%s.cab' % NAME[key])
    t = tmpl.lower()
    repl = ['cars/%s/car.carbin=%s' % (t, os.path.join(out, 'car.carbin'))]
    for n in ('livery0', 'livery0hi', 'livery0nc'):
        repl.append('cars/%s/liveries/standard/%s.xpr=%s' % (t, n, os.path.join(out, 'liveries', 'standard', n + '.xpr')))
    if run([sys.executable, os.path.join(T, 'forzacab.py'), 'replace', os.path.join(DISC, 'media', 'cabs', 'car_%s.cab' % tmpl), cab] + repl, log):
        print(key, 'cab FAILED'); return False
    cmd = [sys.executable, os.path.join(T, 'addcar.py'), DISC, MODS, tmpl, NAME[key], '--ordinal', str(ORD[key]), '--name', name, '--short', short,
           '--cab', cab, '--make', make, '--year', str(year), '--price', str(price), '--engine-like', eng,
           '--engine', NAME[key], '--power', str(hp), '--torque', str(tq), '--mass', str(kg), '--stats-like', tmpl,
           '--performance', '%s,%s,%s' % perf]
    for p in phys: cmd += ['--physics-like', p]
    if os.path.exists(os.path.join(out, 'upgrades.xml')): cmd += ['--upgrades', os.path.join(out, 'upgrades.xml')]
    if os.path.exists(os.path.join(out, 'liveries.bin')): cmd += ['--liveries', os.path.join(out, 'liveries.bin')]
    if run(cmd, log):
        print(key, 'addcar FAILED (see %s)' % log); return False
    print('%-9s installed as %s' % (key, NAME[key]), flush=True)
    return True


if __name__ == '__main__':
    what, keys = sys.argv[1], sys.argv[2:] or list(CARS)
    for k in keys:
        try:
            if what == 'convert': convert(k)
            elif what == 'preview': preview(k)
            elif what == 'icon': print(k, icon(k))
            elif what == 'install': install(k) and place_icon(k) is None
            elif what == 'tile': place_icon(k)
        except Exception as e:
            print(k, what, 'ERROR', e, flush=True)
