"""Class F's badges (the user's, 6 Nov: "call it F, a darker red than S"): each class strip's S slot recoloured from
S's orange to a deep crimson, its letter taken out (filled from the background round it) and an F drawn in its
place in the same manner (white, heavy, slanted, a dark drop shadow). Writes PNGs of the new slots into classicons/
for a look; fclass.py puts them into the strips."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
D = r'E:\xbrt_scr\newcars\classicons'
CRIMSON = np.array([110, 0, 25], float)  # (S is 223, 133, 27; R and the race classes 170, 0, 0)
ORANGE = np.array([223, 133, 27], float)
FONT = r'C:\Windows\Fonts\ariblk.ttf'


def recolour(a):
    """Orange (S's) pixels to crimson, keeping their shading: by each pixel's brightness against S's own orange."""
    a = a.astype(float).copy()
    rgb = a[..., :3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    warm = (rgb[..., 0] >= rgb[..., 1]) & (rgb[..., 1] >= rgb[..., 2] - 10) & (sat > 0.12) & (rgb[..., 0] - rgb[..., 2] > 25)  # (the pale tan of S's shadows too)
    lum = rgb @ np.array([0.299, 0.587, 0.114]) / (ORANGE @ np.array([0.299, 0.587, 0.114]))
    rgb[warm] = np.clip(CRIMSON[None, :] * lum[warm][:, None] * 1.15, 0, 255)
    a[..., :3] = rgb
    return a


def fill(a, mask, steps=400):
    """The masked pixels filled from round them (repeated neighbour means), as the backgrounds are smooth."""
    a = a.copy()
    known = ~mask
    a[mask, :3] = 0
    for _ in range(steps):
        acc = np.zeros(a.shape[:2] + (3,)); n = np.zeros(a.shape[:2])
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s = np.roll(np.roll(a[..., :3], dy, 0), dx, 1); k = np.roll(np.roll(known, dy, 0), dx, 1)
            acc += s * k[..., None]; n += k
        upd = mask & (n > 0)
        a[upd, :3] = acc[upd] / n[upd][:, None]
        known = known | upd
    return a


def letter_mask(a, box):
    """The white letter and its dark rim inside box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    rgb = a[..., :3]
    white = rgb.min(-1) > 200
    m = np.zeros(white.shape, bool); m[y0:y1, x0:x1] = white[y0:y1, x0:x1]
    for _ in range(2):  # (its outline and shadow round it)
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    mm = np.zeros_like(m); mm[y0:y1, x0:x1] = m[y0:y1, x0:x1]
    return mm


def draw_f(img, box, shadow=(45, 0, 10), outline=None, slant=0.22, size=None):
    """An F in box: white, heavy, slanted, a drop shadow down and to the left."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    size = size or int(h * 1.18)
    font = ImageFont.truetype(FONT, size)
    pad = size
    layer = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bb = d.textbbox((0, 0), 'F', font=font)
    tx = pad + (w - (bb[2] - bb[0])) // 2 - bb[0]
    ty = pad + (h - (bb[3] - bb[1])) // 2 - bb[1]
    off = max(1, h // 12)
    if outline: d.text((tx, ty), 'F', font=font, fill=outline, stroke_width=max(1, h // 16), stroke_fill=outline)
    d.text((tx - off, ty + off), 'F', font=font, fill=shadow + (255,))
    d.text((tx, ty), 'F', font=font, fill=(232, 232, 232, 255))
    layer = layer.transform(layer.size, Image.AFFINE, (1, slant, -slant * layer.size[1] / 2, 0, 1, 0), Image.BICUBIC)
    layer = layer.crop((pad, pad, pad + w, pad + h))
    img.alpha_composite(layer, (x0, y0))
    return img


def slot(path, i, h, w=None):
    im = Image.open(os.path.join(D, path)).convert('RGBA')
    w = w or im.size[0]
    return im.crop((0, i * h, w, i * h + h))


def make():
    out = {}
    # the subclass label (45 x 32, S1 is slot 19): F alone
    s = np.asarray(slot('frontend_sym_classlabel.xpr.png', 19, 32), float)
    s = recolour(s)
    s = fill(s, letter_mask(s, (2, 2, 43, 30)))
    im = Image.fromarray(s.astype(np.uint8), 'RGBA')
    out['sym_classlabel'] = draw_f(im, (3, 1, 42, 31), shadow=(50, 0, 12))
    # the time-trial labels (45 x 32, S at 16)
    s = np.asarray(slot('frontend_sym_classlabel-trial.xpr.png', 16, 32), float)
    s = recolour(s); s = fill(s, letter_mask(s, (1, 1, 44, 31)))
    out['sym_classlabel-trial'] = draw_f(Image.fromarray(s.astype(np.uint8), 'RGBA'), (3, 1, 42, 31), shadow=(50, 0, 12), slant=0.12)
    # the class letters, small (21 x 15) and medium (25 x 18), S at 4
    for name, h in (('ico_class', 15), ('ico_class-med', 18)):
        s = np.asarray(slot('frontend_%s.xpr.png' % name, 4, h), float)
        s = recolour(s); s = fill(s, letter_mask(s, (0, 0, s.shape[1], h)))
        out[name] = draw_f(Image.fromarray(s.astype(np.uint8), 'RGBA'), (0, 0, s.shape[1], h), shadow=(50, 0, 12), slant=0.1)
    # the border (108 x 60, S at 4): only its colour
    out['ico_class_border'] = Image.fromarray(recolour(np.asarray(slot('frontend_ico_class_border.xpr.png', 4, 60), float)).astype(np.uint8), 'RGBA')
    # the large "S CLASS" tile (108 x 60, S at 4), every language's: the letter above "C.L.A.S.S"
    for lang in ('', 'de_', 'en_', 'es_', 'fr_', 'it_', 'ja_', 'ko_', 'zh_'):
        s = np.asarray(slot('frontend_%sico_class-lg.xpr.png' % lang, 4, 60), float)
        s = recolour(s)
        s = fill(s, letter_mask(s, (30, 1, 80, 40)), steps=600)
        out[lang + 'ico_class-lg'] = draw_f(Image.fromarray(s.astype(np.uint8), 'RGBA'), (34, 2, 76, 40), shadow=(30, 0, 8), outline=(20, 20, 20, 255))
    return out


if __name__ == '__main__':
    out = make()
    tiles = []
    for k, im in out.items():
        im.save(os.path.join(D, 'F_%s.png' % k))
        big = im.resize((im.size[0] * 5, im.size[1] * 5), Image.NEAREST)
        bg = Image.new('RGBA', big.size, (80, 80, 80, 255)); bg.alpha_composite(big); tiles.append(bg)
    # beside S for comparison
    W = sum(t.size[0] for t in tiles[:6]) + 60
    sheet = Image.new('RGB', (W, 320), (30, 30, 30)); x = 0
    for t in tiles[:6]: sheet.paste(t.convert('RGB'), (x, 0)); x += t.size[0] + 10
    sheet.save(os.path.join(D, 'F_preview.png'))
    print(list(out))
