"""A Professional series of four catch-up events: one lap each, on four circuits, against a single
Class D car picked at random, which starts part of a lap ahead (the runtime moves its grid place: hle_career.c, from the
mods folder's catchup.txt). Open from level 20 to Class A cars.

The opponent: each event's AIField takes one car (NumAICars 1) at random (random="true", as the
disc's R-P1 Championship picks its field) from the series' list. The head start: catchup.txt,
"<event ordinal> <fraction of a lap>", written here (replacing the events' lines).

The logo (logo_art): the Class A tile and the Class D tile either side of a slash, their C-L-A-S-S painted out and their letters leaning forward, the A chasing the D with
fading copies of itself and speed streaks behind it, and Catch Up under them in a racing script, white shading into the other half's colour (a placeholder).

The Professional list (events\\spec; the Pro Series folder is the career's Championship Series,
where it was first) goes up by level: it shows after the level-15 series, its seriesorder its place
as the disc's there (addseries.py).

  python tools/catchupseries.py <disc> <mods folder> [head start, a fraction of a lap]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import amateurseries as A

NAME = 'Catch-Up Challenge'
KIND = 'spec'            # the career's Professional list (proseries is its Championship Series)
EVENT_ORDINAL = 385      # after the Amateur series' 371-384: 385-388
SERIES_ID = 233          # after the Amateur series' 229-232
LEVEL = 20               # (the user's: level 20, Class A against Class D)
CLASS_A = [[('perfclass', '=', 'A')]]  # as the disc's Class B Championship has its class
TRACKS = (1, 9, 3, 2)    # Laguna Seca, Road Atlanta, Maple Valley, Silverstone
LAPS = 1
XP = 4000                # a win, each event
PRIZE_CLASS = (13, 14, 15, 16)  # the prize: a Class A car (gamecars.dat's subclass at 100: A4-A1, performancesubclass.dat),
                         # picked at random from those no level gives and no series has as its prize
CHASER = 10              # the logo's left half: the Class A tile (the player's class), the Class D tile (7) on the right
HEAD_START = 0.2         # of a lap (half, a third and a quarter were too much to catch up in one lap, the user found)
# the field to pick from: Class D cars at their best (D1, D2), as AI car models (100 + ordinal):
# Civic Type R, Integra Type R, Celica GTS, Audi TT 3.2, VW R32, RX-7, Silvia S14, Delta Integrale
D_CARS = [107, 109, 114, 118, 120, 233, 315, 213]
DRIVERS = (24, 35, 49)
CAPTION = [('Catch Up', 77, 26, 'catchup')]  # a placeholder: a racing script in the halves' colours
A.STYLES['catchup'] = dict(font='MAGNETOB.TTF', fill='split', slant=-0.15, stretch=1.0, cut=(121, 89),  # logo_art's slash
                           left=(195, 150, 255), right=(255, 225, 80))  # each half's lettering in the other's colour: lavender on the A's yellow, yellow on the D's purple
DESC = 'Open to Class A cars. Four one-lap races: a Class D car starts a fifth of a lap ahead, catch it.'


def lifted(t, x0=64, x1=147, y1=78):
    """A class tile's big letter lifted off: (the tile with the letter's place filled in from either
    side, row by row; the letter with its outline and shadow, and how much of each pixel is it)."""
    import numpy as np
    bg = t.copy()
    left, right = np.median(t[:y1, x0 - 4:x0], 1), np.median(t[:y1, x1:x1 + 4], 1)
    s = np.linspace(0, 1, x1 - x0)[None, :, None]
    bg[:y1, x0:x1] = left[:, None] * (1 - s) + right[:, None] * s
    diff = np.abs(t[..., :3] - bg[..., :3]).max(2)
    mask = np.clip((diff - 18) / 40, 0, 1)
    mask[y1:] = 0
    return bg, t, mask


def lean(img, k, y0):
    """img leaned forward (to the right above y0) by k pixels a row."""
    import numpy as np
    out = np.empty_like(img)
    for y in range(img.shape[0]):
        out[y] = np.roll(img[y], int(round(k * (y0 - y))), 0)
    return out


def logo_art(disc, mods):
    """The logo's picture: the Class A tile left of a slash, the Class D tile right of it, their
    C-L-A-S-S rows painted out and their letters leaning forward, the A chasing the D with fading
    copies of itself and speed streaks behind it, and a white line along the slash."""
    import numpy as np
    th, tw = A.addseries.LG[1], A.addseries.LG[0]
    yy, xx = np.mgrid[0:th, 0:tw].astype(float)
    sides = []
    for t, dx, k, ghosts in ((A.tile(disc, mods, CHASER), -46, 0.25, ((-26, 0.35), (-13, 0.6))), (A.tile(disc, mods, 7), 46, 0.25, ())):
        bg, letter, mask = lifted(t)
        A.clear(bg, 76, 113)  # the C-L-A-S-S row, from the ground without the letter
        letter, mask = lean(letter, k, 40), lean(mask, k, 40)
        out = bg.copy()
        if ghosts:  # speed streaks behind the A: light lines from its back, fading out to the left
            back = {y: np.nonzero(np.roll(mask, dx, 1)[y] > 0.5)[0] for y in range(th)}
            for y in range(3, 76, 4):
                if not len(back[y]): continue
                x0 = back[y].min()
                ln = np.clip(xx[y] / x0, 0, 1) ** 1.5 * (xx[y] < x0) * 0.75
                out[y, :, :3] = out[y, :, :3] * (1 - ln[:, None]) + 240 * ln[:, None]
        for gx, alpha in ghosts + ((0, 1.0),):  # the copies furthest back first, the letter last
            sh = dx + gx
            m = np.roll(mask, sh, 1) * alpha
            l = np.roll(letter, sh, 1)
            if sh > 0: m[:, :sh] = 0
            else: m[:, sh:] = 0
            if gx: l = l * 0.6 + 255 * 0.4  # a ghost: the letter, paler
            out = out * (1 - m[..., None]) + l * m[..., None]
        sides.append(out)
    cut = 89 + 32 * (1 - yy / th)  # the slash: (121, 0) at the top to (89, 117) at the foot, through the middle, leaning as the letters do
    w = np.clip(xx - cut + 0.5, 0, 1)[..., None]  # 0: the B's side, 1: the D's
    a = sides[0] * (1 - w) + sides[1] * w
    # a white line along it, with a glow
    d = xx - cut
    white = np.clip(2.0 - np.abs(d), 0, 1)[..., None]
    glow = np.exp(-np.abs(d) / 4.0)[..., None] * 0.4
    a[..., :3] = a[..., :3] + (255 - a[..., :3]) * glow
    a[..., :3] = a[..., :3] * (1 - white) + 250 * white
    a[..., 3] = 255
    return a


def series_xml(prize):
    ai = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n'
                 % (car, driver, skill) for driver, skill in zip(DRIVERS, ('Easy', 'Medium', 'Hard')) for car in D_CARS)
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="{ICON}" Level="%d">\r\n'
         '\t<Scoring>\r\n\t\t<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>\r\n'
         '\t\t<score pos="2"></score>\r\n\t</Scoring>\r\n\t<Restrictions>\r\n' % (NAME, SERIES_ID, LEVEL, prize, prize) +
         A.restrictions(CLASS_A) + '\t</Restrictions>\r\n\t<AIField>\r\n' + ai + '\t</AIField>\r\n')
    for k, track in enumerate(TRACKS):
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="1450">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
              '\t\t<AIField NumAICars="1" random="true" byclass="false" duplicates="false" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="0.01" fuel="0.01" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
              '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n'
              '\t\t\t<score pos="1" pts="10" xp="%d"></score>\r\n\t\t\t<score pos="2" pts="0" xp="0"></score>\r\n'
              '\t\t</Scoring>\r\n\t</event>\r\n' % (k + 1, NAME, EVENT_ORDINAL + k, track, LAPS, XP))
    return x + '</series>\r\n'


def prize_pool(disc, mods):
    """The Class A cars no level gives (rarity\\<region>\\rarityregiondef.xml's CareerCarGift; its
    CareerCarUnlock only puts a car on sale, and every car has one) and no series has as its prize
    (events\\...\\*.xml, arcade\\*.xml), but this one's; and the prize this one has now, if any."""
    import re
    import struct
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    f = {k.lower(): v for k, v in mega.files.items()}
    g = f['forzadb\\cardb\\gamecars.dat']
    sub = {struct.unpack_from('<I', g, i)[0]: struct.unpack_from('<I', g, i + 100)[0] for i in range(0, len(g) - 175, 176)}
    priced = {int(o): int(p) for o, p in re.findall(r'<car [^>]*?Ordinal="(\d+)"[^>]*?Price="(\d+)"', f['cars\\carlist.xml'].decode('latin-1'))}
    taken, ours = set(), None
    for k, v in f.items():
        if not k.endswith('.xml') or not k.startswith(('rarity\\', 'events\\', 'arcade\\')): continue
        s = v.decode('latin-1', 'ignore')
        if k.startswith('rarity\\'): taken |= {int(o) for o in re.findall(r'CareerCarGift="(\d+)"', s)}
        elif 'displayname="%s"' % NAME in s[:400]: ours = int(re.search(r'CareerCarUnlock="(\d+)"', s).group(1))
        else: taken |= {int(o) for o in re.findall(r'CareerCar(?:Unlock|Gift)="(\d+)"', s)}
    pool = sorted(o for o, c in sub.items() if c in PRIZE_CLASS and o not in taken and priced.get(o, 0) >= 100)
    return pool, ours


def install(disc, mods, head_start=HEAD_START):
    import random
    pool, ours = prize_pool(disc, mods)
    if not pool: raise SystemExit('no Class A car is left that no level gives and no series has as its prize')
    prize = ours if ours in pool else random.choice(pool)  # (kept when run again)
    print('prize: %s (%d), of %d free Class A cars' % (addcar.car_name(disc, mods, prize), prize, len(pool)))
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'catchup.xml')
        open(p, 'w', encoding='latin-1', newline='').write(series_xml(prize))
        png = A.logo(disc, mods, dict(image=logo_art(disc, mods)), CAPTION, tmp)
        addseries.remove(disc, mods, 'proseries', NAME)  # (it was in the Championship Series list before)
        addseries.main(disc, mods, KIND, p, NAME, '%s First place receives the %s.' % (DESC, addcar.car_name(disc, mods, prize)),
                       event_name=NAME, logo='%s,%s' % (png, png))
    path = os.path.join(mods, 'catchup.txt')
    ours = ['%d' % (EVENT_ORDINAL + k) for k in range(len(TRACKS))]
    lines = [l for l in (open(path).read().splitlines() if os.path.exists(path) else []) if l.split()[:1] not in [[o] for o in ours]]
    open(path, 'w').write('\n'.join(lines + ['%s %.3f' % (o, head_start) for o in ours]) + '\n')
    print('%s: events %s-%s, head start %.3f of a lap (%s)' % (NAME, ours[0], ours[-1], head_start, path))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else HEAD_START)
