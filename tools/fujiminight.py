"""Fujimi Kaido at night, and the Midnight Touge (the user's, 16 Nov: "an event with 2 events, both in the long
Fujimi tracks at night ... a touge-esque race. Make sure the track is illuminated and the car headlights are on.
Event restriction: D-Spec Only, Class A or below. 1v1").

Two tracks more in the list, copies of Fujimi Kaido Hill Climb (10) and Down Hill (51) with their own names
(FujimiNight, FujimiNightReverse), data folders and AI files (the same, renamed), and a collision file of their own:
its folder is what the runtime tells the loading track by (file.c), and under <mods>\\track\\FujimiNight\\ are the
night's copies of what both load: the scenery bundle with every lightmap (the scenery's and the trees') and the sky
taken down to a moonlit blue, and the small textures' file (.pvs.stx) the same. FujimiNightReverse's folder holds a
use.txt naming FujimiNight (file.c), so the 167 MB bundle is there once. track.ini is a night's: the light on the
cars, the fog, and the keys the disc's night tracks (Tokyo, Pacific Shipyards) have for the cars' lights; the track
list's TimeOfDay is ten at night.

The series, in the career's Point to Point list: two one-lap races against one D-Spec car picked at random, up the
mountain and down it. Entry: one <or> a D-Spec car, each with perfclass <> S (a road car is never Class R; seven
alternatives of two restrictions, 14 in all: the Drift Championship has seven, Sunday Stroll 15 restrictions). A race
of two cars is a catch-up race only on a track whose racing line's points catchup.txt lists (hle_career.c), and
Fujimi's are not there: no head start.

  python tools/fujiminight.py <disc> <mods folder> [tracks|series]
"""
import os
import re
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addcar
import addseries
import aitrack
import amateurseries as A
import evening
import shipyardloop
import xb2

B = chr(92)
PREFIX = 'tex_tracks_japanese_mountain_'
SKY = PREFIX + 'textures_sky__sky'
SUN = PREFIX + 'textures_sky__sun'
# (source's name, its disc folder, the new name, its title)
TRACKS = (('JapaneseMountain', 'JapaneseMountain', 'FujimiNight', 'Fujimi Kaido Hill Climb (Night)'),
          ('JapaneseMtReverse', 'JapaneseMtReverse', 'FujimiNightReverse', 'Fujimi Kaido Down Hill (Night)'))
TIME = '22.00'
# a lightmap texel c (0.5 leaves the texture as it is) becomes c (1 - LIFT) + TONE LIFT: the day's sun and shade
# brought close together and down, towards a blue
LIGHT = (float(os.environ.get('NIGHT_LIFT', 0.92)), tuple(float(v) for v in os.environ.get('NIGHT_TONE', '0.024,0.037,0.080').split(',')))
CAR_LIGHT = tuple(float(v) for v in os.environ.get('NIGHT_CAR', '0.22,0.27,0.42').split(','))  # the cars' light along the track, of the day's
SKY_TONE = (0.94, (0.006, 0.011, 0.032))
MOON = (0.35, (0.80, 0.85, 1.0))  # the sun's disc, paled: the moon
INI = {
    'GeneralRender\\Lighting\\Ambient\\Red': '0.10', 'GeneralRender\\Lighting\\Ambient\\Green': '0.12', 'GeneralRender\\Lighting\\Ambient\\Blue': '0.19',
    'GeneralRender\\Lighting\\Diffuse\\Red': '0.05', 'GeneralRender\\Lighting\\Diffuse\\Green': '0.06', 'GeneralRender\\Lighting\\Diffuse\\Blue': '0.10',
    'GeneralRender\\Effects\\Fog\\Red': '8', 'GeneralRender\\Effects\\Fog\\Green': '12', 'GeneralRender\\Effects\\Fog\\Blue': '24',
    'GeneralRender\\Effects\\Fog\\End': '700.000000', 'GeneralRender\\Effects\\Fog\\EndLevel': '0.60',
    'GeneralRender\\Sky\\SunScale': '0.600000', 'GeneralRender\\Sky\\SunFlareSacle': '0.300000', 'GeneralRender\\Sky\\SunEnvMapScale': '0.200000',
    'GeneralRender\\Sky\\Bloom\\Red': '25',
    # the cars' lights, as the disc's night tracks have them (Tokyo's values; the lights' reach further: no street lamps here)
    'GeneralRender\\Cars\\Lights\\LightFalloffDist': os.environ.get('NIGHT_REACH', '30'),
    'GeneralRender\\Cars\\Lights\\UseShadowHelper': 'No',
    'GeneralRender\\Shadow\\NumNightShadows': '1',
    'GeneralRender\\Shadow\\FocusHiLOD': '5', 'GeneralRender\\Shadow\\FocusLoLOD': '5',
    'GeneralRender\\Shadow\\NonFocusHiLOD': '5', 'GeneralRender\\Shadow\\NonFocusLoLOD': '5',
    'GeneralRender\\Shadow\\ProjectedColor\\Alpha': '0', 'GeneralRender\\Shadow\\ProjectedColor\\Red': '98',
    'GeneralRender\\Shadow\\ProjectedColor\\Green': '98', 'GeneralRender\\Shadow\\ProjectedColor\\Blue': '98',
    'GeneralRender\\Shadow\\DropColor\\Red': '32', 'GeneralRender\\Shadow\\DropColor\\Green': '32', 'GeneralRender\\Shadow\\DropColor\\Blue': '32',
    'GeneralRender\\LightBuffer\\OptimalLineAmbient': '0.01',
    'GeneralRender\\LightBuffer\\ClearColor\\Red': '24', 'GeneralRender\\LightBuffer\\ClearColor\\Green': '24', 'GeneralRender\\LightBuffer\\ClearColor\\Blue': '24',
    'GeneralRender\\Trees\\LightmapAmount': '0.0',  # (the trees by the track's light alone: with their lightmaps' share they stayed a day's green)
}
for _k, _v in [kv.split('=', 1) for kv in os.environ.get('NIGHT_INI', '').split(';') if '=' in kv]:
    INI['GeneralRender' + B + _k] = _v

# the track's options.xml: the game's own night (the cars' lights on, their night materials), as Tokyo's and Pacific
# Shipyards' ('lit="false"': no floodlights, as Sunset Speedway's night has), and their moon for the sun
OPTIONS = ('<options>\r\n    <environment night="true" lit="%s"/>\r\n    <sun texture="\\media\\temp\\moon.tga"/>\r\n</options>'
           % os.environ.get('NIGHT_LIT', 'false')).encode('latin-1')

SERIES = 'Midnight Touge'
DESC = 'Open to D-Spec cars of Class A and below. Two one-on-one runs on Fujimi Kaido at night: up the mountain, then down it.'
KIND = 'pointtopoint'
LEVEL = 10
SERIES_ID = 238
EVENT_ORDINAL = 420      # 420, 421 (the Eliminator's end at 419)
XP = 9000                # a win, each run
DSPEC = (250, 259, 263, 265, 111, 150, 159)   # the D-Spec cars (tools/driftcars.py; the Drift Championship's list)
# the rival: the D-Spec cars have no AI car models (ai\\aicarmodellist.xml; with theirs named the grid held the player alone,
# the test of 16 Nov) and are set up to slide, so the cars they are made from: Trueno, Silvia S15, 240SX, RX-7, stock
# on Easy, a stage of upgrades more on Medium and on Hard (the list's +1000, +2000)
RIVALS = (29, 89, 131, 133)
DRIVERS = (22, 36, 50)


# The scenery that has no lightmap over it, or too little of one, and stood out a day's colour in the night (the
# user's, 16 Nov: "make some of the scenery darker as well ... so it doesn't look weird": the leafy trees by the road
# a light green, the houses white): its own textures taken down, by group; the road signs and the tunnel's lamps
# left as they are, to be read and to glow.
DARK = {'vegetation_final': (float(os.environ.get('NIGHT_VEG', 0.82)), (0.02, 0.035, 0.07)),
        'buildings': (float(os.environ.get('NIGHT_BLDG', 0.75)), (0.03, 0.04, 0.08)),
        'ambient_objects': (0.40, (0.03, 0.04, 0.08)),
        'temp': (0.40, (0.03, 0.04, 0.08))}
KEEP = ('roadsigns', 'light')


def how_of(name):
    """(lift, tone, a lightmap: its format told by its blocks) for a texture of the night's, or None."""
    if is_light(name): return LIGHT + (True,)
    if name == SKY: return SKY_TONE + (True,)
    if name == SUN: return MOON + (True,)
    if name.startswith(PREFIX + 'textures_'):
        group, _, rest = name[len(PREFIX + 'textures_'):].partition('__')
        if group in DARK and not any(k in rest for k in KEEP): return DARK[group] + (False,)
    return None


def tone_blocks(data, f, lift, colour):
    """A DXT texture's levels (f: 0x0C DXT1, 0x0E DXT3, 0x0F DXT5) with its colours c -> c (1 - lift) + colour lift."""
    evening.LIFT, evening.WARM = lift, colour
    if f == 0x0C:
        n = len(data) // 8 * 8
        return evening.lift_blocks(np.frombuffer(data[:n], np.uint8).copy(), False).tobytes() + data[n:]
    n = len(data) // 16 * 16
    blocks = np.frombuffer(data[:n], np.uint8).reshape(-1, 16).copy()
    blocks[:, 8:] = evening.lift_blocks(np.ascontiguousarray(blocks[:, 8:]).reshape(-1), True).reshape(-1, 8)
    return blocks.tobytes() + data[n:]


def tone(data, lift, colour):
    evening.LIFT, evening.WARM = lift, colour
    return evening.lift_lightmap(data)


def is_light(name):
    return name.startswith(PREFIX + 'textures_shadows__') or name.startswith(PREFIX + 'treelightmaps__')


def stx_formats(data, names):
    """{texture name: its D3D format} from QuickPreview1.pvs.stx's headers (night_stx's layout)."""
    import struct
    size, slots, _, nres = struct.unpack_from('<4I', data, 20)
    table = np.frombuffer(data, '<i4', nres, 36)
    heads = 36 + 4 * nres
    out = {}
    for j, r in enumerate(names):
        if j + 9 < nres and table[j + 9] >= 0:
            out[r[0]] = (struct.unpack_from('<5I', data, heads + 20 * int(table[j + 9]))[3] >> 8) & 0xFF
    return out


def night_res(res, stx):
    names, _ = xb2.resources(bytes(res))
    formats = stx_formats(stx, names)
    n = 0
    import struct
    for r in names:
        how = how_of(r[0])
        if not how: continue
        if how[2]:
            res[r[3]:r[3] + r[4]] = tone(bytes(res[r[3]:r[3] + r[4]]), *how[:2])
        else:
            f = formats.get(r[0])  # (from the small textures' file: the bundle's own headers are not where its index says)
            if f not in (0x0C, 0x0E, 0x0F): continue
            res[r[3]:r[3] + r[4]] = tone_blocks(bytes(res[r[3]:r[3] + r[4]]), f, *how[:2])
        n += 1
    return names, n


def night_stx(data, names):
    """QuickPreview1.pvs.stx (evening.stx's layout: the scenery's textures at 32 texels or less, drawn before the
    full ones load) with the lightmaps and the sky as the bundle's."""
    import struct
    out = bytearray(data)
    size, slots, _, nres = struct.unpack_from('<4I', data, 20)
    table = np.frombuffer(data, '<i4', nres, 36)
    heads = 36 + 4 * nres
    base = heads + 20 * slots
    done = 0
    for j, r in enumerate(names):
        how = how_of(r[0])
        if not how or j + 9 >= nres: continue
        how = how[:2]
        k = table[j + 9]
        if k < 0: continue
        _, word, _, fmt, _ = struct.unpack_from('<5I', data, heads + 20 * k)
        f, w, h, mips = (fmt >> 8) & 0xFF, 1 << ((fmt >> 20) & 15), 1 << ((fmt >> 24) & 15), max((fmt >> 16) & 15, 1)
        o = base + (word & 0x7FFFFFFF)
        if f not in (0x0C, 0x0E, 0x0F): continue
        bs = 8 if f == 0x0C else 16
        n = sum(max(w >> m, 4) // 4 * (max(h >> m, 4) // 4) for m in range(mips)) * bs
        evening.LIFT, evening.WARM = how
        if bs == 16:
            blocks = np.frombuffer(bytes(out[o:o + n]), np.uint8).reshape(-1, 16).copy()
            blocks[:, 8:] = evening.lift_blocks(np.ascontiguousarray(blocks[:, 8:]).reshape(-1), True).reshape(-1, 8)
            out[o:o + n] = blocks.tobytes()
        else:
            out[o:o + n] = evening.lift_blocks(np.frombuffer(bytes(out[o:o + n]), np.uint8).copy(), False).tobytes()
        done += 1
    return bytes(out), done


def car_light(data):
    """trackLightmap.dat (u32 3, then a zlib stream of 4-byte texels: the light on the cars along the track, a colour
    and a fourth byte left as it is) with the colours taken down to the night's."""
    import struct
    import zlib
    if struct.unpack_from('<I', data)[0] != 3: return data
    px = np.frombuffer(zlib.decompress(data[4:]), np.uint8).reshape(-1, 4).astype(float)
    px[:, :3] *= np.array(CAR_LIGHT)[::-1]  # (the texels are blue, green, red: red-first made the car orange)
    return struct.pack('<I', 3) + zlib.compress(np.clip(np.round(px), 0, 255).astype(np.uint8).tobytes(), 9)


def track_ini(text):
    evening.INI = INI
    return evening.track_ini(text)


def video(folder):
    return 'd:' + B + 'media' + B + 'tracks' + B + folder + B + 'Flythrough.bik'


def entry(tracklist, src, tag, title, name_id, src_folder):
    m = re.search(r'<track\s[^>]*\sname="%s".*?/>' % src, tracklist, re.S)
    e = m.group(0)
    recs = re.findall(r'<track\s.*?/>', tracklist, re.S)
    ordinal = max(int(x) for r in recs for x in re.findall(r'\bOrdinal="(\d+)"', r)) + 1

    def attr(e, k, v):
        e2, n = re.subn(r'\b%s="[^"]*"' % k, lambda m: '%s="%s"' % (k, v), e, count=1)
        return e2 if n else re.sub(r'\s*/>$', lambda m: ' %s="%s" />' % (k, v), e)
    folder = 'd:' + B + 'media' + B + 'tracks' + B + tag + B
    for k, v in (('RosettaName', title), ('name', tag), ('trackIdentifier', tag), ('tracknameid', name_id),
                 ('collisionFile', folder + 'QuickPreview1.col'), ('dataFile', folder + 'QuickPreview.xml'),
                 ('trackSegCamsFile', folder + 'TrackSegCams.xml'), ('Ordinal', ordinal), ('TimeOfDay', TIME), ('Video', video(src_folder))):
        e = attr(e, k, v)
    last = recs[-1]
    at = tracklist.index(last) + len(last)
    return tracklist[:at] + '\r\n\r\n\t' + e + tracklist[at:], ordinal


def install_tracks(disc, mods):
    mega = addcar.Archive(disc, mods, 'Mega.ca2')
    files = {k.lower(): k for k in mega.files}
    tl_key = files['forzadb' + B + 'tracklist.xml']
    tracklist = mega.files[tl_key].decode('latin-1')
    listed = {tag: re.search(r'<track\s[^>]*\sname="%s"[^>]*?\sOrdinal="(\d+)"' % tag, tracklist, re.S) for _, _, tag, _ in TRACKS}
    ordinals = []
    ai = 'ai' + B + 'drivatarv2' + B
    for src, folder, tag, title in TRACKS:
        if listed[tag]:
            ordinals.append(int(listed[tag].group(1)))
            m = re.search(r'<track\s[^>]*\sname="%s".*?/>' % tag, tracklist, re.S)
            if ' Video="' not in m.group(0):  # (its preview on the track's screen: the source's; none named is looked for in its own folder, "a problem with the disc")
                tracklist = tracklist[:m.start()] + re.sub(r'\s*/>$', lambda _: ' Video="%s" />' % video(folder), m.group(0)) + tracklist[m.end():]
        else:
            nid = None
            loc = addcar.disc_file(disc, 'media', 'Loc')
            for lang in sorted(os.listdir(loc)):
                p = addcar.disc_file(disc, 'media', 'Loc', lang, 'TrackStrings.str')
                if not p: continue
                mp = os.path.join(mods, 'media', 'Loc', lang, 'TrackStrings.str')
                new = addcar.write_strings(open(mp if os.path.exists(mp) else p, 'rb').read(), [('IDS_Track_Name_' + tag, title)])
                i = addcar.string_ids(new)['IDS_Track_Name_' + tag]
                if nid not in (None, i): raise SystemExit('track name ids differ between languages')
                nid = i
                os.makedirs(os.path.dirname(mp), exist_ok=True)
                open(mp, 'wb').write(new)
            tracklist, ordinal = entry(tracklist, src, tag, title, nid, folder)
            ordinals.append(ordinal)
            print('"%s": track %d, name string %d' % (title, ordinal, nid))
        # its data folder (the night's track.ini) and AI files, the source's
        s, d = 'tracks' + B + src.lower() + B, 'tracks' + B + tag.lower() + B
        for k in list(mega.files):
            if k.lower().startswith(s):
                v = mega.files[k]
                if k.lower().endswith('track.ini'): v = track_ini(v.decode('latin-1')).encode('latin-1')
                if k.lower().endswith('options.xml'): v = OPTIONS
                mega.files[d + k[len(s):].lower()] = v
        for k in list(mega.files):
            kl = k.lower()
            if not kl.startswith(ai): continue
            rest = kl[len(ai):]
            for a, b in ((src.lower() + 'geometry.bin', tag.lower() + 'geometry.bin'), (src.lower() + 'segmentation.bin', tag.lower() + 'segmentation.bin'),
                         ('interaction-rt-' + src.lower() + '.bin', 'interaction-rt-' + tag.lower() + '.bin'),
                         ('segmentprofiles' + B + src.lower() + B + 'default.bin', 'segmentprofiles' + B + tag.lower() + B + 'default.bin')) + \
                        tuple((lv + B + src.lower() + '.bin', lv + B + tag.lower() + '.bin') for lv in ('level1', 'level2', 'level3')):
                if rest == a:
                    v = mega.files[k]
                    try: v = aitrack.renamed(v, tag) if b'trackName' in v[:4000] else v
                    except Exception: pass
                    mega.files[ai + b] = v
        v, fields = aitrack.mlp.read(mega.files[files[ai + 'tracklist.bin']])
        names = [v['trackList_%d' % i] for i in range(1, int(v['trackList_size'][0]) + 1)]
        if tag.encode() not in names:
            names.append(tag.encode())
            mega.files[files[ai + 'tracklist.bin']] = aitrack.mlp.write([('trackList_size', 'int32', [len(names)])] +
                                                                         [('trackList_%d' % (i + 1), 'char', nm) for i, nm in enumerate(names)])
        # its folder on the disc: the collision (the runtime's mark of the loading track) and the source's small files
        dd = os.path.join(mods, 'media', 'tracks', tag)
        os.makedirs(dd, exist_ok=True)
        open(os.path.join(dd, 'QuickPreview1.col'), 'wb').write(open(addcar.disc_file(disc, 'media', 'tracks', 'JapaneseMountain', 'QuickPreview1.col'), 'rb').read())
        sf = addcar.disc_file(disc, 'media', 'tracks', folder)
        for f in os.listdir(sf):
            fl = f.lower()
            if fl.endswith(('.xb2', '.bik', '.col')) or fl.startswith(('quickpreview1.pvs', 'quickpreview1.xbp')): continue
            data = open(os.path.join(sf, f), 'rb').read()
            if fl == 'tracklightmap.dat': data = car_light(data)
            open(os.path.join(dd, f), 'wb').write(data)
    mega.files[tl_key] = tracklist.encode('latin-1')
    mega.check()
    mega.write()
    # the night's scenery, once, under the first track's folder
    first = os.path.join(mods, 'track', TRACKS[0][2])
    if os.environ.get('NIGHT_SCENERY') == '0' and os.path.exists(os.path.join(first, 'hdd', 'Partition5', 'JapaneseMountain.res')): return ordinals
    res = shipyardloop.unpack_xb2(addcar.disc_file(disc, 'media', 'tracks', 'JapaneseMountain', 'QuickPreview1.xb2'))
    names, n = night_res(res, open(addcar.disc_file(disc, 'media', 'tracks', 'JapaneseMountain', 'QuickPreview1.pvs.stx'), 'rb').read())
    os.makedirs(os.path.join(first, 'hdd', 'Partition5'), exist_ok=True)
    open(os.path.join(first, 'hdd', 'Partition5', 'JapaneseMountain.res'), 'wb').write(res)
    print('%d lightmaps, sky and scenery textures taken down to night' % n)
    for folder in ('JapaneseMountain', 'JapaneseMtReverse'):
        data, k = night_stx(open(addcar.disc_file(disc, 'media', 'tracks', folder, 'QuickPreview1.pvs.stx'), 'rb').read(), names)
        os.makedirs(os.path.join(first, 'media', 'tracks', folder), exist_ok=True)
        open(os.path.join(first, 'media', 'tracks', folder, 'QuickPreview1.pvs.stx'), 'wb').write(data)
        print('%s: %d small textures' % (folder, k))
    for _, _, tag, _ in TRACKS[1:]:
        os.makedirs(os.path.join(mods, 'track', tag), exist_ok=True)
        open(os.path.join(mods, 'track', tag, 'use.txt'), 'w').write(TRACKS[0][2] + '\n')
    return ordinals


def logo_art():
    """A night over the mountain: a deep blue sky, the moon, the mountain's outline and the road's bends lit up it."""
    th, tw = addseries.LG[1], addseries.LG[0]
    yy, xx = np.mgrid[0:th, 0:tw].astype(float)
    a = np.zeros((th, tw, 4))
    t = (yy / th)[..., None]
    a[..., :3] = np.array((10, 14, 40)) * (1 - t) + np.array((40, 52, 110)) * t
    rng = np.random.default_rng(7)
    for _ in range(60):
        x, y = rng.integers(0, tw), rng.integers(0, th // 2)
        a[y, x, :3] = 190 + rng.integers(0, 60)
    d = np.hypot(xx - 168, yy - 30)
    moon = np.clip(13 - d, 0, 1)[..., None]
    glow = np.exp(-np.clip(d - 13, 0, None) / 9.0)[..., None] * 0.45
    a[..., :3] = a[..., :3] + (np.array((235, 238, 255)) - a[..., :3]) * np.clip(moon + glow, 0, 1)
    ridge = 70 - 34 * np.exp(-((xx - 96) / 46.0) ** 2) + 6 * np.sin(xx / 13.0) + 3 * np.sin(xx / 5.0)
    hill = np.clip(yy - ridge, 0, 1)[..., None]
    a[..., :3] = a[..., :3] * (1 - hill) + np.array((6, 9, 20)) * hill
    # the road: a lit zigzag up the mountain
    road = np.zeros((th, tw))
    pts = [(20, 112), (150, 100), (60, 88), (128, 77), (78, 66), (110, 57), (90, 49), (98, 42)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for s in np.linspace(0, 1, 200):
            x, y = x0 + (x1 - x0) * s, y0 + (y1 - y0) * s
            w = 0.6 + 2.2 * (y - 40) / 72.0
            road = np.maximum(road, np.clip(w - np.hypot(xx - x, yy - y), 0, 1))
    a[..., :3] = a[..., :3] * (1 - road[..., None]) + np.array((255, 214, 120)) * road[..., None]
    a[..., 3] = 255
    return a


def series_xml(tracks):
    ai = ''.join('\t\t<AIPlayer name="If you see this, it is a bug" aicarmodelid="%d" AIDriverModelID="%d" AppearanceID="0" %s />\r\n'
                 % (100 + car + 1000 * stage, driver, skill) for stage, (driver, skill) in enumerate(zip(DRIVERS, ('Easy', 'Medium', 'Hard'))) for car in RIVALS)
    x = ('<?xml version="1.0"?>\r\n<series displayname="%s" seriesnameid="{SERIES_NAME_ID}" seriesdescid="{SERIES_DESC_ID}" '
         'seriesid="%d" seriesordinal="0" seriesorder="0" Icon="{ICON}" Level="%d">\r\n'
         '\t<Scoring>\r\n\t\t<score pos="1"></score>\r\n\t\t<score pos="2"></score>\r\n\t</Scoring>\r\n\t<Restrictions>\r\n' % (SERIES, SERIES_ID, LEVEL) +
         A.restrictions([[('carid', '=', car), ('perfclass', '<>', 'S')] for car in DSPEC]) + '\t</Restrictions>\r\n\t<AIField>\r\n' + ai + '\t</AIField>\r\n')
    for k, track in enumerate(tracks):
        x += ('\t<event eventid="%d" displayname="%s" eventordinal="%d" eventtextid="{EVENT_NAME_ID}" eventdescid="{EVENT_DESC_ID}" '
              'type="Single" leaderboard="1450">\r\n'
              '\t\t<track Ordinal="%d" />\r\n\t\t<laps count="1" />\r\n'
              '\t\t<AIField NumAICars="1" random="true" byclass="false" duplicates="false" />\r\n'
              '\t\t<AIModeSettings>\r\n\t\t\t<pitting aipitting tire="0.01" fuel="0.01" engine="0.5" transmission="0.5" suspension="0.5" spreadpercent="0" />\r\n'
              '\t\t</AIModeSettings>\r\n\t\t<Scoring>\r\n'
              '\t\t\t<score pos="1" pts="10" xp="%d"></score>\r\n\t\t\t<score pos="2" pts="0" xp="0"></score>\r\n'
              '\t\t</Scoring>\r\n\t</event>\r\n' % (k + 1, SERIES, EVENT_ORDINAL + k, track, XP))
    return x + '</series>\r\n'


def install_series(disc, mods, tracks):
    global DSPEC
    import driftcars
    DSPEC = tuple(sorted(driftcars.ordinals(disc, mods).values())) or DSPEC  # (every D-Spec car there is)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'touge.xml')
        open(p, 'w', encoding='latin-1', newline='').write(series_xml(tracks))
        png = A.logo(disc, mods, dict(image=logo_art()), [('MIDNIGHT', 4, 22, 'chrome'), ('TOUGE', 88, 24, 'faceoff')], tmp)
        addseries.main(disc, mods, KIND, p, SERIES, DESC, event_name=SERIES, logo='%s,%s' % (png, png))
    print('%s: events %d, %d on tracks %s' % (SERIES, EVENT_ORDINAL, EVENT_ORDINAL + 1, tracks))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4): raise SystemExit(__doc__)
    what = sys.argv[3] if len(sys.argv) > 3 else 'all'
    if any(part.lower() in ('udata', 'tdata', 'partition1', 'partition2') for part in os.path.abspath(sys.argv[2]).split(os.sep)):
        raise SystemExit('%s: a save folder' % sys.argv[2])
    ords = install_tracks(sys.argv[1], sys.argv[2])
    if what in ('all', 'series'): install_series(sys.argv[1], sys.argv[2], ords)
