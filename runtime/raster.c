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
 *             sampling, wrap or clamp; 3D and cube maps read as 2D) or
 *             passing its texture coordinate through as a colour (Forza's
 *             text uses that to pick a channel of its glyph cache). Linear
 *             (LU_IMAGE) textures take texel coordinates, the rest 0..1.
 *   colour    the register combiners (general stages and the final
 *             combiner) over T0-T3; alpha test; blending; colour write mask.
 *   surface   linear colour buffers, 32 or 16 bit. No depth or stencil.
 *
 * XBRT_TEX_DUMP=<folder> saves every texture as it is decoded, and log
 * level 2 lists each new combination of pixel state once.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "nv2a.h"

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
#define SET_TEXTURE_IMAGE_RECT 0x1B1C
#define SET_TEXTURE_PALETTE 0x1B20
#define SET_TRANSFORM_EXECUTION_MODE 0x1E94

#define KT(m) K((m) + 0x40 * (uint32_t)(i)) /* texture stage i's copy of a texture method */

enum { ATTR_POS = 0, ATTR_DIFFUSE = 3, ATTR_TEX0 = 9, NATTR = 16 };

typedef struct {
    float a[NATTR][4];
} Vertex;

static Vertex cur;            /* the inline attribute values */
static Vertex verts[4096];    /* the primitive being collected */
static int nverts, prim;      /* prim: SET_BEGIN_END op, 0 outside Begin/End */
static uint32_t inline_buf[4096]; /* INLINE_ARRAY words of this Begin/End */
static int ninline;

static inline uint8_t *phys(uint32_t pa) { return xb_mem + RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)); }
static inline float f32(uint32_t v) { float f; memcpy(&f, &v, 4); return f; }

static uint32_t dma_base(uint32_t handle_method) {
    uint32_t b = nv2a_dma_base(nv2a_lookup(K(handle_method)), NULL);
    return b == ~0u ? 0 : b;
}

/* ---- textures ---- */

typedef struct {
    uint32_t key[6]; /* offset, format, control1, image rect, palette, generation */
    int w, h, linear;
    uint32_t *texels; /* A8R8G8B8 */
} Texture;

static Texture cache[64];
static int cache_next;
static uint32_t generation; /* bumped when render targets may have changed what textures hold */

void nv2a_raster_invalidate(void) { generation++; }

/* Morton order, as the NV2A swizzles: bits of x and y interleaved, x first,
 * until the smaller dimension runs out. */
static uint32_t swizzle(uint32_t x, uint32_t y, int w, int h) {
    uint32_t r = 0, bit = 0;
    for (int s = 1; s < w || s < h; s <<= 1) {
        if (s < w) r |= ((x & s) ? 1u : 0u) << bit++;
        if (s < h) r |= ((y & s) ? 1u : 0u) << bit++;
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
    if (!checked) checked = 1, dir = getenv("XBRT_TEX_DUMP");
    if (!dir || !*dir || count >= 2000) return;
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
    uint32_t key[6] = {KT(SET_TEXTURE_OFFSET), fmt, KT(SET_TEXTURE_CONTROL1), KT(SET_TEXTURE_IMAGE_RECT), KT(SET_TEXTURE_PALETTE), generation};
    for (int i = 0; i < 64; i++)
        if (cache[i].texels && !memcmp(cache[i].key, key, sizeof key)) return &cache[i];

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
    const uint8_t *src = phys(base);
    if (src + (size_t)w * h * 4 > xb_mem + RT_PHYS_VIEW + RT_PHYS_SIZE && !(color >= 0x0C && color <= 0x0F)) return NULL;

    Texture *t = &cache[cache_next];
    cache_next = (cache_next + 1) % 64;
    free(t->texels);
    t->texels = malloc((size_t)w * h * 4);
    memcpy(t->key, key, sizeof key);
    t->w = w, t->h = h, t->linear = linear;
    uint32_t *o = t->texels;

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
                dxt_block(src + ((size_t)by * ((w + 3) / 4) + bx) * bs, kind, blk);
                for (int i = 0; i < 16; i++) {
                    int x = bx * 4 + i % 4, y = by * 4 + i / 4;
                    if (x < w && y < h) o[y * w + x] = blk[i];
                }
            }
        dump_texture(t, base, fmt);
        return t;
    }
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            uint32_t i = linear ? 0 : swizzle((uint32_t)x, (uint32_t)y, w, h);
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
            case 0x0B: v = pal[src[i]]; break;
            case 0x00: case 0x13: { uint8_t y8 = linear ? src[(size_t)y * pitch + x] : src[i]; v = 0xFF000000u | y8 * 0x010101u; break; }
            case 0x19: case 0x1F: { uint8_t a8 = linear ? src[(size_t)y * pitch + x] : src[i]; v = (uint32_t)a8 << 24 | 0xFFFFFF; break; }
            case 0x1A: case 0x20: { const uint8_t *p = linear ? src + (size_t)y * pitch + (size_t)x * 2 : src + (size_t)i * 2; v = (uint32_t)p[1] << 24 | p[0] * 0x010101u; break; }
            default: v = 0xFFFF00FFu; /* not decoded: magenta */
            }
            o[y * w + x] = v;
        }
    dump_texture(t, base, fmt);
    return t;
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

static void vsh_input(const uint32_t *t, int mux, int reg, int neg, int swz_word, int swz_bit, int scalar,
                      float r[13][4], const Vertex *in, const VshOut *out, int a0, float v[4]) {
    float s[4] = {0, 0, 0, 0};
    if (mux == 1) {
        if (reg == 12) memcpy(s, out->o[O_POS], sizeof s);
        else if (reg < 12) memcpy(s, r[reg], sizeof s);
    } else if (mux == 2) {
        memcpy(s, in->a[field(t, 1, 9, 4)], sizeof s);
    } else if (mux == 3) {
        int c = (int)field(t, 1, 13, 8) + (field(t, 3, 1, 1) ? a0 : 0);
        if (c >= 0 && c < 192)
            for (int k = 0; k < 4; k++) s[k] = f32(constants[c][k]);
    }
    for (int k = 0; k < 4; k++) {
        int sel = (int)field(t, swz_word, swz_bit - 2 * (scalar ? 0 : k), 2);
        v[k] = neg ? -s[sel] : s[sel];
    }
}

static void write_masked(float dst[4], const float src[4], uint32_t mask) {
    for (int k = 0; k < 4; k++)
        if (mask & (8u >> k)) dst[k] = src[k];
}

static void run_program(const Vertex *in, VshOut *out) {
    float r[13][4] = {{0}};
    int a0 = 0;
    memset(out, 0, sizeof *out);
    out->o[O_D0][3] = out->o[O_D1][3] = 1;
    for (int i = 0; i < 4; i++) out->o[O_T0 + i][3] = 1;
    for (uint32_t slot = K(SET_TRANSFORM_PROGRAM_START); slot < 136; slot++) {
        const uint32_t *t = program[slot];
        uint32_t mac = field(t, 1, 21, 4), ilu = field(t, 1, 25, 3);
        float A[4], B[4], C[4], m[4] = {0}, l[4] = {0};
        int ilu_scalar = ilu >= 2 && ilu <= 6;
        vsh_input(t, (int)field(t, 2, 26, 2), (int)field(t, 2, 28, 4), (int)field(t, 1, 8, 1), 1, 6, 0, r, in, out, a0, A);
        vsh_input(t, (int)field(t, 2, 11, 2), (int)field(t, 2, 13, 4), (int)field(t, 2, 25, 1), 2, 23, 0, r, in, out, a0, B);
        vsh_input(t, (int)field(t, 3, 28, 2), (int)(field(t, 2, 0, 2) << 2 | field(t, 3, 30, 2)), (int)field(t, 2, 10, 1), 2, 8,
                  ilu_scalar, r, in, out, a0, C);
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

        uint32_t out_reg = field(t, 3, 20, 4), mac_mask = field(t, 3, 24, 4), ilu_mask = field(t, 3, 16, 4);
        uint32_t o_mask = field(t, 3, 12, 4), orb = field(t, 3, 11, 1), o_addr = field(t, 3, 3, 8), o_mux = field(t, 3, 2, 1);
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
        if (field(t, 3, 0, 1)) break; /* final */
    }
}

/* Program and constant uploads; called before the generic method handling. */
static int program_method(uint32_t method, uint32_t arg) {
    if (method >= SET_TRANSFORM_PROGRAM && method < SET_TRANSFORM_PROGRAM + 0x80) {
        uint32_t k = (method - SET_TRANSFORM_PROGRAM) / 4 % 4;
        if (program_load < 136) program[program_load][k] = arg;
        if (k == 3) program_load++;
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

static void stage(Comb *cb, uint32_t icw, uint32_t ocw, int alpha, int mux_msb) {
    int n = alpha ? 1 : 3;
    float a[3], b[3], c[3], d[3], ab[3], cd[3], ms[3];
    input(cb, icw >> 24 & 255, alpha, a), input(cb, icw >> 16 & 255, alpha, b);
    input(cb, icw >> 8 & 255, alpha, c), input(cb, icw & 255, alpha, d);
    uint32_t flags = ocw >> 12, m = flags & 0x38;
    float abd = a[0] * b[0] + (alpha ? 0 : a[1] * b[1] + a[2] * b[2]), cdd = c[0] * d[0] + (alpha ? 0 : c[1] * d[1] + c[2] * d[2]);
    float r0a = cb->r[12][3];
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

/* The fragment colour from the interpolated diffuse colour and T0-T3. */
static void combine(const float v0[4], const float tv[4][4], int t0_used, float out[4]) {
    Comb cb;
    memset(&cb, 0, sizeof cb);
    memcpy(cb.r[4], v0, sizeof cb.r[4]);
    memcpy(cb.r[8], tv, 4 * sizeof cb.r[8]);
    cb.r[12][3] = t0_used ? cb.r[8][3] : 1; /* R0.a starts as T0.a */
    uint32_t ctl = K(SET_COMBINER_CONTROL);
    int stages = (int)(ctl & 0xFF), mux_msb = (ctl >> 8) & 1;
    if (stages > 8) stages = 8;
    for (int i = 0; i < stages; i++) {
        argb(K(SET_COMBINER_FACTOR0 + 4 * ((ctl & 0x1000) ? i : 0)), cb.r[1]);
        argb(K(SET_COMBINER_FACTOR1 + 4 * ((ctl & 0x10000) ? i : 0)), cb.r[2]);
        stage(&cb, K(SET_COMBINER_COLOR_ICW + 4 * i), K(SET_COMBINER_COLOR_OCW + 4 * i), 0, mux_msb);
        stage(&cb, K(SET_COMBINER_ALPHA_ICW + 4 * i), K(SET_COMBINER_ALPHA_OCW + 4 * i), 1, mux_msb);
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
    float x, y, c[4], tc[4][4]; /* position, diffuse, texture coordinates 0-3 */
} Pt;

static Pt project(const Vertex *v) {
    if ((K(SET_TRANSFORM_EXECUTION_MODE) & 3) == 2) { /* a vertex program: oPos is in surface coordinates */
        VshOut o;
        run_program(v, &o);
        Pt r;
        r.x = o.o[O_POS][0], r.y = o.o[O_POS][1];
        for (int k = 0; k < 4; k++) r.c[k] = o.o[O_D0][k] != o.o[O_D0][k] ? 1 : fminf(fmaxf(o.o[O_D0][k], 0), 1);
        memcpy(r.tc, o.o[O_T0], sizeof r.tc);
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
    memcpy(r.c, v->a[ATTR_DIFFUSE], sizeof r.c);
    memcpy(r.tc, v->a[ATTR_TEX0], sizeof r.tc);
    return r;
}

static void triangle(const Vertex *va, const Vertex *vb, const Vertex *vc) {
    uint32_t fmt = K(SET_SURFACE_FORMAT), color = fmt & 15, type = (fmt >> 8) & 15, aa = (fmt >> 12) & 15;
    int bpp = (color >= 4 && color <= 8) ? 4 : (color >= 1 && color <= 3) ? 2 : 0;
    if (type != 1 || !bpp) {
        static uint32_t last;
        if (rt_log_level && last != fmt) rt_log("raster: surface format %x not drawn (offset %08x)\n", fmt, K(SET_SURFACE_COLOR_OFFSET));
        last = fmt;
        return;
    }
    int sx = (aa == 1 || aa == 2) ? 2 : 1, sy = aa == 2 ? 2 : 1;
    int cx0 = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) & 0xFFFF) * sx, cw = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) >> 16) * sx;
    int cy0 = (int)(K(SET_SURFACE_CLIP_VERTICAL) & 0xFFFF) * sy, ch = (int)(K(SET_SURFACE_CLIP_VERTICAL) >> 16) * sy;
    uint32_t pitch = K(SET_SURFACE_PITCH) & 0xFFFF;
    uint32_t base = dma_base(SET_CONTEXT_DMA_COLOR) + K(SET_SURFACE_COLOR_OFFSET);
    if (!pitch || (uint32_t)(cx0 + cw) * (uint32_t)bpp > pitch) return;

    Pt a = project(va), b = project(vb), c = project(vc);
    a.x *= sx, b.x *= sx, c.x *= sx, a.y *= sy, b.y *= sy, c.y *= sy; /* logical pixels to samples */
    float area = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    if (fabsf(area) < 1e-6f) return;
    int x0 = (int)floorf(fminf(a.x, fminf(b.x, c.x))), x1 = (int)ceilf(fmaxf(a.x, fmaxf(b.x, c.x)));
    int y0 = (int)floorf(fminf(a.y, fminf(b.y, c.y))), y1 = (int)ceilf(fmaxf(a.y, fmaxf(b.y, c.y)));
    if (x0 < cx0) x0 = cx0;
    if (y0 < cy0) y0 = cy0;
    if (x1 > cx0 + cw) x1 = cx0 + cw;
    if (y1 > cy0 + ch) y1 = cy0 + ch;
    if (x0 >= x1 || y0 >= y1) return;

    /* Texture stages: SET_SHADER_STAGE_PROGRAM has five bits of mode per
     * stage: 0 off, 1-3 sample a texture (2D, 3D, cube; all read as 2D
     * here), 4 pass the texture coordinate through as the colour. */
    uint32_t prog = K(SET_SHADER_STAGE_PROGRAM);
    int mode[4];
    Texture *tex[4] = {NULL, NULL, NULL, NULL};
    for (int i = 0; i < 4; i++) {
        mode[i] = (int)(prog >> (5 * i)) & 31;
        if (!prog && i == 0 && (KT(SET_TEXTURE_CONTROL0) >> 30 & 1)) mode[i] = 1;
        if (mode[i] >= 1 && mode[i] <= 3 && (KT(SET_TEXTURE_CONTROL0) >> 30 & 1)) tex[i] = texture(i);
    }
    if (rt_log_level >= 2) { /* each new combination of pixel state, once */
        static uint32_t seen[256][8];
        static int nseen;
        uint32_t key[8] = {K(SET_TEXTURE_FORMAT), K(SET_COMBINER_CONTROL), K(SET_COMBINER_COLOR_ICW), K(SET_COMBINER_COLOR_OCW),
                           K(SET_COMBINER_ALPHA_ICW), K(SET_COMBINER_SPECULAR_FOG_CW0), K(SET_COMBINER_SPECULAR_FOG_CW1), prog | (uint32_t)(tex[0] != NULL) << 30 | K(SET_BLEND_ENABLE) << 31};
        int found = 0;
        for (int i = 0; i < nseen; i++) found |= !memcmp(seen[i], key, sizeof key);
        if (!found && nseen < 256) {
            memcpy(seen[nseen++], key, sizeof key);
            rt_log("draw state: texfmt %08x ctl %x cicw %08x cocw %08x aicw %08x fc %08x %08x en/tex/blend %x blend %x %x alpha %x ref %x c=%.2f,%.2f,%.2f,%.2f\n", key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7],
                   K(SET_BLEND_FUNC_SFACTOR), K(SET_BLEND_FUNC_DFACTOR), K(SET_ALPHA_TEST_ENABLE), K(SET_ALPHA_REF), a.c[0], a.c[1], a.c[2], a.c[3]);
            rt_log("   mode %x, attr3 fmt %08x v3 %.2f %.2f %.2f %.2f, attr4 fmt %08x\n", K(SET_TRANSFORM_EXECUTION_MODE),
                   K(SET_VERTEX_DATA_ARRAY_FORMAT + 12), va->a[3][0], va->a[3][1], va->a[3][2], va->a[3][3], K(SET_VERTEX_DATA_ARRAY_FORMAT + 16));
        }
    }
    int blend = K(SET_BLEND_ENABLE) != 0;
    uint32_t sf = K(SET_BLEND_FUNC_SFACTOR), df = K(SET_BLEND_FUNC_DFACTOR), eq = K(SET_BLEND_EQUATION), mask = K(SET_COLOR_MASK);
    if (!mask) mask = 0x01010101u;
    uint32_t bc = K(SET_BLEND_COLOR);
    float cc[4] = {(bc >> 16 & 255) / 255.0f, (bc >> 8 & 255) / 255.0f, (bc & 255) / 255.0f, (bc >> 24) / 255.0f};
    float inv = 1.0f / area;

    for (int y = y0; y < y1; y++) {
        uint8_t *row = phys(base + (uint32_t)y * pitch);
        float py = (float)y + 0.5f;
        for (int x = x0; x < x1; x++) {
            float px = (float)x + 0.5f;
            float w0 = ((b.x - px) * (c.y - py) - (b.y - py) * (c.x - px)) * inv;
            float w1 = ((c.x - px) * (a.y - py) - (c.y - py) * (a.x - px)) * inv;
            float w2 = 1.0f - w0 - w1;
            if (w0 < 0 || w1 < 0 || w2 < 0) continue;
            float s[4];
            for (int k = 0; k < 4; k++) s[k] = a.c[k] * w0 + b.c[k] * w1 + c.c[k] * w2;
            float tv[4][4] = {{0}};
            for (int i = 0; i < 4; i++) {
                if (!mode[i] || (mode[i] != 4 && !tex[i])) continue;
                float q[4];
                for (int k = 0; k < 4; k++) q[k] = a.tc[i][k] * w0 + b.tc[i][k] * w1 + c.tc[i][k] * w2;
                if (mode[i] == 4) {
                    for (int k = 0; k < 4; k++) tv[i][k] = fminf(fmaxf(q[k], 0), 1);
                } else {
                    if (q[3] != 0 && q[3] != 1) q[0] /= q[3], q[1] /= q[3]; /* projective */
                    argb(sample(tex[i], i, q[0], q[1]), tv[i]);
                }
            }
            combine(s, tv, mode[0] != 0, s);
            if (!alpha_pass(s[3])) continue;
            uint32_t dst;
            if (bpp == 4) memcpy(&dst, row + x * 4, 4);
            else { uint16_t d16; memcpy(&d16, row + x * 2, 2); dst = rgb565(d16, 255); }
            float d[4] = {(dst >> 16 & 255) / 255.0f, (dst >> 8 & 255) / 255.0f, (dst & 255) / 255.0f, (dst >> 24) / 255.0f};
            float o[4];
            for (int k = 0; k < 4; k++) {
                float v = s[k];
                if (blend) {
                    float fs = blend_factor(sf, k, s, d, cc), fd = blend_factor(df, k, s, d, cc);
                    if (eq == 0x800A) v = s[k] * fs - d[k] * fd;
                    else if (eq == 0x800B) v = d[k] * fd - s[k] * fs;
                    else if (eq == 0x8007) v = fminf(s[k], d[k]);
                    else if (eq == 0x8008) v = fmaxf(s[k], d[k]);
                    else v = s[k] * fs + d[k] * fd;
                }
                o[k] = v < 0 ? 0 : v > 1 ? 1 : v;
            }
            uint32_t out = (uint32_t)(o[3] * 255 + 0.5f) << 24 | (uint32_t)(o[0] * 255 + 0.5f) << 16 | (uint32_t)(o[1] * 255 + 0.5f) << 8 |
                           (uint32_t)(o[2] * 255 + 0.5f);
            uint32_t wm = (mask & 1 ? 0x000000FFu : 0) | (mask & 0x100 ? 0x0000FF00u : 0) | (mask & 0x10000 ? 0x00FF0000u : 0) |
                          (mask & 0x1000000 ? 0xFF000000u : 0);
            out = (dst & ~wm) | (out & wm);
            if (bpp == 4) memcpy(row + x * 4, &out, 4);
            else {
                uint16_t o16 = (uint16_t)((out >> 8 & 0xF800) | (out >> 5 & 0x07E0) | (out >> 3 & 0x001F));
                memcpy(row + x * 2, &o16, 2);
            }
        }
    }
}

static void draw(void) {
    uint32_t mode = K(SET_TRANSFORM_EXECUTION_MODE) & 3;
    if (mode != 0 && mode != 2) {
        nv2a.skipped++;
        return;
    }
    Vertex *v = verts;
    int n = nverts;
    switch (prim) {
    case 5: for (int i = 0; i + 2 < n; i += 3) triangle(&v[i], &v[i + 1], &v[i + 2]); break;
    case 6: for (int i = 0; i + 2 < n; i++) i & 1 ? triangle(&v[i + 1], &v[i], &v[i + 2]) : triangle(&v[i], &v[i + 1], &v[i + 2]); break;
    case 7: case 10: for (int i = 1; i + 1 < n; i++) triangle(&v[0], &v[i], &v[i + 1]); break;
    case 8: for (int i = 0; i + 3 < n; i += 4) triangle(&v[i], &v[i + 1], &v[i + 2]), triangle(&v[i], &v[i + 2], &v[i + 3]); break;
    case 9: for (int i = 0; i + 3 < n; i += 2) triangle(&v[i], &v[i + 1], &v[i + 3]), triangle(&v[i], &v[i + 3], &v[i + 2]); break;
    }
}

static void emit(void) {
    if (prim && nverts < (int)(sizeof verts / sizeof verts[0])) verts[nverts++] = cur;
}

/* Vertex arrays: offset bit 31 picks the second vertex DMA. */
static void fetch(uint32_t index, Vertex *out, const uint32_t **inl) {
    for (int a = 0; a < NATTR; a++) {
        uint32_t f = K(SET_VERTEX_DATA_ARRAY_FORMAT + 4 * a), type = f & 15, size = (f >> 4) & 15, stride = f >> 8;
        if (!size) continue;
        const uint8_t *p;
        if (inl) {
            p = (const uint8_t *)*inl;
        } else {
            uint32_t off = K(SET_VERTEX_DATA_ARRAY_OFFSET + 4 * a);
            p = phys(dma_base(off & 0x80000000u ? SET_CONTEXT_DMA_VERTEX_B : SET_CONTEXT_DMA_VERTEX_A) + (off & 0x7FFFFFFFu) + index * stride);
        }
        float v[4] = {0, 0, 0, 1};
        uint32_t bytes = 0;
        for (uint32_t k = 0; k < size && k < 4; k++) {
            switch (type) {
            case 2: v[k] = f32((uint32_t)(p[4 * k] | p[4 * k + 1] << 8 | p[4 * k + 2] << 16 | (uint32_t)p[4 * k + 3] << 24)); bytes = 4 * size; break;
            case 0: v[k] = p[k] / 255.0f; bytes = 4; break; /* D3DCOLOR, swapped below */
            case 4: v[k] = p[k] / 255.0f; bytes = size; break;
            case 1: v[k] = (int16_t)(p[2 * k] | p[2 * k + 1] << 8) / 32767.0f; bytes = 2 * size; break;
            case 5: v[k] = (float)(int16_t)(p[2 * k] | p[2 * k + 1] << 8); bytes = 2 * size; break;
            default: bytes = 4 * size; break;
            }
        }
        if (type == 0) { float t = v[0]; v[0] = v[2], v[2] = t; } /* B,G,R,A in memory */
        memcpy(out->a[a], v, sizeof v);
        if (inl) *inl += (bytes + 3) / 4;
    }
}

/* Called for every Kelvin method after its value is stored in nv2a.kelvin. */
void nv2a_raster_method(uint32_t method, uint32_t arg) {
    if (program_method(method, arg)) return;
    if (method == SET_BEGIN_END) {
        if (arg) {
            prim = (int)arg, nverts = 0, ninline = 0;
        } else if (prim) {
            if (ninline) { /* INLINE_ARRAY: whole vertices, attribute by attribute */
                const uint32_t *p = inline_buf, *end = inline_buf + ninline;
                while (p < end && nverts < (int)(sizeof verts / sizeof verts[0])) {
                    verts[nverts] = cur;
                    fetch(0, &verts[nverts], &p);
                    nverts++;
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
        for (uint32_t i = 0; i < count && nverts < (int)(sizeof verts / sizeof verts[0]); i++) {
            verts[nverts] = cur;
            fetch(start + i, &verts[nverts++], NULL);
        }
    } else if (method == ARRAY_ELEMENT16 && prim) {
        for (int h = 0; h < 2 && nverts < (int)(sizeof verts / sizeof verts[0]); h++) {
            verts[nverts] = cur;
            fetch(h ? arg >> 16 : arg & 0xFFFF, &verts[nverts++], NULL);
        }
    } else if (method == ARRAY_ELEMENT32 && prim) {
        if (nverts < (int)(sizeof verts / sizeof verts[0])) {
            verts[nverts] = cur;
            fetch(arg, &verts[nverts++], NULL);
        }
    } else if (method == INLINE_ARRAY && prim) {
        if (ninline < (int)(sizeof inline_buf / sizeof inline_buf[0])) inline_buf[ninline++] = arg;
    }
}
