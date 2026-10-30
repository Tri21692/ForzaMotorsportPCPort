/* XBRT_LIST_CHECK=1: a check for a crash with the Lamborghini Gallardo loaded.
 * sub_00271300 walks a list of objects (0x56F858, its count at 0x56F860)
 * and calls each one's first virtual function. With the Gallardo loaded
 * (in the garage, or its livery's decal editor opened) one entry was a block
 * the game had freed and reused: its first bytes were the path
 * "cars\LamborghiniGallardo\...", and the call went to 0. This logs every
 * free (sub_00059560) of a block still in that list: the block, its place
 * in the list, its first word and the return addresses on the stack, which
 * say who freed it.
 *
 * game_free is out/code_*.c's f_00059560 as it was generated: if the game is
 * recompiled again, copy it anew. */
#include <stdio.h>
#include <stdlib.h>

#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

static void game_free(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 00059560  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 00059561  mov esi, dword ptr [esp+0x8] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000008u)));
    /* 00059565  test esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00059567  jz 0x595ed */
    if (zf) goto L_000595ED;
    /* 0005956D  mov al, byte ptr [0x51843c] */
    c->eax = (c->eax & 0xFFFFFF00u) | (uint8_t)((uint32_t)xb_rd8((uint32_t)(0x0051843Cu)));
    /* 00059572  test al, al */
    { uint32_t a = (c->eax & 0xFFu), b = (c->eax & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 00059574  jz 0x595e0 */
    if (zf) goto L_000595E0;
    /* 00059576  call 0x593d0 */
    xb_push(c, 0x0005957Bu); f_000593D0(c);
    /* 0005957B  push 0x589324 */
    { uint32_t v = 0x589324u; xb_push(c, v); }
    /* 00059580  call dword ptr [0x485d84] */
    xb_push(c, 0x00059586u); xb_kernel(c, 277); /* RtlEnterCriticalSection */
    /* 00059586  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 00059588  sar ecx, 0x10 */
    { uint32_t a = c->ecx, n = 0x10u & 0x1Fu, r; if (n) { int64_t s = (int32_t)(a); r = (uint32_t)(s >> (n > 31 ? 31 : n)) & 0xFFFFFFFFu; cf = (uint32_t)(s >> (n - 1 > 31 ? 31 : n - 1)) & 1; of = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); } }
    /* 0005958B  mov eax, ecx */
    c->eax = (uint32_t)(c->ecx);
    /* 0005958D  shr eax, 0x5 */
    { uint32_t a = c->eax, n = 0x5u & 0x1Fu, r; if (n) { r = (uint32_t)((uint64_t)a >> n); cf = (uint32_t)((uint64_t)a >> (n - 1)) & 1; of = (a >> 31) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 00059590  mov edx, dword ptr [eax*4+0x589340] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->eax * 4 + 0x00589340u)));
    /* 00059597  and ecx, 0x1f */
    { uint32_t a = c->ecx, b = 0x1Fu, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 0005959A  shr edx, cl */
    { uint32_t a = c->edx, n = (c->ecx & 0xFFu) & 0x1Fu, r; if (n) { r = (uint32_t)((uint64_t)a >> n); cf = (uint32_t)((uint64_t)a >> (n - 1)) & 1; of = (a >> 31) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edx = (uint32_t)(r); } }
    /* 0005959C  test dl, 0x1 */
    { uint32_t a = (c->edx & 0xFFu), b = 0x1u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 0005959F  jz 0x595d0 */
    if (zf) goto L_000595D0;
    /* 000595A1  mov eax, esi */
    c->eax = (uint32_t)(c->esi);
    /* 000595A3  and eax, 0xfffff000 */
    { uint32_t a = c->eax, b = 0xFFFFF000u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 000595A8  push edi */
    { uint32_t v = c->edi; xb_push(c, v); }
    /* 000595A9  mov edi, dword ptr [eax+0xff8] */
    c->edi = (uint32_t)(xb_rd32((uint32_t)(c->eax + 0x00000FF8u)));
    /* 000595AF  call 0x593d0 */
    xb_push(c, 0x000595B4u); f_000593D0(c);
    /* 000595B4  mov ecx, eax */
    c->ecx = (uint32_t)(c->eax);
    /* 000595B6  lea eax, ptr [edi-0x1] */
    c->eax = (uint32_t)((uint32_t)(c->edi + 0xFFFFFFFFu));
    /* 000595B9  cdq */
    c->edx = (uint32_t)((int32_t)c->eax >> 31);
    /* 000595BA  and edx, 0x3 */
    { uint32_t a = c->edx, b = 0x3u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edx = (uint32_t)(r); }
    /* 000595BD  add eax, edx */
    { uint32_t a = c->eax, b = c->edx, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 000595BF  sar eax, 0x2 */
    { uint32_t a = c->eax, n = 0x2u & 0x1Fu, r; if (n) { int64_t s = (int32_t)(a); r = (uint32_t)(s >> (n > 31 ? 31 : n)) & 0xFFFFFFFFu; cf = (uint32_t)(s >> (n - 1 > 31 ? 31 : n - 1)) & 1; of = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 000595C2  imul eax, eax, 0x2c */
    { int64_t p = (int64_t)(int32_t)(c->eax) * (int64_t)(int32_t)(0x2Cu); uint32_t r = (uint32_t)p & 0xFFFFFFFFu; cf = of = p != (int64_t)(int32_t)(r); c->eax = (uint32_t)(r); }
    /* 000595C5  add ecx, eax */
    { uint32_t a = c->ecx, b = c->eax, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 000595C7  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 000595C8  call 0x27d100 */
    xb_push(c, 0x000595CDu); f_0027D100(c);
    /* 000595CD  xor esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
    /* 000595CF  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
L_000595D0:;
    /* 000595D0  call 0x593d0 */
    xb_push(c, 0x000595D5u); f_000593D0(c);
    /* 000595D5  push 0x589324 */
    { uint32_t v = 0x589324u; xb_push(c, v); }
    /* 000595DA  call dword ptr [0x485d88] */
    xb_push(c, 0x000595E0u); xb_kernel(c, 294); /* RtlLeaveCriticalSection */
L_000595E0:;
    /* 000595E0  test esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 000595E2  jz 0x595ed */
    if (zf) goto L_000595ED;
    /* 000595E4  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 000595E5  call 0x2f9a97 */
    xb_push(c, 0x000595EAu); f_002F9A97(c);
    /* 000595EA  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
L_000595ED:;
    /* 000595ED  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 000595EE  ret */
    c->esp += 4; return;
}


void f_00059560(XbCtx *c) {
    static int on = -1;
    if (on < 0) on = getenv("XBRT_LIST_CHECK") && atoi(getenv("XBRT_LIST_CHECK"));
    if (on) {
        uint32_t p = xb_rd32(c->esp + 4), list = xb_rd32(0x56F858), n = xb_rd32(0x56F860);
        if (p && list && n < 4096)
            for (uint32_t i = 0; i < n; i++)
                if (xb_rd32(list + 4 * i) == p) {
                    fprintf(stderr, "xbrt: list check: freed block %08x, entry %u of %u in 0x56F858's list, first word %08x; stack:", p, i, n, xb_rd32(p));
                    for (int k = 0; k < 48; k++) {
                        uint32_t v = xb_rd32(c->esp + 4 * k);
                        if (v >= 0x10000 && v < 0x400000) fprintf(stderr, " %08x", v);  /* the code's return addresses */
                    }
                    fprintf(stderr, "\n");
                    break;
                }
    }
    game_free(c);
}
