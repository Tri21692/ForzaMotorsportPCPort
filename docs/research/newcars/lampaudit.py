"""The groups at each end of a source car (level A) with their sheet's size and mean colour, to see which sheet
covers a lamp (the user's 6 Nov screenshots: dark tail lights).   python lampaudit.py key front|rear"""
import sys, os, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np, nfsu
from nfsu2forza import nfsu_rgba
k, end = sys.argv[1], sys.argv[2]
d = os.path.join(r'E:\xbrt_scr\newcars', 'src', k); d = os.path.join(d, os.listdir(d)[0])
ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
tx = nfsu.read_textures(os.path.join(d, 'TEXTURES.BIN'))
roles = ['HEADLIGHT_LEFT', 'HEADLIGHT_RIGHT', 'BRAKELIGHT_LEFT', 'BRAKELIGHT_RIGHT', 'HEADLIGHT_GLASS_LEFT', 'HEADLIGHT_GLASS_RIGHT', 'BRAKELIGHT_GLASS_LEFT', 'BRAKELIGHT_GLASS_RIGHT', 'WINDOW_FRONT', 'BLACK', 'CHROME', 'GRILL', 'REAR_DEFROSTER', 'INTERIOR', 'SIDELIGHT']
rn = {nfsu.bhash(r): '[' + r + ']' for r in roles}
def desc(th):
    if th in tx and tx[th].get('data'):
        try:
            im = nfsu_rgba(tx[th]); m = im[..., :3].reshape(-1, 3)
            return '%-24s %08x %4dx%-4d rgb %3d %3d %3d sd %3d a<128 %.2f' % (tx[th]['name'][:24], th, im.shape[1], im.shape[0], *m.mean(0), m.std(0).mean(), (im[..., 3] < 128).mean())
        except Exception as e: return '%s %08x ?' % (tx[th]['name'], th)
    return '%-24s %08x (not in the pack)' % (rn.get(th, '?'), th)
allx = np.concatenate([np.array([v[0] for v in p['verts']]) for p in ps if p['verts']])
lo, hi = allx.min(), allx.max()
for p in ps:
    if not (p['name'].endswith('_A') or p['name'].endswith('BASE')) or 'DAMAGE' in p['name']: continue
    idx = [i for t in p['tris'] for i in t]
    for g in p['groups']:
        cnt, = struct.unpack_from('<I', g, 12); first, = struct.unpack_from('<I', g, 0x34); ti, si = struct.unpack_from('<II', g, 0x1C)
        V = np.array([p['verts'][i][:3] for i in idx[first:first + cnt] if i < len(p['verts'])])
        if not len(V): continue
        near = V[:, 0].mean() > hi - 0.5 if end == 'front' else V[:, 0].mean() < lo + 0.5
        if not near or V[:, 2].mean() < 0.35: continue
        th = p['textures'][ti] if ti < len(p['textures']) else 0
        mat = p['materials'][si] if si < len(p.get('materials', [])) else ''
        print('%-26s %-9s %5d y %+.2f..%+.2f z %.2f..%.2f  %s' % (p['name'][-26:], mat[:9], cnt // 3, V[:, 1].min(), V[:, 1].max(), V[:, 2].min(), V[:, 2].max(), desc(th)))
