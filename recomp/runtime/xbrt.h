/*
 * xbrt.h: what recompiled Xbox code needs from the runtime.
 *
 * Generated functions take the CPU state as an XbCtx and reach guest
 * memory through xb_mem, the host address of guest address 0. The runtime
 * reserves 4 GB (plus slack for accesses that straddle the top) so every
 * 32-bit guest address is valid and pointers inside the game need no
 * translation.
 *
 * Build generated code with -ffp-contract=off (an FMA rounds once where the
 * Pentium III rounds twice) and never with -ffast-math, which breaks the
 * NaN and signed-zero behaviour the SSE translation relies on.
 * -fno-math-errno lets sqrtf compile to a single sqrtss.
 */
#ifndef XBRT_H
#define XBRT_H

#include <stdint.h>
#include <string.h>

/* One SSE register: the Pentium III has SSE1, four floats per register. */
typedef union XbVec {
    float f[4];
    uint32_t u[4];
    uint64_t q[2];
} XbVec;

typedef struct XbCtx {
    uint32_t eax, ecx, edx, ebx, esp, ebp, esi, edi;
    uint32_t df;      /* direction flag: 0 up, 1 down */
    uint32_t fs_base; /* guest address the fs segment starts at */
    XbVec xmm[8];
    uint32_t mxcsr;   /* only stored and reloaded; rounding is the default */
} XbCtx;

extern uint8_t *xb_mem;

static inline uint8_t xb_rd8(uint32_t a) { return xb_mem[a]; }
static inline uint16_t xb_rd16(uint32_t a) { uint16_t v; memcpy(&v, xb_mem + a, 2); return v; }
static inline uint32_t xb_rd32(uint32_t a) { uint32_t v; memcpy(&v, xb_mem + a, 4); return v; }
static inline void xb_wr8(uint32_t a, uint8_t v) { xb_mem[a] = v; }
static inline void xb_wr16(uint32_t a, uint16_t v) { memcpy(xb_mem + a, &v, 2); }
static inline void xb_wr32(uint32_t a, uint32_t v) { memcpy(xb_mem + a, &v, 4); }

static inline float xb_rdf(uint32_t a) { float v; memcpy(&v, xb_mem + a, 4); return v; }
static inline void xb_wrf(uint32_t a, float v) { memcpy(xb_mem + a, &v, 4); }
static inline uint64_t xb_rd64(uint32_t a) { uint64_t v; memcpy(&v, xb_mem + a, 8); return v; }
static inline void xb_wr64(uint32_t a, uint64_t v) { memcpy(xb_mem + a, &v, 8); }
static inline XbVec xb_rdv(uint32_t a) { XbVec v; memcpy(&v, xb_mem + a, 16); return v; }
static inline void xb_wrv(uint32_t a, XbVec v) { memcpy(xb_mem + a, &v, 16); }

/* Float to int32 as cvttss2si/cvtss2si do: NaN and out-of-range give the
 * "integer indefinite" 0x80000000. */
static inline uint32_t xb_f2i_trunc(float f) {
    return (f >= -2147483648.0f && f < 2147483648.0f) ? (uint32_t)(int32_t)f : 0x80000000u;
}
static inline uint32_t xb_f2i_round(float f) {
    return (f >= -2147483648.0f && f < 2147483648.0f) ? (uint32_t)(int32_t)__builtin_rintf(f) : 0x80000000u;
}

static inline void xb_push(XbCtx *c, uint32_t v) { c->esp -= 4; xb_wr32(c->esp, v); }
static inline uint32_t xb_pop(XbCtx *c) { uint32_t v = xb_rd32(c->esp); c->esp += 4; return v; }

/* PF: set when the low byte has an even number of 1 bits. */
static inline uint32_t xb_parity(uint32_t v) { return !__builtin_parity(v & 0xFF); }

/* Leaving generated code. The runtime implements these. */
void xb_call_indirect(XbCtx *c, uint32_t target); /* call through a pointer */
void xb_kernel(XbCtx *c, uint32_t ordinal);       /* xboxkrnl.exe import */
void xb_trap(XbCtx *c, uint32_t addr, const char *why) __attribute__((noreturn));

#endif
