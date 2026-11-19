"""Car-select tiles with the wheels where the game puts them: carlit ICON=1 with HUBS (the template's hubs from its
rotors or physics, its stock ride heights and tyre sizes, as tyrecheck.py), cut out into the car's 128 x 64 tile, then
the disc's form and the badges (tools/caricontile.py). The arch-guess the tiles had put the Neon's and the Celica's
front tyres low and ahead of their arches (the user's of 5 Nov: check the tyres on all icons).

  python iconfix.py <ordinal> <car.carbin> <livery0hi.png> <physics car> <paint r,g,b> <ops, e.g. form:dlc> [--preview]"""
import sys, os, subprocess
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
sys.path.insert(0, r'E:\xbrt_scr\newcars')
import numpy as np
from PIL import Image
import carbin
import tyrecheck
G, DISC, MODS, BLENDER = tyrecheck.G, tyrecheck.DISC, tyrecheck.MODS, tyrecheck.BLENDER


def render(cb, livery, physics_car, paint, out_prefix):
    c = carbin.read(open(cb, 'rb').read())
    wb, zc, rf, rr, df, dr = tyrecheck.data(physics_car)
    hf, hr = tyrecheck.hubs_of(c, wb, zc)
    env = dict(os.environ, ICON='1', HUBS='%f,%f,%f,%f,%f,%f' % (hf, hr, rf, rr, df, dr))
    log = out_prefix + '_icon.log'
    subprocess.run([BLENDER, '-b', '--python', os.path.join(G, 'tools', 'carlit.py'), '--', cb, livery, out_prefix, paint],
                   env=env, stdout=open(log, 'w'), stderr=subprocess.STDOUT, cwd=G)
    return out_prefix + '_icon.png'


def tile_of(png):
    im = Image.open(png).convert('RGBA')
    box = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    if box: im = im.crop(box)
    im.thumbnail((124, 60), Image.LANCZOS)
    tile = Image.new('RGBA', (128, 64), (0, 0, 0, 0))
    tile.paste(im, ((128 - im.size[0]) // 2, (64 - im.size[1]) // 2 + 1), im)
    return tile


def place(o, png, ops='form:dlc'):
    import addcar, caricontile, forzaxpr as fx
    tile = tile_of(png)
    src, dst = caricontile.pack_path(DISC, MODS, o)
    d = bytearray(open(src, 'rb').read())
    t = fx.textures(d)[0]
    enc = fx.encode_dxt5(np.ascontiguousarray(np.asarray(tile, np.uint8)))
    off = t['start'] + (o % 64) * addcar.TILE
    d[off:off + addcar.TILE] = enc
    open(dst, 'wb').write(bytes(d))
    caricontile.main(DISC, MODS, ['%d:%s' % (o, ops)])
    return dst


if __name__ == '__main__':
    a = sys.argv[1:]
    o, cb, livery, phys, paint, ops = int(a[0]), a[1], a[2], a[3], a[4], a[5]
    png = render(cb, livery, phys, paint, os.path.join(os.path.dirname(cb), 'iconfix'))
    print(png)
    if '--preview' not in a:
        print(place(o, png, ops))
