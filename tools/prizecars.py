"""Prize cars for the added series that had none (the user's, 7 Nov: "for the events without prize cars, pick random
but fitting prize cars"), in place: 1st overall in the series gets the car (the disc's way: <rewards CareerCarUnlock
CareerCarGift> on the series' own pos 1 score), and the series' description ends "First place receives the <car>."
as the disc's do. Each pick fits its series: a drift car for drifting, a muscle car for the first Mayhem Tour, the
Mercedes 190E Evo II for Rivals (the M3's old rival), a rear-engine Porsche for the Rear-Engine Rebellion, a GTE race
car for a race-car Grand Prix, the Nurburgring-tuned LF-A for the Nordschleife. Idempotent.

  python tools/prizecars.py <disc> <mods folder>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
from mayhemchamp import text_of

B = '\\'
# (series file, its displayname (checked), the car's ordinal, the car's name as the shop shows it)
PRIZES = [
    (r'events\Drift\Ser00001.xml', 'Drift Championship', 272, 'Nissan Silvia S15 Spec-R'),
    (r'events\Mayhem\Ser00001.xml', 'Mayhem Tour', 261, 'Dodge Charger SRT8'),
    (r'events\Mayhem\Ser00002.xml', 'Mayhem Tour II', 270, 'Chevrolet Corvette ZR1 (C7)'),
    (r'events\Mayhem\Ser00003.xml', 'Mayhem Tour Championship', 271, 'Lamborghini Egoista'),
    (r'events\spec\Ser00010.xml', 'Rivals', 231, 'Mercedes 190E 2.5-16 Evolution II'),
    (r'events\spec\Ser00014.xml', 'Rear-Engine Rebellion', 244, 'Porsche 911 GT2 RS'),
    (r'events\spec\Ser00018.xml', 'Shipyard Grand Prix', 254, 'BMW Motorsport M8 GTE'),
    (r'events\spec\Ser00023.xml', 'Nordschleife Endurance', 175, 'Lexus LF-A Concept'),
]


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    keys = {k.lower(): k for k in mega.files}
    descs = {}
    for path, name, car, car_name in PRIZES:
        k = keys.get(path.lower())
        if not k: raise SystemExit('no %s' % path)
        x = mega.files[k].decode('latin-1')
        head = re.search(r'<series [^>]*>', x).group(0)
        if 'displayname="%s"' % name not in head: raise SystemExit('%s is not %s' % (path, name))
        top = re.search(r'\t<Scoring>.*?</Scoring>', x, re.S)  # (the series' own: before its events)
        old = re.search(r'<score pos="1">.*?</score>', top.group(0)).group(0)
        new = '<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>' % (car, car)
        sc = top.group(0).replace(old, new, 1)
        x = x[:top.start()] + sc + x[top.end():]
        mega.files[k] = x.encode('latin-1')
        descs[int(re.search(r'seriesdescid="(\d+)"', head).group(1))] = car_name
        print('%-26s 1st: %s (%d)' % (name, car_name, car))
    mega.check(); mega.write()
    loc = os.path.join(mods, 'media', 'Loc')
    for lang in sorted(os.listdir(loc)):
        mp = os.path.join(loc, lang, 'EventStrings.str')
        if not os.path.exists(mp): continue
        d = open(mp, 'rb').read()
        changes = {}
        for sid, car_name in descs.items():
            t = text_of(d, sid)
            if t is None: raise SystemExit('%s: no string %d' % (lang, sid))
            t2 = t.split('First place receives the ')[0].rstrip() + ' First place receives the %s.' % car_name
            if t2 != t: changes[sid] = t2
        if changes: open(mp, 'wb').write(addcar.replace_strings(d, changes))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    main(*sys.argv[1:])
