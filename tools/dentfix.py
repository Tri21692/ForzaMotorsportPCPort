"""Dents for the converted cars (the user's, 16 Nov: "implementing the damage that the original game had").

A car part's Damage chunk is the part crumpled: a count, then a position and a normal (six int16) a vertex, which
the game morphs the part towards as it takes damage. The disc's cars have theirs modelled (their ends pushed in up
to half a metre). The converters (nfsu2forza.py and the tools on it) write it as a copy of the part undamaged, so a
converted car never dented, however hard it was hit.

Here every such part of a car in the mods folder (a Damage chunk with its vertices exactly the part's) gets a
crumple worked out from where each vertex is on the car:
  - the ends pushed in along the car, from 55% of its half length outwards, up to END m at the tip;
  - the flanks pushed in across it, from 70% of its half width, up to SIDE m;
  - all of it uneven, by a smooth pattern of the vertex's place alone, so vertices that share a place in two
    parts (a seam between panels) move alike and no gap opens.
Parts that already move (a donor's kept bumper, a disc car's copy) are left as they are. Run again, it changes
nothing more.

  python tools/dentfix.py <mods folder> [car ...]        (no cars: every car_*.cab there)
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import carbin
import forzacab

UNIT = 4096 / 0.6096     # model units a metre
END, SIDE = 0.26, 0.09   # metres, at the car's tip and at its flank's widest


def pattern(p):
    """0.45 to 1, smooth in space (p in metres)."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    n = (np.sin(7.1 * x + 1.3) * np.sin(5.3 * y + 0.7) + np.sin(4.7 * z + 2.1) * np.sin(6.1 * x - 0.4) + np.sin(8.3 * y - 1.1) * np.sin(3.9 * z + 0.2)) / 3
    return 0.725 + 0.275 * n


def crumple(v, lo, hi):
    """v (n x 3, model units) crumpled, for a car whose body spans lo..hi."""
    p = v / UNIT
    c, half = (lo + hi) / 2 / UNIT, (hi - lo) / 2 / UNIT
    r = p - c
    k = pattern(p)
    out = p.copy()
    az = np.clip((np.abs(r[:, 2]) / half[2] - 0.55) / 0.45, 0, 1) ** 1.5
    out[:, 2] -= np.sign(r[:, 2]) * END * az * k
    ax = np.clip((np.abs(r[:, 0]) / half[0] - 0.70) / 0.30, 0, 1) ** 1.5
    out[:, 0] -= np.sign(r[:, 0]) * SIDE * ax * k
    out[:, 1] += 0.05 * az * (k - 0.725) / 0.275   # the crushed end buckled up and down a little
    return np.clip(np.round(out * UNIT), -32767, 32767)


def fix(blob):
    car = carbin.read(blob)
    todo, allv = [], []
    for part in car['parts']:
        if not part['verts']: continue
        V = np.array([v[:3] for v in part['verts']], float)
        allv.append(V)
        d = part['Damage'][1]
        n = struct.unpack_from('<I', d)[0] if len(d) >= 4 else 0
        if n and n == len(part['verts']):
            D = np.frombuffer(d, '<i2', n * 6, 4).reshape(n, 6)
            if not np.abs(D[:, :3] - V).max(): todo.append((part, V, D))
    if not todo: return None, 0
    every = np.vstack(allv)
    lo, hi = np.percentile(every, 0.5, axis=0), np.percentile(every, 99.5, axis=0)
    for part, V, D in todo:
        new = D.copy()
        new[:, :3] = crumple(V, lo, hi).astype('<i2')
        part['Damage'] = (part['Damage'][0], struct.pack('<I', len(V)) + new.astype('<i2').tobytes())
    return carbin.write(car), len(todo)


def main(mods, only=()):
    cabs = os.path.join(mods, 'media', 'cabs')
    for f in sorted(os.listdir(cabs)):
        if not (f.lower().startswith('car_') and f.lower().endswith('.cab')): continue
        if only and f[4:-4].lower() not in [o.lower() for o in only]: continue
        path = os.path.join(cabs, f)
        files, root = addcar.cab_files(open(path, 'rb').read())
        key = next((k for k in files if k.lower().endswith('car.carbin')), None)
        if not key: continue
        try:
            new, n = fix(files[key])
        except Exception as e:
            print('%s: not read (%r), left' % (f, e))
            continue
        if new is None:
            print('%s: nothing flat' % f)
            continue
        files[key] = new
        open(path, 'wb').write(forzacab.pack(files, root))
        print('%s: %d parts given dents' % (f, n))


if __name__ == '__main__':
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[1]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[1])
    main(sys.argv[1], sys.argv[2:])
