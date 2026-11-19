"""Each add-on car geared to its real top speed (the user's, 6 Nov: "7th gear is there, but not the actual top speeds
of the cars, mainly the Chiron"): the speed at the redline in top gear (the engine's RedlineRPM, the stock rear
tyre's rolling radius, the stock gearbox's top gear and final drive) set to 1.04 x the real top speed by the final
drive, every transmission level scaled alike. Whether the car gets there is its power against its drag; this only
stops the gearing from capping it.   python topspeed.py [--dry]"""
import sys, re, math, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar
B = chr(92)
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = r'E:\Forza Motorsport Remastered\run\mods_track'
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
MARGIN = 1.04


def main(dry):
    cars = addcar.Archive(DISC, MODS, 'Cars.ca2')
    lk = {k.lower(): k for k in cars.files}
    get = lambda *p: bytes(cars.files[lk[B.join(p).lower()]]).decode('latin-1')
    for key, v in nc.CARS.items():
        name, vmax = nc.NAME[key], v[12][2]
        td = get('cars', name, 'tooldata.xml')
        eng = re.search(r'<E0 [^>]*File="([^"]*)"', td).group(1)
        rpm = float(re.search(r'RedlineRPM="([^"]+)"', get('engines', eng, 'physics', 'enginetuning', 'l0.xml')).group(1))
        lvl = int(re.search(r'<Tire StockLevel="(\d+)"', td).group(1))
        blk = re.search(r'<Tire StockLevel.*?<L%d[^>]*>(.*?)</L%d>' % (lvl, lvl), td, re.S).group(1)
        a = dict(re.findall(r'(\w+)="([^"]+)"', re.search(r'<Rears ([^>]*)/>', blk).group(1)))
        radius = (float(a['WheelDiameter']) * 25.4 + 2 * float(a['TireWidth']) * float(a['TireRatio']) / 100) / 2000
        gsl = int(re.search(r'<Transmission StockLevel="(\d+)"', td).group(1)) if re.search(r'<Transmission StockLevel="(\d+)"', td) else 0
        files = {lv: get('cars', name, 'physics', 'transmission', 'l%d.xml' % lv) for lv in range(4) if B.join(('cars', name, 'physics', 'transmission', 'l%d.xml' % lv)).lower() in lk}
        x = files[gsl] if gsl in files else files[0]
        fd = float(re.search(r'FinalDriveRatio="([^"]+)"', x).group(1))
        g = [float(r) for i, r in re.findall(r'v(\d+)="([^"]+)"', re.search(r'<GearRatios([^>]*)/>', x).group(1)) if int(i) > 0 and float(r) > 0]
        top = g[-1]
        v_now = rpm / 60 * 2 * math.pi * radius / (top * fd) * 3.6
        fd_new = rpm / 60 * 2 * math.pi * radius / (top * vmax * MARGIN / 3.6)
        k = fd_new / fd
        print('%-28s redline %5.0f rpm  tyre r %.3f m  top gear %.2f x fd %.2f: %3.0f km/h at the redline, real %3.0f -> fd %.2f (x%.2f)' % (name, rpm, radius, top, fd, v_now, vmax, fd_new, k))
        if dry: continue
        for lv, t in files.items():
            f0 = float(re.search(r'FinalDriveRatio="([^"]+)"', t).group(1))
            t2 = re.sub(r'FinalDriveRatio="[^"]+"', 'FinalDriveRatio="%.4f"' % (f0 * k), t)
            cars.files[lk[B.join(('cars', name, 'physics', 'transmission', 'l%d.xml' % lv)).lower()]] = t2.encode('latin-1')
    if dry: raise SystemExit('dry run: nothing written')
    cars.check(); cars.write()
    print('written')


if __name__ == '__main__':
    main('--dry' in sys.argv)
