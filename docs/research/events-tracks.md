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

tools/addseries.py adds one; the Forced Induction Cup (Club Ser00021,
Level 15) is the first: Class B cars with a turbo or supercharger, four
races (Tsukuba, Road Atlanta, Tokyo, Silverstone), the Buick GNX to the
winner, a field of eight Class B turbo cars.

- The loader formats `%s\Ser%05u.xml` from 1 up and stops at the first
  number missing (0x7E9B0), so a new series is the next number in its kind.
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
  save's layout does not change. Series ordinals are per kind (club 0-19,
  the new one 20) and only looked up. checkin.ini's
  GameSettings\EventCounts\CareerEvents (315, the career's events less the
  online ones) bounds the completion percentage's loop; left as it is, the
  new series may not count towards it.
