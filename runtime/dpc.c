/* Kernel timers and deferred procedure calls.
 *
 * One runtime thread plays the part of the Xbox's DPC level: it fires
 * expired timers (signalling them and queueing their DPC) and runs queued
 * DPC routines on its own guest context at DISPATCH_LEVEL, holding the
 * big lock like any guest thread.
 */
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "rt.h"

typedef struct {
    uint32_t timer, dpc, period_ms;
    uint64_t due;
} Timer;

static Timer timers[256];
static int ntimers;

typedef struct {
    uint32_t dpc, arg1, arg2;
} Queued;

static Queued queue[256];
static int nqueued;

void rt_timer_set(uint32_t timer, uint64_t due, uint32_t period_ms, uint32_t dpc) {
    if (ntimers == 256) rt_fatal(NULL, "too many kernel timers");
    timers[ntimers++] = (Timer){timer, dpc, period_ms, due};
    xb_wr32(timer + 4, 0); /* not signalled until it expires */
    xb_wr8(timer + 3, 1);  /* Inserted */
}

int rt_timer_cancel(uint32_t timer) {
    for (int i = 0; i < ntimers; i++) {
        if (timers[i].timer == timer) {
            timers[i] = timers[--ntimers];
            xb_wr8(timer + 3, 0);
            return 1;
        }
    }
    return 0;
}

void rt_dpc_queue(uint32_t dpc, uint32_t arg1, uint32_t arg2) {
    for (int i = 0; i < nqueued; i++)
        if (queue[i].dpc == dpc) return; /* already queued, as on the Xbox */
    if (nqueued == 256) rt_fatal(NULL, "DPC queue full");
    queue[nqueued++] = (Queued){dpc, arg1, arg2};
}

static void *dpc_main(void *arg) {
    RtThread *t = arg;
    rt_self = t;
    XbCtx *c = &t->ctx;
    xb_wr8(t->kpcr + 0x24, 2); /* DISPATCH_LEVEL */
    for (;;) {
        pthread_mutex_lock(&rt_gil);
        uint64_t now = rt_now_100ns();
        for (int i = 0; i < ntimers;) {
            Timer *tm = &timers[i];
            if (tm->due > now) {
                i++;
                continue;
            }
            xb_wr32(tm->timer + 4, 1);
            pthread_cond_broadcast(&rt_changed);
            if (tm->dpc) rt_dpc_queue(tm->dpc, (uint32_t)now, (uint32_t)(now >> 32));
            if (tm->period_ms) {
                tm->due += (uint64_t)tm->period_ms * 10000;
                i++;
            } else {
                xb_wr8(tm->timer + 3, 0);
                *tm = timers[--ntimers];
            }
        }
        while (nqueued) {
            Queued q = queue[0];
            memmove(queue, queue + 1, --nqueued * sizeof *queue);
            uint32_t routine = xb_rd32(q.dpc + 0x0C), context = xb_rd32(q.dpc + 0x10);
            rt_guest_call(c, routine, 4, q.dpc, context, q.arg1, q.arg2);
        }
        pthread_mutex_unlock(&rt_gil);
        usleep(1000);
    }
    return NULL;
}

void rt_dpc_start(void) {
    RtThread *t = rt_thread_create(0x10000, 0, 0);
    pthread_t h;
    pthread_attr_t a;
    pthread_attr_init(&a);
    pthread_attr_setstacksize(&a, 16u << 20);
    pthread_create(&h, &a, dpc_main, t);
    pthread_attr_destroy(&a);
}
