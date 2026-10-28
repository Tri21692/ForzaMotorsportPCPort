"""Pacific Shipyards at the end of the afternoon, for the circuits: its night made early evening.

Pacific Shipyards is lit at 1 am: its scenery's lightmaps (the bundle's
tex_tracks_vancouver_textures_shadows*, DXT1 or DXT5, the lamps' pools of
light baked in) are near black away from the lamps, its sky texture
(sky__newcloudsky, 512 x 512 A8R8G8B8) a dark blue, and its lamps glow
(prim 15 meshes) and flare. Here:

  - every lightmap is lifted towards a warm light: each DXT block's two
    colours c become c (1 - LIFT) + WARM LIFT, which, being affine, is the
    same change to every texel the block makes (the colours between are
    blends of the two); a block whose colours swap order is turned round
    (its indices remapped) so a DXT1 block keeps its mode;
  - the sky's texels are tinted orange by their brightness (clouds kept);
  - the street lamps' and floodlights' glows are hidden (lamp_glows), and the
    flares faded out, by the track.ini settings INI, with the light, fog and
    colour of an evening; the track list's TimeOfDay (an hour) is TIME.
"""
import struct

import numpy as np

import xb2

LIFT = 0.42
WARM = (0.60, 0.47, 0.34)          # what the lightmaps go towards (0-1: a lightmap at 0.5 leaves a texture as it is)
SKY = (1.0, 0.60, 0.34)            # the sky at the horizon
DUSK = (0.46, 0.40, 0.58)          # and overhead
TIME = '18.25'                     # the track list's TimeOfDay: a quarter past six
INI = {
    'GeneralRender\\Lighting\\Ambient\\Red': '0.62',
    'GeneralRender\\Lighting\\Ambient\\Green': '0.52',
    'GeneralRender\\Lighting\\Ambient\\Blue': '0.46',
    'GeneralRender\\Lighting\\Diffuse\\Red': '0.95',
    'GeneralRender\\Lighting\\Diffuse\\Green': '0.66',
    'GeneralRender\\Lighting\\Diffuse\\Blue': '0.42',
    'GeneralRender\\Effects\\Fog\\Red': '214',
    'GeneralRender\\Effects\\Fog\\Green': '138',
    'GeneralRender\\Effects\\Fog\\Blue': '96',
    'GeneralRender\\Effects\\Fog\\EndLevel': '0.30',
    'GeneralRender\\Effects\\Desaturate\\PostMod\\Red': '255',
    'GeneralRender\\Effects\\Desaturate\\PostMod\\Green': '226',
    'GeneralRender\\Effects\\Desaturate\\PostMod\\Blue': '196',
    'GeneralRender\\Particles\\Flare\\AlphaScale': '0.000000',
    'GeneralRender\\Particles\\Flare\\MinimumAlphaScale': '0.000000',
}


def lightmaps(names):
    """The lightmap texture resources: (data offset, size)."""
    return [(r[3], r[4]) for r in names if r[0].startswith('tex_tracks_vancouver_textures_shadows')]


def is_dxt5(data):
    """DXT5 (16-byte blocks, the first 8 an alpha block) or DXT1 (8-byte colour blocks): a
    lightmap's alpha blocks are nearly all one value (opaque), its colour blocks are not."""
    if len(data) % 16: return False
    q = np.frombuffer(data, '<u8')
    even, odd = q[0::2], q[1::2]
    vals, counts = np.unique(even, return_counts=True)
    top = vals[np.argmax(counts)]
    return (even == top).mean() > 0.5 and (odd == top).mean() < 0.1


def lift_blocks(colour, four_colour_always):
    """Colour blocks (n x 8 bytes: u16 c0, c1 565, u32 indices) with c -> c (1 - LIFT) + WARM LIFT."""
    c = colour.view('<u2').reshape(-1, 4)[:, :2].astype(np.int32)
    idx = colour.view('<u4').reshape(-1, 2)[:, 1].copy()
    rgb = np.stack([(c >> 11) & 31, (c >> 5) & 63, c & 31], -1).astype(float) / (31, 63, 31)
    rgb = rgb * (1 - LIFT) + np.array(WARM) * LIFT
    q = np.round(np.clip(rgb, 0, 1) * (31, 63, 31)).astype(np.int32)
    new = (q[..., 0] << 11) | (q[..., 1] << 5) | q[..., 2]
    if not four_colour_always:
        was4 = c[:, 0] > c[:, 1]
        now4 = new[:, 0] > new[:, 1]
        flip = was4 != now4
        # a 4-colour block whose colours came out equal: one apart again (its mode kept)
        tie = flip & was4 & (new[:, 0] == new[:, 1])
        bump = tie & (new[:, 0] < 0xFFFF)
        new[bump, 0] += 1
        new[tie & ~bump, 1] -= 1
        flip &= ~tie
        new[flip] = new[flip][:, ::-1]
        # turned round: in 4-colour mode indices 0<->1 and 2<->3; in 3-colour, 0<->1 (2 the middle, 3 clear)
        x = idx[flip]
        b = np.zeros_like(x)
        for k in range(16):
            v = (x >> np.uint32(2 * k)) & np.uint32(3)
            v = np.where(was4[flip], v ^ 1, np.where(v < 2, v ^ 1, v))
            b |= v.astype(np.uint32) << np.uint32(2 * k)
        idx[flip] = b
    out = colour.copy()
    out.view('<u2').reshape(-1, 4)[:, :2] = new.astype(np.uint16)
    out.view('<u4').reshape(-1, 2)[:, 1] = idx
    return out


def lift_lightmap(data):
    if is_dxt5(data):
        blocks = np.frombuffer(data, np.uint8).reshape(-1, 16).copy()
        blocks[:, 8:] = lift_blocks(np.ascontiguousarray(blocks[:, 8:]).reshape(-1), True).reshape(-1, 8)
        return blocks.tobytes()
    if len(data) % 8: return data
    return lift_blocks(np.frombuffer(data, np.uint8).copy(), False).tobytes()


def tint_sky(data, size=512):
    """The sky texture's levels (A8R8G8B8 swizzled, B G R A bytes; `size` square, then its mips):
    each texel the evening's colour at its height (its row in each of the texture's two bands of
    sky, top to horizon: dusk violet to SKY's orange) times its brightness against its row's (the
    clouds)."""
    import forzaxpr
    out, o, w = bytearray(data), 0, size
    while w >= 1 and o + w * w * 4 <= len(data):
        px = np.frombuffer(data, np.uint8, w * w * 4, o).reshape(-1, 4).astype(float) / 255
        idx = forzaxpr.unswizzle_index(w, w, 1).reshape(-1)  # texel (y, x) in row order -> its place
        row = np.empty(w * w, int)
        row[idx] = np.repeat(np.arange(w), w)
        lum = px[:, 2] * 0.3 + px[:, 1] * 0.59 + px[:, 0] * 0.11
        mean = np.bincount(row, lum, w) / w
        k = max(w // 64, 1)  # over a few rows: one row's own made streaks
        mean = np.convolve(np.pad(mean, k, mode='edge'), np.ones(2 * k + 1) / (2 * k + 1), 'valid')
        t = ((row % max(w // 2, 1)) / max(w // 2 - 1, 1)) ** 1.4  # 0 the band's top, 1 its horizon
        colour = np.array(DUSK) * (1 - t[:, None]) + np.array(SKY) * t[:, None]
        rgb = np.clip(colour * np.clip(lum / np.maximum(mean[row], 1e-3), 0.7, 1.5)[:, None], 0, 1)
        px[:, 2], px[:, 1], px[:, 0] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
        out[o:o + w * w * 4] = np.round(px * 255).astype(np.uint8).tobytes()
        o += w * w * 4
        w //= 2
    return bytes(out)


def apply(res):
    """The bundle (bytearray) made evening: lightmaps and sky. Returns (lightmaps changed, sky texels)."""
    names, _ = xb2.resources(bytes(res))
    n = 0
    for at, size in lightmaps(names):
        res[at:at + size] = lift_lightmap(bytes(res[at:at + size]))
        n += 1
    sky = [r for r in names if r[0] == 'tex_tracks_vancouver_textures_sky__newcloudsky']
    for r in sky:
        res[r[3]:r[3] + r[4]] = tint_sky(bytes(res[r[3]:r[3] + r[4]]))
    return n, sum(r[4] // 4 for r in sky)


def lamp_glows(res, model):
    """The prim 15 (glow) meshes of the street lamps and floodlights: names with 'light'."""
    names, _ = xb2.resources(bytes(res))
    n = struct.unpack_from('<I', res, model)[0]
    out = set()
    for i in range(n):
        a = struct.unpack_from('<I', res, model + 4 + 4 * i)[0]
        vb, _, prim = struct.unpack_from('<HHH', res, model + a + 16)
        if prim == 15 and 9 <= vb < len(names) + 9 and 'light' in names[vb - 9][0]:
            out.add(i)
    return out


def track_ini(text):
    """track.ini (CRLF lines, 'key value') with INI's keys set."""
    lines = text.split('\r\n')
    seen = set()
    for i, l in enumerate(lines):
        k = l.split(None, 1)[:1]
        if k and k[0] in INI:
            lines[i] = k[0] + ' ' + INI[k[0]]
            seen.add(k[0])
    lines += [k + ' ' + v for k, v in INI.items() if k not in seen]
    return '\r\n'.join(lines)
