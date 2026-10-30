"""A lap time estimate for a track and a class of car: the track's suggested line (its AI file,
ai\\drivatarv2\\<track>geometry.bin: waypoints every 2 m, fChiOptimal across the road) driven by a
point-mass car with a class's grip, power to weight and top speed. The speed through each
corner is what the grip allows on that line's radius; then forward from each point the car
accelerates as power allows, and backward from each corner it brakes in time. Used for the
career time trials' target times (careertimetrial.py), scaled to what a person drives.

  python tools/laptime.py <disc> <mods> [track...]      the estimate for each class
"""
import sys

import numpy as np

import addcar
import mlp

B = '\\'
G = 9.81

# class: (grip in g, power to weight W/kg at the wheels, top speed km/h, drag-limited)
CLASSES = {
    'D': (0.88, 55, 175),
    'C': (0.93, 75, 200),
    'B': (0.98, 100, 225),
    'A': (1.04, 130, 250),
    'S': (1.10, 175, 280),
    'GT': (1.30, 230, 290),
    'GTS': (1.45, 280, 305),
    'P1': (1.85, 400, 330),
}


def line(mega, track):
    """The suggested line's points (n, 2) on the ground and its heights, a closed loop (or not)."""
    g, _ = mlp.read(mega.files['ai' + B + 'drivatarv2' + B + track.lower() + 'geometry.bin'])
    w = np.stack([g['fWaypointX'], g['fWaypointY'], g['fWaypointZ']], 1).astype(float)
    nrm = np.stack([g['fNormalX'], g['fNormalY'], g['fNormalZ']], 1).astype(float)
    p = w + g['fChiOptimal'][:, None].astype(float) * nrm
    # the waypoints are (world x, z, y): the ground is X and Y
    return p[:, :2], p[:, 2], int(g['iType'][0]) == 0


def curvature(p, closed, span=6):
    """1 / radius at each point, from the circle through the points span either side, smoothed."""
    n = len(p)
    idx = np.arange(n)
    a = p[(idx - span) % n] if closed else p[np.clip(idx - span, 0, n - 1)]
    c = p[(idx + span) % n] if closed else p[np.clip(idx + span, 0, n - 1)]
    b = p
    ab, bc, ca = np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)
    cross = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    k = 2 * cross / np.maximum(ab * bc * ca, 1e-9)
    kern = np.ones(5) / 5
    k = np.convolve(np.concatenate([k[-2:], k, k[:2]]) if closed else np.pad(k, 2, mode='edge'), kern, 'valid')
    return k


def lap(mega, track, cls, start_speed=None):
    """Seconds round the line in a car of the class (from the line at speed for a circuit)."""
    mu, pw, vtop = CLASSES[cls]
    vtop /= 3.6
    p, h, closed = line(mega, track)
    seg = np.linalg.norm(np.diff(np.vstack([p, p[:1]]) if closed else p, axis=0), axis=1)
    k = curvature(p, closed)
    vmax = np.minimum(np.sqrt(mu * G / np.maximum(k, 1e-6)), vtop)
    n = len(p)
    v = vmax.copy()
    grade = np.diff(np.concatenate([h, h[:1]]) if closed else np.append(h, h[-1])) / np.maximum(np.append(seg, seg[-1])[:n], 0.1)

    def accel(vi, i):
        drive = min(pw / max(vi, 3.0), mu * G)            # power or traction limited
        return drive - (pw / vtop) * (vi / vtop) ** 2 - G * grade[i]  # drag: no more at the top speed

    for _ in range(2 if closed else 1):                    # twice round: the loop's speed carries over
        for i in range(n):
            j = (i + 1) % n
            if not closed and j == 0: break
            ds = seg[i] if i < len(seg) else seg[-1]
            # what is left of the grip after cornering drives or brakes
            lat = min(1.0, (v[i] ** 2 * k[i]) / (mu * G))
            room = np.sqrt(max(0.0, 1 - lat ** 2))
            a = min(accel(v[i], i), mu * G * room + 0.15 * G)
            v[j] = min(vmax[j], np.sqrt(max(v[i] ** 2 + 2 * a * ds, 0.0)))
        if not closed and start_speed is not None: v[0] = min(v[0], start_speed)
        for i in range(n - 1, -1, -1):
            j = (i + 1) % n
            if not closed and i == n - 1: continue
            ds = seg[i] if i < len(seg) else seg[-1]
            lat = min(1.0, (v[j] ** 2 * k[j]) / (mu * G))
            room = np.sqrt(max(0.0, 1 - lat ** 2))
            b = mu * G * max(room, 0.25) + (pw / vtop) * (v[j] / vtop) ** 2
            v[i] = min(v[i], np.sqrt(v[j] ** 2 + 2 * b * ds))
    vm = (v + np.roll(v, -1)) / 2 if closed else (v[:-1] + v[1:]) / 2
    return float(np.sum(seg[:len(vm)] / np.maximum(vm[:len(seg)], 1.0))), float(seg.sum())


if __name__ == '__main__':
    mega = addcar.Archive(sys.argv[1], sys.argv[2], 'Mega.ca2')
    tracks = sys.argv[3:] or ['Tsukuba', 'Lagunaseca', 'Silverstone', 'Nurburgring']
    for t in tracks:
        times = [lap(mega, t, c) for c in CLASSES]
        print('%-22s %6.0f m  ' % (t, times[0][1]) + '  '.join('%s %d:%04.1f' % (c, s // 60, s % 60) for c, (s, _) in zip(CLASSES, times)))
