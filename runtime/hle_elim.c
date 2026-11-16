/* Eliminator events (the user's, 15 Nov: "let's do an eliminator event where every lap, last place is eliminated"):
 * the events listed in <mods>/eliminator.txt (a line "events <ordinal> ..."; tools/eliminator.py writes it and gives
 * each race one lap fewer than it has cars, so the last lap is a duel).
 *
 *  - A round a lap: once all but one of the racers still in have finished lap L (their lap count, timing +0x9C, at L:
 *    0 as they first cross the line from the grid), the one that has not is out; two over the line in the same tick,
 *    the one behind (the less of the race reached, timing +0x78).
 *  - A rival out: its run finished as the game finishes one (hle_kaizo.c's way: the progress at 1.0, the lap count at
 *    the event's), and its car taken off the road: held still far under it, so those left are the ones racing
 *    (XBRT_ELIM_PARK=0: left to drive on).
 *  - The player out: the race ends there, in the place it held (8th of 8 in the first round, 2nd in the last).
 *  - The last one in has won: the player's run finished at once, 1st.
 *  - Places: those out by the round they went in (the first out last), those in by the game's own order, set after
 *    the game's ranking and before a finished racer's place is recorded (hle_career.c), so the results and the
 *    winnings go by them.
 *
 * XBRT_ELIM_TEST=1: any race of three or more (testing, an Arcade race). */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "xbrt.h"

#define EL_MAX 16
#define EL_EVENTS 32
#define PARK_DEPTH 300.0f

extern char rt_toast_text[64];
extern volatile uint64_t rt_toast_until;

static uint32_t events[EL_EVENTS];
static int nevents;
static pthread_once_t once = PTHREAD_ONCE_INIT;

static void load(void) {
    char path[1200], line[512];
    snprintf(path, sizeof path, "%s/eliminator.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        if (strncmp(line, "events", 6)) continue;
        char *p = line + 6, *end;
        for (;;) {
            unsigned long v = strtoul(p, &end, 10);
            if (end == p || nevents >= EL_EVENTS) break;
            events[nevents++] = (uint32_t)v, p = end;
        }
    }
    fclose(f);
    fprintf(stderr, "xbrt: eliminator events: %d from %s\n", nevents, path);
}

static float rdf(uint32_t a) { uint32_t v = xb_rd32(a); float f; memcpy(&f, &v, 4); return f; }
static void wrf(uint32_t a, float f) { uint32_t v; memcpy(&v, &f, 4); xb_wr32(a, v); }
static double rdd(uint32_t a) { uint64_t v = (uint64_t)xb_rd32(a) | (uint64_t)xb_rd32(a + 4) << 32; double d; memcpy(&d, &v, 8); return d; }

static void say(const char *msg, int seconds) {
    snprintf(rt_toast_text, sizeof rt_toast_text, "%s", msg);
    rt_toast_until = rt_now_100ns() + (uint64_t)seconds * 10000000ull;
}

static struct {
    uint32_t race, racer0; unsigned serial;
    int on, n;                 /* n: the racers as the race began */
    uint32_t r[EL_MAX];        /* the racers, in the list's order */
    int out[EL_MAX];           /* 0 in; else the round it went out in (1 the first) */
    float park[EL_MAX][3];     /* where an eliminated rival's car is held */
    int rounds;                /* those out so far */
    int me_out, won;           /* the player's own end */
    uint32_t me_place;         /* the place the player's run ended in */
    uint64_t warned_at;
} e;

static int listed(void) {
    static int test = -1;
    if (test < 0) test = getenv("XBRT_ELIM_TEST") && atoi(getenv("XBRT_ELIM_TEST"));
    if (test) return 1;
    pthread_once(&once, load);
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    if (!nevents || !ev || ev >= RT_USER_LIMIT) return 0;
    uint32_t ordinal = xb_rd32(ev + 0x10);
    for (int i = 0; i < nevents; i++)
        if (events[i] == ordinal) return 1;
    return 0;
}

/* hle_kaizo.c's finish: the progress at 1.0 (every tick until the racer is done) and the lap count at the event's. */
static void finish(uint32_t timing) {
    double one = 1.0;
    uint64_t v;
    memcpy(&v, &one, 8);
    for (uint32_t o = 0x70; o <= 0x78; o += 8) xb_wr32(timing + o, (uint32_t)v), xb_wr32(timing + o + 4, (uint32_t)(v >> 32));
    uint32_t race = xb_rd32(0x592984), ev = race ? xb_rd32(race + 0x318) : 0, laps = ev && ev < RT_USER_LIMIT ? xb_rd32(ev + 0x24) : 0;
    if (laps && laps < 100 && (int32_t)xb_rd32(timing + 0x9C) < (int32_t)laps) xb_wr32(timing + 0x9C, laps);
}

static int slot_of(uint32_t racer) {
    for (int i = 0; i < e.n; i++)
        if (e.r[i] == racer) return i;
    return -1;
}

/* An Eliminator race running (the Mayhem and Kaizo codes keep out of the way of it by this). */
int rt_elim_on(void) { return e.on && xb_rd32(0x592984) == e.race; }

/* The racers' places (after the game's ranking, hle_career.c): those in by the game's order, then those out, the
 * last out first. */
void rt_elim_places(void) {
    if (!rt_elim_on()) return;
    uint32_t arr = xb_rd32(0x58DAA0 + 4), n = xb_rd32(0x58DAA0 + 0x10);
    if (!arr || arr >= RT_USER_LIMIT || (int)n != e.n) return;
    int in = e.n - e.rounds;
    for (int i = 0; i < e.n; i++) {
        uint32_t r = e.r[i], place;
        if (xb_rd32(arr + 4 * (uint32_t)i) != r) return; /* (the list changed: not ours any more) */
        if (e.out[i]) place = (uint32_t)(e.n - e.out[i] + 1);
        else {
            place = 1;
            uint32_t mine = xb_rd32(r + 0xBC);
            for (int j = 0; j < e.n; j++)
                if (j != i && !e.out[j]) {
                    uint32_t theirs = xb_rd32(e.r[j] + 0xBC);
                    place += theirs < mine || (theirs == mine && j < i);
                }
            if ((int)place > in) place = (uint32_t)in;
        }
        if (xb_rd32(r + 0xBC) != place) xb_wr32(r + 0xBC, place);
    }
}

/* A racer about to be recorded as over the line (hle_career.c's f_000B4AA0): its place put right first. */
void rt_elim_place(uint32_t racer) {
    if (!rt_elim_on()) return;
    int i = slot_of(racer);
    if (i < 0) return;
    uint32_t place = 0;
    if (e.out[i]) place = (uint32_t)(e.n - e.out[i] + 1);
    else if (xb_rd32(racer + 0x14) == 0 && e.won) place = 1;
    if (place && xb_rd32(racer + 0xBC) != place) {
        fprintf(stderr, "xbrt: eliminator: a racer%s recorded %u (the game's place for it %u)\n", xb_rd32(racer + 0x14) == 0 ? " (the player)" : "", place, xb_rd32(racer + 0xBC));
        xb_wr32(racer + 0xBC, place);
    }
}

/* With rt_gil held, from rt_career_tick. */
void rt_elim_tick(void) {
    uint32_t race = xb_rd32(0x592984);
    if (!race) { e.on = 0, e.race = 0; return; }
    uint32_t arr = xb_rd32(0x58DAA0 + 4), n = xb_rd32(0x58DAA0 + 0x10);
    if (!arr || arr >= RT_USER_LIMIT || n < 3 || n > EL_MAX) { e.on = 0; return; }
    unsigned serial;
    int state = rt_qr_music(&serial); /* 1 racing, 2 paused or over, 3 the grid */
    uint32_t r0 = xb_rd32(arr);
    int me = -1;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (!r || r >= RT_USER_LIMIT) return;
        if (xb_rd32(r + 0x14) == 0 && me < 0) me = (int)i;
    }
    if (me < 0) return;
    /* a new race, or a restart (the grid again with something already decided) */
    if (race != e.race || r0 != e.racer0 || serial != e.serial || (int)n != e.n || (state == 3 && (e.rounds || e.me_out || e.won))) {
        int was = e.on && e.rounds;
        memset(&e, 0, sizeof e);
        e.race = race, e.racer0 = r0, e.serial = serial, e.n = (int)n;
        for (uint32_t i = 0; i < n; i++) e.r[i] = xb_rd32(arr + 4 * i);
        int rt_qr_mayhem_grid(void);
        e.on = listed() && !rt_qr_mayhem() && !rt_qr_mayhem_grid();
        if (e.on) fprintf(stderr, "xbrt: eliminator: this race, %u cars%s\n", n, was ? " (a restart: all in again)" : "");
    }
    if (!e.on) {
        /* (the event's record comes after the race: looked at again until the race is under way) */
        if (state == 3 && listed()) e.race = 0;
        return;
    }
    static int park = -1, spare = -1; /* XBRT_ELIM_TEST=2: the player spared, the last rival goes (testing the rounds to the win) */
    if (spare < 0) spare = getenv("XBRT_ELIM_TEST") && atoi(getenv("XBRT_ELIM_TEST")) == 2;
    if (park < 0) park = !(getenv("XBRT_ELIM_PARK") && !atoi(getenv("XBRT_ELIM_PARK")));
    /* those out: finished, and held off the road */
    for (int i = 0; i < e.n; i++) {
        if (!e.out[i]) continue;
        uint32_t r = e.r[i], t = xb_rd32(r + 0xC0), car = xb_rd32(r + 0xA0);
        if (!t || t >= RT_USER_LIMIT) continue;
        if (!(xb_rd32(r + 0x1B8) & 0xFF)) finish(t);
        if (i != me && park && car && car < RT_USER_LIMIT) {
            for (uint32_t k = 0; k < 3; k++) wrf(car + 0x14 + 4 * k, e.park[i][k]), wrf(car + 0x44 + 4 * k, 0);
        }
    }
    if (e.won && !(xb_rd32(e.r[me] + 0x1B8) & 0xFF)) finish(xb_rd32(e.r[me] + 0xC0));
    if (e.me_out || e.won) return; /* (the player's run is over: nothing more to judge) */
    if (state != 1) return;
    int in = e.n - e.rounds;
    if (in < 2) return;
    int32_t round = e.rounds + 1;
    int over = 0, last = -1;
    double last_prog = 1e30;
    for (int i = 0; i < e.n; i++) {
        if (e.out[i]) continue;
        uint32_t t = xb_rd32(e.r[i] + 0xC0);
        if (!t || t >= RT_USER_LIMIT) return;
        int32_t lap = (int32_t)xb_rd32(t + 0x9C);
        double prog = rdd(t + 0x78);
        if (lap >= round) over++;
        /* the one to go: not over the line this round before one that is; among equals, the less of the race reached */
        double key = (lap >= round ? 1000.0 : 0.0) + prog;
        if (spare && i == me) continue; /* (testing: the player never the one to go) */
        if (key < last_prog) last_prog = key, last = i;
    }
    /* the player last of those in: told, every 10 s */
    {
        uint32_t mine = xb_rd32(e.r[me] + 0xBC);
        uint64_t now = rt_now_100ns();
        int32_t mylap = (int32_t)xb_rd32(xb_rd32(e.r[me] + 0xC0) + 0x9C);
        if ((int)mine >= in && mylap >= 0 && over < in - 1 && now - e.warned_at > 100000000ull) {
            e.warned_at = now;
            say("LAST PLACE: OUT AT THE LINE", 3);
        }
    }
    if (over < in - 1 || last < 0) return;
    /* the round is decided */
    e.rounds++;
    e.out[last] = e.rounds;
    uint32_t r = e.r[last], car = xb_rd32(r + 0xA0), t = xb_rd32(r + 0xC0);
    char msg[64];
    if (last == me) {
        e.me_out = 1, e.me_place = (uint32_t)in;
        finish(t);
        snprintf(msg, sizeof msg, "ELIMINATED: PLACE %d OF %d", in, e.n);
        say(msg, 6);
        fprintf(stderr, "xbrt: eliminator: round %d, the player out, place %d of %d: the race ends\n", round, in, e.n);
        return;
    }
    if (car && car < RT_USER_LIMIT)
        e.park[last][0] = rdf(car + 0x14), e.park[last][1] = rdf(car + 0x18) - PARK_DEPTH, e.park[last][2] = rdf(car + 0x1C);
    finish(t);
    fprintf(stderr, "xbrt: eliminator: round %d, racer %d out (place %d of %d), %d left\n", round, last, in, e.n, in - 1);
    if (in - 1 == 1) {
        e.won = 1;
        finish(xb_rd32(e.r[me] + 0xC0));
        say("ELIMINATOR WON!", 6);
        fprintf(stderr, "xbrt: eliminator: the player is the last one in: won\n");
    } else {
        snprintf(msg, sizeof msg, "RIVAL ELIMINATED: %d LEFT", in - 1);
        say(msg, 4);
    }
}
