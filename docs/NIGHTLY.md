# Nightly runs

Unattended work sessions run on the maintainer's Windows PC between 11 pm
and 8 am Eastern. Each one reads this file first and updates it before it
stops. It is the handoff between sessions: what works, the current lead,
and how to reproduce it.

## Setup on this machine

| what | where |
|---|---|
| Go 1.27 | `C:\Program Files\Go\bin` |
| gcc, make, gdb (w64devkit) | `C:\Users\maste\Downloads\w64devkit\bin` |
| XbSymbolDatabase | `C:\Users\maste\XbSymbolDatabase` |
| extracted disc (`default.xbe` + `media`) | `C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso` |
| working folder for runs (git-ignored) | `run/`, with the hard disk in `run/hdd` |

In Git Bash:

```sh
export PATH="/c/Program Files/Go/bin:/c/Users/maste/Downloads/w64devkit/bin:$PATH"
X="/c/Users/maste/Downloads/extract-xiso-win32-release/Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso/default.xbe"
rm -f out/*.c                                   # xbrecomp does not delete files it no longer writes
go run ./cmd/xbrecomp -xbsdb /c/Users/maste/XbSymbolDatabase -o out/ "$X"
make -C runtime GEN=../out -j20
cd run && XBRT_LOG=1 XBRT_HDD=hdd timeout 120 ../runtime/forza.exe "$X" > log.txt 2>&1
```

Tests: `FORZA_XBE="$X" XBSDB=/c/Users/maste/XbSymbolDatabase go test ./...`

## Debugging techniques that worked

- `XBRT_LOG=1` (kernel calls) and `2` (also file read/write contents,
  push buffer); the GPU logs a counts line every 300 vblanks.
- Sample where the game is: run it in the background, then
  `gdb -q -batch -p <pid> -ex "thread apply all bt 24"` a few times. Host
  frames named `f_XXXXXXXX` are guest functions at that address.
- Under gdb from the start, first `handle SIGSEGV nostop noprint pass`:
  the runtime commits guest memory on first touch through access
  violations. Break on runtime functions (`rt_open`, `k_file_*`), not on
  the generated weak symbols, which did not trigger.
- `XBRT_TRACE_OPEN=<substring>` prints a guest backtrace when a matching
  file is opened; `XBRT_DEBUG_BADHANDLE=1` does so when an invalid handle
  reaches ObReferenceObjectByHandle.
- `go run ./cmd/xbedis -xbsdb ... "$X" 0xADDR` disassembles one function;
  `go run ./cmd/xbemap -xbsdb ... -o forza.map "$X"` writes the map.
- The installer manifest is the `BKGDINST` section (37 files, 4 MB zlib
  chunks with SHA-1s).

## Current lead (2026-10-18)

The game reaches its main loop and polls the controller, then stops:

```
xbrt: indirect call to 003a98c0, which is not a translated function (return address 003a8c15)
```

`0x3A98C0` is a real method in `FZFULLUI` (`push esi; mov esi, ecx; mov
eax, [esi]; call [eax+8]; ...`), 16-byte aligned after `int3` padding,
reached only through a vtable the game builds at run time. Discovery
misses it: it has no `push ebp; mov ebp, esp` prologue and nothing
points at it statically.

Tried: seeding every 16-aligned address after `int3` padding in
`scanPrologues`, behind `plausible`. It found ~300 more functions but not
this one: `plausible(0x3A98C0)` returns false although a linear decode
of its first 80 instructions is clean, so it is the jump-target check
at the end of `plausible` (a branch landing inside a decoded
instruction). Find which branch, decide whether the check or the walk is
wrong, then land the padding scan with its own `Source` (after
`FromDataRef`, so `TestAnalyze`'s expectations hold) and check the
real-game tests still pass.

A wider fix to consider: when an indirect call hits an untranslated
address, log it to a file the next xbrecomp run reads as extra seeds.

## Next after that

1. Whatever the game hits next (keep fixing in boot order).
2. Pace flips to the vertical blank (they run ~500/s).
3. A window, and presenting the front buffer.
4. Drawing: see the phase 4 list in [ROADMAP.md](ROADMAP.md).

## Log

- 2026-10-18 (interactive): Windows port; boot through install, DSOUND,
  font cache and front end to the main loop. See the commit for detail.
