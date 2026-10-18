/*
 * The PC runtime that recompiled Xbox code runs on: guest memory, the
 * Xbox kernel's exports (HLE), threads and the file system.
 *
 * Threads: each guest thread is a host thread with its own XbCtx. Only one
 * runs guest code at a time (the "big lock", rt_gil); kernel calls that
 * block release it. The Xbox has one CPU and game code was written for
 * that, so this matches what the game expects and keeps it deterministic
 * between blocking points.
 */
#ifndef RT_H
#define RT_H

#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>

#include "xbrt.h"

/* ---- status codes ---- */
#define STATUS_SUCCESS 0x00000000u
#define STATUS_TIMEOUT 0x00000102u
#define STATUS_PENDING 0x00000103u
#define STATUS_NOT_IMPLEMENTED 0xC0000002u
#define STATUS_INVALID_HANDLE 0xC0000008u
#define STATUS_INVALID_PARAMETER 0xC000000Du
#define STATUS_END_OF_FILE 0xC0000011u
#define STATUS_NO_MEMORY 0xC0000017u
#define STATUS_OBJECT_NAME_INVALID 0xC0000033u
#define STATUS_OBJECT_NAME_NOT_FOUND 0xC0000034u
#define STATUS_OBJECT_NAME_COLLISION 0xC0000035u
#define STATUS_OBJECT_PATH_NOT_FOUND 0xC000003Au
#define STATUS_ACCESS_DENIED 0xC0000022u
#define STATUS_NO_MORE_FILES 0x80000006u
#define STATUS_UNRECOGNIZED_VOLUME 0xC000014Fu

/* ---- logging ---- */
extern int rt_log_level; /* XBRT_LOG: 0 quiet, 1 kernel calls, 2 more */
void rt_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void rt_fatal(XbCtx *c, const char *fmt, ...) __attribute__((noreturn, format(printf, 2, 3)));

/* ---- memory (mem.c) ----
 * Regions of the 4 GB guest space:
 *   0x00010000  the XBE image, then user allocations (NtAllocateVirtualMemory)
 *   0x80000000+ contiguous memory, Xbox style (MmAllocateContiguousMemory)
 *   0xB0000000  kernel pool and system memory
 *   0xC0000000  kernel data: exported variables, thread and PCR blocks
 *   0xFFFF0000  fake addresses of kernel functions, stored in the thunks */
#define RT_USER_BASE 0x00010000u
#define RT_USER_LIMIT 0x7FFE0000u
#define RT_CONTIG_BASE 0x83000000u
#define RT_CONTIG_LIMIT 0x90000000u
#define RT_POOL_BASE 0xB0000000u
#define RT_POOL_LIMIT 0xBF000000u
#define RT_KDATA_BASE 0xC0000000u
#define RT_KDATA_LIMIT 0xC8000000u
#define RT_KFUNC_BASE 0xFFFF0000u

void rt_mem_init(void);
uint32_t rt_user_alloc(uint32_t base, uint32_t size, uint32_t protect); /* 0 on failure */
int rt_user_free(uint32_t base, uint32_t *size);
int rt_user_query(uint32_t addr, uint32_t *base, uint32_t *size, uint32_t *protect, uint32_t *state);
uint32_t rt_contig_alloc(uint32_t size, uint32_t align);
uint32_t rt_pool_alloc(uint32_t size);
uint32_t rt_kdata_alloc(uint32_t size);
void rt_mem_reserve_image(uint32_t base, uint32_t size);
uint32_t rt_size_of(uint32_t addr); /* size of a pool/contiguous block, 0 if unknown */

static inline char *rt_str(uint32_t a) { return (char *)(xb_mem + a); }

/* ---- the loaded XBE (main.c) ---- */
typedef struct {
    uint32_t base, entry, thunk, tls_dir;
    uint32_t tls_size; /* per-thread TLS area, as the kernel computes it */
    char path[1024];   /* host path of default.xbe */
    char dir[1024];    /* its directory: the default disc root */
} RtImage;
extern RtImage rt_image;

/* ---- threads and objects (thread.c) ---- */
extern pthread_mutex_t rt_gil;
extern pthread_cond_t rt_changed; /* broadcast whenever an object is signalled */

typedef struct RtThread {
    XbCtx ctx;
    uint32_t kthread; /* guest KTHREAD/ETHREAD */
    uint32_t kpcr;    /* guest KPCR this thread sees at fs: */
    uint32_t handle;
    uint32_t start, arg1, arg2; /* StartRoutine(StartContext1, StartContext2) */
    int terminated;
    uint32_t exit_code;
    pthread_t host;
} RtThread;

extern __thread RtThread *rt_self;
RtThread *rt_thread_create(uint32_t stack_size, uint32_t tls_size, uint32_t extra_size);
void rt_thread_start(RtThread *t);
void rt_thread_run_main(RtThread *t, uint32_t entry);
uint64_t rt_now_100ns(void); /* monotonic, Xbox system time units */

/* Handle table. */
enum { OBJ_FREE, OBJ_EVENT, OBJ_SEMAPHORE, OBJ_MUTANT, OBJ_THREAD, OBJ_FILE, OBJ_SYMLINK, OBJ_TIMER, OBJ_DIR };
typedef struct {
    int type;
    int refs;
    int signaled;       /* event state, semaphore count, mutant free (1) */
    int manual;         /* manual-reset event */
    int limit;          /* semaphore maximum */
    RtThread *owner;    /* mutant */
    int recursion;      /* mutant */
    RtThread *thread;   /* thread object */
    int fd;             /* file */
    char *path;         /* file, directory or symlink target (host or Xbox path) */
    void *dir;          /* directory listing cursor */
    uint64_t pos;       /* file position */
} RtObject;
uint32_t rt_handle_new(int type);
RtObject *rt_handle_get(uint32_t h);
void rt_handle_close(uint32_t h);

/* Waiting: block until ready(arg) or the deadline (absolute rt_now_100ns,
 * 0 for none). Called with rt_gil held; releases it while waiting.
 * Returns 1 if ready, 0 on timeout. */
int rt_wait(int (*ready)(void *), void *arg, uint64_t deadline);
uint64_t rt_deadline(uint32_t timeout_ptr); /* from a guest PLARGE_INTEGER */

/* ---- kernel exports (kernel.c) ---- */
void rt_kernel_init(void);
const XbKernelInfo *rt_kernel_info(uint32_t ordinal);
void rt_call(XbCtx *c, uint32_t target); /* run guest code at target */
/* Call a stdcall guest function from host code, e.g. a DPC routine, and
 * return its EAX. Every register is restored afterwards, so this is safe
 * in the middle of a kernel call. */
uint32_t rt_guest_call(XbCtx *c, uint32_t fn, int nargs, ...);

/* ---- timers and DPCs (dpc.c) ---- */
void rt_dpc_start(void);
void rt_dpc_queue(uint32_t dpc, uint32_t arg1, uint32_t arg2);
void rt_timer_set(uint32_t timer, uint64_t due, uint32_t period_ms, uint32_t dpc);
int rt_timer_cancel(uint32_t timer);

/* ---- files (file.c) ---- */
void rt_files_init(void);
uint32_t rt_symlink(const char *link, const char *target);
uint32_t rt_open(uint32_t *handle, uint32_t obj_attr, uint32_t disposition, uint32_t options, uint32_t *info);
uint32_t rt_read(uint32_t h, uint32_t buf, uint32_t len, uint32_t offset_ptr, uint32_t *done);
uint32_t rt_write(uint32_t h, uint32_t buf, uint32_t len, uint32_t offset_ptr, uint32_t *done);
const char *rt_object_name(uint32_t obj_attr, char *out, size_t n);

#endif
