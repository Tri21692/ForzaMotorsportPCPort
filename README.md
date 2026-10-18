# ForzaMotorsportPC

A PC port of 2005 Forza Motorsport.

A from-scratch effort to bring the original Xbox **Forza Motorsport** (2005,
title ID `4D53006E`) to PC as a native program. The plan is a static
recompilation of the game's own code plus a PC runtime for the Xbox kernel,
graphics, audio and input. See [docs/ROADMAP.md](docs/ROADMAP.md).

**Status: phase 1, naming the library code.** Nothing runs yet. What exists today:

- `xbe` parses an XBE: header, certificate, sections (with SHA-1 checks),
  linked XDK libraries, TLS and the kernel import table. It names all 371
  `xboxkrnl.exe` exports, including their calling conventions.
- `analysis` finds the game's code by recursive descent from the entry
  point, plus prologue and vtable scans. On Forza that comes to about
  17,000 functions and 88% of `.text`.
- `sigdb` names XDK library code (D3D8, DSOUND, XAPI, XACT, XOnline...) by
  matching byte signatures from Cxbx-Reloaded's
  [XbSymbolDatabase](https://github.com/Cxbx-Reloaded/XbSymbolDatabase). On
  Forza it names 412 symbols in about 0.1 s, `mainCRTStartup` among them, at
  exactly the XBE's entry point.
- Three tools: `xbeinfo`, `xbemap` and `xbedis`.

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
```

`xbemap` prints per-section coverage and writes a map with one line per
function: address, size, section, how it was found, name, and the kernel
calls it makes.

### Library names

`xbemap` and `xbedis` take `-xbsdb DIR`, which points at a checkout of
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

The real-game tests guard discovery quality, so a change that drops
coverage or brings back false function starts fails them.

## Notes

- [docs/research/xbe.md](docs/research/xbe.md): what is in Forza's XBE and what
  it tells us about the port.
- The kernel export list comes from nxdk's `xboxkrnl.exe.def` (CC0). To
  regenerate it, run `go generate ./xbe`.
