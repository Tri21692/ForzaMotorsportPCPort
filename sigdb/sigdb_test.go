package sigdb_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Tri21692/ForzaMotorsportPC/internal/xbetest"
	"github.com/Tri21692/ForzaMotorsportPC/sigdb"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// A miniature XbSymbolDatabase checkout, written in the same syntax as the
// real one, covering each feature the parser and scanner support.
const xapiTable = `
#include "OOVPA_databases.h"
#include "Xapi/3911.inl"
#include "Xapi/5849.inl"

static OOVPATable XAPILIB_OOVPA_Table[] = {
    REGISTER_OOVPAS_M(SYM_VAR(g_Var),
                      SYM_SIG(3911)),
    // Bar needs Foo, which is registered after it: takes a second pass.
    REGISTER_OOVPAS(SYM_FUN(Bar, CALL(std), STACK(/*default*/), PARAMS(PARAM1(void))),
                    SYM_SIG(3911)),
    REGISTER_OOVPAS(SYM_FUN(Baz, CALL(std), STACK(/*default*/), PARAMS(PARAM1(void))),
                    SYM_SIG(3911)),
    REGISTER_OOVPAS(SYM_FUN(Qux, CALL(std), STACK(/*default*/), PARAMS(PARAM1(void))),
                    SYM_SIG(3911)),
    REGISTER_OOVPAS(SYM_FUN(Foo, CALL(std), STACK(4), PARAMS(PARAM(psh, x))),
                    SYM_SIG(3911, 5849)),
    REGISTER_OOVPAS(SYM_FUN(Zed, CALL(std), STACK(/*default*/), PARAMS(PARAM1(void))),
                    SYM_SIG(6000)),
    REGISTER_OOVPAS_M(SYM_FUN(Manual, CALL(std), STACK(/*default*/), PARAMS(PARAM1(void))),
                      SYM_SIG(3911)),
};
`

const xapi3911 = `
// SPDX-License-Identifier: ODbL-1.0
OOVPA_SIG_HEADER_NO_XREF(g_Var,
                         3911)
OOVPA_SIG_MATCH_DUMMY();

OOVPA_SIG_HEADER_XREF(Bar,
                      3911,
                      XRefOne)
OOVPA_SIG_MATCH(
    // call Foo
    XREF_ENTRY(0x01, XREF_Foo),
    { 0x00, 0xE8 },
    { 0x05, 0xC3 },
    //
);

OOVPA_SIG_HEADER_XREF(Baz,
                      3911,
                      XRefOne)
OOVPA_SIG_MATCH(
    /* mov eax, [g_Var] */
    XREF_ENTRY(0x01, XREF_g_Var),
    OV_MATCH(0x00, 0xA1),
    { 0x05, 0xC3 },
);

OOVPA_SIG_HEADER_XREF(Qux,
                      3911,
                      XRefOne)
OOVPA_SIG_MATCH(
    // Written as OV_MATCH, but the header's XRef count makes the first
    // entry an XRef, exactly as the C matcher reads it.
    OV_MATCH(0x02, XREF_KT_FUNC_NtClose),
    OV_MATCH(0x00, 0xFF, 0x15),
    { 0x06, 0xC3 },
);

OOVPA_SIG_HEADER_NO_XREF(Foo_4,
                         3911)
OOVPA_SIG_MATCH(
    { 0x00, 0x55 }, { 0x01, 0x8B }, { 0x02, 0xEC },
);

OOVPA_SIG_HEADER_NO_XREF(Manual,
                         3911)
OOVPA_SIG_MATCH(
    OV_MATCH(0x00, 0x90, 0x90, 0x90, 0xC3),
);

#if 0 // a broken signature, never compiled
OOVPA_SIG_HEADER_NO_XREF(Broken, 3911)
OOVPA_SIG_MATCH( { 0x00, nonsense } );
#endif
`

const xapi5849 = `
OOVPA_SIG_HEADER_NO_XREF(Foo_4,
                         5849)
OOVPA_SIG_MATCH(
    OV_MATCH(0x00, 0x55, 0x8B, 0xEC, 0x33, 0xC0),
);

OOVPA_SIG_HEADER_NO_XREF(Zed,
                         6000)
OOVPA_SIG_MATCH(
    OV_MATCH(0x00, 0x90, 0x90, 0x90, 0xC3),
);
`

const libSource = `
    pContext->xref_database[XREF_g_Var] = XREF_ADDR_DERIVE; //In use
`

// renderStates builds a manual_d3d8__ltcg.h with the 167-entry table the
// loader insists on; only its shape matters to these tests.
func renderStates() string {
	var b strings.Builder
	b.WriteString("static const RenderStateRevision DxbxRenderStateInfo[] = {\n")
	for i := 0; i < 167; i++ {
		if i == 136 {
			b.WriteString("    { 3424, 0000, XREF_NAME(D3DRS_PSTextureModes) },\n")
			continue
		}
		b.WriteString("    { 3424, 0000 /*, XREF_NAME(D3DRS_X) */ },\n")
	}
	b.WriteString("};\n")
	return b.String()
}

func emptyTable(name string) string {
	return "static OOVPATable " + name + "[] = {\n};\n"
}

func writeDB(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	files := map[string]string{
		"src/OOVPADatabase/Xapi_OOVPA.c":     xapiTable,
		"src/OOVPADatabase/Xapi/3911.inl":    xapi3911,
		"src/OOVPADatabase/Xapi/5849.inl":    xapi5849,
		"src/lib/libXbSymbolDatabase.c":      libSource,
		"src/lib/manual_d3d8__ltcg.h":        renderStates(),
		"src/OOVPADatabase/D3D8_OOVPA.c":     emptyTable("D3D8_OOVPA_Table"),
		"src/OOVPADatabase/DSound_OOVPA.c":   emptyTable("DSound_OOVPA_manual_Table") + emptyTable("DSound_OOVPA_Table"),
		"src/OOVPADatabase/XActEng_OOVPA.c":  emptyTable("XACTENG_OOVPA_Table"),
		"src/OOVPADatabase/XGraphic_OOVPA.c": emptyTable("XGRAPHC_OOVPA_Table"),
		"src/OOVPADatabase/XOnline_OOVPA.c":  emptyTable("XONLINE_OOVPA_Table"),
		"src/OOVPADatabase/XNet_OOVPA.c":     emptyTable("XNET_OOVPA_Table"),
	}
	for name, body := range files {
		p := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func testXBE(t *testing.T) *xbe.File {
	t.Helper()
	text := make([]byte, 0x40)
	for i := range text {
		text[i] = 0xCC
	}
	at := func(va uint32, b ...byte) { copy(text[va-0x11000:], b) }
	at(0x11000, 0xE8, 0x1B, 0, 0, 0, 0xC3)                // Bar: call Foo; ret
	at(0x11010, 0xA1, 0x00, 0x00, 0x03, 0x00, 0xC3)       // Baz: mov eax, [30000]; ret
	at(0x11018, 0xFF, 0x15, 0x00, 0x00, 0x02, 0x00, 0xC3) // Qux: call [NtClose]; ret
	at(0x11020, 0x55, 0x8B, 0xEC, 0x33, 0xC0, 0x5D, 0xC3) // Foo
	at(0x11030, 0x90, 0x90, 0x90, 0xC3)                   // Zed / Manual

	raw := xbetest.Image{
		Title: "Sigs", Entry: 0x11000, Thunk: 0x20000,
		Sections: []xbetest.Section{
			{Name: ".text", VA: 0x11000, Data: text, Flags: xbe.SecExecutable},
			{Name: ".rdata", VA: 0x20000, Data: xbetest.Thunks(187)},
			{Name: ".data", VA: 0x30000, Data: make([]byte, 16), Flags: xbe.SecWritable},
		},
	}.Build()
	f, err := xbe.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	return f
}

func TestLoad(t *testing.T) {
	db, err := sigdb.Load(writeDB(t))
	if err != nil {
		t.Fatal(err)
	}
	if !db.Derive["g_Var"] {
		t.Error("g_Var not marked derive")
	}
	if len(db.RenderStates) != 167 || db.RenderStates[136].XRef != "D3DRS_PSTextureModes" || db.RenderStates[0].XRef != "" {
		t.Errorf("render states: %d entries, [136] = %+v", len(db.RenderStates), db.RenderStates[136])
	}
	var xapi *sigdb.LibraryDB
	for _, tbl := range db.Tables {
		if tbl.Libraries[0] == "XAPILIB" {
			xapi = tbl
		}
	}
	syms := map[string]*sigdb.Symbol{}
	for _, s := range xapi.Symbols {
		syms[s.Name] = s
	}
	foo := syms["Foo_4"]
	if foo == nil || foo.XRef != "Foo" || foo.Conv != "std" || len(foo.Revisions) != 2 || foo.Revisions[1].Version != 5849 {
		t.Fatalf("Foo_4 = %+v", foo)
	}
	if len(foo.Params) != 1 || foo.Params[0] != (sigdb.Param{Loc: "psh", Name: "x"}) {
		t.Errorf("Foo_4 params = %+v", foo.Params)
	}
	if p := syms["Bar"].Params; len(p) != 0 {
		t.Errorf("Bar takes void, got params %+v", p)
	}
	if got := len(foo.Revisions[1].Sig.Bytes); got != 5 {
		t.Errorf("Foo_4 5849 has %d bytes, want 5 from OV_MATCH", got)
	}
	if v := syms["g_Var"]; v == nil || v.Kind != sigdb.Variable || v.Scan != sigdb.ScanManual || len(v.Revisions) != 0 {
		t.Errorf("g_Var = %+v (dummy signature should leave no revisions)", v)
	}
	if q := syms["Qux"]; q == nil || len(q.Revisions[0].Sig.XRefs) != 1 || q.Revisions[0].Sig.XRefs[0] != (sigdb.XRef{Off: 2, Name: "KT_FUNC_NtClose"}) || len(q.Revisions[0].Sig.Bytes) != 3 {
		t.Errorf("Qux = %+v", q.Revisions[0].Sig)
	}
}

func TestScan(t *testing.T) {
	db, err := sigdb.Load(writeDB(t))
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]sigdb.Match{}
	for _, m := range sigdb.Scan(testXBE(t), db) {
		got[m.Name] = m
	}
	want := map[string]uint32{
		"Bar": 0x11000, "Baz": 0x11010, "Qux": 0x11018, "Foo_4": 0x11020, "g_Var": 0x30000,
	}
	for name, addr := range want {
		if m, ok := got[name]; !ok || m.Addr != addr {
			t.Errorf("%s = %+v, want address %#x", name, m, addr)
		}
	}
	if len(got) != len(want) {
		t.Errorf("got %v", got)
	}
	if v := got["Foo_4"].Version; v != 5849 {
		t.Errorf("Foo_4 matched revision %d, want the highest allowed (5849)", v)
	}
	if !got["g_Var"].Derived || got["g_Var"].Kind != sigdb.Variable {
		t.Errorf("g_Var = %+v, want a derived variable", got["g_Var"])
	}
	if got["Bar"].Library != "XAPILIB" {
		t.Errorf("Bar library = %q", got["Bar"].Library)
	}
}

// TestForza runs the real database over the real game when both are given.
func TestForza(t *testing.T) {
	path, root := os.Getenv("FORZA_XBE"), os.Getenv("XBSDB")
	if path == "" || root == "" {
		t.Skip("set FORZA_XBE and XBSDB (an XbSymbolDatabase checkout) to run")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	f, err := xbe.Parse(raw)
	if err != nil {
		t.Fatal(err)
	}
	db, err := sigdb.Load(root)
	if err != nil {
		t.Fatal(err)
	}
	ms := sigdb.Scan(f, db)
	byName := map[string]uint32{}
	seen := map[uint32]string{}
	for _, m := range ms {
		byName[m.Name] = m.Addr
		if m.Kind != sigdb.Function {
			continue
		}
		if other, dup := seen[m.Addr]; dup {
			t.Errorf("%s and %s both at %#x", other, m.Name, m.Addr)
		}
		seen[m.Addr] = m.Name
	}
	// The CRT entry the signatures find must be the XBE's own entry point.
	if a := byName["mainCRTStartup"]; a != f.EntryPoint {
		t.Errorf("mainCRTStartup at %#x, entry point %#x", a, f.EntryPoint)
	}
	// Values XbSymbolDatabase's own CLI printed for this XBE (507 symbols,
	// all of which this scan reproduces at the same addresses). These come
	// from the hand-written scans, so they guard manual.go.
	for name, want := range map[string]uint32{
		"D3D_g_RenderState":                0x3C87B0,
		"D3DRS_CullMode":                   0x3C89FC,
		"D3DDevice_SetRenderState_Simple":  0x3B7500,
		"CDirectSoundStream_AddRef":        0x3F2049,
		"CDirectSoundStream_GetStatus__r2": 0x3F21DD,
		"g_DeviceType_Gamepad":             0x47CFBC,
		"XGetSectionSize":                  0x268076,
		"D3DDevice__m_SwapCallback_OFFSET": 0x1DB4,
		"XInputClose":                      0x47E5FC,
	} {
		if got, ok := byName[name]; !ok || got != want {
			t.Errorf("%s = %#x (found %v), want %#x", name, got, ok, want)
		}
	}
	if len(ms) < 507 {
		t.Errorf("%d symbols, want at least the reference's 507", len(ms))
	}
}

func TestScanCRT(t *testing.T) {
	allmul := []byte{0x8B, 0x44, 0x24, 0x08, 0x8B, 0x4C, 0x24, 0x10, 0x0B, 0xC8, 0x8B, 0x4C, 0x24, 0x0C,
		0x75, 0x09, 0x8B, 0x44, 0x24, 0x04, 0xF7, 0xE1, 0xC2, 0x10, 0x00}
	wcslen := []byte{0x8B, 0x44, 0x24, 0x04, 0x66, 0x8B, 0x08, 0x40, 0x40, 0x66, 0x85, 0xC9, 0x75, 0xF6,
		0x2B, 0x44, 0x24, 0x04, 0xD1, 0xF8, 0x48, 0xC3}
	// _chkstk has wildcards at its jump displacements.
	chkstk := []byte{0x85, 0xC0, 0x74, 0x99, 0x3D, 0x00, 0x10, 0x00, 0x00, 0x73, 0x77, 0xF7, 0xD8, 0x03, 0xC4,
		0x83, 0xC0, 0x04, 0x85, 0x00, 0x94, 0x8B, 0x00, 0x50, 0xC3, 0x51, 0x8D, 0x4C, 0x24, 0x08, 0x81, 0xE9}
	text := make([]byte, 0x200)
	copy(text[0x10:], allmul)
	copy(text[0x40:], wcslen)
	copy(text[0x80:], wcslen) // twice: ambiguous, must stay unnamed
	copy(text[0xC0:], chkstk)

	f, err := xbe.Parse(xbetest.Image{
		Title: "CRT", Entry: 0x11000, Thunk: 0x20000,
		Sections: []xbetest.Section{
			{Name: ".text", VA: 0x11000, Data: text, Flags: xbe.SecExecutable},
			{Name: ".rdata", VA: 0x20000, Data: xbetest.Thunks(187)},
		},
	}.Build())
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]uint32{}
	for _, m := range sigdb.ScanCRT(f) {
		got[m.Name] = m.Addr
	}
	want := map[string]uint32{"_allmul": 0x11010, "_chkstk": 0x110C0}
	if len(got) != len(want) {
		t.Errorf("got %v, want %v", got, want)
	}
	for name, addr := range want {
		if got[name] != addr {
			t.Errorf("%s at %#x, want %#x", name, got[name], addr)
		}
	}
}

// TestForzaCRT pins every C runtime pattern to the address it was checked
// against by hand.
func TestForzaCRT(t *testing.T) {
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
	want := map[string]uint32{
		"_ftol2": 0x2F8078, "strncpy": 0x2F8900, "memcpy": 0x2F8A30, "_alldiv": 0x2F8D70,
		"_allmul": 0x2F8E20, "strncat": 0x2F9230, "wcscpy": 0x2F9419, "wcsncpy": 0x2F94A5,
		"_aullshr": 0x2F9830, "_chkstk": 0x2F9B50, "strncmp": 0x2F9C70, "wcslen": 0x2FA266,
		"_allshl": 0x2FA2B0, "_aulldiv": 0x2FA2D0, "_aullrem": 0x2FA490, "_SEH_prolog": 0x2FB0CC,
		"_SEH_epilog": 0x2FB107, "_allrem": 0x2FB720, "_EH_prolog": 0x2FC130,
	}
	got := map[string]uint32{}
	for _, m := range sigdb.ScanCRT(f) {
		got[m.Name] = m.Addr
	}
	for name, addr := range want {
		if got[name] != addr {
			t.Errorf("%s at %#x, want %#x", name, got[name], addr)
		}
	}
	if len(got) != len(want) {
		t.Errorf("found %d CRT functions, want %d", len(got), len(want))
	}
}
