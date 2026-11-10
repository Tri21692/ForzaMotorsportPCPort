/* The add-on cars in Free Run and the arcade's car lists, and a "DLC Cars" entry in the store's Advanced Search
 * (the user's, 6 Nov).
 *
 * Free Run and the arcade: those lists are car-database queries filtered on "unlocked" (field 0x3b), which asks
 * f_00171000(ordinal): past the end of an unlock bitset a car counts as unlocked, inside it its bit decides. The
 * bitset comes from the profile, made before the add-on cars were (their bits are clear): they, and so class F,
 * never showed. The ordinals in <mods>/addon_cars.txt (a number a line, # comments) are unlocked whatever the
 * bit says. Nothing is written to the profile. XBRT_ADDON_UNLOCK=0 turns it off.
 *
 * Advanced Search: its class list is "Any" and one entry a performanceclass.dat row (f_0017B790); the mods
 * folder's row 8 is "DLC Cars" (docs/research/newcars/dlcclass.py). f_003726D0 applies the search: the class
 * list's choice (screen +0x2280, of +0x2274 entries) becomes a condition on the screen's query (+0x1C10,
 * f_00173770's) through f_001767A0(field, comparison, value); the last entry was the race class's, "perfclass_id
 * at least 6"; entry n is otherwise "perfclass_id = row n-1's id". When "DLC Cars" (row id 8) is chosen, that condition is "unlocked = 1" here instead,
 * and for that query f_00171000 says whether the car is an add-on. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xbrt.h"

static int rt_unlock_ready;
static unsigned char rt_addon[1024]; /* (ordinals 0-299; room to spare) */
static int rt_unlock_on = 1;
static uint32_t rt_dlc_pending, rt_dlc_query; /* the search query being given its conditions / given the DLC one */

static void unlock_load(void) {
    rt_unlock_ready = 1;
    if (getenv("XBRT_ADDON_UNLOCK") && !atoi(getenv("XBRT_ADDON_UNLOCK"))) rt_unlock_on = 0;
    char path[512];
    snprintf(path, sizeof path, "%s/addon_cars.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char *hash = strchr(line, '#');
        if (hash) *hash = 0;
        char *end;
        long o = strtol(line, &end, 10);
        if (end != line && o >= 0 && o < (long)sizeof rt_addon) rt_addon[o] = 1;
    }
    fclose(f);
}

void orig_f_00171000(XbCtx *c); /* a car unlocked in a query's bitset (wraps.txt) */
void f_00171000(XbCtx *c) {
    uint32_t self = c->ecx;
    uint32_t ordinal = xb_rd32(c->esp + 4); /* (thiscall: the return address, the ordinal) */
    orig_f_00171000(c);
    if (!rt_unlock_ready) unlock_load();
    int addon = ordinal < sizeof rt_addon && rt_addon[ordinal];
    if (rt_dlc_query && self - 4 == rt_dlc_query) { c->eax = addon; return; } /* (the search's "DLC Cars") */
    if (rt_unlock_on && c->eax == 0 && addon) c->eax = 1;
    extern int rt_qr_prize_locked(uint32_t ordinal);
    if (c->eax && rt_qr_prize_locked(ordinal)) c->eax = 0; /* (Mayhem's prize car, until given: hle_quickrace.c) */
}

static int class_row_is_dlc(uint32_t row) { /* performanceclass.dat's rows, 24 bytes: the row's id is 8 */
    uint32_t begin = xb_rd32(0x5BD6DC), end = xb_rd32(0x5BD6E0);
    return begin && begin + 24 * (row + 1) <= end && xb_rd32(begin + 24 * row) == 8;
}

void orig_f_003726D0(XbCtx *c); /* the Advanced Search applied (wraps.txt) */
void f_003726D0(XbCtx *c) {
    uint32_t screen = c->ecx;
    uint32_t sel = xb_rd32(screen + 0x2280), count = xb_rd32(screen + 0x2274), query = xb_rd32(screen + 0x1C10);
    int dlc = sel > 0 && sel + 1 != count && class_row_is_dlc(sel - 1); /* (entry n is row n-1; the last entry is the game's own) */
    if (rt_dlc_query == query) rt_dlc_query = 0;
    rt_dlc_pending = dlc ? query : 0;
    orig_f_003726D0(c);
    rt_dlc_pending = 0;
}

void orig_f_001767A0(XbCtx *c); /* a query's condition (field, comparison, value) (wraps.txt) */
void f_001767A0(XbCtx *c) {
    if (rt_dlc_pending && c->ecx == rt_dlc_pending && xb_rd32(c->esp + 4) == 0x26) { /* perfclass_id: the class list's */
        xb_wr32(c->esp + 4, 0x3B);  /* unlocked */
        xb_wr32(c->esp + 8, 0);     /* = */
        xb_wr32(c->esp + 12, 1);
        rt_dlc_query = rt_dlc_pending;
    }
    orig_f_001767A0(c);
}
