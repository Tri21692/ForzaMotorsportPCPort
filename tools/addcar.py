"""Add a car to Forza as a car of its own, copied from one already there,
instead of putting it in another car's place. Made for the converted NFSU
240SX, which was built in the Civic SI's slot: this copies that slot (as
the mods folder has it, with the S13's body, identity, engine and wheel)
to a new car, and --restore gives the Civic SI back its own files.

  python tools/addcar.py <disc folder> <mods folder> <from> <new> [--ordinal N]
                         [--name <model name>] [--short <short name>] [--restore]
                         [--cab <car cab>] [--make <car>] [--year <year>] [--price <credits>]
                         [--engine-like <car> [--engine <name>] [--power <hp>] [--torque <lb-ft>]]
                         [--mass <kg>] [--stats-like <car>] [--upgrades <upgrades.xml>]
                         [--liveries <liveries.bin>] [--physics-like <car>:<part>[,<part>...]]...
                         [--tooldata-like <car>:<Section>[,...]]... [--tires <front>,<rear>]
                         [--final-drive <ratio>] [--performance <0-60 s>,<0-100 mph s>,<top km/h>]
  e.g.  <disc>  run/mods  CivicSI  Nissan240SXS13  --name "240SX" --restore

<from> and <new> are car names as in cars\\carlist.xml (<new> must not be
there yet). The new car gets, from the mods folder's copy of each file if
there is one, else the disc's:

  Mega.ca2       cars\\carlist.xml: <from>'s entry under the new name and
                 ordinal; forzadb\\cardb\\model.dat and gamecars.dat: its
                 rows (ordinal set, model.dat's name string ids the new
                 car's own); tires\\art\\<wheel>\\: its stock wheel, under the
                 new name
  MegaXPR.ca2    the wheel's textures, likewise
  Cars.ca2       cars\\<from>\\ (tooldata, physics, config) as cars\\<new>\\,
                 the wheel there named after the new car
  car_<new>.cab  <from>'s car cab, cars\\<from>\\ renamed (the model, liveries
                 and engine sounds; engines keep their names)
  media/cars/<new>.liveries.bin    <from>'s, if it has one
  media/caricons<n>.xpr            <from>'s car-select tile, at the new ordinal
  media/Loc/*/CarDataStrings.str   IDS_Model_<ordinal>_Name and _ShortName

--cab: the new car's cab from this file (a converted model, packed into a copy
of <from>'s cab) instead of <from>'s. --make: the maker of that car (its
dealer and logo), or a maker's name as make.dat has it (addmake.py adds
one). --year: the model year. --engine-like: its own copy of
that car's engine and sound (named --engine), scaled to --power and
--torque. --mass: the weight. --stats-like: the menus' figures and ratings
of a similar car. --upgrades: the shop's body kits, hoods and wings that
nfsu2forza.py writes for a Most Wanted car. --liveries: the paint shop's copy of the
livery (nfsu2forza.py --liveries) instead of <from>'s. --physics-like (any
number): those folders of cars\\<car>\\physics (every upgrade level), e.g.
AudiRS6:drivetraindiff (its differentials, and so all-wheel drive) or
Ferrari360:transmission,brakes. --tooldata-like (any number): those
upgrade lists of tooldata.xml (stock level, prices, brake parts, tyre
sizes), e.g. Ferrari360:Brakes,Tire. --tires: every tyre level's sizes,
e.g. 235/35R19,295/30R19. --final-drive: the stock gearbox's final drive
(every level scaled alike). --performance: the spec screen's 0-60 mph and
0-100 mph times and top speed. --mass scales every weight level; with
--cab the driver's seat and mirror view move with the roof's height.

The ordinal is a number no car has and nothing names as a car
(carlist, AI opponents, career prizes): the lists skip 13 numbers, and
some that no car has are named by events' AI players (aicarmodelid);
after those, 244-299. The game holds 300 cars, ordinals 0-299 (below).
The game sizes its car tables from the files (model.dat's reader divides
the size by 104) and finds rows by ordinal; the rows stay in ordinal order.

The .ca2 archives must keep as many 4 MB streams as the disc's: the
runtime can only re-sign records the executable already has (file.c).

--restore: <from> goes back to the disc's files (its carlist entry, rows,
cars\\<from>\\, wheel, icon tile, name strings), and the mods folder's
car_<from>.cab is renamed car_<from>.cab.replaced.

Writes only into the mods folder, never the saves.
"""
import math
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forzacab

B = '\\'
CHUNK = 4 << 20
TILE = 16 * (128 // 4) * 16  # a 128x64 DXT5 icon: 16 rows of 32 blocks of 16 bytes
# The game's limits (25 Oct, from the executable): carlist.xml is read into
# a fixed table of 300 cars with no bound check (0x44340: 140-byte records,
# then (ordinal, record) pairs at +0xA418), and per-car tables of the
# profile are 300 long and indexed by ordinal (a 300-bit set and 12-byte
# records, 0x55610 and 0x56060; an ordinal of 300 or more is skipped).
# The icon packs hold 5 x 64 tiles.
MAX_CARS, MAX_ORDINAL = 300, 299


def unpack_ca2(path):
    data, raw = open(path, 'rb').read(), b''
    while data:  # zlib streams of 4 MB each, zero-padded between
        z = zlib.decompressobj()
        raw += z.decompress(data)
        data = z.unused_data.lstrip(b'\0')
        if not z.eof: break
    return raw


def cab_files(blob):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.cab', delete=False) as f: f.write(blob)
    try:
        d, _, es = forzacab.read(f.name)
        return {e['name']: forzacab.data(d, e) for e in es}, (es[0]['root'] if es else '')
    finally:
        os.remove(f.name)


def disc_file(disc, *parts):
    """A path on the disc, matched without regard to case."""
    p = disc
    for part in parts:
        hit = next((f for f in os.listdir(p) if f.lower() == part.lower()), None) if os.path.isdir(p) else None
        if hit is None: return None
        p = os.path.join(p, hit)
    return p


class Archive:
    """One of the disc's .ca2, as the mods folder has it (or the disc)."""

    def __init__(self, disc, mods, name):
        self.disc_path = disc_file(disc, 'media', 'cabs', name)
        self.out = os.path.join(mods, 'media', 'cabs', name)
        disc_raw = unpack_ca2(self.disc_path)
        self.streams = math.ceil(len(disc_raw) / CHUNK)
        self.disc, _ = cab_files(disc_raw)
        self.files, self.root = cab_files(unpack_ca2(self.out) if os.path.exists(self.out) else disc_raw)
        self.name = name

    def check(self):
        """Packed, and as many streams as the disc's, before anything is written."""
        self.blob = blob = forzacab.pack(self.files, self.root)
        if math.ceil(len(blob) / CHUNK) != self.streams:
            raise SystemExit('%s: %d bytes unpacked, %d streams of 4 MB; the disc has %d, and the game would refuse it; nothing written'
                             % (self.name, len(blob), math.ceil(len(blob) / CHUNK), self.streams))

    def write(self):
        blob = self.blob
        os.makedirs(os.path.dirname(self.out), exist_ok=True)
        open(self.out, 'wb').write(forzacab.ca2(blob))
        print('%s: %d files, %.2f of %d MB' % (self.name, len(self.files), len(blob) / 1048576, 4 * self.streams))


def under(files, prefix):
    return {k: v for k, v in files.items() if k.lower().startswith(prefix.lower())}


def rename_tree(files, src, dst):
    """Every file under src (a path ending in a backslash) copied under dst."""
    got = under(files, src)
    for k, v in got.items(): files[dst + k[len(src):]] = v
    return len(got)


def restore_tree(files, disc, prefix):
    for k in list(under(files, prefix)): del files[k]
    for k, v in under(disc, prefix).items(): files[k] = v


# ---- carlist.xml

def car_block(xml, name):
    m = re.search(r'[ \t]*<car name="%s"[^>]*>.*?</car>\r?\n' % re.escape(name), xml, re.S | re.I)
    if not m: raise SystemExit('carlist.xml: no car named %s' % name)
    return m


def ordinal_of(xml, name):
    return int(re.search(r'Ordinal="(\d+)"', car_block(xml, name).group(0)).group(1))


def free_ordinal(mega):
    """The lowest number no car has and no file names as a car."""
    xml = mega['cars' + B + 'carlist.xml'].decode('latin-1')
    used = {int(o) for o in re.findall(r'Ordinal="(\d+)"', xml)}
    named = set()
    for k, v in mega.items():
        if k.lower().endswith('.xml'):
            named |= {int(o) for o in re.findall(rb'(?i)(?:aicarmodelid|carmodelid|careercarunlock)="(\d+)"', v)}
    for o in range(MAX_ORDINAL + 1):
        if o not in used and o not in named: return o
    raise SystemExit('no free ordinal up to %d' % MAX_ORDINAL)


# ---- forzadb\cardb tables: rows by ordinal, in ordinal order

def table_rows(blob, size):
    return [blob[i:i + size] for i in range(0, len(blob), size)]


def row_of(rows, ordinal):
    return next(r for r in rows if struct.unpack_from('<I', r)[0] == ordinal)


def put_row(rows, row):
    o = struct.unpack_from('<I', row)[0]
    rows = [r for r in rows if struct.unpack_from('<I', r)[0] != o] + [row]
    return b''.join(sorted(rows, key=lambda r: struct.unpack_from('<I', r)[0]))


# ---- media/Loc/*/CarDataStrings.str
# "LSBL", u32 28 (header), u32 4, u32 block 1, u32 block 2, u32 0, u32 0.
# Block 1: u32 size, u32 n, n + 1 entries of u16 id, u32 offset in UTF-16
# characters (the last id 65535, its offset the end of the text), then the
# NUL-terminated UTF-16 strings. Block 2: u32 size, u32 n, n entries of u16
# id, u16 id, u32 byte offset, then the ASCII names (IDS_Model_44_Name).

def read_strings(d):
    assert d[:4] == b'LSBL', d[:4]
    b1, b2 = struct.unpack_from('<II', d, 12)
    s1, n1 = struct.unpack_from('<II', d, b1)
    e1 = [struct.unpack_from('<HI', d, b1 + 8 + 6 * i) for i in range(n1 + 1)]
    p1 = b1 + 8 + 6 * (n1 + 1)
    text = d[p1:b1 + s1]
    s2, n2 = struct.unpack_from('<II', d, b2)
    e2 = [struct.unpack_from('<HHI', d, b2 + 8 + 8 * i) for i in range(n2)]
    p2 = b2 + 8 + 8 * n2
    names = d[p2:b2 + s2]
    return e1, text, e2, names


def string_ids(d):
    e1, text, e2, names = read_strings(d)
    out = {}
    for i, _, off in e2:
        out[names[off:names.index(b'\0', off)].decode()] = i
    return out


def write_strings(d, add):
    """d with strings added: add is [(name, text)]; ids after the highest."""
    e1, text, e2, names = read_strings(d)
    end = e1[-1][1]  # the sentinel's offset: where the text ends
    body, tail = bytearray(text[:end * 2]), text[end * 2:]
    nid = max(i for i, _ in e1[:-1]) + 1
    names = bytearray(names)
    e1, e2 = e1[:-1], list(e2)
    for name, s in add:
        e1.append((nid, len(body) // 2))
        body += s.encode('utf-16-le') + b'\0\0'
        e2.append((nid, nid, len(names)))
        names += name.encode() + b'\0'
        nid += 1
    e1.append((0xFFFF, len(body) // 2))
    blk1 = b''.join(struct.pack('<HI', i, o) for i, o in e1) + bytes(body) + tail
    blk1 = struct.pack('<II', 8 + len(blk1), len(e1) - 1) + blk1
    blk2 = b''.join(struct.pack('<HHI', i, j, o) for i, j, o in e2) + bytes(names)
    blk2 = struct.pack('<II', 8 + len(blk2), len(e2)) + blk2
    head = bytearray(d[:28])
    struct.pack_into('<II', head, 12, 28, 28 + len(blk1))
    return bytes(head) + blk1 + blk2


# ----

def main(disc, mods, src, new, ordinal=None, name=None, short=None, restore=False, cab=None, make=None, year=None,
         engine_like=None, engine=None, power=None, torque=None, mass=None, stats_like=None, price=None, upgrades=None, liveries=None,
         physics_like=None, tooldata_like=None, tires=None, final_drive=None, performance=None):
    mega, cars, xpr = Archive(disc, mods, 'Mega.ca2'), Archive(disc, mods, 'Cars.ca2'), Archive(disc, mods, 'MegaXPR.ca2')
    m = mega.files
    key = 'cars' + B + 'carlist.xml'
    xml = m[key].decode('latin-1')
    if re.search(r'<car name="%s"' % re.escape(new), xml, re.I): raise SystemExit('carlist.xml: %s is there already' % new)
    so = ordinal_of(xml, src)
    if ordinal is None: ordinal = free_ordinal(m)
    if re.search(r'Ordinal="%d"' % ordinal, xml): raise SystemExit('ordinal %d is taken' % ordinal)
    if not 0 <= ordinal <= MAX_ORDINAL: raise SystemExit('ordinal %d: the game keeps cars 0-%d only' % (ordinal, MAX_ORDINAL))
    if len(re.findall(r'<car name=', xml)) >= MAX_CARS: raise SystemExit('carlist.xml has %d cars, as many as the game holds' % MAX_CARS)
    if len(new) >= 60: raise SystemExit('%s: names are kept in 60 bytes' % new)
    wheel = re.search(r'<WheelStyle>\s*<P0 [^>]*File="([^"]*)"', cars.files[B.join(('cars', src.lower(), 'tooldata.xml'))].decode('latin-1')).group(1)

    # Mega.ca2: the car list, the tables, the wheel's model
    blk = car_block(xml, src)
    entry = re.sub(r'Ordinal="\d+"', 'Ordinal="%d"' % ordinal, re.sub(r'name="[^"]*"', 'name="%s"' % new, blk.group(0), count=1))
    for attr, val in (('displayName', name), ('shortName', short or name)):
        if val: entry = re.sub(r'\b%s="[^"]*"' % attr, '%s="%s"' % (attr, val), entry)
    xml = xml[:blk.end()] + entry + xml[blk.end():]
    model = table_rows(m[B.join(('forzadb', 'cardb', 'model.dat'))], 104)
    games = table_rows(m[B.join(('forzadb', 'cardb', 'gamecars.dat'))], 176)
    mrow, grow = bytearray(row_of(model, so)), bytearray(row_of(games, so))
    # the names: the car's own strings, taken from what <from> shows now
    loc = disc_file(disc, 'media', 'Loc')
    shown = {}
    for lang in sorted(os.listdir(loc)):
        p = disc_file(disc, 'media', 'Loc', lang, 'CarDataStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'CarDataStrings.str')
        cur = open(mp if os.path.exists(mp) else p, 'rb').read()
        e1, text, _, _ = read_strings(cur)
        ids = dict(e1[:-1])
        def text_of(i):
            o = ids[i] * 2
            e = o
            while text[e:e + 2] != b'\0\0': e += 2
            return text[o:e].decode('utf-16-le')
        nid, sid = struct.unpack_from('<HH', mrow, 12)
        shown[lang] = (p, mp, name or text_of(nid), short or name or text_of(sid))
    struct.pack_into('<I', mrow, 0, ordinal)
    if year: struct.pack_into('<I', mrow, 16, year)
    if make and re.search(r'<car name="%s"' % re.escape(make), xml, re.I):
        # the maker (and so the dealer and logo) of another car: carlist's Make and manufacturerid, model.dat's make id
        theirs = car_block(xml, make).group(0)
        for attr in ('Make', 'manufacturerid'):
            val = re.search(r'\b%s="([^"]*)"' % attr, theirs).group(1)
            xml = xml.replace(entry, re.sub(r'\b%s="[^"]*"' % attr, '%s="%s"' % (attr, val), entry))
            entry = re.sub(r'\b%s="[^"]*"' % attr, '%s="%s"' % (attr, val), entry)
        mrow[4:8] = row_of(model, ordinal_of(xml, make))[4:8]
    elif make:  # a maker by name, as make.dat has it (one addmake.py added): its id; no manufacturerid (0, as many cars)
        import addmake
        hit = [r for r in addmake.makes(m[B.join(('forzadb', 'cardb', 'make.dat'))]) if r[4].lower() == make.lower()]
        if not hit: raise SystemExit('--make %s: no car or maker of that name' % make)
        for attr, val in (('Make', hit[0][4]), ('manufacturerid', '0')):
            new_entry = re.sub(r'\b%s="[^"]*"' % attr, '%s="%s"' % (attr, val), entry)
            xml, entry = xml.replace(entry, new_entry), new_entry
        struct.pack_into('<I', mrow, 4, hit[0][0])
    if stats_like:  # the menus' figures and ratings of a similar car: gamecars.dat's summary, carlist's ratings and class
        so2 = ordinal_of(xml, stats_like)
        theirs = row_of(games, so2)
        grow[8:164] = theirs[8:164]
        g = car_block(xml, stats_like).group(0)
        for attr in ('BasePerformanceClass', 'Speed', 'Accel', 'Brake', 'Handl', 'Rare', 'carDriveType'):
            val = re.search(r'\b%s="([^"]*)"' % attr, g).group(1)
            new_entry = re.sub(r'\b%s="[^"]*"' % attr, '%s="%s"' % (attr, val), entry)
            xml, entry = xml.replace(entry, new_entry), new_entry
        mrow[32:72] = row_of(model, so2)[32:72]  # specs (the prices at 24 and 28 stay, see --price)
        mrow[80:92] = row_of(model, so2)[80:92]  # the spec screen's 0-60 mph and 0-100 mph (s) and top speed (m/s)
    if performance:  # those figures as the real car's: model.dat's 80-88, gamecars.dat's 48, 52 and 64
        t60, t100, vmax = performance
        struct.pack_into('<3f', mrow, 80, t60, t100, vmax / 3.6)
        struct.pack_into('<2f', grow, 48, t60, t100)
        struct.pack_into('<f', grow, 64, vmax / 3.6)
    if power:  # gamecars.dat's power figure: tenths of a kilowatt
        struct.pack_into('<f', grow, 12, power * 0.745699872 * 10)
    if price:  # model.dat's two prices (24, 28) and gamecars.dat's (88, 92)
        struct.pack_into('<II', mrow, 24, price, price)
        struct.pack_into('<II', grow, 88, price, price)
    struct.pack_into('<II', grow, 0, ordinal, ordinal)
    # Mega.ca2's wheel model, MegaXPR.ca2's textures, under the new car's name
    wsrc, wdst = B.join(('tires', 'art', wheel.lower())) + B, B.join(('tires', 'art', new.lower())) + B
    # copied only when the mods folder changed it (the S13's NFSU rim): a stock
    # wheel is shared, as cars share them on the disc, and Mega.ca2 has room
    # for few copies (its 3 streams of 4 MB)
    own_wheel = any(under(a.files, wsrc) != under(a.disc, wsrc) for a in (mega, xpr))
    nw = rename_tree(m, wsrc, wdst) + rename_tree(xpr.files, wsrc, wdst) if own_wheel else 0

    if restore:
        xml = xml.replace(car_block(xml, src).group(0), car_block(mega.disc[key].decode('latin-1'), src).group(0))
        dmodel = table_rows(mega.disc[B.join(('forzadb', 'cardb', 'model.dat'))], 104)
        dgames = table_rows(mega.disc[B.join(('forzadb', 'cardb', 'gamecars.dat'))], 176)
        model = table_rows(put_row(model, row_of(dmodel, so)), 104)
        games = table_rows(put_row(games, row_of(dgames, so)), 176)
        dw = re.search(r'<WheelStyle>\s*<P0 [^>]*File="([^"]*)"', cars.disc[B.join(('cars', src.lower(), 'tooldata.xml'))].decode('latin-1')).group(1)
        for arch in (mega, xpr):
            restore_tree(arch.files, arch.disc, B.join(('tires', 'art', dw.lower())) + B)
    m[key] = xml.encode('latin-1')
    # model.dat's string ids: set below, once the strings are written
    # Cars.ca2: the car's folder, its wheel named after it
    csrc, cdst = B.join(('cars', src.lower())) + B, B.join(('cars', new.lower())) + B
    nc = rename_tree(cars.files, csrc, cdst)
    tk = cdst + 'tooldata.xml'
    if own_wheel:
        cars.files[tk] = re.sub(rb'(<WheelStyle>\s*<P0 [^>]*File=")[^"]*"', lambda g: g.group(1) + new.encode() + b'"', cars.files[tk])
    if restore: restore_tree(cars.files, cars.disc, csrc)
    tool = cars.files[tk].decode('latin-1')
    audio = {}  # the engine's sound, for the car's cab (below)
    if engine_like:
        # Its own copy of another car's engine, physics and sound, as the only
        # engine in the shop; the power and torque scaled to the given figures
        # (the whole curve to the power, then up to the torque peak the rest,
        # the power peak as it was: a supercharger's flat torque).
        theirs = cars.files[B.join(('cars', engine_like.lower(), 'tooldata.xml'))].decode('latin-1')
        eng = re.search(r'<E0 [^>]*File="([^"]*)"', theirs).group(1)
        ename = engine or new
        ep_f, ep_s = B.join(('engines', eng.lower())) + B, B.join(('engines', ename.lower())) + B
        for k in [k for k in cars.files if k.lower().startswith(ep_f)]:
            cars.files[ep_s + k[len(ep_f):]] = cars.files[k]
        e0 = '<E0 Name="%s" File="%s" Price="0" />' % (name or new, ename)
        tool = re.sub(r'<Engines>.*?</Engines>', '<Engines>\n\t\t\t' + e0 + '\n\t\t</Engines>', tool, flags=re.S)
        import caridentity
        tun = [ep_s + B.join(('physics', 'enginetuning', 'l%d.xml' % lv)) for lv in range(4)]
        l0 = cars.files[tun[0]].decode('latin-1')
        hp0 = struct.unpack_from('<f', row_of(games, ordinal_of(xml, engine_like)), 12)[0] / 10 / 0.745699872
        k1 = power / hp0 if power else 1.0
        k2 = torque * 1.3558179 / (caridentity.peak_torque(l0) * k1) if torque else 1.0
        for t in tun:
            if t in cars.files:
                x = caridentity.raise_torque(cars.files[t].decode('latin-1'), k1, upto_power=False)
                cars.files[t] = caridentity.raise_torque(x, k2).encode('latin-1')
        print('engine %s: %s\'s (%s), %.0f hp x%.3f%s, torque to %.0f lb-ft (x%.3f below the power peak)'
              % (ename, engine_like, eng, hp0, k1, ' = %.0f hp' % power if power else '', caridentity.peak_torque(l0) * k1 * k2 / 1.3558179, k2))
        donor = disc_file(disc, 'media', 'cabs', 'car_%s.cab' % engine_like)
        dfiles, _ = cab_files(open(donor, 'rb').read())
        ea = B.join(('engines', eng.lower(), 'audio')) + B
        for k, v in dfiles.items():
            if not k.lower().startswith(ea): continue
            rest = re.sub(re.escape(eng.lower()), ename.lower(), k[len(ea):])
            if k.lower().endswith('.ini'): v = re.sub(re.escape(eng).encode(), ename.encode(), v, flags=re.I)
            audio[B.join(('engines', ename.lower(), 'audio')) + B + rest] = v
        print('engine sound: %d files from car_%s.cab' % (len(audio), engine_like))
    for spec in physics_like or ():  # <car>:<part>,<part>: those parts' physics (every level) from another car
        car, parts = spec.split(':')
        pp = B.join(('cars', car.lower(), 'physics')) + B
        for part in parts.split(','):
            src_p, dst_p = pp + part.lower() + B, cdst + B.join(('physics', part.lower())) + B
            got = under(cars.files, src_p)
            if not got: raise SystemExit('--physics-like %s: %s has no physics\\%s' % (spec, car, part))
            for k in list(under(cars.files, dst_p)): del cars.files[k]
            for k, v in got.items(): cars.files[dst_p + k[len(src_p):]] = v
            if part.lower() == 'drivetraindiff':  # and which wheels it drives: nonupgradedata's Drivetrain Type, carlist's carDriveType
                nk = cdst + B.join(('physics', 'nonupgradedata.xml'))
                dtype = re.search(rb'<Drivetrain Type="([^"]*)"', cars.files[pp + 'nonupgradedata.xml']).group(1)
                cars.files[nk] = re.sub(rb'(<Drivetrain Type=")[^"]*"', lambda g: g.group(1) + dtype + b'"', cars.files[nk])
                val = re.search(r'\bcarDriveType="([^"]*)"', car_block(xml, car).group(0)).group(1)
                new_entry = re.sub(r'\bcarDriveType="[^"]*"', 'carDriveType="%s"' % val, entry)
                xml, entry = xml.replace(entry, new_entry), new_entry
                m[key] = xml.encode('latin-1')
                mrow[52:56] = row_of(model, ordinal_of(xml, car))[52:56]  # the spec screen's drivetrain (drivetraintype.dat)
                print('drivetrain: %s (%s)' % (dtype.decode(), car))
            print('physics\\%s: %d files from %s' % (part.lower(), len(got), car))
    for spec in tooldata_like or ():  # <car>:<Section>,<Section>: tooldata's upgrade lists (stock level, prices, brake parts, tyre sizes) of another car
        car, secs = spec.split(':')
        theirs = cars.files[B.join(('cars', car.lower(), 'tooldata.xml'))].decode('latin-1')
        for sec in secs.split(','):
            pat = r'\t*<%s\b[^>]*>.*?</%s>' % (sec, sec)
            blk = re.search(pat, theirs, re.S)
            if not blk or not re.search(pat, tool, re.S): raise SystemExit('--tooldata-like %s: no <%s> in both' % (spec, sec))
            tool = re.sub(pat, lambda _: blk.group(0), tool, count=1, flags=re.S)
            print('tooldata <%s>: %s\'s' % (sec, car))
    if tires:  # every tyre level's sizes: "235/35R19,295/30R19", the front's and the rear's (the top level 10 mm wider)
        sizes = [re.fullmatch(r'(\d+)/(\d+)R(\d+)', s).groups() for s in tires.split(',')]
        def level(m_):
            body = m_.group(0)
            wider = 10 if m_.group(1) == '3' else 0
            for end, (w_, r_, d_) in zip(('Fronts', 'Rears'), sizes):
                body = re.sub(r'<%s [^>]*/>' % end, '<%s TireWidth="%d" TireRatio="%s" WheelDiameter="%s" />' % (end, int(w_) + wider, r_, d_), body)
            return body
        tire = re.search(r'<Tire\b.*?</Tire>', tool, re.S).group(0)
        tool = tool.replace(tire, re.sub(r'<L(\d)\b.*?</L\1>', level, tire, flags=re.S))
        print('tyres: %s' % tires)
    if final_drive:  # every gearbox level's final drive ratio scaled so the stock one is this (longer: a higher top speed)
        tl = [cdst + B.join(('physics', 'transmission', 'l%d.xml' % lv)) for lv in range(4)]
        k_ = final_drive / float(re.search(rb'FinalDriveRatio="([0-9.]+)"', cars.files[tl[0]]).group(1))
        for t in tl:
            if t in cars.files:
                cars.files[t] = re.sub(rb'FinalDriveRatio="([0-9.]+)"', lambda g: b'FinalDriveRatio="%.3f"' % (float(g.group(1)) * k_), cars.files[t])
        print('final drive: %.2f (x%.3f at every level)' % (final_drive, k_))
    if mass:  # the stock weight, kg, and the lighter upgrade levels by as much
        wl = [cdst + B.join(('physics', 'weight', 'l%d.xml' % lv)) for lv in range(4)]
        old = float(re.search(rb' Mass="([0-9.]+)"', cars.files[wl[0]]).group(1))
        for wk in wl:
            if wk in cars.files:
                cars.files[wk] = re.sub(rb' Mass="([0-9.]+)"', lambda g: b' Mass="%.3f"' % (float(g.group(1)) * mass / old), cars.files[wk])
        print('weight: %.1f kg -> %.1f kg (every level x%.3f)' % (old, mass, mass / old))
    if cab:  # the driver and mirror view as much lower (or higher) as the new roof is than <from>'s: the driver's head stuck out of the Gallardo's roof
        import carbin
        def roof_and_length(blob):
            parts = carbin.read(blob)['parts']
            body = [v for p in parts if p['name'] == 'body_LOD1' for v in p['verts']]
            return max(v[1] for v in body) / 4096, (max(v[2] for v in body) - min(v[2] for v in body)) / 4096
        def carbin_of(path):
            fs, _ = cab_files(open(path, 'rb').read())
            return next(v for k, v in fs.items() if k.lower().endswith('car.carbin'))
        theirs_cab = disc_file(disc, 'media', 'cabs', 'car_%s.cab' % src)
        (r0, len0), (r1, _) = roof_and_length(carbin_of(theirs_cab)), roof_and_length(carbin_of(cab))
        md = cars.files[cdst + B.join(('physics', 'maxdata.xml'))].decode('latin-1')
        bb = re.search(r'MinZ="([-0-9.]+)"[^>]*MaxZ="([-0-9.]+)"', md)
        dy = (r1 - r0) * (float(bb.group(2)) - float(bb.group(1))) / len0  # carbin units to metres, by the body's length
        nk = cdst + 'nontooldata.xml'
        nt = cars.files[nk].decode('latin-1')
        for tag in ('DriverPosition', 'RearViewPosition'):
            nt = re.sub(r'(<%s\b[^>]*\by=")([-+0-9.]+)"' % tag, lambda g: '%s%.2f"' % (g.group(1), float(g.group(2)) + dy), nt)
        cars.files[nk] = nt.encode('latin-1')
        print('driver: %+.2f m (the roof %+.2f carbin units)' % (dy, r1 - r0))
    if upgrades:  # the shop's body parts (nfsu2forza.py's upgrades.xml for a Most Wanted car)
        u = open(upgrades).read()
        for tag in ('FrontBumper', 'RearBumper', 'SideSkirt', 'Hood', 'Wing'):
            mine_blk = re.search(r'\t*<%s>.*?</%s>\n?' % (tag, tag), u, re.S)
            if mine_blk: tool = re.sub(r'\t*<%s>.*?</%s>\n?' % (tag, tag), lambda _: mine_blk.group(0), tool, count=1, flags=re.S)
        print('shop: front bumpers, rear bumpers, skirts, hoods and wings from %s' % upgrades)
    cars.files[tk] = tool.encode('latin-1')

    # the strings, in every language: the same ids in each
    new_ids, strings = None, {}
    for lang, (p, mp, n, s) in shown.items():
        base = open(p if restore else (mp if os.path.exists(mp) else p), 'rb').read()
        ids = string_ids(base)
        want = [('IDS_Model_%d_Name' % ordinal, n), ('IDS_Model_%d_ShortName' % ordinal, s)]
        if any(k in ids for k, _ in want): raise SystemExit('%s: strings for ordinal %d are there already' % (lang, ordinal))
        out = write_strings(base, want)
        got = string_ids(out)
        these = (got[want[0][0]], got[want[1][0]])
        if new_ids not in (None, these): raise SystemExit('%s: the new string ids differ between languages' % lang)
        new_ids = these
        strings[mp] = out  # written with the archives, at the end
    struct.pack_into('<HH', mrow, 12, *new_ids)
    m[B.join(('forzadb', 'cardb', 'model.dat'))] = put_row(model, bytes(mrow))
    m[B.join(('forzadb', 'cardb', 'gamecars.dat'))] = put_row(games, bytes(grow))
    en = shown.get('en') or next(iter(shown.values()))
    print('carlist: %s, ordinal %d, a copy of %s (ordinal %d), shown as "%s" ("%s"), string ids %d, %d'
          % (new, ordinal, src, so, en[2], en[3], *new_ids))
    print('wheel: tires\\art\\%s (%d files) from %s' % (new.lower(), nw, wheel) if own_wheel else "wheel: %s's, shared" % wheel)
    print('cars.cab: %d files under cars\\%s' % (nc, new.lower()))
    for a in (mega, cars, xpr): a.check()
    for a in (mega, cars, xpr): a.write()
    for mp, out in strings.items():
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(out)

    # the car's cab
    cab_out = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % new)
    mine = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % src)
    cab_in = cab or (mine if os.path.exists(mine) else disc_file(disc, 'media', 'cabs', 'car_%s.cab' % src))
    files, root = cab_files(open(cab_in, 'rb').read())
    out = {}
    for k, v in files.items():
        out[cdst + k[len(csrc):] if k.lower().startswith(csrc) else k] = v
    out.update(audio)
    os.makedirs(os.path.dirname(cab_out), exist_ok=True)
    open(cab_out, 'wb').write(forzacab.pack(out, root))
    print('car_%s.cab: %d files from %s' % (new, len(out), cab_in))
    # the paint shop's liveries, if it has some
    lv = disc_file(disc, 'media', 'cars', '%s.liveries.bin' % src)
    mlv = os.path.join(mods, 'media', 'cars', '%s.liveries.bin' % src)
    if os.path.exists(mlv): lv = mlv
    if liveries: lv = liveries  # a converted car's own (nfsu2forza.py --liveries)
    if lv:
        os.makedirs(os.path.join(mods, 'media', 'cars'), exist_ok=True)
        open(os.path.join(mods, 'media', 'cars', '%s.liveries.bin' % new), 'wb').write(open(lv, 'rb').read())
        print('media/cars/%s.liveries.bin from %s' % (new, lv))
    # the car-select icon: <from>'s tile at the new ordinal
    def pack_path(o, mods_first=True):
        n = 'caricons%d.xpr' % (o // 64 + 1)
        mp = os.path.join(mods, 'media', n)
        return mp if mods_first and os.path.exists(mp) else disc_file(disc, 'media', n), mp
    import forzaxpr
    sp, _ = pack_path(so)
    tile = bytes(icon_tile(open(sp, 'rb').read(), so))
    dp, dmp = pack_path(ordinal)
    d = bytearray(open(dp, 'rb').read())
    set_tile(d, ordinal, tile)
    if restore and (so // 64 == ordinal // 64):
        set_tile(d, so, icon_tile(open(pack_path(so, False)[0], 'rb').read(), so))
    open(dmp, 'wb').write(bytes(d))
    if restore and so // 64 != ordinal // 64:
        sd = bytearray(open(pack_path(so)[0], 'rb').read())
        set_tile(sd, so, icon_tile(open(pack_path(so, False)[0], 'rb').read(), so))
        open(pack_path(so)[1], 'wb').write(bytes(sd))
    print('icon: caricons%d.xpr tile %d from caricons%d.xpr tile %d' % (ordinal // 64 + 1, ordinal % 64, so // 64 + 1, so % 64))
    if restore:
        if os.path.exists(mine):
            os.replace(mine, mine + '.replaced')
            print('%s -> car_%s.cab.replaced (the disc\'s is read again)' % (mine, src))
        print('%s: back to the disc\'s files' % src)


def icon_tile(pack, ordinal):
    import forzaxpr
    t = forzaxpr.textures(bytearray(pack))[0]
    assert (t['w'], t['h'], t['format']) == (128, 4096, 0x0F), t
    o = t['start'] + (ordinal % 64) * TILE
    return pack[o:o + TILE]


def set_tile(pack, ordinal, tile):
    import forzaxpr
    t = forzaxpr.textures(pack)[0]
    o = t['start'] + (ordinal % 64) * TILE
    pack[o:o + TILE] = tile


if __name__ == '__main__':
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a in ('--ordinal', '--name', '--short', '--cab', '--make', '--year', '--engine-like', '--engine', '--power', '--torque',
                 '--mass', '--stats-like', '--price', '--upgrades', '--liveries'): opts[a[2:].replace('-', '_')] = next(it)
        elif a in ('--physics-like', '--tooldata-like'): opts.setdefault(a[2:].replace('-', '_'), []).append(next(it))
        elif a in ('--tires', '--final-drive', '--performance'): opts[a[2:].replace('-', '_')] = next(it)
        elif a == '--restore': opts['restore'] = True
        else: args.append(a)
    if len(args) != 4: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(args[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % args[1])
    main(*args, ordinal=int(opts['ordinal']) if 'ordinal' in opts else None, name=opts.get('name'), short=opts.get('short'),
         cab=opts.get('cab'), make=opts.get('make'), year=int(opts['year']) if 'year' in opts else None,
         engine_like=opts.get('engine_like'), engine=opts.get('engine'), power=float(opts['power']) if 'power' in opts else None,
         torque=float(opts['torque']) if 'torque' in opts else None, mass=float(opts['mass']) if 'mass' in opts else None,
         stats_like=opts.get('stats_like'), price=int(opts['price']) if 'price' in opts else None, upgrades=opts.get('upgrades'), liveries=opts.get('liveries'),
         physics_like=opts.get('physics_like'), tooldata_like=opts.get('tooldata_like'), tires=opts.get('tires'),
         final_drive=float(opts['final_drive']) if 'final_drive' in opts else None,
         performance=tuple(float(x) for x in opts['performance'].split(',')) if 'performance' in opts else None,
         restore=opts.get('restore', False))
