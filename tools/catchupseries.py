"""A Professional series of four catch-up events: one lap each, on four circuits, against a single
Class D car picked at random, which starts part of a lap ahead (the runtime moves its grid place: hle_career.c, from the
mods folder's catchup.txt). Open from level 35 to Class S cars.

The opponent: each event's AIField takes one car (NumAICars 1) at random (random="true", as the
disc's R-P1 Championship picks its field) from the series' list. The head start: catchup.txt,
"<event ordinal> <fraction of a lap> <the track's racing line's points>", a race each (HEAD_STARTS),
written here (replacing the events' lines); the runtime picks the line by the loaded track's points.

The logo (logo_art): the Class S tile and the Class D tile either side of a slash, their C-L-A-S-S painted out and their letters leaning forward, the S chasing the D with
fading copies of itself and speed streaks behind it, and Catch Up under them in a racing script, white shading into the other half's colour (a placeholder).

The Professional list (events\\spec; the Pro Series folder is the career's Championship Series,
where it was first) goes up by level: it shows after the level-15 series, its seriesorder its place
as the disc's there (addseries.py).

  python tools/catchupseries.py <disc> <mods folder> [one head start for every race, a fraction of a lap]
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
LEVEL = 35               # (the user's: level 35, Class S against Class D; Class A was too hard for a casual player)
CLASS_S = [[('perfclass', '=', 'S')]]  # as the disc's class championships have theirs
TRACKS = (1, 9, 3, 2)    # Laguna Seca, Road Atlanta, Maple Valley, Silverstone
LAPS = 1
XP = 4000                # a win, each event
PRIZE = 82               # the Lamborghini Gallardo: no level gives it and no other series has it as its prize
                         # (drawn at random from the nine such Class A cars; the user kept it, listed S4 since)
CHASER = 11              # the logo's left half: the Class S tile (the player's class), the Class D tile (7) on the right
HEAD_STARTS = (1 / 6, 1 / 5, 1 / 4, 1 / 3)  # of a lap, a race each, as TRACKS (the user's: Class S from level 35)
# the field to pick from: Class D cars at their best (D1, D2), as AI car models (100 + ordinal):
# Civic Type R, Integra Type R, Celica GTS, Audi TT 3.2, VW R32, RX-7, Silvia S14, Delta Integrale
D_CARS = [107, 109, 114, 118, 120, 233, 315, 213]
DRIVERS = (24, 35, 49)
CAPTION = [('Catch Up', 77, 26, 'catchup')]  # a placeholder: a racing script in the halves' colours
A.STYLES['catchup'] = dict(font='MAGNETOB.TTF', fill='split', slant=-0.15, stretch=1.0, cut=(121, 89),  # logo_art's slash
                           left=(195, 150, 255), right=(255, 165, 70))  # each half's lettering in the other's colour: lavender on the S's orange, orange on the D's purple
DESC = 'Open to Class S cars. Four one-lap races against a Class D car with a head start: catch it.'


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
    """The logo's picture: the Class S tile left of a slash, the Class D tile right of it, their
    C-L-A-S-S rows painted out and their letters leaning forward, the S chasing the D with fading
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
        if ghosts:  # speed streaks behind the S: light lines from its back, fading out to the left
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
         A.restrictions(CLASS_S) + '\t</Restrictions>\r\n\t<AIField>\r\n' + ai + '\t</AIField>\r\n')
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


def track_points(disc, mods, ordinal):
    """A track's racing line's point count (its AI geometry's iLength, ai\\drivatarv2\\<name>geometry.bin):
    what the runtime tells the race's track by at the grid (hle_career.c)."""
    import re
    import mlp
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    f = {k.lower(): v for k, v in mega.files.items()}
    tl = f['forzadb\\tracklist.xml'].decode('latin-1')
    name = next(n for n, o in re.findall(r'<track[^>]*?\sname="([^"]*)"[^>]*?\sOrdinal="(\d+)"', tl, re.S) if int(o) == ordinal)
    out, _ = mlp.read(f['ai\\drivatarv2\\' + name.lower() + 'geometry.bin'])
    return int(out['iLength'][0])


def install(disc, mods, head_starts=HEAD_STARTS):
    prize = PRIZE
    print('prize: %s (%d)' % (addcar.car_name(disc, mods, prize), prize))
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
    ours_lines = ['%s %.3f %d' % (o, h, track_points(disc, mods, t)) for o, h, t in zip(ours, head_starts, TRACKS)]
    open(path, 'w').write('\n'.join(lines + ours_lines) + '\n')
    print('%s: events %s-%s, head starts %s (%s)' % (NAME, ours[0], ours[-1], '; '.join(ours_lines), path))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2], (float(sys.argv[3]),) * len(TRACKS) if len(sys.argv) > 3 else HEAD_STARTS)
