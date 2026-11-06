"""Glass (WINDOW* material groups) in each source car's BASE_A / KIT00 parts: triangles and their x (fwd) range, and
how many of BASE's glass triangles have no window-part triangle within 3 cm (glass only BASE has)."""
import sys, os, re, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
def glass_tris(p):
    out = []
    idx = [i for t in p['tris'] for i in t]
    for g in p['groups']:
        cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
        ti, si = struct.unpack_from('<II', g, 0x1C)
        mat = p['materials'][si] if si < len(p.get('materials', [])) else ''
        if not mat.upper().startswith('WINDOW') or mat.upper().endswith('_MASK'): continue
        for j in range(first, first + cnt - 2, 3):
            t = idx[j:j + 3]
            if max(t) < len(p['verts']): out.append([p['verts'][i][:3] for i in t])
    return np.array(out).reshape(-1, 3, 3)
for k in (sys.argv[1:] or sorted(os.listdir(os.path.join(W, 'src')))):
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    try: ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
    except Exception as e: print(k, 'read failed'); continue
    base = [p for p in ps if re.search(r'_BASE(_A)?$', p['name'])]
    wins = [p for p in ps if 'KIT00' in p['name'] and p['name'].endswith('_A') and 'DAMAGE' not in p['name']]
    B = np.concatenate([glass_tris(p) for p in base]) if base else np.zeros((0, 3, 3))
    Wt = [(p['name'].split('KIT00_')[1], glass_tris(p)) for p in wins]
    Wt = [(n, t) for n, t in Wt if len(t)]
    allw = np.concatenate([t for _, t in Wt]) if Wt else np.zeros((0, 3, 3))
    only = 0; xr = []
    if len(B):
        wc = allw.mean(1) if len(allw) else np.zeros((0, 3))
        for t in B:
            c = t.mean(0)
            if not len(wc) or np.min(np.linalg.norm(wc - c, axis=1)) > 0.03:
                only += 1; xr.append(c[0])
    print('%-9s BASE glass %4d tris, %4d only in BASE (x %s)  windows: %s' % (k, len(B), only,
          '%.2f..%.2f' % (min(xr), max(xr)) if xr else '-', ' '.join('%s:%d' % (n.replace('_A', ''), len(t)) for n, t in Wt)))
