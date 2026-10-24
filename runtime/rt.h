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
#include <time.h>

#include "xbrt.h"

/* ---- status codes ---- */
#ifdef _WIN32 /* windows.h has some of these, typed DWORD */
#undef STATUS_TIMEOUT
#undef STATUS_PENDING
#undef STATUS_INVALID_HANDLE
#undef STATUS_INVALID_PARAMETER
#undef STATUS_NO_MEMORY
#undef STATUS_USER_APC
#endif
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
/* Debugging toggles, flipped live with F5-F9 in the window (display.c):
 * drawing with one of the GPU's features off, to see what hides a thing. */
#define RT_DBG_NO_CULL 1u
#define RT_DBG_NO_DEPTH 2u
#define RT_DBG_NO_ALPHA 4u
#define RT_DBG_NO_CLIP 8u
#define RT_DBG_CPU_VSH 16u
extern volatile uint32_t rt_debug_keys;
void rt_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void rt_backtrace(XbCtx *c); /* registers and likely return addresses, to stderr */
void rt_fatal(XbCtx *c, const char *fmt, ...) __attribute__((noreturn, format(printf, 2, 3)));

/* ---- memory (mem.c) ----
 * Regions of the 4 GB guest space:
 *   0x00010000  the XBE image, then user allocations (NtAllocateVirtualMemory)
 *   0x80000000  the 64 MB of RAM, by physical address: contiguous memory
 *   0xB0000000  kernel pool and system memory
 *   0xC0000000  kernel data: exported variables, thread and PCR blocks
 *   0xF0000000  the same RAM again (write-combined view)
 *   0xFD000000  the GPU's registers (NV2A, 16 MB)
 *   0xFFFF0000  fake addresses of kernel functions, stored in the thunks */
#define RT_USER_BASE 0x00010000u
#define RT_USER_LIMIT 0x7FFE0000u
#define RT_PHYS_SIZE 0x04000000u
#define RT_PHYS_VIEW 0x80000000u
#define RT_PHYS_WC 0xF0000000u
#define RT_PHYS_INSTANCE 0x03FE0000u /* GPU instance memory, 64 KB, then 64 KB padding */
#define RT_NV2A_BASE 0xFD000000u
#define RT_APU_BASE 0xFE800000u /* the audio processor's registers, 512 KB */
#define RT_APU_SIZE 0x00080000u
#define RT_ACI_BASE 0xFEC00000u /* the AC'97 controller, 4 KB */
#define RT_ACI_SIZE 0x00001000u
#define RT_POOL_BASE 0xB0000000u
#define RT_POOL_LIMIT 0xBF000000u
#define RT_KDATA_BASE 0xC0000000u
#define RT_KDATA_LIMIT 0xC8000000u
#define RT_KFUNC_BASE 0xFFFF0000u

void rt_mem_init(void);
/* Make [addr, addr+size) usable. A no-op on Linux; on Windows guest memory
 * is committed on first use, and host calls that write guest memory
 * (ReadFile) need it committed beforehand. */
void rt_mem_commit(uint32_t addr, uint32_t size);
uint32_t rt_user_alloc(uint32_t base, uint32_t size, uint32_t protect); /* 0 on failure */
int rt_user_free(uint32_t base, uint32_t *size);
int rt_user_query(uint32_t addr, uint32_t *base, uint32_t *size, uint32_t *protect, uint32_t *state);
/* Contiguous physical memory in [lo, hi], returned at its 0x80000000 view. */
uint32_t rt_contig_alloc(uint32_t size, uint32_t lo, uint32_t hi, uint32_t align);
void rt_contig_free(uint32_t va);
uint32_t rt_phys_of(uint32_t va);
#define RT_PHYS_ALIAS 0x40000000u /* stand-in physical pages of memory outside the 64 MB (rt_phys_of) */
uint8_t *rt_phys_ptr(uint32_t pa); /* a physical address as devices see it, stand-ins included */
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
/* Take the big lock. A thread spinning in guest code hands it over at its
 * next loop back-edge (xb_preempt), so use this rather than locking
 * rt_gil directly whenever the caller has work to do. */
void rt_gil_lock(void);
extern pthread_cond_t rt_changed; /* broadcast whenever an object is signalled */

typedef struct RtThread {
    XbCtx ctx;
    uint32_t kthread; /* guest KTHREAD/ETHREAD */
    uint32_t kpcr;    /* guest KPCR this thread sees at fs: */
    uint32_t handle;
    uint32_t start, arg1, arg2; /* StartRoutine(StartContext1, StartContext2) */
    int terminated;
    int suspend;  /* suspend count; a thread starts running guest code only at 0 */
    int started;  /* has begun running guest code */
    uint32_t exit_code;
    pthread_t host;
    struct { uint32_t routine, context, iosb; } apc[1024]; /* user APCs, run at the next alertable wait (streaming queues many) */
    int napc;
    uint32_t last_call, last_from; /* its latest kernel call (ordinal) and caller, for thread dumps */
    struct RtThread *next_all;      /* every thread started, for thread dumps */
} RtThread;

extern __thread RtThread *rt_self;
/* Condition variables time out against RT_COND_CLOCK: monotonic on Linux,
 * the wall clock on Windows, where winpthreads waits on that. */
#ifdef _WIN32
#define RT_COND_CLOCK CLOCK_REALTIME
#else
#define RT_COND_CLOCK CLOCK_MONOTONIC
#endif
void rt_cond_init(pthread_cond_t *cv);
void rt_abstime(struct timespec *ts, uint64_t ns_from_now); /* for pthread_cond_timedwait */
void rt_dpc_wake(void);                                       /* dpc.c: an interrupt is pending */
RtThread *rt_thread_create(uint32_t stack_size, uint32_t tls_size, uint32_t extra_size);
void rt_thread_start(RtThread *t);
void rt_thread_run_main(RtThread *t, uint32_t entry);
uint64_t rt_now_100ns(void); /* monotonic, Xbox system time units */

/* Handle table. */
enum { OBJ_FREE, OBJ_EVENT, OBJ_SEMAPHORE, OBJ_MUTANT, OBJ_THREAD, OBJ_FILE, OBJ_SYMLINK, OBJ_TIMER, OBJ_DIR };
typedef struct {
    int type;
    int refs;           /* the handle, plus ObReferenceObjectByHandle's references */
    int closed;         /* the handle is closed; references keep the object */
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
    uint32_t file_object; /* guest FILE_OBJECT, made when the game asks for it */
    int raw;              /* a raw hard disk partition: its number + 1 */
    int delete_on_close;  /* FileDispositionInformation */
    char *host;           /* file: host path, for share checks */
    uint8_t access, share; /* file: SHARE_* bits it uses (read 1, write 2, delete 4) and allows */
    uint8_t unbuffered;    /* file: opened with FILE_NO_INTERMEDIATE_BUFFERING */
} RtObject;
uint32_t rt_handle_new(int type);
RtObject *rt_handle_get(uint32_t h);
void rt_handle_close(uint32_t h);

/* Waiting: block until ready(arg) or the deadline (absolute rt_now_100ns,
 * 0 for none). Called with rt_gil held; releases it while waiting.
 * Returns 1 if ready, 0 on timeout. */
int rt_wait(int (*ready)(void *), void *arg, uint64_t deadline);
uint64_t rt_deadline(uint32_t timeout_ptr); /* from a guest PLARGE_INTEGER */

/* User APCs: an I/O call given an ApcRoutine queues one on the calling
 * thread, which runs it, as ApcRoutine(ApcContext, IoStatusBlock, 0), the
 * next time it waits alertably. That wait then returns STATUS_USER_APC.
 * rt_run_user_apcs returns how many ran. */
#define STATUS_USER_APC 0x000000C0u
void rt_queue_user_apc(uint32_t routine, uint32_t context, uint32_t iosb);
int rt_run_user_apcs(XbCtx *c);

/* ---- kernel exports (kernel.c) ---- */
void rt_kernel_init(void);
void rt_fibers_init(void); /* hle_fiber.c: fiber stacks */
void rt_crypto_init(void); /* crypto.c: the Xc* exports */
/* Other files add handlers for their part of the kernel. A handler reads
 * its arguments from the guest stack and returns EAX; see kernel.c. */
typedef uint32_t (*RtHandler)(XbCtx *c);
void rt_kernel_handler(uint32_t ordinal, RtHandler h);
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

/* ---- hardware (hw.c): interrupts, PCI, I/O ports, video output ---- */
void rt_hw_init(void);
void rt_interrupt_raise(uint32_t vector); /* from any thread; the DPC thread runs the ISR */
void rt_interrupts_run(XbCtx *c);         /* DPC thread: run raised ISRs */
void rt_interrupt_ack(uint32_t irq, void (*ack)(void)); /* called after the ISR for irq */
extern uint32_t rt_display_fb;            /* AvSetDisplayMode: front buffer, physical */
extern uint32_t rt_display_mode, rt_display_format, rt_display_pitch;

/* ---- the picture (display.c): window and screenshots ---- */
void rt_display_init(void);
void rt_display_compose(uint32_t *out); /* 640x480 xRGB, as the TV would show it */
#define RT_DISPLAY_MAX (640 * 4 * 480 * 4)
void rt_display_compose_best(uint32_t *out, int *w, int *h); /* at the drawn resolution when the GPU has it (up to RT_DISPLAY_MAX pixels) */
int rt_gl_frame(uint32_t fb, uint32_t *out, int max_pixels, int *w, int *h);
void rt_display_new_frame(void); /* a new drawn-resolution picture: the window shows it now */
int rt_display_focused(void);           /* the game's window has the keyboard */

/* ---- the audio processor (apu.c) ---- */
void rt_apu_init(void);
void rt_apu_tick(void); /* DPC thread, every millisecond, with rt_gil held */
void rt_log_tick(void); /* likewise: turns logging on at XBRT_LOG_FROM */
void nv2a_log_stats(void); /* likewise: the GPU stats line every 5 s at log level 1 */
void rt_thread_dump(void); /* every guest thread's state, to stderr; with rt_gil held */
uint32_t rt_apu_read(uint32_t off, int bytes);
void rt_apu_write(uint32_t off, int bytes, uint32_t v);
uint32_t rt_aci_read(uint32_t off, int bytes);
void rt_aci_write(uint32_t off, int bytes, uint32_t v);

/* ---- files (file.c) ---- */
void rt_files_init(void);
uint32_t rt_symlink(const char *link, const char *target);
uint32_t rt_open(uint32_t *handle, uint32_t obj_attr, uint32_t access, uint32_t share, uint32_t disposition,
                 uint32_t options, uint32_t *info);
RtObject *rt_handle_slot(int i);
void rt_object_release(uint32_t h); /* drop a reference to the object behind h, even once h is closed */ /* the handle table, for walking: NULL past the end or for free slots */
uint32_t rt_read(uint32_t h, uint32_t buf, uint32_t len, uint32_t offset_ptr, uint32_t *done);
uint32_t rt_write(uint32_t h, uint32_t buf, uint32_t len, uint32_t offset_ptr, uint32_t *done);
const char *rt_object_name(uint32_t obj_attr, char *out, size_t n);
/* The guest FILE_OBJECT for a file or directory handle, and back. */
uint32_t rt_file_object(uint32_t h);
uint32_t rt_file_handle(uint32_t file_object);
void rt_file_delete(const char *xbox_path); /* when its last handle closes */
void rt_listing_free(void *listing);       /* a directory handle's listing cursor */

#endif
