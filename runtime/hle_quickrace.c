/* Quick Race (the user's, 2026-11-02): in the Arcade Race menus X opens a menu (glover.c draws it,
 * like F1's) to pick a track, the number of opponents (2 to 7: one opponent is the Catch-Up event's),
 * the laps and modifiers; the Quick Race arcade event (tools/quickrace.py adds it) is then rewritten
 * in memory to that track, field and laps (rt_qr_apply), and the modifiers act in its races:
 *
 *   Takedowns   after Burnout 3, on a real touch (both cars jolted, under 5 m apart): a slam (from the
 *               side) throws a rival across the road, a shunt (from behind) punts it on, both turning it
 *               out of grip, and your car, heavier, keeps half the knock; a wall (blown up: thrown up,
 *               rolling), a stop or the road left within 3 s is a takedown (banner, count, half a nitro
 *               tank), its wreck back 60 m behind you and chasing hard (up to 15 m/s faster) till it is
 *               near; your car stopped or off the track for 3 s is set back on the racing line, rolling.
 *   Low Gravity the cars fall at 40% of the pull: long, floaty crests.
 *   Nitro       hold the right stick in (R3; N on the keyboard: Y is the game's look back) for a push along
 *               the car's heading, from a tank that fills again slowly.
 *   Slipstream  close behind a car (within 25 m, in line), a strong tow.
 *
 * From the race (rt_qr_tick, rt_gil held): the racers (0x58DAA0), each car's pose (+0x14: x y z, then the
 * 3x3 turn by rows, forward the third) and velocity (+0x44, m/s), the racing line ([0x5E1450]+4). The
 * modifiers act only in the Quick Race event once it is set (Series 1 - Race 1, by its name), or in every
 * race with XBRT_QR_ALWAYS=1 (testing). */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"

static float rdf(uint32_t a) {
    uint32_t b = xb_rd32(a);
    float f;
    memcpy(&f, &b, 4);
    return f;
}
static void wrf(uint32_t a, float f) {
    /* never a NaN or an infinity, nor a speed or place past any track's, into a car (the user's crash of 3 Nov: the
     * game's collision went round for good on NaNs in a car); one such refused said once */
    if (!(f > -20000.0f && f < 20000.0f)) {
        static int told;
        if (!told++) fprintf(stderr, "xbrt: quick race: a bad value (%g) not written at %08x\n", (double)f, a);
        return;
    }
    uint32_t b;
    memcpy(&b, &f, 4);
    xb_wr32(a, b);
}

volatile int rt_qr_mods = QR_TAKEDOWNS; /* the modifiers chosen (rt.h QR_*) */
#define MAXQE 8
static uint32_t qr_events[MAXQE];        /* the event's records in RAM (rt_qr_apply): more than one copy can be there */
static int nqe;
static uint32_t qr_event;                /* the first of them; 0 until Quick Race is set (and after Restore) */
#define QR_EVENT_NAME 3073               /* the arcade event Quick Race takes over: Series 1 - Race 1 */
static int takedowns, nitro_y;
static float tank = 1.0f;
static char note[48];
static uint64_t note_until;

static void say_for(const char *m, double secs) {
    snprintf(note, sizeof note, "%s", m);
    note_until = rt_now_100ns() + (uint64_t)(secs * 1e7);
}
static void say(const char *m) { say_for(m, 1.5); }
const char *rt_qr_note(void) { return note_until && rt_now_100ns() < note_until ? note : NULL; }

/* ---- Mayhem (the user's, 3 Nov): a career category of its own (tools/mayhemseries.py; first a secret code on
 * the event menus). <mods>/mayhem.txt names its events ("events <ordinal>..."): a race of one of them is Mayhem's:
 * takedowns always on, the rivals faster and driving at the player, the player able to be taken down too (hit hard
 * by a rival and then a wall or a stop within 3 s: slow motion on its own wreck, then back on the line, repaired),
 * the boost, the arcade handling and the cartoon look. XBRT_MAYHEM names another file; XBRT_MAYHEM_TEST=1 makes
 * any race Mayhem's (testing).
 *
 * Mayhem Moments (the user's): a takedown at a named place on a track ("moment <track> <x> <z> <radius> <top y
 * or -> <name>|<what to do>" lines: a place within the radius, and below that height if given; a name on more
 * lines, more places for it) is labelled with its name, and unlocks it: kept in <mods>/mayhem_moments.txt (a name
 * a line; never the save), shown lit in F1's Mayhem Moments page (glover.c) with its photograph. */
static int mayhem_race;
#define MM_MAX 16
#define MM_ZONES 16 /* (the user's, 7 Nov: Mother Trucker on every trailer of Pacific Shipyards: 10 places) */
static struct { int track, nz; float zone[MM_ZONES][4]; char name[40], todo[120]; int got; } mm[MM_MAX]; /* zone: x, z, radius, top y */
static struct { int track; float share; } mspread[32]; /* "spread <track> <percent>": the rivals over that much of the lap */
static int nmspread;
static int nmm, mm_loaded;
static int mm_prize; /* "prize <car ordinal>": the car for every Moment found (the user's, 7 Nov) */
static uint32_t mayhem_ev[32];
static int nmayhem_ev;
static char mm_flash[64]; /* the last Moment's banner, MAYHEM MOMENT! and its name */
static uint64_t mm_flash_until;
static int mm_flash_new; /* (unlocked by it: the banner says so) */
static const char *mods_dir(void) { return getenv("XBRT_MODS") && *getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods"; }
static void mayhem_load_once(void);
static pthread_once_t mm_once = PTHREAD_ONCE_INIT;
static void mayhem_load(void) { pthread_once(&mm_once, mayhem_load_once); } /* (F1's page on the GPU's thread too: once, whole) */
static void mayhem_load_once(void) {
    mm_loaded = 1;
    char path[512], line[512];
    const char *p = getenv("XBRT_MAYHEM");
    if (p && *p) snprintf(path, sizeof path, "%s", p);
    else snprintf(path, sizeof path, "%s/mayhem.txt", mods_dir());
    FILE *f = fopen(path, "r");
    while (f && fgets(line, sizeof line, f)) {
        if (!strncmp(line, "events", 6)) {
            char *s = line + 6, *e;
            for (unsigned long v; nmayhem_ev < 32 && (v = strtoul(s, &e, 10), e != s); s = e) mayhem_ev[nmayhem_ev++] = (uint32_t)v;
        } else if (!strncmp(line, "prize ", 6)) {
            mm_prize = atoi(line + 6);
        } else if (!strncmp(line, "spread ", 7) && nmspread < 32) {
            int track;
            float pct;
            if (sscanf(line + 7, "%d %f", &track, &pct) == 2 && pct > 0 && pct <= 100)
                mspread[nmspread].track = track, mspread[nmspread++].share = pct / 100.0f;
        } else if (!strncmp(line, "moment ", 7) && nmm < MM_MAX) {
            int n = 0, track;
            float x, z, r;
            char top[16];
            if (sscanf(line + 7, "%d %f %f %f %15s %n", &track, &x, &z, &r, top, &n) < 5 || !n) continue;
            char *t = line + 7 + n, *bar = strchr(t, '|');
            t[strcspn(t, "\r\n")] = 0;
            if (bar) *bar = 0;
            int k = 0;
            while (k < nmm && strcmp(mm[k].name, t)) k++; /* (a name seen: another place for it) */
            if (k == nmm) {
                memset(&mm[k], 0, sizeof mm[k]), mm[k].track = track, nmm++;
                snprintf(mm[k].name, sizeof mm[k].name, "%s", t);
                if (bar) snprintf(mm[k].todo, sizeof mm[k].todo, "%s", bar + 1);
            }
            if (mm[k].nz < MM_ZONES) {
                float *zn = mm[k].zone[mm[k].nz++];
                zn[0] = x, zn[1] = z, zn[2] = r, zn[3] = strcmp(top, "-") ? (float)atof(top) : 1e9f;
            }
        }
    }
    if (f) fclose(f);
    snprintf(path, sizeof path, "%s/mayhem_moments.txt", mods_dir());
    f = fopen(path, "r");
    while (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        for (int i = 0; i < nmm; i++) if (!strcmp(line, mm[i].name)) mm[i].got = 1;
    }
    if (f) fclose(f);
    fprintf(stderr, "xbrt: mayhem: %d events, %d moments from %s\n", nmayhem_ev, nmm, path);
}
int rt_mm_count(void) { mayhem_load(); return nmm; }
/* The share of the lap Mayhem's rivals are spread over on the race's track (hle_career.c's grid): mayhem.txt's
 * "spread <track> <percent>" (the user's, 7 Nov: "don't space out as much on Pacific/Fujimi, makes it impossible":
 * on their long laps the leaders began most of a lap ahead), else the whole lap. */
float rt_qr_mayhem_share(void) {
    mayhem_load();
    uint32_t race = xb_rd32(0x592984), ev = race ? xb_rd32(race + 0x318) : 0;
    int track = ev && ev < RT_USER_LIMIT ? (int)xb_rd32(ev + 0x20) : -1;
    const char *qt_ = getenv("XBRT_QR_TEST"), *cm = qt_ ? strchr(qt_, ',') : NULL;
    if (track < 0 && cm) track = atoi(cm + 1); /* (testing: an arcade race has no event record; XBRT_QR_TEST's track) */
    for (int i = 0; i < nmspread; i++)
        if (mspread[i].track == track) return mspread[i].share;
    return 1.0f;
}
void rt_mm_get(int i, const char **name, const char **todo, int *got) {
    mayhem_load();
    *name = mm[i].name, *todo = mm[i].todo, *got = mm[i].got;
}
const char *rt_mm_flash(void) { return mm_flash_until && rt_now_100ns() < mm_flash_until ? mm_flash : NULL; }
/* The banner's age in seconds (its flash and pop) and whether the Moment was new. */
float rt_mm_flash_age(int *is_new) {
    *is_new = mm_flash_new;
    return mm_flash_until ? (float)(5.0 - (double)(mm_flash_until - rt_now_100ns()) / 1e7) : 99.0f;
}
/* Whether (x, y, z) is in one of Moment i's places. */
static int mm_in(int i, float x, float y, float z) {
    for (int k = 0; k < mm[i].nz; k++) {
        const float *zn = mm[i].zone[k];
        if ((x - zn[0]) * (x - zn[0]) + (z - zn[1]) * (z - zn[1]) <= zn[2] * zn[2] && y < zn[3]) return 1;
    }
    return 0;
}
/* A takedown at (x, y, z) on the race's track: a Mayhem Moment's place? Its banner, and unlocked if new. 1 if one. */
static int mayhem_moment(float x, float y, float z) {
    uint32_t race = xb_rd32(0x592984), ev = race ? xb_rd32(race + 0x318) : 0;
    int track = ev && ev < RT_USER_LIMIT ? (int)xb_rd32(ev + 0x20) : -1;
    for (int i = 0; i < nmm; i++) {
        if (mm[i].track != track || !mm_in(i, x, y, z)) continue;
        snprintf(mm_flash, sizeof mm_flash, "%s", mm[i].name);
        mm_flash_until = rt_now_100ns() + 50000000, mm_flash_new = !mm[i].got;
        fprintf(stderr, "xbrt: mayhem: moment %s%s\n", mm[i].name, mm[i].got ? "" : " (unlocked)");
        if (!mm[i].got) {
            mm[i].got = 1;
            char path[512];
            snprintf(path, sizeof path, "%s/mayhem_moments.txt", mods_dir());
            FILE *f = fopen(path, "a");
            if (f) fprintf(f, "%s\n", mm[i].name), fclose(f);
        }
        return 1;
    }
    return 0;
}

/* The car for every Mayhem Moment (the user's, 7 Nov: "a prize car for getting all Mayhem Moments"): mayhem.txt's
 * "prize <ordinal>". Given the game's own way (docs/research/car-gift.md): the career's series flow works out a
 * finished race's rewards with f_0017E270(..., gifts, ...), its second argument the list of cars won (a vector<int>:
 * begin +4, end +8); the ordinal is pushed onto it there (f_0018C280, push_back), so the game's CarUnlock screen
 * shows it, puts it in the garage (or credits if the garage is full), takes its picture and saves. Owed while
 * every Moment is found and <mods>/mayhem_prize.txt doesn't say "given"; marked given when the garage takes the
 * car (its add, f_00056A40(ordinal, ...), thiscall), never in the save. XBRT_MM_PRIZE=0: off. */
static int mm_prize_given = -1;
static const char *mm_prize_path(void) {
    static char path[512];
    snprintf(path, sizeof path, "%s/mayhem_prize.txt", mods_dir());
    return path;
}
static int mm_prize_owed(void) {
    mayhem_load();
    if (!mm_prize || !nmm || (getenv("XBRT_MM_PRIZE") && !atoi(getenv("XBRT_MM_PRIZE")))) return 0;
    for (int i = 0; i < nmm; i++) if (!mm[i].got) return 0;
    if (mm_prize_given < 0) {
        char line[64] = "";
        FILE *f = fopen(mm_prize_path(), "r");
        if (f) { if (!fgets(line, sizeof line, f)) line[0] = 0; fclose(f); }
        mm_prize_given = !strncmp(line, "given", 5);
    }
    if (mm_prize_given) return 0;
    uint32_t n = xb_rd32(0x57D188); /* (the car list: an ordinal it has, or the car screen reads a null car) */
    for (uint32_t r = 0; r < n && r < 400; r++)
        if (xb_rd32(0x57D18C + r * 0x8C + 0x7C) == (uint32_t)mm_prize) return 1;
    fprintf(stderr, "xbrt: mayhem prize: car %d not in the car list\n", mm_prize);
    return 0;
}
void orig_f_0017E270(XbCtx *c); /* a finished race's rewards (wraps.txt) */
void f_0017E270(XbCtx *c) {
    uint32_t gifts = xb_rd32(c->esp + 8), race = xb_rd32(0x592984); /* (cdecl: read before the call returns) */
    orig_f_0017E270(c);
    if (!gifts || !race || xb_rd32(race + 0x24) != 0 || !mm_prize_owed()) return;
    uint32_t b = xb_rd32(gifts + 4), e = xb_rd32(gifts + 8);
    for (uint32_t p = b; p && p < e; p += 4) if (xb_rd32(p) == (uint32_t)mm_prize) return; /* (on it already) */
    uint32_t scratch = c->esp - 0x10, ecx = c->ecx;
    xb_wr32(scratch, (uint32_t)mm_prize);
    c->ecx = gifts;
    rt_guest_call(c, 0x0018C280u, 1, scratch);
    c->ecx = ecx;
    fprintf(stderr, "xbrt: mayhem prize: every Moment found, car %d to the car screen\n", mm_prize);
}
void orig_f_00056A40(XbCtx *c); /* the garage takes a car (wraps.txt) */
void f_00056A40(XbCtx *c) {
    uint32_t ordinal = xb_rd32(c->esp + 4);
    orig_f_00056A40(c);
    if (mm_prize && ordinal == (uint32_t)mm_prize && c->eax && mm_prize_given == 0) {
        FILE *f = fopen(mm_prize_path(), "w");
        if (f) fprintf(f, "given %d\n", mm_prize), fclose(f);
        mm_prize_given = 1;
        fprintf(stderr, "xbrt: mayhem prize: car %d in the garage\n", mm_prize);
    }
}

int rt_qr_takedowns(void) { return takedowns; }
int rt_qr_mayhem(void) { return mayhem_race && xb_rd32(0x592984); }
float rt_qr_tank(void) { return tank; }


static int active(void) {
    static int always = -1;
    if (always < 0) always = getenv("XBRT_QR_ALWAYS") && atoi(getenv("XBRT_QR_ALWAYS"));
    if (always || mayhem_race) return 1;
    if (!qr_event) return 0; /* (Quick Race not set) */
    /* the race's event by its name, whichever copy of the record it runs on (the modifiers never acted: this
     * asked for an event ordinal nothing set) */
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    return ev && ev < RT_USER_LIMIT && xb_rd32(ev + 0x14) == QR_EVENT_NAME;
}

/* The racing line point nearest (x, z), or -1. */
static int nearest(uint32_t xs, uint32_t zs, uint32_t np, float x, float z) {
    int k = -1;
    float best = 1e30f;
    for (uint32_t j = 0; j < np; j++) {
        float px = rdf(xs + 4 * j) - x, pz = rdf(zs + 4 * j) - z, d = px * px + pz * pz;
        if (d < best) best = d, k = (int)j;
    }
    return k;
}

#define MAXCARS 32 /* racers (Mayhem's big field: 17; was 12) */
static struct {
    uint32_t car;
    float v[3], pos[3];
    uint64_t still_since, off_since, hit_at, spin_until, down_at, tumble_until, chase_until, spun_since, wall_until;
    float spin;   /* radians a second about the up axis, until spin_until */
    float impact; /* the closing speed of the player's last hit on it, m/s */
    float push[2]; uint64_t push_until; /* a hit's shove, m/s, given over 0.2 s (at once it jolted) */
    int line, kind; /* kind: the player's last hit on it, 1 a slam (side), 2 a shunt (from behind) */
} cs[MAXCARS];

/* A car's damage (found with XBRT_DMGSCAN and the user's crashes on 3 Nov: after the hard ones, three floats of
 * 0..1 at +0x70, +0x74 and +0x78 of 128-byte records from car+0x4380 to +0x5A80 stood and stayed, none before).
 * A takedown's wreck wrecked (the user's: "extremely damaged"), every record at DMG_FULL; back to none on its
 * respawn. XBRT_DMGMAX=<s>: the player's car so that long into a race (testing: what it looks like). */
#define DMG_FIRST 0x4380u
#define DMG_LAST 0x5A80u
#define DMG_FULL 0.95f
#define DMG_N (((DMG_LAST - DMG_FIRST) / 0x80 + 1) * 3)
/* Only the damage the game itself has set, raised (every field written, the second wreck of the user's test, another
 * car, went over something else and the game stopped with a bad push buffer: its car has fewer such records),
 * and those same fields put back to none on the respawn. */
static struct { uint32_t car, at[DMG_N]; int n; } dmg[MAXCARS];
static void damage_set(int slot, uint32_t car, float amount) {
    if (slot < 0 || slot >= MAXCARS) return;
    if (amount > 0) {
        dmg[slot].car = car, dmg[slot].n = 0;
        for (uint32_t r = DMG_FIRST; r <= DMG_LAST; r += 0x80)
            for (uint32_t k = 0x70; k <= 0x78; k += 4) {
                float v = rdf(car + r + k);
                if (v > 0.0005f && v < amount) wrf(car + r + k, amount), dmg[slot].at[dmg[slot].n++] = car + r + k;
            }
    } else if (dmg[slot].car == car) {
        for (int j = 0; j < dmg[slot].n; j++) wrf(dmg[slot].at[j], 0);
        dmg[slot].n = 0, dmg[slot].car = 0;
    }
}

/* The car rolled by a radians about its own forward axis (the blown-up wreck's tumble). */
static void roll(uint32_t car, float a) {
    float c = cosf(a), s = sinf(a), r[3], u[3];
    for (int j = 0; j < 3; j++) r[j] = rdf(car + 0x20 + 4 * (uint32_t)j), u[j] = rdf(car + 0x2C + 4 * (uint32_t)j);
    for (int j = 0; j < 3; j++) wrf(car + 0x20 + 4 * (uint32_t)j, r[j] * c + u[j] * s), wrf(car + 0x2C + 4 * (uint32_t)j, -r[j] * s + u[j] * c);
}

/* The car's heading turned by a radians about the world's up axis (its 3x3 by rows, each an axis in the world):
 * its velocity kept, so it slides, out of grip. (No spin rate known in the car: the pose, which the physics
 * takes as it takes respawn's.) */
static void yaw(uint32_t car, float a) {
    float c = cosf(a), s = sinf(a);
    for (int row = 0; row < 3; row++) {
        uint32_t at = car + 0x20 + 12 * (uint32_t)row;
        float x = rdf(at), z = rdf(at + 8);
        wrf(at, x * c + z * s), wrf(at + 8, -x * s + z * c);
    }
}

/* How much the racing line turns over the next stretch from point k (radians, from its heading 5 points on to
 * 20 on): Mayhem's pushes stay off in the corners (where they put the rivals off their lines). */
static float line_turn(uint32_t xs, uint32_t zs, uint32_t np, int k) {
    int a = k, b = (k + 5) % (int)np, c = (k + 20) % (int)np;
    float x1 = rdf(xs + 4 * b) - rdf(xs + 4 * a), z1 = rdf(zs + 4 * b) - rdf(zs + 4 * a);
    float x2 = rdf(xs + 4 * c) - rdf(xs + 4 * b), z2 = rdf(zs + 4 * c) - rdf(zs + 4 * b);
    float t = atan2f(x1 * z2 - z1 * x2, x1 * x2 + z1 * z2);
    return t < 0 ? -t : t;
}

/* The racing line's point about m metres behind point k (the takedown wreck's place: behind the player). */
static int behind(uint32_t xs, uint32_t zs, uint32_t np, int k, float m) {
    for (int j = 0; j < (int)np && m > 0; j++) {
        int k2 = (k - 1 + (int)np) % (int)np;
        float dx = rdf(xs + 4 * k) - rdf(xs + 4 * k2), dz = rdf(zs + 4 * k) - rdf(zs + 4 * k2);
        m -= sqrtf(dx * dx + dz * dz), k = k2;
    }
    return k;
}

/* The car set back on the racing line at point k (+ a few on), facing along it, rolling at 15 m/s. */
static void respawn(uint32_t car, uint32_t xs, uint32_t zs, uint32_t ys, uint32_t np, int k) {
    k = (k + 4) % (int)np;
    float x = rdf(xs + 4 * k), y = rdf(ys + 4 * k), z = rdf(zs + 4 * k);
    int k2 = (k + 3) % (int)np;
    float fx = rdf(xs + 4 * k2) - x, fz = rdf(zs + 4 * k2) - z, len = sqrtf(fx * fx + fz * fz);
    if (len < 0.1f) return;
    fx /= len, fz /= len;
    float pose[12] = {x, y + 0.6f, z, fz, 0, -fx, 0, 1, 0, fx, 0, fz};
    for (int j = 0; j < 12; j++) wrf(car + 0x14 + 4 * j, pose[j]);
    wrf(car + 0x44, fx * 15), wrf(car + 0x48, 0), wrf(car + 0x4C, fz * 15);
    wrf(car + 0x50, 0), wrf(car + 0x54, 0), wrf(car + 0x58, 0); /* (its spin stopped: a blown-up wreck's tumble, kept as
                                                                 * it was set down on the line, went with it into the
                                                                 * road; the hang after a takedown of 5 Nov had NaNs) */
}

/* A car's pose, velocity or spin not a number, or far past any race's (a car's physics gone to NaN: the game's
 * then ran on with it and stopped drawing, "no frame for 8 s", the user's of 5 Nov, a takedown's respawn before). */
static int car_broken(uint32_t car) {
    for (uint32_t j = 0; j < 12; j++) { float f = rdf(car + 0x14 + 4 * j); if (!(f > -1e5f && f < 1e5f)) return 1; }
    for (uint32_t j = 0; j < 6; j++) { float f = rdf(car + 0x44 + 4 * j); if (!(f > -2e3f && f < 2e3f)) return 1; }
    return 0;
}

static uint32_t heapcam[8]; /* the scan's last camera copies on the heap (cam_debug_tick) */
static int nheapcam;

/* XBRT_CAMSCAN=3: 60 s into a race, every place within 8 KB of the camera's copies on the heap (its objects: they
 * move from run to run) holding the player's car or racer record's address is given a rival's for 6 s, then put
 * back: does the camera follow? */
static void cam_swap_test(void) {
    static uint64_t t0, t1;
    static uint32_t at[64], was[64];
    static int n;
    uint64_t now = rt_now_100ns();
    if (!xb_rd32(0x592984)) { t0 = t1 = 0; return; }
    if (!t0) t0 = now;
    if (!t1 && now - t0 > 600000000 && nheapcam) {
        uint32_t list = 0x58DAA0, cnt = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), me = 0, rme = 0, them = 0, rthem = 0;
        for (uint32_t i = 0; arr && i < cnt && i < 12; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            if (!r || r >= RT_USER_LIMIT) continue;
            if (xb_rd32(r + 0x14) == 0) rme = r, me = xb_rd32(r + 0xA0);
            else if (!rthem) rthem = r, them = xb_rd32(r + 0xA0);
        }
        if (!me || !them) return;
        n = 0;
        uint32_t lo = heapcam[0], hi = heapcam[0];
        for (int i = 1; i < nheapcam; i++) lo = heapcam[i] < lo ? heapcam[i] : lo, hi = heapcam[i] > hi ? heapcam[i] : hi;
        for (uint32_t a = (lo - 0x2000) & ~3u; a < hi + 0x2000 && n < 64; a += 4) {
            uint32_t w = xb_rd32(a);
            if (w == me || w == rme) at[n] = a, was[n] = w, xb_wr32(a, w == me ? them : rthem), n++;
        }
        t1 = now;
        rt_time_scale(0.35); /* (and the game's clock slowed: does the race slow?) */
        fprintf(stderr, "xbrt: camswap: race clock %.3f at %.3f s\n", rdf(xb_rd32(rme + 0xC0) + 0xA0), now / 1e7);
        fprintf(stderr, "xbrt: camswap: %d places now hold the rival's (car %08x, racer %08x):", n, them, rthem);
        for (int i = 0; i < n; i++) fprintf(stderr, " %08x", at[i]);
        fprintf(stderr, "\n");
    }
    if (t1 && n && now - t1 > 60000000) {
        for (int i = 0; i < n; i++) xb_wr32(at[i], was[i]);
        rt_time_scale(1.0);
        uint32_t list = 0x58DAA0, arr = xb_rd32(list + 4), r0 = arr ? xb_rd32(arr) : 0;
        for (uint32_t i = 0; arr && i < xb_rd32(list + 0x10) && i < 12; i++)
            if (xb_rd32(xb_rd32(arr + 4 * i) + 0x14) == 0) r0 = xb_rd32(arr + 4 * i);
        fprintf(stderr, "xbrt: camswap: race clock %.3f at %.3f s\n", r0 ? rdf(xb_rd32(r0 + 0xC0) + 0xA0) : -1.0f, now / 1e7);
        fprintf(stderr, "xbrt: camswap: put back\n");
        n = 0;
    }
}

/* Finding the game's camera (for the takedown camera): XBRT_CAMSCAN=1, in a race every 4 s, the places in the game's
 * committed memory holding the camera's position (rt_cam_pos, from the frame's constants) as three floats in a
 * row, logged. XBRT_CAMPOKE=<hex address>: the float there and the next two raised 3 m in y every tick, to see
 * whether the picture follows (the camera's own) or not (a copy). */
static void cam_debug_tick(void) {
    static int on = -1, npoke;
    static uint32_t poke[8];
    static const float step[8] = {1, 7, 31, 113, 2, 5, 13, 59}; /* (several at once, told apart by how far the camera goes) */
    if (on < 0) {
        on = getenv("XBRT_CAMSCAN") ? atoi(getenv("XBRT_CAMSCAN")) : 0;
        for (const char *e = getenv("XBRT_CAMPOKE"); e && *e && npoke < 8; e = strchr(e, ',') ? strchr(e, ',') + 1 : "")
            poke[npoke++] = (uint32_t)strtoul(e, NULL, 16);
    }
    for (int i = 0; i < npoke && xb_rd32(0x592984); i++) wrf(poke[i] + 4, rdf(poke[i] + 4) + step[i]);
    static uint64_t next;
    uint64_t now = rt_now_100ns();
    if (on == 3) cam_swap_test();
    if (!on || !xb_rd32(0x592984) || now < next || !rt_cam_frame) return;
    next = now + 40000000;
    float cx = rt_cam_pos[0], cy = rt_cam_pos[1], cz = rt_cam_pos[2];
    nheapcam = 0;
    fprintf(stderr, "xbrt: camscan: camera at %.2f %.2f %.2f:", cx, cy, cz);
    int n = 0;
    uint32_t at = RT_USER_BASE, b, sz, pr, st;
    while (at < RT_USER_LIMIT && n < 40) {
        if (!rt_user_query(at, &b, &sz, &pr, &st) || !sz) { at = b + (sz ? sz : 0x1000); continue; }
        if (at < b) at = b;
        uint32_t end = b + sz;
        if (st == 0x1000)
            for (uint32_t a = at; a + 12 <= end && n < 40; a += 4) {
                float x = rdf(a);
                if (!(fabsf(x - cx) <= 0.05f && fabsf(rdf(a + 4) - cy) <= 0.05f && fabsf(rdf(a + 8) - cz) <= 0.05f)) continue; /* (NaN fails) */
                fprintf(stderr, " %08x", a), n++;
                if (a >= 0x01000000 && nheapcam < 8) heapcam[nheapcam++] = a;
            }
        at = end;
    }
    fprintf(stderr, " (%d)\n", n);
    if (on >= 2) { /* XBRT_CAMSCAN=2: what follows the player's car: the places holding its car or racer record's address */
        uint32_t list = 0x58DAA0, cnt = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), me = 0, rme = 0;
        for (uint32_t i = 0; arr && i < cnt && i < 12; i++) {
            uint32_t r = xb_rd32(arr + 4 * i);
            if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) rme = r, me = xb_rd32(r + 0xA0);
        }
        fprintf(stderr, "xbrt: camscan: the player's car %08x, racer %08x, held at:", me, rme);
        int m = 0;
        for (at = RT_USER_BASE; me && at < RT_USER_LIMIT && m < 60;) {
            if (!rt_user_query(at, &b, &sz, &pr, &st) || !sz) { at = b + (sz ? sz : 0x1000); continue; }
            if (at < b) at = b;
            uint32_t end = b + sz;
            if (st == 0x1000)
                for (uint32_t a = at; a + 4 <= end && m < 60; a += 4) {
                    uint32_t w = xb_rd32(a);
                    if (w == me || w == rme) fprintf(stderr, " %08x%s", a, w == me ? "c" : "r"), m++;
                }
            at = end;
        }
        fprintf(stderr, " (%d)\n", m);
    }
}

/* ---- the takedown camera (the user's, after Burnout 3's): for TDCAM_S seconds the game's own chase camera rides
 * with the wreck, the game slowed to TDCAM_SLOW (rt_time_scale: its clock), and the player's car is held on the
 * suggested line (the autopilot) until the player takes it back: steers, brakes, or lets off and presses the
 * throttle again (hle_input.c). The camera follows whichever car its objects point at: they hold the player's car
 * and racer record's addresses, and given a rival's (a test, XBRT_CAMSCAN=3) the camera rode with the rival. They
 * are found once a race on the grid: the camera's position (rt_cam_pos) in the game's committed memory, then the
 * player's addresses within 8 KB of those copies on the heap (the objects move from run to run). */
#define TDCAM_S 3.0
#define TDCAM_SLOW 0.5 /* (30 frames a second, the user's: the game steps its race a frame at a time, so half speed) */
static uint32_t cslot[16], cslot_was[16], cslot_now[16];
static uint32_t td_from, td_to; /* the cars the camera cut between */
static int ncslot = -1;      /* -1: not looked for yet this race */
static uint32_t cam_lo, cam_hi; /* the camera's object: the bunch of its position's copies found on the grid */

/* The camera cut to another car instead of swinging over (the user's: "camera still not cutting over"): within
 * the camera's own object only (1 KB round its position's copies: over 8 KB, 347 places moved and the rival froze),
 * every three floats standing within 15 m of the car it leaves (its places, where it looks, its smoothing's
 * state) moved by the way from that car to the other. */
static void cam_cut(uint32_t from, uint32_t to) {
    static int on = -1; /* (XBRT_CAMCUT=1 only, for testing: once, the rival went 570 m in the 3 s; unproven) */
    if (on < 0) on = getenv("XBRT_CAMCUT") && atoi(getenv("XBRT_CAMCUT"));
    if (!on || !cam_hi || !from || !to) return;
    float f[3] = {rdf(from + 0x14), rdf(from + 0x18), rdf(from + 0x1C)}, d[3] = {rdf(to + 0x14) - f[0], rdf(to + 0x18) - f[1], rdf(to + 0x1C) - f[2]};
    int n = 0;
    for (uint32_t a = (cam_lo - 0x400) & ~3u; a < cam_hi + 0x400; a += 4) {
        float x = rdf(a), y = rdf(a + 4), z = rdf(a + 8);
        if (!(fabsf(x - f[0]) < 15 && fabsf(z - f[2]) < 15 && fabsf(y - f[1]) < 8)) continue;
        wrf(a, x + d[0]), wrf(a + 4, y + d[1]), wrf(a + 8, z + d[2]);
        a += 8, n++;
    }
    fprintf(stderr, "xbrt: quick race: the camera cut, %d places moved %.0f m\n", n, sqrtf(d[0] * d[0] + d[2] * d[2]));
}
volatile uint64_t rt_present_hold_until; /* (rt.h, glfill.c) */
volatile char rt_photo_path[512];
#define DRIFT_BRAKE 13.0f /* m/s^2 at full brake in a drift */
#define MAYHEM_RIVAL_NUDGES 0 /* the rivals' pushes below, off: the game's own driving (the user's, 5 Nov: "don't worry about
                                * the opponents AI. Return them to original values"; with them on they hit the walls) */
#define AI_PUSH 3.0f      /* m/s^2: Mayhem's rivals pushed on along the straights (the user's, 5 Nov: "return them to original
                           * values": 4 a while) */
#define AI_PUSH_TOP 85.0f /* m/s: under this (90 a while) */
#define MAYHEM_PULL 3.5f  /* m/s^2 at full throttle, on top of the game's: the player's (5 before the user's, 5 Nov: "make the
                           * acceleration a little slower") */
#define DRIFT_OUT 9000000ull /* 100 ns: the way out of a drift eased over 0.9 s */
#define DRIFT_EASE 3.5f /* the slip closed at this rate a second on the way out */
static uint64_t qr_ticks; /* rt_qr_tick's that acted (the handling's state dropped when it missed one)*/
static int me_drift; /* the player's car drifting or easing out of one, this tick (no spin-out then) */
volatile float rt_drift_look; /* (rt.h: the look wanted in a drift, radians, + to the right; hle_input.c holds the right stick so) */
volatile int rt_photo_lookback; /* (rt.h, hle_input.c: 1 Y held, the game looking back; 2 right, 3 left: the right stick) */
volatile float rt_toon; /* (rt.h: Mayhem's cartoon look, glfill.c) */
static uint64_t flame_until; /* real time: the boost burning (its flame drawn by glover.c) */
static uint32_t flame_car;

/* The boost's flame: the player's car's tail, low and in the middle (2.1 m back, 0.35 m up), and the way back. */
int rt_qr_flame(float pos[3], float back[3], float *power) {
    uint32_t car = flame_car;
    if (!flame_until || rt_now_100ns() > flame_until || !car || car >= RT_USER_LIMIT || !xb_rd32(0x592984)) return 0;
    float fx = rdf(car + 0x38), fy = rdf(car + 0x3C), fz = rdf(car + 0x40), ux = rdf(car + 0x2C), uy = rdf(car + 0x30), uz = rdf(car + 0x34);
    pos[0] = rdf(car + 0x14) - fx * 2.1f + ux * 0.35f, pos[1] = rdf(car + 0x18) - fy * 2.1f + uy * 0.35f, pos[2] = rdf(car + 0x1C) - fz * 2.1f + uz * 0.35f;
    back[0] = -fx, back[1] = -fy, back[2] = -fz;
    *power = 1.0f;
    return 1;
}
static uint32_t cand[24], cand_was[24]; /* the places to try (find_cam_slots), the camera's among them (cam_probe_tick) */
static int ncand, probe_i, probe_stage;
static int cam_retry; /* the camera's holds looked for again on the grid (fewer than 2 found) */
static uint64_t cam_retry_at;
static uint64_t tdcam_until; /* real time */
static uint64_t auto_until; /* real time: the autopilot let go by then at the latest (7 s after the camera is back) */
volatile int rt_qr_auto;     /* the autopilot: 2 just started, 1 on (hle_input.c ends it) */
static float auto_speed, auto_p[2];
static int auto_k = -1;

int rt_qr_cam_active(void) { return tdcam_until != 0; }

static uint64_t probe_began; /* (the probe's hold renewed as it goes, 10 s at most: 24 places at 30 fps outran 3 s) */
static void find_cam_slots(uint32_t me, uint32_t rme) {
    float cx = rt_cam_pos[0], cy = rt_cam_pos[1], cz = rt_cam_pos[2];
    uint32_t copy[32], at = RT_USER_BASE, b, sz, pr, st;
    int nc = 0;
    while (at < RT_USER_LIMIT && nc < 32) { /* (in address order: the regions come so) */
        if (!rt_user_query(at, &b, &sz, &pr, &st) || !sz) { at = b + (sz ? sz : 0x1000); continue; }
        if (at < b) at = b;
        uint32_t end = b + sz;
        if (st == 0x1000 && at >= 0x01000000)
            for (uint32_t a = at; a + 12 <= end && nc < 32; a += 4)
                if (fabsf(rdf(a) - cx) <= 0.05f && fabsf(rdf(a + 4) - cy) <= 0.05f && fabsf(rdf(a + 8) - cz) <= 0.05f) copy[nc++] = a;
        at = end;
    }
    /* the camera's objects: the closest bunch of those copies (each within 4 KB of the next), and only 2 KB round
     * it: from the lowest copy to the highest, another run took in the race's and the HUD's hold on the player's
     * car too (16 places), and given the rival, takedowns stopped counting and the camera went wrong */
    /* Every bunch, the biggest first, gives its places to try (the user's, 7 Nov: "takedown camera wasn't working" on
     * Pacific Shipyards and Fujimi: there 6 copies came as two bunches of 3, the first taken was not the camera's,
     * and the camera followed none of its 2 places); the probe then finds the camera's among them all. */
    int bs[32], bn[32], nb = 0;
    for (int i = 0; i < nc;) {
        int j = i;
        while (j + 1 < nc && copy[j + 1] - copy[j] < 0x1000) j++;
        bs[nb] = i, bn[nb++] = j - i + 1;
        i = j + 1;
    }
    for (int x = 1; x < nb; x++) /* (by size, the biggest first; the lower address first among equals) */
        for (int y = x; y > 0 && bn[y] > bn[y - 1]; y--) { int t = bs[y]; bs[y] = bs[y - 1], bs[y - 1] = t; t = bn[y]; bn[y] = bn[y - 1], bn[y - 1] = t; }
    int best = nb ? bs[0] : 0, bestn = nb ? bn[0] : 0;
    uint32_t lo = nc ? copy[best] : 0, hi = nc ? copy[best + bestn - 1] : 0;
    cam_lo = lo, cam_hi = hi;
    ncand = 0, ncslot = 0, probe_i = 0, probe_stage = 0;
    for (int b2 = 0; b2 < nb && ncand < 24; b2++) {
        uint32_t l2 = copy[bs[b2]], h2 = copy[bs[b2] + bn[b2] - 1];
        for (uint32_t a = (l2 - 0x2000) & ~3u; a < h2 + 0x2000 && ncand < 24; a += 4) {
            uint32_t w = xb_rd32(a);
            if (w != me && w != rme) continue;
            int seen = 0;
            for (int q = 0; q < ncand; q++) seen |= cand[q] == a;
            if (!seen) cand[ncand] = a, cand_was[ncand++] = w;
        }
    }
    fprintf(stderr, "xbrt: quick race: the camera's hold on the player's car, %d places to try (%d copies, %d together over %u bytes)\n",
            ncand, nc, bestn, hi - lo);
    /* The camera's two holds told by their look, not tried (the user's, 7 Nov: the probe held the picture still on the
     * grid for seconds, "game still froze"): in every probe's finds, the camera's hold on the car is the second of two
     * copies of the car's address 8 bytes apart, and its hold on the racer record the first of two copies side by side,
     * 0xB0 or 0x260 bytes before it (the far and the near chase cameras). So no probe: those, when the look is there. */
    static int noprobe = -1;
    if (noprobe < 0) noprobe = !(getenv("XBRT_CAM_PROBE") && atoi(getenv("XBRT_CAM_PROBE")));
    if (noprobe) {
        uint32_t H = 0, R = 0;
        for (int q = 0; q < ncand && !H; q++)
            if (cand_was[q] == me && xb_rd32(cand[q] - 8) == me && xb_rd32(cand[q] - 4) != me) H = cand[q];
        for (uint32_t a = H ? H - 4 : 0; H && a >= H - 0x400; a -= 4)
            if (xb_rd32(a) == rme && xb_rd32(a + 4) == rme && xb_rd32(a - 4) != rme) { R = a; break; }
        ncslot = 0, probe_i = ncand; /* (none to try) */
        if (R) cslot[ncslot] = R, cslot_was[ncslot++] = rme;
        if (H) cslot[ncslot] = H, cslot_was[ncslot++] = me;
        fprintf(stderr, "xbrt: quick race: the camera's holds by their look: car %08x, racer %08x (%d)", H, R, ncslot);
        for (int q = 0; q < ncand && ncslot < 2; q++) /* (not found: each place and its neighbours, to learn the look) */
            fprintf(stderr, "%s %08x=%s [-8]%08x [-4]%08x [+4]%08x", q ? "," : "; places:", cand[q], cand_was[q] == me ? "car" : "racer", xb_rd32(cand[q] - 8), xb_rd32(cand[q] - 4), xb_rd32(cand[q] + 4));
        if (H && !R) { /* (for the next look: what stands where the racer's were) */
            fprintf(stderr, "; at -0xB0: %08x %08x, at -0x260: %08x %08x", xb_rd32(H - 0xB0), xb_rd32(H - 0xAC), xb_rd32(H - 0x260), xb_rd32(H - 0x25C));
        }
        fprintf(stderr, "\n");
        return;
    }
    if (ncand) rt_present_hold_until = rt_now_100ns() + 30000000, probe_began = rt_now_100ns(); /* (the picture held while they are tried: no flicker) */
}

/* Debugging (XBRT_CAMSCAN_LATE=1): every 3 s, read only, the camera position's copies in memory, by bunch, and the
 * player's car's and racer record's addresses held within 8 KB of each bunch: when the camera's hold on the racer
 * record comes to be (on the grid without a press of the view button only the car's was found, 7 Nov). */
static float cam_along(uint32_t me);
static void cam_scan_debug(uint32_t me, uint32_t rme, int lap) {
    static uint64_t next;
    uint64_t now = rt_now_100ns();
    if (now < next) return;
    next = now + 30000000;
    float cx = rt_cam_pos[0], cy = rt_cam_pos[1], cz = rt_cam_pos[2];
    uint32_t copy[32], at = RT_USER_BASE, b, sz, pr, st;
    int nc = 0;
    while (at < RT_USER_LIMIT && nc < 32) {
        if (!rt_user_query(at, &b, &sz, &pr, &st) || !sz) { at = b + (sz ? sz : 0x1000); continue; }
        if (at < b) at = b;
        uint32_t end = b + sz;
        if (st == 0x1000 && at >= 0x01000000)
            for (uint32_t a = at; a + 12 <= end && nc < 32; a += 4)
                if (fabsf(rdf(a) - cx) <= 0.05f && fabsf(rdf(a + 4) - cy) <= 0.05f && fabsf(rdf(a + 8) - cz) <= 0.05f) copy[nc++] = a;
        at = end;
    }
    fprintf(stderr, "xbrt: camscan: lap %d, the camera %.1f m along the car, %d copies:", lap, cam_along(me), nc);
    for (int i = 0; i < nc;) {
        int j = i;
        while (j + 1 < nc && copy[j + 1] - copy[j] < 0x1000) j++;
        fprintf(stderr, " [%08x-%08x:", copy[i], copy[j]);
        for (uint32_t a = (copy[i] - 0x2000) & ~3u; a < copy[j] + 0x2000; a += 4) {
            uint32_t w = xb_rd32(a);
            if (w == me) fprintf(stderr, " car@%08x", a);
            else if (w == rme) fprintf(stderr, " RACER@%08x", a);
        }
        fprintf(stderr, "]");
        i = j + 1;
    }
    fprintf(stderr, "\n");
}

/* Which of those places the camera itself follows (the user's: the camera "not cutting over": with 2 of them it
 * faced the wreck but stood at the player's car, with 16 the race and the HUD went to the rival too): on the grid,
 * the camera still, each given a rival's car or racer record for a few frames, then put back; those that moved the
 * camera (the frame's view, rt_cam_pos) are the camera's. Once a race; on the grid only. */
static void cam_probe_tick(uint32_t me, uint32_t rme, uint32_t them, uint32_t rthem) {
    static uint32_t frame;
    static float base[3];
    if (probe_i >= ncand || !them) return;
    uint32_t f = rt_cam_frame;
    if (probe_stage == 0) { /* the camera as it stands */
        base[0] = rt_cam_pos[0], base[1] = rt_cam_pos[1], base[2] = rt_cam_pos[2];
        xb_wr32(cand[probe_i], cand_was[probe_i] == me ? them : rthem);
        frame = f, probe_stage = 1;
        if (rt_now_100ns() - probe_began < 100000000) rt_present_hold_until = rt_now_100ns() + 20000000;
    } else if (probe_stage == 1 && f - frame >= 6) { /* moved? (6 frames: the camera catches up) */
        float dx = rt_cam_pos[0] - base[0], dy = rt_cam_pos[1] - base[1], dz = rt_cam_pos[2] - base[2], d = sqrtf(dx * dx + dy * dy + dz * dz);
        xb_wr32(cand[probe_i], cand_was[probe_i]);
        if (d > 3.0f && ncslot < 16) cslot[ncslot] = cand[probe_i], cslot_was[ncslot++] = cand_was[probe_i];
        fprintf(stderr, "xbrt: quick race: camera probe %08x (%s): the camera moved %.2f m%s\n", cand[probe_i],
                cand_was[probe_i] == me ? "car" : "racer", d, d > 3.0f ? ": the camera's" : "");
        frame = f, probe_stage = 2;
    } else if (probe_stage == 2 && f - frame >= 3) { /* back where it was: the next */
        probe_i++, probe_stage = 0;
        if (probe_i >= ncand) {
            rt_present_hold_until = 0; /* (the picture moves on) */
            fprintf(stderr, "xbrt: quick race: the camera follows %d of the %d places\n", ncslot, ncand);
        }
    }
    (void)rme;
}

/* The camera's object as it was when the takedown camera began (its places the probe found, 512 bytes round
 * them): put back at the end, its places near the player's car moved by as far as the car went meanwhile, so
 * the camera cuts straight back behind it facing the right way. Left to itself it came back facing the car from
 * the front (the wreck's tumble in its turn) for some 4 s. */
#define CAM_SNAP 0x2000
static uint32_t snap_lo, snap_n;
static uint32_t snap_w[CAM_SNAP / 4];
static float snap_p[3];

static void cam_snapshot(uint32_t me) {
    uint32_t lo = ~0u, hi = 0;
    for (int i = 0; i < ncslot; i++) lo = cslot[i] < lo ? cslot[i] : lo, hi = cslot[i] > hi ? cslot[i] : hi;
    snap_n = 0;
    if (!hi) return;
    lo = (lo - 0x200) & ~3u, hi += 0x200;
    if (hi - lo > CAM_SNAP) return; /* (not one object, it seems: left alone) */
    snap_lo = lo, snap_n = (hi - lo) / 4;
    for (uint32_t k = 0; k < snap_n; k++) snap_w[k] = xb_rd32(lo + 4 * k);
    snap_p[0] = rdf(me + 0x14), snap_p[1] = rdf(me + 0x18), snap_p[2] = rdf(me + 0x1C);
}

static void cam_restore(uint32_t me) {
    if (!snap_n || !me) return;
    float d[3] = {rdf(me + 0x14) - snap_p[0], rdf(me + 0x18) - snap_p[1], rdf(me + 0x1C) - snap_p[2]};
    int moved = 0;
    for (uint32_t k = 0; k < snap_n; k++) {
        uint32_t w = snap_w[k];
        float x, y, z;
        memcpy(&x, &w, 4);
        if (k + 2 < snap_n) memcpy(&y, &snap_w[k + 1], 4), memcpy(&z, &snap_w[k + 2], 4);
        if (k + 2 < snap_n && fabsf(x - snap_p[0]) < 20 && fabsf(z - snap_p[2]) < 20 && fabsf(y - snap_p[1]) < 10) {
            wrf(snap_lo + 4 * k, x + d[0]), wrf(snap_lo + 4 * k + 4, y + d[1]), wrf(snap_lo + 4 * k + 8, z + d[2]);
            k += 2, moved++;
            continue;
        }
        float a = fabsf(x);
        if (a > 1e-6f && a < 1e6f) xb_wr32(snap_lo + 4 * k, w); /* (floats only: no pointer, count or flag of then over now's) */
    }
    fprintf(stderr, "xbrt: quick race: the camera put back (%u bytes, %d places moved %.0f m)\n", snap_n * 4, moved, sqrtf(d[0] * d[0] + d[2] * d[2]));
    snap_n = 0;
}

/* In-car views (the user's, 4 Nov: "takedowns weren't displaying properly on Rio", raced from the bumper): the takedown
 * camera moves the chase camera's object, and in the bumper or hood view the camera is another, with one of its two
 * holds on the car. The view was switched to the chase one for the search and each takedown (4 Nov), then forced
 * (5 Nov); the user's, 7 Nov: "remove the camera changing code": the player's view is never changed. In an in-car
 * view the holds aren't looked for and a takedown has no camera of its own; Mayhem's grid recommends a chase view. */
#define CAM_INCAR 3.2f
#define CAM_BEHIND 2.5f /* m: a chase view's camera stands over this behind the car's middle */
static int view_tip;        /* Mayhem: the view looked at on this grid: 1 an in-car one (the chase view recommended), 2 not */
static int raced;           /* the player off the grid this race: back on it is a restart */
/* the camera's place along the car's nose (m, + ahead of the car's middle): the chase views stand some 4-6 m behind;
 * the bumper, the hood and the cockpit on the car or ahead of it. (By the distance alone, under CAM_INCAR, the user's
 * bumper view, 4.3 m ahead of the M3's middle, was a chase view: "the camera was forced on front bumper") */
static float cam_along(uint32_t me) {
    float dx = rt_cam_pos[0] - rdf(me + 0x14), dz = rt_cam_pos[2] - rdf(me + 0x1C);
    float hx = rdf(me + 0x38), hz = rdf(me + 0x40), hl = sqrtf(hx * hx + hz * hz);
    return hl > 0.1f ? (dx * hx + dz * hz) / hl : 0;
}
static int cam_in_car(uint32_t me) { return cam_along(me) > -CAM_BEHIND; }

static void tdcam_end(void) {
    if (!tdcam_until) return;
    for (int i = 0; i < ncslot; i++)
        if (xb_rd32(cslot[i]) == cslot_now[i]) xb_wr32(cslot[i], cslot_was[i]);
    cam_restore(td_from); /* (straight back behind the player's car, facing on) */
    cam_cut(td_to, td_from); /* (straight back behind the player's car) */
    rt_time_scale(1.0), rt_vblank_rate = 1.0f;
    auto_until = rt_now_100ns() + 70000000; /* (held on the line past that, takedowns stopped counting: the user's; 4 s, then 7 s (the
                                             * user's, 7 Nov: "make the autopilot a little longer, unless the user press a button") */
    tdcam_until = 0;
}


static void tdcam_start(uint32_t car, uint32_t racer, uint32_t me, float speed) {
    if (tdcam_until) return;
    if (car == me) { /* Mayhem: the player's own crash: the camera already on it; slow motion and the bars only */
        rt_time_scale(TDCAM_SLOW), rt_vblank_rate = (float)TDCAM_SLOW;
        tdcam_until = rt_now_100ns() + (uint64_t)(TDCAM_S * 1e7);
        td_from = td_to = 0, snap_n = 0;
        (void)racer, (void)speed;
        return;
    }
    if (ncslot <= 0) return;
    if (cam_in_car(me)) return; /* (an in-car view: the camera shown isn't the one the holds move) */
    for (int i = 0; i < ncslot; i++)
        if (xb_rd32(cslot[i]) != cslot_was[i]) { /* (not the player's any more: the camera's object gone or remade) */
            fprintf(stderr, "xbrt: quick race: the camera's places changed; no takedown camera until the next race\n");
            ncslot = -1;
            return;
        }
    cam_snapshot(me);
    for (int i = 0; i < ncslot; i++) {
        cslot_now[i] = cslot_was[i] == me ? car : racer;
        xb_wr32(cslot[i], cslot_now[i]);
    }
    td_from = me, td_to = car;
    cam_cut(me, car); /* (straight onto the wreck) */
    rt_time_scale(TDCAM_SLOW), rt_vblank_rate = (float)TDCAM_SLOW; /* (the blanks slow the race; the clock our nudges' steps) */
    tdcam_until = rt_now_100ns() + (uint64_t)(TDCAM_S * 1e7);
    rt_qr_auto = 2, auto_speed = speed < 15 ? 15 : speed, auto_k = -1;
}

/* The autopilot: the car moved along the racing line at auto_speed (the game's clock), facing along it, its height
 * left to the physics. Its own place on the line kept (auto_p, auto_k) so it runs smoothly between the points. */
static void autopilot(uint32_t car, uint32_t xs, uint32_t zs, uint32_t np, double dt) {
    if (auto_k < 0) {
        auto_k = nearest(xs, zs, np, rdf(car + 0x14), rdf(car + 0x1C));
        auto_p[0] = rdf(xs + 4 * auto_k), auto_p[1] = rdf(zs + 4 * auto_k);
    }
    float m = auto_speed * (float)dt, fx = 0, fz = 1;
    for (int guard = 0; guard < 64; guard++) {
        int k2 = (auto_k + 1) % (int)np;
        float tx = rdf(xs + 4 * k2) - auto_p[0], tz = rdf(zs + 4 * k2) - auto_p[1], d = sqrtf(tx * tx + tz * tz);
        if (d > 1e-4f) fx = tx / d, fz = tz / d;
        if (d > m) { auto_p[0] += fx * m, auto_p[1] += fz * m; break; }
        auto_p[0] += tx, auto_p[1] += tz, m -= d, auto_k = k2;
    }
    float pose[12] = {auto_p[0], rdf(car + 0x18), auto_p[1], fz, 0, -fx, 0, 1, 0, fx, 0, fz};
    for (int j = 0; j < 12; j++) wrf(car + 0x14 + 4 * j, pose[j]);
    wrf(car + 0x44, fx * auto_speed), wrf(car + 0x4C, fz * auto_speed);
}

/* Finding a car's damage (for the takedown's wrecks): XBRT_DMGSCAN=1, watched from the race's start: the player's
 * car's first 32 KB and the first 4 KB of every object its first 2 KB points at (up to 48). Damage only grows, so
 * the floats that were 0 then and never went down since (looked at every 0.2 s) and now stand above 0 (up to 5)
 * are logged every 10 s ("car+offset" or "pointer@its place in the car+offset"); the rest (suspension, wheels'
 * turning, the moving parts) drop out as soon as they fall back. (The car's own 32 KB alone: none but an angle.) */
static void dmg_debug_tick(void) {
    enum { SPAN = 0x8000, OBJ = 0x2000, NOBJ = 64, NW = SPAN / 4 + NOBJ * OBJ / 4 };
    static int on = -1, nobj;
    static float prev[NW];
    static uint8_t alive[NW];
    static uint32_t car, base[1 + NOBJ], from[1 + NOBJ];
    static uint64_t look_at, print_at;
    if (on < 0) on = getenv("XBRT_DMGSCAN") && atoi(getenv("XBRT_DMGSCAN"));
    if (!on || !xb_rd32(0x592984)) { car = 0; return; }
    uint32_t list = 0x58DAA0, cnt = xb_rd32(list + 0x10), arr = xb_rd32(list + 4), me = 0, rme = 0;
    for (uint32_t i = 0; arr && i < cnt && i < 12; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) me = xb_rd32(r + 0xA0), rme = r;
    }
    if (!me || me >= RT_USER_LIMIT) return;
    uint32_t tm = xb_rd32(rme + 0xC0);
    if (!tm || tm >= RT_USER_LIMIT || (int)xb_rd32(tm + 0x9C) < 0) return; /* (from the start line on) */
    uint64_t now = rt_now_100ns();
    /* word k: the car's own (k < SPAN/4), else object j's ((k - SPAN/4) / (OBJ/4)) */
    #define DMG_ADDR(k) ((k) < SPAN / 4 ? me + 4 * (k) : base[1 + ((k) - SPAN / 4) / (OBJ / 4)] + 4 * (((k) - SPAN / 4) % (OBJ / 4)))
    if (me != car) {
        car = me, nobj = 0;
        for (uint32_t o = 0; o < 0x1000 && nobj < NOBJ; o += 4) { /* (the car's pointers, then the racer record's: from +0x800) */
            uint32_t p = xb_rd32(o < 0x800 ? me + o : rme + o - 0x800), b, sz, pr, st;
            if (p < 0x01000000 || p >= RT_USER_LIMIT || (p & 3) || (p >= me && p < me + SPAN)) continue;
            if (!rt_user_query(p, &b, &sz, &pr, &st) || st != 0x1000 || p + OBJ > b + sz) continue;
            int dup = 0;
            for (int j = 0; j < nobj; j++) dup |= base[1 + j] == p;
            if (!dup) base[1 + nobj] = p, from[1 + nobj++] = o;
        }
        for (uint32_t k = 0; k < NW; k++) {
            if (k >= SPAN / 4 && (k - SPAN / 4) / (OBJ / 4) >= (uint32_t)nobj) { alive[k] = 0; continue; }
            prev[k] = rdf(DMG_ADDR(k)), alive[k] = prev[k] == 0.0f;
        }
        look_at = print_at = now;
        fprintf(stderr, "xbrt: dmgscan: watching car %08x and %d objects it points at\n", me, nobj);
        return;
    }
    { /* the crashes, timed, to match the readings to */
        static float lv[3];
        static uint64_t lt, told;
        float v[3] = {rdf(me + 0x44), rdf(me + 0x48), rdf(me + 0x4C)};
        double d = lt ? (now - lt) / 1e7 : 0;
        float jx = v[0] - lv[0], jz = v[2] - lv[2], j = d > 0 && d < 0.25 ? sqrtf(jx * jx + jz * jz) / (float)d : 0;
        if (j > 150 && now - told > 10000000) told = now, fprintf(stderr, "xbrt: dmgscan: crash, jolt %.0f m/s^2 at %.1f s\n", j, now / 1e7);
        memcpy(lv, v, sizeof v), lt = now;
    }
    if (now - look_at > 2000000) {
        look_at = now;
        for (uint32_t k = 0; k < NW; k++) {
            if (!alive[k]) continue;
            float v = rdf(DMG_ADDR(k));
            if (!(v >= prev[k] - 1e-6f) || v > 5.0f) alive[k] = 0; /* (went down, NaN, or no damage figure) */
            else prev[k] = v;
        }
    }
    if (now - print_at > 50000000) {
        print_at = now;
        fprintf(stderr, "xbrt: dmgscan: at %.1f s, grown and never down:", now / 1e7);
        int n = 0;
        for (uint32_t k = 0; k < NW && n < 150; k++) {
            if (!alive[k] || !(prev[k] > 0.0005f)) continue;
            if (k < SPAN / 4) fprintf(stderr, " car+%x=%.3f", 4 * k, prev[k]);
            else fprintf(stderr, " [%s%x]+%x=%.3f", from[1 + (k - SPAN / 4) / (OBJ / 4)] < 0x800 ? "car+" : "racer+", from[1 + (k - SPAN / 4) / (OBJ / 4)] % 0x800, 4 * ((k - SPAN / 4) % (OBJ / 4)), prev[k]);
            if (0) fprintf(stderr, " [%x]+%x=%.3f", from[1 + (k - SPAN / 4) / (OBJ / 4)], 4 * ((k - SPAN / 4) % (OBJ / 4)), prev[k]);
            n++;
        }
        fprintf(stderr, " (%d)\n", n);
    }
    #undef DMG_ADDR
}

void rt_qr_tick(void) {
    cam_debug_tick();
    dmg_debug_tick();
    static uint64_t last;
    uint64_t now = rt_game_now_100ns(); /* (the game's clock: in the takedown's slow motion, everything here slows with it) */
    double dt = last ? (now - last) / 1e7 : 0;
    last = now;
    { /* a race begun: Mayhem's, when on and a career menu was up within the minute before */
        static uint32_t race_was, ev_was;
        uint32_t race = xb_rd32(0x592984);
        uint32_t ev = race ? xb_rd32(race + 0x318) : 0;
        if (ev >= RT_USER_LIMIT) ev = 0;
        /* (decided again when the race or its event changes: the race is there before its event is, a grid's
         * worth of ticks, so deciding only when the race appeared saw no event and no career race was Mayhem's) */
        if (race != race_was || ev != ev_was) {
            mayhem_load();
            uint32_t ord = ev ? xb_rd32(ev + 0x10) : 0xFFFFFFFFu;
            int was = race == race_was && mayhem_race;
            mayhem_race = 0;
            for (int k = 0; race && k < nmayhem_ev; k++) mayhem_race |= mayhem_ev[k] == ord; /* (one of the Mayhem category's events) */
            if (race && getenv("XBRT_MAYHEM_TEST") && atoi(getenv("XBRT_MAYHEM_TEST"))) mayhem_race = 1; /* (any race, testing) */
            if (race && mayhem_race && !was) fprintf(stderr, "xbrt: mayhem: this race (event %u)\n", ord);
            if (race && ev && ev != ev_was) fprintf(stderr, "xbrt: race's event ordinal %u\n", ord);
            race_was = race, ev_was = ev;
        }
    }
    if (tdcam_until && rt_now_100ns() >= tdcam_until) tdcam_end();
    if (rt_qr_auto && !tdcam_until && auto_until && rt_now_100ns() >= auto_until) rt_qr_auto = 0, auto_until = 0;
    if (!xb_rd32(0x592984) || !active()) {
        if (probe_i < ncand && probe_stage == 1) xb_wr32(cand[probe_i], cand_was[probe_i]); /* (quit mid-probe: put back) */
        probe_i = ncand = 0, probe_stage = 0;
        tdcam_end(), rt_qr_auto = 0, ncslot = -1, cam_retry = 0, rt_toon = 0, rt_view_cam.on = 0, rt_photo_lookback = 0, rt_drift_look = 0, view_tip = 0, raced = 0;
        memset(cs, 0, sizeof cs); takedowns = 0, tank = 1; return;
    }
    if (dt <= 0 || dt > 0.25) return;
    int mods = mayhem_race ? QR_TAKEDOWNS | QR_NITRO : rt_qr_mods; /* (Mayhem: takedowns and the boost, whatever Quick Race's menu has) */
    rt_toon = mayhem_race ? 1.0f : 0.0f; /* (Mayhem's cartoon look: glfill.c) */
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (!arr || arr >= RT_USER_LIMIT || n > MAXCARS) return;
    uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
    uint32_t np = line ? xb_rd32(line + 8) : 0, xs = line ? xb_rd32(line + 0x30) : 0, zs = line ? xb_rd32(line + 0x44) : 0, ys = line ? xb_rd32(line + 0x58) : 0;
    int have_line = np > 2 && np < 100000 && xs && zs && ys;
    uint32_t me = 0, rme = 0;
    int im = -1;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) me = xb_rd32(r + 0xA0), im = (int)i, rme = r;
    }
    { /* the camera's hold on the player's car, looked for once on the grid (the camera still there: its copies match) */
        static uint64_t grid_since;
        uint32_t tm = rme ? xb_rd32(rme + 0xC0) : 0;
        int on_grid = tm && tm < RT_USER_LIMIT && (int)xb_rd32(tm + 0x9C) < 0;
        if (!on_grid) grid_since = 0;
        else if (!grid_since) grid_since = now;
        /* Mayhem: the player's own view (the user's, 7 Nov: "Don't force the camera change anymore in Mayhem Events";
         * forced to the near chase since 5 Nov), and in a view in the car (the bumper, the hood, the cockpit) a chase
         * view recommended, once a start, half a second off the grid: the grid's own camera stood at the bumper (4.3 m
         * along the car) in a chase view too, and the tip came wrongly */
        static uint64_t go_since;
        if (on_grid || !rme) go_since = 0;
        else if (!go_since) go_since = now;
        { /* a restart (the race's record kept, the player back on the grid after racing): the race's own counts again */
            if (rme && !on_grid && tm && tm < RT_USER_LIMIT) raced = 1;
            else if (on_grid && raced) {
                raced = 0, takedowns = 0, tank = 1;
                memset(cs, 0, sizeof cs);
                fprintf(stderr, "xbrt: quick race: restarted: takedowns and the boost from nothing again\n");
            }
        }
        if (!mayhem_race || on_grid) view_tip = 0;
        else if (!view_tip && me && rt_cam_frame && go_since && now - go_since > 5000000) {
            float vdx = rt_cam_pos[0] - rdf(me + 0x14), vdy = rt_cam_pos[1] - rdf(me + 0x18), vdz = rt_cam_pos[2] - rdf(me + 0x1C);
            float d = sqrtf(vdx * vdx + vdy * vdy + vdz * vdz), al = cam_along(me);
            if (cam_in_car(me) && d < 7) {
                view_tip = 1;
                say_for("TIP: A CHASE VIEW IS BEST FOR MAYHEM (RB / E)", 6.0);
                fprintf(stderr, "xbrt: mayhem: an in-car view (the camera %.1f m along the car): the chase view recommended\n", al);
            } else view_tip = 2;
        }
        { static int scan = -1; if (scan < 0) scan = getenv("XBRT_CAMSCAN_LATE") != NULL;
          if (scan && me && rt_cam_frame) cam_scan_debug(me, rme, tm && tm < RT_USER_LIMIT ? (int)xb_rd32(tm + 0x9C) : -9); }
        if (ncslot < 0 && me && on_grid && rt_cam_frame && now - grid_since > 20000000 && (mods & QR_TAKEDOWNS)) find_cam_slots(me, rme); /* (whatever the grid's camera: it holds the chase camera's places nearby) */
        { /* fewer than the camera's 2 holds found (its place and where it looks: with 1 the takedown camera faced the
           * wreck from the player's car; the user's, 7 Nov: "takedown camera wasn't working" on Pacific Shipyards and
           * Fujimi, 0 and 1 found there): looked for again on the grid, 3 times at most, the best kept */
            static int best_n = -1;
            static uint32_t best_s[16], best_w[16];
            if (ncslot < 0 && cam_retry == 0) best_n = -1;
            if (ncslot >= 0 && probe_i >= ncand && ncand > 0 && ncslot < 2 && on_grid && cam_retry < 3 && now >= cam_retry_at) {
                if (ncslot > best_n) {
                    best_n = ncslot;
                    for (int i = 0; i < ncslot; i++) best_s[i] = cslot[i], best_w[i] = cslot_was[i];
                }
                cam_retry++, cam_retry_at = now + 10000000, ncslot = -1;
                fprintf(stderr, "xbrt: quick race: the camera's holds looked for again (%d found; try %d)\n", best_n, cam_retry);
            } else if (cam_retry > 0 && best_n > (ncslot < 0 ? 0 : ncslot) && ((ncslot >= 0 && probe_i >= ncand && cam_retry >= 3) || !on_grid)) {
                for (int i = 0; i < best_n; i++) cslot[i] = best_s[i], cslot_was[i] = best_w[i];
                ncslot = best_n, best_n = -1, probe_i = ncand;
                fprintf(stderr, "xbrt: quick race: the camera follows the best search's %d places\n", ncslot);
            }
        }
        if (ncslot >= 0 && probe_i < ncand && on_grid && me) { /* then which of them the camera follows (a rival 4 m or more off) */
            uint32_t them = 0, rthem = 0;
            for (uint32_t i = 0; i < n && !them; i++) {
                uint32_t r = xb_rd32(arr + 4 * i), c = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xA0) : 0;
                if (!c || r == rme || c >= RT_USER_LIMIT) continue;
                float dx = rdf(c + 0x14) - rdf(me + 0x14), dz = rdf(c + 0x1C) - rdf(me + 0x1C);
                if (dx * dx + dz * dz > 16) them = c, rthem = r;
            }
            cam_probe_tick(me, rme, them, rthem);
        } else if (probe_i < ncand && !on_grid && probe_stage) { /* (the start came first: what was being tried put back) */
            xb_wr32(cand[probe_i], cand_was[probe_i]);
            probe_stage = 0, probe_i = ncand, rt_present_hold_until = 0;
            fprintf(stderr, "xbrt: quick race: the camera probe cut short by the start: %d places\n", ncslot);
        }
        /* testing: XBRT_TD_TEST=<s>: that long into the race, the takedown camera on the first rival; the race clock
         * (timing +0xA0) at its start and end against real time tells how much the game slowed */
        static uint64_t race_since, td_real;
        static uint32_t td_clock, td_car;
        static float td_p[3], td_sp;
        if (on_grid || !rme) race_since = 0;
        else if (!race_since) race_since = now;
        const char *dm = getenv("XBRT_DMGMAX");
        static int dm_done;
        if (!race_since) dm_done = 0;
        if (dm && race_since && !dm_done && now - race_since > (uint64_t)(atof(dm) * 1e7) && me) {
            dm_done = 1, damage_set(im, me, DMG_FULL);
            fprintf(stderr, "xbrt: dmg test: the player's car wrecked\n");
        }
        const char *bt = getenv("XBRT_MM_BANNER_TEST"); /* testing: that many seconds in, a Mayhem Moment's banner (as new) */
        static int bt_done;
        if (!race_since) bt_done = 0;
        if (bt && race_since && !bt_done && nmm && now - race_since > (uint64_t)(atof(bt) * 1e7)) {
            bt_done = 1, say("MAYHEM MOMENT!");
            snprintf(mm_flash, sizeof mm_flash, "%s", mm[0].name), mm_flash_until = rt_now_100ns() + 50000000, mm_flash_new = 1;
        }
        const char *tt = getenv("XBRT_TD_TEST");
        if (tt && race_since && !td_real && now - race_since > (uint64_t)(atof(tt) * 1e7) && tm) {
            for (uint32_t i = 0; i < n; i++) {
                uint32_t r = xb_rd32(arr + 4 * i);
                if (r && r != rme && r < RT_USER_LIMIT) {
                    tdcam_start(xb_rd32(r + 0xA0), r, me, 30);
                    damage_set((int)i, xb_rd32(r + 0xA0), DMG_FULL); /* (the damage path too, on what it has) */
                    td_real = rt_now_100ns(), td_clock = xb_rd32(tm + 0xA0), td_car = xb_rd32(r + 0xA0);
                    td_p[0] = rdf(td_car + 0x14), td_p[2] = rdf(td_car + 0x1C);
                    td_sp = sqrtf(rdf(td_car + 0x44) * rdf(td_car + 0x44) + rdf(td_car + 0x4C) * rdf(td_car + 0x4C));
                    fprintf(stderr, "xbrt: td test: camera on racer %u (%d places), clock %u, at %.2f real s (the rival at %.0f %.0f, the player at %.0f %.0f)\n",
                            i, ncslot, td_clock, rt_now_100ns() / 1e7, td_p[0], td_p[2], rdf(me + 0x14), rdf(me + 0x1C));
                    break;
                }
            }
        }
        static int told;
        if (td_real && !tdcam_until && !told && tm) {
            told = 1;
            float ddx = rdf(td_car + 0x14) - td_p[0], ddz = rdf(td_car + 0x1C) - td_p[2];
            fprintf(stderr, "xbrt: td test: over: the race clock %u later over %.2f real s (the autopilot %s); the rival went %.1f m at %.1f m/s (%.1f m at full speed)\n",
                    xb_rd32(tm + 0xA0) - td_clock, (rt_now_100ns() - td_real) / 1e7, rt_qr_auto ? "on" : "off",
                    sqrtf(ddx * ddx + ddz * ddz), td_sp, td_sp * (rt_now_100ns() - td_real) / 1e7);
        }
    }
    { /* a restart makes the racers again: the camera's places, the count, the boost and our record of the cars
       * afresh (the audit: the camera wrote into the old ones) */
        static uint32_t rme_was;
        if (rme && rme_was && rme != rme_was) {
            tdcam_end(), rt_qr_auto = 0, ncslot = -1, takedowns = 0, tank = 1;
            memset(cs, 0, sizeof cs);
            fprintf(stderr, "xbrt: quick race: a new run (restart): ours afresh\n");
        }
        if (rme) rme_was = rme;
    }
    for (uint32_t i = 0; i < n && i < MAXCARS; i++) { /* (before the pause's check: a car gone to NaN stopped the race too) */
        uint32_t r = xb_rd32(arr + 4 * i), car = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xA0) : 0;
        if (!car || car >= RT_USER_LIMIT) continue;
        if (have_line && cs[i].car == car && car_broken(car)) { /* set back on the line where it last was */
            float lx = cs[i].pos[0], lz = cs[i].pos[2];
            int at = lx > -1e5f && lx < 1e5f && lz > -1e5f && lz < 1e5f ? nearest(xs, zs, np, lx, lz) : 0;
            fprintf(stderr, "xbrt: quick race: racer %u's car not a number (%g %g %g, v %g %g %g): set back on the line at point %d\n",
                    i, rdf(car + 0x14), rdf(car + 0x18), rdf(car + 0x1C), rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C), at);
            respawn(car, xs, zs, ys, np, at);
        }
    }
    { /* paused (the race's clock stands while its menu is up and the game steps nothing), or the player's race done
       * (+0x1B8: the cool-down lap, the replay): nothing of ours acts (the audit: low gravity and the pushes piled
       * up in the frozen velocities and launched the cars on unpause; the menu's stick turned the car) */
        static uint32_t clock_racer;
        static float clock_was, me_was[3];
        static int why_was, lap_was = -9;
        uint32_t tmr = rme ? xb_rd32(rme + 0xC0) : 0;
        float clock = tmr && tmr < RT_USER_LIMIT ? rdf(tmr + 0xA0) : 0;
        float mpos[3] = {me ? rdf(me + 0x14) : 0, me ? rdf(me + 0x18) : 0, me ? rdf(me + 0x1C) : 0};
        /* (paused: the clock AND the player's car standing, the car for over 0.25 s. The user's "brake to drift stops
         * working on lap 2": this clock (+0xA0) stops at the first lap's end (83.4 s and on, the log), so from lap 2 all
         * of ours stood as if paused; and with the car's standing too, a tick (ours run twice a physics step, the car
         * moved every other) was "paused" every other one) */
        static uint64_t me_still_since;
        int still = mpos[0] == me_was[0] && mpos[1] == me_was[1] && mpos[2] == me_was[2];
        if (!still) me_still_since = 0;
        else if (!me_still_since) me_still_since = now;
        int paused = rme && rme == clock_racer && clock > 0 && clock == clock_was && me_still_since && now - me_still_since > 2500000;
        clock_racer = rme, clock_was = clock, memcpy(me_was, mpos, sizeof me_was);
        int lapn = tmr && tmr < RT_USER_LIMIT ? (int)xb_rd32(tmr + 0x9C) : -9;
        uint32_t evp = xb_rd32(0x592984) ? xb_rd32(xb_rd32(0x592984) + 0x318) : 0;
        uint32_t laps = evp && evp < RT_USER_LIMIT ? xb_rd32(evp + 0x24) : 0;
        /* the player's run done (+0x1B8), once its laps are all done (the event's, +0x24) */
        int done = rme && (xb_rd32(rme + 0x1B8) & 0xFF) && (laps == 0 || laps > 99 || lapn >= (int)laps) && !getenv("XBRT_MM_PHOTO");
        int why = paused ? 1 : done ? 2 : rme && (xb_rd32(rme + 0x1B8) & 0xFF) ? 3 : 0;
        if (lapn != lap_was || why != why_was) {
            fprintf(stderr, "xbrt: quick race: lap %d of %u, clock %.1f s, %s\n", lapn, laps, clock,
                    why == 1 ? "paused" : why == 2 ? "the player's race done" : why == 3 ? "marked done before its laps (ours acts on)" : "racing");
            lap_was = lapn, why_was = why;
        }
        if (paused) return;
        if (done) {
            if (tdcam_until) tdcam_end();
            rt_qr_auto = 0;
            return;
        }
    }
    qr_ticks++;
    float mp[3] = {0, 0, 0}, mdv[3] = {0, 0, 0}, mjolt = 0, mv0[3] = {0, 0, 0};
    if (me) {
        mp[0] = rdf(me + 0x14), mp[1] = rdf(me + 0x18), mp[2] = rdf(me + 0x1C);
        if (cs[im].car == me) { /* the player's own jolt this tick (a touch jolts both cars) */
            memcpy(mv0, cs[im].v, sizeof mv0); /* (its velocity before the touch: the closing speed) */
            for (int j = 0; j < 3; j++) mdv[j] = rdf(me + 0x44 + 4 * (uint32_t)j) - cs[im].v[j];
            mjolt = sqrtf(mdv[0] * mdv[0] + mdv[2] * mdv[2]) / (float)dt;
        }
    }
    int touched = 0; /* the player's knock taken back once a tick, however many cars it touched */
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i), car = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xA0) : 0;
        uint32_t timing = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0;
        if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) continue;
        int lap = (int)xb_rd32(timing + 0x9C);
        float v[3] = {rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C)}, p[3] = {rdf(car + 0x14), rdf(car + 0x18), rdf(car + 0x1C)};
        if (cs[i].car != car) { memset(&cs[i], 0, sizeof cs[i]); cs[i].car = car; memcpy(cs[i].v, v, sizeof v); memcpy(cs[i].pos, p, sizeof p); continue; }
        if (lap < 0 && rdf(timing + 0xA0) <= 0) { memcpy(cs[i].v, v, sizeof v); memcpy(cs[i].pos, p, sizeof p); continue; } /* (the grid: the race's clock not yet started) */
        static const char *photo = (const char *)1; /* XBRT_MM_PHOTO=<folder> (tools/mayhemphotos.py): a Mayhem Moment staged for
                                                     * its photographs, three times, a camera each (the user's: "a mix of
                                                     * everything but straight on"): the player's car put on the line 60 m
                                                     * before the Moment's place and driven on, a rival put by it there and
                                                     * thrown as a wall takedown throws one, and the picture saved 12 times
                                                     * as it flies, <folder>/mm<i>_<angle>_<k>.ppm, to pick from. Angles:
                                                     * 0 looking back (Y held) at the rival thrown behind; 1 and 2 the
                                                     * camera looking to the landmark's side (the right stick) at a rival
                                                     * thrown off that way just ahead and level */
        /* (XBRT_MM_PHOTO_ANGLES=5,6,7: just those, in that order; 3 and 4 the diagonals, back and ahead; 5-7 the wreck
         * camera, the camera put on the thrown rival as a takedown's is: 5 looking back across at the player's car
         * on the landmark's side, 6 the same the other side, 7 looking aside at the player's car. The game's own
         * camera view, chase, far chase or bumper, is the one the run's menu presses left it in.) */
        static int angles[16], nangles = -1, ai;
        if (nangles < 0) {
            const char *s = getenv("XBRT_MM_PHOTO_ANGLES");
            nangles = 0;
            for (; s && *s && nangles < 16; s++) if (*s >= '0' && *s <= '9') angles[nangles++] = *s - '0';
            if (!nangles) for (; nangles < 5; nangles++) angles[nangles] = nangles;
        }
        if (photo == (const char *)1) photo = getenv("XBRT_MM_PHOTO");
        if (photo && car == me && have_line) { /* (the race on: its clock started, above; the car still behind the line) */
            static int stage, target_k, shots, mi = -1;
            static float side;
            static uint64_t next_shot;
            int angle = ai < nangles ? angles[ai] : -1, wreckcam = angle >= 5;
            uint32_t race = xb_rd32(0x592984), ev = race ? xb_rd32(race + 0x318) : 0;
            int track = ev && ev < RT_USER_LIMIT ? (int)xb_rd32(ev + 0x20) : -1;
            if (mi < 0)
                for (int k = 0; k < nmm && mi < 0; k++) if (mm[k].track == track) mi = k;
            if (mi >= 0 && stage == 0 && ai < nangles) { /* the line's point nearest the place's middle (and under its top) */
                const float *zn = mm[mi].zone[0];
                float best = 1e30f, at[2] = {zn[0], zn[1]};
                /* (XBRT_MM_PHOTO_AT=x,z: the line's point nearest there instead, the landmark still the zone's: New
                 * York's Toys R Us sign is 8-20 m up, seen only from the far pass, 30 m across) */
                const char *ats = getenv("XBRT_MM_PHOTO_AT");
                if (ats) sscanf(ats, "%f,%f", &at[0], &at[1]);
                for (int k = 0; k < (int)np; k++) {
                    float ex = rdf(xs + 4 * k) - at[0], ez = rdf(zs + 4 * k) - at[1], d = ex * ex + ez * ez;
                    if (d < best && rdf(ys + 4 * k) < zn[3]) best = d, target_k = k;
                }
                respawn(car, xs, zs, ys, np, (target_k - 34 + (int)np) % (int)np); /* (30 points on: 60 m before) */
                rt_qr_auto = 1, auto_until = 0, auto_k = -1, auto_speed = 26.0f;
                stage = 1, shots = 0;
                fprintf(stderr, "xbrt: mm photo: %s, line point %d, angle %d\n", mm[mi].name, target_k, angle);
                continue;
            }
            int ahead = auto_k >= 0 ? (target_k - auto_k + (int)np) % (int)np : 1 << 30; /* (line points to the place) */
            int past = auto_k >= 0 ? (auto_k - target_k + (int)np) % (int)np : 1 << 30;
            int behind = angle == 0 || angle == 3; /* (the looks back: the rival thrown behind the player, past the place) */
            if (stage == 1 && ((behind && past >= 6 && past < 40) || (!behind && ahead <= 10))) {
                int found = 0;
                for (uint32_t j = 0, nth = 0; j < n && !found; j++) { /* a rival (another each angle): put by the player and thrown */
                    uint32_t r2 = xb_rd32(arr + 4 * j), c2 = r2 && r2 < RT_USER_LIMIT ? xb_rd32(r2 + 0xA0) : 0;
                    if (!c2 || c2 == me || c2 >= RT_USER_LIMIT || (int)j >= MAXCARS || nth++ != (uint32_t)ai) continue;
                    found = 1;
                    /* angle 0: 10 m behind the player, slower, falling back past the place; 1: 6 m ahead and thrown off to
                     * the landmark's side, the camera looking that way; 2: level with the player, the same */
                    int k2 = (auto_k + (angle == 0 ? -5 : angle == 3 ? -3 : angle == 1 || wreckcam ? 3 : angle == 4 ? 6 : 1) + (int)np) % (int)np, k3 = (k2 + 3) % (int)np;
                    respawn(c2, xs, zs, ys, np, (k2 - 4 + (int)np) % (int)np);
                    float fx = rdf(xs + 4 * k3) - rdf(xs + 4 * k2), fz = rdf(zs + 4 * k3) - rdf(zs + 4 * k2), fl = sqrtf(fx * fx + fz * fz);
                    if (fl < 0.1f) break;
                    fx /= fl, fz /= fl;
                    const float *zn = mm[mi].zone[0]; /* (thrown towards the landmark's side of the road) */
                    side = (zn[0] - rdf(xs + 4 * k2)) * fz - (zn[1] - rdf(zs + 4 * k2)) * fx >= 0 ? 1.0f : -1.0f;
                    float sx = fz * side, sz = -fx * side, fwd = behind ? 16.0f : 25.0f, lat = angle == 0 ? 6.0f : 9.0f;
                    if (angle > 0) wrf(c2 + 0x14, rdf(c2 + 0x14) + sx * 4), wrf(c2 + 0x1C, rdf(c2 + 0x1C) + sz * 4); /* (beside, a lane over) */
                    wrf(c2 + 0x44, fx * fwd + sx * lat), wrf(c2 + 0x48, 8.0f), wrf(c2 + 0x4C, fz * fwd + sz * lat);
                    cs[j].car = c2, cs[j].down_at = now, cs[j].hit_at = 0;
                    cs[j].tumble_until = now + 12000000, cs[j].spin = side * 3.0f, cs[j].spin_until = cs[j].tumble_until;
                    damage_set((int)j, c2, DMG_FULL);

                    /* the game's own looks: Y back; the right stick to the landmark's side (the free camera,
                     * rt_view_cam, moved nothing in a race) */
                    rt_photo_lookback = angle == 0 ? 1 : angle == 3 || angle == 5 ? (side > 0 ? 4 : 5) : angle == 6 ? (side > 0 ? 5 : 4) :
                        angle == 4 ? (side > 0 ? 6 : 7) : angle == 7 ? (side > 0 ? 3 : 2) : side > 0 ? 2 : 3; /* (3, 4: the diagonals, the user's) */
                    if (wreckcam && ncslot > 0) tdcam_start(c2, r2, me, auto_speed); /* (the camera on the wreck, in slow motion) */
                    stage = 2, next_shot = now + 1000000; /* (the first a moment in) */
                }
                if (!found) stage = 0, ai++; /* (no such rival: the next angle) */
            }
            if (stage == 2 && now >= next_shot && !rt_photo_path[0]) {
                snprintf((char *)rt_photo_path, sizeof rt_photo_path, "%s/mm%d_%d_%02d.ppm", photo, mi, angle, shots++);
                next_shot = now + 800000; /* (0.08 s apart: the wreck's flight) */
                if (shots == 12) {
                    rt_photo_lookback = 0;
                    if (wreckcam) tdcam_end();
                    stage = 0, ai++;
                    if (ai == nangles) fprintf(stderr, "xbrt: mm photo: done\n");
                }
            }
        }
        { /* XBRT_AUTODRIVE=<m/s> (testing: the custom tracks' audits): the player's car on the autopilot all race, along
           * the AI line at that speed, the camera behind it as when driven (XBRT_QR_ALWAYS=1 to run outside Quick Race) */
            static int autod = -1;
            if (autod < 0) autod = getenv("XBRT_AUTODRIVE") ? atoi(getenv("XBRT_AUTODRIVE")) : 0;
            if (autod > 0 && car == me && have_line && !rt_qr_auto && !tdcam_until)
                rt_qr_auto = 1, auto_until = 0, auto_k = -1, auto_speed = (float)autod;
            static int looks = -1; /* XBRT_AUTODRIVE_LOOKS=1: the camera turned round the car's looks, 1.5 s each (ahead,
                                    * back, the sides, the diagonals), for things drawn or not by the angle (the garage) */
            if (looks < 0) looks = getenv("XBRT_AUTODRIVE_LOOKS") && atoi(getenv("XBRT_AUTODRIVE_LOOKS"));
            if (looks && autod > 0 && car == me) rt_photo_lookback = (int)((rt_now_100ns() / 15000000) % 8);
        }
        if (car == me && rt_qr_auto && have_line) { /* the autopilot holds it on the line: nothing else acts on it */
            autopilot(car, xs, zs, np, dt);
            cs[i].v[0] = rdf(car + 0x44), cs[i].v[1] = rdf(car + 0x48), cs[i].v[2] = rdf(car + 0x4C);
            cs[i].still_since = 0;
            continue;
        }
        static int wallfix = -1; /* XBRT_WALL_FIX=0: off (testing: the comparison) */
        if (wallfix < 0) wallfix = !getenv("XBRT_WALL_FIX") || atoi(getenv("XBRT_WALL_FIX"));
        if (wallfix && car == me && mayhem_race && !cs[i].down_at && cs[i].car == car) {
            /* a wall (the user's, 7 Nov: "wall collision chaos when smacking/riding it on Mayhem races"): the game's own
             * knock along the ground since our last tick over 100 m/s^2 (10 g; its tyres give 1-2, a drift's up to 6), no
             * other car within 6 m: Mayhem's handling, pull and lighter fall stand down for 0.4 s and the game's physics
             * settles the contact. (Against the wall the handling put the speed back along the nose, turned the body into
             * the barrier and pulled on; the game threw the car back out, and at 80% of the pull it flew.) */
            float gx = v[0] - cs[i].v[0], gz = v[2] - cs[i].v[2], g = sqrtf(gx * gx + gz * gz) / (float)dt;
            int near_car = 0;
            for (uint32_t j = 0; j < n && !near_car; j++) {
                uint32_t r2 = xb_rd32(arr + 4 * j), c2 = r2 && r2 < RT_USER_LIMIT ? xb_rd32(r2 + 0xA0) : 0;
                if (!c2 || c2 == car || c2 >= RT_USER_LIMIT) continue;
                float ex = p[0] - rdf(c2 + 0x14), ez = p[2] - rdf(c2 + 0x1C);
                near_car = ex * ex + ez * ez < 36;
            }
            /* (the bar: 3x the car's own knocks of the last ~2 s, never under 100: a race car's tyres alone gave 100-210
             * m/s^2 on Laguna in the Championship, so every drift ended "on a wall" at once and the handling stood down
             * round the lap, the user's "brake-to-drift/handling feels off"; a road car's stay under 35, its bar 100.
             * A wall's own knock is over 300, its log line's.
             * It learned only from the knocks under the bar, so a race car's never raised it: still 100, and in the
             * Championship of 7 Nov every drift ended "on a wall" the tick it began, 40 times a corner, the user's "still
             * feels completely different". The knock measured is against the speed WE wrote last tick: in a drift the
             * game's tyres pushing back on our slide, 114-171 in a race car. Now it learns from every knock, clipped at
             * 100 (the bar 100-300), and while the drift is ours (or easing out) the bar is 300: a wall in a drift
             * is the drift's own "knock" too, a fifth of the speed gone) */
            static float gbase = 30.0f;
            if (lap < 0) gbase = 30.0f;
            float bar = gbase * 3.0f < 100.0f ? 100.0f : gbase * 3.0f;
            /* (and the tick a drift begins, brake and stick: the log's first "wall", 171, came the tick before the drift's in) */
            int drifty = me_drift || (rt_pad_brake > 0.06f && (rt_pad_steer > 0.3f || rt_pad_steer < -0.3f));
            if (drifty && bar < 300.0f) bar = 300.0f;
            gbase += ((g < 100.0f ? g : 100.0f) - gbase) * (1.0f - expf(-(float)dt / 2.0f));
            if (g > bar && !near_car && lap >= 0) {
                static int wlog = -1;
                if (wlog < 0) wlog = getenv("XBRT_WALLLOG") != NULL;
                if (wlog || cs[i].wall_until < now) fprintf(stderr, "xbrt: mayhem: the player's car on a wall (%.0f m/s^2, the bar %.0f): ours stood down at %.3f s\n", g, bar, now / 1e7);
                cs[i].wall_until = now + 4000000;
            }
        }
        int on_wall = car == me && cs[i].wall_until > now;
        if (car == me && mayhem_race && getenv("XBRT_CHAOS")) { /* testing: the player's car tilted (up under 0.85), bouncing
                                                                  * (up or down over 3 m/s), spinning (over 2.5 rad/s), ticks a 30 s */
            static int tipped, flying, spinning, ticks; static uint64_t next;
            float a0 = rdf(car + 0x50), a1 = rdf(car + 0x54), a2 = rdf(car + 0x58);
            ticks++, tipped += rdf(car + 0x30) < 0.85f, flying += v[1] > 3 || v[1] < -3, spinning += a0 * a0 + a1 * a1 + a2 * a2 > 6.25f;
            if (!next) next = now + 300000000;
            else if (now > next) fprintf(stderr, "xbrt: chaos: %d of %d ticks tilted, %d bouncing, %d spinning\n", tipped, ticks, flying, spinning), tipped = flying = spinning = ticks = 0, next = now + 300000000;
        }
        if (mods & QR_LOWGRAVITY) v[1] += (float)(9.81 * 0.6 * dt), wrf(car + 0x48, v[1]); /* (60% of the pull given back) */
        else if (mayhem_race && !on_wall && (car == me || cs[i].tumble_until || cs[i].down_at)) v[1] += (float)(9.81 * 0.2 * dt), wrf(car + 0x48, v[1]);
        /* (Mayhem's over-the-top physics: 80% of the pull, longer flights: the player's car, and a rival only as a wreck,
         * thrown. On every rival it took a fifth of their tyres' load, and with the push below they reached the bends
         * too fast and stopped at the walls: 14-18 m/s their median on Tokyo, 19-22 without Mayhem, the tests of 5 Nov) */
        if (mods & QR_SLIPSTREAM) { /* a tow from any car close ahead, in line */
            float sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
            for (uint32_t j = 0; j < n && sp > 10; j++) {
                uint32_t r2 = xb_rd32(arr + 4 * j), c2 = r2 && r2 < RT_USER_LIMIT ? xb_rd32(r2 + 0xA0) : 0;
                if (!c2 || c2 == car || c2 >= RT_USER_LIMIT) continue;
                float dx = rdf(c2 + 0x14) - p[0], dz = rdf(c2 + 0x1C) - p[2], d = sqrtf(dx * dx + dz * dz);
                if (d < 4 || d > 25) continue;
                float along = (dx * v[0] + dz * v[2]) / (d * sp);
                if (along > 0.97f) {
                    float a = (float)(3.0 * dt) * (1 - d / 25);
                    v[0] += v[0] / sp * a * 1.0f, v[2] += v[2] / sp * a * 1.0f;
                    wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                    break;
                }
            }
        }
        if ((mods & QR_NITRO) && car == me) {
            /* the boost: hold R3 (N). Mayhem's is stronger and fills itself (slowly, faster in a drift, half a tank a
             * takedown): an arcade racer's nitrous, its flame at the exhaust (rt_qr_flame, glover.c) */
            static int dry; /* emptied: none until let go and a quarter back (held on empty, it refilled a tick and pushed again) */
            float push = mayhem_race ? 13.0f : 9.0f, last = mayhem_race ? 3.0f : 4.0f; /* m/s^2; seconds a tank lasts */
            if (tank <= 0) dry = 1;
            if (dry && !nitro_y && tank >= 0.25f) dry = 0;
            if (nitro_y && !dry && !cs[i].down_at) {
                float fx = rdf(car + 0x38), fz = rdf(car + 0x40);
                v[0] += fx * (float)(push * dt), v[2] += fz * (float)(push * dt);
                wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                tank -= (float)(dt / last);
                if (tank < 0) tank = 0;
                flame_until = rt_now_100ns() + 1500000, flame_car = car;
            } else if (!nitro_y && tank < 1) tank += (float)(dt / (mayhem_race ? 40.0 : 30.0)); /* filled again, while not held */
        }
        if (car == me && mayhem_race) {
            /* Mayhem's camera: the game's own (the user's, 5 Nov: "return the camera to normal functionality"; the look led
             * round the turns, before it kept behind the rear bumper, both on the right stick, taken out). The near chase
             * view stays forced (the grid's view survey). */
            rt_drift_look = 0;
        }
        if (car == me) me_drift = 0; /* (set again below while drifting or easing out) */
        /* on the ground: the speed off the road's face (the car's up, the pose's second row) small; in the air the game's
         * own, falling at Mayhem's 80%. (The world's up once: the user's "brake to drift stops working on up/downhill
         * roads": 30 m/s down a 8% grade is -2.4 m/s, steeper ones were "in the air") */
        float vn = v[0] * rdf(car + 0x2C) + v[1] * rdf(car + 0x30) + v[2] * rdf(car + 0x34);
        if (mayhem_race && car == me && lap >= 0 && !cs[i].down_at && rdf(car + 0x30) > 0.5f && vn < 3.0f && vn > -4.5f) {
            /* Mayhem's handling (the user's: an arcade racer's, "grippy but not insane", brake to drift), on top of
             * the game's physics, the player's car only, nothing of the car's data changed:
             *  - grip: most of a slide across the heading taken out (a third a 1/8 s), so it goes where it points;
             *  - turn: a little more from the stick, rising with speed to 25 m/s, the speed carried round;
             *  - more pull from the throttle, a firmer brake (not in a drift), a little held down over crests;
             *  - drift (rewritten after the user's "brake to drift does not work at all": the game's tyres took a slide
             *    out at about 1 g a tick and our 0.9/s let-off was nothing against it, the brake held slowed it under
             *    12 m/s, and the stick through the middle, as in any counter-steer, ended it): a tap of the brake while
             *    turned in over 15 m/s and the drift is ours alone until it ends: the heading turned by us (into the
             *    corner 0.6 rad/s and up to 0.9 more with the stick held in), the game's own turn
             *    taken back out, the way it goes trailing the heading (a third of the slip closed a 1/9 s: some 20-40
             *    degrees held), the speed ours (the throttle holds it, off it a gentle loss, the brake 6 m/s^2), the
             *    boost filling; the stick let go (or out of the corner) ends it and the car shoots out the way it
             *    points with all of the speed (the user's: "grip is never lost"), as do under 10 m/s or a knock (a wall, a car: 15% of the speed gone in a tick; the jolt over 60 m/s^2 fired on
             *    the game's own tyres every tick). */
            static int drifting;
            static float drift_dir, dsp, vdx, vdz, lhx, lhz;
            static uint64_t straight_since, out_until; /* out_until: the way out of a drift, blended (the user's "smoother") */
            static uint32_t drift_car;
            static uint64_t drift_tick;
            /* a new car, or the handling off for over 0.4 s (the autopilot, a wreck, a respawn) ends it; a shorter gap (a
             * bump, a crest's hop) is carried over, the heading taken afresh. (It once ended on any missed tick, and on
             * the car 25 m off the AI's line, "stuck" to the respawner: the user's drifts that stopped working) */
            if (drift_car != car || qr_ticks - drift_tick > 24) drifting = 0, out_until = 0, drift_car = car;
            int resumed = drift_tick + 1 != qr_ticks;
            drift_tick = qr_ticks;
            float hx = rdf(car + 0x38), hz = rdf(car + 0x40), hl = sqrtf(hx * hx + hz * hz);
            if (resumed && hl > 0.1f) lhx = hx / hl, lhz = hz / hl;
            if (hl > 0.1f) {
                hx /= hl, hz /= hl;
                float rx = hz, rz = -hx; /* (its right: the pose's first row) */
                float vf = v[0] * hx + v[2] * hz, vl = v[0] * rx + v[2] * rz, sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
                float steer = rt_pad_steer, thr = rt_pad_throttle, brk = rt_pad_brake;
                float as = steer < 0 ? -steer : steer;
                static int dlog = -1;
                if (dlog < 0) dlog = getenv("XBRT_DRIFTLOG") != NULL;
                if (!drifting && brk > 0.06f && as > 0.3f && vf > 15 && sp > 1) { /* (a tap or a light hold: the user's) */
                    drifting = 1, drift_dir = steer > 0 ? 1.0f : -1.0f, dsp = sp, vdx = v[0] / sp, vdz = v[2] / sp, straight_since = 0;
                    lhx = hx, lhz = hz;
                    fprintf(stderr, "xbrt: drift: in (%s, %.1f m/s)\n", drift_dir > 0 ? "right" : "left", sp);
                }
                if (drifting) {
                    /* the game's own turn since the last tick taken out (its tyres pull the nose straight) */
                    float gturn = atan2f(lhz * hx - lhx * hz, lhx * hx + lhz * hz); /* (+: to the right, as yaw()) */
                    float into = steer * drift_dir > 0 ? steer * drift_dir : 0;
                    float rot = drift_dir * (0.6f + 0.9f * into) * (dsp > 20 ? 1.0f : dsp / 20);
                    yaw(car, rot * (float)dt - gturn);
                    hx = rdf(car + 0x38), hz = rdf(car + 0x40), hl = sqrtf(hx * hx + hz * hz);
                    if (hl > 0.1f) hx /= hl, hz /= hl;
                    lhx = hx, lhz = hz;
                    /* the way it goes, turned towards the heading by a share of the slip (at most 65 degrees behind) */
                    float slip = atan2f(vdz * hx - vdx * hz, vdx * hx + vdz * hz); /* (heading from the way: +: right) */
                    float a = slip * (1 - expf(-3.0f * (float)dt));
                    if (slip - a > 1.13f) a = slip - 1.13f;
                    if (slip - a < -1.13f) a = slip + 1.13f;
                    float c = cosf(a), s = sinf(a), nx = vdx * c + vdz * s, nz = -vdx * s + vdz * c;
                    vdx = nx, vdz = nz;
                    dsp += (float)dt * (thr > 0.05f ? (dsp < 90 ? 0.5f * MAYHEM_PULL * thr : 0) : -1.5f) - (float)dt * DRIFT_BRAKE * (brk > 0.25f ? brk : 0);
                    /* (the brake: the drift's speed is ours, the game's brakes can't slow it: 6 m/s^2 at full was the
                     * user's 'braking ineffective'; DRIFT_BRAKE, as on the road; a light touch, the tap that starts a
                     * drift, takes nothing) */
                    if (mods & QR_NITRO) tank = tank + (float)(dt / 4.0) > 1 ? 1 : tank + (float)(dt / 4.0); /* (a drift fills the boost: 4 s a tank) */
                    (void)straight_since;
                    me_drift = 1;
                    /* a knock: a fifth of the speed gone in a tick (15% and 1 m/s fired on a wall's brush, a kerb, a
                     * landing; a carried-over gap's speed is the game's, no knock) */
                    const char *why = on_wall ? "wall" : dsp < 10 ? "slow" : !resumed && sp < dsp * 0.8f - 1.5f ? "knock" : steer * drift_dir < 0.15f ? "let go" : NULL;
                    if (dlog && (int)(now / 2500000) != (int)((now - (uint64_t)(dt * 1e7)) / 2500000))
                        fprintf(stderr, "xbrt: drift: slip %.0f deg, speed %.1f, turn %.2f (the game's %.2f) rad/s, steer %.2f, ang +0x50 %.2f %.2f %.2f\n",
                                slip * 57.3f, dsp, rot, gturn / dt, steer, rdf(car + 0x50), rdf(car + 0x54), rdf(car + 0x58));
                    if (why) {
                        drifting = 0;
                        fprintf(stderr, "xbrt: drift: out (%s)\n", why);
                        if (why[0] == 'l') out_until = now + DRIFT_OUT; /* shot out: the speed kept, swung to the way it points over DRIFT_OUT (the user's: grip never lost; at once it jerked; at 0.3 s 'so sudden') */
                    } else {
                        v[0] = vdx * dsp, v[2] = vdz * dsp;
                        v[1] -= (float)(2.5 * dt);
                        wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                    }
                } else if (out_until > now && dsp > 1 && !on_wall) {
                    /* out of a drift: the way it goes swung to the heading (half of the slip a 1/16 s), all of the
                     * drift's speed kept and more with the throttle; the stick steers as on the road */
                    float slip = atan2f(vdz * hx - vdx * hz, vdx * hx + vdz * hz);
                    float a = slip * (1 - expf(-DRIFT_EASE * (float)dt)), c = cosf(a), s = sinf(a); /* (eased: the user's 'let the car ease a bit') */
                    me_drift = 1;
                    float nx = vdx * c + vdz * s, nz = -vdx * s + vdz * c;
                    vdx = nx, vdz = nz;
                    if (thr > 0.05f && dsp < 90) dsp += MAYHEM_PULL * thr * (float)dt;
                    if (brk > 0.05f) dsp -= 14.0f * brk * (float)dt;
                    float turn = steer * 0.55f * (dsp > 25 ? 1.0f : dsp / 25);
                    if (turn > 0.001f || turn < -0.001f) {
                        yaw(car, turn * (float)dt);
                        float tc = cosf(turn * (float)dt), ts = sinf(turn * (float)dt), tx = vdx * tc + vdz * ts, tz = -vdx * ts + vdz * tc;
                        vdx = tx, vdz = tz;
                    }
                    if (!resumed && sp < dsp * 0.8f - 1.5f) out_until = 0; /* (a knock: the game's again) */
                    else {
                        v[0] = vdx * dsp, v[2] = vdz * dsp;
                        v[1] -= (float)(2.5 * dt);
                        wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                    }
                } else {
                    float ramp = vf > 25 ? 1.0f : vf > 0 ? vf / 25 : 0;
                    float turn = on_wall ? 0 : steer * 0.55f * ramp; /* rad/s (none on a wall: the body turned into the barrier) */
                    if (turn > 0.001f || turn < -0.001f) {
                        yaw(car, turn * (float)dt);
                        hx = rdf(car + 0x38), hz = rdf(car + 0x40), hl = sqrtf(hx * hx + hz * hz);
                        if (hl > 0.1f) hx /= hl, hz /= hl;
                        rx = hz, rz = -hx; /* (vf and vl kept: the velocity turns with the car, the speed carried round) */
                    }
                    vl *= expf(-3.2f * (float)dt);
                    if (!on_wall && thr > 0.05f && vf > -1 && vf < 95) vf += MAYHEM_PULL * thr * (float)dt;
                    if (brk > 0.05f && vf > 0) vf -= (vf < 14.0f * brk * (float)dt ? vf : 14.0f * brk * (float)dt); /* (14 m/s^2 on the game's: the user's "more effective"; was 8) */
                    v[0] = hx * vf + rx * vl, v[2] = hz * vf + rz * vl;
                    if (!on_wall) v[1] -= (float)(2.5 * dt); /* (planted; not on a wall: pressed down against it, it bounced) */
                    wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                }
            }
        }
        int hit_lately = cs[i].hit_at && cs[i].impact > 0 && now - cs[i].hit_at < 30000000; /* (the player's hit, under 3 s ago) */
        if (MAYHEM_RIVAL_NUDGES && mayhem_race && car != me && me && lap >= 0 && !cs[i].down_at && !hit_lately && rdf(car + 0x30) > 0.7f && have_line) {
            /* Mayhem's rivals: the game's own driving (the user's, 5 Nov: "return their handling model, just make them
             * slightly faster", after the rails and the corner assist of 4 Nov), faster (a push along their heading,
             * AI_PUSH m/s^2, under AI_PUSH_TOP m/s: 3 and 85 before) and at the player (within 14 m and not far ahead of
             * it, a pull across, 1.5 m/s^2), both only where the line runs nearly straight and the rival is on it (the
             * user's: "AI seems to go off their lines": everywhere, they overshot the corners); off its line by 3 m or
             * more, a pull back to it. Not for 3 s after the player's hit (the audit of the user's "takedowns are barely
             * registering": it steered a slammed rival back before it could crash) */
            int lk = nearest(xs, zs, np, p[0], p[2]);
            float lxp = rdf(xs + 4 * lk) - p[0], lzp = rdf(zs + 4 * lk) - p[2], loff = sqrtf(lxp * lxp + lzp * lzp);
            int straight = line_turn(xs, zs, np, lk) < 0.12f && loff < 4;
            float hx = rdf(car + 0x38), hz = rdf(car + 0x40), sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
            if (straight && sp > 8 && sp < AI_PUSH_TOP) v[0] += hx * (float)(AI_PUSH * dt), v[2] += hz * (float)(AI_PUSH * dt);
            float ax = mp[0] - p[0], az = mp[2] - p[2], d = sqrtf(ax * ax + az * az), along = ax * hx + az * hz;
            float lx = ax - along * hx, lz = az - along * hz, ll = sqrtf(lx * lx + lz * lz);
            if (straight && d > 2 && d < 14 && sp > 12 && along > -6 && ll > 0.3f) v[0] += lx / ll * (float)(1.5 * dt), v[2] += lz / ll * (float)(1.5 * dt);
            if (loff > 3 && loff < 25) v[0] += lxp / loff * (float)(2.0 * dt), v[2] += lzp / loff * (float)(2.0 * dt);
            wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
        }
        if (mods & QR_TAKEDOWNS) {
            /* After Burnout 3 (the user's reference video): a slam from the side throws the rival sideways across the
             * road, a shunt from behind punts it on, both turning it out of grip; if it then hits a wall, stops or
             * leaves the road within 3 s it is a takedown (banner, count, half a nitro tank) and the wreck comes back
             * behind the player 2 s later. Your own car, stuck 3 s: back on the line. Along the ground: no hop. */
            float dv[3] = {v[0] - cs[i].v[0], v[1] - cs[i].v[1], v[2] - cs[i].v[2]};
            float jolt = sqrtf(dv[0] * dv[0] + dv[1] * dv[1] + dv[2] * dv[2]) / (float)dt;
            float dx = p[0] - mp[0], dz = p[2] - mp[2], dd = sqrtf(dx * dx + dz * dz);
            int fresh = cs[i].hit_at && now - cs[i].hit_at < 30000000; /* the player's hit, under 3 s ago */
            /* a touch: both cars jolted this tick, side by side or nose to tail (the user's: it fired without
             * one, on a rival's own knock near the player) */
            int touch = !photo && car != me && me && dd < 6.0f && dd > 0.1f && jolt > 40 && mjolt > 25; /* (none in the photo runs: a real takedown there froze the shots) */ /* (6 m: nose to tail the middles are 4.5 apart; 4 missed most shunts) */
            if (touch) { /* and pushed apart along the line between them, as a collision does: the rival away from the
                          * player, the player back from it (the user's: no takedown without contact; two cars side by
                          * side each striking a wall or a kerb jolt too, but not so) */
                float ux = dx / dd, uz = dz / dd;
                touch = dv[0] * ux + dv[2] * uz > 0.5f && mdv[0] * ux + mdv[2] * uz < -0.3f;
            }
            /* how hard: the speed the two closed at just before (the player's and its velocities of the tick before,
             * along the line between them). Resistance (the user's): a nudge under 4.5 m/s is the game's own touch,
             * and above it the throw and spin grow with the impact, full at 18 m/s, so neither car flies off light
             * (and halved again: "very easy to move opponents around") */
            float closing = touch ? ((mv0[0] - cs[i].v[0]) * dx + (mv0[2] - cs[i].v[2]) * dz) / dd : 0;
            int theirs = 0; /* Mayhem: the rival hit the player (it closed faster), not the player it */
            if (touch && closing >= 4.5f && mayhem_race && im >= 0 && now - cs[i].hit_at > 10000000 && !cs[i].down_at) {
                float ux = dx / dd, uz = dz / dd;
                theirs = -(cs[i].v[0] * ux + cs[i].v[2] * uz) > mv0[0] * ux + mv0[2] * uz;
            }
            if (theirs) { /* the player slammed: thrown away from the rival, out of grip; a takedown if a wall or a stop follows */
                float ux = dx / dd, uz = dz / dd, s = closing / 18 > 1 ? 1 : closing / 18, w[3];
                (void)w;
                cs[im].push[0] = -ux * 2.5f * s, cs[im].push[1] = -uz * 2.5f * s, cs[im].push_until = now + 2000000; /* (over 0.2 s) */
                cs[im].hit_at = now, cs[im].impact = closing, cs[im].kind = 1;
                cs[im].spin = (rand() & 1 ? 1 : -1) * 1.5f * s, cs[im].spin_until = now + 5000000;
                cs[i].hit_at = now, cs[i].impact = 0; /* (its own crash after is no takedown of the player's) */
                fresh = 0;
                say("SLAMMED!");
            } else if (touch && closing >= 4.5f && now - cs[i].hit_at > 10000000 && !cs[i].down_at) {
                float fx = rdf(me + 0x38), fz = rdf(me + 0x40), ux = dx / dd, uz = dz / dd; /* the player's heading; the way to the rival */
                float ahead = ux * fx + uz * fz, s = closing / 18 > 1 ? 1 : closing / 18;
                float big = mayhem_race ? 1.8f : 1.0f, spinx = mayhem_race ? 1.6f : 1.0f; /* (Mayhem's over the top: thrown further, spun more) */
                if (ahead > 0.8f) { /* a shunt: punted on, along the player's heading */
                    cs[i].kind = 2;
                    cs[i].push[0] = fx * 1.5f * s * big, cs[i].push[1] = fz * 1.5f * s * big;
                    cs[i].spin = (rand() & 1 ? 1 : -1) * 0.8f * s * spinx;
                    say("SHUNT!");
                } else { /* a slam: across, away from the player (the side of the heading it is on) */
                    float lx = ux - ahead * fx, lz = uz - ahead * fz, ll = sqrtf(lx * lx + lz * lz);
                    if (ll > 0.01f) lx /= ll, lz /= ll;
                    cs[i].kind = 1;
                    cs[i].push[0] = lx * 2 * s * big, cs[i].push[1] = lz * 2 * s * big;
                    cs[i].spin = (lx * fz - lz * fx > 0 ? 1 : -1) * 1.2f * s * spinx; /* (its nose turned towards where it is thrown) */
                    say("SLAM!");
                }
                cs[i].impact = closing;
                cs[i].push_until = now + 2000000; /* (the shove over 0.2 s, not at once: the user's "smoother, same weight") */
                cs[i].hit_at = now, cs[i].spin_until = now + 5000000;
                fresh = 0; /* (this tick's jolt is the hit, not a wall) */
                if (!touched) { /* the player's car heavier: 60% of the knock it took given back (the user's: "less recoil";
                                 * 30% bounced it back off, half earlier let it shove through when the rivals were lighter) */
                    touched = 1;
                    float w[3];
                    for (int j = 0; j < 3; j++) w[j] = rdf(me + 0x44 + 4 * (uint32_t)j) - 0.6f * mdv[j];
                    wrf(me + 0x44, w[0]), wrf(me + 0x4C, w[2]); /* (not the up: no lift) */
                    if (im >= 0 && cs[im].car == me) cs[im].v[0] = w[0], cs[im].v[2] = w[2];
                }
            }
            if (cs[i].push_until > now) { /* a hit's shove, a share a tick */
                v[0] += cs[i].push[0] * (float)(dt / 0.2), v[2] += cs[i].push[1] * (float)(dt / 0.2);
                wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
            }
            if (cs[i].spin_until > now) yaw(car, cs[i].spin * (float)dt);
            float sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
            int k = have_line ? nearest(xs, zs, np, p[0], p[2]) : -1;
            float off = 0;
            if (k >= 0) { float lx = rdf(xs + 4 * k) - p[0], lz = rdf(zs + 4 * k) - p[2]; off = sqrtf(lx * lx + lz * lz); }
            int stuck = sp < 2.0f || off > 25.0f || rdf(car + 0x30) < 0.3f; /* (stopped, far off the line, or on its side) */
            float flat = sqrtf(dv[0] * dv[0] + dv[2] * dv[2]) / (float)dt; /* (along the ground: a landing is no wall) */
            /* a wall: a hard knock with no other car within 5 m (so not a car's), soon after the hit but not the hit's
             * own tick (the user's: "wall takedowns should only happen if they hit a wall") */
            int car_near = 0; /* a car within 5 m it was knocked away from (the knock that car's); a knock towards one is
                               * a wall's (the audit: a rival pinned on the wall by the player never counted, the player near) */
            float fl = sqrtf(dv[0] * dv[0] + dv[2] * dv[2]);
            for (uint32_t j = 0; j < n && !car_near && fl > 1e-4f; j++) {
                uint32_t r2 = xb_rd32(arr + 4 * j), c2 = r2 && r2 < RT_USER_LIMIT ? xb_rd32(r2 + 0xA0) : 0;
                if (!c2 || c2 == car || c2 >= RT_USER_LIMIT) continue;
                float ex = p[0] - rdf(c2 + 0x14), ez = p[2] - rdf(c2 + 0x1C), el = sqrtf(ex * ex + ez * ez);
                car_near = el < 5 && el > 0.01f && (dv[0] * ex + dv[2] * ez) / el > 0.3f * fl;
            }
            int wall = fresh && flat > 150 && !car_near && now - cs[i].hit_at > 1500000;
            /* a crash: rolled onto its side or roof, or spun to a stop (not merely shoved wide: those counted, the
             * user's "takedowns are a little buggy") */
            /* or spun out (the audit: a rival spun round and still rolling never counted): its nose over 90 degrees off
             * the way it goes, or over 55 for 0.4 s */
            float hx2 = rdf(car + 0x38), hz2 = rdf(car + 0x40), hl2 = sqrtf(hx2 * hx2 + hz2 * hz2);
            float hv = sp > 4 && hl2 > 0.1f ? (hx2 * v[0] + hz2 * v[2]) / (hl2 * sp) : 1;
            if (hv < 0.57f) { if (!cs[i].spun_since) cs[i].spun_since = now; }
            else cs[i].spun_since = 0;
            int spun = hv < 0 || (cs[i].spun_since && now - cs[i].spun_since > 4000000);
            if (car == me && me_drift) spun = 0; /* (the player's drift is no spin: held 55 degrees across, a rival's knock
                                                  * under 3 s before had it "TAKEN DOWN" mid-drift, the drift lost) */
            int crashed = sp < 3.0f || rdf(car + 0x30) < 0.3f || spun;
            if (car == me && mayhem_race && fresh && cs[i].impact >= 9.0f && !cs[i].down_at && (wall || crashed)) {
                /* Mayhem: the player taken down: wrecked, slow motion on its own crash (the camera already on it), then
                 * back on the line ahead, repaired (below) */
                cs[i].down_at = now;
                say("TAKEN DOWN!");
                fprintf(stderr, "xbrt: mayhem: the player taken down (%s)\n", wall ? "wall" : "stopped");
                damage_set((int)i, car, DMG_FULL);
                tdcam_start(car, r, me, 0);
            }
            /* a takedown only after a real impact (the user's: "a few where it was too soft"): the player's hit at
             * 7.5 m/s (17 mph) or more closing (9 before the audit: with the other fixes it barely registered), and the
             * wall's knock over 150 m/s^2 */
            static int tdlog = -1;
            if (tdlog < 0) tdlog = getenv("XBRT_TDLOG") != NULL;
            if (tdlog && car != me && (touch || (fresh && (wall || crashed || flat > 100))))
                fprintf(stderr, "xbrt: td: racer %u dd %.1f jolt %.0f/%.0f touch %d closing %.1f impact %.1f flat %.0f near %d sp %.1f hv %.2f wall %d crashed %d\n",
                        i, dd, jolt, mjolt, touch, closing, cs[i].impact, flat, car_near, sp, hv, wall, crashed);
            if (car != me && fresh && cs[i].impact >= 7.5f && !cs[i].down_at && (wall || crashed)) {
                cs[i].down_at = now;
                takedowns++;
                tank = tank + 0.5f > 1 ? 1 : tank + 0.5f; /* (a takedown fills the boost, as Burnout's) */
                int moment = mayhem_race && mayhem_moment(p[0], p[1], p[2]); /* (a Mayhem Moment's place: its own banner, glover.c) */
                say(moment ? "MAYHEM MOMENT!" : wall ? "WALL TAKEDOWN!" : "TAKEDOWN!");
                if (moment) tank = 1; /* (a full boost) */
                fprintf(stderr, "xbrt: quick race: takedown %d (racer %u, %s) at %.3f s\n", takedowns, i, wall ? "wall" : rdf(car + 0x30) < 0.3f ? "rolled" : "stopped", rt_now_100ns() / 1e7);
                tdcam_start(car, r, me, sqrtf(mv0[0] * mv0[0] + mv0[2] * mv0[2])); /* the camera on the wreck, slowed, the player's car on the line */
                damage_set((int)i, car, DMG_FULL); /* (wrecked; repaired on its respawn) */
                if (wall) { /* blown up (the user's: "explodes" on the wall): thrown up off the wall, rolling, for 1.2 s */
                    v[1] += mayhem_race ? 11.0f : 7.0f, v[0] -= dv[0] * 0.3f, v[2] -= dv[2] * 0.3f; /* (Mayhem's thrown higher) */
                    wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                    cs[i].tumble_until = now + 12000000, cs[i].spin = (rand() & 1 ? 1 : -1) * 4.0f, cs[i].spin_until = cs[i].tumble_until;
                }
            }
            if (cs[i].tumble_until > now) roll(car, 6.0f * (float)dt);
            if (stuck) { if (!cs[i].still_since) cs[i].still_since = now; }
            else cs[i].still_since = 0;
            if (cs[i].down_at && !stuck && !cs[i].tumble_until && now - cs[i].down_at > 30000000) /* (it drove on: in the race again, */
                cs[i].down_at = 0, damage_set((int)i, car, 0);                                     /* repaired: left wrecked, it limped */
                                                                                                    /* at walking pace all race, 5 Nov) */
            uint64_t wait = cs[i].down_at ? 20000000 : 30000000; /* a wreck 2 s, any other car 3 s */
            int blown = cs[i].tumble_until && now - cs[i].down_at > 25000000; /* a blown-up wreck: gone 2.5 s on, landed or not */
            int mine_down = car == me && cs[i].down_at && now - cs[i].down_at > 20000000; /* (Mayhem: the player's wreck, 2 s on) */
            static int no_ai_respawn = -1; /* XBRT_NO_AI_RESPAWN=1 (testing): a stuck rival left to the game */
            if (no_ai_respawn < 0) no_ai_respawn = getenv("XBRT_NO_AI_RESPAWN") != NULL;
            if (no_ai_respawn && car != me && !cs[i].down_at) stuck = 0;
            if (((stuck && cs[i].still_since && now - cs[i].still_since > wait) || blown || mine_down) && k >= 0) {
                int at = k;
                if (cs[i].down_at && car != me && me) at = behind(xs, zs, np, nearest(xs, zs, np, mp[0], mp[2]), 60); /* the wreck: back behind the player */
                respawn(car, xs, zs, ys, np, at);
                if (cs[i].down_at) damage_set((int)i, car, 0); /* (the wreck back as new) */
                if (cs[i].down_at && car != me) cs[i].chase_until = now + 200000000; /* then a hard chase back to the player, up to 20 s */
                cs[i].still_since = cs[i].down_at = cs[i].spin_until = cs[i].tumble_until = 0;
                if (car == me) say("RESPAWN");
                fprintf(stderr, "xbrt: quick race: racer %u respawned at line point %d (%s) at %.3f s\n", i, at, car == me ? "the player" : "an opponent", rt_now_100ns() / 1e7);
                v[0] = rdf(car + 0x44), v[1] = rdf(car + 0x48), v[2] = rdf(car + 0x4C);
            }
            if (cs[i].chase_until > now && me) { /* rubber band: pushed hard along its heading while the player is ahead and over 25 m off */
                float hx = rdf(car + 0x38), hz = rdf(car + 0x40), ax = mp[0] - p[0], az = mp[2] - p[2], d = sqrtf(ax * ax + az * az);
                float msp = sqrtf(rdf(me + 0x44) * rdf(me + 0x44) + rdf(me + 0x4C) * rdf(me + 0x4C)), csp = sqrtf(v[0] * v[0] + v[2] * v[2]);
                if (d < 25 || ax * hx + az * hz < 0) cs[i].chase_until = 0; /* caught up, or past: racing as before */
                else if (csp < msp + 15 && k >= 0 && line_turn(xs, zs, np, k) < 0.12f) { /* up to 15 m/s faster than the player, on the straights (it overshot the corners) */
                    v[0] += hx * (float)(8.0 * dt), v[2] += hz * (float)(8.0 * dt);
                    wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                }
            }
        }
        memcpy(cs[i].v, v, sizeof v);
        memcpy(cs[i].pos, p, sizeof p);
    }
}

/* An arcade event's record (as the game parses arcade\Ser*.xml: +0x0C the leaderboard, 4000; +0x10 its
 * ordinal; +0x14 its name's string id; +0x20 the track's ordinal; +0x24 the laps; +0x2C 1.0; +0x34 its
 * display name), found by its name's string id in RAM: up to max of them into out, how many. */
static int find_events(uint32_t textid, uint32_t *out, int max) {
    /* the game's committed allocations only (as nv2a.c's zone scan): read, a free page is committed on the fault
     * (mem.c), and a scan of the whole 2 GB stalled the game for seconds and the menu music never came back */
    int n = 0;
    uint32_t at = RT_USER_BASE, b, sz, pr, st;
    while (at < RT_USER_LIMIT && n < max) {
        if (!rt_user_query(at, &b, &sz, &pr, &st) || !sz) {
            at = b + (sz ? sz : 0x1000);
            continue;
        }
        if (at < b) at = b;
        uint32_t end = b + sz;
        if (st == 0x1000) /* MEM_COMMIT */
            for (uint32_t a = at; a + 0x40 <= end && n < max; a += 4)
                if (xb_rd32(a + 0x14) == textid && xb_rd32(a + 0x0C) == 4000 && xb_rd32(a + 0x2C) == 0x3F800000u && xb_rd32(a + 0x24) - 1 < 99)
                    out[n++] = a;
        at = end;
    }
    return n;
}

static uint32_t find_event(uint32_t textid) {
    uint32_t a;
    return find_events(textid, &a, 1) ? a : 0;
}

/* find_event, remembered (a scan at most every 3 s): the pad asks each poll. */
static uint32_t find_event_cached(uint32_t textid) {
    static uint32_t at;
    static uint64_t next;
    if (at && xb_rd32(at + 0x14) == textid && xb_rd32(at + 0x0C) == 4000) return at;
    uint64_t now = rt_now_100ns();
    if (now < next) return 0;
    next = now + 30000000;
    return at = find_event(textid);
}

/* The field: the opponents. The event's AIField is parsed (f_0007D470, its NumAICars at +4) into the event's
 * record at +0x26C, so the count is the record's +0x270 (7 on the disc's arcade events). */
#define QR_FIELD_AT 0x270
static void rt_qr_set_field(int n) {
    for (int i = 0; i < nqe; i++) {
        uint32_t was = xb_rd32(qr_events[i] + QR_FIELD_AT);
        if (was < 1 || was > 15) { fprintf(stderr, "xbrt: quick race: copy %d: the field's count not where expected (+%x = %u): left\n", i, QR_FIELD_AT, was); continue; }
        xb_wr32(qr_events[i] + QR_FIELD_AT, (uint32_t)n);
        fprintf(stderr, "xbrt: quick race: copy %d: opponents %u -> %d\n", i, was, n);
    }
}

/* The Quick Race event set to a track, laps (the field: rt_qr_set_field), in every copy of its record in RAM:
 * the user's New York Circuit was written into one, and the race ran elsewhere. 1 if any. */
int rt_qr_apply(uint32_t textid, uint32_t track, uint32_t laps) {
    nqe = find_events(textid, qr_events, MAXQE);
    if (!nqe) return 0;
    for (int i = 0; i < nqe; i++) {
        xb_wr32(qr_events[i] + 0x20, track), xb_wr32(qr_events[i] + 0x24, laps);
        fprintf(stderr, "xbrt: quick race: event %08x (name %u, copy %d of %d) set to track %u, %u laps\n", qr_events[i], textid, i, nqe, track, laps);
    }
    qr_event = qr_events[0];
    return 1;
}

/* Testing: XBRT_QR_TEST=<name id>[/<name id>...],<track>,<laps> once the menus are up (the event records found):
 * more than one, each of them (the photo runs: whichever arcade event the menu opens on, a profile's own). */
void rt_qr_test_tick(void) {
    static int done, got[32];
    static uint64_t next, first;
    const char *e = getenv("XBRT_QR_TEST");
    if (done || !e) return;
    uint64_t now = rt_now_100ns();
    if (now < next) return;
    next = now + 50000000; /* (every 5 s until they are found) */
    const char *c = strchr(e, ',');
    unsigned track = 0, laps = 0, ids[32];
    int n = 0, left = 0;
    if (!c || sscanf(c, ",%u,%u", &track, &laps) != 2) return;
    for (const char *s = e; s < c && n < 32; s++) {
        char *end;
        unsigned long v = strtoul(s, &end, 10);
        if (end == s) continue;
        ids[n++] = (unsigned)v, s = end;
        if (*s != '/') s--;
    }
    for (int i = 0; i < n; i++) {
        if (!got[i] && rt_qr_apply(ids[i], track, laps)) {
            got[i] = 1, first = first ? first : now;
            if (getenv("XBRT_QR_FIELD")) rt_qr_set_field(atoi(getenv("XBRT_QR_FIELD"))); /* (the opponents: the big field's test, 16) */
        }
        left += !got[i];
    }
    if (n && (!left || (first && now - first > 600000000))) done = 1; /* (all, or a minute after the first) */
}

/* ---- the Quick Race menu (X on the arcade screens; glover.c draws it) ---- */

#define MAXQT 64
static struct { int ordinal; char name[48]; } qt[MAXQT]; /* the tracks (<mods>/quickrace.txt, tools/quickracetracks.py) */
static int nqt = -1;
static volatile int menu_open, menu_sel;
static int q_track, q_opp = 7, q_laps = 3, q_applied;
static uint32_t base_track = 4, base_laps = 2; /* Series 1 - Race 1 as the disc has it (put back by Restore) */

static void load_tracks(void) {
    if (nqt >= 0) return;
    nqt = 0;
    char path[1200];
    snprintf(path, sizeof path, "%s/quickrace.txt", getenv("XBRT_MODS") && *getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    char line[128];
    while (f && nqt < MAXQT && fgets(line, sizeof line, f)) {
        int o, n = 0;
        if (sscanf(line, "%d %n", &o, &n) < 1 || !n) continue;
        line[strcspn(line, "\r\n")] = 0;
        qt[nqt].ordinal = o;
        snprintf(qt[nqt].name, sizeof qt[nqt].name, "%s", line + n);
        nqt++;
    }
    if (f) fclose(f);
    for (int i = 0; i < nqt; i++) if (qt[i].ordinal == 84) q_track = i; /* (Fuji first) */
}

enum { QI_TRACK, QI_OPP, QI_LAPS, QI_TAKEDOWNS, QI_LOWGRAV, QI_NITRO, QI_SLIP, QI_GO, QI_RESTORE, QI_N };
static const int QI_FLAG[QI_N] = {0, 0, 0, QR_TAKEDOWNS, QR_LOWGRAVITY, QR_NITRO, QR_SLIPSTREAM, 0, 0};

int rt_qr_menu_open(void) { return menu_open; }

/* Row i's label and value for drawing; how many rows (and which is chosen) as the return and *sel. */
int rt_qr_menu_row(int i, const char **label, char *value, int n, int *sel) {
    static const char *labels[QI_N] = {"Track", "Opponents", "Laps", "Takedowns", "Low Gravity", "Nitro  (hold R3 / N)", "Slipstream", "Start Quick Race", "Restore Series 1 - Race 1"};
    *sel = menu_sel;
    if (i < 0 || i >= QI_N) return QI_N;
    *label = labels[i];
    value[0] = 0;
    if (i == QI_TRACK) snprintf(value, (size_t)n, "%s", nqt > 0 ? qt[q_track].name : "(no quickrace.txt)");
    else if (i == QI_OPP) snprintf(value, (size_t)n, "%d", q_opp);
    else if (i == QI_LAPS) snprintf(value, (size_t)n, "%d", q_laps);
    else if (QI_FLAG[i]) snprintf(value, (size_t)n, "%s", rt_qr_mods & QI_FLAG[i] ? "On" : "Off");
    else if (i == QI_GO) snprintf(value, (size_t)n, "%s", q_applied ? "Set: pick Series 1 - Race 1" : "");
    return QI_N;
}

static void name_events(const char *name) { /* the records' display name (+0x34, inline, 40 bytes) */
    for (int e = 0; e < nqe; e++)
        for (int i = 0; i < 40; i++) xb_wr8(qr_events[e] + 0x34 + (uint32_t)i, (uint8_t)(i < (int)strlen(name) ? name[i] : 0));
}

static void menu_key(int key) {
    int d = key == RT_OV_LEFT ? -1 : key == RT_OV_RIGHT || key == RT_OV_OK ? 1 : 0;
    switch (key) {
    case RT_OV_UP: menu_sel = (menu_sel + QI_N - 1) % QI_N; return;
    case RT_OV_DOWN: menu_sel = (menu_sel + 1) % QI_N; return;
    case RT_OV_BACK: menu_open = 0; return;
    }
    if (!d) return;
    if (menu_sel == QI_TRACK && nqt > 0) q_track = (q_track + d + nqt) % nqt;
    else if (menu_sel == QI_OPP) q_opp = q_opp + d < 2 ? 7 : q_opp + d > 7 ? 2 : q_opp + d;
    else if (menu_sel == QI_LAPS) q_laps = q_laps + d < 1 ? 20 : q_laps + d > 20 ? 1 : q_laps + d;
    else if (QI_FLAG[menu_sel]) rt_qr_mods ^= QI_FLAG[menu_sel];
    else if (menu_sel == QI_GO && key == RT_OV_OK && nqt > 0) {
        if (rt_qr_apply(QR_EVENT_NAME, (uint32_t)qt[q_track].ordinal, (uint32_t)q_laps)) {
            name_events("Quick Race");
            rt_qr_set_field(q_opp);
            q_applied = 1, menu_open = 0;
        }
    } else if (menu_sel == QI_RESTORE && key == RT_OV_OK && qr_event) {
        for (int i = 0; i < nqe; i++) xb_wr32(qr_events[i] + 0x20, base_track), xb_wr32(qr_events[i] + 0x24, base_laps);
        name_events("Series 1 - Race 1");
        rt_qr_set_field(7);
        qr_event = 0, nqe = 0, q_applied = 0, menu_open = 0;
    }
}

/* The pad (hle_input.c, every poll): R3 (N) the nitro; X opens the menu off the track once the arcade's events are
 * loaded (the menus of Arcade Race); while open it takes the pad (1). */
int rt_qr_pad(uint16_t buttons, const uint8_t analog[8], const int16_t thumbs[4]) {
    static uint16_t was;
    static int x_was, a_was, b_was, stick_was;
    nitro_y = (buttons & 0x80) != 0; /* (R3: Y looks back) */
    int x = analog[2] > 128;
    static int eat;
    if (!menu_open && eat) { /* the press that closed the menu, still held: not the game's */
        if (analog[0] > 128 || (buttons & 0x30) || x) return 1;
        eat = 0;
    }
    if (!menu_open) {
        if (x && !x_was && !xb_rd32(0x592984) && !rt_mg_career_menu_recent() && find_event_cached(QR_EVENT_NAME)) {
            load_tracks();
            menu_open = 1, menu_sel = 0;
            fprintf(stderr, "xbrt: quick race: menu\n");
        }
        x_was = x, was = buttons;
        if (!menu_open) return 0;
        a_was = analog[0] > 128, b_was = analog[1] > 128;
        return 1;
    }
    uint16_t down = buttons & ~was;
    int stick = thumbs[1] > 20000 ? 1 : thumbs[1] < -20000 ? 2 : thumbs[0] < -20000 ? 3 : thumbs[0] > 20000 ? 4 : 0;
    int a = analog[0] > 128 || (buttons & 0x10), b = analog[1] > 128 || (buttons & 0x20) || x;
    if ((down & 0x1) || (stick == 1 && stick_was != 1)) menu_key(RT_OV_UP);
    if ((down & 0x2) || (stick == 2 && stick_was != 2)) menu_key(RT_OV_DOWN);
    if ((down & 0x4) || (stick == 3 && stick_was != 3)) menu_key(RT_OV_LEFT);
    if ((down & 0x8) || (stick == 4 && stick_was != 4)) menu_key(RT_OV_RIGHT);
    if (a && !a_was) menu_key(RT_OV_OK);
    if (b && !b_was && !(x && x_was)) menu_key(RT_OV_BACK);
    a_was = a, b_was = b, x_was = x, stick_was = stick, was = buttons;
    if (!menu_open) eat = 1;
    return 1;
}
