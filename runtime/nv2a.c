/* The NV2A, the Xbox's GPU, as far as its driver (the recompiled D3D)
 * sees it.
 *
 * D3D runs unchanged and talks to the GPU the way it does on the console:
 * it writes registers at 0xFD000000 and builds a push buffer of GPU
 * methods in RAM. Its register accesses arrive at xb_mmio_read/write (the
 * recompiler routes driver code's memory accesses through a range check),
 * which give the registers their hardware behaviour: interrupt status bits
 * clear when written with ones, the timer counts, flushes complete. Every
 * other register is plain storage. A device thread runs the push buffer
 * from GET up to PUT whenever PUT moves, and raises the vertical blank.
 *
 * Register offsets, the push buffer format and the instance memory
 * structures (RAMHT, DMA objects) are the ones the nouveau project
 * documents for NV04-NV2x GPUs.
 */
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "rt.h"
#include "nv2a.h"
#include "gl.h"

#define REG(off) (*(volatile uint32_t *)(xb_mem + RT_NV2A_BASE + (off)))
#define RAMIN(off) (*(volatile uint32_t *)(xb_mem + RT_NV2A_BASE + 0x700000 + (off)))

/* ---- registers ---- */
#define PMC_BOOT_0 0x000000
#define PMC_INTR_0 0x000100
#define PMC_INTR_EN_0 0x000140
#define PMC_INTR_PFIFO (1u << 8)
#define PMC_INTR_PGRAPH (1u << 12)
#define PMC_INTR_PCRTC (1u << 24)

#define PFIFO_INTR_0 0x002100
#define PTIMER_INTR_0 0x009100
#define PFIFO_RUNOUT_STATUS 0x002400
#define PFIFO_RAMHT 0x002210
#define PFIFO_CACHE1_PUSH1 0x003204
#define PFIFO_CACHE1_STATUS 0x003214
#define PFIFO_CACHE1_DMA_PUSH 0x003220
#define PFIFO_CACHE1_DMA_STATE 0x003228
#define PFIFO_CACHE1_DMA_INSTANCE 0x00322C
#define PFIFO_CACHE1_DMA_PUT 0x003240
#define PFIFO_CACHE1_DMA_GET 0x003244
#define PFIFO_CACHE1_REF 0x003248
#define PFIFO_CACHE1_DMA_SUBROUTINE 0x00324C

#define PTIMER_NUMERATOR 0x009200
#define PTIMER_DENOMINATOR 0x009210
#define PTIMER_TIME_0 0x009400
#define PTIMER_TIME_1 0x009410

#define PFB_CFG0 0x100200
#define PFB_CSTATUS 0x10020C
#define PFB_WBC 0x100410
#define PFB_WBC_FLUSH (1u << 16)

#define PGRAPH_INTR 0x400100
#define PGRAPH_INTR_ERROR (1u << 20)
#define PGRAPH_NSOURCE 0x400108
#define PGRAPH_NSOURCE_NOTIFICATION (1u << 0)
#define PGRAPH_CTX_USER 0x400148
#define PGRAPH_STATUS 0x400700
#define PGRAPH_TRAPPED_ADDR 0x400704
#define PGRAPH_TRAPPED_DATA_LOW 0x400708

#define PVIDEO_BUFFER 0x008700 /* video overlay: buffers queued for display */
#define PVIDEO_STOP 0x008704

#define PCRTC_INTR_0 0x600100
#define PCRTC_INTR_EN_0 0x600140
#define PCRTC_START 0x600800

/* The buffers D3D has pointed the CRTC at: a trapped notify may make its
 * vertical blank handler show one of them. */
static uint32_t scanout[4];

#define PRAMDAC_NVPLL 0x680500
#define PRAMDAC_MPLL 0x680504
#define PRAMDAC_VPLL 0x680508

#define USER_DMA_PUT 0x800040
#define USER_DMA_GET 0x800044
#define USER_REF 0x800048

#define GPU_IRQ 3

/* ---- state ---- */

Nv2a nv2a;

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER; /* registers with effects */
static struct { uint32_t put, get; } recent_put[64];      /* PUT writes, and GET then */
static unsigned recent_put_n;
uint64_t pusher_t_busy; /* 100 ns units the device thread spent in run_pushbuf */
static uint64_t trap_t_wait; /* ... of which waiting for the driver's ISR after a trapped method */
static pthread_cond_t kick = PTHREAD_COND_INITIALIZER;   /* PUT moved */
static uint64_t start_ns;

/* ---- instance memory ---- */

/* Look an object handle up in the hash table. A linear search finds the
 * same entry the hardware's hash would, and needs no hash. Returns the
 * object's offset in instance memory, or ~0. The entries found last are
 * remembered, and used while they still hold the handle: draws look up
 * their DMA objects many times each (every vertex attribute), and the
 * search of a 4096-entry table was a few percent of the device thread. */
uint32_t nv2a_lookup(uint32_t handle) {
    static struct { uint32_t handle, e; } recent[16];
    uint32_t ramht = REG(PFIFO_RAMHT);
    uint32_t base = ((ramht >> 4) & 0x1F) << 12, size = 0x1000u << ((ramht >> 16) & 3);
    unsigned slot = (handle * 2654435761u) >> 28;
    uint32_t e = recent[slot].e;
    if (recent[slot].handle == handle && e >= base && e < base + size && RAMIN(e) == handle && (RAMIN(e + 4) & 0x80000000u))
        return (RAMIN(e + 4) & 0xFFFF) << 4;
    for (e = base; e < base + size; e += 8) {
        if (RAMIN(e) == handle && (RAMIN(e + 4) & 0x80000000u)) {
            recent[slot].handle = handle, recent[slot].e = e;
            return (RAMIN(e + 4) & 0xFFFF) << 4;
        }
    }
    return ~0u;
}

/* A DMA object: class and adjust in word 0, limit in word 1, page frame in
 * word 2. Returns the physical address of offset 0, or ~0. */
uint32_t nv2a_dma_base(uint32_t inst, uint32_t *limit) {
    if (inst == ~0u) return ~0u;
    uint32_t w0 = RAMIN(inst), w2 = RAMIN(inst + 8);
    if (limit) *limit = RAMIN(inst + 4);
    return (w2 & 0xFFFFF000u) | (w0 >> 20);
}

static inline uint8_t *phys(uint32_t pa) { return xb_mem + RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)); }

/* ---- interrupts ---- */

/* PMC_INTR_0 summarises the units' status registers; the interrupt line
 * is level-triggered, so this runs after every change and after each ISR.
 * Called with lock held. */
static void update_irq(void) {
    uint32_t pending = 0;
    if (REG(PGRAPH_INTR)) pending |= PMC_INTR_PGRAPH;
    if (REG(PCRTC_INTR_0) & REG(PCRTC_INTR_EN_0)) pending |= PMC_INTR_PCRTC;
    if (REG(PFIFO_INTR_0)) pending |= PMC_INTR_PFIFO;
    REG(PMC_INTR_0) = pending;
    if (pending && (REG(PMC_INTR_EN_0) & 1)) rt_interrupt_raise(0x30 + GPU_IRQ);
}

static void after_isr(void) {
    pthread_mutex_lock(&lock);
    update_irq();
    pthread_mutex_unlock(&lock);
}

/* ---- registers ---- */

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

/* Debugging: XBRT_FRAME_TRACE=<file> writes a timeline, one event a line
 * as "<ms> <event> <arg>": V vertical blank, P the game moves PUT, S a
 * flip stall starts, R D3D's handler releases it, F a flip, W/w the device
 * thread starts/stops waiting for work. Written once a second from the
 * device thread. */
static struct { uint64_t t; char c; uint32_t a; } tr_ring[1 << 18];
static uint32_t tr_n, tr_done;
static int tr_on;
static FILE *tr_file;

void nv2a_trace(char what, uint32_t arg) {
    if (!tr_on) return;
    uint32_t i = __atomic_fetch_add(&tr_n, 1, __ATOMIC_RELAXED) & ((1 << 18) - 1);
    tr_ring[i].t = now_ns(), tr_ring[i].c = what, tr_ring[i].a = arg;
}

static void trace_write(void) {
    uint32_t n = __atomic_load_n(&tr_n, __ATOMIC_ACQUIRE);
    if (n - tr_done > (1 << 18)) tr_done = n - (1 << 18);
    for (; tr_done < n; tr_done++) {
        uint32_t i = tr_done & ((1 << 18) - 1);
        fprintf(tr_file, "%.3f %c %u\n", (tr_ring[i].t - start_ns) / 1e6, tr_ring[i].c, tr_ring[i].a);
    }
    fflush(tr_file);
}

/* PTIMER runs at the core clock scaled by NUMERATOR / DENOMINATOR, which
 * D3D programs. */
static uint64_t ptimer(void) {
    uint64_t num = REG(PTIMER_NUMERATOR), den = REG(PTIMER_DENOMINATOR);
    if (!num || !den) num = den = 1;
    unsigned __int128 t = (unsigned __int128)(now_ns() - start_ns) * 233333324u * num;
    return (uint64_t)(t / (1000000000u * den));
}

uint32_t xb_mmio_read(uint32_t a, int bytes) {
    if (a - RT_APU_BASE < RT_APU_SIZE) return rt_apu_read(a - RT_APU_BASE, bytes);
    if (a - RT_ACI_BASE < RT_ACI_SIZE) return rt_aci_read(a - RT_ACI_BASE, bytes);
    if (a - RT_NV2A_BASE >= 0x01000000u) { /* other devices: plain storage until modelled */
        if (bytes == 4) return xb_rd32(a);
        return bytes == 2 ? xb_rd16(a) : xb_rd8(a);
    }
    uint32_t off = a - RT_NV2A_BASE;
    switch (off) {
    case PTIMER_TIME_0:
        return (uint32_t)(ptimer() << 5);
    case PTIMER_TIME_1:
        return (uint32_t)(ptimer() >> 27) & 0x1FFFFFFF;
    case PVIDEO_STOP:
        return 0;
    case USER_DMA_GET:
        return REG(PFIFO_CACHE1_DMA_GET);
    }
    if (rt_log_level) { /* registers read as plain storage: name the new ones */
        static uint8_t seen[0x1000000 / 4 / 8];
        uint32_t i = off / 4;
        if (!(seen[i / 8] & (1u << (i % 8)))) {
            seen[i / 8] |= 1u << (i % 8);
            rt_log("nv2a: register %06x first read (= %08x)\n", off, REG(off & ~3u));
        }
    }
    if (bytes == 4) return REG(off);
    if (bytes == 2) return *(volatile uint16_t *)(xb_mem + a);
    return *(volatile uint8_t *)(xb_mem + a);
}

void xb_mmio_write(uint32_t a, int bytes, uint32_t v) {
    if (a - RT_APU_BASE < RT_APU_SIZE) {
        rt_apu_write(a - RT_APU_BASE, bytes, v);
        return;
    }
    if (a - RT_ACI_BASE < RT_ACI_SIZE) {
        rt_aci_write(a - RT_ACI_BASE, bytes, v);
        return;
    }
    if (a - RT_NV2A_BASE >= 0x01000000u) { /* other devices: plain storage until modelled */
        if (bytes == 4) xb_wr32(a, v);
        else if (bytes == 2) xb_wr16(a, (uint16_t)v);
        else xb_wr8(a, (uint8_t)v);
        return;
    }
    uint32_t off = a - RT_NV2A_BASE;
    if (bytes != 4) { /* nothing with effects is written in parts */
        if (bytes == 2) *(volatile uint16_t *)(xb_mem + a) = (uint16_t)v;
        else *(volatile uint8_t *)(xb_mem + a) = (uint8_t)v;
        return;
    }
    pthread_mutex_lock(&lock);
    switch (off) {
    case PFIFO_INTR_0:
    case PTIMER_INTR_0:
    case PGRAPH_INTR:
    case PCRTC_INTR_0: /* write one to clear */
        REG(off) &= ~v;
        update_irq();
        if (off == PGRAPH_INTR) pthread_cond_broadcast(&kick); /* a trapped method may resume */
        break;
    case PMC_INTR_EN_0:
    case PCRTC_INTR_EN_0:
        REG(off) = v;
        update_irq();
        break;
    case 0x40071C: /* NV_PGRAPH_INCREMENT: bit 1 moves FLIP_READ on (D3D does at vertical blanks) */
        if (v & 2) {
            uint32_t mod = nv2a.kelvin[0x128 / 4], r = nv2a.kelvin[0x120 / 4] + 1;
            nv2a.kelvin[0x120 / 4] = mod ? r % mod : r;
            if (nv2a.flip_stall) nv2a_trace('R', 0);
            nv2a.flip_stall = 0;
            pthread_cond_signal(&kick);
        }
        REG(off) = v;
        break;
    case PFB_WBC: /* write-back cache flush: done at once */
        __atomic_thread_fence(__ATOMIC_SEQ_CST);
        REG(off) = v & ~PFB_WBC_FLUSH;
        break;
    case USER_DMA_PUT:
    case PFIFO_CACHE1_DMA_PUT:
        recent_put[recent_put_n % 64].put = v, recent_put[recent_put_n % 64].get = REG(PFIFO_CACHE1_DMA_GET);
        recent_put_n++;
        nv2a_trace('P', v);
        REG(USER_DMA_PUT) = v;
        REG(PFIFO_CACHE1_DMA_PUT) = v;
        pthread_cond_signal(&kick);
        break;
    case PTIMER_TIME_0:
    case PTIMER_TIME_1:
        break; /* nobody sets the clock */
    case PCRTC_START: { /* remember the buffers scanned out (two or three, alternating) */
        int i = 0;
        while (i < 4 && scanout[i] && scanout[i] != v) i++;
        if (i == 4) {
            memmove(scanout, scanout + 1, 3 * sizeof *scanout);
            i = 3;
        }
        scanout[i] = v;
        REG(off) = v;
        break;
    }
    case PVIDEO_STOP: /* bit 0 tears the overlay down, as xemu has it; D3D waits for the buffers to drain */
        if (v & 1) REG(PVIDEO_BUFFER) = 0;
        break;
    default:
        REG(off) = v;
    }
    pthread_mutex_unlock(&lock);
}

/* ---- the push buffer ---- */

/* The latest control words (jumps, calls, returns), for the report when a
 * push buffer goes wrong. */
static struct { uint32_t get, put, count, method, end; } recent_pass[64]; /* reader passes */
static unsigned recent_pass_n;
static struct { uint32_t at, word, put; } recent_ctl[16];
static unsigned recent_n;
/* XBRT_PB_TRACE=<file>: every word parsed, the last 65536 of them, written
 * out at the first bad word (debugging the reader losing sync). */
static struct { uint32_t at, word, count; } pb_ring[65536];
static unsigned pb_n;

/* Runs the push buffer from GET towards PUT, as xemu's pusher does: PUT is
 * read again before every word (D3D keeps kicking while a long pass runs)
 * and GET is published as it moves. A jump to itself parks the GPU until
 * PUT moves; that returns 0, so the device thread goes back to its timed
 * wait (and keeps raising vertical blanks) instead of spinning here. */
static uint64_t vblank_due; /* when the device loop raises the next vertical blank */

static int run_pushbuf(void) {
    uint32_t put = REG(PFIFO_CACHE1_DMA_PUT), get = REG(PFIFO_CACHE1_DMA_GET);
    if (get == put || nv2a.flip_stall) return 0; /* a flip stall parks like a jump to itself */
    int parked = 0;
    uint32_t limit = 0;
    uint32_t base = nv2a_dma_base(REG(PFIFO_CACHE1_DMA_INSTANCE) << 4, &limit);
    if (base == ~0u) base = 0;
    uint32_t method = nv2a.method, subch = nv2a.subch, count = nv2a.count, ni = nv2a.ni;
    unsigned pass = recent_pass_n++ % 64;
    recent_pass[pass].get = get, recent_pass[pass].put = put, recent_pass[pass].count = count, recent_pass[pass].method = method;
    recent_pass[pass].end = 0;
    static int tracing = -1;
    if (tracing < 0) tracing = getenv("XBRT_PB_TRACE") != NULL;
    int guard = 0;
    while (guard++ < 1 << 16) { /* then back to the device loop, which raises vertical blanks */
        REG(PFIFO_CACHE1_DMA_GET) = get;
        REG(USER_DMA_GET) = get;
        put = REG(PFIFO_CACHE1_DMA_PUT);
        if (get == put) break;
        if (!(guard & 127) && now_ns() >= vblank_due) break; /* a long pass let vertical blanks slip to ~45 Hz: the game's clock */
        uint32_t word = *(volatile uint32_t *)phys(base + get);
        if (tracing) {
            pb_ring[pb_n % 65536].at = get, pb_ring[pb_n % 65536].word = word, pb_ring[pb_n % 65536].count = count;
            pb_n++;
        }
        get += 4;
        if (count) { /* a parameter */
            nv2a_method(subch, method, word);
            if (!ni) method += 4;
            count--;
            if (nv2a.flip_stall) { /* FLIP_STALL: back to the device loop, which raises vertical blanks */
                parked = 1;
                break;
            }
            continue;
        }
        if (rt_log_level >= 2 && ((word & 0xE0000003u) == 0x20000000u || (word & 3)))
            rt_log("nv2a: push buffer %08x: %08x\n", get - 4, word);
        if ((word & 0xE0000003u) == 0x20000000u || (word & 3) || word == 0x00020000u) {
            recent_ctl[recent_n % 16].at = get - 4, recent_ctl[recent_n % 16].word = word, recent_ctl[recent_n % 16].put = put;
            recent_n++;
        }
        if ((word & 0xE0000003u) == 0x20000000u) { /* old-style jump */
            get = word & 0x1FFFFFFFu;
        } else if ((word & 3) == 1) { /* jump */
            if ((word & ~3u) == get - 4) { /* to itself: park here until PUT moves */
                get -= 4;
                parked = 1;
                break;
            }
            get = word & ~3u;
        } else if ((word & 3) == 2) { /* call */
            REG(PFIFO_CACHE1_DMA_SUBROUTINE) = get | 1;
            get = word & ~3u;
        } else if (word == 0x00020000u) { /* return */
            get = REG(PFIFO_CACHE1_DMA_SUBROUTINE) & ~3u;
            REG(PFIFO_CACHE1_DMA_SUBROUTINE) = 0;
        } else if ((word & 0xE0030003u) == 0 || (word & 0xE0030003u) == 0x40000000u) {
            method = word & 0x1FFF;
            subch = (word >> 13) & 7;
            count = (word >> 18) & 0x7FF;
            ni = (word & 0x40000000u) != 0;
        } else {
            static int reported;
            if (!reported++) {
                fprintf(stderr, "xbrt: bad push buffer word %08x at %08x (base %08x, put %08x); latest control words:\n", word, get - 4,
                        base, put);
                for (unsigned i = recent_n > 16 ? recent_n - 16 : 0; i < recent_n; i++)
                    fprintf(stderr, "  at %08x: %08x (put %08x)\n", recent_ctl[i % 16].at, recent_ctl[i % 16].word, recent_ctl[i % 16].put);
                fprintf(stderr, "  latest PUT writes (put, get then):");
                for (unsigned i = recent_put_n > 64 ? recent_put_n - 64 : 0; i < recent_put_n; i++)
                    fprintf(stderr, "%s%08x/%08x", (i % 6) ? " " : "\n    ", recent_put[i % 64].put, recent_put[i % 64].get);
                fprintf(stderr, "\n  latest passes (get, put, count, method, end):");
                for (unsigned i = recent_pass_n > 64 ? recent_pass_n - 64 : 0; i < recent_pass_n; i++)
                    fprintf(stderr, "\n    %08x %08x %u %04x %08x", recent_pass[i % 64].get, recent_pass[i % 64].put,
                            recent_pass[i % 64].count, recent_pass[i % 64].method, recent_pass[i % 64].end);
                fprintf(stderr, "\n");
                uint32_t last = recent_ctl[(recent_n - 1) % 16].at;
                fprintf(stderr, "  words before %08x:", last);
                for (uint32_t a = last - 0x100; a <= last; a += 4)
                    fprintf(stderr, "%s%08x", (a - (last - 0x100)) % 32 ? " " : "\n    ", *(volatile uint32_t *)phys(base + a));
                fprintf(stderr, "\n");
                const char *path = getenv("XBRT_PB_TRACE");
                FILE *f = path ? fopen(path, "w") : NULL;
                if (f) {
                    for (unsigned i = pb_n > 65536 ? pb_n - 65536 : 0; i < pb_n; i++)
                        fprintf(f, "%08x %08x %u\n", pb_ring[i % 65536].at, pb_ring[i % 65536].word, pb_ring[i % 65536].count);
                    fclose(f);
                }
            }
            rt_log("nv2a: bad push buffer word %08x at %08x (base %08x, put %08x, instance %08x)\n", word, get - 4, base, put, REG(PFIFO_CACHE1_DMA_INSTANCE));
        }
    }
    nv2a.method = method, nv2a.subch = subch, nv2a.count = count, nv2a.ni = ni;
    recent_pass[pass].end = get;
    nv2a_raster_flush();
    REG(PFIFO_CACHE1_DMA_GET) = get;
    REG(USER_DMA_GET) = get;
    return !parked;
}

/* Hand a method to the driver's interrupt handler, as PGRAPH does for a
 * NO_OPERATION with a nonzero parameter: record it in TRAPPED_ADDR/DATA,
 * raise the ERROR interrupt, and stall the push buffer until the ISR
 * clears it. D3D's BlockOnTime waits for this (D3D sets an event in the
 * ISR). Layout as xemu has it; runs on the device thread. */
static void trap_method(uint32_t subch, uint32_t method, uint32_t arg) {
    nv2a_raster_flush();
    /* D3D's notify after a frame's last draw into its front buffer tells
     * the vertical blank handler that the frame can be shown, well before
     * the frame's FLIP_INCREMENT_WRITE (shadow maps and the like for the
     * next frame come in between). Drawing on the GPU reaches RAM at
     * flips, so the CRTC could be pointed at a front buffer that RAM still
     * held mid-frame: a frame's environment pass and its bloom passes in
     * the top-left quarter, black, held for seconds during loads. What the
     * GPU drew over the scanout buffers goes to RAM before the driver sees
     * the notify, as it would have on the hardware. */
    uint32_t size = (rt_display_pitch ? rt_display_pitch : 640 * 4) * 480;
    for (int i = 0; i < 4; i++)
        if (scanout[i]) nv2a_raster_sync_range(scanout[i], size);
    uint64_t t0 = rt_now_100ns();
    pthread_mutex_lock(&lock);
    uint32_t chid = (REG(PGRAPH_CTX_USER) >> 24) & 0x1F;
    REG(PGRAPH_TRAPPED_ADDR) = chid << 20 | subch << 16 | (method & 0x1FFF);
    REG(PGRAPH_TRAPPED_DATA_LOW) = arg;
    REG(PGRAPH_NSOURCE) = PGRAPH_NSOURCE_NOTIFICATION;
    REG(PGRAPH_INTR) |= PGRAPH_INTR_ERROR;
    update_irq();
    nv2a.traps++;
    if (rt_log_level >= 2) rt_log("nv2a: trapped method %04x = %08x\n", method, arg);
    while (REG(PGRAPH_INTR) & PGRAPH_INTR_ERROR) {
        struct timespec ts;
        rt_abstime(&ts, 100000000); /* 100 ms; say so if the driver never answers */
        if (pthread_cond_timedwait(&kick, &lock, &ts) != 0 && (REG(PGRAPH_INTR) & PGRAPH_INTR_ERROR))
            rt_log("nv2a: still waiting for the driver to clear PGRAPH_INTR (%08x)\n", REG(PGRAPH_INTR));
    }
    pthread_mutex_unlock(&lock);
    trap_t_wait += rt_now_100ns() - t0;
}

/* Channel methods (below 0x100) are PFIFO's own; the rest go to the
 * object bound to the subchannel. */
/* Debugging: XBRT_GPU_DUMP=<file>:<first flip>:<flips> writes every method
 * from that flip on, for that many flips, as "flip class method value". */
static void dump_method(uint32_t subch, uint32_t method, uint32_t arg) {
    static FILE *f;
    static int state; /* 0 unparsed, 1 armed, 2 off */
    static uint32_t first, count;
    if (state == 0) {
        const char *e = getenv("XBRT_GPU_DUMP");
        char path[512];
        state = 2;
        if (e && sscanf(e, "%511[^:]:%u:%u", path, &first, &count) == 3 && (f = fopen(path, "w"))) state = 1;
    }
    if (state != 1 || nv2a.flips < first) return;
    if (nv2a.flips >= first + count) {
        fclose(f);
        state = 2;
        return;
    }
    fprintf(f, "%u %02x %04x %08x\n", nv2a.flips, nv2a.class_[subch], method, arg);
}

void nv2a_method(uint32_t subch, uint32_t method, uint32_t arg) {
    dump_method(subch, method, arg);
    if (method == 0) {
        nv2a.object[subch] = arg;
        uint32_t inst = nv2a_lookup(arg);
        nv2a.class_[subch] = inst == ~0u ? 0 : RAMIN(inst) & 0xFF;
        if (rt_log_level) rt_log("nv2a: subchannel %u = object %08x, class %02x\n", subch, arg, nv2a.class_[subch]);
        return;
    }
    if (method < 0x100) {
        switch (method) {
        case 0x50: /* SET_REFERENCE */
            REG(PFIFO_CACHE1_REF) = arg;
            REG(USER_REF) = arg;
            return;
        }
        if (rt_log_level >= 2) rt_log("nv2a: channel method %03x = %08x (subchannel %u)\n", method, arg, subch);
        return;
    }
    switch (nv2a.class_[subch]) {
    case 0x97:
        if (method == 0x100 && arg) { /* NO_OPERATION with a parameter: a notify for the driver */
            trap_method(subch, method, arg);
            return;
        }
        nv2a_kelvin(method, arg);
        return;
    case 0x44: /* image pattern: SET_MONOCHROME_COLOR0 lands in PGRAPH's PATT_COLOR0 */
        if (method == 0x310) REG(0x400B10) = arg;
        return;
    }
    if (rt_log_level >= 2) rt_log("nv2a: class %02x (subchannel %u) method %04x = %08x\n", nv2a.class_[subch], subch, method, arg);
}

/* ---- recording ----
 * XBRT_RECORD=<file.mp4>: what the TV shows at every vertical blank, from
 * XBRT_RECORD_FROM seconds (default 0) for XBRT_RECORD_FOR seconds (default
 * 15), piped into ffmpeg (XBRT_FFMPEG, default "ffmpeg") as H.264 at 59.94
 * fps, scaled 2x. Taken after the read-backs land, before D3D's handler can
 * move the CRTC: the frame on screen during that blank. */
static void record_vblank(void) {
    static int state; /* 0 not set up, 1 waiting or recording, 2 done or off */
    static FILE *pipe;
    static double from, len;
    static uint32_t px[RT_DISPLAY_MAX], out[RT_DISPLAY_MAX];
    static int rw, rh; /* the recording's size: twice 640x480, or the drawn resolution when larger */
    if (state == 2) return;
    if (state == 0) {
        const char *out = getenv("XBRT_RECORD");
        if (!out || !*out) {
            state = 2;
            return;
        }
        from = getenv("XBRT_RECORD_FROM") ? atof(getenv("XBRT_RECORD_FROM")) : 0;
        len = getenv("XBRT_RECORD_FOR") ? atof(getenv("XBRT_RECORD_FOR")) : 15;
        state = 1;
    }
    double now = rt_now_100ns() / 1e7;
    if (now < from) return;
    if (!pipe) {
        const char *ff = getenv("XBRT_FFMPEG");
        char cmd[2048];
        int w, h;
        rt_display_compose_best(px, &w, &h);
        rw = w > 1280 ? w : 1280, rh = h > 960 ? h : 960;
        snprintf(cmd, sizeof cmd,
                 "\"\"%s\" -loglevel error -y -f rawvideo -pix_fmt bgra -s %dx%d -r 60000/1001 -i - "
                 "-c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p \"%s\"\"",
                 ff && *ff ? ff : "ffmpeg", rw, rh, getenv("XBRT_RECORD"));
#ifdef _WIN32
        pipe = _popen(cmd, "wb");
#else
        pipe = popen(cmd, "w");
#endif
        if (!pipe) {
            fprintf(stderr, "xbrt: XBRT_RECORD: cannot start ffmpeg\n");
            state = 2;
            return;
        }
        fprintf(stderr, "xbrt: recording to %s\n", getenv("XBRT_RECORD"));
    }
    if (now >= from + len) {
#ifdef _WIN32
        _pclose(pipe);
#else
        pclose(pipe);
#endif
        fprintf(stderr, "xbrt: recording finished\n");
        state = 2;
        return;
    }
    int w, h;
    rt_display_compose_best(px, &w, &h);
    for (int y = 0; y < rh; y++) /* nearest: the 640x480 picture (menus, movies) doubled */
        for (int x = 0; x < rw; x++) out[y * rw + x] = px[(y * h / rh) * w + x * w / rw];
    fwrite(out, 4, (size_t)rw * rh, pipe);
}

/* ---- the device thread ---- */

static void *device_main(void *arg) {
    (void)arg;
    const char *gpu = getenv("XBRT_GPU");
    if (gpu && !strcmp(gpu, "gl")) rt_gl_init(); /* the context lives on this thread */
    uint64_t next_vblank = now_ns() + 16683333;
    vblank_due = next_vblank;
    pthread_mutex_lock(&lock);
    for (;;) {
        uint64_t t = now_ns();
        if (t >= next_vblank) {
            next_vblank += 16683333; /* 59.94 Hz */
            if (t > next_vblank) next_vblank = t + 16683333;
            vblank_due = next_vblank;
            nv2a.vblanks++;
            nv2a_trace('V', nv2a.vblanks);
            /* A blank shows one waiting frame: a stalled one may go on (kelvin.c, FLIP_STALL). */
            if (nv2a.queued) nv2a.queued--;
            if (nv2a.flip_stall && nv2a.queued < 2) nv2a.flip_stall = 0, nv2a_trace('R', 1);
            if (tr_on && nv2a.vblanks % 60 == 0) trace_write();
            { /* XBRT_RAM_DUMP=<file>:<seconds>: the 64 MB of RAM, once (debugging) */
                static const char *spec;
                static int checked;
                if (!checked) checked = 1, spec = getenv("XBRT_RAM_DUMP");
                const char *colon = spec ? strrchr(spec, ':') : NULL;
                if (colon && nv2a.vblanks == (uint32_t)(atof(colon + 1) * 60)) {
                    char path[1024];
                    snprintf(path, sizeof path, "%.*s", (int)(colon - spec), spec);
                    FILE *f = fopen(path, "wb");
                    if (f) fwrite(xb_mem + RT_PHYS_VIEW, 1, RT_PHYS_SIZE, f), fclose(f);
                    rt_log("nv2a: RAM dumped to %s\n", path);
                }
            }
            if (0)
                rt_log("nv2a: %u vblanks, %u flips, %u draws (%u skipped), %u clears, %u traps; get %08x put %08x, "
                       "PATT_COLOR0 %08x, intr %08x\n", nv2a.vblanks, nv2a.flips, nv2a.draws, nv2a.skipped, nv2a.clears,
                       nv2a.traps, REG(PFIFO_CACHE1_DMA_GET), REG(PFIFO_CACHE1_DMA_PUT), REG(0x400B10), REG(PGRAPH_INTR));
            nv2a_raster_vblank(); /* before D3D's handler can point the CRTC at them */
            nv2a_raster_present(REG(PCRTC_START));
            record_vblank();
            REG(PCRTC_INTR_0) |= 1;
            update_irq();
        }
        nv2a_raster_poll();
        if (REG(PFIFO_CACHE1_DMA_GET) != REG(PFIFO_CACHE1_DMA_PUT)) {
            pthread_mutex_unlock(&lock);
            uint64_t t0 = rt_now_100ns();
            int moved = run_pushbuf();
            pusher_t_busy += rt_now_100ns() - t0;
            pthread_mutex_lock(&lock);
            if (moved) continue;
        }
        struct timespec ts;
        rt_abstime(&ts, next_vblank - t);
        nv2a_trace('W', 0);
        pthread_cond_timedwait(&kick, &lock, &ts);
        nv2a_trace('w', 0);
    }
    return NULL;
}

void rt_nv2a_init(void) {
    start_ns = now_ns();
    REG(PMC_BOOT_0) = 0x02A000A2u;
    REG(PFB_CFG0) = 3;
    REG(PFB_CSTATUS) = RT_PHYS_SIZE;
    REG(PRAMDAC_NVPLL) = 0x00011C01u;
    REG(PRAMDAC_MPLL) = 0x00007702u;
    REG(PRAMDAC_VPLL) = 0x0003C20Du;
    REG(PFIFO_CACHE1_STATUS) = 0x10; /* EMPTY */
    REG(PFIFO_RUNOUT_STATUS) = 0x10; /* EMPTY */
    rt_interrupt_ack(GPU_IRQ, after_isr);
    rt_cond_init(&kick);
    if (getenv("XBRT_FRAME_TRACE") && (tr_file = fopen(getenv("XBRT_FRAME_TRACE"), "w"))) tr_on = 1;
    pthread_t h;
    pthread_create(&h, NULL, device_main, NULL);
}

/* The stats line, every 5 seconds at log level 1 or with XBRT_STATS=1 (which
 * prints it without the cost of logging every kernel call); from the DPC
 * thread, so it keeps coming while the device thread is busy. */
void nv2a_log_stats(void) {
    static uint64_t next;
    static int stats = -1;
    if (stats < 0) stats = getenv("XBRT_STATS") && atoi(getenv("XBRT_STATS"));
    uint64_t t = now_ns();
    if ((!rt_log_level && !stats) || t < next) return;
    next = t + 5000000000ull;
    extern uint64_t raster_t_state, raster_t_setup, raster_t_fill, raster_t_decode, raster_n_decode, raster_t_hash, raster_hash_bytes;
    fprintf(stderr, "[%10.3f] nv2a: texture decodes %llu, %.1f s; texture checks hashed %llu MB, %.1f s\n", rt_now_100ns() / 1e7,
            (unsigned long long)raster_n_decode, raster_t_decode / 1e7, (unsigned long long)(raster_hash_bytes >> 20), raster_t_hash / 1e7);
    fprintf(stderr, "[%10.3f] nv2a: device thread: pusher %.1f s, of which draw state %.1f s, vertices %.1f s, filling %.1f s\n",
            rt_now_100ns() / 1e7, pusher_t_busy / 1e7, raster_t_state / 1e7, raster_t_setup / 1e7, raster_t_fill / 1e7);
    {
        extern uint64_t prof_t[6], prof_n, prof_verts, raster_t_fetch;
        static uint64_t lt[6], ln, lv, lf;
        uint64_t dn = prof_n - ln ? prof_n - ln : 1;
        fprintf(stderr, "[%10.3f] nv2a: per GPU draw (%llu, %.0f verts): fetch %.1f us; prog %.1f bind %.1f upload %.1f consts %.1f frag %.1f call %.1f us\n",
                rt_now_100ns() / 1e7, (unsigned long long)(prof_n - ln), (double)(prof_verts - lv) / dn, (raster_t_fetch - lf) / 10.0 / dn,
                (prof_t[0] - lt[0]) / 10.0 / dn, (prof_t[1] - lt[1]) / 10.0 / dn, (prof_t[2] - lt[2]) / 10.0 / dn,
                (prof_t[3] - lt[3]) / 10.0 / dn, (prof_t[4] - lt[4]) / 10.0 / dn, (prof_t[5] - lt[5]) / 10.0 / dn);
        memcpy(lt, prof_t, sizeof lt), ln = prof_n, lv = prof_verts, lf = raster_t_fetch;
    }
    fprintf(stderr, "[%10.3f] nv2a: waiting for the driver after %u traps: %.1f s\n", rt_now_100ns() / 1e7, nv2a.traps, trap_t_wait / 1e7);
    fprintf(stderr, "[%10.3f] nv2a: %u vblanks, %u flips, %u draws (%u skipped), %u clears, %u traps; get %08x put %08x, "
            "PATT_COLOR0 %08x, intr %08x, scanout %08x\n", rt_now_100ns() / 1e7, nv2a.vblanks, nv2a.flips, nv2a.draws, nv2a.skipped,
            nv2a.clears, nv2a.traps, REG(PFIFO_CACHE1_DMA_GET), REG(PFIFO_CACHE1_DMA_PUT), REG(0x400B10), REG(PGRAPH_INTR),
            REG(PCRTC_START));
}
