"""A 7th gear for the add-on cars whose real gearboxes have 7 or more (the user's, 6 Nov: "7th and 8th gears for the
class F cars or any other car that needs it"). forza.exe reads GearRatios v0..v7 into a fixed array of 8
(0xEC2E0: reverse and up to 7 forward, -1 for none), so 7 is the most there is; the disc's Chrysler ME412 has 7.
Every transmission level (l0-l3, the shop's upgrades): its 1st and its top gear kept, 7 forward gears spaced
evenly (geometric) between them, so the top speed stays and the steps are closer; gamecars.dat's gear count 7.
Cars.ca2 and Mega.ca2 in the mods folder.   python gears7.py [--dry]"""
import sys, re, struct, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = r'E:\Forza Motorsport Remastered\run\mods_track'
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
SEVEN = ['chiron', 'jesko', 'senna', 'huayra', 'terzo', 'svj', 'huracan', 'f8', 'gt2rs', 'zr1', 'fordgt17', 'm2', 'rs5']


def seven(xml):
    m = re.search(r'<GearRatios([^>]*)/>', xml)
    v = {int(i): float(r) for i, r in re.findall(r'v(\d+)="([^"]+)"', m.group(1))}
    fwd = [v[i] for i in sorted(v) if i > 0 and v[i] > 0]
    if len(fwd) >= 7: return xml, fwd, fwd
    g1, gt = fwd[0], fwd[-1]
    new = [g1 * (gt / g1) ** (k / 6) for k in range(7)]
    attrs = ' v0="%s" ' % m.group(1).split('v0="')[1].split('"')[0] + ' '.join('v%d="%.4f"' % (i + 1, r) for i, r in enumerate(new))
    return xml[:m.start()] + '<GearRatios%s/>' % attrs + xml[m.end():], fwd, new


def main(dry):
    cars = addcar.Archive(DISC, MODS, 'Cars.ca2')
    mega = addcar.Archive(DISC, MODS, 'Mega.ca2')
    gk = B.join(('forzadb', 'cardb', 'gamecars.dat'))
    games = addcar.table_rows(mega.files[gk], 176)
    lk = {k.lower(): k for k in cars.files}
    for key in SEVEN:
        name = nc.NAME[key]
        for lv in range(4):
            k = lk.get(B.join(('cars', name, 'physics', 'transmission', 'l%d.xml' % lv)).lower())
            if not k: continue
            xml = bytes(cars.files[k]).decode('latin-1')
            out, old, new = seven(xml)
            if out != xml: cars.files[k] = out.encode('latin-1')
            if lv == 0: print('%-28s l0 %d -> %d gears: %s' % (name, len(old), len(new), ' '.join('%.2f' % r for r in new)))
        o = nc.ORD[key]
        g = bytearray(addcar.row_of(games, o))
        struct.pack_into('<I', g, 32, 7)  # (the menus' gear count, an integer: the Enzo's 6)
        games = addcar.table_rows(addcar.put_row(games, bytes(g)), 176)
    if dry: raise SystemExit('dry run: nothing written')
    mega.files[gk] = b''.join(games)
    for a in (cars, mega): a.check()
    for a in (cars, mega): a.write()
    print('written')


if __name__ == '__main__':
    main('--dry' in sys.argv)
