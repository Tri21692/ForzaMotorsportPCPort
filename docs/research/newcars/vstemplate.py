"""Each add-on beside its template (whose wheels the game draws on it, and which they fit), both with the game's own
tyres (gameview), side-on and rear three-quarter: gameview/vs_<key>.png, add-on above, template below.
python vstemplate.py key [key ...]"""
import sys, os, shutil
sys.path.insert(0, r'E:\xbrt_scr\newcars')
os.environ.setdefault('VIEWS', 'left,rearc')
import gameview as gv
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor


def pair(key):
    gv.one(key)
    a = Image.open(os.path.join(gv.W, 'gameview', key + '.png')).convert('RGB')
    tp, _ = gv.nc.template_files(gv.nc.CARS[key][9])
    tdir = os.path.join(gv.W, 'gameview', key)
    tkey = key  # (the template drawn through the same car's data: its wheels are the template's)
    shutil.copytree(tdir, tdir + '_t', dirs_exist_ok=True)
    orig = os.path.join(gv.W, 'gameview', key)
    gv.one(key, src=tp)
    b = Image.open(os.path.join(gv.W, 'gameview', key + '.png')).convert('RGB')
    s = Image.new('RGB', (a.width, a.height * 2), 'black'); s.paste(a, (0, 0)); s.paste(b, (0, a.height))
    ImageDraw.Draw(s).text((6, a.height + 4), 'template ' + gv.nc.CARS[key][9], fill='cyan')
    s.save(os.path.join(gv.W, 'gameview', 'vs_' + key + '.png'))
    return key


if __name__ == '__main__':
    for k in sys.argv[1:]: print(pair(k), 'done', flush=True)
