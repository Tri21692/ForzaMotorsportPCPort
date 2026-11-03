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

#define MAXCARS 12
static struct {
    uint32_t car;
    float v[3], pos[3];
    uint64_t still_since, off_since, hit_at, spin_until, down_at, tumble_until, chase_until;
    float spin; /* radians a second about the up axis, until spin_until */
    int line, kind; /* kind: the player's last hit on it, 1 a slam (side), 2 a shunt (from behind) */
} cs[MAXCARS];

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
    int im = -1;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) me = xb_rd32(r + 0xA0), im = (int)i;
    }
    float mp[3] = {0, 0, 0}, mdv[3] = {0, 0, 0}, mjolt = 0;
    if (me) {
        mp[0] = rdf(me + 0x14), mp[1] = rdf(me + 0x18), mp[2] = rdf(me + 0x1C);
        if (cs[im].car == me) { /* the player's own jolt this tick (a touch jolts both cars) */
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
            static int dry; /* emptied: none until let go and a quarter back (held on empty, it refilled a tick and pushed again) */
            if (tank <= 0) dry = 1;
            if (dry && !nitro_y && tank >= 0.25f) dry = 0;
            if (nitro_y && !dry) {
                float fx = rdf(car + 0x38), fz = rdf(car + 0x40);
                v[0] += fx * (float)(9.0 * dt), v[2] += fz * (float)(9.0 * dt);
                wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                tank -= (float)(dt / 4.0); /* 4 s a tank */
                if (tank < 0) tank = 0;
            } else if (!nitro_y && tank < 1) tank += (float)(dt / 30.0); /* filled again in 30 s, while not held */
        }
        if (rt_qr_mods & QR_TAKEDOWNS) {
            /* After Burnout 3 (the user's reference video): a slam from the side throws the rival sideways across the
             * road, a shunt from behind punts it on, both turning it out of grip; if it then hits a wall, stops or
             * leaves the road within 3 s it is a takedown (banner, count, half a nitro tank) and the wreck comes back
             * behind the player 2 s later. Your own car, stuck 3 s: back on the line. Along the ground: no hop. */
            float dv[3] = {v[0] - cs[i].v[0], v[1] - cs[i].v[1], v[2] - cs[i].v[2]};
            float jolt = sqrtf(dv[0] * dv[0] + dv[1] * dv[1] + dv[2] * dv[2]) / (float)dt;
            float dx = p[0] - mp[0], dz = p[2] - mp[2], dd = sqrtf(dx * dx + dz * dz);
            int near_me = car != me && me && dd < 8;
            int fresh = cs[i].hit_at && now - cs[i].hit_at < 30000000; /* the player's hit, under 3 s ago */
            /* a touch: both cars jolted this tick, side by side or nose to tail (the user's: it fired without
             * one, on a rival's own knock near the player) */
            int touch = car != me && me && dd < 5.0f && dd > 0.1f && jolt > 40 && mjolt > 25;
            if (touch && now - cs[i].hit_at > 10000000 && !cs[i].down_at) {
                float fx = rdf(me + 0x38), fz = rdf(me + 0x40), ux = dx / dd, uz = dz / dd; /* the player's heading; the way to the rival */
                float ahead = ux * fx + uz * fz;
                /* the rivals a touch heavier than before (half the throw), the player's car heavier still: */
                if (ahead > 0.8f) { /* a shunt: punted on, along the player's heading */
                    cs[i].kind = 2;
                    v[0] += fx * 3, v[2] += fz * 3;
                    cs[i].spin = (rand() & 1 ? 1 : -1) * 1.5f;
                    say("SHUNT!");
                } else { /* a slam: across, away from the player (the side of the heading it is on) */
                    float lx = ux - ahead * fx, lz = uz - ahead * fz, ll = sqrtf(lx * lx + lz * lz);
                    if (ll > 0.01f) lx /= ll, lz /= ll;
                    cs[i].kind = 1;
                    v[0] += lx * 4, v[2] += lz * 4;
                    cs[i].spin = (lx * fz - lz * fx > 0 ? 1 : -1) * 2.0f; /* (its nose turned towards where it is thrown) */
                    say("SLAM!");
                }
                wrf(car + 0x44, v[0]), wrf(car + 0x4C, v[2]);
                cs[i].hit_at = now, cs[i].spin_until = now + 5000000;
                fresh = 0; /* (this tick's jolt is the hit, not a wall) */
                if (!touched) { /* the player's car heavier: half of the knock it took given back */
                    touched = 1;
                    float w[3];
                    for (int j = 0; j < 3; j++) w[j] = rdf(me + 0x44 + 4 * (uint32_t)j) - 0.5f * mdv[j];
                    wrf(me + 0x44, w[0]), wrf(me + 0x4C, w[2]); /* (not the up: no lift) */
                    if (im >= 0 && cs[im].car == me) cs[im].v[0] = w[0], cs[im].v[2] = w[2];
                }
            }
            if (cs[i].spin_until > now) yaw(car, cs[i].spin * (float)dt);
            float sp = sqrtf(v[0] * v[0] + v[2] * v[2]);
            int k = have_line ? nearest(xs, zs, np, p[0], p[2]) : -1;
            float off = 0;
            if (k >= 0) { float lx = rdf(xs + 4 * k) - p[0], lz = rdf(zs + 4 * k) - p[2]; off = sqrtf(lx * lx + lz * lz); }
            int stuck = sp < 2.0f || off > 25.0f || rdf(car + 0x30) < 0.3f; /* (stopped, far off the line, or on its side) */
            float flat = sqrtf(dv[0] * dv[0] + dv[2] * dv[2]) / (float)dt; /* (along the ground: a landing is no wall) */
            int wall = fresh && flat > 80 && !near_me; /* a hard knock away from the player soon after the player's hit */
            if (car != me && fresh && !cs[i].down_at && (wall || stuck)) {
                cs[i].down_at = now;
                takedowns++;
                tank = tank + 0.5f > 1 ? 1 : tank + 0.5f; /* (a takedown fills the boost, as Burnout's) */
                say(wall ? "WALL TAKEDOWN!" : cs[i].kind == 2 ? "SHUNT TAKEDOWN!" : "SLAM TAKEDOWN!");
                fprintf(stderr, "xbrt: quick race: takedown %d (racer %u, %s)\n", takedowns, i, wall ? "wall" : cs[i].kind == 2 ? "shunt" : "slam");
                if (wall) { /* blown up (the user's: "explodes" on the wall): thrown up off the wall, rolling, for 1.2 s */
                    v[1] += 7.0f, v[0] -= dv[0] * 0.3f, v[2] -= dv[2] * 0.3f;
                    wrf(car + 0x44, v[0]), wrf(car + 0x48, v[1]), wrf(car + 0x4C, v[2]);
                    cs[i].tumble_until = now + 12000000, cs[i].spin = (rand() & 1 ? 1 : -1) * 4.0f, cs[i].spin_until = cs[i].tumble_until;
                }
            }
            if (cs[i].tumble_until > now) roll(car, 6.0f * (float)dt);
            if (stuck) { if (!cs[i].still_since) cs[i].still_since = now; }
            else cs[i].still_since = 0;
            if (cs[i].down_at && !stuck && !cs[i].tumble_until && now - cs[i].down_at > 30000000) cs[i].down_at = 0; /* (it drove on: in the race again) */
            uint64_t wait = cs[i].down_at ? 20000000 : 30000000; /* a wreck 2 s, any other car 3 s */
            int blown = cs[i].tumble_until && now - cs[i].down_at > 25000000; /* a blown-up wreck: gone 2.5 s on, landed or not */
            if (((stuck && cs[i].still_since && now - cs[i].still_since > wait) || blown) && k >= 0) {
                int at = k;
                if (cs[i].down_at && me) at = behind(xs, zs, np, nearest(xs, zs, np, mp[0], mp[2]), 60); /* the wreck: back behind the player */
                respawn(car, xs, zs, ys, np, at);
                if (cs[i].down_at && car != me) cs[i].chase_until = now + 200000000; /* then a hard chase back to the player, up to 20 s */
                cs[i].still_since = cs[i].down_at = cs[i].spin_until = cs[i].tumble_until = 0;
                if (car == me) say("RESPAWN");
                fprintf(stderr, "xbrt: quick race: racer %u respawned at line point %d (%s)\n", i, at, car == me ? "the player" : "an opponent");
                v[0] = rdf(car + 0x44), v[1] = rdf(car + 0x48), v[2] = rdf(car + 0x4C);
            }
            if (cs[i].chase_until > now && me) { /* rubber band: pushed hard along its heading while the player is ahead and over 25 m off */
                float hx = rdf(car + 0x38), hz = rdf(car + 0x40), ax = mp[0] - p[0], az = mp[2] - p[2], d = sqrtf(ax * ax + az * az);
                float msp = sqrtf(rdf(me + 0x44) * rdf(me + 0x44) + rdf(me + 0x4C) * rdf(me + 0x4C)), csp = sqrtf(v[0] * v[0] + v[2] * v[2]);
                if (d < 25 || ax * hx + az * hz < 0) cs[i].chase_until = 0; /* caught up, or past: racing as before */
                else if (csp < msp + 15) { /* up to 15 m/s faster than the player */
                    v[0] += hx * (float)(14.0 * dt), v[2] += hz * (float)(14.0 * dt);
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
