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

#define PCRTC_INTR_0 0x600100
#define PCRTC_INTR_EN_0 0x600140
#define PCRTC_START 0x600800

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
static pthread_cond_t kick = PTHREAD_COND_INITIALIZER;   /* PUT moved */
static uint64_t start_ns;

/* ---- instance memory ---- */

/* Look an object handle up in the hash table. A linear search finds the
 * same entry the hardware's hash would, and needs no hash. Returns the
 * object's offset in instance memory, or ~0. */
uint32_t nv2a_lookup(uint32_t handle) {
    uint32_t ramht = REG(PFIFO_RAMHT);
    uint32_t base = ((ramht >> 4) & 0x1F) << 12, size = 0x1000u << ((ramht >> 16) & 3);
    for (uint32_t e = base; e < base + size; e += 8) {
        if (RAMIN(e) == handle && (RAMIN(e + 4) & 0x80000000u)) return (RAMIN(e + 4) & 0xFFFF) << 4;
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
    uint32_t off = a - RT_NV2A_BASE;
    switch (off) {
    case PTIMER_TIME_0:
        return (uint32_t)(ptimer() << 5);
    case PTIMER_TIME_1:
        return (uint32_t)(ptimer() >> 27) & 0x1FFFFFFF;
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
    case PFB_WBC: /* write-back cache flush: done at once */
        __atomic_thread_fence(__ATOMIC_SEQ_CST);
        REG(off) = v & ~PFB_WBC_FLUSH;
        break;
    case USER_DMA_PUT:
    case PFIFO_CACHE1_DMA_PUT:
        REG(USER_DMA_PUT) = v;
        REG(PFIFO_CACHE1_DMA_PUT) = v;
        pthread_cond_signal(&kick);
        break;
    case PTIMER_TIME_0:
    case PTIMER_TIME_1:
        break; /* nobody sets the clock */
    default:
        REG(off) = v;
    }
    pthread_mutex_unlock(&lock);
}

/* ---- the push buffer ---- */

static void run_pushbuf(void) {
    uint32_t put = REG(PFIFO_CACHE1_DMA_PUT), get = REG(PFIFO_CACHE1_DMA_GET);
    if (get == put) return;
    uint32_t limit = 0;
    uint32_t base = nv2a_dma_base(REG(PFIFO_CACHE1_DMA_INSTANCE) << 4, &limit);
    if (base == ~0u) base = 0;
    uint32_t method = nv2a.method, subch = nv2a.subch, count = nv2a.count, ni = nv2a.ni;
    int guard = 0;
    while (get != put && guard++ < 1 << 22) {
        uint32_t word = *(volatile uint32_t *)phys(base + get);
        get += 4;
        if (count) { /* a parameter */
            nv2a_method(subch, method, word);
            if (!ni) method += 4;
            count--;
            continue;
        }
        if (rt_log_level >= 2 && ((word & 0xE0000003u) == 0x20000000u || (word & 3)))
            rt_log("nv2a: push buffer %08x: %08x\n", get - 4, word);
        if ((word & 0xE0000003u) == 0x20000000u) { /* old-style jump */
            get = word & 0x1FFFFFFFu;
        } else if ((word & 3) == 1) { /* jump */
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
            rt_log("nv2a: bad push buffer word %08x at %08x (base %08x, put %08x, instance %08x)\n", word, get - 4, base, put, REG(PFIFO_CACHE1_DMA_INSTANCE));
        }
    }
    nv2a.method = method, nv2a.subch = subch, nv2a.count = count, nv2a.ni = ni;
    REG(PFIFO_CACHE1_DMA_GET) = get;
    REG(USER_DMA_GET) = get;
}

/* Hand a method to the driver's interrupt handler, as PGRAPH does for a
 * NO_OPERATION with a nonzero parameter: record it in TRAPPED_ADDR/DATA,
 * raise the ERROR interrupt, and stall the push buffer until the ISR
 * clears it. D3D's BlockOnTime waits for this (D3D sets an event in the
 * ISR). Layout as xemu has it; runs on the device thread. */
static void trap_method(uint32_t subch, uint32_t method, uint32_t arg) {
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
}

/* Channel methods (below 0x100) are PFIFO's own; the rest go to the
 * object bound to the subchannel. */
void nv2a_method(uint32_t subch, uint32_t method, uint32_t arg) {
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
    }
    if (rt_log_level >= 2) rt_log("nv2a: class %02x (subchannel %u) method %04x = %08x\n", nv2a.class_[subch], subch, method, arg);
}

/* ---- the device thread ---- */

static void *device_main(void *arg) {
    (void)arg;
    uint64_t next_vblank = now_ns() + 16683333;
    pthread_mutex_lock(&lock);
    for (;;) {
        uint64_t t = now_ns();
        if (t >= next_vblank) {
            next_vblank += 16683333; /* 59.94 Hz */
            if (t > next_vblank) next_vblank = t + 16683333;
            nv2a.vblanks++;
            if (rt_log_level && nv2a.vblanks % 300 == 0)
                rt_log("nv2a: %u vblanks, %u flips, %u draws, %u clears, %u traps\n", nv2a.vblanks, nv2a.flips,
                       nv2a.draws, nv2a.clears, nv2a.traps);
            REG(PCRTC_INTR_0) |= 1;
            update_irq();
        }
        if (REG(PFIFO_CACHE1_DMA_GET) != REG(PFIFO_CACHE1_DMA_PUT)) {
            pthread_mutex_unlock(&lock);
            run_pushbuf();
            pthread_mutex_lock(&lock);
            continue;
        }
        struct timespec ts;
        rt_abstime(&ts, next_vblank - t);
        pthread_cond_timedwait(&kick, &lock, &ts);
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
    pthread_t h;
    pthread_create(&h, NULL, device_main, NULL);
}
