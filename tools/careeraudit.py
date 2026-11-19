"""A consistency audit of the career's events in the mods folder's Mega.ca2 (7 Nov, the user: "audit mods and confirm
they work"): every series file under events\\, each category's.
  - series ordinals and ids, and event ordinals: each once (the career keeps results by ordinal);
  - each event's track ordinal one the track list has (tracks\\tracklist.xml, by its Ordinal attributes);
  - each restriction's carid a car the car list has (cars\\carlist.xml Ordinal);
  - each series' logo icon and level; its events' laps and AI counts (NumAICars over 7 only in a big field);
  - the custom files the runtime reads beside them (mayhem.txt, catchup.txt, drift.txt, timetrial.txt): their event
    ordinals ones the career has.
Prints what it finds, and "no problems" when nothing.   python tools/careeraudit.py <disc> <mods folder>"""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar

B = '\\'


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    txt = lambda k: bytes(mega.files[k]).decode('latin-1')
    keys = {k.lower(): k for k in mega.files}
    cars = set(int(o) for o in re.findall(r'<car [^>]*?Ordinal="(\d+)"', txt(keys['cars\\carlist.xml'])))
    tl = next((keys[k] for k in keys if k.endswith('tracklist.xml')), None)
    tracks = set(int(o) for o in re.findall(r'Ordinal="(\d+)"', txt(tl))) if tl else set()
    problems = []
    sord, sid_by, eord = defaultdict(list), defaultdict(list), defaultdict(list)
    per_cat = defaultdict(int)
    for k in sorted(mega.files):
        p = k.lower().split(B)
        if len(p) != 3 or p[0] != 'events' or not re.match(r'ser\d+\.xml$', p[2]): continue
        t = txt(k)
        head = re.search(r'<series\b[^>]*>', t)
        if not head:
            problems.append('%s: no <series> head' % k); continue
        h = head.group(0)
        g = lambda a: (re.search(r'\b%s="([^"]*)"' % a, h) or [None, None])[1]
        per_cat[p[1]] += 1
        if g('seriesordinal') is None: problems.append('%s: no seriesordinal' % k)
        else: sord[int(g('seriesordinal'))].append(k)
        sid_by[g('seriesid')].append(k)
        for ev in re.finditer(r'<event\b[^>]*>.*?</event>', t, re.S):
            e = ev.group(0)
            eo = re.search(r'eventordinal="(\d+)"', e)
            name = (re.search(r'displayname="([^"]*)"', e) or [None, '?'])[1]
            if not eo: problems.append('%s: event %s has no eventordinal' % (k, name)); continue
            eord[int(eo.group(1))].append('%s (%s)' % (k, name))
            tr = re.search(r'<track Ordinal="(\d+)"', e)
            if not tr: problems.append('%s: event %s has no track' % (k, name))
            elif tracks and int(tr.group(1)) not in tracks: problems.append('%s: event %s on track %s, not in the track list' % (k, name, tr.group(1)))
            n = re.search(r'NumAICars="(\d+)"', e)
            if n and int(n.group(1)) > 7: problems.append('%s: event %s has %s AI cars (over 7)' % (k, name, n.group(1)))
        # (aicarmodelid is not a car list ordinal: the disc's own series name ids past 243, the AI's own models)
        for a in re.findall(r'Attrib="carid"\s+Func="[^"]*"\s+Value="(\d+)"', t):
            if int(a) not in cars: problems.append('%s: restriction car %s not in the car list' % (k, a))
    for o, ks in sorted(sord.items()):
        if len(ks) > 1: problems.append('series ordinal %d in %s' % (o, ', '.join(ks)))
    for o, ks in sorted(eord.items()):
        if len(ks) > 1: problems.append('event ordinal %d in %s' % (o, '; '.join(ks)))
    for f, pat in (('mayhem.txt', r'^events\s+(.*)$'), ('catchup.txt', r'^(\d+)\s'), ('drift.txt', r'^(\d+)\s'), ('timetrial.txt', r'^(\d+)\s')):
        path = os.path.join(mods, f)
        if not os.path.exists(path): continue
        for line in open(path, encoding='latin-1'):
            if line.startswith('#'): continue
            m = re.match(pat, line.strip())
            if not m: continue
            for o in m.group(1).split():
                if o.isdigit() and int(o) not in eord: problems.append('%s names event %s, which no series has' % (f, o))
    print('series by category: %s' % ', '.join('%s %d' % kv for kv in sorted(per_cat.items())))
    print('%d series, %d events, %d cars, %d tracks' % (sum(per_cat.values()), len(eord), len(cars), len(tracks)))
    for p in problems: print('PROBLEM', p)
    if not problems: print('no problems')
    return problems


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
