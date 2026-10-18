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

## Phase 0: read the executable (mostly done)

- [x] XBE parser: sections, certificate, libraries, TLS, kernel thunks, SHA-1
- [x] Kernel export table with calling conventions
- [x] Function discovery: descent, jump tables, prologue and vtable scans
- [ ] Disassembly listing per function (`xbemap -dis`)
- [ ] Lower the indirect-jump count: find register-loaded jump tables and
      `jmp eax` after table loads
- [ ] Cross-references from code to data (strings, globals, float constants)

## Phase 1: name the library code

- Match XAPI, LIBC and LIBCPMT functions inside `.text` by byte signatures
  for XDK 5849. Cxbx-Reloaded's XbSymbolDatabase covers this version. Check
  its license before taking data from it, or build our own signatures from
  an XDK we have the rights to.
- Name the exported entry points of the D3D, DSOUND and XACT sections. These
  are the functions the runtime replaces.
- Output: a symbol map with real names wherever possible.

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

- Implement the 159 kernel imports listed in research/xbe.md: threads,
  sync, files mapped to an extracted-disc folder, memory, the crypto used
  for saves, and the data exports.
- Section loading: `XeLoadSection` / `XeUnloadSection` for `FZGINIT` and
  `FZFULLUI`.
- First milestone: the game boots, reaches its main loop, and logs its file
  reads, with graphics stubbed out.

## Phase 4: graphics

- Replace the Xbox D3D8 API at the function level. The closest PC target is
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
