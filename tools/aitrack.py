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


def geometry(centre, half, crc, circuit=True):
    p, h = waypoints(centre, half)
    t = np.roll(p, -1, 0) - np.roll(p, 1, 0)
    left = np.stack([-t[:, 2], t[:, 0]], 1)
    left /= np.linalg.norm(left, axis=1)[:, None]
    n = len(p)
    one = np.ones(n, '<f4')
    return mlp.write([
        ('iCRC', 'uint32', np.asarray(crc, '<u4')),
        ('iLength', 'int32', [n]),
        ('iType', 'int8', [0 if circuit else 1]),
        ('fWaypointX', 'float', p[:, 0]), ('fWaypointY', 'float', p[:, 2]), ('fWaypointZ', 'float', p[:, 1]),
        ('fNormalX', 'float', left[:, 0] * h), ('fNormalY', 'float', left[:, 1] * h), ('fNormalZ', 'float', np.zeros(n)),
        ('fLeftWallChi', 'float', one), ('fRightWallChi', 'float', -one),
        ('fChiOptimal', 'float', racing_line(p, h)),
        ('fLeftCurbChi', 'float', one), ('fRightCurbChi', 'float', -one),
    ]), p


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


def install(mega, name, centre, half, circuit=True):
    """Into the open Mega.ca2 archive `mega` (addcar.Archive): the track's geometry and segmentation,
    and its name in the AI track list. Returns (waypoints, segments)."""
    ai = 'ai' + B + 'drivatarv2' + B
    crc = mlp.read(mega.files[ai + 'vancouverreversegeometry.bin'])[0]['iCRC']
    geo, p = geometry(centre, half, crc, circuit)
    # the AI drivers' files: a track in the list needs them all or its load fails ("disc error"), and
    # they go by its segments (Pacific Shipyards II's 55 against this one's 14: a crash at the start);
    # a stock track's with as many segments, named for this one. The turns' threshold is eased or
    # tightened until the lap cuts into a count a stock track has.
    for turn in (0.012, 0.011, 0.013, 0.010, 0.014, 0.009, 0.015, 0.016, 0.008, 0.018, 0.020):
        seg, nseg = segmentation(p, turn=turn)
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
    p_half = waypoints(centre, half)[1]
    data = 'tracks' + B + name.lower() + B
    kept = {}
    for f in ('audioreflections.xml', 'audioambient.xml'):
        if data + f in mega.files:
            xml, kept[f] = world_sounds(mega.files[data + f].decode('latin-1'), p, p_half)
            mega.files[data + f] = xml.encode('latin-1')
    return p, nseg, kept
