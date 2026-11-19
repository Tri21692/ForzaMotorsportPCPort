import sys
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, carbin
for path in sys.argv[1:]:
    c = carbin.read(open(path, 'rb').read())
    print('==', path)
    for p in c['parts']:
        if not p['name'].startswith('glass') or not p['name'].endswith('_LOD1'): continue
        if not any(sp['indices'] != [0, 0, 0] for sp in p['subparts'] if sp['id'] == 1): continue
        V = np.array([v[:3] for v in p['verts']]) / 4096 / 1.602
        print('  %-14s n %5d  x %5.2f..%5.2f  y %5.2f..%5.2f  z(fwd) %5.2f..%5.2f' % (p['name'], len(V), V[:,0].min(), V[:,0].max(), V[:,1].min(), V[:,1].max(), V[:,2].min(), V[:,2].max()))
