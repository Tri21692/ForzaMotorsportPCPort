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
    c->esp += 8; /* ret 4 */
}
