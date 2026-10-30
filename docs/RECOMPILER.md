# The recompiler

`recomp` turns each function that discovery found in Forza's XBE into a C
function. `cmd/xbrecomp` runs it over the whole game:

```sh
go run ./cmd/xbrecomp -xbsdb ~/XbSymbolDatabase -o out/ default.xbe
```

The output is `funcs.h`, `dispatch.c` (Xbox address → function table),
`code_NNNN.c` and the runtime header `xbrt.h`. It builds with gcc or clang;
see [Building the output](#building-the-output).

## How the C works

| x86 | C |
|---|---|
| Registers | fields of `XbCtx` (`c->eax`, `c->xmm[i]`, `c->st[i]`) |
| Memory | `xb_mem + address`: one 4 GB reservation, so Xbox pointers are used as they are |
| EFLAGS | local variables set by every flag-writing instruction. gcc deletes the ones nothing reads, and MSVC never keeps flags live across calls, so locals are enough |
| `jmp`/`jcc` inside a function | `goto` |
| `jmp` to another function | call, then return (a tail call) |
| `jmp [table + reg*4]` | `switch` over the table's targets |
| `call` / `ret` | push the real return address on the Xbox stack, call the C function; `ret` pops it and returns. Code that reads its own return address (`_chkstk`, `_SEH_prolog`) still works |
| `call [kernel thunk]` | `xb_kernel(c, ordinal)` |
| `call reg` / `call [mem]` | `xb_call_indirect(c, target)` |
| Anything unsupported | `xb_trap(c, addr, "unsupported: OP")`, so gaps fail loudly at run time |

A function's body is everything reachable from its entry without jumping
to another function's entry (`analysis.Body`). Falling through into a
known entry, or branching to one conditionally, keeps going: flags can be
live there, and a host call would lose them. That matters because data
references create false starts inside real functions; in Forza 3,198
functions run through one, and one of them (0x7B649, right after a `cmp`)
made every profile save fail. Tails that MSVC shares
between functions are duplicated into each one, since C cannot jump between
functions. Such a tail can sit below the entry, so a function starts with a
`goto` to its entry whenever the entry is not its lowest address. A jump
back to the entry is a loop, never a recursive call.

### Floating point

- **SSE1** maps to C `float` and runs on the host's SSE unit. The results are
  bit-identical as long as the C is built without FMA contraction and
  without fast math. MIN/MAX follow x86's NaN rule, and float-to-int gives
  the "integer indefinite" `0x80000000` for NaN and out-of-range values.
- **x87** maps to C `long double`. On x86-64 gcc and clang that is the x87's
  own 80-bit format, computed by the host's x87 unit. When the game loads a
  control word (`fldcw`), the runtime loads it into the host FPU too, so
  precision control (24/53/64-bit) and rounding modes apply exactly as on
  the Xbox. Transcendentals (`fsin`, `fpatan`, `fyl2x`…), `fprem` and the
  constants run as the real instructions via inline assembly, not libm. The
  x87 register stack lives in `XbCtx`, because MSVC returns `float`/`double`
  in ST(0) across calls.

- **MMX** (Bink, WMA) aliases the x87 registers as the hardware does.
  MMi is the low 64 bits of physical register Ri, a write sets Ri's
  exponent field to all ones, and every MMX instruction resets TOP to 0.
  Code that mixes MMX and x87 therefore behaves as on the Xbox.

Not modelled yet:
- the x87 tag word (FXAM never reports "empty") and x87 exception flags;
- the MXCSR rounding mode and flush-to-zero bits (MXCSR is stored and
  reloaded);
- RCPSS/RSQRTSS give exact results, where the Pentium III gives a 12-bit
  approximation.

## Coverage on Forza

| | functions fully translated | instructions |
|---|---|---|
| integer core | 81.6% | 62.4% |
| + SSE1 | 88.3% | 72.1% |
| + x87 | 98.7% | 96.9% |
| + MMX, `RCL`/`RCR`, `CMPXCHG8B`, `RDTSC` | 99.0% (17,292 of 17,462) | 97.8% |
| + pointer-only functions found (see below) | **99.1%** (of ~25,300) | **96.7%** |

The last row has more functions because discovery got stricter and wider
at once: immediates and data in every section (code sections included)
that point at plausible code now become function starts, and every
candidate must survive a plausibility walk (no `AAA`/`LES`/`IN`, no jump
into the middle of an instruction). Functions reached only through a
pointer, such as callbacks handed to the kernel, were what stopped the
first boots.

What's left is code that should never be translated:
- privileged instructions (`IN`/`OUT`/`CLI`/`STI`/`WBINVD`/`IRETD`) inside
  the D3D and DSOUND driver code, which phases 4 and 5 replace;
- bytes that discovery mistook for code (`AAA`, `LES`, `INTO`, `ENTER`…),
  most of them from data references that only look like functions. These
  include the ~50 "jumps outside function", such as a "function" that is
  just `jz` to itself.

`RDTSC` calls the runtime's `xb_rdtsc`, so the runtime controls what time
the game sees.

## Testing: differential against a reference CPU

`recomp/difftest_test.go` runs translated code and the original x86 from
the same starting state, then compares the results:

- **The C side** (`testdata/harness.c`) is the generated C plus a small
  harness. Each case runs in a forked child with a 0.2 s budget.
- **The reference side** (`testdata/unicorn_ref.py`) runs the original
  bytes on [Unicorn](https://www.unicorn-engine.org/), a CPU emulator
  derived from QEMU.
- **Starting state:** the XBE image, plus a 1 MB scratch region and a stack
  filled from a seeded generator. About a quarter of the dwords are
  pointers into scratch, so real code finds data it can follow. Registers
  are random (pointers, small integers, random bits), and XMM registers
  hold random floats including NaN, infinity and denormals.
- **Compared:** all 8 integer registers, a CRC of the scratch region, the
  stack and every writable section, a CRC of the XMM registers, and the
  x87 TOP and registers. A case the reference cannot finish (bad memory
  access, exception, more than 2M instructions) is skipped.

Two suites:

- **`TestEdgeDifferential`** runs in CI. `testdata/edge.s`, generated by
  `mkedge.py`, has 348 functions, one per instruction form: every ALU op
  at every width with both carry states, shifts and rotates with all
  counts, mul/div, bit ops, string ops with REP prefixes in both
  directions, all 16 conditions as jcc/setcc/cmov, SSE1, x87 including
  rounding and precision control, and MMX. Each case saves EFLAGS masked to
  the flags that instruction defines, and `.org` fails the build if a case
  outgrows its 256-byte slot. **Result: 473 forms, 13,573 cases, 0
  mismatches.**
- **`TestForzaDifferential`** needs `FORZA_XBE`. It runs every Forza
  function that translates fully, including call chains whose callees are
  all testable, except those that call the kernel, call indirectly, use
  `fs:`, `RDTSC` or x87 transcendentals (see below). **Result: 5,021
  functions (1,636 of them calling others), 6,241 compared cases, 0
  mismatches.** The other random cases fault on the
  reference CPU, usually on a random pointer, and are skipped. The run
  takes about 13 minutes.

Build tooling the suites need: gcc, GNU `as`/`objcopy`, and Python with
`unicorn` (`XBRT_PYTHON` picks the interpreter). `XBRT_KEEP=dir` keeps the
generated harness and inputs for debugging by hand.

### Where Unicorn is not a valid reference

Unicorn 2.1 is built on QEMU 5, which deviates from a real x87 in places.
The edge suite steers around these, and each one is commented in
`mkedge.py`:

- **x87 loads of signaling NaNs.** A real x87 (with invalid-operation
  masked) loads them as quiet NaNs, and so does our translation, which uses
  the real instruction. QEMU 5 keeps them signaling. Edge inputs are made
  quiet first.
- **Transcendentals and `fprem`/`fprem1`.** QEMU computes these through
  host double precision, so its results aren't the x87's. They are not in
  the edge suite, and the Forza test skips functions that use them.
- **MMX writes.** A real CPU sets the aliased x87 register's exponent to
  all ones (Intel SDM §9.5.1), and QEMU 5 leaves it 0. MMX edge cases
  store their results and then overwrite the x87 registers. For Forza
  functions that use MMX, the x87 register field is left out of the
  comparison; their MMX values still compare through memory and
  registers. Checked by hand on Forza's Bink code: every 64-bit MMX value
  matches, and only the exponent field differs.
- **Initial state.** Unicorn starts with x87 control word 0 (24-bit
  precision, exceptions unmasked) and IF clear. The harness sets the
  power-on values (`0x037F`, IF=1) on both sides.

What the differential tests found:

- **A real translator bug, found by the Forza test.** Functions whose
  shared tail sits below their entry started executing at the tail. In
  Forza that's 3 of 3,391 leaf functions, among them the CRT's `strchr`.
  It's fixed, with a unit test (`TestEntryNotFirst`).
- **Harness bugs:** the IF bit, raw EFLAGS left on the stack by `pushfd`,
  and a `fork`/`exit` interaction that re-read input files. They're fixed,
  and noted in the code where they could come back.
- **Unicorn deviations**, listed above. Each one was traced to the
  hardware definition, and in each case our translation follows the
  hardware.

## Building the output

```sh
gcc -O2 -ffp-contract=off -fno-math-errno -c code_0000.c   # and so on
```

- `-ffp-contract=off`: an FMA rounds once where the Pentium III rounds twice.
- No `-ffast-math`: it breaks NaN and signed-zero behaviour.
- `-fno-math-errno`: lets `sqrtf` compile to a single `sqrtss`.
- MSVC is not supported: its `long double` is 64-bit, not x87.
