/* The Xbox's hardware below the GPU: interrupts, PCI configuration space,
 * I/O ports and the video encoder (AV pack).
 *
 * Interrupts: a driver connects an ISR to a vector with KeConnectInterrupt.
 * Device models raise a vector from any thread; the DPC thread runs the
 * ISR at the interrupt's IRQL, the way the CPU would have interrupted
 * whatever was running. ISRs then queue DPCs, which that thread also runs.
 */
#include <string.h>

#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

/* ---- interrupts ---- */

#define VECTOR_BASE 0x30 /* vector = IRQ + 0x30, as the Xbox HAL assigns them */
#define PROFILE_LEVEL 26 /* IRQL = 26 - IRQ */

static uint32_t connected[16]; /* KINTERRUPT per IRQ, 0 if none */
static void (*acks[16])(void);  /* device hooks run after its ISR */
static volatile uint32_t raised;

/* HalGetInterruptVector(BusInterruptLevel, *Irql) -> vector */
static uint32_t k_HalGetInterruptVector(XbCtx *c) {
    uint32_t irq = ARG(0);
    if (irq >= 16) return 0;
    xb_wr8(ARG(1), (uint8_t)(PROFILE_LEVEL - irq));
    return VECTOR_BASE + irq;
}

/* KINTERRUPT: ServiceRoutine +0, ServiceContext +4, BusInterruptLevel +8,
 * Irql +0x0C, Connected +0x10, ShareVector +0x11, Mode +0x12. */
static uint32_t k_KeInitializeInterrupt(XbCtx *c) {
    /* (Interrupt, ServiceRoutine, ServiceContext, Vector, Irql, InterruptMode, ShareVector) */
    uint32_t in = ARG(0);
    xb_wr32(in + 0x00, ARG(1));
    xb_wr32(in + 0x04, ARG(2));
    xb_wr32(in + 0x08, ARG(3) - VECTOR_BASE);
    xb_wr32(in + 0x0C, ARG(4) & 0xFF);
    xb_wr8(in + 0x10, 0);
    xb_wr8(in + 0x11, (uint8_t)ARG(6));
    xb_wr8(in + 0x12, (uint8_t)ARG(5));
    return 0;
}

static uint32_t k_KeConnectInterrupt(XbCtx *c) {
    uint32_t in = ARG(0), irq = xb_rd32(in + 8);
    if (irq >= 16 || connected[irq] || xb_rd8(in + 0x10)) return 0;
    connected[irq] = in;
    xb_wr8(in + 0x10, 1);
    rt_log("interrupt: IRQ %u connected to ISR %08x\n", irq, xb_rd32(in));
    return 1;
}

static uint32_t k_KeDisconnectInterrupt(XbCtx *c) {
    uint32_t in = ARG(0), irq = xb_rd32(in + 8);
    if (irq >= 16 || connected[irq] != in) return 0;
    connected[irq] = 0;
    xb_wr8(in + 0x10, 0);
    return 1;
}

void rt_interrupt_raise(uint32_t vector) {
    __atomic_or_fetch(&raised, 1u << (vector - VECTOR_BASE), __ATOMIC_SEQ_CST);
    rt_dpc_wake();
}

void rt_interrupts_run(XbCtx *c) {
    uint32_t r = __atomic_exchange_n(&raised, 0, __ATOMIC_SEQ_CST);
    for (uint32_t irq = 0; r; irq++, r >>= 1) {
        uint32_t in = connected[irq];
        if (!(r & 1) || !in) continue;
        uint32_t kpcr = rt_self->kpcr;
        uint8_t old = xb_rd8(kpcr + 0x24);
        xb_wr8(kpcr + 0x24, xb_rd8(in + 0x0C));
        rt_guest_call(c, xb_rd32(in), 2, in, xb_rd32(in + 4));
        xb_wr8(kpcr + 0x24, old);
        if (acks[irq]) acks[irq]();
    }
}

void rt_interrupt_ack(uint32_t irq, void (*ack)(void)) { acks[irq] = ack; }

/* ---- PCI configuration space ----
 * HalReadWritePCISpace(BusNumber, SlotNumber, RegisterNumber, Buffer,
 * Length, WritePCISpace). Reads return what was last written (zero at
 * first); the drivers only adjust a few bits of the host bridge. */

static uint8_t pci[2][32][256];

static uint32_t k_HalReadWritePCISpace(XbCtx *c) {
    uint32_t bus = ARG(0), slot = ARG(1), reg = ARG(2), buf = ARG(3), len = ARG(4), write = ARG(5);
    if (bus >= 2 || (slot & 0x1F) != slot || reg >= 256 || len > 256 - reg) return 0;
    if (write) memcpy(pci[bus][slot] + reg, xb_mem + buf, len);
    else memcpy(xb_mem + buf, pci[bus][slot] + reg, len);
    return 0;
}

/* ---- I/O ports ----
 * The drivers poke a few ports (the SMBus at 0xC000, ACPI and GPIO at
 * 0x8000). Nothing behind them matters to the game yet, so reads return 0
 * and writes are dropped, with a log line to show what is used. */

uint32_t xb_io_in(XbCtx *c, uint32_t port, int bytes) {
    if (rt_log_level) rt_log("port in%c %04x\n", "bw?d"[bytes - 1], port);
    return 0;
}

void xb_io_out(XbCtx *c, uint32_t port, int bytes, uint32_t v) {
    if (rt_log_level) rt_log("port out%c %04x <- %x\n", "bw?d"[bytes - 1], port, v);
}

/* ---- video encoder ---- */

uint32_t rt_display_fb, rt_display_mode, rt_display_format, rt_display_pitch;

/* AvSetDisplayMode(RegisterBase, Step, Mode, Format, Pitch, FrameBuffer) */
static uint32_t k_AvSetDisplayMode(XbCtx *c) {
    rt_display_mode = ARG(2);
    rt_display_format = ARG(3);
    rt_display_pitch = ARG(4);
    rt_display_fb = ARG(5);
    rt_log("display mode %08x, format %x, pitch %u, front buffer %08x\n", ARG(2), ARG(3), ARG(4), ARG(5));
    return 0;
}

/* AvSendTVEncoderOption(RegisterBase, Option, Param, *Result) */
static uint32_t k_AvSendTVEncoderOption(XbCtx *c) {
    uint32_t result = ARG(3);
    if (!result) return 0;
    switch (ARG(1)) {
    case 6: /* AV_QUERY_AV_CAPABILITIES: standard AV pack, NTSC-M */
        xb_wr32(result, 0x00400101u);
        break;
    default:
        xb_wr32(result, 0);
    }
    return 0;
}

void rt_hw_init(void) {
    rt_kernel_handler(2, k_AvSendTVEncoderOption);
    rt_kernel_handler(3, k_AvSetDisplayMode);
    rt_kernel_handler(44, k_HalGetInterruptVector);
    rt_kernel_handler(46, k_HalReadWritePCISpace);
    rt_kernel_handler(98, k_KeConnectInterrupt);
    rt_kernel_handler(100, k_KeDisconnectInterrupt);
    rt_kernel_handler(109, k_KeInitializeInterrupt);
}
