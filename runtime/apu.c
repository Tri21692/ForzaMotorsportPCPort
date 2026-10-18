/* The MCPX audio processing unit (APU), as far as DSOUND sees it.
 *
 * DSOUND runs recompiled and drives the APU through its registers at
 * 0xFE800000: the global block (interrupts, the front end that takes
 * voice methods, the setup engine and its sample counter) below 0x20000,
 * then the voice processor's method FIFO at 0x20000, and the two DSPs (GP
 * at 0x30000, EP at 0x50000). Nothing is mixed or played yet. What is
 * modelled is what DSOUND waits on to get through initialisation, at the
 * level xemu does it (hw/xbox/mcpx/apu): the method FIFO always has room,
 * the sample counter runs at 48 kHz, interrupt bits clear when written
 * with ones, and the front end's "notify" write lands in memory at once.
 * Every other register is plain storage.
 *
 * Register names are the ones xemu uses (apu_regs.h).
 */
#include "rt.h"

#define REG(off) (*(volatile uint32_t *)(xb_mem + RT_APU_BASE + (off)))

#define NV_PAPU_ISTS 0x1000      /* interrupt status, write one to clear */
#define NV_PAPU_FEMEMADDR 0x1324 /* front end: where a notify is written */
#define NV_PAPU_FEMEMDATA 0x1334 /* front end: the notify value */
#define NV_PAPU_XGSCNT 0x200C    /* setup engine: global sample count */
#define NV1BA0_PIO_FREE 0x20010  /* voice processor: free method FIFO entries */

static uint64_t start_100ns;

uint32_t rt_apu_read(uint32_t off, int bytes) {
    switch (off) {
    case NV1BA0_PIO_FREE:
        return 0x80; /* the FIFO is never full: methods take effect at once */
    case NV_PAPU_XGSCNT:
        return (uint32_t)((rt_now_100ns() - start_100ns) * 48000 / 10000000);
    }
    if (bytes == 4) return REG(off);
    if (bytes == 2) return *(volatile uint16_t *)(xb_mem + RT_APU_BASE + off);
    return *(volatile uint8_t *)(xb_mem + RT_APU_BASE + off);
}

void rt_apu_write(uint32_t off, int bytes, uint32_t v) {
    if (bytes == 4) {
        switch (off) {
        case NV_PAPU_ISTS:
            REG(off) &= ~v;
            return;
        case NV_PAPU_FEMEMDATA:
            xb_wr32(RT_PHYS_VIEW + (REG(NV_PAPU_FEMEMADDR) & (RT_PHYS_SIZE - 1)), v);
            break;
        }
        REG(off) = v;
        return;
    }
    if (bytes == 2) *(volatile uint16_t *)(xb_mem + RT_APU_BASE + off) = (uint16_t)v;
    else *(volatile uint8_t *)(xb_mem + RT_APU_BASE + off) = (uint8_t)v;
}

void rt_apu_init(void) {
    start_100ns = rt_now_100ns();
    rt_mem_commit(RT_APU_BASE, RT_APU_SIZE);
}
