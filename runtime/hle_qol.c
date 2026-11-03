/* Quality of life (the user's, 2026-11-01).
 *
 * Fast loading (fast_loading in forza.ini, XBRT_FAST_LOADING; on by default, F1): the game holds
 * its loading screens for a least time. 0x1B51D0, as a race starts or restarts, reads the tick count
 * (0x265046) and, unless 3 s have passed since the load began, sleeps until 1 s or 3 s have (0.5 s
 * when the screen's flag at +0x34 is clear); the picture stops meanwhile (the user's 1.15 s stops in
 * the frame traces of 31 Oct, every one at a race load). Nothing waits on it: the loader thread waited
 * for the main thread to finish the hold. Here that one reading is 3 s later, so the hold ends at once;
 * every other caller gets the true count.
 *
 * Skip intro (skip_intro, XBRT_SKIP_INTRO; on by default): the intro video at every start
 * (media\FrontEnd\IntroVideo.bik) skipped as the player would, A pressed once for them 0.8 s after
 * file.c sees it opened. Taking the file away instead would be a disc error. */
#include <stdio.h>
#include <stdlib.h>

#include "funcs.h"
#include "rt.h"

volatile int rt_fast_loading = -1, rt_skip_intro = -1;
volatile uint64_t rt_intro_at;

int rt_qol_pad(void) {
    if (!rt_intro_at) return 0;
    if (rt_skip_intro < 0) rt_skip_intro = !(getenv("XBRT_SKIP_INTRO") && !atoi(getenv("XBRT_SKIP_INTRO")));
    uint64_t t = rt_now_100ns() - rt_intro_at;
    return rt_skip_intro && t > 8000000 && t < 10000000; /* 0.8 to 1.0 s after it opened */
}

void orig_f_00265046(XbCtx *c); /* GetTickCount, the game's own (wraps.txt) */
void f_00265046(XbCtx *c) {
    uint32_t ret = xb_rd32(c->esp);
    orig_f_00265046(c);
    if (ret != 0x1B52AA) return; /* the hold's first reading, after the load (0x1B52A5) */
    if (rt_fast_loading < 0) rt_fast_loading = !(getenv("XBRT_FAST_LOADING") && !atoi(getenv("XBRT_FAST_LOADING")));
    if (rt_fast_loading) c->eax += 3001;
}
