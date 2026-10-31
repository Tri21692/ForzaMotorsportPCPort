/* Career time trials placed by the clock (XBRT_CAREER_TIMETRIAL=1, with
 * tools/careertimetrial.py's events). Alone on the track a player always
 * finishes first; here a time trial's place comes from the lap time and
 * the event's three target times instead: under the first 1st, under the
 * second 2nd, under the third 3rd, else 4th.
 *
 * The game asks for the local player's racer through 0x755D0 (the racer
 * list at 0x58DAA0, a pointer per racer at +4, the count at +0x10; type
 * +0x14, 0 a person), and everything after the finish reads the
 * place from what it returns: the results table (0x1A5BFB), the podium
 * flag (0x184407) and the scoring, medal and rewards (0x17E270, the medal
 * byte per event ordinal at 0x77B60). So the place is set there, once the
 * lap is done: racer +0xBC the place (1 first), +0xC0 its timing (+0x9C
 * laps done, +0xA0 the race's time, +0x94 the best lap, seconds); the
 * event is [0x592984]+0x318 (its ordinal at +0x10), set during the race.
 *
 * The targets: <mods>/timetrial.txt, a line per event, "ordinal gold silver
 * bronze" in milliseconds (careertimetrial.py writes it).
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "funcs.h"
#include "rt.h"

#define MAX_TT 128
static struct { uint32_t ordinal, ms[3]; } tt[MAX_TT];
static int ntt;
static pthread_once_t tt_once = PTHREAD_ONCE_INIT; /* read once, by whichever thread asks first (the game's or the GPU's) */

static void tt_load(void) {
    if (!getenv("XBRT_CAREER_TIMETRIAL") || !atoi(getenv("XBRT_CAREER_TIMETRIAL"))) return;
    char path[1200];
    snprintf(path, sizeof path, "%s/timetrial.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[256];
    while (ntt < MAX_TT && fgets(line, sizeof line, f))
        if (sscanf(line, "%u %u %u %u", &tt[ntt].ordinal, &tt[ntt].ms[0], &tt[ntt].ms[1], &tt[ntt].ms[2]) == 4) ntt++;
    fclose(f);
    fprintf(stderr, "xbrt: career time trials: %d target times from %s\n", ntt, path);
}

/* The running event's targets (the table's entry), or -1 when it is not a time trial. */
static int tt_event(void) {
    pthread_once(&tt_once, tt_load);
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    if (!ntt || !ev || ev >= RT_USER_LIMIT) return -1;
    uint32_t ordinal = xb_rd32(ev + 0x10);
    for (int i = 0; i < ntt; i++)
        if (tt[i].ordinal == ordinal) return i;
    static uint32_t told; /* debugging the next test: an event that is not one */
    if (ordinal != told) told = ordinal, fprintf(stderr, "xbrt: career event %u (event at %08x): not a time trial\n", ordinal, ev);
    return -1;
}

/* The racer's time so far and laps done ([racer+0xC0]: +0xA0 the race's seconds, +0x9C laps). */
static int tt_clock(uint32_t racer, uint32_t *ms, uint32_t *laps) {
    uint32_t timing = racer ? xb_rd32(racer + 0xC0) : 0;
    if (!timing || timing >= RT_USER_LIMIT) return 0;
    uint32_t bits = xb_rd32(timing + 0xA0);
    float s;
    memcpy(&s, &bits, 4);
    if (!(s >= 0 && s < 36000)) return 0;
    *ms = (uint32_t)(s * 1000.0f + 0.5f), *laps = xb_rd32(timing + 0x9C);
    return 1;
}

static void tt_place(uint32_t racer) {
    int i = tt_event();
    uint32_t ms, laps;
    if (i < 0 || !tt_clock(racer, &ms, &laps) || laps < 1 || !ms) return;
    uint32_t place = 4;
    for (int k = 2; k >= 0; k--)
        if (ms <= tt[i].ms[k]) place = (uint32_t)k + 1;
    static uint32_t logged_ordinal, logged_ms;
    if (logged_ordinal != tt[i].ordinal || logged_ms != ms) {
        logged_ordinal = tt[i].ordinal, logged_ms = ms;
        fprintf(stderr, "xbrt: time trial %u: %u.%03u s (targets %u, %u, %u ms): place %u (the game had %u)\n", tt[i].ordinal, ms / 1000,
                ms % 1000, tt[i].ms[0], tt[i].ms[1], tt[i].ms[2], place, xb_rd32(racer + 0xBC));
    }
    if (xb_rd32(racer + 0xBC) != place) xb_wr32(racer + 0xBC, place);
}

/* For the race HUD (glover.c, on the GPU's thread: reads only): during a career time trial, its
 * three targets, the player's time so far and whether the lap is done. */
int rt_tt_hud(uint32_t targets[3], uint32_t *elapsed, int *done) {
    int i = tt_event();
    if (i < 0) return 0;
    uint32_t list = 0x58DAA0, count = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), racer = 0;
    if (!arr || arr >= RT_USER_LIMIT || count > 16) return 0;
    for (uint32_t k = 0; k < count && !racer; k++) {
        uint32_t r = xb_rd32(arr + k * 4);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) racer = r;
    }
    uint32_t laps;
    if (!tt_clock(racer, elapsed, &laps)) return 0;
    memcpy(targets, tt[i].ms, sizeof tt[i].ms);
    *done = laps >= 1;
    return 1;
}

/* Racer *RacerList::LocalPlayer(int n) (thiscall, ret 4): the game's, instruction for instruction. */
void f_000755D0(XbCtx *c) {
    uint32_t list = c->ecx, count = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), want = xb_rd32(c->esp + 4);
    uint32_t found = 0, k = 0, i = 0;
    for (; i < count; i++) {
        uint32_t r = xb_rd32(arr + i * 4), type = xb_rd32(r + 0x14);
        c->ecx = type;
        if (type == 0) { /* (the original also tests 3, after a jump that leaves only 0 to 2) */
            if (k == want) { found = r; break; }
            k++;
        }
    }
    if (count) c->edx = arr + i * 4; /* as the original leaves them */
    c->eax = found;
    if (found && list == 0x58DAA0) tt_place(found);
    if (list == 0x58DAA0 && count == 2 && getenv("XBRT_CATCHUP_DUMP")) { /* debugging: both racers' laps and times, every 5 s */
        static uint64_t next;
        uint64_t now = rt_now_100ns();
        if (now >= next) {
            next = now + 50000000;
            fprintf(stderr, "xbrt: racers:");
            for (uint32_t i = 0; i < count; i++) {
                uint32_t r = xb_rd32(arr + i * 4), t = r ? xb_rd32(r + 0xC0) : 0;
                float s = 0;
                if (t && t < RT_USER_LIMIT) { uint32_t b = xb_rd32(t + 0xA0); memcpy(&s, &b, 4); }
                fprintf(stderr, " [type %u place %u laps %u time %.1f]", xb_rd32(r + 0x14), xb_rd32(r + 0xBC), t && t < RT_USER_LIMIT ? xb_rd32(t + 0x9C) : 0, s);
            }
            fprintf(stderr, "\n");
        }
    }
    c->esp += 8; /* ret 4 */
}

/* Catch-up events (<mods>/catchup.txt, a line per event: "ordinal fraction"): the opponent starts
 * that fraction of a lap ahead of the pole. CCar::ResetPositionForGrid (0x410E0, thiscall, the
 * grid place as its argument) puts a car on the track's racing line, when the track has one
 * ([0x5E1450] the track, +8 set; [+4] the line: +8 its points, about 2 m apart from the start
 * line, +0x30/0x44/0x58 their x, z, y), at point (10 - place) * 4: the pole at 36, each place
 * after it 4 points back. A place below -1 is the game's own way to put a car part of the way
 * round: -place percent of the line's points on (0x41313; [0x486f10] 0.01). The opponent's place
 * is changed to minus the fraction's percent. (A place far below -1 taken as grid places, -226,
 * read past the line's end: the car went to near the map's origin and drove on from wherever that
 * met the track, at Laguna Seca 30% of the lap on.) The grid is laid before the race has its
 * event ([0x592984] still 0), so the race is told by its field: the player and one AI car, which
 * no event of the disc has (seven or none), and the first line's fraction is used. The opponent's
 * car is told by its racer's record (+0xA0 holds the car), not by its place: the game gives the
 * player place 1 or 2 (moving place 2 put the player half a lap on and left the opponent). */
#define MAX_CU 32
static struct { uint32_t ordinal; float frac; } cu[MAX_CU];
static int ncu;
static pthread_once_t cu_once = PTHREAD_ONCE_INIT;
static volatile int cu_active; /* a catch-up race is on: rt_career_tick counts the opponent's lap as begun */

static void cu_load(void) {
    char path[1200];
    snprintf(path, sizeof path, "%s/catchup.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[256];
    while (ncu < MAX_CU && fgets(line, sizeof line, f))
        if (sscanf(line, "%u %f", &cu[ncu].ordinal, &cu[ncu].frac) == 2 && cu[ncu].frac > 0 && cu[ncu].frac < 1) ncu++;
    fclose(f);
    fprintf(stderr, "xbrt: catch-up events: %d from %s\n", ncu, path);
}

void orig_f_000410E0(XbCtx *c); /* the game's own (wraps.txt) */
void f_000410E0(XbCtx *c) {
    pthread_once(&cu_once, cu_load);
    int32_t place = (int32_t)xb_rd32(c->esp + 4);
    uint32_t car = c->ecx;
    static uint32_t player_car; /* the player's car and grid place, as last placed */
    static int32_t player_place;
    int moved_opponent = 0;
    if (ncu) {
        /* a race against one opponent: the racer list holds the player (type 0) and one AI car; the
         * car being placed is the opponent's when the AI racer's record holds it (+0xA0) */
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), people = 0, mine = 0;
        for (uint32_t i = 0; i < n && n == 2 && arr; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            if (!r || r >= RT_USER_LIMIT) continue;
            people += xb_rd32(r + 0x14) == 0;
            mine |= xb_rd32(r + 0x14) != 0 && xb_rd32(r + 0xA0) == car;
            if (xb_rd32(r + 0x14) == 0 && xb_rd32(r + 0xA0) == car) player_car = car, player_place = place;
        }
        uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
        int32_t points = line ? (int32_t)xb_rd32(line + 8) : 0;
        if (n == 2 && people == 1 && mine && points > 0) {
            cu_active = 1;
            int32_t pct = (int32_t)(cu[0].frac * 100.0f + 0.5f), moved = -(pct < 2 ? 2 : pct > 99 ? 99 : pct); /* -1 is the pole's */
            xb_wr32(c->esp + 4, (uint32_t)moved);
            moved_opponent = 1;
            fprintf(stderr, "xbrt: catch-up: the opponent's grid place %d -> %d, %.2f of the lap (%d points) ahead\n", place, moved, cu[0].frac, points);
        }
    }
    if (ncu && getenv("XBRT_CATCHUP_DUMP")) { /* debugging: which racer this car is (the racer whose record holds the car's address) */
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
        fprintf(stderr, "xbrt: grid: car %08x place %d;", car, place);
        for (uint32_t i = 0; i < n && i < 8 && arr; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            int at = -1;
            for (uint32_t o = 0; r && o < 0x400 && at < 0; o += 4)
                if (xb_rd32(r + o) == car) at = (int)o;
            fprintf(stderr, " racer %08x type %u holds it at %d;", r, r ? xb_rd32(r + 0x14) : 0, at);
        }
        fprintf(stderr, "\n");
    }
    uint32_t ret = xb_rd32(c->esp);
    orig_f_000410E0(c);
    int player_now = 0; /* (the car remembered still the player's: never one of an earlier race) */
    for (uint32_t i = 0, list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4); moved_opponent && arr && i < n && i < 16; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0 && xb_rd32(r + 0xA0) == player_car) player_now = 1;
    }
    if (moved_opponent && player_now && player_car != car) {
        /* and the player's car placed again, last: on a restart the game turned the player's car to
         * the heading of the grid's last placing, the opponent's half a lap on (the user's car faced
         * away from the start line); the game's own call again, its frame as the caller's (ret 4) */
        uint32_t ecx = c->ecx;
        c->esp -= 8;
        xb_wr32(c->esp, ret);
        xb_wr32(c->esp + 4, (uint32_t)player_place);
        c->ecx = player_car;
        orig_f_000410E0(c);
        c->ecx = ecx;
        fprintf(stderr, "xbrt: catch-up: the player's car placed again (place %d), its heading the grid's\n", player_place);
    }
    if (ncu && getenv("XBRT_CATCHUP_DUMP")) { /* debugging: the car's first floats after placing, to find its position */
        fprintf(stderr, "xbrt: placed car %08x (place %d):", car, place);
        for (uint32_t o = 0; o < 0x600; o += 4) {
            float f;
            uint32_t v = xb_rd32(car + o);
            memcpy(&f, &v, 4);
            if (f > 50.0f || f < -50.0f) if (f < 5000.0f && f > -5000.0f) fprintf(stderr, " +%x=%.1f", o, f);
        }
        fprintf(stderr, "\n");
    }
}

/* With rt_gil held, from the DPC thread's every pass. The opponent of a catch-up race starts past
 * the start line, so its lap count (racer +0xC0 -> +0x9C: -1 on the grid, 0 once the line is
 * crossed) stays -1 until it reaches the line half a lap on, and it would then have a whole lap
 * still to drive (seen: -1 to 0 on reaching it). 2 s after the race is under way ([0x592984] set;
 * the racers' own clocks start at the line), the opponent's lap is counted as begun, so its reaching
 * the line finishes its lap. */
void rt_career_tick(void) {
    if (getenv("XBRT_RACE_DUMP")) { /* debugging: every racer's type, lap and car position (+0x14 x, +0x1c z), every 5 s */
        static uint64_t next;
        uint64_t now = rt_now_100ns();
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
        if (now >= next && n && arr && xb_rd32(0x592984)) {
            next = now + 50000000;
            fprintf(stderr, "xbrt: race:");
            for (uint32_t i = 0; i < n && i < 8; i++) {
                uint32_t r = xb_rd32(arr + 4 * i), t = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0, car = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xA0) : 0;
                float x = 0, z = 0;
                if (car && car < RT_USER_LIMIT) { uint32_t v = xb_rd32(car + 0x14); memcpy(&x, &v, 4); v = xb_rd32(car + 0x1C); memcpy(&z, &v, 4); }
                fprintf(stderr, " [%u lap %d %.0f %.0f]", r ? xb_rd32(r + 0x14) : 9, t && t < RT_USER_LIMIT ? (int)xb_rd32(t + 0x9C) : -9, x, z);
            }
            fprintf(stderr, "\n");
        }
    }
    if (getenv("XBRT_POS_TRACE")) { /* debugging: the player's car (racer type 0) position, 20 times a second, as
                                       "seconds x y z" lines (where a car falls through the ground, and how) */
        static FILE *f;
        static uint64_t next, t0;
        uint64_t now = rt_now_100ns();
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
        if (!f) f = fopen(getenv("XBRT_POS_TRACE"), "w"), t0 = now;
        if (f && now >= next && n && n < 16 && arr && xb_rd32(0x592984)) {
            next = now + 500000;
            for (uint32_t i = 0; i < n; i++) {
                uint32_t r = xb_rd32(arr + 4 * i), car = r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0 ? xb_rd32(r + 0xA0) : 0;
                if (!car || car >= RT_USER_LIMIT) continue;
                float p[3];
                for (int k = 0; k < 3; k++) { uint32_t v = xb_rd32(car + 0x14 + 4 * k); memcpy(&p[k], &v, 4); }
                fprintf(f, "%.2f %.2f %.2f %.2f\n", (now - t0) / 1e7, p[0], p[1], p[2]);
                fflush(f);
                break;
            }
        }
    }
    if (!cu_active) return;
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (n != 2 || !arr) { cu_active = 0; return; }
    uint32_t lap[2] = {0, 0}, type[2], timing[2];
    for (uint32_t i = 0; i < 2; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        timing[i] = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0;
        type[i] = r ? xb_rd32(r + 0x14) : ~0u;
        if (!timing[i] || timing[i] >= RT_USER_LIMIT) return;
        lap[i] = xb_rd32(timing[i] + 0x9C);
    }
    int me = type[0] == 0 ? 0 : 1, ai = 1 - me;
    static uint64_t next;
    uint64_t now = rt_now_100ns();
    if (getenv("XBRT_CATCHUP_DUMP") && now >= next) {
        next = now + 50000000;
        fprintf(stderr, "xbrt: catch-up laps: player %d, opponent %d;", (int)lap[me], (int)lap[ai]);
        for (int i = 0; i < 2; i++) { /* debugging: each car's first words, to find its position */
            uint32_t car = xb_rd32(xb_rd32(arr + 4 * i) + 0xA0);
            fprintf(stderr, " %s:", i == me ? "player" : "opponent");
            for (uint32_t o = 0x10; car && car < RT_USER_LIMIT && o < 0x80; o += 4) {
                float f;
                uint32_t v = xb_rd32(car + o);
                memcpy(&f, &v, 4);
                fprintf(stderr, " %.1f", f);
            }
        }
        fprintf(stderr, "\n");
    }
    static uint64_t since;
    if (!xb_rd32(0x592984)) since = 0; /* the race (its event, [0x592984]) not under way yet */
    else if (!since) since = now;
    if (since && now - since > 20000000 && lap[ai] == 0xFFFFFFFFu) { /* 2 s into the race */
        xb_wr32(timing[ai] + 0x9C, 0);
        fprintf(stderr, "xbrt: catch-up: the opponent's lap counted as begun\n");
        if (!getenv("XBRT_CATCHUP_DUMP")) cu_active = 0; /* debugging: the dump goes on */
    }
}
