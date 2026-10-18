"""Writes edge.s, the recompiler's edge-case suite: one small function per
instruction form, run by TestEdgeDifferential against Unicorn.

usage: python3 mkedge.py edge.s

Each case starts from random registers (esi points at random memory),
runs its body, then saves EFLAGS masked to the flags that instruction
defines; flags Intel leaves undefined may differ between real CPUs, so
they are not compared.
"""
import sys
ALL, LOGIC, MUL, CFONLY, ZFONLY, SHIFT, SHIFT1 = 0x8D5, 0x8C5, 0x801, 0x001, 0x040, 0x0C5, 0x8C5
cases = []
def case(name, body, mask):
    cases.append((name, body, mask))

for op in ["add", "sub", "adc", "sbb", "cmp"]:
    for w, a, b in [("32", "eax", "ebx"), ("16", "ax", "bx"), ("8", "al", "bl"), ("8h", "ah", "bh")]:
        # bt seeds CF from a random bit, so adc/sbb see both carries.
        case(f"{op}{w}", ["bt ecx, 0", f"{op} {a}, {b}"], ALL)
    case(f"{op}_mem", [f"bt ecx, 3", f"{op} dword ptr [esi], edx"], ALL)
    case(f"{op}_imm8", [f"{op} eax, -3"], ALL)
for op in ["and", "or", "xor", "test"]:
    case(f"{op}32", [f"{op} eax, ebx"], LOGIC)
    case(f"{op}8", [f"{op} al, bh"], LOGIC)
for op in ["inc", "dec"]:
    case(f"{op}32", ["bt ecx, 1", f"{op} eax"], ALL)
    case(f"{op}8", ["bt ecx, 1", f"{op} bl"], ALL)
case("neg32", ["neg eax"], ALL)
case("neg8", ["neg ah"], ALL)
case("not32", ["not eax"], 0)
for op in ["shl", "shr", "sar"]:
    case(f"{op}_cl", [f"{op} eax, cl"], SHIFT)
    case(f"{op}_1", [f"{op} ebx, 1"], SHIFT1)
    case(f"{op}_imm", [f"{op} edx, 7"], SHIFT)
    case(f"{op}8_cl", ["and ecx, 7", f"{op} al, cl"], SHIFT)
    case(f"{op}16_imm", [f"{op} bx, 5"], SHIFT)
for op in ["rol", "ror"]:
    case(f"{op}_cl", [f"{op} eax, cl"], CFONLY)
    case(f"{op}_1", [f"{op} ebx, 1"], 0x801)
    case(f"{op}8_cl", [f"{op} dl, cl"], CFONLY)
case("shld_cl", ["shld eax, ebx, cl"], SHIFT)
case("shrd_imm", ["shrd eax, edx, 9"], SHIFT)
case("imul2", ["imul eax, ebx"], MUL)
case("imul3", ["imul eax, ebx, -77"], MUL)
case("imul16", ["imul ax, bx"], MUL)
case("imul1", ["imul ebx"], MUL)
case("mul32", ["mul ebx"], MUL)
case("mul8", ["mul bl"], MUL)
case("mul16", ["mul bx"], MUL)
case("div32", ["xor edx, edx", "or ebx, 1", "div ebx"], None)
case("idiv32", ["cdq", "or ebx, 1", "idiv ebx"], None)
case("div8", ["and eax, 0x7FFF", "or bl, 0x80", "div bl"], None)
case("idiv16", ["cwd", "or bx, 1", "idiv bx"], None)
for op in ["bt", "bts", "btr", "btc"]:
    case(f"{op}_reg", [f"{op} eax, ebx"], CFONLY)
    case(f"{op}_imm", [f"{op} edx, 13"], CFONLY)
    case(f"{op}_mem_reg", ["and ebx, 0xFF", f"{op} dword ptr [esi], ebx"], CFONLY)
case("bsf", ["or ebx, 0x1000", "bsf eax, ebx"], ZFONLY)
case("bsr", ["bsr eax, ebx"], ZFONLY)
case("bswap", ["bswap eax"], 0)
case("xadd", ["xadd dword ptr [esi], eax"], ALL)
case("cmpxchg", ["cmpxchg dword ptr [esi], ebx"], ALL)
case("cmpxchg_eq", ["mov eax, dword ptr [esi]", "cmpxchg dword ptr [esi], ebx"], ALL)
case("xchg_mem", ["xchg dword ptr [esi+4], ecx"], 0)
case("cbw", ["cbw"], 0)
case("cwde", ["cwde"], 0)
case("cdq", ["cdq"], 0)
case("cwd", ["cwd"], 0)
case("movsx8", ["movsx eax, bl"], 0)
case("movsx16", ["movsx eax, word ptr [esi+2]"], 0)
case("movzx8h", ["movzx edx, ah"], 0)
case("lea", ["lea eax, [ebx+ecx*4-0x1234]"], 0)
case("sahf", ["sahf"], 0xD5)
case("lahf", ["cmp ebx, ecx", "lahf"], 0xD5)
for cc in ["o","no","b","ae","e","ne","be","a","s","ns","p","np","l","ge","le","g"]:
    case(f"set{cc}", ["cmp eax, ebx", f"set{cc} dl"], 0)
    case(f"cmov{cc}", ["cmp ecx, edx", f"cmov{cc} eax, ebx"], 0)
    case(f"j{cc}", ["xor edx, edx", "cmp al, bl", f"j{cc} 1f", "inc edx", "1:"], 0)
case("rep_movsb", ["cld", "and ecx, 63", "mov edi, esi", "add edi, 0x100", "rep movsb"], 0)
case("rep_movsd", ["cld", "and ecx, 15", "lea edi, [esi+0x200]", "rep movsd"], 0)
case("rep_stosd", ["cld", "and ecx, 15", "lea edi, [esi+0x40]", "rep stosd"], 0)
case("rep_stosb_back", ["std", "and ecx, 31", "lea edi, [esi+0x80]", "rep stosb", "cld"], 0)
case("repne_scasb", ["cld", "or ecx, 0x40", "and ecx, 0x7F", "mov edi, esi", "repne scasb"], ALL)
case("repe_cmpsb", ["cld", "and ecx, 0x3F", "lea edi, [esi+1]", "repe cmpsb"], ALL)
case("lodsd", ["cld", "lodsd"], 0)
case("loop", ["and ecx, 7", "inc ecx", "xor eax, eax", "2:", "add eax, ebx", "loop 2b"], 0)
case("jecxz", ["and ecx, 1", "xor eax, eax", "jecxz 3f", "inc eax", "3:"], 0)
case("pushad_popad", ["pushad", "mov eax, 1", "mov ebx, 2", "popad"], 0)
case("leave", ["push ebp", "mov ebp, esp", "sub esp, 32", "mov dword ptr [ebp-4], eax", "leave"], 0)
case("push_esp_rel", ["push dword ptr [esp+8]", "pop eax"], 0)
case("sub_reg8", ["mov ah, bl", "add ah, cl", "mov dh, al"], ALL)
case("rol16", ["rol ax, cl"], CFONLY)
case("adc_chain", ["add eax, ebx", "adc edx, ecx", "sbb esi, 1"], ALL)
for op in ["rcl", "rcr"]:
    case(f"{op}_cl", ["bt edx, 0", f"{op} eax, cl"], CFONLY)
    case(f"{op}_1", ["bt edx, 0", f"{op} ebx, 1"], 0x801)
    case(f"{op}8_cl", ["bt edx, 1", f"{op} al, cl"], CFONLY)
    case(f"{op}16_imm", ["bt edx, 2", f"{op} bx, 9"], CFONLY)
case("cmpxchg8b", ["cmpxchg8b qword ptr [esi]"], 0x40)
case("cmpxchg8b_eq", ["mov eax, dword ptr [esi]", "mov edx, dword ptr [esi+4]", "cmpxchg8b qword ptr [esi]"], 0x40)

# SSE1. xmm0-7 start as random floats (normal values, zeros, raw bits that
# include NaN, infinity and denormals); esi points at random memory.
for op in ["addss", "subss", "mulss", "divss", "minss", "maxss", "sqrtss"]:
    case(op, [f"{op} xmm0, xmm1"], None)
    case(op + "_mem", [f"{op} xmm2, dword ptr [esi]"], None)
for op in ["addps", "subps", "mulps", "divps", "minps", "maxps", "sqrtps", "andps", "andnps", "orps", "xorps"]:
    case(op, [f"{op} xmm3, xmm4"], None)
    case(op + "_mem", ["and esi, -16", f"{op} xmm5, xmmword ptr [esi]"], None)
case("movss_rr", ["movss xmm0, xmm7"], None)
case("movss_load", ["movss xmm1, dword ptr [esi+4]"], None)
case("movss_store", ["movss dword ptr [esi+8], xmm2"], None)
case("movaps_load", ["and esi, -16", "movaps xmm3, xmmword ptr [esi]"], None)
case("movaps_store", ["and esi, -16", "movaps xmmword ptr [esi+16], xmm4"], None)
case("movups", ["movups xmm5, xmmword ptr [esi+3]", "movups xmmword ptr [esi+37], xmm6"], None)
case("movlps_movhps", ["movlps xmm0, qword ptr [esi]", "movhps qword ptr [esi+8], xmm1", "movhps xmm2, qword ptr [esi+16]"], None)
case("movhlps_movlhps", ["movhlps xmm3, xmm4", "movlhps xmm5, xmm6"], None)
for imm in [0x00, 0x1B, 0xE4, 0x4E]:
    case(f"shufps_{imm:02x}", [f"shufps xmm1, xmm2, 0x{imm:02X}"], None)
case("unpcklps", ["unpcklps xmm0, xmm1"], None)
case("unpckhps", ["unpckhps xmm2, xmm3"], None)
for pred in range(8):
    case(f"cmpps_{pred}", [f"cmpps xmm4, xmm5, {pred}"], None)
    case(f"cmpss_{pred}", [f"cmpss xmm6, xmm7, {pred}"], None)
for op in ["comiss", "ucomiss"]:
    case(op, [f"{op} xmm0, xmm1"], 0x8D5)
    case(op + "_self", [f"{op} xmm2, xmm2"], 0x8D5)
case("cvtsi2ss", ["cvtsi2ss xmm0, eax", "cvtsi2ss xmm1, dword ptr [esi]"], None)
case("cvttss2si", ["cvttss2si eax, xmm1", "cvttss2si ebx, dword ptr [esi]"], None)
case("cvtss2si", ["cvtss2si eax, xmm2"], None)
case("movmskps", ["movmskps eax, xmm3"], None)
case("mxcsr", ["mov dword ptr [esp-8], 0x1F80", "ldmxcsr dword ptr [esp-8]", "stmxcsr dword ptr [esp-12]"], None)
case("rcpss", ["rcpss xmm0, xmm1"], None)
case("rsqrtps", ["rsqrtps xmm2, xmm3"], None)

# x87. Operands come from random memory at esi, read as floats, doubles and
# integers (quiet NaN, infinity and denormals included). Results are left
# on the register stack and stored, so both are compared.
#
# Where Unicorn (QEMU 5) is no reference for the real x87, cases stay out:
# - transcendentals (fsin, fcos, fptan, fpatan, fyl2x, f2xm1) and partial
#   remainders (fprem, fprem1), which it computes through host doubles;
# - signaling NaN loads, which a real x87 quiets and Unicorn does not.
#   QUIET sets the quiet bit of every float and double input first.
F, D = "dword ptr", "qword ptr"
QUIET = ["or dword ptr [esi], 0x00400000", "or dword ptr [esi+4], 0x00400000", "or dword ptr [esi+8], 0x00400000",
         "or dword ptr [esi+4], 0x00080000", "or dword ptr [esi+12], 0x00080000", "or dword ptr [esi+20], 0x00080000",
         "or dword ptr [esi+16], 0x00400000"]


def fcase(name, body, mask):
    case(name, QUIET + body, mask)


fcase("fld_fstp_m32", [f"fld {F} [esi]", f"fstp {F} [esi+64]"], None)
fcase("fld_fst_m64", [f"fld {D} [esi]", f"fst {D} [esi+64]"], None)
fcase("fld_m80_roundtrip", [f"fld {D} [esi]", "fstp tbyte ptr [esi+64]", "fld tbyte ptr [esi+64]"], None)
fcase("fld_st", [f"fld {F} [esi]", f"fld {F} [esi+4]", "fld st(1)", "fst st(2)"], None)
for w, m in [("16", "word ptr"), ("32", F), ("64", D)]:
    fcase(f"fild{w}", [f"fild {m} [esi]"], None)
    fcase(f"fistp{w}", [f"fld {F} [esi]", f"fistp {m} [esi+64]"], None)
fcase("fist16_32", [f"fld {D} [esi]", "fist word ptr [esi+64]", f"fist {F} [esi+68]"], None)
for op in ["fadd", "fsub", "fsubr", "fmul", "fdiv", "fdivr"]:
    fcase(op + "_m32", [f"fld {F} [esi]", f"{op} {F} [esi+4]"], None)
    fcase(op + "_m64", [f"fld {D} [esi]", f"{op} {D} [esi+8]"], None)
    fcase(op + "_st0_sti", [f"fld {F} [esi]", f"fld {F} [esi+4]", f"{op} st(0), st(1)"], None)
    fcase(op + "_sti_st0", [f"fld {F} [esi]", f"fld {F} [esi+4]", f"{op} st(1), st(0)"], None)
    fcase(op + "p", [f"fld {F} [esi]", f"fld {F} [esi+4]", f"{op}p st(1), st(0)"], None)
    iop = "fi" + op[1:]
    fcase(iop + "16", [f"fld {F} [esi]", f"{iop} word ptr [esi+4]"], None)
    fcase(iop + "32", [f"fld {F} [esi]", f"{iop} {F} [esi+4]"], None)
for op in ["fchs", "fabs", "fsqrt", "frndint"]:
    fcase(op, [f"fld {F} [esi]", op], None)
fcase("fscale", [f"fild word ptr [esi]", f"fld {F} [esi+4]", "fscale"], None)
fcase("fxch", [f"fld {F} [esi]", f"fld {F} [esi+4]", f"fld {F} [esi+8]", "fxch st(2)"], None)
for k in ["fldz", "fld1", "fldpi", "fldl2e", "fldl2t", "fldlg2", "fldln2"]:
    fcase(k, [k], None)
for op in ["fcom", "fcomp", "fucom", "fucomp"]:
    fcase(op + "_st", [f"fld {F} [esi]", f"fld {F} [esi+4]", f"{op} st(1)", "fnstsw ax"], None)
    if not op.startswith("fucom"):  # fucom has no memory form
        fcase(op + "_m64", [f"fld {F} [esi]", f"{op} {D} [esi+8]", "fnstsw ax"], None)
fcase("fcompp", [f"fld {F} [esi]", f"fld {F} [esi+4]", "fcompp", "fnstsw ax", "sahf"], 0xD5)
fcase("fucompp", [f"fld {F} [esi]", f"fld {F} [esi+4]", "fucompp", "fnstsw ax"], None)
fcase("ficom", [f"fld {F} [esi]", f"ficom {F} [esi+4]", "fnstsw ax"], None)
fcase("ficomp16", [f"fld {F} [esi]", "ficomp word ptr [esi+4]", "fnstsw ax"], None)
fcase("ftst", [f"fld {F} [esi]", "ftst", "fnstsw ax"], None)
fcase("fxam", [f"fld {F} [esi]", "fxam", "fnstsw ax"], None)
fcase("fxam_zero", ["fldz", "fchs", "fxam", "fnstsw word ptr [esi]"], None)
for op in ["fcomi", "fcomip", "fucomi", "fucomip"]:
    fcase(op, [f"fld {F} [esi]", f"fld {F} [esi+4]", f"{op} st(0), st(1)"], 0x45)
for cc in ["b", "e", "be", "u", "nb", "ne", "nbe", "nu"]:
    fcase(f"fcmov{cc}", [f"fld {F} [esi]", f"fld {F} [esi+4]", "cmp eax, ebx", f"fcmov{cc} st(0), st(1)"], None)
fcase("fnstcw_fldcw", ["fnstcw word ptr [esi]", "fldcw word ptr [esi]", "fnstcw word ptr [esi+2]"], None)
for cw, what in [(0x077F, "round_down"), (0x0B7F, "round_up"), (0x0F7F, "truncate")]:
    fcase(f"rc_{what}", [f"mov word ptr [esp-8], 0x{cw:04X}", "fldcw word ptr [esp-8]", f"fld {D} [esi]",
                        f"fdiv {D} [esi+8]", f"fist {F} [esi+64]", f"fst {F} [esi+68]", "frndint",
                        "mov word ptr [esp-8], 0x037F", "fldcw word ptr [esp-8]"], None)
for cw, what in [(0x027F, "double"), (0x007F, "single")]:
    fcase(f"pc_{what}", [f"mov word ptr [esp-8], 0x{cw:04X}", "fldcw word ptr [esp-8]", f"fld {D} [esi]",
                        f"fmul {D} [esi+8]", f"fadd {D} [esi+16]", "mov word ptr [esp-8], 0x037F",
                        "fldcw word ptr [esp-8]"], None)
fcase("fninit", [f"fld {F} [esi]", "fninit", "fnstcw word ptr [esi]", "fnstsw word ptr [esi+2]"], None)
fcase("fincstp", [f"fld {F} [esi]", "fincstp", "fdecstp", "fdecstp"], None)
fcase("fnstsw_top", [f"fld {F} [esi]", f"fld {F} [esi+4]", "fnstsw ax"], None)

# MMX. Operands are loaded from random memory. MMX registers alias the x87
# registers, and a real CPU sets the aliased register's exponent field to
# all ones on every MMX write; Unicorn (QEMU 5) leaves it 0. So each case
# stores mm0-mm3 and the x87 status word (TOP) to memory, then overwrites
# all eight x87 registers with fldz, and only the stored values compare.
MM = ["movq mm0, qword ptr [esi]", "movq mm1, qword ptr [esi+8]"]
MM_END = ["movq qword ptr [esi+64], mm0", "movq qword ptr [esi+72], mm1", "movq qword ptr [esi+80], mm2",
          "movq qword ptr [esi+88], mm3", "fnstsw word ptr [esi+96]", "emms"] + ["fldz"] * 8


def mcase(name, body):
    case(name, body + MM_END, None)

for op in ["paddb", "paddw", "paddd", "psubb", "psubw", "psubd", "paddsb", "paddsw", "psubsb", "psubsw",
           "paddusb", "paddusw", "psubusb", "psubusw", "pmullw", "pmulhw", "pmulhuw", "pmaddwd",
           "pcmpeqb", "pcmpeqw", "pcmpeqd", "pcmpgtb", "pcmpgtw", "pcmpgtd", "pavgb", "pavgw",
           "pmaxsw", "pminsw", "pmaxub", "pminub", "pand", "pandn", "por", "pxor",
           "punpcklbw", "punpcklwd", "punpckldq", "punpckhbw", "punpckhwd", "punpckhdq",
           "packsswb", "packuswb", "packssdw"]:
    mcase(op, MM + [f"{op} mm0, mm1"])
    size = "dword" if op.startswith("punpckl") else "qword"  # low unpacks read m32
    mcase(op + "_mem", MM + [f"{op} mm1, {size} ptr [esi+16]"])
for op in ["psllw", "pslld", "psllq", "psrlw", "psrld", "psrlq", "psraw", "psrad"]:
    mcase(op + "_imm", MM + [f"{op} mm0, 5"])
    mcase(op + "_big", MM + [f"{op} mm1, 40"])
    mcase(op + "_reg", MM + ["mov eax, ecx", "and eax, 0x7F", "movd mm2, eax", f"{op} mm0, mm2"])
mcase("pshufw", MM + ["pshufw mm2, mm0, 0x1B", "pshufw mm3, qword ptr [esi+8], 0xE4"])
mcase("movd", MM + ["movd mm2, ecx", "movd eax, mm0", "movd dword ptr [esi+32], mm1"])
mcase("movq_store", MM + ["movq qword ptr [esi+40], mm0", "movntq qword ptr [esi+48], mm1"])
mcase("pmovmskb", MM + ["pmovmskb eax, mm0"])
mcase("mmx_resets_top", ["fld1", "fld1", "movq mm0, qword ptr [esi]"])
# SSE/MMX conversions: random floats include NaN and out-of-range values,
# which give the integer indefinite value.
mcase("cvtps2pi", MM + ["cvtps2pi mm2, xmm1", "cvttps2pi mm3, qword ptr [esi+24]"])
mcase("cvtpi2ps", MM + ["cvtpi2ps xmm2, mm1", "cvtpi2ps xmm3, qword ptr [esi+24]"])

out = [".intel_syntax noprefix", ".code32", ".text",
       "# Generated by mkedge.py: one function per instruction form, each",
       "# 256 bytes apart. A function runs its body, stores EFLAGS (masked",
       "# to the flags that instruction defines) at [esp-64], and returns.", ""]
for i, (name, body, mask) in enumerate(cases):
    out.append(f".balign 256")
    out.append(f"# {i}: {name}")
    out.append(f"f_{name}:")
    out += ["    " + l if not l.endswith(":") else l for l in body]
    if mask is not None:
        # pushfd leaves the raw value (undefined flags included) in its
        # stack slot; keep only the masked copy.
        out += ["    pushfd", "    pop dword ptr [esp-64]", f"    and dword ptr [esp-64], 0x{mask:X}",
                "    mov dword ptr [esp-4], 0"]
    out.append("    ret")
    # The test finds case i at offset 256*i; .org pads to the next slot and
    # fails to assemble if a case outgrows its 256 bytes.
    out.append(f".org f_{name} + 256")
open(sys.argv[1], "w").write("\n".join(out) + "\n")
print(len(cases), "cases")
