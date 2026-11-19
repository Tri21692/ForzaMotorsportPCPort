"""Longest triangle edges in each car's window parts and roof (metres): spikes from bad indices stand out."""
import sys, os, re, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
for k in (sys.argv[1:] or sorted(os.listdir(os.path.join(W, 'src')))):
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    out = []
    for p in nfsu.read(os.path.join(d, 'GEOMETRY.BIN')):
        if not re.search(r'WINDOW_A$', p['name']) or 'DAMAGE' in p['name']: continue
        V = np.array([v[:3] for v in p['verts']])
        idx = [i for t in p['tris'] for i in t]
        for g in p['groups']:
            cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
            T = np.array([idx[j:j + 3] for j in range(first, first + cnt - 2, 3) if max(idx[j:j + 3]) < len(V)])
            if not len(T): continue
            e = np.max([np.linalg.norm(V[T[:, a]] - V[T[:, b]], axis=1) for a, b in ((0, 1), (1, 2), (0, 2))], axis=0)
            out.append((round(float(e.max()), 2), int((e > 1.8).sum()), len(T)))
    print('%-9s longest %s' % (k, sorted(out, reverse=True)[:3]))
