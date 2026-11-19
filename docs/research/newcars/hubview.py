"""Side views of converted cars in Blender with the wheels where the game's physics puts them (tyrecheck: hubs,
ride heights, stock tyre sizes), next to the store's side-on frame of the same car (the store pass's cars/<n>,
frame 20), to check the wheel placement against the game.   python hubview.py key:storeindex ..."""
import sys, os, subprocess, shutil, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, forzaxpr, tyrecheck
from PIL import Image, ImageDraw
G = r'E:\Forza Motorsport Remastered'; W = r'E:\xbrt_scr\newcars'; ST = r'E:\xbrt_scr\store\cars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
rows = []
for arg in sys.argv[1:]:
    k, n = arg.split(':')
    od = os.path.join(W, 'hubview', k); os.makedirs(od, exist_ok=True)
    shutil.copy(os.path.join(W, 'out', k, 'car.carbin'), od); shutil.copy(os.path.join(W, 'out', k, 'liveries', 'standard', 'livery0hi.xpr'), od)
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    c = carbin.read(open(os.path.join(od, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(nc.NAME[k]); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    with open(os.path.join(od, 'log'), 'w') as log:
        subprocess.run([tyrecheck.BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png'), os.path.join(od, 'v')],
                       env=dict(os.environ, VIEWS='left', HUBS='%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr)), stdout=log, stderr=subprocess.STDOUT, cwd=G)
    a = Image.open(os.path.join(od, 'v_left.png')).convert('RGB'); a.thumbnail((640, 430))
    D = os.path.join(ST, n); fs = sorted(os.listdir(D), key=lambda f: os.path.getmtime(os.path.join(D, f)))
    b = Image.open(os.path.join(D, fs[min(20, len(fs) - 1)])).convert('RGB').crop((100, 180, 1180, 640)); b.thumbnail((640, 430))
    rows.append((k, a, b))
sh = Image.new('RGB', (1280, 430 * len(rows)), 'white')
for i, (k, a, b) in enumerate(rows):
    sh.paste(a, (0, 430 * i)); sh.paste(b, (640, 430 * i)); ImageDraw.Draw(sh).text((4, 430 * i + 4), k + ': Blender (left), game (right)', fill='red')
sh.save(os.path.join(W, 'hubview', os.environ.get('OUT', 'compare') + '.jpg'), quality=85)
