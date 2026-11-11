import sys, os, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, carbin
from nfsu2forza import strip_tris
U = 4096 * 1.602
def loops(c, weld=0.006):
    p = next(p for p in c['parts'] if p['name'] == 'bumperF_LOD1')
    sp = [s for s in p['subparts'] if s['id'] == 1 and s['material'] == 1][1]
    V = np.array(p['verts'], float)[:, :3] / U
    key, P, ids = {}, [], []
    for v in V:
        k = tuple(np.round(v / weld).astype(int))
        if k not in key: key[k] = len(P); P.append(v)
        ids.append(key[k])
    P = np.array(P); edges = collections.Counter()
    for t in strip_tris(sp['indices']):
        a, b, c_ = (ids[i] for i in t)
        if len({a, b, c_}) == 3:
            for e in ((a, b), (b, c_), (c_, a)): edges[tuple(sorted(e))] += 1
    adj = collections.defaultdict(list)
    for (a, b), n in edges.items():
        if n == 1: adj[a].append(b); adj[b].append(a)
    seen, out = set(), []
    for s in list(adj):
        if s in seen: continue
        ring, prev, cur = [s], None, s; seen.add(s)
        while True:
            nx = [n for n in adj[cur] if n != prev and n not in seen]
            if not nx: break
            prev, cur = cur, nx[0]; ring.append(cur); seen.add(cur)
        Q = P[ring]
        perim = np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1).sum()
        out.append((perim, s in adj[ring[-1]], Q))
    return out
if __name__ == '__main__':
    c = carbin.read(open(r'E:\xbrt_scr\newcars\out\%s\car.carbin' % sys.argv[1], 'rb').read())
    L = sorted(loops(c), key=lambda l: -l[0])
    print(len(L), 'loops')
    for perim, closed, Q in L[:30]:
        c0 = Q.mean(0); sv = np.linalg.svd(Q - c0, compute_uv=False)
        print('perim %.2f closed %d n %4d centre x %.2f y %.2f z %.2f  flat %.3f  box %s' % (perim, closed, len(Q), *c0, sv[2] / np.sqrt(len(Q)), (Q.max(0) - Q.min(0)).round(2)))
