# runtime

The C runtime that recompiled Xbox code links against. It stands in for
the Xbox kernel (HLE): the game's own code, XAPI and the C runtime run
recompiled, and every `xboxkrnl.exe` import lands here instead.

Linux on x86-64 with gcc or clang. The generated code keeps x87 math in
80-bit `long double`, which needs an x86 host.

## Build and run

```sh
go run ./cmd/xbrecomp -xbsdb ~/XbSymbolDatabase -o out/ default.xbe
make -C runtime GEN=../out -j$(nproc)
runtime/forza path/to/default.xbe
```

`-xbsdb` is needed: the runtime replaces library functions by name, and
the names come from XbSymbolDatabase. The generated C is large, so the
first build takes a while.

| variable | meaning | default |
|---|---|---|
| `XBRT_DISC` | the extracted disc (`D:`, `\Device\CdRom0`) | the XBE's directory |
| `XBRT_HDD` | the hard disk; `PartitionN` folders inside it | `./hdd` |
| `XBRT_LOG` | `1` logs every kernel call, `2` more | quiet |

## Layout

| file | |
|---|---|
| `rt.h` | shared declarations and the guest address map |
| `main.c` | XBE loader, logging, fatal errors with a guest backtrace |
| `mem.c` | the 4 GB guest space, virtual/contiguous/pool allocators |
| `thread.c` | guest threads (TLS, KPCR, KTHREAD), the big lock, handles, waits |
| `kernel.c` | kernel export dispatch and the Rtl/Ke/Nt/Ps/Ob/Mm/Ex/Hal/Io/Xe handlers |
| `file.c` | devices, symbolic links and the Nt file calls |
| `dpc.c` | kernel timers and the DPC thread |
| `hw.c` | interrupts, PCI config space, I/O ports, the video encoder |
| `nv2a.c` | the GPU as its driver sees it: registers, push buffer, vblank |
| `kelvin.c` | the GPU's 3D engine methods (state only; nothing is drawn yet) |
| `hle_input.c` | XAPI's controller functions, replaced |

## The GPU

D3D itself runs recompiled. What the runtime models is the hardware under
it: the NV2A's registers at 0xFD000000 and the push buffer of GPU methods
D3D writes in RAM. The recompiler routes memory accesses in the driver
sections (D3D, DSOUND) through a range check, so register reads and writes
reach `nv2a.c` with their hardware behaviour (interrupt bits that clear
when written with ones, a running timer, flushes that complete). A device
thread runs the push buffer whenever D3D moves PUT, writes fences back,
and raises the 60 Hz vertical blank. Drawing those methods on the PC is
the next step.

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
