/* Class F, above S (the user's, 6 Nov 2026: a rating for the hyper cars, "call it F, a darker red than S").
 *
 * forza.exe's f_0016D130(ordinal, performance) gives a car its subclass: the first of the 20 upper bounds at
 * 0x52CA00 (D4 0.239 .. S2 0.645, S1 unbounded) the car's performance figure (f_0016CFF0: power, torque,
 * weight, the wider tyre, docs/research/cars.md) does not pass, 1..20, unless model.dat's row (+0x44) sets
 * one (the race classes GT, GTS, P1: 21-23). Past F_BOUND an S1 car is subclass 24 here, "F" of class 7,
 * which the mods folder's performancesubclass.dat and performanceclass.dat add, with their names and
 * badges (docs/research/newcars/fclass.py). No disc car comes near: the fastest road car's figure is
 * 0.665; the add-on hyper cars' 0.70 to 1.14.
 *
 * XBRT_FCLASS=0 leaves the game's subclasses as they were (S1 has no top then). */
#include <stdlib.h>
#include <string.h>
#include "xbrt.h"

#define F_BOUND 0.700f
#define SUB_S1 20u
#define SUB_F 24u

static int rt_fclass = -1;

void orig_f_0016D130(XbCtx *c); /* the subclass from the performance figure (wraps.txt) */
void f_0016D130(XbCtx *c) {
    float perf = xb_rdf(c->esp + 8); /* (cdecl: the return address, the ordinal, the figure) */
    orig_f_0016D130(c);
    if (rt_fclass < 0) rt_fclass = !(getenv("XBRT_FCLASS") && !atoi(getenv("XBRT_FCLASS")));
    if (rt_fclass && c->eax == SUB_S1 && perf > F_BOUND) c->eax = SUB_F;
}
