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

  python tools/careertimetrial.py <disc> <mods folder>
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
# the target times against laptime.py's estimate: 1st, 2nd, 3rd
FACTORS = (1.04, 1.09, 1.15)

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
        for i, t in enumerate(ts):
            est, _ = laptime.lap(mega, names[t], SIM_CLASS.get(cls, cls))
            ms = [int(round(est * f * 10)) * 100 for f in FACTORS]
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
        field = re.search(r'<AIField>.*?</AIField>', mega.files['events' + B + 'spec' + B + 'ser%05d.xml' % spec].decode('latin-1'), re.S).group(0)
        head = ('<?xml version="1.0"?>\r\n<series displayname="Class %s Time Trials" seriesnameid="{IDS_Mod_TT%s_Name}" '
                'seriesdescid="{IDS_Mod_TT%s_Desc}" seriesid="58" seriesordinal="%d" seriesorder="%d" Icon="%d"%s>\r\n'
                '\t<Scoring>\r\n\t\t<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>\r\n' +
                ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(2, 9)) +
                '\t</Scoring>\r\n\t<Restrictions>\r\n\t\t<Restriction Attrib="%s" Func="=" Value="%s" />\r\n\t</Restrictions>\r\n'
                '\t%s\r\n') % (cls, tag, tag, SERIES_ORDINAL + k, k, icon, ' Level="%d"' % level if level else '', prize, prize, attr, value, field)
        series.append(head + '\r\n'.join('\t' + e for e in events) + '\r\n</series>\r\n')
    return series, targets, strings


def install(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    tl = mega.files['forzadb' + B + 'tracklist.xml'].decode('latin-1')
    tracks = [dict(re.findall(r'(\w+)="([^"]*)"', r)) for r in re.findall(r'<track\s.*?/>', tl, re.S)]
    series, targets, strings = build(disc, mods, mega, tracks)
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
            open(mp, 'wb').write(d)
    for k in list(mega.files):
        if k.lower().startswith('events' + B + 'timetrial' + B): del mega.files[k]
    for k, x in enumerate(series):
        x = re.sub(r'\{(IDS_\w+)\}', lambda m: str(ids[m.group(1)]), x)
        mega.files['events' + B + 'TimeTrial' + B + 'Ser%05d.xml' % (k + 1)] = x.encode('latin-1')
    mega.check(); mega.write()
    ev = os.path.join(mods, 'media', 'Events')
    os.makedirs(ev, exist_ok=True)
    shutil.copyfile(addcar.disc_file(disc, 'media', 'Events', 'OnlineCareer.bik'), os.path.join(ev, 'TimeTrial.bik'))
    open(os.path.join(mods, 'timetrial.txt'), 'w').write('# ordinal, then the target times for 1st, 2nd and 3rd (ms)\n' + '\n'.join(targets) + '\n')
    print('Time Trial category: %d series, %d events' % (len(series), len(targets)))
    for line in targets: print(' ', line)


if __name__ == '__main__':
    install(sys.argv[1], sys.argv[2])
