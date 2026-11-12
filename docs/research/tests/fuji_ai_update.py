"""fuji_ai_update.py <disc> <build folder> <mods folder>: Fuji's layout changed (the main straight's line, 11 Nov):
what `fujitrack.py install` wrote from it, written again in place: the AI files and the suggested line (Mega.ca2),
the audio spline (a record a waypoint), the track's map tile (MegaXPR.ca2). `update` does the track files."""
import os, sys
import numpy as np
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import addcar, addseries, aitrack, fujitrack as F
import shipyardloop as sl
B = '\\'
disc, build_dir, mods = sys.argv[1:4]
if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(mods).split(os.sep)):
    raise SystemExit('%s: a save folder' % mods)
mega = addcar.Archive(disc, mods, 'Mega.ca2')
E = np.load(os.path.join(build_dir, 'fuji_forza.npz'))
centre = E['centre']
half = np.linalg.norm(E['inner'] - E['outer'], axis=1) / 2
wps, nseg, sounds = aitrack.install(mega, F.TAG, (E['inner'] + E['outer']) / 2, half, line=F.racing_line(build_dir))
print('AI files: %d waypoints, %d segments; sounds kept %s' % (len(wps), nseg, sounds))
xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
key = next(k for k in xpr.files if k.lower() == 'frontend' + B + 'gfx_trackmaps.xpr')
xpr.files[key] = addseries.put_tile(xpr.files[key], F.MAP_TILE, sl.trackmap(centre.copy()), (128, 128, 4))
for a in (mega, xpr): a.check()
for a in (mega, xpr): a.write()
d = os.path.join(mods, 'media', 'tracks', F.TAG)
ra = addcar.disc_file(disc, 'media', 'tracks', F.DONOR_TRACK)
for f in os.listdir(ra):
    if f.lower() == 'audiospline.bin':
        ref = mega.files['ai' + B + 'drivatarv2' + B + F.DONOR_TRACK.lower() + 'geometry.bin']
        open(os.path.join(d, 'AudioSpline.bin'), 'wb').write(aitrack.audio_spline(wps, ref, open(os.path.join(ra, f), 'rb').read()))
        print('audio spline: %d records' % len(wps))
