"""The Mayhem Tour split in two, in place (the user's, 7 Nov: "split the current mayhem event into 2 events, with the
latter being locked until level 30"): events\\Mayhem\\Ser00001.xml keeps its seriesordinal (108: the career keeps
results by it), its name, logo and level, and its first four races (Tokyo, Pacific Shipyards, Fujimi, New York);
Ser00002.xml, "Mayhem Tour II", a new seriesordinal (the highest of all the series' plus one), level 30, its own logo
(tile mayhemlogos.FIRST + 1, MAYHEM over TOUR II), the same rules, field and scoring, and the last four races (Road
Atlanta, Rio, Sunset, Maple Valley). Each race keeps its event ordinal (mayhem.txt's and the Moments'). New strings:
the two descriptions (four races each) and the second's name. Idempotent: with a Ser00002 there, nothing is done.

  python tools/mayhemsplit.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import mayhemlogos

B = '\\'
SPLIT = 4
LEVEL2 = 30
NAME2 = 'Mayhem Tour II'
DESC1 = ('Four races of takedowns, boost and over-the-top physics, with a Mayhem Moment to find on each. Open to Class '
         'A cars.')
DESC2 = ('Four more races of takedowns, boost and over-the-top physics, with a Mayhem Moment to find on each. Open to '
         'Class A cars.')
COLOURS2 = ((20, 20, 90), (200, 40, 160))


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    keys = {k.lower(): k for k in mega.files}
    k1 = keys.get(B.join(('events', 'mayhem', 'ser00001.xml')))
    if not k1: raise SystemExit('no Mayhem Ser00001')
    k2 = k1[:-len('Ser00001.xml')] + 'Ser00002.xml'
    if k2.lower() in keys:
        print('%s there already: split before' % k2)
        return
    x = bytes(mega.files[k1]).decode('latin-1')
    events = re.findall(r'\t<event\b.*?</event>', x, re.S)
    if len(events) <= SPLIT: raise SystemExit('%d races: nothing to split' % len(events))
    ords = [int(o) for k in mega.files if k.lower().startswith('events' + B) for o in re.findall(r'seriesordinal="(\d+)"', bytes(mega.files[k]).decode('latin-1'))]
    ord2 = max(ords) + 1
    # strings, every language (one id for all: checked)
    loc = os.path.join(mods, 'media', 'Loc')
    ids = None
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()
        want = [('IDS_Mod_MayhemTour_Desc4', DESC1), ('IDS_Mod_MayhemTour2_Name', NAME2), ('IDS_Mod_MayhemTour2_Desc', DESC2)]
        have = addcar.string_ids(d)
        add = [w for w in want if w[0] not in have]
        if add: d = addcar.write_strings(d, add); have = addcar.string_ids(d)
        got = tuple(have[w[0]] for w in want)
        if ids is not None and got != ids: raise SystemExit('%s: the string ids differ between languages (%s, %s)' % (lang, got, ids))
        ids = got
        open(mp, 'wb').write(d)
    head = re.search(r'<series [^>]*>', x).group(0)
    body_start, body_end = x.index(head) + len(head), x.index(events[0])
    common = x[body_start:body_end]  # (scoring, restrictions, the field: the same for both)
    def series(h, evs):
        evs = [re.sub(r'eventid="\d+"', 'eventid="%d"' % i, e, count=1) for i, e in enumerate(evs)]
        return '<?xml version="1.0"?>\r\n' + h + common + '\r\n'.join(evs) + '\r\n</series>\r\n'
    h1 = re.sub(r'seriesdescid="\d+"', 'seriesdescid="%d"' % ids[0], head)
    h2 = head
    for a, v in (('displayname', NAME2), ('seriesnameid', ids[1]), ('seriesdescid', ids[2]), ('seriesordinal', ord2),
                 ('seriesorder', 1), ('Icon', mayhemlogos.FIRST + 1), ('Level', LEVEL2)):
        h2 = re.sub(r'\b%s="[^"]*"' % a, '%s="%s"' % (a, v), h2)
    mega.files[k1] = series(h1, events[:SPLIT]).encode('latin-1')
    mega.files[k2] = series(h2, events[SPLIT:]).encode('latin-1')
    mega.check(); mega.write()
    say = lambda evs: ', '.join(re.search(r'displayname="([^"]*)"', e).group(1) for e in evs)
    print('%s: Mayhem Tour, %s' % (k1, say(events[:SPLIT])))
    print('%s: %s (series %d, level %d), %s' % (k2, NAME2, ord2, LEVEL2, say(events[SPLIT:])))
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    lg, sm = mayhemlogos.logo('Tour II', COLOURS2, *addseries.LG[:2]), mayhemlogos.logo('Tour II', COLOURS2, *addseries.SM[:2])
    for k in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
        if not m: continue
        size = addseries.LG if m.group(1).lower() == 'lg' else addseries.SM
        xpr.files[k] = addseries.put_tile(xpr.files[k], mayhemlogos.FIRST + 1, lg if m.group(1).lower() == 'lg' else sm, size)
    xpr.check(); xpr.write()
    print('logo: tile %d' % (mayhemlogos.FIRST + 1))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
