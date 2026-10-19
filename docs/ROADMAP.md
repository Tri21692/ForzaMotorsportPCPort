# Roadmap

The goal is a native PC executable built from the player's own
`default.xbe`, with no emulator inside it. This is the static recompilation
approach that N64Recomp and XenonRecomp use. The original Xbox has two
things going for it here:

- The CPU is a Pentium III. That means x86 in and x86 out, with no
  endianness change, a well-documented instruction set, and SSE1 that maps
  straight to modern SSE.
- The XDK libraries are linked into sections with their own names (see
  [research/xbe.md](research/xbe.md)). Where the game code ends and D3D or
  DSOUND begins is known for free.

The hard parts are graphics and audio, not the CPU.

## Phase 0: read the executable (done)

- [x] XBE parser: sections, certificate, libraries, TLS, kernel thunks, SHA-1
- [x] Kernel export table with calling conventions
- [x] Function discovery: descent, jump tables, prologue and vtable scans
- [x] Disassembly listing per function (`xbedis`)
- [x] Jump tables indexed after `and reg, mask` (unused slots) and after
      `neg reg` (backwards), as the CRT's memcpy/memmove use them.
- [ ] Lower the indirect-jump count: find register-loaded jump tables and
      `jmp eax` after table loads
- [ ] Cross-references from code to data (strings, globals, float constants)

## Phase 1: name the library code (done)

- [x] Signature matcher for XbSymbolDatabase (package `sigdb`): it parses
      the database's C sources and runs its XRef-resolving scan.
- [x] Port the hand-written scans (`manual_*.h`): D3D render-state block,
      device callbacks, DSOUND stream vtable, XAPI device tables.
- [x] **Checked against the original.** XbSymbolDatabase's own C CLI,
      built from source, prints 507 symbols for Forza. `sigdb` finds all
      507 at identical addresses, plus 4 internal values the CLI computes
      but doesn't print.
- [x] C runtime helpers the database lacks (`sigdb/crt.go`, our own
      patterns): 64-bit arithmetic, `_ftol2`, `_chkstk`, SEH frames,
      `memcpy` and the string routines. 19 functions, each checked by
      disassembly. memset/strlen/strcpy/strcmp are compiler intrinsics in
      this build, so they are inlined rather than called.
- [x] Calling conventions and parameter lists from the database are kept
      on each symbol, for the runtime's replacement functions.

Result: 530 named library symbols. Still open but not blocking: the rest
of LIBC (printf family, heap, file I/O), which can be named as the
recompiler runs into them.

## Phase 2: static recompiler (x86 → C) (done)

Design and test details are in [RECOMPILER.md](RECOMPILER.md).

- [x] One C function per discovered function: registers in a context
      struct, memory as a flat 4 GB space at the Xbox addresses, flags as
      locals the compiler prunes, `goto`/tail calls/`switch` for control
      flow.
- [x] Integer core, SSE1, x87 as 80-bit `long double` on the host x87
      with the game's control word mirrored, MMX aliased onto the x87
      registers as on hardware. **99.2% of Forza's functions translate
      fully**. The rest is driver code that gets replaced, plus misdecoded
      data, and all of the generated C compiles.
- [x] Differential testing against Unicorn: 473 edge-case instruction
      forms (13,573 cases, 0 mismatches, run in CI) plus 5,021 fully
      translated Forza functions (6,241 cases, 0 mismatches). This caught one real bug (entry
      ordering), now fixed.
- [x] Data-reference discovery checks every candidate with a
      plausibility walk, and finds functions reached only through
      pointers (immediates and data in all sections).
- [x] Differential tests for functions that call others: call chains
      whose callees are all testable (1,636 functions).
- [x] Every generated function is a weak symbol, and `names.h` maps
      library names to them, so the runtime replaces library code (HLE)
      by defining a function of the same name.
- [ ] x87 tag word and exception flags, MXCSR rounding mode, if the game
      turns out to depend on them.
- [ ] Size and speed: the output is 141 MB of C. Emit flags only where
      some later instruction can read them, and cache memory addresses
      that repeat.

## Phase 3: runtime (HLE kernel) (in progress)

The runtime is in `runtime/`; see [runtime/README.md](../runtime/README.md).

- [x] Load the XBE at `0x10000`, header included, with TLS laid out per
      thread and a KPCR/KTHREAD at `fs:` as XAPI expects.
- [x] Threads as host threads under one big lock, waits, events,
      semaphores, mutants, timers and DPCs (on their own thread).
- [x] Memory: virtual, contiguous, pool and system allocations.
- [x] Files: `\Device\CdRom0` mapped to an extracted-disc folder,
      `\Device\Harddisk0\PartitionN` to `hdd/PartitionN`, symbolic links.
- [x] `XeLoadSection` / `XeUnloadSection`, data exports, non-volatile
      settings, DbgPrint.
- [x] Controllers: XAPI's input functions replaced (one neutral gamepad).
- [x] Interrupts, PCI config space, port I/O, the AV encoder.
- [x] Windows host (MinGW-w64): the 4 GB guest space as placeholders with
      the RAM views mapped twice and memory committed on first touch,
      binary-mode files, timed waits on the wall clock.
- [x] Preemption: translated loop back-edges hand the big lock to a
      waiting thread, so code that spins on a fence lets the ISR in.
- [x] Hard disk as the console has it: raw partitions, the cache partition
      table on partition 0, formatting, `Z:` (`XMountUtilityDrive`) and
      `N:`, delete and rename, FILE_OBJECTs for `XGetFilePhysicalSortKey`.
- [x] Controllers from XInput or the keyboard.
- [x] File semantics the installer needs: NT share access, unbuffered
      writes clipped at end of file, failed reads that leave the
      caller's IO_STATUS_BLOCK and event alone, user APCs (ReadFileEx)
      delivered in alertable waits, the file system cache calls.
- [x] APU registers DSOUND waits on (`apu.c`), networking as "no cable"
      (`hle_net.c`).
- [x] Directory listings, fibers (one host thread per fiber, sharing the
      guest thread), the CPU's identity (cpuid, EFLAGS.ID), save signing
      crypto (SHA-1, HMAC, RC4; the console's keys are zeroed, so saves
      stay on this machine).
- **Status:** with the player's extracted disc, the game boots through
  the install, the movies and its saves into the front end, creates and
  saves a profile, and races: with `XBRT_GPU=gl` a race on Maple Valley
  runs at 16-21 frames a second, all drawn; no sound yet. See
  [NIGHTLY.md](NIGHTLY.md) for what is next.
- [ ] The remaining kernel imports as the game reaches them.

## Phase 4: graphics (in progress)

**Approach chosen: run D3D recompiled and model the GPU underneath it.**
Forza writes the push buffer itself in places (`BeginPush`, and inline
render-state methods), and D3DX and the game call 122 D3D entry points,
so replacing D3D would still need a push-buffer decoder. The hardware
boundary is smaller and fixed instead.

- [x] NV2A registers with hardware behaviour, PFIFO push buffer
      (jumps, calls, methods), object lookup in instance memory, fences
      (semaphore release), vertical blank interrupt. D3D initialises the
      device and runs its startup command stream.
- [x] The driver handshakes `Present` needs: semaphore releases mirrored
      into PGRAPH 0x400B10, NOP notifies trapped to the ISR.
- [x] A window and screenshots: the scanned-out front buffer with the
      video overlay composited, so Bink movies play; colour clears.
- [x] A software rasteriser (`runtime/raster.c`) for the front end:
      inline and array vertices, vertex programs interpreted, the
      transform constants the fixed-function methods load, register
      combiners, four texture stages (swizzled, linear, palettised, DXT;
      pass-through mode), blending, anti-aliased surfaces. The menus
      draw, text included.
- [ ] Pace flips to the vertical blank (they run at ~500 a second now).
- [x] Depth, swizzled and cube textures, shadow maps, filtering and
      mipmaps (GPU path), fog: what the race uses so far.
- [ ] Stencil, fixed-function fog and lighting, texgen.
- [x] Drawing on the PC's GPU (`XBRT_GPU=gl`, docs/GPU.md): register
      combiners as one fragment shader, vertex programs translated to
      GLSL, render targets sampled where they were drawn.
- [ ] Keep framebuffers on the GPU across flips; batch draws.

Earlier notes, from when the plan was to replace the API:

- Replace the Xbox D3D8 API at the function level. Evidence that this
  works for Forza: game code never references D3D's globals (the device
  pointer, push buffer, render state block). All 126 references are inside
  the D3D section, so the game reaches the GPU only through D3D calls.
  The game could still write device memory through a pointer it was
  given, and the runtime should trap that rather than assume it can't
  happen. The closest PC target is
  real D3D8. DXVK has run D3D8 on Vulkan since 2.4, so Xbox D3D → PC D3D8 →
  DXVK is a possible first path. A direct Vulkan backend is the long-term
  option.
- Xbox-only features to handle: swizzled textures, push buffers (check
  whether Forza writes them directly), register combiners (pixel shaders),
  vertex shader microcode, tiling, and the 64 MB unified memory where the
  CPU writes GPU resources in place.
- Bink videos: the recompiled Bink code decodes them, and the frames get
  uploaded as textures.

## Phase 5: audio, input, saves

- DSOUND and XACT: replace with a PC mixer. The game feeds 3D voices and
  effects, and the APU's DSP effects (reverb) will be approximated.
- WMA soundtrack: the recompiled `WMADEC` code decodes it.
- Input: XPP and XInputGetState → XInput/SDL gamepads, plus wheels later.
- Saves: map `U:` to a folder and keep save signing correct.

## Phase 6: PC features

Higher resolutions, widescreen, unlocked frame rate (only after physics is
split from rendering), mod hooks.

## Non-goals

- Shipping any game code or assets.
- Xbox Live. The servers are gone, so online code gets stubbed.
