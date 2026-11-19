"""Close renders of a converted car's lamps (out/<key>: car.carbin and its standard livery atlas), carlit's straight-on
front/rear and close corners, into lampview/<key>.png.   python lampview.py key [key ...]"""
import sys, os, subprocess, shutil
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import forzaxpr
from PIL import Image
G = r'E:\Forza Motorsport Remastered'; W = r'E:\xbrt_scr\newcars'
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
VIEWS = os.environ.get('VIEWS', 'fclose,rearc,front,rear')


def one(k):
    od = os.path.join(W, 'lampview', k); os.makedirs(od, exist_ok=True)
    shutil.copy(os.path.join(W, 'out', k, 'car.carbin'), od)
    shutil.copy(os.path.join(W, 'out', k, 'liveries', 'standard', 'livery0hi.xpr'), od)
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    with open(os.path.join(od, 'render.log'), 'w') as log:
        subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png'), os.path.join(od, 'v')],
                       env=dict(os.environ, VIEWS=VIEWS), stdout=log, stderr=subprocess.STDOUT, cwd=G)
    vs = VIEWS.split(',')
    s = Image.new('RGB', (600 * len(vs), 400), 'black')
    for i, v in enumerate(vs):
        p = os.path.join(od, 'v_%s.png' % v)
        if os.path.exists(p):
            im = Image.open(p).convert('RGB'); im.thumbnail((600, 400)); s.paste(im, (600 * i, 0))
    s.save(os.path.join(W, 'lampview', '%s.png' % k))
    return k


if __name__ == '__main__':
    with ThreadPoolExecutor(3) as ex:
        for k in ex.map(one, sys.argv[1:]): print(k, 'done', flush=True)
