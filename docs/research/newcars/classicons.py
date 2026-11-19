"""The class badges' textures (MegaXPR.ca2 frontend\\*class*.xpr, every language folder too): linear A8R8G8B8
strips (addmake.strip_size), decoded to PNG with their sizes."""
import sys, os, struct
sys.path.insert(0, r'E:\Forza Motorsport Remastered\tools')
import numpy as np
from PIL import Image
import addcar, addmake
DISC = r'C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso'
OUT = r'E:\xbrt_scr\newcars\classicons'
a = addcar.Archive(DISC, r'E:\Forza Motorsport Remastered\run\mods_track', 'MegaXPR.ca2')
B = chr(92)
os.makedirs(OUT, exist_ok=True)
for k in sorted(k for k in a.disc if 'class' in k.lower()):
    d = bytes(a.disc[k])
    hdr = struct.unpack_from('<I', d, 8)[0]
    fmt = (struct.unpack_from('<I', d, 24)[0] >> 8) & 0xFF
    w, h, pitch = addmake.strip_size(d)
    print('%-40s fmt %02x  %d x %d pitch %d  bytes %d' % (k, fmt, w, h, pitch, len(d)))
    if fmt != 0x12: continue
    px = np.frombuffer(d[hdr:hdr + pitch * h], np.uint8).reshape(h, pitch)[:, :w * 4].reshape(h, w, 4)[..., [2, 1, 0, 3]]
    Image.fromarray(px, 'RGBA').save(os.path.join(OUT, k.replace(B, '_') + '.png'))
