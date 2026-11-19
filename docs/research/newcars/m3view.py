"""The M3 GTR Most Wanted (BMWM3GTRMW, an older import, not in newcars.CARS) through the add-on tools: its installed
cab extracted (read only) into out/m3gtr, registered as key 'm3gtr' on its template BMWM3GTR42.
python m3view.py [wheelview|sideplot|measure|lipfit]   (SRC=<carbin> to view a test body)"""
import sys, os
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import forzacab
W = r'E:\xbrt_scr\newcars'
CAB = r'E:\Forza Motorsport Remastered\run\mods_track\media\cabs\car_BMWM3GTRMW.cab'
OUT = os.path.join(W, 'out', 'm3gtr')


def extract():
    dd, ver, es = forzacab.read(CAB)
    pre = 'cars\\bmwm3gtrmw\\'
    for e in es:
        n = e['name'].replace('/', '\\')
        if not n.lower().startswith(pre): continue
        p = os.path.join(OUT, *n[len(pre):].split('\\'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(forzacab.data(dd, e))


def register(nc):
    nc.NAME['m3gtr'] = 'BMWM3GTRMW'
    nc.CARS['m3gtr'] = (None,) * 9 + ('BMWM3GTR42',) + (None,) * 3


if __name__ == '__main__':
    if not os.path.exists(os.path.join(OUT, 'car.carbin')) or os.environ.get('FRESH'): extract()
    what = sys.argv[1] if len(sys.argv) > 1 else 'wheelview'
    if what == 'wheelview':
        import wheelview; register(wheelview.nc); os.makedirs(os.path.join(W, 'wheelview'), exist_ok=True); wheelview.one('m3gtr')
    elif what == 'sideplot':
        sys.argv = ['x', os.path.join(W, 'sp_m3.png'), 'm3gtr']
        import sideplot; register(sideplot.nc)
        from PIL import Image
        im = sideplot.plot('m3gtr', os.environ.get('SRC')); im.save(os.path.join(W, 'sp_m3.png')) if im is not None else None
    elif what == 'measure':
        import runpy, wheelview; register(wheelview.nc); sys.argv = ['x', 'm3gtr']
        runpy.run_path(os.path.join(W, 'wheelmeasure.py'), run_name='__main__')
    elif what == 'lipfit':
        import lipfit; register(lipfit.nc); M, T, f = lipfit.check('m3gtr')
        print('lip %+.3f %+.3f  beside %+.3f %+.3f  f %.3f' % (M[0] - T[0], M[1] - T[1], M[2] - T[2], M[3] - T[3], f))
