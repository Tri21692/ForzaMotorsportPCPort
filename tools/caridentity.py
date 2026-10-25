"""Give one of Forza's cars another car's identity: its name, maker (and so
the maker's logo), ratings, physics and engine (power and recorded sound).
Used to make the Civic SI slot, which carries the converted NFSU 240SX body,
into Forza's own Nissan 240SX SE (that car is not offered in the game).

  python tools/caridentity.py <disc folder> <mods folder> <slot> <from>
  e.g.  <disc>  run/mods  CivicSI  Nissan240SX --name 240SX --year 1991 --mass 1200
  [--name <model name>] [--year <year>] [--mass <kg>]: overrides, as for an
  earlier version of the other car; [--icon <128x64 image>]: the car-select
  thumbnail (media/caricons<n>.xpr); [--price <credits>];
  [--engine <name> [--torque <lb-ft>]]: the slot gets its own copy of the
  engine under that name (physics and sound), so the other car's is not
  changed, with its peak torque set (power peak kept)

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

Never writes the saves (hdd/Partition1, UDATA): the game keeps copies of
the icon packs in each profile (CarIcons1-5.xpr), signed (CarIcons.sig),
and deletes a profile whose files do not match their signature. Patching
those copies cost a user their profiles on 25 Oct. Only the mods folder's
copy of the disc's pack is written.
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


def read_rgba(path):
    """An image as RGBA (h, w, 4), read with ffmpeg (XBRT_FFMPEG or the PATH)."""
    import subprocess
    import numpy as np
    ff = os.environ.get('XBRT_FFMPEG') or 'ffmpeg'
    fp = os.path.join(os.path.dirname(ff), os.path.basename(ff).replace('ffmpeg', 'ffprobe'))
    w, h = (int(x) for x in subprocess.run([fp, '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path],
                                           capture_output=True, text=True, check=True).stdout.split()[0].split(','))
    raw = subprocess.run([ff, '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw[:w * h * 4], np.uint8).reshape(h, w, 4)


def set_icon(pack_path, out_path, ordinal, image):
    """The car-select thumbnail: media/caricons<n>.xpr holds 64 of them, 128x64
    DXT5 tiles stacked in one 128x4096 texture, car <ordinal> in pack
    ordinal // 64 + 1 at tile ordinal % 64. The game copies the packs into
    each profile's save (CarIcons1-5.xpr, signed) and draws those: refuses
    to write anything under a save folder."""
    import numpy as np
    import forzaxpr as fx
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.normpath(os.path.abspath(out_path)).split(os.sep)):
        raise SystemExit('%s: a save; the game deletes profiles whose signed files change' % out_path)
    d = bytearray(open(pack_path, 'rb').read())
    t = fx.textures(d)[0]
    assert (t['w'], t['h'], t['format']) == (128, 4096, 0x0F), t
    img = np.ascontiguousarray(image[:64, :128])
    blocks = fx.encode_dxt5(img)
    o = t['start'] + (ordinal % 64) * 16 * (128 // 4) * 16  # 16 block rows a tile, 32 blocks a row, 16 bytes a block
    d[o:o + len(blocks)] = blocks
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, 'wb').write(bytes(d))


def raise_torque(xml, k, upto_power=True):
    """An enginetuning level with its full-throttle torque curve raised by k
    up to the torque peak, easing back to the stock curve at the power peak
    (so the peak power stays as it was)."""
    m = re.search(r'<FullThrottle([^>]*)>', xml)
    attrs = m.group(1)
    vals = {int(i): float(v) for i, v in re.findall(r' v(\d+)="([^"]*)"', attrs)}
    n = max(vals) + 1
    pt = max(range(n), key=lambda i: vals[i])
    pp = max(range(n), key=lambda i: vals[i] * i)
    def f(i):
        if i <= pt or not upto_power: return k
        if i >= pp: return 1.0
        return k + (1.0 - k) * (i - pt) / (pp - pt)
    new = re.sub(r' v(\d+)="([^"]*)"', lambda g: ' v%s="%.6g"' % (g.group(1), float(g.group(2)) * f(int(g.group(1)))), attrs)
    return xml[:m.start(1)] + new + xml[m.end(1):]


def peak_torque(xml):
    m = re.search(r'<FullThrottle([^>]*)>', xml)
    a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    return float(a['TorqueScale']) * max(float(v) for k, v in a.items() if re.fullmatch(r'v\d+', k))


def main(disc, mods, slot, src, name=None, year=None, mass=None, icon=None, price=None, engine=None, torque=None):
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
    # Kept from the slot too: model.dat 72-80 (the unlock text's string ids)
    # and 92-100 (flags: ff 01 01 01, 3 on a car on sale from the start; a
    # career prize, as Forza's 240SX, has zeros), gamecars.dat 164-176 (ids).
    for table, size, keep in (('model.dat', 104, ((0, 4), (12, 16), (72, 80), (92, 100))),
                              ('gamecars.dat', 176, ((0, 8), (164, 176)))):
        k = B.join(('forzadb', 'cardb', table))
        t = bytearray(files[k])
        rows = {struct.unpack_from('<I', t, r * size)[0]: r for r in range(len(t) // size)}
        a, b = rows[so] * size, rows[fo] * size
        new = bytearray(t[b:b + size])
        for x0, x1 in keep: new[x0:x1] = t[a + x0:a + x1]
        if table == 'model.dat' and year: struct.pack_into('<I', new, 16, year)
        if price:  # two prices (model.dat 24, 28; gamecars.dat 88, 92): the higher one to `price`, the other in proportion
            at = 24 if table == 'model.dat' else 88
            lo, hi = struct.unpack_from('<II', new, at)
            struct.pack_into('<II', new, at, int(round(lo * price / hi / 100)) * 100 if hi else price, price)
        t[a:a + size] = new
        files[k] = bytes(t)
    print('forzadb: %s takes the maker, %sspecs and ratings of %s' % (slot, 'year %d, ' % year if year else 'year, ', src))
    out = os.path.join(mods, 'hdd', 'Partition4', 'mega.cab')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    blob = forzacab.pack(files, root)
    open(out, 'wb').write(blob)
    print('carlist: %s is now "%s" (%s)' % (slot, theirs['displayName'], theirs['Make']))
    if icon:
        so = int(car_attrs(xml, slot)[1]['Ordinal'])
        pack = 'caricons%d.xpr' % (so // 64 + 1)
        mine_pack = os.path.join(mods, 'media', pack)
        set_icon(mine_pack if os.path.exists(mine_pack) else os.path.join(disc, 'media', pack), mine_pack, so, read_rgba(icon))
        print('icon: %s tile %d (profiles made before this keep their own signed copy, with the old icon)' % (pack, so % 64))
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
    src_engine = re.search(r'<E0 [^>]*File="([^"]*)"', tool_s).group(1)
    if engine:  # the slot's own copy of the engine (Forza's other car keeps the stock one)
        ep_f, ep_s = B.join(('engines', src_engine.lower())) + B, B.join(('engines', engine.lower())) + B
        for k in [k for k in files if k.lower().startswith(ep_f)]:
            files[ep_s + k[len(ep_f):]] = files[k]
        tool_s = re.sub(r'(<E0 [^>]*File=")[^"]*(")', lambda g: g.group(1) + engine + g.group(2), tool_s, count=1)
        files[pre_s + 'tooldata.xml'] = tool_s.encode('latin-1')
        if torque:
            l0 = files[ep_s + B.join(('physics', 'enginetuning', 'l0.xml'))].decode('latin-1')
            k = torque * 1.3558179 / peak_torque(l0)
            for lv in range(4):
                tk = ep_s + B.join(('physics', 'enginetuning', 'l%d.xml' % lv))
                if tk in files: files[tk] = raise_torque(files[tk].decode('latin-1'), k).encode('latin-1')
            print('engine %s: stock torque %.0f -> %.0f lb-ft (x%.3f to the torque peak, the power peak as it was)'
                  % (engine, peak_torque(l0) / 1.3558179, torque, k))
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
    eng = B.join(('engines', src_engine.lower())) + B
    added = [k for k in other if k.lower().startswith(eng)]
    for k in added:
        if engine:  # under the slot's engine name, the wave bank paths inside too
            data = re.sub(re.escape(src_engine).encode(), engine.encode(), other[k], flags=re.I) if k.lower().endswith('.ini') else other[k]
            rest = re.sub(re.escape(src_engine.lower()), engine.lower(), k[len(eng):])  # Nissan240SX.xwb too
            files[B.join(('engines', engine.lower())) + B + rest] = data
        else:
            files[k] = other[k]
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
        if a in ('--name', '--year', '--mass', '--icon', '--price', '--engine', '--torque'): opts[a[2:]] = next(it)
        else: args.append(a)
    if len(args) != 4:
        raise SystemExit(__doc__)
    main(*args, name=opts.get('name'), year=int(opts['year']) if 'year' in opts else None,
         mass=float(opts['mass']) if 'mass' in opts else None, icon=opts.get('icon'),
         price=int(opts['price']) if 'price' in opts else None, engine=opts.get('engine'),
         torque=float(opts['torque']) if 'torque' in opts else None)
