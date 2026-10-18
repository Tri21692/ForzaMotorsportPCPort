/* Fibers: XAPI's SwitchToFiber, replaced (HLE).
 *
 * An XAPI fiber is 16 bytes at the top of its own stack: FiberData (+0),
 * StackBase (+4), StackLimit (+8) and the saved esp (+0xC). The running
 * fiber is at offset 0xC of XAPI's per-thread block, which the thread's
 * TLS slot _tls_index points at. CreateFiber, ConvertThreadToFiber and
 * DeleteFiber run recompiled and keep those structures as the game expects.
 *
 * SwitchToFiber cannot: it swaps esp and "returns" into another fiber's
 * code, while translated code keeps its call chain on the host stack. So
 * each fiber runs on a host thread of its own. They share the guest
 * thread's KTHREAD, KPCR and TLS, so to guest code they are one thread
 * (critical section ownership, fs:, GetCurrentFiber all agree). A switch
 * records the new current fiber, wakes its host thread (starting it in
 * XapiFiberStartup the first time) and parks the caller until something
 * switches back. Only one guest thread runs at a time anyway, and a parked
 * fiber waits in rt_wait, which releases the big lock. As XAPI's own
 * SwitchToFiber does, each fiber keeps its own SEH chain (fs:[0]).
 */
#include <stdlib.h>
#include <string.h>

#include "names.h"
#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

#if defined(XB_FN_SwitchToFiber) && defined(XB_ADDR_XapiFiberStartup) && defined(XB_VAR__tls_index)

#define FIBER_CURRENT 0x0C /* in XAPI's per-thread block */

typedef struct Fiber {
    uint32_t guest; /* the guest FIBER */
    RtThread *t;    /* the host thread running it */
    int active;     /* the fiber its guest thread is running now */
    uint32_t seh;   /* its SEH chain head (fs:[0]) while it is switched out */
    struct Fiber *next;
} Fiber;

static Fiber *fibers;

static Fiber *fiber_find(uint32_t guest) {
    for (Fiber *f = fibers; f; f = f->next)
        if (f->guest == guest) return f;
    return NULL;
}

static Fiber *fiber_new(uint32_t guest, RtThread *t) {
    Fiber *f = calloc(1, sizeof *f);
    f->guest = guest, f->t = t;
    f->next = fibers;
    fibers = f;
    return f;
}

static int fiber_active(void *p) { return ((Fiber *)p)->active; }

/* XAPI's per-thread block: [StackBase (fs:[4]) + 4 * _tls_index]. */
static uint32_t xapi_thread_data(XbCtx *c) {
    uint32_t tls = xb_rd32(c->fs_base + 4);
    return xb_rd32(tls + 4 * xb_rd32(XB_VAR__tls_index));
}

/* A host thread for a fiber CreateFiber made: it shares the guest thread's
 * identity and starts in XapiFiberStartup(lpStartAddress), which calls
 * lpStartAddress(FiberData) and never returns. CreateFiber leaves the
 * start address just below the FIBER. */
static RtThread *fiber_thread(XbCtx *c, uint32_t guest) {
    RtThread *t = calloc(1, sizeof *t);
    *t = *rt_self;
    t->napc = 0;
    t->ctx = *c;
    t->ctx.esp = guest - 0x40; /* below CreateFiber's start frame */
    t->start = XB_ADDR_XapiFiberStartup;
    t->arg1 = xb_rd32(guest - 4);
    t->arg2 = 0;
    t->suspend = 0;
    t->started = 0;
    rt_log("fiber %08x starts at %08x\n", guest, t->arg1);
    return t;
}

/* VOID SwitchToFiber(LPVOID lpFiber) */
void XB_FN_SwitchToFiber(XbCtx *c) {
    uint32_t target = ARG(0);
    uint32_t data = xapi_thread_data(c);
    uint32_t cur = xb_rd32(data + FIBER_CURRENT);
    c->esp += 8; /* pop the return address and lpFiber now: this thread resumes after the call */
    if (target == cur) return;

    Fiber *me = fiber_find(cur);
    if (!me) me = fiber_new(cur, rt_self); /* a thread made a fiber by ConvertThreadToFiber */
    me->t = rt_self;
    xb_wr32(data + FIBER_CURRENT, target);

    Fiber *to = fiber_find(target);
    me->active = 0;
    me->seh = xb_rd32(c->fs_base);
    if (!to) {
        to = fiber_new(target, fiber_thread(c, target));
        to->active = 1;
        xb_wr32(c->fs_base, 0xFFFFFFFFu); /* a new fiber starts with an empty SEH chain */
        rt_thread_start(to->t);
    } else {
        to->active = 1;
        xb_wr32(c->fs_base, to->seh);
    }
    pthread_cond_broadcast(&rt_changed);
    rt_wait(fiber_active, me, 0);
}

#endif

/* PVOID MmCreateKernelStack(ULONG NumberOfBytes, BOOLEAN DebuggerThread):
 * returns the stack's base (its top). XAPI allocates fiber stacks this way. */
static uint32_t k_MmCreateKernelStack(XbCtx *c) {
    uint32_t size = (ARG(0) + 0xFFF) & ~0xFFFu;
    uint32_t limit = rt_user_alloc(0, size, 0x04);
    return limit ? limit + size : 0;
}

/* VOID MmDeleteKernelStack(PVOID StackBase, PVOID StackLimit) */
static uint32_t k_MmDeleteKernelStack(XbCtx *c) {
    rt_user_free(ARG(1), NULL);
    return 0;
}

void rt_fibers_init(void) {
    rt_kernel_handler(169, k_MmCreateKernelStack);
    rt_kernel_handler(170, k_MmDeleteKernelStack);
}
