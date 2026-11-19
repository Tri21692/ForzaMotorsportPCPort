/* D3D's LockRect, around Forza's own (HLE).
 *
 * The CPU is about to read or write a surface's or texture's texels. With
 * XBRT_GPU=gl what the GPU drew into them may still be on the GPU only
 * (glfill.c brings it to RAM at flips and when a texture looks at it), so
 * here it reaches RAM first, once the lock has waited for the GPU to be
 * done with the resource. A bought or repainted car's My Cars thumbnail is
 * drawn into a 128x64 surface that the CPU locks at once and compresses
 * into the profile's CarIcons1.xpr: it saved zeros, a black tile.
 *
 * The two wrappers are the game's, instruction for instruction: both pass
 * their arguments on to Lock2DSurface (0x3BF720). Only this executable's
 * addresses; any other gets the generated code.
 */
#include <stdlib.h>

#include "funcs.h"
#include "names.h"
#include "nv2a.h"
#include "rt.h"

#if defined(XB_FN_D3DSurface_LockRect) && defined(XB_FN_D3DTexture_LockRect) && XB_ADDR_D3DSurface_LockRect == 0x003B74B0u && \
    XB_ADDR_D3DTexture_LockRect == 0x003BBCF0u

/* The bytes a D3D resource's texels take: from Data, and Size for a linear
 * surface (width, height, pitch in 64-byte units) or Format for a
 * swizzled one (log2 width and height; four bytes a texel at most, and
 * the smaller levels after it take less again). */
static void resource_reads(uint32_t res) {
    uint32_t data = xb_rd32(res + 4), fmt = xb_rd32(res + 12), size = xb_rd32(res + 16);
    uint32_t n = size ? (((size >> 24) & 0xFF) + 1) * 64 * (((size >> 12) & 0xFFF) + 1)
                      : (1u << ((fmt >> 20) & 15)) * (1u << ((fmt >> 24) & 15)) * 4 * 2;
    nv2a_cpu_reads(data, n);
    static int log = -1; /* XBRT_LOCK_LOG=1: each lock, with the bytes it covers */
    if (log < 0) log = getenv("XBRT_LOCK_LOG") && atoi(getenv("XBRT_LOCK_LOG"));
    if (log) fprintf(stderr, "[%9.3f] lock %08x: data %08x, %u bytes, format %08x, size %08x\n", rt_now_100ns() / 1e7, res, data, n, fmt, size);
}

/* HRESULT D3DSurface_LockRect(D3DSurface *, D3DLOCKED_RECT *, const RECT *, DWORD Flags) */
void XB_FN_D3DSurface_LockRect(XbCtx *c) {
    uint32_t res = xb_rd32(c->esp + 4);
    uint32_t flags = xb_rd32(c->esp + 0x10), rect = xb_rd32(c->esp + 0xC), locked = xb_rd32(c->esp + 8);
    xb_push(c, flags), xb_push(c, rect), xb_push(c, locked), xb_push(c, 0), xb_push(c, 0), xb_push(c, res);
    xb_push(c, 0x003B74CDu);
    f_003BF720(c); /* Lock2DSurface(res, 0, 0, locked, rect, flags) */
    resource_reads(res);
    c->esp += 20;
}

/* HRESULT D3DTexture_LockRect(D3DTexture *, UINT Level, D3DLOCKED_RECT *, const RECT *, DWORD Flags) */
void XB_FN_D3DTexture_LockRect(XbCtx *c) {
    uint32_t res = xb_rd32(c->esp + 4), level = xb_rd32(c->esp + 8);
    uint32_t flags = xb_rd32(c->esp + 0x14), rect = xb_rd32(c->esp + 0x10), locked = xb_rd32(c->esp + 0xC);
    xb_push(c, flags), xb_push(c, rect), xb_push(c, locked), xb_push(c, level), xb_push(c, 0), xb_push(c, res);
    xb_push(c, 0x003BBD10u);
    f_003BF720(c); /* Lock2DSurface(res, 0, level, locked, rect, flags) */
    resource_reads(res);
    c->esp += 24;
}

#endif

/* Debugging: XBRT_BOT_LOG=<ms> logs each D3D_BlockOnTime (0x3BD550: wait until the GPU's GET passes a push-buffer
 * place) that took that long: the place, the game's write place and the GPU's GET and PUT going in and coming out,
 * and the caller (the race-start stutter, 8 Nov: the game spun in it with the GPU idle). */
void orig_f_003BD550(XbCtx *c);
void f_003BD550(XbCtx *c) {
    static int ms = -1;
    if (ms < 0) ms = getenv("XBRT_BOT_LOG") ? atoi(getenv("XBRT_BOT_LOG")) : 0;
    if (!ms) { orig_f_003BD550(c); return; }
    uint32_t from = xb_rd32(c->esp), time = xb_rd32(c->esp + 4), flags = xb_rd32(c->esp + 8);
    uint32_t dev = xb_rd32(0x3C8A48), put = xb_rd32(dev + 0x2C), gp = xb_rd32(dev + 0x30);
    uint32_t get0 = gp ? xb_hw_rd32(gp) : 0, hput0 = xb_mmio_read(RT_NV2A_BASE + 0x800040u, 4), cb = xb_rd32(dev + 0x19FC);
    uint64_t t0 = rt_now_100ns();
    orig_f_003BD550(c);
    uint64_t took = (rt_now_100ns() - t0) / 10000;
    if (took >= (uint64_t)ms)
        fprintf(stderr, "[%9.3f] BlockOnTime %llu ms from %08x: time %08x flags %x, game put %08x -> %08x, GET %08x -> %08x, PUT %08x -> %08x, callback %08x\n",
                rt_now_100ns() / 1e7, (unsigned long long)took, from, time, flags, put, xb_rd32(dev + 0x2C), get0, gp ? xb_hw_rd32(gp) : 0, hput0,
                xb_mmio_read(RT_NV2A_BASE + 0x800040u, 4), cb);
}
