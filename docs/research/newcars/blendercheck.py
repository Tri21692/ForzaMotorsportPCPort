"""Each new car as installed (its cab in run/mods_track): car.carbin and atlas extracted, drawn lit in Blender
(tools/carlit.py) from six sides with the wheels at the game's hubs, plus a back-face pass (BACKRED), into one sheet
a car: E:\\xbrt_scr\\newcars\\check\\<key>.png.   python blendercheck.py [keys]"""
import sys, os, subprocess, importlib.util
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import forzacab, forzaxpr, carbin
import tyrecheck
from PIL import Image, ImageDraw
G, MODS, BLENDER = tyrecheck.G, tyrecheck.MODS, tyrecheck.BLENDER
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
FRESH = os.environ.get('FRESH')
OUT = os.path.join(W, 'check_fresh' if FRESH else 'check')
VIEWS = 'front,rear,left,fside,rtop,cabin'


def one(k):
    name = nc.NAME[k]
    od = os.path.join(OUT, k); os.makedirs(od, exist_ok=True)
    if FRESH:  # the conversion in out/, before it is installed
        import shutil
        shutil.copy(os.path.join(W, 'out', k, 'car.carbin'), od)
        shutil.copy(os.path.join(W, 'out', k, 'liveries', 'standard', 'livery0hi.xpr'), od)
    else:
        d, ver, es = forzacab.read(os.path.join(MODS, 'media', 'cabs', 'car_%s.cab' % name))
        for e in es:
            low = e['name'].lower()
            if low.endswith('car.carbin') or low.endswith('livery0hi.xpr'):
                open(os.path.join(od, os.path.basename(low)), 'wb').write(forzacab.data(d, e))
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    cb, at = os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png')
    c = carbin.read(open(cb, 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(name)
    hf, hr = tyrecheck.hubs_of(c, wb, zc)
    hubs = '%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr)
    log = open(os.path.join(od, 'render.log'), 'w')
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', cb, at, os.path.join(od, 'v')],
                   env=dict(os.environ, VIEWS=VIEWS, HUBS=hubs), stdout=log, stderr=subprocess.STDOUT, cwd=G)
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', cb, at, os.path.join(od, 'b')],
                   env=dict(os.environ, VIEWS='fside,rear', BACKRED='1'), stdout=log, stderr=subprocess.STDOUT, cwd=G)
    ims = [os.path.join(od, 'v_%s.png' % v) for v in VIEWS.split(',')] + [os.path.join(od, 'b_fside.png'), os.path.join(od, 'b_rear.png')]
    tiles = []
    for p in ims:
        im = Image.open(p).convert('RGB') if os.path.exists(p) else Image.new('RGB', (900, 600), 'magenta')
        im.thumbnail((600, 400)); tiles.append(im)
    s = Image.new('RGB', (600 * 4, 400 * 2), 'black')
    for i, t in enumerate(tiles): s.paste(t, ((i % 4) * 600, (i // 4) * 400))
    ImageDraw.Draw(s).text((6, 6), '%s  %s %s  (%s)' % (k, nc.CARS[k][3], nc.CARS[k][1], name), fill='yellow')
    s.save(os.path.join(OUT, '%s.png' % k))
    return k


if __name__ == '__main__':
    keys = sys.argv[1:] or list(nc.CARS)
    with ThreadPoolExecutor(4) as ex:
        for k in ex.map(one, keys): print(k, 'done', flush=True)
