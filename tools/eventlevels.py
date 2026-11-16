"""The added series' classes matched to the levels they unlock at (the user's, 15 Nov: "make sure the class
requirements for the custom events match the level they're unlocked at"; asked which to change: "Change the
levels"). The game's own Professional list is the ladder: Class C at level 10, B 15, A 20, S 30, R-GT 40, R-GTS 45,
R-P1 50. In place (the series keep their ordinals), idempotent:

  - Rear-Engine Rebellion (Class S) 25 -> 30, Shipyard Grand Prix (R-GT) 30 -> 40, Nordschleife Endurance (R-GTS)
    40 -> 45;
  - the Time Trials: Class C 5 -> 10, B 10 -> 15, A 15 -> 20, S 20 -> 30, R-GT 30 -> 40, R-GTS 40 -> 45 (Class D
    open from the start and R-P1 at 50, as they were);
  - Mayhem Tour: level 15 is the user's own (7 Nov: "Mayhem Category unlocks at 15, and so does the event inside"),
    so its class moves: Class A -> Class B, with the disc's Class B Championship's field (Professional), and its
    series' and races' descriptions saying so, in every language.

  python tools/eventlevels.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import mayhemchamp

LEVELS = {  # (folder, series' name): level
    ('spec', 'Rear-Engine Rebellion'): 30,
    ('spec', 'Shipyard Grand Prix'): 40,
    ('spec', 'Nordschleife Endurance'): 45,
    ('timetrial', 'Class C Time Trials'): 10,
    ('timetrial', 'Class B Time Trials'): 15,
    ('timetrial', 'Class A Time Trials'): 20,
    ('timetrial', 'Class S Time Trials'): 30,
    ('timetrial', 'Class R-GT Time Trials'): 40,
    ('timetrial', 'Class R-GTS Time Trials'): 45,
}
TOUR = ('mayhem', 'Mayhem Tour', 'A', 'B', ('spec', 'Class B Championship'))  # folder, name, class from, to, the field's source (the disc's)


def head(x):
    h = re.search(r'<series [^>]*>', x).group(0)
    return re.search(r'displayname="([^"]*)"', h).group(1), h


def block(x, tag):
    return re.search(r'<%s>.*?</%s>' % (tag, tag), x, re.S).group(0)


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    series = {}
    for k in mega.files:
        m = re.match(r'(?i)events\\(\w+)\\ser\d+\.xml$', k)
        if m: series[(m.group(1).lower(), head(mega.files[k].decode('latin-1'))[0])] = k
    changed = 0
    for key, level in LEVELS.items():
        k = series.get(key) or series[(key[0], 'Eliminator')]  # (Nordschleife Endurance, once tools/eliminator.py has made it over)
        x = mega.files[k].decode('latin-1')
        x2 = re.sub(r'(<series\b[^>]*\bLevel=")-?\d+"', lambda g: g.group(1) + '%d"' % level, x, count=1)
        print('%-26s level %s -> %d%s' % (key[1], re.search(r'Level="(-?\d+)"', x).group(1), level, '' if x2 != x else ' (already)'))
        if x2 != x: mega.files[k] = x2.encode('latin-1'); changed += 1
    folder, name, c0, c1, src = TOUR
    k = series[(folder, name)]
    x = mega.files[k].decode('latin-1')
    dk = next(d for d in mega.disc if re.match(r'(?i)events\\%s\\ser\d+\.xml$' % src[0], d) and head(mega.disc[d].decode('latin-1'))[0] == src[1])
    s = mega.disc[dk].decode('latin-1')
    x2 = x.replace(block(x, 'Restrictions'), block(s, 'Restrictions')).replace(block(x, 'AIField'), block(s, 'AIField'))
    assert 'Value="%s"' % c1 in block(x2, 'Restrictions')
    print('%-26s Class %s -> %s, the field %s%s' % (name, c0, c1, dk, '' if x2 != x else ' (already)'))
    if x2 != x: mega.files[k] = x2.encode('latin-1'); changed += 1
    # the Professional list shows its series in their files' order: kept by level (Shipyard Grand Prix, now 40, stood
    # among the 30s), a stable sort, the contents moved between the file names, each slot keeping its seriesorder
    ks = sorted((k for k in mega.files if re.match(r'(?i)events\\spec\\ser\d+\.xml$', k)), key=str.lower)
    xs = [mega.files[k].decode('latin-1') for k in ks]
    lvl = lambda x: int(re.search(r'<series [^>]*Level="(-?\d+)"', x).group(1))
    order = lambda x: re.search(r'<series [^>]*seriesorder="(\d+)"', x).group(1)
    slots = [order(x) for x in xs]
    by = sorted(range(len(xs)), key=lambda i: lvl(xs[i]))
    for k, i, so in zip(ks, by, slots):
        y = re.sub(r'(<series [^>]*seriesorder=")\d+"', lambda g: g.group(1) + so + '"', xs[i], count=1)
        if mega.files[k] != y.encode('latin-1'):
            mega.files[k] = y.encode('latin-1'); changed += 1
            print('%s: %s (level %d)' % (k, head(y)[0], lvl(y)))
    if changed: mega.check(); mega.write()
    # the tour's descriptions
    ids = [int(re.search(r'seriesdescid="(\d+)"', x).group(1))] + [int(i) for i in re.findall(r'<event [^>]*eventdescid="(\d+)"', x)]
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()
        changes = {}
        for i in ids:
            t = mayhemchamp.text_of(d, i)
            if t and 'Class %s' % c0 in t: changes[i] = t.replace('Class %s' % c0, 'Class %s' % c1)
        if changes:
            open(mp, 'wb').write(addcar.replace_strings(d, changes))
            print('%s: %d descriptions' % (lang, len(changes)))
            if lang.lower().startswith('en'):
                for i, t in changes.items(): print('   %d: %s' % (i, t))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
