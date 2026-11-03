/* Quick Race (the user's, 2026-11-02): in the Arcade Race menus X opens a menu (glover.c draws it,
 * like F1's) to pick a track, the number of opponents (2 to 7: one opponent is the Catch-Up event's),
 * the laps and modifiers; the Quick Race arcade event (tools/quickrace.py adds it) is then rewritten
 * in memory to that track, field and laps (rt_qr_apply), and the modifiers act in its races:
 *
 *   Takedowns   cars are light: a hit that jolts an opponent is made 2.5 times harder, with a kick
 *               up, and counts as a takedown when it sends the car off or stops it; a car (yours too)
 *               stopped or off the track for 3 s is set back on the racing line, rolling (a respawn).
 *   Low Gravity the cars fall at 40% of the pull: long, floaty crests.
 *   Nitro       hold the right stick in (R3; N on the keyboard: Y is the game's look back) for a push along
 *               the car's heading, from a tank that fills again slowly.
 *   Slipstream  close behind a car (within 25 m, in line), a strong tow.
 *
 * From the race (rt_qr_tick, rt_gil held): the racers (0x58DAA0), each car's pose (+0x14: x y z, then the
 * 3x3 turn by rows, forward the third) and velocity (+0x44, m/s), the racing line ([0x5E1450]+4). The
 * modifiers act only in the Quick Race event (its ordinal from quickrace.txt), or in every race with
 * XBRT_QR_ALWAYS=1 (testing). */
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
    uint32_t b;
    memcpy(&b, &f, 4);
    xb_wr32(a, b);
}

volatile int rt_qr_mods = QR_TAKEDOWNS; /* the modifiers chosen (rt.h QR_*) */
static int qr_ordinal = -1;              /* the Quick Race event's arcade ordinal (quickrace.txt), -1 none */
static uint32_t qr_event;                /* its record, once found (rt_qr_apply) */
static int takedowns, nitro_y;
static float tank = 1.0f;
static char note[48];
static uint64_t note_until;

static void say(const char *m) {
    snprintf(note, sizeof note, "%s", m);
    note_until = rt_now_100ns() + 15000000;
}
const char *rt_qr_note(void) { return note_until && rt_now_100ns() < note_until ? note : NULL; }
int rt_qr_takedowns(void) { return takedowns; }
float rt_qr_tank(void) { return tank; }


static int active(void) {
    static int always = -1;
    if (always < 0) always = getenv("XBRT_QR_ALWAYS") && atoi(getenv("XBRT_QR_ALWAYS"));
    if (always) return 1;
    if (qr_ordinal < 0 || !qr_event) return 0;
    uint32_t g = xb_rd32(0x592984), ev = g ? xb_rd32(g + 0x318) : 0;
    return ev && ev < RT_USER_LIMIT && ev == qr_event;
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

#define MAXCARS 12
static struct { uint32_t car; float v[3], pos[3]; uint64_t still_since, off_since, hit_at; int line; } cs[MAXCARS];

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
}

void rt_qr_tick(void) {
    static uint64_t last;
    uint64_t now = rt_now_100ns();
    double dt = last ? (now - last) / 1e7 : 0;
    last = now;
    if (!xb_rd32(0x592984) || !active()) { memset(cs, 0, sizeof cs); takedowns = 0, tank = 1; return; }
    if (dt <= 0 || dt > 0.25) return;
    uint32_t list = 0x58DAA0, n = xb_rd32(list + 0x10), arr = xb_rd32(list + 4);
    if (!arr || arr >= RT_USER_LIMIT || n > MAXCARS) return;
    uint32_t track = xb_rd32(0x5E1450), line = track && xb_rd8(track + 8) ? xb_rd32(track + 4) : 0;
    uint32_t np = line ? xb_rd32(line + 8) : 0, xs = line ? xb_rd32(line + 0x30) : 0, zs = line ? xb_rd32(line + 0x44) : 0, ys = line ? xb_rd32(line + 0x58) : 0;
    int have_line = np > 2 && np < 100000 && xs && zs && ys;
    uint32_t me = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) me = xb_rd32(r + 0xA0);
    }
    float mp[3] = {0, 0, 0};
    if (me) mp[0] = rdf(me + 0x14), mp[1] = rdf(me + 0x18), mp[2] = rdf(me + 0x1C);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i), car = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xA0) : 0;
        uint32_t timing = r && r < RT_USER_LIMIT ? xb_rd32(r + 0xC0) : 0;
        if (!car || car >= RT_USER_LIMIT || !timing || timing >= RT_USER_LIMIT) continue;
        int lap = (int)xb_rd32(timing + 0x9C);
        float v[3] = {rdf(car + 0x44), rdf(car + 0x48), rdf(car + 0x4C)}, p[3] = {rdf(car + 0x14), rdf(car + 0x18), rdf(car + 0x1C)};
        if (cs[i].car != car) { memset(&cs[i], 0, sizeof cs[i]); cs[i].car = car; memcpy(cs[i].v, v, sizeof v); memcpy(cs[i].pos, p, sizeof p); continue; }
        if (lap < 0 && rdf(timing + 0xA0) <= 0) { memcpy(cs[i].v, v, sizeof v); memcpy(cs[i].pos, p, sizeof p); continue; } /* (the grid: the race's clock not yet started) */
        if (rt_qr_mods & QR_LOWGRAVITY) v[1] += (float)(9.81 * 0.6 * dt), wrf(car + 0x48, v[1]); /* (60% of the pull given back) */
        if (rt_qr_mods & QR_SLIPSTREAM) { /* a tow from any car close ahead, in line */
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
        if ((rt_qr_mods & QR_NITRO) && car == me) {
            if (nitro_y && tank > 0) {
                float fx = rdf(car + 0x38), fz = rdf(car + 0x40);
                v[0] += fx * (float)(9.0 * dt), v[2] += fz * (float)(9.0 * dt);
                wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                tank -= (float)(dt / 4.0); /* 4 s a tank */
                if (tank < 0) tank = 0;
            } else if (tank < 1) tank += (float)(dt / 30.0); /* filled again in 30 s */
        }
        if (rt_qr_mods & QR_TAKEDOWNS) {
            float dv[3] = {v[0] - cs[i].v[0], v[1] - cs[i].v[1], v[2] - cs[i].v[2]};
            float jolt = sqrtf(dv[0] * dv[0] + dv[1] * dv[1] + dv[2] * dv[2]) / (float)dt;
            float dx = p[0] - mp[0], dz = p[2] - mp[2], near_me = car != me && me && dx * dx + dz * dz < 64;
            if (jolt > 60 && near_me && now - cs[i].hit_at > 10000000) { /* hit by the player: light, so thrown */
                v[0] += dv[0] * 1.5f, v[2] += dv[2] * 1.5f, v[1] += 4.0f;
                wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                cs[i].hit_at = now;
            }
            float sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
            int k = have_line ? nearest(xs, zs, np, p[0], p[2]) : -1;
            float off = 0;
            if (k >= 0) { float lx = rdf(xs + 4 * k) - p[0], lz = rdf(zs + 4 * k) - p[2]; off = sqrtf(lx * lx + lz * lz); }
            int stuck = sp < 2.0f || off > 25.0f || rdf(car + 0x30) < 0.3f; /* (stopped, far off the line, or on its side) */
            if (stuck) { if (!cs[i].still_since) cs[i].still_since = now; }
            else cs[i].still_since = 0;
            if (stuck && cs[i].still_since && now - cs[i].still_since > 30000000 && k >= 0) {
                if (car != me && now - cs[i].hit_at < 80000000) {
                    takedowns++;
                    say("TAKEDOWN!");
                }
                respawn(car, xs, zs, ys, np, k);
                cs[i].still_since = 0;
                if (car == me) say("RESPAWN");
                fprintf(stderr, "xbrt: quick race: racer %u respawned at line point %d (%s)\n", i, k, car == me ? "the player" : "an opponent");
                v[0] = rdf(car + 0x44), v[1] = rdf(car + 0x48), v[2] = rdf(car + 0x4C);
            }
        }
        memcpy(cs[i].v, v, sizeof v);
        memcpy(cs[i].pos, p, sizeof p);
    }
}

void rt_qr_set_ordinal(int o) { qr_ordinal = o; }

/* An arcade event's record (as the game parses arcade\Ser*.xml: +0x0C the leaderboard, 4000; +0x10 its
 * ordinal; +0x14 its name's string id; +0x20 the track's ordinal; +0x24 the laps; +0x2C 1.0; +0x34 its
 * display name), found by its name's string id in RAM; 0 if not there (yet). */
static uint32_t find_event(uint32_t textid) {
    for (uint32_t a = 0x10000; a + 0x40 < RT_USER_LIMIT; a += 4)
        if (xb_rd32(a + 0x14) == textid && xb_rd32(a + 0x0C) == 4000 && xb_rd32(a + 0x2C) == 0x3F800000u && xb_rd32(a + 0x24) - 1 < 99)
            return a;
    return 0;
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
    if (!qr_event) return;
    uint32_t was = xb_rd32(qr_event + QR_FIELD_AT);
    if (was < 1 || was > 15) { fprintf(stderr, "xbrt: quick race: the field's count not where expected (+%x = %u): left\n", QR_FIELD_AT, was); return; }
    xb_wr32(qr_event + QR_FIELD_AT, (uint32_t)n);
    fprintf(stderr, "xbrt: quick race: opponents %u -> %d\n", was, n);
}

/* The Quick Race event set to a track, laps (the field: rt_qr_set_field). 1 if done. */
int rt_qr_apply(uint32_t textid, uint32_t track, uint32_t laps) {
    static uint32_t at, at_id;
    if (!at || at_id != textid || xb_rd32(at + 0x14) != textid) at = find_event(textid), at_id = textid;
    if (!at) return 0;
    xb_wr32(at + 0x20, track), xb_wr32(at + 0x24, laps);
    qr_event = at;
    fprintf(stderr, "xbrt: quick race: event %08x (name %u) set to track %u, %u laps\n", at, textid, track, laps);
    return 1;
}

/* Testing: XBRT_QR_TEST=<name id>,<track>,<laps> once the menus are up (an event record found). */
void rt_qr_test_tick(void) {
    static int done;
    static uint64_t next;
    const char *e = getenv("XBRT_QR_TEST");
    if (done || !e) return;
    uint64_t now = rt_now_100ns();
    if (now < next) return;
    next = now + 50000000; /* (every 5 s until it is found) */
    unsigned id = 0, track = 0, laps = 0;
    if (sscanf(e, "%u,%u,%u", &id, &track, &laps) == 3 && rt_qr_apply(id, track, laps)) done = 1;
}

/* ---- the Quick Race menu (X on the arcade screens; glover.c draws it) ---- */

#define MAXQT 64
static struct { int ordinal; char name[48]; } qt[MAXQT]; /* the tracks (<mods>/quickrace.txt, tools/quickracetracks.py) */
static int nqt = -1;
static volatile int menu_open, menu_sel;
static int q_track, q_opp = 7, q_laps = 3, q_applied;
static uint32_t base_track = 4, base_laps = 2; /* Series 1 - Race 1 as the disc has it (put back by Restore) */
#define QR_EVENT_NAME 3073                     /* the arcade event Quick Race takes over: Series 1 - Race 1 */

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

static void name_event(uint32_t at, const char *name) { /* the record's display name (+0x34, inline, 40 bytes) */
    for (int i = 0; i < 40; i++) xb_wr8(at + 0x34 + (uint32_t)i, (uint8_t)(i < (int)strlen(name) ? name[i] : 0));
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
            name_event(qr_event, "Quick Race");
            rt_qr_set_field(q_opp);
            q_applied = 1, menu_open = 0;
        }
    } else if (menu_sel == QI_RESTORE && key == RT_OV_OK && qr_event) {
        xb_wr32(qr_event + 0x20, base_track), xb_wr32(qr_event + 0x24, base_laps);
        name_event(qr_event, "Series 1 - Race 1");
        rt_qr_set_field(7);
        qr_event = 0, q_applied = 0, menu_open = 0;
    }
}

/* The pad (hle_input.c, every poll): Y the nitro; X opens the menu off the track once the arcade's events are
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
