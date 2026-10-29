/* The career's Race Type screen (XBRT_CAREER_TIMETRIAL=1): the panel of the
 * selected category, sub_00184C30, as recompiled, but for one test. The
 * game draws the "Level N" tab and the "{0}/{1} Events Completed" box only
 * for a tile after the first (its test at 0x184C9D: the first was Online
 * Career's, which has neither), so the Time Trial category that takes its
 * place (nv2a.c's career_timetrial) had neither either. With it in place
 * (its folder renamed: the table's first name at 0x4D02C0) the first tile
 * gets them too; the numbers are the ones sub_00184F30 already works out
 * for it (+0x28 the lowest level, +0x2C done, +0x30 the events).
 *
 * The rest is out/code_0023.c's f_00184C30 as it was generated: if the
 * game is recompiled again, copy it anew and keep the one change, marked. */
#include <stdlib.h>

#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

static int tt_first_tile(uint32_t index) {
    static int on = -1;
    if (on < 0) on = getenv("XBRT_CAREER_TIMETRIAL") && atoi(getenv("XBRT_CAREER_TIMETRIAL"));
    return on && index == 0 && xb_rd32(0x52E850) == 0x4D02C0;
}

void f_00184C30(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 00184C30  sub esp, 0x148 */
    { uint32_t a = c->esp, b = 0x148u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184C36  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 00184C37  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 00184C38  push edi */
    { uint32_t v = c->edi; xb_push(c, v); }
    /* 00184C39  mov edi, ecx */
    c->edi = (uint32_t)(c->ecx);
    /* 00184C3B  mov esi, dword ptr [edi+0x2590] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->edi + 0x00002590u)));
    /* 00184C41  imul esi, esi, 0x34 */
    { int64_t p = (int64_t)(int32_t)(c->esi) * (int64_t)(int32_t)(0x34u); uint32_t r = (uint32_t)p & 0xFFFFFFFFu; cf = of = p != (int64_t)(int32_t)(r); c->esi = (uint32_t)(r); }
    /* 00184C44  add esi, 0x52e850 */
    { uint32_t a = c->esi, b = 0x52E850u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
    /* 00184C4A  lea eax, ptr [esi+0x8] */
    c->eax = (uint32_t)((uint32_t)(c->esi + 0x00000008u));
    /* 00184C4D  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184C4E  lea ecx, ptr [edi+0x3a60] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003A60u));
    /* 00184C54  call 0x129bf0 */
    xb_push(c, 0x00184C59u); f_00129BF0(c);
    /* 00184C59  lea ecx, ptr [esi+0x18] */
    c->ecx = (uint32_t)((uint32_t)(c->esi + 0x00000018u));
    /* 00184C5C  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184C5D  lea ecx, ptr [edi+0x3ba0] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003BA0u));
    /* 00184C63  call 0x129bf0 */
    xb_push(c, 0x00184C68u); f_00129BF0(c);
    /* 00184C68  mov eax, dword ptr [esi+0x4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000004u)));
    /* 00184C6B  mov edx, dword ptr [edi+0x2048] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->edi + 0x00002048u)));
    /* 00184C71  lea ecx, ptr [edi+0x2048] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00002048u));
    /* 00184C77  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184C78  call dword ptr [edx+0x78] */
    { uint32_t t = xb_rd32((uint32_t)(c->edx + 0x00000078u)); xb_push(c, 0x00184C7Bu); xb_call_indirect(c, t); }
    /* 00184C7B  push 0x4b57f8 */
    { uint32_t v = 0x4B57F8u; xb_push(c, v); }
    /* 00184C80  lea ecx, ptr [esp+0x10] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00184C84  call 0x270d00 */
    xb_push(c, 0x00184C89u); f_00270D00(c);
    /* 00184C89  mov ecx, dword ptr [esi] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi)));
    /* 00184C8B  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184C8C  lea ecx, ptr [esp+0x10] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00184C90  call 0x2709e0 */
    xb_push(c, 0x00184C95u); f_002709E0(c);
    /* 00184C95  mov eax, dword ptr [edi+0x2590] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->edi + 0x00002590u)));
    /* 00184C9B  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184C9D  jle 0x184dd9 */
    if ((zf || sf != of) && !tt_first_tile(c->eax)) goto L_00184DD9; /* changed: not for the Time Trial category's first tile */
    /* 00184CA3  mov edx, dword ptr [esi+0x28] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000028u)));
    /* 00184CA6  push 0x0 */
    { uint32_t v = 0x0u; xb_push(c, v); }
    /* 00184CA8  push 0x1 */
    { uint32_t v = 0x1u; xb_push(c, v); }
    /* 00184CAA  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00184CAB  lea eax, ptr [esp+0x1c] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x0000001Cu));
    /* 00184CAF  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184CB0  mov ecx, 0x5bd5e8 */
    c->ecx = (uint32_t)(0x5BD5E8u);
    /* 00184CB5  call 0x169270 */
    xb_push(c, 0x00184CBAu); f_00169270(c);
    /* 00184CBA  xor ecx, ecx */
    { uint32_t a = c->ecx, b = c->ecx, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 00184CBC  mov cx, word ptr [0x4afc84] */
    c->ecx = (c->ecx & 0xFFFF0000u) | (uint16_t)((uint32_t)xb_rd16((uint32_t)(0x004AFC84u)));
    /* 00184CC3  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184CC4  push 0x5bad28 */
    { uint32_t v = 0x5BAD28u; xb_push(c, v); }
    /* 00184CC9  lea ecx, ptr [esp+0x38] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000038u));
    /* 00184CCD  call 0x275380 */
    xb_push(c, 0x00184CD2u); f_00275380(c);
    /* 00184CD2  mov ecx, dword ptr [esp+0x10] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000010u)));
    /* 00184CD6  sub esp, 0x10 */
    { uint32_t a = c->esp, b = 0x10u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184CD9  mov edx, esp */
    c->edx = (uint32_t)(c->esp);
    /* 00184CDB  mov dword ptr [edx], ecx */
    xb_wr32((uint32_t)(c->edx), (uint32_t)(c->ecx));
    /* 00184CDD  mov ecx, dword ptr [esp+0x24] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000024u)));
    /* 00184CE1  mov dword ptr [edx+0x4], ecx */
    xb_wr32((uint32_t)(c->edx + 0x00000004u), (uint32_t)(c->ecx));
    /* 00184CE4  mov ecx, dword ptr [esp+0x28] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000028u)));
    /* 00184CE8  mov dword ptr [edx+0x8], ecx */
    xb_wr32((uint32_t)(c->edx + 0x00000008u), (uint32_t)(c->ecx));
    /* 00184CEB  mov ecx, dword ptr [esp+0x2c] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x0000002Cu)));
    /* 00184CEF  sub esp, 0x10 */
    { uint32_t a = c->esp, b = 0x10u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184CF2  mov dword ptr [edx+0xc], ecx */
    xb_wr32((uint32_t)(c->edx + 0x0000000Cu), (uint32_t)(c->ecx));
    /* 00184CF5  mov ecx, esp */
    c->ecx = (uint32_t)(c->esp);
    /* 00184CF7  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184CF8  call 0x275c00 */
    xb_push(c, 0x00184CFDu); f_00275C00(c);
    /* 00184CFD  lea edx, ptr [esp+0x40] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000040u));
    /* 00184D01  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00184D02  call 0x275c30 */
    xb_push(c, 0x00184D07u); f_00275C30(c);
    /* 00184D07  add esp, 0x24 */
    { uint32_t a = c->esp, b = 0x24u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184D0A  lea eax, ptr [esp+0x20] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00184D0E  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184D0F  lea ecx, ptr [edi+0x3ed0] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003ED0u));
    /* 00184D15  call 0x129bf0 */
    xb_push(c, 0x00184D1Au); f_00129BF0(c);
    /* 00184D1A  lea ecx, ptr [esp+0x20] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00184D1E  call 0x2753b0 */
    xb_push(c, 0x00184D23u); f_002753B0(c);
    /* 00184D23  lea ecx, ptr [esp+0x30] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000030u));
    /* 00184D27  call 0x2753b0 */
    xb_push(c, 0x00184D2Cu); f_002753B0(c);
    /* 00184D2C  lea ecx, ptr [esp+0x10] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00184D30  call 0x2753b0 */
    xb_push(c, 0x00184D35u); f_002753B0(c);
    /* 00184D35  lea ecx, ptr [edi+0x3e18] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003E18u));
    /* 00184D3B  call 0x975f0 */
    xb_push(c, 0x00184D40u); f_000975F0(c);
    /* 00184D40  mov ecx, dword ptr [esi+0x30] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000030u)));
    /* 00184D43  push 0x0 */
    { uint32_t v = 0x0u; xb_push(c, v); }
    /* 00184D45  push 0x1 */
    { uint32_t v = 0x1u; xb_push(c, v); }
    /* 00184D47  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184D48  lea edx, ptr [esp+0x1c] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x0000001Cu));
    /* 00184D4C  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00184D4D  mov ecx, 0x5bd5e8 */
    c->ecx = (uint32_t)(0x5BD5E8u);
    /* 00184D52  call 0x169270 */
    xb_push(c, 0x00184D57u); f_00169270(c);
    /* 00184D57  mov eax, dword ptr [esi+0x2c] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x0000002Cu)));
    /* 00184D5A  push 0x0 */
    { uint32_t v = 0x0u; xb_push(c, v); }
    /* 00184D5C  push 0x1 */
    { uint32_t v = 0x1u; xb_push(c, v); }
    /* 00184D5E  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184D5F  lea ecx, ptr [esp+0x2c] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000002Cu));
    /* 00184D63  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184D64  mov ecx, 0x5bd5e8 */
    c->ecx = (uint32_t)(0x5BD5E8u);
    /* 00184D69  call 0x169270 */
    xb_push(c, 0x00184D6Eu); f_00169270(c);
    /* 00184D6E  xor ecx, ecx */
    { uint32_t a = c->ecx, b = c->ecx, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 00184D70  mov cx, word ptr [0x4af810] */
    c->ecx = (c->ecx & 0xFFFF0000u) | (uint16_t)((uint32_t)xb_rd16((uint32_t)(0x004AF810u)));
    /* 00184D77  lea edx, ptr [esp+0x10] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00184D7B  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00184D7C  lea eax, ptr [esp+0x24] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000024u));
    /* 00184D80  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184D81  lea ebx, ptr [edi+0x3cc0] */
    c->ebx = (uint32_t)((uint32_t)(c->edi + 0x00003CC0u));
    /* 00184D87  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184D88  push 0x5bad28 */
    { uint32_t v = 0x5BAD28u; xb_push(c, v); }
    /* 00184D8D  lea ecx, ptr [esp+0x50] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000050u));
    /* 00184D91  call 0x275380 */
    xb_push(c, 0x00184D96u); f_00275380(c);
    /* 00184D96  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184D97  lea edx, ptr [esp+0x3c] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x0000003Cu));
    /* 00184D9B  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00184D9C  call 0x721f0 */
    xb_push(c, 0x00184DA1u); f_000721F0(c);
    /* 00184DA1  add esp, 0x10 */
    { uint32_t a = c->esp, b = 0x10u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184DA4  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184DA5  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 00184DA7  call 0x129bf0 */
    xb_push(c, 0x00184DACu); f_00129BF0(c);
    /* 00184DAC  lea ecx, ptr [esp+0x30] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000030u));
    /* 00184DB0  call 0x2753b0 */
    xb_push(c, 0x00184DB5u); f_002753B0(c);
    /* 00184DB5  lea ecx, ptr [esp+0x40] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000040u));
    /* 00184DB9  call 0x2753b0 */
    xb_push(c, 0x00184DBEu); f_002753B0(c);
    /* 00184DBE  lea ecx, ptr [esp+0x20] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00184DC2  call 0x2753b0 */
    xb_push(c, 0x00184DC7u); f_002753B0(c);
    /* 00184DC7  lea ecx, ptr [esp+0x10] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00184DCB  call 0x2753b0 */
    xb_push(c, 0x00184DD0u); f_002753B0(c);
    /* 00184DD0  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 00184DD2  call 0x975f0 */
    xb_push(c, 0x00184DD7u); f_000975F0(c);
    /* 00184DD7  jmp 0x184def */
    goto L_00184DEF;
L_00184DD9:;
    /* 00184DD9  lea ecx, ptr [edi+0x3e18] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003E18u));
    /* 00184DDF  call 0x97610 */
    xb_push(c, 0x00184DE4u); f_00097610(c);
    /* 00184DE4  lea ecx, ptr [edi+0x3cc0] */
    c->ecx = (uint32_t)((uint32_t)(c->edi + 0x00003CC0u));
    /* 00184DEA  call 0x97610 */
    xb_push(c, 0x00184DEFu); f_00097610(c);
L_00184DEF:;
    /* 00184DEF  mov eax, dword ptr [esi] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi)));
    /* 00184DF1  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184DF2  push 0x4b57e8 */
    { uint32_t v = 0x4B57E8u; xb_push(c, v); }
    /* 00184DF7  push 0x4b57dc */
    { uint32_t v = 0x4B57DCu; xb_push(c, v); }
    /* 00184DFC  lea ecx, ptr [esp+0x5c] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000005Cu));
    /* 00184E00  push 0x103 */
    { uint32_t v = 0x103u; xb_push(c, v); }
    /* 00184E05  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184E06  call 0x2f8202 */
    xb_push(c, 0x00184E0Bu); f_002F8202(c);
    /* 00184E0B  mov al, byte ptr [edi+0x2588] */
    c->eax = (c->eax & 0xFFFFFF00u) | (uint8_t)((uint32_t)xb_rd8((uint32_t)(c->edi + 0x00002588u)));
    /* 00184E11  add esp, 0x14 */
    { uint32_t a = c->esp, b = 0x14u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184E14  test al, al */
    { uint32_t a = (c->eax & 0xFFu), b = (c->eax & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 00184E16  mov byte ptr [esp+0x153], 0x0 */
    xb_wr8((uint32_t)(c->esp + 0x00000153u), (uint8_t)(0x0u));
    /* 00184E1E  jz 0x184e3d */
    if (zf) goto L_00184E3D;
    /* 00184E20  mov eax, dword ptr [edi+0x2590] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->edi + 0x00002590u)));
    /* 00184E26  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184E28  jl 0x184e3d */
    if ((sf != of)) goto L_00184E3D;
    /* 00184E2A  cmp eax, dword ptr [edi+0x2584] */
    { uint32_t a = c->eax, b = xb_rd32((uint32_t)(c->edi + 0x00002584u)), r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184E30  jnl 0x184e3d */
    if ((sf == of)) goto L_00184E3D;
    /* 00184E32  mov edx, dword ptr [edi+0x257c] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->edi + 0x0000257Cu)));
    /* 00184E38  mov eax, dword ptr [edx+eax*4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->edx + c->eax * 4)));
    /* 00184E3B  jmp 0x184e3f */
    goto L_00184E3F;
L_00184E3D:;
    /* 00184E3D  xor eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
L_00184E3F:;
    /* 00184E3F  movzx eax, byte ptr [eax+0x24] */
    c->eax = (uint32_t)((uint32_t)xb_rd8((uint32_t)(c->eax + 0x00000024u)));
    /* 00184E43  add edi, 0x1c18 */
    { uint32_t a = c->edi, b = 0x1C18u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edi = (uint32_t)(r); }
    /* 00184E49  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184E4A  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 00184E4C  call 0x15e110 */
    xb_push(c, 0x00184E51u); f_0015E110(c);
    /* 00184E51  push 0x0 */
    { uint32_t v = 0x0u; xb_push(c, v); }
    /* 00184E53  lea ecx, ptr [esp+0x54] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000054u));
    /* 00184E57  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184E58  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 00184E5A  call 0x15e240 */
    xb_push(c, 0x00184E5Fu); f_0015E240(c);
    /* 00184E5F  lea ecx, ptr [esp+0xc] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000000Cu));
    /* 00184E63  call 0x270690 */
    xb_push(c, 0x00184E68u); f_00270690(c);
    /* 00184E68  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 00184E69  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 00184E6A  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 00184E6B  add esp, 0x148 */
    { uint32_t a = c->esp, b = 0x148u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184E71  ret */
    c->esp += 4; return;
}
