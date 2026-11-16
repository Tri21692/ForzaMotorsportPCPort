/* A Mayhem race's own car settings (the user's, 15 Nov: "Can Mayhem mode automatically set the transmission to Auto
 * and damage to just cosmetic on just a race level (Not global)?"): on the player's car, for that race only; the
 * profile's Set Difficulty is never written, so every other race and the save keep the user's own.
 *
 *  - Damage: the level (0 cosmetic, 1 limited, 2 simulation) the game takes from the profile's (+0x3B8) into the
 *    racer's car settings (racer +0xB4, +0xE8: f_000779D0 -> f_00043400), and from there, as the car is built, into
 *    the car's own two (car +0xCEC, and its physics' at car +0x1B18 +0xCEC = +0x2804: f_000F1670). All three read 2
 *    in a career race on a Simulation profile, 0 in Arcade. Here: 0 in the car's two (the settings' is only read as the car is built).
 *  - Transmission: three flags of the car, +0xA1C, +0x27F4 and +0x2EC4, each 1 with the Assists' Transmission on
 *    Automatic and 0 on Manual (the only bytes of the car's first 32 KB that followed the setting over two grids of
 *    each, apart from the engine's running figures). Here: 1.
 *
 * Kept so from the career tick while the race is Mayhem's (a restart applies the profile's again).
 * XBRT_MAYHEM_CAR=0: off. XBRT_MAYHEM_CAR_TEST=1: in any race (testing). */
#include <stdio.h>
#include <stdlib.h>

#include "rt.h"
#include "xbrt.h"

#define CAR_DAMAGE 0xE8u
static const uint32_t AUTO[] = {0xA1Cu, 0x27F4u, 0x2EC4u};

void rt_mayhem_car_tick(void) {
    static int on = -1, test;
    static uint32_t told;
    if (on < 0) {
        const char *e = getenv("XBRT_MAYHEM_CAR"), *t = getenv("XBRT_MAYHEM_CAR_TEST");
        on = !(e && !atoi(e)), test = t && atoi(t);
    }
    int rt_qr_mayhem_grid(void);
    if (!on || !xb_rd32(0x592984) || !(test || rt_qr_mayhem() || rt_qr_mayhem_grid())) { told = 0; return; }
    uint32_t arr = xb_rd32(0x58DAA0 + 4), n = xb_rd32(0x58DAA0 + 0x10), car = 0, sett = 0;
    if (!arr || arr >= RT_USER_LIMIT || n > 64) return;
    for (uint32_t i = 0; i < n && !car; i++) {
        uint32_t r = xb_rd32(arr + 4 * i);
        if (r && r < RT_USER_LIMIT && xb_rd32(r + 0x14) == 0) car = xb_rd32(r + 0xA0), sett = xb_rd32(r + 0xB4);
    }
    if (!car || car >= RT_USER_LIMIT) return;
    uint32_t dmg = xb_rd32(car + 0x2804), manual = 0;
    for (int i = 0; i < 3; i++) {
        uint32_t v = xb_rd32(car + AUTO[i]);
        if (v > 1) return;
        manual |= !v;
    }
    if (car != told) {
        told = car;
        fprintf(stderr, "xbrt: mayhem car: the player's car %08x: damage level %u -> cosmetic, transmission %s -> automatic (this race only)\n",
                car, dmg, manual ? "manual" : "automatic");
    }
    /* The damage level, everywhere it stands (the user's, 15 Nov: "Transmission works perfectly but damage is still
     * simulation": the +0xE8 written before is the settings', not the car's, where it stood at 0 anyway). */
    static const uint32_t LIVE[] = {0xCECu, 0x2804u};
    int ok = 1;
    for (int i = 0; i < 2; i++) ok = ok && xb_rd32(car + LIVE[i]) <= 2;
    for (int i = 0; ok && i < 2; i++) /* (not ok: not a car as this build knows it, nothing written) */
        if (xb_rd32(car + LIVE[i])) {
            static int said;
            if (said++ < 6) fprintf(stderr, "xbrt: mayhem car: the damage level at +0x%X was %u: set to 0 (cosmetic)\n", LIVE[i], xb_rd32(car + LIVE[i]));
            xb_wr32(car + LIVE[i], 0);
        }
    (void)sett; /* (the settings' own, +0xE8, is left: only read as the car is built, and not ours to keep) */
    for (int i = 0; i < 3; i++)
        if (!xb_rd32(car + AUTO[i])) {
            static int said;
            if (said++ < 6) fprintf(stderr, "xbrt: mayhem car: the flag at +0x%X was 0 (manual): set to 1\n", AUTO[i]);
            xb_wr32(car + AUTO[i], 1);
        }
}
