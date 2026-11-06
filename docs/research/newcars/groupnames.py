import sys, os, re, struct, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
k, pat = sys.argv[1], sys.argv[2]
d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
tx = nfsu.read_textures(os.path.join(d, 'TEXTURES.BIN'))
names = {h: t['name'] for h, t in tx.items()}
for p in ps:
    if not re.search(pat, p['name']): continue
    idx = [i for t in p['tris'] for i in t]
    agg = collections.OrderedDict()
    for g in p['groups']:
        ti, si = struct.unpack_from('<II', g, 0x1C); cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
        th = p['textures'][ti] if ti < len(p['textures']) else 0
        mat = p['materials'][si] if si < len(p.get('materials', [])) else ''
        V = np.array([p['verts'][i][:3] for i in idx[first:first + cnt] if i < len(p['verts'])])
        key = (names.get(th, '%08x' % th), mat)
        a = agg.setdefault(key, [0, V.min(0), V.max(0)]); a[0] += cnt // 3; a[1] = np.minimum(a[1], V.min(0)); a[2] = np.maximum(a[2], V.max(0))
    print(p['name'])
    for (t, m), (n, lo, hi) in agg.items(): print('   %-24s %-18s %6d  x %5.2f..%5.2f y %5.2f..%5.2f z %5.2f..%5.2f' % (t, m, n, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
