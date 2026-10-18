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
 *
 * x87 code is translated to long double, which gcc and clang on x86-64
 * implement with the x87 unit itself, so arithmetic matches the Pentium
 * III exactly provided the host FPU control word equals the game's (see
 * xb_fpu_setcw). This requires a compiler whose long double is the 80-bit
 * x87 format: gcc or clang, not MSVC.
 */
#ifndef XBRT_H
#define XBRT_H

#include <stdint.h>
#include <string.h>

/* Generated functions are weak: the runtime replaces library routines it
 * implements natively by defining the same symbol. */
#define XB_WEAK __attribute__((weak))

/* At every loop back-edge: re-read guest memory on the next iteration
 * (see recomp.go, jump). */
#define XB_LOOP() __asm__ volatile("" ::: "memory")

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
    long double st[8]; /* x87 physical registers R0-R7; ST(i) is st[(ftop + i) & 7] */
    uint32_t ftop;     /* x87 TOP */
    uint16_t fcw;      /* x87 control word, mirrored into the host FPU */
    uint16_t fsw;      /* x87 status word: condition codes C0-C3 */
} XbCtx;

extern uint8_t *xb_mem;

static inline uint8_t xb_rd8(uint32_t a) { return xb_mem[a]; }
static inline uint16_t xb_rd16(uint32_t a) { uint16_t v; memcpy(&v, xb_mem + a, 2); return v; }
static inline uint32_t xb_rd32(uint32_t a) { uint32_t v; memcpy(&v, xb_mem + a, 4); return v; }
static inline void xb_wr8(uint32_t a, uint8_t v) { xb_mem[a] = v; }
static inline void xb_wr16(uint32_t a, uint16_t v) { memcpy(xb_mem + a, &v, 2); }
static inline void xb_wr32(uint32_t a, uint32_t v) { memcpy(xb_mem + a, &v, 4); }

/* Device registers. Driver code (see Translator.HW) reaches hardware
 * through ordinary loads and stores; its accesses come here, and the GPU's
 * register range (0xFD000000-0xFDFFFFFF) goes to the runtime's model. */
uint32_t xb_mmio_read(uint32_t a, int bytes);
void xb_mmio_write(uint32_t a, int bytes, uint32_t v);
#define XB_IS_MMIO(a) __builtin_expect(((a) >> 24) == 0xFDu, 0)
static inline uint8_t xb_hw_rd8(uint32_t a) { return XB_IS_MMIO(a) ? (uint8_t)xb_mmio_read(a, 1) : xb_rd8(a); }
static inline uint16_t xb_hw_rd16(uint32_t a) { return XB_IS_MMIO(a) ? (uint16_t)xb_mmio_read(a, 2) : xb_rd16(a); }
static inline uint32_t xb_hw_rd32(uint32_t a) { return XB_IS_MMIO(a) ? xb_mmio_read(a, 4) : xb_rd32(a); }
static inline void xb_hw_wr8(uint32_t a, uint8_t v) { if (XB_IS_MMIO(a)) xb_mmio_write(a, 1, v); else xb_wr8(a, v); }
static inline void xb_hw_wr16(uint32_t a, uint16_t v) { if (XB_IS_MMIO(a)) xb_mmio_write(a, 2, v); else xb_wr16(a, v); }
static inline void xb_hw_wr32(uint32_t a, uint32_t v) { if (XB_IS_MMIO(a)) xb_mmio_write(a, 4, v); else xb_wr32(a, v); }

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

/* ---- x87 ---- */

#define XB_ST(i) (c->st[(c->ftop + (i)) & 7])

static inline void xb_fpush(XbCtx *c, long double v) { c->ftop = (c->ftop - 1) & 7; c->st[c->ftop] = v; }
static inline void xb_fpop(XbCtx *c) { c->ftop = (c->ftop + 1) & 7; }

static inline double xb_rdd(uint32_t a) { double v; memcpy(&v, xb_mem + a, 8); return v; }
static inline void xb_wrd(uint32_t a, double v) { memcpy(xb_mem + a, &v, 8); }
static inline long double xb_rdt(uint32_t a) { long double v = 0; memcpy(&v, xb_mem + a, 10); return v; }
static inline void xb_wrt(uint32_t a, long double v) { memcpy(xb_mem + a, &v, 10); }

/* Load the game's control word into the host FPU: precision and rounding
 * then apply to every long double operation, as they did on the Xbox. */
static inline void xb_fpu_setcw(XbCtx *c, uint16_t cw) {
    c->fcw = cw;
    __asm__ volatile("fldcw %0" : : "m"(cw));
}

/* Store as the x87 does, with the current rounding mode; NaN and
 * out-of-range values give the "integer indefinite" value. */
static inline int16_t xb_fist16(long double v) { int16_t r; __asm__("fists %0" : "=m"(r) : "t"(v)); return r; }
static inline int32_t xb_fist32(long double v) { int32_t r; __asm__("fistl %0" : "=m"(r) : "t"(v)); return r; }
static inline int64_t xb_fist64(long double v) {
    int64_t r;
    long double t = v;
    __asm__("fistpll %0" : "=m"(r) : "t"(t) : "st");
    return r;
}

/* One-operand x87 instructions run as themselves, so results match the
 * hardware rather than libm. */
#define XB_X87_UNARY(name, insn) \
    static inline long double name(long double x) { __asm__(insn : "+t"(x)); return x; }
XB_X87_UNARY(xb_fsqrt, "fsqrt")
XB_X87_UNARY(xb_frndint, "frndint")
XB_X87_UNARY(xb_fsin, "fsin")
XB_X87_UNARY(xb_fcos, "fcos")
XB_X87_UNARY(xb_f2xm1, "f2xm1")

#define XB_X87_CONST(name, insn) \
    static inline long double name(void) { long double x; __asm__(insn : "=t"(x)); return x; }
XB_X87_CONST(xb_fldpi, "fldpi")
XB_X87_CONST(xb_fldl2e, "fldl2e")
XB_X87_CONST(xb_fldl2t, "fldl2t")
XB_X87_CONST(xb_fldlg2, "fldlg2")
XB_X87_CONST(xb_fldln2, "fldln2")

/* st0 op st1 -> result left in st1 after a pop (fpatan, fyl2x, fyl2xp1). */
#define XB_X87_BINPOP(name, insn) \
    static inline long double name(long double st1, long double st0) { \
        long double r; __asm__(insn : "=t"(r) : "0"(st0), "u"(st1) : "st(1)"); return r; }
XB_X87_BINPOP(xb_fpatan, "fpatan")
XB_X87_BINPOP(xb_fyl2x, "fyl2x")
XB_X87_BINPOP(xb_fyl2xp1, "fyl2xp1")

/* fptan: tangent of st0; the instruction then pushes 1.0, which the
 * caller does. */
static inline long double xb_fptan(long double x) {
    long double one, r;
    __asm__("fptan" : "=t"(one), "=u"(r) : "0"(x));
    (void)one;
    return r;
}

/* fscale: st0 * 2^trunc(st1), st1 unchanged. */
static inline long double xb_fscale(long double st0, long double st1) {
    __asm__("fscale" : "+t"(st0) : "u"(st1));
    return st0;
}

/* fprem/fprem1: partial remainder; C2 set means the reduction is not done. */
static inline long double xb_fprem(XbCtx *c, long double st0, long double st1, int ieee) {
    uint16_t sw;
    if (ieee)
        __asm__("fprem1\n\tfnstsw %1" : "+t"(st0), "=am"(sw) : "u"(st1));
    else
        __asm__("fprem\n\tfnstsw %1" : "+t"(st0), "=am"(sw) : "u"(st1));
    c->fsw = (c->fsw & ~0x4700) | (sw & 0x4700);
    return st0;
}

/* Condition codes from a comparison: C0 less, C3 equal, all three unordered. */
static inline void xb_fcom(XbCtx *c, long double a, long double b) {
    uint16_t cc = (a != a || b != b) ? 0x4500 : a < b ? 0x0100 : a == b ? 0x4000 : 0;
    c->fsw = (c->fsw & ~0x4700) | cc;
}

/* fxam: classify st0. Empty registers are not tracked and read as values. */
static inline void xb_fxam(XbCtx *c, long double x) {
    uint16_t cc;
    switch (__builtin_fpclassify(0, 1, 2, 3, 4, x)) { /* nan inf normal subnormal zero */
    case 0: cc = 0x0100; break;          /* NaN: C0 */
    case 1: cc = 0x0500; break;          /* infinity: C2 C0 */
    case 2: cc = 0x0400; break;          /* normal: C2 */
    case 3: cc = 0x4400; break;          /* denormal: C3 C2 */
    default: cc = 0x4000; break;         /* zero: C3 */
    }
    if (__builtin_signbit(x)) cc |= 0x0200; /* C1: sign */
    c->fsw = (c->fsw & ~0x4700) | cc;
}

/* ---- MMX ----
 * MMX registers alias the x87 registers: MMi is the low 64 bits of
 * physical register Ri, a write sets Ri's exponent field to all ones, and
 * every MMX instruction resets TOP to 0. This is modelled as the hardware
 * does it, so code that mixes MMX and x87 behaves the same. */
typedef union XbMM {
    uint64_t q;
    uint32_t d[2];
    int32_t sd[2];
    uint16_t w[4];
    int16_t sw[4];
    uint8_t b[8];
    int8_t sb[8];
} XbMM;

static inline uint64_t xb_mmr(XbCtx *c, int i) { uint64_t v; memcpy(&v, &c->st[i], 8); return v; }
static inline void xb_mmw(XbCtx *c, int i, uint64_t v) {
    uint16_t e = 0xFFFF;
    memcpy(&c->st[i], &v, 8);
    memcpy((uint8_t *)&c->st[i] + 8, &e, 2);
}

static inline int8_t xb_sat_s8(int32_t v) { return v > 127 ? 127 : v < -128 ? -128 : (int8_t)v; }
static inline uint8_t xb_sat_u8(int32_t v) { return v > 255 ? 255 : v < 0 ? 0 : (uint8_t)v; }
static inline int16_t xb_sat_s16(int32_t v) { return v > 32767 ? 32767 : v < -32768 ? -32768 : (int16_t)v; }
static inline uint16_t xb_sat_u16(int32_t v) { return v > 65535 ? 65535 : v < 0 ? 0 : (uint16_t)v; }

static inline uint16_t xb_fnstsw(XbCtx *c) { return (uint16_t)((c->fsw & ~0x3800) | ((c->ftop & 7) << 11)); }

static inline void xb_push(XbCtx *c, uint32_t v) { c->esp -= 4; xb_wr32(c->esp, v); }
static inline uint32_t xb_pop(XbCtx *c) { uint32_t v = xb_rd32(c->esp); c->esp += 4; return v; }

/* PF: set when the low byte has an even number of 1 bits. */
static inline uint32_t xb_parity(uint32_t v) { return !__builtin_parity(v & 0xFF); }

/* Tables the translator generates for the runtime. */
typedef struct { uint32_t addr; void (*fn)(XbCtx *); } XbFuncEntry;
extern const XbFuncEntry xb_funcs[];       /* sorted by addr */
extern const unsigned xb_func_count;

/* conv: 0 stdcall, 1 fastcall, 2 cdecl, 3 data (as xbe.CallConv). */
typedef struct { uint32_t ordinal; const char *name; uint8_t conv, argbytes; } XbKernelInfo;
extern const XbKernelInfo xb_kernel_info[]; /* sorted by ordinal */
extern const unsigned xb_kernel_info_count;

/* Leaving generated code. The runtime implements these. */
void xb_call_indirect(XbCtx *c, uint32_t target); /* call through a pointer */
void xb_kernel(XbCtx *c, uint32_t ordinal);       /* xboxkrnl.exe import */
void xb_trap(XbCtx *c, uint32_t addr, const char *why) __attribute__((noreturn));
uint64_t xb_rdtsc(XbCtx *c);                       /* the game's view of the CPU clock */
uint32_t xb_io_in(XbCtx *c, uint32_t port, int bytes); /* port I/O */
void xb_io_out(XbCtx *c, uint32_t port, int bytes, uint32_t v);

#endif
