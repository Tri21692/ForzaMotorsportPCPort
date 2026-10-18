# ForzaMotorsportPC

A PC port of 2005 Forza Motorsport.

A from-scratch effort to bring the original Xbox **Forza Motorsport** (2005,
title ID `4D53006E`) to PC as a native program. The plan is a static
recompilation of the game's own code plus a PC runtime for the Xbox kernel,
graphics, audio and input. See [docs/ROADMAP.md](docs/ROADMAP.md).

**Status: phase 3, the runtime.** The recompiled game builds as a native
Linux program and boots through its own startup code until Direct3D
initialisation, which phase 4 replaces. Nothing is drawn yet. What exists
today:

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
  with x87 kept bit-exact by running it on the host's own x87 unit. **99.1%
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
