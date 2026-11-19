"""The installed car-select tiles of the given ordinals, 3x, on one sheet: python showtiles.py out.png o1 o2 ..."""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, forzaxpr as fx
from PIL import Image, ImageDraw
MODS = r'E:\Forza Motorsport Remastered\run\mods_track\media'
out, ords = sys.argv[1], [int(x) for x in sys.argv[2:]]
pages = {}
tiles = []
for o in ords:
    p = o // 64 + 1
    if p not in pages:
        d = open(os.path.join(MODS, 'caricons%d.xpr' % p), 'rb').read(); t = fx.textures(d)[0]
        pages[p] = fx.dxt(bytes(d[t['start']:]), t['w'], t['h'], 5)
    im = Image.fromarray(np.ascontiguousarray(pages[p][(o % 64) * 64:(o % 64 + 1) * 64, :, :3])).resize((384, 192), Image.LANCZOS)
    ImageDraw.Draw(im).text((3, 178), str(o), fill='yellow'); tiles.append(im)
s = Image.new('RGB', (384 * 4, 192 * ((len(tiles) + 3) // 4)))
for i, t in enumerate(tiles): s.paste(t, ((i % 4) * 384, (i // 4) * 192))
s.save(out); print(out)
