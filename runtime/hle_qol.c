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

/* The same crash a third time (the user's, 17 Nov, after a drift event on Pacific Shipyards: "indirect call to
 * 00000000 ... return address 000a208c", Leaderboard106500 read just before), and no "scoreboards: ... KB loaded"
 * line in the session: the cache never passed 1 MB, so the trim above was not what lost the scoreboard. What is
 * sure: "Updating scoreboards" (0xA2040, thiscall, no arguments, called once from the scoreboards' set-up at
 * 0xA2AAD) calls through the scoreboard at its +0x5C, which the set-up took from the manager's getter (0x32E1A0:
 * base, id, param; 0 when the manager is not open, its byte at +0x2E0, when the scoreboard cannot be made, or when
 * it is gone again after the trim) and never checks. So:
 *  - the getter's every 0 is logged with what it was asked and the manager's state, to learn which it is;
 *  - a set-up whose scoreboard at +0x5C is 0 has its update left out, logged: the race's result goes on to the
 *    screen after it without the scoreboards' part, and the game stays up. */
void orig_f_0032E1A0(XbCtx *c);
void f_0032E1A0(XbCtx *c) {
    uint32_t mgr = c->ecx, base = xb_rd32(c->esp + 4), id = xb_rd32(c->esp + 8), param = xb_rd32(c->esp + 12);
    orig_f_0032E1A0(c);
    if (!c->eax) {
        static int said;
        if (said++ < 40)
            fprintf(stderr, "xbrt: scoreboards: none for Leaderboard%u (base %u, id %u, param %u): the manager %s (boards %u and %u, limit %u KB)\n",
                    base + id + param, base, id, param, mgr && xb_rd8(mgr + 0x2E0) ? "open: not made, or thrown out again" : "not open",
                    mgr ? xb_rd32(mgr + 0x18) : 0, mgr ? xb_rd32(mgr + 0x1C) : 0, mgr ? xb_rd32(mgr + 0x2DC) >> 10 : 0);
    }
}

void orig_f_000A2040(XbCtx *c);
void f_000A2040(XbCtx *c) {
    uint32_t self = c->ecx;
    if (self && !xb_rd32(self + 0x5C)) {
        fprintf(stderr, "xbrt: scoreboards: the race's scoreboard is missing (kind %u, param %u; its others %08x %08x %08x %08x %08x): the update left out, not called through 0\n",
                xb_rd32(self + 4), xb_rd32(self + 0x40), xb_rd32(self + 0x50), xb_rd32(self + 0x54), xb_rd32(self + 0x58), xb_rd32(self + 0x60), xb_rd32(self + 0x64));
        c->esp += 4; /* ret */
        return;
    }
    orig_f_000A2040(c);
}
