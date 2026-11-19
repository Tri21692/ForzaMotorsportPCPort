import sys, os, re, struct, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
k = sys.argv[1]; pat = sys.argv[2] if len(sys.argv) > 2 else r'_BASE(_A)?$'
d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
roles = ['WINDOW_FRONT', 'WINDOW_REAR', 'WINDOW_LEFT_FRONT', 'WINDOW_RIGHT_FRONT', 'WINDOW_LEFT_REAR', 'WINDOW_RIGHT_REAR', 'REAR_DEFROSTER', 'WINDSHIELD']
pre = ps[0]['name'].split('_')[0]
rh = {nfsu.bhash(r): r for r in roles}
for p in ps:
    if not re.search(pat, p['name']): continue
    idx = [i for t in p['tris'] for i in t]
    agg = collections.OrderedDict()
    for g in p['groups']:
        cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34)
        ti, si = struct.unpack_from('<II', g, 0x1C)
        th = p['textures'][ti] if ti < len(p['textures']) else 0
        mat = p['materials'][si] if si < len(p.get('materials', [])) else '?'
        V = np.array([p['verts'][i][:3] for i in idx[first:first + cnt] if i < len(p['verts'])])
        key = (rh.get(th, '%08x' % th), mat)
        a = agg.setdefault(key, [0, 9, -9])
        a[0] += cnt // 3; a[1] = min(a[1], V[:, 0].min()); a[2] = max(a[2], V[:, 0].max())
    print(p['name'])
    for (t, m), (n, x0, x1) in agg.items(): print('   %-20s %-24s %5d  x %.2f..%.2f' % (t, m, n, x0, x1))
