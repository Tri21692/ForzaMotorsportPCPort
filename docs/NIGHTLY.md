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
- Live guest registers from gdb: `frame function thread_main`, then
  `p/x *(XbCtx*)arg` (also `p/x *(unsigned*)(xb_mem + 0xADDR)` for guest
  memory and device registers).
- `XBRT_TRACE_OPEN=<substring>` prints a guest backtrace when a matching
  file is opened; `XBRT_DEBUG_BADHANDLE=1` does so when an invalid handle
  reaches ObReferenceObjectByHandle.
- `go run ./cmd/xbedis -xbsdb ... "$X" 0xADDR` disassembles one function;
  `go run ./cmd/xbemap -xbsdb ... -o forza.map "$X"` writes the map.
- The installer manifest is the `BKGDINST` section (37 files, 4 MB zlib
  chunks with SHA-1s).

## Current lead (2026-10-18, afternoon)

The game now gets through its main loop's start-up, polls the
controller, and opens the attract movie (`D:\MEDIA\FrontEnd\AttractVideo.bik`).
The Bink decode thread starts (created suspended, then resumed), then:

```
xbrt: indirect call to 00000000, which is not a translated function (return address 003b43c6)
```

At `0x3B43B8`/`0x3B43C0` (in `sub_003B4010`, section BINK) Bink calls
through function pointers at `0x5E6FC8` and `0x5E6FF0` (zero-initialised
data). Those are installed by `sub_003B3990`, `sub_003B3AF0` and
`sub_003B3B80` (which choose between `0x3B3670`/`0x3B3740`,
`0x3B3810`/`0x3B38D0` and `0x3B3A70`/`0x3B3AB0` from a bit-reader state
word at `[0x5E6FFC]`). They are not CPU-feature dispatch. `sub_003B3B80`
is called from `sub_003B4010` itself (at `0x3B40FE`) and from
`sub_003B4490`. Next: find out whether `sub_003B3B80` ran before the
failing call (break on `rt_kernel` calls nearby, or add a temporary
`XBRT_LOG` line to the translated function), and whether the path to
`0x3B43B8` skipped it legitimately (then something else should have set
the pointers: look for other writers, including through `[0x5E6FFC]`) or
because a branch went the wrong way (a translation bug: a differential
test of `sub_003B4010` against Unicorn would show it).

Startup is slow under the runtime: the audio banks (TireSkids,
RoadNoise, Collisions) take from ~17 s to ~97 s, and the movie opens at
~124 s. Allow `timeout 200` or more for runs.

## Next after that

1. Whatever the game hits next (keep fixing in boot order).
2. Pace flips to the vertical blank (they run ~500/s).
3. A window, and presenting the front buffer.
4. Drawing: see the phase 4 list in [ROADMAP.md](ROADMAP.md).

## Log

- 2026-10-18 (interactive): Windows port; boot through install, DSOUND,
  font cache and front end to the main loop. See the commit for detail.
- 2026-10-18 (interactive, afternoon): branches now pushed to GitHub as
  backups. Fixed: decoding of an instruction that ends in a section's
  zero-filled tail (FZFULLUI's last byte; found 0x3A98C0 and ~25 more);
  prologues after a function's final jmp count as starts (~740 more
  functions); AC'97 controller model (channel reset); GP DSP command
  mailbox acknowledged (effects not run); MmLockUnlock*; threads created
  suspended plus NtResumeThread/NtSuspendThread; MMIO range widened to
  everything from 0xFD000000. The game now reaches the attract movie.
