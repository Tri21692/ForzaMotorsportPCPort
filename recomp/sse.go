package recomp

import (
	"fmt"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
)

// SSE1, the Pentium III's single-precision vector extension. The host runs
// the same IEEE single-precision arithmetic, so results match bit for bit
// as long as the generated C is compiled without FMA contraction or fast
// math (see runtime/xbrt.h). Two known differences from real hardware:
// RCPSS/RSQRTSS and their packed forms give exact results here, where the
// Pentium III gives a 12-bit approximation, and MXCSR is stored and
// reloaded but its rounding mode and flush-to-zero bits are not applied.

func xmm(a x86asm.Arg) (int, bool) {
	r, ok := a.(x86asm.Reg)
	if !ok || r < x86asm.X0 || r > x86asm.X7 {
		return 0, false
	}
	return int(r - x86asm.X0), true
}

// scalar reads the low float of an xmm register or a 32-bit memory operand.
func (g *gen) scalar(a x86asm.Arg) (string, bool) {
	if i, ok := xmm(a); ok {
		return fmt.Sprintf("c->xmm[%d].f[0]", i), true
	}
	if m, ok := a.(x86asm.Mem); ok {
		if ad, ok := g.addr(m); ok {
			return "xb_rdf(" + ad + ")", true
		}
	}
	return "", false
}

// vector reads a whole xmm register or 128-bit memory operand as an XbVec.
func (g *gen) vector(a x86asm.Arg) (string, bool) {
	if i, ok := xmm(a); ok {
		return fmt.Sprintf("c->xmm[%d]", i), true
	}
	if m, ok := a.(x86asm.Mem); ok {
		if ad, ok := g.addr(m); ok {
			return "xb_rdv(" + ad + ")", true
		}
	}
	return "", false
}

var sseScalarOps = map[x86asm.Op]string{
	x86asm.ADDSS: "a + b", x86asm.SUBSS: "a - b", x86asm.MULSS: "a * b", x86asm.DIVSS: "a / b",
	// x86 MIN/MAX return the second operand when either is NaN or both are
	// zero, which this form reproduces; fminf/fmaxf would not.
	x86asm.MINSS: "a < b ? a : b", x86asm.MAXSS: "a > b ? a : b",
	x86asm.SQRTSS: "__builtin_sqrtf(b)", x86asm.RCPSS: "1.0f / b", x86asm.RSQRTSS: "1.0f / __builtin_sqrtf(b)",
}

var ssePackedOps = map[x86asm.Op]string{
	x86asm.ADDPS: "a + b", x86asm.SUBPS: "a - b", x86asm.MULPS: "a * b", x86asm.DIVPS: "a / b",
	x86asm.MINPS: "a < b ? a : b", x86asm.MAXPS: "a > b ? a : b",
	x86asm.SQRTPS: "__builtin_sqrtf(b)", x86asm.RCPPS: "1.0f / b", x86asm.RSQRTPS: "1.0f / __builtin_sqrtf(b)",
}

var sseBitOps = map[x86asm.Op]string{
	x86asm.ANDPS: "a & b", x86asm.ANDNPS: "~a & b", x86asm.ORPS: "a | b", x86asm.XORPS: "a ^ b",
}

// cmpPredicates are CMPPS/CMPSS's imm8 predicates as C over floats a, b.
var cmpPredicates = [8]string{"a == b", "a < b", "a <= b", "a != a || b != b",
	"!(a == b)", "!(a < b)", "!(a <= b)", "a == a && b == b"}

// sse translates an SSE instruction, reporting false if it is not one this
// translator handles.
func (g *gen) sse(in analysis.Inst) bool {
	op := in.Op
	a0, a1, a2 := in.Args[0], in.Args[1], in.Args[2]
	d, dIsXmm := xmm(a0)

	if expr, ok := sseScalarOps[op]; ok && dIsXmm {
		b, ok := g.scalar(a1)
		if !ok {
			return false
		}
		g.line("{ float a = c->xmm[%d].f[0], b = %s; (void)a; c->xmm[%d].f[0] = %s; }", d, b, d, expr)
		return true
	}
	if expr, ok := ssePackedOps[op]; ok && dIsXmm {
		b, ok := g.vector(a1)
		if !ok {
			return false
		}
		g.line("{ XbVec s = %s; for (int k = 0; k < 4; k++) { float a = c->xmm[%d].f[k], b = s.f[k]; (void)a; c->xmm[%d].f[k] = %s; } }", b, d, d, expr)
		return true
	}
	if expr, ok := sseBitOps[op]; ok && dIsXmm {
		b, ok := g.vector(a1)
		if !ok {
			return false
		}
		g.line("{ XbVec s = %s; for (int k = 0; k < 4; k++) { uint32_t a = c->xmm[%d].u[k], b = s.u[k]; c->xmm[%d].u[k] = %s; } }", b, d, d, expr)
		return true
	}

	switch op {
	case x86asm.MOVSS:
		s, sIsXmm := xmm(a1)
		switch {
		case dIsXmm && sIsXmm:
			g.line("c->xmm[%d].u[0] = c->xmm[%d].u[0];", d, s)
		case dIsXmm:
			m, ok := a1.(x86asm.Mem)
			ad, ok2 := g.addr(m)
			if !ok || !ok2 {
				return false
			}
			// A load clears the upper three lanes; a register move does not.
			g.line("c->xmm[%d].u[0] = xb_rd32(%s); c->xmm[%d].u[1] = c->xmm[%d].u[2] = c->xmm[%d].u[3] = 0;", d, ad, d, d, d)
		case sIsXmm:
			m, ok := a0.(x86asm.Mem)
			ad, ok2 := g.addr(m)
			if !ok || !ok2 {
				return false
			}
			g.line("xb_wr32(%s, c->xmm[%d].u[0]);", ad, s)
		default:
			return false
		}
		return true

	case x86asm.MOVAPS, x86asm.MOVUPS:
		if dIsXmm {
			v, ok := g.vector(a1)
			if !ok {
				return false
			}
			g.line("c->xmm[%d] = %s;", d, v)
			return true
		}
		s, ok := xmm(a1)
		m, ok2 := a0.(x86asm.Mem)
		if !ok || !ok2 {
			return false
		}
		ad, ok := g.addr(m)
		if !ok {
			return false
		}
		g.line("xb_wrv(%s, c->xmm[%d]);", ad, s)
		return true

	case x86asm.MOVLPS, x86asm.MOVHPS:
		lane := 0
		if op == x86asm.MOVHPS {
			lane = 1
		}
		if dIsXmm {
			m, ok := a1.(x86asm.Mem)
			ad, ok2 := g.addr(m)
			if !ok || !ok2 {
				return false
			}
			g.line("c->xmm[%d].q[%d] = xb_rd64(%s);", d, lane, ad)
			return true
		}
		s, ok := xmm(a1)
		m, ok2 := a0.(x86asm.Mem)
		ad, ok3 := g.addr(m)
		if !ok || !ok2 || !ok3 {
			return false
		}
		g.line("xb_wr64(%s, c->xmm[%d].q[%d]);", ad, s, lane)
		return true

	case x86asm.MOVHLPS, x86asm.MOVLHPS:
		s, ok := xmm(a1)
		if !dIsXmm || !ok {
			return false
		}
		if op == x86asm.MOVHLPS {
			g.line("c->xmm[%d].q[0] = c->xmm[%d].q[1];", d, s)
		} else {
			g.line("c->xmm[%d].q[1] = c->xmm[%d].q[0];", d, s)
		}
		return true

	case x86asm.SHUFPS:
		v, ok := g.vector(a1)
		imm, ok2 := a2.(x86asm.Imm)
		if !dIsXmm || !ok || !ok2 {
			return false
		}
		i := uint32(imm)
		g.line("{ XbVec a = c->xmm[%d], b = %s; c->xmm[%d].u[0] = a.u[%d]; c->xmm[%d].u[1] = a.u[%d]; c->xmm[%d].u[2] = b.u[%d]; c->xmm[%d].u[3] = b.u[%d]; }",
			d, v, d, i&3, d, i>>2&3, d, i>>4&3, d, i>>6&3)
		return true

	case x86asm.UNPCKLPS, x86asm.UNPCKHPS:
		v, ok := g.vector(a1)
		if !dIsXmm || !ok {
			return false
		}
		lo := 0
		if op == x86asm.UNPCKHPS {
			lo = 2
		}
		g.line("{ XbVec a = c->xmm[%d], b = %s; c->xmm[%d].u[0] = a.u[%d]; c->xmm[%d].u[1] = b.u[%d]; c->xmm[%d].u[2] = a.u[%d]; c->xmm[%d].u[3] = b.u[%d]; }",
			d, v, d, lo, d, lo, d, lo+1, d, lo+1)
		return true

	case x86asm.CMPPS, x86asm.CMPSS:
		imm, ok := a2.(x86asm.Imm)
		if !dIsXmm || !ok || uint32(imm) > 7 {
			return false
		}
		pred := cmpPredicates[uint32(imm)]
		if op == x86asm.CMPSS {
			b, ok := g.scalar(a1)
			if !ok {
				return false
			}
			g.line("{ float a = c->xmm[%d].f[0], b = %s; c->xmm[%d].u[0] = (%s) ? 0xFFFFFFFFu : 0; }", d, b, d, pred)
			return true
		}
		v, ok := g.vector(a1)
		if !ok {
			return false
		}
		g.line("{ XbVec s = %s; for (int k = 0; k < 4; k++) { float a = c->xmm[%d].f[k], b = s.f[k]; c->xmm[%d].u[k] = (%s) ? 0xFFFFFFFFu : 0; } }", v, d, d, pred)
		return true

	case x86asm.COMISS, x86asm.UCOMISS:
		b, ok := g.scalar(a1)
		if !dIsXmm || !ok {
			return false
		}
		g.line("{ float a = c->xmm[%d].f[0], b = %s; if (a != a || b != b) { zf = pf = cf = 1; } else { zf = a == b; pf = 0; cf = a < b; } of = sf = af = 0; }", d, b)
		return true

	case x86asm.CVTSI2SS:
		v, ok := g.read(a1, 32)
		if !dIsXmm || !ok {
			return false
		}
		g.line("c->xmm[%d].f[0] = (float)(int32_t)%s;", d, v)
		return true

	case x86asm.CVTTSS2SI, x86asm.CVTSS2SI:
		v, ok := g.scalar(a1)
		fn := "xb_f2i_trunc"
		if op == x86asm.CVTSS2SI {
			fn = "xb_f2i_round"
		}
		w, ok2 := g.write(a0, 32, fn+"("+v+")")
		if !ok || !ok2 {
			return false
		}
		g.line("%s", w)
		return true

	case x86asm.MOVMSKPS:
		s, ok := xmm(a1)
		w, ok2 := g.write(a0, 32, fmt.Sprintf("(c->xmm[%d].u[0] >> 31) | (c->xmm[%d].u[1] >> 31) << 1 | (c->xmm[%d].u[2] >> 31) << 2 | (c->xmm[%d].u[3] >> 31) << 3", s, s, s, s))
		if !ok || !ok2 {
			return false
		}
		g.line("%s", w)
		return true

	case x86asm.LDMXCSR:
		if m, ok := a0.(x86asm.Mem); ok {
			if ad, ok := g.addr(m); ok {
				g.line("c->mxcsr = xb_rd32(%s);", ad)
				return true
			}
		}
	case x86asm.STMXCSR:
		if m, ok := a0.(x86asm.Mem); ok {
			if ad, ok := g.addr(m); ok {
				g.line("xb_wr32(%s, c->mxcsr);", ad)
				return true
			}
		}
	case x86asm.SFENCE:
		return true
	}
	return false
}
