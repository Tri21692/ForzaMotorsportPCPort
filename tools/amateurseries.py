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

# (name, level, description, logo (the strip's tile, a top band's height, a bottom band's, the
#  texts [(text, y, size)]), the car won (ordinal) and its name, who may enter, the AI field, the
#  drivers (Easy, Medium, Hard), duplicates, 1st place's xp, events (track ordinal, laps))
SERIES = [
    ('Sunday Stroll', 0, 'An easy drive for tuner and compact cars: hatchbacks, small coupes and saloons.',
     (('tile', 27), 42, 0, [('sunday', 2, 38, 'sunday'), ('stroll', 84, 32, 'sunday')]), 174, 'Mugen Civic Type R', TUNER, TUNER_CARS, (22, 36, 50), False, 3000,
     [(26, 3), (47, 3), (46, 2)]),                      # Tsukuba, Silverstone Club, Road Atlanta Club
    ('Beetle Face Off', 5, 'Volkswagen Beetles only. Upgrade yours as far as you like.',
     (('make', 5), 0, 0, [('BEETLE', 2, 38, 'beetle'), ('FACE OFF', 84, 32, 'beetle')]), 203, 'Mugen S2000', BEETLE, BEETLE_CARS, (25, 36, 50), True, 5000,
     [(1, 2), (26, 3), (27, 2)]),                       # Laguna Seca, Tsukuba, Alpine Ring
    ('Japanese Showdown', 10, 'Japanese cars only.',
     (('flag',), 0, 0, [('JAPANESE', 2, 34, 'japan'), ('SHOWDOWN', 84, 32, 'japan')]), 194, 'Mines Skyline GT-R R34', JAPAN, JAPAN_CARS, (21, 35, 49), False, 7000,
     [(3, 2), (26, 3), (4, 3), (6, 2)]),                # Fujimi Kaido, Tsukuba, Fujimi Kaido Short, Sunset Peninsula
    ('Underdog Challenge', 30, 'Class A cars at most, against a field of Class S supercars.',
     (('vinyl', 0, 'flames'), 0, 0, [('UNDERDOG', 4, 30, 'underdog')]), 40, 'Koenigsegg CC', CLASS_A_OR_BELOW, CLASS_S_CARS, (24, 35, 49), False, 18000,
     [(27, 2), (18, 2), (57, 2), (1, 3)]),              # Alpine Ring, New York, Maple Valley Reverse, Laguna Seca
]
PLACES = ((10, 1.0), (8, 0.7), (6, 0.5), (5, 0.4), (4, 0.3), (3, 0.2), (2, 0.1), (1, 0.0))   # points, share of 1st's xp


def xpr_tile(disc, mods, archive, name, x, y, w, h):
    """A w x h tile at (x, y) of a linear A8R8G8B8 strip in the archive, as RGBA."""
    d = addcar.Archive(disc, mods, archive).files[chr(92).join(('frontend', name))]
    hdr, sw, sh, pitch = addseries.linear(d)
    return np.frombuffer(d, np.uint8, count=h * pitch, offset=hdr + y * pitch).reshape(h, pitch // 4, 4)[:, x:x + w][:, :, [2, 1, 0, 3]].copy()


def dxt3(d, w, h):
    """A DXT3 texture (1 byte of alpha per texel pair, then a DXT1 block) as RGBA."""
    b = np.frombuffer(d, np.uint8, count=w * h).reshape(h // 4, w // 4, 16)
    alpha = np.zeros((h // 4, w // 4, 16), np.uint8)
    for i in range(8):
        alpha[..., 2 * i] = (b[..., i] & 15) * 17
        alpha[..., 2 * i + 1] = (b[..., i] >> 4) * 17
    c0 = b[..., 8].astype(np.int32) | (b[..., 9].astype(np.int32) << 8)
    c1 = b[..., 10].astype(np.int32) | (b[..., 11].astype(np.int32) << 8)
    def c565(c):
        return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], -1)
    p0, p1 = c565(c0), c565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], -2)
    bits = b[..., 12:16].astype(np.uint32)
    idx = bits[..., 0] | (bits[..., 1] << 8) | (bits[..., 2] << 16) | (bits[..., 3] << 24)
    out = np.zeros((h // 4, w // 4, 16, 4), np.uint8)
    for k in range(16):
        sel = (idx >> (2 * k)) & 3
        out[..., k, :3] = np.take_along_axis(pal, sel[..., None, None].repeat(3, -1), -2)[..., 0, :]
        out[..., k, 3] = alpha[..., k]
    return out.reshape(h // 4, w // 4, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(h, w, 4)


def flag():
    """The Japanese flag: a red disc on white."""
    a = np.full((addseries.LG[1], addseries.LG[0], 4), 255, np.uint8)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    a[(xx - a.shape[1] / 2) ** 2 + (yy - a.shape[0] / 2) ** 2 <= (a.shape[0] * 0.3) ** 2, :3] = (188, 0, 45)
    return a


def make_logo(disc, mods, slot):
    """A make's emblem (ico_carlogo.xpr, 108 x 60 a slot) on a blue glow, at 210 x 117."""
    em = xpr_tile(disc, mods, 'MegaXPR.ca2', 'ico_carlogo.xpr', 0, slot * 60, 108, 60)
    big = np.repeat(np.repeat(em, 2, 0), 2, 1)[1:118, 3:213]
    yy, xx = np.mgrid[0:117, 0:210]
    t = np.clip(np.hypot((xx - 105) / 150, (yy - 58) / 80), 0, 1)[..., None]
    bg = np.concatenate([(0, 60, 150) * (1 - t) + (0, 20, 60) * t, np.full((117, 210, 1), 255)], -1)
    al = big[..., 3:4] / 255.0
    bg[..., :3] = big[..., :3] * al + bg[..., :3] * (1 - al)
    return bg.astype(np.uint8)


def vinyl(disc, mods, n):
    """A vinyl of the disc's dlcustom.xpr (1024 x 512 DXT3 sheets), at 210 x 117."""
    d = open(addcar.disc_file(disc, 'media', 'dlcustom.xpr'), 'rb').read()
    a = dxt3(d[2048 + n * 524288:], 1024, 512)
    rows = np.arange(117) * 512 // 117
    cols = np.arange(210) * 1024 // 210
    out = a[rows][:, cols].copy()
    out[..., 3] = 255
    return out


def flames(a, seed=3):
    """Flames rising from the bottom: a yellow base, red tips, their tops set by a noise along the width."""
    h, w = a.shape[:2]
    x = np.arange(w)
    tongues = 0.5 + 0.25 * np.sin(x * 0.07 + seed) + 0.15 * np.sin(x * 0.19 + 2 * seed) + 0.1 * np.sin(x * 0.41 + 5 * seed)
    reach = (0.15 + 0.35 * (tongues - tongues.min()) / np.ptp(tongues))[None, :]
    t = ((h - 1 - np.arange(h)) / (h - 1))[:, None]
    heat = np.clip(1 - t / reach, 0, 1)
    alpha = np.clip((reach - t) * 10, 0, 1) * 0.92
    col = np.stack([np.full_like(heat, 255), 255 * heat ** 1.6, 60 * heat ** 3], -1)
    a[..., :3] = (a[..., :3] * (1 - alpha[..., None]) + col * alpha[..., None]).astype(np.uint8)
    return a


def art(disc, mods, source):
    """The logo's picture (210 x 117, RGBA): a tile of the events strip ('tile', index), the flag,
    a make's emblem ('make', slot) or a vinyl ('vinyl', index), with flames if it says so."""
    if source[0] == 'tile':
        return tile(disc, mods, source[1])
    if source[0] == 'flag':
        return flag()
    if source[0] == 'make':
        return make_logo(disc, mods, source[1])
    if source[0] == 'vinyl':
        a = vinyl(disc, mods, source[1])
        return flames(a) if len(source) > 2 and source[2] == 'flames' else a
    raise SystemExit('logo source: %s' % (source,))


def tile(disc, mods, index):
    """A tile of the large events logo strip (frontend, en, ico_events_lg.xpr)."""
    tw, th, per = addseries.LG
    return xpr_tile(disc, mods, 'MegaXPR.ca2', chr(92).join(('en', 'ico_events_lg.xpr')), index % per * tw, index // per * th, tw, th)


# each caption's look: a fill (solid, or a gradient down the logo), an outline and a slant (rows shifted
# by slant x the distance from the middle), to match the series' theme
STYLES = {
    'sunday': dict(font='comicbd.ttf', fill=('grad', (255, 250, 210), (255, 150, 30)), outline=(160, 40, 0), width=3, slant=-0.25),
    'beetle': dict(font='ariblk.ttf', fill=('grad', (255, 255, 255), (200, 230, 255)), outline=(0, 20, 60), width=6, slant=0.15),
    'japan': dict(font='YuGothB.ttc', fill=('solid', (200, 0, 30)), outline=(20, 20, 20), width=4, slant=0.1),
    'underdog': dict(font='impact.ttf', fill=('grad', (255, 250, 120), (230, 20, 0)), outline=(20, 0, 0), width=4, slant=-0.2),
}


def glyphs(disc_tmp, font, text, y, size, border):
    """The caption's glyphs as a mask (0 to 1) of the logo's size, grown by border pixels."""
    tw, th = addseries.LG[0], addseries.LG[1]
    text = text.replace("'", "")
    vf = ("drawtext=fontfile=%s:text='%s':fontsize=%d:fontcolor=white:borderw=%d:bordercolor=white:"
          "x=(w-text_w)/2:y=%d" % (font, text, size, border, y))
    raw = subprocess.run([os.environ.get('XBRT_FFMPEG') or 'ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'gray', '-s', '%dx%d' % (tw, th), '-i', '-',
                          '-vf', vf, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         input=bytes(tw * th), capture_output=True, check=True, cwd=disc_tmp).stdout
    return np.frombuffer(raw, np.uint8).reshape(th, tw) / 255.0


def shear(m, k):
    """Each row shifted by k times its distance below the middle: a lean, as italics."""
    out = np.zeros_like(m)
    for r in range(m.shape[0]):
        out[r] = np.roll(m[r], int(round((r - m.shape[0] / 2) * k)))
    return out


def logo(disc, mods, source, top, bottom, texts, tmp):
    """The logo's picture (art), dark bands of top and bottom rows, and the captions [(text, y, size, style)]
    in the game's font with each style's fill and outline, as a PNG in tmp."""
    a = art(disc, mods, source).astype(np.float64)
    seed = zlib.crc32(repr((source, texts)).encode())
    # a little grain (a few levels): flat art compresses to less than the archive's streams need
    grain = np.random.default_rng(seed).integers(-3, 4, size=a.shape[:2] + (3,))
    a[..., :3] = np.clip(a[..., :3] + grain, 0, 255)
    if top: a[:top, :, :3] *= 0.2
    if bottom: a[-bottom:, :, :3] *= 0.2
    fonts = {STYLES[st]['font'] for *_, st in texts}
    for f in fonts:  # the Windows fonts, copied into the working folder under names ffmpeg reads
        shutil.copyfile(os.path.join(os.environ.get('WINDIR', 'C:' + chr(92) + 'Windows'), 'Fonts', f), os.path.join(tmp, f))
    rows = np.linspace(0, 1, a.shape[0])[:, None, None]
    for text, y, size, style in texts:
        st = STYLES[style]
        inner = glyphs(tmp, st['font'], text, y, size, 0)
        outer = np.maximum(glyphs(tmp, st['font'], text, y, size, st['width']), inner)
        inner, outer = shear(inner, st['slant']), shear(outer, st['slant'])
        if st['fill'][0] == 'grad':
            top_c, bottom_c = np.array(st['fill'][1], float), np.array(st['fill'][2], float)
            fill = top_c * (1 - rows) + bottom_c * rows
        else:
            fill = np.array(st['fill'][1], float)[None, None, :] * np.ones((a.shape[0], 1, 1))
        o = np.array(st['outline'], float)
        a[..., :3] = a[..., :3] * (1 - outer[..., None]) + o * outer[..., None]
        a[..., :3] = a[..., :3] * (1 - inner[..., None]) + fill * inner[..., None]
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
        for k, (name, level, desc, spec, prize, car, allowed, field, drivers, dup, xp, events) in enumerate(SERIES):
            x, ordinal = series_xml(k, ordinal, name, level, prize, allowed, field, drivers, dup, xp, events)
            p = os.path.join(tmp, 'series%d.xml' % k)
            open(p, 'w', encoding='latin-1', newline='').write(x)
            png = logo(disc, mods, *spec, tmp)
            addseries.main(disc, mods, 'club', p, name, '%s Win the series to win the %s.' % (desc, car), event_name=name,
                           logo='%s,%s' % (png, png))


if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit(__doc__)
    install(sys.argv[1], sys.argv[2])
