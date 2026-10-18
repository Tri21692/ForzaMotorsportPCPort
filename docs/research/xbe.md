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

The signature scan names 412 symbols in about 0.1 s. Every match lands in
its library's own section, and no two functions share an address. Two
independent checks agree with the XBE parser:

- `mainCRTStartup` matches at `0x268EB5`, which is exactly the decoded entry
  point.
- `_tls_index` is derived as `0x5E4C28`, the same address the TLS directory
  gives.

| Library | Symbols | Where |
|---|---|---|
| D3D8 | 102 | `D3D` (and 1 inlined into `.text`) |
| DSOUND | 202 | `DSOUND` |
| XAPILIB | 49 | `.text` `0x264BF7`–`0x26CFF4`, plus `XPP` (input) |
| XACTENG | 20 | `XACTENG` |
| XONLINES | 21 | `XONLINE`, `XNET` |
| XGRAPHC | 7 | `XGRPH` |
| derived | 11 | globals and struct offsets, e.g. `g_XapiMountedMUs`, `D3DDevice__m_VertexShader_OFFSET` = 0x794 |

XAPI sits in one block of `.text` just below the entry point, which is the
usual XDK link order: game objects first, then XAPI and the CRT. The
unnamed functions around `0x264000`–`0x270000` are probably the rest of
XAPI plus LIBC.

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
