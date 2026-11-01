"""Turn a car's vertex normals to the side their triangles face (nfsu2forza.orient_normals),
in a cab already installed, for cars converted before the converter did it itself (1 Nov).
The game lights and reflects by the normals: turned in, they showed as dark patches, most
on light or metallic paint. The disc's own parts already agree, so only converted ones change.

  python tools/fixnormals.py [--dry-run] <car_X.cab> [...]

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


def fix(path, dry=False):
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
        if n:
            print('  %s: %d of %d' % (p['name'], n, len(p['verts'])))
            total += n
    print('%s: %d normals turned%s' % (os.path.basename(path), total, ' (dry run)' if dry else ''))
    if total and not dry:
        files[key] = carbin.write(car)
        open(path, 'wb').write(forzacab.pack(files, root))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--dry-run']
    if not args: raise SystemExit(__doc__)
    for a in args: fix(a, '--dry-run' in sys.argv)
