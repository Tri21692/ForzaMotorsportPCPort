"""Change the physics, upgrade lists, spec-screen figures and career unlock
of a car already in the mods folder (one addcar.py added), as addcar.py's
options do.

  python tools/tunecar.py <disc folder> <mods folder> <car>
                          [--physics-like <car>:<part>[,<part>...]]... [--tooldata-like <car>:<Section>[,...]]...
                          [--tires <front>,<rear>] [--final-drive <ratio>] [--mass <kg>]
                          [--performance <0-60 s>,<0-100 mph s>,<top km/h>] [--power <hp>] [--own-engine <name>] [--price <credits>]
                          [--unlock <level>[,<Europe's>,<Asia's>]] [--paint-like <car>] [--subclass <D4..S1>]
                          [--ratings <speed>,<acceleration>,<handling>]
                          [--scale <physics file or folder>:<attribute>[,...]=<factor>]... [--shift <same>=<amount>]...
  e.g.  <disc>  run/mods_lambo  ChevyCobaltSS  --tires 205/45R18,205/45R18  --final-drive 3.85

See addcar.py for what each does. --unlock: the career's dealers sell the
car only from that driver level on (North America's, then Europe's and
Asia's if given), as the disc's cars: model.dat's flags at 93-95 (one byte
a region, 1 on sale from the start) cleared, a CareerCarUnlock at that
level in rarity/<region>/rarityregiondef.xml (a level's rewards: the
index is the level), and the unlock text the dealer shows (model.dat's
u16 string ids at 72, 74, 76 for the three regions, 78 Arcade's; 1 none),
"Reach Level N to unlock this car for purchase in Buy Cars." in every
language (the disc's own sentence, its number changed); --unlock 0 puts it
on sale from the start. --paint-like: the
paint shop's colour choices of that car, without its vinyl layers. --subclass: the class the
car lists show (gamecars.dat's u32 at 100, a performancesubclass.dat id: D4 1 .. A1 16, S4 17 ..
S1 20, GT 21, GTS 22, P1 23, by name), as the shop works it out from the car's physics (the Gallardo listed A, from
addcar --stats-like, and the shop showed S4). --scale (any number): those attributes of the car's
physics file (aero/body.xml) or of every level of a folder (aero/front: l0-l3.xml) multiplied by the
factor, e.g. aero/front:Downforce0,Downforce1=1.15; --shift adds the amount instead, e.g.
maxdata.xml:MinZ,MaxZ,PosZ=0.275 (the collision box and spheres 0.275 m forward). Writes only into
the mods folder, never the saves. --own-engine: the car's engine copied under
that name (its physics in Cars.ca2, its sound in the car's cab), as its only engine, so a car that
shares one (the M3 GTR MW the disc #42's) can be changed alone; with --power its torque curves are
scaled to that figure (else --power changes only the menus' figure).
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'
REGIONS = (('northamerica', 'NorthAmerica'), ('europe', 'Europe'), ('asia', 'Asia'))
UNLOCK_TEXT = 86  # IDS_Model_139_AsiaUnlockString, the Ferrari 360's: "Reach Level 20 to unlock this car for purchase in Buy Cars."


def set_unlock(disc, mods, mega, o, mrow, levels):
    """The car of ordinal o on sale from those levels (one a region); returns
    the string files to write ({path: bytes}). Level 0 everywhere: on sale
    from the start, no unlock text (as the disc's starting cars)."""
    if not any(levels):
        for region, _ in REGIONS:
            rk = B.join(('rarity', region, 'rarityregiondef.xml'))
            mega.files[rk] = re.sub(r'\s*CareerCarUnlock="%d"(?=\s)' % o, '', mega.files[rk].decode('latin-1')).encode('latin-1')
        struct.pack_into('<4H', mrow, 72, 1, 1, 1, 1)
        mrow[93:96] = b'\1\1\1'
        print('unlock: on sale from the start')
        return {}
    for (region, _), lv in zip(REGIONS, levels):
        rk = B.join(('rarity', region, 'rarityregiondef.xml'))
        x = mega.files[rk].decode('latin-1')
        x = re.sub(r'\s*CareerCarUnlock="%d"(?=\s)' % o, '', x)  # (once only)
        lvs = list(re.finditer(r'<L\b.*?</L>', x, re.S))
        l = lvs[lv]
        nl = '\r\n' if '\r\n' in x else '\n'
        new = l.group(0).replace('<Rewards', '<Rewards' + nl + '\t\t\tCareerCarUnlock="%d"' % o, 1)
        mega.files[rk] = (x[:l.start()] + new + x[l.end():]).encode('latin-1')
    loc = addcar.disc_file(disc, 'media', 'Loc')
    ids, strings = None, {}
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'CarDataStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'CarDataStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        e1, text, _, _ = addcar.read_strings(base)
        a = b = dict(e1[:-1])[UNLOCK_TEXT] * 2
        while text[b:b + 2] != b'\0\0': b += 2
        sentence = text[a:b].decode('utf-16-le')
        have = addcar.string_ids(base)
        names = ['IDS_Model_%d_%sUnlockString' % (o, r) for _, r in REGIONS]
        if any(n in have for n in names):  # set before: the same ids, the text changed
            out = rewrite(base, {have[n]: sentence.replace('20', str(lv)) for n, lv in zip(names, levels)})
        else:
            out = addcar.write_strings(base, [(n, sentence.replace('20', str(lv))) for n, lv in zip(names, levels)])
        got = addcar.string_ids(out)
        these = tuple(got[n] for n in names)
        if ids not in (None, these): raise SystemExit('%s: the new string ids differ between languages' % lang)
        ids, strings[mp] = these, out
    struct.pack_into('<3H', mrow, 72, *ids)
    mrow[93:96] = bytes(3)
    print('unlock: from level %d (North America), %d (Europe), %d (Asia); strings %s' % (*levels, ids))
    return strings


def rewrite(d, texts):
    """CarDataStrings.str with these ids' texts changed ({id: text})."""
    e1, text, e2, names = addcar.read_strings(d)
    order = [i for i, _ in e1[:-1]]
    old = {}
    for i, o in e1[:-1]:
        e = o * 2
        while text[e:e + 2] != b'\0\0': e += 2
        old[i] = text[o * 2:e].decode('utf-16-le')
    old.update(texts)
    body, ent = bytearray(), []
    for i in order:
        ent.append((i, len(body) // 2))
        body += old[i].encode('utf-16-le') + b'\0\0'
    end = e1[-1][1]
    tail = text[end * 2:]
    ent.append((0xFFFF, len(body) // 2))
    blk1 = b''.join(struct.pack('<HI', i, o) for i, o in ent) + bytes(body) + tail
    blk1 = struct.pack('<II', 8 + len(blk1), len(ent) - 1) + blk1
    blk2 = b''.join(struct.pack('<HHI', i, j, o) for i, j, o in e2) + bytes(names)
    blk2 = struct.pack('<II', 8 + len(blk2), len(e2)) + blk2
    head = bytearray(d[:28])
    struct.pack_into('<II', head, 12, 28, 28 + len(blk1))
    return bytes(head) + blk1 + blk2


def main(disc, mods, car, physics_like=None, tooldata_like=None, tires=None, final_drive=None, mass=None, performance=None,
         power=None, unlock=None, paint_like=None, subclass=None, scale=None, shift=None, ratings=None, own_engine=None, price=None):
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
    cab = None
    if own_engine:  # the car's engine copied as its own (another car may share it), physics and sound, and its power scaled
        tool = cars.files[tk].decode('latin-1')
        eng = re.search(r'<E0 [^>]*File="([^"]*)"', tool).group(1)
        if eng.lower() != own_engine.lower():
            ep_f, ep_s = B.join(('engines', eng.lower())) + B, B.join(('engines', own_engine.lower())) + B
            for k in [k for k in cars.files if k.lower().startswith(ep_f)]:
                cars.files[ep_s + k[len(ep_f):]] = cars.files[k]
            cars.files[tk] = re.sub(r'(<E0 [^>]*File=")[^"]*"', lambda g: g.group(1) + own_engine + '"', tool).encode('latin-1')
            cab_path = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % car)  # its sound, in the car's own cab (as addcar.py's --engine-like)
            files, root = addcar.cab_files(open(cab_path, 'rb').read())
            ea = B.join(('engines', eng.lower(), 'audio')) + B
            for k, v in list(files.items()):
                if not k.lower().startswith(ea): continue
                rest = re.sub(re.escape(eng.lower()), own_engine.lower(), k[len(ea):].lower())
                if k.lower().endswith('.ini'): v = re.sub(re.escape(eng).encode(), own_engine.encode(), v, flags=re.I)
                files[B.join(('engines', own_engine.lower(), 'audio')) + B + rest] = v
            cab = (cab_path, files, root)
            print('engine: %s\'s copied as %s (physics, and its sound in car_%s.cab)' % (eng, own_engine, car))
        if power:  # every enginetuning level's full-throttle torque scaled to the power figure: its TorqueScale, since
            # the upgrade levels' curves are all zeros (they take the stock curve's shape at their own scale)
            k1 = power / (struct.unpack_from('<f', grow, 12)[0] / 10 / 0.745699872)
            for lv in range(4):
                t = B.join(('engines', own_engine.lower(), 'physics', 'enginetuning', 'l%d.xml' % lv))
                if t in cars.files:
                    cars.files[t] = re.sub(rb'(<FullThrottle [^>]*?TorqueScale=")([0-9.]+)"',
                                           lambda g: g.group(1) + b'%.6f"' % (float(g.group(2)) * k1), cars.files[t], count=1)
            bk = B.join(('engines', own_engine.lower(), 'physics', 'base.xml'))  # the upgrade screen's graph, as high
            cars.files[bk] = re.sub(rb'(Graphing(?:MaxTorque|MaxPower)=")([0-9.]+)"',
                                    lambda g: g.group(1) + b'%.0f"' % (float(g.group(2)) * k1), cars.files[bk])
            print('engine %s: torque x%.3f = %.0f hp' % (own_engine, k1, power))
    for op, spec in [('x', s) for s in scale or ()] + [('+', s) for s in shift or ()]:  # <file or folder>:<attr>,<attr>=<number>
        where, rest = spec.split(':')
        attrs, n = rest.split('=')
        base = cdst + 'physics' + B + where.replace('/', B).lower()
        keys = [base] if base.endswith('.xml') else [base + B + 'l%d.xml' % lv for lv in range(4)]
        keys = [k for k in keys if k in cars.files]
        if not keys: raise SystemExit('%s: no such physics file' % spec)
        for k in keys:
            x = cars.files[k]
            for a in attrs.split(','):  # (every one of that name: the collision spheres' PosZ)
                if not re.search(rb'\b%s="[-0-9.]+"' % a.encode(), x): raise SystemExit('%s: %s has no %s' % (spec, k, a))
                x = re.sub(rb'(\b%s=")([-0-9.]+)"' % a.encode(),
                           lambda g: g.group(1) + b'%.6g"' % (float(g.group(2)) * float(n) if op == 'x' else float(g.group(2)) + float(n)), x)
            cars.files[k] = x
        print('%s: %s %s%s (%d files)' % (where, attrs, op, n, len(keys)))
    if performance:
        t60, t100, vmax = performance
        struct.pack_into('<3f', mrow, 80, t60, t100, vmax / 3.6)
        struct.pack_into('<2f', grow, 48, t60, t100)
        struct.pack_into('<f', grow, 64, vmax / 3.6)
        print('spec screen: 0-60 mph %.1f s, 0-100 mph %.1f s, %.0f km/h' % performance)
    if power:  # the menus' power figure (gamecars.dat, tenths of a kilowatt); the engine itself as it was but with --own-engine
        struct.pack_into('<f', grow, 12, power * 0.745699872 * 10)
        print('menus: %.0f hp' % power)
    if price:  # what the dealer asks: model.dat's two prices (24, 28) and gamecars.dat's (88, 92), as addcar.py's --price
        struct.pack_into('<II', mrow, 24, price, price)
        struct.pack_into('<II', grow, 88, price, price)
        print('price: %d credits' % price)
    if paint_like:  # the paint shop's base colours as that car's, without its vinyl layers (custom: a race car has no liveries.xml at all, and no paint shop)
        lx = cars.files[B.join(('cars', paint_like.lower(), 'liveries', 'liveries.xml'))].decode('latin-1')
        lx = re.sub(r'[ \t]*<custom\b[^>]*/>\r?\n?', '', lx)
        cars.files[cdst + B.join(('liveries', 'liveries.xml'))] = lx.encode('latin-1')
        print('paint shop: %s\'s colours, no vinyls' % paint_like)
    if subclass:  # the listed class: performancesubclass.dat's 28-byte rows, u32 id, u32 class, then the name at 12
        sd = mega.files[B.join(('forzadb', 'cardb', 'performancesubclass.dat'))]
        ids = {sd[i + 12:i + 16].rstrip(b'\0').decode(): struct.unpack_from('<I', sd, i)[0] for i in range(0, len(sd), 28)}
        if subclass.upper() not in ids: raise SystemExit('--subclass: one of %s' % ', '.join(sorted(ids)))
        was = struct.unpack_from('<I', grow, 100)[0]
        struct.pack_into('<I', grow, 100, ids[subclass.upper()])
        print('listed class: %s (subclass %d, was %d)' % (subclass.upper(), ids[subclass.upper()], was))
    if ratings:  # the car lists' speed, acceleration and handling figures and their mean: gamecars.dat 140-152, model.dat 36-48
        r = list(ratings) + [sum(ratings) / 3]
        struct.pack_into('<4f', grow, 140, *r)
        struct.pack_into('<4f', mrow, 36, *r)
        print('ratings: %.1f %.1f %.1f (%.3f)' % tuple(r))
    strings = {}
    if unlock:
        strings = set_unlock(disc, mods, mega, o, mrow, list(unlock) + [unlock[-1]] * (3 - len(unlock)))
    mega.files[key] = ctx['xml'].encode('latin-1')
    mega.files[mk] = addcar.put_row(model, bytes(mrow))
    mega.files[gk] = addcar.put_row(games, bytes(grow))
    for a in (mega, cars): a.check()
    for a in (mega, cars): a.write()
    if cab:
        import forzacab
        open(cab[0], 'wb').write(forzacab.pack(cab[1], cab[2]))
        print('%s: %d files' % (cab[0], len(cab[1])))
    for mp, out in strings.items():
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(out)


if __name__ == '__main__':
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a in ('--physics-like', '--tooldata-like', '--scale', '--shift'): opts.setdefault(a[2:].replace('-', '_'), []).append(next(it))
        elif a in ('--tires', '--final-drive', '--mass', '--performance', '--power', '--unlock', '--paint-like', '--subclass', '--ratings', '--own-engine', '--price'): opts[a[2:].replace('-', '_')] = next(it)
        else: args.append(a)
    if len(args) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, physics_like=opts.get('physics_like'), tooldata_like=opts.get('tooldata_like'), tires=opts.get('tires'),
         final_drive=float(opts['final_drive']) if 'final_drive' in opts else None,
         mass=float(opts['mass']) if 'mass' in opts else None,
         performance=tuple(float(x) for x in opts['performance'].split(',')) if 'performance' in opts else None,
         power=float(opts['power']) if 'power' in opts else None,
         unlock=tuple(int(x) for x in opts['unlock'].split(',')) if 'unlock' in opts else None,
         paint_like=opts.get('paint_like'), subclass=opts.get('subclass'), scale=opts.get('scale'), shift=opts.get('shift'),
         ratings=tuple(float(x) for x in opts['ratings'].split(',')) if 'ratings' in opts else None, own_engine=opts.get('own_engine'), price=int(opts['price']) if 'price' in opts else None)
