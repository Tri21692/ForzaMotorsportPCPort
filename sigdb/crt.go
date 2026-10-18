package sigdb

import (
	"bytes"
	"strconv"
	"strings"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// C runtime functions XbSymbolDatabase does not cover. These patterns are
// our own, written for the XDK 5849 CRT (MSVC 7.1) and checked by hand
// against Forza's disassembly. The compiler helpers matter most to the
// recompiler: 64-bit arithmetic, float-to-int conversion, stack probes and
// SEH frames, which it should turn into native operations rather than
// translate. Forza inlines memset, strlen, strcpy and strcmp as
// intrinsics, so those have no function to name.
//
// "??" is a wildcard byte, used for jump displacements and addresses.
var crtPatterns = []struct {
	name, conv string
	pattern    string
}{
	// 64-bit integer helpers: operands on the stack, result in EDX:EAX.
	{"_allmul", "std", "8B 44 24 08 8B 4C 24 10 0B C8 8B 4C 24 0C 75 09 8B 44 24 04 F7 E1 C2 10 00"},
	{"_alldiv", "std", "57 56 53 33 FF 8B 44 24 14 0B C0 7D 14 47 8B 54 24 10 F7 D8 F7 DA 83 D8 00 89 44 24 14 89 54 24 10"},
	{"_aulldiv", "std", "53 56 8B 44 24 18 0B C0 75 18 8B 4C 24 14 8B 44 24 10 33 D2 F7 F1 8B D8 8B 44 24 0C F7 F1 8B D3"},
	{"_allrem", "std", "53 57 33 FF 8B 44 24 10 0B C0 7D 14 47 8B 54 24 0C F7 D8 F7 DA 83 D8 00 89 44 24 10 89 54 24 0C"},
	{"_aullrem", "std", "53 8B 44 24 14 0B C0 75 18 8B 4C 24 10 8B 44 24 0C 33 D2 F7 F1 8B 44 24 08 F7 F1 8B C2 33 D2"},
	// Shifts: value in EDX:EAX, count in CL.
	{"_allshl", "reg", "80 F9 40 73 15 80 F9 20 73 06 0F A5 C2 D3 E0 C3 8B D0 33 C0 80 E1 1F D3 E2 C3 33 C0 33 D2 C3"},
	{"_aullshr", "reg", "80 F9 40 73 15 80 F9 20 73 06 0F AD D0 D3 EA C3 8B C2 33 D2 80 E1 1F D3 E8 C3 33 C0 33 D2 C3"},
	// x87 ST(0) to a 64-bit integer in EDX:EAX, truncating. Called 817 times.
	{"_ftol2", "reg", "55 8B EC 83 EC 20 83 E4 F0 D9 C0 D9 54 24 18 DF 7C 24 10 DF 6C 24 10 8B 54 24 18 8B 44 24 10 85 C0"},
	// Stack probe for frames of a page or more; size in EAX.
	{"_chkstk", "reg", "85 C0 74 ?? 3D 00 10 00 00 73 ?? F7 D8 03 C4 83 C0 04 85 00 94 8B 00 50 C3 51 8D 4C 24 08 81 E9"},
	// SEH frame setup and teardown used by functions with __try.
	{"_SEH_prolog", "reg", "68 ?? ?? ?? ?? 64 A1 00 00 00 00 50 8B 44 24 10 89 6C 24 10 8D 6C 24 10 2B E0 53 56 57"},
	{"_SEH_epilog", "reg", "8B 4D F0 64 89 0D 00 00 00 00 59 5F 5E 5B C9 51 C3"},
	{"_EH_prolog", "reg", "6A FF 50 64 A1 00 00 00 00 50 8B 44 24 0C 64 89 25 00 00 00 00 89 6C 24 0C 8D 6C 24 0C 50 C3"},
	// String and memory routines that are real calls in this build.
	{"memcpy", "cdecl", "55 8B EC 57 56 8B 75 0C 8B 4D 10 8B 7D 08 8B C1 8B D1 03 C6 3B FE 76 08 3B F8"},
	{"strncpy", "cdecl", "8B 4C 24 0C 57 85 C9 0F 84 ?? ?? ?? ?? 56 53 8B D9 8B 74 24 14 F7 C6 03 00 00 00 8B 7C 24 10 75"},
	{"strncat", "cdecl", "8B 4C 24 0C 57 85 C9 0F 84 ?? ?? ?? ?? 8B 7C 24 08 56 F7 C7 03 00 00 00 53 74 ?? 8A 07 83 C7 01"},
	{"strncmp", "cdecl", "55 8B EC 57 56 53 8B 4D 10 E3 ?? 8B D9 8B 7D 08 8B F7 33 C0 F2 AE F7 D9 03 CB 8B FE 8B 75 0C F3"},
	{"wcslen", "cdecl", "8B 44 24 04 66 8B 08 40 40 66 85 C9 75 F6 2B 44 24 04 D1 F8 48 C3"},
	{"wcscpy", "cdecl", "8B 4C 24 04 8B 54 24 08 66 8B 02 66 89 01 41 41 42 42 66 85 C0 75 F1 8B 44 24 04 C3"},
	{"wcsncpy", "cdecl", "8B 4C 24 0C 85 C9 56 57 8B 7C 24 0C 8B F7 74 ?? 8B 54 24 10 66 8B 02 66 89 07 47 47 42 42 66 85"},
}

type pattern struct {
	bytes []byte
	mask  []bool // true where the byte must match
}

func parsePattern(s string) pattern {
	var p pattern
	for _, tok := range strings.Fields(s) {
		if tok == "??" {
			p.bytes, p.mask = append(p.bytes, 0), append(p.mask, false)
			continue
		}
		v, err := strconv.ParseUint(tok, 16, 8)
		if err != nil {
			panic("sigdb: bad CRT pattern byte " + tok)
		}
		p.bytes, p.mask = append(p.bytes, byte(v)), append(p.mask, true)
	}
	return p
}

// find returns every offset in data where p matches.
func (p pattern) find(data []byte) []int {
	// Anchor on the longest fixed run so bytes.Index does most of the work.
	bestAt, bestLen := 0, 0
	for i := 0; i < len(p.mask); {
		if !p.mask[i] {
			i++
			continue
		}
		j := i
		for j < len(p.mask) && p.mask[j] {
			j++
		}
		if j-i > bestLen {
			bestAt, bestLen = i, j-i
		}
		i = j
	}
	anchor := p.bytes[bestAt : bestAt+bestLen]
	var out []int
	for from := 0; ; {
		k := bytes.Index(data[from:], anchor)
		if k < 0 {
			return out
		}
		base := from + k - bestAt
		from += k + 1
		if base < 0 || base+len(p.bytes) > len(data) {
			continue
		}
		ok := true
		for i, b := range p.bytes {
			if p.mask[i] && data[base+i] != b {
				ok = false
				break
			}
		}
		if ok {
			out = append(out, base)
		}
	}
}

// ScanCRT names C runtime functions in .text. A pattern counts only if it
// matches exactly once; an ambiguous match is left unnamed rather than
// guessed. It needs no XbSymbolDatabase checkout.
func ScanCRT(f *xbe.File) []Match {
	var out []Match
	for i := range f.Sections {
		sec := &f.Sections[i]
		if sec.Name != ".text" {
			continue
		}
		data := f.SectionData(sec)
		for _, c := range crtPatterns {
			hits := parsePattern(c.pattern).find(data)
			if len(hits) != 1 {
				continue
			}
			out = append(out, Match{Addr: sec.VirtualAddr + uint32(hits[0]), Name: c.name, XRef: c.name,
				Library: "LIBCMT", Kind: Function, Conv: c.conv})
		}
	}
	return out
}
