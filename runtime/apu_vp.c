/* The APU's voice processor (VP): what turns DSOUND's voices into sound.
 *
 * DSOUND drives it through methods written to 0xFE820000 (the "PIO" FIFO,
 * rt_vp_method): it picks a voice (SET_CURRENT_VOICE), sets its format,
 * buffer, pitch, volumes and envelopes (each method one 32-bit word of the
 * voice's 128-byte structure in system RAM at NV_PAPU_VPVADDR), then
 * VOICE_ON links it into one of three lists (2D, 3D, multipass). Every
 * 32 samples at 48 kHz (a frame, rt_vp_frame) the VP walks the lists:
 * decodes each active voice's samples (PCM, or Xbox ADPCM), resamples them
 * by its pitch, applies its envelope and per-bin volumes, and mixes them
 * into 32 mix bins. Streams play lists of segments (SSLs) and notify DSOUND
 * in memory (NV_PAPU_FENADDR) and by interrupt when one is done; voices
 * that went idle are handed back through a front-end trap
 * (SE2FE_IDLE_VOICE).
 *
 * On the Xbox the GP DSP then runs DSOUND's effects (reverb, the speaker
 * mix) over the bins; that DSP is not emulated, so the speaker bins (0-5:
 * front left and right, centre, LFE, rear left and right) and the 3D
 * crosstalk bins (6-9) are mixed down to stereo directly and effect sends
 * are dropped. Each voice's low-pass
 * filter (DLS2 mode) runs as a state-variable filter; not done yet: the
 * parametric EQ mode and HRTF for 3D voices.
 *
 * Layouts and behaviour follow xemu (hw/xbox/mcpx/apu/vp.c, apu_regs.h),
 * which documents the hardware; the code is this project's.
 */
#include <math.h>
#include <stdio.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"

#define REG(off) (*(volatile uint32_t *)(xb_mem + RT_APU_BASE + (off)))

static inline uint8_t *pa(uint32_t addr) { return rt_phys_ptr(addr); } /* sample data may be in user memory (stand-in pages) */
static inline uint32_t rd32(uint32_t addr) { uint32_t v; memcpy(&v, pa(addr), 4); return v; }
static inline void wr32(uint32_t addr, uint32_t v) { memcpy(pa(addr), &v, 4); }

/* Front-end and setup-engine registers */
#define NV_PAPU_ISTS 0x1000
#define ISTS_FETINTSTS (1u << 4)
#define ISTS_FENINTSTS (1u << 5)
#define ISTS_FEVINTSTS (1u << 6)
#define NV_PAPU_FECTL 0x1100
#define FECTL_FEMETHMODE 0xE0u
#define FECTL_TRAPPED 0xE0u
#define FECTL_FETRAPREASON 0xF00u
#define FECTL_REQUESTED 0xF00u
#define NV_PAPU_FECV 0x1110
#define NV_PAPU_FEAV 0x1118
#define NV_PAPU_FENADDR 0x115C
#define NV_PAPU_FEDECMETH 0x1300
#define NV_PAPU_FEDECPARAM 0x1304
#define NV_PAPU_FETFORCE1 0x1504
#define FETFORCE1_SE2FE_IDLE_VOICE (1u << 15)
#define NV_PAPU_SECTL 0x2000
#define SECTL_XCNTMODE 0x18u
#define NV_PAPU_VPVADDR 0x202C
#define NV_PAPU_VPSGEADDR 0x2030
#define NV_PAPU_VPSSLADDR 0x2034
static const uint32_t list_top[3] = {0x2054, 0x2060, 0x206C}; /* TVL2D, TVL3D, TVLMP */

/* PIO methods */
#define M_SET_ANTECEDENT_VOICE 0x120
#define M_VOICE_ON 0x124
#define M_VOICE_OFF 0x128
#define M_VOICE_RELEASE 0x12C
#define M_VOICE_PAUSE 0x140
#define M_SET_CURRENT_SSL 0x190
#define M_SET_SUBMIX_HEADROOM 0x200 /* 32 of them */
#define M_SET_HRTF_HEADROOM 0x280
#define M_SET_HRTF_SUBMIXES 0x2C0
#define M_SET_CURRENT_VOICE 0x2F8
#define M_VOICE_LOCK 0x2FC
#define M_SET_VOICE_SSL_A 0x320
#define M_SET_VOICE_SSL_B 0x35C
#define M_SET_VOICE_TAR_PITCH 0x37C
#define M_SET_SSL_SEGMENT_OFFSET 0x600 /* 64 offset/length pairs */
#define M_SET_CURRENT_INBUF_SGE 0x804
#define M_SET_CURRENT_INBUF_SGE_OFFSET 0x808
#define M_SET_CURRENT_OUTBUF_SGE 0x1800
#define M_SET_CURRENT_OUTBUF_SGE_OFFSET 0x1808
#define SE2FE_IDLE_VOICE 0x8000

/* The voice structure (NV_PAVS), 128 bytes per voice */
#define VOICE_SIZE 0x80
#define V_CFG_VBIN 0x00
#define V_CFG_FMT 0x04
#define V_CFG_ENV0 0x08
#define V_CFG_ENVA 0x0C
#define V_CFG_ENV1 0x10
#define V_CFG_ENVF 0x14
#define V_CFG_MISC 0x18
#define V_CUR_PSL_START 0x20 /* BA: buffer base, 24 bits */
#define V_CUR_PSH_SAMPLE 0x24 /* LBO: loop start */
#define V_CUR_ECNT 0x34      /* envelope counters: amplitude low 16, filter high 16 */
#define V_PAR_STATE 0x54
#define V_PAR_OFFSET 0x58 /* CBO (current sample) low 24, amplitude level high 8 */
#define V_PAR_NEXT 0x5C   /* EBO (end sample) low 24, filter level high 8 */
#define V_TAR_VOLA 0x60
#define V_TAR_VOLB 0x64
#define V_TAR_VOLC 0x68
#define V_TAR_LFO_ENV 0x6C /* amplitude release rate, low 12 */
#define V_TAR_PITCH_LINK 0x7C /* next voice low 16, pitch high 16 */

#define FMT_MULTIPASS_BIN(f) (((f) >> 16) & 31)
#define FMT_SPB(f) (((f) >> 16) & 31)
#define FMT_MULTIPASS (1u << 21)
#define FMT_PERSIST (1u << 23)
#define FMT_STREAM (1u << 24)
#define FMT_LOOP (1u << 25)
#define FMT_CLEAR_MIX (1u << 26)
#define FMT_STEREO (1u << 27)
#define FMT_SAMPLE_SIZE(f) (((f) >> 28) & 3) /* U8, S16, S24, S32 */
#define FMT_CONTAINER(f) (((f) >> 30) & 3)    /* B8, B16, ADPCM, B32 */
#define CONTAINER_ADPCM 2

#define STATE_PAUSED (1u << 18)
#define STATE_NEW (1u << 20)
#define STATE_ACTIVE (1u << 21)
#define STATE_EF_SHIFT 24
#define STATE_EA_SHIFT 28
enum { ENV_OFF, ENV_DELAY, ENV_ATTACK, ENV_HOLD, ENV_DECAY, ENV_SUSTAIN, ENV_RELEASE, ENV_FORCE_RELEASE };

#define MAX_VOICES 256
#define MAX_3D_VOICES 64
#define BINS 32
#define FRAME 32

static pthread_mutex_t vp_lock = PTHREAD_MUTEX_INITIALIZER;
static int irq_pending; /* raised by the frame or a method, delivered by apu.c */

static struct {
    uint32_t base[2];
    uint8_t count[2];
    int index, seg;
} ssl[MAX_VOICES];
static uint32_t ssl_base_page, inbuf_sge, outbuf_sge;
static uint8_t submix_headroom[BINS], hrtf_headroom, hrtf_submix[4];
static uint64_t locked[MAX_VOICES / 64];

/* Per voice, host side: decoded samples not yet resampled, and where the
 * resampler stands between the last two. */
typedef struct {
    float buf[72][2];
    int len, pos;
    float prev[2], cur[2];
    double frac;
    int adpcm_block;
    int16_t adpcm[65 * 2];
    float low[2], band[2]; /* the low-pass filter's state, per channel */
} VoiceHost;
static VoiceHost host[MAX_VOICES];

static uint32_t vaddr(unsigned v, uint32_t off) { return REG(NV_PAPU_VPVADDR) + v * VOICE_SIZE + off; }
static uint32_t vget(unsigned v, uint32_t off) { return rd32(vaddr(v, off)); }
static void vset(unsigned v, uint32_t off, uint32_t val) { wr32(vaddr(v, off), val); }
static void vset_mask(unsigned v, uint32_t off, uint32_t mask, uint32_t val) {
    uint32_t sh = (uint32_t)__builtin_ctz(mask);
    vset(v, off, (vget(v, off) & ~mask) | ((val << sh) & mask));
}
static uint32_t vget_mask(unsigned v, uint32_t off, uint32_t mask) { return (vget(v, off) & mask) >> __builtin_ctz(mask); }

static void notify(unsigned v, int which) {
    uint32_t at = REG(NV_PAPU_FENADDR) + 16 * (2 + v * 4 + (uint32_t)which) + 15; /* the last byte is the status */
    *pa(at) = 1;                                                                 /* NV1BA0_NOTIFICATION_STATUS_DONE_SUCCESS */
    *pa(at - 1) = 1;
    REG(NV_PAPU_ISTS) |= ISTS_FEVINTSTS | ISTS_FENINTSTS;
    irq_pending = 1;
}

static void voice_off(unsigned v) {
    vset_mask(v, V_PAR_STATE, STATE_ACTIVE, 0);
    int which = 0; /* SSL A done */
    if (vget(v, V_CFG_FMT) & FMT_STREAM) which += ssl[v].index;
    notify(v, which);
}

static void envelope_start(unsigned v, uint32_t start, int amplitude) {
    uint32_t sh = amplitude ? STATE_EA_SHIFT : STATE_EF_SHIFT, cmask = amplitude ? 0xFFFFu : 0xFFFF0000u;
    vset_mask(v, V_PAR_STATE, 0xFu << sh, start);
    uint32_t env0 = vget(v, amplitude ? V_CFG_ENV0 : V_CFG_ENV1), enva = vget(v, amplitude ? V_CFG_ENVA : V_CFG_ENVF);
    if (start == ENV_DELAY) vset_mask(v, V_CUR_ECNT, cmask, ((env0 >> 12) & 0xFFF) * 16);
    else if (start == ENV_ATTACK) vset_mask(v, V_CUR_ECNT, cmask, 0);
    else if (start == ENV_HOLD) vset_mask(v, V_CUR_ECNT, cmask, ((enva >> 12) & 0xFFF) * 16);
}

/* A PIO method from DSOUND (offset within the FIFO's block). */
void rt_vp_method(uint32_t method, uint32_t arg) {
    pthread_mutex_lock(&vp_lock);
    uint32_t cv = REG(NV_PAPU_FECV) & 0xFFFF;
    switch (method) {
    case M_SET_ANTECEDENT_VOICE:
        REG(NV_PAPU_FEAV) = arg;
        break;
    case M_VOICE_LOCK:
        if (cv < MAX_VOICES) {
            if (arg & 1) locked[cv / 64] |= 1ull << (cv % 64);
            else locked[cv / 64] &= ~(1ull << (cv % 64));
        }
        break;
    case M_SET_CURRENT_VOICE:
        REG(NV_PAPU_FECV) = arg;
        break;
    case M_VOICE_ON: {
        unsigned v = arg & 0xFFFF;
        if (v >= MAX_VOICES) break;
        uint32_t av = REG(NV_PAPU_FEAV), list = (av >> 16) & 3;
        if (list) { /* at the top of a list */
            vset_mask(v, V_TAR_PITCH_LINK, 0xFFFF, REG(list_top[list - 1]));
            REG(list_top[list - 1]) = v;
        } else { /* after the antecedent voice */
            unsigned a = av & 0xFFFF;
            if (a < MAX_VOICES) {
                vset_mask(v, V_TAR_PITCH_LINK, 0xFFFF, vget(a, V_TAR_PITCH_LINK) & 0xFFFF);
                vset_mask(a, V_TAR_PITCH_LINK, 0xFFFF, v);
            }
        }
        vset_mask(v, V_PAR_OFFSET, 0xFFFFFF, 0);
        ssl[v].seg = ssl[v].index = 0;
        envelope_start(v, arg >> 28, 1);
        envelope_start(v, (arg >> 24) & 0xF, 0);
        VoiceHost *h = &host[v];
        memset(h, 0, sizeof *h);
        h->frac = 1.0, h->adpcm_block = -1;
        vset_mask(v, V_PAR_STATE, STATE_ACTIVE, 1);
        break;
    }
    case M_VOICE_RELEASE: {
        unsigned v = arg & 0xFFFF;
        if (v >= MAX_VOICES) break;
        vset_mask(v, V_CUR_ECNT, 0xFFFF, (vget(v, V_TAR_LFO_ENV) & 0xFFF) * 16);
        vset_mask(v, V_PAR_STATE, 0xFu << STATE_EA_SHIFT, ENV_RELEASE);
        vset_mask(v, V_CUR_ECNT, 0xFFFF0000u, (vget(v, V_CFG_MISC) & 0xFFF) * 16);
        vset_mask(v, V_PAR_STATE, 0xFu << STATE_EF_SHIFT, ENV_RELEASE);
        break;
    }
    case M_VOICE_OFF:
        if ((arg & 0xFFFF) < MAX_VOICES) voice_off(arg & 0xFFFF);
        break;
    case M_VOICE_PAUSE:
        if ((arg & 0xFFFF) < MAX_VOICES) vset_mask(arg & 0xFFFF, V_PAR_STATE, STATE_PAUSED, (arg >> 18) & 1);
        break;
    case M_SET_VOICE_TAR_PITCH:
        if (cv < MAX_VOICES) vset_mask(cv, V_TAR_PITCH_LINK, 0xFFFF0000u, arg >> 16);
        break;
    case 0x300: case 0x304: case 0x308: case 0x30C: case 0x310: case 0x314: case 0x318: /* CFG_VBIN .. CFG_MISC */
        if (cv < MAX_VOICES) vset(cv, method - 0x300, arg);
        break;
    case 0x31C: /* SET_VOICE_TAR_HRTF */
        if (cv < MAX_VOICES) vset_mask(cv, 0x1C, 0xFFFF, arg & 0xFFFF);
        break;
    case 0x360: case 0x364: case 0x368: case 0x36C: case 0x374: case 0x378: /* TAR_VOLA..C, LFO_ENV, FCA, FCB */
        if (cv < MAX_VOICES) vset(cv, method - 0x300, arg);
        break;
    case 0x3A0: /* CFG_BUF_BASE */
        if (cv < MAX_VOICES) vset_mask(cv, V_CUR_PSL_START, 0xFFFFFF, arg);
        break;
    case 0x3A4: /* CFG_BUF_LBO */
        if (cv < MAX_VOICES) vset_mask(cv, V_CUR_PSH_SAMPLE, 0xFFFFFF, arg);
        break;
    case 0x3D8: /* BUF_CBO */
        if (cv < MAX_VOICES) vset_mask(cv, V_PAR_OFFSET, 0xFFFFFF, arg);
        break;
    case 0x3DC: /* CFG_BUF_EBO */
        if (cv < MAX_VOICES) vset_mask(cv, V_PAR_NEXT, 0xFFFFFF, arg);
        break;
    case M_SET_VOICE_SSL_A:
    case M_SET_VOICE_SSL_B:
        if (cv < MAX_VOICES) {
            int s = method == M_SET_VOICE_SSL_B;
            ssl[cv].base[s] = arg >> 8, ssl[cv].count[s] = arg & 0xFF;
        }
        break;
    case M_SET_CURRENT_SSL:
        ssl_base_page = arg;
        break;
    case M_SET_HRTF_SUBMIXES:
        for (int i = 0; i < 4; i++) hrtf_submix[i] = (arg >> (8 * i)) & 31;
        break;
    case M_SET_HRTF_HEADROOM:
        hrtf_headroom = arg & 7;
        break;
    case M_SET_CURRENT_INBUF_SGE:
        inbuf_sge = arg;
        break;
    case M_SET_CURRENT_INBUF_SGE_OFFSET:
        wr32(REG(NV_PAPU_VPSGEADDR) + inbuf_sge * 8, arg & 0xFFFFF000u);
        break;
    case M_SET_CURRENT_OUTBUF_SGE:
        outbuf_sge = arg;
        break;
    case M_SET_CURRENT_OUTBUF_SGE_OFFSET:
        wr32(REG(NV_PAPU_VPSGEADDR) + outbuf_sge * 8, arg & 0xFFFFF000u);
        break;
    default:
        if (method >= M_SET_SUBMIX_HEADROOM && method < M_SET_SUBMIX_HEADROOM + 4 * BINS)
            submix_headroom[(method - M_SET_SUBMIX_HEADROOM) / 4] = arg & 7;
        else if (method >= M_SET_SSL_SEGMENT_OFFSET && method < M_SET_SSL_SEGMENT_OFFSET + 8 * 64)
            wr32(REG(NV_PAPU_VPSSLADDR) + ssl_base_page * 8 + (method - M_SET_SSL_SEGMENT_OFFSET), arg);
        /* HRIR coefficients (0x400-0x43C), output buffers: not used without HRTF and the DSPs */
        break;
    }
    pthread_mutex_unlock(&vp_lock);
}

/* ---- envelopes: one step per frame ---- */

static float envelope(unsigned v, int amplitude) {
    uint32_t sh = amplitude ? STATE_EA_SHIFT : STATE_EF_SHIFT, cmask = amplitude ? 0xFFFFu : 0xFFFF0000u;
    uint32_t loff = amplitude ? V_PAR_OFFSET : V_PAR_NEXT, lmask = 0xFF000000u;
    uint32_t env0 = vget(v, amplitude ? V_CFG_ENV0 : V_CFG_ENV1), enva = vget(v, amplitude ? V_CFG_ENVA : V_CFG_ENVF);
    uint32_t release = amplitude ? vget(v, V_TAR_LFO_ENV) & 0xFFF : vget(v, V_CFG_MISC) & 0xFFF;
    uint32_t cur = vget_mask(v, V_PAR_STATE, 0xFu << sh), count = vget_mask(v, V_CUR_ECNT, cmask);
    uint32_t attack = env0 & 0xFFF, hold = (enva >> 12) & 0xFFF, decay = enva & 0xFFF, sustain = enva >> 24;
    float value = 1.0f;
    switch (cur) {
    case ENV_OFF:
        count = 0;
        vset_mask(v, loff, lmask, 0xFF);
        break;
    case ENV_DELAY:
        vset_mask(v, loff, lmask, 0);
        if (count == 0) cur = ENV_ATTACK;
        else count--;
        value = 0;
        break;
    case ENV_ATTACK:
        value = attack == 0 || count >= attack * 16 ? 1.0f : (float)count / (float)(attack * 16);
        vset_mask(v, loff, lmask, (uint32_t)(value * 255));
        if (attack == 0 || count >= attack * 16) cur = ENV_HOLD, count = hold * 16;
        else count++;
        break;
    case ENV_HOLD:
        vset_mask(v, loff, lmask, 0xFF);
        if (count == 0) cur = ENV_DECAY, count = decay * 16;
        else count--;
        break;
    case ENV_DECAY: {
        float lvl = decay == 0 ? 0.0f : 255.0f * powf(0.99988799f, (float)(decay * 16 - count) * 4096.0f / (float)decay);
        if (lvl <= sustain + 0.2f || lvl > 255.0f || count == 0) {
            cur = ENV_SUSTAIN;
            lvl = sustain;
        } else {
            count--;
            vset_mask(v, loff, lmask, (uint32_t)lvl);
        }
        value = lvl / 255.0f;
        break;
    }
    case ENV_SUSTAIN:
        count = 0;
        vset_mask(v, loff, lmask, sustain);
        value = sustain / 255.0f;
        break;
    case ENV_RELEASE: {
        if (release == 0) count = 0;
        if (count == 0) {
            cur = ENV_FORCE_RELEASE;
            value = 0;
        } else {
            float pos = 1.0f - (float)count / (release * 16.0f);
            value = expf(-6.91f * (pos < 0 ? 0 : pos)) * (float)(vget(v, loff) >> 24) / 255.0f;
            count--;
        }
        break;
    }
    case ENV_FORCE_RELEASE:
    default:
        if (amplitude) voice_off(v);
        return 0;
    }
    vset_mask(v, V_PAR_STATE, 0xFu << sh, cur);
    vset_mask(v, V_CUR_ECNT, cmask, count);
    return value;
}

/* ---- samples ---- */

/* Xbox ADPCM is IMA ADPCM in 36-byte blocks per channel: a 4-byte header
 * (the first sample, the step index) and 64 nibbles; stereo interleaves
 * the channels every 4 bytes after both headers. 64 samples a block. */
static const int16_t ima_step[89] = {7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107,
                                     118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876,
                                     963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
                                     5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385,
                                     24623, 27086, 29794, 32767};
static const int8_t ima_index[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};

static void adpcm_decode(const uint8_t *blk, int channels, int16_t *out /* 65 * channels */) {
    for (int c = 0; c < channels; c++) {
        const uint8_t *hd = blk + 4 * c;
        int pred = (int16_t)(hd[0] | hd[1] << 8), idx = hd[2] > 88 ? 88 : hd[2];
        out[c] = (int16_t)pred;
        int n = 1;
        for (int chunk = 0; chunk < 8; chunk++) {
            const uint8_t *d = blk + 4 * channels + (size_t)(chunk * channels + c) * 4;
            for (int b = 0; b < 8; b++) {
                int nib = (d[b / 2] >> ((b & 1) * 4)) & 15, step = ima_step[idx], diff = step >> 3;
                if (nib & 1) diff += step >> 2;
                if (nib & 2) diff += step >> 1;
                if (nib & 4) diff += step;
                pred += nib & 8 ? -diff : diff;
                pred = pred < -32768 ? -32768 : pred > 32767 ? 32767 : pred;
                idx += ima_index[nib];
                idx = idx < 0 ? 0 : idx > 88 ? 88 : idx;
                out[n++ * channels + c] = (int16_t)pred;
            }
        }
    }
}

/* A buffer's byte at linear offset through the scatter-gather table. */
static uint32_t sge_addr(uint32_t linear) {
    return (rd32(REG(NV_PAPU_VPSGEADDR) + (linear / 4096) * 8) & ~0xFFFu) + linear % 4096;
}

/* Up to n samples of voice v at its current position into out, advancing
 * it; -1 when it has nothing to play (paused, ended, a stream out of data). */
static int voice_samples(unsigned v, float (*out)[2], int n) {
    VoiceHost *h = &host[v];
    uint32_t fmt = vget(v, V_CFG_FMT), state = vget(v, V_PAR_STATE);
    vset(v, V_PAR_STATE, state & ~STATE_NEW);
    if (state & STATE_PAUSED) return -1;
    int stereo = (fmt & FMT_STEREO) != 0, ch = stereo ? 2 : 1, stream = (fmt & FMT_STREAM) != 0;
    int container = (int)FMT_CONTAINER(fmt), size = (int)FMT_SAMPLE_SIZE(fmt), spb = (int)FMT_SPB(fmt) + 1;
    uint32_t cbo = vget(v, V_PAR_OFFSET) & 0xFFFFFF, ebo = vget(v, V_PAR_NEXT) & 0xFFFFFF;
    uint32_t lbo = vget(v, V_CUR_PSH_SAMPLE) & 0xFFFFFF, ba = vget(v, V_CUR_PSL_START) & 0xFFFFFF;
    uint32_t seg_addr = 0;
    if (stream) {
        if (!(fmt & FMT_PERSIST) && vget_mask(v, V_PAR_STATE, 0xFu << STATE_EA_SHIFT) < ENV_RELEASE) {
            voice_off(v);
            return -1;
        }
        int idx = ssl[v].index;
        if (ssl[v].count[idx] == 0) { /* the stream ran dry */
            vset_mask(v, V_PAR_OFFSET, 0xFFFFFF, 0);
            ssl[v].seg = 0;
            if (!(fmt & FMT_PERSIST)) ssl[v].index = 0, voice_off(v);
            else notify(v, idx);
            return -1;
        }
        uint32_t e = REG(NV_PAPU_VPSSLADDR) + (ssl[v].base[idx] + (uint32_t)ssl[v].seg) * 8;
        uint32_t len = rd32(e + 4);
        seg_addr = rd32(e);
        container = (int)((len >> 16) & 3), stereo = (len >> 23) & 1, ch = stereo ? 2 : 1;
        if (container == CONTAINER_ADPCM) size = 2;
        if ((len & 0xFFFF) == 0) return -1;
        ebo = (len & 0xFFFF) - 1;
    }
    int adpcm = container == CONTAINER_ADPCM;
    static const int csize[4] = {1, 2, 0, 4};
    int got = 0;
    for (; got < n && cbo <= ebo; got++, cbo++) {
        if (adpcm) {
            int block = (int)(cbo / 64), at = (int)(cbo % 64);
            if (h->adpcm_block != block) {
                uint8_t blk[72];
                uint32_t bytes = 36u * (uint32_t)ch, lin = (uint32_t)block * bytes;
                if (stream)
                    for (uint32_t i = 0; i < bytes; i += 4) { /* a block can cross a page, and stand-in pages are not adjacent */
                        uint32_t w = rd32(seg_addr + lin + i);
                        memcpy(blk + i, &w, 4);
                    }
                else
                    for (uint32_t i = 0; i < bytes; i += 4) {
                        uint32_t w = rd32(sge_addr(ba + lin + i));
                        memcpy(blk + i, &w, 4);
                    }
                adpcm_decode(blk, ch, h->adpcm);
                h->adpcm_block = block;
            }
            out[got][0] = h->adpcm[at * ch] / 32768.0f;
            out[got][1] = h->adpcm[at * ch + (stereo ? 1 : 0)] / 32768.0f;
        } else {
            int cs = csize[container] ? csize[container] : 2;
            uint32_t bytes = (uint32_t)(cs * ch);
            (void)spb;
            for (int c = 0; c < ch; c++) {
                uint32_t a = stream ? seg_addr + cbo * bytes + (uint32_t)(c * cs) : sge_addr(ba + cbo * bytes + (uint32_t)(c * cs));
                float f;
                switch (size) {
                case 0: f = ((float)*pa(a) - 128.0f) / 128.0f; break;
                case 1: { int16_t s; memcpy(&s, pa(a), 2); f = s / 32768.0f; break; }
                case 2: f = (float)((int32_t)(rd32(a) << 8) >> 8) / 8388608.0f; break;
                default: f = (float)(int32_t)rd32(a) / 2147483648.0f; break;
                }
                out[got][c] = f;
            }
            if (!stereo) out[got][1] = out[got][0];
        }
    }
    if (cbo > ebo) {
        if (stream) {
            int idx = ssl[v].index;
            cbo = 0;
            h->adpcm_block = -1;
            if (++ssl[v].seg >= ssl[v].count[idx]) {
                ssl[v].index = (idx + 1) % 2, ssl[v].seg = 0;
                notify(v, idx);
            }
        } else if (fmt & FMT_LOOP) {
            cbo = lbo;
            h->adpcm_block = -1;
        } else {
            cbo = ebo;
            voice_off(v);
        }
    }
    vset_mask(v, V_PAR_OFFSET, 0xFFFFFF, cbo);
    return got;
}

/* The next source sample of voice v; 0 when there is none (*dry set). */
static void next_sample(unsigned v, float s[2], int *dry) {
    VoiceHost *h = &host[v];
    if (h->pos >= h->len) {
        h->pos = h->len = 0;
        for (int tries = 0; tries < 4 && !h->len; tries++) { /* a segment or loop boundary can return a short count */
            if (!(vget(v, V_PAR_STATE) & STATE_ACTIVE)) break;
            int n = voice_samples(v, h->buf, 64);
            if (n < 0) break;
            h->len = n;
        }
    }
    if (h->pos < h->len) {
        s[0] = h->buf[h->pos][0], s[1] = h->buf[h->pos][1];
        h->pos++;
    } else {
        s[0] = s[1] = 0;
        *dry = 1;
    }
}

static float attenuate(uint32_t vol) {
    vol &= 0xFFF;
    return vol == 0xFFF ? 0.0f : powf(10.0f, (float)vol / -1280.0f);
}

static void voice_process(unsigned v, float mix[BINS][FRAME]) {
    uint32_t fmt = vget(v, V_CFG_FMT);
    if (vget(v, V_PAR_STATE) & STATE_PAUSED) return;
    float ef = envelope(v, 0);
    int16_t pitch = (int16_t)(vget(v, V_TAR_PITCH_LINK) >> 16);
    int8_t pscale = (int8_t)(vget(v, V_CFG_ENV0) >> 24);
    double step = pow(2.0, (pitch + pscale * 32 * ef) / 4096.0);
    float ea = envelope(v, 1);
    if (!(vget(v, V_PAR_STATE) & STATE_ACTIVE)) return;

    float s[FRAME][2];
    if (fmt & FMT_MULTIPASS) { /* the sub-mix the voices before it put in its bin */
        int b = (int)FMT_MULTIPASS_BIN(fmt);
        for (int i = 0; i < FRAME; i++) s[i][0] = s[i][1] = mix[b][i];
        if (fmt & FMT_CLEAR_MIX) memset(mix[b], 0, sizeof mix[b]);
    } else {
        VoiceHost *h = &host[v];
        int dry = 0;
        for (int i = 0; i < FRAME; i++) {
            while (h->frac >= 1.0) {
                h->prev[0] = h->cur[0], h->prev[1] = h->cur[1];
                next_sample(v, h->cur, &dry);
                h->frac -= 1.0;
            }
            float t = (float)h->frac;
            s[i][0] = h->prev[0] + (h->cur[0] - h->prev[0]) * t;
            s[i][1] = h->prev[1] + (h->cur[1] - h->prev[1]) * t;
            h->frac += step;
        }
        if (!(vget(v, V_PAR_STATE) & STATE_ACTIVE)) return;
    }

    /* The voice's low-pass filter (FMODE 1, DLS2; mono 2D voices also in mode
     * 3): cutoff and resonance per channel from TAR_FCA/FCB, as xemu reads
     * them. Forza's wind and road noise is full-band noise shaped this way;
     * unfiltered it was a hiss over the whole race. */
    {
        int ch = (fmt & FMT_STEREO) ? 2 : 1, fmode = (int)((vget(v, V_CFG_MISC) >> 16) & 3);
        int lpf = v < MAX_3D_VOICES ? fmode == 1 : ch == 2 ? fmode == 1 : (fmode & 1);
        if (lpf) {
            VoiceHost *h = &host[v];
            for (int c = 0; c < 2; c++) {
                uint32_t fc = vget(v, 0x74 + (uint32_t)(c % ch) * 4);
                float f = powf(2.0f, (float)(int16_t)(fc & 0xFFFF) / 4096.0f), q = (float)(fc >> 16) / 32768.0f;
                f = f < 0.003906f ? 0.003906f : f > 0.95f ? 0.95f : f; /* cutoff as a fraction of 24 kHz */
                q = q < 0.079407f ? 0.079407f : q > 1 ? 1 : q;
                /* A topology-preserving state-variable filter (Zavalishin),
                 * stable at any cutoff: the plain Chamberlin form blew up near
                 * the top of the range, and its infinities silenced the mix. */
                float g = tanf(1.5707963f * f), k = 2.0f * q;
                if (k < 0.5f) k = 0.5f; /* resonance kept mild: unknown how the hardware scales it */
                float a1 = 1.0f / (1.0f + g * (g + k)), a2 = g * a1, a3 = g * a2;
                if (!isfinite(h->low[c]) || !isfinite(h->band[c])) h->low[c] = h->band[c] = 0;
                for (int i = 0; i < FRAME; i++) {
                    float v3 = s[i][c] - h->low[c], v1 = a1 * h->band[c] + a2 * v3, v2 = h->low[c] + a2 * h->band[c] + a3 * v3;
                    h->band[c] = 2 * v1 - h->band[c], h->low[c] = 2 * v2 - h->low[c];
                    s[i][c] = v2 > 1 ? 1 : v2 < -1 ? -1 : v2;
                }
            }
        }
    }

    uint32_t vb = vget(v, V_CFG_VBIN), va = vget(v, V_TAR_VOLA), vbv = vget(v, V_TAR_VOLB), vc = vget(v, V_TAR_VOLC);
    int bin[8] = {(int)(vb & 31), (int)((vb >> 5) & 31), (int)((vb >> 10) & 31), (int)((vb >> 16) & 31),
                  (int)((vb >> 21) & 31), (int)((vb >> 26) & 31), (int)(fmt & 31), (int)((fmt >> 5) & 31)};
    if (v < MAX_3D_VOICES)
        for (int i = 0; i < 4; i++) bin[i] = hrtf_submix[i];
    uint32_t vol[8] = {(va >> 4) & 0xFFF, va >> 20, (vbv >> 4) & 0xFFF, vbv >> 20, (vc >> 4) & 0xFFF, vc >> 20,
                       (vc & 0xF) << 8 | (vbv & 0xF) << 4 | (va & 0xF), ((vc >> 16) & 0xF) << 8 | ((vbv >> 16) & 0xF) << 4 | ((va >> 16) & 0xF)};
    int ch = (fmt & FMT_STEREO) ? 2 : 1;
    for (int b = 0; b < 8; b++) {
        float g = ea * attenuate(vol[b]);
        if (g == 0) continue;
        int hr = (v < MAX_3D_VOICES && b < 4) ? hrtf_headroom : submix_headroom[bin[b]];
        g /= (float)(1 << hr);
        for (int i = 0; i < FRAME; i++) mix[bin[b]][i] += g * s[i][b % ch];
    }
}

/* One frame: 32 stereo samples into out. Returns 0, with silence, while
 * the setup engine is off or the APU is not set up yet, and -1 while the
 * front end is trapped or halted (DSOUND's ISR is taking an idle voice
 * back): then the caller waits for it rather than skipping the frame. */
int rt_vp_frame(float out[FRAME][2], int *raise_irq) {
    static float mix[BINS][FRAME];
    memset(out, 0, sizeof(float) * FRAME * 2);
    pthread_mutex_lock(&vp_lock);
    if (!(REG(NV_PAPU_SECTL) & SECTL_XCNTMODE) || (REG(NV_PAPU_FECTL) & FECTL_FEMETHMODE) || !REG(NV_PAPU_VPVADDR)) {
        int trapped = (REG(NV_PAPU_FECTL) & FECTL_FEMETHMODE) != 0;
        *raise_irq = irq_pending, irq_pending = 0;
        pthread_mutex_unlock(&vp_lock);
        return trapped ? -1 : 0;
    }
    memset(mix, 0, sizeof mix);
    for (int list = 0; list < 3; list++) {
        uint32_t v = REG(list_top[list]) & 0xFFFF;
        for (int guard = 0; v != 0xFFFF && guard < MAX_VOICES; guard++) {
            if (v >= MAX_VOICES) break;
            uint32_t next = vget(v, V_TAR_PITCH_LINK) & 0xFFFF;
            if (!(vget(v, V_PAR_STATE) & STATE_ACTIVE)) {
                if (REG(NV_PAPU_FETFORCE1) & FETFORCE1_SE2FE_IDLE_VOICE) { /* hand it back: DSOUND unlinks it in its ISR */
                    REG(NV_PAPU_FEDECMETH) = SE2FE_IDLE_VOICE, REG(NV_PAPU_FEDECPARAM) = v;
                    REG(NV_PAPU_FECTL) = (REG(NV_PAPU_FECTL) & ~(FECTL_FEMETHMODE | FECTL_FETRAPREASON)) | FECTL_TRAPPED | FECTL_REQUESTED;
                    REG(NV_PAPU_ISTS) |= ISTS_FETINTSTS;
                    irq_pending = 1;
                    goto done; /* one at a time: the next frames wait until the ISR lets the front end run */
                }
            } else if (!(locked[v / 64] & (1ull << (v % 64)))) {
                voice_process(v, mix);
            }
            v = next;
        }
    }
done:
    for (int i = 0; i < FRAME; i++) {
        /* Speakers: front left/right, centre, rear left/right; then the 3D
         * sound DSOUND routes through the GP DSP's crosstalk program (bins
         * 6-9, front left/right and rear left/right, as the HRTF submix
         * register names them): Forza's engines, tyres and other cars all
         * arrive there through multipass voices. Without the DSP they were
         * silent. LFE (3) and the effect sends (10 and up) are dropped. */
        float c = 0.7071f * mix[2][i];
        out[i][0] = mix[0][i] + c + 0.7071f * mix[4][i] + mix[6][i] + 0.7071f * mix[8][i];
        out[i][1] = mix[1][i] + c + 0.7071f * mix[5][i] + mix[7][i] + 0.7071f * mix[9][i];
        if (!isfinite(out[i][0])) out[i][0] = 0;
        if (!isfinite(out[i][1])) out[i][1] = 0;
    }
    *raise_irq = irq_pending, irq_pending = 0;
    pthread_mutex_unlock(&vp_lock);
    return 1;
}
