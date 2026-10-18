/* Loads the player's default.xbe into guest memory and starts it.
 *
 * usage: forza [path/to/default.xbe]
 *   XBRT_LOG=1   log kernel calls (2: also memory and files)
 *   XBRT_DISC    directory holding the extracted disc (default: the XBE's)
 *   XBRT_HDD     directory for the hard disk partitions (default: ./hdd)
 */
#include <libgen.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "nv2a.h"

#ifdef _WIN32
#include <windows.h>
#endif

RtImage rt_image;
int rt_log_level;

void rt_log(const char *fmt, ...) {
    if (!rt_log_level) return;
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[%9.3f] ", rt_now_100ns() / 1e7);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

/* Print the guest stack's likely return addresses, the closest thing to a
 * backtrace: dwords that point at the instruction after a translated call. */
void rt_backtrace(XbCtx *c) {
    if (!c) return;
    fprintf(stderr, "  eax=%08x ecx=%08x edx=%08x ebx=%08x esp=%08x ebp=%08x esi=%08x edi=%08x\n",
            c->eax, c->ecx, c->edx, c->ebx, c->esp, c->ebp, c->esi, c->edi);
    fprintf(stderr, "  stack:");
    for (int i = 0; i < 64; i++) fprintf(stderr, "%s%08x", i % 8 ? " " : "\n    ", xb_rd32(c->esp + 4 * i));
    fprintf(stderr, "\n");
}

void rt_fatal(XbCtx *c, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "xbrt: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    rt_backtrace(c);
    fflush(stderr);
    _exit(1);
}

void xb_trap(XbCtx *c, uint32_t addr, const char *why) { rt_fatal(c, "trap at %08x: %s", addr, why); }

uint64_t xb_rdtsc(XbCtx *c) {
    (void)c;
    return rt_now_100ns() * 733 / 10; /* a 733 MHz Pentium III */
}

/* cpuid as the Xbox's CPU answers it: a GenuineIntel Pentium III
 * (family 6, model 8) with FPU, TSC, CMOV, MMX, FXSR and SSE, and its
 * 128 KB L2 cache. Code picks routines from this (Bink and the C runtime
 * test for MMX), so it must not see the host's CPU. */
void xb_cpuid(XbCtx *c) {
    uint32_t leaf = c->eax;
    c->eax = c->ebx = c->ecx = c->edx = 0;
    switch (leaf) {
    case 0:
        c->eax = 2;           /* highest leaf */
        c->ebx = 0x756E6547u; /* "Genu" */
        c->edx = 0x49656E69u; /* "ineI" */
        c->ecx = 0x6C65746Eu; /* "ntel" */
        break;
    case 1:
        c->eax = 0x0000068Au;  /* family 6, model 8, stepping 10 */
        c->edx = 0x0383F9FFu;  /* FPU..PGE, CMOV, PAT, PSE36, MMX, FXSR, SSE */
        break;
    case 2:
        c->eax = 0x03020101u; /* TLB and L1 descriptors */
        c->edx = 0x0C040841u; /* L1 caches, 128 KB L2 */
        break;
    }
}

/* ---- XBE loading ---- */

static uint8_t *read_file(const char *path, size_t *n) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = malloc(len);
    if (fread(b, 1, len, f) != (size_t)len) {
        free(b);
        b = NULL;
    }
    fclose(f);
    *n = len;
    return b;
}

static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }

static void load_xbe(const char *path) {
    size_t n;
    uint8_t *raw = read_file(path, &n);
    if (!raw || n < 0x178 || memcmp(raw, "XBEH", 4)) rt_fatal(NULL, "%s is not an XBE", path);
    uint32_t base = le32(raw + 0x104), hdr = le32(raw + 0x108), img = le32(raw + 0x10C);
    uint32_t nsec = le32(raw + 0x11C), sec = le32(raw + 0x120) - base;
    uint32_t entry = le32(raw + 0x128), thunk = le32(raw + 0x158);
    /* Retail keys; the debug ones give an entry outside the image. */
    uint32_t e = entry ^ 0xA8FC57ABu, k = thunk ^ 0x5B6D40B6u;
    if (e < base || e >= base + img) e = entry ^ 0x94859D4Bu, k = thunk ^ 0xEFB1F152u;

    memcpy(xb_mem + base, raw, hdr); /* the game reads its own header back */
    for (uint32_t i = 0; i < nsec; i++) {
        const uint8_t *s = raw + sec + i * 0x38;
        uint32_t va = le32(s + 4), rawoff = le32(s + 12), rawsize = le32(s + 16);
        if (rawoff + rawsize > n) rt_fatal(NULL, "section %u is past the end of the file", i);
        memcpy(xb_mem + va, raw + rawoff, rawsize);
    }
    rt_mem_reserve_image(base, img);

    rt_image.base = base;
    rt_image.entry = e;
    rt_image.thunk = k;
    rt_image.tls_dir = le32(raw + 0x12C);
    if (rt_image.tls_dir) {
        uint32_t d = rt_image.tls_dir;
        uint32_t data = xb_rd32(d + 4) - xb_rd32(d), zero = xb_rd32(d + 16);
        rt_image.tls_size = ((data + zero + 15) & ~15u) + 4; /* as mainCRTStartup computes it */
    }
    snprintf(rt_image.path, sizeof rt_image.path, "%s", path);
    char tmp[1024];
    snprintf(tmp, sizeof tmp, "%s", path);
    snprintf(rt_image.dir, sizeof rt_image.dir, "%s", dirname(tmp));
    free(raw);
    rt_log("loaded %s: entry %08x, kernel thunks %08x, TLS %u bytes\n", path, e, k, rt_image.tls_size);
}

int main(int argc, char **argv) {
    const char *env = getenv("XBRT_LOG");
    rt_log_level = env ? atoi(env) : 0;
#ifdef _WIN32
    timeBeginPeriod(1); /* 1 ms sleeps, as the DPC thread and waits expect */
#endif
    const char *path = argc > 1 ? argv[1] : "default.xbe";

    rt_mem_init();
    load_xbe(path);
    rt_kernel_init();
    rt_fibers_init();
    rt_crypto_init();
    rt_files_init();
    rt_hw_init();
    rt_nv2a_init();
    rt_apu_init();
    rt_display_init();

    RtThread *t = rt_thread_create(0x40000, rt_image.tls_size, 0);
    rt_dpc_start();
    rt_thread_run_main(t, rt_image.entry);
    rt_log("boot thread finished; the game's threads keep running\n");
    pthread_exit(NULL); /* the process ends when the last guest thread does */
}
