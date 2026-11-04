/* Achievements (the user's, 2026-11-02). Watched from the race (rt_ach_tick, from rt_career_tick
 * with rt_gil held) and a few hooks (drift results, time trial and Catch-Up places, F12), kept in
 * achievements.txt beside forza.ini (XBRT_ACHIEVEMENTS names another file; the game's saves are
 * never touched), shown as a banner when one is earned (glover.c) and listed in F1's Achievements
 * tab.
 *
 * From the race: the player's racer (the racer list at 0x58DAA0, type +0x14 0), its car (+0xA0:
 * velocity +0x44..+0x4C, m/s), its timing (+0xC0: +0x9C laps done, -1 on the grid; +0xA0 the race's
 * clock; +0x98 the off-track penalty, seconds, growing as it is earned), its place (+0xBC) and its
 * finish (+0x1B8, low byte, set when its run ends); the track from the file the game loaded
 * (rt_loading_track). */
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "rt.h"

typedef struct {
    const char *id, *name, *desc;
    int goal;
} Ach;

static const Ach ach[] = {
    {"first_win", "First Victory", "Win a race against other cars.", 1},
    {"podiums", "Podium Regular", "Finish in the top three 10 times.", 10},
    {"wins25", "Champion", "Win 25 races.", 25},
    {"clean_win", "Clean Sweep", "Win a race with no off-track penalty.", 1},
    {"comeback", "Comeback Kid", "Win after running last at the end of lap 1.", 1},
    {"ton", "Ton Up", "Reach 100 mph.", 1},
    {"double_ton", "Double Ton", "Reach 200 mph.", 1},
    {"v240", "Beyond 240", "Reach 240 mph.", 1},
    {"drift10k", "Sideways", "Score 10,000 points in a drift event.", 1},
    {"drift_win", "Drift King", "Take 1st place in a drift event.", 1},
    {"tt_gold", "Gold Standard", "Earn gold in a career time trial.", 1},
    {"catchup", "Caught You", "Win a Catch-Up Challenge.", 1},
    {"fuji", "Fuji Pilgrim", "Complete a lap of Fuji Speedway.", 1},
    {"tracks10", "Globetrotter", "Complete a lap on 10 different tracks.", 10},
    {"laps100", "Lap Counter", "Complete 100 laps.", 100},
    {"miles500", "Marathon", "Drive 500 miles in races.", 500},
    {"shots25", "Shutterbug", "Take 25 screenshots (F12).", 25},
};
#define NACH (int)(sizeof ach / sizeof ach[0])
#define MAXTRACKS 64

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static int loaded, prog[NACH];
static long long when[NACH]; /* unix time earned, 0 not yet */
static double miles;
static char tracks[MAXTRACKS][48];
static int ntracks;
static char banner[64];
static uint64_t banner_until;

static const char *path(void) {
    const char *p = getenv("XBRT_ACHIEVEMENTS");
    return p && *p ? p : "achievements.txt";
}

static void load(void) {
    if (loaded) return;
    loaded = 1;
    FILE *f = fopen(path(), "r");
    if (!f) return;
    char line[256], a[64];
    long long t;
    int v;
    double d;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#') continue;
        if (sscanf(line, "track %47s", a) == 1 && ntracks < MAXTRACKS) snprintf(tracks[ntracks++], sizeof tracks[0], "%s", a);
        else if (sscanf(line, "miles %lf", &d) == 1) miles = d;
        else if (sscanf(line, "%63s %d %lld", a, &v, &t) == 3)
            for (int i = 0; i < NACH; i++)
                if (!strcmp(ach[i].id, a)) prog[i] = v, when[i] = t;
    }
    fclose(f);
}

static void save(void) {
    FILE *f = fopen(path(), "w");
    if (!f) return;
    fprintf(f, "# Forza Motorsport PC port achievements: id, progress, when earned (unix time, 0 not yet)\n");
    for (int i = 0; i < NACH; i++) fprintf(f, "%s %d %lld\n", ach[i].id, prog[i], when[i]);
    fprintf(f, "miles %.3f\n", miles);
    for (int i = 0; i < ntracks; i++) fprintf(f, "track %s\n", tracks[i]);
    fclose(f);
}

static int find(const char *id) {
    for (int i = 0; i < NACH; i++)
        if (!strcmp(ach[i].id, id)) return i;
    return -1;
}

/* Progress set to at least v (mu held); earned once it reaches the goal. 1 if it changed. */
static int reach(const char *id, int v) {
    int i = find(id);
    if (i < 0 || prog[i] >= v) return 0;
    prog[i] = v > ach[i].goal ? ach[i].goal : v;
    if (prog[i] >= ach[i].goal && !when[i]) {
        when[i] = (long long)time(NULL);
        snprintf(banner, sizeof banner, "%s", ach[i].name);
        banner_until = rt_now_100ns() + 60000000;
        fprintf(stderr, "xbrt: achievement earned: %s\n", ach[i].name);
    }
    return 1;
}
static int add(const char *id, int by) {
    int i = find(id);
    return i >= 0 && reach(id, prog[i] + by);
}

void rt_ach_add(const char *id, int by) {
    pthread_mutex_lock(&mu);
    load();
    if (add(id, by)) save();
    pthread_mutex_unlock(&mu);
}

void rt_ach_reach(const char *id, int v) {
    pthread_mutex_lock(&mu);
    load();
    if (reach(id, v)) save();
    pthread_mutex_unlock(&mu);
}

/* For F1's list and the banner (glover.c). */
int rt_ach_count(void) { return NACH; }
void rt_ach_get(int i, const char **name, const char **desc, int *progress, int *goal, int *earned) {
    pthread_mutex_lock(&mu);
    load();
    *name = ach[i].name, *desc = ach[i].desc, *progress = prog[i], *goal = ach[i].goal, *earned = when[i] != 0;
    if (!strcmp(ach[i].id, "miles500")) *progress = (int)miles > ach[i].goal ? ach[i].goal : (int)miles;
    pthread_mutex_unlock(&mu);
}
const char *rt_ach_banner(void) { return banner_until && rt_now_100ns() < banner_until ? banner : NULL; }

static float rdf(uint32_t a) {
    uint32_t b = xb_rd32(a);
    float f;
    memcpy(&f, &b, 4);
    return f;
}

/* With rt_gil held, from rt_career_tick: the race watched. */
void rt_ach_tick(void) {
    static uint32_t racer;
    static int32_t lap_was;
    static float clock_was, pen0;
    static uint32_t done_was, lap1_place, field;
    static int dirty;
    static uint64_t saved_at;
    if (!xb_rd32(0x592984)) { racer = 0; return; }
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), r = 0;
    if (!arr || arr >= RT_USER_LIMIT || n > 16) return;
    for (uint32_t k = 0; k < n && !r; k++) {
        uint32_t x = xb_rd32(arr + 4 * k);
        if (x && x < RT_USER_LIMIT && xb_rd32(x + 0x14) == 0) r = x;
    }
    uint32_t car = r ? xb_rd32(r + 0xA0) : 0, timing = r ? xb_rd32(r + 0xC0) : 0;
    if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) return;
    int32_t lap = (int32_t)xb_rd32(timing + 0x9C);
    float clock = rdf(timing + 0xA0);
    uint32_t done = xb_rd32(r + 0x1B8) & 0xFF;
    if (r != racer) { /* a new race (a restart makes the racers again) */
        racer = r, lap_was = lap, clock_was = clock, pen0 = rdf(timing + 0x98), done_was = done, lap1_place = 0, field = n;
        return;
    }
    pthread_mutex_lock(&mu);
    load();
    float vx = rdf(car + 0x44), vy = rdf(car + 0x48), vz = rdf(car + 0x4C), mph = sqrtf(vx * vx + vy * vy + vz * vz) * 2.23694f;
    if (lap >= 0 && !done) {
        if (mph >= 100) reach("ton", 1);
        if (mph >= 200) reach("double_ton", 1);
        if (mph >= 240) reach("v240", 1);
        double dt = clock - clock_was;
        if (dt > 0 && dt < 0.5) miles += mph * dt / 3600.0, dirty = 1;
        int m = (int)miles;
        if (m > prog[find("miles500")]) reach("miles500", m);
    }
    clock_was = clock;
    if (lap > lap_was && lap >= 1) { /* a lap completed */
        add("laps100", lap - lap_was);
        const char *t = rt_loading_track();
        if (t && *t) {
            int seen = 0;
            for (int i = 0; i < ntracks; i++) seen |= !strcasecmp(tracks[i], t);
            if (!seen && ntracks < MAXTRACKS) snprintf(tracks[ntracks++], sizeof tracks[0], "%s", t);
            reach("tracks10", ntracks);
            if (strstr(t, "Fuji")) reach("fuji", 1);
        }
        if (lap == 1) lap1_place = xb_rd32(r + 0xBC);
        dirty = 1;
    }
    lap_was = lap;
    uint32_t ev = xb_rd32(xb_rd32(0x592984) + 0x318), laps = ev && ev < RT_USER_LIMIT ? xb_rd32(ev + 0x24) : 0;
    if (done && !done_was && laps && laps < 100 && lap < (int32_t)laps) done_was = done; /* (quit, not finished: nothing counts) */
    if (done && !done_was) { /* the finish: the event's laps done (ev +0x24) */
        uint32_t place = xb_rd32(r + 0xBC);
        int clean = rdf(timing + 0x98) <= pen0 + 0.001f;
        fprintf(stderr, "xbrt: achievements: finished %u of %u (lap 1: %u), %s\n", place, field, lap1_place, clean ? "clean" : "penalties");
        if (field >= 2 && place >= 1 && place <= 3) add("podiums", 1);
        if (field >= 2 && place == 1) {
            reach("first_win", 1);
            add("wins25", 1);
            if (clean) reach("clean_win", 1);
            if (field >= 4 && lap1_place == field) reach("comeback", 1);
            if (rt_catchup_event()) reach("catchup", 1); /* (the event's: cu_active ends seconds in, so it never counted) */
        }
        if (rt_tt_running() && place == 1) reach("tt_gold", 1);
        dirty = 1;
    }
    done_was = done;
    uint64_t now = rt_now_100ns();
    if (dirty && now - saved_at > 300000000) save(), dirty = 0, saved_at = now; /* (every 30 s at most mid-race; a finish below) */
    if (done && dirty) save(), dirty = 0, saved_at = now;
    pthread_mutex_unlock(&mu);
}
