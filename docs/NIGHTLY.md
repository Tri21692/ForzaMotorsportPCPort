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

## Current lead (2026-10-18, evening)

The front end draws, text included: `runtime/raster.c` rasterises Kelvin
primitives in software (vertex programs interpreted, register
combiners, four texture stages, blending) into the 1280x480
anti-aliased back buffer, and D3D's downsample pass copies it to the
front buffers that PCRTC_START flips between. Screenshots show the
profile screens, dialog boxes and the on-screen keyboard, readable.

`XBRT_AUTOPRESS=1` taps START and A every two seconds, so an unattended
run ends up looping on "Cannot create profile" ('Default' is taken).
Next, drive further into the game: create a profile with a scripted
input sequence (an `XBRT_INPUT_SCRIPT` of timed buttons would do), then
see what the main menu, garage and a race need.

## Next after that

1. Speed: 3 fps in the menus. Profile where host time goes (gdb
   samples of the main thread, or a build with `-O2` for the generated
   code: `make OPT=-O2`) before changing anything.
2. Pace flips to the vertical blank (D3D's presentation interval).
3. Drawing: depth and stencil, swizzled render targets, lighting and
   texgen, filtering (everything is point sampled), 3D and cube maps. See the phase 4 list in
   [ROADMAP.md](ROADMAP.md).

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
- 2026-10-18 (interactive, evening): software rasteriser (raster.c):
  vertex program interpreter, viewport and matrices in the transform
  constants (c58/c59 were zero, so every program put vertices at 0),
  anti-aliasing scale, register combiners (the downsample pass was black
  because texture times diffuse is not what its combiners say). Menus
  draw, without text.
- 2026-10-18 (interactive, night): text. Forza's text is rendered from a
  glyph cache (a 512x512 palettised texture with four glyph layers in
  its R, G, B and A channels; glyphs come from `Z:\fontcache`, which
  the game unpacks from `euro.SXWad` with zlib, read on demand through
  ReadFileEx). Each glyph quad picks its layer with a dot product
  against texture stage 1 in pass-through mode, whose "texture" is the
  texture coordinate itself. The rasteriser only had stage 0; with all
  four stages and the pass-through mode, menus have their text. New
  debugging aids: `XBRT_TEX_DUMP`, `XBRT_RAM_DUMP=<file>:<seconds>`,
  user APCs and pixel-state combinations logged at level 2.
- 2026-10-18 (interactive, evening): CPU detection (pushfd/popfd keep
  AC/ID, cpuid answers as the Xbox's Pentium III), so Bink finds MMX;
  CVTPS2PI/CVTTPS2PI/CVTPI2PS; the video overlay's STOP register; the
  directory listing (NtQueryDirectoryFile); fibers (SwitchToFiber on
  host threads, MmCreate/DeleteKernelStack); SHA-1, HMAC and RC4 for save
  signing. The game now runs its front end; no boot blocker left.
- 2026-10-18 (interactive, night): a window and screenshots (front
  buffer plus the video overlay); colour clears. First pictures: the
  loading spinner, the attract movie and the intro movie with the Forza
  Motorsport logo.
