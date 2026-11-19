"""The pit lanes for the runtime's Quick Race and Mayhem rules (runtime/hle_quickrace.c in_pits: no takedowns and no
"stuck" respawn of a car in the pits): <mods>/pitzones.txt, lines "<track folder> <x> <z>", a point every 5 m along each
track's pit splines (pitin, pitabort, pitout, pitparkin1-8, pitparkout1-8 of its scenery's model_quickpreview_splines).

  python tools/pitzones.py <disc> <mods folder>

Every track folder of the disc with those splines, and the mods folder's own tracks (track\\<name>\\hdd\\Partition4\\*.res:
Fuji Speedway's, read in place of its donor's)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xb2

STEP = 5.0
NAMES = ['pitin', 'pitabort', 'pitout'] + ['pitparkin%d' % k for k in range(1, 9)] + ['pitparkout%d' % k for k in range(1, 9)]


def points(res):
    names, _ = xb2.resources(res)
    out = []
    for r in names:
        if not r[0].startswith('vbuff_quickpreview_splines_') or r[0][len('vbuff_quickpreview_splines_'):-4] not in NAMES: continue
        n = (r[4] + 4) // 16
        P = np.frombuffer(res, '<f4', count=3 * n, offset=r[3]).reshape(-1, 3).astype(float)[:, [0, 2]]
        if len(P) < 2 or not np.isfinite(P).all(): continue
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        t = np.arange(0, s[-1] + STEP / 2, STEP)
        out.append(np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], 1))
    if not out: return np.zeros((0, 2))
    P = np.vstack(out)
    keep = []  # (thinned: the stalls' splines share the lane)
    cells = set()
    for p in P:
        c = (int(p[0] // 3), int(p[1] // 3))
        if c in cells: continue
        cells.add(c); keep.append(p)
    return np.array(keep)


def main(disc, mods):
    rows = []
    tracks = os.path.join(disc, 'media', 'tracks')
    own = {}
    tdir = os.path.join(mods, 'track')
    for t in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        d = os.path.join(tdir, t, 'hdd', 'Partition4')
        for f in os.listdir(d) if os.path.isdir(d) else []:
            if f.lower().endswith('.res'): own[t] = open(os.path.join(d, f), 'rb').read()
    for t in sorted(os.listdir(tracks)):
        f = next((os.path.join(tracks, t, x) for x in os.listdir(os.path.join(tracks, t)) if x.lower() == 'quickpreview1.xb2'), None)
        if not f or t in own: continue
        try: P = points(bytes(xb2.unpack(f)))
        except Exception as e:
            print('%-24s unread (%s)' % (t, e)); continue
        if len(P): rows += [(t, p) for p in P]; print('%-24s %4d points' % (t, len(P)))
    for t, res in own.items():
        P = points(res)
        if t.lower().startswith('vancouver'): P = P[:0]   # (the Pacific Shipyards Circuit: Pacific Shipyards' scenery, no pit lane on its loop)
        if len(P): rows += [(t, p) for p in P]
        print('%-24s %4d points (the mods folder\'s)' % (t, len(P)))
    open(os.path.join(mods, 'pitzones.txt'), 'w').write(''.join('%s %.1f %.1f\n' % (t, p[0], p[1]) for t, p in rows))
    print('%s: %d points' % (os.path.join(mods, 'pitzones.txt'), len(rows)))


if __name__ == '__main__':
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
