"""Each converted add-on car's wheel arches against its hubs (the user's 6 Nov audit: wheels out of their arches).
The arch spans are read off the converted body's sides (hubcheck.spans: the lower edge raised over a wheel); the hubs
from build.log's "wheels:" line (the template's physics or rotors). Prints each arch's middle less its hub (+ = the
arch ahead of the wheel) and the arch's length against the tyre's diameter.   python archcheck.py [key ...]"""
import sys, os, re, importlib.util
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import carbin
from hubcheck import spans
W = r'E:\xbrt_scr\newcars'
spec = importlib.util.spec_from_file_location('nc', os.path.join(W, 'newcars.py')); nc = importlib.util.module_from_spec(spec)
_a = sys.argv; sys.argv = ['x']; spec.loader.exec_module(nc); sys.argv = _a


def main(keys):
    for key in keys or nc.CARS:
        out = os.path.join(W, 'out', key)
        try:
            c = carbin.read(open(os.path.join(out, 'car.carbin'), 'rb').read())
        except Exception as e:
            print('%-9s no carbin (%s)' % (key, e)); continue
        log = open(os.path.join(out, 'build.log'), errors='replace').read()
        m = re.search(r'hubs at ([-\d.]+), ([-\d.]+)', log) or re.search(r'template hubs from its physics: ([-\d.]+), ([-\d.]+)', log)
        rot = sorted({round((min(v[2] for v in q['verts']) + max(v[2] for v in q['verts'])) / 2 / 4096, 3) for q in c['parts'] if 'rotor' in q['name'].lower() and q['verts']})
        hubs = (float(m.group(1)), float(m.group(2))) if m else (rot and (max(rot), min(rot)))
        tyre = [q for q in c['parts'] if re.match(r'(tire|tyre|wheel)', q['name'], re.I) and q['name'].endswith('LOD1') and q['verts']]
        V = np.array([v[:3] for p in c['parts'] if p['name'].endswith('_LOD1') and re.match(r'(body|bumperFa?_|bumperRa?_)', p['name']) for v in p['verts']]) / 4096
        if not len(V): print('%-9s no body' % key); continue
        sp = spans(V)
        line = '%-9s hubs %s ' % (key, hubs and '%.2f %.2f' % hubs)
        for i, s in enumerate(sp):
            if s is None or not hubs: line += ' [%s arch ?]' % 'FR'[i]; continue
            line += ' [%s arch %.2f..%.2f mid %.2f, off %+.2f]' % ('FR'[i], s[0], s[1], s[2], s[2] - hubs[i])
        print(line + ('  tyres: %s' % ','.join(sorted({q['name'] for q in tyre}))[:60] if tyre else ''))


if __name__ == '__main__':
    main(sys.argv[1:])
