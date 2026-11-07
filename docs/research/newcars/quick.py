"""Rear three-quarter and side views of add-ons with the game's tyres (gameview), several cars a sheet beside their
templates' saved renders (gameview/vs_<key>.png's lower half): gameview/quick.jpg.   python quick.py key ..."""
import sys, os
os.environ['VIEWS'] = 'left,rearc'
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import gameview as gv
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor
keys = sys.argv[1:]
with ThreadPoolExecutor(4) as ex: list(ex.map(gv.one, keys))
rows = []
for k in keys:
    a = Image.open(os.path.join(gv.W, 'gameview', k + '.png')).convert('RGB')
    vs = os.path.join(gv.W, 'gameview', 'vs_' + k + '.png')
    b = Image.open(vs).convert('RGB').crop((0, a.height, a.width, 2 * a.height)) if os.path.exists(vs) else Image.new('RGB', a.size)
    r = Image.new('RGB', (a.width * 2, a.height)); r.paste(a, (0, 0)); r.paste(b, (a.width, 0)); rows.append(r.resize((r.width // 2, r.height // 2)))
s = Image.new('RGB', (rows[0].width, rows[0].height * len(rows)))
for i, r in enumerate(rows): s.paste(r, (0, i * r.height))
s.save(os.path.join(gv.W, 'gameview', 'quick.jpg'), quality=85)
