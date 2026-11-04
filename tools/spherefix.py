"""Every mesh's bounding sphere made to hold its vertices, in a track's visibility (QuickPreview1.pvs.ppw), in place.

The game leaves out a mesh whose sphere is off screen. The custom tracks' builders rewrite meshes far off as new
geometry (donors) and move their spheres, found by value (shipyardcircuit.sphere_at): where that search matched
another mesh's record, the donor kept its old sphere, kilometres away, and was drawn only while that place was in
view. The user, 4 Nov: "on Pacific the garage unloads the textures when viewing it at certain angles" (its tin
walls and roof gone looking aside or back from inside, the strip lights left floating). The ppw's records are
walked (fujitrack.ppw_records: one a mesh, in the model's order); a mesh of plain 24-byte vertices that has one
more than 0.5 m outside its sphere gets the sphere of its vertices' box (centre, farthest vertex). Meshes whose
spheres hold them are left as they are (the disc's buildings' are not their vertices' box).

  python tools/spherefix.py <scenery .res> <ppw> [--dry]
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fujitrack
import xb2


def fix(res, ppw, model=None, dry=False, quiet=False):
    """ppw (bytes) with the spheres fixed; returns (new ppw, [(mesh, buffer name, metres out)])."""
    names, _ = xb2.resources(bytes(res))
    if model is None: model = next(r[3] for r in names if r[0] == 'model_quickpreview')
    offs = fujitrack.ppw_records(bytes(ppw))
    n = struct.unpack_from('<I', res, model)[0]
    out, fixed = bytearray(ppw), []
    for i in range(min(n, len(offs))):
        try: info = fujitrack.mesh_info(res, names, model, i)
        except Exception: continue
        if not info: continue
        vb, nidx, vbytes, vsize = info[:4]
        if vsize != 24 or not vbytes: continue
        o = names[vb - 9][3]
        p = np.frombuffer(bytes(res[o:o + vbytes]), np.dtype([('p', '<f4', 3), ('r', 'V12')]))['p'].astype(float)
        if not len(p) or not np.isfinite(p).all() or np.abs(p).max() > 5000: continue
        r, cx, cy, cz = struct.unpack_from('<4f', out, offs[i])
        miss = float((np.linalg.norm(p - [cx, cy, cz], axis=1) - r).max())
        if miss <= 0.5: continue
        c = (p.min(0) + p.max(0)) / 2
        rad = float(np.linalg.norm(p - c, axis=1).max()) + 0.5
        if not dry: struct.pack_into('<4f', out, offs[i], rad, *c)
        fixed.append((i, names[vb - 9][0], miss))
        if not quiet: print('mesh %5d %-44s %6.0f m outside its sphere -> r %.0f at (%.0f, %.0f, %.0f)' % (i, names[vb - 9][0][:44], miss, rad, *c))
    return bytes(out), fixed


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if len(a) != 2: raise SystemExit(__doc__)
    res = open(a[0], 'rb').read()
    ppw = open(a[1], 'rb').read()  # (read before the file is opened to write: that empties it)
    new, fixed = fix(res, ppw, dry='--dry' in sys.argv)
    print('%d spheres %s' % (len(fixed), 'to fix' if '--dry' in sys.argv else 'fixed'))
    if fixed and '--dry' not in sys.argv: open(a[1], 'wb').write(new)
