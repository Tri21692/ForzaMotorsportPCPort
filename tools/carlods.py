"""A car's far detail levels (subparts 2-4) made again from its finest (1), in place in its cab: each part's finest
triangles simplified by edge collapses (quadric error, Garland and Heckbert's), every collapse onto one of the edge's
own vertices (the part's vertices stay as they are, only the far levels' index lists change), none that turns a
face over, the open edges and seams (a vertex with another at the same place: a texture, normal or shading seam)
held by planes of their own, until the part is down to the level's share of the target. The 4 Nov audit: the
Celica GT-Four's Underground 2 model has its four levels copies of the first, and the converter (nfsu2forza.py)
kept 125,719 triangles at level 1 and 104,289 at level 3, against the disc cars' 10,000-35,000 at level 1. Only
part and material pairs that have the level already get it again. (Grid clustering first: the panels tore, the
black insides showed.)

  python tools/carlods.py <mods folder> <car> [<level 2 target>,<3>,<4>]   (default 24000,12000,3000)
"""
import collections
import heapq
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin
import forzacab
import nfsu2forza


def simplify(P, tris, target, seam, N=None):
    """tris (vertex indices into P) collapsed to about target triangles; seam: vertices that must stay put
    (shared places); N: vertex normals, no collapse between two facing more than 70 degrees apart (a door's outer
    skin and its inner panel a centimetre behind cost almost nothing to merge by distance, and the doors fell in).
    Returns the triangle list."""
    F = [list(t) for t in tris]
    alive = [True] * len(F)
    vf = collections.defaultdict(set)
    for fi, t in enumerate(F):
        for v in t: vf[v].add(fi)
    Q = collections.defaultdict(lambda: np.zeros((4, 4)))
    def plane(a, b, c):
        n = np.cross(P[b] - P[a], P[c] - P[a])
        l = np.linalg.norm(n)
        if l < 1e-12: return None, 0.0
        n /= l
        return np.append(n, -n.dot(P[a])), l
    for t in F:
        p, area = plane(*t)
        if p is None: continue
        K = np.outer(p, p) * area
        for v in t: Q[v] += K
    # open edges: a plane through the edge, upright to its face, heavily weighted
    ec = collections.Counter()
    for t in F:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])): ec[(min(a, b), max(a, b))] += 1
    for fi, t in enumerate(F):
        p, area = plane(*t)
        if p is None: continue
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            if ec[(min(a, b), max(a, b))] == 1:
                e = P[b] - P[a]
                n = np.cross(e, p[:3])
                l = np.linalg.norm(n)
                if l < 1e-12: continue
                n /= l
                q = np.append(n, -n.dot(P[a]))
                K = np.outer(q, q) * max(area, np.dot(e, e)) * 100.0
                Q[a] += K; Q[b] += K
    BIG = 1e18
    def cost(a, b):  # a onto b
        if a in seam: return BIG
        if N is not None and np.dot(N[a], N[b]) < 0.34: return BIG
        x = np.append(P[b], 1.0)
        return float(x @ (Q[a] + Q[b]) @ x)
    heap, ver = [], collections.Counter()
    def push(a, b):
        c = min((cost(a, b), a, b), (cost(b, a), b, a))
        if c[0] < BIG: heapq.heappush(heap, (c[0], c[1], c[2], ver[c[1]], ver[c[2]]))
    for (a, b) in ec: push(a, b)
    n = sum(alive)
    def normal(t):
        return np.cross(P[t[1]] - P[t[0]], P[t[2]] - P[t[0]])
    while n > target and heap:
        c, a, b, va, vb = heapq.heappop(heap)
        if ver[a] != va or ver[b] != vb or not vf[a]: continue
        # a's faces with b in them go; the rest have a replaced by b: none may turn over
        ok = True
        for fi in vf[a]:
            if not alive[fi] or b in F[fi]: continue
            t = F[fi]
            nt = [b if v == a else v for v in t]
            n0, n1 = normal(t), normal(nt)
            if np.dot(n0, n1) <= 0.2 * np.linalg.norm(n0) * np.linalg.norm(n1): ok = False; break
        if not ok:
            ver[a] += 1  # (tried: the edges round a again later, from their new costs)
            continue
        for fi in list(vf[a]):
            if not alive[fi]: continue
            if b in F[fi]:
                alive[fi] = False; n -= 1
                for v in F[fi]:
                    if v != a: vf[v].discard(fi)
            else:
                F[fi] = [b if v == a else v for v in F[fi]]
                vf[b].add(fi)
        vf[a] = set()
        Q[b] = Q[b] + Q[a]
        ver[a] += 1; ver[b] += 1
        nb = {v for fi in vf[b] if alive[fi] for v in F[fi]} - {b}
        for v in nb: push(b, v)
    return [tuple(F[fi]) for fi in range(len(F)) if alive[fi]]


def main(mods, car, targets=(24000, 12000, 3000)):
    path = os.path.join(mods, 'media', 'cabs', 'car_%s.cab' % car)
    files, root = addcar.cab_files(open(path, 'rb').read())
    key = next(k for k in files if k.lower().endswith('.carbin'))
    c = carbin.read(files[key])
    # the black insides (the converter's copies facing in, every vertex on one black texel of the atlas: 66,973 of
    # the Celica's 125,719): left out of the far levels, where nobody sees inside; simplified with the skin they
    # showed through it
    import forzaxpr as fx
    ak = next(k for k in files if k.lower().endswith('livery0hi.xpr'))
    t = fx.textures(files[ak])[0]
    atlas = fx.dxt(bytes(files[ak][t['start']:]), t['w'], t['h'], 5)
    def black(part, tris):
        uv = collections.Counter((part['verts'][i][10], part['verts'][i][11]) for tr in tris for i in tr)
        (u, v), n = uv.most_common(1)[0]
        px = atlas[min(t['h'] - 1, v * t['h'] // 65536), min(t['w'] - 1, u * t['w'] // 65536)]
        return n > 0.9 * sum(uv.values()) and int(px[:3].sum()) < 30 and px[3] > 200
    # (a black triangle is an inside where its normals face the car's middle: the windows are Body on the same black
    # texel, nfsu2forza.WINDOWS, facing out, and taken for insides the far levels had no glass; the insides are not
    # all on the skin's own places, inner=2's go through the panel)
    allv = np.array([v[:3] for part in c['parts'] for v in part['verts']], float)
    mid = (allv.min(0) + allv.max(0)) / 2
    fine, has, insides = {}, collections.defaultdict(set), 0
    for pi, part in enumerate(c['parts']):
        V = np.array([v[:6] for v in part['verts']], float)
        for s in part['subparts']:
            if s['id'] != 1: continue
            tr = nfsu2forza.strip_triangles(s['indices'])
            if tr and black(part, tr):
                T = np.array(tr)
                cen, nrm = V[T, :3].mean(1), V[T, 3:6].mean(1)
                inward = ((cen - mid) * nrm).sum(1) < 0
                insides += int(inward.sum())
                tr = [x for x, i in zip(tr, inward) if not i]
            fine.setdefault((pi, s['material']), []).extend(tr)
        for s in part['subparts']:
            if 2 <= s['id'] <= 4: has[s['id']].add((pi, s['material']))
    # a part with level 3 but no 4 gets one (the Celica's hood, bumpers and boot went down to level 3 only: from
    # far off the car drew without them)
    add4 = {pr for pr in has[3] if not any(q[0] == pr[0] for q in has[4])}
    has[4] |= add4
    print('black insides left out of the far levels: %d triangles' % insides)
    before = collections.Counter()
    for part in c['parts']:
        for s in part['subparts']: before[s['id']] += len(nfsu2forza.strip_triangles(s['indices']))
    # vertices at one place facing the same way welded to one (the converter splits a vertex at every texture, normal
    # and shading seam: as seams to hold, nearly every vertex was, and the collapses stopped at 84,626); the black
    # insides, at the same places facing in, stay apart. The far levels draw each welded vertex's first copy.
    welds, seams = {}, {}
    for pi, part in enumerate(c['parts']):
        at = collections.defaultdict(list)
        for i, v in enumerate(part['verts']): at[v[:3]].append(i)
        rep = {}
        for g in at.values():
            heads = []
            for i in g:
                n = np.array(part['verts'][i][3:6], float)
                h = next((j for j in heads if np.dot(n, np.array(part['verts'][j][3:6], float)) > 0), None)
                if h is None: heads.append(i); h = i
                rep[i] = h
        welds[pi], seams[pi] = rep, set()
    new = {}
    for lv, target in zip((2, 3, 4), targets):
        pairs = [pr for pr in has[lv] if pr in fine]
        total = sum(len(fine[pr]) for pr in pairs)
        r = min(1.0, target / max(total, 1))
        new[lv] = {}
        for pi, m in pairs:
            P = np.array([v[:3] for v in c['parts'][pi]['verts']], float)
            N = np.array([v[3:6] for v in c['parts'][pi]['verts']], float)
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            want = max(4, int(len(fine[(pi, m)]) * r))
            w = welds[pi]
            tw = [t for t in ((w[a], w[b], w[c_]) for a, b, c_ in fine[(pi, m)]) if len(set(t)) == 3]
            new[lv][(pi, m)] = simplify(P, tw, want, seams[pi], N) if want < len(tw) else fine[(pi, m)]
        print('level %d: %d -> %d triangles' % (lv, before[lv], sum(len(t) for t in new[lv].values())), flush=True)
    for pi, part in enumerate(c['parts']):
        for s in list(part['subparts']):
            if s['id'] == 3 and (pi, s['material']) in add4 and not any(x['id'] == 4 and x['material'] == s['material'] for x in part['subparts']):
                part['subparts'].append(dict(s, id=4, indices=list(s['indices'])))
    done = set()
    for pi, part in enumerate(c['parts']):
        for s in part['subparts']:
            k = (s['id'], pi, s['material'])
            if not (2 <= s['id'] <= 4 and (pi, s['material']) in new[s['id']]): continue
            t = [] if k in done else new[s['id']][(pi, s['material'])]  # (a pair's second subpart of the level: emptied, all in the first)
            done.add(k)
            s['indices'] = nfsu2forza.strip_long(t) if t else [0, 0, 0]
            s['prim'] = 6
    files[key] = carbin.write(c)
    open(path, 'wb').write(forzacab.pack(files, root))
    print(path)


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], tuple(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 else (24000, 12000, 3000))
