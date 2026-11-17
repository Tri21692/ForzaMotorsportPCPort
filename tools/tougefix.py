"""Midnight Touge, in place (the user's, 17 Nov: "Add a prize car to Midnight Touge, plus only allow D cars for entry.
Anything above that makes it too easy"): the series as tools/fujiminight.py installed it, changed where it stands
(a re-run of that tool would number it anew):

  - entry: each D-Spec car's alternative asks for Class D (it was any class but S, said as "Class A and below"):
    as the mods folder has them the 240SX, Trueno, RX-7, Neon Coupe, Celica GT-Four and Miata D-Specs, stock or
    with upgrades that keep them in D;
  - the prize: 1st overall receives the Mazda RX-7 Spirit R D-Spec (the disc's way, as tools/prizecars.py's);
  - the texts: the series' and its events' descriptions say Class D, the series' ends with the prize.

  python tools/tougefix.py <disc> <mods folder>

Run again, it changes nothing more. Never the saves.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import driftcars
from mayhemchamp import text_of

B = chr(92)
SERIES = 'Midnight Touge'
PRIZE = 'MazdaRX7SpiritDSpec'
PRIZE_NAME = 'Mazda RX-7 Spirit R D-Spec'


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = next((k for k in mega.files if k.lower().startswith('events' + B + 'pointtopoint' + B)
                and ('displayname="%s"' % SERIES) in re.search(r'<series [^>]*>', bytes(mega.files[k]).decode('latin-1')).group(0)), None)
    if not key: raise SystemExit('no %s series in %s' % (SERIES, mods))
    car = driftcars.ordinals(disc, mods).get(PRIZE)
    if car is None: raise SystemExit('no %s in %s' % (PRIZE, mods))
    x = bytes(mega.files[key]).decode('latin-1')
    was = x
    x = x.replace('<Restriction Attrib="perfclass" Func="<>" Value="S" />', '<Restriction Attrib="perfclass" Func="=" Value="D" />')
    top = re.search(r'\t<Scoring>.*?</Scoring>', x, re.S)  # (the series' own: before its events)
    old = re.search(r'<score pos="1">.*?</score>', top.group(0)).group(0)
    sc = top.group(0).replace(old, '<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>' % (car, car), 1)
    x = x[:top.start()] + sc + x[top.end():]
    print('%s: %d alternatives ask for Class D; 1st: %s (%d)%s' % (key, x.count('Attrib="perfclass" Func="=" Value="D"'), PRIZE_NAME, car, '' if x != was else ' (as it was)'))
    if x != was:
        mega.files[key] = x.encode('latin-1')
        mega.check(); mega.write()
    head = re.search(r'<series [^>]*>', x).group(0)
    sid = int(re.search(r'seriesdescid="(\d+)"', head).group(1))
    ids = [sid] + [int(m) for m in re.findall(r'eventdescid="(\d+)"', x)]
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()
        changes = {}
        for i in sorted(set(ids)):
            t = text_of(d, i)
            if t is None: continue
            t2 = t.replace('Class A and below', 'Class D').replace('Class A or below', 'Class D')
            if i == sid: t2 = t2.split('First place receives the ')[0].rstrip() + ' First place receives the %s.' % PRIZE_NAME
            if t2 != t: changes[i] = t2
        if changes:
            open(mp, 'wb').write(addcar.replace_strings(d, changes))
            print('%s: %s' % (lang, '; '.join('%d %r' % kv for kv in sorted(changes.items()))))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    main(sys.argv[1], sys.argv[2])
