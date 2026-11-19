"""Moves the M3 GTR Most Wanted's body over its wheels (the game draws them at the physics hubs; the model has no rotors):
every part but the calipers shifted along the car, linearly between the hubs (front DF m, rear DR m forward), and up
UP m; the panels' hinge pivots (metres) with them.
python m3shift.py in.carbin out.carbin DF DR UP"""
import sys, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools'); sys.path.insert(0, r'E:\xbrt_scr\newcars')
import carbin, tyrecheck

src, dst, DF, DR, UP = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
c = carbin.read(open(src, 'rb').read())
wb, zc, *_ = tyrecheck.data('BMWM3GTRMW')
hf, hr = tyrecheck.hubs_of(c, wb, zc)  # (model units / 4096; 1.6 a metre)


def dz_m(z_units):  # the shift along the car in metres at model z (units / 4096)
    return DR + (DF - DR) * (z_units - hr) / (hf - hr)


n = 0
for p in c['parts']:
    if p['name'].startswith('caliper'): continue
    vs = []
    for v in p['verts']:
        v = list(v)
        z = v[2] / 4096
        v[2] = max(-32768, min(32767, int(round(v[2] + dz_m(z) * 1.6 * 4096))))
        v[1] = max(-32768, min(32767, int(round(v[1] + UP * 1.6 * 4096))))
        vs.append(tuple(v)); n += 1
    p['verts'] = vs
    ver, b = p['Pivots']
    if len(b) >= 16 and struct.unpack_from('<I', b, 0)[0] == 1:
        x, y, z = struct.unpack_from('<3f', b, 4)
        b = b[:4] + struct.pack('<3f', x, y + UP, z + dz_m(z * 1.6)) + b[16:]
        p['Pivots'] = (ver, b)
open(dst, 'wb').write(carbin.write(c))
print('moved %d verts: front %+.3f m, rear %+.3f m, up %+.3f m (hubs %.3f, %.3f)' % (n, DF, DR, UP, hf / 1.6, hr / 1.6))
