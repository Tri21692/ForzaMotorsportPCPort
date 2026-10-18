package sigdb_test

import (
	"os"
	"path/filepath"
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
    XREF_ENTRY(0x02, XREF_KT_FUNC_NtClose),
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

func writeDB(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	files := map[string]string{
		"src/OOVPADatabase/Xapi_OOVPA.c":     xapiTable,
		"src/OOVPADatabase/Xapi/3911.inl":    xapi3911,
		"src/OOVPADatabase/Xapi/5849.inl":    xapi5849,
		"src/lib/libXbSymbolDatabase.c":      libSource,
		"src/OOVPADatabase/D3D8_OOVPA.c":     "",
		"src/OOVPADatabase/DSound_OOVPA.c":   "",
		"src/OOVPADatabase/XActEng_OOVPA.c":  "",
		"src/OOVPADatabase/XGraphic_OOVPA.c": "",
		"src/OOVPADatabase/XOnline_OOVPA.c":  "",
		"src/OOVPADatabase/XNet_OOVPA.c":     "",
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
	if got := len(foo.Revisions[1].Sig.Bytes); got != 5 {
		t.Errorf("Foo_4 5849 has %d bytes, want 5 from OV_MATCH", got)
	}
	if v := syms["g_Var"]; v == nil || v.Kind != sigdb.Variable || v.Scan != sigdb.ScanManual || len(v.Revisions) != 0 {
		t.Errorf("g_Var = %+v (dummy signature should leave no revisions)", v)
	}
	if q := syms["Qux"]; q == nil || len(q.Revisions[0].Sig.XRefs) != 1 || q.Revisions[0].Sig.XRefs[0].Name != "KT_FUNC_NtClose" {
		t.Errorf("Qux = %+v", q)
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
	if len(ms) < 400 {
		t.Errorf("only %d symbols", len(ms))
	}
}
