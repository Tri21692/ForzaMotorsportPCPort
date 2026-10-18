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
open(sys.argv[1], "w").write("\n".join(out) + "\n")
print(len(cases), "cases")
