# ForzaMotorsportPC

A PC port of 2005 Forza Motorsport.

A from-scratch effort to bring the original Xbox **Forza Motorsport** (2005,
title ID `4D53006E`) to PC as a native program. The plan is a static
recompilation of the game's own code plus a PC runtime for the Xbox kernel,
graphics, audio and input. See [docs/ROADMAP.md](docs/ROADMAP.md).

**Status: phase 0, reading the executable.** Nothing runs yet. What exists today:

- `xbe` parses an XBE: header, certificate, sections (with SHA-1 checks),
  linked XDK libraries, TLS and the kernel import table. It names all 371
  `xboxkrnl.exe` exports, including their calling conventions.
- `analysis` finds the game's code by recursive descent from the entry
  point, plus prologue and vtable scans. On Forza that comes to about
  17,000 functions and 88% of `.text`.
- Two tools that use them, `xbeinfo` and `xbemap`.

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
```

`xbemap` prints per-section coverage and writes a map with one line per
function: address, size, section, how it was found, name, and the kernel
calls it makes.

## Tests

```sh
go test ./...                                   # synthetic XBEs, no game needed
FORZA_XBE=/path/to/default.xbe go test ./...    # also check the real game
```

The real-game tests guard discovery quality, so a change that drops
coverage or brings back false function starts fails them.

## Notes

- [docs/research/xbe.md](docs/research/xbe.md): what is in Forza's XBE and what
  it tells us about the port.
- The kernel export list comes from nxdk's `xboxkrnl.exe.def` (CC0). To
  regenerate it, run `go generate ./xbe`.
