/* Prize Match (the user's, 2026-11-02): "a matching minigame on the career menu where every 5 levels
 * gives you a turn. Find the match and win that prize. Random each time."
 *
 * A turn for every 5 driver levels (the profile's level, +0x3DC: the profile is the object the game's
 * level getter f_00078080 is asked about, caught there), the turns taken kept in prizematch.txt beside
 * forza.ini (XBRT_PRIZEMATCH names another; the game's saves are never touched). On the career's menus
 * (their level and credits bar asks the credits getter f_00078050 each frame) a note shows the turns waiting;
 * M (display.c) or the pad's White button opens the game: 16 cards face down, 8 prizes in pairs, dealt
 * at random; turn two at a time; the first pair matched is the prize (credits, added to the profile's
 * +0x3D4 as the game's own setter f_00078D40 stores them, so the game saves them with the profile);
 * after MISSES mismatches the turn ends with CONSOLATION credits. Drawn by glover.c (gl_mg_draw). */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "funcs.h"
#include "rt.h"

#define MISSES 4
#define CONSOLATION 5000
static const int PRIZES[] = {10000, 15000, 25000, 40000, 50000, 75000, 100000, 150000, 250000, 500000, 1000000};
static const int WEIGHT[] = {10, 10, 10, 9, 9, 8, 7, 5, 3, 2, 1}; /* (the jackpot rare) */
#define NPRIZES (int)(sizeof PRIZES / sizeof PRIZES[0])

static volatile uint32_t profile;  /* the profile, as the level getter last saw it */
static volatile uint64_t menu_at;  /* the Race Type screen last drawn */
static int used = -1;               /* turns taken */
static volatile int open_;
static RtMatch m;                   /* the game on the table (rt.h) */
static uint64_t flip_back_at;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;

static const char *path(void) {
    const char *p = getenv("XBRT_PRIZEMATCH");
    return p && *p ? p : "prizematch.txt";
}

static void load(void) {
    if (used >= 0) return;
    used = 0;
    FILE *f = fopen(path(), "r");
    if (!f) return;
    char line[128];
    while (fgets(line, sizeof line, f)) sscanf(line, "used %d", &used);
    fclose(f);
}

static void save(int won) {
    FILE *f = fopen(path(), "r");
    char rest[8192] = "";
    size_t n = 0;
    if (f) { /* (the earlier turns' lines kept, the count rewritten) */
        char line[128];
        while (fgets(line, sizeof line, f) && n + strlen(line) < sizeof rest - 1)
            if (strncmp(line, "used ", 5)) n += (size_t)snprintf(rest + n, sizeof rest - n, "%s", line);
        fclose(f);
    }
    f = fopen(path(), "w");
    if (!f) return;
    fprintf(f, "used %d\n%sturn %d: %d credits\n", used, rest, used, won);
    fclose(f);
}

void orig_f_00078080(XbCtx *c); /* the game's own (wraps.txt) */

/* The level getter: the profile it is asked about. */
void f_00078080(XbCtx *c) {
    if (c->ecx && c->ecx < RT_USER_LIMIT) profile = c->ecx;
    orig_f_00078080(c);
}

void orig_f_00078050(XbCtx *c); /* the game's own (wraps.txt) */

/* The credits getter (the career menus' status bar asks it): the profile too. */
void f_00078050(XbCtx *c) {
    if (c->ecx && c->ecx < RT_USER_LIMIT) profile = c->ecx;
    if (!xb_rd32(0x592984)) menu_at = rt_now_100ns(); /* (off the track: a career menu's level and credits bar is up) */
    orig_f_00078050(c);
}

void rt_mg_menu_seen(void) { menu_at = rt_now_100ns(); }

static int level(void) {
    uint32_t p = profile;
    int l = p ? (int)xb_rd32(p + 0x3DC) : 0;
    return l > 0 && l <= 100 ? l : 0;
}

/* Turns waiting (0 when the profile is not yet known). */
int rt_mg_turns(void) {
    pthread_mutex_lock(&mu);
    load();
    int t = level() / 5 - used;
    pthread_mutex_unlock(&mu);
    return t > 0 ? t : 0;
}

/* The note on the Race Type screen: shown while it is drawn and a turn waits. */
int rt_mg_hint(void) { return !open_ && rt_now_100ns() - menu_at < 5000000 && rt_mg_turns() > 0; }

static void deal(void) {
    memset(&m, 0, sizeof m);
    int pick[8], n = 0;
    while (n < 8) { /* eight different prizes, weighted */
        int tot = 0, i;
        for (i = 0; i < NPRIZES; i++) tot += WEIGHT[i];
        int r = rand() % tot;
        for (i = 0; i < NPRIZES && r >= WEIGHT[i]; i++) r -= WEIGHT[i];
        int dup = 0;
        for (int k = 0; k < n; k++) dup |= pick[k] == PRIZES[i];
        if (!dup) pick[n++] = PRIZES[i];
    }
    for (int i = 0; i < 16; i++) m.prize[i] = pick[i / 2];
    for (int i = 15; i > 0; i--) { /* shuffled */
        int j = rand() % (i + 1), t = m.prize[i];
        m.prize[i] = m.prize[j], m.prize[j] = t;
    }
    m.first = m.second = -1;
    m.misses_left = MISSES;
}

void rt_mg_request(void) {
    if (open_) return;
    if (rt_mg_turns() <= 0 || rt_now_100ns() - menu_at > 5000000) {
        fprintf(stderr, "xbrt: prize match: not now (a career menu %s, profile %08x, level %d, turns %d)\n",
                menu_at && rt_now_100ns() - menu_at <= 5000000 ? "up" : "not seen lately", profile, level(), rt_mg_turns());
        return;
    }
    static int seeded;
    if (!seeded) seeded = 1, srand((unsigned)rt_now_100ns());
    pthread_mutex_lock(&mu);
    deal();
    pthread_mutex_unlock(&mu);
    open_ = 1;
    fprintf(stderr, "xbrt: prize match: a turn (level %d, %d taken before)\n", level(), used);
}

int rt_mg_open(void) { return open_; }

/* A career menu (its level and credits bar) up lately: hle_quickrace.c leaves X to it (the dealer's Car List). */
int rt_mg_career_menu_recent(void) { return rt_now_100ns() - menu_at < 5000000; }

static void finish(int credits) {
    m.done = 1, m.won = credits;
    uint32_t p = profile;
    if (p) {
        uint32_t c = xb_rd32(p + 0x3D4);
        uint64_t t = (uint64_t)c + (uint64_t)credits;
        xb_wr32(p + 0x3D4, t > 0x7FFFFFFF ? 0x7FFFFFFF : (uint32_t)t);
    }
    used++;
    save(credits);
    fprintf(stderr, "xbrt: prize match: won %d credits\n", credits);
}

/* The table as it stands, for drawing (a copy). */
void rt_mg_state(RtMatch *out) {
    pthread_mutex_lock(&mu);
    if (flip_back_at && rt_now_100ns() >= flip_back_at) { /* a mismatch shown long enough: both face down again */
        m.face[m.first] = m.face[m.second] = 0;
        m.first = m.second = -1, flip_back_at = 0;
    }
    *out = m;
    pthread_mutex_unlock(&mu);
}

/* A key or button for the game (RT_OV_*). */
void rt_mg_key(int key) {
    if (!open_) return;
    pthread_mutex_lock(&mu);
    if (m.done || (key == RT_OV_BACK && !m.flips)) { /* over (any key), or closed before a card was turned */
        if (key == RT_OV_OK || key == RT_OV_BACK) open_ = 0;
        pthread_mutex_unlock(&mu);
        return;
    }
    switch (key) {
    case RT_OV_UP: m.cursor = (m.cursor + 12) % 16; break;
    case RT_OV_DOWN: m.cursor = (m.cursor + 4) % 16; break;
    case RT_OV_LEFT: m.cursor = (m.cursor & ~3) | ((m.cursor + 3) & 3); break;
    case RT_OV_RIGHT: m.cursor = (m.cursor & ~3) | ((m.cursor + 1) & 3); break;
    case RT_OV_OK:
        if (flip_back_at || m.face[m.cursor]) break;
        m.face[m.cursor] = 1, m.flips++;
        if (m.first < 0) m.first = m.cursor;
        else {
            m.second = m.cursor;
            if (m.prize[m.first] == m.prize[m.second]) finish(m.prize[m.first]);
            else if (--m.misses_left <= 0) {
                for (int i = 0; i < 16; i++) m.face[i] = 1; /* the table shown */
                finish(CONSOLATION);
            } else flip_back_at = rt_now_100ns() + 9000000;
        }
        break;
    }
    pthread_mutex_unlock(&mu);
}

/* The pad while the game is open (hle_input.c): swallowed (1). The White button opens it. */
int rt_mg_pad(uint16_t buttons, const uint8_t analog[8], const int16_t thumbs[4]) {
    static uint16_t was;
    static int a_was, b_was, w_was, stick_was;
    int white = analog[5] > 128;
    if (!open_) {
        if (white && !w_was) rt_mg_request();
        w_was = white, was = buttons;
        if (!open_) return 0;
    }
    uint16_t down = buttons & ~was;
    int stick = thumbs[1] > 20000 ? 1 : thumbs[1] < -20000 ? 2 : thumbs[0] < -20000 ? 3 : thumbs[0] > 20000 ? 4 : 0;
    int a = analog[0] > 128 || (buttons & 0x10), b = analog[1] > 128 || (buttons & 0x20); /* (Start and Back too: Enter and Esc) */
    if ((down & 0x1) || (stick == 1 && stick_was != 1)) rt_mg_key(RT_OV_UP);
    if ((down & 0x2) || (stick == 2 && stick_was != 2)) rt_mg_key(RT_OV_DOWN);
    if ((down & 0x4) || (stick == 3 && stick_was != 3)) rt_mg_key(RT_OV_LEFT);
    if ((down & 0x8) || (stick == 4 && stick_was != 4)) rt_mg_key(RT_OV_RIGHT);
    if (a && !a_was) rt_mg_key(RT_OV_OK);
    if (b && !b_was) rt_mg_key(RT_OV_BACK);
    a_was = a, b_was = b, w_was = white, stick_was = stick, was = buttons;
    return 1;
}
