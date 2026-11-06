/* The add-on cars in Free Run and the arcade's car lists (the user's, 6 Nov: class F, and every add-on car, only on
 * the garage car selector; "If we can't do Arcade, just do Free Run").
 *
 * Those lists are car-database queries filtered on "unlocked" (field 0x3b), which asks f_00171000(ordinal): past
 * the end of an unlock bitset a car counts as unlocked, inside it its bit decides. The bitset comes from the
 * profile, made before the add-on cars were (their bits are clear): they, and so class F, never showed. Here the
 * ordinals in <mods>/addon_cars.txt (a number a line, # comments) are unlocked whatever the bit says. Nothing is
 * written to the profile. XBRT_ADDON_UNLOCK=0 turns it off. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xbrt.h"

static int rt_unlock_ready;
static unsigned char rt_addon[1024]; /* (ordinals 0-299; room to spare) */

static void unlock_load(void) {
    rt_unlock_ready = 1;
    if (getenv("XBRT_ADDON_UNLOCK") && !atoi(getenv("XBRT_ADDON_UNLOCK"))) return;
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
    uint32_t ordinal = xb_rd32(c->esp + 4); /* (thiscall: the return address, the ordinal) */
    orig_f_00171000(c);
    if (!rt_unlock_ready) unlock_load();
    if (c->eax == 0 && ordinal < sizeof rt_addon && rt_addon[ordinal]) c->eax = 1;
}
