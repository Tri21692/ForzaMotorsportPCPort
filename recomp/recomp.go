// Package recomp translates Xbox x86 functions into C.
//
// Each discovered function becomes `void f_XXXXXXXX(XbCtx *c)`. Registers
// live in the XbCtx and guest memory is reached through xb_mem (see
// runtime/xbrt.h), so the C behaves like the x86 it came from:
//
//   - Flags are locals, computed in full by every instruction that sets
//     them. The C compiler deletes the ones nothing reads, so no flag
//     liveness analysis is needed here. MSVC never keeps flags live across
//     a call or return, which is what makes locals sufficient.
//   - Jumps inside a function become goto; jumps to another function's
//     entry become a call followed by return (a tail call).
//   - call pushes the real return address on the guest stack and calls the
//     host function; ret pops it and returns. Code that reads its own
//     return address, as _chkstk and _SEH_prolog do, keeps working.
//   - Anything not yet supported becomes an xb_trap naming the instruction,
//     so a gap shows up at run time instead of being silently wrong.
package recomp

import (
	"embed"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

//go:embed runtime/xbrt.h
var Runtime embed.FS

// Translator holds what translation needs about the whole program.
type Translator struct {
	P     *analysis.Program
	F     *xbe.File
	Names map[uint32]string // optional real names, used in comments
	Vars  map[uint32]string // named globals, exported to the runtime in names.h
	// HW names the sections whose memory accesses may reach device
	// registers (the XDK's drivers). Their loads and stores go through
	// xb_hw_*, which hands the GPU's register range to the runtime.
	HW map[string]bool
}

var hwAccess = strings.NewReplacer(
	"xb_rd8(", "xb_hw_rd8(", "xb_rd16(", "xb_hw_rd16(", "xb_rd32(", "xb_hw_rd32(",
	"xb_wr8(", "xb_hw_wr8(", "xb_wr16(", "xb_hw_wr16(", "xb_wr32(", "xb_hw_wr32(")

// Func is one translated function.
type Func struct {
	Addr        uint32
	Code        string
	Unsupported map[string]int // instruction mnemonic -> occurrences
	Insts       int
}

// CName is the C identifier for the function at va.
func CName(va uint32) string { return fmt.Sprintf("f_%08X", va) }

type gen struct {
	t      *Translator
	body   analysis.Body
	in     map[uint32]bool
	labels map[uint32]bool
	unsup  map[string]int
	w      strings.Builder
	cur    analysis.Inst
}

// Function translates the function starting at va.
func (t *Translator) Function(va uint32) Func {
	g := &gen{t: t, body: t.P.Body(va), in: map[uint32]bool{}, labels: map[uint32]bool{}, unsup: map[string]int{}}
	for _, in := range g.body.Insts {
		g.in[in.Addr] = true
	}

	var code strings.Builder
	// Shared tails can sit below the entry, and instructions are emitted in
	// address order, so the entry is not necessarily first.
	if len(g.body.Insts) > 0 && g.body.Insts[0].Addr != va {
		g.labels[va] = true
		g.line("goto L_%08X;", va)
	}
	for i, in := range g.body.Insts {
		g.cur = in
		fmt.Fprintf(&g.w, "@@L%08X@@", in.Addr)
		fmt.Fprintf(&g.w, "    /* %08X  %s */\n", in.Addr, x86asm.IntelSyntax(in.Inst, uint64(in.Addr), nil))
		g.inst(in)
		// Make fallthrough explicit when the next instruction emitted is
		// not the next one in memory.
		if fallsThrough(in.Inst) && (i+1 == len(g.body.Insts) || g.body.Insts[i+1].Addr != in.Next()) {
			g.line("%s", g.jump(in.Next()))
		}
	}
	for _, bad := range g.body.Bad {
		fmt.Fprintf(&g.w, "@@L%08X@@", bad)
		g.line("xb_trap(c, 0x%08X, \"undecodable bytes\");", bad)
	}

	name := ""
	if n, ok := t.Names[va]; ok {
		name = " " + n
	}
	// Weak, so the runtime can replace a library function (see names.h).
	fmt.Fprintf(&code, "/* %08X%s */\nXB_WEAK void %s(XbCtx *c) {\n", va, name, CName(va))
	code.WriteString("    uint32_t cf = 0, zf = 0, sf = 0, of = 0, pf = 0, af = 0;\n")
	code.WriteString("    (void)cf; (void)zf; (void)sf; (void)of; (void)pf; (void)af;\n")
	body := labelMark.ReplaceAllStringFunc(g.w.String(), func(m string) string {
		va, _ := strconv.ParseUint(m[3:11], 16, 32)
		return g.label(uint32(va))
	})
	if fn := t.P.Funcs[va]; fn != nil && t.HW[fn.Section] {
		body = hwAccess.Replace(body)
	}
	code.WriteString(body)
	code.WriteString("}\n")
	return Func{Addr: va, Code: code.String(), Unsupported: g.unsup, Insts: len(g.body.Insts)}
}

var cIdent = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

// labelMark is the placeholder emitted before each instruction; it
// becomes a label only if something jumps there.
var labelMark = regexp.MustCompile(`@@L[0-9A-F]{8}@@`)

func (g *gen) label(va uint32) string {
	if g.labels[va] {
		return fmt.Sprintf("L_%08X:;\n", va)
	}
	return ""
}

func fallsThrough(in x86asm.Inst) bool {
	switch in.Op {
	case x86asm.RET, x86asm.JMP, x86asm.HLT, x86asm.UD2, x86asm.INT, x86asm.IRET:
		return false
	}
	return true
}

func (g *gen) line(format string, args ...any) {
	g.w.WriteString("    ")
	fmt.Fprintf(&g.w, format, args...)
	g.w.WriteString("\n")
}

func (g *gen) unsupported(why string) {
	g.unsup[why]++
	g.line("xb_trap(c, 0x%08X, \"unsupported: %s\");", g.cur.Addr, why)
}

// jump is the statement that transfers control to target. A jump back to
// the function's own entry is a loop, not a recursive call.
//
// A backward jump closes a loop, and gets XB_LOOP, a compiler memory
// barrier: guest memory is plain C memory, so without it the C compiler may
// read a polled location once and spin forever, while another thread or a
// device model is what changes it.
func (g *gen) jump(target uint32) string {
	if g.in[target] {
		g.labels[target] = true
		if target <= g.cur.Addr {
			return fmt.Sprintf("{ XB_LOOP(); goto L_%08X; }", target)
		}
		return fmt.Sprintf("goto L_%08X;", target)
	}
	if g.t.P.IsFunc(target) {
		return fmt.Sprintf("{ %s(c); return; }", CName(target))
	}
	g.unsup["jump outside function"]++
	return fmt.Sprintf("xb_trap(c, 0x%08X, \"jump to %08X outside any known function\");", g.cur.Addr, target)
}

// Program translates a set of functions and returns the C files to write:
// funcs.h (prototypes), dispatch.c (address -> function table) and one
// file per chunk of functions.
func (t *Translator) Program(funcs []uint32, perFile int) (map[string]string, []Func) {
	sort.Slice(funcs, func(i, j int) bool { return funcs[i] < funcs[j] })
	files := map[string]string{}

	var h strings.Builder
	h.WriteString("/* Generated by recomp. */\n#ifndef FUNCS_H\n#define FUNCS_H\n#include \"xbrt.h\"\n\n")
	for _, va := range funcs {
		fmt.Fprintf(&h, "void %s(XbCtx *c);\n", CName(va))
	}
	h.WriteString("\n#endif\n")
	files["funcs.h"] = h.String()

	var d strings.Builder
	d.WriteString("/* Generated by recomp: every function, sorted by guest address. */\n#include \"funcs.h\"\n\n")
	fmt.Fprintf(&d, "const unsigned xb_func_count = %d;\n", len(funcs))
	d.WriteString("const XbFuncEntry xb_funcs[] = {\n")
	for _, va := range funcs {
		fmt.Fprintf(&d, "    { 0x%08X, %s },\n", va, CName(va))
	}
	d.WriteString("};\n")
	files["dispatch.c"] = d.String()

	// names.h: XB_FN_<name> is the C function for a named library routine,
	// so the runtime can define a replacement by name.
	var nh strings.Builder
	nh.WriteString("/* Generated by recomp: library functions by name. Defining XB_FN_x in the\n * runtime replaces the translated function (they are weak). */\n#ifndef NAMES_H\n#define NAMES_H\n\n")
	seen := map[string]bool{}
	for _, va := range funcs {
		n, ok := t.Names[va]
		if !ok || seen[n] || !cIdent.MatchString(n) {
			continue
		}
		seen[n] = true
		fmt.Fprintf(&nh, "#define XB_FN_%s %s\n#define XB_ADDR_%s 0x%08Xu\n", n, CName(va), n, va)
	}
	var vars []uint32
	for va := range t.Vars {
		vars = append(vars, va)
	}
	sort.Slice(vars, func(i, j int) bool { return vars[i] < vars[j] })
	for _, va := range vars {
		if n := t.Vars[va]; cIdent.MatchString(n) && !seen[n] {
			seen[n] = true
			fmt.Fprintf(&nh, "#define XB_VAR_%s 0x%08Xu\n", n, va)
		}
	}
	nh.WriteString("\n#endif\n")
	files["names.h"] = nh.String()

	var k strings.Builder
	k.WriteString("/* Generated by recomp: every xboxkrnl.exe export the runtime may be asked for. */\n#include \"xbrt.h\"\n\n")
	exports := xbe.KernelExports()
	fmt.Fprintf(&k, "const unsigned xb_kernel_info_count = %d;\n", len(exports))
	k.WriteString("const XbKernelInfo xb_kernel_info[] = {\n")
	for _, e := range exports {
		fmt.Fprintf(&k, "    { %d, %q, %d, %d },\n", e.Ordinal, e.Name, int(e.Conv), e.ArgBytes)
	}
	k.WriteString("};\n")
	files["kernel_info.c"] = k.String()

	var out []Func
	if perFile <= 0 {
		perFile = 500
	}
	for i := 0; i < len(funcs); i += perFile {
		var b strings.Builder
		b.WriteString("/* Generated by recomp. */\n#include \"funcs.h\"\n\n")
		end := min(i+perFile, len(funcs))
		for _, va := range funcs[i:end] {
			fn := t.Function(va)
			out = append(out, fn)
			b.WriteString(fn.Code)
			b.WriteString("\n")
		}
		files[fmt.Sprintf("code_%04d.c", i/perFile)] = b.String()
	}
	return files, out
}
