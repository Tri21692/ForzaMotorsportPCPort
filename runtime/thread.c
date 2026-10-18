/* Guest threads, the handle table and waiting. */
#include <errno.h>
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "rt.h"

pthread_mutex_t rt_gil = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t rt_changed;
__thread RtThread *rt_self;
volatile uint32_t xb_preempt_pending;

void rt_gil_lock(void) {
    if (pthread_mutex_trylock(&rt_gil) == 0) return;
    __atomic_add_fetch(&xb_preempt_pending, 1, __ATOMIC_SEQ_CST);
    pthread_mutex_lock(&rt_gil);
    __atomic_sub_fetch(&xb_preempt_pending, 1, __ATOMIC_SEQ_CST);
}

/* Called from a loop back-edge in guest code, with rt_gil held. Only code
 * at PASSIVE or APC level gives way: ISRs, DPCs and code that raised IRQL
 * would not be interrupted on the Xbox either. */
void xb_preempt(XbCtx *c) {
    (void)c;
    if (!rt_self || xb_rd8(rt_self->kpcr + 0x24) >= 2) return;
    pthread_mutex_unlock(&rt_gil);
    for (int i = 0; xb_preempt_pending && i < 10000; i++) sched_yield();
    pthread_mutex_lock(&rt_gil);
}

/* Guest code returns here when a thread's start routine finishes. */
#define THREAD_RETURN 0xFFFFFFF0u

uint64_t rt_now_100ns(void) {
    static struct timespec t0;
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    if (!t0.tv_sec && !t0.tv_nsec) t0 = t;
    int64_t ns = (int64_t)(t.tv_sec - t0.tv_sec) * 1000000000ll + (t.tv_nsec - t0.tv_nsec);
    return (uint64_t)ns / 100;
}

/* ---- handles ---- */

static RtObject *objects[4096];

uint32_t rt_handle_new(int type) {
    for (int i = 1; i < 4096; i++) {
        if (!objects[i]) {
            objects[i] = calloc(1, sizeof(RtObject));
            objects[i]->type = type;
            objects[i]->refs = 1;
            objects[i]->fd = -1;
            return 0x100u + 4u * i;
        }
    }
    return 0;
}

RtObject *rt_handle_get(uint32_t h) {
    if (h < 0x100 || (h & 3)) return NULL;
    uint32_t i = (h - 0x100) / 4;
    return i < 4096 ? objects[i] : NULL;
}

RtObject *rt_handle_slot(int i) { return i > 0 && i < 4096 ? objects[i] : NULL; }

void rt_handle_close(uint32_t h) {
    RtObject *o = rt_handle_get(h);
    if (!o) return;
    if (--o->refs > 0) return;
    if (o->fd >= 0 && o->type == OBJ_FILE) close(o->fd);
    if (o->delete_on_close) rt_file_delete(o->path);
    free(o->path);
    free(o->host);
    free(o);
    objects[(h - 0x100) / 4] = NULL;
}

/* ---- waiting ---- */

int rt_wait(int (*ready)(void *), void *arg, uint64_t deadline) {
    for (;;) {
        if (ready(arg)) return 1;
        uint64_t now = rt_now_100ns();
        if (deadline && now >= deadline) return 0;
        /* Wake at least every 10 ms, so timers and KeTickCount move. */
        uint64_t until = now + 100000;
        if (deadline && deadline < until) until = deadline;
        struct timespec ts;
        rt_abstime(&ts, (until - now) * 100);
        pthread_cond_timedwait(&rt_changed, &rt_gil, &ts);
    }
}

void rt_queue_user_apc(uint32_t routine, uint32_t context, uint32_t iosb) {
    RtThread *t = rt_self;
    if (!t) return;
    if (t->napc == (int)(sizeof t->apc / sizeof t->apc[0])) rt_fatal(&t->ctx, "user APC queue full");
    t->apc[t->napc].routine = routine;
    t->apc[t->napc].context = context;
    t->apc[t->napc].iosb = iosb;
    t->napc++;
}

int rt_run_user_apcs(XbCtx *c) {
    RtThread *t = rt_self;
    int ran = 0;
    while (t && t->napc) {
        uint32_t routine = t->apc[0].routine, context = t->apc[0].context, iosb = t->apc[0].iosb;
        memmove(t->apc, t->apc + 1, --t->napc * sizeof t->apc[0]);
        rt_guest_call(c, routine, 3, context, iosb, 0);
        ran++;
    }
    return ran;
}

uint64_t rt_system_time_base; /* Xbox system time (100 ns since 1601) at boot */

uint64_t rt_deadline(uint32_t timeout_ptr) {
    if (!timeout_ptr) return 0;
    int64_t v = (int64_t)xb_rd64(timeout_ptr);
    uint64_t now = rt_now_100ns();
    if (v < 0) return now + (uint64_t)(-v);
    if (v == 0) return now ? now : 1;
    /* Absolute system time. */
    uint64_t rel = (uint64_t)v > rt_system_time_base ? (uint64_t)v - rt_system_time_base : 0;
    return rel > now ? rel : now;
}

/* ---- threads ---- */

/* Lay out a guest thread the way the Xbox kernel does: TLS at the top of
 * the stack, the KPCR's stack base (fs:[4]) just above it. XAPI finds TLS
 * from fs:[4] with a negative _tls_index, so this layout is not optional. */
RtThread *rt_thread_create(uint32_t stack_size, uint32_t tls_size, uint32_t extra_size) {
    RtThread *t = calloc(1, sizeof *t);
    if (stack_size < 0x10000) stack_size = 0x10000;
    tls_size = (tls_size + 3) & ~3u;
    uint32_t stack = rt_user_alloc(0, stack_size + tls_size + 0x1000, 0x04);
    if (!stack) rt_fatal(NULL, "out of guest memory for a thread stack");
    uint32_t top = stack + stack_size + tls_size + 0x1000;
    uint32_t tls = top - tls_size;

    t->kthread = rt_kdata_alloc(0x200 + extra_size);
    uint32_t kt = t->kthread;
    xb_wr8(kt + 0x00, 6);                /* Header.Type: ThreadObject */
    xb_wr32(kt + 0x1C, top);             /* StackBase */
    xb_wr32(kt + 0x20, stack);           /* StackLimit */
    xb_wr32(kt + 0x24, tls - 0x10);      /* KernelStack */
    xb_wr32(kt + 0x28, tls);             /* TlsData */
    if (tls_size >= 4) xb_wr32(tls, tls + 4); /* the TLS "array": one slot */

    t->kpcr = rt_kdata_alloc(0x300);
    uint32_t p = t->kpcr;
    xb_wr32(p + 0x00, 0xFFFFFFFFu); /* NtTib.ExceptionList: end of the SEH chain */
    xb_wr32(p + 0x04, top);         /* NtTib.StackBase, also the TLS base */
    xb_wr32(p + 0x08, stack);       /* NtTib.StackLimit */
    xb_wr32(p + 0x18, p);           /* NtTib.Self */
    xb_wr32(p + 0x1C, p);           /* SelfPcr */
    xb_wr32(p + 0x20, p + 0x28);    /* Prcb */
    xb_wr8(p + 0x24, 0);            /* Irql: PASSIVE_LEVEL */
    xb_wr32(p + 0x28, kt);          /* Prcb.CurrentThread */

    t->ctx.fs_base = p;
    t->ctx.esp = tls - 0x10;
    t->ctx.mxcsr = 0x1F80;
    t->ctx.fcw = 0x037F;
    t->handle = rt_handle_new(OBJ_THREAD);
    rt_handle_get(t->handle)->thread = t;
    return t;
}

static void *thread_main(void *arg) {
    RtThread *t = arg;
    rt_gil_lock();
    rt_self = t;
    XbCtx *c = &t->ctx;
    xb_fpu_setcw(c, c->fcw);
    xb_push(c, t->arg2);
    xb_push(c, t->arg1);
    xb_push(c, THREAD_RETURN);
    rt_log("thread %08x starts at %08x(%08x, %08x)\n", t->handle, t->start, t->arg1, t->arg2);
    rt_call(c, t->start);
    rt_log("thread %08x returned %08x\n", t->handle, c->eax);
    t->terminated = 1;
    t->exit_code = c->eax;
    pthread_cond_broadcast(&rt_changed);
    pthread_mutex_unlock(&rt_gil);
    return NULL;
}

void rt_thread_start(RtThread *t) {
    pthread_attr_t a;
    pthread_attr_init(&a);
    pthread_attr_setstacksize(&a, 64u << 20); /* deep guest call chains run on the host stack */
    if (pthread_create(&t->host, &a, thread_main, t) != 0) rt_fatal(NULL, "pthread_create failed");
    pthread_attr_destroy(&a);
}

void rt_thread_run_main(RtThread *t, uint32_t entry) {
    t->start = entry;
    rt_thread_start(t);
    pthread_join(t->host, NULL);
}

void rt_cond_init(pthread_cond_t *cv) {
    pthread_condattr_t a;
    pthread_condattr_init(&a);
#ifndef _WIN32
    pthread_condattr_setclock(&a, RT_COND_CLOCK);
#endif
    pthread_cond_init(cv, &a);
    pthread_condattr_destroy(&a);
}

void rt_abstime(struct timespec *ts, uint64_t ns_from_now) {
    clock_gettime(RT_COND_CLOCK, ts);
    ts->tv_sec += ns_from_now / 1000000000ull;
    ts->tv_nsec += ns_from_now % 1000000000ull;
    if (ts->tv_nsec >= 1000000000) ts->tv_sec++, ts->tv_nsec -= 1000000000;
}

__attribute__((constructor)) static void init_cond(void) { rt_cond_init(&rt_changed); }
