"""A Time Trial category in career mode (Go Race, the first tile), in place of Online Career,
which offline only says to sign in to Xbox Live. Needs the runtime's XBRT_CAREER_TIMETRIAL=1
(runtime/nv2a.c: it renames the category so its series are read from Events\\TimeTrial and it is
no longer the online one). Into the mods folder:

  - media\\Events\\TimeTrial.bik: the category's video (each has one, D:\\MEDIA\\Events\\<name>.bik;
    without it the screen fails with a disc error): Online Career's;
  - events\\TimeTrial\\Ser00001.xml... (Mega.ca2): its series, made from the main menu's Time
    Trials (driverchallenge\\ser00001.xml: one lap from a rolling start, no other cars), in
    series of four, any car;
  - the tile's title (GameStrings.str) and description (UIStrings.str), every language, in English.

A time trial is scored like any career event: alone, the player always finishes first, so its
rewards come for finishing. Medals by time would need the game's scoring changed (not done).

  python tools/careertimetrial.py <disc> <mods folder>
"""
import os
import re
import shutil
import sys

import addcar

B = '\\'
HELP = 141   # UIStrings: IDS_Event_OnlineCareer_Help, the tile's description
TITLE = 49   # GameStrings: IDS_Event_OnlineCareer, the tile's title
SERIES_ORDINAL = 85      # after the custom cup's 84
EVENT_ORDINAL = 355      # after the custom cup's 351-354; the profile keeps 512 medal bytes
PER_SERIES = 4


def series(events, k):
    head = ('<?xml version="1.0"?>\r\n<series displayname="Time Trial %d" seriesnameid="1058" seriesdescid="2058" '
            'seriesid="58" seriesordinal="%d" seriesorder="%d" Icon="0">\r\n'
            '\t<Scoring>\r\n\t\t<score pos="1"><rewards /></score>\r\n\t</Scoring>\r\n'
            '\t<Restrictions>\r\n\t</Restrictions>\r\n\t<AIField>\r\n\t</AIField>\r\n') % (k + 1, SERIES_ORDINAL + k, k)
    return (head + '\r\n'.join('\t' + e for e in events) + '\r\n</series>\r\n').encode('latin-1')


def install(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    dc = mega.files['driverchallenge' + B + 'ser00001.xml'].decode('latin-1')
    events = re.findall(r'<event\b.*?</event>', dc, re.S)
    out = []
    for i, e in enumerate(events):
        e = re.sub(r'eventordinal="\d+"', 'eventordinal="%d"' % (EVENT_ORDINAL + i), e)
        e = re.sub(r'eventid="\d+"', 'eventid="%d"' % (i % PER_SERIES), e)
        e = re.sub(r'<AIField PlayerCarTypeID="\d+" NumAICars="0" />', '<AIField NumAICars="0" />', e)  # any car
        out.append(e)
    groups = [out[i:i + PER_SERIES] for i in range(0, len(out), PER_SERIES)]
    for k in list(mega.files):
        if k.lower().startswith('events' + B + 'timetrial' + B): del mega.files[k]
    for k, g in enumerate(groups):
        mega.files['events' + B + 'TimeTrial' + B + 'Ser%05d.xml' % (k + 1)] = series(g, k)
    mega.check(); mega.write()
    ev = os.path.join(mods, 'media', 'Events')
    os.makedirs(ev, exist_ok=True)
    shutil.copyfile(addcar.disc_file(disc, 'media', 'Events', 'OnlineCareer.bik'), os.path.join(ev, 'TimeTrial.bik'))
    loc = addcar.disc_file(disc, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'UIStrings.str')
        if not p: continue
        mp = os.path.join(mods, 'media', 'Loc', lang, 'UIStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        new = addcar.replace_strings(base, {HELP: 'Race the clock alone: one lap from a rolling start, in a car of your own. Set your best times on the local scoreboard.'})
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        open(mp, 'wb').write(new)
        p = addcar.disc_file(disc, 'media', 'Loc', lang, 'GameStrings.str')
        mp = os.path.join(mods, 'media', 'Loc', lang, 'GameStrings.str')
        base = open(mp if os.path.exists(mp) else p, 'rb').read()
        open(mp, 'wb').write(addcar.replace_strings(base, {TITLE: 'Time Trial'}))
    print('Time Trial category: %d events in %d series' % (len(out), len(groups)))


if __name__ == '__main__':
    install(sys.argv[1], sys.argv[2])
