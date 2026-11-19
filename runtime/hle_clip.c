/* A track's preview clip of our own (the user's, 11 Nov 2026: Fuji Speedway's event preview showed Road
 * Atlanta's fly-through). The game plays media\tracks\<track>\Flythrough.bik (the path made at 0x3117E4 into the
 * track record +0x76C) with its own Bink code, and nothing here writes Bink video. So the frames are swapped
 * after the decode: when the game opens a .bik with a file of the same name ending .clip beside it (a mod's:
 * tools/makeclip.py writes it), every frame Bink copies out (BinkCopyToBuffer, 0x3ACA10: bink, dest, pitch,
 * height, x, y, flags; the game's one call of it is 0x3A920C, into a locked texture) is painted over with the
 * clip's frame of that number. The .bik beside it stays as the clock: its size, frame count and rate are what
 * the game plays (the disc's fly-throughs: 486 x 364, 900 frames at 29.97 a second).
 *
 * The .clip file: "FZCL", u32 width, height, frames, repeat (Bink frames a clip frame is shown for), then
 * frames + 1 u32 offsets from the file's start, then each frame a zlib stream of width x height RGB565,
 * top row first. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#include "rt.h"

static struct {
    char path[1200];
    uint8_t *file;
    size_t size;
    uint32_t w, h, n, repeat;
    const uint32_t *off;
    uint16_t *px;   /* the frame decoded last */
    int have;       /* its number, -1 none */
} clip;
static int clip_on; /* the .bik opened last has a clip */

/* file.c: the game opens a .bik (its host path) */
void rt_clip_opened(const char *host) {
    char p[1200];
    size_t l = strlen(host);
    clip_on = 0;
    if (l < 5 || l + 2 > sizeof p) return;
    snprintf(p, sizeof p, "%.*s.clip", (int)(l - 4), host);
    if (clip.file && !strcasecmp(p, clip.path)) { clip_on = 1; return; }
    FILE *f = fopen(p, "rb");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *d = size > 20 ? malloc((size_t)size) : NULL;
    if (!d || fread(d, 1, (size_t)size, f) != (size_t)size) { fclose(f); free(d); return; }
    fclose(f);
    uint32_t hd[5];
    memcpy(hd, d, sizeof hd);
    if (memcmp(d, "FZCL", 4) || !hd[1] || !hd[2] || !hd[3] || hd[1] > 2048 || hd[2] > 2048 ||
        20 + 4 * ((uint64_t)hd[3] + 1) > (uint64_t)size) {
        fprintf(stderr, "xbrt: clip %s: not a clip file\n", p);
        free(d);
        return;
    }
    free(clip.file), free(clip.px);
    clip.file = d, clip.size = (size_t)size, clip.w = hd[1], clip.h = hd[2], clip.n = hd[3], clip.repeat = hd[4] ? hd[4] : 1;
    clip.off = (const uint32_t *)(d + 20);
    clip.px = malloc((size_t)clip.w * clip.h * 2);
    clip.have = -1;
    snprintf(clip.path, sizeof clip.path, "%s", p);
    clip_on = clip.px != NULL;
    fprintf(stderr, "xbrt: clip: %s (%u x %u, %u frames, each for %u of the movie's)\n", p, clip.w, clip.h, clip.n, clip.repeat);
}

static int clip_frame(uint32_t k) {
    if ((int)k == clip.have) return 1;
    uint32_t a = clip.off[k], b = clip.off[k + 1];
    if (a >= b || b > clip.size) return 0;
    size_t used;
    if (rt_inflate(clip.file + a, b - a, (uint8_t *)clip.px, (size_t)clip.w * clip.h * 2, &used) != (long)((size_t)clip.w * clip.h * 2)) return 0;
    clip.have = (int)k;
    return 1;
}

void orig_f_003ACA10(XbCtx *c); /* BinkCopyToBuffer (wraps.txt) */
void f_003ACA10(XbCtx *c) {
    uint32_t bink = xb_rd32(c->esp + 4), dest = xb_rd32(c->esp + 8), pitch = xb_rd32(c->esp + 12), dh = xb_rd32(c->esp + 16);
    uint32_t dx = xb_rd32(c->esp + 20), dy = xb_rd32(c->esp + 24), flags = xb_rd32(c->esp + 28);
    orig_f_003ACA10(c);
    if (!clip_on || !bink || !dest) return;
    uint32_t bw = xb_rd32(bink), bh = xb_rd32(bink + 4), frame = xb_rd32(bink + 12), type = flags & 15;
    static int said;
    if (!said) said = 1, fprintf(stderr, "xbrt: clip: the movie %u x %u, frame %u, into a surface of kind %u (pitch %u, height %u, at %u, %u)\n", bw, bh, frame, type, pitch, dh, dx, dy);
    if (!bw || !bh || bw > 2048 || bh > 2048 || dx || dy) return;
    /* Bink's surfaces: 3 and 5 32 bits B G R (A), 4 and 6 R G B (A), 7 4444, 8 5551, 10 565 */
    int bytes = type >= 3 && type <= 6 ? 4 : type == 7 || type == 8 || type == 10 ? 2 : 0;
    if (!bytes || pitch < bw * (uint32_t)bytes) return;
    if (!clip_frame(((frame ? frame - 1 : 0) / clip.repeat) % clip.n)) return;
    if (bh > dh) bh = dh;
    uint8_t *out = xb_mem + dest;
    for (uint32_t y = 0; y < bh; y++) {
        /* (bilinear: the clip is stored smaller than the movie) */
        uint32_t fy = (uint32_t)(((uint64_t)y * (clip.h - 1) << 8) / (bh > 1 ? bh - 1 : 1)), y0 = fy >> 8, wy = fy & 255, y1 = y0 + 1 < clip.h ? y0 + 1 : y0;
        const uint16_t *r0 = clip.px + (size_t)y0 * clip.w, *r1 = clip.px + (size_t)y1 * clip.w;
        uint8_t *row = out + (size_t)y * pitch;
        for (uint32_t x = 0; x < bw; x++) {
            uint32_t fx = (uint32_t)(((uint64_t)x * (clip.w - 1) << 8) / (bw > 1 ? bw - 1 : 1)), x0 = fx >> 8, wx = fx & 255, x1 = x0 + 1 < clip.w ? x0 + 1 : x0;
            uint32_t p[4] = {r0[x0], r0[x1], r1[x0], r1[x1]}, w[4] = {(256 - wx) * (256 - wy), wx * (256 - wy), (256 - wx) * wy, wx * wy};
            uint32_t r = 0, g = 0, b = 0;
            for (int i = 0; i < 4; i++) r += (p[i] >> 11) * w[i], g += ((p[i] >> 5) & 63) * w[i], b += (p[i] & 31) * w[i];
            r >>= 16, g >>= 16, b >>= 16; /* 5, 6, 5 bits */
            if (bytes == 4) {
                uint8_t R = (uint8_t)(r << 3 | r >> 2), G = (uint8_t)(g << 2 | g >> 4), B = (uint8_t)(b << 3 | b >> 2);
                uint8_t *q = row + 4 * x;
                if (type == 4 || type == 6) q[0] = R, q[1] = G, q[2] = B; else q[0] = B, q[1] = G, q[2] = R;
                q[3] = 255;
            } else {
                uint16_t v = type == 10 ? (uint16_t)(r << 11 | g << 5 | b) : type == 8 ? (uint16_t)(0x8000 | r << 10 | (g >> 1) << 5 | b)
                                                                             : (uint16_t)(0xF000 | (r >> 1) << 8 | (g >> 2) << 4 | b >> 1);
                memcpy(row + 2 * x, &v, 2);
            }
        }
    }
}
