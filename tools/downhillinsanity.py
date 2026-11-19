"""Downhill Insanity (the user's, 16 Nov: "Add the same touge race events to the drift categories, but as drift
events (Downhill Insanity)"): a series of the Drift category on the Midnight Touge's two tracks, Fujimi Kaido at
night (tools/fujiminight.py: its Hill Climb and its Down Hill), run alone and scored as the Drift Championship's
events are (runtime/hle_drift.c; <mods>/drift.txt gains their lines, "ordinal 1st 2nd 3rd"). Open to every D-Spec
car there is (tools/driftcars.py), any class.

The targets: the Drift Championship's are 6, 4 and 2 points a metre of lap; the mountain is some 9.9 km of bends
from start to finish. Down it the same; up it, where a car is slow to slide, two thirds. First guesses, to tune by
the user's runs in drift.txt.

  python tools/downhillinsanity.py <disc> <mods folder>

(fujiminight.py's tracks first: it stops without them.)
"""
import os
import re
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import amateurseries as A
import driftcars
import fujiminight

B = chr(92)
NAME = 'Downhill Insanity'
KIND = 'Drift'
LEVEL = 10
SERIES_ID = 239
EVENT_ORDINAL = 422      # 422, 423 (the Midnight Touge's are 420, 421)
RUN_M = 9900             # the run's length, start line to finish
PER_M = ((4.0, 2.7, 1.3), (6.0, 4.0, 2.0))   # up the mountain, down it
XP = 12000


def targets():
    return [[int(round(RUN_M * f / 100)) * 100 for f in per] for per in PER_M]


def logo_art():
    """The Midnight Touge's night mountain, the road's bends a drift's red."""
    a = fujiminight.logo_art()
    warm = (a[..., 0] > 200) & (a[..., 2] < 170) & (np.mgrid[0:a.shape[0], 0:a.shape[1]][0] > 38)
    a[warm, :3] = (255, 70, 50)
    return a


def series_xml(tracks, cars):
    pts = targets()
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="{ICON}" Level="%d">\r\n'
         '\t<Scoring>\r\n' % (NAME, SERIES_ID, LEVEL) + ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(1, 9)) +
         '\t</Scoring>\r\n\t<Restrictions>\r\n' + A.restrictions([[('carid', '=', c)] for c in cars]) + '\t</Restrictions>\r\n'
         '\t<AIField>\r\n\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="129" AIDriverModelID="22" AppearanceID="0" Easy />\r\n'
         '\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="129" AIDriverModelID="36" AppearanceID="0" Medium />\r\n'
         '\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="129" AIDriverModelID="50" AppearanceID="0" Hard />\r\n\t</AIField>\r\n')
    for k, track in enumerate(tracks):
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="20000">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="1" />\r\n\t\t<AIField NumAICars="0" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting nopitting />\r\n\t\t</AIModeSettings>\r\n'
              '\t\t<Scoring>\r\n'
              '\t\t\t<score pos="1" pts="10" xp="%d"></score>\r\n\t\t\t<score pos="2" pts="8" xp="%d"></score>\r\n'
              '\t\t\t<score pos="3" pts="6" xp="%d"></score>\r\n\t\t\t<score pos="4" pts="0" xp="0"></score>\r\n'
              '\t\t</Scoring>\r\n\t</event>\r\n' % (k, NAME, EVENT_ORDINAL + k, track, XP, XP * 7 // 10, XP // 2))
    return x + '</series>\r\n', pts


def install(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    tl = next(v for k, v in mega.files.items() if k.lower() == 'forzadb' + B + 'tracklist.xml').decode('latin-1')
    tracks = []
    for _, _, tag, _ in fujiminight.TRACKS:
        m = re.search(r'<track\s[^>]*\sname="%s"[^>]*?\sOrdinal="(\d+)"' % tag, tl, re.S)
        if not m: raise SystemExit('%s is not in the track list: tools/fujiminight.py first' % tag)
        tracks.append(int(m.group(1)))
    cars = sorted(driftcars.ordinals(disc, mods).values())
    xml, pts = series_xml(tracks, cars)
    desc = ('Open to D-Spec cars. Alone on Fujimi Kaido at night: score by drifting, long and at an angle. '
            'For 1st: %s points up the mountain, %s down it.' % ('{:,}'.format(pts[0][0]), '{:,}'.format(pts[1][0])))
    if KIND not in addseries.KINDS: addseries.KINDS = tuple(addseries.KINDS) + (KIND,)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'downhill.xml')
        open(p, 'w', encoding='latin-1', newline='').write(xml)
        png = A.logo(disc, mods, dict(image=logo_art()), [('DOWNHILL', 4, 22, 'chrome'), ('INSANITY', 88, 22, 'vs')], tmp)
        addseries.main(disc, mods, KIND, p, NAME, desc, event_name=NAME, logo='%s,%s' % (png, png))
    path = os.path.join(mods, 'drift.txt')
    ours = [str(EVENT_ORDINAL + k) for k in range(len(tracks))]
    lines = [l for l in (open(path).read().splitlines() if os.path.exists(path) else []) if l.split()[:1] not in [[o] for o in ours]]
    open(path, 'w').write('\n'.join(lines + ['%s %d %d %d' % ((o,) + tuple(p)) for o, p in zip(ours, pts)]) + '\n')
    print('%s: events %s on tracks %s, targets %s; open to cars %s' % (NAME, ours, tracks, pts, cars))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    install(sys.argv[1], sys.argv[2])
