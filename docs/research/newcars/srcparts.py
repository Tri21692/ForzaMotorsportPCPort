"""A source car's window/glass/lamp parts (level A): verts and box, NFS metres (x fwd?)."""
import sys, os, re
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
pat = sys.argv[2] if len(sys.argv) > 2 else 'WINDOW|GLASS|BASE|LIGHT'
k = sys.argv[1]
d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
for p in nfsu.read(os.path.join(d, 'GEOMETRY.BIN')):
    n = p['name']
    if not re.search(pat, n) or 'DAMAGE' in n or not (n.endswith('_A') or n.endswith('BASE')): continue
    V = np.array([v[:3] for v in p['verts']], float) if p['verts'] else np.zeros((1, 3))
    print('%-40s %5d  x %5.2f..%5.2f  y %5.2f..%5.2f  z %5.2f..%5.2f' % (n, len(p['verts']), *[f(V[:, i]) for i in range(3) for f in (np.min, np.max)]))
