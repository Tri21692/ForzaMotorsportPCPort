"""A track's preview clip of our own, for runtime/hle_clip.c: pictures (a race recorded with XBRT_PRESENT_SHOT at a
steady rate) cropped clear of the HUD, shrunk, and packed as the .clip file read beside the track's Flythrough.bik.

  python tools/makeclip.py <folder of p_*.ppm> <first> <count> <out.clip> [width height] [repeat]

The crop is the middle of a 4:3 picture between the map, the lap times, the speedometer and the place (x 26%-77%,
y 18%-69%: the road ahead over the car's roof). repeat: the movie's frames each clip frame is shown for (2: pictures 66 ms apart under a 29.97 a
second movie). The file: "FZCL", u32 width, height, frames, repeat, frames + 1 u32 offsets, then each frame a zlib
stream of RGB565, top row first."""
import glob, os, struct, sys, zlib
import numpy as np
from PIL import Image

CROP = (0.26, 0.18, 0.77, 0.69)


def main(folder, first, count, out, w=324, h=243, repeat=2):
    num = lambda f: int(os.path.basename(f)[2:-4])  # (p_999, p_1000: by number, not by name)
    fs = sorted(glob.glob(os.path.join(folder, 'p_*.ppm')), key=num)[first:first + count]
    blobs = []
    for f in fs:
        im = Image.open(f).convert('RGB')
        W, H = im.size
        im = im.crop((int(CROP[0] * W), int(CROP[1] * H), int(CROP[2] * W), int(CROP[3] * H))).resize((w, h), Image.LANCZOS)
        a = np.asarray(im).astype(np.uint16)
        px = (a[..., 0] >> 3) << 11 | (a[..., 1] >> 2) << 5 | a[..., 2] >> 3
        blobs.append(zlib.compress(px.astype('<u2').tobytes(), 9))
    n = len(blobs)
    off, at = [], 20 + 4 * (n + 1)
    for b in blobs: off.append(at); at += len(b)
    off.append(at)
    with open(out, 'wb') as f:
        f.write(b'FZCL' + struct.pack('<4I', w, h, n, repeat) + struct.pack('<%dI' % (n + 1), *off) + b''.join(blobs))
    print('%s: %d frames of %d x %d, %.1f MB' % (out, n, w, h, at / 2 ** 20))


if __name__ == '__main__':
    a = sys.argv
    if len(a) < 5: raise SystemExit(__doc__)
    main(a[1], int(a[2]), int(a[3]), a[4], *(int(x) for x in a[5:8]))
