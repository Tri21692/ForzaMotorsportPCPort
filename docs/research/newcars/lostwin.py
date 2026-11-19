"""Non-glass triangles in each car's window parts that its MERGE plan does not take into the body: lost (window
slots keep only glass)."""
import sys, os, re, struct, importlib.util
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import nfsu
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec); sys.argv = ['x']; spec.loader.exec_module(nc)
GL = {nfsu.bhash(r) for r in ('WINDOW_FRONT', 'WINDOW_REAR', 'WINDOW_LEFT_FRONT', 'WINDOW_RIGHT_FRONT', 'WINDOW_LEFT_REAR', 'WINDOW_RIGHT_REAR', 'REAR_DEFROSTER')}
for k in nc.CARS:
    d = os.path.join(W, 'src', k); d = os.path.join(d, os.listdir(d)[0])
    ps = nfsu.read(os.path.join(d, 'GEOMETRY.BIN'))
    merged = set(nc.MERGE.get(k, [])) | set(nc.DROP.get(k, []))
    out = []
    for p in ps:
        m = re.match(r'[^_]+_(KIT00_(?:FRONT|REAR)(?:_LEFT|_RIGHT)?_WINDOW)_A$', p['name'])
        if not m or m.group(1) in merged: continue
        n = 0
        for g in p['groups']:
            ti, si = struct.unpack_from('<II', g, 0x1C); cnt, = struct.unpack_from('<I', g, 12)
            th = p['textures'][ti] if ti < len(p['textures']) else 0
            mat = (p['materials'][si] if si < len(p.get('materials', [])) else '').upper()
            if th not in GL and not mat.startswith('WINDOW'): n += cnt // 3
        if n: out.append('%s:%d' % (m.group(1).replace('KIT00_', ''), n))
    print('%-9s %s' % (k, ' '.join(out)))
