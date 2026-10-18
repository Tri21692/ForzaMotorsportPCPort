# Forza Motorsport's default.xbe

Taken from a retail NTSC/PAL dump (region `0x7` = all regions), certificate
version 1, built 2005-03-29 with XDK **5849**. To reproduce, run
`go run ./cmd/xbeinfo -kernel default.xbe`.

| | |
|---|---|
| Title ID | `4D53006E` ("MS" + 0x006E) |
| Base / image size | `0x10000` / `0x61FEA0` (~6.1 MB) |
| Entry point | `0x268EB5` (retail key) |
| Kernel thunk table | `0x485D80`, start of `.rdata`, 159 imports |
| TLS | no template data, 0xA8 bytes zero-fill, index at `0x5E4C28` |
| Stack / heap | 128 KB stack commit, 1 MB heap reserve |

## Sections

The linker gave each XDK library its own named section, which removes most
of the work of telling game code apart from library code:

| Sections | What they are | Port plan |
|---|---|---|
| `.text`, `FZGINIT`, `FZFULLUI` | Forza's own code (3.5 MB). `FZGINIT`/`FZFULLUI` are loaded on demand with `XeLoadSection` | recompile |
| `D3D`, `D3DX`, `XGRPH` | Xbox Direct3D 8, D3DX, XGraphics | replace (HLE) |
| `DSOUND`, `XACTENG`, `DOLBY` | DirectSound, XACT, Dolby encoder data | replace (HLE) |
| `WMADEC` | WMA decoder | recompile, it is plain CPU code |
| `BINK*` (15 sections) | Bink video decoder and per-format blitters | recompile, then hand frames to the renderer |
| `XONLINE`, `XNET`, `XON_RD` | Xbox Live and networking | stub out |
| `XPP` | Xbox peripheral port (controllers, memory units) | replace with PC input |
| `.rdata`, `.data`, `.data1`, `DDERR`, `BINKDATA` | data | load as is |
| `$$XTIMAGE`, `BKGDINST`, `HASHES`, `.XTLID` | dashboard images, title metadata and hashes (inserted files) | ignore |

XAPI and the C runtime (`LIBCMT`, `LIBCPMT`) have no section of their own.
They are mixed into `.text` and need signature matching (phase 1).

Every section's SHA-1 matches its header except `.data`. That usually means
the dump was patched after mastering, for example by a widescreen, region
or softmod patch. If something in `.data` looks odd later, keep this in mind.

## Kernel imports

There are 159 imports, and 130 of them are called directly from code that
`xbemap` finds. The groups below are what the HLE kernel has to provide:

- **Threads and sync:** `PsCreateSystemThreadEx`, events, semaphores,
  mutants, `NtWaitFor*`, `KeDelayExecutionThread`, critical sections, DPCs,
  timers. These map to OS threads and primitives.
- **Files:** `NtCreateFile`/`NtOpenFile`/`NtReadFile`/`NtWriteFile`,
  directory and volume queries, symbolic links (`D:` → disc, `T:`/`U:` →
  saves, `Z:` → cache). These map to a folder holding the extracted disc
  plus a save folder.
- **Memory:** `MmAllocateContiguousMemory*`, `NtAllocateVirtualMemory`,
  protection queries. These carve out of one 64 MB (or 128 MB) block mapped
  at the game's addresses.
- **Hardware:** `KeConnectInterrupt`, `HalReadWritePCISpace`,
  `MmClaimGpuInstanceMemory`, `Av*`. D3D and DSOUND use these to drive the
  NV2A and APU directly. Once those libraries are replaced, the game itself
  should never reach them.
- **Crypto:** `XcSHA*`, `XcHMAC`, `XcRC4*`, `XcModExp`, signature keys.
  Used for save signing and Xbox Live. Save signing has to give the same
  results as the real thing, or the game rejects its own saves.
- **Data exports:** `KeTickCount`, `XboxHardwareInfo`, `LaunchDataPage`,
  `XboxKrnlVersion` and the key blobs need real backing memory.

## Discovery numbers (xbemap, first version)

| | |
|---|---|
| Functions | ~17,500 over 5 rounds |
| `.text` coverage | 87.8% of bytes decoded as instructions |
| Switch jump tables resolved | 299 |
| Unresolved indirect jumps | 243 |
| Indirect calls | ~8,600, mostly C++ virtual calls |

Notes from tuning:

- 89% of direct call targets in `.text` are 16-byte aligned, and nearly all
  follow `0xCC` padding. Pointers found in data are only trusted as function
  starts when they fit that pattern and come in runs of at least two. That
  cut undecodable "functions" from 201 to 50.
- Data pointers into the middle of known functions are SEH scope-table
  handlers, not new functions, so they are skipped.
- `DSOUND` (35%) and `WMADEC` (26%) have low coverage because both hold large
  tables next to their code. That's fine, since DSOUND gets replaced anyway.

## Library symbols (sigdb + XbSymbolDatabase)

`sigdb` names 530 library symbols: 511 from XbSymbolDatabase and 19 C
runtime functions from our own patterns.

**Checked against the reference implementation.** XbSymbolDatabase's own
C CLI (`XbSymbolDatabaseCLI`, built from the same checkout) reports 507
symbols for this XBE. `sigdb` finds every one of them at the identical
address. The 4 extras are internal values the CLI computes but doesn't
print: `DSS_STREAM_VTABLE`, `DSS_VOICE_VTABLE`, `D3DTSS_TEXCOORDINDEX` and
`D3D_g_Stream_i_pVertexBuffer`. Two independent checks also agree with the
XBE parser:

- `mainCRTStartup` = `0x268EB5`, the decoded entry point.
- `_tls_index` = `0x5E4C28`, the TLS directory's index address.

| Library | Where |
|---|---|
| D3D8 | `D3D` section, plus the render-state block at `0x3C87B0` (`D3D_g_RenderState`) |
| DSOUND | `DSOUND` |
| XAPILIB | `.text` `0x264BF7`–`0x26CFF4`, plus `XPP` (input) |
| XACTENG | `XACTENG` |
| XONLINES | `XONLINE`, `XNET` |
| XGRAPHC | `XGRPH` |
| C runtime | `.text` `0x2F8078`–`0x2FC130` |

XAPI sits in one block of `.text` just below the entry point, and the C
runtime sits at the end of `.text`. That's the usual XDK link order: game
objects first, then XAPI, then the CRT.

### Matching details worth knowing

- **The C matcher treats the first *n* entries of a signature as XRefs**,
  where *n* is the count in its header, whichever macro wrote them. One
  Xapi signature writes a kernel-call XRef as `OV_MATCH`, and reading it as
  a byte loses `XID_fCloseDevice` and `XInputClose`.
- **Section order decides ties.** Sections are scanned in XBE order, and
  within a section the highest matching revision wins.
- The hand-written scans run before the automatic ones and depend on that
  order (D3D's render-state block, for example).

### C runtime

The compiler helpers are what the recompiler cares about most:

- `_ftol2`, the x87-to-integer conversion, is the most-called function in
  the CRT, with 817 call sites. That's a sign of how much the game relies
  on x87.
- `_allmul`/`_alldiv`/`_allrem`/`_aulldiv`/`_aullrem`/`_allshl`/`_aullshr`
  should become native 64-bit operations, not translated calls.
- `_chkstk` is called with the frame size in EAX before large stack frames.
- `_SEH_prolog`/`_SEH_epilog`/`_EH_prolog` mark functions using structured
  or C++ exception handling.

### Graphics access

`D3DDevice_SetRenderState_Simple` writes NV2A commands straight into the
push buffer. The write pointer is the global at `0x3C8A50`, and the code
calls nothing. Game code never references that pointer, `D3D_g_pDevice`
(`0x3C8A48`) or the render-state block. All 126 references to the device
pointer are inside the `D3D` section. So D3D has not been inlined into
Forza's code, and the game drives the GPU only through D3D's functions.

### Startup

`mainCRTStartup` (`0x268EB5`) does the following, in order:

1. It reads the XBE header from memory: the certificate at `[0x10118]` and
   the header size at `[0x10108]`.
2. It sizes the TLS block from the TLS directory at `0x4CE6EC`.
3. It starts `mainXapiStartup` on a new thread with `CreateThread`, or boots
   to the dashboard with `XapiBootToDash` if that fails.
4. It waits on that thread.

The runtime therefore has to map the header at `0x10000` and provide working
thread creation before any game code runs.
