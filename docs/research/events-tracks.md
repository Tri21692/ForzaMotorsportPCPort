# Custom events or custom tracks: which is easier (27 Oct 2026)

Research first; a custom series built since (27 Oct, below).

## Events: easy

A career series is one XML file in `Mega.ca2`, `events\<kind>\Ser<NNNNN>.xml`
(kinds: club 20, spec 20, proseries 15, endurance 10, pointtopoint 10,
onlinecareer 9; arcade has its own 12 in `arcade\`). The executable builds
the names with `%s\Ser%05u.xml`, so a new series is a new numbered file next
to the others. One holds:

- `<series displayname seriesnameid seriesdescid seriesid seriesordinal seriesorder Icon>`:
  its name and description by string id, its order, its picture (an index
  into `Events\Events.xpr` and `Events_LG.xpr`);
- `<Scoring>`: per finishing place the rewards (`CareerCarUnlock`,
  `CareerCarGift` by car ordinal, money);
- `<Restrictions>`: who may enter (`Attrib="region" Value="Europe"`, class,
  make, drivetrain...);
- `<AIField>`: the opponents (car ordinal, Drivatar, difficulty);
- `<event ... type="Single">` blocks: the track (its tracklist ordinal),
  laps, the AI field's size.

What adding one takes: the file, its strings (name, description) added the
way addcar.py adds car names, and a check of how the game counts series
(numbered files until one is missing, or a fixed count). Our added cars can
be prizes or entry restrictions. A few hours, mostly testing in the menus.

## Tracks: very hard

A track is, per `forzadb\tracklist.xml` (which the game checks against a
hash: an edited copy gives "a problem with the disc", so it is patched in
memory, as XBRT_ZONE_LEAD does), a folder on the disc of formats we have
not decoded:

- `QuickPreview1.xb2` (the scenery, 55 MB for Rio) and `quickpreview1.xbp.*`
  (its resources), `QuickPreview1.col` (collision), `QuickPreview1.pvs*`
  (what is visible from where, by zone), `TrackLightmap.dat`,
  `AudioSpline.bin`, `StreamingWaveBank.xwb`, `Flythrough.bik`;
- in `Mega.ca2` `tracks\<name>\`: `track.ini`, `maxdata.xml`,
  `tracksegcams.xml` (replay cameras), `pitcams.xml`, `specialzones.xml`,
  audio settings;
- `AI\DrivatarV2\TrackList.bin` and per-track AI data (racing lines the
  Drivatars learned), plus the minimap and load-screen pictures.

A new track means converting geometry from somewhere (another game's track,
like the cars from Need for Speed) into all of that: the scenery format,
collision, visibility zones, AI lines, cameras and lighting. Each is its
own reverse-engineering project, weeks of work, and the AI would need racing
lines it never learned. A new layout of an existing track (a different
start, a shortcut closed) is smaller but still needs AI lines and cameras.

## Verdict

Events first: data the game already reads as text, and a good use for the
added cars (a Lamborghini series, a series that gives the M3 GTR).

## A custom series, built (27 Oct)

tools/addseries.py adds one; the Forced Induction Cup (Club Ser00019,
Level 15, after the disc's three Level 15 series) is the first: Class B cars with a turbo or supercharger, four
races (Tsukuba, Road Atlanta, Tokyo, Silverstone), the Buick GNX to the
winner, a field of eight Class B turbo cars.

- The loader formats `%s\Ser%05u.xml` from 1 up and stops at the first
  number missing (0x7E9B0), and the list shows them in that order. So a
  series goes in by renumbering the files after its place (added at the end
  it showed after the Level 25 one); seriesorder (+0x554 of the series,
  read at 0x7E523) follows the place.
- seriesorder also keys a sequential series' result in the profile (+0x6a4,
  a byte each, 0x77AE0 and 0x799D0; +0x6c4, 12 bytes each, 0x77BB0), only
  when `sequential="true"` (+0x549), which only the Pro Series have. Moving
  a Pro Series would move its saved progress; addseries.py adds those at the
  end only.
- seriesordinal (+0x550) numbers the career's series across all the lists
  (club 0-19, endurance 20-29, online 30-38, point to point 39-48, pro series
  49-63, spec 64-83; the arcade's 0-11 on their own) and is only searched
  for (0x7CA00, a linear search, no table by it). The cup had 20 at first,
  the same as endurance's first series; it is 84 now, the next free one.
- Restrictions are looked up by field name in the car database (0x170720):
  carid, power, torque, redline, gears, weight, weightdist, pwr, perfclass,
  perfsubclass, value, min/maxupgrade, aspiration, speed, acceleration,
  braking, handling, rarity, make, family, location, region, year,
  drivetrain, engineplacement, body, chassis and their _id/_name forms.
  The disc's events use 12 of them; aspiration (gamecars.dat at 116: na,
  turbo, twin_turbo, positive_super, cent_super) is new here. Top-level
  restrictions must all hold, `<or>` groups any one. String values are the
  names in forzadb\cardb\<field>.dat.
- Strings: media\Loc\<language>\EventStrings.str, the format of
  CarDataStrings.str; new ones take ids after the highest (10011 on).
- Logos: the series list draws `Icon` from frontend\<language>\ico_events_lg.xpr
  (linear A8R8G8B8, 210 x 117 tiles, 15 a row, 60 tiles) and ico_events_sm.xpr
  (108 x 60, 25 a row, 50 tiles), in MegaXPR.ca2 (the series screen builds
  the path, 0x1834E6). The small strip has no free tile and growing it in
  eight languages does not fit in MegaXPR.ca2, so addseries.py takes the
  highest tile no series uses: 24, 28, 30, 43, 44, 46 and 49 are the art of
  series that were cut (49, Trueno, holds the new logo). Events.xpr and
  Events_LG.xpr are the event-type badges (8), not series logos.
- Event ordinals: club 0-70, endurance 71-80, online 81-116, point to point
  117-136, pro series 137-244, spec 245-350; the new events are 351-354. The
  profile keeps a medal byte per career event ordinal at +0x4a4 (512 of them,
  the next field at +0x6a4) and per arcade event at +0x464 (64), so the
  save's layout does not change. checkin.ini's
  GameSettings\EventCounts\CareerEvents (315, the career's events less the
  online ones) bounds the completion percentage's loop; left as it is, the
  new series may not count towards it.

## Pacific Shipyards as a circuit (27 Oct)

Both layouts (Vancouver, VancouverReverse: same scenery, `reverseSplines`)
are used only by point-to-point events; the ends are ~2.5 km apart.

- QuickPreview1.col, decoded: u32 grid columns and rows (20 x 27), f32
  bounds (min x, min z, max x, max z), 100 m cells; 0x28 the file size;
  0x4c the cells used, 0x58 a record each (u32 index, cell, block offset,
  size, 0, end). A block: u32 vertex count, triangle count, vertex offset,
  triangle offset (from the block), a 12 x 12 sub-grid and the cell's
  bounds (the sub-grid's index at +0x278 not worked out); vertices 16 bytes
  (f32 x, y, z, u32), triangles 28 (u32 flags, three vertex offsets, f32
  normal). Flags: 0 road, 0x500 and 0xa00 other surfaces, 0x900, 0x300,
  0x400 walls. scr/lambo/colmap.py draws it from above, colat.py heights.
- The collision is the course alone, a ribbon with walls: no side streets,
  no ground beyond. The teardrop where the course crosses itself is an
  overpass (4.6 m). The scenery (QuickPreview1.xb2, 25 zlib streams, 98 MB
  unpacked) has ~40 `sideroad_NN` meshes and "road closed" signs: side
  streets that are only drawn.
- The best loop: after Pacific Shipyards II's start the course wraps a
  paved, fenced truck lot (flat, -1.8 to -0.1 m); a ~150 m connector across
  it, from the upper road's kink (-495, -77) to the lower road's corner
  (-455, -222), closes a loop of about 1 km.
- Not found yet: where the game keeps the centre line it measures progress
  and laps by (not in the text files; AudioSpline.bin, the xbp files and
  the xb2 are candidates), and the AI's lines (AI\DrivatarV2).

## Pacific Shipyards Circuit: what is built, what the scenery holds (27 Oct)

Built (tools/shipyardloop.py, tools/coledit.py; runtime/file.c): a track
list entry VancouverLoop (Hot Lap 22, no AI) with its own collision, the
loop's edge splines in its own copy of vancouver.res (the runtime opens
mods\hdd\Partition4\<track>\ in place of the cache's files once the track's
collision file has been opened), and a visibility file whose cells all show
Pacific Shipyards II's cells 2-5. It loads and the existing roads draw; the
link has collision but nothing drawn: the scenery has no ground there.

- A track entry names its scenery (resourceFile), collision, visibility
  (pvsFile) and data folder; D:\MEDIA\tracks\<name>\ must hold the audio
  spline, lightmap and glassenv (Flythrough.bik unless Video names one).
  The game copies the collision to N:\<name>.col the first time and reads
  that copy ever after: a changed collision in media\tracks\ is never seen
  (every collision change made for the circuit after its first build went
  unused until it was also installed as track\<track>\hdd\Partition4\
  <name>.col). A collision vertex's u32 is its triangle's normal packed
  (x bits 0-10, z 11-21, signed with 1023 = 1; y 22-31, 511 = 1).
  Screenshots save the vertex constants beside them (.cst) and
  tools/shotpos.py gives the camera's position from them. Laps: a track without
  start/end (and with hotlapordinal) is a circuit; the edge splines, open
  polylines (Tsukuba's ends 7.5 m apart), carry the lap.
- QuickPreview1.pvs (version 0x131f0cf): '3SVP', version, u32, guid, u32
  cells (24); per cell three lists (u32 count; entries of 4, 8, 4 bytes:
  u16 mesh, u16 mask of the cell's 16 steps, the middle list a u32 more);
  6 bytes. Cells run in driving order; the game picks one by progress and
  streams what the cells around it list. The visibility files only load
  from Pacific Shipyards II's folder (from another, the load fails after
  the .stx). .pvs.stx: low-resolution copies of textures, the same for both
  directions; .pvs.ppw: per mesh a bounding sphere (radius, centre).
- The bundle (tools/xb2.py): a 0x200 header, from 0x202 per resource 24
  bytes (header offset, name hash, data offset in the unpacked bundle, size
  twice, name offset from the names at 'resnametable'), then the names.
  Resources are numbered from 9 (0-8 are the bundle's own tables; `types`
  holds a byte per resource). model_quickpreview: u32 meshes (4528, the
  numbers the visibility lists use), their offsets, records of 24-44 bytes;
  the 28-byte one: flags, u32, index count, vertex bytes, u16 vertex buffer,
  u16 stride in dwords (6), u16 primitive (6, a strip), u16 texture, u16
  lightmap, u16 shader. A vertex buffer: the vertices (24 bytes: f32 x, y, z
  in world space, u32, four s16 texture coordinates) then u16 strip
  indices. quickpreview1.xbp.svb: the small vertex buffers again (u32
  resource, u32 size, data; 1993), loaded with the bundle; .cbx: 140 boxes.

## A Time Trial category in career mode (28 Oct)

- The career's Go Race screen shows six categories, a table at 0x52E850
  (0x34 bytes each, filled by the static initializer at 0x307F30): +0 the
  folder's name (series are read from D:\MEDIA\Events\<name>\Ser%05u.xml),
  +4 the kind (5 online, 1 point to point, 2 club, 3 spec, 4 pro series, 0
  endurance), +8 and +0x18 its title and description. The order is Online
  Career, Point to Point, Amateur (Club), Spec, Pro Series, Endurance; loops
  stop at 0x52E988, so a seventh means patching the translated code.
- Online Career is told apart by its name (strcmp with "OnlineCareer" at
  0x4A7194, 0x184FA5 and 0x18575A) and offline only says to sign in to Xbox
  Live. XBRT_CAREER_TIMETRIAL=1 (runtime/nv2a.c) renames it "TimeTrial" (a
  string put in 274 bytes of .rdata nothing uses, 0x4D02B0) and gives it a
  club's kind: it then opens like the other categories.
- Each category also plays D:\MEDIA\Events\<name>.bik; a missing one is a
  disc error. Its title is GameStrings IDS_Event_OnlineCareer (49), its
  description UIStrings IDS_Event_OnlineCareer_Help (141).
- tools/careertimetrial.py fills it: a series a class, Class D (any level)
  to R-P1 (level 50) as the Spec series' ladder, two one-lap time trials
  each with the main menu's Time Trials' rolling starts
  (driverchallenge\ser00001.xml), no other cars; event ordinals 355-370,
  series 85-92. Headless (the first version): the category, its series, the
  race select with a local scoreboard, the grid and the rolling start work.
- Placed by the clock (runtime/hle_career.c): everything after the finish
  reads the player's place from the racer the game gets through 0x755D0
  (the racer list at 0x58DAA0: +4 the racers, +0x10 their count; a racer's
  +0x14 type, 0 a person; +0xBC its place, 1 first; +0xC0 its timing: +0x94
  the best lap, +0xA0 the race's time, seconds, +0x9C laps done): the
  results table (0x1A5BFB), the podium flag (0x184407) and the scoring
  (0x17E270: rewards per place, and the medal, 0x77B60, the profile's byte
  at +0x4A4 + the event's ordinal, kept at its lowest). The running event
  is [0x592984]+0x318 (its EventOrdinal at +0x10, its laps at +0x24; the
  series at +0x314). The replacement 0x755D0 sets the place from the time
  against timetrial.txt's three targets (laptime.py's estimate for the
  track and class, times 1.04, 1.09 and 1.15), once the lap is done.
- The series' place (0x1A76B0) is the worst of its events' best places
  (each event's medal byte, 9 unplayed; the profile fills them with 9 at
  0x78715), and its rewards come as it improves (0x17E400); so a car on a
  series' 1st place is won by winning every event in it. Each time trial
  series gives one no other career series gives.
- The race HUD shows the three targets under the game's lap timer
  (glover.c, gl_tt_hud_draw), each dimmed once the clock passes it.
- The game formats times from milliseconds at 0x169F00 ("%d:%.2d.%.3d").
- Both runs of the first version crashed on leaving the results (an
  indirect call through nothing at 0x26C6AC in the heap's code, then a
  thread started at 0): its series had an empty AI field. Each series now
  lists its class's Spec series' field (none of them race); not yet
  tested.
- .str files carry padding after their structure (its size at +20);
  addcar.replace_strings keeps it, and round-trips a file unchanged.

## Pacific Shipyards Circuit: what drew and what blocked (28 Oct)

- Solid props are quickpreview1.xbp.cbx's boxes (no CollObjs.xml for
  this track): a hidden barricade keeps its box, an invisible wall (the
  hairpin's west half: a 54 x 20 m box). The circuit drops every box
  reaching into its road anywhere round it, not only on the new stretches.
- quickpreview1.xbp.svb (zlib; u32 1, a 16-byte id, u32 count, then per
  buffer u32 resource, u32 size, its bytes) holds byte for byte copies of
  the bundle's small vertex buffers (up to 2 KB; 1993 of them), loaded
  with the scenery. The kerbs, walls and tunnel were drawn in meshes from
  far off: the small ones had their svb copies left as they were, the large
  ones stream in with their own part of the track only. Now each strip is
  simplified (a straight run is one quad), cut to fit the svb meshes the
  loop never shows (243), and the svb rewritten for the track
  (track\<track>\media\tracks\Vancouver\quickpreview1.xbp.svb). Not yet
  seen in the game.
- The walls beside the new road stand on what is drawn there (a fence,
  wall, rail or building face within 8 m of the edge), else 2 m out behind
  the drawn kerb: at 2 m a car went through a fence half a metre out first.
- The side roads 31 and 04 meet at a right angle; the loop cut it by 5 m
  through a wall. The strip left the start road at its top (569) with a
  120 degree, 2 m turn back whose edges crossed; it leaves at 571 now.
- A new track's AI files borrow a stock track's with as many segments;
  aitrack.install eases the turns' threshold until the count is one there.
