/* Achievements (the user's, 2026-11-02). Watched from the race (rt_ach_tick, from rt_career_tick
 * with rt_gil held) and a few hooks (drift results, time trial and Catch-Up places, F12), kept in
 * achievements.txt beside forza.ini (XBRT_ACHIEVEMENTS names another file; the game's saves are
 * never touched), shown as a banner when one is earned (glover.c) and listed in F1's Achievements
 * tab.
 *
 * From the race: the player's racer (the racer list at 0x58DAA0, type +0x14 0), its car (+0xA0:
 * velocity +0x44..+0x4C, m/s), its timing (+0xC0: +0x9C laps done, -1 on the grid; +0x94 the race's
 * clock, running from the countdown and standing while paused; +0xA0 the last lap's time, written as
 * the lap is done (18 Nov: it was read as the race's clock, so the miles never counted: the user's
 * 0.000 after 100 laps); +0x98 the off-track penalty, seconds, growing as it is earned), its place (+0xBC) and its
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
    /* (the user's, 17 Nov, as the Touge was opened to every car: "make an achievement for if you beat it with a
     * D-Spec car": both of its runs won in one, each counted once: the "touge <event>" lines of the file) */
    {"touge_dspec", "Touge Purist", "Win both Midnight Touge runs in a D-Spec car.", 2},
    /* (the user's, 18 Nov: "a few very specific achievements that are somewhat difficult to get. A suggestion is to
     * beat Timo Bernhard's WR on Nordschleife with the vanilla/OG car list only": 5:19.546, the Porsche 919 Evo's lap
     * of 29 June 2018, round the real 20,832 m: 233.8 km/h. The game's Nurburgring is 28,167 m round (its AI
     * waypoints, 14,084 of 2 m; its other tracks are their real length to a percent or three), so 5:19.546 here would
     * is 317 km/h, past any car of the disc's; his pace over the game's lap would be 7:12.05 (the career time
     * trial's silver in a P1 car is 7:11.9). Told so, the user: "No, keep Timo's original WR", and
     * then: "Just Lauda's, Bernhard's is impossible and I didn't realize": Niki Lauda's 6:58.6 of 1975 (the Ferrari
     * 312T, the first lap under seven minutes), 242 km/h over the game's lap: at the edge for a P1 car.
     * A lap of the Nurburgring under it with no off-track penalty, in a
     * car of the disc's (not one of <mods>/addon_cars.txt), not in Mayhem (its boost); and five more of the kind.
     * And (the user's, the same day): "the WR must be in Career and in a regular race": the race a career event's
     * (the event record at the race's +0x318, its leaderboard at +0x0C not the arcade events' 4000: an arcade race
     * has a record too, the first test's "a career event" on an arcade Tsukuba) against rivals, not a time trial, a
     * Catch-Up, a drift or a Mayhem event.
     * Testing: XBRT_ACH_RING=<track folder>,<seconds>[,any] has another track and time stand in (any: an arcade
     * race counted too). */
    {"ring_record", "Ringmeister", "Career race, original car: a clean Nurburgring lap under Lauda's 6:58.6.", 1},
    {"ring_clean", "Green Hell, Clean", "Win a Nurburgring race with no off-track penalty.", 1},
    {"flat_out", "Flat Out", "Hold 200 mph for 30 seconds without dropping below it.", 1},
    {"untouchable", "Untouchable", "Win 5 races in a row with no off-track penalty.", 5},
    /* (the user's, 18 Nov: "do tiers for Kaizo Mode achievements. Kaizo Novice, Amateur, Professional, Master, and
     * King (all original events). You decide on the events needed": the career's own events, the disc's (ordinals
     * 0-80 and 117-350: 315 of them, 81-116 the online ones), each counted once when won with Kaizo Mode on: the
     * "kaizo <event>" lines of the file. They take Kaizo Ace's place (3 wins of any race).
     * Testing: XBRT_ACH_KAIZO=1 has Kaizo taken as on, 2 any finish counted as well.) */
    {"kaizo1", "Kaizo Novice", "Win 5 different original career events in Kaizo Mode.", 5},
    {"kaizo2", "Kaizo Amateur", "Win 25 different original career events in Kaizo Mode.", 25},
    {"kaizo3", "Kaizo Professional", "Win 75 different original career events in Kaizo Mode.", 75},
    {"kaizo4", "Kaizo Master", "Win 150 different original career events in Kaizo Mode.", 150},
    {"kaizo5", "Kaizo King", "Win all 315 original career events in Kaizo Mode.", 315},
    {"last_gasp", "Last Gasp", "Win from 4th or lower at the start of the final lap.", 1},
};
#define NACH (int)(sizeof ach / sizeof ach[0])
#define MAXTRACKS 64

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static int loaded, prog[NACH];
static long long when[NACH]; /* unix time earned, 0 not yet */
static double miles;
static char tracks[MAXTRACKS][48];
static int ntracks;
static uint32_t touge[8]; /* the matched events (the Touge's runs) won in a D-Spec car */
static int ntouge;
static int streak; /* clean wins in a row (Untouchable): "streak <n>" */
#define KZ_EVENTS 351
#define KZ_ORIGINAL(o) ((o) <= 80 || ((o) >= 117 && (o) < KZ_EVENTS))
static unsigned char kz[KZ_EVENTS]; /* the original career events won in Kaizo Mode: "kaizo <event>" */
static int nkz;
#define RING_RECORD 418.6f /* Niki Lauda, Ferrari 312T, 1975 */
int rt_addon_car(uint32_t ordinal); /* hle_unlock.c */
int rt_kaizo_setting(void);
int rt_qr_mayhem(void);
int rt_rival_event(void);
int rt_rival_dspec(void);
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
    /* Each line by its first word, whole (18 Nov: read with "track %47s" and the like, the line "tracks10 10 ..." was
     * a track named "s10", one more each time the file was read: the user's Globetrotter earned by ten starts of the
     * game, the real tracks pushed out of the list; "kaizo1 0 0" would have been event 1 won). */
    while (fgets(line, sizeof line, f)) {
        char key[64], rest[192] = "";
        if (line[0] == '#' || sscanf(line, "%63s %191[^\n]", key, rest) < 1) continue;
        if (!strcmp(key, "track")) {
            int seen = !strcmp(rest, "s10") || !*rest; /* (the old misreading's) */
            for (int k = 0; k < ntracks; k++) seen |= !strcasecmp(tracks[k], rest);
            if (!seen && ntracks < MAXTRACKS && sscanf(rest, "%47s", a) == 1) snprintf(tracks[ntracks++], sizeof tracks[0], "%s", a);
        } else if (!strcmp(key, "miles")) { if (sscanf(rest, "%lf", &d) == 1) miles = d; }
        else if (!strcmp(key, "touge")) { if (sscanf(rest, "%d", &v) == 1 && ntouge < 8) touge[ntouge++] = (uint32_t)v; }
        else if (!strcmp(key, "streak")) { if (sscanf(rest, "%d", &v) == 1) streak = v; }
        else if (!strcmp(key, "kaizo")) { if (sscanf(rest, "%d", &v) == 1 && v >= 0 && v < KZ_EVENTS && KZ_ORIGINAL(v) && !kz[v]) kz[v] = 1, nkz++; }
        else if (sscanf(rest, "%d %lld", &v, &t) == 2)
            for (int k = 0; k < NACH; k++)
                if (!strcmp(ach[k].id, key)) prog[k] = v, when[k] = t;
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
    for (int i = 0; i < ntouge; i++) fprintf(f, "touge %u\n", touge[i]);
    fprintf(f, "streak %d\n", streak);
    for (int i = 0; i < KZ_EVENTS; i++) if (kz[i]) fprintf(f, "kaizo %d\n", i);
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
    static float clock_was, pen0, lap_pen, fast_for;
    static uint32_t done_was, lap1_place, field, last_place;
    static int fin_was;
    static int dirty;
    static uint64_t saved_at;
    if (!xb_rd32(0x592984)) { racer = 0; return; }
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), r = 0;
    if (!arr || arr >= RT_USER_LIMIT || n > 32) return; /* (32: Mayhem's big field, 17) */
    for (uint32_t k = 0; k < n && !r; k++) {
        uint32_t x = xb_rd32(arr + 4 * k);
        if (x && x < RT_USER_LIMIT && xb_rd32(x + 0x14) == 0) r = x;
    }
    uint32_t car = r ? xb_rd32(r + 0xA0) : 0, timing = r ? xb_rd32(r + 0xC0) : 0;
    if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) return;
    int32_t lap = (int32_t)xb_rd32(timing + 0x9C);
    float clock = rdf(timing + 0x94), lap_time = rdf(timing + 0xA0);
    uint32_t done = xb_rd32(r + 0x1B8) & 0xFF;
    if (r != racer) { /* a new race (a restart makes the racers again) */
        racer = r, lap_was = lap, clock_was = clock, pen0 = rdf(timing + 0x98), done_was = done, lap1_place = 0, field = n;
        lap_pen = pen0, fast_for = 0, last_place = 0, fin_was = 1; /* (set right below, from this race's laps) */
        {
            uint32_t ev0 = xb_rd32(xb_rd32(0x592984) + 0x318), laps0 = ev0 && ev0 < RT_USER_LIMIT ? xb_rd32(ev0 + 0x24) : 0;
            fin_was = (laps0 && laps0 < 100 && lap >= (int32_t)laps0) || done;
        }
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
        if (mph < 200 || rt_qr_mayhem()) fast_for = 0; /* (Flat Out: 30 s of the race's clock at 200 mph and over) */
        else if (dt > 0 && dt < 0.5 && (fast_for += (float)dt) >= 30) reach("flat_out", 1);
        int m = (int)miles;
        if (m > prog[find("miles500")]) reach("miles500", m);
    }
    clock_was = clock;
    uint32_t ev = xb_rd32(xb_rd32(0x592984) + 0x318), laps = ev && ev < RT_USER_LIMIT ? xb_rd32(ev + 0x24) : 0;
    static uint32_t ev_told;
    if (ev && ev < RT_USER_LIMIT && lap >= 0 && ev_told != racer) {
        ev_told = racer;
        fprintf(stderr, "xbrt: achievements: the race's event %u, leaderboard %u (%s), track %u, %u laps, %u cars\n", xb_rd32(ev + 0x10), xb_rd32(ev + 0x0C),
                xb_rd32(ev + 0x0C) == 4000 ? "arcade" : "career", xb_rd32(ev + 0x20), laps, field);
    }
    if (lap > lap_was && lap_was < 0) lap_pen = rdf(timing + 0x98); /* (off the grid) */
    if (lap > lap_was && lap >= 1) { /* a lap completed */
        const char *tk = rt_loading_track();
        uint32_t init = xb_rd32(r + 0xB4), ord = init && init < RT_USER_LIMIT ? xb_rd32(init) : ~0u;
        float took = lap_time, pen = rdf(timing + 0x98);
        const char *ring = "Nurburgring", *te = getenv("XBRT_ACH_RING");
        float record = RING_RECORD;
        static char ring_test[48];
        if (te && sscanf(te, "%47[^,],%f", ring_test, &record) == 2) ring = ring_test;
        if (lap == lap_was + 1 && tk && !strcasecmp(tk, ring)) {
            int clean = pen <= lap_pen + 0.001f, og = ord < 1024 && !rt_addon_car(ord);
            RtDriftHud dh;
            int career = ev && ev < RT_USER_LIMIT && xb_rd32(ev + 0x0C) != 4000, regular = field >= 2 && !rt_tt_running() && !rt_catchup_event() && !rt_drift_hud(&dh);
            if (te && strstr(te, ",any")) career = 1;
            fprintf(stderr, "xbrt: achievements: a %s lap of %.3f s (the record %.3f), %s, car %u %s, %s, %s%s\n", ring, took, record,
                    clean ? "clean" : "with penalties", ord, og ? "of the original list" : "an add-on", career ? "a career event" : "not the career",
                    regular ? "a race" : "not a regular race", rt_qr_mayhem() ? ", in Mayhem" : "");
            if (took > 30 && took < record && clean && og && career && regular && !rt_qr_mayhem()) reach("ring_record", 1);
        }
        lap_pen = pen;
        if (laps >= 2 && laps < 100 && lap == (int32_t)laps - 1) last_place = xb_rd32(r + 0xBC); /* the final lap begins */
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
    /* The finish: the event's laps done (ev +0x24). (18 Nov: it waited for the racer's flag at +0x1B8 alone, which
     * a race's end does not set while this runs: no win, podium or clean finish had ever counted, the user's file all
     * 0 after weeks of wins, and two career races finished in tests without the line below. The flag with the laps
     * short is a race quit: nothing counts.) */
    int known = laps && laps < 100, fin = known ? lap >= (int32_t)laps : done != 0;
    if (fin && !fin_was) {
        uint32_t place = xb_rd32(r + 0xBC);
        int clean = rdf(timing + 0x98) <= pen0 + 0.001f;
        fprintf(stderr, "xbrt: achievements: finished %u of %u (lap 1: %u), %s\n", place, field, lap1_place, clean ? "clean" : "penalties");
        if (field >= 2 && place >= 1 && place <= 3) add("podiums", 1);
        {   /* the Kaizo tiers: an original career event won with Kaizo Mode on */
            const char *kt = getenv("XBRT_ACH_KAIZO");
            int kt_ = kt ? atoi(kt) : 0;
            RtDriftHud dh;
            uint32_t o = ev && ev < RT_USER_LIMIT && xb_rd32(ev + 0x0C) != 4000 ? xb_rd32(ev + 0x10) : ~0u;
            if (field >= 2 && (place == 1 || kt_ == 2) && (rt_kaizo_setting() || kt_) && !rt_qr_mayhem() && !rt_drift_hud(&dh) && o < KZ_EVENTS && KZ_ORIGINAL(o)) {
                if (!kz[o]) kz[o] = 1, nkz++;
                fprintf(stderr, "xbrt: achievements: career event %u won in Kaizo Mode: %d of the 315 original events\n", o, nkz);
                reach("kaizo1", nkz), reach("kaizo2", nkz), reach("kaizo3", nkz), reach("kaizo4", nkz), reach("kaizo5", nkz);
            }
        }
        if (field >= 2) { /* Untouchable: clean wins in a row; any other finish against rivals starts over */
            streak = place == 1 && clean ? streak + 1 : 0;
            if (streak) reach("untouchable", streak);
        }
        if (field >= 2 && place == 1) {
            reach("first_win", 1);
            add("wins25", 1);
            if (clean) reach("clean_win", 1);
            if (field >= 4 && lap1_place == field) reach("comeback", 1);
            const char *tk = rt_loading_track();
            if (clean && tk && !strcasecmp(tk, "Nurburgring") && !rt_qr_mayhem()) reach("ring_clean", 1);
            if (field >= 6 && last_place >= 4) reach("last_gasp", 1);
            if (ev && ev < RT_USER_LIMIT && rt_rival_event() && rt_rival_dspec()) { /* a Touge run won in a D-Spec car */
                uint32_t o = xb_rd32(ev + 0x10);
                int seen = 0;
                for (int i = 0; i < ntouge; i++) seen |= touge[i] == o;
                if (!seen && ntouge < 8) touge[ntouge++] = o;
                fprintf(stderr, "xbrt: achievements: Touge event %u won in a D-Spec car (%d of its runs so far)\n", o, ntouge);
                reach("touge_dspec", ntouge);
            }
            if (rt_catchup_event()) reach("catchup", 1); /* (the event's: cu_active ends seconds in, so it never counted) */
        }
        if (rt_tt_running() && place == 1) reach("tt_gold", 1);
        dirty = 1;
    }
    done_was = done, fin_was = fin;
    uint64_t now = rt_now_100ns();
    if (dirty && now - saved_at > 300000000) save(), dirty = 0, saved_at = now; /* (every 30 s at most mid-race; a finish below) */
    if (fin && dirty) save(), dirty = 0, saved_at = now;
    pthread_mutex_unlock(&mu);
}
