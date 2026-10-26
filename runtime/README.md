# runtime

The C runtime that recompiled Xbox code links against. It stands in for
the Xbox kernel (HLE): the game's own code, XAPI and the C runtime run
recompiled, and every `xboxkrnl.exe` import lands here instead.

Linux or Windows on x86-64, with gcc or clang (on Windows, MinGW-w64 gcc,
for example [w64devkit](https://github.com/skeeto/w64devkit)). The
generated code keeps x87 math in 80-bit `long double`, which needs an x86
host and rules out MSVC. Windows needs version 10 1803 or later.

## Build and run

```sh
go run ./cmd/xbrecomp -xbsdb ~/XbSymbolDatabase -entries tools/entries.txt -o out/ default.xbe
make -C runtime GEN=../out -j$(nproc)
runtime/forza path/to/default.xbe        # runtime/forza.exe on Windows
```

Point it at the `default.xbe` of an extracted disc (extract-xiso does
this); the disc's `media` folder must sit next to it, or `XBRT_DISC` must
name the folder that holds it.

`-xbsdb` is needed: the runtime replaces library functions by name, and
the names come from XbSymbolDatabase. The generated C is large, so the
first build takes a while.

| variable | meaning | default |
|---|---|---|
| `XBRT_DISC` | the extracted disc (`D:`, `\Device\CdRom0`) | the XBE's directory |
| `XBRT_HDD` | the hard disk; `PartitionN` folders inside it | `./hdd` |
| `XBRT_LOG` | `1` logs every kernel call, `2` more | quiet |
| `XBRT_AUTOPRESS` | `1` taps START and A every two seconds | off |
| `XBRT_INPUT_SCRIPT` | a file of timed button presses (format in `hle_input.c`; example in `tools/input`) | off |
| `XBRT_INPUT_LIVE` | a file read while the game runs: each line added (`A`, `DOWN 0.12`) is pressed at once; with `XBRT_SCREENSHOT_EVERY` a run can be driven from outside | off |
| `XBRT_LOG_FROM` | with `XBRT_LOG`, start logging only after this many seconds | 0 |
| `XBRT_GPU` | `gl` fills on the GPU with OpenGL 4.3 (docs/GPU.md); several times faster | software |
| `XBRT_STATS` | `1` prints the GPU stats line every 5 s without logging kernel calls | off |
| `XBRT_RASTER_THREADS` | threads that fill pixels | half the logical cores, at most 16 |
| `XBRT_THREAD_DUMP` | seconds (comma-separated) at which to print every guest thread's registers, latest kernel call and stack | off |
| `XBRT_WINDOW` | `0` runs without a window (Windows shows one) | on |
| `XBRT_SCREENSHOT` | a folder to save the picture to as BMP files | off |
| `XBRT_SCREENSHOT_EVERY` | seconds between screenshots | 5 |
| `XBRT_TEX_DUMP` | a folder to save every decoded texture to, as BMP | off |
| `XBRT_RAM_DUMP` | `<file>:<seconds>` saves the 64 MB of RAM once | off |
| `XBRT_GPU_DUMP` | `<file>:<first flip>:<flips>` logs every GPU method, after the vertex program and constants as they stand; a first flip of `@<seconds>` starts at that time, `=<hex offset>` when the GPU is told to draw at that colour offset (`=2a29300:3`: the vinyl editor's livery) | off |
| `XBRT_GL_VSH_DUMP` | a folder to save each vertex program's GLSL to (`vsh<n>.glsl`), and which one every draw ran (`use.txt`: flip, draw, program, vertices) | off |
| `XBRT_GL_NO_SHADOW` | any value lights every shadow-map lookup (debugging) | off |
| `XBRT_GL_NO_STENCIL` | any value turns the stencil test off (before 26 Oct: Forza's race frame lost its glow mask, so no bloom) | off |
| `XBRT_GL_IDLE_READBACK` | `0`: framebuffers the game stopped drawing stay on the GPU (before 25 Oct; the Garage menu went black after the decal editor) | on |
| `XBRT_GL_SWIZZLED` | `0`: draws into swizzled render targets are dropped (before 25 Oct: no vinyls, no environment cube map) | on |
| `XBRT_TEX_LOG` | `1`: each texture (address, format) the first time a draw samples it | off |
| `XBRT_GL_SURF_LOG` | `1`: each GPU framebuffer as it is made (address, size, swizzled or not, depth) | off |
| `XBRT_RT_LOG` | `<hex offset>`: each draw (program, textures) and clear into that colour offset, all session (`2a29300`: the paint shop's livery); the RAM under the first 8 draws' textures to `screenshots/rt_<draw>_<stage>.bin` | off |
| `XBRT_F4_AT` | `<seconds>`: presses F4 once at that time (unattended runs) | off |
| `XBRT_PROFILE` | `<file>`: where the device thread spends its time, sampled every millisecond (the instruction and two callers), rewritten every 5 s; a `base` line first, for addr2line | off |
| `XBRT_GL_SWZ_SCALE` | `0`: swizzled framebuffers (the cars' reflection cube faces, the shade map, the vinyl editor's livery) at the Xbox's size instead of the render scale | 1 |
| `XBRT_DRAW_DISTANCE` | `1`-`8`: Forza's tree, reflection and trackside-detail distances times this, changed in memory after each track sets them (its .ini files are hash-checked). Objects still appear where the track's visibility sets say | 1 |
| `XBRT_ZONE_LEAD` | `1`-`8`: how many track zones ahead of the car Forza keeps loaded (tracklist.xml's ZoneWindowLeadCount, 1 on every track), set in memory (the file is hash-checked); against scenery streaming in in view; `zone_lead` in forza.ini | 3 |
| `XBRT_WAIT_LOG` | `<ms>`: each guest wait that took at least that long, signalled or timed out, with the guest's stack (stalls where the game stops) | off |
| `XBRT_LOCK_LOG` | `1`: each D3D LockRect, with the bytes brought back from the GPU first | off |
| `XBRT_MARK` | software renderer: draws of this many vertices come out magenta; `XBRT_MARK_NOZ=1` also skips their depth test | off |

Controller: on Windows the first XInput pad is the Xbox pad on port 1
(shoulder buttons are WHITE and BLACK); without one, the keyboard
(arrows, Enter START, Escape BACK, Space A, X B, C X, V Y, W/S triggers).

Debugging keys: F12 saves the picture to `screenshots/`; F4 saves the
64 MB of RAM there (`ram_<seconds>.bin`, with the GPU's drawing read back
into it), with every framebuffer's depth (`zmap_<address>.pgm`, shadow maps
among them) and the colour of the small ones (`cmap_<address>.ppm`); F3 writes every GPU method of the next frame there
(`gpu_<seconds>.txt`, as `XBRT_GPU_DUMP`); F5-F9 turn off culling, the
depth test, the alpha test, depth clipping, and GPU vertex programs (the
window title says which are on).

The hard disk folder fills like a console's: `Partition1` holds saves
(`TDATA`, `UDATA`), the game installs its archives to the cache
partitions it claims (`Z:` and `N:`, folders `Partition5` and `Partition4`),
and `partition0.bin` is the raw table of which title owns which cache
partition.

## Layout

| file | |
|---|---|
| `rt.h` | shared declarations and the guest address map |
| `main.c` | XBE loader, logging, fatal errors with a guest backtrace |
| `mem.c` | the 4 GB guest space, virtual/contiguous/pool allocators; on Windows, placeholders and commit on first touch |
| `thread.c` | guest threads (TLS, KPCR, KTHREAD), the big lock, handles, waits |
| `kernel.c` | kernel export dispatch and the Rtl/Ke/Nt/Ps/Ob/Mm/Ex/Hal/Io/Xe handlers |
| `file.c` | devices, symbolic links, raw partitions and the Nt/Io file calls |
| `dpc.c` | kernel timers and the DPC thread |
| `hw.c` | interrupts, PCI config space, I/O ports, the video encoder |
| `nv2a.c` | the GPU as its driver sees it: registers, push buffer, vblank |
| `kelvin.c` | the GPU's 3D engine methods: state, clears, semaphores, notifies |
| `raster.c` | drawing in software: vertices, vertex programs, textures, register combiners, blending |
| `gl.c`, `gl.h` | the OpenGL context and function loader for drawing on the host GPU (docs/GPU.md) |
| `glfill.c` | filling on the GPU: surfaces as framebuffers, the combiners as a shader (included by `raster.c`) |
| `apu.c` | the audio processor's registers, the AC'97 controller, and a stand-in for the GP DSP's command handling (nothing is played yet) |
| `hle_input.c` | XAPI's controller functions, replaced, read from XInput or the keyboard |
| `hle_net.c` | XNet and Winsock startup, replaced: a console with no network cable |
| `hle_fiber.c` | XAPI's SwitchToFiber, replaced: each fiber on its own host thread; fiber stacks |
| `crypto.c` | the kernel's SHA-1, HMAC and RC4 (save signing) |
| `display.c` | the picture: the scanned-out front buffer plus the video overlay, in a window and as screenshots |

## The GPU

D3D itself runs recompiled. What the runtime models is the hardware under
it: the NV2A's registers at 0xFD000000 and the push buffer of GPU methods
D3D writes in RAM. The recompiler routes memory accesses in the driver
sections (D3D, DSOUND) through a range check, so register reads and writes
reach `nv2a.c` with their hardware behaviour (interrupt bits that clear
when written with ones, a running timer, flushes that complete). A device
thread runs the push buffer whenever D3D moves PUT, writes fences back,
and raises the 60 Hz vertical blank.

Two driver handshakes matter for D3D to get past `Present`:

- Each D3D fence also sends the image pattern object (class 0x44,
  subchannel 5) a SET_MONOCHROME_COLOR0 (0x310) with the fence's push
  buffer position, time and lap count packed together. PGRAPH keeps it in
  PATT_COLOR0 (0x400B10), and D3D reads it back to learn how far the GPU
  has got when GET is outside the ring. An earlier guess, the semaphore
  value shifted left by 2, lost the lap bits: after the ring wrapped D3D
  thought the GPU was ahead, overwrote commands not yet read, and the
  race froze.
- A `NO_OPERATION` with a nonzero parameter is a notify for the driver.
  PGRAPH records it in TRAPPED_ADDR/DATA, raises the ERROR interrupt and
  stalls the push buffer until D3D's ISR clears it. D3D sends one per
  frame (Forza's two alternate, which looks like the two framebuffers)
  and uses one to wake `BlockOnTime`'s event.

Colour clears (`CLEAR_SURFACE`) are carried out on linear 32- and 16-bit
surfaces, and `raster.c` draws primitives in software (see the comment
at its top for what is covered). D3D renders a frame into an
anti-aliased back buffer, then draws that as a texture into the front
buffer it flips to, so both have to work for anything to show.
`XBRT_TEX_DUMP=<folder>` saves each texture as it is decoded.

What reaches the screen (`display.c`) is what the console's video output
would show: the front buffer at the address D3D programs into
`PCRTC_START`, with the video overlay (`PVIDEO`) composited on top. Bink
movies are decoded by the CPU into overlay surfaces, so they already
play, as does the loading screen's spinner.

## Threads and preemption

One guest thread runs at a time, under the big lock. A guest loop that
spins waiting for another thread or for an interrupt (D3D does this,
waiting for the GPU to pass a fence) would hold the lock forever, so every
translated loop back-edge checks `xb_preempt_pending` and, at PASSIVE
IRQL, hands the lock to whoever is waiting for it (`rt_gil_lock`). The DPC
thread asks for it every millisecond, which is when interrupts are
delivered. ISRs, DPCs and code at raised IRQL are never preempted.

## Replacing library code

Every generated function is a weak symbol, and xbrecomp writes `names.h`
with one line per named library symbol:

```c
#define XB_FN_XInputGetState f_0030A1B0   /* function */
#define XB_ADDR_XInputGetState 0x0030A1B0u
#define XB_VAR_g_DeviceType_Gamepad 0x004C5F40u /* variable */
```

(addresses for illustration). Defining `void XB_FN_Name(XbCtx *c)` in the
runtime overrides the recompiled function. A replacement reads its
arguments from the guest stack and pops them as the original did; see
`hle_input.c`. Wrap each one in `#ifdef XB_FN_Name`, since another build
of the game may not contain it.
