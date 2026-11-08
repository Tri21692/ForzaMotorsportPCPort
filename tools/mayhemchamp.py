"""The Mayhem Tour Championship, and the Tours' classes (the user's, 7 Nov: "Let's do 1, 5, Lights, Camera, Wrecktion,
and R-Vehicular Damage (Take out an opponent in front of the RVs on Road America. There are multiple spots so add them
all"; "Tour II = S Class, Tour Championship = R Class"; "Tour Championship is unlocked at level 45"), in place:

  - events\\Mayhem\\Ser00003.xml (Mega.ca2): the Championship, a new seriesordinal (the highest plus one), level 45,
    Class R (any R sub-class) with the Class R-GTS Championship's AI field (the disc's level-45 R series), its own logo
    (tile mayhemlogos.FIRST + 2), four races, events 414-417, each with a new Mayhem Moment; prizes 1,800 CR a km (the
    disc's level-45 races: median 1,761);
  - events\\Mayhem\\Ser00002.xml: Mayhem Tour II Class S, with the disc's level-30 Class S Championship's AI field;
  - strings: the Championship's and its races', Tour II's description (Class S), and every Tour race's description
    led by its tour's class (they still had the one-race series' rules: "Supras and RX-7s only.");
  - mayhem.txt: the events and the Moments' places (docs/research/mayhem-championship.md; the RVs from
    E:\\xbrt_scr\\moments2\\rv_zones.py: every stretch of the line with RVs or campers within ~60 m, 16 places).

Idempotent: what's there already is left as it is (the string fixes are made again).

  python tools/mayhemchamp.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import mayhemlogos
import mayhemmerge

B = '\\'
NAME = 'Mayhem Tour Championship'
LEVEL = 45
CLASS = 'R'
EVENT0 = 414           # after the Tour's 406-413 (the profile keeps 512 medal bytes)
ICON = mayhemlogos.FIRST + 2
CR_PER_KM = 1800
FIELD_FROM = r'events\proseries\Ser00013.xml'   # Class R-GTS Championship, level 45 (the disc's)
TOUR2_CLASS, TOUR2_FIELD = 'S', r'events\spec\Ser00017.xml'  # Class S Championship, level 30 (the mods' file, checked by name)
DESC = ('The finale: four races of takedowns, boost and over-the-top physics in race cars, with a Mayhem Moment to find '
        'on each. Open to Class R cars.')
DESC2 = ('Four more races of takedowns, boost and over-the-top physics, with a Mayhem Moment to find on each. Open to '
         'Class S cars. First place receives the Chevrolet Corvette ZR1 (C7).')  # (tools/prizecars.py's prize: kept if this is re-run)
COLOURS = ((25, 20, 15), (215, 170, 40))  # black to gold
RV = 'Take down an opponent in front of the RVs at Road America.'
# (race name, track ordinal, laps, Moment, what to do, places: (x, z, radius))
RACES = [
    ('Laguna Lunacy', 1, 2, 'Re-Tired', 'Take down an opponent into the Turn 11 tyre stacks at Laguna Seca.', [(-124.0, 497.0, 30)]),
    ('Tsukuba Tussle', 26, 3, 'Dunlop-Sided', 'Take down an opponent under the Dunlop bridge at Tsukuba.', [(85.0, -5.0, 30)]),
    # (every camera crane whose boom reaches over the road, the user's 8 Nov; a 4th value: another track, Silverstone's 2 and 47)
    ('Alpine Avalanche', 27, 2, 'Lights, Camera, Wreck-tion', 'Take down an opponent under a camera crane at the Alpine Ring or Silverstone.',
     [(-180.0, -125.0, 25), (-94.0, -304.0, 25), (-237.0, 315.0, 25), (94.6, 799.0, 25, 2), (408.0, 316.0, 25, 2), (94.6, 799.0, 25, 47), (408.0, 316.0, 25, 47)]),
    ('Road America Rampage', 16, 1, 'R-Vehicular Damage', RV, [
        (504.9, 324.7, 45), (511.0, 213.1, 32), (515.1, 127.1, 32), (518.8, 29.2, 26), (522.3, -56.7, 32),
        (526.5, -172.7, 45), (530.0, -262.6, 45), (533.5, -356.5, 45), (538.0, -474.5, 32), (542.0, -578.4, 34),
        (207.2, -729.2, 26), (87.5, -730.9, 28), (107.3, -218.3, 45), (131.2, -131.5, 45), (28.7, 448.6, 28),
        (355.9, 717.0, 30)]),
]


def text_of(d, sid):
    e1, text, _, _ = addcar.read_strings(d)
    for i, o in e1[:-1]:
        if i == sid:
            end = o * 2
            while text[end:end + 2] != b'\0\0': end += 2
            return text[o * 2:end].decode('utf-16-le')
    return None


def series_xml(mega, name, want):
    """The mods folder's series file (the mods renumber some: the disc's spec\\Ser00017 is the Ferrari Supercars Event,
    whose three Ferraris made Tour II take no S car, 7 Nov), checked by its name."""
    x = next(bytes(v) for k, v in mega.files.items() if k.lower() == name.lower()).decode('latin-1')
    got = re.search(r'<series [^>]*displayname="([^"]*)"', x).group(1)
    if got != want: raise SystemExit('%s is %r, not %r' % (name, got, want))
    return x


def block(x, tag):
    return re.search(r'\t<%s>.*?</%s>' % (tag, tag), x, re.S).group(0)


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    keys = {k.lower(): k for k in mega.files}
    k1, k2 = keys[B.join(('events', 'mayhem', 'ser00001.xml'))], keys[B.join(('events', 'mayhem', 'ser00002.xml'))]
    k3 = k1[:-len('Ser00001.xml')] + 'Ser00003.xml'
    have3 = k3.lower() in keys
    x1, x2 = mega.files[k1].decode('latin-1'), mega.files[k2].decode('latin-1')
    # strings, every language (one id for all: checked)
    want = [('IDS_Mod_MayhemChamp_Name', NAME), ('IDS_Mod_MayhemChamp_Desc', DESC)]
    for i, (race, _, _, moment, todo, _) in enumerate(RACES):
        want += [('IDS_Mod_MayhemChamp%d_Name' % i, race),
                 ('IDS_Mod_MayhemChamp%d_Event' % i, 'Class %s only. Mayhem Moment: %s - %s' % (CLASS, moment, todo))]
    fix = {int(re.search(r'seriesdescid="(\d+)"', x2).group(1)): DESC2}
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
        changes = dict(fix)
        for x, cls in ((x1, 'A'), (x2, TOUR2_CLASS)):  # each Tour race's description led by its tour's class
            for sid in re.findall(r'<event [^>]*eventdescid="(\d+)"', x):
                t = text_of(d, int(sid))
                if t and ' Mayhem Moment: ' in t:
                    changes[int(sid)] = 'Class %s only. Mayhem Moment: %s' % (cls, t.split(' Mayhem Moment: ', 1)[1])
        changes = {k: v for k, v in changes.items() if text_of(d, k) != v}
        if changes: d = addcar.replace_strings(d, changes)
        open(mp, 'wb').write(d)
    sid = dict(zip((w[0] for w in want), ids))
    # Tour II: Class S, the disc's Class S field
    s_src = series_xml(mega, TOUR2_FIELD, "Class S Championship")
    x2 = x2.replace(block(x2, 'Restrictions'), block(s_src, 'Restrictions')).replace(block(x2, 'AIField'), block(s_src, 'AIField'))
    mega.files[k2] = x2.encode('latin-1')
    print('%s: Mayhem Tour II, Class %s' % (k2, TOUR2_CLASS))
    # the Championship
    if have3:
        print('%s there already' % k3)
    else:
        r_src = series_xml(mega, FIELD_FROM, "Class R-GTS Championship")
        ords = [int(o) for k in mega.files if k.lower().startswith('events' + B)
                for o in re.findall(r'seriesordinal="(\d+)"', mega.files[k].decode('latin-1'))]
        used = {int(o) for k in mega.files if k.lower().startswith('events' + B)
                for o in re.findall(r'eventordinal="(\d+)"', mega.files[k].decode('latin-1'))}
        clash = used & set(range(EVENT0, EVENT0 + len(RACES)))
        if clash: raise SystemExit('event ordinals in use: %s' % sorted(clash))
        sc = ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, pts, f * 100)
                     for p, (pts, f) in enumerate(zip((10, 8, 6, 5, 4, 3, 2, 1), (100, 70, 50, 40, 30, 20, 10, 0))))
        evs = []
        for i, (race, track, laps, _, _, _) in enumerate(RACES):
            evs.append(('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="%d" eventdescid="%d" type="Single" leaderboard="20000">\r\n'
                        '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
                        '\t\t<AIField NumAICars="7" random="false" byclass="false" duplicates="false" />\r\n'
                        '\t\t<AIModeSettings>\r\n\t\t\t<pitting nopitting />\r\n\t\t</AIModeSettings>\r\n'
                        '\t\t<Scoring>\r\n%s\t\t</Scoring>\r\n\t</event>')
                       % (i, race, EVENT0 + i, sid['IDS_Mod_MayhemChamp%d_Name' % i], sid['IDS_Mod_MayhemChamp%d_Event' % i], track, laps, sc))
        head = ('<series displayname="%s" seriesnameid="%d" seriesdescid="%d" seriesid="58" seriesordinal="%d" seriesorder="2" '
                'Icon="%d" Level="%d">') % (NAME, sid['IDS_Mod_MayhemChamp_Name'], sid['IDS_Mod_MayhemChamp_Desc'], max(ords) + 1, ICON, LEVEL)
        restr = '\t<Restrictions>\r\n\t\t<Restriction Attrib="perfclass" Func="=" Value="%s" />\r\n\t</Restrictions>' % CLASS
        out = '<?xml version="1.0"?>\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n</series>\r\n' % (head, block(x1, 'Scoring'), restr, block(r_src, 'AIField'), '\r\n'.join(evs))
        mega.files[k3] = out.encode('latin-1')
        mayhemmerge.CR_PER_KM = CR_PER_KM
        mayhemmerge.prizes(mega, k3)
        print('%s: %s (series %d, level %d, Class %s), events %d-%d' % (k3, NAME, max(ords) + 1, LEVEL, CLASS, EVENT0, EVENT0 + len(RACES) - 1))
    mega.check(); mega.write()
    if not have3:
        xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
        lg, sm = mayhemlogos.logo('Tour Championship', COLOURS, *addseries.LG[:2]), mayhemlogos.logo('Tour Championship', COLOURS, *addseries.SM[:2])
        for k in sorted(xpr.files):
            m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
            if not m: continue
            size = addseries.LG if m.group(1).lower() == 'lg' else addseries.SM
            while addseries.tiles_in(xpr.files[k], size) <= ICON: xpr.files[k] = addseries.grow(xpr.files[k], size)
            xpr.files[k] = addseries.put_tile(xpr.files[k], ICON, lg if m.group(1).lower() == 'lg' else sm, size)
        xpr.check(); xpr.write()
        print('logo: tile %d' % ICON)
    # mayhem.txt: the events and the Moments
    mt = os.path.join(mods, 'mayhem.txt')
    lines = open(mt).read().splitlines()
    ev = [i for i, l in enumerate(lines) if l.startswith('events')][0]
    have_ev = lines[ev].split()[1:]
    lines[ev] = 'events ' + ' '.join(have_ev + [str(EVENT0 + i) for i in range(len(RACES)) if str(EVENT0 + i) not in have_ev])
    names = {l.split(None, 6)[6].split('|')[0] for l in lines if l.startswith('moment ')}
    for _, track, _, moment, todo, places in RACES:
        if moment in names: continue
        lines += ['moment %d %.1f %.1f %g - %s|%s' % (pl[3] if len(pl) > 3 else track, pl[0], pl[1], pl[2], moment, todo) for pl in places]
    open(mt, 'w').write('\n'.join(lines) + '\n')
    print('mayhem.txt: %s' % lines[ev])


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
