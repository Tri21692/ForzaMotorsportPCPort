"""Per part: the share of faces (finest level) whose winding disagrees with their vertices' normals, as carlit strips
them. A stock car's parts set the baseline; a converted part far off it draws inside out where the game culls.
  python windcheck.py <car.carbin> [...]"""
import sys
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np
import carbin


def part_stats(p):
    V = np.array([v[:6] for v in p['verts']], float)
    if not len(V): return None
    P, N = V[:, :3], V[:, 3:6]
    tri = []
    for sp in p['subparts']:
        if sp['id'] != 1: continue
        ix = sp['indices']
        for k in range(len(ix) - 2):
            a, b, c = (ix[k], ix[k + 1], ix[k + 2]) if k % 2 == 0 else (ix[k + 1], ix[k], ix[k + 2])
            if len({a, b, c}) == 3: tri.append((a, b, c))
    if not tri: return None
    T = np.array(tri)
    g = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    n = N[T].sum(1)
    area = np.linalg.norm(g, axis=1)
    ok = area > 0
    d = np.einsum('ij,ij->i', g[ok], n[ok])
    return len(T), float((d < 0).sum() / max(1, ok.sum())), float(area[ok][d < 0].sum() / max(1e-9, area[ok].sum()))


if __name__ == '__main__':
    for path in sys.argv[1:]:
        c = carbin.read(open(path, 'rb').read())
        print('==', path)
        for p in c['parts']:
            if not p['name'].endswith('_LOD1') and p['name'] not in ('steering_wheel',): continue
            s = part_stats(p)
            if s: print('  %-24s tris %6d  against %.2f (area %.2f)' % (p['name'], *s))
