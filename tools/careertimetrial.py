"""A Time Trial category in career mode (Go Race, the first tile), in place of Online Career,
which offline only says to sign in to Xbox Live. Needs the runtime's XBRT_CAREER_TIMETRIAL=1
(runtime/nv2a.c: it renames the category so its series are read from Events\\TimeTrial and it is
no longer the online one; runtime/hle_career.c: it places the player by the clock). Into the mods
folder:

  - media\\Events\\TimeTrial.bik: the category's video (each has one, D:\\MEDIA\\Events\\<name>.bik;
    without it the screen fails with a disc error): Online Career's;
  - events\\TimeTrial\\Ser00001.xml... (Mega.ca2): a series a class, from Class D (any level) up to
    R-P1 (level 50), like the Spec series' ladder; two one-lap time trials each from the main
    menu's Time Trials' rolling starts (driverchallenge\\ser00001.xml), no other cars;
  - timetrial.txt: each event's three target times (ordinal, then 1st, 2nd and 3rd in ms), from
    laptime.py's estimate for the track and class: under the first is 1st, and so on; slower than
    the third is 4th;
  - strings: the tile's title (GameStrings.str) and description (UIStrings.str), the series' names
    and each event's description with its targets (EventStrings.str), every language, in English.

  python tools/careertimetrial.py <disc> <mods folder> [<drift logo folder: tools/driftlogo.py's drift_lg.png, drift_sm.png>]
"""
import os
import re
import shutil
import sys

import addcar
import laptime

B = '\\'
HELP = 141   # UIStrings: IDS_Event_OnlineCareer_Help, the tile's description
TITLE = 49   # GameStrings: IDS_Event_OnlineCareer, the tile's title
SERIES_ORDINAL = 85      # after the custom cup's 84
EVENT_ORDINAL = 355      # after the custom cup's 351-354; the profile keeps 512 medal bytes
# the target times against laptime.py's estimate: a person's clean lap is PACE of it (the user's
# 1:09.2 at Silverstone Club in Class D, against 1:20.0), and 1st asks for that lap give or take
# MARGIN, from 5% slower in Class D to 2% slower in R-P1 (the user: the first a little harder, the
# last a little easier than 6% and the lap itself), step by step up the ladder;
# 2nd and 3rd are SPREAD slower than 1st
PACE = 0.865
MARGIN = (1.05, 1.02)
SPREAD = (1.0, 1.04, 1.08)

# (class, restriction, level, icon (the Spec series' class logos), tracks (tracklist ordinals), the
# car won (its ordinal; none a prize anywhere else in the career), the Spec series of the class
# whose AI field it lists (events\spec\SerNNNNN; none race, but the career's end of an event reads
# the series' field, and with none it crashed))
LADDER = [
    ('D', ('perfclass', 'D'), 0, 7, (26, 47), 133, 1),             # Tsukuba, Silverstone Club; a Mazda RX-7
    ('C', ('perfclass', 'C'), 5, 8, (1, 27), 5, 2),                # Laguna Seca, Alpine Ring; a Subaru WRX STi
    ('B', ('perfclass', 'B'), 10, 9, (6, 9), 92, 6),               # Sunset Peninsula, Road Atlanta; a Skyline R34 GT-R
    ('A', ('perfclass', 'A'), 15, 10, (8, 25), 8, 8),              # Maple Valley, Rio; a Ferrari 575M
    ('S', ('perfclass', 'S'), 20, 11, (18, 16), 36, 15),           # New York, Road America; a Ferrari Enzo
    ('R-GT', ('perfsubclass', 'GT'), 30, 12, (2, 57), 197, 18),    # Silverstone, Maple Valley Reverse; the JGTC WRX #77
    ('R-GTS', ('perfsubclass', 'GTS'), 40, 13, (3, 52), 213, 19),  # Fujimi Kaido, New York Short Reverse; Team Impul's Skyline
    ('R-P1', ('perfsubclass', 'P1'), 50, 14, (19, 1), 145, 20),    # the Nurburgring, Laguna Seca; a Bentley Speed 8
]
SIM_CLASS = {'R-GT': 'GT', 'R-GTS': 'GTS', 'R-P1': 'P1'}
XP_1ST = 2500      # a Class D win; more up the ladder, like the Spec series' (11000 for five laps)

# Drift series (the user's drift mode, 2026-11-01: runtime/hle_drift.c scores and places them), here
# until the career has a Drift tile of its own: after the time trials in this category, open to the
# drift-spec cars (tools/driftcars.py), one car on the track. (name, level, events (track, laps));
# each event's least scores for 1st, 2nd and 3rd are DRIFT_PER_M points a metre driven (the track's
# length times the laps): first guesses, to tune by the user's drives (<mods>/drift.txt)
DRIFT_SERIES_ORDINAL = 107   # after the Professional series' 103-106
DRIFT_EVENT_ORDINAL = 400    # after theirs, 389-399
DRIFT_CARS = ('NissanSilviaDSpec', 'Nissan240SXDSpec', 'MazdaRX7DSpec', 'ToyotaTruenoDSpec',
              'NissanSilviaS15RDSpec', 'DodgeNeonCoupeDSpec', 'ToyotaCelicaGT4DSpec', 'MazdaMX5RadbulDSpec')  # (tools/driftcars.py's)
DRIFT_PER_M = (6.0, 4.0, 2.0)
# One big series (the user's, 1 Nov: three were too many), the MX-5 RADBUL its prize, its own logo
# (tools/driftlogo.py from the user's DRIFT art) on tile DRIFT_ICON, in the row the small strip grew by
DRIFT = [
    ('Drift Championship', 0, [(26, 2), (47, 2), (1, 2), (27, 1), (82, 2), (83, 2)]),
    # Tsukuba, Silverstone Short, Laguna Seca, Alpine Ring, Pacific Shipyards Circuit and Circuit II
]
DRIFT_PRIZE = 'MazdaMX5Radbul'
# its own career category (the user's: a seventh tile, runtime/hle_career_cats.c): folder, title, description, icon tile,
# its place in the list (1: beside Time Trial, the first)
DRIFT_CATEGORY = ('Drift', 'Drift', 'Slide for points, alone on the track: long, at an angle and over 15 mph. '
                  'Drift-spec cars only. Win the championship for the MX-5 RADBUL.', 8, 1)
DRIFT_ICON = 50


def build_drift(mega, tracks, field):
    """The drift series' XML, drift.txt's lines and their strings (as build's)."""
    xml = mega.files['cars' + B + 'carlist.xml'].decode('latin-1')
    cars = [addcar.ordinal_of(xml, c) for c in DRIFT_CARS if re.search(r'<car name="%s"' % c, xml)]
    if not cars: return [], [], []
    # an <or> a car: each <or> is one alternative whose restrictions all hold (as the disc's Superstreet
    # Face Off, Supra or RX-7); the four in one <or> asked for a car that was all four, and none could enter
    allowed = ''.join('\t\t<or>\r\n\t\t\t<Restriction Attrib="carid" Func="=" Value="%d" />\r\n\t\t</or>\r\n' % c for c in cars)
    length = {int(r['Ordinal']): float(r.get('length', 3000)) for r in tracks}
    series, targets, strings, ordinal = [], [], [], DRIFT_EVENT_ORDINAL
    for k, (name, level, events) in enumerate(DRIFT):
        tag = 'Drift%d' % k
        prize = addcar.ordinal_of(xml, DRIFT_PRIZE) if re.search(r'<car name="%s"' % DRIFT_PRIZE, xml) else None
        reward = '<rewards CareerCarUnlock="%d" CareerCarGift="%d" />' % (prize, prize) if prize is not None else ''  # (as the disc's Opens: 1st overall)
        strings += [('IDS_Mod_%s_Name' % tag, name),
                    ('IDS_Mod_%s_Desc' % tag, 'Open to drift-spec cars. Alone on the track: score by drifting, long and at an angle, '
                                              'over 15 mph. Leaving the road, a spin or a hit loses the drift.'
                                              + (' Win it for the MX-5 RADBUL.' if prize is not None else ''))]
        out = []
        for i, (t, laps) in enumerate(events):
            pts = [int(round(length[t] * laps * f / 100)) * 100 for f in DRIFT_PER_M]
            targets.append('%d %d %d %d' % (ordinal, *pts))
            desc = 'IDS_Mod_%s_Event%d' % (tag, i)
            strings.append((desc, 'Targets: 1st %d, 2nd %d, 3rd %d points.' % tuple(pts)))
            xp = int(XP_1ST * (1 + level / 10))
            out.append(
                '<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{IDS_Mod_%s_Name}" eventdescid="{%s}" type="Single" leaderboard="20000">\r\n'
                '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n\t\t<AIField NumAICars="0" />\r\n'
                '\t\t<AIModeSettings>\r\n\t\t\t<pitting nopitting />\r\n\t\t</AIModeSettings>\r\n'
                '\t\t<Scoring>\r\n'
                '\t\t\t<score pos="1" pts="10" xp="%d"></score>\r\n\t\t\t<score pos="2" pts="8" xp="%d"></score>\r\n'
                '\t\t\t<score pos="3" pts="6" xp="%d"></score>\r\n\t\t\t<score pos="4" pts="0" xp="0"></score>\r\n'
                '\t\t</Scoring>\r\n\t</event>' % (i, name, ordinal, tag, desc, t, laps, xp, xp * 7 // 10, xp // 2))
            ordinal += 1
        head = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{IDS_Mod_%s_Name}" '
                'seriesdescid="{IDS_Mod_%s_Desc}" seriesid="58" seriesordinal="%d" seriesorder="%d" Icon="%d"%s>\r\n'
                '\t<Scoring>\r\n' + ''.join('\t\t<score pos="%d">%s</score>\r\n' % (p, reward if p == 1 else '') for p in range(1, 9)) +
                '\t</Scoring>\r\n\t<Restrictions>\r\n%s\t</Restrictions>\r\n\t%s\r\n') % (
                    name, tag, tag, DRIFT_SERIES_ORDINAL + k, len(LADDER) + k, DRIFT_ICON, ' Level="%d"' % level if level else '', allowed, field)
        series.append(head + '\r\n'.join('\t' + e for e in out) + '\r\n</series>\r\n')
    return series, targets, strings


def clock(ms):
    return '%d:%02d.%03d' % (ms // 60000, ms // 1000 % 60, ms % 1000)


def put_strings(base, texts):
    """EventStrings with texts [(name, text)]: replaced where there (a run before), else added."""
    have = addcar.string_ids(base)
    new = [(n, t) for n, t in texts if n not in have]
    d = addcar.write_strings(base, new) if new else base
    return addcar.replace_strings(d, {have[n]: t for n, t in texts if n in have})


def build(disc, mods, mega, tracks):
    """The series' XML, the targets' lines, and the strings they need [(name, text)]."""
    dc = mega.files['driverchallenge' + B + 'ser00001.xml'].decode('latin-1')
    starts = {}
    for e in re.findall(r'<event\b.*?</event>', dc, re.S):
        t = int(re.search(r'<track Ordinal="(\d+)"', e).group(1))
        starts[t] = (re.search(r'eventtextid="(\d+)"', e).group(1), re.search(r'<rollingstart [^>]*/>', e).group(0))
    names = {int(r['Ordinal']): r['name'] for r in tracks}
    # the cars won, by ordinal, named as the menus name them (make and model)
    cars = {prize: addcar.car_name(disc, mods, prize) for *_, prize, _ in LADDER}
    series, targets, strings, ordinal = [], [], [], EVENT_ORDINAL
    for k, (cls, (attr, value), level, icon, ts, prize, spec) in enumerate(LADDER):
        tag = re.sub(r'\W', '', cls)
        strings += [('IDS_Mod_TT%s_Name' % tag, 'Class %s Time Trials' % cls),
                    ('IDS_Mod_TT%s_Desc' % tag, 'One flying lap each, alone, in a Class %s car: beat the target times for a podium. '
                                                'First place in both receives the %s.' % (cls, cars[prize]))]
        events = []
        margin = MARGIN[0] + (MARGIN[1] - MARGIN[0]) * k / (len(LADDER) - 1)
        for i, t in enumerate(ts):
            est, _ = laptime.lap(mega, names[t], SIM_CLASS.get(cls, cls))
            ms = [int(round(est * PACE * margin * f * 10)) * 100 for f in SPREAD]
            targets.append('%d %d %d %d' % (ordinal, *ms))
            desc = 'IDS_Mod_TT%s_Event%d' % (tag, i)
            strings.append((desc, 'Targets: 1st %s, 2nd %s, 3rd %s. First place in both events receives the %s.' % (*(clock(m) for m in ms), cars[prize])))
            text, start = starts[t]
            xp = int(XP_1ST * (1 + level / 10))
            events.append(
                '<event eventid="%d" displayname="Time Trial" eventordinal="%d" eventtextid="%s" eventdescid="{%s}" type="Single" leaderboard="20000">\r\n'
                '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="1" />\r\n\t\t<AIField NumAICars="0" />\r\n'
                '\t\t<AIModeSettings>\r\n\t\t\t<pitting nopitting />\r\n\t\t\t%s\r\n\t\t</AIModeSettings>\r\n'
                '\t\t<Scoring>\r\n'
                '\t\t\t<score pos="1" pts="10" xp="%d"></score>\r\n\t\t\t<score pos="2" pts="8" xp="%d"></score>\r\n'
                '\t\t\t<score pos="3" pts="6" xp="%d"></score>\r\n\t\t\t<score pos="4" pts="0" xp="0"></score>\r\n'
                '\t\t</Scoring>\r\n\t</event>' % (i, ordinal, text, desc, t, start, xp, xp * 7 // 10, xp // 2))
            ordinal += 1
        # the series' place is the worst of its events' best places (0x1A76B0; an unplayed event
        # counts 9), so its 1st place's rewards, the car, come with a win in every event
        # (the disc's own: series added since, as the Catch-Up Challenge, renumber the mods folder's)
        spec_file = next(v for n, v in mega.disc.items() if n.lower() == ('events' + B + 'spec' + B + 'ser%05d.xml' % spec))
        field = re.search(r'<AIField>.*?</AIField>', spec_file.decode('latin-1'), re.S).group(0)
        head = ('<?xml version="1.0"?>\r\n<series displayname="Class %s Time Trials" seriesnameid="{IDS_Mod_TT%s_Name}" '
                'seriesdescid="{IDS_Mod_TT%s_Desc}" seriesid="58" seriesordinal="%d" seriesorder="%d" Icon="%d"%s>\r\n'
                '\t<Scoring>\r\n\t\t<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>\r\n' +
                ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(2, 9)) +
                '\t</Scoring>\r\n\t<Restrictions>\r\n\t\t<Restriction Attrib="%s" Func="=" Value="%s" />\r\n\t</Restrictions>\r\n'
                '\t%s\r\n') % (cls, tag, tag, SERIES_ORDINAL + k, k, icon, ' Level="%d"' % level if level else '', prize, prize, attr, value, field)
        series.append(head + '\r\n'.join('\t' + e for e in events) + '\r\n</series>\r\n')
    return series, targets, strings


def install(disc, mods, logo_dir=None):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    tl = mega.files['forzadb' + B + 'tracklist.xml'].decode('latin-1')
    tracks = [dict(re.findall(r'(\w+)="([^"]*)"', r)) for r in re.findall(r'<track\s.*?/>', tl, re.S)]
    series, targets, strings = build(disc, mods, mega, tracks)
    spec1 = next(v for n, v in mega.disc.items() if n.lower() == 'events' + B + 'spec' + B + 'ser00001.xml')
    field = re.search(r'<AIField>.*?</AIField>', spec1.decode('latin-1'), re.S).group(0)
    dseries, dtargets, dstrings = build_drift(mega, tracks, field)
    strings += dstrings
    cat_ids = {}  # the Drift category's title (GameStrings) and description (UIStrings), the same ids in every language
    loc = addcar.disc_file(disc, 'media', 'Loc')
    ids = None
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'EventStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'EventStrings.str')
        new = put_strings(open(mp if os.path.exists(mp) else p, 'rb').read(), strings)
        got = addcar.string_ids(new)
        these = {n: got[n] for n, _ in strings}
        if ids not in (None, these): raise SystemExit('%s: the string ids differ between languages' % lang)
        ids = these
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(new)
        for name, change in (('UIStrings.str', {HELP: 'Race the clock alone: one flying lap, three target times. '
                                                                   'Beat them for 1st, 2nd or 3rd; harder classes open as you level up.'}),
                                   ('GameStrings.str', {TITLE: 'Time Trial'})):
            src = addcar.disc_file(disc, 'media', 'Loc', lang, name)
            mp = os.path.join(mods, 'media', 'Loc', lang, name)
            d = addcar.replace_strings(open(mp if os.path.exists(mp) else src, 'rb').read(), change)
            add = {'GameStrings.str': [('IDS_Mod_Category_Drift', DRIFT_CATEGORY[1])],
                   'UIStrings.str': [('IDS_Mod_Category_Drift_Help', DRIFT_CATEGORY[2])]}[name]
            d = put_strings(d, add)
            got = addcar.string_ids(d)[add[0][0]]
            if cat_ids.setdefault(name, got) != got: raise SystemExit('%s %s: the string ids differ between languages' % (lang, name))
            open(mp, 'wb').write(d)
    for k in list(mega.files):
        if k.lower().startswith(('events' + B + 'timetrial' + B, 'events' + B + 'drift' + B)): del mega.files[k]
    for k, x in enumerate(series):
        x = re.sub(r'\{(IDS_\w+)\}', lambda m: str(ids[m.group(1)]), x)
        mega.files['events' + B + 'TimeTrial' + B + 'Ser%05d.xml' % (k + 1)] = x.encode('latin-1')
    for k, x in enumerate(dseries):  # the Drift category's own folder (runtime/hle_career_cats.c, categories.txt)
        x = re.sub(r'\{(IDS_\w+)\}', lambda m: str(ids[m.group(1)]), x)
        x = re.sub(r'seriesorder="\d+"', 'seriesorder="%d"' % k, x)
        mega.files['events' + B + DRIFT_CATEGORY[0] + B + 'Ser%05d.xml' % (k + 1)] = x.encode('latin-1')
    mega.check(); mega.write()
    # the category itself: a line of categories.txt, its icon (tools/drifticon.py's) a 9th tile of the icon
    # strips, and the background video every category plays (a missing one is a disc error)
    ev = os.path.join(mods, 'media', 'Events')
    os.makedirs(ev, exist_ok=True)
    if logo_dir:
        import addseries
        for n, art, size in (('Events.xpr', 'drift_cat_sm.png', (108, 60, 1)), ('Events_LG.xpr', 'drift_cat_lg.png', (210, 117, 1))):
            d = open(addcar.disc_file(disc, 'media', 'Events', n), 'rb').read()
            while addseries.tiles_in(d, size) <= DRIFT_CATEGORY[3]: d = addseries.grow(d, size)
            d = addseries.put_tile(d, DRIFT_CATEGORY[3], addseries.image(os.path.join(logo_dir, art), *size[:2]), size)
            open(os.path.join(ev, n), 'wb').write(d)
    shutil.copyfile(addcar.disc_file(disc, 'media', 'Events', 'Club.bik'), os.path.join(ev, DRIFT_CATEGORY[0] + '.bik'))
    open(os.path.join(mods, 'categories.txt'), 'w').write(
        '# career categories after the six (runtime/hle_career_cats.c): folder, kind (2 club), title id (GameStrings),\n'
        '# description id (UIStrings), icon (a tile of media/Events/Events.xpr), place in the list (0 first)\n'
        '%s 2 %d %d %d %d\n' % (DRIFT_CATEGORY[0], cat_ids['GameStrings.str'], cat_ids['UIStrings.str'], DRIFT_CATEGORY[3], DRIFT_CATEGORY[4]))
    print('Drift category: strings %d, %d, icon %d' % (cat_ids['GameStrings.str'], cat_ids['UIStrings.str'], DRIFT_CATEGORY[3]))
    if logo_dir:  # the drift series' logo on tile DRIFT_ICON of both strips in every language, the small one grown a row for it
        import addseries
        xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
        imgs = {'lg': addseries.image(os.path.join(logo_dir, 'drift_lg.png'), *addseries.LG[:2]),
                'sm': addseries.image(os.path.join(logo_dir, 'drift_sm.png'), *addseries.SM[:2])}
        for k in sorted(xpr.files):
            m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
            if not m: continue
            size = addseries.LG if m.group(1).lower() == 'lg' else addseries.SM
            while addseries.tiles_in(xpr.files[k], size) <= DRIFT_ICON: xpr.files[k] = addseries.grow(xpr.files[k], size)
            xpr.files[k] = addseries.put_tile(xpr.files[k], DRIFT_ICON, imgs[m.group(1).lower()], size)
        xpr.check(); xpr.write()
        print('drift logo: tile %d of the series logos, from %s' % (DRIFT_ICON, logo_dir))
    ev = os.path.join(mods, 'media', 'Events')
    os.makedirs(ev, exist_ok=True)
    shutil.copyfile(addcar.disc_file(disc, 'media', 'Events', 'OnlineCareer.bik'), os.path.join(ev, 'TimeTrial.bik'))
    open(os.path.join(mods, 'timetrial.txt'), 'w').write('# ordinal, then the target times for 1st, 2nd and 3rd (ms)\n' + '\n'.join(targets) + '\n')
    open(os.path.join(mods, 'drift.txt'), 'w').write('# ordinal, then the least scores for 1st, 2nd and 3rd\n' + '\n'.join(dtargets) + '\n')
    print('Time Trial category: %d series, %d events; drift: %d series, %d events' % (len(series), len(targets), len(dseries), len(dtargets)))
    for line in dtargets: print('  drift', line)
    for line in targets: print(' ', line)


if __name__ == '__main__':
    install(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)  # [the drift logo's folder: tools/driftlogo.py]
