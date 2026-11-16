"""Nordschleife Endurance made over into the Eliminator (the user's, 15 Nov: "let's do an eliminator event where
every lap, last place is eliminated. Don't put in the Nordschleife since its too long"). In place: the series keeps
its file, ordinal (106), id, level, class (R-GTS), field and prize; its one race (event 399) and two new ones
(418, 419) are short circuits of one lap fewer than the cars in them, so a car goes out each lap and the last lap
is a duel. The runtime (hle_elim.c) does the eliminating, for the events listed in <mods>/eliminator.txt, written
here. Its name, description and races' texts in every language; its logo the R-GTS tile lettered ELIMINATOR
(tile 54, a Mayhem tile no series shows any more). Idempotent.

  python tools/eliminator.py <disc> <mods folder> [<logo preview png>]
"""
import os
import re
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import amateurseries as A
import mayhemchamp

OLD, NAME = 'Nordschleife Endurance', 'Eliminator'
DESC = ('Open to Class R-GTS cars. Three short circuits, eight cars, seven laps: every lap, the car in last place is '
        'out. Be the last one left. First place receives the Lexus LF-A.')
TILE = 54
N_AI = 7
RACES = [  # (event ordinal, track, name)
    (399, 26, 'Tsukuba Knockout'),
    (418, 47, 'Silverstone Knockout'),
    (419, 46, 'Road Atlanta Knockout'),
]
EVENT_DESC = 'Class R-GTS only. Seven laps: every lap, last place is eliminated.'
XP = 45000
SHARES = (1.0, 0.7, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0)
PTS = (10, 8, 6, 5, 4, 3, 2, 1)


def event_xml(ordinal, track, name, name_id, desc_id):
    return ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="%d" eventdescid="%d" type="Single" leaderboard="1450">\r\n'
            '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
            '\t\t<AIField NumAICars="%d" random="false" byclass="false" duplicates="false" />\r\n'
            '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="0.01" fuel="0.01" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
            '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n' % (ordinal, name, ordinal, name_id, desc_id, track, N_AI, N_AI) +
            ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, PTS[p], int(round(XP * SHARES[p] / 500)) * 500) for p in range(N_AI + 1)) +
            '\t\t</Scoring>\r\n\t</event>\r\n')


def logos(disc, mods):
    with tempfile.TemporaryDirectory() as tmp:
        lg = np.asarray(Image.open(A.logo(disc, mods, dict(tile=13, clear=[(80, 112)], flames=0.45), [('ELIMINATOR', 85, 21, 'chrome')], tmp)).convert('RGBA')).copy()
    sm = np.asarray(Image.fromarray(lg).resize(addseries.SM[:2], Image.LANCZOS)).copy()
    lg[..., 3] = sm[..., 3] = 255
    return lg, sm


def main(disc, mods, preview=None):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    lg, sm = logos(disc, mods)
    if preview:
        Image.fromarray(lg).resize((lg.shape[1] * 3, lg.shape[0] * 3), Image.LANCZOS).save(preview)
        print(preview)
    k = next(k for k, v in mega.files.items() if re.match(r'(?i)events\\spec\\ser\d+\.xml$', k)
             and re.search(rb'<series displayname="(%s|%s)"' % (OLD.encode(), NAME.encode()), v[:300]))
    x = mega.files[k].decode('latin-1')
    others = {int(o) for kk, v in mega.files.items() if re.match(r'(?i)events\\', kk) and kk != k for o in re.findall(rb'eventordinal="(\d+)"', v)}
    clash = [o for o, _, _ in RACES if o in others]
    if clash: raise SystemExit('event ordinals taken elsewhere: %s' % clash)
    name_id, desc_id = (int(re.search(r'%s="(\d+)"' % a, x).group(1)) for a in ('seriesnameid', 'seriesdescid'))
    ev_name0, ev_desc0 = (int(re.search(r'<event [^>]*%s="(\d+)"' % a, x).group(1)) for a in ('eventtextid', 'eventdescid'))
    # the strings, every language (one id for all: checked)
    want = [('IDS_Mod_Elim%d_Name' % i, RACES[i][2]) for i in (1, 2)]
    loc = os.path.join(mods, 'media', 'Loc')
    ids = None
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()
        have = addcar.string_ids(d)
        add = [w for w in want if w[0] not in have]
        if add: d = addcar.write_strings(d, add); have = addcar.string_ids(d)
        got = tuple(have[w[0]] for w in want)
        if ids is not None and got != ids: raise SystemExit('%s: the string ids differ between languages' % lang)
        ids = got
        changes = {name_id: NAME, desc_id: DESC, ev_name0: RACES[0][2], ev_desc0: EVENT_DESC}
        for i, t in zip(got, (RACES[1][2], RACES[2][2])): changes[i] = t
        changes = {i: t for i, t in changes.items() if mayhemchamp.text_of(d, i) != t}
        if changes: d = addcar.replace_strings(d, changes)
        open(mp, 'wb').write(d)
    # the series: its head's name and logo, its races
    head = re.search(r'<series [^>]*>', x).group(0)
    head2 = re.sub(r'displayname="[^"]*"', 'displayname="%s"' % NAME, head)
    head2 = re.sub(r'Icon="\d+"', 'Icon="%d"' % TILE, head2)
    body = x[:x.index('\t<event ')].replace(head, head2)
    evs = ''.join(event_xml(o, t, n, nid, ev_desc0) for (o, t, n), nid in zip(RACES, (ev_name0,) + ids))
    mega.files[k] = (body + evs + '</series>\r\n').encode('latin-1')
    mega.check(); mega.write()
    print('%s: %s, races %s' % (k, NAME, ', '.join('%d %s' % (o, n) for o, _, n in RACES)))
    open(os.path.join(mods, 'eliminator.txt'), 'w', newline='\n').write(
        '# Eliminator events (runtime/hle_elim.c): every lap, the car in last place is out (tools/eliminator.py)\n'
        'events %s\n' % ' '.join(str(o) for o, _, _ in RACES))
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    for kk in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', kk, re.I)
        if not m: continue
        big = m.group(1).lower() == 'lg'
        size = addseries.LG if big else addseries.SM
        while addseries.tiles_in(xpr.files[kk], size) <= TILE: xpr.files[kk] = addseries.grow(xpr.files[kk], size)
        xpr.files[kk] = addseries.put_tile(xpr.files[kk], TILE, lg if big else sm, size)
    xpr.check(); xpr.write()
    print('logo: tile %d' % TILE)


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    main(*sys.argv[1:])
