/* The game's list of growable arrays and its heap, made safer, with checks.
 *
 * sub_00271300 walks a list of array objects (0x56F858, its count at
 * 0x56F860, kept sorted by address: TArrays, which register themselves) and
 * calls each one's first virtual function, at every load (from 0xB0058) and
 * when malloc runs out. An entry that is no longer an object crashed it
 * (0x271279), and the heap's free hung. Seen with the Lamborghini Gallardo
 * loaded, the decal editor, and a category of 25 series. The cause was the
 * runtime's own XBRT_ZONE_LEAD (nv2a.c), which went on writing into the
 * track table after the game had freed it, over the list (found with
 * XBRT_LIST_GUARD). These fixes stay, for the game's own bug below.
 *
 * Fixed here, always on:
 * - sub_00271310 (take off the list) with an object not listed shifted the
 *   whole list down from place -1: the first entry went over the word before
 *   the list (the heap's header of its block) and off the list. Now nothing.
 * - sub_002714A0 (put on the list) added an object listed already again.
 * - A block freed through sub_00059560 first has the objects inside it taken
 *   off the list (sizes from the game's malloc, sub_000594D0).
 * - RtlFreeHeap (sub_0026A438) leaves alone a block that is free already:
 *   freed twice, it pointed at itself in the heap's free list, and the next
 *   free walked that list forever.
 *
 * XBRT_LIST_CHECK=1 logs each of those, with the return addresses on the
 * stack (who), the list's size each time it passes a multiple of 256, the
 * first time it is out of order, and each walk because malloc failed.
 * XBRT_LIST_GUARD=1 catches a write to the list from anywhere else (slow).
 * XBRT_HEAP_WALK=n checks the whole heap every n-th malloc or free.
 *
 * game_free, game_list, game_unlist and game_malloc are out/code_*.c's
 * f_00059560, f_002714A0, f_00271310 and f_000594D0 as they were generated
 * (game_list and game_unlist with the fixes): if the game is recompiled
 * again, copy them anew. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

static int check_on(void) {
    static int on = -1;
    if (on < 0) on = getenv("XBRT_LIST_CHECK") && atoi(getenv("XBRT_LIST_CHECK"));
    return on;
}

static void guard_open(void);
static void guard_close(void);

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


/* How often the fixes in game_list and game_unlist were needed (logged with XBRT_LIST_CHECK). */
static unsigned listed_twice, unlisted_none;

static void game_list(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    uint32_t obj = xb_rd32(c->esp + 4);
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
    /* Listed already: the game added it again, and one removal then left it listed after the
     * object was gone. Now it is listed once. */
    if ((int32_t)c->eax >= 0 && (int32_t)c->eax < (int32_t)xb_rd32(0x56F860) && xb_rd32(xb_rd32(0x56F858) + 4 * c->eax) == obj) {
        listed_twice++;
        { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
        xb_push(c, 0x00271512u); xb_kernel(c, 294); /* RtlLeaveCriticalSection */
        c->esp += 4; return;
    }
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
    /* Not listed: the game went on to shift the whole list down from place -1 (writing its first
     * entry over the word before the list, the heap's header of the list's block, and dropping
     * that entry from the list) and to count one less. Now nothing is changed. */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    unlisted_none++;
    goto L_unlist_none;
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
    if (0) {
L_unlist_none:;
        { uint32_t v = 0x5E5BC8u; xb_push(c, v); }
    }
    /* 002713B8  call dword ptr [0x485d88] */
    xb_push(c, 0x002713BEu); xb_kernel(c, 294); /* RtlLeaveCriticalSection */
    /* 002713BE  ret */
    c->esp += 4; return;
}


/* The game's heap (its allocations and RtlFreeHeap's), and the last frees from it, each with the
 * return addresses on the stack then (XBRT_LIST_CHECK). */
#define HEAP 0x10A0000u
#define FREES 65536
static struct { uint32_t p, from[8]; } frees[FREES];
static int nfrees;

static int link_ok(uint32_t a) { return a >= 0x10000 && a < 0x4000000 && (a & 7) == 0; }

/* The return addresses on the stack (the first 8). */
static void stack_of(XbCtx *c, uint32_t *from) {
    int k = 0;
    for (int j = 0; j < 48 && k < 8; j++) {
        uint32_t v = xb_rd32(c->esp + 4 * j);
        if (v >= 0x10000 && v < 0x400000) from[k++] = v;
    }
    while (k < 8) from[k++] = 0;
}

/* sub_000594D0 as generated (see game_free). */
static void game_malloc(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 000594D0  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 000594D1  mov ebx, dword ptr [esp+0x8] */
    c->ebx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000008u)));
    /* 000594D5  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 000594D6  call 0x59460 */
    xb_push(c, 0x000594DBu); f_00059460(c);
    /* 000594DB  mov edx, eax */
    c->edx = (uint32_t)(c->eax);
    /* 000594DD  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 000594E0  test edx, edx */
    { uint32_t a = c->edx, b = c->edx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 000594E2  jnz 0x5950d */
    if (!zf) goto L_0005950D;
    /* 000594E4  call 0x59360 */
    xb_push(c, 0x000594E9u); f_00059360(c);
    /* 000594E9  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 000594EA  call 0x59460 */
    xb_push(c, 0x000594EFu); f_00059460(c);
    /* 000594EF  mov edx, eax */
    c->edx = (uint32_t)(c->eax);
    /* 000594F1  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 000594F4  test edx, edx */
    { uint32_t a = c->edx, b = c->edx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 000594F6  jnz 0x5950d */
    if (!zf) goto L_0005950D;
    /* 000594F8  call 0x271300 */
    if (check_on()) {
        static int said;
        if (said++ < 200) {
            fprintf(stderr, "xbrt: list check: malloc(%x) failed, walking the list (%u listed), thread %08x; stack:", c->ebx, xb_rd32(0x56F860), rt_self ? rt_self->kthread : 0);
            log_stack(c);
        }
    }
    xb_push(c, 0x000594FDu); f_00271300(c);
    /* 000594FD  call 0x59360 */
    xb_push(c, 0x00059502u); f_00059360(c);
    /* 00059502  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 00059503  call 0x59460 */
    xb_push(c, 0x00059508u); f_00059460(c);
    /* 00059508  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 0005950B  mov edx, eax */
    c->edx = (uint32_t)(c->eax);
L_0005950D:;
    /* 0005950D  mov al, byte ptr [0x58b340] */
    c->eax = (c->eax & 0xFFFFFF00u) | (uint8_t)((uint32_t)xb_rd8((uint32_t)(0x0058B340u)));
    /* 00059512  test al, al */
    { uint32_t a = (c->eax & 0xFFu), b = (c->eax & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 00059514  jz 0x5954f */
    if (zf) goto L_0005954F;
    /* 00059516  test edx, edx */
    { uint32_t a = c->edx, b = c->edx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00059518  jz 0x5954f */
    if (zf) goto L_0005954F;
    /* 0005951A  test ebx, ebx */
    { uint32_t a = c->ebx, b = c->ebx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0005951C  jbe 0x5954f */
    if ((cf | zf)) goto L_0005954F;
    /* 0005951E  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 0005951F  mov esi, ebx */
    c->esi = (uint32_t)(c->ebx);
    /* 00059521  shr esi, 0x2 */
    { uint32_t a = c->esi, n = 0x2u & 0x1Fu, r; if (n) { r = (uint32_t)((uint64_t)a >> n); cf = (uint32_t)((uint64_t)a >> (n - 1)) & 1; of = (a >> 31) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); } }
    /* 00059524  test esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00059526  push edi */
    { uint32_t v = c->edi; xb_push(c, v); }
    /* 00059527  jbe 0x59534 */
    if ((cf | zf)) goto L_00059534;
    /* 00059529  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 0005952B  mov eax, 0xffbfffff */
    c->eax = (uint32_t)(0xFFBFFFFFu);
    /* 00059530  mov edi, edx */
    c->edi = (uint32_t)(c->edx);
    /* 00059532  rep stosd dword ptr [edi] */
    { uint32_t d = c->df ? (uint32_t)-4 : 4; while (c->ecx) { xb_wr32(c->edi, c->eax); c->edi += d; c->ecx--; } }
L_00059534:;
    /* 00059534  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 00059536  and ecx, 0x3 */
    { uint32_t a = c->ecx, b = 0x3u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 00059539  lea edi, ptr [edx+esi*4] */
    c->edi = (uint32_t)((uint32_t)(c->edx + c->esi * 4));
    /* 0005953C  mov esi, ecx */
    c->esi = (uint32_t)(c->ecx);
    /* 0005953E  shr ecx, 0x2 */
    { uint32_t a = c->ecx, n = 0x2u & 0x1Fu, r; if (n) { r = (uint32_t)((uint64_t)a >> n); cf = (uint32_t)((uint64_t)a >> (n - 1)) & 1; of = (a >> 31) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); } }
    /* 00059541  or eax, 0xffffffff */
    { uint32_t a = c->eax, b = 0xFFFFFFFFu, r; r = a | b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00059544  rep stosd dword ptr [edi] */
    { uint32_t d = c->df ? (uint32_t)-4 : 4; while (c->ecx) { xb_wr32(c->edi, c->eax); c->edi += d; c->ecx--; } }
    /* 00059546  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 00059548  and ecx, 0x3 */
    { uint32_t a = c->ecx, b = 0x3u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 0005954B  rep stosb byte ptr [edi] */
    { uint32_t d = c->df ? (uint32_t)-1 : 1; while (c->ecx) { xb_wr8(c->edi, (c->eax & 0xFFu)); c->edi += d; c->ecx--; } }
    /* 0005954D  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 0005954E  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
L_0005954F:;
    /* 0005954F  mov eax, edx */
    c->eax = (uint32_t)(c->edx);
    /* 00059551  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 00059552  ret */
    c->esp += 4; return;
}

/* Sizes of the blocks the game's malloc (sub_000594D0) handed out and that are not yet freed,
 * an open-addressed table keyed by address (1: a removed entry), so that a free can be checked
 * for lists of 0x56F858 inside the block, at any place in it. */
#define LIVE (1u << 21)
static uint32_t *live_at, *live_size, (*live_from)[4];

static uint32_t *live_slot(uint32_t p, int add) {
    if (!live_at) { live_at = calloc(LIVE, 4); live_size = calloc(LIVE, 4); live_from = calloc(LIVE, 16); }
    uint32_t i = (p >> 3) * 2654435761u & (LIVE - 1), *gap = 0;
    for (uint32_t k = 0; k < LIVE; k++, i = (i + 1) & (LIVE - 1)) {
        if (live_at[i] == p) return &live_at[i];
        if (live_at[i] == 1 && !gap) gap = &live_at[i];
        if (!live_at[i]) return add ? (gap ? gap : &live_at[i]) : 0;
    }
    return gap;
}

static void heap_walk_tick(XbCtx *c);

void f_000594D0(XbCtx *c) {
    uint32_t size = xb_rd32(c->esp + 4), from[4] = {0};
    for (int k = 0, j = 0; check_on() && k < 4; k++) {  /* the return addresses on the stack */
        uint32_t v = 0;
        while (j < 32 && !v) { v = xb_rd32(c->esp + 4 * j++); if (v < 0x10000 || v >= 0x400000) v = 0; }
        from[k] = v;
    }
    heap_walk_tick(c);
    game_malloc(c);
    if (c->eax) {
        uint32_t *s = live_slot(c->eax, 1);
        if (s) { *s = c->eax; live_size[s - live_at] = size; memcpy(live_from[s - live_at], from, 16); }
    }
}

/* XBRT_HEAP_WALK=n: every n-th malloc or free through sub_000594D0 / sub_00059560, the whole
 * heap at 0x10A0000 is checked: each segment's blocks from its first one to its last valid one
 * (by the 8-byte headers: size and previous size in 16-byte units, segment index, flags: 1 in use,
 * 0x10 the last before an uncommitted range), each block's previous size against the one before
 * it, and each free block's list links (its first two words) against its neighbours'. The first
 * fault is logged once, with the block before it: its size as malloc was asked for it and who
 * asked (a write past its end), or who last freed the faulty block (a write after a free). */
static void heap_fault(XbCtx *c, const char *what, uint32_t e, uint32_t before) {
    static int told;
    static uint32_t seen;  /* the same block twice running: not a change in progress on another thread */
    if (told || !what || e != seen) { seen = e; return; }
    told = 1;
    fprintf(stderr, "xbrt: heap walk: %s at block %08x (header %08x %08x, words %08x %08x), block before %08x; seen from", what, e,
            xb_rd32(e), xb_rd32(e + 4), xb_rd32(e + 8), xb_rd32(e + 12), before);
    log_stack(c);
    uint32_t *at = before ? live_slot(before + 16, 0) : 0;
    if (at) fprintf(stderr, "xbrt: heap walk: block before: %08x, %x bytes asked for, from %08x %08x %08x %08x\n", before + 16,
                    live_size[at - live_at], live_from[at - live_at][0], live_from[at - live_at][1], live_from[at - live_at][2], live_from[at - live_at][3]);
    else if (before) fprintf(stderr, "xbrt: heap walk: block before: %08x, not from malloc (or freed)\n", before + 16);
    for (int k = 0; k < FREES; k++)
        if (frees[k].p && frees[k].p >= e && frees[k].p <= e + 0x10) {
            fprintf(stderr, "xbrt: heap walk: %08x was freed from", frees[k].p);
            for (int j = 0; j < 8 && frees[k].from[j]; j++) fprintf(stderr, " %08x", frees[k].from[j]);
            fprintf(stderr, "\n");
        }
    fflush(stderr);
}

static void heap_walk(XbCtx *c) {
    heap_fault(c, 0, 0, 0);  /* (forgets a fault seen once that is gone) */
    for (int si = 0; si < 64; si++) {
        uint32_t seg = xb_rd32(HEAP + 0x60 + 4 * si);
        if (!seg) continue;
        uint32_t e = xb_rd32(seg + 0x28), last = xb_rd32(seg + 0x2C), before = 0, ranges = xb_rd32(seg + 0x38);
        for (int n = 0; e && e < last && n < 1000000; n++) {
            uint32_t size = xb_rd16(e), prev = xb_rd16(e + 2);
            uint8_t idx = xb_rd8(e + 4), fl = xb_rd8(e + 5);
            if (!size || idx != si || (before && prev != xb_rd16(before))) { heap_fault(c, "bad header", e, before); return; }
            if (!(fl & 1)) {
                uint32_t f = xb_rd32(e + 8), b = xb_rd32(e + 12);
                if (!link_ok(f) || !link_ok(b) || xb_rd32(f + 4) != e + 8 || xb_rd32(b) != e + 8) { heap_fault(c, "bad free links", e, before); return; }
            }
            if (fl & 0x10) {  /* uncommitted bytes follow: the range that starts at the block's end */
                uint32_t end = e + size * 16, r = ranges, next = 0;
                for (int k = 0; r && k < 4096; k++, r = xb_rd32(r))
                    if (xb_rd32(r + 4) == end) { next = end + xb_rd32(r + 8); break; }
                e = next, before = 0;
                continue;
            }
            before = e;
            e += size * 16;
        }
    }
}

static void heap_walk_tick(XbCtx *c) {
    static int every = -1, n;
    if (every < 0) every = getenv("XBRT_HEAP_WALK") ? atoi(getenv("XBRT_HEAP_WALK")) : 0;
    if (every > 0 && ++n >= every) n = 0, heap_walk(c);
}

/* Who added each object to 0x56F858's list: the return addresses, by the object's address. */
#define ADDS (1u << 16)
static struct { uint32_t obj, from[8]; } adds[ADDS];

/* Takes off 0x56F858's list every object in the block from p (size bytes) that is about to be
 * freed. The list's walk (sub_00271300, at every load and whenever memory runs short) calls a
 * function of each object listed: one in freed memory called whatever was there next (a crash at
 * 0x271279), or wrote into the heap's own links (a hang in the heap's free). Found with a 25th
 * series in a category and with the Lamborghini Gallardo loaded: objects freed while listed. */
static void unlist_inside(XbCtx *c, uint32_t p, uint32_t size) {
    for (int tries = 0; tries < 4096; tries++) {
        uint32_t list = xb_rd32(0x56F858), n = xb_rd32(0x56F860), lo = 0, hi = n;
        if (!list || n >= 0x100000) return;
        while (lo < hi) { uint32_t m = (lo + hi) / 2; if (xb_rd32(list + 4 * m) < p) lo = m + 1; else hi = m; }
        uint32_t e = lo < n ? xb_rd32(list + 4 * lo) : 0;
        if (lo >= n || e < p || e >= p + size) return;
        if (check_on()) {
            fprintf(stderr, "xbrt: list check: freed block %08x (%x bytes) holds entry %u of %u in 0x56F858's list at +%x, first word %08x; stack:", p, size, lo, n, e - p, xb_rd32(e));
            log_stack(c);
            uint32_t i = (e >> 2) * 2654435761u & (ADDS - 1);
            if (adds[i].obj == e) {
                fprintf(stderr, "xbrt: list check: %08x was added from", e);
                for (int k = 0; k < 8 && adds[i].from[k]; k++) fprintf(stderr, " %08x", adds[i].from[k]);
                fprintf(stderr, "\n");
            }
        }
        xb_push(c, e);
        xb_push(c, 0);  /* (a return address game_unlist only pops) */
        guard_open();
        game_unlist(c);
        guard_close();
        c->esp += 4;
        if (xb_rd32(0x56F860) == n) return;  /* nothing came off: not listed after all */
    }
}

void f_00059560(XbCtx *c) {
    heap_walk_tick(c);
    uint32_t p = xb_rd32(c->esp + 4);
    uint32_t *at = p ? live_slot(p, 0) : 0, size = at ? live_size[at - live_at] : 0;
    if (at) *at = 1;
    if (p) unlist_inside(c, p, size ? size : 1);
    game_free(c);
}

/* XBRT_LIST_CHECK: the first time 0x56F858's list is found out of order after an add or a
 * removal (the game's binary search then misses objects that are listed), with what was done. */
static void check_sorted(XbCtx *c, const char *what, uint32_t obj, uint32_t n_before) {
    static int said;
    uint32_t list = xb_rd32(0x56F858), n = xb_rd32(0x56F860);
    if (said >= 5 || !list || n >= 0x100000) return;
    for (uint32_t i = 0; i + 1 < n; i++) {
        if (xb_rd32(list + 4 * i) < xb_rd32(list + 4 * i + 4)) continue;
        said++;
        fprintf(stderr, "xbrt: list check: out of order after %s %08x (%u -> %u listed), thread %08x: [%u] %08x [%u] %08x; around:", what, obj, n_before, n,
                rt_self ? rt_self->kthread : 0, i, xb_rd32(list + 4 * i), i + 1, xb_rd32(list + 4 * i + 4));
        for (uint32_t k = i > 3 ? i - 3 : 0; k < i + 5 && k < n; k++) fprintf(stderr, " %08x", xb_rd32(list + 4 * k));
        fprintf(stderr, "; stack:");
        log_stack(c);
        return;
    }
}

void f_002714A0(XbCtx *c) {
    static uint32_t most = 255;
    uint32_t obj = xb_rd32(c->esp + 4);
    if (check_on()) {
        uint32_t i = (obj >> 2) * 2654435761u & (ADDS - 1);
        adds[i].obj = obj;
        stack_of(c, adds[i].from);
    }
    if (check_on() && xb_rd32(0x56F860) > most) {
        most = xb_rd32(0x56F860) | 255;
        fprintf(stderr, "xbrt: list check: 0x56F858's list at %u, adding %08x (first word %08x); stack:", xb_rd32(0x56F860), obj, xb_rd32(obj));
        log_stack(c);
    }
    uint32_t n = xb_rd32(0x56F860);
    guard_open();
    game_list(c);
    guard_close();
    if (check_on()) check_sorted(c, "adding", obj, n);
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
    guard_open();
    game_unlist(c);
    guard_close();
    if (on) check_sorted(c, "removing", obj, n);
    if (on && n && xb_rd32(0x56F860) == n)
        fprintf(stderr, "xbrt: list check: removing %08x removed nothing (%u listed)\n", obj, n);
}

/* RtlFreeHeap (sub_0026A438: heap, flags, block; it calls sub_0026C6D2) as generated, with every
 * free from the heap at 0x10A0000 put in the history of frees (XBRT_LIST_CHECK) and a block that
 * is free already left alone: freed again, it went into the heap's list of free blocks a second
 * time, pointing at itself, and the next free that walked that list never came out of it (the
 * hang after a race of a category's 25th series was quit). Logged with XBRT_LIST_CHECK, with who
 * freed it before. */
void f_0026A438(XbCtx *c) {
    uint32_t heap = xb_rd32(c->esp + 4), p = xb_rd32(c->esp + 12);
    if (heap == HEAP && p) {
        int on = check_on();
        if (!(xb_rd8(p - 11) & 1)) {  /* its header: the 16 bytes before it, flags at +5 (1: in use) */
            static int said;
            if (on && said++ < 20) {
                fprintf(stderr, "xbrt: list check: block %08x freed again (header %08x %08x); stack:", p, xb_rd32(p - 16), xb_rd32(p - 12));
                log_stack(c);
                for (int k = 0; k < FREES; k++)
                    if (frees[k].p == p) {
                        fprintf(stderr, "xbrt: list check: %08x was freed before from", p);
                        for (int j = 0; j < 8 && frees[k].from[j]; j++) fprintf(stderr, " %08x", frees[k].from[j]);
                        fprintf(stderr, "\n");
                    }
            }
            c->eax = 1;
            c->esp += 16;
            return;
        }
        if (on) {
            int k = nfrees++ % FREES;
            frees[k].p = p;
            stack_of(c, frees[k].from);
        }
    }
    /* 0026A438  push dword ptr [esp+0xc] (three times: the arguments again) */
    for (int k = 0; k < 3; k++) xb_push(c, xb_rd32(c->esp + 12));
    /* 0026A444  call 0x26c6d2 */
    xb_push(c, 0x0026A449u); f_0026C6D2(c);
    /* 0026A449  movzx eax, al */
    c->eax &= 0xFF;
    /* 0026A44C  ret 0xc */
    c->esp += 16;
}

/* XBRT_LIST_GUARD=1 (Windows): 0x56F858's list kept read-only, so that a write to it from anywhere
 * but the game's add and removal (with the list's lock) is caught as it happens and logged, with
 * the guest's return addresses and the host code that wrote. Writes to the rest of a guarded page
 * (other heap blocks) go ahead, one instruction at a time. */
#ifdef _WIN32
#include <windows.h>

static int guard_on = -1, guard_in_op;
static uint32_t guard_lo, guard_hi;  /* the list, as guarded now */
static __thread uint32_t guard_step;  /* a page this thread opened for one instruction */

static void guard_protect(DWORD how) {
    if (guard_hi <= guard_lo) return;
    uint32_t a = guard_lo & ~0xFFFu, e = (guard_hi + 0xFFFu) & ~0xFFFu;
    DWORD old;
    VirtualProtect(xb_mem + a, e - a, how, &old);
}

static void guard_set(void) {
    guard_protect(PAGE_READWRITE);
    uint32_t list = xb_rd32(0x56F858), cap = xb_rd32(0x56F85C) & 0x7FFFFFFFu;
    guard_lo = list, guard_hi = list && cap < 0x100000 ? list + 4 * cap : list;
    guard_protect(PAGE_READONLY);
}

static LONG CALLBACK guard_fault(EXCEPTION_POINTERS *e) {
    EXCEPTION_RECORD *r = e->ExceptionRecord;
    if (r->ExceptionCode == EXCEPTION_SINGLE_STEP && guard_step) {
        uint32_t a = guard_step;
        guard_step = 0;
        uint32_t list = xb_rd32(0x56F858);
        if (list != guard_lo) {  /* the list was made smaller or bigger by its own walk: guard where it is now */
            guard_set();
            return EXCEPTION_CONTINUE_EXECUTION;
        }
        if (a >= list && a < list + 4 * xb_rd32(0x56F860)) {
            static int said;
            if (said++ < 20) {
                HMODULE exe = GetModuleHandleA(NULL);
                fprintf(stderr, "xbrt: list guard: %08x (entry %u) written with %08x, not by the list's code, thread %08x, host forza.exe+%llx; stack:",
                        a, (a - guard_lo) / 4, xb_rd32(a & ~3u), rt_self ? rt_self->kthread : 0,
                        (unsigned long long)((uint8_t *)r->ExceptionAddress - (uint8_t *)exe));
                if (rt_self) log_stack(&rt_self->ctx); else fprintf(stderr, "\n");
                fflush(stderr);
            }
        }
        guard_protect(PAGE_READONLY);
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (r->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || r->NumberParameters < 2 || r->ExceptionInformation[0] != 1)
        return EXCEPTION_CONTINUE_SEARCH;
    uint8_t *p = (uint8_t *)r->ExceptionInformation[1];
    if (guard_hi <= guard_lo || p < xb_mem + (guard_lo & ~0xFFFu) || p >= xb_mem + ((guard_hi + 0xFFFu) & ~0xFFFu))
        return EXCEPTION_CONTINUE_SEARCH;
    guard_step = (uint32_t)(p - xb_mem);
    guard_protect(PAGE_READWRITE);
    e->ContextRecord->EFlags |= 0x100;  /* trap after this one instruction */
    return EXCEPTION_CONTINUE_EXECUTION;
}

static int guard_enabled(void) {
    if (guard_on < 0) {
        guard_on = getenv("XBRT_LIST_GUARD") && atoi(getenv("XBRT_LIST_GUARD"));
        if (guard_on) AddVectoredExceptionHandler(1, guard_fault);
    }
    return guard_on;
}

/* Around the game's own changes to the list. */
static void guard_open(void) {
    if (guard_enabled() && !guard_in_op++) guard_protect(PAGE_READWRITE);
}
static void guard_close(void) {
    if (guard_on > 0 && !--guard_in_op) guard_set();
}

/* A host read (ReadFile) into guest memory on a guarded page fails rather than faulting. */
void rt_list_guard_pause(int pause) {
    if (guard_on <= 0) return;
    if (pause) guard_protect(PAGE_READWRITE); else if (!guard_in_op) guard_protect(PAGE_READONLY);
}
#else
static void guard_open(void) {}
static void guard_close(void) {}
void rt_list_guard_pause(int pause) { (void)pause; }
#endif
