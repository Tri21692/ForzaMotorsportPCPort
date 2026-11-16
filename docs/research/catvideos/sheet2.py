import sys, os
from PIL import Image, ImageDraw
d, a, b, step = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
ks = list(range(a, b, step))
cols = 10
s = Image.new('RGB', (cols * 160, ((len(ks) + cols - 1) // cols) * 120))
dr = ImageDraw.Draw(s)
for i, k in enumerate(ks):
    f = next((os.path.join(d, t % k) for t in ('p_%d.ppm', 'p_%03d.ppm', 'p_%04d.ppm') if os.path.exists(os.path.join(d, t % k))), None)
    if not f: continue
    x, y = (i % cols) * 160, (i // cols) * 120
    s.paste(Image.open(f).resize((160, 120)), (x, y))
    dr.rectangle((x, y, x + 44, y + 11), fill=(0, 0, 0)); dr.text((x + 2, y), str(k), fill=(255, 255, 0))
s.save(sys.argv[5], quality=80)
