/* Kelvin, the NV2A's 3D engine (object class 0x97): the methods D3D sends
 * it through the push buffer.
 *
 * Every method's last value is kept in nv2a.kelvin; the ones with effects
 * beyond state (semaphores, flips, clears, draws) are handled here. Drawing
 * is not implemented yet: draws are counted and dropped.
 */
#include <string.h>

#include "rt.h"
#include "nv2a.h"

#define NO_OPERATION 0x0100
#define FLIP_READ 0x0120
#define FLIP_WRITE 0x0124
#define FLIP_MODULO 0x0128
#define FLIP_INCREMENT_WRITE 0x012C
#define FLIP_STALL 0x0130
#define SET_CONTEXT_DMA_SEMAPHORE 0x01A4
#define SET_BEGIN_END 0x17FC
#define SET_SEMAPHORE_OFFSET 0x1D6C
#define BACK_END_WRITE_SEMAPHORE_RELEASE 0x1D70
#define CLEAR_SURFACE 0x1D94
#define SET_CONTEXT_DMA_COLOR 0x0194
#define SET_SURFACE_FORMAT 0x0208
#define SET_SURFACE_PITCH 0x020C
#define SET_SURFACE_COLOR_OFFSET 0x0210
#define SET_COLOR_CLEAR_VALUE 0x1D90
#define SET_ZSTENCIL_CLEAR_VALUE 0x1D8C
#define SET_CONTEXT_DMA_ZETA 0x0198
#define SET_SURFACE_ZETA_OFFSET 0x0214
#define SET_CLEAR_RECT_HORIZONTAL 0x1D98
#define SET_CLEAR_RECT_VERTICAL 0x1D9C

static uint32_t seen[0x2000 / 4 / 32]; /* methods logged once */

#define K(m) nv2a.kelvin[(m) / 4]

/* CLEAR_SURFACE on the colour buffer: fill the clear rectangle (inclusive
 * corners, in samples when the surface is anti-aliased) with
 * SET_COLOR_CLEAR_VALUE (A8R8G8B8), touching only the channels the method
 * selects. Linear (pitch) surfaces in 32- and 16-bit formats. */
static void clear_color(uint32_t flags) {
    if (!(flags & 0xF0)) return;
    uint32_t fmt = K(SET_SURFACE_FORMAT), color = fmt & 0xF, type = (fmt >> 8) & 0xF, aa = (fmt >> 12) & 0xF;
    if (type != 1) return; /* swizzled */
    uint32_t base = nv2a_dma_base(nv2a_lookup(K(SET_CONTEXT_DMA_COLOR)), NULL);
    if (base == ~0u) return;
    uint32_t addr = base + K(SET_SURFACE_COLOR_OFFSET), pitch = K(SET_SURFACE_PITCH) & 0xFFFF;
    uint32_t x1 = K(SET_CLEAR_RECT_HORIZONTAL) & 0xFFFF, x2 = K(SET_CLEAR_RECT_HORIZONTAL) >> 16;
    uint32_t y1 = K(SET_CLEAR_RECT_VERTICAL) & 0xFFFF, y2 = K(SET_CLEAR_RECT_VERTICAL) >> 16;
    if (aa == 1 || aa == 2) x1 *= 2, x2 = x2 * 2 + 1; /* 2 samples across */
    if (aa == 2) y1 *= 2, y2 = y2 * 2 + 1;           /* and 2 down */
    if (x2 < x1 || y2 < y1 || !pitch) return;
    uint32_t v = K(SET_COLOR_CLEAR_VALUE);
    int bpp = (color >= 4 && color <= 8) ? 4 : (color == 1 || color == 2 || color == 3) ? 2 : 0;
    if (!bpp || (x2 + 1) * (uint32_t)bpp > pitch) return;
    uint32_t mask32 = (flags & 0x10 ? 0x00FF0000u : 0) | (flags & 0x20 ? 0x0000FF00u : 0) | (flags & 0x40 ? 0x000000FFu : 0) |
                      (flags & 0x80 ? 0xFF000000u : 0);
    uint16_t v16 = color == 3 ? (uint16_t)((v >> 8 & 0xF800) | (v >> 5 & 0x07E0) | (v >> 3 & 0x001F))
                              : (uint16_t)((v >> 9 & 0x7C00) | (v >> 6 & 0x03E0) | (v >> 3 & 0x001F));
    uint16_t mask16 = color == 3 ? (uint16_t)((flags & 0x10 ? 0xF800 : 0) | (flags & 0x20 ? 0x07E0 : 0) | (flags & 0x40 ? 0x001F : 0))
                                 : (uint16_t)((flags & 0x10 ? 0x7C00 : 0) | (flags & 0x20 ? 0x03E0 : 0) | (flags & 0x40 ? 0x001F : 0));
    for (uint32_t y = y1; y <= y2; y++) {
        uint8_t *row = xb_mem + RT_PHYS_VIEW + ((addr + y * pitch) & (RT_PHYS_SIZE - 1));
        if (row + (x2 + 1) * bpp > xb_mem + RT_PHYS_VIEW + RT_PHYS_SIZE) return;
        if (bpp == 4) {
            uint32_t *p = (uint32_t *)row;
            for (uint32_t x = x1; x <= x2; x++) p[x] = (p[x] & ~mask32) | (v & mask32);
        } else {
            uint16_t *p = (uint16_t *)row;
            for (uint32_t x = x1; x <= x2; x++) p[x] = (uint16_t)((p[x] & ~mask16) | (v16 & mask16));
        }
    }
}

/* CLEAR_SURFACE on the depth/stencil buffer: Z16, or Z24S8 with depth in
 * the top 24 bits and stencil in the low 8, from SET_ZSTENCIL_CLEAR_VALUE
 * in the same layout. Bit 0 clears depth, bit 1 stencil. */
static void clear_zeta(uint32_t flags) {
    if (!(flags & 3)) return;
    uint32_t fmt = K(SET_SURFACE_FORMAT), zfmt = (fmt >> 4) & 0xF, type = (fmt >> 8) & 0xF, aa = (fmt >> 12) & 0xF;
    if (type != 1 || (zfmt != 1 && zfmt != 2)) return;
    uint32_t base = nv2a_dma_base(nv2a_lookup(K(SET_CONTEXT_DMA_ZETA)), NULL);
    if (base == ~0u) return;
    uint32_t addr = base + K(SET_SURFACE_ZETA_OFFSET), pitch = K(SET_SURFACE_PITCH) >> 16;
    uint32_t x1 = K(SET_CLEAR_RECT_HORIZONTAL) & 0xFFFF, x2 = K(SET_CLEAR_RECT_HORIZONTAL) >> 16;
    uint32_t y1 = K(SET_CLEAR_RECT_VERTICAL) & 0xFFFF, y2 = K(SET_CLEAR_RECT_VERTICAL) >> 16;
    if (aa == 1 || aa == 2) x1 *= 2, x2 = x2 * 2 + 1;
    if (aa == 2) y1 *= 2, y2 = y2 * 2 + 1;
    uint32_t bpp = zfmt == 1 ? 2 : 4;
    if (x2 < x1 || y2 < y1 || !pitch || (x2 + 1) * bpp > pitch) return;
    uint32_t v = K(SET_ZSTENCIL_CLEAR_VALUE);
    uint32_t mask = zfmt == 1 ? (flags & 1 ? 0xFFFFu : 0) : (flags & 1 ? 0xFFFFFF00u : 0) | (flags & 2 ? 0xFFu : 0);
    for (uint32_t y = y1; y <= y2; y++) {
        uint8_t *row = xb_mem + RT_PHYS_VIEW + ((addr + y * pitch) & (RT_PHYS_SIZE - 1));
        if (row + (x2 + 1) * bpp > xb_mem + RT_PHYS_VIEW + RT_PHYS_SIZE) return;
        if (bpp == 2) {
            uint16_t *p = (uint16_t *)row;
            for (uint32_t x = x1; x <= x2; x++) p[x] = (uint16_t)v;
        } else {
            uint32_t *p = (uint32_t *)row;
            for (uint32_t x = x1; x <= x2; x++) p[x] = (p[x] & ~mask) | (v & mask);
        }
    }
}

void nv2a_kelvin(uint32_t method, uint32_t arg) {
    if (method >= 0x2000) return;
    if (rt_log_level >= 3) rt_log("nv2a: kelvin %04x = %08x\n", method, arg);
    nv2a.kelvin[method / 4] = arg;
    nv2a_raster_method(method, arg);
    switch (method) {
    case FLIP_INCREMENT_WRITE: {
        nv2a.flips++;
        nv2a_raster_flip(); /* the display gets its buffers at notifies (trap_method) */
        nv2a_raster_invalidate();
        uint32_t mod = nv2a.kelvin[FLIP_MODULO / 4];
        uint32_t w = nv2a.kelvin[FLIP_WRITE / 4] + 1;
        nv2a.kelvin[FLIP_WRITE / 4] = mod ? w % mod : w;
        return;
    }
    case FLIP_STALL:
        return;
    case BACK_END_WRITE_SEMAPHORE_RELEASE: {
        nv2a_raster_fence(); /* the GPU path reads back at flips, not at every fence; what is on its way lands */
        uint32_t dma = nv2a_lookup(nv2a.kelvin[SET_CONTEXT_DMA_SEMAPHORE / 4]);
        uint32_t base = nv2a_dma_base(dma, NULL);
        if (base == ~0u) {
            rt_log("nv2a: semaphore release without a semaphore DMA object\n");
            return;
        }
        uint32_t pa = base + nv2a.kelvin[SET_SEMAPHORE_OFFSET / 4];
        if (rt_log_level >= 2) rt_log("nv2a: semaphore %08x = %u\n", pa, arg);
        xb_wr32(RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)), arg);
        return;
    }
    case SET_BEGIN_END:
        if (arg) nv2a.draws++;
        return;
    case CLEAR_SURFACE:
        nv2a.clears++;
        if (nv2a_raster_clear(arg)) return;
        nv2a_raster_sync(); /* clears work on RAM */
        clear_color(arg);
        clear_zeta(arg);
        return;
    }
    if (rt_log_level && !(seen[method / 128] & (1u << (method / 4 % 32)))) {
        seen[method / 128] |= 1u << (method / 4 % 32);
        rt_log("nv2a: kelvin method %04x first used (= %08x)\n", method, arg);
    }
}
