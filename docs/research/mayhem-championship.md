# Mayhem Tour Championship: proposed races and Mayhem Moments (7 Nov 2026)

This is a research proposal only. No game or mod file was changed, and the game was not launched. Every spot comes
from the disc's scenery, collision and AI data, plus the mods folder's overrides for the two mod tracks. **None has
been tried in game.**

## The idea

The championship has eight one-race rounds, each with one new Moment. Seven rounds are on tracks the Mayhem Tour
doesn't use. The eighth is New York Circuit Short, a different track ordinal from the Tour's New York round, at a
spot 160 m from Crash 'R Us. Each Moment is a solid, recognisable thing right beside the racing line, where cars
bunch up: a braking zone, a hairpin or a bend.

Lap times are `tools/laptime.py` estimates for Class A (the Tour's class). laptime.py uses a point-mass model, so a
person drives a few percent slower. Lap counts aim for 2-4 minutes.

| # | Track (ordinal) | Laps | Est. race (Class A) | Moment | Centre x, z | r (m) | top y | What to do | Overview |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Mazda Raceway Laguna Seca (1) | 2 | 2 x 1:46 = 3:32 | **Re-Tired** | -124, 497 | 30 | - | Shove a rival into the tyre stacks lining the braking zone into Turn 11 (the last hairpin) | [01](mayhem-championship/01_laguna_retired.png) |
| 2 | Silverstone Circuit (2) | 1 | 2:14 | **A Bridge Too Far** | -305, 222 | 32 | - | Take a rival out under the bridge at Bridge corner (tyre wall on the right, bridge piers on the left) | [02](mayhem-championship/02_silverstone_bridge.png) |
| 3 | Blue Mountains Raceway (8) | 1 | 2:28 | **Toyo Story** | -770, 282 | 32 | - | Slam a rival into the tyre barrier on the outside of the hairpin just past the Toyo bridge | [03](mayhem-championship/03_bluemountains_toyo.png) |
| 4 | Road America (16) | 1 | 2:38 | **Grandstand Slam** | 280, 428 | 28 | - | In the Turn 5 braking zone, pin a rival against the concrete wall below the bleachers | [04](mayhem-championship/04_roadamerica_t5.png) |
| 5 | Tsukuba Circuit (26) | 3 | 3 x 1:07 = 3:21 | **Dunlop-Sided** | 85, -5 | 30 | - | Take down a rival under the Dunlop bridge (its legs stand at both road edges) | [05](mayhem-championship/05_tsukuba_dunlop.png) |
| 6 | Alpine Ring (27) | 2 | 2 x 1:37 = 3:13 | **Pit-iful** | 458, -293 | 25 | - | Out of the last corner, push a rival into the tyre wall at the pit-lane split | [06](mayhem-championship/06_alpine_pitentry.png) |
| 7 | Pacific Shipyards Circuit (82, mod) | 3 | 3 x 1:08 = 3:24 | **Double Parked** | -485, -85 | 25 | - | Send a rival into the parked cars on the outside of the right-hander | [07](mayhem-championship/07_shipyardcircuit_cars.png) |
| 8 | New York Circuit Short (52) | 3 | 3 x 1:10 = 3:29 | **Happy Wreck Year** | -165, -240 | 32 | - | At the Times Square hairpin round One Times Square (where the ball drops), wreck a rival into the barriers | [08](mayhem-championship/08_nyshort_timessquare.png) |

No circle needs a top y. In each one, a single run of the track's own line passes through, and no other road crosses
above or below it.

### The lines for mayhem.txt (proposed, not applied)

```
moment 1 -124.0 497.0 30 - Re-Tired|Take down an opponent into the Turn 11 tyre stacks at Laguna Seca.
moment 2 -305.0 222.0 32 - A Bridge Too Far|Take down an opponent under the bridge at Silverstone.
moment 8 -770.0 282.0 32 - Toyo Story|Take down an opponent in the hairpin past the Toyo bridge at Blue Mountains.
moment 16 280.0 428.0 28 - Grandstand Slam|Take down an opponent into the wall below the Turn 5 bleachers at Road America.
moment 26 85.0 -5.0 30 - Dunlop-Sided|Take down an opponent under the Dunlop bridge at Tsukuba.
moment 27 458.0 -293.0 25 - Pit-iful|Take down an opponent into the pit-entry tyre wall at the Alpine Ring.
moment 82 -485.0 -85.0 25 - Double Parked|Take down an opponent into the parked cars on the Pacific Shipyards Circuit.
moment 52 -165.0 -240.0 32 - Happy Wreck Year|Take down an opponent at the Times Square hairpin in New York.
```

**Limit:** runtime/hle_quickrace.c has `MM_MAX 16`. The 8 existing Moments plus these 8 fill it exactly. Adding any
alternate means raising `MM_MAX`, and the F1 Mayhem Moments page (glover.c) would then show more than 16. That page
layout is untested even at 16. Names fit `name[40]` and the what-to-do texts fit `todo[120]`.

## Why each spot, and what was verified

How collision was checked. **.col walls** means wall triangles (|normal y| <= 0.7) in the track's QuickPreview1.col
lying on the prop's own footprint. **cbx** means a solid-prop box in quickpreview1.xbp.cbx that overlaps it.
**Nothing between** means no .col wall crosses, at car height, the straight line from the AI line to the prop. The
turn rate is the AI line's heading change in deg/m (a hairpin is 4-8, a fast kink under 1).

1. **Laguna Seca, Turn 11 tyre stacks (Re-Tired).**
   - 13 wrapped tyre stacks (`tirestack_1`-`_13` / `tirewrap*`) stand in a row along the left edge of the braking
     zone into the last hairpin, 6.2-6.6 m from the AI line (line points 1591-1624; the hairpin is 1625-1650 at up
     to 3.9 deg/m).
   - Each stack carries 19-29 .col wall triangles. They have no cbx; their collision is in the .col. Nothing between.
   - Cars brake hard here off the long back section, so a rival diving down the inside meets the stacks.

2. **Silverstone, Bridge corner (A Bridge Too Far).**
   - The bridge (`bridge_blackcar`) spans the road at line point 1892. One pier block has 7 .col wall triangles, the
     other has cbx box 4.
   - A tyre wall (`lodset18_tirewall_18`, 63 .col wall triangles) runs along the right edge 8.6 m from the line.
     Nothing between.
   - **Weakest pick:** this is a fast right kink (at most 0.7 deg/m), not a braking zone, so cars are less bunched.
     Silverstone's slower corners checked here (line points 1343-1419 and 1765) have open run-off with no wall near
     the line. Silverstone Short (47) doesn't pass the bridge.

3. **Blue Mountains, the hairpin past the Toyo bridge (Toyo Story).**
   - The last hairpin (line points 2401-2464, 2.5 deg/m) starts about 20 m after the Toyo Tires footbridge
     (`bridge_toyo`, cbx 155), which you see on the approach. The circle's centre is about 85 m past the bridge.
   - Its outside is a tyre barrier: `barrier_tire_43_o` (56 .col wall triangles, cbx 156/157) and `_43_o2` (58, cbx
     3), 8.4-8.6 m from the line. Nothing between.
   - The bridge itself is outside the circle. The circle is the hairpin.

4. **Road America, Turn 5 (Grandstand Slam).**
   - The end of the longest straight. Brake-marker boards (`braker_markers_s1`) count down to a 2.3 deg/m left
     turn.
   - On the right of the braking zone, a concrete wall with a catch fence (`concrete32`, `wirefence54`; cbx 194-197,
     15 .col wall triangles) runs right at the line's edge, with the big bleachers (`bleacher_large_04/05`) behind
     it.
   - The outside of the corner itself is open run-off, so the Moment is the braking zone beside the wall, not the
     exit.

5. **Tsukuba, the Dunlop bridge (Dunlop-Sided).**
   - The Dunlop footbridge (`dunlopbridge`) crosses a 1.5-1.9 deg/m bend at line point 451.
   - Its legs carry .col wall triangles: 9 for the leg 0.9 m from the line, 32 for the one 7.1 m out. Foam-block
     barriers (`foamblock_tan12/13`, 44 wall triangles) line the edge.
   - Tsukuba's paddock trucks (`ja_mitsu_truck`, `ja_isuzu_truck`) were checked too. They stand behind walls, out of
     reach.

6. **Alpine Ring, the pit-entry tyre wall (Pit-iful).**
   - The pit lane splits off to the right on the exit of the last corner (line points 1634-1677, up to 2.0 deg/m).
   - The split's nose is a tyre wall (`49_`-`53_tirewall`, 43-54 .col wall triangles), 10-13 m from the line.
     Nothing between.
   - A rival pushed wide on the exit goes straight into it.

7. **Pacific Shipyards Circuit, the parked cars (Double Parked).**
   - A row of parked cars (`cars_15`: cbx 19, 9 .col wall triangles; `cars_02b`: 10) stands at the road's edge on
     the outside of a 2.9 deg/m right-hander, 6.5 m from the line (line points 888-911).
   - Checked against the circuit's own overrides: its VancouverLoop.col, cbx and vancouver.res in mods_track. It's a
     different place from every Mother Trucker trailer, which are all on Pacific Shipyards (20).
   - **Not verified:** that the cars are still drawn in the circuit build. shipyardcircuit.py repacked svb meshes the
     loop never shows as donors, and the cars' small buffers could be among them. Blender renders can't show this,
     so check it in game.

8. **New York Circuit Short, the Times Square hairpin (Happy Wreck Year).**
   - The tightest corner in the set (8.3 deg/m, line points 1104-1143) goes round One Times Square (`onetimessquare`,
     cbx 1), the New Year's Eve ball-drop building.
   - The outside is cement barriers with billboard boards (`cementbarriers`, `ny_barriers_billboards41/47_short`;
     cbx 45, 49, 57-61; 7-16 .col wall triangles each), 10-13 m from the line. Nothing between.
   - This reuses New York's scenery. The Tour's Crash 'R Us is on track 18 at (-180, -80); this is track 52, 160 m
     south, at a different object.

## Alternates

| Track (ordinal) | Laps | Moment | Centre x, z | r | What to do | Note | Overview |
|---|---|---|---|---|---|---|---|
| Laguna Seca (1) | 2 | **Corkscrewed** | 335, 100 | 35 | Take down a rival in the Corkscrew | Swap for Re-Tired if you want the famous corner. The tyre wall on the outside is 15-20 m off the line and the Corkscrew signs barely collide (1 wall triangle), so it's a bend Moment like Rio's. Line drops ~10 m inside the circle | [a](mayhem-championship/alt_a_laguna_corkscrew.png) |
| Test Track Infield (21) | 1 | **Crash Test Dummy** | 810, 235 | 35 | Slam a rival into the chevron boards at the hairpin | Chevron boards are solid (`sign_cornerarrow08`: 240 wall triangles, cbx 30/68); 7.2 deg/m. **But one lap is about 4:32 (Class A estimate), over the 4-minute target** | [b](mayhem-championship/alt_b_testtrack_hairpin.png) |
| Fuji Speedway (84, mod) | 1 | **Fuji-Yama Slamma** | -645, 1205 | 40 | Take down a rival in Turn 1 after the 1.5 km straight | A bend Moment only. Fuji's cbx is empty, its walls are 40-60 m out on the run-off, and its moved Road Atlanta props can't be placed from the .res (picture shows the road and walls only). Lap estimate 2:14 | [c](mayhem-championship/alt_c_fuji_t1.png) |
| Alpine Ring (27) | 2 | **Lights, Camera, Wreck-tion** | -180, -125 | 25 | Take down a rival under the camera crane | The crane truck stands behind the road-edge wall and its arm hangs over the line (0.7 deg/m bend). Very visible, but the crane itself can't be hit (3 wall triangles at its base) | [d](mayhem-championship/alt_d_alpine_crane.png) |

Also rejected:
- **Pacific Shipyards Circuit steamroller (Steamrolled).** It sits on the circuit's road at a corner (line points
  694-700) with its cbx box dropped. If it's drawn, cars pass through it.
- **Nürburgring (19).** A 21 km lap.
- **Silverstone Short, Road Atlanta Short and Maple Valley Short.** They overlap tracks that already have a round.

## Open points

- Nothing here has been driven. Check each spot in game, for example with a photo run like the Tour's (XBRT_MM_PHOTO
  staging per Moment). This matters most for Double Parked (do the cars draw?) and A Bridge Too Far (do cars bunch
  in a fast kink?).
- The collision evidence is data, not driving. Wall triangles and boxes show something solid is there. The .col
  surface codes (0x1300/0xb00 on tyre walls, 0x400 on concrete) weren't decoded.
- Three rounds are one lap (Silverstone, Blue Mountains, Road America), so the player passes their Moment only once.
  mayhem.txt's `spread <track> <percent>` could start the rivals closer, as was done for Pacific and Fujimi.
- Building the championship (a series like the Tour's, event ordinals, the `events` line, photos for the F1 page) is
  separate work and wasn't started.

Scripts, all read-only, are in `E:\xbrt_scr\moments2\`: m2.py, fams.py, famgroup.py, chk.py, scan.py, ov.py,
final.py and laps.py. They ran with `python -E -P` rather than `-I`, because NumPy is installed only in the user
site-packages, which `-I` turns off. `-P` still keeps the script and current folders off the import path.
