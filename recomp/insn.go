package recomp

import (
	"fmt"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// ---- operands ----

var reg32 = map[x86asm.Reg]string{
	x86asm.EAX: "eax", x86asm.ECX: "ecx", x86asm.EDX: "edx", x86asm.EBX: "ebx",
	x86asm.ESP: "esp", x86asm.EBP: "ebp", x86asm.ESI: "esi", x86asm.EDI: "edi",
}

// regInfo returns a register's 32-bit parent, width and bit offset.
func regInfo(r x86asm.Reg) (parent string, bits, shift int, ok bool) {
	switch {
	case r >= x86asm.EAX && r <= x86asm.EDI:
		return reg32[r], 32, 0, true
	case r >= x86asm.AX && r <= x86asm.DI:
		return reg32[x86asm.EAX+(r-x86asm.AX)], 16, 0, true
	case r >= x86asm.AL && r <= x86asm.BL:
		return reg32[x86asm.EAX+(r-x86asm.AL)], 8, 0, true
	case r >= x86asm.AH && r <= x86asm.BH:
		return reg32[x86asm.EAX+(r-x86asm.AH)], 8, 8, true
	}
	return "", 0, 0, false
}

func mask(bits int) string {
	switch bits {
	case 8:
		return "0xFFu"
	case 16:
		return "0xFFFFu"
	}
	return "0xFFFFFFFFu"
}

func ctype(bits int) string {
	switch bits {
	case 8:
		return "uint8_t"
	case 16:
		return "uint16_t"
	}
	return "uint32_t"
}

// sext sign-extends a bits-wide value to int32.
func sext(bits int, e string) string {
	switch bits {
	case 8:
		return "(int32_t)(int8_t)(" + e + ")"
	case 16:
		return "(int32_t)(int16_t)(" + e + ")"
	}
	return "(int32_t)(" + e + ")"
}

// addr is the guest address of a memory operand.
func (g *gen) addr(m x86asm.Mem) (string, bool) {
	if g.cur.AddrSize != 32 {
		return "", false
	}
	e := ""
	add := func(s string) {
		if e != "" {
			e += " + "
		}
		e += s
	}
	switch m.Segment {
	case 0, x86asm.DS, x86asm.SS, x86asm.ES, x86asm.CS:
	case x86asm.FS:
		add("c->fs_base")
	default:
		return "", false
	}
	if m.Base != 0 {
		r, ok := reg32[m.Base]
		if !ok {
			return "", false
		}
		add("c->" + r)
	}
	if m.Index != 0 {
		r, ok := reg32[m.Index]
		if !ok {
			return "", false
		}
		if m.Scale > 1 {
			add(fmt.Sprintf("c->%s * %d", r, m.Scale))
		} else {
			add("c->" + r)
		}
	}
	if m.Disp != 0 || e == "" {
		add(fmt.Sprintf("0x%08Xu", uint32(m.Disp)))
	}
	return "(uint32_t)(" + e + ")", true
}

// size is an operand's width in bits.
func (g *gen) size(a x86asm.Arg) int {
	switch a := a.(type) {
	case x86asm.Reg:
		if _, bits, _, ok := regInfo(a); ok {
			return bits
		}
	case x86asm.Mem:
		return g.cur.MemBytes * 8
	}
	return g.cur.DataSize
}

// read is a C expression for an operand's value, zero-extended to 32 bits.
func (g *gen) read(a x86asm.Arg, bits int) (string, bool) {
	switch a := a.(type) {
	case x86asm.Reg:
		p, w, sh, ok := regInfo(a)
		if !ok {
			return "", false
		}
		switch {
		case w == 32:
			return "c->" + p, true
		case sh == 8:
			return fmt.Sprintf("((c->%s >> 8) & 0xFFu)", p), true
		default:
			return fmt.Sprintf("(c->%s & %s)", p, mask(w)), true
		}
	case x86asm.Mem:
		ad, ok := g.addr(a)
		if !ok {
			return "", false
		}
		switch bits {
		case 8:
			return "(uint32_t)xb_rd8(" + ad + ")", true
		case 16:
			return "(uint32_t)xb_rd16(" + ad + ")", true
		case 32:
			return "xb_rd32(" + ad + ")", true
		}
	case x86asm.Imm:
		return fmt.Sprintf("0x%Xu", uint64(a)&uint64(maskVal(bits))), true
	}
	return "", false
}

func maskVal(bits int) uint32 {
	if bits >= 32 {
		return 0xFFFFFFFF
	}
	return 1<<bits - 1
}

// write is a C statement storing v (already masked or not) to an operand.
func (g *gen) write(a x86asm.Arg, bits int, v string) (string, bool) {
	switch a := a.(type) {
	case x86asm.Reg:
		p, w, sh, ok := regInfo(a)
		if !ok {
			return "", false
		}
		switch {
		case w == 32:
			return fmt.Sprintf("c->%s = (uint32_t)(%s);", p, v), true
		case sh == 8:
			return fmt.Sprintf("c->%s = (c->%s & 0xFFFF00FFu) | ((uint32_t)(uint8_t)(%s) << 8);", p, p, v), true
		case w == 16:
			return fmt.Sprintf("c->%s = (c->%s & 0xFFFF0000u) | (uint16_t)(%s);", p, p, v), true
		default:
			return fmt.Sprintf("c->%s = (c->%s & 0xFFFFFF00u) | (uint8_t)(%s);", p, p, v), true
		}
	case x86asm.Mem:
		ad, ok := g.addr(a)
		if !ok {
			return "", false
		}
		switch bits {
		case 8:
			return fmt.Sprintf("xb_wr8(%s, (uint8_t)(%s));", ad, v), true
		case 16:
			return fmt.Sprintf("xb_wr16(%s, (uint16_t)(%s));", ad, v), true
		case 32:
			return fmt.Sprintf("xb_wr32(%s, (uint32_t)(%s));", ad, v), true
		}
	}
	return "", false
}

// szp sets ZF, SF and PF from a bits-wide result r.
func szp(bits int) string {
	return fmt.Sprintf("zf = r == 0; sf = (r >> %d) & 1; pf = xb_parity(r);", bits-1)
}

// ---- conditions ----

var conds = map[x86asm.Op]string{
	x86asm.JO: "of", x86asm.JNO: "!of", x86asm.JB: "cf", x86asm.JAE: "!cf",
	x86asm.JE: "zf", x86asm.JNE: "!zf", x86asm.JBE: "(cf | zf)", x86asm.JA: "(!cf && !zf)",
	x86asm.JS: "sf", x86asm.JNS: "!sf", x86asm.JP: "pf", x86asm.JNP: "!pf",
	x86asm.JL: "(sf != of)", x86asm.JGE: "(sf == of)", x86asm.JLE: "(zf || sf != of)", x86asm.JG: "(!zf && sf == of)",
}

var setccs = map[x86asm.Op]x86asm.Op{
	x86asm.SETO: x86asm.JO, x86asm.SETNO: x86asm.JNO, x86asm.SETB: x86asm.JB, x86asm.SETAE: x86asm.JAE,
	x86asm.SETE: x86asm.JE, x86asm.SETNE: x86asm.JNE, x86asm.SETBE: x86asm.JBE, x86asm.SETA: x86asm.JA,
	x86asm.SETS: x86asm.JS, x86asm.SETNS: x86asm.JNS, x86asm.SETP: x86asm.JP, x86asm.SETNP: x86asm.JNP,
	x86asm.SETL: x86asm.JL, x86asm.SETGE: x86asm.JGE, x86asm.SETLE: x86asm.JLE, x86asm.SETG: x86asm.JG,
}

var cmovs = map[x86asm.Op]x86asm.Op{
	x86asm.CMOVO: x86asm.JO, x86asm.CMOVNO: x86asm.JNO, x86asm.CMOVB: x86asm.JB, x86asm.CMOVAE: x86asm.JAE,
	x86asm.CMOVE: x86asm.JE, x86asm.CMOVNE: x86asm.JNE, x86asm.CMOVBE: x86asm.JBE, x86asm.CMOVA: x86asm.JA,
	x86asm.CMOVS: x86asm.JS, x86asm.CMOVNS: x86asm.JNS, x86asm.CMOVP: x86asm.JP, x86asm.CMOVNP: x86asm.JNP,
	x86asm.CMOVL: x86asm.JL, x86asm.CMOVGE: x86asm.JGE, x86asm.CMOVLE: x86asm.JLE, x86asm.CMOVG: x86asm.JG,
}

func hasPrefix(in x86asm.Inst, p x86asm.Prefix) bool {
	for _, q := range in.Prefix {
		if q == 0 {
			break
		}
		if q&0xFF == p&0xFF && q&x86asm.PrefixIgnored == 0 {
			return true
		}
	}
	return false
}

func rel(in analysis.Inst) (uint32, bool) {
	if r, ok := in.Args[0].(x86asm.Rel); ok {
		return in.Next() + uint32(int32(r)), true
	}
	return 0, false
}

// ---- instructions ----

func (g *gen) inst(in analysis.Inst) {
	op := in.Op
	a0, a1, a2 := in.Args[0], in.Args[1], in.Args[2]

	if g.sse(in) || g.x87(in) {
		return
	}

	if c, ok := conds[op]; ok {
		t, ok := rel(in)
		if !ok {
			g.unsupported(op.String() + " (indirect)")
			return
		}
		g.line("if (%s) %s", c, g.jump(t))
		return
	}
	if j, ok := setccs[op]; ok {
		if s, ok := g.write(a0, 8, conds[j]); ok {
			g.line("%s", s)
			return
		}
	}
	if j, ok := cmovs[op]; ok {
		bits := g.size(a0)
		src, ok1 := g.read(a1, bits)
		dst, ok2 := g.write(a0, bits, src)
		if ok1 && ok2 {
			g.line("if (%s) { %s }", conds[j], dst)
			return
		}
	}

	switch op {
	case x86asm.NOP, x86asm.PREFETCHNTA, x86asm.PREFETCHT0, x86asm.PREFETCHT1, x86asm.PREFETCHT2:
		return

	case x86asm.MOV:
		bits := g.size(a0)
		v, ok1 := g.read(a1, bits)
		w, ok2 := g.write(a0, bits, v)
		if ok1 && ok2 {
			g.line("%s", w)
			return
		}

	case x86asm.MOVZX, x86asm.MOVSX:
		src := g.size(a1)
		v, ok := g.read(a1, src)
		if !ok {
			break
		}
		if op == x86asm.MOVSX {
			v = "(uint32_t)" + sext(src, v)
		}
		if s, ok := g.write(a0, g.size(a0), v); ok {
			g.line("%s", s)
			return
		}

	case x86asm.LEA:
		m, ok := a1.(x86asm.Mem)
		if !ok {
			break
		}
		m.Segment = 0
		ad, ok := g.addr(m)
		if !ok {
			break
		}
		if s, ok := g.write(a0, g.size(a0), ad); ok {
			g.line("%s", s)
			return
		}

	case x86asm.ADD, x86asm.ADC, x86asm.SUB, x86asm.SBB, x86asm.CMP,
		x86asm.AND, x86asm.OR, x86asm.XOR, x86asm.TEST:
		if g.alu(op, a0, a1) {
			return
		}

	case x86asm.INC, x86asm.DEC, x86asm.NEG, x86asm.NOT:
		if g.unary(op, a0) {
			return
		}

	case x86asm.SHL, x86asm.SHR, x86asm.SAR, x86asm.ROL, x86asm.ROR:
		if g.shift(op, a0, a1) {
			return
		}

	case x86asm.SHLD, x86asm.SHRD:
		if g.shiftDouble(op, a0, a1, a2) {
			return
		}

	case x86asm.IMUL:
		if g.imul(a0, a1, a2) {
			return
		}

	case x86asm.MUL, x86asm.DIV, x86asm.IDIV:
		if g.muldiv(op, a0) {
			return
		}

	case x86asm.CDQ:
		g.line("c->edx = (uint32_t)((int32_t)c->eax >> 31);")
		return
	case x86asm.CWDE:
		g.line("c->eax = (uint32_t)(int32_t)(int16_t)c->eax;")
		return
	case x86asm.CBW:
		g.line("c->eax = (c->eax & 0xFFFF0000u) | (uint16_t)(int16_t)(int8_t)c->eax;")
		return
	case x86asm.CWD:
		g.line("c->edx = (c->edx & 0xFFFF0000u) | (uint16_t)((int16_t)c->eax >> 15);")
		return

	case x86asm.XCHG:
		bits := g.size(a0)
		x, ok1 := g.read(a0, bits)
		y, ok2 := g.read(a1, bits)
		w0, ok3 := g.write(a0, bits, "b")
		w1, ok4 := g.write(a1, bits, "a")
		if ok1 && ok2 && ok3 && ok4 {
			g.line("{ uint32_t a = %s, b = %s; %s %s }", x, y, w0, w1)
			return
		}

	case x86asm.XADD:
		bits := g.size(a0)
		x, ok1 := g.read(a0, bits)
		y, ok2 := g.read(a1, bits)
		w0, ok3 := g.write(a0, bits, "r")
		w1, ok4 := g.write(a1, bits, "a")
		if ok1 && ok2 && ok3 && ok4 {
			g.line("{ uint32_t a = %s, b = %s, r = (a + b) & %s; %s %s %s }", x, y, mask(bits), addFlags(bits), w1, w0)
			return
		}

	case x86asm.CMPXCHG:
		bits := g.size(a0)
		acc := map[int]x86asm.Reg{8: x86asm.AL, 16: x86asm.AX, 32: x86asm.EAX}[bits]
		x, ok1 := g.read(acc, bits)
		d, ok2 := g.read(a0, bits)
		s, ok3 := g.read(a1, bits)
		wd, ok4 := g.write(a0, bits, "s")
		wa, ok5 := g.write(acc, bits, "b")
		if ok1 && ok2 && ok3 && ok4 && ok5 {
			g.line("{ uint32_t a = %s, b = %s, s = %s, r = (a - b) & %s; %s if (zf) { %s } else { %s } }",
				x, d, s, mask(bits), subFlags(bits), wd, wa)
			return
		}

	case x86asm.BSWAP:
		if r, ok := reg32[a0.(x86asm.Reg)]; ok {
			g.line("c->%s = __builtin_bswap32(c->%s);", r, r)
			return
		}

	case x86asm.BT, x86asm.BTS, x86asm.BTR, x86asm.BTC:
		if g.bittest(op, a0, a1) {
			return
		}

	case x86asm.BSF, x86asm.BSR:
		bits := g.size(a0)
		v, ok := g.read(a1, bits)
		fn := "(uint32_t)__builtin_ctz(v)"
		if op == x86asm.BSR {
			fn = "(uint32_t)(31 - __builtin_clz(v))"
		}
		w, ok2 := g.write(a0, bits, fn)
		if ok && ok2 {
			g.line("{ uint32_t v = %s; zf = v == 0; if (v) { %s } }", v, w)
			return
		}

	case x86asm.PUSH:
		bits := g.size(a0)
		if _, isImm := a0.(x86asm.Imm); isImm {
			bits = 32
		}
		if bits != 32 {
			break
		}
		v, ok := g.read(a0, 32)
		if ok {
			// Read first: the operand may use esp, as in push [esp+8].
			g.line("{ uint32_t v = %s; xb_push(c, v); }", v)
			return
		}

	case x86asm.POP:
		if g.size(a0) != 32 {
			break
		}
		// pop [esp+n] addresses with the incremented esp, so pop first.
		if w, ok := g.write(a0, 32, "v"); ok {
			g.line("{ uint32_t v = xb_pop(c); %s }", w)
			return
		}

	case x86asm.PUSHAD:
		g.line("{ uint32_t s = c->esp; xb_push(c, c->eax); xb_push(c, c->ecx); xb_push(c, c->edx); xb_push(c, c->ebx);" +
			" xb_push(c, s); xb_push(c, c->ebp); xb_push(c, c->esi); xb_push(c, c->edi); }")
		return
	case x86asm.POPAD:
		g.line("c->edi = xb_pop(c); c->esi = xb_pop(c); c->ebp = xb_pop(c); c->esp += 4;" +
			" c->ebx = xb_pop(c); c->edx = xb_pop(c); c->ecx = xb_pop(c); c->eax = xb_pop(c);")
		return
	case x86asm.PUSHFD:
		g.line("xb_push(c, cf | 2u | pf << 2 | af << 4 | zf << 6 | sf << 7 | 1u << 9 | c->df << 10 | of << 11);")
		return
	case x86asm.POPFD:
		g.line("{ uint32_t v = xb_pop(c); cf = v & 1; pf = (v >> 2) & 1; af = (v >> 4) & 1; zf = (v >> 6) & 1;" +
			" sf = (v >> 7) & 1; c->df = (v >> 10) & 1; of = (v >> 11) & 1; }")
		return
	case x86asm.LAHF:
		g.line("c->eax = (c->eax & 0xFFFF00FFu) | ((cf | 2u | pf << 2 | af << 4 | zf << 6 | sf << 7) << 8);")
		return
	case x86asm.SAHF:
		g.line("{ uint32_t v = c->eax >> 8; cf = v & 1; pf = (v >> 2) & 1; af = (v >> 4) & 1; zf = (v >> 6) & 1; sf = (v >> 7) & 1; }")
		return

	case x86asm.LEAVE:
		g.line("c->esp = c->ebp; c->ebp = xb_pop(c);")
		return
	case x86asm.CLD:
		g.line("c->df = 0;")
		return
	case x86asm.STD:
		g.line("c->df = 1;")
		return
	case x86asm.CLC:
		g.line("cf = 0;")
		return
	case x86asm.STC:
		g.line("cf = 1;")
		return
	case x86asm.CMC:
		g.line("cf ^= 1;")
		return

	case x86asm.MOVSB, x86asm.MOVSW, x86asm.MOVSD, x86asm.STOSB, x86asm.STOSW, x86asm.STOSD,
		x86asm.LODSB, x86asm.LODSW, x86asm.LODSD, x86asm.SCASB, x86asm.SCASW, x86asm.SCASD,
		x86asm.CMPSB, x86asm.CMPSW, x86asm.CMPSD:
		if g.stringOp(in) {
			return
		}

	case x86asm.JMP:
		g.jmp(in)
		return
	case x86asm.CALL:
		g.call(in)
		return
	case x86asm.RET:
		n := uint32(0)
		if imm, ok := a0.(x86asm.Imm); ok {
			n = uint32(imm)
		}
		g.line("c->esp += %d; return;", 4+n)
		return
	case x86asm.JECXZ:
		if t, ok := rel(in); ok {
			g.line("if (c->ecx == 0) %s", g.jump(t))
			return
		}
	case x86asm.LOOP, x86asm.LOOPE, x86asm.LOOPNE:
		if t, ok := rel(in); ok {
			cond := map[x86asm.Op]string{x86asm.LOOP: "", x86asm.LOOPE: " && zf", x86asm.LOOPNE: " && !zf"}[op]
			g.line("if (--c->ecx != 0%s) %s", cond, g.jump(t))
			return
		}

	case x86asm.INT, x86asm.HLT, x86asm.UD2:
		g.line("xb_trap(c, 0x%08X, \"%s\");", in.Addr, op)
		return
	}
	g.unsupported(opName(in))
}

// opName names an instruction for the unsupported list: the mnemonic, or
// "x87"/"SSE" for whole families not handled yet.
func opName(in analysis.Inst) string {
	s := in.Op.String()
	if s != "" && s[0] == 'F' {
		return "x87 " + s
	}
	for _, a := range in.Args {
		if r, ok := a.(x86asm.Reg); ok && r >= x86asm.X0 && r <= x86asm.X15 {
			return "SSE " + s
		}
		if r, ok := a.(x86asm.Reg); ok && r >= x86asm.M0 && r <= x86asm.M7 {
			return "MMX " + s
		}
	}
	return s
}

func addFlags(bits int) string {
	return fmt.Sprintf("cf = r < a; of = ((~(a ^ b) & (a ^ r)) >> %d) & 1; af = ((a ^ b ^ r) >> 4) & 1; %s", bits-1, szp(bits))
}

func subFlags(bits int) string {
	return fmt.Sprintf("cf = a < b; of = (((a ^ b) & (a ^ r)) >> %d) & 1; af = ((a ^ b ^ r) >> 4) & 1; %s", bits-1, szp(bits))
}

func (g *gen) alu(op x86asm.Op, dst, src x86asm.Arg) bool {
	bits := g.size(dst)
	a, ok1 := g.read(dst, bits)
	b, ok2 := g.read(src, bits)
	if !ok1 || !ok2 {
		return false
	}
	m := mask(bits)
	var body string
	switch op {
	case x86asm.ADD:
		body = fmt.Sprintf("r = (a + b) & %s; %s", m, addFlags(bits))
	case x86asm.ADC:
		body = fmt.Sprintf("r = (a + b + cf) & %s; { uint32_t c0 = cf; cf = c0 ? r <= a : r < a; } of = ((~(a ^ b) & (a ^ r)) >> %d) & 1; af = ((a ^ b ^ r) >> 4) & 1; %s",
			m, bits-1, szp(bits))
	case x86asm.SUB, x86asm.CMP:
		body = fmt.Sprintf("r = (a - b) & %s; %s", m, subFlags(bits))
	case x86asm.SBB:
		body = fmt.Sprintf("r = (a - b - cf) & %s; { uint32_t c0 = cf; cf = c0 ? a <= b : a < b; } of = (((a ^ b) & (a ^ r)) >> %d) & 1; af = ((a ^ b ^ r) >> 4) & 1; %s",
			m, bits-1, szp(bits))
	case x86asm.AND, x86asm.TEST:
		body = "r = a & b; cf = 0; of = 0; af = 0; " + szp(bits)
	case x86asm.OR:
		body = "r = a | b; cf = 0; of = 0; af = 0; " + szp(bits)
	case x86asm.XOR:
		body = "r = a ^ b; cf = 0; of = 0; af = 0; " + szp(bits)
	}
	store := ""
	if op != x86asm.CMP && op != x86asm.TEST {
		w, ok := g.write(dst, bits, "r")
		if !ok {
			return false
		}
		store = " " + w
	}
	g.line("{ uint32_t a = %s, b = %s, r; %s%s }", a, b, body, store)
	return true
}

func (g *gen) unary(op x86asm.Op, dst x86asm.Arg) bool {
	bits := g.size(dst)
	a, ok1 := g.read(dst, bits)
	w, ok2 := g.write(dst, bits, "r")
	if !ok1 || !ok2 {
		return false
	}
	m, sign := mask(bits), fmt.Sprintf("0x%Xu", uint32(1)<<(bits-1))
	var body string
	switch op {
	case x86asm.INC:
		body = fmt.Sprintf("r = (a + 1) & %s; of = r == %s; af = (r & 0xF) == 0; %s", m, sign, szp(bits))
	case x86asm.DEC:
		body = fmt.Sprintf("r = (a - 1) & %s; of = a == %s; af = (a & 0xF) == 0; %s", m, sign, szp(bits))
	case x86asm.NEG:
		body = fmt.Sprintf("r = (0u - a) & %s; cf = a != 0; of = a == %s; af = (a & 0xF) != 0; %s", m, sign, szp(bits))
	case x86asm.NOT:
		body = fmt.Sprintf("r = ~a & %s;", m)
	}
	g.line("{ uint32_t a = %s, r; %s %s }", a, body, w)
	return true
}

func (g *gen) shift(op x86asm.Op, dst, cnt x86asm.Arg) bool {
	bits := g.size(dst)
	a, ok1 := g.read(dst, bits)
	n, ok2 := g.read(cnt, 8)
	w, ok3 := g.write(dst, bits, "r")
	if !ok1 || !ok2 || !ok3 {
		return false
	}
	m, top := mask(bits), bits-1
	var body string
	switch op {
	case x86asm.SHL:
		// Counts past the width only occur for 8/16-bit operands; the
		// result is then 0 with CF undefined, which 64-bit math gives.
		body = fmt.Sprintf("uint64_t w = (uint64_t)a << n; r = (uint32_t)w & %s; cf = (uint32_t)(w >> %d) & 1; of = ((r >> %d) & 1) ^ cf; %s",
			m, bits, top, szp(bits))
	case x86asm.SHR:
		body = fmt.Sprintf("r = (uint32_t)((uint64_t)a >> n); cf = (uint32_t)((uint64_t)a >> (n - 1)) & 1; of = (a >> %d) & 1; %s",
			top, szp(bits))
	case x86asm.SAR:
		body = fmt.Sprintf("int64_t s = %s; r = (uint32_t)(s >> (n > %d ? %d : n)) & %s; cf = (uint32_t)(s >> (n - 1 > %d ? %d : n - 1)) & 1; of = 0; %s",
			sext(bits, "a"), top, top, m, top, top, szp(bits))
	case x86asm.ROL:
		body = fmt.Sprintf("uint32_t k = n %% %d; r = k ? ((a << k) | (a >> (%d - k))) & %s : a; cf = r & 1; of = ((r >> %d) & 1) ^ cf;",
			bits, bits, m, top)
	case x86asm.ROR:
		body = fmt.Sprintf("uint32_t k = n %% %d; r = k ? ((a >> k) | (a << (%d - k))) & %s : a; cf = (r >> %d) & 1; of = cf ^ ((r >> %d) & 1);",
			bits, bits, m, top, top-1)
	}
	// A zero count changes nothing, flags included.
	g.line("{ uint32_t a = %s, n = %s & 0x1Fu, r; if (n) { %s %s } }", a, n, body, w)
	return true
}

func (g *gen) shiftDouble(op x86asm.Op, dst, src, cnt x86asm.Arg) bool {
	if g.size(dst) != 32 {
		return false
	}
	a, ok1 := g.read(dst, 32)
	b, ok2 := g.read(src, 32)
	n, ok3 := g.read(cnt, 8)
	w, ok4 := g.write(dst, 32, "r")
	if !ok1 || !ok2 || !ok3 || !ok4 {
		return false
	}
	body := "r = (a << n) | (b >> (32 - n)); cf = (a >> (32 - n)) & 1;"
	if op == x86asm.SHRD {
		body = "r = (a >> n) | (b << (32 - n)); cf = (a >> (n - 1)) & 1;"
	}
	g.line("{ uint32_t a = %s, b = %s, n = %s & 0x1Fu, r; if (n) { %s of = ((r ^ a) >> 31) & 1; %s %s } }",
		a, b, n, body, szp(32), w)
	return true
}

func (g *gen) imul(a0, a1, a2 x86asm.Arg) bool {
	if a1 == nil {
		return g.muldiv(x86asm.IMUL, a0)
	}
	bits := g.size(a0)
	x, y := a0, a1
	if a2 != nil {
		x, y = a1, a2
	}
	xv, ok1 := g.read(x, bits)
	yv, ok2 := g.read(y, bits)
	w, ok3 := g.write(a0, bits, "r")
	if !ok1 || !ok2 || !ok3 {
		return false
	}
	g.line("{ int64_t p = (int64_t)%s * (int64_t)%s; uint32_t r = (uint32_t)p & %s; cf = of = p != (int64_t)%s; %s }",
		sext(bits, xv), sext(bits, yv), mask(bits), sext(bits, "r"), w)
	return true
}

// muldiv handles the one-operand MUL, IMUL, DIV and IDIV forms, which use
// AL/AX/EAX and AH/DX/EDX implicitly.
func (g *gen) muldiv(op x86asm.Op, src x86asm.Arg) bool {
	bits := g.size(src)
	s, ok := g.read(src, bits)
	if !ok {
		return false
	}
	trap := fmt.Sprintf("xb_trap(c, 0x%08X, \"divide error\");", g.cur.Addr)
	switch bits {
	case 32:
		switch op {
		case x86asm.MUL:
			g.line("{ uint64_t p = (uint64_t)c->eax * %s; c->eax = (uint32_t)p; c->edx = (uint32_t)(p >> 32); cf = of = c->edx != 0; }", s)
		case x86asm.IMUL:
			g.line("{ int64_t p = (int64_t)(int32_t)c->eax * (int32_t)%s; c->eax = (uint32_t)p; c->edx = (uint32_t)((uint64_t)p >> 32); cf = of = p != (int32_t)p; }", s)
		case x86asm.DIV:
			g.line("{ uint64_t n = (uint64_t)c->edx << 32 | c->eax; uint32_t d = %s; if (d == 0 || (n / d) >> 32) %s c->eax = (uint32_t)(n / d); c->edx = (uint32_t)(n %% d); }", s, trap)
		case x86asm.IDIV:
			g.line("{ int64_t n = (int64_t)((uint64_t)c->edx << 32 | c->eax); int32_t d = (int32_t)%s; if (d == 0 || (d == -1 && n == INT64_MIN)) %s int64_t q = n / d;"+
				" if (q != (int32_t)q) %s c->eax = (uint32_t)q; c->edx = (uint32_t)(n %% d); }", s, trap, trap)
		}
	case 16:
		switch op {
		case x86asm.MUL:
			g.line("{ uint32_t p = (c->eax & 0xFFFFu) * %s; c->eax = (c->eax & 0xFFFF0000u) | (p & 0xFFFFu); c->edx = (c->edx & 0xFFFF0000u) | (p >> 16); cf = of = (p >> 16) != 0; }", s)
		case x86asm.IMUL:
			g.line("{ int32_t p = (int16_t)c->eax * (int16_t)%s; c->eax = (c->eax & 0xFFFF0000u) | ((uint32_t)p & 0xFFFFu); c->edx = (c->edx & 0xFFFF0000u) | (((uint32_t)p >> 16) & 0xFFFFu); cf = of = p != (int16_t)p; }", s)
		case x86asm.DIV:
			g.line("{ uint32_t n = (c->edx & 0xFFFFu) << 16 | (c->eax & 0xFFFFu), d = %s; if (d == 0 || (n / d) > 0xFFFFu) %s c->eax = (c->eax & 0xFFFF0000u) | (n / d); c->edx = (c->edx & 0xFFFF0000u) | (n %% d); }", s, trap)
		case x86asm.IDIV:
			g.line("{ int32_t n = (int32_t)((c->edx & 0xFFFFu) << 16 | (c->eax & 0xFFFFu)), d = (int16_t)%s; if (d == 0) %s int32_t q = n / d; if (q != (int16_t)q) %s"+
				" c->eax = (c->eax & 0xFFFF0000u) | ((uint32_t)q & 0xFFFFu); c->edx = (c->edx & 0xFFFF0000u) | ((uint32_t)(n %% d) & 0xFFFFu); }", s, trap, trap)
		}
	case 8:
		switch op {
		case x86asm.MUL:
			g.line("{ uint32_t p = (c->eax & 0xFFu) * %s; c->eax = (c->eax & 0xFFFF0000u) | p; cf = of = (p >> 8) != 0; }", s)
		case x86asm.IMUL:
			g.line("{ int32_t p = (int8_t)c->eax * (int8_t)%s; c->eax = (c->eax & 0xFFFF0000u) | ((uint32_t)p & 0xFFFFu); cf = of = p != (int8_t)p; }", s)
		case x86asm.DIV:
			g.line("{ uint32_t n = c->eax & 0xFFFFu, d = %s; if (d == 0 || (n / d) > 0xFFu) %s c->eax = (c->eax & 0xFFFF0000u) | (n %% d) << 8 | (n / d); }", s, trap)
		case x86asm.IDIV:
			g.line("{ int32_t n = (int16_t)c->eax, d = (int8_t)%s; if (d == 0) %s int32_t q = n / d; if (q != (int8_t)q) %s"+
				" c->eax = (c->eax & 0xFFFF0000u) | ((uint32_t)(n %% d) & 0xFFu) << 8 | ((uint32_t)q & 0xFFu); }", s, trap, trap)
		}
	default:
		return false
	}
	return true
}

func (g *gen) bittest(op x86asm.Op, base, bit x86asm.Arg) bool {
	bits := g.size(base)
	if bits == 8 {
		return false
	}
	idx, ok := g.read(bit, bits)
	if !ok {
		return false
	}
	update := map[x86asm.Op]string{x86asm.BT: "", x86asm.BTS: "v |= m;", x86asm.BTR: "v &= ~m;", x86asm.BTC: "v ^= m;"}[op]
	if m, isMem := base.(x86asm.Mem); isMem {
		// A register bit offset can reach outside the addressed dword.
		ad, ok := g.addr(m)
		if !ok {
			return false
		}
		step := "0"
		if _, isReg := bit.(x86asm.Reg); isReg {
			step = fmt.Sprintf("(uint32_t)(%s >> 5) * 4", sext(bits, idx))
		}
		store := ""
		if update != "" {
			store = "xb_wr32(p, v);"
		}
		g.line("{ uint32_t i = %s, p = %s + %s, v = xb_rd32(p), m = 1u << (i & 31); cf = (v & m) != 0; %s %s }",
			idx, ad, step, update, store)
		return true
	}
	v, ok1 := g.read(base, bits)
	w, ok2 := g.write(base, bits, "v")
	if !ok1 || !ok2 {
		return false
	}
	store := ""
	if update != "" {
		store = w
	}
	g.line("{ uint32_t i = %s, v = %s, m = 1u << (i & %d); cf = (v & m) != 0; %s %s }", idx, v, bits-1, update, store)
	return true
}

// stringOp handles MOVS, STOS, LODS, SCAS and CMPS with REP/REPE/REPNE.
func (g *gen) stringOp(in analysis.Inst) bool {
	for _, a := range in.Args {
		if r, ok := a.(x86asm.Reg); ok && r >= x86asm.X0 && r <= x86asm.X15 {
			return false // SSE2 MOVSD/CMPSD share the mnemonic
		}
	}
	s := in.Op.String()
	kind := s[:4]
	bits := map[byte]int{'B': 8, 'W': 16, 'D': 32}[s[4]]
	n := bits / 8
	rd := map[int]string{8: "xb_rd8", 16: "xb_rd16", 32: "xb_rd32"}[bits]
	wr := map[int]string{8: "xb_wr8", 16: "xb_wr16", 32: "xb_wr32"}[bits]
	acc, _ := g.read(map[int]x86asm.Reg{8: x86asm.AL, 16: x86asm.AX, 32: x86asm.EAX}[bits], bits)
	setAcc, _ := g.write(map[int]x86asm.Reg{8: x86asm.AL, 16: x86asm.AX, 32: x86asm.EAX}[bits], bits, "v")
	step := fmt.Sprintf("uint32_t d = c->df ? (uint32_t)-%d : %d;", n, n)

	var one string
	compares := false
	switch kind {
	case "MOVS":
		one = fmt.Sprintf("%s(c->edi, %s(c->esi)); c->esi += d; c->edi += d;", wr, rd)
	case "STOS":
		one = fmt.Sprintf("%s(c->edi, %s); c->edi += d;", wr, acc)
	case "LODS":
		one = fmt.Sprintf("{ uint32_t v = %s(c->esi); %s } c->esi += d;", rd, setAcc)
	case "SCAS":
		one = fmt.Sprintf("{ uint32_t a = %s, b = %s(c->edi), r = (a - b) & %s; %s } c->edi += d;", acc, rd, mask(bits), subFlags(bits))
		compares = true
	case "CMPS":
		one = fmt.Sprintf("{ uint32_t a = %s(c->esi), b = %s(c->edi), r = (a - b) & %s; %s } c->esi += d; c->edi += d;", rd, rd, mask(bits), subFlags(bits))
		compares = true
	default:
		return false
	}
	switch {
	case hasPrefix(in.Inst, x86asm.PrefixREP) && compares:
		g.line("{ %s while (c->ecx) { %s c->ecx--; if (!zf) break; } }", step, one)
	case hasPrefix(in.Inst, x86asm.PrefixREPN) && compares:
		g.line("{ %s while (c->ecx) { %s c->ecx--; if (zf) break; } }", step, one)
	case hasPrefix(in.Inst, x86asm.PrefixREP):
		g.line("{ %s while (c->ecx) { %s c->ecx--; } }", step, one)
	default:
		g.line("{ %s %s }", step, one)
	}
	return true
}

func (g *gen) jmp(in analysis.Inst) {
	if t, ok := rel(in); ok {
		g.line("%s", g.jump(t))
		return
	}
	if k, ok := g.thunk(in); ok {
		g.line("xb_kernel(c, %d); return; /* %s */", k.Ordinal, k.Name)
		return
	}
	v, ok := g.read(in.Args[0], 32)
	if !ok {
		g.unsupported("JMP operand")
		return
	}
	if targets, ok := g.body.Tables[in.Addr]; ok {
		g.line("switch (%s) {", v)
		seen := map[uint32]bool{}
		for _, t := range targets {
			if !seen[t] {
				seen[t] = true
				g.line("case 0x%08Xu: %s", t, g.jump(t))
			}
		}
		g.line("default: xb_trap(c, 0x%08X, \"switch target outside its table\");", in.Addr)
		g.line("}")
		return
	}
	g.line("{ uint32_t t = %s; xb_call_indirect(c, t); return; }", v)
}

func (g *gen) call(in analysis.Inst) {
	next := in.Next()
	if t, ok := rel(in); ok {
		switch {
		case g.t.P.IsFunc(t):
			g.line("xb_push(c, 0x%08Xu); %s(c);%s", next, CName(t), g.calleeComment(t))
		case t == next:
			// call $+5; pop reg: reads its own address, a PIC idiom.
			g.line("xb_push(c, 0x%08Xu);", next)
		default:
			g.unsup["call outside function"]++
			g.line("xb_trap(c, 0x%08X, \"call to %08X, not a known function\");", in.Addr, t)
		}
		return
	}
	if k, ok := g.thunk(in); ok {
		g.line("xb_push(c, 0x%08Xu); xb_kernel(c, %d); /* %s */", next, k.Ordinal, k.Name)
		return
	}
	v, ok := g.read(in.Args[0], 32)
	if !ok {
		g.unsupported("CALL operand")
		return
	}
	g.line("{ uint32_t t = %s; xb_push(c, 0x%08Xu); xb_call_indirect(c, t); }", v, next)
}

func (g *gen) calleeComment(t uint32) string {
	if n, ok := g.t.Names[t]; ok {
		return " /* " + n + " */"
	}
	return ""
}

func (g *gen) thunk(in analysis.Inst) (xbe.KernelImport, bool) {
	m, ok := in.Args[0].(x86asm.Mem)
	if !ok || m.Base != 0 || m.Index != 0 || m.Segment != 0 {
		return xbe.KernelImport{}, false
	}
	return g.t.F.KernelBySlot(uint32(m.Disp))
}
