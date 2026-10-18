package recomp_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/internal/xbetest"
	"github.com/Tri21692/ForzaMotorsportPC/recomp"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// program builds a small XBE exercising each kind of control transfer.
func program(t *testing.T) (*recomp.Translator, *analysis.Program) {
	t.Helper()
	text := make([]byte, 0x80)
	for i := range text {
		text[i] = 0xCC
	}
	at := func(va uint32, b ...byte) { copy(text[va-0x11000:], b) }

	// 11000 entry: call 11010; call [NtClose]; jmp 11040 (tail call)
	at(0x11000, 0xE8, 0x0B, 0, 0, 0)
	at(0x11005, 0xFF, 0x15, 0x00, 0x00, 0x02, 0x00)
	at(0x1100B, 0xE9, 0x30, 0, 0, 0)
	// 11010: switch on eax through a table at 11024
	at(0x11010, 0x83, 0xF8, 0x02)
	at(0x11013, 0x77, 0x0D)
	at(0x11015, 0xFF, 0x24, 0x85, 0x24, 0x10, 0x01, 0x00)
	at(0x1101C, 0xB0, 0x00, 0xC3)
	at(0x1101F, 0xB0, 0x01, 0xC3)
	at(0x11022, 0xC3)
	tbl := xbetest.Le32(nil, 0x1101C)
	tbl = xbetest.Le32(tbl, 0x1101F)
	tbl = xbetest.Le32(tbl, 0x11022)
	at(0x11024, tbl...)
	at(0x11030, 0xFF, 0xFF, 0xFF, 0xFF)
	// 11040: an x87 load, not supported yet; then ret 4
	at(0x11040, 0xD9, 0x44, 0x24, 0x04, 0xC2, 0x04, 0x00)

	f, err := xbe.Parse(xbetest.Image{
		Title: "Recomp", Entry: 0x11000, Thunk: 0x20000,
		Sections: []xbetest.Section{
			{Name: ".text", VA: 0x11000, Data: text, Flags: xbe.SecExecutable},
			{Name: ".rdata", VA: 0x20000, Data: xbetest.Thunks(187)},
		},
	}.Build())
	if err != nil {
		t.Fatal(err)
	}
	p := analysis.Analyze(f, 0x11040)
	return &recomp.Translator{P: p, F: f, Names: map[uint32]string{0x11010: "Switch"}}, p
}

func TestControlFlow(t *testing.T) {
	tr, _ := program(t)
	entry := tr.Function(0x11000).Code
	for _, want := range []string{
		"xb_push(c, 0x00011005u); f_00011010(c); /* Switch */",
		"xb_push(c, 0x0001100Bu); xb_kernel(c, 187); /* NtClose */",
		"{ f_00011040(c); return; }",
	} {
		if !strings.Contains(entry, want) {
			t.Errorf("entry lacks %q:\n%s", want, entry)
		}
	}

	sw := tr.Function(0x11010).Code
	for _, want := range []string{
		"if ((!cf && !zf)) goto L_00011022;",
		"case 0x0001101Cu: goto L_0001101C;",
		"L_0001101F:;",
		"c->esp += 4; return;",
	} {
		if !strings.Contains(sw, want) {
			t.Errorf("switch lacks %q:\n%s", want, sw)
		}
	}
	if strings.Contains(sw, "L_00011013:") {
		t.Error("label emitted for an address nothing jumps to")
	}

	x87 := tr.Function(0x11040)
	if x87.Unsupported["x87 FLD"] != 1 || !strings.Contains(x87.Code, `xb_trap(c, 0x00011040, "unsupported: x87 FLD");`) {
		t.Errorf("x87 FLD not trapped: %v\n%s", x87.Unsupported, x87.Code)
	}
	if !strings.Contains(x87.Code, "c->esp += 8; return;") {
		t.Errorf("ret 4 not translated:\n%s", x87.Code)
	}
}

// TestSwitchReadsTable checks the switch reads the table entry, not the
// table address. This is the jmp dword ptr [table + eax*4] form.
func TestSwitchReadsTable(t *testing.T) {
	tr, _ := program(t)
	sw := tr.Function(0x11010).Code
	if !strings.Contains(sw, "switch (xb_rd32((uint32_t)(c->eax * 4 + 0x00011024u)))") {
		t.Errorf("switch does not load the table entry:\n%s", sw)
	}
}

// TestProgramCompiles writes a whole translated program and builds it with
// gcc, which catches C the translator emits but a compiler rejects.
func TestProgramCompiles(t *testing.T) {
	if _, err := exec.LookPath("gcc"); err != nil {
		t.Skip("gcc not found")
	}
	tr, p := program(t)
	var funcs []uint32
	for va := range p.Funcs {
		funcs = append(funcs, va)
	}
	files, out := tr.Program(funcs, 2)
	if len(out) != len(funcs) {
		t.Fatalf("translated %d of %d functions", len(out), len(funcs))
	}
	dir := t.TempDir()
	hdr, _ := recomp.Runtime.ReadFile("runtime/xbrt.h")
	files["xbrt.h"] = string(hdr)
	var srcs []string
	for name, body := range files {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
		if strings.HasSuffix(name, ".c") {
			srcs = append(srcs, filepath.Join(dir, name))
		}
	}
	for _, src := range srcs {
		cmd := exec.Command("gcc", "-std=c11", "-Wall", "-Werror", "-Wno-unused-label", "-c", "-o", os.DevNull, src)
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Errorf("%s: %v\n%s", filepath.Base(src), err, out)
		}
	}
}
