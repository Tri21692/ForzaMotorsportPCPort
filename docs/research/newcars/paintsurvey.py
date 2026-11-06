"""Per source car: the level-A parts holding painted (SKIN1) triangles, and their share; KIT00_BODY's first."""
import sys, os, re, struct as st, collections
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import nfsu, nfsu2forza
W = r'E:\xbrt_scr\newcars'
for k in sorted(os.listdir(os.path.join(W, 'src'))) if len(sys.argv) < 2 else sys.argv[1:]:
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
    pre = os.path.basename(d)
    skin = {nfsu2forza.bhash(pre + '_SKIN1'), nfsu2forza.bhash('SKIN1')}
    tex = nfsu.read_textures(os.path.join(d, 'TEXTURES.BIN'))
    for h, t in tex.items():
        if t['name'].upper().endswith('_SKIN1'): skin.add(h)
    c = collections.Counter(); tot = collections.Counter()
    for p in ps:
        if not (p['name'].endswith('_A') or p['name'].endswith('_BASE')): continue
        if 'KIT00' not in p['name'] and 'BASE' not in p['name']: continue
        b = re.sub(r'^.*?_(KIT00_|BASE)', r'\1', p['name'])[:-2] if p['name'].endswith('_A') else 'BASE'
        for g in p['groups']:
            ti, = st.unpack_from('<I', g, 0x1C); cnt, = st.unpack_from('<I', g, 12)
            h = p['textures'][ti] if ti < len(p['textures']) else 0
            tot[b] += cnt // 3
            if h in skin: c[b] += cnt // 3
    s = sum(c.values()) or 1
    print('%-9s %s' % (k, ' '.join('%s:%d%%(%d)' % (n.replace('KIT00_', ''), 100 * v / s, v) for n, v in c.most_common() if v)))
