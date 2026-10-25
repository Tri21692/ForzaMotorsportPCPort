"""Give one of Forza's cars another car's identity: its name, maker (and so
the maker's logo), ratings, physics and engine (power and recorded sound).
Used to make the Civic SI slot, which carries the converted NFSU 240SX body,
into Forza's own Nissan 240SX SE (that car is not offered in the game).

  python tools/caridentity.py <disc folder> <mods folder> <slot> <from>
  e.g.  <disc>  run/mods  CivicSI  Nissan240SX --name 240SX --year 1991 --mass 1200
  [--name <model name>] [--year <year>] [--mass <kg>]: overrides, as for an
  earlier version of the other car

Writes into the mods folder (read instead of the game's files, see
runtime/file.c), starting from what is already there:

  hdd/Partition4/mega.cab   cars\\carlist.xml: the slot's entry takes the other's
                            displayName, shortName, Make, carDriveType,
                            manufacturerid, BasePerformanceClass and ratings
  hdd/Partition4/cars.cab   cars\\<slot>\\tooldata.xml: the price, engines and tyres;
                            cars\\<slot>\\physics\\* and config.ini: the other's.
                            The slot's cameras, driver position and body parts
                            stay (nontooldata.xml, the parts lists).
  media/cabs/car_<slot>.cab engines\\<from>\\audio\\*: the other's engine sound
  media/Loc/*/CarDataStrings.str
                            the slot's engine name (shown as the car's model)
                            becomes the other's, in place

The game's own data only: nothing here comes from another game.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forzacab

B = '\\'
CARLIST_FIELDS = ('displayName', 'shortName', 'Make', 'carDriveType', 'manufacturerid', 'BasePerformanceClass',
                  'Speed', 'Accel', 'Brake', 'Handl', 'Rare')


def entries(path):
    if path.lower().endswith('.ca2'):  # a whole cab, zlib-compressed (what the game installs to the cache)
        import tempfile, zlib
        data, raw = open(path, 'rb').read(), b''
        while data:  # zlib streams of 4 MB each, zero-padded between
            z = zlib.decompressobj()
            raw += z.decompress(data)
            data = z.unused_data.lstrip(b'\0')
            if not z.eof: break
        with tempfile.NamedTemporaryFile(suffix='.cab', delete=False) as f: f.write(raw)
        try: return entries(f.name)
        finally: os.remove(f.name)
    d, ver, es = forzacab.read(path)
    return {e['name']: forzacab.data(d, e) for e in es}, (es[0]['root'] if es else '')


def source(mods, disc, cache, ca2):
    """The mods folder's copy of a cache archive if there is one, else the
    disc's (the copy in the cache is rebuilt by the game at every boot)."""
    p = os.path.join(mods, 'hdd', 'Partition4', cache)
    return p if os.path.exists(p) else os.path.join(disc, 'media', 'cabs', ca2)


def car_attrs(xml, name):
    m = re.search(r'<car name="%s"[^>]*>' % re.escape(name), xml, re.I)
    if not m: raise SystemExit('carlist.xml: no car %s' % name)
    return m, dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))


def block(xml, tag):
    m = re.search(r'<%s\b.*?</%s>' % (tag, tag), xml, re.S)
    return m


def main(disc, mods, slot, src, name=None, year=None, mass=None):
    ls, lf = slot.lower(), src.lower()
    # mega.cab: the car list
    files, root = entries(source(mods, disc, 'mega.cab', 'Mega.ca2'))
    key = B.join(('cars', 'carlist.xml'))
    xml = files[key].decode('latin-1')
    _, theirs = car_attrs(xml, src)
    m, _ = car_attrs(xml, slot)
    tag = m.group(0)
    for f in CARLIST_FIELDS:
        tag = re.sub(r'\b%s="[^"]*"' % f, '%s="%s"' % (f, theirs[f]), tag)
    xml = xml[:m.start()] + tag + xml[m.end():]
    files[key] = xml.encode('latin-1')
    # forzadb\cardb: one row per car, by its Ordinal. model.dat (104 bytes):
    # u32 ordinal, u32 make (make.dat), u32, u16 u16 string ids, u32 year,
    # prices, specs. gamecars.dat (176 bytes): u32 ordinal twice, the
    # physics summary and at 124 the ratings the menu shows (speed, accel,
    # brake, corner, then rarity). The slot's row takes the other's, keeping
    # its ordinal and (model.dat) its string ids.
    so, fo = int(car_attrs(xml, slot)[1]['Ordinal']), int(theirs['Ordinal'])
    for table, size, keep in (('model.dat', 104, ((0, 4), (12, 16))), ('gamecars.dat', 176, ((0, 8),))):
        k = B.join(('forzadb', 'cardb', table))
        t = bytearray(files[k])
        rows = {struct.unpack_from('<I', t, r * size)[0]: r for r in range(len(t) // size)}
        a, b = rows[so] * size, rows[fo] * size
        new = bytearray(t[b:b + size])
        for x0, x1 in keep: new[x0:x1] = t[a + x0:a + x1]
        if table == 'model.dat' and year: struct.pack_into('<I', new, 16, year)
        t[a:a + size] = new
        files[k] = bytes(t)
    print('forzadb: %s takes the maker, %sspecs and ratings of %s' % (slot, 'year %d, ' % year if year else 'year, ', src))
    out = os.path.join(mods, 'hdd', 'Partition4', 'mega.cab')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    blob = forzacab.pack(files, root)
    open(out, 'wb').write(blob)
    print('carlist: %s is now "%s" (%s)' % (slot, theirs['displayName'], theirs['Make']))
    # cars.cab: tooldata, physics, config
    files, root = entries(source(mods, disc, 'cars.cab', 'Cars.ca2'))
    pre_s, pre_f = B.join(('cars', ls)) + B, B.join(('cars', lf)) + B
    tool_s, tool_f = files[pre_s + 'tooldata.xml'].decode('latin-1'), files[pre_f + 'tooldata.xml'].decode('latin-1')
    mine = re.search(r'<E0 Name="([^"]*)"', tool_s).group(1)  # the slot's model name, before it changes
    for tag in ('Misc', 'Engines', 'Tire', 'Weight'):
        a, b = (block(tool_s, tag) if tag != 'Misc' else re.search(r'<Misc[^>]*/>', tool_s)), \
               (block(tool_f, tag) if tag != 'Misc' else re.search(r'<Misc[^>]*/>', tool_f))
        if a and b: tool_s = tool_s[:a.start()] + b.group(0) + tool_s[a.end():]
    files[pre_s + 'tooldata.xml'] = tool_s.encode('latin-1')
    n = 0
    for f in [k for k in files if k.lower().startswith(pre_f.lower() + 'physics' + B) or k.lower() == (pre_f + 'config.ini').lower()]:
        files[pre_s + f[len(pre_f):]] = files[f]
        n += 1
    if mass:  # the stock (l0) weight, as kg
        wk = pre_s + B.join(('physics', 'weight', 'l0.xml'))
        w = files[wk].decode('latin-1')
        old = re.search(r' Mass="([0-9.]+)"', w)
        if old:
            files[wk] = (w[:old.start(1)] + '%.3f' % mass + w[old.end(1):]).encode('latin-1')
            print('weight: %s kg -> %.1f kg' % (old.group(1), mass))
    out = os.path.join(mods, 'hdd', 'Partition4', 'cars.cab')
    open(out, 'wb').write(forzacab.pack(files, root))
    print('cars.cab: tooldata (price, engines, tyres, weight) and %d physics files from %s' % (n, src))
    # the car's cab: the other engine's sound
    car_in = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % slot)
    if not os.path.exists(car_in): car_in = os.path.join(disc, 'media', 'cabs', 'car_%s.cab' % slot)
    files, root = entries(car_in)
    theirs_cab = next(os.path.join(disc, 'media', 'cabs', f) for f in os.listdir(os.path.join(disc, 'media', 'cabs'))
                      if f.lower() == ('car_%s.cab' % src).lower())
    other, _ = entries(theirs_cab)
    eng = B.join(('engines', lf)) + B
    added = [k for k in other if k.lower().startswith(eng)]
    for k in added: files[k] = other[k]
    out = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % slot)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(forzacab.pack(files, root))
    print('car_%s.cab: %d engine sound files from %s' % (slot, len(added), src))
    # the shown model name: the slot's engine name (tooldata E0) in CarDataStrings.str, in place
    new = name or re.search(r'<E0 Name="([^"]*)"', tool_f).group(1)
    loc = os.path.join(disc, 'media', 'Loc')
    for lang in os.listdir(loc):
        p = os.path.join(loc, lang, 'CarDataStrings.str')
        if not os.path.exists(p): continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'CarDataStrings.str')
        d = bytearray(open(mp if os.path.exists(mp) else p, 'rb').read())
        a, b = (mine + '\0').encode('utf-16-le'), new.encode('utf-16-le')
        if mine == new: continue
        if len(b) > len(a) - 2: raise SystemExit('%s: "%s" is longer than "%s"' % (lang, new, mine))
        hits = 0
        i = d.find(a)
        while i >= 0:
            d[i:i + len(a)] = b + bytes(len(a) - len(b))
            hits += 1
            i = d.find(a, i + len(a))
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(bytes(d))
        print('%s CarDataStrings.str: "%s" -> "%s" (%d)' % (lang, mine, new, hits))


if __name__ == '__main__':
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a in ('--name', '--year', '--mass'): opts[a[2:]] = next(it)
        else: args.append(a)
    if len(args) != 4:
        raise SystemExit(__doc__)
    main(*args, name=opts.get('name'), year=int(opts['year']) if 'year' in opts else None,
         mass=float(opts['mass']) if 'mass' in opts else None)
