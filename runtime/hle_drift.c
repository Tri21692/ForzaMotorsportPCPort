/* Drift events (the user's, 2026-11-01): one car on the track, scored by its drifts, placed by the
 * score against the event's targets (<mods>/drift.txt, a line per event: "ordinal 1st 2nd 3rd", the
 * least score for each place; tools/driftseries.py writes it), as a time trial is placed by the
 * clock (hle_career.c).
 *
 * A drift: the car sliding, its heading at least ANGLE_MIN degrees off the way it is going. While it
 * lasts it scores the distance covered times how far past ANGLE_MIN the angle is (degrees, up to
 * 90): length and angle, not speed (the user: NFSU's is a different game). It ends when the car has
 * run straight for HOLD seconds, and is banked into the total times a length bonus (1 + its length /
 * LENGTH_BONUS metres, at most LENGTH_MAX). It is lost, nothing banked, when the car
 *  - spins (the angle past SPIN degrees),
 *  - hits something (its velocity changing faster than IMPACT m/s^2: no braking or cornering comes
 *    near; a wall or another car does),
 *  - leaves the road: the race's own off-track penalty growing (timing +0x98, the seconds of
 *    penalty: found in the race dumps of 2026-10-31, it only steps up, and grows while the car is
 *    off the track's edges). A slide begun off the road scores nothing when it comes back onto it:
 *    no drift starts until the car has run straight on the road for HOLD seconds.
 * Under MIN_SPEED (15 mph) there is no drift and no points.
 *
 * The car (racer +0xA0): +0x38 its heading (the turn's third row), +0x44 its velocity (m/s),
 * world x, y up, z. The race: [0x592984]+0x318 the event (+0x10 its ordinal, +0x24 its laps);
 * scoring from the first lap's start (timing +0x9C 0) to the laps' end. */
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "funcs.h"
#include "rt.h"

#define ANGLE_MIN 12.0f
#define SPIN 110.0f
#define HOLD 0.7          /* s */
#define IMPACT 30.0f      /* m/s^2, about 3 g */
#define MIN_SPEED 6.7056f /* m/s, 15 mph: slower than this, no drift and no points (the user's) */
#define LENGTH_BONUS 150.0
#define LENGTH_MAX 3.0

#define MAX_DR 32
static struct { uint32_t ordinal, target[3]; } dr[MAX_DR];
static int ndr;
static pthread_once_t dr_once = PTHREAD_ONCE_INIT;

static void dr_load(void) {
    char path[1200], line[256];
    snprintf(path, sizeof path, "%s/drift.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    while (ndr < MAX_DR && fgets(line, sizeof line, f))
        if (sscanf(line, "%u %u %u %u", &dr[ndr].ordinal, &dr[ndr].target[0], &dr[ndr].target[1], &dr[ndr].target[2]) == 4) ndr++;
    fclose(f);
    fprintf(stderr, "xbrt: drift events: %d from %s\n", ndr, path);
}

/* The running event's entry, or -1 when it is not a drift event; its laps. */
static int dr_event(uint32_t *laps) {
    pthread_once(&dr_once, dr_load);
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    if (!ndr || !ev || ev >= RT_USER_LIMIT) return -1;
    uint32_t ordinal = xb_rd32(ev + 0x10);
    for (int i = 0; i < ndr; i++)
        if (dr[i].ordinal == ordinal) {
            if (laps) *laps = xb_rd32(ev + 0x24);
            return i;
        }
    return -1;
}

static float rdf(uint32_t a) {
    uint32_t b = xb_rd32(a);
    float f;
    memcpy(&f, &b, 4);
    return f;
}

/* The run's state (the DPC thread writes it with rt_gil held; the HUD reads it). */
static struct {
    uint32_t racer;
    unsigned serial;          /* the race begun (rt_qr_music): a restart keeps the racer, not this */
    double total, cur, len;   /* banked, the drift now (before its length bonus), its length (m) */
    float angle, v[3], penalty, pos[3]; /* pos: the car's place at the last tick it moved */
    int drifting, done, offroad;  /* offroad: the car left the road and has not yet run straight on it */
    int line_k, ww;               /* the racing line's point nearest the car; facing the wrong way since ww_clock */
    float ww_clock;               /* (the race's clock, timing +0x94: it stands while paused) */
    uint64_t last, calm_since, v_at, straight_since;
    float clock;                  /* the race's clock (timing +0xA0) at the last tick */
    char msg[32];
    uint64_t msg_until;
} ds;

static void dr_say(const char *m) {
    snprintf(ds.msg, sizeof ds.msg, "%s", m);
    ds.msg_until = rt_now_100ns() + 15000000;
}

static double bonus(double len) { double b = 1.0 + len / LENGTH_BONUS; return b > LENGTH_MAX ? LENGTH_MAX : b; }

static void dr_bank(void) {
    if (ds.drifting && ds.cur > 0) {
        double got = ds.cur * bonus(ds.len);
        ds.total += got;
        char m[32];
        snprintf(m, sizeof m, "+%.0f", got);
        dr_say(m);
    }
    ds.cur = ds.len = 0, ds.drifting = 0, ds.calm_since = 0;
}

static void dr_lose(const char *why) {
    if (ds.drifting && ds.cur > 0) dr_say(why);
    ds.cur = ds.len = 0, ds.drifting = 0, ds.calm_since = 0;
}

static uint32_t player_racer(void) {
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (!arr || arr >= RT_USER_LIMIT || n > 16) return 0;
    for (uint32_t k = 0; k < n; k++) {
        uint32_t r = xb_rd32(arr + 4 * k);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) return r;
    }
    return 0;
}

/* ---- the wrong way (the user's, 9 Nov: driving the track backwards to farm drift points) ----
 * The car facing more than WW_ANGLE degrees from the way the track runs (the AI's racing line, in race order: the
 * track 0x5E1450 +4, its points' x, z, y at +0x30, +0x44, +0x58) for WW_SECONDS of the race's clock: the drift in
 * progress is lost and the car is set back on the line, facing along it, standing. A drift's own angle stays under
 * 90 (past SPIN it is lost anyway), so only a car turned round counts. */
#define WW_ANGLE 120.0f
#define WW_SECONDS 3.0f

static void wrf(uint32_t a, float f) {
    uint32_t u;
    memcpy(&u, &f, 4);
    xb_wr32(a, u);
}

static int dr_line(uint32_t *xs, uint32_t *zs, uint32_t *ys, uint32_t *np) {
    uint32_t track = xb_rd32(0x5E1450), line = track && track < RT_USER_LIMIT && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
    if (!line || line >= RT_USER_LIMIT) return 0;
    *np = xb_rd32(line + 8), *xs = xb_rd32(line + 0x30), *zs = xb_rd32(line + 0x44), *ys = xb_rd32(line + 0x58);
    return *np > 8 && *np < 100000 && *xs && *xs < RT_USER_LIMIT && *zs && *zs < RT_USER_LIMIT && *ys && *ys < RT_USER_LIMIT;
}

/* The line's point nearest (x, z): near the last one found, or (a quarter of the time, or far from it) all of them. */
static int dr_nearest(uint32_t xs, uint32_t zs, uint32_t np, float x, float z) {
    static unsigned n;
    int best = -1, lo = 0, hi = (int)np;
    float bd = 1e30f;
    if (ds.line_k > 0 && ds.line_k < (int)np && (n++ & 3)) lo = ds.line_k - 60, hi = ds.line_k + 60;
    for (int i = lo; i < hi; i++) {
        int k = (i % (int)np + (int)np) % (int)np;
        float dx = rdf(xs + 4 * k) - x, dz = rdf(zs + 4 * k) - z, d = dx * dx + dz * dz;
        if (d < bd) bd = d, best = k;
    }
    if (lo != 0 && bd > 60.0f * 60.0f) { /* (lost it: all of them) */
        ds.line_k = 0;
        return dr_nearest(xs, zs, np, x, z);
    }
    return ds.line_k = best;
}

/* The drift's own respawn: on the line a little ahead of point k, facing along it, standing (no push, no spin). */
static void dr_respawn(uint32_t car, uint32_t xs, uint32_t zs, uint32_t ys, uint32_t np, int k) {
    k = (k + 2) % (int)np;
    int k2 = (k + 3) % (int)np;
    float x = rdf(xs + 4 * k), y = rdf(ys + 4 * k), z = rdf(zs + 4 * k);
    float fx = rdf(xs + 4 * k2) - x, fz = rdf(zs + 4 * k2) - z, len = sqrtf(fx * fx + fz * fz);
    if (!(len > 0.1f) || !(x == x) || !(y == y) || !(z == z)) return;
    fx /= len, fz /= len;
    float pose[12] = {x, y + 0.6f, z, fz, 0, -fx, 0, 1, 0, fx, 0, fz}; /* position, then the turn's rows (the third: the nose) */
    for (int j = 0; j < 12; j++) wrf(car + 0x14 + 4 * j, pose[j]);
    for (int j = 0; j < 6; j++) wrf(car + 0x44 + 4 * j, 0); /* velocity and spin */
    ds.pos[0] = x, ds.pos[1] = y + 0.6f, ds.pos[2] = z; /* (not taken for the game's respawn: our own message stands) */
    memset(ds.v, 0, sizeof ds.v);
    fprintf(stderr, "xbrt: drift event: the wrong way for %.0f s: set back on the line at point %d\n", WW_SECONDS, k);
}

/* 1 when the car was just set back (nothing more this tick). */
static int dr_wrong_way(uint32_t car, uint32_t timing) {
    uint32_t xs, zs, ys, np;
    if (!dr_line(&xs, &zs, &ys, &np)) return 0;
    float x = rdf(car + 0x14), z = rdf(car + 0x1C), hx = rdf(car + 0x38), hz = rdf(car + 0x40);
    int k = dr_nearest(xs, zs, np, x, z);
    if (k < 0) return 0;
    int k2 = (k + 3) % (int)np;
    float dx = rdf(xs + 4 * k2) - rdf(xs + 4 * k), dz = rdf(zs + 4 * k2) - rdf(zs + 4 * k);
    float dl = sqrtf(dx * dx + dz * dz), hl = sqrtf(hx * hx + hz * hz);
    if (!(dl > 0.01f) || !(hl > 0.1f)) return 0;
    float c = (dx * hx + dz * hz) / (dl * hl);
    int wrong = c < cosf(WW_ANGLE * 3.14159265f / 180.0f);
    float clk = rdf(timing + 0x94);
    if (!wrong) {
        ds.ww = 0;
        return 0;
    }
    if (!ds.ww) {
        ds.ww = 1, ds.ww_clock = clk;
        return 0;
    }
    if (clk - ds.ww_clock < WW_SECONDS) return 0;
    if (ds.drifting && ds.cur > 0) dr_lose("WRONG WAY: DRIFT LOST");
    else dr_say("WRONG WAY");
    dr_respawn(car, xs, zs, ys, np, k);
    ds.ww = 0;
    return 1;
}

/* With rt_gil held, from rt_career_tick: the drift scoring. */
void rt_drift_tick(void) {
    uint32_t laps = 0;
    if (!xb_rd32(0x592984) || dr_event(&laps) < 0) { ds.racer = 0; return; }
    uint32_t r = player_racer(), car = r ? xb_rd32(r + 0xA0) : 0, timing = r ? xb_rd32(r + 0xC0) : 0;
    if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) return;
    uint64_t now = rt_now_100ns();
    unsigned serial;
    rt_qr_music(&serial);
    /* A new run: another racer, or the same one restarted (the user's 9 Nov restart from the pause menu kept the
     * racer, so the run before it carried on: its points and its end) */
    if (r != ds.racer || serial != ds.serial) {
        memset(&ds, 0, sizeof ds);
        ds.racer = r, ds.serial = serial, ds.last = now, ds.penalty = rdf(timing + 0x98), ds.clock = rdf(timing + 0xA0);
        fprintf(stderr, "xbrt: drift event: a run begins\n");
    }
    int32_t lap = (int32_t)xb_rd32(timing + 0x9C);
    /* How far the car went since the last tick it moved: the drift's length from that, not from a clock. Paused, the
     * car stands and nothing scores (the user's, 3 Nov: pausing mid-drift, the frozen car's slide scored on and on).
     * The race clock read before (timing +0xA0) is the last lap's time, not a running clock: it stood at 0 all of
     * the first lap and then jumped, so nothing ever scored (the user's, 8 Nov: "no points are being awarded"). */
    float clock = rdf(timing + 0xA0);
    float pos[3] = {rdf(car + 0x14), rdf(car + 0x18), rdf(car + 0x1C)};
    double moved = hypot(pos[0] - ds.pos[0], pos[2] - ds.pos[2]);
    int fresh = ds.pos[0] == 0 && ds.pos[2] == 0;
    if (moved > 0 || fresh) memcpy(ds.pos, pos, sizeof pos);
    /* A jump: the game's respawn (or ours, below, which moves ds.pos with the car): the drift in progress is lost (the
     * user's, 9 Nov: "A respawn also kills the drift") */
    if (!fresh && moved > 20 && !ds.done) dr_lose("RESPAWN: DRIFT LOST");
    if (fresh || moved > 20) moved = 0; /* (the first tick, or a jump: a restart, a respawn) */
    ds.clock = clock, ds.last = now;
    if (ds.done) return;
    if (laps && lap >= (int32_t)laps) { /* the last lap done: what is drifting now counts */
        dr_bank();
        ds.done = 1;
        fprintf(stderr, "xbrt: drift event: %.0f points\n", ds.total);
        { /* the achievements: a score of 10,000, a 1st place (the event's first target) */
            int i = dr_event(NULL);
            if (ds.total >= 10000) rt_ach_reach("drift10k", 1);
            if (i >= 0 && ds.total >= dr[i].target[0]) rt_ach_reach("drift_win", 1);
        }
        return;
    }
    float v[3] = {rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C)}, fx = rdf(car + 0x38), fz = rdf(car + 0x40);
    float pen = rdf(timing + 0x98);
    { /* debugging: XBRT_DRIFT_LOG=1, the scoring's state twice a second */
        static int on = -1;
        static uint64_t nx;
        if (on < 0) on = getenv("XBRT_DRIFT_LOG") && atoi(getenv("XBRT_DRIFT_LOG"));
        if (on && now >= nx) {
            nx = now + 5000000;
            float sp0 = hypotf(v[0], v[2]), fl0 = hypotf(fx, fz), c0 = sp0 > 0.1f && fl0 > 0.1f ? (v[0] * fx + v[2] * fz) / (sp0 * fl0) : 1;
            fprintf(stderr, "xbrt: drift log: lap %d of %u clock %.2f moved %.3f speed %.1f angle %.1f heading %.2f,%.2f pen %.3f (was %.3f) offroad %d drifting %d cur %.0f len %.0f total %.0f\n",
                    lap, laps, clock, moved, sp0, acosf(c0 < -1 ? -1 : c0 > 1 ? 1 : c0) * 57.29578f, fx, fz, pen, ds.penalty, ds.offroad, ds.drifting, ds.cur, ds.len, ds.total);
        }
    }
    int off = pen > ds.penalty + 0.001f;
    ds.penalty = pen;
    if (lap < 0) { /* not yet started: nothing to score */
        memcpy(ds.v, v, sizeof v), ds.v_at = now;
        return;
    }
    if (dr_wrong_way(car, timing)) return;
    if (moved == 0) return; /* paused (or no physics step since the last tick): the car stands */
    if (now - ds.v_at >= 500000) { /* every 50 ms: an impact is a jump in velocity */
        double t = (now - ds.v_at) / 1e7, dv = sqrt((v[0] - ds.v[0]) * (v[0] - ds.v[0]) + (v[1] - ds.v[1]) * (v[1] - ds.v[1]) + (v[2] - ds.v[2]) * (v[2] - ds.v[2]));
        memcpy(ds.v, v, sizeof v), ds.v_at = now;
        if (dv / t > IMPACT) { dr_lose("HIT: DRIFT LOST"); return; }
    }
    if (off) { dr_lose("OFF ROAD: DRIFT LOST"); ds.offroad = 1, ds.straight_since = 0; return; }
    float sp = hypotf(v[0], v[2]), fl = hypotf(fx, fz);
    float a = 0;
    if (sp >= MIN_SPEED && fl > 0.1f) {
        float c = (v[0] * fx + v[2] * fz) / (sp * fl);
        a = acosf(c < -1 ? -1 : c > 1 ? 1 : c) * 57.29578f;
    }
    ds.angle = a;
    if (ds.offroad) { /* a slide begun off the road scores nothing when it comes back on: first HOLD s straight (or slow) on it */
        if (a >= ANGLE_MIN) ds.straight_since = 0;
        else if (!ds.straight_since) ds.straight_since = now;
        else if ((now - ds.straight_since) / 1e7 > HOLD) ds.offroad = 0;
        if (ds.offroad) return;
    }
    if (a > SPIN) { dr_lose("SPUN: DRIFT LOST"); return; }
    if (a >= ANGLE_MIN) {
        ds.drifting = 1, ds.calm_since = 0;
        ds.cur += moved * ((a > 90 ? 90 : a) - (ANGLE_MIN - 2));
        ds.len += moved;
    } else if (ds.drifting) {
        if (!ds.calm_since) ds.calm_since = now;
        else if ((now - ds.calm_since) / 1e7 > HOLD) dr_bank();
    }
}

/* From the racer lookup (hle_career.c's 0x755D0), as a time trial's: once the laps are done, the
 * player's place from the score (1st at the first target or more ...; else 4th). */
void rt_drift_place(uint32_t racer) {
    int i = dr_event(NULL);
    if (i < 0 || racer != ds.racer || !ds.done) return;
    uint32_t place = 4;
    for (int k = 2; k >= 0; k--)
        if (ds.total >= dr[i].target[k]) place = (uint32_t)k + 1;
    static uint32_t told;
    if (told != racer) told = racer, fprintf(stderr, "xbrt: drift event %u: %.0f points (targets %u, %u, %u): place %u\n", dr[i].ordinal, ds.total,
                                             dr[i].target[0], dr[i].target[1], dr[i].target[2], place);
    if (xb_rd32(racer + 0xBC) != place) xb_wr32(racer + 0xBC, place);
}

/* For the race HUD (glover.c, on the GPU's thread: reads only). */
int rt_drift_hud(RtDriftHud *h) {
    int i = dr_event(NULL);
    if (i < 0 || !ds.racer) return 0;
    h->total = (uint32_t)ds.total;
    h->drift = ds.drifting ? (uint32_t)(ds.cur * bonus(ds.len)) : 0;
    h->mult = (float)bonus(ds.len);
    h->angle = ds.angle;
    h->drifting = ds.drifting;
    h->done = ds.done;
    memcpy(h->target, dr[i].target, sizeof h->target);
    h->msg = rt_now_100ns() < ds.msg_until ? ds.msg : NULL;
    return 1;
}
