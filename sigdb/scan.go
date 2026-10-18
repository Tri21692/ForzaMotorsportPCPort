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
	Library string
	Version uint16 // signature revision that matched
	Kind    Kind
	Conv    string
	Derived bool // address read from another signature, not matched itself
}

// xref slot states, as in XbSymbolDatabase.
const (
	stateUnknown = iota // not yet located; signatures needing it wait
	stateDerive         // the next signature to reference it sets it
	stateKnown
)

type slot struct {
	state int
	addr  uint32
}

type scanner struct {
	f     *xbe.File
	xrefs map[string]*slot
	found map[string]*Match // by xref

	pendingDerived int // xrefs learned by derivation since the last pass
}

func (s *scanner) get(name string) *slot {
	if v := s.xrefs[name]; v != nil {
		return v
	}
	v := &slot{}
	s.xrefs[name] = v
	return v
}

// set records an address for an xref the first time it is learned.
func (s *scanner) set(name string, addr uint32) bool {
	v := s.get(name)
	if v.state == stateKnown {
		return false
	}
	v.state, v.addr = stateKnown, addr
	return true
}

// region is one XBE section's file-backed bytes and a first-byte index.
type region struct {
	va   uint32
	data []byte
	at   [256][]uint32 // offsets of each byte value
}

func newRegion(f *xbe.File, sec *xbe.Section) *region {
	r := &region{va: sec.VirtualAddr, data: f.SectionData(sec)}
	for i, b := range r.data {
		r.at[b] = append(r.at[b], uint32(i))
	}
	return r
}

// Scan locates every symbol it can. Libraries are matched against the
// XBE's library list: a table is used if the XBE links one of its
// libraries, and only revisions at or below that library's build are
// tried, like the original's strict version limit.
//
// Unlike XbSymbolDatabase, which finishes each library before the next,
// passes repeat over all libraries until a full pass learns nothing. That
// can only find more, never less.
func Scan(f *xbe.File, db *DB) []Match {
	s := &scanner{f: f, xrefs: map[string]*slot{}, found: map[string]*Match{}}
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
		lib     string
		build   uint16
		table   *LibraryDB
		regions []*region
	}
	regions := map[string][]*region{}
	for i := range f.Sections {
		sec := &f.Sections[i]
		regions[sec.Name] = append(regions[sec.Name], newRegion(f, sec))
	}
	var jobs []job
	for _, t := range db.Tables {
		lib, ver := "", uint16(0)
		for _, name := range t.Libraries {
			if b, ok := build[name]; ok {
				lib, ver = name, b
				break
			}
		}
		if lib == "" {
			continue
		}
		var rs []*region
		for _, sec := range t.Sections {
			rs = append(rs, regions[sec]...)
		}
		jobs = append(jobs, job{lib, ver, t, rs})
	}

	for pass := 0; ; pass++ {
		learned := 0
		for _, j := range jobs {
			for _, sym := range j.table.Symbols {
				if sym.Scan&ScanAuto == 0 || s.found[sym.XRef] != nil {
					continue
				}
				if s.get(sym.XRef).state == stateKnown {
					continue // learned by derivation, or an alternate signature
				}
				addr, rev, ok := s.scanSymbol(sym, j.build, j.regions, pass == 0)
				if !ok {
					continue
				}
				if s.set(sym.XRef, addr) {
					learned++
				}
				s.found[sym.XRef] = &Match{Addr: addr, Name: sym.Name, XRef: sym.XRef,
					Library: j.lib, Version: rev, Kind: sym.Kind, Conv: sym.Conv}
			}
		}
		learned += s.pendingDerived
		s.pendingDerived = 0
		if learned == 0 {
			break
		}
	}

	var out []Match
	for _, m := range s.found {
		out = append(out, *m)
	}
	// XRefs learned only by derivation (globals, struct offsets) are
	// reported too, except kernel thunks, which xbeinfo already lists.
	bySlot := map[string]*Symbol{}
	for _, t := range db.Tables {
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
			m.Name, m.Kind, m.Conv = sym.Name, sym.Kind, sym.Conv
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

// scanSymbol tries each revision the build allows and keeps the highest
// one that matches, as XbSDBi_OOVPATable_scan does.
func (s *scanner) scanSymbol(sym *Symbol, build uint16, regions []*region, firstPass bool) (uint32, uint16, bool) {
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
		for _, r := range regions {
			if a, hit := s.locate(rev.Sig, r); hit {
				addr, ver, ok = a, rev.Version, true
				break
			}
		}
	}
	return addr, ver, ok
}

// locate finds the first place in r where sig matches.
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
			v := binary.LittleEndian.Uint32(r.data[base+uint32(x.Off):])
			if s.set(x.Name, v) {
				s.pendingDerived++
			}
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

func (s *scanner) compare(sig *Signature, r *region, base uint32) bool {
	for _, x := range sig.XRefs {
		v := s.xrefs[x.Name]
		if v.state != stateKnown {
			continue // derive slots are filled on match, not checked
		}
		at := base + uint32(x.Off)
		actual := binary.LittleEndian.Uint32(r.data[at:])
		// Absolute address, or rel32 measured from the end of the field.
		if actual != v.addr && actual+r.va+at+4 != v.addr {
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
