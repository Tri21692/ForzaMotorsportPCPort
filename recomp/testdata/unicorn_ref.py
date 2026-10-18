"""Reference side of the differential test: runs the original x86 code on
Unicorn with the same prepared state as harness.c and prints results in
the same format.

usage: python3 unicorn_ref.py image.bin funcs.txt < cases
  funcs.txt: one guest address (hex) per line, indexed like the harness
  cases and output: see harness.c. A case the CPU cannot finish (bad
  memory access, exception, runaway loop) prints "fault".

Keep the memory layout and fill in sync with harness.c.
"""
import struct
import sys
import zlib

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_PROT_ALL
from unicorn.x86_const import (UC_X86_REG_CR0, UC_X86_REG_CR4, UC_X86_REG_EAX, UC_X86_REG_EBP,
                               UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EDX,
                               UC_X86_REG_EFLAGS, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP,
                               UC_X86_REG_MXCSR, UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2,
                               UC_X86_REG_XMM3, UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6,
                               UC_X86_REG_XMM7)

SCRATCH_BASE, SCRATCH_SIZE = 0x10000000, 0x00100000
STACK_BASE, STACK_SIZE = 0x10F00000, 0x00010000
RETURN_SENTINEL = 0x0BAD0000
MAX_INSNS = 2_000_000

XMMS = [UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2, UC_X86_REG_XMM3,
        UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6, UC_X86_REG_XMM7]

REGS = [UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX,
        UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI]


def page_span(va, length):
    lo = va & ~0xFFF
    hi = (va + length + 0xFFF) & ~0xFFF
    return lo, hi


class Xorshift:
    def __init__(self, seed):
        self.x = seed or 1

    def next(self):
        x = self.x
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.x = x
        return x


def fill(rng, size):
    out = bytearray(size)
    for off in range(0, size, 4):
        v = rng.next()
        k = v & 3
        if k == 0:
            w = SCRATCH_BASE + (rng.next() & (SCRATCH_SIZE - 1) & ~3)
        elif k == 1:
            w = rng.next() & 0xFF
        else:
            w = rng.next()
        struct.pack_into("<I", out, off, w)
    return bytes(out)


def rand_float_bits(rng):
    v = rng.next()
    k = v & 7
    if k == 0:
        return 0
    if k == 1:
        return rng.next()
    return (rng.next() & 0x807FFFFF) | ((120 + (rng.next() & 15)) << 23)


def crc(chunks):
    h = 0
    for c in chunks:
        h = zlib.crc32(c, h)
    return h


def main():
    image_path, funcs_path = sys.argv[1], sys.argv[2]
    records = []
    data = open(image_path, "rb").read()
    pos = 0
    while pos < len(data):
        va, ln = struct.unpack_from("<II", data, pos)
        pos += 8
        n = ln & 0x7FFFFFFF
        records.append((va, n, bool(ln & 0x80000000), data[pos:pos + n]))
        pos += n
    funcs = [int(l, 16) for l in open(funcs_path) if l.strip()]

    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    spans = {}
    for va, n, _, _ in records:
        lo, hi = page_span(va, n)
        for p in range(lo, hi, 0x1000):
            spans[p] = True
    # Map contiguous runs of image pages once.
    pages = sorted(spans)
    i = 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 0x1000:
            j += 1
        uc.mem_map(pages[i], pages[j] - pages[i] + 0x1000, UC_PROT_ALL)
        i = j + 1
    uc.mem_map(SCRATCH_BASE, SCRATCH_SIZE, UC_PROT_ALL)
    uc.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_ALL)
    # Enable SSE: clear CR0.EM, set CR0.MP, and set CR4.OSFXSR/OSXMMEXCPT.
    uc.reg_write(UC_X86_REG_CR0, (uc.reg_read(UC_X86_REG_CR0) & ~0x4) | 0x2)
    uc.reg_write(UC_X86_REG_CR4, uc.reg_read(UC_X86_REG_CR4) | 0x600)

    writable = [(va, n) for va, n, w, _ in records if w]
    fills = {}  # seed -> (scratch, stack, xmm); filling in Python is slow
    for line in sys.stdin:
        parts = line.split()
        if len(parts) != 9:
            continue
        idx = int(parts[0])
        regs = [int(x, 16) for x in parts[1:8]]
        seed = int(parts[8], 16)

        for va, n, _, blob in records:
            uc.mem_write(va, blob)
        if seed not in fills:
            rng = Xorshift(seed)
            scratch, stack = fill(rng, SCRATCH_SIZE), fill(rng, STACK_SIZE)
            xmm = []
            for _ in range(8):
                lanes = [rand_float_bits(rng) for _ in range(4)]
                xmm.append(sum(v << (32 * k) for k, v in enumerate(lanes)))
            fills[seed] = (scratch, stack, xmm)
        uc.mem_write(SCRATCH_BASE, fills[seed][0])
        uc.mem_write(STACK_BASE, fills[seed][1])
        for reg, v in zip(XMMS, fills[seed][2]):
            uc.reg_write(reg, v)
        uc.reg_write(UC_X86_REG_MXCSR, 0x1F80)

        esp = STACK_BASE + STACK_SIZE - 0x1000 - 4
        uc.mem_write(esp, struct.pack("<I", RETURN_SENTINEL))
        for reg, v in zip([UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX,
                           UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EDI], regs):
            uc.reg_write(reg, v)
        uc.reg_write(UC_X86_REG_ESP, esp)
        # IF set, as game code always runs with interrupts enabled.
        uc.reg_write(UC_X86_REG_EFLAGS, 0x202)
        try:
            uc.emu_start(funcs[idx], RETURN_SENTINEL, count=MAX_INSNS)
        except UcError:
            print("fault", flush=True)
            continue
        if uc.reg_read(UC_X86_REG_EIP) != RETURN_SENTINEL:
            print("fault", flush=True)
            continue
        out = [uc.reg_read(r) for r in REGS]
        chunks = [bytes(uc.mem_read(SCRATCH_BASE, SCRATCH_SIZE)), bytes(uc.mem_read(STACK_BASE, STACK_SIZE))]
        chunks += [bytes(uc.mem_read(va, n)) for va, n in writable]
        xmm = b"".join(uc.reg_read(r).to_bytes(16, "little") for r in XMMS)
        print("ok " + " ".join("%08x" % v for v in out) + " %08x %08x" % (crc(chunks), zlib.crc32(xmm)), flush=True)


if __name__ == "__main__":
    main()
