"""Close-ups of each wheel as the game draws it (gameview's tyre model, scale, hubs and track), add-on above,
template below: each wheel straight from the side and from a low three-quarter (front wheel from ahead, rear from
behind), as the store's camera sees them.   python wheelview.py key [key ...]  ->  wheelview/<key>.jpg
SRC=<carbin> draws another body in the add-on's place (a test conversion)."""
import sys, os, re, subprocess, shutil, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, forzaxpr, tyrecheck
from tyremodel import mega, lk, ck, cars, B
from trackcheck import track
from PIL import Image, ImageDraw
G = r'E:\Forza Motorsport Remastered'; W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a


def render(key, body, od, scale=None):
    name = nc.NAME[key]
    os.makedirs(od, exist_ok=True)
    shutil.copy(body, os.path.join(od, 'car.carbin'))
    shutil.copy(os.path.join(W, 'out', key, 'liveries', 'standard', 'livery0hi.xpr'), od)
    forzaxpr.decode(os.path.join(od, 'livery0hi.xpr'), od)
    td = bytes(cars.files[ck[('cars' + B + name + B + 'tooldata.xml').lower()]]).decode('latin-1')
    style = re.search(r'<WheelStyle>.*?File="([^"]+)"', td, re.S).group(1)
    cfgk = ck.get(('cars' + B + name + B + 'config.ini').lower())
    cfg = bytes(cars.files[cfgk]).decode('latin-1') if cfgk else ''
    fs = float((re.search(r'FrontTireScale\s+([\d.]+)', cfg) or [0, 1])[1]); rs = float((re.search(r'RearTireScale\s+([\d.]+)', cfg) or [0, 1])[1])
    if scale: fs, rs = scale
    open(os.path.join(od, 'tire.carbin'), 'wb').write(bytes(mega.files[lk[('tires' + B + 'art' + B + style + B + 'tire.carbin').lower()]]))
    c = carbin.read(open(os.path.join(od, 'car.carbin'), 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(name); hf, hr = tyrecheck.hubs_of(c, wb, zc)
    tf, tr = track(name)
    # Blender's axes: x forward (model z / 1.6), y the car's left, z up; the hub's height as carlit's HUBS puts it
    fx, rx = hf / 1.6, hr / 1.6
    fz, rz = -rf + df / 2, -rr + dr / 2
    yl = tf / 2
    cams = ['fs:%f:%f:%f:%f:%f:%f' % (fx, yl + 3.0, fz + 0.15, fx, yl, fz + 0.15),
            'f3:%f:%f:%f:%f:%f:%f' % (fx + 1.9, yl + 2.2, fz + 0.25, fx, yl - 0.1, fz + 0.1),
            'rs:%f:%f:%f:%f:%f:%f' % (rx, yl + 3.0, rz + 0.15, rx, yl, rz + 0.15),
            'r3:%f:%f:%f:%f:%f:%f' % (rx - 1.9, yl + 2.2, rz + 0.25, rx, yl - 0.1, rz + 0.1),
            'fb:%f:%f:%f:%f:%f:%f' % (fx + 3.0, yl - 0.15, fz + 0.15, fx, yl - 0.15, fz + 0.15),
            'rb:%f:%f:%f:%f:%f:%f' % (rx - 3.0, yl - 0.15, rz + 0.15, rx, yl - 0.15, rz + 0.15)]
    env = dict(os.environ, CAMS=';'.join(cams), LENS='38', HUBS='%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr), TIRE=os.path.join(od, 'tire.carbin'),
               TSCALE='%f,%f' % (fs, rs), TRACK='%f,%f' % (tf, tr))
    env.pop('VIEWS', None)
    with open(os.path.join(od, 'log'), 'w') as log:
        subprocess.run([tyrecheck.BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', os.path.join(od, 'car.carbin'), os.path.join(od, 'livery0hi.png'), os.path.join(od, 'v')],
                       env=env, stdout=log, stderr=subprocess.STDOUT, cwd=G)
    ims = []
    for v in ('fs', 'f3', 'rs', 'r3'):
        p = os.path.join(od, 'v_%s.png' % v)
        im = Image.open(p).convert('RGB') if os.path.exists(p) else Image.new('RGB', (900, 600), 'magenta')
        im.thumbnail((450, 300)); ims.append(im)
    row = Image.new('RGB', (1800, 300)); [row.paste(im, (450 * i, 0)) for i, im in enumerate(ims)]
    render.last = dict(fx=fx, rx=rx, fz=fz, rz=rz, yl=yl, rf_=df / 2, rr_=dr / 2, fs=fs, rs=rs, od=od)
    return row, (fs, rs, style)


def one(key):
    src = os.environ.get('SRC') or os.path.join(W, 'out', key, 'car.carbin')
    sc = tuple(float(x) for x in os.environ['TS'].split(',')) if os.environ.get('TS') else None
    a, (fs, rs, style) = render(key, src, os.path.join(W, 'wheelview', key), sc)
    tp, _ = nc.template_files(nc.CARS[key][9])
    b, _ = render(key, tp, os.path.join(W, 'wheelview', key + '_t'), sc)
    s = Image.new('RGB', (1800, 600)); s.paste(a, (0, 0)); s.paste(b, (0, 300))
    d = ImageDraw.Draw(s); d.text((6, 4), '%s  (%s tyres x%.2f/%.2f)' % (key, style, fs, rs), fill='yellow'); d.text((6, 304), 'template ' + nc.CARS[key][9], fill='cyan')
    s.save(os.path.join(W, 'wheelview', key + '.jpg'), quality=88)
    return key


if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(os.path.join(W, 'wheelview'), exist_ok=True)
    with ThreadPoolExecutor(3) as ex:
        for k in ex.map(one, sys.argv[1:]): print(k, 'done', flush=True)
