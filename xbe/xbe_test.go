package xbe_test

import (
	"errors"
	"os"
	"testing"

	"github.com/Tri21692/ForzaMotorsportPC/internal/xbetest"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func sample(debug bool) xbetest.Image {
	return xbetest.Image{
		Title:   "Test Title",
		TitleID: 0x4D53006E,
		Entry:   0x11000,
		Thunk:   0x20000,
		Debug:   debug,
		Sections: []xbetest.Section{
			{Name: ".text", VA: 0x11000, Data: []byte{0xC3}, Flags: xbe.SecPreload | xbe.SecExecutable},
			{Name: ".rdata", VA: 0x20000, Data: xbetest.Thunks(187, 156, 999), Flags: xbe.SecPreload},
			{Name: ".data", VA: 0x30000, Data: []byte{1, 2, 3, 4}, BSS: 0x100, Flags: xbe.SecWritable | xbe.SecPreload},
		},
	}
}

func TestParse(t *testing.T) {
	for _, debug := range []bool{false, true} {
		f, err := xbe.Parse(sample(debug).Build())
		if err != nil {
			t.Fatal(err)
		}
		if f.Debug != debug {
			t.Errorf("Debug = %v, want %v", f.Debug, debug)
		}
		if f.EntryPoint != 0x11000 || f.KernelThunk != 0x20000 {
			t.Errorf("entry %#x thunk %#x", f.EntryPoint, f.KernelThunk)
		}
		if f.Certificate.TitleName != "Test Title" || f.Certificate.TitleID != 0x4D53006E {
			t.Errorf("certificate %+v", f.Certificate)
		}
		if len(f.Libraries) != 1 || f.Libraries[0].String() != "XAPILIB 1.0.5849" {
			t.Errorf("libraries %v", f.Libraries)
		}
		if len(f.Sections) != 3 || f.Sections[1].Name != ".rdata" {
			t.Fatalf("sections %+v", f.Sections)
		}
		for i := range f.Sections {
			if !f.VerifyDigest(&f.Sections[i]) {
				t.Errorf("%s digest mismatch", f.Sections[i].Name)
			}
		}
	}
}

func TestKernelImports(t *testing.T) {
	f, err := xbe.Parse(sample(false).Build())
	if err != nil {
		t.Fatal(err)
	}
	want := []struct {
		name string
		conv xbe.CallConv
		args int
	}{
		{"NtClose", xbe.Stdcall, 4},
		{"KeTickCount", xbe.Data, 0},
		{"KernelOrdinal999", xbe.Stdcall, 0},
	}
	if len(f.Kernel) != len(want) {
		t.Fatalf("got %d imports, want %d", len(f.Kernel), len(want))
	}
	for i, w := range want {
		k := f.Kernel[i]
		if k.Name != w.name || k.Conv != w.conv || k.ArgBytes != w.args || k.Slot != 0x20000+4*uint32(i) {
			t.Errorf("import %d = %+v, want %s %v/%d", i, k, w.name, w.conv, w.args)
		}
	}
	if k, ok := f.KernelBySlot(0x20004); !ok || k.Name != "KeTickCount" {
		t.Errorf("KernelBySlot(0x20004) = %+v, %v", k, ok)
	}
	if _, ok := f.KernelBySlot(0x20002); ok {
		t.Error("KernelBySlot accepted a misaligned slot")
	}
	if _, ok := f.KernelBySlot(0x2000C); ok {
		t.Error("KernelBySlot accepted the terminator")
	}
}

func TestKernelTable(t *testing.T) {
	for ord, name := range map[uint32]string{
		1: "AvGetSavedDataAddress", 49: "HalReturnToFirmware", 187: "NtClose",
		255: "PsCreateSystemThreadEx", 327: "XeLoadSection",
	} {
		if k, ok := xbe.LookupKernel(ord); !ok || k.Name != name {
			t.Errorf("ordinal %d = %q, want %q", ord, k.Name, name)
		}
	}
	if k, _ := xbe.LookupKernel(250); k.Conv != xbe.Fastcall {
		t.Errorf("ObfDereferenceObject conv = %v, want fastcall", k.Conv)
	}
	if k, _ := xbe.LookupKernel(8); k.Conv != xbe.Cdecl {
		t.Errorf("DbgPrint conv = %v, want cdecl", k.Conv)
	}
}

func TestBytes(t *testing.T) {
	f, err := xbe.Parse(sample(false).Build())
	if err != nil {
		t.Fatal(err)
	}
	if v, err := f.Uint32(0x30000); err != nil || v != 0x04030201 {
		t.Errorf("Uint32(.data) = %#x, %v", v, err)
	}
	if _, err := f.Bytes(0x30010, 4); !errors.Is(err, xbe.ErrZeroFill) {
		t.Errorf("BSS read error = %v, want ErrZeroFill", err)
	}
	if _, err := f.Bytes(0x300FE, 8); err == nil || errors.Is(err, xbe.ErrZeroFill) {
		t.Errorf("read past section end error = %v", err)
	}
	if _, err := f.Bytes(0x50000, 1); err == nil {
		t.Error("unmapped read succeeded")
	}
	if b, err := f.Bytes(xbetest.Base, 4); err != nil || string(b) != "XBEH" {
		t.Errorf("header read = %q, %v", b, err)
	}
}

func TestParseRejects(t *testing.T) {
	if _, err := xbe.Parse([]byte("MZ not an xbe")); err == nil {
		t.Error("accepted a non-XBE")
	}
	raw := sample(false).Build()
	if _, err := xbe.Parse(raw[:0x1800]); err == nil {
		t.Error("accepted a truncated XBE")
	}
}

// TestForza checks the real game when FORZA_XBE points at its default.xbe.
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
	if f.Certificate.TitleID != 0x4D53006E || f.Certificate.TitleName != "Forza Motorsport" {
		t.Fatalf("not Forza Motorsport: %+v", f.Certificate)
	}
	if f.Debug || f.EntryPoint != 0x268EB5 || f.KernelThunk != 0x485D80 {
		t.Errorf("entry %#x thunk %#x debug %v", f.EntryPoint, f.KernelThunk, f.Debug)
	}
	if len(f.Sections) != 39 || len(f.Kernel) != 159 || len(f.Libraries) != 12 {
		t.Errorf("%d sections, %d kernel imports, %d libraries", len(f.Sections), len(f.Kernel), len(f.Libraries))
	}
	for _, k := range f.Kernel {
		if _, ok := xbe.LookupKernel(k.Ordinal); !ok {
			t.Errorf("unknown kernel ordinal %d", k.Ordinal)
		}
	}
}
