/* Loads the player's default.xbe into guest memory and starts it.
 *
 * usage: forza [path/to/default.xbe]
 *   XBRT_LOG=1   log kernel calls (2: also memory and files)
 *   XBRT_LOG_FROM=<seconds>  start logging only then
 *   XBRT_THREAD_DUMP=<seconds>  print every thread's state then (debugging)
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

    /* XBRT_FPS=30 or 60: Forza's frame rate. The retail game presents every
     * second vertical blank (30 fps); the 60 fps patch is this one value in
     * .data set to 1. Only where the neighbouring bytes are Forza's. */
    const char *fps = getenv("XBRT_FPS");
    const uint32_t at = 0x554944;
    int forza = at + 8 <= base + img && xb_rd32(at - 4) == 1 && (xb_rd32(at) == 1 || xb_rd32(at) == 2) && xb_rd32(at + 4) == 0x80000002u;
    if (forza) rt_frame_interval_at = at; /* the flip pacing reads it (nv2a.c) */
    if (fps && *fps) {
        uint32_t interval = atoi(fps) >= 60 ? 1 : 2;
        if (forza) {
            rt_log("XBRT_FPS=%s: frame interval %u -> %u vertical blanks\n", fps, xb_rd32(at), interval);
            xb_wr32(at, interval);
        } else {
            fprintf(stderr, "xbrt: XBRT_FPS: this is not the Forza Motorsport the setting knows; ignored\n");
        }
    }

    rt_image.base = base;
    rt_image.size = img;
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

/* Functions built with xbrecomp -trace call these: one line per call and
 * per return. Arguments that point at text show it. */
static void trace_arg(char *out, size_t n, uint32_t v) {
    int len = 0;
    if (v >= 0x10000 && v < 0x08000000)
        while (len < 60 && xb_mem[v + len] >= 0x20 && xb_mem[v + len] < 0x7F) len++;
    if (len >= 3 && !xb_mem[v + len]) snprintf(out, n, "%08x \"%.*s\"", v, len, (const char *)xb_mem + v);
    else snprintf(out, n, "%08x", v);
}

void xb_trace_enter(XbCtx *c, uint32_t fn) {
    char a[5][80];
    for (int i = 0; i < 5; i++) trace_arg(a[i], sizeof a[i], xb_rd32(c->esp + 4 + 4 * i));
    char e[80];
    trace_arg(e, sizeof e, c->ecx);
    fprintf(stderr, "[%10.3f] trace %08x from %08x: ecx %s; %s, %s, %s, %s, %s\n", rt_now_100ns() / 1e7, fn, xb_rd32(c->esp), e,
            a[0], a[1], a[2], a[3], a[4]);
}

void xb_trace_leave(XbCtx *c, uint32_t fn) {
    fprintf(stderr, "[%10.3f] trace %08x returns %08x\n", rt_now_100ns() / 1e7, fn, c->eax);
}

static int log_deferred;  /* XBRT_LOG's level, held back until XBRT_LOG_FROM */
static double log_from;

void rt_log_tick(void) {
    static const char *dumps; /* XBRT_THREAD_DUMP: seconds, comma-separated */
    static double dump_at = -1;
    if (dump_at < 0) {
        dumps = getenv("XBRT_THREAD_DUMP");
        dump_at = dumps && atof(dumps) > 0 ? atof(dumps) : 0;
    }
    if (dump_at > 0 && rt_now_100ns() >= (uint64_t)(dump_at * 1e7)) {
        fprintf(stderr, "---- threads at %.1f s ----\n", rt_now_100ns() / 1e7);
        rt_thread_dump();
        dumps = strchr(dumps, ',');
        dump_at = dumps ? atof(++dumps) : 0;
    }
    { /* A hang: no frame for 8 s once the game has shown some. Every
       * thread's state, once a stall, for the log (XBRT_HANG_DUMP=0: off);
       * a wait that never ends is otherwise never logged. */
        static int on = -1, dumped;
        static uint32_t flips;
        static uint64_t since;
        if (on < 0) on = !getenv("XBRT_HANG_DUMP") || atoi(getenv("XBRT_HANG_DUMP"));
        uint64_t now = rt_now_100ns();
        if (nv2a.flips != flips || nv2a.flips < 100) flips = nv2a.flips, since = now, dumped = 0;
        else if (on && !dumped && now - since > 80000000) {
            fprintf(stderr, "---- no frame for 8 s at %.1f s (after %u): threads ----\n", now / 1e7, flips);
            rt_thread_dump();
            dumped = 1;
        }
    }
    if (log_deferred && rt_now_100ns() >= (uint64_t)(log_from * 1e7)) {
        rt_log_level = log_deferred, log_deferred = 0;
        rt_log("logging from here on (XBRT_LOG_FROM)\n");
    }
}

void rt_sleep_precise(uint64_t ns) {
#ifdef _WIN32
    static __thread HANDLE timer;
    if (!timer) timer = CreateWaitableTimerExW(NULL, NULL, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    LARGE_INTEGER due = {.QuadPart = -(LONGLONG)(ns / 100)};
    if (timer && SetWaitableTimer(timer, &due, 0, NULL, NULL, FALSE)) WaitForSingleObject(timer, INFINITE);
    else Sleep((DWORD)(ns / 1000000));
#else
    struct timespec ts = {(time_t)(ns / 1000000000u), (long)(ns % 1000000000u)};
    nanosleep(&ts, NULL);
#endif
}

/* XBRT_PROFILE=<file>: where a thread spends its time (the device
 * thread's, nv2a.c), sampled every millisecond from inside the process:
 * the instruction and two callers, rewritten every 5 s as "<count> <pc>
 * <caller> <caller's caller>" after a "base" line for addr2line. A
 * debugger attaching to sample stopped the game long enough to skew it. */
#ifdef _WIN32
#define PROF_SLOTS 65536
static struct { uint64_t pc[3]; uint32_t n; } prof_tab[PROF_SLOTS];

static void prof_write(const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "base %llx\n", (unsigned long long)(uintptr_t)GetModuleHandleW(NULL));
    for (int i = 0; i < PROF_SLOTS; i++)
        if (prof_tab[i].n)
            fprintf(f, "%u %llx %llx %llx\n", prof_tab[i].n, (unsigned long long)prof_tab[i].pc[0], (unsigned long long)prof_tab[i].pc[1],
                    (unsigned long long)prof_tab[i].pc[2]);
    fclose(f);
}

static void *prof_main(void *arg) {
    HANDLE th = arg;
    const char *path = getenv("XBRT_PROFILE");
    uint64_t last = rt_now_100ns();
    for (;;) {
        rt_sleep_precise(1000000);
        if (SuspendThread(th) == (DWORD)-1) break;
        CONTEXT c = {.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER};
        uint64_t pc[3] = {0};
        if (GetThreadContext(th, &c)) {
            pc[0] = c.Rip;
            for (int k = 1; k < 3; k++) { /* by the unwind tables: no frame pointers at -O2 */
                DWORD64 image;
                PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(c.Rip, &image, NULL);
                if (!fn) break;
                void *handler;
                DWORD64 frame;
                RtlVirtualUnwind(UNW_FLAG_NHANDLER, image, c.Rip, fn, &c, &handler, &frame, NULL);
                pc[k] = c.Rip;
            }
        }
        ResumeThread(th);
        uint64_t h = (pc[0] * 0x9E3779B97F4A7C15ull ^ pc[1] * 0xC2B2AE3D27D4EB4Full ^ pc[2]) >> 48;
        for (int probe = 0; probe < 64; probe++, h = (h + 1) % PROF_SLOTS)
            if (!prof_tab[h].n || !memcmp(prof_tab[h].pc, pc, sizeof pc)) {
                memcpy(prof_tab[h].pc, pc, sizeof pc), prof_tab[h].n++;
                break;
            }
        if (rt_now_100ns() - last > 50000000) last = rt_now_100ns(), prof_write(path);
    }
    return NULL;
}
#endif

void rt_profile_thread(pthread_t t) {
#ifdef _WIN32
    if (!getenv("XBRT_PROFILE")) return;
    pthread_t p;
    pthread_create(&p, NULL, prof_main, pthread_gethandle(t));
#else
    (void)t;
#endif
}

int main(int argc, char **argv) {
    rt_settings_load(); /* forza.ini: before anything reads an XBRT_* switch */
    rt_soundtracks_init();
    const char *env = getenv("XBRT_LOG");
    rt_log_level = env ? atoi(env) : 0;
    const char *from = getenv("XBRT_LOG_FROM");
    if (from && atof(from) > 0 && rt_log_level) log_from = atof(from), log_deferred = rt_log_level, rt_log_level = 0;
#ifdef _WIN32
    timeBeginPeriod(1); /* 1 ms sleeps, as the DPC thread and waits expect */
    { /* which Windows 11 drops for a process with no window in view (headless,
       * minimised, covered): sleeps to the next vertical blank woke 4-15 ms
       * late. Nor slow its threads to save power. */
        PROCESS_POWER_THROTTLING_STATE p = {PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED | PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION, 0};
        SetProcessInformation(GetCurrentProcess(), ProcessPowerThrottling, &p, sizeof p);
    }
#endif
    const char *path = argc > 1 ? argv[1] : "default.xbe";

    rt_mem_init();
    load_xbe(path);
    rt_kernel_init();
    rt_fibers_init();
    rt_crypto_init();
    rt_files_init();
    rt_mods_installer_records();
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
