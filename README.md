# ForzaMotorsportPC

A PC port of 2005 Forza Motorsport.

A from-scratch effort to bring the original Xbox **Forza Motorsport** (2005,
title ID `4D53006E`) to PC as a native program. The plan is a static
recompilation of the game's own code plus a PC runtime for the Xbox kernel,
graphics, audio and input. See [docs/ROADMAP.md](docs/ROADMAP.md).

**Status: playable on Windows.** The recompiled game builds as a native
Windows program. With the player's extracted disc it runs the
menus, career, arcade races and the garage with sound, drawn on the GPU
through OpenGL, all through the game's own D3D and DSOUND down to models
of the Xbox's GPU and APU. Custom cars, series, events and a track can be
added through a mods folder (see [Mods](#mods)). What exists:

- `xbe` parses an XBE: header, certificate, sections (with SHA-1 checks),
  linked XDK libraries, TLS and the kernel import table. It names all 371
  `xboxkrnl.exe` exports, including their calling conventions.
- `analysis` finds the game's code by recursive descent from the entry
  point, plus prologue and vtable scans. Candidates are checked by a
  plausibility walk. On Forza that comes to about 26,000 functions and
  96% of `.text`.
- `sigdb` names library code. XDK libraries (D3D8, DSOUND, XAPI, XACT,
  XOnline...) are matched with signatures from Cxbx-Reloaded's
  [XbSymbolDatabase](https://github.com/Cxbx-Reloaded/XbSymbolDatabase),
  including ports of its hand-written scans. C runtime helpers are matched
  with our own patterns. On Forza that's 530 symbols. All 507 the original
  C implementation reports for this XBE come out at the same addresses.
- `recomp` translates the game's x86 to C: integer, SSE1, x87 and MMX,
  with x87 kept bit-exact by running it on the host's own x87 unit. **99.2%
  of Forza's functions translate fully.** Correctness is checked by
  differential testing against the Unicorn CPU emulator: 473 edge-case
  instruction forms pass with 0 mismatches, and so do 5,021 of Forza's own
  functions, call chains included (6,241 cases). See [docs/RECOMPILER.md](docs/RECOMPILER.md).
- `runtime` is the C runtime the generated code links against: the Xbox
  kernel's exports (HLE), threads, memory, files and controllers. See
  [runtime/README.md](runtime/README.md).
- Five tools: `xbeinfo`, `xbemap`, `xbedis`, `xbesyms` and `xbrecomp`.

## You need your own copy

This repo never contains game code or data, and it never will. Dump
`default.xbe` (and later the rest of the disc) from your own copy, then
point the tools at it. `.gitignore` keeps `*.xbe`, `*.iso` and dumps out of
commits.

## Build and play (Windows)

You need:

- your own extracted disc (extract-xiso makes a folder with `default.xbe`
  and `media`);
- Go 1.24 or later;
- [w64devkit](https://github.com/skeeto/w64devkit) (gcc; MSVC cannot build
  the generated code, which keeps x87 math in 80-bit `long double`);
- a checkout of [XbSymbolDatabase](https://github.com/Cxbx-Reloaded/XbSymbolDatabase)
  (library names; read at run time, see [Library names](#library-names));
- Windows 10 1803 or later, and a GPU with OpenGL 4.3.

In Git Bash, from the repository:

```sh
export PATH="/c/Program Files/Go/bin:/path/to/w64devkit/bin:$PATH"
X="/path/to/extracted disc/default.xbe"
go run ./cmd/xbrecomp -xbsdb /path/to/XbSymbolDatabase -entries tools/entries.txt -o out/ "$X"
make -C runtime GEN=../out -j8          # runtime/forza.exe
```

`xbrecomp` writes the game's code as C into `out/`. Keep
`-entries tools/entries.txt`: it lists functions the game only reaches
through pointers, and without them the game stops when it gets there.

The first build takes a while (about 50 large generated files). After a
change to the runtime alone, only `make` runs again. `rm -f out/*.c` before
`xbrecomp` if the recompiler changed, since it does not delete files it no
longer writes.

To play, make an empty `run` folder next to `runtime` and start the game
from it: it holds the hard disk (saves and the cache) and the settings. A
launcher, `Play Forza.bat` next to `runtime`:

```bat
@echo off
cd /d "%~dp0run"
set XBRT_GPU=gl
set XBRT_HDD=hdd
"%~dp0runtime\forza.exe" "C:\path\to\extracted disc\default.xbe"
if errorlevel 1 pause
```

The first start makes `run\forza.ini` and `run\hdd`. Frame rate,
resolution, widescreen, volume and the rest are in `forza.ini`, or press F1
in the game. The game's saves live in `run\hdd`: back that folder up, and
never edit the save files (they are signed; the game deletes profiles that
fail the check). A pad is read through XInput; without one, the keyboard
(see [runtime/README.md](runtime/README.md)). Every setting and debugging
switch is listed there.

## Mods

`XBRT_MODS=<folder>` (relative to `run`) lays a mods folder over the disc:

| in the mods folder | what it does |
|---|---|
| `media\...` | replaces the disc's file at that path. Changed installer archives (`media\cabs\Cars.ca2`, `Mega.ca2`, `MegaXPR.ca2`) are re-signed at boot, so the game accepts them; they may also be bigger than the disc's (this port only) |
| `hdd\Partition<n>\...` | stands in for a cache file (never `cars.cab`, `mega.cab` or `megaxpr.cab`, which the installer writes itself) |
| `track\<track>\...` | files used only while that track loads: a new layout on another track's scenery |
| `timetrial.txt` | target times for the career's Time Trial category (`XBRT_CAREER_TIMETRIAL=1`) |

The tools that build mods from your disc are in `tools/` (Python 3):
`addcar.py` (a car from another car or another game), `addseries.py`,
`amateurseries.py` and `careertimetrial.py` (career series and events),
`shipyardcircuit.py` (the Pacific Shipyards Circuit), and `moddisc.py`
(a copy of the disc with a mods folder's files in it, for ports and
emulators without a mods folder). How the game's data works, and the
limits on what can be added: [docs/research/cars.md](docs/research/cars.md)
and [docs/research/events-tracks.md](docs/research/events-tracks.md).

## Tools

Requires Go 1.24+.

```sh
go run ./cmd/xbeinfo default.xbe            # header, sections, libraries
go run ./cmd/xbeinfo -kernel default.xbe    # plus all 159 kernel imports
go run ./cmd/xbemap -o forza.map default.xbe
go run ./cmd/xbedis default.xbe 0x268EB5    # disassemble one function
go run ./cmd/xbesyms default.xbe            # list named library symbols
go run ./cmd/xbrecomp -o out/ default.xbe   # translate everything to C
```

`xbemap` prints per-section coverage and writes a map with one line per
function: address, size, section, how it was found, name, and the kernel
calls it makes.

### Library names

C runtime helpers are always named. For XDK library names, `xbemap`,
`xbedis` and `xbesyms` take `-xbsdb DIR`, which points at a checkout of
XbSymbolDatabase:

```sh
git clone https://github.com/Cxbx-Reloaded/XbSymbolDatabase ~/XbSymbolDatabase
go run ./cmd/xbemap -xbsdb ~/XbSymbolDatabase -o forza.map default.xbe
go run ./cmd/xbedis -xbsdb ~/XbSymbolDatabase default.xbe D3DDevice_Clear
```

The database's code is MIT, but its signature data is ODbL-1.0, a
share-alike license. That's why it's read from your checkout at run time
and never copied into this repo.

## Tests

```sh
go test ./...                                   # synthetic data, no game needed
FORZA_XBE=/path/to/default.xbe go test ./...    # also check the real game
FORZA_XBE=... XBSDB=~/XbSymbolDatabase go test ./...   # and the signatures
```

The recompiler's differential tests also need gcc, GNU binutils and Python
with `pip install unicorn`. They skip without them.

The real-game tests guard discovery quality, so a change that drops
coverage or brings back false function starts fails them.

## Notes

- [docs/research/xbe.md](docs/research/xbe.md): what is in Forza's XBE and what
  it tells us about the port.
- The kernel export list comes from nxdk's `xboxkrnl.exe.def` (CC0). To
  regenerate it, run `go generate ./xbe`.
