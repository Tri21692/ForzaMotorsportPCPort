"""A car's cab (or a converter output folder) drawn lit in Blender, a sheet of views.
  python viewcar.py <cab or folder> <out jpg> [views] [paint]"""
import sys, os, subprocess
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import forzacab, forzaxpr
from PIL import Image
G = r'E:\Forza Motorsport Remastered'
BLENDER = r'C:\Program Files\Blender Foundation\Blender 3.3\blender.exe'
src, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
views = sys.argv[3] if len(sys.argv) > 3 else 'front,rear,left,fside,fclose,rearc'
paint = sys.argv[4] if len(sys.argv) > 4 else '0.45,0.47,0.55'
od = out[:-4] + '_w'; os.makedirs(od, exist_ok=True)
if os.path.isdir(src):
    open(os.path.join(od, 'car.carbin'), 'wb').write(open(os.path.join(src, 'car.carbin'), 'rb').read())
    open(os.path.join(od, 'livery0hi.xpr'), 'wb').write(open(os.path.join(src, 'liveries', 'standard', 'livery0hi.xpr'), 'rb').read())
else:
    d, ver, es = forzacab.read(src)
    for e in es:
        low = e['name'].lower()
        if low.endswith('car.carbin') or low.endswith('livery0hi.xpr'):
            open(os.path.join(od, os.path.basename(low)), 'wb').write(forzacab.data(d, e))
forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'),
                os.path.join(od, 'livery0hi.png'), os.path.join(od, 'l'), paint],
               env=dict(os.environ, VIEWS=views), stdout=open(os.path.join(od, 'render.log'), 'w'), stderr=subprocess.STDOUT, cwd=G)
vs = views.split(',')
ims = [Image.open(os.path.join(od, 'l_%s.png' % v)).convert('RGB') for v in vs if os.path.exists(os.path.join(od, 'l_%s.png' % v))]
w, h = 800, 520
s = Image.new('RGB', (w * 3, h * ((len(ims) + 2) // 3)), 'black')
for i, im in enumerate(ims):
    im.thumbnail((w, h)); s.paste(im, (i % 3 * w, i // 3 * h))
s.save(out, quality=88); print(out, len(ims))
