# Custom events or custom tracks: which is easier (27 Oct 2026)

Research only; nothing built yet.

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
