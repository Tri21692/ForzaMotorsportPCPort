"""lightcheck's views of fresh builds (out/<key>): check_lights/fresh_<n>.jpg.  python lightfresh.py keys..."""
import sys, os, subprocess, shutil
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import forzaxpr
from PIL import Image, ImageDraw
G = r'E:\Forza Motorsport Remastered'; W = r'E:\xbrt_scr\newcars'
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
def one(k):
    od = os.path.join(W, 'check_lights', 'fresh', k); os.makedirs(od, exist_ok=True)
    shutil.copy(os.path.join(W, 'out', k, 'car.carbin'), od)
    shutil.copy(os.path.join(W, 'out', k, 'liveries', 'standard', 'livery0hi.xpr'), od)
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png'),
                    os.path.join(od, 'l'), '0.9,0.9,0.9'], env=dict(os.environ, VIEWS='fclose,rearc'), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, cwd=G)
    return k
ks = sys.argv[1:]
with ThreadPoolExecutor(4) as ex: list(ex.map(one, ks))
for i in range(0, len(ks), 8):
    part = ks[i:i + 8]
    s = Image.new('RGB', (1200, 400 * len(part)), 'black')
    for j, k in enumerate(part):
        for v, x in (('fclose', 0), ('rearc', 600)):
            p = os.path.join(W, 'check_lights', 'fresh', k, 'l_%s.png' % v)
            if os.path.exists(p): im = Image.open(p).convert('RGB'); im.thumbnail((600, 400)); s.paste(im, (x, j * 400))
        ImageDraw.Draw(s).text((6, j * 400 + 6), k, fill='yellow')
    s.save(os.path.join(W, 'check_lights', 'fresh_%d.jpg' % (i // 8)), quality=88)
print('done')
