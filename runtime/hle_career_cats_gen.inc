/* f_00184F30: 2 table addresses made cat_base()/cat_end(), the item kind its icon */
void f_00184F30(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 00184F30  sub esp, 0x24 */
    { uint32_t a = c->esp, b = 0x24u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184F33  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 00184F34  push ebp */
    { uint32_t v = c->ebp; xb_push(c, v); }
    /* 00184F35  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 00184F36  mov esi, ecx */
    c->esi = (uint32_t)(c->ecx);
    /* 00184F38  push edi */
    { uint32_t v = c->edi; xb_push(c, v); }
    /* 00184F39  mov dword ptr [esp+0x24], esi */
    xb_wr32((uint32_t)(c->esp + 0x00000024u), (uint32_t)(c->esi));
    /* 00184F3D  call 0x50270 */
    xb_push(c, 0x00184F42u); f_00050270(c);
    /* 00184F42  add esi, 0x2550 */
    { uint32_t a = c->esi, b = 0x2550u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
    /* 00184F48  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 00184F4A  call 0x1fa550 */
    xb_push(c, 0x00184F4Fu); f_001FA550(c);
    /* 00184F4F  test dword ptr [esi+0x8], 0x7fffffff */
    { uint32_t a = xb_rd32((uint32_t)(c->esi + 0x00000008u)), b = 0x7FFFFFFFu, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184F56  jz 0x184f8b */
    if (zf) goto L_00184F8B;
    /* 00184F58  mov eax, dword ptr [esi+0x4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000004u)));
    /* 00184F5B  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184F5D  mov dword ptr [esi+0x4], 0x0 */
    xb_wr32((uint32_t)(c->esi + 0x00000004u), (uint32_t)(0x0u));
    /* 00184F64  jz 0x184f6f */
    if (zf) goto L_00184F6F;
    /* 00184F66  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00184F67  call 0x59560 */
    xb_push(c, 0x00184F6Cu); f_00059560(c);
    /* 00184F6C  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
L_00184F6F:;
    /* 00184F6F  mov edi, dword ptr [esi+0x8] */
    c->edi = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000008u)));
    /* 00184F72  mov ecx, dword ptr [esi+0xc] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x0000000Cu)));
    /* 00184F75  and edi, 0x80000000 */
    { uint32_t a = c->edi, b = 0x80000000u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edi = (uint32_t)(r); }
    /* 00184F7B  mov eax, edi */
    c->eax = (uint32_t)(c->edi);
    /* 00184F7D  add eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00184F7F  sar eax, 0x1 */
    { uint32_t a = c->eax, n = 0x1u & 0x1Fu, r; if (n) { int64_t s = (int32_t)(a); r = (uint32_t)(s >> (n > 31 ? 31 : n)) & 0xFFFFFFFFu; cf = (uint32_t)(s >> (n - 1 > 31 ? 31 : n - 1)) & 1; of = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 00184F81  cmp ecx, eax */
    { uint32_t a = c->ecx, b = c->eax, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184F83  mov dword ptr [esi+0x8], edi */
    xb_wr32((uint32_t)(c->esi + 0x00000008u), (uint32_t)(c->edi));
    /* 00184F86  jle 0x184f8b */
    if ((zf || sf != of)) goto L_00184F8B;
    /* 00184F88  mov dword ptr [esi+0xc], eax */
    xb_wr32((uint32_t)(c->esi + 0x0000000Cu), (uint32_t)(c->eax));
L_00184F8B:;
    /* 00184F8B  mov ebp, 0x52e850 */
    c->ebp = (uint32_t)(cat_base());
L_00184F90:;
    /* 00184F90  mov ecx, dword ptr [ebp] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->ebp)));
    /* 00184F93  mov eax, dword ptr [ebp+0x4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebp + 0x00000004u)));
    /* 00184F96  push 0x4a7194 */
    { uint32_t v = 0x4A7194u; xb_push(c, v); }
    /* 00184F9B  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00184F9C  mov dword ptr [esp+0x34], eax */
    xb_wr32((uint32_t)(c->esp + 0x00000034u), (uint32_t)(c->eax));
    /* 00184FA0  mov edi, 0x1 */
    c->edi = (uint32_t)(0x1u);
    /* 00184FA5  call 0x2f97e5 */
    xb_push(c, 0x00184FAAu); f_002F97E5(c);
    /* 00184FAA  add esp, 0x8 */
    { uint32_t a = c->esp, b = 0x8u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00184FAD  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00184FAF  jnz 0x184fca */
    if (!zf) goto L_00184FCA;
    /* 00184FB1  call 0xcf090 */
    xb_push(c, 0x00184FB6u); f_000CF090(c);
    /* 00184FB6  mov edx, dword ptr [eax] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->eax)));
    /* 00184FB8  mov ecx, eax */
    c->ecx = (uint32_t)(c->eax);
    /* 00184FBA  call dword ptr [edx+0x1c] */
    { uint32_t t = xb_rd32((uint32_t)(c->edx + 0x0000001Cu)); xb_push(c, 0x00184FBDu); xb_call_indirect(c, t); }
    /* 00184FBD  mov ebx, eax */
    c->ebx = (uint32_t)(c->eax);
    /* 00184FBF  neg ebx */
    { uint32_t a = c->ebx, r; r = (0u - a) & 0xFFFFFFFFu; cf = a != 0; of = a == 0x80000000u; af = (a & 0xF) != 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 00184FC1  sbb bl, bl */
    { uint32_t a = (c->ebx & 0xFFu), b = (c->ebx & 0xFFu), r; r = (a - b - cf) & 0xFFu; { uint32_t c0 = cf; cf = c0 ? a <= b : a < b; } of = (((a ^ b) & (a ^ r)) >> 7) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00184FC3  inc bl */
    { uint32_t a = (c->ebx & 0xFFu), r; r = (a + 1) & 0xFFu; of = r == 0x80u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)(r); }
    /* 00184FC5  jmp 0x185114 */
    goto L_00185114;
L_00184FCA:;
    /* 00184FCA  mov ecx, 0x58e2a0 */
    c->ecx = (uint32_t)(0x58E2A0u);
    /* 00184FCF  mov byte ptr [esp+0x13], 0x1 */
    xb_wr8((uint32_t)(c->esp + 0x00000013u), (uint8_t)(0x1u));
    /* 00184FD4  mov dword ptr [esp+0x30], 0x0 */
    xb_wr32((uint32_t)(c->esp + 0x00000030u), (uint32_t)(0x0u));
    /* 00184FDC  call 0x77ac0 */
    xb_push(c, 0x00184FE1u); f_00077AC0(c);
    /* 00184FE1  mov esi, eax */
    c->esi = (uint32_t)(c->eax);
    /* 00184FE3  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 00184FE5  mov dword ptr [esp+0x20], esi */
    xb_wr32((uint32_t)(c->esp + 0x00000020u), (uint32_t)(c->esi));
    /* 00184FE9  call 0x78080 */
    xb_push(c, 0x00184FEEu); f_00078080(c);
    /* 00184FEE  push 0x4b57f8 */
    { uint32_t v = 0x4B57F8u; xb_push(c, v); }
    /* 00184FF3  lea ecx, ptr [esp+0x20] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00184FF7  mov dword ptr [esp+0x2c], eax */
    xb_wr32((uint32_t)(c->esp + 0x0000002Cu), (uint32_t)(c->eax));
    /* 00184FFB  call 0x270d00 */
    xb_push(c, 0x00185000u); f_00270D00(c);
    /* 00185000  mov eax, dword ptr [ebp] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebp)));
    /* 00185003  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185004  lea ecx, ptr [esp+0x20] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00185008  call 0x2709e0 */
    xb_push(c, 0x0018500Du); f_002709E0(c);
    /* 0018500D  lea ecx, ptr [esp+0x1c] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000001Cu));
    /* 00185011  call 0x2702d0 */
    xb_push(c, 0x00185016u); f_002702D0(c);
    /* 00185016  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185017  call 0x7e960 */
    xb_push(c, 0x0018501Cu); f_0007E960(c);
    /* 0018501C  mov ebx, eax */
    c->ebx = (uint32_t)(c->eax);
    /* 0018501E  xor eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00185020  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00185023  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 00185025  mov dword ptr [esp+0x18], eax */
    xb_wr32((uint32_t)(c->esp + 0x00000018u), (uint32_t)(c->eax));
    /* 00185029  mov dword ptr [esp+0x14], eax */
    xb_wr32((uint32_t)(c->esp + 0x00000014u), (uint32_t)(c->eax));
    /* 0018502D  call 0x22c480 */
    xb_push(c, 0x00185032u); f_0022C480(c);
    /* 00185032  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185034  jbe 0x1850d3 */
    if ((cf | zf)) goto L_001850D3;
    /* 0018503A  lea ebx, ptr [ebx] */
    c->ebx = (uint32_t)((uint32_t)(c->ebx));
L_00185040:;
    /* 00185040  mov ecx, dword ptr [esp+0x14] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000014u)));
    /* 00185044  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00185045  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 00185047  call 0x7c9e0 */
    xb_push(c, 0x0018504Cu); f_0007C9E0(c);
    /* 0018504C  mov edx, dword ptr [esp+0x28] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000028u)));
    /* 00185050  mov esi, eax */
    c->esi = (uint32_t)(c->eax);
    /* 00185052  mov eax, dword ptr [ebp+0x28] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebp + 0x00000028u)));
    /* 00185055  mov ecx, dword ptr [esi+0x544] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000544u)));
    /* 0018505B  cmp eax, ecx */
    { uint32_t a = c->eax, b = c->ecx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0018505D  cmovnb eax, ecx */
    if (!cf) { c->eax = (uint32_t)(c->ecx); }
    /* 00185060  mov dword ptr [ebp+0x28], eax */
    xb_wr32((uint32_t)(c->ebp + 0x00000028u), (uint32_t)(c->eax));
    /* 00185063  cmp edx, dword ptr [esi+0x544] */
    { uint32_t a = c->edx, b = xb_rd32((uint32_t)(c->esi + 0x00000544u)), r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185069  jb 0x185078 */
    if (cf) goto L_00185078;
    /* 0018506B  mov byte ptr [esp+0x13], 0x0 */
    xb_wr8((uint32_t)(c->esp + 0x00000013u), (uint8_t)(0x0u));
    /* 00185070  mov dword ptr [esp+0x30], 0x1 */
    xb_wr32((uint32_t)(c->esp + 0x00000030u), (uint32_t)(0x1u));
L_00185078:;
    /* 00185078  xor edi, edi */
    { uint32_t a = c->edi, b = c->edi, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edi = (uint32_t)(r); }
    /* 0018507A  lea ebx, ptr [ebx] */
    c->ebx = (uint32_t)((uint32_t)(c->ebx));
L_00185080:;
    /* 00185080  mov ecx, dword ptr [esi+0x758] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000758u)));
    /* 00185086  test ecx, ecx */
    { uint32_t a = c->ecx, b = c->ecx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185088  jz 0x1850b3 */
    if (zf) goto L_001850B3;
    /* 0018508A  mov eax, dword ptr [esi+0x75c] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x0000075Cu)));
    /* 00185090  sub eax, ecx */
    { uint32_t a = c->eax, b = c->ecx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00185092  sar eax, 0x2 */
    { uint32_t a = c->eax, n = 0x2u & 0x1Fu, r; if (n) { int64_t s = (int32_t)(a); r = (uint32_t)(s >> (n > 31 ? 31 : n)) & 0xFFFFFFFFu; cf = (uint32_t)(s >> (n - 1 > 31 ? 31 : n - 1)) & 1; of = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 00185095  cmp edi, eax */
    { uint32_t a = c->edi, b = c->eax, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185097  jnb 0x1850b3 */
    if (!cf) goto L_001850B3;
    /* 00185099  mov eax, ecx */
    c->eax = (uint32_t)(c->ecx);
    /* 0018509B  mov ecx, dword ptr [eax+edi*4] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->eax + c->edi * 4)));
    /* 0018509E  lea eax, ptr [eax+edi*4] */
    c->eax = (uint32_t)((uint32_t)(c->eax + c->edi * 4));
    /* 001850A1  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 001850A2  mov ecx, dword ptr [esp+0x24] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000024u)));
    /* 001850A6  call 0x783b0 */
    xb_push(c, 0x001850ABu); f_000783B0(c);
    /* 001850AB  cmp eax, 0x3 */
    { uint32_t a = c->eax, b = 0x3u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001850AE  jnbe 0x1850b7 */
    if ((!cf && !zf)) goto L_001850B7;
    /* 001850B0  inc edi */
    { uint32_t a = c->edi, r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edi = (uint32_t)(r); }
    /* 001850B1  jmp 0x185080 */
    { XB_LOOP(); goto L_00185080; }
L_001850B3:;
    /* 001850B3  inc dword ptr [esp+0x18] */
    { uint32_t a = xb_rd32((uint32_t)(c->esp + 0x00000018u)), r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); xb_wr32((uint32_t)(c->esp + 0x00000018u), (uint32_t)(r)); }
L_001850B7:;
    /* 001850B7  mov esi, dword ptr [esp+0x14] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000014u)));
    /* 001850BB  inc esi */
    { uint32_t a = c->esi, r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
    /* 001850BC  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 001850BE  mov dword ptr [esp+0x14], esi */
    xb_wr32((uint32_t)(c->esp + 0x00000014u), (uint32_t)(c->esi));
    /* 001850C2  call 0x22c480 */
    xb_push(c, 0x001850C7u); f_0022C480(c);
    /* 001850C7  cmp esi, eax */
    { uint32_t a = c->esi, b = c->eax, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001850C9  jb 0x185040 */
    if (cf) { XB_LOOP(); goto L_00185040; }
    /* 001850CF  mov esi, dword ptr [esp+0x20] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000020u)));
L_001850D3:;
    /* 001850D3  mov edx, dword ptr [esp+0x18] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000018u)));
    /* 001850D7  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 001850D9  mov dword ptr [ebp+0x2c], edx */
    xb_wr32((uint32_t)(c->ebp + 0x0000002Cu), (uint32_t)(c->edx));
    /* 001850DC  call 0x22c480 */
    xb_push(c, 0x001850E1u); f_0022C480(c);
    /* 001850E1  test ebx, ebx */
    { uint32_t a = c->ebx, b = c->ebx, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001850E3  mov dword ptr [ebp+0x30], eax */
    xb_wr32((uint32_t)(c->ebp + 0x00000030u), (uint32_t)(c->eax));
    /* 001850E6  jz 0x1850f8 */
    if (zf) goto L_001850F8;
    /* 001850E8  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 001850EA  call 0x7e7f0 */
    xb_push(c, 0x001850EFu); f_0007E7F0(c);
    /* 001850EF  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 001850F0  call 0x59560 */
    xb_push(c, 0x001850F5u); f_00059560(c);
    /* 001850F5  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
L_001850F8:;
    /* 001850F8  test esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001850FA  jz 0x185103 */
    if (zf) goto L_00185103;
    /* 001850FC  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 001850FE  call 0x777f0 */
    xb_push(c, 0x00185103u); f_000777F0(c);
L_00185103:;
    /* 00185103  lea ecx, ptr [esp+0x1c] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000001Cu));
    /* 00185107  call 0x270690 */
    xb_push(c, 0x0018510Cu); f_00270690(c);
    /* 0018510C  mov edi, dword ptr [esp+0x30] */
    c->edi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000030u)));
    /* 00185110  mov bl, byte ptr [esp+0x13] */
    c->ebx = (c->ebx & 0xFFFFFF00u) | (uint8_t)((uint32_t)xb_rd8((uint32_t)(c->esp + 0x00000013u)));
L_00185114:;
    /* 00185114  push 0x34 */
    { uint32_t v = 0x34u; xb_push(c, v); }
    /* 00185116  call 0x594d0 */
    xb_push(c, 0x0018511Bu); f_000594D0(c);
    /* 0018511B  mov esi, eax */
    c->esi = (uint32_t)(c->eax);
    /* 0018511D  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00185120  test esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185122  jz 0x18515e */
    if (zf) goto L_0018515E;
    /* 00185124  lea eax, ptr [ebp+0x8] */
    c->eax = (uint32_t)((uint32_t)(c->ebp + 0x00000008u));
    /* 00185127  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185128  lea ecx, ptr [esi+0x4] */
    c->ecx = (uint32_t)((uint32_t)(c->esi + 0x00000004u));
    /* 0018512B  mov dword ptr [esi], 0x49d998 */
    xb_wr32((uint32_t)(c->esi), (uint32_t)(0x49D998u));
    /* 00185131  call 0x275c00 */
    xb_push(c, 0x00185136u); f_00275C00(c);
    /* 00185136  lea ecx, ptr [ebp+0x18] */
    c->ecx = (uint32_t)((uint32_t)(c->ebp + 0x00000018u));
    /* 00185139  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 0018513A  lea ecx, ptr [esi+0x14] */
    c->ecx = (uint32_t)((uint32_t)(c->esi + 0x00000014u));
    /* 0018513D  call 0x275c00 */
    xb_push(c, 0x00185142u); f_00275C00(c);
    /* 00185142  mov edx, dword ptr [esp+0x2c] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x0000002Cu)));
    /* 00185146  mov byte ptr [esi+0x24], bl */
    xb_wr8((uint32_t)(c->esi + 0x00000024u), (uint8_t)((c->ebx & 0xFFu)));
    /* 00185149  mov dword ptr [esi], 0x49da98 */
    xb_wr32((uint32_t)(c->esi), (uint32_t)(0x49DA98u));
    /* 0018514F  mov dword ptr [esi+0x30], 0xffffffff */
    xb_wr32((uint32_t)(c->esi + 0x00000030u), (uint32_t)(0xFFFFFFFFu));
    /* 00185156  mov dword ptr [esi+0x28], edx */
    xb_wr32((uint32_t)(c->esi + 0x00000028u), (uint32_t)(c->edx));
    xb_wr32((uint32_t)(c->esi + 0x28u), cat_frame(c->ebp, c->edx)); /* changed: the icon */
    /* 00185159  mov dword ptr [esi+0x2c], edi */
    xb_wr32((uint32_t)(c->esi + 0x0000002Cu), (uint32_t)(c->edi));
    /* 0018515C  jmp 0x185160 */
    goto L_00185160;
L_0018515E:;
    /* 0018515E  xor esi, esi */
    { uint32_t a = c->esi, b = c->esi, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esi = (uint32_t)(r); }
L_00185160:;
    /* 00185160  mov ebx, dword ptr [esp+0x24] */
    c->ebx = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000024u)));
    /* 00185164  mov eax, dword ptr [ebx+0x2558] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebx + 0x00002558u)));
    /* 0018516A  mov ecx, dword ptr [ebx+0x255c] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->ebx + 0x0000255Cu)));
    /* 00185170  add ebx, 0x2550 */
    { uint32_t a = c->ebx, b = 0x2550u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 00185176  shl eax, 0x1 */
    { uint32_t a = c->eax, n = 0x1u & 0x1Fu, r; if (n) { uint64_t w = (uint64_t)a << n; r = (uint32_t)w & 0xFFFFFFFFu; cf = (uint32_t)(w >> 32) & 1; of = ((r >> 31) & 1) ^ cf; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 00185178  inc ecx */
    { uint32_t a = c->ecx, r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ecx = (uint32_t)(r); }
    /* 00185179  sar eax, 0x1 */
    { uint32_t a = c->eax, n = 0x1u & 0x1Fu, r; if (n) { int64_t s = (int32_t)(a); r = (uint32_t)(s >> (n > 31 ? 31 : n)) & 0xFFFFFFFFu; cf = (uint32_t)(s >> (n - 1 > 31 ? 31 : n - 1)) & 1; of = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); } }
    /* 0018517B  cmp eax, ecx */
    { uint32_t a = c->eax, b = c->ecx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0018517D  jnl 0x185190 */
    if ((sf == of)) goto L_00185190;
    /* 0018517F  add eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 00185181  cmp ecx, eax */
    { uint32_t a = c->ecx, b = c->eax, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185183  jnl 0x185188 */
    if ((sf == of)) goto L_00185188;
    /* 00185185  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185186  jmp 0x185189 */
    goto L_00185189;
L_00185188:;
    /* 00185188  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
L_00185189:;
    /* 00185189  mov ecx, ebx */
    c->ecx = (uint32_t)(c->ebx);
    /* 0018518B  call 0x7c8f0 */
    xb_push(c, 0x00185190u); f_0007C8F0(c);
L_00185190:;
    /* 00185190  mov eax, dword ptr [ebx+0xc] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebx + 0x0000000Cu)));
    /* 00185193  mov ecx, dword ptr [ebx+0x4] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->ebx + 0x00000004u)));
    /* 00185196  mov dword ptr [ecx+eax*4], esi */
    xb_wr32((uint32_t)(c->ecx + c->eax * 4), (uint32_t)(c->esi));
    /* 00185199  mov edx, dword ptr [ebx+0xc] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->ebx + 0x0000000Cu)));
    /* 0018519C  inc edx */
    { uint32_t a = c->edx, r; r = (a + 1) & 0xFFFFFFFFu; of = r == 0x80000000u; af = (r & 0xF) == 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edx = (uint32_t)(r); }
    /* 0018519D  add ebp, 0x34 */
    { uint32_t a = c->ebp, b = 0x34u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebp = (uint32_t)(r); }
    /* 001851A0  cmp ebp, 0x52e988 */
    { uint32_t a = c->ebp, b = cat_end(), r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001851A6  mov dword ptr [ebx+0xc], edx */
    xb_wr32((uint32_t)(c->ebx + 0x0000000Cu), (uint32_t)(c->edx));
    /* 001851A9  jl 0x184f90 */
    if ((sf != of)) { XB_LOOP(); goto L_00184F90; }
    /* 001851AF  mov esi, dword ptr [esp+0x24] */
    c->esi = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x00000024u)));
    /* 001851B3  push 0x0 */
    { uint32_t v = 0x0u; xb_push(c, v); }
    /* 001851B5  push 0x2 */
    { uint32_t v = 0x2u; xb_push(c, v); }
    /* 001851B7  lea ecx, ptr [esi+0x2470] */
    c->ecx = (uint32_t)((uint32_t)(c->esi + 0x00002470u));
    /* 001851BD  call 0x1935e0 */
    xb_push(c, 0x001851C2u); f_001935E0(c);
    /* 001851C2  mov edx, dword ptr [esi-0x28] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0xFFFFFFD8u)));
    /* 001851C5  lea ecx, ptr [esi-0x28] */
    c->ecx = (uint32_t)((uint32_t)(c->esi + 0xFFFFFFD8u));
    /* 001851C8  call dword ptr [edx+0x7c] */
    { uint32_t t = xb_rd32((uint32_t)(c->edx + 0x0000007Cu)); xb_push(c, 0x001851CBu); xb_call_indirect(c, t); }
    /* 001851CB  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 001851CC  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 001851CD  pop ebp */
    { uint32_t v = xb_pop(c); c->ebp = (uint32_t)(v); }
    /* 001851CE  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 001851CF  add esp, 0x24 */
    { uint32_t a = c->esp, b = 0x24u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 001851D2  ret */
    c->esp += 4; return;
}

/* f_001856B0: 2 table addresses made cat_base()/cat_end() */
void f_001856B0(XbCtx *c) {
    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;
    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;
    /* 001856B0  sub esp, 0x14 */
    { uint32_t a = c->esp, b = 0x14u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 001856B3  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 001856B4  xor ebx, ebx */
    { uint32_t a = c->ebx, b = c->ebx, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->ebx = (uint32_t)(r); }
    /* 001856B6  mov dword ptr [esp+0x4], ebx */
    xb_wr32((uint32_t)(c->esp + 0x00000004u), (uint32_t)(c->ebx));
    /* 001856BA  mov eax, dword ptr [esp+0x1c] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esp + 0x0000001Cu)));
    /* 001856BE  sub eax, ebx */
    { uint32_t a = c->eax, b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 001856C0  push esi */
    { uint32_t v = c->esi; xb_push(c, v); }
    /* 001856C1  push edi */
    { uint32_t v = c->edi; xb_push(c, v); }
    /* 001856C2  mov esi, ecx */
    c->esi = (uint32_t)(c->ecx);
    /* 001856C4  jz 0x185724 */
    if (zf) goto L_00185724;
    /* 001856C6  sub eax, 0x2 */
    { uint32_t a = c->eax, b = 0x2u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
    /* 001856C9  jnz 0x18589a */
    if (!zf) goto L_0018589A;
    /* 001856CF  mov ecx, dword ptr [0x5bd7bc] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(0x005BD7BCu)));
    /* 001856D5  cmp ecx, ebx */
    { uint32_t a = c->ecx, b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001856D7  jz 0x1856de */
    if (zf) goto L_001856DE;
    /* 001856D9  mov edi, dword ptr [ecx+0x24] */
    c->edi = (uint32_t)(xb_rd32((uint32_t)(c->ecx + 0x00000024u)));
    /* 001856DC  jmp 0x1856e4 */
    goto L_001856E4;
L_001856DE:;
    /* 001856DE  mov eax, dword ptr [esi+0x28] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000028u)));
    /* 001856E1  mov edi, dword ptr [eax+0x24] */
    c->edi = (uint32_t)(xb_rd32((uint32_t)(c->eax + 0x00000024u)));
L_001856E4:;
    /* 001856E4  cmp ecx, ebx */
    { uint32_t a = c->ecx, b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001856E6  jz 0x1856ee */
    if (zf) goto L_001856EE;
    /* 001856E8  mov edx, dword ptr [ecx] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->ecx)));
    /* 001856EA  push 0x1 */
    { uint32_t v = 0x1u; xb_push(c, v); }
    /* 001856EC  call dword ptr [edx] */
    { uint32_t t = xb_rd32((uint32_t)(c->edx)); xb_push(c, 0x001856EEu); xb_call_indirect(c, t); }
L_001856EE:;
    /* 001856EE  mov ecx, dword ptr [esi+0x28] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000028u)));
    /* 001856F1  cmp ecx, ebx */
    { uint32_t a = c->ecx, b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001856F3  mov dword ptr [0x5bd7bc], ebx */
    xb_wr32((uint32_t)(0x005BD7BCu), (uint32_t)(c->ebx));
    /* 001856F9  jz 0x185701 */
    if (zf) goto L_00185701;
    /* 001856FB  mov eax, dword ptr [ecx] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ecx)));
    /* 001856FD  push 0x1 */
    { uint32_t v = 0x1u; xb_push(c, v); }
    /* 001856FF  call dword ptr [eax] */
    { uint32_t t = xb_rd32((uint32_t)(c->eax)); xb_push(c, 0x00185701u); xb_call_indirect(c, t); }
L_00185701:;
    /* 00185701  cmp edi, 0x80000001 */
    { uint32_t a = c->edi, b = 0x80000001u, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185707  mov dword ptr [esi+0x28], ebx */
    xb_wr32((uint32_t)(c->esi + 0x00000028u), (uint32_t)(c->ebx));
    /* 0018570A  jz 0x18589a */
    if (zf) goto L_0018589A;
    /* 00185710  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 00185711  mov dword ptr [esi+0x1c], 0x1855f0 */
    xb_wr32((uint32_t)(c->esi + 0x0000001Cu), (uint32_t)(0x1855F0u));
    /* 00185718  mov byte ptr [esi+0x18], 0x1 */
    xb_wr8((uint32_t)(c->esi + 0x00000018u), (uint8_t)(0x1u));
    /* 0018571C  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 0018571D  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 0018571E  add esp, 0x14 */
    { uint32_t a = c->esp, b = 0x14u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00185721  ret 0x4 */
    c->esp += 8; return;
L_00185724:;
    /* 00185724  push 0x4b57f8 */
    { uint32_t v = 0x4B57F8u; xb_push(c, v); }
    /* 00185729  lea ecx, ptr [esp+0x28] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000028u));
    /* 0018572D  call 0x270d00 */
    xb_push(c, 0x00185732u); f_00270D00(c);
    /* 00185732  mov ecx, dword ptr [esi+0x2c] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x0000002Cu)));
    /* 00185735  imul ecx, ecx, 0x34 */
    { int64_t p = (int64_t)(int32_t)(c->ecx) * (int64_t)(int32_t)(0x34u); uint32_t r = (uint32_t)p & 0xFFFFFFFFu; cf = of = p != (int64_t)(int32_t)(r); c->ecx = (uint32_t)(r); }
    /* 00185738  mov edx, dword ptr [ecx+0x52e850] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->ecx + cat_base())));
    /* 0018573E  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 0018573F  lea ecx, ptr [esp+0x28] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000028u));
    /* 00185743  call 0x2709e0 */
    xb_push(c, 0x00185748u); f_002709E0(c);
    /* 00185748  mov eax, dword ptr [esi+0x2c] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x0000002Cu)));
    /* 0018574B  imul eax, eax, 0x34 */
    { int64_t p = (int64_t)(int32_t)(c->eax) * (int64_t)(int32_t)(0x34u); uint32_t r = (uint32_t)p & 0xFFFFFFFFu; cf = of = p != (int64_t)(int32_t)(r); c->eax = (uint32_t)(r); }
    /* 0018574E  mov ecx, dword ptr [eax+0x52e850] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->eax + cat_base())));
    /* 00185754  push 0x4a7194 */
    { uint32_t v = 0x4A7194u; xb_push(c, v); }
    /* 00185759  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 0018575A  call 0x2f97e5 */
    xb_push(c, 0x0018575Fu); f_002F97E5(c);
    /* 0018575F  add esp, 0x8 */
    { uint32_t a = c->esp, b = 0x8u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 00185762  test eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185764  jnz 0x18585f */
    if (!zf) goto L_0018585F;
    /* 0018576A  cmp dword ptr [esi+0x28], ebx */
    { uint32_t a = xb_rd32((uint32_t)(c->esi + 0x00000028u)), b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0018576D  jnz 0x185842 */
    if (!zf) goto L_00185842;
    /* 00185773  cmp dword ptr [esi+0x34], ebx */
    { uint32_t a = xb_rd32((uint32_t)(c->esi + 0x00000034u)), b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 00185776  jnz 0x18578d */
    if (!zf) goto L_0018578D;
    /* 00185778  lea ecx, ptr [esp+0x24] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000024u));
    /* 0018577C  call 0x2702d0 */
    xb_push(c, 0x00185781u); f_002702D0(c);
    /* 00185781  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185782  call 0x7e960 */
    xb_push(c, 0x00185787u); f_0007E960(c);
    /* 00185787  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 0018578A  mov dword ptr [esi+0x34], eax */
    xb_wr32((uint32_t)(c->esi + 0x00000034u), (uint32_t)(c->eax));
L_0018578D:;
    /* 0018578D  push ebp */
    { uint32_t v = c->ebp; xb_push(c, v); }
    /* 0018578E  mov ecx, 0x58e2a0 */
    c->ecx = (uint32_t)(0x58E2A0u);
    /* 00185793  call 0x77ac0 */
    xb_push(c, 0x00185798u); f_00077AC0(c);
    /* 00185798  push ebx */
    { uint32_t v = c->ebx; xb_push(c, v); }
    /* 00185799  mov ecx, 0x58daa0 */
    c->ecx = (uint32_t)(0x58DAA0u);
    /* 0018579E  mov edi, eax */
    c->edi = (uint32_t)(c->eax);
    /* 001857A0  call 0x755d0 */
    xb_push(c, 0x001857A5u); f_000755D0(c);
    /* 001857A5  mov ebp, eax */
    c->ebp = (uint32_t)(c->eax);
    /* 001857A7  mov edx, dword ptr [ebp+0xb4] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->ebp + 0x000000B4u)));
    /* 001857AD  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 001857AE  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 001857B0  call 0x779b0 */
    xb_push(c, 0x001857B5u); f_000779B0(c);
    /* 001857B5  test edi, edi */
    { uint32_t a = c->edi, b = c->edi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001857B7  jz 0x1857c0 */
    if (zf) goto L_001857C0;
    /* 001857B9  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 001857BB  call 0x777f0 */
    xb_push(c, 0x001857C0u); f_000777F0(c);
L_001857C0:;
    /* 001857C0  call 0x4ab80 */
    xb_push(c, 0x001857C5u); f_0004AB80(c);
    /* 001857C5  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 001857C6  lea ecx, ptr [esp+0x14] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000014u));
    /* 001857CA  call 0x270d00 */
    xb_push(c, 0x001857CFu); f_00270D00(c);
    /* 001857CF  push 0x56b0 */
    { uint32_t v = 0x56B0u; xb_push(c, v); }
    /* 001857D4  call 0x594d0 */
    xb_push(c, 0x001857D9u); f_000594D0(c);
    /* 001857D9  mov edi, eax */
    c->edi = (uint32_t)(c->eax);
    /* 001857DB  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 001857DE  test edi, edi */
    { uint32_t a = c->edi, b = c->edi, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 001857E0  jz 0x185825 */
    if (zf) goto L_00185825;
    /* 001857E2  mov eax, dword ptr [ebp+0xb4] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->ebp + 0x000000B4u)));
    /* 001857E8  mov ecx, dword ptr [esi+0x34] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000034u)));
    /* 001857EB  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 001857EC  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 001857ED  lea ecx, ptr [esp+0x18] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000018u));
    /* 001857F1  mov ebx, 0x1 */
    c->ebx = (uint32_t)(0x1u);
    /* 001857F6  call 0x2702d0 */
    xb_push(c, 0x001857FBu); f_002702D0(c);
    /* 001857FB  xor edx, edx */
    { uint32_t a = c->edx, b = c->edx, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->edx = (uint32_t)(r); }
    /* 001857FD  mov dx, word ptr [0x4afbcc] */
    c->edx = (c->edx & 0xFFFF0000u) | (uint16_t)((uint32_t)xb_rd16((uint32_t)(0x004AFBCCu)));
    /* 00185804  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185805  lea ecx, ptr [esp+0x20] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000020u));
    /* 00185809  push edx */
    { uint32_t v = c->edx; xb_push(c, v); }
    /* 0018580A  push 0x5bad28 */
    { uint32_t v = 0x5BAD28u; xb_push(c, v); }
    /* 0018580F  call 0x275380 */
    xb_push(c, 0x00185814u); f_00275380(c);
    /* 00185814  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185815  push 0x2 */
    { uint32_t v = 0x2u; xb_push(c, v); }
    /* 00185817  push 0x4b5474 */
    { uint32_t v = 0x4B5474u; xb_push(c, v); }
    /* 0018581C  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 0018581E  call 0x183b60 */
    xb_push(c, 0x00185823u); f_00183B60(c);
    /* 00185823  jmp 0x185827 */
    goto L_00185827;
L_00185825:;
    /* 00185825  xor eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
L_00185827:;
    /* 00185827  test bl, 0x1 */
    { uint32_t a = (c->ebx & 0xFFu), b = 0x1u, r; r = a & b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 7) & 1; pf = xb_parity(r); }
    /* 0018582A  mov dword ptr [esi+0x28], eax */
    xb_wr32((uint32_t)(c->esi + 0x00000028u), (uint32_t)(c->eax));
    /* 0018582D  pop ebp */
    { uint32_t v = xb_pop(c); c->ebp = (uint32_t)(v); }
    /* 0018582E  jz 0x185839 */
    if (zf) goto L_00185839;
    /* 00185830  lea ecx, ptr [esp+0x10] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000010u));
    /* 00185834  call 0x2753b0 */
    xb_push(c, 0x00185839u); f_002753B0(c);
L_00185839:;
    /* 00185839  lea ecx, ptr [esp+0xc] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x0000000Cu));
    /* 0018583D  call 0x270690 */
    xb_push(c, 0x00185842u); f_00270690(c);
L_00185842:;
    /* 00185842  mov ecx, dword ptr [esi+0x28] */
    c->ecx = (uint32_t)(xb_rd32((uint32_t)(c->esi + 0x00000028u)));
    /* 00185845  mov eax, dword ptr [esi] */
    c->eax = (uint32_t)(xb_rd32((uint32_t)(c->esi)));
    /* 00185847  push ecx */
    { uint32_t v = c->ecx; xb_push(c, v); }
    /* 00185848  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 0018584A  call dword ptr [eax+0x8] */
    { uint32_t t = xb_rd32((uint32_t)(c->eax + 0x00000008u)); xb_push(c, 0x0018584Du); xb_call_indirect(c, t); }
    /* 0018584D  lea ecx, ptr [esp+0x24] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000024u));
    /* 00185851  call 0x270690 */
    xb_push(c, 0x00185856u); f_00270690(c);
    /* 00185856  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 00185857  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 00185858  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 00185859  add esp, 0x14 */
    { uint32_t a = c->esp, b = 0x14u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 0018585C  ret 0x4 */
    c->esp += 8; return;
L_0018585F:;
    /* 0018585F  push 0x40 */
    { uint32_t v = 0x40u; xb_push(c, v); }
    /* 00185861  call 0x594d0 */
    xb_push(c, 0x00185866u); f_000594D0(c);
    /* 00185866  mov edi, eax */
    c->edi = (uint32_t)(c->eax);
    /* 00185868  add esp, 0x4 */
    { uint32_t a = c->esp, b = 0x4u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 0018586B  cmp edi, ebx */
    { uint32_t a = c->edi, b = c->ebx, r; r = (a - b) & 0xFFFFFFFFu; cf = a < b; of = (((a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); }
    /* 0018586D  jz 0x185882 */
    if (zf) goto L_00185882;
    /* 0018586F  lea ecx, ptr [esp+0x24] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000024u));
    /* 00185873  call 0x2702d0 */
    xb_push(c, 0x00185878u); f_002702D0(c);
    /* 00185878  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185879  mov ecx, edi */
    c->ecx = (uint32_t)(c->edi);
    /* 0018587B  call 0x17d6d0 */
    xb_push(c, 0x00185880u); f_0017D6D0(c);
    /* 00185880  jmp 0x185884 */
    goto L_00185884;
L_00185882:;
    /* 00185882  xor eax, eax */
    { uint32_t a = c->eax, b = c->eax, r; r = a ^ b; cf = 0; of = 0; af = 0; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->eax = (uint32_t)(r); }
L_00185884:;
    /* 00185884  mov edx, dword ptr [esi] */
    c->edx = (uint32_t)(xb_rd32((uint32_t)(c->esi)));
    /* 00185886  push eax */
    { uint32_t v = c->eax; xb_push(c, v); }
    /* 00185887  mov ecx, esi */
    c->ecx = (uint32_t)(c->esi);
    /* 00185889  mov dword ptr [0x5bd7bc], eax */
    xb_wr32((uint32_t)(0x005BD7BCu), (uint32_t)(c->eax));
    /* 0018588E  call dword ptr [edx+0x8] */
    { uint32_t t = xb_rd32((uint32_t)(c->edx + 0x00000008u)); xb_push(c, 0x00185891u); xb_call_indirect(c, t); }
    /* 00185891  lea ecx, ptr [esp+0x24] */
    c->ecx = (uint32_t)((uint32_t)(c->esp + 0x00000024u));
    /* 00185895  call 0x270690 */
    xb_push(c, 0x0018589Au); f_00270690(c);
L_0018589A:;
    /* 0018589A  pop edi */
    { uint32_t v = xb_pop(c); c->edi = (uint32_t)(v); }
    /* 0018589B  pop esi */
    { uint32_t v = xb_pop(c); c->esi = (uint32_t)(v); }
    /* 0018589C  pop ebx */
    { uint32_t v = xb_pop(c); c->ebx = (uint32_t)(v); }
    /* 0018589D  add esp, 0x14 */
    { uint32_t a = c->esp, b = 0x14u, r; r = (a + b) & 0xFFFFFFFFu; cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> 31) & 1; af = ((a ^ b ^ r) >> 4) & 1; zf = r == 0; sf = (r >> 31) & 1; pf = xb_parity(r); c->esp = (uint32_t)(r); }
    /* 001858A0  ret 0x4 */
    c->esp += 8; return;
}
