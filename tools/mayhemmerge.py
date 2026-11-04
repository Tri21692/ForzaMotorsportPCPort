"""The Mayhem category's eight one-race series made one series of eight races, in place (the user's, 4 Nov: "make 1
event with all the races we have made, inside of that. Later, we'll make a 2nd event with the same amount of races").
events\\Mayhem\\Ser00001.xml keeps its seriesordinal (108; the career keeps results by it) and becomes the tour:
its name and description new strings, its logo tile 51 redrawn (tools/mayhemlogos.py's look: MAYHEM over TOUR),
its restrictions and AI field Peach State Pileup's (Class A: the disc's series have no restrictions of their own
per race, and one field races every event), and the eight races in tools/mayhemseries.py's order, each its own
event ordinal (406-413: <mods>/mayhem.txt's, the Moments'), track, laps, name and Moment text as before. Ser00002-8
removed. Idempotent: a merged Ser00001 is left as it is.

  python tools/mayhemmerge.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import mayhemlogos
import mayhemseries

B = '\\'
NAME = 'Mayhem Tour'
DESC = ('Eight races, one tour: takedowns, boost and over-the-top physics on every track, and a Mayhem Moment to find '
        'on each. Open to Class A cars.')
FIELD_FROM = 'Peach State Pileup'
COLOURS = ((120, 10, 20), (250, 140, 20))


CR_PER_KM = 1500  # 1st place's credits a km of the race (the disc's races at levels 30-39: median 1,471)


def prizes(mega, key):
    """Each race's 1st-place credits (its xp, the "1st Place" the menu shows) CR_PER_KM times its distance (the AI
    line's length times the laps), to the hundred; 2nd and 3rd kept at their shares of 1st (the user's, 4 Nov: "adjust
    the reward CR of each race accordingly": all eight paid 6,000)."""
    import numpy as np
    import laptime
    tl = bytes(next(v for k, v in mega.files.items() if k.lower().endswith('tracklist.xml'))).decode('utf-8', 'replace')
    names = {int(a['Ordinal']): a['name'] for a in (dict(re.findall(r'(\w+)="([^"]*)"', t)) for t in re.findall(r'<track\b(.*?)/>', tl, re.S)) if 'Ordinal' in a}
    x = mega.files[key].decode('latin-1')
    def one(m):
        e = m.group(0)
        t = int(re.search(r'<track Ordinal="(\d+)"', e).group(1)); laps = int(re.search(r'<laps count="(\d+)"', e).group(1))
        p, _, closed = laptime.line(mega, names[t])
        km = float(np.linalg.norm(np.diff(np.vstack([p, p[:1]]) if closed else p, axis=0), axis=1).sum()) * laps / 1000
        xp = dict((int(a), int(b)) for a, b in re.findall(r'<score pos="(\d)"[^>]*xp="(\d+)"', e))
        first = int(round(km * CR_PER_KM / 100)) * 100
        new = {k: (first if k == 1 else int(round(first * v / xp[1] / 100)) * 100) for k, v in xp.items() if xp.get(1)}
        print('  %-22s %-20s %d lap%s %5.1f km: 1st %6d -> %6d' % (re.search(r'displayname="([^"]*)"', e).group(1), names[t], laps, '' if laps == 1 else 's', km, xp.get(1, 0), first))
        return re.sub(r'(<score pos="(\d)"[^>]*xp=")(\d+)"', lambda g: '%s%d"' % (g.group(1), new.get(int(g.group(2)), int(g.group(3)))), e)
    mega.files[key] = re.sub(r'<event\b.*?</event>', one, x, flags=re.S).encode('latin-1')


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    keys = sorted(k for k in mega.files if k.lower().startswith('events' + B + 'mayhem' + B) and k.lower().endswith('.xml'))
    first = next(k for k in keys if k.lower().endswith('ser00001.xml'))
    x1 = mega.files[first].decode('latin-1')
    if x1.count('<event ') > 1:
        print('%s: merged already; the prizes:' % first)
        prizes(mega, first)
        mega.check(); mega.write()
        return
    by = {}
    for k in keys:
        x = mega.files[k].decode('latin-1')
        by[re.search(r'displayname="([^"]*)"', x).group(1)] = x
    order = [s[0] for s in mayhemseries.SERIES]
    missing = [n for n in order if n not in by]
    if missing: raise SystemExit('no series named %s' % ', '.join(missing))
    events = []
    for i, n in enumerate(order):
        e = re.search(r'\t<event\b.*?</event>', by[n], re.S).group(0)
        events.append(re.sub(r'eventid="\d+"', 'eventid="%d"' % i, e, count=1))
    donor = by[FIELD_FROM]
    restr = re.search(r'\t<Restrictions>.*?</Restrictions>', donor, re.S).group(0)
    field = re.search(r'\t<AIField>.*?</AIField>', donor, re.S).group(0)
    # the strings, every language (one id for all: checked)
    loc = os.path.join(mods, 'media', 'Loc')
    ids = None
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()  # (read before the file is opened to write: that empties it)
        have = addcar.string_ids(d)
        if 'IDS_Mod_MayhemTour_Name' not in have:
            d = addcar.write_strings(d, [('IDS_Mod_MayhemTour_Name', NAME), ('IDS_Mod_MayhemTour_Desc', DESC)])
            have = addcar.string_ids(d)
        got = (have['IDS_Mod_MayhemTour_Name'], have['IDS_Mod_MayhemTour_Desc'])
        if ids is not None and got != ids: raise SystemExit('%s: the string ids differ between languages (%s, %s)' % (lang, got, ids))
        ids = got
        open(mp, 'wb').write(d)
    head = re.search(r'<series [^>]*>', x1).group(0)
    head = re.sub(r'displayname="[^"]*"', 'displayname="%s"' % NAME, head)
    head = re.sub(r'seriesnameid="\d+"', 'seriesnameid="%d"' % ids[0], head)
    head = re.sub(r'seriesdescid="\d+"', 'seriesdescid="%d"' % ids[1], head)
    head = re.sub(r'Icon="\d+"', 'Icon="%d"' % mayhemlogos.FIRST, head)
    scoring = re.search(r'\t<Scoring>.*?</Scoring>', x1, re.S).group(0)
    out = '<?xml version="1.0"?>\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n</series>\r\n' % (head, scoring, restr, field, '\r\n'.join(events))
    mega.files[first] = out.encode('latin-1')
    for k in keys:
        if k != first: del mega.files[k]
    mega.check(); mega.write()
    print('%s: %s, %d races (events %s); %d series removed' % (first, NAME, len(events),
          ', '.join(re.search(r'eventordinal="(\d+)"', e).group(1) for e in events), len(keys) - 1))
    # the logo
    xpr = addcar.Archive(disc, mods, 'MegaXPR.ca2')
    lg, sm = mayhemlogos.logo('Tour', COLOURS, *addseries.LG[:2]), mayhemlogos.logo('Tour', COLOURS, *addseries.SM[:2])
    for k in sorted(xpr.files):
        m = re.match(r'frontend\\[a-z]{2}\\ico_events_(lg|sm)\.xpr$', k, re.I)
        if not m: continue
        size = addseries.LG if m.group(1).lower() == 'lg' else addseries.SM
        xpr.files[k] = addseries.put_tile(xpr.files[k], mayhemlogos.FIRST, lg if m.group(1).lower() == 'lg' else sm, size)
    xpr.check(); xpr.write()
    print('logo: tile %d' % mayhemlogos.FIRST)


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
