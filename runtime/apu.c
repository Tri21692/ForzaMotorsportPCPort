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
#include <string.h>

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

/* The GP DSP, a 56300 that runs the effects image DSOUND downloads, is
 * not emulated. DSOUND hands it commands through a word at offset 0x810
 * of the DSP's scratch memory (in system RAM, found through the
 * scatter-gather table NV_PAPU_GPSADDR points at) and spins until the
 * DSP's executive clears it. While the DSP is out of reset, this stands in
 * for that executive and acknowledges each command at once; no effect is
 * actually run. Called every millisecond from the DPC thread. */
#define NV_PAPU_GPSADDR 0x2040
#define NV_PAPU_GPRST 0x3FFFC /* GP block at 0x30000, reset register at 0xFFFC */
#define GP_RUNNING 3          /* GPRST | GPDSPRST: out of reset */
#define GP_COMMAND 0x810

void rt_apu_tick(void) {
    if ((REG(NV_PAPU_GPRST) & GP_RUNNING) != GP_RUNNING) return;
    uint32_t sge = REG(NV_PAPU_GPSADDR);
    if (!sge || sge >= RT_PHYS_SIZE) return;
    uint32_t page = xb_rd32(RT_PHYS_VIEW + sge) & ~0xFFFu;
    if (page >= RT_PHYS_SIZE) return;
    uint32_t cmd = RT_PHYS_VIEW + page + GP_COMMAND;
    if (xb_rd32(cmd)) {
        if (rt_log_level >= 2) rt_log("apu: GP DSP command %u acknowledged\n", xb_rd32(cmd));
        xb_wr32(cmd, 0);
    }
}

void rt_apu_init(void) {
    start_100ns = rt_now_100ns();
    rt_mem_commit(RT_APU_BASE, RT_APU_SIZE);
    rt_mem_commit(RT_ACI_BASE, RT_ACI_SIZE);
}

/* ---- the AC'97 controller (ACI) at 0xFEC00000 ----
 * The APU's mixed output reaches the audio codec through an AC'97
 * controller, laid out as xemu has it (hw/xbox/mcpx/aci.c): the codec's
 * mixer registers at 0x000, the bus master at 0x100. Each bus master
 * channel is 16 bytes, standard AC'97: buffer descriptor base (+0),
 * current and last valid index (+4, +5), status (+6), position (+8),
 * prefetch (+0xA), control (+0xB). DSOUND resets its output channels
 * through the control register and waits for the reset bit to clear.
 * Nothing is played: a channel never leaves the halted state. */

#define ACI_REG8(off) (*(volatile uint8_t *)(xb_mem + RT_ACI_BASE + (off)))
#define ACI_REG16(off) (*(volatile uint16_t *)(xb_mem + RT_ACI_BASE + (off)))
#define ACI_NABM 0x100
#define AC97_POWERDOWN 0x26 /* codec: ADC, DAC, analog and Vref ready in bits 0-3 */
#define AC97_GLOB_STA 0x30  /* bus master: bit 8, primary codec ready */
#define CH_SR 0x6           /* status: bit 0, DMA controller halted */
#define CH_CR 0xB           /* control: bit 0 run, bit 1 reset registers */

uint32_t rt_aci_read(uint32_t off, int bytes) {
    if (off == AC97_POWERDOWN) return 0x000F;
    if (off == ACI_NABM + AC97_GLOB_STA) return 0x00000100;
    if (bytes == 4) return *(volatile uint32_t *)(xb_mem + RT_ACI_BASE + off);
    if (bytes == 2) return ACI_REG16(off);
    return ACI_REG8(off);
}

void rt_aci_write(uint32_t off, int bytes, uint32_t v) {
    if (off >= ACI_NABM && off < ACI_NABM + 0x80 && (off & 0xF) == CH_CR && bytes == 1) {
        uint32_t ch = off & ~0xFu;
        if (v & 2) { /* reset registers: done at once, back to the halted state */
            memset(xb_mem + RT_ACI_BASE + ch, 0, 16);
            ACI_REG16(ch + CH_SR) = 1;
            return;
        }
        ACI_REG8(off) = (uint8_t)v;
        return;
    }
    if (bytes == 4) *(volatile uint32_t *)(xb_mem + RT_ACI_BASE + off) = v;
    else if (bytes == 2) ACI_REG16(off) = (uint16_t)v;
    else ACI_REG8(off) = (uint8_t)v;
}
