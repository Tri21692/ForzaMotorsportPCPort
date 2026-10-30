/* XBRT_LIST_CHECK=1: checks for a crash with the Lamborghini Gallardo loaded.
 * sub_00271300 walks a list of objects (0x56F858, its count at 0x56F860:
 * streams, by what they count, kept sorted by address) and calls each one's
 * first virtual function. With the Gallardo loaded (its livery's decal
 * editor opened) one entry was not an object: once its first bytes were the
 * path "cars\LamborghiniGallardo\...", once 0xF5, entry 3,889 of the list;
 * the call went to 0. Another time the game hung in the heap's free.
 *
 * Logged: every free (sub_00059560) of a block still in that list, with its
 * place in the list and its first word; the list's size each time it passes
 * a new multiple of 256, with who added to it (sub_002714A0); and every
 * removal (sub_00271310) of an object not listed once, or that removed
 * nothing. Each with the return addresses on the stack, which say who.
 *
 * game_free, game_list and game_unlist are out/code_*.c's f_00059560,
 * f_002714A0 and f_00271310 as they were generated: if the game is
 * recompiled again, copy them anew. */
#include <stdio.h>
#include <stdlib.h>

#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

static int check_on(void) {
    static int on = -1;
    if (on < 0) on = getenv("XBRT_LIST_CHECK") && atoi(getenv("XBRT_LIST_CHECK"));
    return on;
}

static void log_stack(XbCtx *c) {
    for (int k = 0; k < 48; k++) {
        uint32_t v = xb_rd32(c->esp + 4 * k);
        if (v >= 0x10000 && v < 0x400000) fprintf(stderr, " %08x", v);  /* the code's return addresses */
    }
    fprintf(stderr, "\n");
}

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


static void game_list(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 002714A0  test byte ptr [0x5e5be4], 0x1 */
    { uint32_t a = (uint32_t)xb_rd8((uint32_t)(0x005E5BE4u)), b = 0x1u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 002714A7  jnz 0x2714ce */
    if (!zf) goto L_002714CE;
    /* 002714A9  mov eax, dword ptr [0x5e5be4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(0x005E5BE4u)));
    /* 002714AE  or eax, 0x1 */
    { uint32_t a = c->eax, b = 0x1u, r; r = a | b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 002714B1  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 002714B6  mov dword ptr [0x5e5be4], eax */
    xb_wr32((uint32_t)(0x005E5BE4u), (uint32_t)(c->eax));
    /* 002714BB  call dword ptr [0x485d80] */
    xb_push(c, 0x002714C1u); xb_kernel(c, 291); /* RtlInitializeCriticalSection */
    /* 002714C1  push 0x30a5b0 */
    { uint32_t v = 0x30A5B0u; xb_push(c, v); }
    /* 002714C6  call 0x2f8f34 */
    xb_push(c, 0x002714CBu); f_002F8F34(c);
    /* 002714CB  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
L_002714CE:;
    /* 002714CE  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 002714D3  call dword ptr [0x485d84] */
    xb_push(c, 0x002714D9u); xb_kernel(c, 277); /* RtlEnterCriticalSection */
    /* 002714D9  mov eax, dword ptr [esp+0x4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000004u)));
    /* 002714DD  lea ecx, ptr [esp+0x4] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 002714E1  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 002714E2  mov ecx, 0x56f854 */
    c->ecx = (uint32_t)(0x56F854u);
    /* 002714E7  mov dword ptr [esp+0x8], eax */
    xb_wr32((uint32_t)(c->esp + 0x00000008u), (uint32_t)(c->eax));
    /* 002714EB  call 0x271110 */
    xb_push(c, 0x002714F0u); f_00271110(c);
    /* 002714F0  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 002714F1  lea edx, ptr [esp+0x8] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000008u));
    /* 002714F5  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 002714F6  mov ecx, 0x56f854 */
    c->ecx = (uint32_t)(0x56F854u);
    /* 002714FB  call 0x2713f0 */
    xb_push(c, 0x00271500u); f_002713F0(c);
    /* 00271500  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 00271505  mov byte ptr [0x5e5bc5], 0x1 */
    xb_wr8((uint32_t)(0x005E5BC5u), (uint8_t)(0x1u));
    /* 0027150C  call dword ptr [0x485d88] */
    xb_push(c, 0x00271512u); xb_kernel(c, 294); /* RtlLeaveCriticalSection */
    /* 00271512  ret */
    c->esp += 4; return;
}


static void game_unlist(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 00271310  test byte ptr [0x5e5be4], 0x1 */
    { uint32_t a = (uint32_t)xb_rd8((uint32_t)(0x005E5BE4u)), b = 0x1u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 00271317  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 00271318  jnz 0x271341 */
    if (!zf) goto L_00271341;
    /* 0027131A  mov esi, dword ptr [0x5e5be4] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(0x005E5BE4u)));
    /* 00271320  or esi, 0x1 */
    { uint32_t a = c->esi, b = 0x1u, r; r = a | b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
    /* 00271323  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 00271328  mov dword ptr [0x5e5be4], esi */
    xb_wr32((uint32_t)(0x005E5BE4u), (uint32_t)(c->esi));
    /* 0027132E  call dword ptr [0x485d80] */
    xb_push(c, 0x00271334u); xb_kernel(c, 291); /* RtlInitializeCriticalSection */
    /* 00271334  push 0x30a5b0 */
    { uint32_t v = 0x30A5B0u; xb_push(c, v); }
    /* 00271339  call 0x2f8f34 */
    xb_push(c, 0x0027133Eu); f_002F8F34(c);
    /* 0027133E  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
L_00271341:;
    /* 00271341  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 00271346  call dword ptr [0x485d84] */
    xb_push(c, 0x0027134Cu); xb_kernel(c, 277); /* RtlEnterCriticalSection */
    /* 0027134C  mov esi, dword ptr [esp+0x8] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000008u)));
    /* 00271350  lea eax, ptr [esp+0x8] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000008u));
    /* 00271354  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00271355  mov ecx, 0x56f854 */
    c->ecx = (uint32_t)(0x56F854u);
    /* 0027135A  mov dword ptr [esp+0xc], esi */
    xb_wr32((uint32_t)(c->esp + 0x0000000Cu), (uint32_t)(c->esi));
    /* 0027135E  call 0x271110 */
    xb_push(c, 0x00271363u); f_00271110(c);
    /* 00271363  mov ecx, dword ptr [0x56f860] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(0x0056F860u)));
    /* 00271369  cmp eax, ecx */
    { uint32_t a = c->eax, b = c->ecx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0027136B  mov edx, dword ptr [0x56f858] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(0x0056F858u)));
    /* 00271371  jnl 0x271378 */
    if ((sf == of)) goto L_00271378;
    /* 00271373  cmp esi, dword ptr [edx+eax*4] */
    { uint32_t a = c->esi, b = xb_rd32((uint32_t)(c->edx + c->eax * 4)), r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00271376  jz 0x27137b */
    if (zf) goto L_0027137B;
L_00271378:;
    /* 00271378  or eax, 0xffffffff */
    { uint32_t a = c->eax, b = 0xFFFFFFFFu, r; r = a | b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
L_0027137B:;
    /* 0027137B  lea esi, ptr [ecx-0x1] */
    c->esi = (uint32_t)((uint32_t)(c->ecx + 0xFFFFFFFFu));
    /* 0027137E  cmp eax, esi */
    { uint32_t a = c->eax, b = c->esi, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00271380  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 00271381  jnl 0x2713a5 */
    if ((sf == of)) goto L_002713A5;
    /* 00271383  jmp 0x271390 */
    goto L_00271390;
L_00271385:;
    /* 00271385  mov edx, dword ptr [0x56f858] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(0x0056F858u)));
    /* 0027138B  jmp 0x271390 */
    goto L_00271390;
L_00271390:;
    /* 00271390  mov ecx, dword ptr [edx+eax*4+0x4] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->edx + c->eax * 4 + 0x00000004u)));
    /* 00271394  mov dword ptr [edx+eax*4], ecx */
    xb_wr32((uint32_t)(c->edx + c->eax * 4), (uint32_t)(c->ecx));
    /* 00271397  mov ecx, dword ptr [0x56f860] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(0x0056F860u)));
    /* 0027139D  inc eax */
    { uint32_t a = c->eax, r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 0027139E  lea edx, ptr [ecx-0x1] */
    c->edx = (uint32_t)((uint32_t)(c->ecx + 0xFFFFFFFFu));
    /* 002713A1  cmp eax, edx */
    { uint32_t a = c->eax, b = c->edx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 002713A3  jl 0x271385 */
    if ((sf != of)) { XB_LOOP(); goto L_00271385; }
L_002713A5:;
    /* 002713A5  dec ecx */
    { uint32_t a = c->ecx, r; r = (a - 1) & 0xFFFFFFFFu; of = a == 0x80000000u; af = (a & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 002713A6  push 0x5e5bc8 */
    { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    /* 002713AB  mov dword ptr [0x56f860], ecx */
    xb_wr32((uint32_t)(0x0056F860u), (uint32_t)(c->ecx));
    /* 002713B1  mov byte ptr [0x5e5bc5], 0x1 */
    xb_wr8((uint32_t)(0x005E5BC5u), (uint8_t)(0x1u));
    /* 002713B8  call dword ptr [0x485d88] */
    xb_push(c, 0x002713BEu); xb_kernel(c, 294); /* RtlLeaveCriticalSection */
    /* 002713BE  ret */
    c->esp += 4; return;
}


void f_00059560(XbCtx *c) {
    if (check_on()) {
        uint32_t p = xb_rd32(c->esp + 4), list = xb_rd32(0x56F858), n = xb_rd32(0x56F860);
        if (p && list && n < 0x100000)
            for (uint32_t i = 0; i < n; i++)
                if (xb_rd32(list + 4 * i) == p) {
                    fprintf(stderr, "xbrt: list check: freed block %08x, entry %u of %u in 0x56F858's list, first word %08x; stack:", p, i, n, xb_rd32(p));
                    log_stack(c);
                    break;
                }
    }
    game_free(c);
}

void f_002714A0(XbCtx *c) {
    static uint32_t most = 255;
    uint32_t obj = xb_rd32(c->esp + 4);
    if (check_on() && xb_rd32(0x56F860) > most) {
        most = xb_rd32(0x56F860) | 255;
        fprintf(stderr, "xbrt: list check: 0x56F858's list at %u, adding %08x (first word %08x); stack:", xb_rd32(0x56F860), obj, xb_rd32(obj));
        log_stack(c);
    }
    game_list(c);
}

void f_00271310(XbCtx *c) {
    int on = check_on();
    uint32_t obj = xb_rd32(c->esp + 4), n = xb_rd32(0x56F860), list = xb_rd32(0x56F858);
    if (on && list) {
        int seen = 0;
        for (uint32_t i = 0; i < n && i < 0x100000; i++) seen += xb_rd32(list + 4 * i) == obj;
        if (seen != 1) {
            fprintf(stderr, "xbrt: list check: removing %08x, listed %d times in %u (first word %08x); stack:", obj, seen, n, xb_rd32(obj));
            log_stack(c);
        }
    }
    game_unlist(c);
    if (on && n && xb_rd32(0x56F860) == n)
        fprintf(stderr, "xbrt: list check: removing %08x removed nothing (%u listed)\n", obj, n);
}
