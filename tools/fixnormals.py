"""Turn a car's vertex normals to the side their triangles face (nfsu2forza.orient_normals),
in a cab already installed, for cars converted before the converter did it itself (1 Nov).
The game lights and reflects by the normals: turned in, they showed as dark patches, most
on light or metallic paint. The disc's own parts already agree, so only converted ones change.

  python tools/fixnormals.py [--dry-run] [--smooth] <car_X.cab> [...]

--smooth: every part's normals made again from its surface too (nfsu2forza.smooth_normals), for a
car thinned in Blender (the MX-5 RADBUL, the SC63).
--shade: the outside parts' shading bytes from their height and facing (nfsu2forza.shade_vertices),
for a converted car (they were the template's nearest vertex's: patchy reflections).

Rewrites only the cab's car.carbin, in place (keep a copy). Prints each changed part.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin
import forzacab
import nfsu2forza


SHARE = 0.05  # a part is changed only when more of its normals than this face away (the disc's: 3% at most)


def fix(path, dry=False, smooth=False, shade=False):
    files, root = addcar.cab_files(open(path, 'rb').read())
    key = next(k for k in files if k.lower().endswith('car.carbin'))
    car = carbin.read(files[key])
    total = 0
    for p in car['parts']:
        keep = (p['verts'], p['Damage'])
        n = nfsu2forza.orient_normals(p)
        if n and n < SHARE * len(p['verts']):  # a few on a disc part (a crease made so): left as made
            p['verts'], p['Damage'] = keep
            n = 0
        if smooth and p['name'].endswith('_LOD1') and not p['name'].startswith(('interior', 'steering')):
            n += nfsu2forza.smooth_normals(p)
        if n:
            print('  %s: %d of %d' % (p['name'], n, len(p['verts'])))
            total += n
    if shade:
        outside = [p for p in car['parts'] if p['name'].endswith('_LOD1') and not p['name'].startswith(nfsu2forza.CABIN)]
        total += nfsu2forza.shade_vertices(outside)
    print('%s: %d normals and shades changed%s' % (os.path.basename(path), total, ' (dry run)' if dry else ''))
    if total and not dry:
        files[key] = carbin.write(car)
        open(path, 'wb').write(forzacab.pack(files, root))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a not in ('--dry-run', '--smooth', '--shade')]
    if not args: raise SystemExit(__doc__)
    for a in args: fix(a, '--dry-run' in sys.argv, '--smooth' in sys.argv, '--shade' in sys.argv)
