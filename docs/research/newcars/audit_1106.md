# Add-on car audit, 6 Nov (the user's 35 store screenshots, 11:02-11:07)

## 1. Wheels
- Maloo (shot 228): the front wheel is too big and sits forward of its arch.
- Huracan Performante (282): both arches stand high over the wheels, with black gaps.
- M8 GTE (346): the rear wheel sits back in its arch.

## 2. Lights
- Brera (78): tail lights dark grey, unlit.
- 335i (104, 108): left tail light white/clear, right one red.
- Eclipse GT (113, 119): headlights black holes; tail lights missing (black voids beside the ECLIPSE panel).
- Evora (154): round tail lights grey/white, no red.
- RS 5 (199, 203, 223): headlights and tail lights black.
- Sesto Elemento (304): headlights black.

## 3. Geometry and textures
- Senna (363): the front fender behind the front wheel is missing (see-through to the frame).
- Terzo (360, 368): see-through hood vent, the front fender stands off the body, a red shard under the nose.
- Diablo SV (279): wing pieces sit on the nose; the front fender over the wheel is torn.
- M8 GTE (346): jagged white sawtooth along the sill; a torn edge behind the front wheel.
- Charger (233): ragged edge on the rear quarter; the lower body is black.
- Countach (264): no side glass; a black block hangs under the nose.
- Celica GT-Four D-Spec (126): the big wing floats above the boot, with its middle missing.
- Eclipse GT (119): the big wing (kit) stands far above the boot.

Looked fine: Chiron, Jesko, SC63, ZR1, GT2 RS, GTX1, Egoista, M3 GTR, Silvia S15 / D-Spec, 190E.

## Done (installed 6 Nov ~12:32; backups E:\xbrt_scr\newcars\backup_preaudit_20261106_1230, E:\xbrt_scr\kits\backup_20261106_1232)
- Wheels: newcars.py ARCHES for the M8 GTE, Senna, 190E, Eclipse, Charger, Brera, LF-A, XK, 4C, Countach, from
  sideplot.py (each arch's opening against the game's wheel). Every add-on's arches now sit within 8 cm of its hubs.
- Lights (tools/nfsu2forza.py, all Most Wanted ports):
  - Every made or re-pointed lamp sheet is packed. The Evora's named only BRAKELIGHT_RIGHT, and its lamps read blank
    atlas: grey-white.
  - The lit _ON sheets are preferred. Of two cut-short sheets the same size, the brighter one is taken.
  - Tail-light sheets have their red lifted.
  - Flat, near-black and small tint sheets count as lenses, also at draw time in parts of mixed materials (the
    Brera's grey tint).
  - Trim triangles get their own corners.
  - A lamp's own sheet is kept, not swapped for its end's. Its material follows its end of the car (the RS5's rear
    lamps are on its HEADLIGHT sheet).
  - Lamps go into the body when the template has no lamp slot (the Eclipse GTS: tail lights and headlights were
    missing).
  - NFSU_COVERS (newcars COVERS, the RS5) leaves out shells of other sheets within ~5 cm of its lamps.
- Diablo: the raised pop-up lamp pods are left out. The nose shows their wells, as if closed.
- Celica GT-Four (and D-Spec, Neon, Silvia): Underground 2 spoilers face away from the car with a black underside.
  The wing had drawn only its end plates.

## Left as they are
- Countach glass: its own is crumpled shards, so the open frames are kept.
- Terzo, Senna: the source's own concept-car panels and openings.
- M8 GTE sill: a ragged skirt edge in the source.
- Brera, Evora and RS5 tail lights: now their own lamp art, but dim in Blender. To check in game.
