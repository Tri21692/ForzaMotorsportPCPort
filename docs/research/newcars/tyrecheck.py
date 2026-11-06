"""Every car drawn side-on with its tyres where the game puts them (hubs: the model's rotors, else the physics'
wheelbase about its middle at 1.602 units a metre; height: the stock ride height; size: the stock tyres), to check the
arches over them. Installed custom cars from run/mods_track, the new conversions from out/ with their templates' data.

  python tyrecheck.py installed|new|all [names]"""
import sys, os, re, subprocess, json
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import carbin, forzacab, addcar
from PIL import Image, ImageDraw
B = chr(92)
G = r'E:\Forza Motorsport Remastered'
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
MODS = os.path.join(G, 'run', 'mods_track')
W = r'E:\xbrt_scr\newcars'
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
cars = addcar.Archive(DISC, MODS, 'Cars.ca2')


def data(name):
    def f(rel):
        k = next((k for k in cars.files if k.lower() == ('cars' + B + name + B + rel).lower()), None)
        return bytes(cars.files[k]).decode('latin-1') if k else ''
    md, td = f('physics' + B + 'maxdata.xml'), f('tooldata.xml')
    wb = float(re.search(r'Wheelbase="([^"]+)"', md).group(1)); zc = float(re.search(r'BottomCenterWheelbasePos[^>]*z="([^"]+)"', md).group(1))
    rf = float(re.search(r'FrontStockRideHeight="([^"]+)"', md).group(1)); rr = float(re.search(r'RearStockRideHeight="([^"]+)"', md).group(1))
    lvl = int(re.search(r'<Tire StockLevel="(\d+)"', td).group(1))
    blk = re.search(r'<Tire StockLevel.*?<L%d[^>]*>(.*?)</L%d>' % (lvl, lvl), td, re.S).group(1)
    def dia(which):
        a = dict(re.findall(r'(\w+)="([^"]+)"', re.search(r'<%s ([^>]*)/>' % which, blk).group(1)))
        return (float(a['WheelDiameter']) * 25.4 + 2 * float(a['TireWidth']) * float(a['TireRatio']) / 100) / 1000
    return wb, zc, rf, rr, dia('Fronts'), dia('Rears')


def hubs_of(c, wb, zc):
    rot = [(min(v[2] for v in q['verts']) + max(v[2] for v in q['verts'])) / 2 / 4096 for q in c['parts'] if q['name'].startswith('rotor') or '_rotor' in q['name']]
    if any(z > 0 for z in rot) and any(z < 0 for z in rot):
        return max(z for z in rot if z > 0), min(z for z in rot if z < 0)  # (as the converter: the rotors')
    return (zc + wb / 2) * 1.602, (zc - wb / 2) * 1.602


def render(label, cb, atlas, physics_car, outdir):
    os.makedirs(outdir, exist_ok=True)
    c = carbin.read(open(cb, 'rb').read())
    wb, zc, rf, rr, df, dr = data(physics_car)
    hf, hr = hubs_of(c, wb, zc)
    env = dict(os.environ, VIEWS='left', HUBS='%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr))
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', cb, atlas, os.path.join(outdir, 't')],
                   env=env, stdout=open(os.path.join(outdir, 'tyres.log'), 'w'), stderr=subprocess.STDOUT, cwd=G)
    return os.path.join(outdir, 't_left.png'), (hf, hr, df, dr)


def sheet(items, path):
    tiles = []
    for label, png, info in items:
        if not os.path.exists(png): continue
        im = Image.open(png).convert('RGB'); im = im.crop((0, int(im.size[1] * 0.2), im.size[0], int(im.size[1] * 0.85))); im.thumbnail((560, 260))
        ImageDraw.Draw(im).text((4, 4), '%s  hubs %.2f %.2f  tyres %.2f %.2f m' % ((label,) + info), fill='yellow')
        tiles.append(im)
    if not tiles: return
    w, h = tiles[0].size
    s = Image.new('RGB', (w * 3, h * ((len(tiles) + 2) // 3)), 'black')
    for i, t in enumerate(tiles): s.paste(t, ((i % 3) * w, (i // 3) * h))
    s.save(path); print(path, len(tiles))


if __name__ == '__main__':
    what, only = sys.argv[1], sys.argv[2:]
    items = []
    if what in ('installed', 'all'):
        A = r'E:\xbrt_scr\audit'
        for name in sorted(os.listdir(A)):
            d = os.path.join(A, name)
            if not os.path.isfile(os.path.join(d, 'car.carbin')) or (only and name not in only) or 'MX5' in name: continue
            png, info = render(name, os.path.join(d, 'car.carbin'), os.path.join(d, 'livery0hi.png'), name, os.path.join(d, 'tyres'))
            items.append((name, png, info))
        sheet(items, os.path.join(W, 'tyres_installed.png'))
    if what in ('new', 'all'):
        sys.path.insert(0, W)
        import importlib.util
        spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec); sys.argv = ['x']; spec.loader.exec_module(nc)
        items = []
        for k, v in nc.CARS.items():
            d = os.path.join(W, 'out', k)
            if (only and k not in only) or not os.path.exists(os.path.join(d, 'car.carbin')): continue
            if not os.path.exists(os.path.join(d, 'livery0hi.png')):
                import forzaxpr; forzaxpr.decode(os.path.join(d, 'liveries', 'standard', 'livery0hi.xpr'), d)
            png, info = render(k, os.path.join(d, 'car.carbin'), os.path.join(d, 'livery0hi.png'), v[9], os.path.join(d, 'tyres'))
            items.append((k, png, info))
        for i in range(0, len(items), 12):
            sheet(items[i:i + 12], os.path.join(W, 'tyres_new_%d.png' % (i // 12)))
