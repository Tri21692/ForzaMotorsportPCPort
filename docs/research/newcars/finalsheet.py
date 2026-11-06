"""All cars' fresh renders on a few pages: front three-quarter, rear-top and side per car, labelled."""
import os, sys
from PIL import Image, ImageDraw
W = r'E:\xbrt_scr\newcars'
D = os.path.join(W, 'check_fresh')
keys = sorted(k for k in os.listdir(D) if os.path.isdir(os.path.join(D, k)) and os.path.exists(os.path.join(D, k, 'v_front.png')))
views = ('front', 'rtop', 'rear')
tw, th = 300, 200
per = 8
for page in range(0, len(keys), per):
    ks = keys[page:page + per]
    s = Image.new('RGB', (tw * len(views) * 2, th * ((len(ks) + 1) // 2)), 'black')
    for i, k in enumerate(ks):
        for j, v in enumerate(views):
            im = Image.open(os.path.join(D, k, 'v_%s.png' % v)).convert('RGB')
            im = im.crop((int(im.size[0] * 0.08), int(im.size[1] * 0.05), int(im.size[0] * 0.92), int(im.size[1] * 0.8)))
            im.thumbnail((tw, th))
            s.paste(im, ((i % 2) * tw * len(views) + j * tw, (i // 2) * th))
        ImageDraw.Draw(s).text(((i % 2) * tw * len(views) + 4, (i // 2) * th + 4), k, fill='yellow')
    out = os.path.join(W, 'final_%d.png' % (page // per))
    s.save(out, quality=88)
    print(out)
