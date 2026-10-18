/* The Xbox kernel's exports, implemented on the host (HLE).
 *
 * Generated code calls xb_kernel(c, ordinal) after pushing its return
 * address. A handler reads its arguments from the guest stack, returns the
 * value for EAX, and xb_kernel then pops the return address and, for
 * stdcall/fastcall, the arguments, as the real export would. An ordinal
 * without a handler stops the program with its name and arguments, which
 * is how the next thing to implement shows up.
 */
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))
#define K(name) static uint32_t k_##name(XbCtx *c)

extern uint64_t rt_system_time_base;
static uint32_t v_tick_count; /* guest address of KeTickCount */

const XbKernelInfo *rt_kernel_info(uint32_t ordinal) {
    unsigned lo = 0, hi = xb_kernel_info_count;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (xb_kernel_info[mid].ordinal < ordinal) lo = mid + 1;
        else hi = mid;
    }
    return lo < xb_kernel_info_count && xb_kernel_info[lo].ordinal == ordinal ? &xb_kernel_info[lo] : NULL;
}

/* ---- calling guest code ---- */

void xb_call_indirect(XbCtx *c, uint32_t target) {
    if (target >= RT_KFUNC_BASE) { /* a kernel function through its thunk value */
        xb_kernel(c, (target - RT_KFUNC_BASE) / 4);
        return;
    }
    unsigned lo = 0, hi = xb_func_count;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (xb_funcs[mid].addr < target) lo = mid + 1;
        else hi = mid;
    }
    if (lo < xb_func_count && xb_funcs[lo].addr == target) {
        xb_funcs[lo].fn(c);
        return;
    }
    rt_fatal(c, "indirect call to %08x, which is not a translated function (return address %08x)", target, xb_rd32(c->esp));
}

void rt_call(XbCtx *c, uint32_t target) { xb_call_indirect(c, target); }

#define CALL_RETURN 0xFFFFFFF4u

uint32_t rt_guest_call(XbCtx *c, uint32_t fn, int nargs, ...) {
    XbCtx saved = *c;
    uint32_t args[8];
    va_list ap;
    va_start(ap, nargs);
    for (int i = 0; i < nargs && i < 8; i++) args[i] = va_arg(ap, uint32_t);
    va_end(ap);
    c->esp -= 0x40; /* leave the caller's stack alone */
    for (int i = nargs - 1; i >= 0; i--) xb_push(c, args[i]);
    xb_push(c, CALL_RETURN);
    rt_call(c, fn);
    uint32_t r = c->eax;
    *c = saved;
    return r;
}

/* ---- Rtl ---- */

/* RTL_CRITICAL_SECTION: a 16-byte dispatcher header, then LockCount
 * (+0x10), RecursionCount (+0x14) and OwningThread (+0x18). */
K(RtlInitializeCriticalSection) {
    uint32_t cs = ARG(0);
    memset(xb_mem + cs, 0, 0x1C);
    xb_wr8(cs, 1); /* SynchronizationEvent */
    xb_wr8(cs + 2, 4);
    xb_wr32(cs + 0x10, 0xFFFFFFFFu);
    return 0;
}

static int cs_free(void *p) { return xb_rd32((uint32_t)(uintptr_t)p + 0x18) == 0; }

K(RtlEnterCriticalSection) {
    uint32_t cs = ARG(0), me = rt_self->kthread;
    if (xb_rd32(cs + 0x18) == me) {
        xb_wr32(cs + 0x14, xb_rd32(cs + 0x14) + 1);
        xb_wr32(cs + 0x10, xb_rd32(cs + 0x10) + 1);
        return 0;
    }
    rt_wait(cs_free, (void *)(uintptr_t)cs, 0);
    xb_wr32(cs + 0x18, me);
    xb_wr32(cs + 0x14, 1);
    xb_wr32(cs + 0x10, xb_rd32(cs + 0x10) + 1);
    return 0;
}

K(RtlTryEnterCriticalSection) {
    uint32_t cs = ARG(0), me = rt_self->kthread, owner = xb_rd32(cs + 0x18);
    if (owner && owner != me) return 0;
    xb_wr32(cs + 0x18, me);
    xb_wr32(cs + 0x14, xb_rd32(cs + 0x14) + 1);
    xb_wr32(cs + 0x10, xb_rd32(cs + 0x10) + 1);
    return 1;
}

K(RtlLeaveCriticalSection) {
    uint32_t cs = ARG(0);
    uint32_t rec = xb_rd32(cs + 0x14) - 1;
    xb_wr32(cs + 0x14, rec);
    xb_wr32(cs + 0x10, xb_rd32(cs + 0x10) - 1);
    if (rec == 0) {
        xb_wr32(cs + 0x18, 0);
        pthread_cond_broadcast(&rt_changed);
    }
    return 0;
}

/* STRING: u16 Length, u16 MaximumLength, char *Buffer. */
K(RtlInitAnsiString) {
    uint32_t s = ARG(0), src = ARG(1);
    uint32_t n = src ? (uint32_t)strlen(rt_str(src)) : 0;
    xb_wr16(s, n);
    xb_wr16(s + 2, src ? n + 1 : 0);
    xb_wr32(s + 4, src);
    return 0;
}

K(RtlEqualString) {
    uint32_t a = ARG(0), b = ARG(1), nocase = ARG(2) & 0xFF;
    uint16_t la = xb_rd16(a), lb = xb_rd16(b);
    if (la != lb) return 0;
    const char *pa = rt_str(xb_rd32(a + 4)), *pb = rt_str(xb_rd32(b + 4));
    return (nocase ? strncasecmp(pa, pb, la) : strncmp(pa, pb, la)) == 0;
}

K(RtlNtStatusToDosError) {
    switch (ARG(0)) {
    case STATUS_SUCCESS: return 0;
    case STATUS_OBJECT_NAME_NOT_FOUND: return 2;   /* ERROR_FILE_NOT_FOUND */
    case STATUS_OBJECT_PATH_NOT_FOUND: return 3;   /* ERROR_PATH_NOT_FOUND */
    case STATUS_ACCESS_DENIED: return 5;
    case STATUS_INVALID_HANDLE: return 6;
    case STATUS_NO_MEMORY: return 8;
    case STATUS_NO_MORE_FILES: return 18;
    case STATUS_END_OF_FILE: return 38;            /* ERROR_HANDLE_EOF */
    case STATUS_INVALID_PARAMETER: return 87;
    case STATUS_NOT_IMPLEMENTED: return 120;
    case STATUS_OBJECT_NAME_COLLISION: return 183; /* ERROR_ALREADY_EXISTS */
    case STATUS_TIMEOUT: return 1460;
    case STATUS_PENDING: return 997;               /* ERROR_IO_PENDING */
    }
    return 317; /* ERROR_MR_MID_NOT_FOUND */
}

/* TIME_FIELDS: Year, Month, Day, Hour, Minute, Second, Milliseconds, Weekday (u16 each). */
K(RtlTimeToTimeFields) {
    uint64_t t = xb_rd64(ARG(0));
    uint32_t tf = ARG(1);
    int64_t secs = (int64_t)(t / 10000000ull) - 11644473600ll; /* 1601 -> 1970 */
    time_t tt = (time_t)secs;
    struct tm tm;
    gmtime_r(&tt, &tm);
    uint16_t v[8] = {(uint16_t)(tm.tm_year + 1900), (uint16_t)(tm.tm_mon + 1), (uint16_t)tm.tm_mday, (uint16_t)tm.tm_hour,
                     (uint16_t)tm.tm_min, (uint16_t)tm.tm_sec, (uint16_t)((t / 10000) % 1000), (uint16_t)tm.tm_wday};
    for (int i = 0; i < 8; i++) xb_wr16(tf + 2 * i, v[i]);
    return 0;
}

K(RtlTimeFieldsToTime) {
    uint32_t tf = ARG(0), out = ARG(1);
    struct tm tm = {0};
    tm.tm_year = xb_rd16(tf) - 1900, tm.tm_mon = xb_rd16(tf + 2) - 1, tm.tm_mday = xb_rd16(tf + 4);
    tm.tm_hour = xb_rd16(tf + 6), tm.tm_min = xb_rd16(tf + 8), tm.tm_sec = xb_rd16(tf + 10);
    int64_t secs = (int64_t)timegm(&tm) + 11644473600ll;
    xb_wr64(out, (uint64_t)secs * 10000000ull + xb_rd16(tf + 12) * 10000ull);
    return 1;
}

K(RtlCompareMemoryUlong) {
    uint32_t src = ARG(0), len = ARG(1), pat = ARG(2), n = 0;
    while (n + 4 <= len && xb_rd32(src + n) == pat) n += 4;
    return n;
}

/* ---- Ke: time, IRQL, dispatcher objects ---- */

K(KeQueryPerformanceCounter) {
    uint64_t v = rt_now_100ns() * 733333333ull / 10000000ull;
    c->edx = (uint32_t)(v >> 32);
    return (uint32_t)v;
}

K(KeQueryPerformanceFrequency) {
    c->edx = 0;
    return 733333333u;
}

K(KeQuerySystemTime) {
    xb_wr64(ARG(0), rt_system_time_base + rt_now_100ns());
    return 0;
}

static int never(void *p) { (void)p; return 0; }

K(KeDelayExecutionThread) {
    uint64_t d = rt_deadline(ARG(2));
    rt_wait(never, NULL, d ? d : rt_now_100ns() + 1);
    return STATUS_SUCCESS;
}

K(KeStallExecutionProcessor) {
    usleep(ARG(0));
    return 0;
}

static uint32_t irql_swap(uint8_t to) {
    uint32_t p = rt_self->kpcr + 0x24;
    uint8_t old = xb_rd8(p);
    xb_wr8(p, to);
    return old;
}
K(KeRaiseIrqlToDpcLevel) { return irql_swap(2); }
K(KfRaiseIrql) { return irql_swap((uint8_t)c->ecx); }
K(KfLowerIrql) { irql_swap((uint8_t)c->ecx); return 0; }

K(KeSetBasePriorityThread) { return 0; }
K(KeBugCheck) { rt_fatal(c, "KeBugCheck(%08x)", ARG(0)); }

/* Dispatcher objects in guest memory: DISPATCHER_HEADER is Type (u8),
 * Absolute, Size, Inserted, then SignalState (+4). Types: 0 notification
 * event, 1 synchronization event, 2 mutant, 5 semaphore, 6 thread,
 * 8/9 timers. */
static int header_ready(void *p) { return (int32_t)xb_rd32((uint32_t)(uintptr_t)p + 4) > 0; }

static void header_consume(uint32_t h) {
    switch (xb_rd8(h)) {
    case 1: case 9: xb_wr32(h + 4, 0); break;            /* auto-reset */
    case 2: case 5: xb_wr32(h + 4, xb_rd32(h + 4) - 1); break;
    }
}

K(KeSetEvent) {
    uint32_t e = ARG(0);
    uint32_t prev = xb_rd32(e + 4);
    xb_wr32(e + 4, 1);
    pthread_cond_broadcast(&rt_changed);
    return prev;
}

K(KeWaitForSingleObject) {
    uint32_t obj = ARG(0);
    if (!rt_wait(header_ready, (void *)(uintptr_t)obj, rt_deadline(ARG(4)))) return STATUS_TIMEOUT;
    header_consume(obj);
    return STATUS_SUCCESS;
}

/* KDPC: Type (u16), Inserted, pad, DpcListEntry, DeferredRoutine (+0x0C),
 * DeferredContext (+0x10), SystemArgument1/2 (+0x14/+0x18). */
K(KeInitializeDpc) {
    uint32_t d = ARG(0);
    memset(xb_mem + d, 0, 0x1C);
    xb_wr16(d, 19); /* DpcObject */
    xb_wr32(d + 0x0C, ARG(1));
    xb_wr32(d + 0x10, ARG(2));
    return 0;
}

K(KeInsertQueueDpc) {
    rt_dpc_queue(ARG(0), ARG(1), ARG(2));
    return 1;
}

K(KeRemoveQueueDpc) { return 0; }

/* KTIMER: header (Type 8 notification / 9 synchronization), DueTime,
 * TimerListEntry, Dpc (+0x20), Period (+0x24). */
K(KeInitializeTimerEx) {
    uint32_t t = ARG(0);
    memset(xb_mem + t, 0, 0x28);
    xb_wr8(t, 8 + (ARG(1) & 1));
    xb_wr8(t + 2, 0x0A);
    return 0;
}

static uint64_t due_time(uint32_t lo, uint32_t hi) {
    int64_t v = (int64_t)((uint64_t)hi << 32 | lo);
    uint64_t now = rt_now_100ns();
    if (v < 0) return now + (uint64_t)(-v);
    uint64_t rel = (uint64_t)v > rt_system_time_base ? (uint64_t)v - rt_system_time_base : 0;
    return rel > now ? rel : now;
}

/* KeSetTimer(Timer, DueTime (by value), Dpc) and KeSetTimerEx(..., Period, Dpc). */
K(KeSetTimer) {
    int was = rt_timer_cancel(ARG(0));
    rt_timer_set(ARG(0), due_time(ARG(1), ARG(2)), 0, ARG(3));
    return was;
}

K(KeSetTimerEx) {
    int was = rt_timer_cancel(ARG(0));
    rt_timer_set(ARG(0), due_time(ARG(1), ARG(2)), ARG(3), ARG(4));
    return was;
}

K(KeCancelTimer) { return rt_timer_cancel(ARG(0)); }

/* ---- Nt objects by handle ---- */

static int obj_ready(RtObject *o) {
    switch (o->type) {
    case OBJ_EVENT: case OBJ_SEMAPHORE: case OBJ_TIMER: return o->signaled > 0;
    case OBJ_MUTANT: return o->owner == NULL || o->owner == rt_self;
    case OBJ_THREAD: return o->thread && o->thread->terminated;
    }
    return 1;
}

static void obj_consume(RtObject *o) {
    switch (o->type) {
    case OBJ_EVENT: if (!o->manual) o->signaled = 0; break;
    case OBJ_SEMAPHORE: o->signaled--; break;
    case OBJ_MUTANT: o->owner = rt_self; o->recursion++; break;
    }
}

static uint32_t make(uint32_t out, int type) {
    uint32_t h = rt_handle_new(type);
    if (!h) return STATUS_NO_MEMORY;
    xb_wr32(out, h);
    return STATUS_SUCCESS;
}

K(NtCreateEvent) {
    uint32_t r = make(ARG(0), OBJ_EVENT);
    RtObject *o = rt_handle_get(xb_rd32(ARG(0)));
    if (o) o->manual = ARG(2) == 0, o->signaled = ARG(3) & 0xFF;
    return r;
}

K(NtSetEvent) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    if (ARG(1)) xb_wr32(ARG(1), o->signaled);
    o->signaled = 1;
    pthread_cond_broadcast(&rt_changed);
    return STATUS_SUCCESS;
}

K(NtClearEvent) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    o->signaled = 0;
    return STATUS_SUCCESS;
}

K(NtCreateSemaphore) {
    uint32_t r = make(ARG(0), OBJ_SEMAPHORE);
    RtObject *o = rt_handle_get(xb_rd32(ARG(0)));
    if (o) o->signaled = (int)ARG(2), o->limit = (int)ARG(3);
    return r;
}

K(NtReleaseSemaphore) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    if (ARG(2)) xb_wr32(ARG(2), o->signaled);
    o->signaled += (int)ARG(1);
    if (o->limit && o->signaled > o->limit) o->signaled = o->limit;
    pthread_cond_broadcast(&rt_changed);
    return STATUS_SUCCESS;
}

K(NtCreateMutant) {
    uint32_t r = make(ARG(0), OBJ_MUTANT);
    RtObject *o = rt_handle_get(xb_rd32(ARG(0)));
    if (o && (ARG(2) & 0xFF)) o->owner = rt_self, o->recursion = 1;
    return r;
}

K(NtReleaseMutant) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    if (ARG(1)) xb_wr32(ARG(1), o->recursion);
    if (o->owner == rt_self && --o->recursion == 0) o->owner = NULL;
    pthread_cond_broadcast(&rt_changed);
    return STATUS_SUCCESS;
}

static int handle_ready(void *p) {
    RtObject *o = rt_handle_get((uint32_t)(uintptr_t)p);
    return !o || obj_ready(o);
}

static uint32_t wait_one(uint32_t h, uint32_t timeout) {
    RtObject *o = rt_handle_get(h);
    if (!o) return STATUS_INVALID_HANDLE;
    if (!rt_wait(handle_ready, (void *)(uintptr_t)h, rt_deadline(timeout))) return STATUS_TIMEOUT;
    if ((o = rt_handle_get(h))) obj_consume(o);
    return STATUS_SUCCESS;
}

K(NtWaitForSingleObject) { return wait_one(ARG(0), ARG(2)); }
K(NtWaitForSingleObjectEx) { return wait_one(ARG(0), ARG(3)); }

typedef struct {
    uint32_t n, handles, all, which;
} MultiWait;

static int multi_ready(void *p) {
    MultiWait *w = p;
    int ready = 0;
    for (uint32_t i = 0; i < w->n; i++) {
        RtObject *o = rt_handle_get(xb_rd32(w->handles + 4 * i));
        if (!o || obj_ready(o)) {
            if (!w->all) {
                w->which = i;
                return 1;
            }
            ready++;
        }
    }
    return w->all && ready == (int)w->n;
}

K(NtWaitForMultipleObjectsEx) {
    MultiWait w = {ARG(0), ARG(1), ARG(2) == 0, 0};
    if (!rt_wait(multi_ready, &w, rt_deadline(ARG(5)))) return STATUS_TIMEOUT;
    for (uint32_t i = 0; i < w.n; i++) {
        if (!w.all && i != w.which) continue;
        RtObject *o = rt_handle_get(xb_rd32(w.handles + 4 * i));
        if (o) obj_consume(o);
    }
    return w.all ? STATUS_SUCCESS : w.which;
}

K(NtClose) {
    if (!rt_handle_get(ARG(0))) return STATUS_INVALID_HANDLE;
    rt_handle_close(ARG(0));
    return STATUS_SUCCESS;
}

K(NtYieldExecution) {
    pthread_mutex_unlock(&rt_gil);
    sched_yield();
    pthread_mutex_lock(&rt_gil);
    return STATUS_SUCCESS;
}

/* ---- threads ---- */

K(PsCreateSystemThreadEx) {
    uint32_t out = ARG(0), extra = ARG(1), stack = ARG(2), tls = ARG(3), tid = ARG(4);
    RtThread *t = rt_thread_create(stack ? stack : 0x10000, tls, extra);
    t->start = ARG(9), t->arg1 = ARG(5), t->arg2 = ARG(6);
    if (out) xb_wr32(out, t->handle);
    if (tid) xb_wr32(tid, t->handle);
    if (ARG(7) & 0xFF) rt_log("PsCreateSystemThreadEx: CreateSuspended is not supported yet; starting anyway\n");
    rt_thread_start(t);
    return STATUS_SUCCESS;
}

K(PsTerminateSystemThread) {
    rt_self->terminated = 1;
    rt_self->exit_code = ARG(0);
    rt_log("thread %08x terminated (%08x)\n", rt_self->handle, ARG(0));
    pthread_cond_broadcast(&rt_changed);
    pthread_mutex_unlock(&rt_gil);
    pthread_exit(NULL);
}

K(ObReferenceObjectByHandle) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    o->refs++;
    /* Threads give their guest ETHREAD; other objects are host-side and
     * only their handle means anything to the game. */
    xb_wr32(ARG(2), o->type == OBJ_THREAD ? o->thread->kthread : ARG(0));
    return STATUS_SUCCESS;
}

K(ObfDereferenceObject) { return 0; }

/* ---- memory ---- */

K(NtAllocateVirtualMemory) {
    uint32_t pbase = ARG(0), psize = ARG(2), protect = ARG(4);
    uint32_t a = rt_user_alloc(xb_rd32(pbase), xb_rd32(psize), protect);
    if (rt_log_level > 1) rt_log("  -> %08x size %08x\n", a, xb_rd32(psize));
    if (!a) return STATUS_NO_MEMORY;
    xb_wr32(pbase, a);
    xb_wr32(psize, (xb_rd32(psize) + 0xFFF) & ~0xFFFu);
    return STATUS_SUCCESS;
}

K(NtFreeVirtualMemory) {
    uint32_t size;
    if (!rt_user_free(xb_rd32(ARG(0)), &size)) return STATUS_INVALID_PARAMETER;
    if (ARG(1)) xb_wr32(ARG(1), size);
    return STATUS_SUCCESS;
}

/* MEMORY_BASIC_INFORMATION: BaseAddress, AllocationBase, AllocationProtect,
 * RegionSize, State, Protect, Type. */
K(NtQueryVirtualMemory) {
    uint32_t base, size, protect, state, out = ARG(1);
    int used = rt_user_query(ARG(0), &base, &size, &protect, &state);
    xb_wr32(out + 0, ARG(0) & ~0xFFFu);
    xb_wr32(out + 4, used ? base : 0);
    xb_wr32(out + 8, used ? protect : 0);
    xb_wr32(out + 12, size - ((ARG(0) & ~0xFFFu) - base));
    xb_wr32(out + 16, state);
    xb_wr32(out + 20, protect);
    xb_wr32(out + 24, used ? 0x20000 : 0); /* MEM_PRIVATE */
    return STATUS_SUCCESS;
}

K(MmAllocateContiguousMemory) { return rt_contig_alloc(ARG(0), 0x1000); }
K(MmAllocateContiguousMemoryEx) { return rt_contig_alloc(ARG(0), ARG(3)); }
K(MmFreeContiguousMemory) { return 0; }
K(MmPersistContiguousMemory) { return 0; }
K(MmQueryAllocationSize) { return rt_size_of(ARG(0)); }
K(MmGetPhysicalAddress) { return ARG(0) & 0x7FFFFFFFu; }
K(MmAllocateSystemMemory) { return rt_pool_alloc(ARG(0)); }
K(MmFreeSystemMemory) { return rt_size_of(ARG(0)); }
K(MmQueryAddressProtect) { return 0x04; }
K(MmSetAddressProtect) { return 0; }

/* MM_STATISTICS: Length, then 64 MB worth of page counts. */
K(MmQueryStatistics) {
    uint32_t s = ARG(0);
    xb_wr32(s + 4, 16384); /* TotalPhysicalPages */
    xb_wr32(s + 8, 8192);  /* AvailablePages */
    return STATUS_SUCCESS;
}

K(ExAllocatePoolWithTag) { return rt_pool_alloc(ARG(0)); }
K(ExFreePool) { return 0; }
K(ExQueryPoolBlockSize) { return rt_size_of(ARG(0)); }

/* ExQueryNonVolatileSetting(index, *type, value, length, *resultLength):
 * the EEPROM settings. Language English, region North America, everything
 * else 0. */
K(ExQueryNonVolatileSetting) {
    uint32_t index = ARG(0), type = ARG(1), value = ARG(2), len = ARG(3), result = ARG(4);
    uint32_t v = 0;
    switch (index) {
    case 0x07: v = 1; break;     /* XC_LANGUAGE: English */
    case 0x104: v = 1; break;    /* XC_FACTORY_GAME_REGION: North America */
    case 0x10C: v = 0x400100; break; /* XC_FACTORY_AV_REGION: NTSC-M */
    }
    if (type) xb_wr32(type, 4); /* REG_DWORD */
    if (value && len >= 4) xb_wr32(value, v);
    if (result) xb_wr32(result, 4);
    rt_log("  setting %#x = %#x\n", index, v);
    return STATUS_SUCCESS;
}

/* ---- Hal, Av, Io, Xe, Dbg ---- */

K(HalReturnToFirmware) {
    rt_log("HalReturnToFirmware(%u): the game asked to leave\n", ARG(0));
    fflush(stderr);
    _exit(0);
}
K(HalRegisterShutdownNotification) { return 0; }
K(HalIsResetOrShutdownPending) { return 0; }
K(AvGetSavedDataAddress) { return 0; }
K(AvSetSavedDataAddress) { return 0; }

K(IoCreateSymbolicLink) {
    uint32_t link = ARG(0), dev = ARG(1);
    char l[260], d[260];
    snprintf(l, sizeof l, "%.*s", xb_rd16(link), rt_str(xb_rd32(link + 4)));
    snprintf(d, sizeof d, "%.*s", xb_rd16(dev), rt_str(xb_rd32(dev + 4)));
    return rt_symlink(l, d);
}

K(IoDeleteSymbolicLink) { return STATUS_SUCCESS; }

/* IoCreateDevice(DriverObject, DeviceExtensionSize, DeviceName, DeviceType,
 * Exclusive, DeviceObject*): a DEVICE_OBJECT (0x50 bytes) followed by its
 * extension. Type 3, DriverObject +0x08, Flags +0x14, DeviceExtension
 * +0x18, DeviceType +0x1C, StackSize +0x1E, SectorSize +0x20. */
K(IoCreateDevice) {
    uint32_t ext = ARG(1), d = rt_kdata_alloc(0x50 + ext);
    xb_wr16(d, 3);
    xb_wr16(d + 2, 0x50);
    xb_wr32(d + 0x04, 1);
    xb_wr32(d + 0x08, ARG(0));
    xb_wr32(d + 0x14, 0x80); /* DO_DEVICE_INITIALIZING */
    xb_wr32(d + 0x18, ext ? d + 0x50 : 0);
    xb_wr8(d + 0x1C, ARG(3));
    xb_wr8(d + 0x1E, 1);
    xb_wr32(ARG(5), d);
    if (ARG(2)) {
        uint32_t n = ARG(2);
        rt_log("  device %.*s\n", xb_rd16(n), rt_str(xb_rd32(n + 4)));
    }
    return STATUS_SUCCESS;
}

/* XeLoadSection(XBE_SECTION_HEADER *): every section was loaded with the
 * image, so this only keeps the reference count the game may look at. */
K(XeLoadSection) {
    uint32_t s = ARG(0);
    xb_wr32(s + 0x18, xb_rd32(s + 0x18) + 1);
    rt_log("  load section %s\n", rt_str(xb_rd32(s + 0x14)));
    return STATUS_SUCCESS;
}

K(XeUnloadSection) {
    uint32_t s = ARG(0);
    if (xb_rd32(s + 0x18)) xb_wr32(s + 0x18, xb_rd32(s + 0x18) - 1);
    return STATUS_SUCCESS;
}

K(DbgPrint) {
    fprintf(stderr, "[game] %s", rt_str(ARG(0)));
    return 0;
}

/* ---- dispatch ---- */

typedef uint32_t (*Handler)(XbCtx *);
static Handler handlers[400];

#define H(ord, name) handlers[ord] = k_##name

extern uint32_t k_file_NtCreateFile(XbCtx *c);
extern uint32_t k_file_NtOpenFile(XbCtx *c);
extern uint32_t k_file_NtReadFile(XbCtx *c);
extern uint32_t k_file_NtWriteFile(XbCtx *c);
extern uint32_t k_file_NtQueryInformationFile(XbCtx *c);
extern uint32_t k_file_NtSetInformationFile(XbCtx *c);
extern uint32_t k_file_NtQueryVolumeInformationFile(XbCtx *c);
extern uint32_t k_file_NtQueryFullAttributesFile(XbCtx *c);
extern uint32_t k_file_NtOpenSymbolicLinkObject(XbCtx *c);
extern uint32_t k_file_NtQuerySymbolicLinkObject(XbCtx *c);

void xb_kernel(XbCtx *c, uint32_t ordinal) {
    const XbKernelInfo *k = rt_kernel_info(ordinal);
    if (v_tick_count) xb_wr32(v_tick_count, (uint32_t)(rt_now_100ns() / 10000));
    Handler h = ordinal < 400 ? handlers[ordinal] : NULL;
    if (rt_log_level) {
        rt_log("%s(", k ? k->name : "?");
        int n = k ? (k->conv == 1 ? 2 : k->argbytes / 4) : 0;
        for (int i = 0; i < n && i < 10; i++) {
            uint32_t v = k->conv == 1 ? (i == 0 ? c->ecx : i == 1 ? c->edx : ARG(i - 2)) : ARG(i);
            fprintf(stderr, "%s%x", i ? ", " : "", v);
        }
        fprintf(stderr, ") from %08x\n", xb_rd32(c->esp));
    }
    if (!h) {
        char args[256] = "";
        for (int i = 0; i < 6; i++) snprintf(args + strlen(args), sizeof args - strlen(args), " %08x", ARG(i));
        rt_fatal(c, "kernel export %u (%s) is not implemented; called from %08x, stack args:%s", ordinal,
                 k ? k->name : "unknown", xb_rd32(c->esp), args);
    }
    c->eax = h(c);
    uint32_t pop = 4;
    if (k && k->conv == 0) pop += k->argbytes;
    if (k && k->conv == 1 && k->argbytes > 8) pop += k->argbytes - 8;
    c->esp += pop;
}

/* Kernel variables the XBE imports, with the values a retail Xbox has. */
static uint32_t data_export(const XbKernelInfo *k) {
    uint32_t a;
    if (!strcmp(k->name, "KeTickCount")) return v_tick_count = rt_kdata_alloc(4);
    if (!strcmp(k->name, "XboxKrnlVersion")) {
        a = rt_kdata_alloc(8);
        xb_wr16(a, 1), xb_wr16(a + 2, 0), xb_wr16(a + 4, 5838), xb_wr16(a + 6, 1);
        return a;
    }
    if (!strcmp(k->name, "XeImageFileName")) {
        const char *name = "\\Device\\CdRom0\\default.xbe";
        uint32_t buf = rt_kdata_alloc(64);
        strcpy(rt_str(buf), name);
        a = rt_kdata_alloc(8);
        xb_wr16(a, strlen(name)), xb_wr16(a + 2, strlen(name) + 1), xb_wr32(a + 4, buf);
        return a;
    }
    if (!strcmp(k->name, "HalDiskCachePartitionCount")) {
        a = rt_kdata_alloc(4);
        xb_wr32(a, 3);
        return a;
    }
    if (!strcmp(k->name, "LaunchDataPage")) return rt_kdata_alloc(4); /* NULL: a cold boot */
    /* Everything else (object types, keys, hardware info) starts zeroed. */
    return rt_kdata_alloc(0x200);
}

void rt_kernel_init(void) {
    rt_system_time_base = (uint64_t)(time(NULL) + 11644473600ll) * 10000000ull;
    H(1, AvGetSavedDataAddress);
    H(4, AvSetSavedDataAddress);
    H(8, DbgPrint);
    H(15, ExAllocatePoolWithTag);
    H(17, ExFreePool);
    H(23, ExQueryPoolBlockSize);
    H(24, ExQueryNonVolatileSetting);
    H(47, HalRegisterShutdownNotification);
    H(49, HalReturnToFirmware);
    H(65, IoCreateDevice);
    H(67, IoCreateSymbolicLink);
    H(69, IoDeleteSymbolicLink);
    H(95, KeBugCheck);
    H(99, KeDelayExecutionThread);
    H(97, KeCancelTimer);
    H(107, KeInitializeDpc);
    H(113, KeInitializeTimerEx);
    H(119, KeInsertQueueDpc);
    H(137, KeRemoveQueueDpc);
    H(149, KeSetTimer);
    H(150, KeSetTimerEx);
    H(126, KeQueryPerformanceCounter);
    H(127, KeQueryPerformanceFrequency);
    H(128, KeQuerySystemTime);
    H(129, KeRaiseIrqlToDpcLevel);
    H(143, KeSetBasePriorityThread);
    H(145, KeSetEvent);
    H(151, KeStallExecutionProcessor);
    H(159, KeWaitForSingleObject);
    H(160, KfRaiseIrql);
    H(161, KfLowerIrql);
    H(165, MmAllocateContiguousMemory);
    H(166, MmAllocateContiguousMemoryEx);
    H(167, MmAllocateSystemMemory);
    H(171, MmFreeContiguousMemory);
    H(172, MmFreeSystemMemory);
    H(173, MmGetPhysicalAddress);
    H(178, MmPersistContiguousMemory);
    H(179, MmQueryAddressProtect);
    H(180, MmQueryAllocationSize);
    H(181, MmQueryStatistics);
    H(182, MmSetAddressProtect);
    H(184, NtAllocateVirtualMemory);
    H(186, NtClearEvent);
    H(187, NtClose);
    H(189, NtCreateEvent);
    H(192, NtCreateMutant);
    H(193, NtCreateSemaphore);
    H(199, NtFreeVirtualMemory);
    H(217, NtQueryVirtualMemory);
    H(221, NtReleaseMutant);
    H(222, NtReleaseSemaphore);
    H(225, NtSetEvent);
    H(233, NtWaitForSingleObject);
    H(234, NtWaitForSingleObjectEx);
    H(235, NtWaitForMultipleObjectsEx);
    H(238, NtYieldExecution);
    H(246, ObReferenceObjectByHandle);
    H(250, ObfDereferenceObject);
    H(255, PsCreateSystemThreadEx);
    H(258, PsTerminateSystemThread);
    H(269, RtlCompareMemoryUlong);
    H(277, RtlEnterCriticalSection);
    H(279, RtlEqualString);
    H(289, RtlInitAnsiString);
    H(291, RtlInitializeCriticalSection);
    H(294, RtlLeaveCriticalSection);
    H(301, RtlNtStatusToDosError);
    H(304, RtlTimeFieldsToTime);
    H(305, RtlTimeToTimeFields);
    H(306, RtlTryEnterCriticalSection);
    H(327, XeLoadSection);
    H(328, XeUnloadSection);
    H(358, HalIsResetOrShutdownPending);
    handlers[190] = k_file_NtCreateFile;
    handlers[202] = k_file_NtOpenFile;
    handlers[219] = k_file_NtReadFile;
    handlers[236] = k_file_NtWriteFile;
    handlers[211] = k_file_NtQueryInformationFile;
    handlers[226] = k_file_NtSetInformationFile;
    handlers[218] = k_file_NtQueryVolumeInformationFile;
    handlers[210] = k_file_NtQueryFullAttributesFile;
    handlers[203] = k_file_NtOpenSymbolicLinkObject;
    handlers[215] = k_file_NtQuerySymbolicLinkObject;

    /* Fill the XBE's kernel thunk table: functions get fake addresses that
     * xb_call_indirect recognises, variables get real storage. */
    for (uint32_t slot = rt_image.thunk;; slot += 4) {
        uint32_t v = xb_rd32(slot);
        if (!v) break;
        uint32_t ord = v & 0x7FFFFFFFu;
        const XbKernelInfo *k = rt_kernel_info(ord);
        xb_wr32(slot, k && k->conv == 3 ? data_export(k) : RT_KFUNC_BASE + 4 * ord);
    }
}
