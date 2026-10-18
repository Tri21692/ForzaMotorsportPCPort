package recomp

import (
	"fmt"
	"strings"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
)

// MMX, used by Bink and the WMA decoder. Registers alias the x87 stack as
// on the hardware (see xb_mmr/xb_mmw in xbrt.h), including the reset of
// TOP to 0 that every MMX instruction performs.

func mmReg(a x86asm.Arg) (int, bool) {
	r, ok := a.(x86asm.Reg)
	if !ok || r < x86asm.M0 || r > x86asm.M7 {
		return 0, false
	}
	return int(r - x86asm.M0), true
}

// mm64 is a 64-bit MMX source: a register or a 64-bit memory operand.
func (g *gen) mm64(a x86asm.Arg) (string, bool) {
	if i, ok := mmReg(a); ok {
		return fmt.Sprintf("xb_mmr(c, %d)", i), true
	}
	if m, ok := a.(x86asm.Mem); ok {
		if ad, ok := g.addr(m); ok {
			return "xb_rd64(" + ad + ")", true
		}
	}
	return "", false
}

// mmxLane describes an element-wise op over n lanes of field, computing
// expr from a.<field>[k] and b.<field>[k] (written $A and $B).
type mmxLane struct {
	field string
	n     int
	expr  string
}

var mmxLanes = map[x86asm.Op]mmxLane{
	x86asm.PADDB: {"b", 8, "$A + $B"}, x86asm.PADDW: {"w", 4, "$A + $B"}, x86asm.PADDD: {"d", 2, "$A + $B"},
	x86asm.PSUBB: {"b", 8, "$A - $B"}, x86asm.PSUBW: {"w", 4, "$A - $B"}, x86asm.PSUBD: {"d", 2, "$A - $B"},
	x86asm.PADDSB: {"sb", 8, "xb_sat_s8($A + $B)"}, x86asm.PADDSW: {"sw", 4, "xb_sat_s16($A + $B)"},
	x86asm.PSUBSB: {"sb", 8, "xb_sat_s8($A - $B)"}, x86asm.PSUBSW: {"sw", 4, "xb_sat_s16($A - $B)"},
	x86asm.PADDUSB: {"b", 8, "xb_sat_u8($A + $B)"}, x86asm.PADDUSW: {"w", 4, "xb_sat_u16($A + $B)"},
	x86asm.PSUBUSB: {"b", 8, "xb_sat_u8($A - $B)"}, x86asm.PSUBUSW: {"w", 4, "xb_sat_u16($A - $B)"},
	x86asm.PMULLW: {"sw", 4, "(int16_t)($A * $B)"}, x86asm.PMULHW: {"sw", 4, "(int16_t)(($A * $B) >> 16)"},
	x86asm.PMULHUW: {"w", 4, "(uint16_t)(((uint32_t)$A * $B) >> 16)"},
	x86asm.PCMPEQB: {"b", 8, "$A == $B ? 0xFF : 0"}, x86asm.PCMPEQW: {"w", 4, "$A == $B ? 0xFFFF : 0"},
	x86asm.PCMPEQD: {"d", 2, "$A == $B ? 0xFFFFFFFFu : 0"},
	x86asm.PCMPGTB: {"sb", 8, "$A > $B ? -1 : 0"}, x86asm.PCMPGTW: {"sw", 4, "$A > $B ? -1 : 0"},
	x86asm.PCMPGTD: {"sd", 2, "$A > $B ? -1 : 0"},
	x86asm.PAVGB:   {"b", 8, "($A + $B + 1) >> 1"}, x86asm.PAVGW: {"w", 4, "($A + $B + 1) >> 1"},
	x86asm.PMAXSW: {"sw", 4, "$A > $B ? $A : $B"}, x86asm.PMINSW: {"sw", 4, "$A < $B ? $A : $B"},
	x86asm.PMAXUB: {"b", 8, "$A > $B ? $A : $B"}, x86asm.PMINUB: {"b", 8, "$A < $B ? $A : $B"},
}

var mmxBits = map[x86asm.Op]string{
	x86asm.PAND: "a & b", x86asm.PANDN: "~a & b", x86asm.POR: "a | b", x86asm.PXOR: "a ^ b",
}

// mmxShifts: lane field, width, and whether it is logical left, logical
// right or arithmetic right.
var mmxShifts = map[x86asm.Op]struct {
	field string
	bits  int
	kind  byte
}{
	x86asm.PSLLW: {"w", 16, 'l'}, x86asm.PSLLD: {"d", 32, 'l'}, x86asm.PSLLQ: {"q", 64, 'l'},
	x86asm.PSRLW: {"w", 16, 'r'}, x86asm.PSRLD: {"d", 32, 'r'}, x86asm.PSRLQ: {"q", 64, 'r'},
	x86asm.PSRAW: {"sw", 16, 'a'}, x86asm.PSRAD: {"sd", 32, 'a'},
}

func (g *gen) mmx(in analysis.Inst) bool {
	op := in.Op
	a0, a1, a2 := in.Args[0], in.Args[1], in.Args[2]
	d, dIsMM := mmReg(a0)

	if l, ok := mmxLanes[op]; ok && dIsMM {
		src, ok := g.mm64(a1)
		if !ok {
			return false
		}
		expr := strings.NewReplacer("$A", "a."+l.field+"[k]", "$B", "b."+l.field+"[k]").Replace(l.expr)
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }, b = { .q = %s }, r; for (int k = 0; k < %d; k++) r.%s[k] = %s; c->ftop = 0; xb_mmw(c, %d, r.q); }",
			d, src, l.n, l.field, expr, d)
		return true
	}
	if expr, ok := mmxBits[op]; ok && dIsMM {
		src, ok := g.mm64(a1)
		if !ok {
			return false
		}
		g.line("{ uint64_t a = xb_mmr(c, %d), b = %s; c->ftop = 0; xb_mmw(c, %d, %s); }", d, src, d, expr)
		return true
	}
	if sh, ok := mmxShifts[op]; ok && dIsMM {
		var cnt string
		if imm, ok := a1.(x86asm.Imm); ok {
			cnt = fmt.Sprintf("%dull", uint64(imm)&0xFF)
		} else if v, ok := g.mm64(a1); ok {
			cnt = v
		} else {
			return false
		}
		if sh.field == "q" {
			expr := "n > 63 ? 0 : a << n"
			if sh.kind == 'r' {
				expr = "n > 63 ? 0 : a >> n"
			}
			g.line("{ uint64_t a = xb_mmr(c, %d), n = %s; c->ftop = 0; xb_mmw(c, %d, %s); }", d, cnt, d, expr)
			return true
		}
		var expr string
		switch sh.kind {
		case 'l':
			expr = fmt.Sprintf("n > %d ? 0 : a.%s[k] << n", sh.bits-1, sh.field)
		case 'r':
			expr = fmt.Sprintf("n > %d ? 0 : a.%s[k] >> n", sh.bits-1, sh.field)
		default:
			expr = fmt.Sprintf("a.%s[k] >> (n > %d ? %d : n)", sh.field, sh.bits-1, sh.bits-1)
		}
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }, r; uint64_t n = %s; for (int k = 0; k < %d; k++) r.%s[k] = %s; c->ftop = 0; xb_mmw(c, %d, r.q); }",
			d, cnt, 64/sh.bits, sh.field, expr, d)
		return true
	}

	switch op {
	case x86asm.EMMS:
		// Marks the x87 registers empty; tags are not modelled.
		return true

	case x86asm.MOVQ, x86asm.MOVNTQ:
		if dIsMM {
			v, ok := g.mm64(a1)
			if !ok {
				return false
			}
			g.line("{ uint64_t v = %s; c->ftop = 0; xb_mmw(c, %d, v); }", v, d)
			return true
		}
		s, ok := mmReg(a1)
		m, ok2 := a0.(x86asm.Mem)
		if !ok || !ok2 {
			return false
		}
		ad, ok := g.addr(m)
		if !ok {
			return false
		}
		g.line("c->ftop = 0; xb_wr64(%s, xb_mmr(c, %d));", ad, s)
		return true

	case x86asm.MOVD:
		if dIsMM {
			v, ok := g.read(a1, 32)
			if !ok {
				return false
			}
			g.line("{ uint64_t v = %s; c->ftop = 0; xb_mmw(c, %d, v); }", v, d)
			return true
		}
		s, ok := mmReg(a1)
		if !ok {
			return false
		}
		w, ok := g.write(a0, 32, fmt.Sprintf("(uint32_t)xb_mmr(c, %d)", s))
		if !ok {
			return false
		}
		g.line("c->ftop = 0; %s", w)
		return true

	case x86asm.PUNPCKLBW, x86asm.PUNPCKLWD, x86asm.PUNPCKLDQ, x86asm.PUNPCKHBW, x86asm.PUNPCKHWD, x86asm.PUNPCKHDQ:
		src, ok := g.mm64(a1)
		if !dIsMM || !ok {
			return false
		}
		field := map[x86asm.Op]string{
			x86asm.PUNPCKLBW: "b", x86asm.PUNPCKHBW: "b", x86asm.PUNPCKLWD: "w",
			x86asm.PUNPCKHWD: "w", x86asm.PUNPCKLDQ: "d", x86asm.PUNPCKHDQ: "d",
		}[op]
		n := map[string]int{"b": 8, "w": 4, "d": 2}[field]
		base := 0
		if op == x86asm.PUNPCKHBW || op == x86asm.PUNPCKHWD || op == x86asm.PUNPCKHDQ {
			base = n / 2
		}
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }, b = { .q = %s }, r; for (int k = 0; k < %d; k++) { r.%s[2 * k] = a.%s[%d + k]; r.%s[2 * k + 1] = b.%s[%d + k]; } c->ftop = 0; xb_mmw(c, %d, r.q); }",
			d, src, n/2, field, field, base, field, field, base, d)
		return true

	case x86asm.PACKSSWB, x86asm.PACKUSWB, x86asm.PACKSSDW:
		src, ok := g.mm64(a1)
		if !dIsMM || !ok {
			return false
		}
		from, to, sat, n := "sw", "sb", "xb_sat_s8", 4
		switch op {
		case x86asm.PACKUSWB:
			to, sat = "b", "xb_sat_u8"
		case x86asm.PACKSSDW:
			from, to, sat, n = "sd", "sw", "xb_sat_s16", 2
		}
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }, b = { .q = %s }, r; for (int k = 0; k < %d; k++) { r.%s[k] = %s(a.%s[k]); r.%s[%d + k] = %s(b.%s[k]); } c->ftop = 0; xb_mmw(c, %d, r.q); }",
			d, src, n, to, sat, from, to, n, sat, from, d)
		return true

	case x86asm.PMADDWD:
		src, ok := g.mm64(a1)
		if !dIsMM || !ok {
			return false
		}
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }, b = { .q = %s }, r; for (int k = 0; k < 2; k++) r.d[k] = (uint32_t)((int32_t)a.sw[2 * k] * b.sw[2 * k]) + (uint32_t)((int32_t)a.sw[2 * k + 1] * b.sw[2 * k + 1]); c->ftop = 0; xb_mmw(c, %d, r.q); }",
			d, src, d)
		return true

	case x86asm.PSHUFW:
		src, ok := g.mm64(a1)
		imm, ok2 := a2.(x86asm.Imm)
		if !dIsMM || !ok || !ok2 {
			return false
		}
		i := uint32(imm)
		g.line("{ XbMM a = { .q = %s }, r; r.w[0] = a.w[%d]; r.w[1] = a.w[%d]; r.w[2] = a.w[%d]; r.w[3] = a.w[%d]; c->ftop = 0; xb_mmw(c, %d, r.q); }",
			src, i&3, i>>2&3, i>>4&3, i>>6&3, d)
		return true

	case x86asm.PMOVMSKB:
		s, ok := mmReg(a1)
		w, ok2 := g.write(a0, 32, "m")
		if !ok || !ok2 {
			return false
		}
		g.line("{ XbMM a = { .q = xb_mmr(c, %d) }; uint32_t m = 0; for (int k = 0; k < 8; k++) m |= (uint32_t)(a.b[k] >> 7) << k; c->ftop = 0; %s }", s, w)
		return true
	}
	return false
}
