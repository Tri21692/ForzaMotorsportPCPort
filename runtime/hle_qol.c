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

/* DSOUND's command to the GP DSP (0x3F602C, thiscall, two arguments: CDirectSound_CommitEffectData's): it spins until
 * the DSP has acknowledged the last command, then writes the next one. The DSP isn't run; apu.c's rt_apu_tick stands
 * in for its executive and acknowledges from the DPC thread every millisecond, so each command waited a tick or more.
 * A race's start sends a long run of them as its sounds load, and the game stood still for 370 ms between Start Race
 * and the intro (the user's, 8 Nov: "Alpine Ring dropped below 30"; on every track). Each is acknowledged as it is
 * written: what the tick does, without the wait. XBRT_GP_ACK_NOW=0: as before. */
void orig_f_003F602C(XbCtx *c);
void f_003F602C(XbCtx *c) {
    static int on = -1;
    if (on < 0) on = !getenv("XBRT_GP_ACK_NOW") || atoi(getenv("XBRT_GP_ACK_NOW"));
    orig_f_003F602C(c);
    if (on) rt_apu_tick();
}

/* The scoreboards' cache (the user's crash after a Fuji race, 10 Nov; the same at Tsukuba, 9 Nov). The leaderboard
 * manager (0x5929E8) holds every scoreboard loaded, keyed by id (Leaderboard106500 is 100000 + 6500): its getter
 * (vtable +4, 0x32E1A0) makes one it lacks, adds it and then trims the cache (0x32E010) while the scoreboards'
 * sizes (vtable +0x38, 0x32BBA0) pass the manager's limit (+0x2DC, 1 MB from 0x3308E3), each time throwing out the
 * least lately used one not in use. Past the limit the one just made is that one: the getter then finds nothing
 * and returns 0, and "Updating scoreboards" after a race (0xA2040) calls through it (the indirect call to 0 at
 * 0xA208A). With the added cars and tracks the scoreboards pass 1 MB; the limit is 8 MB here
 * (XBRT_SCOREBOARD_MB). */
void orig_f_0032E010(XbCtx *c); /* the leaderboard cache trimmed to its limit (thiscall) (wraps.txt) */
void f_0032E010(XbCtx *c) {
    static uint32_t limit;
    if (!limit) {
        const char *e = getenv("XBRT_SCOREBOARD_MB");
        limit = (uint32_t)(e && atoi(e) > 0 ? atoi(e) : 8) << 20;
    }
    uint32_t self = c->ecx;
    if (xb_rd32(self + 0x2DC) < limit) xb_wr32(self + 0x2DC, limit);
    static int logged;
    if (logged < 4) {
        uint32_t eax = c->eax, edx = c->edx; /* (the sizes' sum, as the trim measures it) */
        xb_push(c, 0x0032E01Bu); f_0032BBA0(c);
        uint32_t used = c->eax;
        c->eax = eax; c->edx = edx; c->ecx = self;
        if (used > (1u << 20)) {
            logged++;
            fprintf(stderr, "xbrt: scoreboards: %u KB loaded, past the game's 1 MB (the limit is %u MB)\n", used >> 10, limit >> 20);
        }
    }
    orig_f_0032E010(c);
}
