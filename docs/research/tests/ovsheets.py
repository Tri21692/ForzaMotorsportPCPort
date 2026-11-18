import glob, sys
from PIL import Image
d = sys.argv[1]
def sheet(name, ims, cols=2):
    ims = [im for im in ims if im is not None]
    if not ims: return
    w, h = ims[0].size
    s = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * h))
    for k, im in enumerate(ims): s.paste(im.resize((w, h)), ((k % cols) * w, (k // cols) * h))
    s.save(d + '/' + name + '.jpg', quality=88)
def j(f):
    try: return Image.open(d + '/' + f + '.jpg')
    except Exception: return None
sheet('sheetA', [j('t0'), j('t1'), j('t2'), j('t3')])
sheet('sheetB', [j('t4'), j('t5'), j('t6'), j('t6b')])
sheet('sheetC', [j('t6c'), j('t7'), j('qr'), j('pm')])
sheet('sheetD', [j('menu'), j('menu2')])
ps = sorted(glob.glob('E:/xbrt_scr/vid/hud_t/p_*.ppm'))
last = len(ps) - 1
hud = [Image.open(ps[last - 4 * k]) for k in range(7, -1, -1) if last - 4 * k >= 0]
sheet('sheetE', hud[:4]); sheet('sheetF', hud[4:])
print('sheets in', d)
