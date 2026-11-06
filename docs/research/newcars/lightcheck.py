"""Every custom car's lamps up close (carlit fclose, rearc and a straight-on front and rear), from the installed cabs:
the 32 new cars and the earlier add-ons (anything in run/mods_track's cabs the disc has not), one sheet each of
8 cars: check_lights/lights_<n>.png.   python lightcheck.py [names]"""
import sys, os, subprocess, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import forzacab, forzaxpr
from PIL import Image, ImageDraw
G = r'E:\Forza Motorsport Remastered'
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
CABS = os.path.join(G, 'run', 'mods_track', 'media', 'cabs')
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
OUT = r'E:\xbrt_scr\newcars\check_lights'
disc = {f.lower() for f in os.listdir(os.path.join(DISC, 'media', 'cabs'))}
cars = sorted(f[4:-4] for f in os.listdir(CABS) if f.lower().startswith('car_') and f.lower().endswith('.cab') and f.lower() not in disc)
VIEWS = 'fclose,rearc'


def one(name):
    od = os.path.join(OUT, name); os.makedirs(od, exist_ok=True)
    d, ver, es = forzacab.read(os.path.join(CABS, 'car_%s.cab' % name))
    for e in es:
        low = e['name'].lower()
        if low.endswith('car.carbin') or low.endswith('livery0hi.xpr'):
            open(os.path.join(od, os.path.basename(low)), 'wb').write(forzacab.data(d, e))
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'),
                    os.path.join(od, 'livery0hi.png'), os.path.join(od, 'l'), '0.9,0.9,0.9'],
                   env=dict(os.environ, VIEWS=VIEWS), stdout=open(os.path.join(od, 'render.log'), 'w'), stderr=subprocess.STDOUT, cwd=G)
    return name


if __name__ == '__main__':
    only = sys.argv[1:]
    todo = [c for c in cars if not only or c in only]
    with ThreadPoolExecutor(4) as ex:
        for n in ex.map(one, todo): print(n, flush=True)
    for i in range(0, len(todo), 8):
        ks = todo[i:i + 8]
        s = Image.new('RGB', (1200, 400 * len(ks)), 'black')
        for j, n in enumerate(ks):
            for v, x in (('fclose', 0), ('rearc', 600)):
                p = os.path.join(OUT, n, 'l_%s.png' % v)
                if os.path.exists(p):
                    im = Image.open(p).convert('RGB'); im.thumbnail((600, 400)); s.paste(im, (x, j * 400))
            ImageDraw.Draw(s).text((6, j * 400 + 6), n, fill='yellow')
        s.save(os.path.join(OUT, 'lights_%d.jpg' % (i // 8)), quality=88)
    print(len(todo), 'cars')
