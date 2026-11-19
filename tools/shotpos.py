"""Where a screenshot was taken: the camera's position from the .cst saved
beside it (the runtime saves the 192 vertex constants, 4 floats each, at the
100th draw of the frame after a screenshot).

The world's draws take a position to the screen with four rows of constants,
a view and projection in one: x, y, w of the result are 0 at the camera, so
the camera is the point where those three rows (as planes) meet. Every run of
four rows is tried; those whose meeting point is in the world are printed.
On Pacific Shipyards the world's camera was rows 166-169 (the others found
are near the origin: the HUD's and the shadows').

  python tools/shotpos.py <shot.cst>... [--near x,z]   (--near: the closest first)
"""
import sys

import numpy as np


def candidates(c):
    out = []
    for r in range(0, 189):
        m = c[r:r + 4].astype(float)
        if not np.all(np.isfinite(m)) or np.abs(m).max() > 1e6: continue
        a = m[[0, 1, 3], :3]
        if abs(np.linalg.det(a)) < 1e-9: continue
        p = np.linalg.solve(a, -m[[0, 1, 3], 3])
        if not (np.abs(p[[0, 2]]).max() < 3000 and -50 < p[1] < 300): continue
        out.append((r, p))
    return out


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    near = None
    if '--near' in sys.argv:
        near = np.array([float(v) for v in sys.argv[sys.argv.index('--near') + 1].split(',')])
        args = [a for a in args if a != sys.argv[sys.argv.index('--near') + 1]]
    for path in args:
        c = np.fromfile(path, '<f4').reshape(192, 4)
        found = candidates(c)
        if near is not None: found.sort(key=lambda f: np.hypot(f[1][0] - near[0], f[1][2] - near[1]))
        else: found.sort(key=lambda f: f[0] != 166)
        print(path)
        for r, p in found[:8]:
            print('  rows %3d-%3d: camera at x %8.1f  y %6.1f  z %8.1f' % (r, r + 3, p[0], p[1], p[2]))
