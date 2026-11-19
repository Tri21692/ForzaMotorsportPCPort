import sys, os, re, struct, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
GLN = ('WINDOW_FRONT', 'WINDOW_REAR', 'WINDOW_LEFT_FRONT', 'WINDOW_RIGHT_FRONT', 'WINDOW_LEFT_REAR', 'WINDOW_RIGHT_REAR', 'REAR_DEFROSTER')
for k in sys.argv[1:]:
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
    tx = nfsu.read_textures(os.path.join(d, 'TEXTURES.BIN')) if os.path.exists(os.path.join(d, 'TEXTURES.BIN')) else {}
    names = {h: (t['name'] if isinstance(t, dict) else str(t)) for h, t in (tx.items() if isinstance(tx, dict) else [])}
    for r in GLN: names[nfsu.bhash(r)] = r
    body = [p for p in ps if re.search(r'_KIT00_BODY_A$', p['name'])]
    BV = np.array([v[:3] for p in body for v in p['verts']]) if body else np.zeros((0, 3))
    for p in ps:
        m = re.match(r'[^_]+_(KIT00_(?:FRONT|REAR)_WINDOW)_A$', p['name'])
        if not m: continue
        idx = [i for t in p['tris'] for i in t]
        agg = collections.OrderedDict()
        for g in p['groups']:
            ti, si = struct.unpack_from('<II', g, 0x1C); cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            nm = names.get(th, '%08x' % th)
            if nm in GLN: continue
            V = np.array([p['verts'][i][:3] for i in idx[first:first + cnt] if i < len(p['verts'])])
            a = agg.setdefault(nm, [0, V.min(0), V.max(0), 0])
            a[0] += cnt // 3; a[1] = np.minimum(a[1], V.min(0)); a[2] = np.maximum(a[2], V.max(0))
            if len(BV):  # share of these verts duplicated in the body (within 5 mm)
                sub = V[:: max(1, len(V) // 60)]
                a[3] = np.mean([np.min(np.abs(BV - v).sum(1)) < 0.005 for v in sub])
        print(k, m.group(1))
        for nm, (n, lo, hi, dup) in agg.items():
            if n > 20: print('   %-26s %6d  x %5.2f..%5.2f z %5.2f..%5.2f  in body %.0f%%' % (nm, n, lo[0], hi[0], lo[2], hi[2], dup * 100))
