"""Mayhem as a career category (the user's, 3 Nov: "Instead of a cheat code, make Mayhem mode a career
category ... Level 35 Required"): eight one-event series, each on a track with a Mayhem Moment, each with
its own restrictions (a disc series' restrictions and AI field, so the field fits them), all from level
35. runtime/hle_quickrace.c makes any race of these events a Mayhem race (<mods>/mayhem.txt's events
line) and reads the Moments from the same file. Into the mods folder:

  - events\\Mayhem\\Ser00001.xml... (Mega.ca2): the series;
  - strings: the series' names and descriptions, each event's (EventStrings.str), the category's title
    (GameStrings.str) and description (UIStrings.str), every language, in English;
  - categories.txt: the category's line (runtime/hle_career_cats.c), other categories' lines kept;
  - media\\Events\\Events.xpr, Events_LG.xpr: its icon on tile CAT_ICON (tools/mayhemicon.py's art);
    media\\Events\\Mayhem.bik (Club.bik's: every category plays one);
  - MegaXPR.ca2 frontend\\<lang>\\ico_events_lg/sm.xpr: the series' logo on tile LOGO;
  - mayhem.txt: the events, and the Moments (track, place, name, what to do).

  python tools/mayhemseries.py <disc> <mods folder> <art folder (mayhemicon.py's)>
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
from careertimetrial import put_strings

B = '\\'
SERIES_ORDINAL = 108   # after the Drift Championship's 107
EVENT_ORDINAL = 406    # after its 400-405 (the profile keeps 512 medal bytes)
LEVEL = 35
LOGO = 51              # the series logos' tile (ico_events; 51-59 were free)
CATEGORY = ('Mayhem', 'Mayhem', 'Takedowns, boost and over-the-top physics: smash the field into the walls before '
            'they do it to you. Find every Mayhem Moment.', 9, 2)  # folder, title, description, icon tile, place (after Drift)

# (series name, track ordinal, laps, the disc series whose restrictions and AI field it takes, its rules said
# in words, the Mayhem Moment on it (name, what to do, its places: (x, z, radius, top y or None) in the game's
# coordinates, found in the disc's scenery by name (tunnel ceiling, trailers, bridge, storefront, sign, bleachers,
# ambulance) and checked against the AI line; Rio's bend the S-jog at its line points 750-777, the user's ("slightly
# further down the road" than the lone kink at 606-617)), and a restriction added to the disc series' if any
# (the audit, 3 Nov: the level-0 Opens' Class D fields met whatever a level-35 player brought, so the donors are
# now series whose fields fit their restrictions)
SERIES = [
    ('Tunnel Vision', 17, 3, r'events\club\ser00016.xml', 'Supras and RX-7s only.',
     ('Ari-Wall-to', 'Take down an opponent in the Tokyo Tunnel.',
      [(151.1, -206.2, 180, -7.0), (483.9, -319.0, 180, -7.0)])),  # (the only stretch under y -7: the road beside it is above)
    ('Dockyard Demolition', 20, 1, r'events\club\ser00018.xml', 'Heavyweights only.',  # (1 lap: point to point)
     ('Mother Trucker', 'Take down an opponent into the Pacific Shipyards trailers.', [(-503.0, -567.0, 22, None)])),  # (the parked semi's trailer at the road's edge, line points 3397-3415: the only trailer with collision a car can reach; the user's 'trailers you can crash into')
    ('Mountain Wreckage', 10, 1, r'events\club\ser00014.xml', 'Imprezas and Lancers only.',
     ('Suspended', 'Take down an opponent on the bridge in Fujimi Kaido.', [(2152.5, -49.4, 78, None)])),
    ('Big Apple Brawl', 18, 2, r'events\club\ser00015.xml', 'American muscle from before 1975, Class A and below.',
     ("Crash 'R Us", "Take down an opponent in front of the Toys 'R Us in New York.", [(-180.0, -80.0, 30, None)])),  # (the store's south corner: its TOYS R US sign is the building's south face, z -87..-59, 8-18 m up (vbuff toysrus_vb1, texture toys_r_us_002); the road side, z -60..-31, is its Swatch and Foot Locker shops (toys_r_us_001), where it was first put)
    ('Peach State Pileup', 9, 3, r'events\spec\ser00008.xml', 'Class A only.',
     ('Land-Filled Up', 'Take down an opponent in front of the Sunoco sign at Road Atlanta.', [(-577.0, -299.0, 30, None)])),
    ('Rio Rumble', 25, 2, r'events\spec\ser00011.xml', 'Stock Ferrari 360 Modenas only.',
     ("Stick It To 'Em", 'Take down an opponent on the small bend in Rio.', [(-625.1, -807.4, 35, None)])),
    ('Infield Insanity', 5, 3, r'events\club\ser00019.xml', 'Corvettes only.',
     ('Standing Crashvation', 'Take down an opponent in front of the bleachers in the Sunset Peninsula infield.', [(171.0, -400.0, 40, None)])),
    ('Valley of Carnage', 3, 2, r'events\spec\ser00015.xml', 'Class S only.',
     ('Wham-Bulance', 'Take down an opponent in front of the ambulance at Maple Valley.', [(42.0, -448.0, 30, None)])),
]
XP = 6000  # a win's (the level-35 disc series' run 5000-8000)
EXTRA = {'Big Apple Brawl': [('perfclass', '<>', 'S'), ('perfclass', '<>', 'R')]}  # (the GT40 Mk II, S3, against a Class B field)


def build(mega):
    series, strings, events = [], [], []
    for k, (name, track, laps, donor, rule, (moment, todo, _)) in enumerate(SERIES):
        tag = 'Mayhem%d' % k
        src = next(v for n, v in mega.disc.items() if n.lower() == donor.lower()).decode('latin-1')
        restr = re.search(r'\t<Restrictions>.*?</Restrictions>', src, re.S).group(0)
        for a, f, v in EXTRA.get(name, ()):  # (top level: all of them hold, with the donor's)
            restr = restr.replace('\t</Restrictions>', '\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n\t</Restrictions>' % (a, f, v))
        field = re.search(r'\t<AIField>.*?</AIField>', src, re.S).group(0)
        ordinal = EVENT_ORDINAL + k
        events.append((ordinal, track, moment))
        strings += [('IDS_Mod_%s_Name' % tag, name),
                    ('IDS_Mod_%s_Desc' % tag, 'Mayhem: %s Takedowns count, and you can be taken down. Hold the boost '
                                              '(R3) and tap the brake into a corner to drift. Mayhem Moment: %s - %s'
                                              % (rule, moment, todo)),
                    ('IDS_Mod_%s_Event' % tag, '%s Mayhem Moment: %s - %s' % (rule, moment, todo))]
        sc = ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, pts, XP * f // 100)
                     for p, (pts, f) in enumerate(zip((10, 8, 6, 5, 4, 3, 2, 1), (100, 70, 50, 40, 30, 20, 10, 0))))
        ev = ('<event eventid="0" displayname="%s" eventordinal="%d" eventtextid="{IDS_Mod_%s_Name}" eventdescid="{IDS_Mod_%s_Event}" '
              'type="Single" leaderboard="20000">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
              '\t\t<AIField NumAICars="7" random="false" byclass="false" duplicates="false" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting nopitting />\r\n\t\t</AIModeSettings>\r\n'
              '\t\t<Scoring>\r\n%s\t\t</Scoring>\r\n\t</event>') % (name, ordinal, tag, tag, track, laps, sc)
        head = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{IDS_Mod_%s_Name}" seriesdescid="{IDS_Mod_%s_Desc}" '
                'seriesid="58" seriesordinal="%d" seriesorder="%d" Icon="%d" Level="%d">\r\n'
                '\t<Scoring>\r\n' + ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(1, 9)) + '\t</Scoring>\r\n'
                '%s\r\n%s\r\n') % (name, tag, tag, SERIES_ORDINAL + k, k, LOGO, LEVEL, restr, field)
        series.append(head + '\t' + ev + '\r\n</series>\r\n')
    return series, strings, events


def install(disc, mods, art):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    series, strings, events = build(mega)
    loc = addcar.disc_file(disc, 'media', 'Loc')
    ids, cat_ids = None, {}
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
        for name, add in (('GameStrings.str', ('IDS_Mod_Category_Mayhem', CATEGORY[1])),
                          ('UIStrings.str', ('IDS_Mod_Category_Mayhem_Help', CATEGORY[2]))):
            src = addcar.disc_file(disc, 'media', 'Loc', lang, name)
            mp = os.path.join(mods, 'media', 'Loc', lang, name)
            d = put_strings(open(mp if os.path.exists(mp) else src, 'rb').read(), [add])
            got = addcar.string_ids(d)[add[0]]
            if cat_ids.setdefault(name, got) != got: raise SystemExit('%s %s: the string ids differ between languages' % (lang, name))
            open(mp, 'wb').write(d)
    for k in list(mega.files):
        if k.lower().startswith('events' + B + 'mayhem' + B): del mega.files[k]
    for k, x in enumerate(series):
        x = re.sub(r'\{(IDS_\w+)\}', lambda m: str(ids[m.group(1)]), x)
        mega.files['events' + B + CATEGORY[0] + B + 'Ser%05d.xml' % (k + 1)] = x.encode('latin-1')
    mega.check(); mega.write()
    # the category: its icon a tile of the strips (the mods folder's, Drift's tile already in them), its video, its line
    ev = os.path.join(mods, 'media', 'Events')
    os.makedirs(ev, exist_ok=True)
    for n, png, size in (('Events.xpr', 'mayhem_cat_sm.png', (108, 60, 1)), ('Events_LG.xpr', 'mayhem_cat_lg.png', (210, 117, 1))):
        mp = os.path.join(ev, n)
        d = open(mp if os.path.exists(mp) else addcar.disc_file(disc, 'media', 'Events', n), 'rb').read()
        while addseries.tiles_in(d, size) <= CATEGORY[3]: d = addseries.grow(d, size)
        d = addseries.put_tile(d, CATEGORY[3], addseries.image(os.path.join(art, png), *size[:2]), size)
        open(mp, 'wb').write(d)
    shutil.copyfile(addcar.disc_file(disc, 'media', 'Events', 'Club.bik'), os.path.join(ev, CATEGORY[0] + '.bik'))
    cp = os.path.join(mods, 'categories.txt')
    keep = [l for l in (open(cp).read().splitlines() if os.path.exists(cp) else []) if not l.startswith(CATEGORY[0] + ' ')]
    open(cp, 'w').write('\n'.join(keep + ['%s 2 %d %d %d %d' % (CATEGORY[0], cat_ids['GameStrings.str'], cat_ids['UIStrings.str'],
                                                                 CATEGORY[3], CATEGORY[4])]) + '\n')
    # the series' logo on tile LOGO of both strips in every language
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    imgs = {'lg': addseries.image(os.path.join(art, 'mayhem_lg.png'), *addseries.LG[:2]),
            'sm': addseries.image(os.path.join(art, 'mayhem_sm.png'), *addseries.SM[:2])}
    for k in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
        if not m: continue
        size = addseries.LG if m.group(1).lower() == 'lg' else addseries.SM
        while addseries.tiles_in(xpr.files[k], size) <= LOGO: xpr.files[k] = addseries.grow(xpr.files[k], size)
        xpr.files[k] = addseries.put_tile(xpr.files[k], LOGO, imgs[m.group(1).lower()], size)
    xpr.check(); xpr.write()
    # the runtime's file: the events, and the Moments' places
    moments = ''.join('moment %d %.1f %.1f %g %s %s|%s\n' % (track, x, z, r, '-' if top is None else '%g' % top, moment, todo)
                      for _, track, _, _, _, (moment, todo, places) in SERIES for x, z, r, top in places)
    open(os.path.join(mods, 'mayhem.txt'), 'w').write(
        '# Mayhem (runtime/hle_quickrace.c): its events (tools/mayhemseries.py), then a line a Mayhem Moment\'s place:\n'
        '# moment <track ordinal> <x> <z> <radius m> <top y or -> <name>|<what to do>\n'
        'events ' + ' '.join(str(o) for o, _, _ in events) + '\n' + moments)
    print('Mayhem category: strings %d, %d, icon %d; %d series, events %s' % (cat_ids['GameStrings.str'], cat_ids['UIStrings.str'],
                                                                             CATEGORY[3], len(series), ' '.join(str(o) for o, _, _ in events)))


if __name__ == '__main__':
    if len(sys.argv) != 4: raise SystemExit(__doc__)
    install(*sys.argv[1:])
