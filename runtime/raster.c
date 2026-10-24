/* Drawing Kelvin primitives in software: enough of the NV2A's 3D engine
 * for Forza's front end, which is screen-space quads with one texture,
 * vertex colours and alpha blending, plus D3D's own passes (the
 * anti-aliased back buffer is downsampled into the displayed buffer by
 * drawing it as a texture).
 *
 * The pipeline, as xemu has it (hw/xbox/nv2a/pgraph):
 *   vertices  inline (SET_VERTEX*, SET_VERTEX_DATA*: writing attribute 0,
 *             the position, completes a vertex), INLINE_ARRAY, or vertex
 *             arrays (DRAW_ARRAYS, ARRAY_ELEMENT16/32) in the array formats.
 *   transform fixed function: position times the composite matrix,
 *             divided by w, plus the viewport offset; or a vertex program,
 *             interpreted, whose oPos is already in screen coordinates (D3D's
 *             programs scale by c58 and offset by c59, the viewport, which
 *             the fixed-function methods load into the transform constants).
 *             Either way the result is in pixels, which an anti-aliased
 *             surface multiplies into samples. No lighting or texgen yet.
 *   texture   four stages, each off, sampling a texture (swizzled and
 *             linear formats, 32 and 16 bit, 8-bit palettes, DXT1/3/5; point
 *             sampling, wrap or clamp; cube maps; 3D textures read as 2D) or
 *             passing its texture coordinate through as a colour (Forza's
 *             text uses that to pick a channel of its glyph cache). Linear
 *             (LU_IMAGE) textures take texel coordinates, the rest 0..1.
 *   colour    the register combiners (general stages and the final
 *             combiner) over T0-T3; alpha test; blending; colour write mask.
 *   depth     Z16 and Z24S8 buffers: test, write mask, clears (kelvin.c).
 *             z is interpolated linearly on screen; colours and texture
 *             coordinates perspective-correctly, through 1/w. No stencil.
 *   surface   linear colour buffers, 32 or 16 bit.
 *
 * XBRT_TEX_DUMP=<folder> saves every texture as it is decoded, and log
 * level 2 lists each new combination of pixel state once.
 */
#include <math.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "rt.h"
#include "nv2a.h"
#include "gl.h"
#undef DrawState /* windows.h, through the GL headers, defines it */

#define K(m) nv2a.kelvin[(m) / 4]

#define SET_CONTEXT_DMA_A 0x0184
#define SET_CONTEXT_DMA_B 0x0188
#define SET_CONTEXT_DMA_COLOR 0x0194
#define SET_CONTEXT_DMA_VERTEX_A 0x019C
#define SET_CONTEXT_DMA_VERTEX_B 0x01A0
#define SET_SURFACE_CLIP_HORIZONTAL 0x0200
#define SET_SURFACE_CLIP_VERTICAL 0x0204
#define SET_SURFACE_FORMAT 0x0208
#define SET_SURFACE_PITCH 0x020C
#define SET_SURFACE_COLOR_OFFSET 0x0210
#define SET_SURFACE_ZETA_OFFSET 0x0214
#define SET_CONTEXT_DMA_ZETA 0x0198
#define SET_DEPTH_TEST_ENABLE 0x030C
#define SET_DEPTH_FUNC 0x0354
#define SET_DEPTH_MASK 0x035C
#define SET_SHADOW_DEPTH_FUNC 0x1E6C
#define SET_FOG_MODE 0x029C
#define SET_FOG_ENABLE 0x02A4
#define SET_FOG_COLOR 0x02A8
#define SET_FOG_PARAMS 0x09C0
#define SET_ALPHA_TEST_ENABLE 0x0300
#define SET_BLEND_ENABLE 0x0304
#define SET_ALPHA_FUNC 0x033C
#define SET_ALPHA_REF 0x0340
#define SET_BLEND_FUNC_SFACTOR 0x0344
#define SET_BLEND_FUNC_DFACTOR 0x0348
#define SET_BLEND_COLOR 0x034C
#define SET_BLEND_EQUATION 0x0350
#define SET_COLOR_MASK 0x0358
#define SET_COMPOSITE_MATRIX 0x0680
#define SET_VIEWPORT_OFFSET 0x0A20
#define SET_VERTEX3F 0x1500
#define SET_VERTEX4F 0x1518
#define SET_VERTEX_DATA_ARRAY_OFFSET 0x1720
#define SET_VERTEX_DATA_ARRAY_FORMAT 0x1760
#define SET_BEGIN_END 0x17FC
#define ARRAY_ELEMENT16 0x1800
#define ARRAY_ELEMENT32 0x1808
#define DRAW_ARRAYS 0x1810
#define INLINE_ARRAY 0x1818
#define SET_VERTEX_DATA2F_M 0x1880
#define SET_VERTEX_DATA2S 0x1900
#define SET_VERTEX_DATA4UB 0x1940
#define SET_VERTEX_DATA4S_M 0x1980
#define SET_VERTEX_DATA4F_M 0x1A00
#define SET_TEXTURE_OFFSET 0x1B00
#define SET_TEXTURE_FORMAT 0x1B04
#define SET_TEXTURE_ADDRESS 0x1B08
#define SET_TEXTURE_CONTROL0 0x1B0C
#define SET_TEXTURE_CONTROL1 0x1B10
#define SET_TEXTURE_FILTER 0x1B14
#define SET_TEXTURE_IMAGE_RECT 0x1B1C
#define SET_TEXTURE_PALETTE 0x1B20
#define SET_TRANSFORM_EXECUTION_MODE 0x1E94

#define KT(m) K((m) + 0x40 * (uint32_t)(i)) /* texture stage i's copy of a texture method */

enum { ATTR_POS = 0, ATTR_DIFFUSE = 3, ATTR_TEX0 = 9, NATTR = 16 };

typedef struct {
    float a[NATTR][4];
} Vertex;

static Vertex cur;            /* the inline attribute values */
static Vertex *verts;          /* the primitive being collected */
static int nverts, prim;      /* prim: SET_BEGIN_END op, 0 outside Begin/End */
static uint32_t *inline_buf;  /* INLINE_ARRAY words of this Begin/End */
static int ninline;
static int verts_cap, inline_cap;

/* The next vertex of the primitive, starting from the inline values. Both
 * buffers grow: with 4096 vertices (and 4096 inline words) the rest of a
 * bigger draw was dropped. */
static Vertex *vert_new(void) {
    if (nverts == verts_cap) verts_cap = verts_cap ? verts_cap * 2 : 4096, verts = realloc(verts, (size_t)verts_cap * sizeof *verts);
    verts[nverts] = cur;
    return &verts[nverts++];
}

static inline uint8_t *phys(uint32_t pa) { return xb_mem + RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)); }
static inline float f32(uint32_t v) { float f; memcpy(&f, &v, 4); return f; }

static uint32_t dma_base(uint32_t handle_method) {
    uint32_t b = nv2a_dma_base(nv2a_lookup(K(handle_method)), NULL);
    return b == ~0u ? 0 : b;
}

/* ---- textures ---- */

typedef struct {
    uint32_t key[5]; /* offset, format, control1, image rect, palette */
    uint64_t hash;   /* of the bytes it was decoded from */
    uint32_t gen;    /* the generation it was last known good in */
    int w, h, linear;
    int cube;         /* six faces, one after another in texels */
    int levels;       /* mipmap levels decoded: each face is level 0, then 1, ... */
    size_t face_texels; /* texels in one face, all its levels */
    uint32_t depth;   /* a depth texture: texels hold depth, up to this maximum */
    uint32_t *texels; /* A8R8G8B8 */
    uint32_t version; /* bumped at each decode */
    GLuint gl;        /* its GL texture, made from version gl_version */
    uint32_t gl_version;
    int surface;      /* gl is a framebuffer's colour texture (glfill.c), sampled where it was drawn */
    int alpha_one;    /* ... of an X8R8G8B8 texture: alpha reads as one */
    uint64_t sig;     /* hash_sparse of its bytes when last fully hashed */
    uint32_t sig_checks; /* checks since the last full hash */
    uint32_t zaddr;   /* a shadow map sampled on the GPU: its depth's address (glvsh.c's shadow-matrix forwarding) */
} Texture;

static Texture cache[512]; /* a race frame uses a few hundred textures */
static Texture *gl_rt_texture(int i, uint32_t base, uint32_t pitch, uint32_t color, int w, int h);
static uint32_t draw_lo, draw_hi; /* the draw's colour buffer, which its textures must not be read from on the GPU */
static uint32_t draw_zlo, draw_zhi; /* ... and its depth buffer */
static int gl_rt_depth = -1;        /* sample shadow maps from their framebuffer, not through RAM (XBRT_GL_RT_DEPTH=0: through RAM) */
static int batch_writes(uint32_t base, uint32_t size); /* would the pending batch draw into these bytes? */
static void gl_sync_range(uint32_t base, uint32_t size);
static void gl_present_vblank(uint32_t fb);
static void gl_present_poll(int wait);
static Texture *gl_rt_swizzled(int i, uint32_t base, uint32_t color, int w, int h, int cube);
static uint32_t gl_sync_fmt; /* the texture format behind a gl_sync_range, for XBRT_GL_SYNC_LOG */
static void gl_sync_cpu(void);
static void gl_sync_color_async(uint32_t base, uint32_t size);
static void gl_flip(void);
static void gl_complete(void);
static int cache_next;
static uint32_t generation; /* bumped when render targets may have changed what textures hold */

void nv2a_raster_invalidate(void) {
    nv2a_raster_flush(); /* what was drawn before may be a texture now (on the GPU, texture() reads back what it needs) */
    generation++;
}

/* Whether bytes changed since they were last seen, for textures and
 * surfaces: four independent lanes of multiply and fold, combined at the
 * end. One lane is a chain of dependent multiplies; four keep the
 * multiplier busy, several times the speed over the megabytes a frame
 * checks. */
/* A sparse signature: 64 bytes of every 2 KB (and the tail). Checking it
 * each frame and the whole every 32nd time (sig_full) costs a 32nd of
 * hashing everything: re-hashing every texture and framebuffer each frame
 * was a third of the device thread at the race start, which fell to 45 fps. */
static uint64_t hash_bytes(const uint8_t *p, uint32_t n);
static uint64_t hash_sparse(const uint8_t *p, uint32_t n) {
    if (n <= 4096) return hash_bytes(p, n);
    uint64_t h = 0x9E3779B97F4A7C15ull ^ n;
    for (uint32_t k = 0; k + 64 <= n; k += 2048) h = (h ^ hash_bytes(p + k + 1024, k + 1088 <= n ? 64 : 0)) * 0x100000001B3ull ^ hash_bytes(p + k, 64);
    return h ^ hash_bytes(p + n - 64, 64);
}

static uint64_t hash_bytes(const uint8_t *p, uint32_t n) {
    uint64_t h[4] = {0x9E3779B97F4A7C15ull ^ n, 0xC2B2AE3D27D4EB4Full, 0x165667B19E3779F9ull, 0x27D4EB2F165667C5ull};
    uint32_t k = 0;
    for (; k + 32 <= n; k += 32)
        for (int j = 0; j < 4; j++) {
            uint64_t v;
            memcpy(&v, p + k + 8 * j, 8);
            h[j] = (h[j] ^ v) * 0x100000001B3ull;
            h[j] ^= h[j] >> 29;
        }
    uint64_t r = h[0] ^ (h[1] * 3) ^ (h[2] * 5) ^ (h[3] * 7);
    for (; k < n; k++) r = (r ^ p[k]) * 0x100000001B3ull;
    return r;
}

/* Morton order, as the NV2A swizzles: bits of x and y interleaved, x first,
 * until the smaller dimension runs out. */
static uint32_t swizzle3(uint32_t x, uint32_t y, uint32_t z, int w, int h, int d);
static uint32_t swizzle(uint32_t x, uint32_t y, int w, int h) {
    uint32_t r = 0, bit = 0;
    for (int s = 1; s < w || s < h; s <<= 1) {
        if (s < w) r |= ((x & s) ? 1u : 0u) << bit++;
        if (s < h) r |= ((y & s) ? 1u : 0u) << bit++;
    }
    return r;
}

/* ... and of a volume texture: x, y and z bits in turn. */
static uint32_t swizzle3(uint32_t x, uint32_t y, uint32_t z, int w, int h, int d) {
    uint32_t r = 0, bit = 0;
    for (int s = 1; s < w || s < h || s < d; s <<= 1) {
        if (s < w) r |= ((x & s) ? 1u : 0u) << bit++;
        if (s < h) r |= ((y & s) ? 1u : 0u) << bit++;
        if (s < d) r |= ((z & s) ? 1u : 0u) << bit++;
    }
    return r;
}

static uint32_t rgb565(uint16_t p, uint32_t a) {
    return a << 24 | (uint32_t)((p >> 11) * 255 / 31) << 16 | (uint32_t)(((p >> 5) & 63) * 255 / 63) << 8 | (uint32_t)((p & 31) * 255 / 31);
}

static void dxt_block(const uint8_t *b, int kind, uint32_t out[16]) {
    const uint8_t *cb = kind == 1 ? b : b + 8;
    uint16_t c0 = (uint16_t)(cb[0] | cb[1] << 8), c1 = (uint16_t)(cb[2] | cb[3] << 8);
    uint32_t col[4];
    col[0] = rgb565(c0, 0), col[1] = rgb565(c1, 0);
    for (int i = 0; i < 2; i++) {
        uint32_t a = col[0], b2 = col[1];
        int r0 = a >> 16 & 255, g0 = a >> 8 & 255, b0 = a & 255, r1 = b2 >> 16 & 255, g1 = b2 >> 8 & 255, bb1 = b2 & 255;
        if (kind != 1 || c0 > c1) {
            int w0 = i == 0 ? 2 : 1, w1 = 3 - w0;
            col[2 + i] = (uint32_t)((r0 * w0 + r1 * w1) / 3) << 16 | (uint32_t)((g0 * w0 + g1 * w1) / 3) << 8 | (uint32_t)((b0 * w0 + bb1 * w1) / 3);
        } else {
            col[2 + i] = i == 0 ? (uint32_t)((r0 + r1) / 2) << 16 | (uint32_t)((g0 + g1) / 2) << 8 | (uint32_t)((b0 + bb1) / 2) : 0;
        }
    }
    uint32_t idx = (uint32_t)(cb[4] | cb[5] << 8 | cb[6] << 16 | (uint32_t)cb[7] << 24);
    for (int i = 0; i < 16; i++) {
        int k = (idx >> (2 * i)) & 3;
        uint32_t a = 255;
        if (kind == 1) a = (c0 <= c1 && k == 3) ? 0 : 255;
        out[i] = col[k] | a << 24;
    }
    if (kind == 3) { /* explicit 4-bit alpha */
        for (int i = 0; i < 16; i++) {
            uint32_t a = (b[i / 2] >> ((i & 1) * 4)) & 15;
            out[i] = (out[i] & 0xFFFFFF) | (a * 17) << 24;
        }
    } else if (kind == 5) { /* interpolated alpha */
        uint32_t a[8];
        a[0] = b[0], a[1] = b[1];
        for (int i = 1; i < 7; i++) a[i + 1] = a[0] > a[1] ? ((7 - i) * a[0] + i * a[1]) / 7 : 0;
        if (a[0] <= a[1]) {
            for (int i = 1; i < 5; i++) a[i + 1] = ((5 - i) * a[0] + i * a[1]) / 5;
            a[6] = 0, a[7] = 255;
        }
        uint64_t bits = 0;
        for (int i = 0; i < 6; i++) bits |= (uint64_t)b[2 + i] << (8 * i);
        for (int i = 0; i < 16; i++) out[i] = (out[i] & 0xFFFFFF) | a[(bits >> (3 * i)) & 7] << 24;
    }
}

/* XBRT_TEX_DUMP=<folder>: every texture decoded, as a 32-bit BMP with alpha. */
static void dump_texture(const Texture *t, uint32_t offset, uint32_t fmt) {
    static const char *dir;
    static int checked, count;
    static double from;
    if (!checked) checked = 1, dir = getenv("XBRT_TEX_DUMP"), from = getenv("XBRT_TEX_DUMP_FROM") ? atof(getenv("XBRT_TEX_DUMP_FROM")) : 0;
    if (!dir || !*dir || count >= 2000) return;
    if (t->w * t->h < 64 || rt_now_100ns() / 1e7 < from) return; /* XBRT_TEX_DUMP_FROM=<seconds>; not the 1x1 colours */
    char path[1024];
    snprintf(path, sizeof path, "%s/tex_%04d_%08x_%08x_%dx%d.bmp", dir, count++, offset, fmt, t->w, t->h);
    FILE *f = fopen(path, "wb");
    if (!f) return;
    uint8_t h[54] = {'B', 'M'};
    uint32_t size = 54 + (uint32_t)t->w * t->h * 4;
    uint32_t vals[] = {size, 0, 54, 40, (uint32_t)t->w, (uint32_t)-t->h};
    memcpy(h + 2, &vals[0], 4), memcpy(h + 10, &vals[2], 4), memcpy(h + 14, &vals[3], 4), memcpy(h + 18, &vals[4], 4), memcpy(h + 22, &vals[5], 4);
    h[26] = 1, h[28] = 32;
    fwrite(h, 1, 54, f);
    fwrite(t->texels, 4, (size_t)t->w * t->h, f);
    fclose(f);
}

/* Stage i's texture, decoded to A8R8G8B8 (cached until the next flip). */
static Texture *texture(int i) {
    uint32_t fmt = KT(SET_TEXTURE_FORMAT), color = (fmt >> 8) & 0xFF;
    if (rt_gl_on && (color == 0x12 || color == 0x1E || color == 0x11 || (color == 0x2E && gl_rt_depth))) { /* linear: perhaps a render target */
        Texture *rt = gl_rt_texture(i, dma_base((fmt & 3) == 2 ? SET_CONTEXT_DMA_B : SET_CONTEXT_DMA_A) + KT(SET_TEXTURE_OFFSET),
                                    KT(SET_TEXTURE_CONTROL1) >> 16, color, (int)(KT(SET_TEXTURE_IMAGE_RECT) >> 16),
                                    (int)(KT(SET_TEXTURE_IMAGE_RECT) & 0xFFFF));
        if (rt) return rt;
    }
    if (rt_gl_on && (color == 0x06 || color == 0x07) && ((fmt >> 16) & 15) == 1) { /* swizzled, one level: perhaps a render target */
        Texture *rt = gl_rt_swizzled(i, dma_base((fmt & 3) == 2 ? SET_CONTEXT_DMA_B : SET_CONTEXT_DMA_A) + KT(SET_TEXTURE_OFFSET), color,
                                     1 << ((fmt >> 20) & 15), 1 << ((fmt >> 24) & 15), (int)((fmt >> 2) & 1));
        if (rt) return rt;
    }
    uint32_t key[5] = {KT(SET_TEXTURE_OFFSET), fmt, KT(SET_TEXTURE_CONTROL1), KT(SET_TEXTURE_IMAGE_RECT), KT(SET_TEXTURE_PALETTE)};
    Texture *hit = NULL;
    for (int i = 0; i < 512 && !hit; i++)
        if (cache[i].texels && !memcmp(cache[i].key, key, sizeof key)) hit = &cache[i];
    if (hit && hit->gen == generation) return hit;

    int linear = (color >= 0x10 && color <= 0x20) || color == 0x24 || color == 0x25 || color >= 0x2E;
    int w, h;
    if (linear) {
        w = (int)(KT(SET_TEXTURE_IMAGE_RECT) >> 16), h = (int)(KT(SET_TEXTURE_IMAGE_RECT) & 0xFFFF);
    } else {
        w = 1 << ((fmt >> 20) & 15), h = 1 << ((fmt >> 24) & 15);
    }
    if (w <= 0 || h <= 0 || w > 4096 || h > 4096) return NULL;
    uint32_t base = dma_base((fmt & 3) == 2 ? SET_CONTEXT_DMA_B : SET_CONTEXT_DMA_A) + KT(SET_TEXTURE_OFFSET);
    uint32_t pitch = KT(SET_TEXTURE_CONTROL1) >> 16;
    /* A cube map holds six faces, each with its mipmap chain, rounded up to
     * 128 bytes (xemu: NV2A_CUBEFACE_ALIGNMENT). */
    int cube = (fmt >> 2) & 1, faces = cube ? 6 : 1, levels = (int)((fmt >> 16) & 15);
    int dxt = color >= 0x0C && color <= 0x0F, dxt_bytes = color == 0x0C ? 8 : 16;
    /* A volume texture (dimensionality 3, depth in bits 28-31): Forza's car
     * bodies and lights have two slices. Only slice 0 is decoded and
     * sampled as 2D. DXT volumes keep the slices of each 4x4 block together,
     * up to four at a time (as xemu decodes them); decoded as 2D they came
     * out in stripes and grids over the cars. */
    int depth = ((fmt >> 4) & 15) == 3 ? 1 << ((fmt >> 28) & 15) : 1;
    int bpp = (color == 0x06 || color == 0x07 || color == 0x12 || color == 0x1E) ? 4
              : (color == 0x0B || color == 0x00 || color == 0x13 || color == 0x19 || color == 0x1F) ? 1 : 2;
    uint32_t face_size = 0;
    for (int l = 0; l < (levels ? levels : 1); l++) {
        int lw = w >> l > 1 ? w >> l : 1, lh = h >> l > 1 ? h >> l : 1;
        int ld = depth >> l > 1 ? depth >> l : 1;
        face_size += (dxt ? (uint32_t)((lw + 3) / 4 * ((lh + 3) / 4) * dxt_bytes) : (uint32_t)(lw * lh * bpp)) * (uint32_t)ld;
    }
    face_size = (face_size + 127) & ~127u;
    if (base + (uint64_t)face_size * faces > (uint64_t)RT_PHYS_SIZE * 2 && !dxt && !linear) return NULL;

    /* Since the last surface change or flip the bytes may have changed (a
     * render target drawn to, or the CPU writing); a hash of them says
     * whether the decoded copy still holds. Re-decoding every texture after
     * every surface change cost a tenth of the frame. */
    uint32_t size = linear ? (pitch ? pitch : (uint32_t)w * (uint32_t)bpp) * (uint32_t)h : face_size * (uint32_t)faces;
    if (size > RT_PHYS_SIZE) size = RT_PHYS_SIZE;
    if (batch_writes(base, size)) nv2a_raster_flush(); /* draw into it first */
    if (rt_gl_on) gl_sync_fmt = fmt, gl_sync_range(base, size);              /* the GPU drew into it */
    uint64_t hash;
    extern uint64_t raster_t_hash, raster_hash_bytes;
    uint64_t th0 = rt_now_100ns();
    uint64_t quick_sig = 0;
    {
        const uint8_t *p = phys(base);
        uint32_t n = size;
        if (p + n > xb_mem + RT_PHYS_VIEW + RT_PHYS_SIZE) n = (uint32_t)(xb_mem + RT_PHYS_VIEW + RT_PHYS_SIZE - p);
        uint64_t sig = hash_sparse(p, n);
        if (hit && sig == hit->sig && ++hit->sig_checks % 32 != 0 && color != 0x0B) { /* very likely unchanged */
            raster_t_hash += rt_now_100ns() - th0;
            hit->gen = generation;
            return hit;
        }
        raster_hash_bytes += size;
        hash = hash_bytes(p, n) ^ size;
        if (hit) hit->sig = sig;
        quick_sig = sig;
        if (color == 0x0B) { /* the palette is part of what the texture looks like */
            uint32_t pl = KT(SET_TEXTURE_PALETTE);
            const uint8_t *pp = phys(dma_base((pl & 1) ? SET_CONTEXT_DMA_B : SET_CONTEXT_DMA_A) + (pl & ~63u));
            for (int j = 0; j < 1024; j += 8) {
                uint64_t v;
                memcpy(&v, pp + j, 8);
                hash = (hash ^ v) * 0x100000001B3ull;
            }
        }
    }
    raster_t_hash += rt_now_100ns() - th0;
    if (hit && hit->hash == hash) {
        hit->gen = generation;
        return hit;
    }
    extern uint64_t raster_t_decode, raster_n_decode;
    uint64_t td0 = rt_now_100ns();
    raster_n_decode++;
    nv2a_raster_flush(); /* batched triangles may point at the entry about to be replaced */
    Texture *t = hit;
    if (!t) {
        t = &cache[cache_next];
        cache_next = (cache_next + 1) % 512;
    }
    /* The GPU samples the game's own mipmaps; the software rasteriser only
     * reads level 0, so it does not decode the rest. Linear textures have
     * no mipmaps on the NV2A. */
    int nl = rt_gl_on && !linear && levels > 1 ? levels : 1;
    size_t face_texels = 0;
    for (int l = 0; l < nl; l++) face_texels += (size_t)(w >> l > 1 ? w >> l : 1) * (size_t)(h >> l > 1 ? h >> l : 1);
    free(t->texels);
    t->texels = malloc(face_texels * 4 * faces);
    memcpy(t->key, key, sizeof key);
    t->hash = hash, t->gen = generation, t->sig = quick_sig, t->sig_checks = 0;
    t->version++;
    t->w = w, t->h = h, t->linear = linear, t->cube = cube;
    t->levels = nl, t->face_texels = face_texels;
    t->depth = color == 0x2E ? 0xFFFFFF : color == 0x30 ? 0xFFFF : 0;
  for (int face = 0; face < faces; face++) {
   const uint8_t *fsrc = phys(base + (uint32_t)face * face_size);
   uint32_t *fo = t->texels + (size_t)face * face_texels;
   size_t soff = 0, ooff = 0;
   for (int l = 0; l < nl; l++) {
    /* The level's own size: w and h from here on are this level's. */
    int w = t->w >> l > 1 ? t->w >> l : 1, h = t->h >> l > 1 ? t->h >> l : 1;
    const uint8_t *src = fsrc + soff;
    uint32_t *o = fo + ooff;
    int ld = depth >> l > 1 ? depth >> l : 1; /* this level's slices */
    soff += (dxt ? (size_t)((w + 3) / 4 * ((h + 3) / 4) * dxt_bytes) : (size_t)w * h * bpp) * (size_t)ld;
    ooff += (size_t)w * h;

    uint32_t pal[256] = {0};
    if (color == 0x0B) {
        uint32_t p = KT(SET_TEXTURE_PALETTE);
        uint32_t pbase = dma_base((p & 1) ? SET_CONTEXT_DMA_B : SET_CONTEXT_DMA_A) + (p & ~63u);
        memcpy(pal, phys(pbase), sizeof pal);
    }
    if (color >= 0x0C && color <= 0x0F) { /* DXT: 4x4 blocks, linear */
        int kind = color == 0x0C ? 1 : color == 0x0E ? 3 : 5, bs = kind == 1 ? 8 : 16;
        uint32_t blk[16];
        for (int by = 0; by < (h + 3) / 4; by++)
            for (int bx = 0; bx < (w + 3) / 4; bx++) {
                dxt_block(src + ((size_t)by * ((w + 3) / 4) + bx) * (size_t)(ld < 4 ? ld : 4) * bs, kind, blk);
                for (int i = 0; i < 16; i++) {
                    int x = bx * 4 + i % 4, y = by * 4 + i / 4;
                    if (x < w && y < h) o[y * w + x] = blk[i];
                }
            }
        continue;
    }
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            uint32_t i = linear ? 0 : ld > 1 ? swizzle3((uint32_t)x, (uint32_t)y, 0, w, h, ld) : swizzle((uint32_t)x, (uint32_t)y, w, h);
            uint32_t v;
            switch (color) {
            case 0x06: case 0x07: case 0x12: case 0x1E: { /* 32-bit */
                const uint8_t *p = linear ? src + (size_t)y * pitch + (size_t)x * 4 : src + (size_t)i * 4;
                v = (uint32_t)(p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24);
                if (color == 0x07 || color == 0x1E) v |= 0xFF000000u;
                break;
            }
            case 0x05: case 0x11: case 0x02: case 0x03: case 0x10: case 0x1C: case 0x04: case 0x1D: { /* 16-bit */
                const uint8_t *p = linear ? src + (size_t)y * pitch + (size_t)x * 2 : src + (size_t)i * 2;
                uint16_t s = (uint16_t)(p[0] | p[1] << 8);
                if (color == 0x05 || color == 0x11) v = rgb565(s, 255);
                else if (color == 0x04 || color == 0x1D)
                    v = (uint32_t)((s >> 12) * 17) << 24 | (uint32_t)((s >> 8 & 15) * 17) << 16 | (uint32_t)((s >> 4 & 15) * 17) << 8 | (s & 15) * 17;
                else
                    v = (uint32_t)((s >> 15) || color == 0x03 || color == 0x1C ? 255 : 0) << 24 | (uint32_t)((s >> 10 & 31) * 255 / 31) << 16 |
                        (uint32_t)((s >> 5 & 31) * 255 / 31) << 8 | (uint32_t)((s & 31) * 255 / 31);
                break;
            }
            case 0x2E: { /* depth X8_Y24, linear: keep the 24 bits of depth */
                const uint8_t *p = src + (size_t)y * pitch + (size_t)x * 4;
                v = (uint32_t)(p[1] | p[2] << 8 | p[3] << 16);
                break;
            }
            case 0x30: { /* depth Y16, linear */
                const uint8_t *p = src + (size_t)y * pitch + (size_t)x * 2;
                v = (uint32_t)(p[0] | p[1] << 8);
                break;
            }
            case 0x0B: v = pal[src[i]]; break;
            case 0x00: case 0x13: { uint8_t y8 = linear ? src[(size_t)y * pitch + x] : src[i]; v = 0xFF000000u | y8 * 0x010101u; break; }
            case 0x19: case 0x1F: { uint8_t a8 = linear ? src[(size_t)y * pitch + x] : src[i]; v = (uint32_t)a8 << 24 | 0xFFFFFF; break; }
            case 0x1A: case 0x20: { const uint8_t *p = linear ? src + (size_t)y * pitch + (size_t)x * 2 : src + (size_t)i * 2; v = (uint32_t)p[1] << 24 | p[0] * 0x010101u; break; }
            default: { /* not decoded: magenta, and say so once per format */
                static uint8_t told[256];
                if (!told[color]) told[color] = 1, fprintf(stderr, "xbrt: texture format %02x (%08x, %dx%d) is not decoded\n", color, fmt, w, h);
                v = 0xFFFF00FFu;
            }
            }
            o[y * w + x] = v;
        }
   }
  }
    dump_texture(t, base, fmt);
    raster_t_decode += rt_now_100ns() - td0;
    return t;
}

/* A cube map: the major axis of (s, t, r) picks the face, as OpenGL does. */
static uint32_t sample_cube(const Texture *t, float s, float tt, float r) {
    float as = fabsf(s), at = fabsf(tt), ar = fabsf(r), sc, tc, ma;
    int face;
    if (as >= at && as >= ar) face = s >= 0 ? 0 : 1, sc = s >= 0 ? -r : r, tc = -tt, ma = as;
    else if (at >= ar) face = tt >= 0 ? 2 : 3, sc = s, tc = tt >= 0 ? r : -r, ma = at;
    else face = r >= 0 ? 4 : 5, sc = r >= 0 ? s : -s, tc = -tt, ma = ar;
    if (ma == 0) return 0;
    int x = (int)((sc / ma + 1) * 0.5f * (float)t->w), y = (int)((tc / ma + 1) * 0.5f * (float)t->h);
    x = x < 0 ? 0 : x >= t->w ? t->w - 1 : x;
    y = y < 0 ? 0 : y >= t->h ? t->h - 1 : y;
    return t->texels[(size_t)face * t->face_texels + (size_t)y * t->w + x];
}

static int wrap(int c, int n, int mode) {
    if (mode == 1 || mode == 0) { c %= n; return c < 0 ? c + n : c; } /* wrap */
    if (mode == 2) { int p = ((c % (2 * n)) + 2 * n) % (2 * n); return p < n ? p : 2 * n - 1 - p; } /* mirror */
    return c < 0 ? 0 : c >= n ? n - 1 : c; /* clamp */
}

static uint32_t sample(const Texture *t, int i, float s, float tt) {
    if (!t->linear) s *= (float)t->w, tt *= (float)t->h;
    uint32_t addr = KT(SET_TEXTURE_ADDRESS);
    int x = wrap((int)floorf(s), t->w, (int)(addr & 15)), y = wrap((int)floorf(tt), t->h, (int)((addr >> 8) & 15));
    return t->texels[y * t->w + x];
}

/* ---- vertex programs ----
 * 136 slots of 128-bit instructions and 192 vec4 constants, loaded through
 * SET_TRANSFORM_PROGRAM / SET_TRANSFORM_CONSTANT from the slot the _LOAD
 * methods set, four words per slot. Instruction fields as xemu decodes them
 * (pgraph/glsl/vsh-prog.c). A MAC and an ILU op may share an instruction:
 * both read their inputs first; the ILU then writes R1. R12 reads oPos. */

#define SET_TRANSFORM_PROGRAM 0x0B00
#define SET_TRANSFORM_CONSTANT 0x0B80
#define SET_TRANSFORM_PROGRAM_LOAD 0x1E9C
#define SET_TRANSFORM_PROGRAM_START 0x1EA0
#define SET_TRANSFORM_CONSTANT_LOAD 0x1EA4

static uint32_t program[136][4];
static uint32_t constants[192][4];
static uint32_t program_load, constant_load;

enum { O_POS = 0, O_D0 = 3, O_D1 = 4, O_FOG = 5, O_PTS = 6, O_B0 = 7, O_B1 = 8, O_T0 = 9 };

typedef struct {
    float o[16][4]; /* output registers, by the hardware's numbering */
} VshOut;

static uint32_t field(const uint32_t *t, int word, int bit, int len) { return (t[word] >> bit) & ((1u << len) - 1); }

static void write_masked(float dst[4], const float src[4], uint32_t mask) {
    for (int k = 0; k < 4; k++)
        if (mask & (8u >> k)) dst[k] = src[k];
}

/* The program decoded once per change, for the per-vertex loop: the same
 * fields as above, taken out of the instruction words ahead of time. Run
 * per vertex the bit fields cost more than the arithmetic. */
typedef struct {
    uint8_t mux, reg, neg, sel[4]; /* sel: the swizzle, component by component */
} VshIn;

typedef struct {
    uint8_t mac, ilu, final, attr, rel;
    int16_t c;
    VshIn in[3]; /* A, B, C */
    uint8_t out_reg, mac_mask, ilu_mask, o_mask, orb, o_mux;
    uint16_t o_addr;
} VshIns;

static VshIns vprog[136];
static uint32_t vprog_version, vprog_decoded = ~0u, vprog_start = ~0u; /* vprog_version: bumped by program uploads */

static void vsh_decode_in(const uint32_t *t, int mux, int reg, int neg, int swz_word, int swz_bit, int scalar, VshIn *d) {
    d->mux = (uint8_t)mux, d->reg = (uint8_t)reg, d->neg = (uint8_t)neg;
    for (int k = 0; k < 4; k++) d->sel[k] = (uint8_t)field(t, swz_word, swz_bit - 2 * (scalar ? 0 : k), 2);
}

/* Called before vertices are projected: the workers only read vprog. */
static void vsh_decode(void) {
    uint32_t start = K(SET_TRANSFORM_PROGRAM_START);
    if (vprog_decoded == vprog_version && vprog_start == start) return;
    for (uint32_t slot = start; slot < 136; slot++) {
        const uint32_t *t = program[slot];
        VshIns *d = &vprog[slot];
        d->mac = (uint8_t)field(t, 1, 21, 4), d->ilu = (uint8_t)field(t, 1, 25, 3);
        int ilu_scalar = d->ilu >= 2 && d->ilu <= 6;
        d->attr = (uint8_t)field(t, 1, 9, 4), d->c = (int16_t)field(t, 1, 13, 8), d->rel = (uint8_t)field(t, 3, 1, 1);
        vsh_decode_in(t, (int)field(t, 2, 26, 2), (int)field(t, 2, 28, 4), (int)field(t, 1, 8, 1), 1, 6, 0, &d->in[0]);
        vsh_decode_in(t, (int)field(t, 2, 11, 2), (int)field(t, 2, 13, 4), (int)field(t, 2, 25, 1), 2, 23, 0, &d->in[1]);
        vsh_decode_in(t, (int)field(t, 3, 28, 2), (int)(field(t, 2, 0, 2) << 2 | field(t, 3, 30, 2)), (int)field(t, 2, 10, 1), 2, 8,
                      ilu_scalar, &d->in[2]);
        d->out_reg = (uint8_t)field(t, 3, 20, 4), d->mac_mask = (uint8_t)field(t, 3, 24, 4), d->ilu_mask = (uint8_t)field(t, 3, 16, 4);
        d->o_mask = (uint8_t)field(t, 3, 12, 4), d->orb = (uint8_t)field(t, 3, 11, 1), d->o_addr = (uint16_t)field(t, 3, 3, 8);
        d->o_mux = (uint8_t)field(t, 3, 2, 1), d->final = (uint8_t)field(t, 3, 0, 1);
    }
    vprog_decoded = vprog_version, vprog_start = start;
}

static inline void vsh_in(const VshIns *ins, const VshIn *d, float r[13][4], const Vertex *in, const VshOut *out, int a0, float v[4]) {
    static const float zero[4];
    const float *s = zero;
    float c[4];
    if (d->mux == 1) {
        if (d->reg == 12) s = out->o[O_POS];
        else if (d->reg < 12) s = r[d->reg];
    } else if (d->mux == 2) {
        s = in->a[ins->attr];
    } else if (d->mux == 3) {
        int k = ins->c + (ins->rel ? a0 : 0);
        if (k >= 0 && k < 192) {
            for (int j = 0; j < 4; j++) c[j] = f32(constants[k][j]);
            s = c;
        }
    }
    if (d->neg)
        for (int k = 0; k < 4; k++) v[k] = -s[d->sel[k]];
    else
        for (int k = 0; k < 4; k++) v[k] = s[d->sel[k]];
}

static void run_program(const Vertex *in, VshOut *out) {
    float r[13][4] = {{0}};
    int a0 = 0;
    memset(out, 0, sizeof *out);
    out->o[O_D0][3] = out->o[O_D1][3] = 1;
    for (int i = 0; i < 4; i++) out->o[O_T0 + i][3] = 1;
    for (uint32_t slot = vprog_start; slot < 136; slot++) {
        const VshIns *ins = &vprog[slot];
        uint32_t mac = ins->mac, ilu = ins->ilu;
        float A[4], B[4], C[4], m[4] = {0}, l[4] = {0};
        vsh_in(ins, &ins->in[0], r, in, out, a0, A);
        vsh_in(ins, &ins->in[1], r, in, out, a0, B);
        vsh_in(ins, &ins->in[2], r, in, out, a0, C);
        switch (mac) {
        case 1: memcpy(m, A, sizeof m); break;
        case 2: for (int k = 0; k < 4; k++) m[k] = (A[k] == 0 || B[k] == 0) ? 0 : A[k] * B[k]; break;
        case 3: for (int k = 0; k < 4; k++) m[k] = A[k] + C[k]; break;
        case 4: for (int k = 0; k < 4; k++) m[k] = ((A[k] == 0 || B[k] == 0) ? 0 : A[k] * B[k]) + C[k]; break;
        case 5: m[0] = m[1] = m[2] = m[3] = A[0] * B[0] + A[1] * B[1] + A[2] * B[2]; break;
        case 6: m[0] = m[1] = m[2] = m[3] = A[0] * B[0] + A[1] * B[1] + A[2] * B[2] + B[3]; break;
        case 7: m[0] = m[1] = m[2] = m[3] = A[0] * B[0] + A[1] * B[1] + A[2] * B[2] + A[3] * B[3]; break;
        case 8: m[0] = 1, m[1] = A[1] * B[1], m[2] = A[2], m[3] = B[3]; break;
        case 9: for (int k = 0; k < 4; k++) m[k] = fminf(A[k], B[k]); break;
        case 10: for (int k = 0; k < 4; k++) m[k] = fmaxf(A[k], B[k]); break;
        case 11: for (int k = 0; k < 4; k++) m[k] = A[k] < B[k]; break;
        case 12: for (int k = 0; k < 4; k++) m[k] = A[k] >= B[k]; break;
        }
        float x = C[0];
        switch (ilu) {
        case 1: memcpy(l, C, sizeof l); break;
        case 2: l[0] = l[1] = l[2] = l[3] = 1.0f / x; break;
        case 3: { float v = 1.0f / x; if (fabsf(v) < 5.42101e-20f) v = v < 0 ? -5.42101e-20f : 5.42101e-20f;
                  if (fabsf(v) > 1.884467e+19f) v = v < 0 ? -1.884467e+19f : 1.884467e+19f;
                  l[0] = l[1] = l[2] = l[3] = v; break; }
        case 4: l[0] = l[1] = l[2] = l[3] = x == 0 ? INFINITY : 1.0f / sqrtf(fabsf(x)); break;
        case 5: l[0] = exp2f(floorf(x)), l[1] = x - floorf(x), l[2] = exp2f(x), l[3] = 1; break;
        case 6: { float a = fabsf(x);
                  if (a == 0) l[0] = l[2] = -INFINITY, l[1] = l[3] = 1;
                  else l[0] = floorf(log2f(a)), l[1] = a / exp2f(floorf(log2f(a))), l[2] = log2f(a), l[3] = 1;
                  break; }
        case 7: { float d = fmaxf(C[0], 0), s = fmaxf(C[1], 0), p = fminf(fmaxf(C[3], -127.9961f), 127.9961f);
                  l[0] = 1, l[1] = d, l[2] = d > 0 ? powf(s, p) : 0, l[3] = 1; break; }
        }

        uint32_t out_reg = ins->out_reg, mac_mask = ins->mac_mask, ilu_mask = ins->ilu_mask;
        uint32_t o_mask = ins->o_mask, orb = ins->orb, o_addr = ins->o_addr, o_mux = ins->o_mux;
        if (mac == 13) {
            a0 = (int)floorf(A[0] + 0.001f);
        } else if (mac) {
            if (!(ilu && out_reg == 1) && out_reg < 12) write_masked(r[out_reg], m, mac_mask);
            if (out_reg == 12) write_masked(out->o[O_POS], m, mac_mask);
        }
        if (ilu) {
            uint32_t reg = mac ? 1 : out_reg;
            if (reg < 12) write_masked(r[reg], l, ilu_mask);
            else if (reg == 12) write_masked(out->o[O_POS], l, ilu_mask);
        }
        if (o_mask && (mac || ilu)) {
            const float *v = o_mux ? l : m;
            if ((o_mux == 0 && mac && mac != 13) || (o_mux == 1 && ilu)) {
                if (orb == 1) write_masked(out->o[o_addr & 15], v, o_mask);
                else if (o_addr < 192)
                    for (int k = 0; k < 4; k++)
                        if (o_mask & (8u >> k)) memcpy(&constants[o_addr][k], &v[k], 4);
            }
        }
        if (ins->final) break;
    }
}

/* Program and constant uploads; called before the generic method handling. */
static int program_method(uint32_t method, uint32_t arg) {
    if (method >= SET_TRANSFORM_PROGRAM && method < SET_TRANSFORM_PROGRAM + 0x80) {
        uint32_t k = (method - SET_TRANSFORM_PROGRAM) / 4 % 4;
        if (program_load < 136) program[program_load][k] = arg;
        if (k == 3) program_load++;
        vprog_version++;
        return 1;
    }
    if (method >= SET_TRANSFORM_CONSTANT && method < SET_TRANSFORM_CONSTANT + 0x80) {
        uint32_t k = (method - SET_TRANSFORM_CONSTANT) / 4 % 4;
        if (constant_load < 192) constants[constant_load][k] = arg;
        if (k == 3) constant_load++;
        return 1;
    }
    /* Fixed-function state that lives in the transform constants (xemu's
     * XFCTX rows), where D3D's own programs read it: c58 viewport scale,
     * c59 viewport offset, and so on. Kelvin keeps its copy too. */
    static const struct { uint16_t method, size, row; } xfctx[] = {
        {0x0440, 0x040, 0x04}, /* projection matrix */
        {0x0480, 0x100, 0x08}, /* model view matrices, 8 rows apart */
        {0x0580, 0x100, 0x0C}, /* inverse model view matrices */
        {0x0680, 0x040, 0x00}, /* composite matrix */
        {0x06C0, 0x100, 0x44}, /* texture matrices */
        {0x0840, 0x100, 0x40}, /* texgen planes */
        {0x09D0, 0x010, 0x39}, /* fog plane */
        {0x0A20, 0x010, 0x3B}, /* viewport offset */
        {0x0A50, 0x010, 0x38}, /* eye position */
        {0x0AF0, 0x010, 0x3A}, /* viewport scale */
    };
    for (size_t i = 0; i < sizeof xfctx / sizeof xfctx[0]; i++) {
        if (method < xfctx[i].method || method >= xfctx[i].method + xfctx[i].size) continue;
        uint32_t slot = (method - xfctx[i].method) / 4, row = xfctx[i].row;
        row += xfctx[i].size == 0x100 ? slot / 16 * 8 + slot % 16 / 4 : slot / 4;
        constants[row][slot % 4] = arg;
        return 0;
    }
    if (method == SET_TRANSFORM_PROGRAM_LOAD) { program_load = arg; return 1; }
    if (method == SET_TRANSFORM_CONSTANT_LOAD) { constant_load = arg; return 1; }
    return 0;
}

/* ---- the pipeline ---- */

static float blend_factor(uint32_t f, int ch, const float s[4], const float d[4], const float c[4]) {
    switch (f) {
    case 0x0000: return 0;
    case 0x0001: return 1;
    case 0x0300: return s[ch];
    case 0x0301: return 1 - s[ch];
    case 0x0302: return s[3];
    case 0x0303: return 1 - s[3];
    case 0x0304: return d[3];
    case 0x0305: return 1 - d[3];
    case 0x0306: return d[ch];
    case 0x0307: return 1 - d[ch];
    case 0x0308: return ch == 3 ? 1 : fminf(s[3], 1 - d[3]);
    case 0x8001: return c[ch];
    case 0x8002: return 1 - c[ch];
    case 0x8003: return c[3];
    case 0x8004: return 1 - c[3];
    }
    return 1;
}

/* ---- register combiners ----
 * The pixel stage, as xemu reads it (pgraph/glsl/psh.c): up to eight
 * general stages, each computing A*B and C*D (or dot products) and their
 * sum or mux into a register, for RGB and alpha separately, then the final
 * combiner: rgb = A*B + (1-A)*C + D, alpha = G. Inputs are a register
 * (0 zero, 1/2 the stage constants, 3 fog, 4/5 the vertex colours, 8-11 the
 * textures, 12/13 R0/R1, 14 V1+R0, 15 E*F), a channel bit (0x10: alpha;
 * for alpha inputs, otherwise blue) and a mapping (bits 5-7). Only texture
 * stage 0 is sampled; T1-T3 read as zero. */
#define SET_COMBINER_ALPHA_ICW 0x0260
#define SET_COMBINER_SPECULAR_FOG_CW0 0x0288
#define SET_COMBINER_SPECULAR_FOG_CW1 0x028C
#define SET_COMBINER_FACTOR0 0x0A60
#define SET_COMBINER_FACTOR1 0x0A80
#define SET_COMBINER_ALPHA_OCW 0x0AA0
#define SET_COMBINER_COLOR_ICW 0x0AC0
#define SET_SPECULAR_FOG_FACTOR 0x1E20
#define SET_COMBINER_COLOR_OCW 0x1E40
#define SET_COMBINER_CONTROL 0x1E60
#define SET_SHADER_STAGE_PROGRAM 0x1E70

typedef struct {
    float r[16][4]; /* the registers, by number */
    float e[3], f[3];
} Comb;

static void argb(uint32_t v, float o[4]) {
    o[0] = (v >> 16 & 255) / 255.0f, o[1] = (v >> 8 & 255) / 255.0f, o[2] = (v & 255) / 255.0f, o[3] = (v >> 24) / 255.0f;
}

static float map_in(float x, uint32_t mode) {
    switch (mode >> 5) {
    case 0: return fmaxf(x, 0);
    case 1: return 1 - fminf(fmaxf(x, 0), 1);
    case 2: return 2 * fmaxf(x, 0) - 1;
    case 3: return 1 - 2 * fmaxf(x, 0);
    case 4: return fmaxf(x, 0) - 0.5f;
    case 5: return 0.5f - fmaxf(x, 0);
    case 6: return x;
    default: return -x;
    }
}

/* One input byte, as three RGB values or (alpha) one value. */
static void input(const Comb *cb, uint32_t in, int alpha, float o[3]) {
    const float *r = cb->r[in & 15];
    float tmp[4];
    if ((in & 15) == 15) { tmp[0] = cb->e[0] * cb->f[0], tmp[1] = cb->e[1] * cb->f[1], tmp[2] = cb->e[2] * cb->f[2], tmp[3] = 0; r = tmp; }
    if (alpha) o[0] = map_in(in & 0x10 ? r[3] : r[2], in & 0xE0);
    else
        for (int k = 0; k < 3; k++) o[k] = map_in(in & 0x10 ? r[3] : r[k], in & 0xE0);
}

static float map_out(float x, uint32_t m) {
    switch (m) {
    case 0x08: x -= 0.5f; break;
    case 0x10: x *= 2; break;
    case 0x18: x = (x - 0.5f) * 2; break;
    case 0x20: x *= 4; break;
    case 0x30: x /= 2; break;
    }
    return fminf(fmaxf(x, -1), 1);
}

/* One half (RGB or alpha) of a general combiner stage. Both halves read
 * the registers as they were before the stage (in) and write cb: the
 * alpha half reading what the RGB half just wrote took the car paint's
 * unshadowed light (0.7 x T2.b) from a dot product instead. */
static void stage(const Comb *in, Comb *cb, uint32_t icw, uint32_t ocw, int alpha, int mux_msb) {
    int n = alpha ? 1 : 3;
    float a[3], b[3], c[3], d[3], ab[3], cd[3], ms[3];
    input(in, icw >> 24 & 255, alpha, a), input(in, icw >> 16 & 255, alpha, b);
    input(in, icw >> 8 & 255, alpha, c), input(in, icw & 255, alpha, d);
    uint32_t flags = ocw >> 12, m = flags & 0x38;
    float abd = a[0] * b[0] + (alpha ? 0 : a[1] * b[1] + a[2] * b[2]), cdd = c[0] * d[0] + (alpha ? 0 : c[1] * d[1] + c[2] * d[2]);
    float r0a = in->r[12][3];
    int sel = mux_msb ? r0a >= 0.5f : ((int)(r0a * 255) & 1);
    for (int k = 0; k < n; k++) {
        float x = !alpha && (flags & 2) ? abd : a[k] * b[k], y = !alpha && (flags & 1) ? cdd : c[k] * d[k];
        ms[k] = map_out(flags & 4 ? (sel ? y : x) : x + y, m);
        ab[k] = map_out(x, m), cd[k] = map_out(y, m);
    }
    uint32_t dab = ocw >> 4 & 15, dcd = ocw & 15, dms = ocw >> 8 & 15;
    for (int k = 0; k < n; k++) {
        int ch = alpha ? 3 : k;
        if (dab) cb->r[dab][ch] = ab[k];
        if (dcd) cb->r[dcd][ch] = cd[k];
        if (dms) cb->r[dms][ch] = ms[k];
    }
    if (!alpha && dab && (flags & 0x80)) cb->r[dab][3] = ab[2];
    if (!alpha && dcd && (flags & 0x40)) cb->r[dcd][3] = cd[2];
}

/* Fog, per vertex as the NV2A computes it (xemu, pgraph/glsl/vsh.c): a
 * distance (a vertex program's oFog.x) through SET_FOG_MODE's curve with
 * the two SET_FOG_PARAMS. D3D biases the parameters (linear by 1, the
 * exponentials by 1.5, so that both sit in the hardware's range), which
 * comes off again here. The combiners read the result as register 3's
 * alpha, next to SET_FOG_COLOR. */
static float fog_factor(float dist) {
    if (!K(SET_FOG_ENABLE)) return 1;
    float p0 = f32(K(SET_FOG_PARAMS)), p1 = f32(K(SET_FOG_PARAMS + 4)), f;
    switch (K(SET_FOG_MODE)) {
    case 0x0800: case 0x0802: f = p0 + exp2f(dist * p1 * 16.0f) - 1.5f; break;             /* EXP, EXP_ABS */
    case 0x0801: case 0x0803: f = p0 + exp2f(-dist * dist * p1 * p1 * 32.0f) - 1.5f; break; /* EXP2, EXP2_ABS */
    default: f = p0 + dist * p1 - 1.0f; break;                                             /* LINEAR, LINEAR_ABS */
    }
    switch (K(SET_FOG_MODE)) {
    case 0x0802: case 0x0803: case 0x0804: f = fabsf(f); break;
    }
    return f != f ? 1 : f;
}

/* SET_FOG_COLOR's channels are ABGR, unlike the combiner constants. */
static void fog_color(float o[3]) {
    uint32_t v = K(SET_FOG_COLOR);
    o[0] = (v & 255) / 255.0f, o[1] = (v >> 8 & 255) / 255.0f, o[2] = (v >> 16 & 255) / 255.0f;
}

/* The fragment colour from the interpolated diffuse (V0) and specular (V1)
 * colours and T0-T3. */
static void combine(const float v0[4], const float v1[4], const float tv[4][4], float fog, int t0_used, float out[4]) {
    Comb cb;
    memset(&cb, 0, sizeof cb);
    fog_color(cb.r[3]);
    cb.r[3][3] = fminf(fmaxf(fog, 0), 1);
    memcpy(cb.r[4], v0, sizeof cb.r[4]);
    memcpy(cb.r[5], v1, sizeof cb.r[5]);
    memcpy(cb.r[8], tv, 4 * sizeof cb.r[8]);
    cb.r[12][3] = t0_used ? cb.r[8][3] : 1; /* R0.a starts as T0.a */
    uint32_t ctl = K(SET_COMBINER_CONTROL);
    int stages = (int)(ctl & 0xFF), mux_msb = (ctl >> 8) & 1;
    if (stages > 8) stages = 8;
    for (int i = 0; i < stages; i++) {
        argb(K(SET_COMBINER_FACTOR0 + 4 * ((ctl & 0x1000) ? i : 0)), cb.r[1]);
        argb(K(SET_COMBINER_FACTOR1 + 4 * ((ctl & 0x10000) ? i : 0)), cb.r[2]);
        Comb in = cb;
        stage(&in, &cb, K(SET_COMBINER_COLOR_ICW + 4 * i), K(SET_COMBINER_COLOR_OCW + 4 * i), 0, mux_msb);
        stage(&in, &cb, K(SET_COMBINER_ALPHA_ICW + 4 * i), K(SET_COMBINER_ALPHA_OCW + 4 * i), 1, mux_msb);
    }
    uint32_t f0 = K(SET_COMBINER_SPECULAR_FOG_CW0), f1 = K(SET_COMBINER_SPECULAR_FOG_CW1);
    if (!f0 && !f1) { /* no final combiner: R0 */
        for (int k = 0; k < 4; k++) out[k] = fminf(fmaxf(cb.r[12][k], 0), 1);
        return;
    }
    argb(K(SET_SPECULAR_FOG_FACTOR), cb.r[1]);
    argb(K(SET_SPECULAR_FOG_FACTOR + 4), cb.r[2]);
    for (int k = 0; k < 3; k++) { /* V1+R0 */
        float v1 = f1 & 0x40 ? 1 - cb.r[5][k] : cb.r[5][k], r0 = f1 & 0x20 ? 1 - cb.r[12][k] : cb.r[12][k];
        cb.r[14][k] = f1 & 0x80 ? fminf(fmaxf(v1 + r0, 0), 1) : v1 + r0;
    }
    input(&cb, f1 >> 24 & 255, 0, cb.e), input(&cb, f1 >> 16 & 255, 0, cb.f);
    float a[3], b[3], c[3], d[3], g[3];
    input(&cb, f0 >> 24 & 255, 0, a), input(&cb, f0 >> 16 & 255, 0, b);
    input(&cb, f0 >> 8 & 255, 0, c), input(&cb, f0 & 255, 0, d);
    input(&cb, f1 >> 8 & 255, 1, g);
    for (int k = 0; k < 3; k++) out[k] = fminf(fmaxf(d[k] + a[k] * b[k] + (1 - a[k]) * c[k], 0), 1);
    out[3] = fminf(fmaxf(g[0], 0), 1);
}

static int alpha_pass(float a) {
    if (!K(SET_ALPHA_TEST_ENABLE)) return 1;
    float ref = (float)(K(SET_ALPHA_REF) & 255) / 255.0f;
    switch (K(SET_ALPHA_FUNC)) {
    case 0x200: return 0;
    case 0x201: return a < ref;
    case 0x202: return a == ref;
    case 0x203: return a <= ref;
    case 0x204: return a > ref;
    case 0x205: return a != ref;
    case 0x206: return a >= ref;
    }
    return 1;
}

typedef struct {
    float x, y, z, iw;          /* screen position, depth, 1/w */
    float c[4], c1[4], tc[4][4]; /* diffuse, specular, texture coordinates 0-3 */
    float fog;                  /* fog factor: 1 none, 0 all fog colour */
} Pt;

static float inv_w(float w) { return fabsf(w) < 1e-20f ? 1 : 1 / w; }

static Pt project(const Vertex *v) {
    if ((K(SET_TRANSFORM_EXECUTION_MODE) & 3) == 2) { /* a vertex program: oPos is in surface coordinates */
        VshOut o;
        run_program(v, &o);
        Pt r;
        r.x = o.o[O_POS][0], r.y = o.o[O_POS][1], r.z = o.o[O_POS][2];
        r.iw = inv_w(o.o[O_POS][3]); /* D3D's programs divide x, y, z themselves and leave w */
        for (int k = 0; k < 4; k++) r.c[k] = o.o[O_D0][k] != o.o[O_D0][k] ? 1 : fminf(fmaxf(o.o[O_D0][k], 0), 1);
        for (int k = 0; k < 4; k++) r.c1[k] = o.o[O_D1][k] != o.o[O_D1][k] ? 0 : fminf(fmaxf(o.o[O_D1][k], 0), 1);
        memcpy(r.tc, o.o[O_T0], sizeof r.tc);
        r.fog = fog_factor(o.o[O_FOG][0]);
        return r;
    }
    const uint32_t *m = &nv2a.kelvin[SET_COMPOSITE_MATRIX / 4];
    float p[4], o[4];
    memcpy(p, v->a[ATTR_POS], sizeof p);
    for (int i = 0; i < 4; i++) o[i] = p[0] * f32(m[4 * i]) + p[1] * f32(m[4 * i + 1]) + p[2] * f32(m[4 * i + 2]) + p[3] * f32(m[4 * i + 3]);
    float w = fabsf(o[3]) < 1e-20f ? 1e-20f : o[3];
    Pt r;
    r.x = o[0] / w + f32(K(SET_VIEWPORT_OFFSET));
    r.y = o[1] / w + f32(K(SET_VIEWPORT_OFFSET + 4));
    r.z = o[2] / w + f32(K(SET_VIEWPORT_OFFSET + 8));
    r.iw = inv_w(o[3]);
    memcpy(r.c, v->a[ATTR_DIFFUSE], sizeof r.c);
    memcpy(r.c1, v->a[ATTR_DIFFUSE + 1], sizeof r.c1); /* specular */
    memcpy(r.tc, v->a[ATTR_TEX0], sizeof r.tc);
    r.fog = 1; /* fixed-function fog (SET_FOG_GEN_MODE) is not modelled */
    return r;
}

/* State that holds for a whole draw: the surfaces, the texture stages, depth
 * and blending. Methods do not change in the middle of a Begin/End. */
typedef struct {
    int bpp, sx, sy, cx0, cw, cy0, ch;
    uint32_t base, pitch;
    int mode[4];
    Texture *tex[4];
    int ztest, zbpp;
    uint32_t zbase, zpitch, zfunc, zwrite;
    float zmax;
    int blend;
    uint32_t sf, df, eq, wm;
    float cc[4];
} DrawState;

typedef struct {
    Pt a, b, c;
    int x0, x1, y0, y1;
    float inv;
    int state; /* its draw's DrawState, in the batch */
} Tri;

static int draw_state(DrawState *d) {
    uint32_t fmt = K(SET_SURFACE_FORMAT), color = fmt & 15, type = (fmt >> 8) & 15, aa = (fmt >> 12) & 15;
    d->bpp = (color >= 4 && color <= 8) ? 4 : (color >= 1 && color <= 3) ? 2 : 0;
    if (type != 1 || !d->bpp) {
        static uint32_t last;
        if (rt_log_level && last != fmt) rt_log("raster: surface format %x not drawn (offset %08x)\n", fmt, K(SET_SURFACE_COLOR_OFFSET));
        last = fmt;
        return 0;
    }
    d->sx = (aa == 1 || aa == 2) ? 2 : 1, d->sy = aa == 2 ? 2 : 1;
    d->cx0 = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) & 0xFFFF) * d->sx, d->cw = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) >> 16) * d->sx;
    d->cy0 = (int)(K(SET_SURFACE_CLIP_VERTICAL) & 0xFFFF) * d->sy, d->ch = (int)(K(SET_SURFACE_CLIP_VERTICAL) >> 16) * d->sy;
    d->pitch = K(SET_SURFACE_PITCH) & 0xFFFF;
    d->base = dma_base(SET_CONTEXT_DMA_COLOR) + K(SET_SURFACE_COLOR_OFFSET);
    if (!d->pitch || (uint32_t)(d->cx0 + d->cw) * (uint32_t)d->bpp > d->pitch) return 0;

    /* Texture stages: SET_SHADER_STAGE_PROGRAM has five bits of mode per
     * stage: 0 off, 1-3 sample a texture (2D, 3D, cube), 4 pass the
     * texture coordinate through as the colour. */
    uint32_t prog = K(SET_SHADER_STAGE_PROGRAM);
    draw_lo = d->base & (RT_PHYS_SIZE - 1), draw_hi = draw_lo + d->pitch * (uint32_t)(d->cy0 + d->ch);
    draw_zlo = draw_zhi = 0;
    if ((K(SET_SURFACE_FORMAT) >> 4) & 15) {
        draw_zlo = (dma_base(SET_CONTEXT_DMA_ZETA) + K(SET_SURFACE_ZETA_OFFSET)) & (RT_PHYS_SIZE - 1);
        draw_zhi = draw_zlo + (K(SET_SURFACE_PITCH) >> 16) * (uint32_t)(d->cy0 + d->ch);
    }
    if (gl_rt_depth < 0) gl_rt_depth = !getenv("XBRT_GL_RT_DEPTH") || atoi(getenv("XBRT_GL_RT_DEPTH"));
    for (int i = 0; i < 4; i++) {
        d->mode[i] = (int)(prog >> (5 * i)) & 31;
        d->tex[i] = NULL;
        if (!prog && i == 0 && (KT(SET_TEXTURE_CONTROL0) >> 30 & 1)) d->mode[i] = 1;
        if (d->mode[i] >= 1 && d->mode[i] <= 3 && (KT(SET_TEXTURE_CONTROL0) >> 30 & 1)) d->tex[i] = texture(i);
    }
    if (rt_log_level >= 2) { /* each new combination of pixel state, once */
        static uint32_t seen[256][8];
        static int nseen;
        uint32_t key[8] = {K(SET_TEXTURE_FORMAT), K(SET_COMBINER_CONTROL), K(SET_COMBINER_COLOR_ICW), K(SET_COMBINER_COLOR_OCW),
                           K(SET_COMBINER_ALPHA_ICW), K(SET_COMBINER_SPECULAR_FOG_CW0), K(SET_COMBINER_SPECULAR_FOG_CW1),
                           prog | (uint32_t)(d->tex[0] != NULL) << 30 | K(SET_BLEND_ENABLE) << 31};
        int found = 0;
        for (int i = 0; i < nseen; i++) found |= !memcmp(seen[i], key, sizeof key);
        if (!found && nseen < 256) {
            memcpy(seen[nseen++], key, sizeof key);
            rt_log("draw state: texfmt %08x ctl %x cicw %08x cocw %08x aicw %08x fc %08x %08x prog/tex/blend %x blend %x %x alpha %x ref %x\n",
                   key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7], K(SET_BLEND_FUNC_SFACTOR), K(SET_BLEND_FUNC_DFACTOR),
                   K(SET_ALPHA_TEST_ENABLE), K(SET_ALPHA_REF));
        }
    }
    /* The depth buffer: same sample grid as the colour buffer. */
    uint32_t zfmt = (fmt >> 4) & 15;
    d->zpitch = K(SET_SURFACE_PITCH) >> 16;
    d->zbpp = zfmt == 1 ? 2 : zfmt == 2 ? 4 : 0;
    d->ztest = K(SET_DEPTH_TEST_ENABLE) && d->zbpp && d->zpitch && (uint32_t)(d->cx0 + d->cw) * (uint32_t)d->zbpp <= d->zpitch;
    d->zbase = d->ztest ? dma_base(SET_CONTEXT_DMA_ZETA) + K(SET_SURFACE_ZETA_OFFSET) : 0;
    d->zfunc = K(SET_DEPTH_FUNC), d->zwrite = d->ztest && K(SET_DEPTH_MASK);
    d->zmax = d->zbpp == 2 ? 65535.0f : 16777215.0f;

    d->blend = K(SET_BLEND_ENABLE) != 0;
    d->sf = K(SET_BLEND_FUNC_SFACTOR), d->df = K(SET_BLEND_FUNC_DFACTOR), d->eq = K(SET_BLEND_EQUATION);
    uint32_t mask = K(SET_COLOR_MASK);
    if (!mask) mask = 0x01010101u;
    d->wm = (mask & 1 ? 0x000000FFu : 0) | (mask & 0x100 ? 0x0000FF00u : 0) | (mask & 0x10000 ? 0x00FF0000u : 0) |
            (mask & 0x1000000 ? 0xFF000000u : 0);
    uint32_t bc = K(SET_BLEND_COLOR);
    d->cc[0] = (bc >> 16 & 255) / 255.0f, d->cc[1] = (bc >> 8 & 255) / 255.0f, d->cc[2] = (bc & 255) / 255.0f, d->cc[3] = (bc >> 24) / 255.0f;
    return 1;
}

/* Projects a triangle and clips its bounding box; 0 if nothing is drawn. */
static int setup_tri(const DrawState *d, Tri *t, const Pt *pa, const Pt *pb, const Pt *pc) {
    Pt a = *pa, b = *pb, c = *pc;
    a.x *= d->sx, b.x *= d->sx, c.x *= d->sx, a.y *= d->sy, b.y *= d->sy, c.y *= d->sy; /* logical pixels to samples */
    float area = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    if (fabsf(area) < 1e-6f || area != area) return 0;
    float fx0 = fminf(a.x, fminf(b.x, c.x)), fx1 = fmaxf(a.x, fmaxf(b.x, c.x));
    float fy0 = fminf(a.y, fminf(b.y, c.y)), fy1 = fmaxf(a.y, fmaxf(b.y, c.y));
    if (fx1 < d->cx0 || fy1 < d->cy0 || fx0 > d->cx0 + d->cw || fy0 > d->cy0 + d->ch) return 0;
    int x0 = fx0 < d->cx0 ? d->cx0 : (int)floorf(fx0), x1 = fx1 > d->cx0 + d->cw ? d->cx0 + d->cw : (int)ceilf(fx1);
    int y0 = fy0 < d->cy0 ? d->cy0 : (int)floorf(fy0), y1 = fy1 > d->cy0 + d->ch ? d->cy0 + d->ch : (int)ceilf(fy1);
    if (x0 >= x1 || y0 >= y1) return 0;
    t->a = a, t->b = b, t->c = c;
    t->x0 = x0, t->x1 = x1, t->y0 = y0, t->y1 = y1;
    t->inv = 1.0f / area;
    return 1;
}

/* Fills the rows y of a triangle with y % step == first. */
static void fill(const DrawState *d, const Tri *t, int first, int step) {
    const Pt a = t->a, b = t->b, c = t->c;
    float inv = t->inv;
    int y0 = t->y0 + ((first - t->y0 % step) % step + step) % step;
    for (int y = y0; y < t->y1; y += step) {
        uint8_t *row = phys(d->base + (uint32_t)y * d->pitch);
        float py = (float)y + 0.5f;
        for (int x = t->x0; x < t->x1; x++) {
            float px = (float)x + 0.5f;
            float w0 = ((b.x - px) * (c.y - py) - (b.y - py) * (c.x - px)) * inv;
            float w1 = ((c.x - px) * (a.y - py) - (c.y - py) * (a.x - px)) * inv;
            float w2 = 1.0f - w0 - w1;
            if (w0 < 0 || w1 < 0 || w2 < 0) continue;
            uint8_t *zp = NULL;
            uint32_t zv = 0;
            if (d->ztest) {
                float z = a.z * w0 + b.z * w1 + c.z * w2;
                zv = (uint32_t)fminf(fmaxf(z, 0), d->zmax);
                zp = phys(d->zbase + (uint32_t)y * d->zpitch) + x * d->zbpp;
                uint32_t old;
                if (d->zbpp == 2) { uint16_t o16; memcpy(&o16, zp, 2); old = o16; }
                else { memcpy(&old, zp, 4); old >>= 8; }
                int pass;
                switch (d->zfunc) {
                case 0x200: pass = 0; break;
                case 0x201: pass = zv < old; break;
                case 0x202: pass = zv == old; break;
                case 0x203: pass = zv <= old; break;
                case 0x204: pass = zv > old; break;
                case 0x205: pass = zv != old; break;
                case 0x206: pass = zv >= old; break;
                default: pass = 1;
                }
                if (!pass) continue;
            }
            /* Perspective-correct weights for everything but z. */
            float p0 = w0 * a.iw, p1 = w1 * b.iw, p2 = w2 * c.iw, psum = p0 + p1 + p2;
            if (psum != 0 && psum == psum) p0 /= psum, p1 /= psum, p2 /= psum;
            else p0 = w0, p1 = w1, p2 = w2;
            float s[4], s1[4];
            for (int k = 0; k < 4; k++) s[k] = a.c[k] * p0 + b.c[k] * p1 + c.c[k] * p2;
            for (int k = 0; k < 4; k++) s1[k] = a.c1[k] * p0 + b.c1[k] * p1 + c.c1[k] * p2;
            float tv[4][4] = {{0}};
            for (int i = 0; i < 4; i++) {
                const Texture *tx = d->tex[i];
                if (!d->mode[i] || (d->mode[i] != 4 && !tx)) continue;
                float q[4];
                for (int k = 0; k < 4; k++) q[k] = a.tc[i][k] * p0 + b.tc[i][k] * p1 + c.tc[i][k] * p2;
                if (d->mode[i] == 4) {
                    for (int k = 0; k < 4; k++) tv[i][k] = fminf(fmaxf(q[k], 0), 1);
                } else if (tx->depth) { /* a shadow map: compare, as xemu does */
                    float qw = q[3] != 0 ? q[3] : 1;
                    uint32_t dd = sample(tx, i, q[0] / qw, q[1] / qw);
                    float r = d->mode[i] == 2 ? fminf(fmaxf(q[2] / qw, 0), (float)tx->depth) : 0, dv = (float)dd;
                    int lit;
                    switch (K(SET_SHADOW_DEPTH_FUNC) & 7) {
                    case 0: lit = 0; break;
                    case 1: lit = dv < r; break;
                    case 2: lit = dv == r; break;
                    case 3: lit = dv <= r; break;
                    case 4: lit = dv > r; break;
                    case 5: lit = dv != r; break;
                    case 6: lit = dv >= r; break;
                    default: lit = 1;
                    }
                    for (int k = 0; k < 4; k++) tv[i][k] = lit ? 1 : 0;
                } else if (tx->cube) {
                    argb(sample_cube(tx, q[0], q[1], q[2]), tv[i]);
                } else {
                    if (q[3] != 0 && q[3] != 1) q[0] /= q[3], q[1] /= q[3]; /* projective */
                    argb(sample(tx, i, q[0], q[1]), tv[i]);
                }
            }
            combine(s, s1, tv, a.fog * p0 + b.fog * p1 + c.fog * p2, d->mode[0] != 0, s);
            if (!alpha_pass(s[3])) continue;
            uint32_t dst;
            if (d->bpp == 4) memcpy(&dst, row + x * 4, 4);
            else { uint16_t d16; memcpy(&d16, row + x * 2, 2); dst = rgb565(d16, 255); }
            float dc[4] = {(dst >> 16 & 255) / 255.0f, (dst >> 8 & 255) / 255.0f, (dst & 255) / 255.0f, (dst >> 24) / 255.0f};
            float o[4];
            for (int k = 0; k < 4; k++) {
                float v = s[k];
                if (d->blend) {
                    float fs = blend_factor(d->sf, k, s, dc, d->cc), fd = blend_factor(d->df, k, s, dc, d->cc);
                    if (d->eq == 0x800A) v = s[k] * fs - dc[k] * fd;
                    else if (d->eq == 0x800B) v = dc[k] * fd - s[k] * fs;
                    else if (d->eq == 0x8007) v = fminf(s[k], dc[k]);
                    else if (d->eq == 0x8008) v = fmaxf(s[k], dc[k]);
                    else v = s[k] * fs + dc[k] * fd;
                }
                o[k] = v < 0 ? 0 : v > 1 ? 1 : v;
            }
            uint32_t out = (uint32_t)(o[3] * 255 + 0.5f) << 24 | (uint32_t)(o[0] * 255 + 0.5f) << 16 | (uint32_t)(o[1] * 255 + 0.5f) << 8 |
                           (uint32_t)(o[2] * 255 + 0.5f);
            out = (dst & ~d->wm) | (out & d->wm);
            if (d->bpp == 4) memcpy(row + x * 4, &out, 4);
            else {
                uint16_t o16 = (uint16_t)((out >> 8 & 0xF800) | (out >> 5 & 0x07E0) | (out >> 3 & 0x001F));
                memcpy(row + x * 2, &o16, 2);
            }
            if (d->zwrite) {
                if (d->zbpp == 2) { uint16_t z16 = (uint16_t)zv; memcpy(zp, &z16, 2); }
                else { uint32_t old; memcpy(&old, zp, 4); old = (old & 0xFF) | zv << 8; memcpy(zp, &old, 4); } /* stencil kept */
            }
        }
    }
}

/* ---- filling in parallel ----
 * Worker thread w fills the rows y % workers == w of every triangle of a
 * draw, in order. A pixel is only ever touched by one thread, in the order
 * the triangles came, so blending and depth come out as if drawn one by
 * one. XBRT_RASTER_THREADS sets the count (default: half the host's
 * logical cores, about one a physical core, at most 16; 1 fills on the
 * device thread alone). */
static int workers = -1;
static pthread_t worker_threads[16];
static pthread_mutex_t pool_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t pool_go = PTHREAD_COND_INITIALIZER, pool_done = PTHREAD_COND_INITIALIZER;
static unsigned pool_job;
static int pool_left;
static const DrawState *pool_states;
static const Tri *pool_tris;
static int pool_ntris;
static void (*pool_fn)(int w); /* the job: fill_job or project_job */

static void fill_job(int w) {
    for (int i = 0; i < pool_ntris; i++) fill(&pool_states[pool_tris[i].state], &pool_tris[i], w, workers);
}

static Pt *pts; /* the draw's vertices, projected */
static int pts_cap;

static void project_job(int w) {
    for (int i = w; i < nverts; i += workers) pts[i] = project(&verts[i]);
}

static void run_pool(void (*fn)(int w));

/* Draws come thousands to a frame, so waking the workers through a
 * condition variable each time cost more than the filling. Both sides spin
 * briefly on the counters first and sleep only if that runs out. */
#define POOL_SPINS 500

static void *worker_main(void *arg) {
    int w = (int)(intptr_t)arg;
    unsigned seen = 0;
    for (;;) {
        for (int spins = 0; __atomic_load_n(&pool_job, __ATOMIC_ACQUIRE) == seen;) {
            if (++spins < POOL_SPINS) {
                __builtin_ia32_pause();
                continue;
            }
            pthread_mutex_lock(&pool_lock);
            while (__atomic_load_n(&pool_job, __ATOMIC_ACQUIRE) == seen) pthread_cond_wait(&pool_go, &pool_lock);
            pthread_mutex_unlock(&pool_lock);
        }
        seen = __atomic_load_n(&pool_job, __ATOMIC_ACQUIRE);
        pool_fn(w);
        if (__atomic_sub_fetch(&pool_left, 1, __ATOMIC_ACQ_REL) == 0) {
            pthread_mutex_lock(&pool_lock);
            pthread_cond_signal(&pool_done);
            pthread_mutex_unlock(&pool_lock);
        }
    }
    return NULL;
}

static void start_workers(void) {
    const char *e = getenv("XBRT_RASTER_THREADS");
    long cores = 1;
#ifdef _WIN32
    cores = pthread_num_processors_np();
#else
    cores = sysconf(_SC_NPROCESSORS_ONLN);
#endif
    workers = e && atoi(e) > 0 ? atoi(e) : (int)(cores >= 4 ? cores / 2 : 1); /* one per physical core, leaving the hyperthreads */
    if (workers > 16) workers = 16;
    if (workers > 1)
        for (int i = 0; i < workers; i++) pthread_create(&worker_threads[i], NULL, worker_main, (void *)(intptr_t)i);
    rt_log("raster: %d fill thread%s\n", workers, workers == 1 ? "" : "s");
}

/* Triangles are filled in batches across draws: a pool round trip per draw
 * cost more than the filling for the thousands of small draws in a frame.
 * Each triangle keeps its draw's state, and the batch is filled whenever
 * its results could be seen: a surface change or a flip
 * (nv2a_raster_invalidate), a clear, a semaphore or notify, the end of a
 * push buffer pass, or a texture decode. */
static Tri *tris;
static int ntris, tris_cap;
static DrawState *bstates;
static int nstates, states_cap;
static long batch_pixels;
static struct { uint32_t lo, hi; } batch_surf[16]; /* the byte ranges the batch draws into */
static int nbatch_surf;

static void batch_note(uint32_t lo, uint32_t hi) {
    uint32_t len = hi - lo;
    lo &= RT_PHYS_SIZE - 1, hi = lo + len; /* physical, as textures are compared */
    for (int i = 0; i < nbatch_surf; i++)
        if (batch_surf[i].lo == lo && batch_surf[i].hi == hi) return;
    if (nbatch_surf == 16) nv2a_raster_flush();
    batch_surf[nbatch_surf].lo = lo, batch_surf[nbatch_surf].hi = hi;
    nbatch_surf++;
}

static int batch_writes(uint32_t base, uint32_t size) {
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + size;
    for (int i = 0; i < nbatch_surf; i++)
        if (lo < batch_surf[i].hi && batch_surf[i].lo < hi) return 1;
    return 0;
}

/* Where the device thread's time goes, in 100 ns units, for the stats line. */
uint64_t raster_t_state, raster_t_setup, raster_t_fill, raster_t_decode, raster_n_decode, raster_t_hash, raster_hash_bytes;

static void add_tri(int state, int ia, int ib, int ic) {
    if (ntris == tris_cap) {
        tris_cap = tris_cap ? tris_cap * 2 : 1024;
        tris = realloc(tris, (size_t)tris_cap * sizeof *tris);
    }
    Tri *t = &tris[ntris];
    if (setup_tri(&bstates[state], t, &pts[ia], &pts[ib], &pts[ic])) {
        t->state = state;
        batch_pixels += (long)(t->x1 - t->x0) * (t->y1 - t->y0) / 2;
        ntris++;
    }
}

void nv2a_raster_flush(void) {
    if (!ntris) {
        nstates = 0;
        nbatch_surf = 0;
        return;
    }
    uint64_t t0 = rt_now_100ns();
    if (workers <= 1 || batch_pixels < 256) {
        for (int i = 0; i < ntris; i++) fill(&bstates[tris[i].state], &tris[i], 0, 1);
    } else {
        pool_states = bstates, pool_tris = tris, pool_ntris = ntris;
        run_pool(fill_job);
    }
    ntris = nstates = 0;
    batch_pixels = 0;
    nbatch_surf = 0;
    raster_t_fill += rt_now_100ns() - t0;
}

void nv2a_raster_sync(void) {
    nv2a_raster_flush();
    if (rt_gl_on) gl_sync_cpu();
}

void nv2a_raster_sync_range(uint32_t base, uint32_t size) {
    nv2a_raster_flush();
    if (rt_gl_on) gl_sync_color_async(base, size);
}

void nv2a_raster_flip(void) {
    nv2a_raster_flush();
    if (rt_gl_on) gl_flip();
}

void nv2a_raster_vblank(void) {
    if (rt_gl_on) gl_complete();
}

void nv2a_raster_present(uint32_t fb) {
    if (rt_gl_on) gl_present_vblank(fb);
}

void nv2a_raster_poll(void) {
    if (rt_gl_on) gl_present_poll(0);
}

#define SET_COLOR_CLEAR_VALUE 0x1D90
#define SET_ZSTENCIL_CLEAR_VALUE 0x1D8C
#define SET_CLEAR_RECT_HORIZONTAL 0x1D98
#define SET_CLEAR_RECT_VERTICAL 0x1D9C
#include "glfill.c"
#include "glvsh.c"

/* CLEAR_SURFACE: on the GPU when it draws, else 0 and kelvin.c clears RAM. */
int nv2a_raster_clear(uint32_t flags) {
    if (!rt_gl_on) return 0;
    nv2a_raster_flush();
    return gl_clear(flags);
}


/* Runs fn on every worker and waits for them all. */
static void run_pool(void (*fn)(int w)) {
    pool_fn = fn;
    __atomic_store_n(&pool_left, workers, __ATOMIC_RELEASE);
    __atomic_add_fetch(&pool_job, 1, __ATOMIC_RELEASE);
    pthread_mutex_lock(&pool_lock);
    pthread_cond_broadcast(&pool_go); /* for workers that went to sleep */
    pthread_mutex_unlock(&pool_lock);
    for (int spins = 0; __atomic_load_n(&pool_left, __ATOMIC_ACQUIRE);) {
        if (++spins < POOL_SPINS) {
            __builtin_ia32_pause();
            continue;
        }
        pthread_mutex_lock(&pool_lock);
        while (__atomic_load_n(&pool_left, __ATOMIC_ACQUIRE)) pthread_cond_wait(&pool_done, &pool_lock);
        pthread_mutex_unlock(&pool_lock);
    }
}

static void draw(void) {
    uint32_t mode = K(SET_TRANSFORM_EXECUTION_MODE) & 3;
    if (mode != 0 && mode != 2) {
        nv2a.skipped++;
        return;
    }
    DrawState d;
    uint64_t t0 = rt_now_100ns();
    int ok = draw_state(&d);
    uint64_t t1 = rt_now_100ns();
    raster_t_state += t1 - t0;
    if (!ok) return;
    if (workers < 0) start_workers();
    int n = nverts;
    if (n < 3) return;
    if (nstates == states_cap) {
        states_cap = states_cap ? states_cap * 2 : 256;
        bstates = realloc(bstates, (size_t)states_cap * sizeof *bstates);
    }
    uint32_t rows = (uint32_t)(d.cy0 + d.ch);
    batch_note(d.base, d.base + d.pitch * rows);
    if (d.ztest) batch_note(d.zbase, d.zbase + d.zpitch * rows);
    int st = nstates++;
    bstates[st] = d;
    /* Each vertex once (strips and quads share them), on the workers when
     * there are enough to be worth it. */
    if (mode == 2) {
        vsh_decode();
        if (rt_gl_on && gl_vsh_on() && !(rt_debug_keys & RT_DBG_CPU_VSH) && gl_draw_vsh(&d, verts, n, prim)) return; /* the GPU runs the program */
    }
    if (n > pts_cap) {
        pts_cap = n > 4096 ? n : 4096;
        pts = realloc(pts, (size_t)pts_cap * sizeof *pts);
    }
    if (workers > 1 && n >= 64) run_pool(project_job);
    else
        for (int i = 0; i < n; i++) pts[i] = project(&verts[i]);
    switch (prim) {
    case 5: for (int i = 0; i + 2 < n; i += 3) add_tri(st, i, i + 1, i + 2); break;
    case 6: for (int i = 0; i + 2 < n; i++) i & 1 ? add_tri(st, i + 1, i, i + 2) : add_tri(st, i, i + 1, i + 2); break;
    case 7: case 10: for (int i = 1; i + 1 < n; i++) add_tri(st, 0, i, i + 1); break;
    case 8: for (int i = 0; i + 3 < n; i += 4) add_tri(st, i, i + 1, i + 2), add_tri(st, i, i + 2, i + 3); break;
    case 9: for (int i = 0; i + 3 < n; i += 2) add_tri(st, i, i + 1, i + 3), add_tri(st, i, i + 3, i + 2); break;
    }
    raster_t_setup += rt_now_100ns() - t1;
    if (rt_gl_on) { /* the GPU fills */
        uint64_t t3 = rt_now_100ns();
        gl_draw(&bstates[st], tris, ntris);
        ntris = nstates = 0;
        batch_pixels = 0;
        nbatch_surf = 0;
        raster_t_fill += rt_now_100ns() - t3;
        return;
    }
    static int no_batch = -1; /* batching is off unless XBRT_BATCH=1: it left the race view black, and gained nothing */
    if (no_batch < 0) no_batch = !(getenv("XBRT_BATCH") && atoi(getenv("XBRT_BATCH")));
    if (ntris >= 1 << 16 || no_batch) nv2a_raster_flush();
}

static void emit(void) {
    if (prim) vert_new();
}

/* Vertex arrays: offset bit 31 picks the second vertex DMA. */
/* The arrays' layout, worked out once per Begin: the formats and offsets
 * are set before it. Looking the DMA objects up for every attribute of
 * every vertex was a quarter of the device thread once vertex programs
 * ran on the GPU. */
typedef struct {
    uint8_t a, type, size;
    uint32_t stride, base; /* base: the physical address of element 0 */
} FetchAttr;

static FetchAttr fattr[NATTR];
static int nfattr;

static void fetch_layout(void) {
    nfattr = 0;
    for (int a = 0; a < NATTR; a++) {
        uint32_t f = K(SET_VERTEX_DATA_ARRAY_FORMAT + 4 * a), size = (f >> 4) & 15;
        if (!size) continue;
        uint32_t off = K(SET_VERTEX_DATA_ARRAY_OFFSET + 4 * a);
        FetchAttr *fa = &fattr[nfattr++];
        fa->a = (uint8_t)a, fa->type = (uint8_t)(f & 15), fa->size = (uint8_t)size, fa->stride = f >> 8;
        fa->base = dma_base(off & 0x80000000u ? SET_CONTEXT_DMA_VERTEX_B : SET_CONTEXT_DMA_VERTEX_A) + (off & 0x7FFFFFFFu);
    }
}

static void fetch(uint32_t index, Vertex *out, const uint32_t **inl) {
    /* One loop per format (the per-component switch was a quarter of the
     * device thread in a race): floats are a straight copy. */
    for (int i = 0; i < nfattr; i++) {
        const FetchAttr *fa = &fattr[i];
        uint32_t type = fa->type, size = fa->size < 4 ? fa->size : 4;
        const uint8_t *p = inl ? (const uint8_t *)*inl : phys(fa->base + index * fa->stride);
        float *v = out->a[fa->a];
        uint32_t bytes;
        v[0] = v[1] = v[2] = 0, v[3] = 1;
        switch (type) {
        case 2: memcpy(v, p, 4 * size); bytes = 4 * fa->size; break;
        case 0: /* D3DCOLOR: B,G,R,A in memory */
            v[0] = p[2] / 255.0f, v[1] = p[1] / 255.0f, v[2] = p[0] / 255.0f, v[3] = p[3] / 255.0f;
            if (size < 4) v[3] = 1;
            if (size < 3) v[2] = 0;
            bytes = 4;
            break;
        case 4: for (uint32_t k = 0; k < size; k++) v[k] = p[k] / 255.0f; bytes = fa->size; break;
        case 1: for (uint32_t k = 0; k < size; k++) { int16_t t; memcpy(&t, p + 2 * k, 2); v[k] = t / 32767.0f; } bytes = 2 * fa->size; break;
        case 5: for (uint32_t k = 0; k < size; k++) { int16_t t; memcpy(&t, p + 2 * k, 2); v[k] = (float)t; } bytes = 2 * fa->size; break;
        case 6: { /* CMP: a normal packed in 32 bits, signed x:11 y:11 z:10 (Forza's normals, attribute 2; read as zeros before) */
            uint32_t w;
            memcpy(&w, p, 4);
            v[0] = (float)((int32_t)(w << 21) >> 21) / 1023.0f;
            v[1] = (float)((int32_t)(w << 10) >> 21) / 1023.0f;
            v[2] = (float)((int32_t)w >> 22) / 511.0f;
            bytes = 4 * fa->size;
            break;
        }
        default: bytes = 4 * fa->size; break;
        }
        if (inl) *inl += (bytes + 3) / 4;
    }
}

/* Called for every Kelvin method after its value is stored in nv2a.kelvin. */
void nv2a_raster_method(uint32_t method, uint32_t arg) {
    if (program_method(method, arg)) return;
    if (method == SET_BEGIN_END) {
        if (arg) {
            prim = (int)arg, nverts = 0, ninline = 0;
            fetch_layout();
        } else if (prim) {
            if (ninline) { /* INLINE_ARRAY: whole vertices, attribute by attribute */
                const uint32_t *p = inline_buf, *end = inline_buf + ninline;
                while (p < end) {
                    const uint32_t *was = p;
                    fetch(0, vert_new(), &p);
                    if (p == was) break; /* no attributes enabled */
                }
            }
            draw();
            prim = 0;
        }
        return;
    }
    if (method == SET_SURFACE_COLOR_OFFSET || method == SET_SURFACE_FORMAT) nv2a_raster_invalidate();
    if (method >= SET_VERTEX3F && method < SET_VERTEX3F + 12) {
        cur.a[ATTR_POS][(method - SET_VERTEX3F) / 4] = f32(arg);
        if (method == SET_VERTEX3F + 8) cur.a[ATTR_POS][3] = 1, emit();
    } else if (method >= SET_VERTEX4F && method < SET_VERTEX4F + 16) {
        cur.a[ATTR_POS][(method - SET_VERTEX4F) / 4] = f32(arg);
        if (method == SET_VERTEX4F + 12) emit();
    } else if (method >= SET_VERTEX_DATA2F_M && method < SET_VERTEX_DATA2F_M + 0x80) {
        int a = (int)(method - SET_VERTEX_DATA2F_M) / 8, k = (int)((method - SET_VERTEX_DATA2F_M) % 8) / 4;
        cur.a[a][k] = f32(arg);
        if (k == 1) {
            cur.a[a][2] = 0, cur.a[a][3] = 1;
            if (a == ATTR_POS) emit();
        }
    } else if (method >= SET_VERTEX_DATA4F_M && method < SET_VERTEX_DATA4F_M + 0x100) {
        int a = (int)(method - SET_VERTEX_DATA4F_M) / 16, k = (int)((method - SET_VERTEX_DATA4F_M) % 16) / 4;
        cur.a[a][k] = f32(arg);
        if (k == 3 && a == ATTR_POS) emit();
    } else if (method >= SET_VERTEX_DATA4UB && method < SET_VERTEX_DATA4UB + 0x40) {
        int a = (int)(method - SET_VERTEX_DATA4UB) / 4;
        for (int k = 0; k < 4; k++) cur.a[a][k] = (float)((arg >> (8 * k)) & 255) / 255.0f;
        if (a == ATTR_POS) emit();
    } else if (method >= SET_VERTEX_DATA2S && method < SET_VERTEX_DATA2S + 0x40) {
        int a = (int)(method - SET_VERTEX_DATA2S) / 4;
        cur.a[a][0] = (float)(int16_t)arg, cur.a[a][1] = (float)(int16_t)(arg >> 16), cur.a[a][2] = 0, cur.a[a][3] = 1;
        if (a == ATTR_POS) emit();
    } else if (method >= SET_VERTEX_DATA4S_M && method < SET_VERTEX_DATA4S_M + 0x80) {
        int a = (int)(method - SET_VERTEX_DATA4S_M) / 8, k = (int)((method - SET_VERTEX_DATA4S_M) % 8) / 4;
        cur.a[a][2 * k] = (float)(int16_t)arg, cur.a[a][2 * k + 1] = (float)(int16_t)(arg >> 16);
        if (k == 1 && a == ATTR_POS) emit();
    } else if (method == DRAW_ARRAYS && prim) {
        uint32_t start = arg & 0xFFFFFF, count = (arg >> 24) + 1;
        for (uint32_t i = 0; i < count; i++) fetch(start + i, vert_new(), NULL);
    } else if (method == ARRAY_ELEMENT16 && prim) {
        for (int h = 0; h < 2; h++) fetch(h ? arg >> 16 : arg & 0xFFFF, vert_new(), NULL);
    } else if (method == ARRAY_ELEMENT32 && prim) {
        fetch(arg, vert_new(), NULL);
    } else if (method == INLINE_ARRAY && prim) {
        if (ninline == inline_cap) inline_cap = inline_cap ? inline_cap * 2 : 4096, inline_buf = realloc(inline_buf, (size_t)inline_cap * 4);
        inline_buf[ninline++] = arg;
    }
}
