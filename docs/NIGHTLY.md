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

## Current lead (2026-10-18, late evening)

**The car drives.** `tools/input/race.txt` goes from boot through Arcade
Race to the starting grid, starts the race and holds the throttle; the
Civic does 27 mph a few seconds in, with the HUD, minimap and opponents
drawn. About 2-3 frames a second.

    XBRT_STATS=1 XBRT_INPUT_SCRIPT=../tools/input/race.txt XBRT_WINDOW=0 \
      XBRT_SCREENSHOT=shots XBRT_SCREENSHOT_EVERY=20 XBRT_HDD=hdd \
      timeout 420 ../runtime/forza.exe <default.xbe>

Use `XBRT_STATS=1` rather than `XBRT_LOG` for timing: logging every
kernel call slows the game's CPU side several times over.

Where the time goes (stats line): the device thread is busy all the
time, three quarters of it filling pixels even on 12 workers; vertices
about 10%, texture decodes a few %. The software rasteriser is near its
ceiling: the next real speed-up is drawing on the host GPU (vertex
programs and register combiners translated to shaders; see ROADMAP
phase 4), which is the large piece of work left.

Open bugs, in order:

1. `XBRT_BATCH=1` (fills batched across draws) leaves the race view
   black: a flush point is missing (a texture read of a surface the batch
   draws into without a surface change in between, perhaps through the
   zeta buffer, which `batch_note` covers but `nv2a_raster_invalidate`
   does not). Off by default; it gained nothing yet, but will matter
   once vertex work moves elsewhere.
2. Rendering: point sampling everywhere (blocky reflections and
   textures), no mipmaps, no fog, no stencil, the ground texture
   swims (no filtering). A grey frame sometimes during the pre-race
   flyby.
3. Audio: none (DSOUND's voices are mixed by nothing).

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
- 2026-10-18 (interactive, night): profile saving and the main menu.
  "Unable to save player profile" came from the recompiler, not the
  runtime: a data reference had made a false function start at
  0x7B649, the instruction after a `cmp` in the save routine, and the
  generated code reached it through a host call, so the `jnz` there read
  fresh flags and took the failure path. `analysis.Body` now walks
  through a known start that code falls into or branches to
  conditionally (3,198 functions in Forza do), stopping only where a
  `jmp` reaches it. Also: NtFlushBuffersFile, `XBRT_INPUT_SCRIPT` for
  timed button presses, `XBRT_LOG_FROM` to log only late in a run, and
  `xbrecomp -trace a,b,...` to make chosen functions log their arguments
  and results (it rewrites only changed C files, so a rebuild with a
  trace takes about a minute).
- 2026-10-18 (interactive, evening): into a race. Saves: with XboxHDKey
  zeroed XAPI keys signatures with the whole EEPROM, which the runtime
  left as stack garbage ("profile is damaged" on the next boot); now a
  fixed image. Fibers: a deleted fiber's host thread could be woken for a
  new fiber at the same address (KeBugCheck); MmDeleteKernelStack now
  forgets them. Files: ObfDereferenceObject did nothing, so closed files
  kept their share access and an exclusive reopen of a track file failed
  (the race load hung reading INVALID_HANDLE_VALUE). XLATB translated.
  Rasteriser: depth buffers, perspective-correct interpolation, the
  specular colour (V1). New aids: `XBRT_THREAD_DUMP=<s>[,<s>...]`, and
  sharing violations, reads past EOF and reads on bad handles print
  without a log.
- 2026-10-18 (interactive, night): races run and drive. Freezes: D3D
  learns GPU progress from PATT_COLOR0 (0x400B10), which the image
  pattern object's SET_MONOCHROME_COLOR0 (class 0x44, 0x310) sets; the
  old guess lost the lap bits, so D3D overwrote unread commands. The
  pusher now reads PUT every word, publishes GET as it goes and parks on
  a jump to itself (it spun forever before, starving vertical blanks).
  CancelIo's walk of IdexChannelObject+0x28 needs an empty list, not
  zeros. Rendering: cube maps, shadow maps (depth textures with the
  shadow compare). Speed 0.35 -> ~2.8 fps: filling on worker threads by
  rows, vertices once per draw and in parallel, a texture cache kept
  across surface changes (hash-checked). XBRT_STATS, XBRT_BATCH,
  XBRT_RASTER_THREADS; host crashes print their address.
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
