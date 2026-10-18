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

static uint32_t seen[0x2000 / 4 / 32]; /* methods logged once */

void nv2a_kelvin(uint32_t method, uint32_t arg) {
    if (method >= 0x2000) return;
    if (rt_log_level >= 3) rt_log("nv2a: kelvin %04x = %08x\n", method, arg);
    nv2a.kelvin[method / 4] = arg;
    switch (method) {
    case FLIP_INCREMENT_WRITE: {
        nv2a.flips++;
        uint32_t mod = nv2a.kelvin[FLIP_MODULO / 4];
        uint32_t w = nv2a.kelvin[FLIP_WRITE / 4] + 1;
        nv2a.kelvin[FLIP_WRITE / 4] = mod ? w % mod : w;
        return;
    }
    case FLIP_STALL:
        return;
    case BACK_END_WRITE_SEMAPHORE_RELEASE: {
        uint32_t dma = nv2a_lookup(nv2a.kelvin[SET_CONTEXT_DMA_SEMAPHORE / 4]);
        uint32_t base = nv2a_dma_base(dma, NULL);
        if (base == ~0u) {
            rt_log("nv2a: semaphore release without a semaphore DMA object\n");
            return;
        }
        uint32_t pa = base + nv2a.kelvin[SET_SEMAPHORE_OFFSET / 4];
        if (rt_log_level >= 2) rt_log("nv2a: semaphore %08x = %u\n", pa, arg);
        xb_wr32(RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)), arg);
        /* PGRAPH keeps the low bits of the last released value at 0x400B10
         * (bits 2-6). D3D's BlockOnTime spins until they match the
         * semaphore in RAM; inferred from that loop (0x3BD240 in Forza). */
        *(volatile uint32_t *)(xb_mem + RT_NV2A_BASE + 0x400B10) = arg << 2;
        return;
    }
    case SET_BEGIN_END:
        if (arg) nv2a.draws++;
        return;
    case CLEAR_SURFACE:
        nv2a.clears++;
        return;
    }
    if (rt_log_level && !(seen[method / 128] & (1u << (method / 4 % 32)))) {
        seen[method / 128] |= 1u << (method / 4 % 32);
        rt_log("nv2a: kelvin method %04x first used (= %08x)\n", method, arg);
    }
}
