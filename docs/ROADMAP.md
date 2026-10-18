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

## Phase 2: static recompiler (x86 → C)

- Emit one C function per discovered function. Registers and flags live in a
  context struct, and memory goes through a flat block mapped at the Xbox
  addresses (base `0x10000`), so pointers in the game stay valid.
- Indirect calls and jumps go through a lookup table from Xbox address to
  host function. Misses log and trap, which tells us what discovery missed.
- x87 FPU (a stack machine with 80-bit registers, which the physics code
  uses heavily), SSE1 and MMX (Bink). Getting x87 precision right matters
  for a driving sim; replays and physics can drift on 64-bit doubles.
- Calls into replaced libraries become calls into the runtime.
- Test by running small functions natively and recompiled side by side, and
  later by comparing traces against xemu.

## Phase 3: runtime (HLE kernel)

- Map the XBE header itself at `0x10000`. `mainCRTStartup` reads it back
  (certificate pointer at `0x10118`, header size at `0x10108`) along with
  the TLS directory, just as it would on the console.
- Implement the 159 kernel imports listed in research/xbe.md: threads,
  sync, files mapped to an extracted-disc folder, memory, the crypto used
  for saves, and the data exports.
- Section loading: `XeLoadSection` / `XeUnloadSection` for `FZGINIT` and
  `FZFULLUI`.
- First milestone: the game boots, reaches its main loop, and logs its file
  reads, with graphics stubbed out.

## Phase 4: graphics

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
