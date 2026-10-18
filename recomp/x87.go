package recomp

import (
	"fmt"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
)

// x87, the stack-based FPU. Values are C long double, which on x86-64
// gcc and clang is the x87's own 80-bit format computed by the x87 unit,
// so precision and rounding follow the control word the game loads
// (xb_fpu_setcw). The register stack lives in XbCtx because MSVC returns
// float and double results in ST(0) across calls.
//
// Not modelled: the tag word (FXAM never reports "empty"), exception
// flags, and the environment/state save instructions (FNSAVE, FRSTOR,
// FLDENV, FNSTENV), which remain unsupported.

func st(i int) string { return fmt.Sprintf("XB_ST(%d)", i) }

func fpr(a x86asm.Arg) (int, bool) {
	r, ok := a.(x86asm.Reg)
	if !ok || r < x86asm.F0 || r > x86asm.F7 {
		return 0, false
	}
	return int(r - x86asm.F0), true
}

// fmem is a memory operand's value as a long double. Integer forms read
// signed integers; float forms read 32/64/80-bit floats (MemBytes 0 is the
// decoder's encoding of the 80-bit form).
func (g *gen) fmem(a x86asm.Arg, integer bool) (string, bool) {
	m, ok := a.(x86asm.Mem)
	if !ok {
		return "", false
	}
	ad, ok := g.addr(m)
	if !ok {
		return "", false
	}
	if integer {
		switch g.cur.MemBytes {
		case 2:
			return "(long double)(int16_t)xb_rd16(" + ad + ")", true
		case 4:
			return "(long double)(int32_t)xb_rd32(" + ad + ")", true
		case 8:
			return "(long double)(int64_t)xb_rd64(" + ad + ")", true
		}
		return "", false
	}
	switch g.cur.MemBytes {
	case 4:
		return "(long double)xb_rdf(" + ad + ")", true
	case 8:
		return "(long double)xb_rdd(" + ad + ")", true
	case 0:
		return "xb_rdt(" + ad + ")", true
	}
	return "", false
}

// fstore is the statement storing long double v to a float memory operand.
func (g *gen) fstore(a x86asm.Arg, v string) (string, bool) {
	m, ok := a.(x86asm.Mem)
	if !ok {
		return "", false
	}
	ad, ok := g.addr(m)
	if !ok {
		return "", false
	}
	switch g.cur.MemBytes {
	case 4:
		return fmt.Sprintf("xb_wrf(%s, (float)%s);", ad, v), true
	case 8:
		return fmt.Sprintf("xb_wrd(%s, (double)%s);", ad, v), true
	case 0:
		return fmt.Sprintf("xb_wrt(%s, %s);", ad, v), true
	}
	return "", false
}

type farith struct {
	expr string // over a (destination) and b (source)
	pop  bool
	int  bool // source is an integer memory operand
}

var x87Arith = map[x86asm.Op]farith{
	x86asm.FADD: {"a + b", false, false}, x86asm.FSUB: {"a - b", false, false}, x86asm.FSUBR: {"b - a", false, false},
	x86asm.FMUL: {"a * b", false, false}, x86asm.FDIV: {"a / b", false, false}, x86asm.FDIVR: {"b / a", false, false},
	x86asm.FADDP: {"a + b", true, false}, x86asm.FSUBP: {"a - b", true, false}, x86asm.FSUBRP: {"b - a", true, false},
	x86asm.FMULP: {"a * b", true, false}, x86asm.FDIVP: {"a / b", true, false}, x86asm.FDIVRP: {"b / a", true, false},
	x86asm.FIADD: {"a + b", false, true}, x86asm.FISUB: {"a - b", false, true}, x86asm.FISUBR: {"b - a", false, true},
	x86asm.FIMUL: {"a * b", false, true}, x86asm.FIDIV: {"a / b", false, true}, x86asm.FIDIVR: {"b / a", false, true},
}

var x87Consts = map[x86asm.Op]string{
	x86asm.FLDZ: "0.0L", x86asm.FLD1: "1.0L", x86asm.FLDPI: "xb_fldpi()", x86asm.FLDL2E: "xb_fldl2e()",
	x86asm.FLDL2T: "xb_fldl2t()", x86asm.FLDLG2: "xb_fldlg2()", x86asm.FLDLN2: "xb_fldln2()",
}

var x87Unary = map[x86asm.Op]string{
	x86asm.FCHS: "-x", x86asm.FABS: "__builtin_fabsl(x)", x86asm.FSQRT: "xb_fsqrt(x)", x86asm.FRNDINT: "xb_frndint(x)",
	x86asm.FSIN: "xb_fsin(x)", x86asm.FCOS: "xb_fcos(x)", x86asm.F2XM1: "xb_f2xm1(x)",
}

var fcmovs = map[x86asm.Op]string{
	x86asm.FCMOVB: "cf", x86asm.FCMOVE: "zf", x86asm.FCMOVBE: "(cf | zf)", x86asm.FCMOVU: "pf",
	x86asm.FCMOVNB: "!cf", x86asm.FCMOVNE: "!zf", x86asm.FCMOVNBE: "(!cf && !zf)", x86asm.FCMOVNU: "!pf",
}

// x87 translates an x87 instruction, reporting false if it is not one this
// translator handles.
func (g *gen) x87(in analysis.Inst) bool {
	op := in.Op
	a0, a1 := in.Args[0], in.Args[1]

	if ar, ok := x87Arith[op]; ok {
		// Forms: (mem) ST0 op= mem; (F0, Fi) ST0 op= STi; (Fi, F0) STi op= ST0.
		if a1 == nil {
			b, ok := g.fmem(a0, ar.int)
			if !ok {
				return false
			}
			g.line("{ long double a = %s, b = %s; %s = %s; }", st(0), b, st(0), ar.expr)
			return true
		}
		d, ok1 := fpr(a0)
		s, ok2 := fpr(a1)
		if !ok1 || !ok2 {
			return false
		}
		pop := ""
		if ar.pop {
			pop = " xb_fpop(c);"
		}
		g.line("{ long double a = %s, b = %s; %s = %s;%s }", st(d), st(s), st(d), ar.expr, pop)
		return true
	}
	if v, ok := x87Consts[op]; ok {
		g.line("xb_fpush(c, %s);", v)
		return true
	}
	if expr, ok := x87Unary[op]; ok {
		g.line("{ long double x = %s; %s = %s; }", st(0), st(0), expr)
		return true
	}
	if cond, ok := fcmovs[op]; ok {
		s, ok := fpr(a1)
		if !ok {
			return false
		}
		g.line("if (%s) %s = %s;", cond, st(0), st(s))
		return true
	}

	switch op {
	case x86asm.FLD, x86asm.FILD:
		if i, ok := fpr(a0); ok {
			g.line("{ long double v = %s; xb_fpush(c, v); }", st(i))
			return true
		}
		v, ok := g.fmem(a0, op == x86asm.FILD)
		if !ok {
			return false
		}
		g.line("xb_fpush(c, %s);", v)
		return true

	case x86asm.FST, x86asm.FSTP:
		pop := ""
		if op == x86asm.FSTP {
			pop = " xb_fpop(c);"
		}
		if i, ok := fpr(a0); ok {
			g.line("%s = %s;%s", st(i), st(0), pop)
			return true
		}
		w, ok := g.fstore(a0, st(0))
		if !ok {
			return false
		}
		g.line("%s%s", w, pop)
		return true

	case x86asm.FIST, x86asm.FISTP:
		m, ok := a0.(x86asm.Mem)
		if !ok {
			return false
		}
		ad, ok := g.addr(m)
		if !ok {
			return false
		}
		pop := ""
		if op == x86asm.FISTP {
			pop = " xb_fpop(c);"
		}
		switch g.cur.MemBytes {
		case 2:
			g.line("xb_wr16(%s, (uint16_t)xb_fist16(%s));%s", ad, st(0), pop)
		case 4:
			g.line("xb_wr32(%s, (uint32_t)xb_fist32(%s));%s", ad, st(0), pop)
		case 8:
			g.line("xb_wr64(%s, (uint64_t)xb_fist64(%s));%s", ad, st(0), pop)
		default:
			return false
		}
		return true

	case x86asm.FXCH:
		i := 1
		if r, ok := fpr(a0); ok {
			i = r
		}
		g.line("{ long double t = %s; %s = %s; %s = t; }", st(0), st(0), st(i), st(i))
		return true

	case x86asm.FCOM, x86asm.FCOMP, x86asm.FUCOM, x86asm.FUCOMP, x86asm.FICOM, x86asm.FICOMP:
		var b string
		if i, ok := fpr(a0); ok {
			b = st(i)
		} else if a0 == nil {
			b = st(1)
		} else {
			v, ok := g.fmem(a0, op == x86asm.FICOM || op == x86asm.FICOMP)
			if !ok {
				return false
			}
			b = v
		}
		pop := ""
		if op == x86asm.FCOMP || op == x86asm.FUCOMP || op == x86asm.FICOMP {
			pop = " xb_fpop(c);"
		}
		g.line("xb_fcom(c, %s, %s);%s", st(0), b, pop)
		return true

	case x86asm.FCOMPP, x86asm.FUCOMPP:
		g.line("xb_fcom(c, %s, %s); xb_fpop(c); xb_fpop(c);", st(0), st(1))
		return true

	case x86asm.FTST:
		g.line("xb_fcom(c, %s, 0.0L);", st(0))
		return true

	case x86asm.FXAM:
		g.line("xb_fxam(c, %s);", st(0))
		return true

	case x86asm.FCOMI, x86asm.FCOMIP, x86asm.FUCOMI, x86asm.FUCOMIP:
		i, ok := fpr(a1)
		if !ok {
			return false
		}
		pop := ""
		if op == x86asm.FCOMIP || op == x86asm.FUCOMIP {
			pop = " xb_fpop(c);"
		}
		g.line("{ long double a = %s, b = %s; if (a != a || b != b) { zf = pf = cf = 1; } else { zf = a == b; pf = 0; cf = a < b; } of = sf = af = 0;%s }",
			st(0), st(i), pop)
		return true

	case x86asm.FNSTSW:
		if r, ok := a0.(x86asm.Reg); ok && r == x86asm.AX {
			g.line("c->eax = (c->eax & 0xFFFF0000u) | xb_fnstsw(c);")
			return true
		}
		if m, ok := a0.(x86asm.Mem); ok {
			if ad, ok := g.addr(m); ok {
				g.line("xb_wr16(%s, xb_fnstsw(c));", ad)
				return true
			}
		}

	case x86asm.FNSTCW:
		if m, ok := a0.(x86asm.Mem); ok {
			if ad, ok := g.addr(m); ok {
				g.line("xb_wr16(%s, c->fcw);", ad)
				return true
			}
		}

	case x86asm.FLDCW:
		if m, ok := a0.(x86asm.Mem); ok {
			if ad, ok := g.addr(m); ok {
				g.line("xb_fpu_setcw(c, xb_rd16(%s));", ad)
				return true
			}
		}

	case x86asm.FSINCOS:
		g.line("{ long double x = %s; %s = xb_fsin(x); xb_fpush(c, xb_fcos(x)); }", st(0), st(0))
		return true
	case x86asm.FPTAN:
		g.line("%s = xb_fptan(%s); xb_fpush(c, 1.0L);", st(0), st(0))
		return true
	case x86asm.FPATAN, x86asm.FYL2X, x86asm.FYL2XP1:
		fn := map[x86asm.Op]string{x86asm.FPATAN: "xb_fpatan", x86asm.FYL2X: "xb_fyl2x", x86asm.FYL2XP1: "xb_fyl2xp1"}[op]
		g.line("{ long double r = %s(%s, %s); xb_fpop(c); %s = r; }", fn, st(1), st(0), st(0))
		return true
	case x86asm.FSCALE:
		g.line("%s = xb_fscale(%s, %s);", st(0), st(0), st(1))
		return true
	case x86asm.FPREM, x86asm.FPREM1:
		ieee := 0
		if op == x86asm.FPREM1 {
			ieee = 1
		}
		g.line("%s = xb_fprem(c, %s, %s, %d);", st(0), st(0), st(1), ieee)
		return true

	case x86asm.FNINIT:
		g.line("c->ftop = 0; c->fsw = 0; xb_fpu_setcw(c, 0x037F);")
		return true
	case x86asm.FINCSTP:
		g.line("c->ftop = (c->ftop + 1) & 7;")
		return true
	case x86asm.FDECSTP:
		g.line("c->ftop = (c->ftop - 1) & 7;")
		return true
	case x86asm.FWAIT, x86asm.FNOP, x86asm.FFREE, x86asm.FNCLEX:
		// No exception state or tag word is kept, so these do nothing.
		return true
	}
	return false
}
