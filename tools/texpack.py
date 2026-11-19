"""An HD texture pack for the port (runtime/gltexhd.c): the game's textures, exported while playing,
upscaled offline, laid where the runtime swaps them in as they load.

  1. Play with XBRT_TEX_EXPORT=<folder> (or set it in a launcher): each texture the game uploads is
     saved there once, as <key>.bmp (32-bit, with alpha), the key the runtime finds it by.
  2. python tools/texpack.py <that folder> <pack folder> [--upscaler <realesrgan-ncnn-vulkan.exe>]
         [--model realesrgan-x4plus] [--scale 2|4] [--max-out 1024] [--min 32] [--max 1024]
     writes <pack folder>/<key>.hd for each ('XHD1', u32 width, u32 height, BGRA texels, rows down).
  3. The pack folder is <mods>/textures (or XBRT_TEX_PACK): the next start reads it.

With --upscaler, Real-ESRGAN (ncnn/Vulkan, BSD-3, github.com/xinntao/Real-ESRGAN) draws the colour,
adding detail; the alpha (cut-outs: fences, foliage, decals) is scaled smoothly by ffmpeg. Without
it, ffmpeg's Lanczos does both: no more than the runtime's own 2x (texture_upscale), so a pack is
worth making with an upscaler. Textures under --min or over --max texels a side, and plain ones (a
single colour), are left out. Done ones (<key>.hd there) are skipped, so a pack grows as more of the
game is played and exported.

Each texture is made --scale times bigger, or 2x where that would pass --max-out texels a side
(a 512 one: 1024): the pack is held uncompressed on the GPU (4 bytes a texel, 16 times the memory
at 4x), and an 8 GB card also holds the game drawn at 4x its size. Frames of videos and copies of
the screen (redrawn at one address) are not exported by the runtime; ones exported before it left
them out can be left out here with --skip-sizes 486x364,640x240. Textures --max-clear (0.9) or more
fully clear are left out: the menus' text comes from glyph sheets holding a different letter in each
channel, which an upscaler for pictures mixes (each letter came out boxed, bits of others in it).
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

FF = os.environ.get('XBRT_FFMPEG') or 'ffmpeg'


def read_bmp(path):
    """The runtime's export: BGRA rows, top-down (negative height)."""
    d = open(path, 'rb').read()
    off, = struct.unpack_from('<I', d, 10)
    w, h = struct.unpack_from('<ii', d, 18)
    px = np.frombuffer(d, np.uint8, offset=off, count=w * abs(h) * 4).reshape(abs(h), w, 4)
    return px if h < 0 else px[::-1]


def run_ff(args, data=None):
    return subprocess.run([FF, '-v', 'error', '-y'] + args, input=data, capture_output=True, check=True).stdout


def to_png(rgb, path):
    h, w = rgb.shape[:2]
    run_ff(['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (w, h), '-i', '-', path], rgb.tobytes())


def from_png(path, w, h, fmt='rgb24'):
    raw = run_ff(['-i', path, '-vf', 'scale=%d:%d:flags=lanczos' % (w, h), '-f', 'rawvideo', '-pix_fmt', fmt, '-'])
    return np.frombuffer(raw, np.uint8).reshape(h, w, -1)


def lanczos(plane, w, h, fmt):
    """A plane (rgb24 or gray) scaled to w x h by ffmpeg's Lanczos."""
    ih, iw = plane.shape[:2]
    raw = run_ff(['-f', 'rawvideo', '-pix_fmt', fmt, '-s', '%dx%d' % (iw, ih), '-i', '-', '-vf', 'scale=%d:%d:flags=lanczos' % (w, h),
                  '-f', 'rawvideo', '-pix_fmt', fmt, '-'], plane.tobytes())
    return np.frombuffer(raw, np.uint8).reshape(h, w, -1)


def bilinear(a, s):
    """a (h x w x c, float) s times bigger, bilinear, held at the edges."""
    h, w = a.shape[:2]
    def axis(n):
        t = (np.arange(n * s) + 0.5) / s - 0.5
        i = np.clip(np.floor(t).astype(int), 0, n - 1)
        return i, np.minimum(i + 1, n - 1), np.clip(t - i, 0, 1)
    y0, y1, fy = axis(h)
    x0, x1, fx = axis(w)
    fy, fx = fy[:, None, None], fx[None, :, None]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def keep_colour(up, orig, s):
    """The upscaler's detail on the original's colour: up (s times orig's size) shifted so that each
    s x s block averages to the original texel again. Real-ESRGAN smooths the speckle out of noisy
    surfaces (asphalt, grass, concrete) and they came out up to 20 levels darker."""
    h, w = orig.shape[:2]
    up = up.astype(np.float32)
    low = up.reshape(h, s, w, s, 3).mean((1, 3))
    return np.clip(up + bilinear(orig.astype(np.float32) - low, s) + 0.5, 0, 255).astype(np.uint8)


def write_hd(path, bgra):
    h, w = bgra.shape[:2]
    with open(path + '.part', 'wb') as f:
        f.write(struct.pack('<4sII', b'XHD1', w, h))
        f.write(np.ascontiguousarray(bgra).tobytes())
    os.replace(path + '.part', path)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('export'), ap.add_argument('pack')
    ap.add_argument('--upscaler'), ap.add_argument('--model', default='realesrgan-x4plus')
    ap.add_argument('--scale', type=int, default=4, choices=(2, 4))
    ap.add_argument('--max-out', type=int, default=1024)
    ap.add_argument('--skip-sizes', default='')
    ap.add_argument('--max-clear', type=float, default=0.9)
    ap.add_argument('--min', type=int, default=32), ap.add_argument('--max', type=int, default=1024)
    a = ap.parse_args(argv)
    os.makedirs(a.pack, exist_ok=True)
    todo = []
    for name in sorted(os.listdir(a.export)):
        if not name.lower().endswith('.bmp') or len(name) != 20: continue
        key = name[:16]
        if os.path.exists(os.path.join(a.pack, key + '.hd')): continue
        px = read_bmp(os.path.join(a.export, name))
        h, w = px.shape[:2]
        if min(w, h) < a.min or max(w, h) > a.max or '%dx%d' % (w, h) in a.skip_sizes.split(','): continue
        if max(w, h) * 2 > a.max_out: continue
        if np.ptp(px[..., :3].reshape(-1, 3), 0).max() < 6: continue  # one colour: nothing to sharpen
        if (px[..., 3] == 0).mean() >= a.max_clear: continue  # nearly all clear: the text's glyph sheets
        todo.append((key, px))
    print('%d textures to upscale (%s)' % (len(todo), 'Real-ESRGAN %s' % a.model if a.upscaler else 'Lanczos: no upscaler given'))
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, 'in'), os.path.join(tmp, 'out')
        os.makedirs(src), os.makedirs(dst)
        for key, px in todo:  # the colour, RGB
            to_png(np.ascontiguousarray(px[..., [2, 1, 0]]), os.path.join(src, key + '.png'))
        if a.upscaler and todo:
            subprocess.run([a.upscaler, '-i', src, '-o', dst, '-n', a.model, '-s', '4', '-f', 'png'], check=True,
                           cwd=os.path.dirname(os.path.abspath(a.upscaler)))
        for n, (key, px) in enumerate(todo):
            h, w = px.shape[:2]
            s = a.scale if max(w, h) * a.scale <= a.max_out else 2
            W, H = w * s, h * s
            out = os.path.join(dst, key + '.png')
            rgb = from_png(out, W, H) if a.upscaler and os.path.exists(out) else lanczos(np.ascontiguousarray(px[..., [2, 1, 0]]), W, H, 'rgb24')
            rgb = keep_colour(rgb, px[..., [2, 1, 0]], s)
            alpha = px[..., 3]
            al = np.full((H, W, 1), 255, np.uint8) if alpha.min() == 255 else lanczos(np.ascontiguousarray(alpha), W, H, 'gray')
            write_hd(os.path.join(a.pack, key + '.hd'), np.concatenate([rgb[..., [2, 1, 0]], al], -1))
            if n % 100 == 99: print('  %d of %d' % (n + 1, len(todo)))
    print('pack: %s (%d files)' % (a.pack, len([f for f in os.listdir(a.pack) if f.endswith('.hd')])))


if __name__ == '__main__':
    main(sys.argv[1:])
