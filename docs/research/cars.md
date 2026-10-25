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
`mega.cab`, `megaxpr.cab`) are not looked at yet.

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
| 0x12E | entries, 24 bytes each, sorted by hash |

An entry is: u32 name hash, u32 data offset (from the start of the file),
u32 packed size, u32 unpacked size, u32 name offset, u32 0. After the table
come a u32 (unknown) and the names, NUL-terminated, with backslashes
(`cars\nissan240sx\car.carbin`); name offsets count from the first name.
Each entry's data is a zlib stream, or stored as is when the packed size
equals the unpacked size. The hash function is not identified yet; it is
needed to write new cabs.

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

- `Attribs` (version 1, 0x48 bytes): a count (1) of five-float... records
  (positions; not decoded).
- `Driver` (version 1): the driver's position (floats).
- u32 part count (84 on the 240SX), then that many `Part` chunks (version 3).
- `Flare` records after the parts (light flares; not decoded).

A part: u32 (unknown), a length-prefixed name, two u32s, then:

- `Verts\0`, u32 count, then 20 bytes a vertex: int16 x, y, z (metres x 4096;
  z runs along the car), int16 normal x, y, z (unit length / 32768), 4 bytes
  (two equal bytes and two zeros: likely shading or ambient occlusion), u16
  u, v.
- `Damage`, `Pivots`, `Attributes` blocks (not decoded; the driver's limbs
  are in their own space, so the pivots place them).
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

- Materials: what the material numbers mean and which texture each uses.
- The 16 bytes in each subpart, the `Damage`, `Pivots` and `Attributes`
  blocks, `Attribs`, `Driver` and `Flare`.
- The cab name hash.
- How the game builds its car list (the list of names, prices, classes and
  icons), for adding cars rather than replacing them.
