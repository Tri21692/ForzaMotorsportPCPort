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
ENTRY = ('ToyotaTrueno', 'ToyotaTruenoDSpec')
MODELS = (9901, 9902, 9903)  # the rival's AI car models: Easy, Medium, Hard
RIVAL_STAGE = int(os.environ.get('TOUGE_RIVAL_STAGE', '3'))  # the rival Trueno's upgrade stage (1-3)
DESC = ('Open to the Toyota Trueno and its D-Spec. Two one-on-one runs on Fujimi Kaido at night against a Trueno tuned '
        'to Class A: up the mountain, then down it. First place receives the %s.')


def main(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    key = next((k for k in mega.files if k.lower().startswith('events' + B + 'pointtopoint' + B)
                and ('displayname="%s"' % SERIES) in re.search(r'<series [^>]*>', bytes(mega.files[k]).decode('latin-1')).group(0)), None)
    if not key: raise SystemExit('no %s series in %s' % (SERIES, mods))
    car = driftcars.ordinals(disc, mods).get(PRIZE)
    if car is None: raise SystemExit('no %s in %s' % (PRIZE, mods))
    x = bytes(mega.files[key]).decode('latin-1')
    was = x
    # (17 Nov, the day's last, the user: "Make the requirement the Trueno. For the opponent, do the same but have
    # theirs upgraded to A class". Before it, the same day: Class D only, then Class B and below, then any car of
    # that class with a rival in the player's own car and setup.) Entry: the Trueno or its D-Spec, an <or> each,
    # whatever its upgrades.
    carlist = mega.files['cars' + B + 'carlist.xml'].decode('latin-1')
    cars = [addcar.ordinal_of(carlist, n) for n in ENTRY if re.search(r'<car name="%s"' % n, carlist)]
    body = ''.join('\t\t<or>\r\n\t\t\t<Restriction Attrib="carid" Func="=" Value="%d" />\r\n\t\t</or>\r\n' % c for c in cars)
    x = re.sub(r'(<Restrictions>\r?\n).*?(\t</Restrictions>)', lambda q: q.group(1) + body + q.group(2), x, count=1, flags=re.S)
    top = re.search(r'\t<Scoring>.*?</Scoring>', x, re.S)  # (the series' own: before its events)
    old = re.search(r'<score pos="1">.*?</score>', top.group(0)).group(0)
    sc = top.group(0).replace(old, '<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>' % (car, car), 1)
    x = x[:top.start()] + sc + x[top.end():]
    print('%s: open to cars %s; 1st: %s (%d)%s' % (key, cars, PRIZE_NAME, car, '' if x != was else ' (as it was)'))
    # the rival: the Trueno tuned to Class A, an AI car model of its own a difficulty (MODELS; the drivers differ):
    # the game's Trueno with every part at stage 3 (ai\aicarmodellist.xml's 3129) on its own engine
    # (EngineInstalledId 0: 3129 names a fourth engine and the Trueno has three, its own and two swaps of up to
    # 550 hp), each with a copy of that model's Drivatar controller. By the game's class figure
    # (docs/research/cars.md) that is Class A for 190 to 345 hp, and the engine's power graph ends at 280:
    # 1803 lb, 195 mm tyres and the stage's 0.05 give 0.281 before the power. Worked out, not read from the game.
    lk = {k.lower(): k for k in mega.files}
    lname = lk['ai' + B + 'aicarmodellist.xml']
    al = bytes(mega.files[lname]).decode('latin-1')
    al0 = al
    like = RIVAL_STAGE * 1000 + 100 + cars[0]
    src = re.search(r'[ \t]*<AICarModel Id="%d">.*?</AICarModel>\r?\n' % like, al, re.S).group(0)
    src = re.sub(r'EngineInstalledId="\d+"', 'EngineInstalledId="0"', src)
    pred = lk['ai' + B + 'drivatarv2' + B + 'controllers' + B + '%d-pred.bin' % like]
    for mid in MODELS:
        mine = src.replace('Id="%d"' % like, 'Id="%d"' % mid, 1)
        old = re.search(r'[ \t]*<AICarModel Id="%d">.*?</AICarModel>\r?\n' % mid, al, re.S)
        al = al.replace(old.group(0), mine) if old else al.replace('</AICarModelList>', mine + '</AICarModelList>')
        mega.files[lk.get(pred.lower().replace('%d-pred' % like, '%d-pred' % mid), pred.replace('%d-pred' % like, '%d-pred' % mid))] = bytes(mega.files[pred])
    if al != al0: mega.files[lname] = al.encode('latin-1')
    field = re.search(r'\t<AIField>\r?\n.*?\t</AIField>', x, re.S)
    rivals = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n' % r
                     for r in zip(MODELS, (22, 36, 50), ('Easy', 'Medium', 'Hard')))
    x = x[:field.start()] + '\t<AIField>\r\n' + rivals + '\t</AIField>' + x[field.end():]
    print('the rival: AI car models %s (as %d, its own engine)%s' % (MODELS, like, '' if (x, al) != (was, al0) else ' (as it was)'))
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
            t2 = DESC % PRIZE_NAME if i == sid else t
            if t2 != t: changes[i] = t2
        if changes:
            open(mp, 'wb').write(addcar.replace_strings(d, changes))
            print('%s: %s' % (lang, '; '.join('%d %r' % kv for kv in sorted(changes.items()))))
    # the matched rival (the user's, 17 Nov: "give the opponent the same performance stats that I have, along with
    # the pace matching"; runtime/hle_rival.c): the Touge's events, each D-Spec car's twin (the car it was made
    # from: the rival drives that with the player's parts and tuning), and the pace matching (8%, in full 60 m apart)
    # (no "models" line since the Trueno rule: the rival is no longer given the player's car and setup; the twins
    # still tell the runtime which cars are D-Specs, for the slide's speed hold and the achievement)
    evs = re.findall(r'eventordinal="(\d+)"', x)
    lines = ['events ' + ' '.join(evs)]
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
