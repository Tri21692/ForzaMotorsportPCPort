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
#include <math.h>
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

/* Each time trial's best time (ms), kept in <mods>/timetrial_best.txt ("ordinal ms" lines), not in the
 * saves: shown under its targets (rt_tt_best). */
static uint32_t tt_best[MAX_TT];

static void tt_best_path(char *path, size_t n) {
    snprintf(path, n, "%s/timetrial_best.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
}

static void tt_best_load(void) {
    static int loaded;
    if (loaded) return;
    loaded = 1;
    char path[1200], line[64];
    tt_best_path(path, sizeof path);
    FILE *f = fopen(path, "r");
    if (!f) return;
    uint32_t o, ms;
    while (fgets(line, sizeof line, f))
        if (sscanf(line, "%u %u", &o, &ms) == 2)
            for (int i = 0; i < ntt; i++)
                if (tt[i].ordinal == o) tt_best[i] = ms;
    fclose(f);
}

static void tt_best_note(int i, uint32_t ms) {
    tt_best_load();
    if (tt_best[i] && tt_best[i] <= ms) return;
    tt_best[i] = ms;
    char path[1200];
    tt_best_path(path, sizeof path);
    FILE *f = fopen(path, "w");
    if (!f) return;
    for (int k = 0; k < ntt; k++)
        if (tt_best[k]) fprintf(f, "%u %u\n", tt[k].ordinal, tt_best[k]);
    fclose(f);
}

uint32_t rt_tt_best(void) {
    int i = tt_event();
    if (i < 0) return 0;
    tt_best_load();
    return tt_best[i];
}

static void tt_place(uint32_t racer) {
    int i = tt_event();
    uint32_t ms, laps;
    if (i < 0 || !tt_clock(racer, &ms, &laps) || laps < 1 || !ms) return;
    tt_best_note(i, ms);
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
    if (found && list == 0x58DAA0) rt_drift_place(found);
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

/* With rt_gil held, from rt_career_tick: during a career time trial, the player's lap, checkpoints
 * and progress logged as they change (and every 10 s), and the race ended if the game counted the
 * lap but not the finish. The race ends a racer's run once its progress (timing +0x70, a double:
 * laps begun less one plus the lap's fraction, the most it has reached; 0x5C2D0) reaches 1.0
 * (0xAE616, [0x486E7C]): the racer is marked done (+0x1B8) and the race is over once all are
 * (0xAE70D-0xAE719). Some time trials ran on past the line (why not yet seen): once the lap count
 * (+0x9C) has reached the event's laps (+0x24) and the racer is still not done 1 s later, its
 * progress (+0x70 and +0x78) is set to 1.0. */
static void tt_watch(void) {
    static uint32_t racer_was, ordinal_was;
    static int32_t lap_was, cp_was;
    static uint32_t done_was;
    static uint64_t next_log, counted_at;
    int i = tt_event();
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), racer = 0;
    if (i < 0 || !arr || arr >= RT_USER_LIMIT || n > 16) { racer_was = 0; return; }
    for (uint32_t k = 0; k < n && !racer; k++) {
        uint32_t r = xb_rd32(arr + 4 * k);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) racer = r;
    }
    uint32_t timing = racer ? xb_rd32(racer + 0xC0) : 0;
    if (!timing || timing >= RT_USER_LIMIT) return;
    uint32_t ev = xb_rd32(xb_rd32(0x592984) + 0x318), laps = xb_rd32(ev + 0x24), done = xb_rd32(racer + 0x1B8) & 0xFF;
    int32_t lap = (int32_t)xb_rd32(timing + 0x9C), cp = (int32_t)xb_rd32(timing + 0x88);
    uint64_t v = (uint64_t)xb_rd32(timing + 0x70) | (uint64_t)xb_rd32(timing + 0x74) << 32;
    double progress;
    memcpy(&progress, &v, 8);
    uint32_t ms = 0, l;
    tt_clock(racer, &ms, &l);
    uint64_t now = rt_now_100ns();
    if (racer != racer_was || tt[i].ordinal != ordinal_was) /* a new run (a restart makes the racers again) */
        racer_was = racer, ordinal_was = tt[i].ordinal, lap_was = cp_was = -9, done_was = 9, next_log = 0, counted_at = 0;
    if (lap != lap_was || cp != cp_was || done != done_was || now >= next_log) {
        fprintf(stderr, "xbrt: time trial %u: lap %d of %u, checkpoints %d, progress %.3f, clock %u.%03u s, done %u (racers %u)\n",
                tt[i].ordinal, lap, laps, cp, progress, ms / 1000, ms % 1000, done, n);
        lap_was = lap, cp_was = cp, done_was = done, next_log = now + 100000000;
    }
    if (done || !laps || laps > 99 || lap < (int32_t)laps || progress >= 1.0) { counted_at = 0; return; }
    if (!counted_at) { counted_at = now; return; }
    if (now - counted_at < 10000000) return;
    double one = 1.0;
    memcpy(&v, &one, 8);
    for (uint32_t o = 0x70; o <= 0x78; o += 8) xb_wr32(timing + o, (uint32_t)v), xb_wr32(timing + o + 4, (uint32_t)(v >> 32));
    fprintf(stderr, "xbrt: time trial %u: the lap counted (%d of %u) but the race ran on, at progress %.3f: progress set to 1, to finish\n",
            tt[i].ordinal, lap, laps, progress);
    counted_at = 0;
}

/* Catch-up events (<mods>/catchup.txt, a line per event: "ordinal fraction points", points the
 * event's track's racing line's count, its AI geometry's iLength): the opponent starts
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
 * no event of the disc has (seven or none), and its track by the line's points: the line of that
 * many points gives the fraction (else the first line). The opponent's
 * car is told by its racer's record (+0xA0 holds the car), not by its place: the game gives the
 * player place 1 or 2 (moving place 2 put the player half a lap on and left the opponent). */
#define MAX_CU 32
static struct { uint32_t ordinal; float frac; int32_t points; } cu[MAX_CU]; /* points: its track's racing line's (0 any) */
static int ncu;
static pthread_once_t cu_once = PTHREAD_ONCE_INIT;
static volatile int cu_active; /* a catch-up race is on: rt_career_tick counts the opponent's lap as begun */
static uint32_t cu_player_car, cu_grid[12]; /* the player's car and its pose as the grid left it (+0x14: x y z, the 3x3 turn) */
static volatile int cu_grid_ok;

static void cu_load(void) {
    char path[1200];
    snprintf(path, sizeof path, "%s/catchup.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[256];
    while (ncu < MAX_CU && fgets(line, sizeof line, f)) { /* "ordinal fraction [points]" */
        cu[ncu].points = 0;
        if (sscanf(line, "%u %f %d", &cu[ncu].ordinal, &cu[ncu].frac, &cu[ncu].points) >= 2 && cu[ncu].frac > 0 && cu[ncu].frac < 1) ncu++;
    }
    fclose(f);
    fprintf(stderr, "xbrt: catch-up events: %d from %s\n", ncu, path);
}

void orig_f_000410E0(XbCtx *c); /* the game's own (wraps.txt) */
void f_000410E0(XbCtx *c) {
    pthread_once(&cu_once, cu_load);
    int32_t place = (int32_t)xb_rd32(c->esp + 4);
    uint32_t car = c->ecx;
    if (ncu) {
        /* a race against one opponent: the racer list holds the player (type 0) and one AI car; the
         * car being placed is the opponent's when the AI racer's record holds it (+0xA0) */
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), people = 0, mine = 0;
        for (uint32_t i = 0; i < n && n == 2 && arr; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            if (!r || r >= RT_USER_LIMIT) continue;
            people += xb_rd32(r + 0x14) == 0;
            mine |= xb_rd32(r + 0x14) != 0 && xb_rd32(r + 0xA0) == car;
        }
        uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
        int32_t points = line ? (int32_t)xb_rd32(line + 8) : 0;
        /* the event's line by its track's racing line (the grid is laid before the race has its event: the
         * user's head starts differ by track); no line of the track's length, no head start (the Rivals
         * duels are two cars too), unless the lines give no lengths (catchup.txt's first form: the first) */
        int k = -1, any_points = 0;
        for (int j = 0; j < ncu; j++) any_points |= cu[j].points > 0;
        for (int j = 0; j < ncu; j++) if (cu[j].points == points) { k = j; break; }
        if (k < 0 && !any_points && ncu) k = 0;
        if (n == 2 && people == 1 && mine && points > 0 && k >= 0) {
            cu_active = 1;
            int32_t pct = (int32_t)(cu[k].frac * 100.0f + 0.5f), moved = -(pct < 2 ? 2 : pct > 99 ? 99 : pct); /* -1 is the pole's */
            xb_wr32(c->esp + 4, (uint32_t)moved);
            fprintf(stderr, "xbrt: catch-up: the opponent's grid place %d -> %d, %.2f of the lap (%d points) ahead\n", place, moved, cu[k].frac, points);
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
    orig_f_000410E0(c);
    if (ncu) { /* the player's car as placed: its pose, for rt_career_tick to keep it on a restart */
        uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
        for (uint32_t i = 0; i < n && n == 2 && arr; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0 && xb_rd32(r + 0xA0) == car) {
                /* facing along the racing line where it stands: on a restart the game turned it as the
                 * last placing before it, the opponent's a quarter of a lap on (the user faced a wall).
                 * The car's turn (+0x20, 3x3 by rows): the third row forward, the first the forward
                 * turned to the right (z, -x), the second up, as the game lays a car on the grid */
                uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
                uint32_t np = line ? xb_rd32(line + 8) : 0, xs = line ? xb_rd32(line + 0x30) : 0, zs = line ? xb_rd32(line + 0x44) : 0;
                if (np > 2 && np < 100000 && xs && zs) {
                    float cx, cz, best = 1e30f, f[2] = {0, 0}, rot[9];
                    uint32_t v = xb_rd32(car + 0x14), k = 0;
                    memcpy(&cx, &v, 4); v = xb_rd32(car + 0x1C); memcpy(&cz, &v, 4);
                    for (uint32_t j = 0; j < np; j++) {
                        float px, pz;
                        v = xb_rd32(xs + 4 * j); memcpy(&px, &v, 4); v = xb_rd32(zs + 4 * j); memcpy(&pz, &v, 4);
                        float d2 = (px - cx) * (px - cx) + (pz - cz) * (pz - cz);
                        if (d2 < best) best = d2, k = j;
                    }
                    float ax, az, bx, bz;
                    v = xb_rd32(xs + 4 * k); memcpy(&ax, &v, 4); v = xb_rd32(zs + 4 * k); memcpy(&az, &v, 4);
                    v = xb_rd32(xs + 4 * ((k + 2) % np)); memcpy(&bx, &v, 4); v = xb_rd32(zs + 4 * ((k + 2) % np)); memcpy(&bz, &v, 4);
                    float len = sqrtf((bx - ax) * (bx - ax) + (bz - az) * (bz - az));
                    for (int j = 0; j < 9; j++) { v = xb_rd32(car + 0x20 + 4 * j); memcpy(&rot[j], &v, 4); }
                    if (len > 0.1f && best < 25.0f) {
                        f[0] = (bx - ax) / len, f[1] = (bz - az) / len;
                        if (rot[6] * f[0] + rot[8] * f[1] < 0.9f) { /* not along the line: turned */
                            float want[9] = {f[1], 0, -f[0], 0, 1, 0, f[0], 0, f[1]};
                            for (int j = 0; j < 9; j++) { memcpy(&v, &want[j], 4); xb_wr32(car + 0x20 + 4 * j, v); }
                            fprintf(stderr, "xbrt: catch-up: the player's car turned along the line (it faced %.2f %.2f, the line %.2f %.2f)\n", rot[6], rot[8], f[0], f[1]);
                        }
                    }
                }
                for (int k = 0; k < 12; k++) cu_grid[k] = xb_rd32(car + 0x14 + 4 * k);
                cu_player_car = car, cu_grid_ok = 1;
            }
        }
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
/* Track audits (2026-11-02, XBRT_TOUR=<seconds>[,<points>[,3]]): once the race is on, every that many seconds
 * the player's car is set down <points> (default 50, about 100 m) further along the track's racing line
 * ([0x5E1450]+4: +8 its points, +0x30/0x44/0x58 their x, z, y), facing along it (the grid's turn, as
 * f_000410E0 lays it), stopped: a lap of views for the screenshots without anyone driving. With ,3 each point
 * is shown three times, facing along the line, then to its left, then to its right (the woods beside it). */
static void tour_tick(void) {
    static double every = -1;
    static int step, views, view, k = -1;
    static uint64_t next;
    if (every < 0) {
        const char *e = getenv("XBRT_TOUR");
        every = e ? atof(e) : 0;
        step = e && strchr(e, ',') ? atoi(strchr(e, ',') + 1) : 50;
        if (step <= 0) step = 50;
        views = e && strchr(e, ',') && strchr(strchr(e, ',') + 1, ',') ? atoi(strchr(strchr(e, ',') + 1, ',') + 1) : 1;
        if (views != 3) views = 1;
    }
    if (every <= 0 || !xb_rd32(0x592984)) { k = -1, next = 0; return; }
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), car = 0;
    for (uint32_t i = 0; i < n && n <= 16 && arr && !car; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) car = xb_rd32(r + 0xA0);
    }
    uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
    uint32_t np = line ? xb_rd32(line + 8) : 0, xs = line ? xb_rd32(line + 0x30) : 0, zs = line ? xb_rd32(line + 0x44) : 0, ys = line ? xb_rd32(line + 0x58) : 0;
    if (!car || car >= RT_USER_LIMIT || np < 3 || np > 100000 || !xs || !zs || !ys) return;
    uint64_t now = rt_now_100ns();
    if (!next) { next = now + (uint64_t)(every * 1e7); return; }
    if (now < next) return;
    next = now + (uint64_t)(every * 1e7);
    if (k < 0) k = 0, view = 0;
    else if (++view >= views) view = 0, k = (k + step) % (int)np;
    float p[3], q[2], v;
    uint32_t w;
    w = xb_rd32(xs + 4 * k); memcpy(&p[0], &w, 4); w = xb_rd32(ys + 4 * k); memcpy(&p[1], &w, 4); w = xb_rd32(zs + 4 * k); memcpy(&p[2], &w, 4);
    w = xb_rd32(xs + 4 * ((k + 3) % np)); memcpy(&q[0], &w, 4); w = xb_rd32(zs + 4 * ((k + 3) % np)); memcpy(&q[1], &w, 4);
    float fx = q[0] - p[0], fz = q[1] - p[2], len = sqrtf(fx * fx + fz * fz);
    if (len < 0.1f) return;
    fx /= len, fz /= len;
    if (view) { /* 1: to the left, 2: to the right (the grid's turn: right is (z, -x)) */
        float t = fx;
        if (view == 1) fx = -fz, fz = t;
        else fx = fz, fz = -t;
    }
    float pose[12] = {p[0], p[1] + 0.5f, p[2], fz, 0, -fx, 0, 1, 0, fx, 0, fz};
    for (int j = 0; j < 12; j++) memcpy(&w, &pose[j], 4), xb_wr32(car + 0x14 + 4 * j, w);
    v = 0, memcpy(&w, &v, 4);
    for (int j = 0; j < 3; j++) xb_wr32(car + 0x44 + 4 * j, w);
    fprintf(stderr, "xbrt: tour: point %d of %u view %d: %.1f %.1f %.1f\n", k, np, view, p[0], p[1], p[2]);
}

void rt_career_tick(void) {
    tour_tick();
    rt_ach_tick();
    rt_qr_tick();
    rt_qr_test_tick();
    if (getenv("XBRT_EVENT_DUMP")) { /* debugging (Quick Race): the running event's record, once each, its words */
        static uint32_t told;
        uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
        if (ev && ev < RT_USER_LIMIT && ev != told) {
            told = ev;
            fprintf(stderr, "xbrt: event record at %08x (game %08x):", ev, g);
            for (uint32_t o = 0; o < 0x200; o += 4) fprintf(stderr, "%s+%02x=%x", o % 32 ? " " : "\n  ", o, xb_rd32(ev + o));
            fprintf(stderr, "\n");
            uint32_t p0 = xb_rd32(ev);
            if (p0 && p0 < RT_USER_LIMIT) { /* what its first word points at (the field?) */
                fprintf(stderr, "xbrt: event record's +00 -> %08x:", p0);
                for (uint32_t o = 0; o < 0x100; o += 4) fprintf(stderr, "%s+%02x=%x", o % 32 ? " " : "\n  ", o, xb_rd32(p0 + o));
                fprintf(stderr, "\n");
            }
        }
    }
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
            if (getenv("XBRT_RACE_DUMP")[0] == '2') /* =2: each racer's place, line point, and its timing record's words */
                for (uint32_t i = 0; i < n && i < 8; i++) {
                    uint32_t r = xb_rd32(arr + 4 * i), t = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0;
                    if (!r || r >= RT_USER_LIMIT) continue;
                    fprintf(stderr, "xbrt: racer %u type %u place %u point %u frac %08x timing:", i, xb_rd32(r + 0x14), xb_rd32(r + 0xBC), xb_rd32(r + 0x43C), xb_rd32(r + 0x440));
                    for (uint32_t o = 0; t && t < RT_USER_LIMIT && o < 0x200; o += 4) fprintf(stderr, " %08x", xb_rd32(t + o));
                    fprintf(stderr, "\n");
                }
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
    if (xb_rd32(0x592984)) tt_watch();
    rt_drift_tick();
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
    /* the player's car kept facing as the grid placed it while it stands there: on a restart the game
     * turned it to the heading of the grid's last placing, the opponent's (the user's car faced away
     * from the start line). Placing it again (the game's own call) froze the game; its turn is put
     * back instead, until it moves or its lap begins */
    uint32_t pcar = xb_rd32(xb_rd32(arr + 4 * me) + 0xA0);
    if (cu_grid_ok && pcar == cu_player_car && (int32_t)lap[me] == -1) {
        float p[3], g[3];
        for (int k = 0; k < 3; k++) { uint32_t v = xb_rd32(pcar + 0x14 + 4 * k); memcpy(&p[k], &v, 4); memcpy(&g[k], &cu_grid[k], 4); }
        if ((p[0] - g[0]) * (p[0] - g[0]) + (p[2] - g[2]) * (p[2] - g[2]) < 0.25f) {
            int off = 0;
            for (int k = 3; k < 12; k++) {
                float a, b;
                uint32_t v = xb_rd32(pcar + 0x14 + 4 * k);
                memcpy(&a, &v, 4); memcpy(&b, &cu_grid[k], 4);
                if (a - b > 0.05f || b - a > 0.05f) off = 1;
            }
            if (off) {
                for (int k = 3; k < 12; k++) xb_wr32(pcar + 0x14 + 4 * k, cu_grid[k]);
                static uint64_t said;
                if (rt_now_100ns() - said > 50000000) said = rt_now_100ns(), fprintf(stderr, "xbrt: catch-up: the player's car turned back to face the grid\n");
            }
        }
    }
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
        /* and its checkpoints: the start line's counted as passed (+0x88 those passed in the race, +0x8c
         * this lap's; -1 on the grid, 0 past the line). The race ranks by them first: started past the
         * line, the opponent never passed one, and the player showed 1st until it finished. Its head
         * start (a quarter of the lap) is short of the next (the player's first came at half the lap
         * at Laguna Seca). */
        if ((int32_t)xb_rd32(timing[ai] + 0x88) < 0) xb_wr32(timing[ai] + 0x88, 0), xb_wr32(timing[ai] + 0x8C, 0);
        /* the race's own measure, what it ranks by: +0x70 (and +0x78) a double, laps begun less one plus
         * the lap's fraction (+0x80), added to as the car goes. The opponent's ran -0.75 to -0.14 (a
         * lap behind its fraction) and the player, at 0.01 to 0.65, showed 1st: one lap added. */
        for (uint32_t o = 0x70; o <= 0x78; o += 8) {
            uint64_t v = (uint64_t)xb_rd32(timing[ai] + o) | (uint64_t)xb_rd32(timing[ai] + o + 4) << 32;
            double d;
            memcpy(&d, &v, 8);
            if (d < 0.0 && d > -1.0) {
                d += 1.0;
                memcpy(&v, &d, 8);
                xb_wr32(timing[ai] + o, (uint32_t)v), xb_wr32(timing[ai] + o + 4, (uint32_t)(v >> 32));
            }
        }
        fprintf(stderr, "xbrt: catch-up: the opponent's lap counted as begun, the start line passed\n");
    }
    /* done once the opponent's lap is begun and the player's too (off the grid); the dump goes on */
    if (lap[ai] != 0xFFFFFFFFu && (int32_t)lap[me] >= 0 && !getenv("XBRT_CATCHUP_DUMP")) cu_active = 0;
}

/* For the race HUD (glover.c, on the GPU's thread: reads only): in a Catch-Up race, how far the
 * player leads the opponent, in metres (negative: behind), from both racers' progress (timing
 * +0x70: laps begun less one plus the lap's fraction) and the lap's length (its racing line's
 * points, about 2 m apart). */
int rt_catchup_active(void) { return cu_active; }
int rt_tt_running(void) { return tt_event() >= 0; }

int rt_catchup_hud(int *metres) {
    pthread_once(&cu_once, cu_load);
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    if (!ncu || !ev || ev >= RT_USER_LIMIT) return 0;
    uint32_t ordinal = xb_rd32(ev + 0x10);
    int k = -1;
    for (int i = 0; i < ncu; i++)
        if (cu[i].ordinal == ordinal) k = i;
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (k < 0 || n != 2 || !arr || arr >= RT_USER_LIMIT || cu[k].points <= 0) return 0;
    double prog[2] = {0, 0};
    int me = -1;
    for (uint32_t i = 0; i < 2; i++) {
        uint32_t r = xb_rd32(arr + 4 * i), t = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0;
        if (!t || t >= RT_USER_LIMIT) return 0;
        uint64_t v = (uint64_t)xb_rd32(t + 0x70) | (uint64_t)xb_rd32(t + 0x74) << 32;
        memcpy(&prog[i], &v, 8);
        if (xb_rd32(r + 0x14) == 0) me = (int)i;
    }
    if (me < 0 || !(prog[0] > -2 && prog[0] < 50 && prog[1] > -2 && prog[1] < 50)) return 0;
    *metres = (int)lround((prog[me] - prog[1 - me]) * cu[k].points * 2.0);
    return 1;
}
