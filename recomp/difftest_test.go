package recomp_test

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"fmt"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/internal/xbetest"
	"github.com/Tri21692/ForzaMotorsportPC/recomp"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// The differential test runs recompiled functions and the original x86 on
// Unicorn from the same random state, then compares every register and a
// CRC of all writable memory. It needs gcc and a Python with the unicorn
// module (XBRT_PYTHON, default python3); it skips without them. Set
// XBRT_KEEP to a directory to keep the harness and inputs for debugging.

const scratchBase = 0x10000000

// cflags are the flags generated code must be built with (see xbrt.h).
var cflags = []string{"-ffp-contract=off", "-fno-math-errno", "-lm"}

func tools(t *testing.T) (python string) {
	t.Helper()
	if _, err := exec.LookPath("gcc"); err != nil {
		t.Skip("gcc not found")
	}
	python = os.Getenv("XBRT_PYTHON")
	if python == "" {
		python = "python3"
	}
	if err := exec.Command(python, "-c", "import unicorn").Run(); err != nil {
		t.Skipf("%s has no unicorn module (pip install unicorn, or set XBRT_PYTHON)", python)
	}
	return python
}

var otherFunc = regexp.MustCompile(`\bf_[0-9A-F]{8}\b`)

// noReference matches x87 instructions Unicorn computes through host
// double precision rather than as the x87 does, so a function using them
// cannot be checked against it (see docs/RECOMPILER.md).
var noReference = regexp.MustCompile(`/\* [0-9A-F]{8}  (fsin|fcos|fsincos|fptan|fpatan|fyl2x|fyl2xp1|f2xm1|fprem|fprem1)\b`)

// leafFuncs picks functions the translator fully handles that call nothing
// and use no fs: segment, so they run in the harness on their own.
func leafFuncs(tr *recomp.Translator, p *analysis.Program) map[uint32]recomp.Func {
	out := map[uint32]recomp.Func{}
	for va, fn := range p.Funcs {
		if len(fn.Calls)+len(fn.TailCalls)+len(fn.KernelCalls)+fn.IndirectCalls+fn.Unresolved > 0 || fn.BadDecode {
			continue
		}
		code := tr.Function(va)
		if len(code.Unsupported) > 0 || strings.Contains(code.Code, "fs_base") || strings.Contains(code.Code, "xb_call_indirect") ||
			strings.Contains(code.Code, "xb_kernel") || strings.Contains(code.Code, "xb_rdtsc") ||
			len(otherFunc.FindAllString(code.Code, -1)) != 1 || noReference.MatchString(code.Code) {
			continue
		}
		out[va] = code
	}
	return out
}

type caseResult struct {
	fn   uint32
	in   string
	c, u string
}

// runDiff builds the harness for funcs, runs cases on both sides and
// returns (compared, mismatches).
func runDiff(t *testing.T, f *xbe.File, funcs map[uint32]recomp.Func, perFunc int) (int, []caseResult) {
	t.Helper()
	python := tools(t)
	dir := t.TempDir()
	if keep := os.Getenv("XBRT_KEEP"); keep != "" {
		// Keep the harness, generated C and inputs for debugging by hand.
		dir = filepath.Join(keep, t.Name())
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
	}

	addrs := make([]uint32, 0, len(funcs))
	for va := range funcs {
		addrs = append(addrs, va)
	}
	sort.Slice(addrs, func(i, j int) bool { return addrs[i] < addrs[j] })

	var gen strings.Builder
	gen.WriteString("#include \"xbrt.h\"\n\n")
	for _, va := range addrs {
		fmt.Fprintf(&gen, "void %s(XbCtx *c);\n", recomp.CName(va))
	}
	for _, va := range addrs {
		gen.WriteString(funcs[va].Code)
	}
	gen.WriteString("\ntypedef void (*xb_fn)(XbCtx *);\nconst xb_fn test_funcs[] = {\n")
	var list strings.Builder
	for _, va := range addrs {
		fmt.Fprintf(&gen, "    %s,\n", recomp.CName(va))
		fmt.Fprintf(&list, "%08x\n", va)
	}
	fmt.Fprintf(&gen, "};\nconst unsigned test_func_count = %d;\n", len(addrs))

	hdr, _ := recomp.Runtime.ReadFile("runtime/xbrt.h")
	harness, err := os.ReadFile("testdata/harness.c")
	if err != nil {
		t.Fatal(err)
	}
	write := func(name string, b []byte) {
		if err := os.WriteFile(filepath.Join(dir, name), b, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("xbrt.h", hdr)
	write("harness.c", harness)
	write("gen.c", []byte(gen.String()))
	write("funcs.txt", []byte(list.String()))
	write("image.bin", imageBlob(f))

	build := exec.Command("gcc", append([]string{"-O1", "-w", "-o", filepath.Join(dir, "harness"),
		filepath.Join(dir, "harness.c"), filepath.Join(dir, "gen.c")}, cflags...)...)
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("gcc: %v\n%s", err, out)
	}

	rng := rand.New(rand.NewSource(1))
	reg := func() uint32 {
		switch rng.Intn(4) {
		case 0, 1:
			return scratchBase + uint32(rng.Intn(0x100000))&^3
		case 2:
			return uint32(rng.Intn(256))
		}
		return rng.Uint32()
	}
	var cases strings.Builder
	var inputs []string
	var owners []uint32
	for i, va := range addrs {
		for k := 0; k < perFunc; k++ {
			line := fmt.Sprintf("%d %x %x %x %x %x %x %x %x", i, reg(), reg(), reg(), reg(), reg(), reg(), reg(), 1+rng.Intn(8))
			cases.WriteString(line + "\n")
			inputs = append(inputs, line)
			owners = append(owners, va)
		}
	}

	run := func(cmd *exec.Cmd) []string {
		cmd.Stdin = strings.NewReader(cases.String())
		var out, stderr bytes.Buffer
		cmd.Stdout, cmd.Stderr = &out, &stderr
		if err := cmd.Run(); err != nil {
			t.Fatalf("%s: %v\n%s", cmd.Path, err, stderr.String())
		}
		var lines []string
		sc := bufio.NewScanner(&out)
		for sc.Scan() {
			lines = append(lines, sc.Text())
		}
		return lines
	}
	cOut := run(exec.Command(filepath.Join(dir, "harness"), filepath.Join(dir, "image.bin")))
	uOut := run(exec.Command(python, "testdata/unicorn_ref.py", filepath.Join(dir, "image.bin"), filepath.Join(dir, "funcs.txt")))
	if len(cOut) != len(inputs) || len(uOut) != len(inputs) {
		t.Fatalf("got %d harness and %d reference results for %d cases", len(cOut), len(uOut), len(inputs))
	}

	compared := 0
	var bad []caseResult
	for i := range inputs {
		if uOut[i] == "fault" {
			continue // the real CPU could not finish this case either
		}
		compared++
		if cOut[i] != uOut[i] {
			bad = append(bad, caseResult{fn: owners[i], in: inputs[i], c: cOut[i], u: uOut[i]})
		}
	}
	return compared, bad
}

// imageBlob serializes the XBE as loaded: header page and every section,
// zero-fill included. Writable sections are flagged for hashing.
func imageBlob(f *xbe.File) []byte {
	var b bytes.Buffer
	rec := func(va uint32, data []byte, writable bool) {
		n := uint32(len(data))
		if writable {
			n |= 0x80000000
		}
		binary.Write(&b, binary.LittleEndian, va)
		binary.Write(&b, binary.LittleEndian, n)
		b.Write(data)
	}
	hdr, _ := f.Bytes(f.Header.BaseAddress, f.Header.SizeOfHeaders)
	rec(f.Header.BaseAddress, hdr, false)
	for i := range f.Sections {
		s := &f.Sections[i]
		data := make([]byte, s.VirtualSize)
		copy(data, f.SectionData(s))
		rec(s.VirtualAddr, data, s.Flags&xbe.SecWritable != 0)
	}
	return b.Bytes()
}

func report(t *testing.T, compared int, bad []caseResult) {
	t.Helper()
	t.Logf("%d cases compared, %d mismatches", compared, len(bad))
	byFunc := map[uint32]int{}
	for _, r := range bad {
		byFunc[r.fn]++
	}
	for i, r := range bad {
		if i == 20 {
			t.Errorf("... %d more mismatches in %d functions", len(bad)-20, len(byFunc))
			break
		}
		t.Errorf("%08X  in: %s\n  recompiled: %s\n  reference:  %s", r.fn, r.in, r.c, r.u)
	}
}

// TestForzaDifferential checks recompiled Forza leaf functions against the
// real instructions.
func TestForzaDifferential(t *testing.T) {
	path := os.Getenv("FORZA_XBE")
	if path == "" {
		t.Skip("set FORZA_XBE to the game's default.xbe to run")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	f, err := xbe.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	p := analysis.Analyze(f)
	tr := &recomp.Translator{P: p, F: f}
	funcs := leafFuncs(tr, p)
	t.Logf("%d fully translated leaf functions", len(funcs))
	compared, bad := runDiff(t, f, funcs, 4)
	report(t, compared, bad)
	if compared < len(funcs) {
		t.Errorf("only %d cases could be compared", compared)
	}
}

// TestEdgeDifferential assembles testdata/edge.s, one function per tricky
// instruction form, and checks each against Unicorn. Unlike the Forza
// test it needs no game files, only gcc, GNU as/objcopy and unicorn.
func TestEdgeDifferential(t *testing.T) {
	tools(t)
	for _, tool := range []string{"as", "objcopy"} {
		if _, err := exec.LookPath(tool); err != nil {
			t.Skipf("%s not found", tool)
		}
	}
	dir := t.TempDir()
	obj, bin := filepath.Join(dir, "edge.o"), filepath.Join(dir, "edge.bin")
	if out, err := exec.Command("as", "--32", "-o", obj, "testdata/edge.s").CombinedOutput(); err != nil {
		t.Fatalf("as: %v\n%s", err, out)
	}
	if out, err := exec.Command("objcopy", "-O", "binary", "-j", ".text", obj, bin).CombinedOutput(); err != nil {
		t.Fatalf("objcopy: %v\n%s", err, out)
	}
	code, err := os.ReadFile(bin)
	if err != nil {
		t.Fatal(err)
	}
	src, _ := os.ReadFile("testdata/edge.s")
	cases := strings.Count(string(src), "\nf_")

	const text = 0x11000
	raw := xbetest.Image{
		Title: "Edge", Entry: text, Thunk: 0x80000,
		Sections: []xbetest.Section{
			{Name: ".text", VA: text, Data: code, Flags: xbe.SecExecutable},
			{Name: ".rdata", VA: 0x80000, Data: xbetest.Thunks(187)},
			{Name: ".data", VA: 0x90000, Data: make([]byte, 0x100), Flags: xbe.SecWritable},
		},
	}.Build()
	f, err := xbe.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	var seeds []uint32
	for off := 0; off < len(code); off += 256 {
		seeds = append(seeds, text+uint32(off))
	}
	p := analysis.Analyze(f, seeds...)
	tr := &recomp.Translator{P: p, F: f}
	funcs := leafFuncs(tr, p)
	if len(funcs) != cases {
		for _, va := range seeds {
			if _, ok := funcs[va]; !ok {
				t.Errorf("case at %#x not testable: %v", va, tr.Function(va).Unsupported)
			}
		}
		t.Fatalf("%d of %d cases testable", len(funcs), cases)
	}
	compared, bad := runDiff(t, f, funcs, 40)
	report(t, compared, bad)
	if compared < cases*20 {
		t.Errorf("only %d of %d cases ran on the reference CPU", compared, cases*40)
	}
}
