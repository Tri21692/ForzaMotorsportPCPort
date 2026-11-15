/* Kaizo Mode (the user's, 15 Nov: "No body damage, no hitting other cars, limited engine damage, and no off
 * roading/hitting walls. If any of these occur, race ends prematurely. CR will be doubled", and "you will always
 * start in last place"). The F1 menu's Kaizo Mode tab switches it (forza.ini's kaizo); it holds for every race
 * with a rival in it but Mayhem's and the drift events (their rules are hits and slides).
 *
 *  - The start: the player's car on the grid's last place, the rivals behind it each moved up one (rt_kaizo_grid,
 *    from hle_career.c's CCar::ResetPositionForGrid).
 *  - The run, watched from the career tick while the race's clock runs:
 *      a hit      the car's velocity changed faster than IMPACT (hle_drift.c's measure: no braking or cornering
 *                 comes near it): another car, a wall;
 *      off road   the game's own penalty clock (timing +0x98) went up: it counts time off the track and contact;
 *      damage     any of the car's damage records (car +0x4380.., hle_quickrace.c) past DAMAGE_MAX: the engine's
 *                 from over-revving may wear that far ("limited engine damage"), a panel's never gets there
 *                 without a hit.
 *    Any of them ends the race there: the racer's progress set to 1.0, as a finished run's (hle_career.c's time
 *    trials), its place the last (rt_kaizo_place, where the game looks the place up and where it records a racer
 *    over the line).
 *  - A clean finish: the race's credits doubled, as the rewards add them (f_00078940, the profile's add-credits,
 *    called from the rewards at 0x17E606).
 * XBRT_KAIZO=1 turns it on for a test; XBRT_KAIZO_TEST=1 only logs what would have ended the race (the autopilot
 * hits things); XBRT_KAIZO_FAIL_AT=<s> ends it that long into a race; XBRT_KAIZO_WIN_AT=<s> finishes it clean and 1st
 * then (the payout). */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "xbrt.h"

#define IMPACT 30.0f       /* m/s^2, about 3 g (hle_drift.c's) */
#define DAMAGE_MAX 0.25f   /* of 1: what a damage record may reach */
#define DMG_FIRST 0x4380u
#define DMG_LAST 0x5A80u
#define DMG_N (((DMG_LAST - DMG_FIRST) / 0x80 + 1) * 3)
#define GRACE 15000000ull  /* 1.5 s from the lights: the launch's wheelspin and the cars sorting themselves out */

extern char rt_toast_text[64];
extern volatile uint64_t rt_toast_until;

static float rdf(uint32_t a) { uint32_t v = xb_rd32(a); float f; memcpy(&f, &v, 4); return f; }

static struct {
    uint32_t racer; unsigned serial;
    int on, failed, clear, told;
    float penalty, v[3];
    uint64_t v_at, began, said_at, failed_at;
    int lapped, ended, winning; /* winning: XBRT_KAIZO_WIN_AT's finish, 1st (testing the payout) */
    float dmg0[DMG_N]; /* the damage records as the race began (some stand above none on a whole car) */
} k;

static void say(const char *msg, int seconds) {
    snprintf(rt_toast_text, sizeof rt_toast_text, "%s", msg);
    rt_toast_until = rt_now_100ns() + (uint64_t)seconds * 10000000ull;
}

int rt_kaizo_setting(void) {
    const char *e = getenv("XBRT_KAIZO"), *s = rt_settings_get("kaizo");
    return e && *e ? atoi(e) : s && atoi(s);
}

static uint32_t racers(uint32_t *arr) {
    uint32_t n = xb_rd32(0x58DAA0 + 0x10);
    *arr = xb_rd32(0x58DAA0 + 4);
    return *arr && *arr < RT_USER_LIMIT && n <= 64 ? n : 0;
}
static uint32_t player_racer(void) {
    uint32_t arr, n = racers(&arr);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) return r;
    }
    return 0;
}

/* A race Kaizo's rules hold in: the setting on, a rival in it, not Mayhem's, not a drift event. */
static int kaizo_race(void) {
    uint32_t arr;
    RtDriftHud h;
    int rt_qr_mayhem_grid(void);
    return rt_kaizo_setting() && racers(&arr) >= 2 && !rt_qr_mayhem() && !rt_qr_mayhem_grid() && !rt_drift_hud(&h);
}

/* The run finished as the game finishes one: the racer's progress (timing +0x70, a double; +0x78 the most reached)
 * at 1.0, which the race's tick tests each frame (0xAE616) to mark the racer done (+0x1B8). The game works the
 * progress out again each frame, so it is written every tick until the racer is done (written once, the race ran
 * on), and the lap count (+0x9C) is set to the event's laps: the progress alone did not end an Arcade race. */
static void finish(uint32_t timing) {
    double one = 1.0;
    uint64_t v;
    memcpy(&v, &one, 8);
    for (uint32_t o = 0x70; o <= 0x78; o += 8) xb_wr32(timing + o, (uint32_t)v), xb_wr32(timing + o + 4, (uint32_t)(v >> 32));
    {
        uint32_t race = xb_rd32(0x592984), ev = race ? xb_rd32(race + 0x318) : 0, laps = ev && ev < RT_USER_LIMIT ? xb_rd32(ev + 0x24) : 0;
        if (laps && laps < 100 && (int32_t)xb_rd32(timing + 0x9C) < (int32_t)laps) {
            xb_wr32(timing + 0x9C, laps);
            if (!k.lapped++) fprintf(stderr, "xbrt: kaizo: the lap count set to %u\n", laps);
        }
    }
}

/* The race ended here: the run finished, last. */
static void fail(uint32_t timing, const char *why) {
    static int test = -1;
    if (test < 0) test = getenv("XBRT_KAIZO_TEST") && atoi(getenv("XBRT_KAIZO_TEST"));
    if (test && rt_now_100ns() - k.said_at < 10000000) return; /* (a line a second) */
    k.said_at = rt_now_100ns();
    fprintf(stderr, "xbrt: kaizo: %s%s\n", why, test ? " (test: the race goes on)" : ": the race ends");
    if (test) return;
    k.failed = 1, k.failed_at = rt_now_100ns();
    finish(timing);
    char msg[64];
    snprintf(msg, sizeof msg, "KAIZO FAILED: %s", why);
    say(msg, 5);
}

/* With rt_gil held, from rt_career_tick. */
void rt_kaizo_tick(void) {
    if (!xb_rd32(0x592984)) {
        /* The race gone: the game takes it down before this tick sees its racer done, so a run begun and never
         * ended by Kaizo counts as clean here (only a finished race is paid: one quit pays nothing to double). */
        if (k.on && k.began && !k.failed && !k.clear) {
            k.clear = 1;
            fprintf(stderr, "xbrt: kaizo: the race over, clean: its credits doubled when paid\n");
        }
        k.racer = 0, k.on = 0;
        return;
    }
    uint32_t r = player_racer(), car = r ? xb_rd32(r + 0xA0) : 0, timing = r ? xb_rd32(r + 0xC0) : 0;
    if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) return;
    unsigned serial;
    int state = rt_qr_music(&serial); /* 1 racing, 2 paused or over, 3 the grid */
    uint64_t now = rt_now_100ns();
    if (r != k.racer || serial != k.serial) { /* a new run (a restart too) */
        if (getenv("XBRT_KAIZO_TEST")) fprintf(stderr, "xbrt: kaizo: a new run: racer %08x -> %08x, serial %u -> %u, state %d, done %u, began %d, failed %d\n", k.racer, r, k.serial, serial, state, xb_rd32(r + 0x1B8) & 0xFF, k.began != 0, k.failed);
        memset(&k, 0, sizeof k);
        k.racer = r, k.serial = serial, k.on = kaizo_race();
        if (k.on) fprintf(stderr, "xbrt: kaizo: this race\n");
    }
    if (!k.on) return;
    float v[3] = {rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C)}, pen = rdf(timing + 0x98);
    int done = xb_rd32(r + 0x1B8) & 0xFF;
    if ((k.failed || k.winning) && !done && state == 1) finish(timing);
    if (k.failed && done && !k.ended++) fprintf(stderr, "xbrt: kaizo: the race over, %.1f s after it was ended\n", (now - k.failed_at) / 1e7);
    if (state != 1 || done || k.failed) { /* the grid, a pause, the end: nothing judged, the measures kept current */
        if (state == 3) k.began = 0;
        if (done && !k.failed && !k.clear && k.began) {
            k.clear = 1;
            fprintf(stderr, "xbrt: kaizo: a clean finish: its credits doubled\n");
        }
        k.penalty = pen, memcpy(k.v, v, sizeof v), k.v_at = now;
        return;
    }
    if (!k.began) {
        k.began = now, k.penalty = pen, memcpy(k.v, v, sizeof v), k.v_at = now;
        for (int i = 0; i < DMG_N; i++) k.dmg0[i] = rdf(car + DMG_FIRST + (uint32_t)(i / 3) * 0x80 + 0x70 + 4 * (uint32_t)(i % 3));
        if (!k.told++) say("KAIZO MODE: NO CONTACT, STAY ON THE ROAD", 4);
        return;
    }
    if (now - k.began < GRACE) { k.penalty = pen, memcpy(k.v, v, sizeof v), k.v_at = now; return; }
    { /* testing the payout: a clean finish, 1st, forced so long in */
        const char *e = getenv("XBRT_KAIZO_WIN_AT");
        if (e && !k.winning && (now - k.began) / 1e7 > atof(e)) {
            k.winning = 1, k.failed_at = now;
            fprintf(stderr, "xbrt: kaizo: test: the race finished clean, 1st\n");
            finish(timing);
            return;
        }
        if (k.winning) return;
    }
    { /* testing: an end forced so long in */
        const char *e = getenv("XBRT_KAIZO_FAIL_AT");
        if (e && (now - k.began) / 1e7 > atof(e)) { fail(timing, "TEST"); return; }
    }
    if (now - k.v_at >= 500000) { /* every 50 ms: an impact is a jump in velocity */
        double t = (now - k.v_at) / 1e7, dv = sqrt((v[0] - k.v[0]) * (v[0] - k.v[0]) + (v[1] - k.v[1]) * (v[1] - k.v[1]) + (v[2] - k.v[2]) * (v[2] - k.v[2]));
        memcpy(k.v, v, sizeof v), k.v_at = now;
        if (t < 0.5 && dv / t > IMPACT) {
            if (getenv("XBRT_KAIZO_TEST") && now - k.said_at >= 10000000) fprintf(stderr, "xbrt: kaizo: velocity changed %.1f m/s in %.3f s (%.0f m/s^2)\n", dv, t, dv / t);
            fail(timing, "CONTACT");
            if (k.failed) return;
        }
    }
    if (pen > k.penalty + 0.001f) {
        if (getenv("XBRT_KAIZO_TEST") && now - k.said_at >= 10000000) fprintf(stderr, "xbrt: kaizo: the penalty clock %.3f -> %.3f\n", k.penalty, pen);
        fail(timing, "OFF THE ROAD");
        if (k.failed) return;
    }
    k.penalty = pen;
    for (int i = 0; i < DMG_N; i++) {
        float d = rdf(car + DMG_FIRST + (uint32_t)(i / 3) * 0x80 + 0x70 + 4 * (uint32_t)(i % 3)), d0 = k.dmg0[i];
        if (d0 >= 0 && d0 <= 1.5f && d <= 1.5f && d - d0 > DAMAGE_MAX) {
            if (getenv("XBRT_KAIZO_TEST") && now - k.said_at >= 10000000) fprintf(stderr, "xbrt: kaizo: damage record %d field %d: %.3f (was %.3f)\n", i / 3, i % 3, d, d0);
            fail(timing, "CAR DAMAGED");
            return;
        }
    }
}

/* The player's place in a race Kaizo ended: the last (from hle_career.c: the racer lookup, and a racer recorded
 * over the line). */
void rt_kaizo_place(uint32_t racer) {
    if (k.winning && racer == k.racer) { if (xb_rd32(racer + 0xBC) != 1) xb_wr32(racer + 0xBC, 1); return; }
    if (!k.failed || racer != k.racer) return;
    uint32_t arr, n = racers(&arr);
    if (n >= 2 && xb_rd32(racer + 0xBC) != n) xb_wr32(racer + 0xBC, n);
}

/* The grid (hle_career.c's f_000410E0, before the game places `car` at `place`, 1 the pole): the place it takes
 * under Kaizo. The cars come one at a time in no order known here, so each rival's place is kept as it is laid, and
 * when the player's comes (the game's place for it p, Kaizo's the last) the rivals already laid behind p are laid
 * again one place up (*again: how many, their cars and places in cars[] and places[]); a rival laid after it and
 * behind p moves up as it comes. */
#define GRID_MAX 16
static struct { uint32_t car[GRID_MAX]; int32_t place[GRID_MAX]; int n, mine; uint64_t at; } g;
int32_t rt_kaizo_grid(uint32_t car, int32_t place, uint32_t *cars, int32_t *places, int *again) {
    *again = 0;
    uint32_t arr, n = racers(&arr);
    uint64_t now = rt_now_100ns();
    if (now - g.at > 3000000) g.n = 0, g.mine = 0; /* (a grid is laid in one go: 0.3 s on, another) */
    g.at = now;
    if (!rt_kaizo_setting() || n < 3 || n > GRID_MAX || place < 1 || place > (int32_t)n) return place;
    int rt_qr_mayhem_grid(void);
    if (rt_qr_mayhem() || rt_qr_mayhem_grid()) return place;
    int mine = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0 && xb_rd32(r + 0xA0) == car) mine = 1;
    }
    if (mine) {
        g.mine = place;
        for (int i = 0; i < g.n; i++)
            if (g.place[i] > place) cars[*again] = g.car[i], places[*again] = g.place[i] - 1, (*again)++;
        fprintf(stderr, "xbrt: kaizo: the player's grid place %d -> %u (%d rivals moved up)\n", place, n, *again);
        return (int32_t)n;
    }
    if (g.n < GRID_MAX) g.car[g.n] = car, g.place[g.n] = place, g.n++;
    return g.mine && place > g.mine ? place - 1 : place;
}

/* The profile's add-credits (thiscall: the amount, a flag): a clean Kaizo race's rewards, twice. */
void orig_f_00078940(XbCtx *c);
void f_00078940(XbCtx *c) {
    uint32_t ret = xb_rd32(c->esp), amount = xb_rd32(c->esp + 4);
    if (getenv("XBRT_KAIZO_TEST") || k.clear)
        fprintf(stderr, "xbrt: kaizo: credits added: %u (from %08x), kaizo clear %d\n", amount, ret, k.clear);
    /* (the rewards are worked out as the race finishes, before this tick sees its racer done or the race gone: a
     * run begun under Kaizo and not ended by it is the clean one) */
    if ((k.clear || (k.on && k.began && !k.failed)) && ret == 0x0017E60Bu && amount && amount < 0x20000000u) {
        xb_wr32(c->esp + 4, amount * 2);
        /* (the rewards' record, esi at the call, its winnings at +4: doubled there too, for the screens that show it) */
        if (c->esi && c->esi < RT_USER_LIMIT && xb_rd32(c->esi + 4) == amount) xb_wr32(c->esi + 4, amount * 2);
        char msg[64];
        snprintf(msg, sizeof msg, "KAIZO CLEAR: %u CR DOUBLED", amount);
        say(msg, 5);
        fprintf(stderr, "xbrt: kaizo: %u credits doubled\n", amount);
        k.clear = 0, k.on = 0; /* (once a race) */
    }
    orig_f_00078940(c);
}
