"""A converted add-on in Blender with the wheels as the game draws them: the WheelStyle's own tyre model
(tires\\art\\<style>\\tire.carbin, Mega.ca2) at the car's config.ini tyre scales, its hubs, ride heights and track
from the car's physics (tyrecheck, maxdata TrackOuter). Views side-on, rear three-quarter and front three-quarter.
TPOS=outer (default: the tyre's outer face at half the track) or centre.
  python gameview.py key [key ...]      ->  gameview/<key>.png (and <key>/v_*.png)"""
import sys, os, re, subprocess, shutil, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, forzaxpr, tyrecheck
from tyremodel import mega, lk, ck, cars, B
from trackcheck import track
from PIL import Image, ImageDraw
G = r'E:\Forza Motorsport Remastered'; W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a
VIEWS = os.environ.get('VIEWS', 'left,rearc,fside')


def one(key, src=None):
    name = nc.NAME[key]
    od = os.path.join(W, 'gameview', key); os.makedirs(od, exist_ok=True)
    shutil.copy(src or os.path.join(W, 'out', key, 'car.carbin'), os.path.join(od, 'car.carbin'))
    shutil.copy(os.path.join(W, 'out', key, 'liveries', 'standard', 'livery0hi.xpr'), od)
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    td = bytes(cars.files[ck[('cars' + B + name + B + 'tooldata.xml').lower()]]).decode('latin-1')
    style = re.search(r'<WheelStyle>.*?File="([^"]+)"', td, re.S).group(1)
    cfgk = ck.get(('cars' + B + name + B + 'config.ini').lower())
    cfg = bytes(cars.files[cfgk]).decode('latin-1') if cfgk else ''
    fs = float((re.search(r'FrontTireScale\s+([\d.]+)', cfg) or [0, 1])[1]); rs = float((re.search(r'RearTireScale\s+([\d.]+)', cfg) or [0, 1])[1])
    open(os.path.join(od, 'tire.carbin'), 'wb').write(bytes(mega.files[lk[('tires' + B + 'art' + B + style + B + 'tire.carbin').lower()]]))
    c = carbin.read(open(os.path.join(od, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(name); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    tf, tr = track(name)
    env = dict(os.environ, VIEWS=VIEWS, HUBS='%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr), TIRE=os.path.join(od, 'tire.carbin'),
               TSCALE='%f,%f' % (fs, rs), TRACK='%f,%f' % (tf, tr))
    with open(os.path.join(od, 'log'), 'w') as log:
        subprocess.run([tyrecheck.BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png'), os.path.join(od, 'v')],
                       env=env, stdout=log, stderr=subprocess.STDOUT, cwd=G)
    vs = VIEWS.split(',')
    sh = Image.new('RGB', (600 * len(vs), 400), 'black')
    for i, v in enumerate(vs):
        p = os.path.join(od, 'v_%s.png' % v)
        if os.path.exists(p):
            im = Image.open(p).convert('RGB'); im.thumbnail((600, 400)); sh.paste(im, (600 * i, 0))
    ImageDraw.Draw(sh).text((6, 4), '%s  tyres %s x%.2f/%.2f' % (key, style, fs, rs), fill='yellow')
    sh.save(os.path.join(W, 'gameview', key + '.png'))
    return key


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        for k in ex.map(one, sys.argv[1:]): print(k, 'done', flush=True)
