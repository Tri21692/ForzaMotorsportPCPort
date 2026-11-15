import importlib.util, os, sys, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
spec = importlib.util.spec_from_file_location('nc', r'E:\xbrt_scr\newcars\newcars.py'); nc = importlib.util.module_from_spec(spec)
a = sys.argv[1:]; sys.argv = ['x']; spec.loader.exec_module(nc)
import nfsu, nfsu2forza
for k in a or list(nc.CARS):
    sd = nc.stage(nc.CARS[k][0], k)
    ps = nfsu.read(os.path.join(sd, 'GEOMETRY.BIN'))
    ts = sorted([p for p in ps if 'FRONT_TIRE' in p['name']], key=lambda p: -len(p['verts']))
    p = ts[0]
    gs = []
    for g in p['groups']:
        cnt, = struct.unpack_from('<I', g, 12); ti, si = struct.unpack_from('<II', g, 0x1C)
        gs.append('%s/%s:%d' % (p['materials'][si] if si < len(p['materials']) else si, ('%08x' % p['textures'][ti]) if isinstance(p['textures'][ti], int) else p['textures'][ti], cnt // 3))
    print('%-9s %-28s %5d v; %s' % (k, p['name'], len(p['verts']), ' '.join(gs)[:230]))
