"""Four more Amateur (Club) series, through addseries.py (run again, each is replaced):

  - Sunday Stroll (any level): tuner and compact cars, the Hatch, Integra and Eclipse families
    and the other small coupes and saloons by car;
  - Beetle Face Off (level 5): Volkswagen Beetles only (carid 48), upgrades allowed; stock and
    upgraded Beetles against you;
  - Japanese Showdown (level 10): Japanese cars (location, the make's country);
  - Underdog Challenge (level 30): Class A or below (perfclass D, C, B or A), against the
    Class S Championship's field.

Each logo is made from the game's own art: a tile of the large events logo strip
(frontend\\en\\ico_events_lg.xpr, MegaXPR.ca2) with a dark band and its name set in the game's
font (ArialUni.Ttf, on the disc) by ffmpeg. The tile is the highest one no series uses
(addseries.py), so the series list draws it.

Restrictions are alternatives (each <or>) of conditions that all hold, as the disc's
(pro series 8: Viper and not R, or Corvette and not R). An AI car model id is 100 + the car's
ordinal stock, 1000 more a stage of upgrades (ai\\aicarmodellist.xml). Run after
careertimetrial.py: addseries.py numbers the series after the highest seriesordinal there is,
and the Time Trial's are fixed at 85-92. Event ordinals 371-384, after the Time Trial's.

  python tools/amateurseries.py <disc> <mods folder>
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries

EVENT_ORDINAL = 371
SERIES_ID = 229          # after the Forced Induction Cup's 228

# AI fields: eight cars, raced by the drivers given for Easy, Medium and Hard
TUNER_CARS = [107, 110, 114, 109, 124, 102, 208, 207]    # Civic Type R, RSX Type S, Celica GTS, Integra Type R, Eclipse GSX, Focus SVT, Mini Cooper S, Mazda 3
BEETLE_CARS = [148, 1148, 2148, 3148, 148, 1148, 2148, 3148]  # the Beetle at each upgrade stage
JAPAN_CARS = [192, 113, 106, 253, 116, 105, 127, 191]    # Skyline R34, Supra, RX-7, NSX-R, Evo VIII, WRX STi, 350Z, S2000
CLASS_S_CARS = [136, 173, 143, 199, 239, 137, 285, 202]  # the Class S Championship's: Enzo, Carrera GT, Zonda, Cerbera, ME412, F50, Tuscan R, S7

# who may enter: a list of alternatives, each a list of (attribute, func, value) that all hold
TUNER = ([[('family', '=', f)] for f in ('Hatch', 'Integra', 'Eclipse')] +
         # RSX, Celica GTS, Civic SI, Tiburon, Protege, Del Sol, Jetta, Talon, the 1.8 Celica, APR's Celica
         [[('carid', '=', o)] for o in (10, 14, 44, 47, 49, 52, 61, 127, 164, 226)])
BEETLE = [[('carid', '=', 48)]]
JAPAN = [[('location', '=', 'Japan')]]
CLASS_A_OR_BELOW = [[('perfclass', '=', c)] for c in 'DCBA']

# (name, level, description, logo (its art: an official tile with rows painted out, emblems and
#  flames, or the flag; its captions [(text, y, size, style)]), the car won (ordinal), who may enter, the AI field, the
#  drivers (Easy, Medium, Hard), duplicates, 1st place's xp, events (track ordinal, laps))
SERIES = [
    ('Sunday Stroll', 0, 'Open to tuner and compact cars: hatchbacks, small coupes and sedans.',
     (dict(tile=27, clear=[(5, 40)]), [('SUNDAY STROLL', 7, 28, 'category')]), 174, TUNER, TUNER_CARS, (22, 36, 50), False, 3000,
     [(26, 3), (47, 3), (46, 2)]),                      # Tsukuba, Silverstone Club, Road Atlanta Club
    ('Beetle Face Off', 5, 'Open to Volkswagen New Beetle models, upgrades allowed.',
     (dict(tile=34, clear=[(8, 34), (86, 107)], emblems=[(5, 32, 58, 30), (5, 178, 58, 30)]), [('BEETLE', 9, 24, 'faceoff'), ('BEETLE', 86, 24, 'faceoff')]), 203, BEETLE, BEETLE_CARS, (25, 36, 50), True, 5000,
     [(1, 2), (26, 3), (27, 2)]),                       # Laguna Seca, Tsukuba, Alpine Ring
    ('Japanese Showdown', 10, 'Open to cars originating from Japan.',
     (dict(flag=True), [('JAPANESE', 6, 22, 'faceoff'), ('SHOWDOWN', 88, 22, 'faceoff')]), 194, JAPAN, JAPAN_CARS, (21, 35, 49), False, 7000,
     [(3, 2), (26, 3), (4, 3), (6, 2)]),                # Fujimi Kaido, Tsukuba, Fujimi Kaido Short, Sunset Peninsula
    ('Underdog Challenge', 30, 'Open to Class A cars and below, against a field of Class S cars.',
     (dict(tile=10, clear=[(80, 112)], flames=0.5), [('UNDERDOG', 84, 22, 'chrome')]), 40, CLASS_A_OR_BELOW, CLASS_S_CARS, (24, 35, 49), False, 18000,
     [(27, 2), (18, 2), (57, 2), (1, 3)]),              # Alpine Ring, New York, Maple Valley Reverse, Laguna Seca
]
PLACES = ((10, 1.0), (8, 0.7), (6, 0.5), (5, 0.4), (4, 0.3), (3, 0.2), (2, 0.1), (1, 0.0))   # points, share of 1st's xp


def xpr_tile(disc, mods, archive, name, x, y, w, h):
    """A w x h tile at (x, y) of a linear A8R8G8B8 strip in the archive, as RGBA."""
    d = addcar.Archive(disc, mods, archive).files[chr(92).join(('frontend', name))]
    hdr, sw, sh, pitch = addseries.linear(d)
    return np.frombuffer(d, np.uint8, count=h * pitch, offset=hdr + y * pitch).reshape(h, pitch // 4, 4)[:, x:x + w][:, :, [2, 1, 0, 3]].copy()


def tile(disc, mods, index):
    """A tile of the large events logo strip (frontend, en, ico_events_lg.xpr), as floats."""
    tw, th, per = addseries.LG
    return xpr_tile(disc, mods, 'MegaXPR.ca2', chr(92).join(('en', 'ico_events_lg.xpr')), index % per * tw, index // per * th, tw, th).astype(float)


def clear(a, r0, r1):
    """Rows r0 to r1 painted out: each column blended from the background just above to just below
    (medians of four rows, so the outline art's thin lines drop out)."""
    above = np.median(a[max(r0 - 4, 0):r0], 0) if r0 > 0 else None
    below = np.median(a[r1 + 1:r1 + 5], 0) if r1 + 1 < a.shape[0] else None
    above = below if above is None else above
    below = above if below is None else below
    t = np.linspace(0, 1, r1 - r0 + 1)[:, None, None]
    a[r0:r1 + 1] = above * (1 - t) + below * t


def flag():
    """The Japanese flag, shaded like cloth in light: a soft diagonal sheen, the disc lit from the top left."""
    th, tw = addseries.LG[1], addseries.LG[0]
    yy, xx = np.mgrid[0:th, 0:tw].astype(float)
    sheen = 0.9 + 0.1 * np.cos((xx + yy * 1.6) / 45)
    a = np.zeros((th, tw, 4))
    a[..., :3] = 250 * sheen[..., None]
    r = np.hypot(xx - tw / 2, yy - th / 2)
    disc = np.clip(th * 0.3 - r + 0.5, 0, 1)[..., None]
    lit = np.clip(1.12 - np.hypot(xx - tw / 2 + 12, yy - th / 2 + 12) / (th * 0.6), 0.88, 1.12)[..., None]
    a[..., :3] = a[..., :3] * (1 - disc) + np.array((215, 10, 45)) * lit * disc
    a[..., 3] = 255
    return a


def emblem(disc, mods, a, slot, cx, cy, height):
    """A make's emblem (ico_carlogo.xpr, 108 x 60 a slot) drawn on a, centred at (cx, cy), height rows high."""
    em = xpr_tile(disc, mods, 'MegaXPR.ca2', 'ico_carlogo.xpr', 0, slot * 60, 108, 60).astype(float)
    # the slot's box (its border's colour) keyed out, so only the emblem is drawn
    edge = np.concatenate([em[0], em[-1], em[:, 0], em[:, -1]])
    box = np.median(edge[:, :3], 0)
    em[..., 3] = np.minimum(em[..., 3], np.clip(np.abs(em[..., :3] - box).sum(-1) * 4, 0, 255))
    ys, xs = np.nonzero(em[..., 3] > 16)
    em = em[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h = height
    w = max(1, round(em.shape[1] * h / em.shape[0]))
    em = em[(np.arange(h) * em.shape[0] // h)][:, (np.arange(w) * em.shape[1] // w)]
    y0, x0 = cy - h // 2, cx - w // 2
    al = em[..., 3:4] / 255
    a[y0:y0 + h, x0:x0 + w, :3] = em[..., :3] * al + a[y0:y0 + h, x0:x0 + w, :3] * (1 - al)


def flames(a, reach=0.4, seed=3):
    """Flames rising from the bottom, up to reach of the height: a yellow base, red tips."""
    h, w = a.shape[:2]
    x = np.arange(w)
    tongues = 0.5 + 0.25 * np.sin(x * 0.07 + seed) + 0.15 * np.sin(x * 0.19 + 2 * seed) + 0.1 * np.sin(x * 0.41 + 5 * seed)
    top = (reach * (0.35 + 0.65 * (tongues - tongues.min()) / np.ptp(tongues)))[None, :]
    t = ((h - 1 - np.arange(h)) / (h - 1))[:, None]
    heat = np.clip(1 - t / top, 0, 1)
    alpha = np.clip((top - t) * 10, 0, 1) * 0.92
    col = np.stack([250 - 50 * (1 - heat), 40 + 190 * heat ** 1.6, 30 * heat ** 3], -1)
    a[..., :3] = a[..., :3] * (1 - alpha[..., None]) + col * alpha[..., None]


def art(disc, mods, source):
    """The logo's picture, 210 x 117 RGBA floats: an official tile with rows painted out (clear) and makes'
    emblems (slot, x, y, height), or the flag; flames if it says so."""
    a = flag() if source.get('flag') else tile(disc, mods, source['tile'])
    for r0, r1 in source.get('clear', ()):
        clear(a, r0, r1)
    if source.get('flames'):
        flames(a, source['flames'])
    for slot, cx, cy, h in source.get('emblems', ()):
        emblem(disc, mods, a, slot, cx, cy, h)
    return a


# the lettering of the official logos: white or chrome, a thin black outline and a soft shadow, in the
# face of their kind (category names condensed heavy italic like HATCHBACK and FORCED INDUCTION;
# face-offs wide caps like ECLIPSE VS INTEGRA; the class tiles' chrome C-L-A-S-S). Windows' fonts.
STYLES = {
    'category': dict(font='impact.ttf', fill='white', slant=-0.2, stretch=1.0),
    'faceoff': dict(font='ariblk.ttf', fill='white', slant=0.0, stretch=1.3),
    'chrome': dict(font='ariblk.ttf', fill='chrome', slant=0.0, stretch=1.2),
}


def glyphs(tmp, font, text, y, size, border, stretch):
    """The caption's glyphs as a mask (0 to 1) of the logo's size, grown by border pixels and widened by
    stretch about the middle."""
    tw, th = addseries.LG[0], addseries.LG[1]
    vf = ("drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=white:borderw=%d:bordercolor=white:"
          "x=(w-text_w)/2:y=%d" % (font, text.replace("'", ""), size, border, y))
    raw = subprocess.run([os.environ.get('XBRT_FFMPEG') or 'ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'gray', '-s', '%dx%d' % (tw, th), '-i', '-',
                          '-vf', vf, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         input=bytes(tw * th), capture_output=True, check=True, cwd=tmp).stdout
    m = np.frombuffer(raw, np.uint8).reshape(th, tw) / 255.0
    if stretch != 1.0:
        xs = (np.arange(tw) - tw / 2) / stretch + tw / 2
        x0 = np.clip(np.floor(xs).astype(int), 0, tw - 2)
        f = np.clip(xs - x0, 0, 1)
        m = m[:, x0] * (1 - f) + m[:, x0 + 1] * f
    return m


def shear(m, k, centre):
    """Each row shifted by k times its distance below the centre row: italics lean right for k < 0."""
    out = np.zeros_like(m)
    for r in range(m.shape[0]):
        d = int(round((r - centre) * k))
        if d > 0: out[r, d:] = m[r, :-d]
        elif d < 0: out[r, :d] = m[r, -d:]
        else: out[r] = m[r]
    return out


def blur(m):
    p = np.pad(m, 1, mode='edge')
    return sum(p[dy:dy + m.shape[0], dx:dx + m.shape[1]] for dy in range(3) for dx in range(3)) / 9


def logo(disc, mods, source, texts, tmp):
    """The logo (art) with its captions [(text, y, size, style)] lettered as the official logos are, as a PNG in tmp."""
    a = art(disc, mods, source)
    seed = zlib.crc32(repr((source, texts)).encode())
    # a little grain (a few levels): flat art compresses to less than the archive's streams need
    a[..., :3] = np.clip(a[..., :3] + np.random.default_rng(seed).integers(-3, 4, size=a.shape[:2] + (3,)), 0, 255)
    for f in {STYLES[st]['font'] for *_, st in texts}:  # Windows' fonts, copied where ffmpeg reads them by name
        shutil.copyfile(os.path.join(os.environ.get('WINDIR', 'C:' + chr(92) + 'Windows'), 'Fonts', f), os.path.join(tmp, f))
    for text, y, size, style in texts:
        st = STYLES[style]
        inner = glyphs(tmp, st['font'], text, y, size, 0, st['stretch'])
        rows = np.nonzero(inner.max(1) > 0.5)[0]
        centre = (rows.min() + rows.max()) / 2  # the caption leans about its own middle
        inner = shear(inner, st['slant'], centre)
        outer = np.maximum(shear(glyphs(tmp, st['font'], text, y, size, 2, st['stretch']), st['slant'], centre), inner)
        shadow = blur(np.roll(np.roll(outer, 2, 0), 2, 1)) * 0.6
        rows = np.nonzero(inner.max(1) > 0.5)[0]
        t = np.clip((np.arange(a.shape[0]) - rows.min()) / max(np.ptp(rows), 1), 0, 1)[:, None, None]
        if st['fill'] == 'chrome':  # light to grey at the horizon, a bright line, then grey again
            fill = np.where(t < 0.55, 255 - 90 * t / 0.55, np.where(t < 0.62, 240, 215 - 40 * (t - 0.62) / 0.38))
            fill = np.broadcast_to(fill, t.shape[:1] + (1, 3)) * np.array((1.0, 1.0, 1.04))
        else:  # white, a touch of grey at the foot
            fill = np.broadcast_to(255 - 45 * t ** 2, t.shape[:1] + (1, 3))
        for m, col in ((shadow, 0), (outer, 0), (inner, fill)):
            a[..., :3] = a[..., :3] * (1 - m[..., None]) + col * m[..., None]
    a[..., 3] = 255
    out = os.path.join(os.path.abspath(tmp), 'logo%08x.png' % seed)
    tw, th = addseries.LG[0], addseries.LG[1]
    subprocess.run([os.environ.get('XBRT_FFMPEG') or 'ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba',
                    '-s', '%dx%d' % (tw, th), '-i', '-', out], input=np.clip(a, 0, 255).astype(np.uint8).tobytes(), check=True)
    return out


def restrictions(alternatives):
    if len(alternatives) == 1:
        return ''.join('\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in alternatives[0])
    return ''.join('\t\t<or>\r\n' + ''.join('\t\t<Restriction Attrib="%s" Func="%s" Value="%s" />\r\n' % r for r in alt) + '\t\t</or>\r\n'
                   for alt in alternatives)


def series_xml(k, ordinal, name, level, prize, allowed, field, drivers, duplicates, xp, events):
    ai = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n'
                 % (car, driver, skill) for driver, skill in zip(drivers, ('Easy', 'Medium', 'Hard')) for car in field)
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="{ICON}"%s>\r\n'
         '\t<Scoring>\r\n\t\t<score pos="1"><rewards CareerCarUnlock="%d" CareerCarGift="%d" /></score>\r\n' %
         (name, SERIES_ID + k, ' Level="%d"' % level if level else '', prize, prize) +
         ''.join('\t\t<score pos="%d"></score>\r\n' % p for p in range(2, 9)) +
         '\t</Scoring>\r\n\t<Restrictions>\r\n' + restrictions(allowed) + '\t</Restrictions>\r\n'
         '\t<AIField>\r\n' + ai + '\t</AIField>\r\n')
    for track, laps in events:
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="1450">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="%d" />\r\n'
              '\t\t<AIField NumAICars="7" random="false" byclass="false" duplicates="%s" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="0.01" fuel="0.01" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
              '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n' % (ordinal, name, ordinal, track, laps, 'true' if duplicates else 'false') +
              ''.join('\t\t\t<score pos="%d" pts="%d" xp="%d"></score>\r\n' % (p + 1, pts, int(round(xp * share / 500)) * 500)
                      for p, (pts, share) in enumerate(PLACES)) +
              '\t\t</Scoring>\r\n\t</event>\r\n')
        ordinal += 1
    return x + '</series>\r\n', ordinal


def install(disc, mods):
    ordinal = EVENT_ORDINAL
    with tempfile.TemporaryDirectory() as tmp:
        for k, (name, level, desc, spec, prize, allowed, field, drivers, dup, xp, events) in enumerate(SERIES):
            x, ordinal = series_xml(k, ordinal, name, level, prize, allowed, field, drivers, dup, xp, events)
            p = os.path.join(tmp, 'series%d.xml' % k)
            open(p, 'w', encoding='latin-1', newline='').write(x)
            png = logo(disc, mods, *spec, tmp)
            # worded as the disc's: "Open to ... First place receives the <make> <model>."
            addseries.main(disc, mods, 'club', p, name, '%s First place receives the %s.' % (desc, addcar.car_name(disc, mods, prize)), event_name=name,
                           logo='%s,%s' % (png, png))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2])
