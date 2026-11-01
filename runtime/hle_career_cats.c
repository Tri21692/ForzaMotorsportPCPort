/* More career categories than the six (the user's Drift, 2026-11-01). The Race Type screen's
 * categories are a table at 0x52E850, 0x34 bytes each, filled by a static initializer (0x307F30):
 * +0 the folder's name (series from D:\MEDIA\Events\<name>\Ser%05u.xml), +4 the kind (5 online,
 * 1 point to point, 2 club, 3 spec, 4 pro series, 0 endurance), +8 and +0x18 the title and the
 * description (string objects: a cached text, 0, the string table, u16 id), +0x28 +0x2C +0x30 what
 * the list works out (the lowest level, events done, events). Its readers are the list's builder
 * (0x184F30: an item an entry, to 0x52E988), the selection (0x1856B0: [screen+0x2C] * 0x34) and the
 * panel (0x184C30, hle_career_panel.c); here they are the generated code with the table's address
 * a variable (hle_career_cats_gen.inc, made from out/code_0023.c: if the game is recompiled, make
 * it again). <mods>/categories.txt adds categories after the six, a line each:
 *
 *     <folder name> <kind> <title id> <description id> <icon>
 *
 * (the ids in the title's and the description's string tables, as the first category's: GameStrings
 * and UIStrings; the icon a tile of media/Events/Events.xpr and Events_LG.xpr); then the table is
 * copied into kernel data with room for them, the first time the list is built. Without the file
 * nothing changes.
 *
 * The icon: the list item keeps the entry's kind at +0x28 and the icon strips' tiles follow the
 * kinds (0 a fuel can for endurance .. 5 two helmets for online; 6 a stopwatch and 7 cones unused).
 * The item gets the icon's tile there instead (cat_frame): an added category's own, the Time Trial
 * category's the stopwatch; the table keeps the kind the game's logic goes by. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

#define CAT_TABLE 0x52E850u
#define CAT_SIZE 0x34u
#define CAT_DISC 6u
#define CAT_MAX 12u
#define TT_NAME 0x4D02C0u /* the Time Trial category's folder name (nv2a.c's career_timetrial) */

static uint32_t base = CAT_TABLE, count = CAT_DISC;
static struct { char name[32]; uint32_t icon; } added[CAT_MAX - CAT_DISC];
static unsigned nadded;
static int ready;

static void setup(void) {
    if (ready) return;
    const char *tt = getenv("XBRT_CAREER_TIMETRIAL");
    if (tt && atoi(tt) && xb_rd32(CAT_TABLE) != TT_NAME) return; /* the Time Trial rename first (nv2a.c) */
    ready = 1;
    char path[1200], line[256];
    snprintf(path, sizeof path, "%s/categories.txt", getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    FILE *f = fopen(path, "r");
    if (!f) return;
    struct { char name[32]; uint32_t kind, title, desc, icon; } want[CAT_MAX - CAT_DISC];
    unsigned n = 0;
    while (n < CAT_MAX - CAT_DISC && fgets(line, sizeof line, f))
        if (line[0] != '#' && sscanf(line, "%31s %u %u %u %u", want[n].name, &want[n].kind, &want[n].title, &want[n].desc, &want[n].icon) == 5) n++;
    fclose(f);
    if (!n) return;
    uint32_t t = rt_kdata_alloc((CAT_DISC + n) * CAT_SIZE), names = rt_kdata_alloc(n * 32);
    for (uint32_t o = 0; o < CAT_DISC * CAT_SIZE; o += 4) xb_wr32(t + o, xb_rd32(CAT_TABLE + o));
    for (unsigned k = 0; k < n; k++) {
        uint32_t e = t + (CAT_DISC + k) * CAT_SIZE, nm = names + 32 * k;
        for (unsigned i = 0; i < 32; i++) xb_wr8(nm + i, (uint8_t)(i < strlen(want[k].name) ? want[k].name[i] : 0));
        for (uint32_t o = 0; o < CAT_SIZE; o += 4) xb_wr32(e + o, 0);
        xb_wr32(e + 0x00, nm);
        xb_wr32(e + 0x04, want[k].kind);
        xb_wr32(e + 0x10, xb_rd32(CAT_TABLE + 0x10)), xb_wr16(e + 0x14, (uint16_t)want[k].title); /* the first's tables */
        xb_wr32(e + 0x20, xb_rd32(CAT_TABLE + 0x20)), xb_wr16(e + 0x24, (uint16_t)want[k].desc);
        snprintf(added[k].name, sizeof added[k].name, "%s", want[k].name);
        added[k].icon = want[k].icon;
        fprintf(stderr, "xbrt: career category %u: %s (kind %u, strings %u, %u, icon %u)\n", CAT_DISC + k, want[k].name, want[k].kind,
                want[k].title, want[k].desc, want[k].icon);
    }
    nadded = n, base = t, count = CAT_DISC + n;
}

uint32_t cat_base(void) { setup(); return base; }
static uint32_t cat_end(void) { return cat_base() + count * CAT_SIZE; }

/* The icon for the list item of the entry at e, whose kind is k. */
static uint32_t cat_frame(uint32_t e, uint32_t k) {
    uint32_t nm = xb_rd32(e);
    if (nm == TT_NAME) return 6;
    for (unsigned i = 0; i < nadded; i++)
        if (e == base + (CAT_DISC + i) * CAT_SIZE) return added[i].icon;
    return k;
}

#include "hle_career_cats_gen.inc"
