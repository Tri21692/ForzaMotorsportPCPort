package analysis_test

import (
	"os"
	"slices"
	"testing"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/internal/xbetest"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// testImage holds one function for each way of discovering code.
func testImage() []byte {
	text := make([]byte, 0x80)
	for i := range text {
		text[i] = 0xCC
	}
	at := func(va uint32, b ...byte) { copy(text[va-0x11000:], b) }

	// 11000 entry: call 11010; call [NtClose slot]; ret
	at(0x11000, 0xE8, 0x0B, 0, 0, 0)
	at(0x11005, 0xFF, 0x15, 0x00, 0x00, 0x02, 0x00)
	at(0x1100B, 0xC3)

	// 11010: three-way switch through a jump table at 11024
	at(0x11010, 0x83, 0xF8, 0x02) // cmp eax, 2
	at(0x11013, 0x77, 0x0D)       // ja 11022
	at(0x11015, 0xFF, 0x24, 0x85, 0x24, 0x10, 0x01, 0x00)
	at(0x1101C, 0xB0, 0x00, 0xC3) // case 0: mov al, 0; ret
	at(0x1101F, 0xB0, 0x01, 0xC3) // case 1
	at(0x11022, 0xC3)             // case 2 and default
	tbl := xbetest.Le32(nil, 0x1101C)
	tbl = xbetest.Le32(tbl, 0x1101F)
	tbl = xbetest.Le32(tbl, 0x11022)
	at(0x11024, tbl...)
	at(0x11030, 0xFF, 0xFF, 0xFF, 0xFF)

	// 11040, 11050: only reachable through a vtable in .rdata
	at(0x11040, 0x33, 0xC0, 0xC3) // xor eax, eax; ret
	at(0x11050, 0x33, 0xC0, 0xC3)
	// 11060: never referenced, but has a standard prologue
	at(0x11060, 0x55, 0x8B, 0xEC, 0x5D, 0xC3)
	// 11070: referenced by a single pointer only, so not trusted
	at(0x11070, 0xB8, 1, 0, 0, 0, 0xC3)

	rdata := xbetest.Thunks(187)
	rdata = xbetest.Le32(rdata, 0x11040)
	rdata = xbetest.Le32(rdata, 0x11050)
	rdata = xbetest.Le32(rdata, 0)
	rdata = xbetest.Le32(rdata, 0x11070)
	rdata = xbetest.Le32(rdata, 0)

	return xbetest.Image{
		Title: "Analysis", Entry: 0x11000, Thunk: 0x20000,
		Sections: []xbetest.Section{
			{Name: ".text", VA: 0x11000, Data: text, Flags: xbe.SecPreload | xbe.SecExecutable},
			{Name: ".rdata", VA: 0x20000, Data: rdata, Flags: xbe.SecPreload},
		},
	}.Build()
}

func TestAnalyze(t *testing.T) {
	f, err := xbe.Parse(testImage())
	if err != nil {
		t.Fatal(err)
	}
	p := analysis.Analyze(f)

	want := map[uint32]analysis.Source{
		0x11000: analysis.FromEntry,
		0x11010: analysis.FromCall,
		0x11040: analysis.FromDataRef,
		0x11050: analysis.FromDataRef,
		0x11060: analysis.FromPrologue,
	}
	var got []uint32
	for _, fn := range p.Sorted() {
		got = append(got, fn.Addr)
		if w, ok := want[fn.Addr]; !ok || fn.Source != w {
			t.Errorf("function %#x found by %v, want %v (expected: %v)", fn.Addr, fn.Source, w, ok)
		}
	}
	if len(got) != len(want) {
		t.Errorf("functions %x, want %d of them", got, len(want))
	}

	entry := p.Funcs[0x11000]
	if !slices.Equal(entry.Calls, []uint32{0x11010}) || !slices.Equal(entry.KernelCalls, []uint32{187}) {
		t.Errorf("entry calls %x kernel %v", entry.Calls, entry.KernelCalls)
	}
	sw := p.Funcs[0x11010]
	if sw.JumpTables != 1 || sw.Insns != 8 || sw.End != 0x11023 || sw.Unresolved != 0 {
		t.Errorf("switch function %+v", sw)
	}
	if p.Owner[0x1101F] != 0x11010 {
		t.Errorf("case 1 owned by %#x", p.Owner[0x1101F])
	}
	if !p.Code[".text"] || p.Code[".rdata"] {
		t.Errorf("code sections %v", p.Code)
	}
}

// TestForza guards discovery quality on the real game: if a change drops
// coverage or brings back the false starts the filters removed, it fails.
func TestForza(t *testing.T) {
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
	var textBytes, bad int
	for _, fn := range p.Funcs {
		if fn.Section == ".text" {
			textBytes += fn.Bytes
		}
		if fn.BadDecode {
			bad++
		}
	}
	text := f.Sections[0]
	if cover := float64(textBytes) / float64(text.RawSize); cover < 0.85 {
		t.Errorf(".text coverage %.1f%%, want at least 85%%", 100*cover)
	}
	if bad > 100 {
		t.Errorf("%d functions hit undecodable bytes, want at most 100", bad)
	}
	if len(p.Funcs) < 15000 {
		t.Errorf("only %d functions found", len(p.Funcs))
	}
}
