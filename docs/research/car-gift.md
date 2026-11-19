# How a prize car reaches the garage (CareerCarGift)

Read-only study of the recompiled code (out/code_*.c) and default.xbe, 7 Nov 2026.
Goal: let the runtime give the player car ordinal N once, for example when every
Mayhem Moment has been collected.

## The chain, end to end

1. **SeriesFlow** (class name string at 0x4B44B4, vtable 0x4B4490). Its vf+0x20 is
   `f_00183F30`, the career series loop: race, results, rewards, the car screen, the save, then
   the next race. It keeps a local `vector<int>` gift list at `[esp+0x34]`: begin +4, end +8,
   capacity +0xC, all three zeroed at 0x18442B.
2. At 0x18444B it calls **`f_0017E270(arg1, &gifts)`**. This is cdecl (plain `ret`, the caller
   pops 8 bytes). arg1 is a per-event byte array from `f_00077BB0(profile, series)` when the
   series flag `[series+0x549]` is set, otherwise 0. `f_0017E270` reads
   `edi = [[0x592984]+0x24]`, the race's end state. Only when that is 0 (finished normally; the
   abort value is 0x80000001) does it apply the reward lists: event, medal, podium and
   series-completion. It does so with `f_0007AD40(this=list, &gifts)` at 0x17E417, 0x17E46A,
   0x17E4F2 and 0x17E64F.
3. `f_0007AD40`, reward type 3 (CareerCarGift), only does `f_0018C280(this=&gifts, &ordinal)`.
   That is `vector<int>::push_back(const int&)`: a pointer to the value, `ret 4`, and it grows
   the vector through 0x2A5D0. Nothing else happens there: no garage change, no flag.
4. Back in `f_00183F30`: if `[[0x592984]+0x24] != 0x80000001` (0x18445C) it makes
   `thumbs = f_00372280(profile)` (0x1844D0). This is a 0x220-byte car-icon cache, vtable
   0x4B3AE8, loaded from the profile's `CarIcons.sig` "thumbnails". **If the gift vector is not
   empty** (0x1844E4), it builds the **"CarUnlock" screen** on the stack:
   `f_0033D220(this, 2, &gifts, profile, thumbs, 0, 0)`, thiscall, `ret 0x18`. It runs the
   screen modally (vf+0x38) and then destroys it (0x33C6D0).
5. Then the garage's vf+0x34 (`f_00057150`) runs. After that the save
   **"ScoreboardUpdating"** screen (`f_0019CC60`) is given the vector {profile, thumbs}
   (0x18457B-0x184601, `f_0019D040`) and run. That saves the profile, the new car included, and
   the icon cache. Then `thumbs` is deleted (vf0(1)).

A second caller exists: `f_00156110` at 0x156178. It is a menu state machine whose class is not
identified; it runs when `[this+0x48]` is 0xC9..0xCD. It does the same with `this+0xC8` as the
gift vector. Its state 0x155C40 builds the same CarUnlock screen, with 10 000 / 5 000 ms
auto-advance, as a pushed screen (vf+8). Afterwards 0x155AE0 runs the save screen with
`this+0xB8` = {profile, thumbs}. So either flow consumes whatever is in the vector when
`f_0017E270` returns.

## The CarUnlock screen (where the car is really added)

- Base constructor `f_0033CE60(mode, &gifts, timeoutA, timeoutB)`. It copies the vector
  (`f_00048130`) to **this+0x611C** (begin +0x6120, end +0x6124). The index is at +0x1C14
  (starts at -1).
- `f_0033C9B0` (state, arg -1) moves to the next ordinal. It looks the car up with
  `f_00052A00(0x57D188, ordinal)` (the carlist table), loads its model into the viewer at
  +0x6130 and fills the labels (`f_0033C3F0`). When the list is used up, it closes the screen.
- **`f_0033CBD0`** is the derived class's input handler, secondary vtable 0x4A1F7C+0x58 (this
  pointer = object+0x28). It runs on A, or when the timeout expires:
  - `garage = [profile+0x35C]` (profile = object+0x64B0, thumbs = object+0x64B4).
  - **`garage->vf3C()`** = "full" (`f_00053680`: vf38 count >= 300). If the garage is full, the
    player gets credits instead: `f_00078940(profile, value, 0)` (the add-credits function), and
    the "GarageIsFullPopup" shows.
  - Otherwise: `entry = garage->vf44(ordinal, 0, 0, 0)`, then
    `thumbs->vf24(garage->vf7C(entry) /*slot*/, &viewer)`. That captures the new car's garage
    icon from the 3D view (`f_003718C0`: stores it, marks the cache dirty at +0x214).
  - Then it goes back to state 0x33C9B0 for the next car.

The value given to vf44 is `[gamecars row(ordinal)+4]`, which is used as the key of the
model.dat row (`f_0016CDB0` -> `f_0016CF20` -> `f_0016B6D0`). The dealer passes the same
derived value (0x36D30A). The docs say both tables are "by ordinal", so it is the ordinal itself
(a strong guess; not checked in memory).

## The function that adds a car to the garage

**Garage vtable 0x48EE34** (object made by `f_000570F0` / `f_00056870`, 0x6A00 bytes,
`[profile+0x35C]`; 300 entries of 12 bytes at +0x7D0; an occupancy bitset via +0x15E0).

`garage->vf44` = **`f_00056A40`**, thiscall (ecx = garage), callee pops 0x10:

```
entry* __thiscall f_00056A40(garage, uint32 ordinal, uint8 makeCurrent, uint8 useSlot, uint32 slot)
```

- It looks for `ordinal` in the carlist table (count at `[0x57D188]`, 0x8C-byte rows from
  0x57D18C, ordinal at row+0x7C). If the ordinal is unknown it returns 0 and adds nothing.
- `f_000560A0(ordinal, useSlot, slot)` takes the given slot if it is free, otherwise the first
  free one, and sets its bit. **With no free slot it uses -1 and corrupts memory**, so always
  check vf3C first, as every caller does. It then builds the car's stock data.
- It then sets up the default configuration (0x550D0, 0x55470, 0x52F10, 0x53280; byte +0xDC
  cleared). If `makeCurrent` is set, `garage->vf54(slot)` selects the car.
- **Returns** the 12-byte entry (`garage+0x7D0+slot*12`, whose +0 is the garage), or 0.
  `garage->vf7C(entry)` (`f_000536B0`) turns it into the slot index.
- vf48 (`f_00056B40`) is a lighter add without the default setup and without makeCurrent.

Other callers: the dealer's buy, `f_00079130(profile, ordinal, makeCurrent)`. It takes the
price from `[profile+0x3D4]`, then calls `vf44(ordinal, makeCurrent, 0, 0)`. The dealer screen
(0x36D31D) then paints the car, captures its icon (`f_00372280`, vf5C, vf24) and saves through
"SaveLoadHandler" with {profile, thumbs}.

Pointers available at run time:
- `profile = xb_rd32(0x58E2A0 + 0x1A44)` (what `f_00077AC0` returns; refcount at +4,
  `f_000777F0` releases it).
- `garage = xb_rd32(profile + 0x35C)`, `vt = xb_rd32(garage)` (0x48EE34).
- `session = xb_rd32(0x592984)` (0 off the track); end state at `session+0x24`.

## Recommendation: push N into the gift vector (wrap 0x17E270)

This is the safest route. The game itself then shows the CarUnlock screen with the car, handles
a full garage (credits plus a popup), adds the car with `vf44`, captures its garage icon and
saves the profile and the icons. It works for both callers (SeriesFlow and the 0x156110 flow).
Mayhem races are career events (Mayhem Tour, series 108), so they end through SeriesFlow.

wraps.txt: `17E270  # the race's rewards (cdecl: per-event bytes, gift vector*): hle_... gives
the Mayhem Moments car`

```c
void orig_f_0017E270(XbCtx *c);
void f_0017E270(XbCtx *c) {
    uint32_t gifts = xb_rd32(c->esp + 8);           /* cdecl arg 2 (vector<int>*), at entry */
    uint32_t s = xb_rd32(0x592984);
    int finished = s && xb_rd32(s + 0x24) == 0;      /* the game's own condition for rewards */
    orig_f_0017E270(c);                              /* (its ret pops only the return address) */
    if (!gifts || !finished || !gift_pending() || !car_known(N)) return;
    uint32_t tmp = c->esp - 0x10;                    /* inside rt_guest_call's 0x40-byte gap */
    xb_wr32(tmp, N);
    uint32_t ecx = c->ecx;
    c->ecx = gifts;
    rt_guest_call(c, 0x0018C280u, 1, tmp);           /* vector<int>::push_back(&N) */
    c->ecx = ecx;
    gift_mark_given();                               /* in <mods>/..., never the save */
}
/* car_known: n = xb_rd32(0x57D188); any i < n with xb_rd32(0x57D18C + i*0x8C + 0x7C) == N */
```

Notes:
- Keep the gift "pending" until a race that finishes normally. An aborted race (0x80000001)
  shows no CarUnlock screen, so do not mark it given then. The `== 0` check above matches that.
- Mark it given when it is pushed, in the mods folder. If the user turns the game off during
  the car screen, before the save, the car is lost while marked given. A stricter way: also wrap
  `f_00056A40` and mark it given when it is called with N while the gift is pending.
- Validate N against the carlist table. With an unknown ordinal the screen passes a null car
  record on (0x33CA5A -> 0x270D00) and would probably crash (a guess).
- The vector may already hold series prizes. Pushing at the end just adds one more car screen.

## Alternative (not recommended): add it directly from a menu hook

On the game thread, off the track (`[0x592984] == 0`, e.g. in the f_00078050 wrapper):

```c
uint32_t p = xb_rd32(0x58E2A0 + 0x1A44), g = xb_rd32(p + 0x35C), vt = xb_rd32(g);
c->ecx = g; int full = rt_guest_call(c, xb_rd32(vt + 0x3C), 0) & 0xFF;
if (!full) { c->ecx = g; entry = rt_guest_call(c, 0x00056A40u, 4, N, 0, 0, 0); }
```

This adds the car, but:
- Nothing captures the garage icon, so that slot shows whatever CarIcons.sig had there.
- Nothing saves, so the car is only stored at the game's next save (the next race end, a dealer
  buy).
- There is no "you won a car" screen.
- Calling into the game from inside a getter that the menu draws each frame is re-entrant.

## Sure vs guessed

Sure (read from the disassembly):
- The chain f_00183F30 (SeriesFlow vf+0x20) -> f_0017E270 -> f_0007AD40 -> push_back.
- The vector is consumed by the CarUnlock screen (f_0033D220/f_0033CE60/f_0033CBD0).
- vf44 = f_00056A40, with its arguments, return value and the slot overflow when full.
- The garage-full credits branch, the icon capture and the save screen afterwards.
- The vtable addresses and the class-name strings.

Guessed:
- The value passed to vf44 equals the vector's ordinal (gamecars+4 = model.dat key).
- A bad ordinal crashes the screen.
- f_00057150 (garage vf34, after the screen) is a refresh of the current car.
- What the 0x156110 flow is.

Nothing was run in the game.
