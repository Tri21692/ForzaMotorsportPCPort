"""Every group near a car's front or rear lamps (its texture, material, triangles, box), level A."""
import sys, os, struct, re
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
W = r'E:\xbrt_scr\newcars'
k, end = sys.argv[1], sys.argv[2]  # front | rear
d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
tx = nfsu.read_textures(os.path.join(d, 'TEXTURES.BIN'))
roles = ['HEADLIGHT_LEFT', 'HEADLIGHT_RIGHT', 'BRAKELIGHT_LEFT', 'BRAKELIGHT_RIGHT', 'HEADLIGHT_GLASS_LEFT', 'HEADLIGHT_GLASS_RIGHT', 'BRAKELIGHT_GLASS_LEFT', 'BRAKELIGHT_GLASS_RIGHT', 'WINDOW_FRONT', 'BLACK', 'CHROME', 'GRILL', 'REAR_DEFROSTER', 'INTERIOR']
names = {h: t['name'] for h, t in tx.items()}; names.update({nfsu.bhash(r): '[' + r + ']' for r in roles})
allx = np.concatenate([np.array([v[0] for v in p['verts']]) for p in ps if p['verts']])
lo, hi = allx.min(), allx.max()
for p in ps:
    if not (p['name'].endswith('_A') or p['name'].endswith('BASE')) or 'DAMAGE' in p['name'] or 'DECAL' in p['name']: continue
    idx = [i for t in p['tris'] for i in t]
    for g in p['groups']:
        cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34); ti, si = struct.unpack_from('<II', g, 0x1C)
        V = np.array([p['verts'][i][:3] for i in idx[first:first + cnt] if i < len(p['verts'])])
        if not len(V): continue
        x = V[:, 0].mean()
        near = x > hi - 0.45 if end == 'front' else x < lo + 0.45
        if not near or V[:, 2].mean() < 0.3: continue
        th = p['textures'][ti] if ti < len(p['textures']) else 0
        mat = p['materials'][si] if si < len(p.get('materials', [])) else ''
        print('%-34s %-26s %-10s %5d  x %.2f..%.2f z %.2f..%.2f' % (p['name'][-34:], names.get(th, '%08x' % th), mat[:10], cnt // 3, V[:, 0].min(), V[:, 0].max(), V[:, 2].min(), V[:, 2].max()))
