"""cuts.py <folder> <first> <last>: the camera's cuts in a run of pictures (a jump in the picture from one to the next),
as the stretches between them: first picture, count."""
import os
import sys

import numpy as np
from PIL import Image

d, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])


def small(k):
    for t in ('p_%d.ppm', 'p_%03d.ppm', 'p_%04d.ppm'):
        f = os.path.join(d, t % k)
        if os.path.exists(f):
            return np.asarray(Image.open(f).convert('L').resize((64, 48)), dtype=np.float32)
    return None


prev, start, out, diffs = None, a, [], []
for k in range(a, b):
    im = small(k)
    if im is None: continue
    if prev is not None:
        df = float(np.abs(im - prev).mean())
        diffs.append(df)
        med = float(np.median(diffs[-40:])) if len(diffs) > 5 else 8.0
        if df > max(22.0, 3.5 * med):
            out.append((start, k - start))
            start = k
    prev = im
out.append((start, b - start))
print(' '.join('%d:%d' % s for s in out))
