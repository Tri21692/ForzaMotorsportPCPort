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
	Conv      string  // std, cdecl, fast, thi, ... as the database spells it
	Params    []Param // in declaration order; empty for void or variables
	Scan      ScanType
	Revisions []Revision // ascending versions
}

// Param is one function parameter. Loc says where it is passed: "psh"
// (pushed on the stack) or a register such as "ecx" or "eax".
type Param struct {
	Loc  string
	Name string
}

// RenderState is one entry of the D3D8 render state table, in table order.
// XRef is set for the states the database tracks by name.
type RenderState struct {
	Version, Removed uint16
	XRef             string
}

// Available reports whether the state exists in a given D3D8 build.
func (r RenderState) Available(build uint16) bool {
	return r.Version <= build && (r.Removed == 0 || build < r.Removed)
}

// LibraryDB is the symbol table for one or more XDK libraries, and the XBE
// sections they are searched in. It follows SymbolDBList in
// libXbSymbolDatabase.c.
type LibraryDB struct {
	Name      string   // table name in the database source
	Libraries []string // XBE library names this table applies to
	Sections  []string
	Symbols   []*Symbol
}

type DB struct {
	Tables []*LibraryDB
	// Derive lists XRefs that start out as "derive": a signature that
	// references one sets it on match instead of checking it.
	Derive map[string]bool
	// RenderStates is the D3D8 render state layout from
	// manual_d3d8__ltcg.h, used to place the D3DRS_* globals.
	RenderStates []RenderState
}

// Table returns the table with the given database name, or nil.
func (db *DB) Table(name string) *LibraryDB {
	for _, t := range db.Tables {
		if t.Name == name {
			return t
		}
	}
	return nil
}

// libraryTables follows SymbolDBList in libXbSymbolDatabase.c, without the
// LTCG tables (Forza links the standard libraries).
var libraryTables = []struct {
	file, table string
	libs        []string
	sections    []string
}{
	{"D3D8_OOVPA.c", "D3D8_OOVPA_Table", []string{"D3D8", "D3D8LTCG"}, []string{".text", "D3D", "FLASHROM"}},
	// Used only by the hand-written DSOUND scan.
	{"DSound_OOVPA.c", "DSound_OOVPA_manual_Table", []string{"DSOUND"}, []string{"DSOUND", ".rdata", "FLASHROM", ".text"}},
	{"DSound_OOVPA.c", "DSound_OOVPA_Table", []string{"DSOUND"}, []string{"DSOUND", ".rdata", "FLASHROM"}},
	{"XActEng_OOVPA.c", "XACTENG_OOVPA_Table", []string{"XACTENG"}, []string{"XACTENG", "FLASHROM"}},
	{"Xapi_OOVPA.c", "XAPILIB_OOVPA_Table", []string{"XAPILIB"}, []string{".text", "XPP", "FLASHROM"}},
	{"XGraphic_OOVPA.c", "XGRAPHC_OOVPA_Table", []string{"XGRAPHC"}, []string{".text", "XGRPH", "FLASHROM"}},
	{"XOnline_OOVPA.c", "XONLINE_OOVPA_Table", []string{"XONLINE", "XONLINES", "XONLINLS"}, []string{".text", "XONLINE", "XNET", "FLASHROM"}},
	{"XNet_OOVPA.c", "XNET_OOVPA_Table", []string{"XNET", "XNETS", "XNETN", "XONLINE", "XONLINES", "XONLINLS"}, []string{".text", "XNET", "FLASHROM"}},
}

// Load reads an XbSymbolDatabase checkout (the repository root).
func Load(root string) (*DB, error) {
	dbDir := filepath.Join(root, "src", "OOVPADatabase")
	db := &DB{Derive: map[string]bool{}}
	for _, t := range libraryTables {
		lib, err := loadTable(dbDir, t.file, t.table)
		if err != nil {
			return nil, err
		}
		lib.Name, lib.Libraries, lib.Sections = t.table, t.libs, t.sections
		db.Tables = append(db.Tables, lib)
	}
	libDir := filepath.Join(root, "src", "lib")
	src, err := os.ReadFile(filepath.Join(libDir, "libXbSymbolDatabase.c"))
	if err != nil {
		return nil, err
	}
	for _, m := range deriveRe.FindAllStringSubmatch(preprocess(string(src)), -1) {
		db.Derive[m[1]] = true
	}
	rs, err := os.ReadFile(filepath.Join(libDir, "manual_d3d8__ltcg.h"))
	if err != nil {
		return nil, err
	}
	if db.RenderStates, err = parseRenderStates(preprocess(string(rs))); err != nil {
		return nil, err
	}
	return db, nil
}

var renderStateRe = regexp.MustCompile(`\{\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*XREF_NAME\((\w+)\))?\s*\}`)

// parseRenderStates reads the DxbxRenderStateInfo table. Entries whose
// XREF_NAME is commented out keep their slot but have no XRef.
func parseRenderStates(src string) ([]RenderState, error) {
	start := strings.Index(src, "DxbxRenderStateInfo[] =")
	if start < 0 {
		return nil, fmt.Errorf("manual_d3d8__ltcg.h: DxbxRenderStateInfo table not found")
	}
	end := strings.Index(src[start:], "};")
	if end < 0 {
		return nil, fmt.Errorf("manual_d3d8__ltcg.h: DxbxRenderStateInfo table not terminated")
	}
	var out []RenderState
	for _, m := range renderStateRe.FindAllStringSubmatch(src[start:start+end], -1) {
		v, _ := strconv.Atoi(m[1])
		r, _ := strconv.Atoi(m[2])
		out = append(out, RenderState{Version: uint16(v), Removed: uint16(r), XRef: m[3]})
	}
	// The C source asserts this size; a mismatch means the format moved.
	if len(out) != 167 {
		return nil, fmt.Errorf("manual_d3d8__ltcg.h: read %d render states, want 167", len(out))
	}
	return out, nil
}

var deriveRe = regexp.MustCompile(`xref_database\[XREF_(\w+)\]\s*=\s*XREF_ADDR_DERIVE`)

// loadTable parses one symbol table from a *_OOVPA.c file, with the
// signatures from the .inl files that file includes.
func loadTable(dir, file, table string) (*LibraryDB, error) {
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

	body, err := tableBody(dropDirectives(src), table)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", file, err)
	}
	lib := &LibraryDB{}
	for _, call := range findCalls(body, registerRe) {
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

// tableBody returns the initializer of `static OOVPATable name[] = {...}`.
func tableBody(src, name string) (string, error) {
	i := strings.Index(src, "OOVPATable "+name+"[]")
	if i < 0 {
		return "", fmt.Errorf("table %s not found", name)
	}
	open := strings.Index(src[i:], "{")
	if open < 0 {
		return "", fmt.Errorf("table %s has no body", name)
	}
	start := i + open + 1
	args, end, ok := splitArgs(src, start)
	if !ok || args == nil {
		return "", fmt.Errorf("table %s not terminated", name)
	}
	return src[start : end-1], nil
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
		if len(a) > 4 {
			sym.Params = params(a[4])
		}
	case strings.HasPrefix(info, "SYM_FUN"):
		a, ok := inner(info, "SYM_FUN")
		if !ok || len(a) < 3 {
			return nil, nil, fmt.Errorf("bad %s", info)
		}
		name = a[0]
		structName = name + stackSuffix(a[2])
		sym.Conv = callName(a[1])
		if len(a) > 3 {
			sym.Params = params(a[3])
		}
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

// params reads PARAMS(PARAM(psh, x), PARAM(ecx, this)). PARAM1(void) and
// an empty list give nil.
func params(s string) []Param {
	list, ok := inner(s, "PARAMS")
	if !ok {
		return nil
	}
	var out []Param
	for _, p := range list {
		a, ok := inner(p, "PARAM")
		if !ok || len(a) != 2 {
			continue
		}
		out = append(out, Param{Loc: a[0], Name: a[1]})
	}
	return out
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
		xrefCount, err := headerXRefCount(h.name, h.args)
		if err != nil {
			return fmt.Errorf("%s: %w", key, err)
		}
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
		entries, err := parseEntries(body)
		if err != nil {
			return fmt.Errorf("%s: %w", key, err)
		}
		if err := sig.fill(entries, xrefCount); err != nil {
			return fmt.Errorf("%s: %w", key, err)
		}
		sigs[key] = sig
	}
	return nil
}

// headerXRefCount reads the XRef count from a signature header. The C
// matcher treats the first that-many entries as XRefs, whichever macro
// wrote them, so the count matters more than the entry syntax.
func headerXRefCount(macro string, args []string) (int, error) {
	var a string
	switch {
	case strings.Contains(macro, "NO_XREF"):
		return 0, nil
	case strings.HasPrefix(macro, "OOVPA_SIG_HEADER_"): // (Name, Version, XRefCount[, Detect])
		if len(args) < 3 {
			return 0, fmt.Errorf("%s: missing XRef count", macro)
		}
		a = args[2]
	default: // old style OOVPA_XREF(Name, Version, Count, XRefCount[, Detect])
		if len(args) < 4 {
			return 0, fmt.Errorf("%s: missing XRef count", macro)
		}
		a = args[3]
	}
	words := map[string]int{"XRefZero": 0, "XRefOne": 1, "XRefTwo": 2, "XRefThree": 3, "XRefFour": 4}
	if n, ok := words[strings.TrimSpace(a)]; ok {
		return n, nil
	}
	return evalInt(a)
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

// entry is one (offset, value) pair as written. XRef is set when the value
// is an XREF_ name rather than a number.
type entry struct {
	off  int
	val  int
	xref string
}

var entryRe = regexp.MustCompile(`XREF_ENTRY\s*\(|OV_MATCH\s*\(|\{`)

// parseEntries lists a signature body's entries in source order;
// OV_MATCH(off, a, b, c) expands to one entry per byte, as the macro does.
func parseEntries(body string) ([]entry, error) {
	var out []entry
	for _, loc := range entryRe.FindAllStringIndex(body, -1) {
		tok := body[loc[0]:loc[1]]
		args, _, ok := splitArgs(body, loc[1])
		if !ok {
			return nil, fmt.Errorf("unterminated entry")
		}
		if strings.HasPrefix(tok, "{") && len(args) != 2 {
			continue // a nested brace that is not a pair
		}
		if len(args) < 2 {
			return nil, fmt.Errorf("%s needs an offset and a value: %v", tok, args)
		}
		off, err := evalInt(args[0])
		if err != nil {
			return nil, err
		}
		if strings.HasPrefix(tok, "XREF_ENTRY") && len(args) != 2 {
			return nil, fmt.Errorf("XREF_ENTRY needs 2 arguments: %v", args)
		}
		for i, a := range args[1:] {
			e := entry{off: off + i}
			if name, isRef := strings.CutPrefix(a, "XREF_"); isRef {
				e.xref = name
			} else if e.val, err = evalInt(a); err != nil {
				return nil, err
			}
			out = append(out, e)
		}
	}
	return out, nil
}

// fill splits entries into XRefs (the first xrefCount) and bytes.
func (s *Signature) fill(entries []entry, xrefCount int) error {
	if xrefCount > len(entries) {
		return fmt.Errorf("header declares %d XRefs but has %d entries", xrefCount, len(entries))
	}
	for i, e := range entries {
		if e.off < 0 || e.off > 0xFFFF {
			return fmt.Errorf("offset %#x out of range", e.off)
		}
		if i < xrefCount {
			if e.xref == "" {
				return fmt.Errorf("entry %d at %#x should be an XRef", i, e.off)
			}
			s.XRefs = append(s.XRefs, XRef{Off: uint16(e.off), Name: e.xref})
			s.maxOff(uint16(e.off) + 3)
			continue
		}
		if e.xref != "" {
			return fmt.Errorf("XRef %s at %#x is past the declared XRef count", e.xref, e.off)
		}
		if e.val < 0 || e.val > 0xFF {
			return fmt.Errorf("byte %#x at %#x out of range", e.val, e.off)
		}
		s.Bytes = append(s.Bytes, Byte{Off: uint16(e.off), Val: byte(e.val)})
		s.maxOff(uint16(e.off))
	}
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
		n, err := strconv.ParseInt(strings.TrimSpace(part), 0, 32)
		if err != nil {
			return 0, fmt.Errorf("cannot evaluate %q", s)
		}
		total += int(n)
	}
	return total, nil
}
