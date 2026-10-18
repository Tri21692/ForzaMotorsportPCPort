/* Guest memory: one 4 GB reservation and simple allocators over it.
 *
 * The Xbox's 64 MB of RAM is shared with the GPU. It is one host memory
 * object mapped at every place the Xbox sees it: 0x80000000 + physical
 * (the kernel's view, where contiguous memory lives), 0xF0000000 +
 * physical (write-combined, which D3D uses for GPU data).
 */
#define _GNU_SOURCE
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rt.h"

uint8_t *xb_mem;

/* ---- user virtual memory: a list of regions, first fit, 64 KB grain ---- */

typedef struct {
    uint32_t base, size, protect, state; /* state: MEM_RESERVE 0x2000 / MEM_COMMIT 0x1000 */
} Region;

static Region *regions;
static int nregions, capregions;

static void region_add(uint32_t base, uint32_t size, uint32_t protect, uint32_t state) {
    if (nregions == capregions) {
        capregions = capregions ? 2 * capregions : 64;
        regions = realloc(regions, capregions * sizeof *regions);
    }
    /* Keep sorted by base. */
    int i = nregions;
    while (i > 0 && regions[i - 1].base > base) {
        regions[i] = regions[i - 1];
        i--;
    }
    regions[i] = (Region){base, size, protect, state};
    nregions++;
}

static Region *region_at(uint32_t addr) {
    for (int i = 0; i < nregions; i++)
        if (addr >= regions[i].base && addr - regions[i].base < regions[i].size) return &regions[i];
    return NULL;
}

static int range_free(uint32_t base, uint32_t size) {
    for (int i = 0; i < nregions; i++) {
        uint32_t b = regions[i].base, e = b + regions[i].size;
        if (base < e && b < base + size) return 0;
    }
    return 1;
}

void rt_mem_reserve_image(uint32_t base, uint32_t size) {
    region_add(base, (size + 0xFFFF) & ~0xFFFFu, 0x04 /* PAGE_READWRITE */, 0x1000);
}

uint32_t rt_user_alloc(uint32_t base, uint32_t size, uint32_t protect) {
    size = (size + 0xFFF) & ~0xFFFu;
    if (size == 0) return 0;
    if (base) {
        Region *r = region_at(base);
        if (r) { /* committing inside an existing reservation */
            r->state = 0x1000;
            return base & ~0xFFFu;
        }
        base &= ~0xFFFFu;
        if (!range_free(base, size)) return 0;
        region_add(base, size, protect, 0x1000);
        return base;
    }
    for (uint32_t a = 0x01000000u; a + size < RT_USER_LIMIT; a += 0x10000) {
        if (range_free(a, size)) {
            region_add(a, size, protect, 0x1000);
            return a;
        }
    }
    return 0;
}

int rt_user_free(uint32_t base, uint32_t *size) {
    for (int i = 0; i < nregions; i++) {
        if (regions[i].base == (base & ~0xFFFu)) {
            if (size) *size = regions[i].size;
            memset(xb_mem + regions[i].base, 0, regions[i].size);
            memmove(&regions[i], &regions[i + 1], (nregions - i - 1) * sizeof *regions);
            nregions--;
            return 1;
        }
    }
    return 0;
}

int rt_user_query(uint32_t addr, uint32_t *base, uint32_t *size, uint32_t *protect, uint32_t *state) {
    Region *r = region_at(addr);
    if (r) {
        *base = r->base, *size = r->size, *protect = r->protect, *state = r->state;
        return 1;
    }
    /* A free range: up to the next region. */
    uint32_t end = RT_USER_LIMIT;
    for (int i = 0; i < nregions; i++)
        if (regions[i].base > addr && regions[i].base < end) end = regions[i].base;
    *base = addr & ~0xFFFu, *size = end - *base, *protect = 0x01, *state = 0x10000; /* MEM_FREE */
    return 0;
}

/* ---- physical memory: contiguous allocations, one bit per page ---- */

#define PAGES (RT_PHYS_SIZE / 0x1000)
static uint8_t page_used[PAGES];

typedef struct {
    uint32_t base, size;
} Block;
static Block *blocks;
static int nblocks, capblocks;

static void block_add(uint32_t base, uint32_t size) {
    if (nblocks == capblocks) {
        capblocks = capblocks ? 2 * capblocks : 256;
        blocks = realloc(blocks, capblocks * sizeof *blocks);
    }
    blocks[nblocks++] = (Block){base, size};
}

static Block *block_at(uint32_t addr) {
    for (int i = nblocks - 1; i >= 0; i--)
        if (blocks[i].base == addr) return &blocks[i];
    return NULL;
}

/* Like the kernel, allocate from the top of the acceptable range down, so
 * low memory stays free for code that needs it. */
uint32_t rt_contig_alloc(uint32_t size, uint32_t lo, uint32_t hi, uint32_t align) {
    uint32_t n = (size + 0xFFF) / 0x1000;
    uint32_t step = align > 0x1000 ? align / 0x1000 : 1;
    if (n == 0) return 0;
    if (hi >= RT_PHYS_SIZE) hi = RT_PHYS_SIZE - 1;
    uint32_t lop = lo / 0x1000, hip = hi / 0x1000 + 1; /* pages [lop, hip) */
    if (hip < lop + n) return 0;
    for (int64_t p = (int64_t)(hip - n) / step * step; p >= lop; p -= step) {
        uint32_t i = 0;
        while (i < n && !page_used[p + i]) i++;
        if (i < n) continue;
        memset(page_used + p, 1, n);
        uint32_t va = RT_PHYS_VIEW + (uint32_t)p * 0x1000;
        block_add(va, n * 0x1000);
        memset(xb_mem + va, 0, n * 0x1000);
        return va;
    }
    return 0;
}

void rt_contig_free(uint32_t va) {
    Block *b = block_at(va);
    if (!b || va < RT_PHYS_VIEW || va - RT_PHYS_VIEW >= RT_PHYS_SIZE) return;
    memset(page_used + (va - RT_PHYS_VIEW) / 0x1000, 0, b->size / 0x1000);
    *b = blocks[--nblocks];
}

uint32_t rt_phys_of(uint32_t va) {
    if (va >= RT_PHYS_VIEW && va - RT_PHYS_VIEW < RT_PHYS_SIZE) return va - RT_PHYS_VIEW;
    if (va >= RT_PHYS_WC && va - RT_PHYS_WC < RT_PHYS_SIZE) return va - RT_PHYS_WC;
    return va & 0x7FFFFFFFu; /* not GPU-visible here; good enough for logging */
}

/* ---- bump allocators for pool and kernel data ---- */

typedef struct {
    uint32_t next, limit;
} Bump;

static Bump pool = {RT_POOL_BASE, RT_POOL_LIMIT};
static Bump kdata = {RT_KDATA_BASE, RT_KDATA_LIMIT};

static uint32_t bump(Bump *b, uint32_t size, uint32_t align) {
    if (align < 16) align = 16;
    uint32_t a = (b->next + align - 1) & ~(align - 1);
    if (a + size > b->limit || a + size < a) return 0;
    b->next = a + size;
    block_add(a, size);
    return a;
}

uint32_t rt_pool_alloc(uint32_t size) { return bump(&pool, size, 16); }
uint32_t rt_kdata_alloc(uint32_t size) { return bump(&kdata, size, 16); }

uint32_t rt_size_of(uint32_t addr) {
    Block *b = block_at(addr);
    return b ? b->size : 0;
}

static void map_ram(int fd, uint32_t at, uint32_t offset, uint32_t size) {
    if (mmap(xb_mem + at, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED, fd, offset) == MAP_FAILED) {
        perror("xbrt: mapping Xbox RAM");
        exit(1);
    }
}

void rt_mem_init(void) {
    xb_mem = mmap(NULL, (1ull << 32) + 0x10000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (xb_mem == MAP_FAILED) {
        perror("xbrt: reserving 4 GB of guest memory");
        exit(1);
    }
    int fd = memfd_create("xbox-ram", 0);
    if (fd < 0 || ftruncate(fd, RT_PHYS_SIZE) < 0) {
        perror("xbrt: creating Xbox RAM");
        exit(1);
    }
    map_ram(fd, RT_PHYS_VIEW, 0, RT_PHYS_SIZE);
    map_ram(fd, RT_PHYS_WC, 0, RT_PHYS_SIZE);
    close(fd);
    /* The kernel's own pages at the bottom, and the GPU instance memory
     * plus padding at the top, are never handed out. */
    memset(page_used, 1, 0x100000 / 0x1000);
    memset(page_used + (RT_PHYS_INSTANCE / 0x1000), 1, (RT_PHYS_SIZE - RT_PHYS_INSTANCE) / 0x1000);
}
