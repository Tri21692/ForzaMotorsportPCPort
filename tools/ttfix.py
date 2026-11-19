"""The career Time Trials' targets again, in place, from a rolling start (the 4 Nov audit: careertimetrial.py's
estimate was a flying lap, but each event begins rolling at its <rollingstart> speed some waypoints, 2 m apart,
before the line: on the fast short laps the targets were seconds too fast, the oval's Class B 1st 223 km/h on
average). The installed series kept as they are (their ordinals: the career keeps results by them); timetrial.txt
and each event's "Targets: ..." text (EventStrings, every language) rewritten. Idempotent.

  python tools/ttfix.py <disc> <mods folder> [--dry]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import careertimetrial as CT
import laptime

TOP_SHARE = CT.TOP_SHARE

B = '\\'


def main(disc, mods, dry=False):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    tl = bytes(next(v for k, v in mega.files.items() if k.lower().endswith('tracklist.xml'))).decode('utf-8', 'replace')
    names = {int(a['Ordinal']): a['name'] for a in (dict(re.findall(r'(\w+)="([^"]*)"', t)) for t in re.findall(r'<track\b(.*?)/>', tl, re.S)) if 'Ordinal' in a}
    tp = os.path.join(mods, 'timetrial.txt')
    lines = open(tp).read().splitlines()
    old = {int(l.split()[0]): l for l in lines if l.split() and l.split()[0].isdigit()}
    new, descs = {}, {}
    for k, (cls, _, _, _, ts, _, _) in enumerate(CT.LADDER):
        margin = CT.MARGIN[0] + (CT.MARGIN[1] - CT.MARGIN[0]) * k / (len(CT.LADDER) - 1)
        key = 'Class %s Time Trials' % cls
        f = next(n for n, v in mega.files.items() if n.lower().startswith('events' + B + 'timetrial' + B) and ('displayname="%s"' % key).encode() in v[:300])
        x = mega.files[f].decode('latin-1')
        for e in re.findall(r'<event\b.*?</event>', x, re.S):
            o = int(re.search(r'eventordinal="(\d+)"', e).group(1))
            t = int(re.search(r'<track Ordinal="(\d+)"', e).group(1))
            rs = re.search(r'<rollingstart startwaypoint="(-?\d+)" speed="([\d.]+)"', e)
            roll = (float(rs.group(2)), 2.0 * abs(int(rs.group(1)))) if rs else None
            est, length = laptime.lap(mega, names[t], CT.SIM_CLASS.get(cls, cls), rolling=roll)
            # (PACE makes up for the estimate's careful cornering, not for straights: on the oval, flat out, it put
            # Class B's 1st at 222 km/h on average against a 225 km/h top speed: 1st at most 93% of it)
            first = max(est * CT.PACE * margin, length / (laptime.CLASSES[CT.SIM_CLASS.get(cls, cls)][2] / 3.6 * TOP_SHARE))
            ms = [int(round(first * s * 10)) * 100 for s in CT.SPREAD]
            new[o] = '%d %d %d %d' % (o, *ms)
            descs[int(re.search(r'eventdescid="(\d+)"', e).group(1))] = ms
            was = [int(v) for v in old[o].split()[1:4]] if o in old else None
            print('%d %-7s %-24s %5.0f m  1st %s -> %s  (%3.0f -> %3.0f km/h)' % (o, cls, names[t], length, CT.clock(was[0]) if was else '-', CT.clock(ms[0]),
                  length / (was[0] / 1000) * 3.6 if was else 0, length / (ms[0] / 1000) * 3.6))
    if dry: return
    out = [new.get(int(l.split()[0]), l) if l.split() and l.split()[0].isdigit() else l for l in lines]
    open(tp, 'w').write('\n'.join(out) + '\n')
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()  # (read before the file is opened to write: that empties it)
        e1, text, _, _ = addcar.read_strings(d)
        have = {i: o for i, o in e1[:-1]}
        changes = {}
        for i, ms in descs.items():
            if i not in have: continue
            k0 = have[i] * 2
            k1 = k0
            while k1 + 1 < len(text) and text[k1:k1 + 2] != b'\0\0': k1 += 2
            s = text[k0:k1].decode('utf-16-le')
            s2 = re.sub(r'Targets: 1st \d+:\d+\.\d+, 2nd \d+:\d+\.\d+, 3rd \d+:\d+\.\d+', 'Targets: 1st %s, 2nd %s, 3rd %s' % tuple(CT.clock(m) for m in ms), s)
            if s2 != s: changes[i] = s2
        if changes: open(mp, 'wb').write(addcar.replace_strings(d, changes))
        print(lang, '%d target texts' % len(changes))


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--dry']
    if len(a) != 2: raise SystemExit(__doc__)
    main(*a, dry='--dry' in sys.argv)
