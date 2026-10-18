package sigdb

import (
	"encoding/binary"
	"sort"
	"strings"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// Match is a located symbol.
type Match struct {
	Addr    uint32
	Name    string
	XRef    string
	Library string // empty for values only ever derived
	Version uint16 // signature revision that matched
	Kind    Kind
	Conv    string
	Params  []Param
	Derived bool // address read from another signature, not matched itself
}

// XRef slot states, as in XbSymbolDatabase.
const (
	stateUnknown = iota // not yet located; signatures needing it wait
	stateDerive         // the next signature to reference it sets it
	stateKnown
)

type slot struct {
	state int
	addr  uint32
}

// region is one XBE section's file-backed bytes and a byte-value index.
type region struct {
	name string
	va   uint32
	data []byte
	at   [256][]uint32 // offsets of each byte value
}

func (r *region) contains(va uint32) bool {
	return va >= r.va && va-r.va < uint32(len(r.data))
}

type scanner struct {
	f       *xbe.File
	db      *DB
	xrefs   map[string]*slot
	found   map[string]*Match // by xref
	regions []*region         // every section, in XBE order
	learned int               // xrefs set so far; passes stop when it stalls
}

func (s *scanner) get(name string) *slot {
	if v := s.xrefs[name]; v != nil {
		return v
	}
	v := &slot{}
	s.xrefs[name] = v
	return v
}

func (s *scanner) known(name string) bool { return s.get(name).state == stateKnown }

// unset is XbSDBi_IsXRefAddrUnset: unknown or waiting to be derived.
func (s *scanner) unset(name string) bool { return !s.known(name) }

func (s *scanner) addr(name string) uint32 { return s.get(name).addr }

func (s *scanner) setState(name string, st int) {
	v := s.get(name)
	v.state, v.addr = st, 0
}

// set records an address the first time an xref is learned.
func (s *scanner) set(name string, addr uint32) bool {
	v := s.get(name)
	if v.state == stateKnown {
		return false
	}
	v.state, v.addr = stateKnown, addr
	s.learned++
	return true
}

// force sets an xref even if known, like XbSDBi_SetXRefDatabase.
func (s *scanner) force(name string, addr uint32) {
	v := s.get(name)
	if v.state != stateKnown {
		s.learned++
	}
	v.state, v.addr = stateKnown, addr
}

// register is XbSDBi_RegisterSymbolManual: the first address registered
// for an xref wins. An empty name means the symbol's own.
func (s *scanner) register(sym *Symbol, name, lib string, ver uint16, addr uint32) {
	if !s.set(sym.XRef, addr) {
		return
	}
	if name == "" {
		name = sym.Name
	}
	s.found[sym.XRef] = &Match{Addr: addr, Name: name, XRef: sym.XRef, Library: lib,
		Version: ver, Kind: sym.Kind, Conv: sym.Conv, Params: sym.Params}
}

func (s *scanner) u32(va uint32) (uint32, bool) {
	v, err := s.f.Uint32(va)
	return v, err == nil
}

func (s *scanner) u8(va uint32) (byte, bool) {
	b, err := s.f.Bytes(va, 1)
	if err != nil {
		return 0, false
	}
	return b[0], true
}

// tableRegions lists the sections a table is searched in, in XBE order,
// which decides which match wins when a symbol appears twice.
func (s *scanner) tableRegions(t *LibraryDB) []*region {
	var out []*region
	for _, r := range s.regions {
		for _, name := range t.Sections {
			if r.name == name {
				out = append(out, r)
				break
			}
		}
	}
	return out
}

// Scan locates every symbol it can, the way XbSymbolDatabase does: the
// hand-written scans first, then signature passes until a full pass learns
// nothing. A table is used if the XBE links one of its libraries, and only
// revisions at or below that library's build are tried.
//
// One difference: XbSymbolDatabase finishes each library before starting
// the next, whereas here every pass covers all libraries. That can only
// find more, not less.
func Scan(f *xbe.File, db *DB) []Match {
	s := &scanner{f: f, db: db, xrefs: map[string]*slot{}, found: map[string]*Match{}}
	for i := range f.Sections {
		sec := &f.Sections[i]
		r := &region{name: sec.Name, va: sec.VirtualAddr, data: f.SectionData(sec)}
		for j, b := range r.data {
			r.at[b] = append(r.at[b], uint32(j))
		}
		s.regions = append(s.regions, r)
	}
	for name := range db.Derive {
		s.get(name).state = stateDerive
	}
	for _, k := range f.Kernel {
		s.set("KT_FUNC_"+k.Name, k.Slot)
	}

	build := map[string]uint16{}
	for _, l := range f.Libraries {
		build[l.Name] = l.Build
	}
	type job struct {
		lib   string
		build uint16
		table *LibraryDB
	}
	var jobs []job
	for _, t := range db.Tables {
		for _, name := range t.Libraries {
			if b, ok := build[name]; ok {
				jobs = append(jobs, job{name, b, t})
				break
			}
		}
	}

	// Hand-written scans run first, in the XBE's library order.
	for _, l := range f.Libraries {
		s.manual(l.Name, l.Build)
	}

	for pass := 0; ; pass++ {
		before := s.learned
		for _, j := range jobs {
			for _, r := range s.tableRegions(j.table) {
				for _, sym := range j.table.Symbols {
					if sym.Scan&ScanAuto == 0 || s.known(sym.XRef) {
						continue
					}
					if addr, ver, ok := s.scanIn(sym, j.build, r, pass == 0); ok {
						s.register(sym, "", j.lib, ver, addr)
					}
				}
			}
		}
		if s.learned == before {
			break
		}
	}
	return s.results()
}

func (s *scanner) results() []Match {
	var out []Match
	for _, m := range s.found {
		out = append(out, *m)
	}
	// XRefs learned only by derivation (globals, struct offsets) are
	// reported too, except kernel thunks, which xbeinfo already lists.
	bySlot := map[string]*Symbol{}
	for _, t := range s.db.Tables {
		for _, sym := range t.Symbols {
			if bySlot[sym.XRef] == nil {
				bySlot[sym.XRef] = sym
			}
		}
	}
	for name, v := range s.xrefs {
		if v.state != stateKnown || s.found[name] != nil || strings.HasPrefix(name, "KT_FUNC_") {
			continue
		}
		m := Match{Addr: v.addr, Name: name, XRef: name, Kind: Variable, Derived: true}
		if sym := bySlot[name]; sym != nil {
			m.Name, m.Kind, m.Conv, m.Params = sym.Name, sym.Kind, sym.Conv, sym.Params
		}
		out = append(out, m)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Addr != out[j].Addr {
			return out[i].Addr < out[j].Addr
		}
		return out[i].Name < out[j].Name
	})
	return out
}

// scanIn tries each revision the build allows within one section and keeps
// the highest that matches, as XbSDBi_OOVPATable_scan does.
func (s *scanner) scanIn(sym *Symbol, build uint16, r *region, firstPass bool) (uint32, uint16, bool) {
	var addr uint32
	var ver uint16
	ok := false
	for _, rev := range sym.Revisions {
		if rev.Version > build {
			continue
		}
		if !firstPass && len(rev.Sig.XRefs) == 0 {
			continue // nothing new can make an xref-free signature match
		}
		if a, hit := s.locate(rev.Sig, r); hit {
			addr, ver, ok = a, rev.Version, true
		}
	}
	return addr, ver, ok
}

// locate finds the first place in r where sig matches (or the n-th, for
// signatures with a detect selection), deriving xrefs from that match.
func (s *scanner) locate(sig *Signature, r *region) (uint32, bool) {
	var derive []XRef
	for _, x := range sig.XRefs {
		switch s.get(x.Name).state {
		case stateUnknown:
			return 0, false
		case stateDerive:
			derive = append(derive, x)
		}
	}
	if len(sig.Bytes) == 0 && len(sig.XRefs) == 0 {
		return 0, false
	}
	limit := len(r.data) - int(sig.MaxOff)
	if limit <= 0 {
		return 0, false
	}

	matches := 0
	try := func(base uint32) (uint32, bool) {
		if !s.compare(sig, r, base) {
			return 0, false
		}
		matches++
		if sig.Detect != 0 && matches != sig.Detect {
			return 0, false
		}
		for _, x := range derive {
			s.set(x.Name, binary.LittleEndian.Uint32(r.data[base+uint32(x.Off):]))
		}
		return r.va + base, true
	}

	// Walk candidates from the rarest byte in the signature.
	if len(sig.Bytes) > 0 {
		key := sig.Bytes[0]
		for _, b := range sig.Bytes[1:] {
			if len(r.at[b.Val]) < len(r.at[key.Val]) {
				key = b
			}
		}
		for _, p := range r.at[key.Val] {
			if p < uint32(key.Off) {
				continue
			}
			base := p - uint32(key.Off)
			if int(base) >= limit {
				break
			}
			if a, ok := try(base); ok {
				return a, true
			}
		}
		return 0, false
	}
	for base := 0; base < limit; base++ {
		if a, ok := try(uint32(base)); ok {
			return a, true
		}
	}
	return 0, false
}

// matchRef is XbSDBi_MatchXRefAddr: the dword at off is either the target
// address or a rel32 measured from the end of the field.
func matchRef(r *region, off, target uint32) bool {
	if int(off)+4 > len(r.data) {
		return false
	}
	actual := binary.LittleEndian.Uint32(r.data[off:])
	return actual == target || actual+r.va+off+4 == target
}

func (s *scanner) compare(sig *Signature, r *region, base uint32) bool {
	for _, x := range sig.XRefs {
		v := s.xrefs[x.Name]
		if v.state != stateKnown {
			continue // derive slots are filled on match, not checked
		}
		if !matchRef(r, base+uint32(x.Off), v.addr) {
			return false
		}
	}
	for _, b := range sig.Bytes {
		if r.data[base+uint32(b.Off)] != b.Val {
			return false
		}
	}
	return true
}
