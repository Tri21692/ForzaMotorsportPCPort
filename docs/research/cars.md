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

`Cars.ca2` is a whole cab compressed with zlib. The installer unpacks it to
the cache partition as `hdd/Partition4/cars.cab`, and the game reads that
copy, so a changed `Cars.ca2` in the mods folder will not reach the game
until the cache copy is rebuilt as well. `Mega.ca2` and `MegaXPR.ca2` (cache:
`mega.cab` on N: = Partition4, `megaxpr.cab` on Z: = Partition5) hold the
shared files, wheels among them. The game deletes and installs `mega.cab`
again from the disc at every boot. The mods folder covers the cache
partitions too (`mods/hdd/Partition4/mega.cab`), read only: opens that
write, deletes and renames get the real file, or the game's reinstall
deleted the mod.

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
