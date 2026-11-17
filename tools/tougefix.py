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
MODELS = (9901, 9902, 9903)  # the matched rival's AI car models: Easy, Medium, Hard
MODEL_LIKE = 189             # (the stock Silvia S15's: what the rival is, should the runtime not change it)


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = next((k for k in mega.files if k.lower().startswith('events' + B + 'pointtopoint' + B)
                and ('displayname="%s"' % SERIES) in re.search(r'<series [^>]*>', bytes(mega.files[k]).decode('latin-1')).group(0)), None)
    if not key: raise SystemExit('no %s series in %s' % (SERIES, mods))
    car = driftcars.ordinals(disc, mods).get(PRIZE)
    if car is None: raise SystemExit('no %s in %s' % (PRIZE, mods))
    x = bytes(mega.files[key]).decode('latin-1')
    was = x
    # (17 Nov, later, the user: "just make the touge event B class. D is too hard now": Class B and below, said as
    # not A and not S, both to hold within a car's alternative)
    two = lambda m: m.group(1) + '<Restriction Attrib="perfclass" Func="<>" Value="A" />' + m.group(1) + '<Restriction Attrib="perfclass" Func="<>" Value="S" />'
    if 'Attrib="perfclass" Func="<>" Value="A"' not in x:
        x = re.sub(r'(\r?\n[ \t]*)<Restriction Attrib="perfclass" Func="(?:=" Value="D|<>" Value="S)" />', two, x)
    # (17 Nov, evening, the user: "No D-Spec cars are required, it's just too difficult to keep speed": any car of
    # Class B and below: no car alternatives, the class asked of every car, race cars out too)
    body = ''.join('\t\t<Restriction Attrib="perfclass" Func="<>" Value="%s" />\r\n' % c for c in ('A', 'S', 'R'))
    x = re.sub(r'(<Restrictions>\r?\n).*?(\t</Restrictions>)', lambda q: q.group(1) + body + q.group(2), x, count=1, flags=re.S)
    top = re.search(r'\t<Scoring>.*?</Scoring>', x, re.S)  # (the series' own: before its events)
    old = re.search(r'<score pos="1">.*?</score>', top.group(0)).group(0)
    sc = top.group(0).replace(old, '<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>' % (car, car), 1)
    x = x[:top.start()] + sc + x[top.end():]
    print('%s: open to Class B and below (%d car alternatives); 1st: %s (%d)%s' % (key, x.count('Attrib="carid"'), PRIZE_NAME, car, '' if x != was else ' (as it was)'))
    # the matched rival's own AI car models (17 Nov: when an AI car is made the game does not yet say which event is
    # loading, so runtime/hle_rival.c knows the Touge's rival by its model's Id): one a difficulty, copies of the
    # stock Silvia S15's (189) under Ids nothing else has, each with a copy of its Drivatar controller; the series'
    # rivals are these three, whose car and setup the runtime makes the player's
    lk = {k.lower(): k for k in mega.files}
    lname = lk['ai' + B + 'aicarmodellist.xml']
    al = bytes(mega.files[lname]).decode('latin-1')
    al0 = al
    src = re.search(r'[ \t]*<AICarModel Id="%d">.*?</AICarModel>\r?\n' % MODEL_LIKE, al, re.S).group(0)
    pred = lk['ai' + B + 'drivatarv2' + B + 'controllers' + B + '%d-pred.bin' % MODEL_LIKE]
    for mid in MODELS:
        if '<AICarModel Id="%d">' % mid not in al:
            al = al.replace('</AICarModelList>', src.replace('Id="%d"' % MODEL_LIKE, 'Id="%d"' % mid, 1) + '</AICarModelList>')
        mega.files.setdefault(pred.replace('%d-pred' % MODEL_LIKE, '%d-pred' % mid), bytes(mega.files[pred]))
    if al != al0: mega.files[lname] = al.encode('latin-1')
    field = re.search(r'\t<AIField>\r?\n.*?\t</AIField>', x, re.S)
    rivals = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n' % r
                     for r in zip(MODELS, (22, 36, 50), ('Easy', 'Medium', 'Hard')))
    x = x[:field.start()] + '\t<AIField>\r\n' + rivals + '\t</AIField>' + x[field.end():]
    print('the rival: AI car models %s (as %d), one a difficulty%s' % (MODELS, MODEL_LIKE, '' if (x, al) != (was, al0) else ' (as it was)'))
    if x != was or al != al0:
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
            t2 = t.replace('Class A and below', 'Class D').replace('Class A or below', 'Class D').replace('Class D', 'Class B and below').replace('Open to D-Spec cars of', 'Open to cars of')
            if i == sid: t2 = t2.split('First place receives the ')[0].rstrip() + ' First place receives the %s.' % PRIZE_NAME
            if t2 != t: changes[i] = t2
        if changes:
            open(mp, 'wb').write(addcar.replace_strings(d, changes))
            print('%s: %s' % (lang, '; '.join('%d %r' % kv for kv in sorted(changes.items()))))
    # the matched rival (the user's, 17 Nov: "give the opponent the same performance stats that I have, along with
    # the pace matching"; runtime/hle_rival.c): the Touge's events, each D-Spec car's twin (the car it was made
    # from: the rival drives that with the player's parts and tuning), and the pace matching (8%, in full 60 m apart)
    carlist = mega.files['cars' + B + 'carlist.xml'].decode('latin-1')
    evs = re.findall(r'eventordinal="(\d+)"', x)
    lines = ['events ' + ' '.join(evs), 'models ' + ' '.join(str(m) for m in MODELS)]
    for c in driftcars.CARS:
        if re.search(r'<car name="%s"' % c[1], carlist) and re.search(r'<car name="%s"' % c[0], carlist):
            lines.append('twin %d %d' % (addcar.ordinal_of(carlist, c[1]), addcar.ordinal_of(carlist, c[0])))
    lines.append('pace %s %s' % (os.environ.get('TOUGE_PACE', '0.08'), os.environ.get('TOUGE_PACE_M', '60')))
    open(os.path.join(mods, 'rivalmatch.txt'), 'w').write('\n'.join(lines) + '\n')
    print('rivalmatch.txt: ' + '; '.join(lines))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    main(sys.argv[1], sys.argv[2])
