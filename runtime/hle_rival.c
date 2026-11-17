/* The matched rival (the user's, 17 Nov: "give the opponent the same performance stats that I have, along with the
 * pace matching", of Midnight Touge's one-on-one runs): in the events <mods>/rivalmatch.txt names,
 *
 *   events <ordinal>...        the events it holds in (the Touge's 420 421)
 *   twin <car> <car>           a car the rival never drives itself and the one it drives for it (a D-Spec car and
 *                              the car it was made from: the D-Spec's loose tail is the player's to hold, not the AI's)
 *   pace <fraction> <metres>   the pace matching: the rival's speed eased or pressed by up to that fraction, in full
 *                              at that many metres ahead or behind (hle_quickrace.c reads these: rt_rival_pace)
 *
 * the rival's car is the player's: the same car (or its twin) with the player's own setup, every part and tuning
 * figure of it, so the two have the same engine, weight and tyres whatever the player brings.
 *
 * How: an AI car is made from an AI car model (ai\aicarmodellist.xml: the list at [0x56B5D8]+4, 0x10C bytes an
 * entry: +0 the Id, +4 a CarInit). A CarInit: +0 CarModelId (the car's ordinal), +4 the setup (0xE0 bytes: the
 * installed parts and the tuning, 0x534E0 reads it from the XML), +0xE4 Automatic, +0xE8 and +0xEC the assists,
 * +0xF0 UseStockSetup, +0xF4 CarLiveryId, +0xF8 the livery picked. The player's own CarInit is at [racer+0xB4] of
 * the racer list's person (0x58DAA0; type 0, or 3): the AI's maker (0x228F10) reads the assists from it the same way.
 * The list's lookup by Id (0x43A90, thiscall, the Id its argument) is what the field's preload (0x22AEE8) and each
 * AI car's making (0x229ADB) go through, so the entry it returns is changed there, and put back as it was at the
 * next lookup that is not a matched event's (the list is the game's for every race). XBRT_RIVAL=0: off; =log: the
 * two CarInits written out. Nothing of the saves or the car data is touched. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <pthread.h>
#include "xbrt.h"
#include "funcs.h"
#include "rt.h"

int rt_is_object(uint32_t a);

#define MAX_EV 32
#define MAX_TW 64
#define ENTRY 0x10C
static uint32_t evs[MAX_EV], mods[MAX_EV], tw[MAX_TW][2];
static int nev, nmod, ntw;
static float pace_frac, pace_dist = 60;
static pthread_once_t rv_once = PTHREAD_ONCE_INIT;

static void rv_load(void) {
    char path[1200], line[512];
    snprintf(path, sizeof path, "%s/rivalmatch.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        if (!strncmp(line, "events", 6)) {
            char *p = line + 6, *e;
            for (unsigned long v = strtoul(p, &e, 10); e != p && nev < MAX_EV; p = e, v = strtoul(p, &e, 10)) evs[nev++] = (uint32_t)v;
        } else if (!strncmp(line, "models", 6)) {
            char *p = line + 6, *e;
            for (unsigned long v = strtoul(p, &e, 10); e != p && nmod < MAX_EV; p = e, v = strtoul(p, &e, 10)) mods[nmod++] = (uint32_t)v;
        } else if (ntw < MAX_TW && sscanf(line, "twin %u %u", &tw[ntw][0], &tw[ntw][1]) == 2) ntw++;
        else sscanf(line, "pace %f %f", &pace_frac, &pace_dist);
    }
    fclose(f);
    fprintf(stderr, "xbrt: matched rival: %d events, %d AI car models, %d twins, pace %.2f over %.0f m, from %s\n", nev, nmod, ntw, pace_frac, pace_dist, path);
}

/* Is the event being raced (or loaded) a matched one? XBRT_RIVAL_TEST=1: any race is. */
int rt_rival_event(void) {
    const char *e = getenv("XBRT_RIVAL");
    if (e && !strcmp(e, "0")) return 0;
    pthread_once(&rv_once, rv_load);
    if (getenv("XBRT_RIVAL_TEST")) return 1;
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    if (ev && rt_is_object(ev)) {
        uint32_t o = xb_rd32(ev + 0x10);
        for (int i = 0; i < nev; i++) if (evs[i] == o) return 1;
        return 0;
    }
    /* (the race has its event only a grid's worth of ticks in, after its cars are made: until then the event the
     * career is starting, 0x5B6944, while the track being loaded, 0x592E7C, is its own: it keeps the last career
     * event after its race, as hle_quickrace.c's mayhem_grid_event found) */
    ev = xb_rd32(0x5B6944);
    if (!ev || !rt_is_object(ev) || xb_rd32(ev + 0x20) != xb_rd32(0x592E7C)) return 0;
    uint32_t o = xb_rd32(ev + 0x10);
    for (int i = 0; i < nev; i++) if (evs[i] == o) return 1;
    return 0;
}

/* The pace matching's figures (0 fraction: none). */
float rt_rival_pace(float *dist) {
    pthread_once(&rv_once, rv_load);
    const char *e = getenv("XBRT_RIVAL_PACE");
    if (dist) *dist = pace_dist > 5 ? pace_dist : 60;
    return e ? (float)atof(e) : pace_frac;
}

static void dump(const char *what, uint32_t a) {
    fprintf(stderr, "xbrt: matched rival: %s CarInit %08x:", what, a);
    for (int i = 0; i < 0x108; i += 4) fprintf(stderr, "%s%08x", i % 32 ? " " : "\n   ", xb_rd32(a + i));
    fprintf(stderr, "\n");
}

/* Is the AI car model a matched rival's? (When an AI car is made the game does not yet say which event is loading:
 * the race, its event, the career's event 0x5B6944 and the track loading 0x592E7C were all 0 at the lookups of the
 * Touge's rival, 17 Nov. So the matched events' rivals are AI car models of their own, "models <Id>..." in the
 * file: tools/tougefix.py adds them.) XBRT_RIVAL_TEST=1: any is. */
static int rival_model(uint32_t id) {
    const char *e = getenv("XBRT_RIVAL");
    if (e && !strcmp(e, "0")) return 0;
    pthread_once(&rv_once, rv_load);
    if (getenv("XBRT_RIVAL_TEST")) return 1;
    for (int i = 0; i < nmod; i++) if (mods[i] == id) return 1;
    return 0;
}

static uint32_t held;          /* the entry changed, 0 none */
static uint8_t was[ENTRY];     /* as it was */

void orig_f_00043A90(XbCtx *c);
void f_00043A90(XbCtx *c) {
    uint32_t id = xb_rd32(c->esp + 4);
    if (held) memcpy(xb_mem + held, was, ENTRY), held = 0;
    orig_f_00043A90(c);
    uint32_t e = c->eax;
    const char *env = getenv("XBRT_RIVAL");
    int log = env && !strcmp(env, "log");
    if (log) {
        uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0, ce = xb_rd32(0x5B6944), ok = ce && rt_is_object(ce);
        fprintf(stderr, "xbrt: matched rival: AI car model %u looked up: race %08x, its event %08x, the career's event %08x (ordinal %d, track %d), the track loading %d\n",
                id, g, ev, ce, ok ? (int)xb_rd32(ce + 0x10) : -1, ok ? (int)xb_rd32(ce + 0x20) : -1, (int)xb_rd32(0x592E7C));
    }
    if (!e || !rt_is_object(e) || !rival_model(id)) return;
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), mine = 0;
    for (uint32_t i = 0; arr && i < n && i < 64 && !mine; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && rt_is_object(r) && (xb_rd32(r + 0x14) == 0 || xb_rd32(r + 0x14) == 3)) mine = xb_rd32(r + 0xB4);
    }
    if (!mine || !rt_is_object(mine)) {
        fprintf(stderr, "xbrt: matched rival: AI car model %u asked for with no player's car to match (%u racers)\n", id, n);
        return;
    }
    if (log) dump("the player's", mine), dump("the rival's", e + 4);
    uint32_t car = xb_rd32(mine), drives = car;
    for (int i = 0; i < ntw; i++) if (tw[i][0] == car) drives = tw[i][1];
    if (drives >= 300) return;
    memcpy(was, xb_mem + e, ENTRY), held = e;
    uint32_t theirs = xb_rd32(e + 4);
    xb_wr32(e + 4, drives);
    memcpy(xb_mem + e + 4 + 4, xb_mem + mine + 4, 0xE0); /* the setup: the parts and the tuning */
    xb_mem[e + 4 + 0xF0] = xb_mem[mine + 0xF0];          /* (its own setup, or the stock one, as the player's) */
    static uint32_t told_id, told_car;
    if (told_id != id || told_car != car)
        told_id = id, told_car = car,
        fprintf(stderr, "xbrt: matched rival: AI car model %u (car %u) drives car %u with the player's setup (the player's car %u)\n", id, theirs, drives, car);
}

/* The pace matching (rt_qr_tick calls it every tick of the game, the tick's seconds given): in a matched event with
 * a pace set, each rival's ground covered is eased or pressed by up to the fraction, by how far along the racing
 * line it is ahead of the player or behind (in full at the metres set, in proportion nearer): its place moved along
 * its own way a little less, or more, than it drove, so its driving, grip and corner speeds stay the game's. Not on
 * the grid, under 8 m/s (a start, a spin, a wall) or off the ground's pace in the air. */
static float rdf(uint32_t a) { float f; memcpy(&f, xb_mem + a, 4); return f; }
static void wrf(uint32_t a, float f) { memcpy(xb_mem + a, &f, 4); }

void rt_rival_tick(double dt) {
    static int said;
    static uint64_t ticks;
    float dist, frac = rt_rival_pace(&dist);
    if (frac <= 0 || dt <= 0 || dt > 0.25 || !xb_rd32(0x592984) || !rt_rival_event()) return;
    if (frac > 0.25f) frac = 0.25f;
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (!arr || !rt_is_object(arr) || n < 2 || n > 16) return;
    uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
    uint32_t np = line ? xb_rd32(line + 8) : 0, xs = line ? xb_rd32(line + 0x30) : 0, zs = line ? xb_rd32(line + 0x44) : 0;
    if (np < 3 || np > 100000 || !xs || !zs) return;
    uint32_t me = 0;
    for (uint32_t i = 0; i < n && !me; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && rt_is_object(r) && xb_rd32(r + 0x14) == 0) {
            uint32_t tm = xb_rd32(r + 0xC0);
            if (tm && rt_is_object(tm) && ((int)xb_rd32(tm + 0x9C) >= 0 || rdf(tm + 0xA0) > 0)) me = xb_rd32(r + 0xA0);
        }
    }
    if (!me || !rt_is_object(me)) return;
    float mx = rdf(me + 0x14), mz = rdf(me + 0x1C);
    int km = -1, loop;
    { /* the player's point, and whether the line closes on itself (a circuit) or not (a point-to-point run) */
        float best = 1e30f;
        for (uint32_t j = 0; j < np; j++) {
            float px = rdf(xs + 4 * j) - mx, pz = rdf(zs + 4 * j) - mz, d = px * px + pz * pz;
            if (d < best) best = d, km = (int)j;
        }
        float ex = rdf(xs) - rdf(xs + 4 * (np - 1)), ez = rdf(zs) - rdf(zs + 4 * (np - 1));
        loop = ex * ex + ez * ez < 60.0f * 60.0f;
    }
    ticks++;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (!r || !rt_is_object(r) || xb_rd32(r + 0x14) == 0 || xb_rd32(r + 0x14) == 3) continue;
        uint32_t car = xb_rd32(r + 0xA0), tm = xb_rd32(r + 0xC0);
        if (!car || !rt_is_object(car) || !tm || !rt_is_object(tm)) continue;
        if ((int)xb_rd32(tm + 0x9C) < 0 && rdf(tm + 0xA0) <= 0) continue; /* (the grid) */
        float p[3] = {rdf(car + 0x14), rdf(car + 0x18), rdf(car + 0x1C)}, v[3] = {rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C)};
        float sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
        if (!(sp > 8.0f) || !(sp < 150.0f) || rdf(car + 0x30) < 0.7f) continue;
        int kr = -1;
        float best = 1e30f;
        for (uint32_t j = 0; j < np; j++) {
            float px = rdf(xs + 4 * j) - p[0], pz = rdf(zs + 4 * j) - p[2], d = px * px + pz * pz;
            if (d < best) best = d, kr = (int)j;
        }
        if (best > 30.0f * 30.0f) continue; /* (far off the line: not racing) */
        int dk = kr - km;
        if (loop) { if (dk > (int)np / 2) dk -= (int)np; if (dk < -(int)np / 2) dk += (int)np; }
        /* the points' spacing about the rival: 8 points' run */
        int a = kr, b = kr + 8 < (int)np ? kr + 8 : (loop ? (kr + 8) % (int)np : (int)np - 1);
        if (a == b) a = b - 8 > 0 ? b - 8 : 0;
        float sx = rdf(xs + 4 * b) - rdf(xs + 4 * a), sz = rdf(zs + 4 * b) - rdf(zs + 4 * a);
        float step = sqrtf(sx * sx + sz * sz) / 8.0f;
        if (!(step > 0.05f) || !(step < 50.0f)) continue;
        float gap = dk * step, f = gap / dist; /* (+: the rival ahead) */
        if (f > 1) f = 1;
        if (f < -1) f = -1;
        float k = -f * frac * (float)dt; /* (ahead: a little less ground; behind: a little more) */
        wrf(car + 0x14, p[0] + v[0] * k), wrf(car + 0x18, p[1] + v[1] * k), wrf(car + 0x1C, p[2] + v[2] * k);
        if (said < 3 || ticks % 600 == 0) said++, fprintf(stderr, "xbrt: rival pace: rival %u is %.0f m %s at %.0f m/s: its pace %+.1f%%\n", i, gap < 0 ? -gap : gap, gap < 0 ? "behind" : "ahead", sp, -f * frac * 100);
    }
}
