"""A track's AI files (media\\AI\\DrivatarV2, in Mega.ca2 as ai\\drivatarv2\\...) made from its edge
splines: what the game measures a car's progress round the track by (laps, the timer, the race
HUD's map, the suggested line), whether or not AI drivers race there (Tokyo has aiReady="false"
and still has them; a track without them counts no laps).

  <name>geometry.bin      MLP: iCRC uint32 x 6, iLength int32, iType int8 (0 a circuit, 1 point to
                          point); per waypoint, every 2 m from the lap line the way round: its
                          position (the world's x, z, y), the road's half width as a vector to the
                          left of the way round (fNormal), and across the road in units of it
                          (chi: +1 the left edge, -1 the right) the walls, the kerbs and the
                          suggested line
  <name>segmentation.bin  MLP: the lap cut into straights and turns: start, apex and end waypoints,
                          length, peak curvature, a turn type
  tracklist.bin           MLP: the tracks with AI files, by name

The six CRCs are not plain CRC-32s of the splines (not worked out); Pacific Shipyards II's are
used. Turn types are a guess (0 straight, 2 a turn, 7 a hairpin).
"""
import numpy as np

import mlp

B = '\\'
STEP = 2.0


def waypoints(centre, half):
    """Every STEP m round the closed loop `centre` ((x, y, z) from the lap line the way round),
    with the road's half width there: (points, half widths)."""
    closed = np.vstack([centre, centre[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(closed[:, [0, 2]], axis=0), axis=1))])
    n = int(round(s[-1] / STEP))
    want = np.linspace(0, s[-1], n, endpoint=False)
    p = np.stack([np.interp(want, s, closed[:, k]) for k in range(3)], 1)
    h = np.interp(want, s, np.concatenate([half, half[:1]]))
    return p, h


def racing_line(p, h, margin=0.25, rounds=400):
    """A suggested line: across the road (chi, -1..1), smoothed toward the straightest path that
    stays `margin` (of the half width) inside the edges."""
    t = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    left = np.stack([-t[:, 2], t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    xz = p[:, [0, 2]]
    chi = np.zeros(len(p))
    for _ in range(rounds):
        q = xz + left * (chi * h)[:, None]
        mid = (np.roll(q, 1, 0) + np.roll(q, -1, 0)) / 2
        chi = np.clip(((mid - xz) * left).sum(1) / h, -1 + margin, 1 - margin)
    return chi


def curvature(p, smooth=5):
    """The waypoints' curvature (1/m, + to the left): the turn between the two steps before a point and the
    two after it, over the two steps between their middles; the mean of `smooth` points. (segmentation's
    own is half this: it divides by 4 steps.)"""
    xz = p[:, [0, 2]]
    a = np.arctan2(np.roll(xz, -2, 0)[:, 1] - xz[:, 1], np.roll(xz, -2, 0)[:, 0] - xz[:, 0])
    b = np.arctan2(xz[:, 1] - np.roll(xz, 2, 0)[:, 1], xz[:, 0] - np.roll(xz, 2, 0)[:, 0])
    step = np.linalg.norm(np.roll(xz, -1, 0) - xz, axis=1).mean()
    k = np.angle(np.exp(1j * (a - b))) / (2 * step)
    m = smooth // 2
    return np.convolve(np.concatenate([k[-m:], k, k[:m]]), np.ones(smooth) / smooth, 'valid') if m else k


def rounded(p, h):
    """Waypoints rounded off: each the weighted mean of the five round it, then set every equal step again
    from the first. The scenery's edge points are 3.2 m apart, and waypoints laid 2 m apart along the
    straight lines between them turn at those only: the normals, and the suggested line laid along them,
    jumped there (17 Nov)."""
    w = np.array([1, 4, 6, 4, 1], float) / 16
    q = sum(w[j] * np.roll(p, 2 - j, 0) for j in range(5))
    g = sum(w[j] * np.roll(h, 2 - j) for j in range(5))
    closed = np.vstack([q, q[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(closed[:, [0, 2]], axis=0), axis=1))])
    want = np.linspace(0, s[-1], len(p), endpoint=False)
    return np.stack([np.interp(want, s, closed[:, k]) for k in range(3)], 1), np.interp(want, s, np.concatenate([g, g[:1]]))


def racing_line_wide(margin=1.8, most=0.83, shortest=0.002, sweeps=300, least=1.15):
    """A suggested line that uses the road: across it (chi) the path of least bending, a little of the
    shortest path with it, kept `margin` m inside the edges (no further out than `most` of the half
    width: the disc's lines reach 0.83): wide into a corner, in to its apex, out wide again. racing_line's
    is the shortest path, hugging the inside of every corner, 24 to 44 km/h round them (the audit of 17
    Nov). For geometry's `line`. The least squares of the line's second differences, the points at their
    limits held and the rest solved, those that would come in off their limits let go, until none would;
    then relaxed point by point."""
    def line(p, h, left):
        n = len(p)
        xz = p[:, [0, 2]]
        N = left * h[:, None]
        lim = np.clip(1 - margin / h, 0.1, most)
        # and its points no nearer each other than `least` m: inside a tight bend the edge's points
        # stand nearly still (the normals fan out from it), and a line laid near that edge bunched up
        # there; no nearer it than where a step of the line is still `least` m
        lims = {}
        for sg in (1, -1):
            E = xz + sg * N
            e = (np.linalg.norm(np.roll(E, -1, 0) - E, axis=1) + np.linalg.norm(E - np.roll(E, 1, 0), axis=1)) / 2
            st = (np.linalg.norm(np.roll(xz, -1, 0) - xz, axis=1) + np.linalg.norm(xz - np.roll(xz, 1, 0), axis=1)) / 2
            c = np.where(e < least, (st - least) / np.maximum(st - e, 1e-6), 1.0)
            c = np.minimum(c, np.minimum(np.roll(c, 1), np.roll(c, -1)))
            lims[sg] = np.minimum(lim, np.clip(c, 0.05, 1.0))
        hi, lo = lims[1], -lims[-1]
        I = np.eye(n)
        D2 = np.roll(I, -1, 1) - 2 * I + np.roll(I, 1, 1)
        D1 = np.roll(I, -1, 1) - I
        H, g = np.zeros((n, n)), np.zeros(n)
        for c in (0, 1):
            for D, w in ((D2, 1.0), (D1, shortest)):
                M = D * N[:, c][None, :]
                H += w * M.T @ M
                g += w * M.T @ (D @ xz[:, c])
        x = np.zeros(n)
        held = np.zeros(n, bool)
        for _ in range(400):
            f = ~held
            x[f] = np.linalg.solve(H[np.ix_(f, f)], -(g[f] + H[np.ix_(f, held)] @ x[held]))
            over = f & ((x > hi + 1e-9) | (x < lo - 1e-9))
            x = np.clip(x, lo, hi)
            if over.any(): held |= over; continue
            # the held points that would rather come in off their limit: let go (the worst of them first)
            grad = H @ x + g
            want = np.where(held & (x >= hi - 1e-9), grad, np.where(held & (x <= lo + 1e-9), -grad, 0.0))
            if want.max() <= 1e-9: break
            held &= ~(want >= 0.5 * want.max())
        d = np.diag(H)
        for _ in range(sweeps):
            for c in range(3):  # (each point's best place given the rest; every third at once: they share no term)
                i = np.arange(c, n - (n % 3 and 2), 3)
                x[i] = np.clip(x[i] - (g[i] + H[i] @ x) / d[i], lo[i], hi[i])
            for i in range(n - (n % 3 and 2), n):
                x[i] = np.clip(x[i] - (g[i] + H[i] @ x) / d[i], lo[i], hi[i])
        return x
    return line


def edge_waypoints(left, right):
    """Waypoints from the track's two edge lines (closed, point for point: the scenery's edge splines):
    every STEP m along the middle between them, each with the vector from it to the left edge, its
    normal, not square to the way round where the edges are not (inside a tight bend one edge stands
    still while the other goes round: the disc's normals lean as much as 30 degrees, New York's). The
    edges' points are 3.2 m apart: both rounded off between (as rounded) and set again.
    (points, normals (x, z), half widths)."""
    def along(l, r, n=None):
        mid = (l + r) / 2
        closed = np.vstack([mid, mid[:1]])
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(closed[:, [0, 2]], axis=0), axis=1))])
        want = np.linspace(0, s[-1], n or int(round(s[-1] / STEP)), endpoint=False)
        f = lambda e: np.stack([np.interp(want, s, np.concatenate([e[:, k], e[:1, k]])) for k in range(3)], 1)
        return f(l), f(r)
    l, r = along(np.asarray(left, float), np.asarray(right, float))
    w = np.array([1, 4, 6, 4, 1], float) / 16
    l, r = (sum(w[j] * np.roll(e, 2 - j, 0) for j in range(5)) for e in (l, r))
    l, r = along(l, r, len(l))
    N = ((l - r) / 2)[:, [0, 2]]
    return (l + r) / 2, N, np.linalg.norm(N, axis=1)


def geometry(centre, half, crc, circuit=True, line=None, round_off=False, edges=None):
    p, h = waypoints(centre, half)
    if round_off:
        # and no wider than the road's own bend lets it be: its edges, a half width along the normals,
        # cross where the half width is more than the bend's radius (the line knotted there, 17 Nov)
        p, h = rounded(p, h)
        h = np.minimum(h, 0.9 / np.maximum(np.abs(curvature(p)), 1e-6))
    t = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    left = np.stack([-t[:, 2], t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    if edges is not None:  # the edges themselves: the waypoints between them, the normals across
        p, N, h = edge_waypoints(*edges)
        left = N / h[:, None]
    n = len(p)
    one = np.ones(n, '<f4')
    return mlp.write([
        ('iCRC', 'uint32', np.asarray(crc, '<u4')),
        ('iLength', 'int32', [n]),
        ('iType', 'int8', [0 if circuit else 1]),
        ('fWaypointX', 'float', p[:, 0]), ('fWaypointY', 'float', p[:, 2]), ('fWaypointZ', 'float', p[:, 1]),
        ('fNormalX', 'float', left[:, 0] * h), ('fNormalY', 'float', left[:, 1] * h), ('fNormalZ', 'float', np.zeros(n)),
        ('fLeftWallChi', 'float', one), ('fRightWallChi', 'float', -one),
        ('fChiOptimal', 'float', racing_line(p, h) if line is None else line(p, h, left)),
        ('fLeftCurbChi', 'float', one), ('fRightCurbChi', 'float', -one),
    ]), p, h


def segmentation(p, turn=0.012, hairpin=0.08):
    """The lap's straights and turns from the waypoints' curvature (1/m, + to the left)."""
    n = len(p)
    xz = p[:, [0, 2]]
    a = np.arctan2(np.roll(xz, -2, 0)[:, 1] - xz[:, 1], np.roll(xz, -2, 0)[:, 0] - xz[:, 0])
    b = np.arctan2(xz[:, 1] - np.roll(xz, 2, 0)[:, 1], xz[:, 0] - np.roll(xz, 2, 0)[:, 0])
    k = (np.angle(np.exp(1j * (a - b)))) / (4 * STEP)
    k = np.convolve(np.concatenate([k[-5:], k, k[:5]]), np.ones(11) / 11, 'valid')
    bent = np.abs(k) > turn
    # start the cut where a straight starts, so no segment wraps the lap's end
    first = next((i for i in range(n) if bent[i - 1] and not bent[i]), 0)
    order = [(first + i) % n for i in range(n)]
    segs, cur = [], [order[0]]
    for i in order[1:]:
        if bent[i] != bent[cur[0]]:
            segs.append(cur); cur = [i]
        else: cur.append(i)
    segs.append(cur)
    start, apex, end, length, peak, kind = [], [], [], [], [], []
    for s in segs:
        start.append(s[0]); end.append((s[-1] + 1) % n); length.append(len(s))
        if bent[s[0]]:
            j = max(s, key=lambda i: abs(k[i]))
            apex.append(j); peak.append(float(k[j])); kind.append(7 if abs(k[j]) > hairpin else 2)
        else:
            apex.append(s[len(s) // 2]); peak.append(0.0); kind.append(0)
    return mlp.write([
        ('iNumSegments', 'int32', [len(segs)]), ('iTrackLength', 'int32', [n]),
        ('iStart', 'int32', start), ('iApex', 'int32', apex), ('iEnd', 'int32', end), ('iLength', 'int32', length),
        ('fPeakCurvature', 'float', peak), ('iTurnType', 'int32', kind),
    ]), len(segs)


MIN_TURN = {5: 34, 7: 30, 2: 26, -1: 16}   # a turn segment's least length by its type, waypoints (the disc's: 68, 58, 50, 32 m)


def segmentation_stock(p, turn=0.016, join=20, share=30, minor=15.0):
    """The lap cut the way the disc's are (the audit of 17 Nov, against all 23 of its tracks): a bend is
    the waypoints whose curvature (1/m, + to the left) is over `turn`, bends of one hand within `join`
    waypoints one bend; by the angle it turns through a hairpin (type 5: 120 degrees and more; the disc's
    7 is a street corner), a tight right-angle corner (7: 60 degrees and more within 36 m), a corner (2:
    40 and more), a kink (-1: `minor` and more), or nothing (the straight's). A turn's segment reaches
    from before the bend to after it (the braking and the exit), no shorter than the disc's of its type
    (MIN_TURN); a straight left shorter than `share` waypoints between two turns is shared out between
    them. iLength is end - start + 1, as the disc's. (segmentation's: types 0, 2 and 7, turn segments 8
    to 28 m long, straights with real bends in them.)"""
    n = len(p)
    k = curvature(p, 11)
    k5 = curvature(p, 5)
    bent = np.abs(k) > turn
    first = next((i for i in range(n) if bent[i - 1] and not bent[i]), 0)
    order = [(first + i) % n for i in range(n)]
    runs, cur = [], []
    for i in order:  # the bends, as waypoints in order from `first` (a straight's start: none wraps it)
        if bent[i] and cur and np.sign(k[i]) == np.sign(k[cur[-1]]) and (i - cur[-1]) % n == 1: cur.append(i)
        elif bent[i]:
            if cur: runs.append(cur)
            cur = [i]
    if cur: runs.append(cur)
    pos = {i: j for j, i in enumerate(order)}   # a waypoint's place from `first`
    merged = []
    for r in runs:
        if merged and np.sign(k[r[0]]) == np.sign(k[merged[-1][0]]) and pos[r[0]] - pos[merged[-1][-1]] <= join:
            merged[-1] = [order[j] for j in range(pos[merged[-1][0]], pos[r[-1]] + 1)]
        else: merged.append(r)
    turns = []
    for r in merged:
        deg = abs(float(np.degrees(np.sum(k[r]) * STEP)))
        kind = 5 if deg >= 120 else 7 if deg >= 60 and len(r) <= 18 else 2 if deg >= 40 else -1 if deg >= minor else 0
        if not kind: continue
        a, b = pos[r[0]] - 4, pos[r[-1]] + 4   # (the curvature is a mean of 11: the bend begins a little before)
        more = MIN_TURN[kind] - (b - a + 1)
        if more > 0: a, b = a - (more + 1) // 2, b + more // 2
        apex = max(r, key=lambda i: abs(k5[i]))
        turns.append([a, b, apex, float(k5[apex]), kind])
    for t0, t1 in zip(turns[:-1], turns[1:]):  # too short a straight between two: theirs, half each
        if t1[0] - t0[1] - 1 < share:
            cut = min(max((t0[1] + t1[0] + 1) // 2, pos[t0[2]] + 2), pos[t1[2]] - 2)
            t0[1], t1[0] = cut - 1, cut
    if turns and turns[0][0] + n - turns[-1][1] - 1 < share:
        cut = (turns[-1][1] + turns[0][0] + n + 1) // 2
        turns[-1][1], turns[0][0] = cut - 1, cut - n
    segs = []   # (start, apex, end, peak, type) in places from `first`, end exclusive
    at = turns[0][0] if turns else 0
    for a, b, apex, peak, kind in turns:
        if a > at: segs.append((at, (at + a) // 2, a, 0.0, 0))
        segs.append((a, pos[apex], b + 1, peak, kind))
        at = b + 1
    end = (turns[0][0] if turns else 0) + n
    if at < end: segs.append((at, (at + end) // 2, end, 0.0, 0))
    w = lambda j: order[j % n]
    return mlp.write([
        ('iNumSegments', 'int32', [len(segs)]), ('iTrackLength', 'int32', [n]),
        ('iStart', 'int32', [w(a) for a, _, _, _, _ in segs]), ('iApex', 'int32', [w(x) for _, x, _, _, _ in segs]),
        ('iEnd', 'int32', [w(b) for _, _, b, _, _ in segs]), ('iLength', 'int32', [b - a + 1 for a, _, b, _, _ in segs]),
        ('fPeakCurvature', 'float', [c for _, _, _, c, _ in segs]), ('iTurnType', 'int32', [t for _, _, _, _, t in segs]),
    ]), len(segs)


def audio_spline(points, geometry_ref, audio_ref):
    """The track's AudioSpline.bin (media\tracks\<name>): u32 12, u32 24, u32 n, then per AI waypoint
    24 bytes of sound settings; the game walks it by the AI's waypoints, so it has to have as many.
    Each of `points` (the waypoints, (x, y, z)) gets the record of the nearest waypoint of a track
    whose geometry and audio spline are given (MLP bytes, AudioSpline bytes)."""
    import struct
    g, _ = mlp.read(geometry_ref)
    ref = np.column_stack([g['fWaypointX'], g['fWaypointY']])  # the world's x, z
    n_ref = struct.unpack_from('<I', audio_ref, 8)[0]
    assert n_ref == len(ref), (n_ref, len(ref))
    recs = [audio_ref[12 + 24 * i:12 + 24 * (i + 1)] for i in range(n_ref)]
    out = [struct.pack('<III', 12, 24, len(points))]
    for x, y, z in points:
        out.append(recs[int(np.argmin(np.hypot(ref[:, 0] - x, ref[:, 1] - z)))])
    return b''.join(out)


def world_sounds(xml, points, half, keep=60.0):
    """A track data folder's audioreflections.xml or audioambient.xml (WORLDSOUNDS: TOTALWAYPOINTS,
    then SOUNDs placed by AI waypoint) remade for another track's waypoints: the total its count,
    each sound within `keep` m of its road placed at its nearest waypoint (chi across the road),
    the rest dropped. Sounds placed past the end of the waypoints call through nothing."""
    import re
    xz = points[:, [0, 2]]
    t = np.roll(xz, -1, 0) - np.roll(xz, 1, 0)
    left = np.stack([-t[:, 1], t[:, 0]], 1); left /= np.linalg.norm(left, axis=1)[:, None]
    out = []
    for m in re.finditer(r'<SOUND [^>]*/>', xml):
        snd = m.group(0)
        x, z = float(re.search(r' X="([^"]*)"', snd).group(1)), float(re.search(r' Z="([^"]*)"', snd).group(1))
        d = np.hypot(xz[:, 0] - x, xz[:, 1] - z)
        i = int(np.argmin(d))
        if d[i] > keep: continue
        chi = float(np.dot((x, z) - xz[i], left[i]) / half[i])
        snd = re.sub(r' WAYPOINT="[^"]*"', ' WAYPOINT="%d"' % i, snd)
        snd = re.sub(r' KAPPA="[^"]*"', ' KAPPA="0.000000"', snd)
        snd = re.sub(r' CHI="[^"]*"', ' CHI="%.6f"' % chi, snd)
        out.append(chr(9) + snd)
    nl = chr(13) + chr(10)
    return ('<?xml version="1.0" ?>' + nl + '<WORLDSOUNDS TOTALWAYPOINTS="%d" >' % len(points) + nl +
            ''.join(o + nl for o in out) + '</WORLDSOUNDS>' + nl), len(out)


def like(mega, nseg):
    """A stock track whose segmentation has `nseg` segments (its AI files stand in for a new track's)."""
    ai = 'ai' + B + 'drivatarv2' + B
    for k in sorted(mega.files):
        if k.startswith(ai) and k.endswith('segmentation.bin') and k.count(B) == 2:
            t = k[len(ai):-len('segmentation.bin')]
            if t and int(mlp.read(mega.files[k])[0]['iNumSegments'][0]) == nseg and ai + 'level1' + B + t + '.bin' in mega.files:
                return t
    raise SystemExit('no stock track with %d segments for the AI files' % nseg)


def renamed(d, name):
    """An MLP file with its trackName field set to `name`."""
    v, fields = mlp.read(d)
    return mlp.write([(n, t, name.encode() if n == 'trackName' else v[n]) for n, t, c, k in fields])


def install(mega, name, centre, half, circuit=True, line=None, stock_like=False, edges=None):
    """Into the open Mega.ca2 archive `mega` (addcar.Archive): the track's geometry and segmentation,
    and its name in the AI track list. `line`, if given, makes the suggested line: a function of the waypoints,
    their half widths and their left normals (x, z) giving chi across the road. `stock_like` (the Pacific
    Shipyards Circuit's, 17 Nov): the waypoints rounded off and their widths held to the bends' radii
    (geometry's round_off), the lap cut as the disc's are (segmentation_stock); `edges`, its two edge lines
    (left, right): the waypoints between them and the normals across (edge_waypoints). Returns (waypoints, segments)."""
    ai = 'ai' + B + 'drivatarv2' + B
    crc = mlp.read(mega.files[ai + 'vancouverreversegeometry.bin'])[0]['iCRC']
    geo, p, p_half = geometry(centre, half, crc, circuit, line, round_off=stock_like and edges is None, edges=edges)
    # the AI drivers' files: a track in the list needs them all or its load fails ("disc error"), and
    # they go by its segments (Pacific Shipyards II's 55 against this one's 14: a crash at the start);
    # a stock track's with as many segments, named for this one. The turns' threshold is eased or
    # tightened until the lap cuts into a count a stock track has.
    tries = [dict(turn=t) for t in (0.012, 0.011, 0.013, 0.010, 0.014, 0.009, 0.015, 0.016, 0.008, 0.018, 0.020)]
    if stock_like: tries = [dict(share=sh, minor=mi) for mi in (15.0, 20.0, 25.0, 12.0) for sh in (30, 25, 35, 20, 40)]
    for kw in tries:
        seg, nseg = (segmentation_stock if stock_like else segmentation)(p, **kw)
        try:
            donor = like(mega, nseg)
            break
        except SystemExit:
            continue
    else: raise SystemExit('no stock track with the segments of %s at any threshold' % name)
    mega.files[ai + name.lower() + 'geometry.bin'] = geo
    mega.files[ai + name.lower() + 'segmentation.bin'] = seg
    for sub in ('level1', 'level2', 'level3'):
        mega.files[ai + sub + B + name.lower() + '.bin'] = renamed(mega.files[ai + sub + B + donor + '.bin'], name)
    mega.files[ai + 'interaction-rt-' + name.lower() + '.bin'] = renamed(mega.files[ai + 'interaction-rt-' + donor + '.bin'], name)
    mega.files[ai + 'segmentprofiles' + B + name.lower() + B + 'default.bin'] = mega.files[ai + 'segmentprofiles' + B + donor + B + 'default.bin']
    v, fields = mlp.read(mega.files[ai + 'tracklist.bin'])
    names = [v['trackList_%d' % i] for i in range(1, int(v['trackList_size'][0]) + 1)]
    if name.encode() not in names: names.append(name.encode())  # stored without a terminating 0
    mega.files[ai + 'tracklist.bin'] = mlp.write([('trackList_size', 'int32', [len(names)])] +
                                                 [('trackList_%d' % (i + 1), 'char', nm) for i, nm in enumerate(names)])
    data = 'tracks' + B + name.lower() + B
    kept = {}
    for f in ('audioreflections.xml', 'audioambient.xml'):
        if data + f in mega.files:
            xml, kept[f] = world_sounds(mega.files[data + f].decode('latin-1'), p, p_half)
            mega.files[data + f] = xml.encode('latin-1')
    return p, nseg, kept
