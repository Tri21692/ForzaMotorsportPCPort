# Forza Motorsport's car files

What a car is made of on the disc, as far as it is decoded (25 Oct 2026),
for the custom-cars work on the roadmap. `tools/forzacab.py` lists and
unpacks the archives.

## Where a car lives

| File | What it holds |
|---|---|
| `media/cabs/car_<name>.cab` | The car itself: `car.carbin` (model), liveries, engine sounds |
| `media/cabs/Cars.ca2` | Every car's physics, engine, liveries list and config, as XML |
| `media/cars/<Name>.liveries.bin` | Livery data for the paint shop (not decoded) |
| `media/caricons1-5.xpr` | Menu icons (copied to each save as `CarIcons*.xpr`) |

`Cars.ca2` is a cab in 4 MB zlib streams. The installer unpacks it to
the cache partition as `hdd/Partition4/cars.cab`, and the game reads that
copy. `Mega.ca2` and `MegaXPR.ca2` (cache: `mega.cab` on N: = Partition4,
`megaxpr.cab` on Z: = Partition5) hold the shared files, wheels among
them. The game deletes and installs `mega.cab` again from the disc at
every boot. **Mod these as the disc's archives** (`mods/media/cabs/Mega.ca2`,
`tools/forzacab.py ca2`; see below), and the installer builds the cache
from them. The mods folder covers the cache partitions too
(`mods/hdd/Partition4/mega.cab`, read only), but do not put the installed
archives there: the installer checks the size of what it has just
written, the overlay answers with the mod's, and it truncates the real
copy, which was left zeros (on 25 Oct mega.cab, megaxpr.cab and cars.cab
on both disks, hidden by the mods' copies).

## Car icons and the saves

The car-select thumbnails are `media/caricons1-5.xpr`: a 128x4096 DXT5
texture each, 64 tiles of 128x64, car `Ordinal` n at pack n // 64 + 1,
tile n % 64. The game copies them into every profile's save
(`UDATA/4d53006e/<profile>/CarIcons1-5.xpr`, signed by `CarIcons.sig`) and
draws those copies. **Never edit save files:** on 25 Oct patching one tile
in those copies made the game delete each profile so changed (the backup
taken first was the only way back). Change the disc's pack through the
mods folder only (`tools/caridentity.py --icon`); the mods overlay does not
cover the save partitions (1 and 2) at all, by design (runtime/file.c).

## A car's identity (tools/caridentity.py)

What the menus show and the car drives like, all reachable through the
mods folder: `carlist.xml` (only Ordinal, shortName and Name are read,
per the executable's strings), `forzadb\cardb\model.dat` (104-byte rows
by ordinal: make id from make.dat, year, two prices, specs, and at 92 the
flags that make it buyable from the start, zero on a career prize) and
`gamecars.dat` (176-byte rows: physics summary, at 124 the ratings the
menu shows) in mega.cab; `cars\<car>	ooldata.xml` (its `<E0 Name>` is the
model name shown, its `File` the engine) and physics in cars.cab;
`engines\<engine>\physics` in cars.cab and `engines\<engine>\audio` in the
car's own cab (the wave bank paths name the engine); the model name again
in `media/Loc/*/CarDataStrings.str`. Career prizes are events'
`<rewards CareerCarUnlock="<ordinal>">`.

The Civic SI slot is now Forza's 240SX SE (an S14, a career prize) made
into the S13: 1991, 1,250 kg, 24,000 credits, on sale from the start, its
own engine copy (Nissan240SXS13, so the S14 is unchanged) at 160 lb-ft
with the power peak kept (155 hp).

The shop's power, torque and weight come from the disc's `Cars.ca2`,
which the background installer (code at 0x27E3E0) unpacks to the cache.
Its table is the BKGDINST section (xbe offset 0x5b5000, not preloaded):
per archive an entry of five u32 (two name offsets, first record index,
stream count, the last stream's unpacked size), and per 4 MB zlib stream
a record (u32 offset, u32 stream length, SHA-1 of the *unpacked* 4 MB;
Cars.ca2's at xbe offset 0x5b8c64). `InstallMarker1/2.dat` on Z: hold the
copy from the last install; a stream whose record differs is unpacked
again and its SHA-1 checked (a mismatch: "a problem with the disc"). For a
.ca2 in the mods folder the runtime rewrites its records, its entry's
last size and the section's header digest at boot (file.c), when it has
as many streams as the disc's; `tools/forzacab.py ca2` writes one from a
cab. With the S13's Cars.ca2 there the shop shows 155 hp, 160 lb-ft and
2,756 lb; Mega.ca2 and MegaXPR.ca2 (the wheel, the car's identity) go
the same way.

"A problem with the disc" also comes from any file that fails to load
(0x107830), a blank cache copy among them.

My Cars thumbnails are not the icon packs' tiles: the game renders each
owned car and writes it into the profile's `CarIcons1.xpr` (tiles 0, 1,
... by garage slot). They came out black in the port until LockRect
brought the GPU's drawing to RAM (25 Oct).

Removing a mod is safe: the overlay only reads. A car *added* (not in a
slot) that a save refers to will need a fallback once its mod is gone: a
stock Mazda MX-5.

## Adding a car (tools/addcar.py)

A car is, by name: its `carlist.xml` entry, its rows in `model.dat` and
`gamecars.dat`, `cars\<name>\` in cars.cab (tooldata, physics, config),
`car_<name>.cab`, `media/cars/<name>.liveries.bin` (179 of the 231 cars
have one), its wheel `tires\art\<File>\` (mega.cab and megaxpr.cab; the
only other name a car's files hold, in tooldata's `WheelStyle`), an icon
tile by ordinal, and its name strings. A file in the mods folder at a
path the disc does not have is found too, so a new `car_<name>.cab` loads.

- Ordinals run 0-243 for 231 cars; 13 are unused (56, 81, 82, 95, 96, 111,
  150, 159, 165, 172, 175, 223, 231). Events' `<AIPlayer aicarmodelid=>`
  names some of those (111, 150, 159, 165, 172, 175, 223, 231: a car
  there would race as those AI cars), so a new car takes one nothing
  names (56, 81, 82, 95, 96).
- The tables are sized from the files: model.dat's reader (0x16FE30,
  called from 0x173A90 for each forzadb table at 0x179740) divides the
  size by 104 into a vector; rows are kept in ordinal order and found by
  ordinal. gamecars.dat's loader is 0x63540, carlist.xml's 0x44340.
- `media/Loc/<lang>/CarDataStrings.str`: "LSBL", u32 28, u32 4, u32 block
  1, u32 block 2, u32 0, u32 0. Block 1: u32 size, u32 count, count + 1
  entries of u16 id, u32 offset in UTF-16 characters (the last id 0xFFFF,
  at the end of the text), then the NUL-terminated strings. Block 2: u32
  size, u32 count, entries of u16 id, u16 id, u32 byte offset, then ASCII
  names (`IDS_Model_44_Name`). model.dat holds a car's name and short
  name ids at 12 and 14 (Civic SI: 160, 161); the ids are the same in
  every language, 1-1125 on the disc.
- The archives grow (a car is ~20-40 KB of physics, ~300 bytes of tables;
  a wheel only when the mods changed it, stock ones are shared) and must
  keep their stream counts: cars.cab 6.3 of 8 MB, mega.cab 11.6 of 12 MB,
  megaxpr.cab 44 of 48 MB with three cars added. cars.cab has room for
  about 80 more.
- **The game's limits: 300 cars, ordinals 0-299.** carlist.xml is read
  (0x44340) into a fixed global table at 0x57D188: a count, 300 records of
  140 bytes from +4 (name in 60 bytes at 0, shortName at 0x3C, ordinal at
  0x7C), then at +0xA414 (record, ordinal) pairs. The loop has no bound:
  a 301st car would overwrite what follows. The profile's per-car tables
  are 300 long and indexed by ordinal (0x55610 finds the next set bit of a
  300-bit set; 0x56060 returns one of 300 12-byte records at +0x7D0 if its
  bit is set; an ordinal of 300 or more is skipped), and 0x15AE25 keeps a
  stored ordinal in -1..299. The icon packs reach 319. So 244-299 are
  free as well as the gaps: 61 more cars, 69 with the AI-named numbers.
  Seen in guest memory on 25 Oct: 234 cars, test copies at 244 and 299
  read with their ordinals.

The S13 as its own car (25 Oct, not yet seen in the game):
`addcar.py <disc> run/mods_addcar CivicSI Nissan240SXS13 --restore` on a
copy of the mods folder: ordinal 56, strings 1126/1127 ("240SX"), its own
wheel and engine, the Civic SI back as the disc has it. The game accepts
the three archives and boots to the attract movie. Profiles made before
keep their own signed copies of the icon packs, so the new car's tile may
be blank in them.

## Wheels

A car's stock wheel is `tires\art\<File>\` with `<File>` from its
tooldata.xml (`<WheelStyle><P0 File="CivicSI"/>`; upgrade wheels are listed
in mega.cab's `cars\wheelstyle.xml`): `tire.carbin` in mega.cab, and
`wheel.xpr` (64x64 DXT5) and `wheel_vol.xpr` (64x64x4) in megaxpr.cab. The
game fits the model to the tyre size in the physics (scaling it changes
nothing). tire.carbin is one part, `wheel_LOD1`, axle along x, outer face
at its lowest x: material 8 the tyre, 11 the spokes and rim face (textured
from the top-left quarter of wheel.xpr), 12 the barrel, 13 a disc behind the
spokes (drawn only spinning). A copy of the files in the car's own cab is
not read. `nfsu2forza.py --wheel` puts the NFSU car's stock rim on material
11 (wheel.xpr then 128x128, the NFSU texture in that quarter); the cabs go
in the mods folder with `forzacab.py replace`.


## The .cab container

Not a Microsoft CAB. Little-endian throughout:

| Offset | Field |
|---|---|
| 0x00 | magic `0xC0C0AAAA` |
| 0x04 | version, 15 |
| 0x08 | entry count |
| 0x0C | 1 |
| 0x10 | file size |
| 0x14 | total unpacked size (a little over the entries' sum) |
| 0x18 | two equal u32s, meaning unknown |
| 0x30 | u16 1 |
| 0x32 | the root path, NUL-terminated: empty in car cabs, `engines\eng_c5r427\` in a shared engine cab |
| 0x132 | entries, 24 bytes each, sorted by hash |

The game reads the first 0x12E bytes as the header (0x103890 for version
14, 0x103910 for 15). An entry is: u32 data offset (from the start of the
file), u32 packed size, u32 unpacked size, u32 name offset, u32 0, u32
name hash. The names follow the table, NUL-terminated, with backslashes
(`cars\nissan240sx\car.carbin`); name offsets count from the first name.
Each entry's data is a zlib stream, or stored as is when the packed size
equals the unpacked size.

The hash is Bob Jenkins' lookup2 with initial value 0, over the root path
and name, lower-cased (the lookup at 0x103630 copies the name, lower-cases
it through `std::transform`, and hashes it at 0x103290). It matches all
48,049 entries in the disc's 239 cabs and the three cache cabs;
`forzacab.name_hash` computes it.

The other header fields: 0x0C is 1 when any entry is compressed (0 in
`mini.cab`, all stored); 0x14 is the data start plus every unpacked size;
0x18 and 0x1C are both the length of the names. Names are sorted, the data
follows in the same order with no gaps, and zlib level 9 reproduces the
disc's streams: `forzacab.py pack` rebuilds `car_nissan240sx.cab` and
`engine_eng_c5r427.cab` byte for byte.

Tested in the game (25 Oct): the Civic SI's three liveries recoloured to
green (40, 230, 40), packed, and put in the mods folder as
`media\cabs\car_CivicSI.cab`; the car select, the player's car and an AI
Civic all showed green.

## car_nissan240sx.cab (122 entries)

- `cars\nissan240sx\car.carbin`, 1.2 MB: the model.
- `cars\nissan240sx\liveries\standard\livery0-6.livery`: small XML, the paint
  colour (`<override red= green= blue= texture="livery0"/>`), a shader
  settings file and average colours.
- `livery0.xpr`, `livery0hi.xpr`, `livery0nc.xpr`: texture packs (XPR, the
  Xbox's resource format) for the paint; `hi` and `nc` variants.
- `engines\nissan240sx\audio\...`: 111 files, `.ini` settings and `.xwb`
  wave banks, in two detail levels (`lod1`, `lod2`).

## car.carbin

A chunk is u32 size (its whole length), u32 version, a NUL-terminated name,
then its contents. The file is one chunk, `Car` (version 3):

- `Attribs` (version 1, 0x48 bytes): u32 1, u32 5, then floats in mirrored
  left/right pairs (positions; not decoded further).
- `Driver` (version 1): 15 floats, positions for the shared driver's IK
  targets (seat, hands on the wheel, feet). The driver itself is one skinned
  model for every car, `drivers\driver.bin` in `Mega.ca2` with its skeleton
  in `temp\driver.xml` (butt, chest, shoulders, hands, feet, head); the
  car's own limb parts (`Head`, `Chest`, `Left_Thigh` ...) are 32-vertex
  boxes with no pivots. A converted car can keep its donor's `Driver` chunk
  and limb parts.
- u32 part count (84 on the 240SX), then that many `Part` chunks (version 3).
- `Flare` records after the parts (light flares; not decoded).

A part: u32 (unknown), a length-prefixed name, two u32s, then:

- `Verts\0`, u32 count, then 20 bytes a vertex: int16 x, y, z (metres x 4096;
  z runs along the car), int16 normal x, y, z (unit length / 32768), 4 bytes
  (two equal bytes and two zeros: likely shading or ambient occlusion), u16
  u, v.
- Three chunks (version 0), in this order:
  - `Damage`: u32 count, 0 or the part's vertex count, then 12 bytes a
    vertex: int16 position and int16 unit normal of the crushed shape, which
    the game blends towards in a crash. Body panels, bumpers, skirts, lights
    and the hood have one; glass, the interior, mirrors and brakes do not.
  - `Pivots`: u32 count (0 or 1), then a hinge for parts that swing or hang
    loose when damaged (hood, mirrors, wings, exhaust, some bumpers): float3
    hinge point in the car's space (the rear bumper's at z = -1.94), float3 x
    3 axes, two small angle limits (0.02, 0.04), two spring constants (200 on
    bumpers, 120 on wings, 130 on mirrors and the hood) and two dampings (2).
  - `Attributes`: three floats, (1, 0, 0) on fixed parts and (1, 0.2, x) on
    hinged ones; x (3 on the rear bumper, 0.1 on mirrors and race wings, 0.8
    on the exhaust) is likely how easily it breaks off.
- u32 subpart count, then `Subpart` chunks (version 2): u32 subpart id, u32
  material (1-35 on the 240SX), u32 primitive (always 6: the Xbox's
  triangle strip), u32 index count, 16 bytes (unknown; sometimes a float),
  then u16 indices into the part's vertices.

Exported this way, the 240SX's 84 parts give 72,735 triangles, and the body
renders correctly from the side, top and front.

Part names show how a car is built: the body (`body_LOD1`), hood, trunk,
glass, lights, mirrors, interior, brake rotors and calipers, a cage, the
driver's 17 limbs, and the upgrade body kits as alternatives: front and rear
bumpers `a`-`h` plus `race`, skirts `b`-`h` each side, wings `a`-`g` and three
race wings. An NFS Underground car is also a kit of parts, which helps a
converter.

## Materials

A subpart's material number indexes this list, from the executable's
strings (file offset 0x481500), which matches what the 240SX's parts use
(body panels 1, glass 2, tail lights 3, headlights 4, interior 14, race
wings 19, front grilles 35):

0 None, 1 Body, 2 Window, 3 TailLights, 4 HeadLights, 5 ReverseLights,
6 BlackGlass, 7 Chrome, 8 Tire, 9 Black, 10 Tire2, 11 Rim, 12 InnerRim,
13 BlurredRim, 14 Interior, 15 Frame, 16 RedGlass, 17 RimChrome, 18 Matte,
19 CarbonFiber, 20 Plastic, 21 Plastic2, 22 RubberTrim, 23 InnerRimChrome,
24 BlurredRimChrome, 25 NamePlate, 26 Badge, 27 Number, 28 Misc, 29 Misc2,
30 HeadlightGlass, 31 WhiteTailLights, 32 TailLightsOn, 33 Reflectors,
34 Grille1, 35 Grille2

Each has day and night shader settings (specular, metal, fresnel, top and
bottom colours) in `cars\globalmaterialsettings.xml` in `Mega.ca2` (cache
`mega.cab`); paint finishes are `cars\shadersettings\*.xml` there.

## Textures

A car's paint and details are one atlas per livery, in XPR0 packs (the
Xbox's resource format: `XPR0`, total size, header size, 20-byte D3D
resource headers ending in 0xFFFFFFFF, data from the header size). On the
240SX:

| File | Texture |
|---|---|
| `livery0.xpr` | 512x512 volume, 2 slices, DXT5 |
| `livery0nc.xpr` | the same, uncompressed A8R8G8B8 (swizzled) |
| `livery0hi.xpr` | 1024x1024, DXT5, 11 mip levels |

Slice 0 is the clean car: lights, badges, grille, dashboard, with white
where the paint colour shows through. Slice 1 is the same atlas damaged
(scratches, cracked lights); the game blends towards it with damage. DXT
volumes keep each 4x4 block's slices together. Vertex u, v are u16 / 65536
into the atlas; rendering the 240SX this way puts the headlights, grille
and exhaust where they belong, with the livery's colour on material 1.
Shared textures (`grille1.xpr`, `grille2.xpr`, wheels in `tires\art\`,
drop shadows) are in `MegaXPR.ca2` (cache `megaxpr.cab`).

## Physics (Cars.ca2 / cars.cab), per car

XML, at four upgrade levels (`l0`-`l3`) where parts can be upgraded:

- `cars\<name>\physics\`: `weight` (mass, centre of mass, block size),
  `aero\body`, `aero\front`, `aero\rear`, `brakes`, `clutch`,
  `drivetraindiff`, `suspension`, `tiremod`, `transmission`, plus
  `maxdata.xml`, `nontooldata.xml`, `nonupgradedata.xml`.
- `engines\<name>\physics\`: `base.xml` (mass, inertia, fuel), and
  `enginetuning`, `fuelignition`, `intakeexhaust`, `intercooler`,
  `supercharger`, `turbo`.
- `cars\<name>\config.ini` (driver shifting, tyre scale, shadow size),
  `liveries\liveries.xml`, `audio\<name>.ini`, `tooldata.xml`.

## Still to find

- Which materials take a shared texture or only shader colours (the tail
  lights rendered pale from the atlas alone).
- The 16 bytes in each subpart, the u32 at the start of each part (it looks
  like an id: `33a72b01` to `33b92b01` across the wings), `Attribs` and
  `Flare`.
- How the game builds its car list (the list of names, prices, classes and
  icons), for adding cars rather than replacing them.

## Need for Speed Underground cars (the converter's source)

`tools/nfsu.py` reads a PC NFSU car folder (`CARS\<car>\`): `list` for the
parts of `GEOMETRY.BIN`, `textures` for `TEXTURES.BIN`. Both are EA's chunk
format (u32 id, u32 size; bit 31 marks a container; data that needs
alignment starts with 0x11 padding, the index lists included).

- Geometry: 400 parts on the 240SX, each with a name, texture and shader
  hash lists and one mesh: 36-byte vertices (float3 position with x
  forward, y left, z up in metres; float3 normal; RGBA colour; float2 uv),
  u16 triangle lists, and groups (bounds, index count and first index,
  texture index at 0x1C, shader index at 0x20).
- Names: `240SX_KIT00_*` is the stock car (body, roof, hood, trunk, both
  bumpers, skirts, spoiler, head and brake lights, exhaust, engine, one
  wheel drawn four times), `KIT01`-`KIT15` body kits, `STYLE01`-`STYLE20`
  hoods, spoilers and roofs; `_A` to `_D` are detail levels. The stock car
  at `_A` is about 3,900 triangles (Forza's 240SX body alone is 22,000).
- Textures: a texture pack; each texture is JDLZ-compressed on its own
  (EA's LZ, implemented in `nfsu.jdlz`), DXT1/DXT3 or 32-bit BGRA, not
  swizzled; 117 of the 240SX's 119 unpack to exactly their stated size.
  Names hash with EA's usual function (h = h * 33 + c from 0xFFFFFFFF).
  `240SX_SKIN1`, which the body panels use, is in no file: the game builds
  it from the paint and vinyls, so those parts become Forza's Body material
  and take the livery colour.

Rendered from these readers, the stock 240SX comes out whole, with its
headlights, badge and third brake light textured in place.

For the converter: NFSU's kit-of-parts maps onto Forza's (KIT bumpers and
skirts to Forza's `a`-`h` variants, STYLE hoods and spoilers to its hoods and
wings); positions need x/y/z swapped to Forza's axes (z along the car) and
scaling to int16 x 4096; normals to int16; triangle lists to strips (or
strips of three); textures packed into one Forza atlas with the uvs moved
into their places; and handling, sounds, damage shapes and the driver
borrowed from a similar Forza car (its own 240SX for this one).

## Need for Speed Most Wanted cars (26 Oct)

`CARS/<car>/GEOMETRY.BIN` has Underground's chunks and vertices (36 bytes,
metres, x forward, y left, z up); `tools/nfsu.py` reads both and hands MW
parts over in Underground's shape. The differences:

- The part header's name is at 0xA0 (Underground 0x94).
- Material groups (00134b02) are 104 bytes: float3 min and max, the
  texture index in the bytes at 0x18, u32 vertices at 0x3C, triangles at
  0x40, first index at 0x44. Each has a name, one 00134c02 chunk a group
  in order (BODY, BODY_CHROME, WINDOW_FRONT, WINDOW_FRONT_MASK,
  LEFT_HEADLIGHT_KIT00_BULB ...); the converter maps those (mw_material).
- Parts: `<CAR>_KIT00_BODY` holds the bumpers and skirts; the roof (with
  a copy of each window) is `<CAR>_BASE_A`-`D`; the windows (FRONT_WINDOW,
  FRONT_LEFT_WINDOW ...), lamps and their glass, mirrors, hood and spoiler
  are parts of their own; `_E` is a far body, DAMAGE0_* the crushed
  panels. KIT01-04 are body kits. Brakes and tyres sit at the origin
  (placed at run time), so the axles come from the body's wheel openings.
- Textures are named by role (HEADLIGHT_LEFT, BRAKELIGHT_RIGHT,
  WINDOW_FRONT, DOORLINE, LICENSEPLATE, `<CAR>_SKIN1` the paint) and
  resolved to the car's own at run time (`<CAR>_KIT00_HEADLIGHT`, its
  `_ON` twin for lit lamps).
- TEXTURES.BIN: no header chunks; 33310003 entries of 24 bytes (u32 hash,
  file offset, packed size, unpacked size, flags, 0), each texture JDLZ
  (or HUFF, not decoded: the lit lamps) unpacking to the top level's
  pixels and then a 0x9C header (name at 0x0C, width and height at 0x44,
  FourCC at 0x90).

The Chevrolet Cobalt SS (not in Forza) converted on the Civic SI (26 Oct),
added as its own car with addcar.py (`--cab`, `--make CamaroZ28`, ordinal
81, "Cobalt SS"), the Civic's physics and engine: body, roof, glass,
lamps, mirrors, hood and spoiler, badges and lamps from its textures,
the 240SX conversion byte for byte as before. Seen in the shop (26 Oct): right but for the lamps.

- **The livery atlas's alpha is not opacity:** the template's lamp texels
  have alpha 0 (taillights 25 on average), and so does nearly all its
  paint. Most Wanted's opaque lamp textures drew as white lamps; the
  converter now gives them alpha 0. Badges keep theirs (the decal material
  uses it).
- **The shop's parts are tooldata.xml's lists** (FrontBumper, RearBumper,
  SideSkirt, Hood, Wing ...): each choice names the parts it draws, and a
  choice may name several or none. MW body kits are whole bodies (they
  differ from the stock one up the fenders and out to 1.0 m a side), so
  for a Most Wanted car the body part is only the roof (BASE), each front
  bumper a whole kit's body (stock in bumperFa, KIT01-05 in b-f; the
  extras with two near levels and the stock far ones), and the rear
  bumper and skirt lists keep only their stock choice, with no parts.
  Hoods f and g take two of the car's STYLE hoods, wings c, d, g and raceA
  four of CARS/SPOILER's shared spoilers (stood where the car's own spoiler
  is, as wide), wingb the car's own spoiler as the stock choice, and a last
  choice has no wing. nfsu2forza.py writes those lists (upgrades.xml),
  addcar.py --upgrades puts them in. Part ids (u32 before the name) are
  not a hash we know, so no parts are added: only the template's slots.
- **Its engine:** addcar.py --engine-like MiniCooper (the supercharged R53),
  as CobaltSSLSJ with its sound, x1.258 to 205 hp and the torque up to 200
  lb-ft below the power peak; 1,284 kg; the Dodge SRT-4's menu figures and
  ratings; 21,000 credits. gamecars.dat's u32 at 12 is the power, tenths
  of a kilowatt (Civic SI 1193, Mini 1215, SRT-4 1715).

## The converter (tools/nfsu2forza.py), first version (25 Oct)

`python tools/nfsu2forza.py <template car.carbin> <NFSU car folder> <out car.carbin> [--keep-glass]`
puts an NFSU car's stock body on a Forza car; `tools/carbin.py` reads and
writes car.carbin (it rebuilds the disc's files byte for byte). Tested in
races on the Civic SI and built on Forza's 240SX for driving. What the game
needs, learned the hard way:

- A subpart's id is its detail level (1 nearest, 2-4 further, 5 on the
  body): numbered 0, 1, 2 ..., most of the car was never drawn up close.
- Forza strips wind opposite to NFSU's triangles once the axes are swapped
  (Forza = 1.70 x (-y, z, x) for the 240SX); the two cancel, so triangles
  keep NFSU's order. Reversed, every panel was inside out.
- Texture coordinates matter even for paint: one fixed "white" spot drew
  the body black. Each new vertex copies the uv and shading bytes of the
  nearest template vertex of the same material.
- The paint is the stage-3 combiner constant times the texel (where its
  alpha is 0) times the lighting, so a dark paint texel turns every colour
  black. The body material reads texture coordinates as if 32768 spans the
  atlas (the Civic's paint coordinates are all under 32768 and land on
  white read so); the Cobalt's paint texel was white read as 65536 a span
  but black (packed headlight glass) read as 32768. The converter now picks
  one that is white either way and keeps both spots clear of the atlas.
- One subpart per detail level and material (as Forza's own).
- Parts that had a damage shape keep one (the undamaged shape for now).
- NFSU shaders without a known name: 12c9453c is the rubber round the
  windows, the B pillar and the trim strips, 010cb64a the inside of the
  wheel arches; 52bf4c34 (texture bd1f0e0a) is the floor pan. The first
  two are drawn black now (paint on a black texel of the atlas).
- The NFSU car has no window glass: its windows are holes in the body.
  The converter welds the stock parts, finds the large closed holes high
  on the car (windshield, rear glass, door and quarter windows: six on the
  240SX) and fills each with a fan, from both sides, in the template's
  nearest glass part with that part's texture coordinates. Glass samples
  its own texture, not the livery: in the Civic's body part, with paint
  coordinates, Window drew fully clear. `--keep-glass` keeps the
  template's glass instead.
- The NFSU car's own textures (lights, badges) go into the livery atlas
  (`pack_atlas`): Civic's atlas is badges on clear texels (clear shows the
  paint), so there is room. livery0hi.xpr (1024, DXT5, 11 mips) is what the
  car-select screen draws; livery0.xpr (512, DXT5, two slices: clean and
  damaged, each block's slices together) and livery0nc.xpr (the same,
  swizzled BGRA) are the race's. Free room is judged on the clean slice
  and the hi atlas only: the damaged slice is scratches laid out for the
  Civic's own body. Only the 4x4 blocks touched are encoded again
  (`forzaxpr.encode_dxt5`); the paint and black texels are kept clear of.
- The body and hatch get a black inside (copies facing in, set in about a
  centimetre): drawn from outside only, the far side of the S13's empty
  hatch area was missing through the quarter windows and the studio showed
  through. On the panels themselves the copies speckled the paint black
  (they fought the outside in the shadow map).
- 19 triangles of the 240SX's roof are wound against their normals (NFSU
  draws both sides); they are turned to face their normals.
- The template's cabin (interior, cage, bands, steering wheel) is fitted
  into the new shell (body, hood, trunk and the glass) by height and by
  width; triangles still outside are then dropped: those with nothing of
  the shell over them within 6 cm (the shell's triangles rasterised over
  the ground plan) and those down in a wheel arch (under the NFSU car's
  arch liners, 010cb64a). Pulling stray corners in instead stretched
  triangles across the glass. The Civic's cabin is wider and longer than
  the S13's greenhouse: its headliner and cage stood out of the rear
  glass, and its rear wheel tubs out of the S13's arches.
- Window panes follow the glass's curve: heights over each pane's plane
  are fitted to its rim as a quadric, and two rings of points inside take
  them (a flat fan sagged under the S13's curved hatch glass and the cage
  showed through).
- Every template wing becomes the NFSU car's own spoiler; the Civic's
  floated behind the hatch. Its badges are hidden.
- The dark vertical bands on the rear panel are the software renderer's
  shadows; with XBRT_GPU=gl they are not there.
- The template's panel seams (30 `Line` chunks after the parts: polylines
  of points and normals on its body, which the game draws as thin blended
  line strips) followed the Civic's hood, doors and trunk lid and floated
  off the new body as grey lines and bands; they are dropped. Its two
  `Flare` chunks stay. Also dropped: the template's `bands` (strips under
  its rear glass), its exhausts (the tailpipe hung out under the S13's
  bumper; NFSU's EXHAUST part sits at the origin, placed by the game) and
  the light-material bits of its interior (a third brake light).
- NFSU shader `MIRROR` (the mirrors' glass) becomes Chrome, as the Civic's
  mirror glass; 52bf4c34 (the floor pan) black trim (as Black it drew
  clear, and the cabin floor was see-through). Lamp triangles on black
  texels (the S13's centre garnish) are black trim: the lamp material lit
  them pale.
- The wheels stay where the template's physics puts them (its brake
  rotors mark the hubs), so the body is stretched along its length between
  the middles of its wheel-arch liners to put each arch over its hub
  (x1.758 between them on the Civic, 1.658 elsewhere). Scaled evenly, the
  S13's shorter wheelbase left the rear wheels 0.18 behind their arches.
- Badges: decals placed by a ray from outside onto the body, as a grid of
  points each dropped onto the panel and set 4 mm off it (flat and set off
  3 cm, they stood off the tail's curve), in the
  bumpers at their end of the car (every variant). Material 26 (Badge)
  reads its texture coordinates doubled, u16 / 32768 into the atlas: at
  / 65536 the decals drew a quarter of the atlas squeezed into them, and
  NFSU's own nose emblem the marker lamps beside it. Material 25 (the
  Civic's badges) drew nothing of them. In the body part the same decals
  drew nothing usable either. `--badges <folder>` takes logo.* and model.*
  (any image ffmpeg reads) for the emblem and the lettering; they are the
  user's own files (trademarks), kept out of the repository. Without it
  the NFSU badge sheet's small ones stand in.
- Still to do: real damage shapes, the NFSU wheel's tyre (the template's
  is kept), and body kits as Forza's bumper and skirt
  variants.

### The missing roof (solved, 25 Oct)

The template's interior covered it. The Civic's headliner (in
`interior_LOD1`, black) and its roll-cage bands reach y 1.90 and 1.80; the
fitted S13's roof tops out at 1.76, so they stood out of it and drew over
it from above. From the car-select camera, which is a little above the roof, that
read as a black or missing roof. The converter now squashes the
template's cabin parts (interior, bands, cage, steering wheel) under the
new roof: each vertex keeps its share of the height between the floor
and the roof over it (`fit_cabin` in tools/nfsu2forza.py).

How it was found, for next time: an `XBRT_GPU_DUMP` of a car-select frame
shows the car drawn three times: into a 768x768 shadow map (colour
masked, draws 9-60), the car itself, then the floor's mirror image
(culling flipped). Stage 1 is that shadow map (PROJECT3D on a depth
texture), stage 3 a cube reflection, and stage 2's coordinates come from
an all-zero matrix (constants 100-103). Running the car's vertex program
(`XBRT_GL_VSH_DUMP`) over the test squares gave the same outputs over the
cabin as over the hood; `XBRT_GL_NO_SHADOW` changed nothing;
`XBRT_MARK=25` showed the squares drawn (as a sliver: the camera is
at about their height). Hiding the interior and the bands brought the roof
back.

The notes below, from before the trace, were wrong on one point:
hiding the interior does change it (that test must not have taken).

### Notes from before the trace

On the Civic template the converted car draws everywhere except where a
surface faces up over the cabin: the S13's roof panel, its sunroof and its
hatch glass are missing, while its pillars and windshield header draw.
Tests in scripted races, each one change from the working build:

- Not the data: the triangles are in the level-1 strip, wound and lit like
  the rest; drawn from both sides they are still missing.
- Not the part, material, texel or shading bytes: moved into `bands` or
  `nocage`, as paint or black, they are still missing.
- Not the height: lowered 0.5 they draw (at dashboard height, inside the
  cabin outline from above?); raised 0.3, the frame floats visibly but the
  panel does not. Synthetic flat squares draw beside the car at any height
  and over the hood at roof height, but not over the cabin, even at 2.6.
- Not covered by something: nothing of the template reaches 2.6, and
  hiding its interior, cage and window surrounds changes nothing. Keeping
  its sunroof glass changes nothing.
- No texture the game decodes on the car-select screen looks like a mask.
  The squares beside the car also came out black with the paint texel,
  so the body shader takes something from the position.

Next: trace the car's draw calls (XBRT_GPU_DUMP) for the body and compare
the state for the roof's triangles with the hood's: texture stages,
texkill or alpha test, and any texture coordinates computed from position.
