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
 * The voice processor (apu_vp.c) takes the FIFO's methods and mixes a
 * frame of 32 samples at a time on a thread of its own, paced by the
 * PC's sound card (waveOut, 48 kHz stereo); the sample counter counts the
 * frames it made. XBRT_AUDIO=0: silent, paced by the clock alone.
 * XBRT_VOLUME=<0..1>: the output level (default 1).
 *
 * Register names are the ones xemu uses (apu_regs.h).
 */
#include <math.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"

void rt_vp_method(uint32_t method, uint32_t arg);
int rt_vp_frame(float out[32][2], int *raise_irq);
int rt_vp_write_fectl(uint32_t v);
int rt_vp_isr_cleared(void);

#define REG(off) (*(volatile uint32_t *)(xb_mem + RT_APU_BASE + (off)))

#define NV_PAPU_ISTS 0x1000      /* interrupt status, write one to clear */
#define NV_PAPU_FECTL 0x1100     /* front end control: the trap DSOUND's ISR releases */
#define NV_PAPU_IEN 0x1004       /* interrupt enable; bit 0 (GINTSTS) the global one */
#define NV_PAPU_FEMEMADDR 0x1324 /* front end: where a notify is written */
#define NV_PAPU_FEMEMDATA 0x1334 /* front end: the notify value */
#define NV_PAPU_XGSCNT 0x200C    /* setup engine: global sample count */
#define NV1BA0_PIO_FREE 0x20010  /* voice processor: free method FIFO entries */

static volatile uint32_t frames; /* made by the voice processor; XGSCNT is 32 samples each */

/* IRQ 5 while an enabled interrupt is pending; the ISR clears ISTS bits by
 * writing them, after which it is raised again if any are left. */
#define APU_IRQ 5
static void apu_irq(void) {
    uint32_t pending = REG(NV_PAPU_ISTS) & ~1u & REG(NV_PAPU_IEN);
    if ((REG(NV_PAPU_IEN) & 1) && pending) {
        __atomic_or_fetch(&REG(NV_PAPU_ISTS), 1u, __ATOMIC_SEQ_CST); /* atomic: the voice processor sets bits from its own thread */
        rt_interrupt_raise(0x30 + APU_IRQ);
    } else {
        __atomic_and_fetch(&REG(NV_PAPU_ISTS), ~1u, __ATOMIC_SEQ_CST);
    }
}

uint32_t rt_apu_read(uint32_t off, int bytes) {
    switch (off) {
    case NV1BA0_PIO_FREE:
        return 0x80; /* the FIFO is never full: methods take effect at once */
    case NV_PAPU_XGSCNT:
        return frames * 32;
    }
    if (bytes == 4) return REG(off);
    if (bytes == 2) return *(volatile uint16_t *)(xb_mem + RT_APU_BASE + off);
    return *(volatile uint8_t *)(xb_mem + RT_APU_BASE + off);
}

/* The DSPs' boot ROM: when a DSP leaves reset (both bits of its reset
 * register set, from a value that did not have both), it copies the first
 * 0x800 words of its scratch memory, which DSOUND has filled with the
 * DSP's program, into its program RAM; 24-bit words, one per 32 bits
 * (as xemu bootstraps its DSPs). The scratch memory is in system RAM, through
 * the scatter-gather table at GPSADDR/EPSADDR (8 bytes an entry, the
 * page's address first). The programs themselves do not run here, but
 * DSOUND checks the EP's: when P:6 does not hold the 0xCCCCCC its image
 * has there, it takes the DSP for dead and resets both, stalling the CPU
 * 10 ms each time, some thirty times a second. */
#define DSP_BOOT_WORDS 0x800
#define DSP_PMEM 0xA000 /* NV_PAPU_GPPMEM / NV_PAPU_EPPMEM, in the DSP's block */

static void dsp_bootstrap(uint32_t block, uint32_t sge_reg) {
    uint32_t sge = REG(sge_reg);
    if (!sge || sge >= RT_PHYS_SIZE) return;
    for (uint32_t w = 0; w < DSP_BOOT_WORDS; w++) {
        uint32_t byte = w * 4, page = xb_rd32(RT_PHYS_VIEW + sge + byte / 4096 * 8) & ~0xFFFu;
        if (page >= RT_PHYS_SIZE) return;
        REG(block + DSP_PMEM + byte) = xb_rd32(RT_PHYS_VIEW + page + byte % 4096) & 0xFFFFFF;
    }
}

void rt_apu_write(uint32_t off, int bytes, uint32_t v) {
    if (bytes == 4 && off >= 0x20000 && off < 0x30000) { /* the voice processor's method FIFO */
        rt_vp_method(off - 0x20000, v);
        return;
    }
    if (bytes == 4) {
        switch (off) {
        case 0x3FFFC: /* NV_PAPU_GPRST */
        case 0x5FFFC: /* NV_PAPU_EPRST */
            if ((REG(off) & 3) != 3 && (v & 3) == 3) dsp_bootstrap(off & ~0xFFFFu, off == 0x3FFFC ? 0x2040 : 0x2048);
            break;
        case NV_PAPU_ISTS:
            __atomic_and_fetch(&REG(off), ~v, __ATOMIC_SEQ_CST);
            rt_vp_isr_cleared();
            apu_irq();
            return;
        case NV_PAPU_FECTL:
            if (rt_vp_write_fectl(v)) apu_irq();
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

/* ---- output ---- */

#define OUT_FRAMES 32 /* VP frames per buffer: 1024 samples, 21 ms */
#define OUT_BUFS 4

static float volume = 0.7f; /* XBRT_VOLUME; below 1 for headroom: the mix of all bins can exceed full scale */
void rt_apu_set_volume(float v) { volume = v < 0 ? 0 : v > 1 ? 1 : v; }
static FILE *dump; /* XBRT_AUDIO_DUMP=<file>: the output as raw 48 kHz 16-bit stereo, for checking and for recordings */

/* One buffer's worth of frames, as 16-bit stereo. */
static void make(int16_t *pcm) {
    for (int f = 0; f < OUT_FRAMES; f++) {
        float s[32][2];
        int irq = 0;
        if (rt_vp_frame(s, &irq)) frames++;
        if (irq) apu_irq();
        /* A compressor on the whole mix: when the level goes over 0.5 the gain
         * comes down within ~2 ms and recovers over ~250 ms, the same for both
         * channels, so the waveform keeps its shape. At the race start, with
         * every engine revving at once, the mix is ~5x the usual level; the
         * per-sample soft clipping used before distorted it into a harsh
         * rasp. The soft clip stays only as a last guard. */
        static float env = 0;
        for (int i = 0; i < 32; i++) {
            float l = s[i][0] * volume, r = s[i][1] * volume, pk = fmaxf(fabsf(l), fabsf(r));
            env = pk > env ? env + (pk - env) * 0.01f : env + (pk - env) * 0.00008f; /* attack ~2 ms, release ~250 ms at 48 kHz */
            float g = env > 0.5f ? 0.5f / env : 1.0f;
            float o[2] = {l * g, r * g};
            for (int c = 0; c < 2; c++) {
                float x = o[c], a = fabsf(x);
                if (a > 0.8f) x = copysignf(0.8f + 0.2f * tanhf((a - 0.8f) / 0.2f), x);
                pcm[(f * 32 + i) * 2 + c] = (int16_t)(x * 32767);
            }
        }
    }
    if (dump) fwrite(pcm, 4, OUT_FRAMES * 32, dump), fflush(dump);
}

#ifdef _WIN32
#include <windows.h>
#include <mmsystem.h>

static void *audio_main(void *arg) {
    int on = arg != NULL;
    static int16_t pcm[OUT_BUFS][OUT_FRAMES * 32 * 2];
    HWAVEOUT out = NULL;
    HANDLE done = CreateEventA(NULL, FALSE, FALSE, NULL);
    WAVEFORMATEX wf = {WAVE_FORMAT_PCM, 2, 48000, 48000 * 4, 4, 16, 0};
    if (on && waveOutOpen(&out, WAVE_MAPPER, &wf, (DWORD_PTR)done, 0, CALLBACK_EVENT) != MMSYSERR_NOERROR) {
        fprintf(stderr, "xbrt: no sound output device; audio is silent\n");
        out = NULL;
    }
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    if (!out) { /* silent: frames at the rate of the clock */
        uint64_t next = rt_now_100ns();
        for (;;) {
            make(pcm[0]);
            next += (uint64_t)OUT_FRAMES * 32 * 10000000 / 48000;
            int64_t wait = (int64_t)(next - rt_now_100ns());
            if (wait > 0) Sleep((DWORD)(wait / 10000));
        }
    }
    WAVEHDR hdr[OUT_BUFS];
    memset(hdr, 0, sizeof hdr);
    for (int i = 0; i < OUT_BUFS; i++) {
        hdr[i].lpData = (LPSTR)pcm[i], hdr[i].dwBufferLength = sizeof pcm[i];
        waveOutPrepareHeader(out, &hdr[i], sizeof hdr[i]);
        make(pcm[i]);
        waveOutWrite(out, &hdr[i], sizeof hdr[i]);
    }
    unsigned underruns = 0;
    for (;;) {
        WaitForSingleObject(done, 100);
        int ndone = 0;
        for (int i = 0; i < OUT_BUFS; i++) ndone += (hdr[i].dwFlags & WHDR_DONE) != 0;
        if (ndone == OUT_BUFS && (++underruns <= 200 || underruns % 100 == 0)) /* all played out: the sound card ran dry (a gap) */
            fprintf(stderr, "[%9.3f] apu: output ran dry (%u times)\n", rt_now_100ns() / 1e7, underruns);
        for (int i = 0; i < OUT_BUFS; i++)
            if (hdr[i].dwFlags & WHDR_DONE) {
                make(pcm[i]);
                waveOutWrite(out, &hdr[i], sizeof hdr[i]);
            }
    }
    return NULL;
}
#else
static void *audio_main(void *arg) {
    (void)arg;
    static int16_t pcm[OUT_FRAMES * 32 * 2];
    for (;;) {
        make(pcm);
        struct timespec ts = {0, OUT_FRAMES * 32 * 1000000000L / 48000};
        nanosleep(&ts, NULL);
    }
    return NULL;
}
#endif

void rt_apu_init(void) {
    rt_mem_commit(RT_APU_BASE, RT_APU_SIZE);
    rt_mem_commit(RT_ACI_BASE, RT_ACI_SIZE);
    const char *a = getenv("XBRT_AUDIO"), *vol = getenv("XBRT_VOLUME");
    if (vol) volume = (float)atof(vol);
    const char *d = getenv("XBRT_AUDIO_DUMP");
    if (d && *d) dump = fopen(d, "wb");
    if (dump) fprintf(stderr, "xbrt: audio dump starts at %.3f s\n", rt_now_100ns() / 1e7);
    rt_interrupt_ack(APU_IRQ, apu_irq);
    pthread_t t;
    pthread_create(&t, NULL, audio_main, (a && !atoi(a)) ? NULL : (void *)1);
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
