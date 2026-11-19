import sys, os, re, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import nfsu
W = r'E:\xbrt_scr\newcars'
H = {nfsu.bhash(r): r for r in ('REAR_DEFROSTER', 'WINDOW_REAR', 'WINDOW_FRONT')}
for k in sorted(os.listdir(os.path.join(W, 'src'))):
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
    hits = {}
    for p in ps:
        n = p['name']
        if 'DAMAGE' in n or not (n.endswith('_A') or n.endswith('BASE')): continue
        for g in p['groups']:
            ti, si = struct.unpack_from('<II', g, 0x1C); cnt, = struct.unpack_from('<I', g, 12)
            t = H.get(p['textures'][ti] if ti < len(p['textures']) else 0)
            mat = p['materials'][si] if si < len(p.get('materials', [])) else ''
            if t: hits.setdefault(t, []).append('%s(%s,%d)' % (re.sub(r'^[^_]+_|_A$', '', n), mat[:14], cnt // 3))
    print('%-9s %s' % (k, '  '.join('%s: %s' % (t, ' '.join(v)) for t, v in hits.items())))
