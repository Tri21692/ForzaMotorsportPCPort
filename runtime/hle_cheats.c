/* Profile-name cheats: the game's own, and one more. Named "nOsLiW" a new
 * career's profile gets 900,000,000 experience (level 50) and every car and
 * track; named "tEAm4za", 900,000,000 credits. sub_00364970 compares the
 * profile's name with those two (0x4AC344, 0x4AC33C) and sets the flags at
 * 0x5BAA8D-0x5BAA90 that the career's start (0x36CE5C) reads.
 *
 * Named "D3bUg", a new career's profile gets 999,999,999 credits and level
 * 50 (PlayerLevelDef.xml's last level, 8,000,000 experience), and nothing
 * else: no unlocks. The name is put in .rdata nothing uses (0x4D02B0 on,
 * after nv2a.c's TimeTrial at 0x4D02C0) and compared after the other two;
 * the career's start then sets the credits it starts with (sub_00078D40,
 * returning to 0x36CE6F) to that, and the experience (sub_00078E30) with
 * them. The profile is the game's to save: nothing is written to a save.
 *
 * The rest is out/code_0042.c's f_00364970 and out/code_0009.c's f_00078D40
 * as they were generated: if the game is recompiled again, copy them anew
 * and keep the changes, marked. */
#include "funcs.h"
#include "rt.h"

#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"

static const char D3BUG[] = "D3bUg";
#define D3BUG_AT 0x4D02E0u
#define D3BUG_CREDITS 999999999u
#define D3BUG_XP 8000000u  /* level 50 */

static int rt_d3bug;

void f_00364970(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    rt_d3bug = 0;  /* changed */
    for (unsigned i = 0; i < sizeof D3BUG; i++) xb_wr8(D3BUG_AT + i, (uint8_t)D3BUG[i]);  /* changed */
    /* 00364970  mov ecx, dword ptr [esp+0x4] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000004u)));
    /* 00364974  sub esp, 0x368 */
    { uint32_t a = c->esp, b = 0x368u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 0036497A  test ecx, ecx */
    { uint32_t a = c->ecx, b = c->ecx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0036497C  mov byte ptr [0x5baa8d], 0x0 */
    xb_wr8((uint32_t)(0x005BAA8Du), (uint8_t)(0x0u));
    /* 00364983  mov byte ptr [0x5baa8e], 0x0 */
    xb_wr8((uint32_t)(0x005BAA8Eu), (uint8_t)(0x0u));
    /* 0036498A  mov byte ptr [0x5baa8f], 0x0 */
    xb_wr8((uint32_t)(0x005BAA8Fu), (uint8_t)(0x0u));
    /* 00364991  mov byte ptr [0x5baa90], 0x0 */
    xb_wr8((uint32_t)(0x005BAA90u), (uint8_t)(0x0u));
    /* 00364998  jz 0x364a6a */
    if (zf) goto L_00364A6A;
    /* 0036499E  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 0036499F  lea eax, ptr [esp+0x14] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000014u));
    /* 003649A3  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 003649A4  lea edx, ptr [esp+0x28] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000028u));
    /* 003649A8  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 003649A9  call 0x77810 */
    xb_push(c, 0x003649AEu); f_00077810(c);
    /* 003649AE  mov ecx, eax */
    c->ecx = (uint32_t)(c->eax);
    /* 003649B0  call 0x7b080 */
    xb_push(c, 0x003649B5u); f_0007B080(c);
    /* 003649B5  push 0x4ac344 */
    { uint32_t v = 0x4AC344u; xb_push(c, v); }
    /* 003649BA  lea ecx, ptr [esp+0x8] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000008u));
    /* 003649BE  call 0x275bd0 */
    xb_push(c, 0x003649C3u); f_00275BD0(c);
    /* 003649C3  lea eax, ptr [esp+0x4] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 003649C7  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 003649C8  lea ecx, ptr [esp+0x18] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000018u));
    /* 003649CC  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 003649CD  call 0x2754d0 */
    xb_push(c, 0x003649D2u); f_002754D0(c);
    /* 003649D2  add esp, 0x8 */
    { uint32_t a = c->esp, b = 0x8u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 003649D5  mov ebx, eax */
    c->ebx = (uint32_t)(c->eax);
    /* 003649D7  neg ebx */
    { uint32_t a = c->ebx, r; r = (0u - a) & 0xFFFFFFFFu; cf = a != 0; of = a == 0x80000000u; af = (a & 0xF) != 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 003649D9  sbb bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = (a - b - cf) & 0xFFu; { uint32_t c0 = cf; cf = c0 ? a <= b : a < b; } of = (((a ^ b) & (a ^ r)) >> 7) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 003649DB  lea ecx, ptr [esp+0x4] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 003649DF  inc bl */
    { uint32_t a = (c->ebx & 0xFFu), r; r = (a + 1) & 0xFFu; of = r == 0x80u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 003649E1  call 0x2753b0 */
    xb_push(c, 0x003649E6u); f_002753B0(c);
    /* 003649E6  test bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 003649E8  jz 0x364a07 */
    if (zf) goto L_00364A07;
    /* 003649EA  mov al, 0x1 */
    c->eax = (c->eax & 0xFFFFFF00u) | (uint8_t)(0x1u);
    /* 003649EC  lea ecx, ptr [esp+0x14] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000014u));
    /* 003649F0  mov byte ptr [0x5baa8d], al */
    xb_wr8((uint32_t)(0x005BAA8Du), (uint8_t)((c->eax & 0xFFu)));
    /* 003649F5  mov byte ptr [0x5baa8e], al */
    xb_wr8((uint32_t)(0x005BAA8Eu), (uint8_t)((c->eax & 0xFFu)));
    /* 003649FA  call 0x2753b0 */
    xb_push(c, 0x003649FFu); f_002753B0(c);
    /* 003649FF  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 00364A00  add esp, 0x368 */
    { uint32_t a = c->esp, b = 0x368u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00364A06  ret */
    c->esp += 4; return;
L_00364A07:;
    /* 00364A07  push 0x4ac33c */
    { uint32_t v = 0x4AC33Cu; xb_push(c, v); }
    /* 00364A0C  lea ecx, ptr [esp+0x8] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000008u));
    /* 00364A10  call 0x275bd0 */
    xb_push(c, 0x00364A15u); f_00275BD0(c);
    /* 00364A15  lea edx, ptr [esp+0x4] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 00364A19  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00364A1A  lea eax, ptr [esp+0x18] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000018u));
    /* 00364A1E  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00364A1F  call 0x2754d0 */
    xb_push(c, 0x00364A24u); f_002754D0(c);
    /* 00364A24  add esp, 0x8 */
    { uint32_t a = c->esp, b = 0x8u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00364A27  mov ebx, eax */
    c->ebx = (uint32_t)(c->eax);
    /* 00364A29  neg ebx */
    { uint32_t a = c->ebx, r; r = (0u - a) & 0xFFFFFFFFu; cf = a != 0; of = a == 0x80000000u; af = (a & 0xF) != 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 00364A2B  sbb bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = (a - b - cf) & 0xFFu; { uint32_t c0 = cf; cf = c0 ? a <= b : a < b; } of = (((a ^ b) & (a ^ r)) >> 7) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00364A2D  lea ecx, ptr [esp+0x4] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 00364A31  inc bl */
    { uint32_t a = (c->ebx & 0xFFu), r; r = (a + 1) & 0xFFu; of = r == 0x80u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00364A33  call 0x2753b0 */
    xb_push(c, 0x00364A38u); f_002753B0(c);
    /* 00364A38  test bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 00364A3A  jz 0x364a59 */
    if (zf) goto L_00364A59;
    /* 00364A3C  mov al, 0x1 */
    c->eax = (c->eax & 0xFFFFFF00u) | (uint8_t)(0x1u);
    /* 00364A3E  lea ecx, ptr [esp+0x14] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000014u));
    /* 00364A42  mov byte ptr [0x5baa8d], al */
    xb_wr8((uint32_t)(0x005BAA8Du), (uint8_t)((c->eax & 0xFFu)));
    /* 00364A47  mov byte ptr [0x5baa8f], al */
    xb_wr8((uint32_t)(0x005BAA8Fu), (uint8_t)((c->eax & 0xFFu)));
    /* 00364A4C  call 0x2753b0 */
    xb_push(c, 0x00364A51u); f_002753B0(c);
    /* 00364A51  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 00364A52  add esp, 0x368 */
    { uint32_t a = c->esp, b = 0x368u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00364A58  ret */
    c->esp += 4; return;
L_00364A59:;
    /* changed: the name compared with "D3bUg" as with "tEAm4za" above */
    { uint32_t v = D3BUG_AT; xb_push(c, v); }
    /* 00364A0C  lea ecx, ptr [esp+0x8] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000008u));
    /* 00364A10  call 0x275bd0 */
    xb_push(c, 0x00364A15u); f_00275BD0(c);
    /* 00364A15  lea edx, ptr [esp+0x4] */
    c->edx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 00364A19  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 00364A1A  lea eax, ptr [esp+0x18] */
    c->eax = (uint32_t)((uint32_t)(c->esp + 0x00000018u));
    /* 00364A1E  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00364A1F  call 0x2754d0 */
    xb_push(c, 0x00364A24u); f_002754D0(c);
    /* 00364A24  add esp, 0x8 */
    { uint32_t a = c->esp, b = 0x8u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00364A27  mov ebx, eax */
    c->ebx = (uint32_t)(c->eax);
    /* 00364A29  neg ebx */
    { uint32_t a = c->ebx, r; r = (0u - a) & 0xFFFFFFFFu; cf = a != 0; of = a == 0x80000000u; af = (a & 0xF) != 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 00364A2B  sbb bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = (a - b - cf) & 0xFFu; { uint32_t c0 = cf; cf = c0 ? a <= b : a < b; } of = (((a ^ b) & (a ^ r)) >> 7) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00364A2D  lea ecx, ptr [esp+0x4] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000004u));
    /* 00364A31  inc bl */
    { uint32_t a = (c->ebx & 0xFFu), r; r = (a + 1) & 0xFFu; of = r == 0x80u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00364A33  call 0x2753b0 */
    xb_push(c, 0x00364A38u); f_002753B0(c);
    /* 00364A38  test bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    rt_d3bug = (c->ebx & 0xFFu) != 0;  /* changed: its result kept for set_credits below */
    /* 00364A59  lea ecx, ptr [esp+0x14] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000014u));
    /* 00364A5D  mov byte ptr [0x5baa8d], 0x0 */
    xb_wr8((uint32_t)(0x005BAA8Du), (uint8_t)(0x0u));
    /* 00364A64  call 0x2753b0 */
    xb_push(c, 0x00364A69u); f_002753B0(c);
    /* 00364A69  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
L_00364A6A:;
    /* 00364A6A  add esp, 0x368 */
    { uint32_t a = c->esp, b = 0x368u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00364A70  ret */
    c->esp += 4; return;
}


static void set_credits(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 00078D40  mov eax, dword ptr [esp+0x4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000004u)));
    /* 00078D44  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00078D46  jnbe 0x78d53 */
    if ((!cf && !zf)) goto L_00078D53;
    /* 00078D48  xor eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00078D4A  mov dword ptr [ecx+0x3d4], eax */
    xb_wr32((uint32_t)(c->ecx + 0x000003D4u), (uint32_t)(c->eax));
    /* 00078D50  ret 0x4 */
    c->esp += 8; return;
L_00078D53:;
    /* 00078D53  cmp eax, 0x7fffffff */
    { uint32_t a = c->eax, b = 0x7FFFFFFFu, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00078D58  jb 0x78d5f */
    if (cf) goto L_00078D5F;
    /* 00078D5A  mov eax, 0x7fffffff */
    c->eax = (uint32_t)(0x7FFFFFFFu);
L_00078D5F:;
    /* 00078D5F  mov dword ptr [ecx+0x3d4], eax */
    xb_wr32((uint32_t)(c->ecx + 0x000003D4u), (uint32_t)(c->eax));
    /* 00078D65  ret 0x4 */
    c->esp += 8; return;
}


void f_00078D40(XbCtx *c) {
    if (rt_d3bug && xb_rd32(c->esp) == 0x0036CE6Fu) {  /* the career's start, its credits */
        uint32_t profile = c->ecx;
        xb_wr32(c->esp + 4, D3BUG_CREDITS);
        set_credits(c);
        c->ecx = profile;
        xb_push(c, D3BUG_XP);
        xb_push(c, 0x0036CE6Fu); f_00078E30(c);
        return;
    }
    set_credits(c);
}
