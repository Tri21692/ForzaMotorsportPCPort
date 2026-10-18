/*
 * Differential test harness: runs recompiled functions on prepared guest
 * state and prints the resulting registers and a memory hash. The same
 * state is built by unicorn_ref.py on a reference CPU, and the test
 * compares the two outputs.
 *
 * usage: harness image.bin < cases
 *   image.bin: records of (u32 guest address, u32 length, bytes)
 *   each case line: func_index eax ecx edx ebx ebp esi edi seed
 * output per case: "ok eax ecx edx ebx esp ebp esi edi memcrc xmmcrc fpu" or
 * "trap ADDR why", where fpu is the x87 TOP and a CRC of the eight physical
 * registers. Condition codes are left out: Intel leaves them undefined
 * after most instructions, and cases that need them store them with fnstsw. A case gets 0.2 s; the reference CPU stops
 * after 2M instructions, so a case that runs longer is never compared.
 *
 * Keep the memory layout and fill in sync with unicorn_ref.py.
 */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#include "xbrt.h"

#define SCRATCH_BASE 0x10000000u
#define SCRATCH_SIZE 0x00100000u
#define STACK_BASE 0x10F00000u
#define STACK_SIZE 0x00010000u
#define RETURN_SENTINEL 0x0BAD0000u

uint8_t *xb_mem;

typedef void (*xb_fn)(XbCtx *);
extern const xb_fn test_funcs[];
extern const unsigned test_func_count;

static jmp_buf trap_jmp;
static uint32_t trap_addr;
static const char *trap_why;

void xb_trap(XbCtx *c, uint32_t addr, const char *why) {
    (void)c;
    trap_addr = addr;
    trap_why = why;
    longjmp(trap_jmp, 1);
}
void xb_call_indirect(XbCtx *c, uint32_t target) { xb_trap(c, target, "indirect call"); }
void xb_kernel(XbCtx *c, uint32_t ordinal) { xb_trap(c, ordinal, "kernel call"); }
uint64_t xb_rdtsc(XbCtx *c) { xb_trap(c, 0, "rdtsc"); }

/* Writable ranges hashed after each case: scratch, stack, then the image's
 * writable sections as listed in image.bin (flag bit 0 of the length). */
typedef struct { uint32_t va, len; } Range;
static Range ranges[64];
static int nranges;

static uint32_t xs;
static uint32_t next_rand(void) {
    xs ^= xs << 13;
    xs ^= xs >> 17;
    xs ^= xs << 5;
    return xs;
}

/* Fill a region with dwords that are a mix of scratch pointers, small
 * integers and random bits, so real code finds plausible data. */
static void fill(uint32_t base, uint32_t size) {
    for (uint32_t off = 0; off < size; off += 4) {
        uint32_t v = next_rand(), w;
        switch (v & 3) {
        case 0: w = SCRATCH_BASE + (next_rand() & (SCRATCH_SIZE - 1) & ~3u); break;
        case 1: w = next_rand() & 0xFF; break;
        default: w = next_rand(); break;
        }
        /* No signaling NaN patterns: a real x87 quiets them on load and
         * Unicorn does not, so they would only test Unicorn. */
        if ((w & 0x7FC00000u) == 0x7F800000u && (w & 0x003FFFFFu)) w |= 0x00400000u; /* float */
        if ((w & 0x7FF80000u) == 0x7FF00000u) w |= 0x00080000u;                      /* double high word */
        xb_wr32(base + off, w);
    }
}

/* Random float bit patterns: mostly ordinary magnitudes (2^-7..2^8, either
 * sign), some zeros and some raw bits for NaN, infinity and denormals. */
static uint32_t rand_float_bits(void) {
    uint32_t v = next_rand();
    switch (v & 7) {
    case 0: return 0;
    case 1: return next_rand();
    default: return (next_rand() & 0x807FFFFFu) | ((120u + (next_rand() & 15)) << 23);
    }
}

static uint32_t crc32_update(uint32_t h, const uint8_t *p, uint32_t n);

/* CRC-32 as zlib computes it, over all ranges in order. */
static uint32_t hash_ranges(void) {
    uint32_t h = 0;
    for (int i = 0; i < nranges; i++) h = crc32_update(h, xb_mem + ranges[i].va, ranges[i].len);
    return h;
}

static uint32_t crc32_update(uint32_t h, const uint8_t *p, uint32_t n) {
    static uint32_t table[256];
    if (!table[1]) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[i] = c;
        }
    }
    h ^= 0xFFFFFFFFu;
    for (uint32_t j = 0; j < n; j++) h = table[(h ^ p[j]) & 0xFF] ^ (h >> 8);
    return h ^ 0xFFFFFFFFu;
}

static void done(void) {
    fflush(stdout);
    _exit(0);
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: harness image.bin < cases\n");
        return 2;
    }
    xb_mem = mmap(NULL, (1ull << 32) + 0x10000, PROT_READ | PROT_WRITE,
                  MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (xb_mem == MAP_FAILED) {
        perror("mmap");
        return 1;
    }
    ranges[nranges++] = (Range){SCRATCH_BASE, SCRATCH_SIZE};
    ranges[nranges++] = (Range){STACK_BASE, STACK_SIZE};

    FILE *img = fopen(argv[1], "rb");
    if (!img) {
        perror(argv[1]);
        return 1;
    }
    uint32_t hdr[2];
    while (fread(hdr, 4, 2, img) == 2) {
        uint32_t va = hdr[0], len = hdr[1] & 0x7FFFFFFFu;
        if (fread(xb_mem + va, 1, len, img) != len) {
            fprintf(stderr, "short image\n");
            return 1;
        }
        if ((hdr[1] & 0x80000000u) && nranges < 64) {
            ranges[nranges++] = (Range){va, len};
        }
    }
    fclose(img);

    unsigned idx;
    uint32_t r[7], seed;
    while (scanf("%u %x %x %x %x %x %x %x %x", &idx, &r[0], &r[1], &r[2], &r[3], &r[4], &r[5], &r[6], &seed) == 9) {
        fflush(stdout);
        /* Each case runs in a child so its writes cannot leak into the next.
         * Children leave through done(): exit() would also flush the
         * inherited stdin and, when stdin is a file, seek the shared offset
         * back, making the parent read old cases again. */
        pid_t pid = fork();
        if (pid == 0) {
            struct itimerval budget = {{0, 0}, {0, 200000}};
            setitimer(ITIMER_REAL, &budget, NULL);
            xs = seed ? seed : 1;
            fill(SCRATCH_BASE, SCRATCH_SIZE);
            fill(STACK_BASE, STACK_SIZE);
            XbCtx c = {0};
            for (int i = 0; i < 8; i++)
                for (int k = 0; k < 4; k++) c.xmm[i].u[k] = rand_float_bits();
            c.mxcsr = 0x1F80; /* power-on default */
            xb_fpu_setcw(&c, 0x037F); /* x87 power-on: 64-bit precision, nearest */
            c.eax = r[0]; c.ecx = r[1]; c.edx = r[2]; c.ebx = r[3];
            c.ebp = r[4]; c.esi = r[5]; c.edi = r[6];
            c.esp = STACK_BASE + STACK_SIZE - 0x1000;
            xb_push(&c, RETURN_SENTINEL);
            if (idx >= test_func_count) {
                printf("trap 0 bad index\n");
                done();
            }
            if (setjmp(trap_jmp)) {
                printf("trap %08x %s\n", trap_addr, trap_why);
                done();
            }
            test_funcs[idx](&c);
            uint8_t fregs[80];
            for (int i = 0; i < 8; i++) memcpy(fregs + 10 * i, &c.st[i], 10);
            printf("ok %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x %u/%08x\n", c.eax, c.ecx, c.edx, c.ebx,
                   c.esp, c.ebp, c.esi, c.edi, hash_ranges(), crc32_update(0, (const uint8_t *)c.xmm, sizeof c.xmm),
                   c.ftop, crc32_update(0, fregs, sizeof fregs));
            done();
        }
        int status;
        waitpid(pid, &status, 0);
        if (!WIFEXITED(status)) {
            printf("trap 0 crashed\n");
        }
    }
    return 0;
}
