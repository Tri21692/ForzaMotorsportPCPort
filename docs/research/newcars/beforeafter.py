"""Before (as installed 5 Nov) and after (6 Nov fixes) for the cars the Blender check changed most."""
import os
from PIL import Image, ImageDraw
W = r'E:\xbrt_scr\newcars'
rows = [('lfa', 'rtop', 'rear window was a hole'), ('335i', 'front', 'no windscreen or side glass'),
        ('brera', 'rtop', 'glass roof was a hole'), ('chiron', 'rtop', 'engine bay missing, Enzo windows'),
        ('m2', 'rtop', 'rear window was a hole'), ('4c', 'front', 'Elise headlight floating off the nose'),
        ('charger', 'left', 'door handles as dark boxes'), ('xk', 'rtop', 'rear window opaque black')]
tw, th = 450, 300
s = Image.new('RGB', (tw * 2, th * len(rows) + 30), (24, 24, 24))
d = ImageDraw.Draw(s)
d.text((tw // 2 - 40, 8), 'BEFORE (installed 5 Nov)', fill='white'); d.text((tw + tw // 2 - 40, 8), 'AFTER (6 Nov)', fill='white')
for i, (k, v, why) in enumerate(rows):
    for j, base in enumerate(('check', 'check_fresh')):
        im = Image.open(os.path.join(W, base, k, 'v_%s.png' % v)).convert('RGB')
        im.thumbnail((tw, th))
        s.paste(im, (j * tw, 30 + i * th))
    d.text((6, 34 + i * th), '%s: %s' % (k, why), fill='yellow')
out = r'E:\Forza Motorsport Remastered\docs\new-cars-blender-fixes.jpg'
s.save(out, quality=85)
print(out)
