// Package sigdb names XDK library functions inside an XBE by matching byte
// signatures from Cxbx-Reloaded's XbSymbolDatabase.
//
// The database is read from a local checkout at run time and never copied
// into this repository. Its signature data is licensed ODbL-1.0 (the code
// is MIT); loading it from the user's own checkout keeps this repo out of
// the share-alike terms. Get it with:
//
//	git clone https://github.com/Cxbx-Reloaded/XbSymbolDatabase
//
// Each signature ("OOVPA") is a list of (offset, byte) pairs, plus XRefs:
// offsets holding a 32-bit address, or a PC-relative displacement, that
// must point at another already-located symbol, or that derive a new
// symbol's address (usually a global variable) on a match.
package sigdb

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// ScanType mirrors DB_ST_*: whether a symbol is found by the generic
// scanner, only by hand-written code (which we do not port), or both.
type ScanType int

const (
	ScanAuto ScanType = 1 << iota
	ScanManual
)

type Kind int

const (
	Function Kind = iota
	Variable
	Internal // a code fragment used only to derive XRefs
)

func (k Kind) String() string {
	return [...]string{"function", "variable", "internal"}[k]
}

type XRef struct {
	Off  uint16
	Name string // XRef name without the XREF_ prefix
}

type Byte struct {
	Off uint16
	Val byte
}

// Signature is one revision's pattern.
type Signature struct {
	XRefs  []XRef
	Bytes  []Byte
	Detect int // 0: first match; n: take the n-th match
	MaxOff uint16
}

type Revision struct {
	Version uint16
	Sig     *Signature
}

type Symbol struct {
	Name      string // display name, e.g. D3DDevice_BeginPush_4
	XRef      string // address slot it fills, e.g. D3DDevice_BeginPush
	Kind      Kind
	Conv      string // std, fastcall, thiscall, ... as given by the database
	Scan      ScanType
	Revisions []Revision // ascending versions
}

// LibraryDB is the symbol table for one or more XDK libraries, and the XBE
// sections they are searched in. It follows SymbolDBList in
// libXbSymbolDatabase.c.
type LibraryDB struct {
	Libraries []string // XBE library names this table applies to
	Sections  []string
	Symbols   []*Symbol
}

type DB struct {
	Tables []*LibraryDB
	// Derive lists XRefs that start out as "derive": a signature that
	// references one sets it on match instead of checking it.
	Derive map[string]bool
}

// libraryTables follows SymbolDBList, without the LTCG tables (Forza links
// the standard libraries) and without DSOUND's manual-only table.
var libraryTables = []struct {
	file     string
	libs     []string
	sections []string
}{
	{"D3D8_OOVPA.c", []string{"D3D8", "D3D8LTCG"}, []string{".text", "D3D", "FLASHROM"}},
	{"DSound_OOVPA.c", []string{"DSOUND"}, []string{"DSOUND", ".rdata", "FLASHROM"}},
	{"XActEng_OOVPA.c", []string{"XACTENG"}, []string{"XACTENG", "FLASHROM"}},
	{"Xapi_OOVPA.c", []string{"XAPILIB"}, []string{".text", "XPP", "FLASHROM"}},
	{"XGraphic_OOVPA.c", []string{"XGRAPHC"}, []string{".text", "XGRPH", "FLASHROM"}},
	{"XOnline_OOVPA.c", []string{"XONLINE", "XONLINES", "XONLINLS"}, []string{".text", "XONLINE", "XNET", "FLASHROM"}},
	{"XNet_OOVPA.c", []string{"XNET", "XNETS", "XNETN", "XONLINE", "XONLINES", "XONLINLS"}, []string{".text", "XNET", "FLASHROM"}},
}

// Load reads an XbSymbolDatabase checkout (the repository root).
func Load(root string) (*DB, error) {
	dbDir := filepath.Join(root, "src", "OOVPADatabase")
	db := &DB{Derive: map[string]bool{}}
	for _, t := range libraryTables {
		lib, err := loadTable(dbDir, t.file)
		if err != nil {
			return nil, err
		}
		lib.Libraries, lib.Sections = t.libs, t.sections
		db.Tables = append(db.Tables, lib)
	}
	src, err := os.ReadFile(filepath.Join(root, "src", "lib", "libXbSymbolDatabase.c"))
	if err != nil {
		return nil, err
	}
	for _, m := range deriveRe.FindAllStringSubmatch(preprocess(string(src)), -1) {
		db.Derive[m[1]] = true
	}
	return db, nil
}

var deriveRe = regexp.MustCompile(`xref_database\[XREF_(\w+)\]\s*=\s*XREF_ADDR_DERIVE`)

// loadTable parses one *_OOVPA.c file and the .inl files it includes.
func loadTable(dir, file string) (*LibraryDB, error) {
	raw, err := os.ReadFile(filepath.Join(dir, file))
	if err != nil {
		return nil, err
	}
	src := preprocess(string(raw))

	sigs := map[string]*Signature{}
	aliases := map[string]string{}
	for _, inc := range includeRe.FindAllStringSubmatch(src, -1) {
		if !strings.HasSuffix(inc[1], ".inl") {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, filepath.FromSlash(inc[1])))
		if err != nil {
			return nil, err
		}
		text := preprocess(string(b))
		if err := parseSignatures(text, sigs); err != nil {
			return nil, fmt.Errorf("%s: %w", inc[1], err)
		}
		for _, m := range aliasRe.FindAllStringSubmatch(text, -1) {
			aliases[m[1]] = m[2]
		}
	}
	for _, m := range aliasRe.FindAllStringSubmatch(src, -1) {
		aliases[m[1]] = m[2]
	}
	lookup := func(name string) *Signature {
		for i := 0; i < 8; i++ {
			if s := sigs[name]; s != nil {
				return s
			}
			a, ok := aliases[name]
			if !ok {
				return nil
			}
			name = a
		}
		return nil
	}

	lib := &LibraryDB{}
	for _, call := range findCalls(dropDirectives(src), registerRe) {
		sym, versions, err := parseRegister(call.name, call.args)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", file, err)
		}
		if sym == nil {
			continue
		}
		for _, v := range versions {
			s := lookup(fmt.Sprintf("%s_%d", sym.Name, v))
			if s == nil {
				return nil, fmt.Errorf("%s: %s registers version %d but no signature %s_%d exists", file, sym.Name, v, sym.Name, v)
			}
			if s.MaxOff == 0 && len(s.Bytes) == 0 && len(s.XRefs) == 0 {
				continue // OOVPA_SIG_MATCH_DUMMY
			}
			sym.Revisions = append(sym.Revisions, Revision{Version: uint16(v), Sig: s})
		}
		sort.Slice(sym.Revisions, func(i, j int) bool { return sym.Revisions[i].Version < sym.Revisions[j].Version })
		lib.Symbols = append(lib.Symbols, sym)
	}
	return lib, nil
}

var (
	includeRe  = regexp.MustCompile(`#include\s+"([^"]+)"`)
	aliasRe    = regexp.MustCompile(`(?m)^\s*#define\s+(\w+_\d+)\s+(\w+_\d+)\s*$`)
	registerRe = regexp.MustCompile(`\bREGISTER_OOVPAS(?:_M|_C)?(?:_PREFIX|_D3D8|_D3D)?\s*\(`)
	sigHeadRe  = regexp.MustCompile(`\b(OOVPA_SIG_HEADER_(?:NO_)?XREF(?:_DETECT|_EXTEND)?|OOVPA_(?:NO_)?XREF(?:_DETECT|_EXTEND)?)\s*\(`)
)

// preprocess joins continued lines, drops comments and evaluates the few
// conditionals the database uses (#if 0/1, #ifndef, #else, #endif).
func preprocess(src string) string {
	src = strings.ReplaceAll(src, "\r\n", "\n")
	src = strings.ReplaceAll(src, "\\\n", " ")
	src = stripBlockComments(src)

	defined := map[string]bool{}
	type cond struct{ parent, active, taken bool }
	var stack []cond
	active := true
	var out strings.Builder
	for _, line := range strings.Split(src, "\n") {
		if i := strings.Index(line, "//"); i >= 0 {
			line = line[:i]
		}
		t := strings.TrimSpace(line)
		if strings.HasPrefix(t, "#") {
			fields := strings.Fields(strings.TrimSpace(t[1:]))
			if len(fields) == 0 {
				continue
			}
			arg := ""
			if len(fields) > 1 {
				arg = fields[1]
			}
			switch fields[0] {
			case "if", "ifdef", "ifndef":
				var v bool
				switch fields[0] {
				case "if":
					v = arg != "0" && arg != ""
				case "ifdef":
					v = defined[arg]
				case "ifndef":
					v = !defined[arg]
				}
				stack = append(stack, cond{parent: active, active: active && v, taken: v})
				active = active && v
			case "else":
				if n := len(stack); n > 0 {
					c := &stack[n-1]
					c.active = c.parent && !c.taken
					c.taken = true
					active = c.active
				}
			case "endif":
				if n := len(stack); n > 0 {
					active = stack[n-1].parent
					stack = stack[:n-1]
				}
			case "define":
				if active {
					defined[arg] = true
					out.WriteString(t + "\n")
				}
			default:
				if active {
					out.WriteString(t + "\n")
				}
			}
			continue
		}
		if active {
			out.WriteString(line + "\n")
		}
	}
	return out.String()
}

// dropDirectives removes preprocessor lines, so macro definitions such as
// `#define REGISTER_OOVPAS_D3D(Symbol, ...)` are not read as calls.
func dropDirectives(src string) string {
	lines := strings.Split(src, "\n")
	for i, l := range lines {
		if strings.HasPrefix(strings.TrimSpace(l), "#") {
			lines[i] = ""
		}
	}
	return strings.Join(lines, "\n")
}

func stripBlockComments(s string) string {
	var b strings.Builder
	for {
		i := strings.Index(s, "/*")
		if i < 0 {
			b.WriteString(s)
			return b.String()
		}
		b.WriteString(s[:i])
		j := strings.Index(s[i+2:], "*/")
		if j < 0 {
			return b.String()
		}
		// Keep line count stable for anyone reading positions.
		b.WriteString(strings.Repeat("\n", strings.Count(s[i:i+2+j+2], "\n")))
		s = s[i+2+j+2:]
	}
}

type call struct {
	name string
	args []string
	end  int
}

// findCalls finds macro invocations matching re (which must end at the
// opening parenthesis) and splits their top-level arguments.
func findCalls(src string, re *regexp.Regexp) []call {
	var out []call
	for _, loc := range re.FindAllStringIndex(src, -1) {
		name := strings.TrimSpace(strings.TrimSuffix(strings.TrimSpace(src[loc[0]:loc[1]]), "("))
		args, end, ok := splitArgs(src, loc[1])
		if ok {
			out = append(out, call{name: name, args: args, end: end})
		}
	}
	return out
}

// splitArgs reads from just after an opening parenthesis to its match.
func splitArgs(src string, start int) ([]string, int, bool) {
	depth := 0
	var args []string
	last := start
	for i := start; i < len(src); i++ {
		switch src[i] {
		case '(', '{', '[':
			depth++
		case ')', '}', ']':
			if depth == 0 {
				args = append(args, strings.TrimSpace(src[last:i]))
				return args, i + 1, true
			}
			depth--
		case ',':
			if depth == 0 {
				args = append(args, strings.TrimSpace(src[last:i]))
				last = i + 1
			}
		}
	}
	return nil, 0, false
}

// inner returns the arguments of a single macro call like SYM_SIG(1, 2).
func inner(s, macro string) ([]string, bool) {
	s = strings.TrimSpace(s)
	if !strings.HasPrefix(s, macro) {
		return nil, false
	}
	rest := strings.TrimSpace(s[len(macro):])
	if !strings.HasPrefix(rest, "(") {
		return nil, false
	}
	idx := strings.Index(s, "(")
	args, _, ok := splitArgs(s, idx+1)
	return args, ok
}

// parseRegister decodes one REGISTER_OOVPAS* call. It returns nil for
// symbol forms we skip (LTCG).
func parseRegister(macro string, args []string) (*Symbol, []int, error) {
	sym := &Symbol{Scan: ScanAuto}
	switch {
	case strings.HasPrefix(macro, "REGISTER_OOVPAS_M"):
		sym.Scan = ScanManual
	case strings.HasPrefix(macro, "REGISTER_OOVPAS_C"):
		sym.Scan = ScanAuto | ScanManual
	}
	prefix := ""
	switch {
	case strings.HasSuffix(macro, "_PREFIX"):
		if len(args) < 1 {
			return nil, nil, fmt.Errorf("%s with no prefix", macro)
		}
		prefix, args = args[0], args[1:]
	case strings.HasSuffix(macro, "_D3D8"):
		prefix = "D3D8"
	case strings.HasSuffix(macro, "_D3D"):
		prefix = "D3D"
	}
	if len(args) < 2 {
		return nil, nil, fmt.Errorf("%s: too few arguments", macro)
	}
	info := args[0]
	var name, structName string
	switch {
	case strings.HasPrefix(info, "SYM_FUN_LTCG"):
		return nil, nil, nil
	case strings.HasPrefix(info, "SYM_FUN_ALT"):
		a, ok := inner(info, "SYM_FUN_ALT")
		if !ok || len(a) < 4 {
			return nil, nil, fmt.Errorf("bad %s", info)
		}
		name = a[0]
		suffix, _ := inner(a[1], "SUFFIX")
		structName = name + stackSuffix(a[3]) + strings.Join(suffix, "")
		sym.Conv = callName(a[2])
	case strings.HasPrefix(info, "SYM_FUN"):
		a, ok := inner(info, "SYM_FUN")
		if !ok || len(a) < 3 {
			return nil, nil, fmt.Errorf("bad %s", info)
		}
		name = a[0]
		structName = name + stackSuffix(a[2])
		sym.Conv = callName(a[1])
	case strings.HasPrefix(info, "SYM_VAR"), strings.HasPrefix(info, "SYM_INT"):
		macroName := info[:7]
		a, ok := inner(info, macroName)
		if !ok || len(a) < 1 {
			return nil, nil, fmt.Errorf("bad %s", info)
		}
		name, structName = a[0], a[0]
		sym.Kind = Variable
		if macroName == "SYM_INT" {
			sym.Kind = Internal
		}
	default:
		return nil, nil, fmt.Errorf("unknown symbol form %q", info)
	}
	sym.Name = structName
	sym.XRef = name
	if prefix != "" {
		sym.XRef = prefix + "_" + name
	}

	var versions []int
	for _, a := range args[1:] {
		vs, ok := inner(a, "SYM_SIG")
		if !ok {
			return nil, nil, fmt.Errorf("%s: expected SYM_SIG, got %q", structName, a)
		}
		for _, v := range vs {
			n, err := strconv.Atoi(strings.TrimSpace(v))
			if err != nil {
				return nil, nil, fmt.Errorf("%s: bad version %q", structName, v)
			}
			versions = append(versions, n)
		}
	}
	return sym, versions, nil
}

// stackSuffix expands STACK(n) the way the database's macro does: "_n", or
// nothing for STACK() and STACK(/*default*/).
func stackSuffix(s string) string {
	a, ok := inner(s, "STACK")
	if !ok || len(a) != 1 || a[0] == "" {
		return ""
	}
	return "_" + a[0]
}

func callName(s string) string {
	if a, ok := inner(s, "CALL"); ok && len(a) == 1 {
		return a[0]
	}
	return ""
}

// parseSignatures reads every OOVPA definition in an .inl file into sigs,
// keyed by struct name (Name_Version).
func parseSignatures(src string, sigs map[string]*Signature) error {
	for _, h := range findCalls(src, sigHeadRe) {
		if len(h.args) < 2 {
			return fmt.Errorf("%s: too few arguments", h.name)
		}
		key := h.args[0] + "_" + strings.TrimSpace(h.args[1])
		sig := &Signature{}
		if strings.Contains(h.name, "DETECT") || strings.Contains(h.name, "EXTEND") {
			sig.Detect = detectValue(h.args[len(h.args)-1])
		}

		rest := strings.TrimLeft(src[h.end:], " \t\n")
		var body string
		switch {
		case strings.HasPrefix(rest, "OOVPA_SIG_MATCH_DUMMY"):
			sigs[key] = sig
			continue
		case strings.HasPrefix(rest, "OOVPA_SIG_MATCH"):
			i := strings.Index(rest, "(")
			args, _, ok := splitArgs(rest, i+1)
			if !ok {
				return fmt.Errorf("%s: unterminated OOVPA_SIG_MATCH", key)
			}
			body = strings.Join(args, ",")
		case strings.HasPrefix(rest, "{"):
			end := strings.Index(rest, "OOVPA_END")
			if end < 0 {
				return fmt.Errorf("%s: missing OOVPA_END", key)
			}
			body = rest[1:end]
			body = body[:strings.LastIndex(body, "}")]
		default:
			return fmt.Errorf("%s: no signature body", key)
		}
		if err := parseEntries(body, sig); err != nil {
			return fmt.Errorf("%s: %w", key, err)
		}
		sigs[key] = sig
	}
	return nil
}

func detectValue(s string) int {
	switch strings.TrimSpace(s) {
	case "DetectFirst":
		return 1
	case "DetectSecond":
		return 2
	case "DetectThird":
		return 3
	case "DetectFourth":
		return 4
	}
	return 0
}

var entryRe = regexp.MustCompile(`XREF_ENTRY\s*\(|OV_MATCH\s*\(|\{`)

func parseEntries(body string, sig *Signature) error {
	for _, loc := range entryRe.FindAllStringIndex(body, -1) {
		tok := body[loc[0]:loc[1]]
		args, _, ok := splitArgs(body, loc[1])
		if !ok {
			return fmt.Errorf("unterminated entry")
		}
		switch {
		case strings.HasPrefix(tok, "XREF_ENTRY"):
			if len(args) != 2 {
				return fmt.Errorf("XREF_ENTRY needs 2 arguments: %v", args)
			}
			off, err := evalInt(args[0])
			if err != nil {
				return err
			}
			sig.XRefs = append(sig.XRefs, XRef{Off: uint16(off), Name: strings.TrimPrefix(args[1], "XREF_")})
			sig.maxOff(uint16(off) + 3)
		case strings.HasPrefix(tok, "OV_MATCH"):
			if len(args) < 2 {
				return fmt.Errorf("OV_MATCH needs bytes: %v", args)
			}
			off, err := evalInt(args[0])
			if err != nil {
				return err
			}
			for i, a := range args[1:] {
				if err := sig.addByte(off+i, a); err != nil {
					return err
				}
			}
		default: // { off, val }
			if len(args) != 2 {
				continue // a nested brace that is not a pair
			}
			off, err := evalInt(args[0])
			if err != nil {
				return err
			}
			if err := sig.addByte(off, args[1]); err != nil {
				return err
			}
		}
	}
	return nil
}

func (s *Signature) addByte(off int, val string) error {
	v, err := evalInt(val)
	if err != nil {
		return err
	}
	if v < 0 || v > 0xFF || off < 0 || off > 0xFFFF {
		return fmt.Errorf("entry {%d, %s} out of range", off, val)
	}
	s.Bytes = append(s.Bytes, Byte{Off: uint16(off), Val: byte(v)})
	s.maxOff(uint16(off))
	return nil
}

func (s *Signature) maxOff(o uint16) {
	if o > s.MaxOff {
		s.MaxOff = o
	}
}

// evalInt handles the literal forms used in the database: decimal, hex and
// sums such as "0x10 + 2".
func evalInt(s string) (int, error) {
	total := 0
	for _, part := range strings.Split(s, "+") {
		part = strings.TrimSpace(part)
		n, err := strconv.ParseInt(part, 0, 32)
		if err != nil {
			// XREF_KT_FUNC_x evaluates to x's kernel ordinal in C. One
			// signature uses it as a byte value; mirror the compiler.
			k, ok := xbe.KernelByName(strings.TrimPrefix(part, "XREF_KT_FUNC_"))
			if !strings.HasPrefix(part, "XREF_KT_FUNC_") || !ok {
				return 0, fmt.Errorf("cannot evaluate %q", s)
			}
			n = int64(k.Ordinal)
		}
		total += int(n)
	}
	return total, nil
}
