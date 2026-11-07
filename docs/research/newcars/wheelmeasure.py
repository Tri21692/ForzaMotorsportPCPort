"""Measures each wheel of an add-on and its template in wheelview's renders (camera 3.0 m off the wheel, 38 mm on a
36 mm sensor, 900 px wide: 316.7 px a metre at the wheel; the camera aimed 0.15 m above the hub, so the hub sits
47 px below the middle): the gap from the tyre's top to the arch lip straight over the hub (+ clear), the arch
opening's middle along the car against the hub (+ ahead), and from straight ahead / behind how far the tyre's outer
face stands out past the body's side just above it (+ out). The tyre's drawn radius is the model's times its scale.
python wheelmeasure.py key [key ...]   (after wheelview.py)   -> prints, and wheelmeasure.json"""
import sys, os, json
import numpy as np
from PIL import Image
sys.path.insert(0, r'E:\xbrt_scr\newcars')
W = r'E:\xbrt_scr\newcars'
PX = 38 / 36 * 900 / 3.0
HUBROW = 300 + 0.15 * PX


def masks(p):
    a = np.asarray(Image.open(p).convert('RGB'), int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > g + 18) & (r > 55)  # the paint (shadowed too)
    tyre = (np.maximum(np.maximum(r, g), b) < 95) & (np.abs(r - g) < 18) & (np.abs(g - b) < 18)
    return red, tyre, a


def side(p, R, ahead_sign):
    red, tyre, a = masks(p)
    cx, hub = 450, int(round(HUBROW))
    top = hub - R * PX
    col = red[:hub, cx - 2:cx + 3].any(1)
    hit = np.nonzero(col[:hub])[0]
    lip = hit.max() if len(hit) else 0
    gap = (top - lip) / PX  # (+: the lip above the tyre's top)
    row = int(round(hub - 0.55 * R * PX))
    lr = red[row]
    left = np.nonzero(lr[:cx])[0]; right = np.nonzero(lr[cx:])[0]
    if len(left) and len(right):
        mid = ((left.max() + 1) + (cx + right.min())) / 2
        off = (mid - cx) / PX * ahead_sign
    else:
        off = float('nan')
    return gap, off


def end(p, R, out_sign):
    red, tyre, a = masks(p)
    hub = int(round(HUBROW))
    win = slice(int(450 - 0.45 * PX), int(450 + 0.45 * PX))  # (the wheel's own neighbourhood: not the car's dark tail panel)
    band_t = tyre[hub - int(0.3 * R * PX):hub + int(0.9 * R * PX), win]
    tc = np.nonzero(band_t.sum(0) > 6)[0] + win.start
    band_b = red[int(hub - (R + 0.10) * PX):int(hub - (R - 0.03) * PX), win]
    bc = np.nonzero(band_b.any(0))[0] + win.start
    if not len(tc) or not len(bc): return float('nan')
    if out_sign > 0: return (tc.max() - bc.max()) / PX
    return (bc.min() - tc.min()) / PX


def measure(od, L):
    f = os.path.join(od, 'v_%s.png')
    Rf, Rr = L['rf_'] * L['fs'], L['rr_'] * L['rs']
    # side views look at the car's left (+y) from outside: forward (+x) is to the image's right
    gf, of = side(f % 'fs', Rf, -1)  # (the nose to the image's left)
    gr, orr = side(f % 'rs', Rr, -1)
    # from ahead (fb, looking back) the car's left is to the image's right; from behind (rb) to its left
    pf = end(f % 'fb', Rf, 1)
    pr = end(f % 'rb', Rr, -1)
    return dict(front=dict(gap=gf, ahead=of, out=pf), rear=dict(gap=gr, ahead=orr, out=pr))


if __name__ == '__main__':
    import wheelview as wv
    res = json.load(open(os.path.join(W, 'wheelmeasure.json'))) if os.path.exists(os.path.join(W, 'wheelmeasure.json')) else {}
    for k in sys.argv[1:]:
        out = {}
        for tag, body in (('car', os.environ.get('SRC') or os.path.join(W, 'out', k, 'car.carbin')), ('template', wv.nc.template_files(wv.nc.CARS[k][9])[0])):
            od = os.path.join(W, 'wheelview', k + ('' if tag == 'car' else '_t'))
            wv.render(k, body, od)
            out[tag] = measure(od, wv.render.last)
        res[k] = out
        c, t = out['car'], out['template']
        print('%-9s' % k + '   '.join('%s gap %+.3f (t %+.3f)  ahead %+.3f (t %+.3f)  out %+.3f (t %+.3f)' % (
            e, c[e]['gap'], t[e]['gap'], c[e]['ahead'], t[e]['ahead'], c[e]['out'], t[e]['out']) for e in ('front', 'rear')), flush=True)
    json.dump(res, open(os.path.join(W, 'wheelmeasure.json'), 'w'), indent=1)
