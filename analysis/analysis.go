// Package analysis finds the code in an XBE: functions, their extents, the
// calls between them and the kernel imports they use. It is the base the
// recompiler builds on, since it has to know what is code before it can
// translate it.
//
// Discovery works in rounds until nothing new turns up:
//
//  1. Recursive descent from the entry point, following direct calls,
//     jumps, conditional branches and MSVC switch jump tables.
//  2. Prologue scan: `push ebp; mov ebp, esp` in bytes no function claimed,
//     inside sections the descent showed to be code.
//  3. Data references: runs of two or more pointers into code found in data
//     sections (vtables and callback tables).
//
// Once the set of function starts settles, bodies are rebuilt in one last
// pass so that a jump into another function's start is recorded as a tail
// call instead of being swallowed into the caller.
package analysis

import (
	"encoding/binary"
	"sort"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

// Source records how a function start was found, most trusted first.
type Source int

const (
	FromEntry Source = iota
	FromCall
	FromSignature // matched an XDK library signature (see package sigdb)
	FromTailJump
	FromPrologue
	FromDataRef
)

func (s Source) String() string {
	return [...]string{"entry", "call", "signature", "tailjump", "prologue", "dataref"}[s]
}

// NumSources is the number of Source values, for tables indexed by Source.
const NumSources = int(FromDataRef) + 1

type Func struct {
	Addr    uint32
	End     uint32 // one past the last byte of the highest instruction
	Source  Source
	Section string
	Insns   int
	Bytes   int // bytes of instructions actually decoded (holes excluded)

	Calls         []uint32 // direct call targets
	TailCalls     []uint32 // jumps to other functions
	KernelCalls   []uint32 // kernel ordinals called or tail-jumped to
	IndirectCalls int      // calls through registers or non-thunk memory
	JumpTables    int
	Unresolved    int // indirect jumps that were not a recognisable table
	BadDecode     bool
}

type Program struct {
	File   *xbe.File
	Funcs  map[uint32]*Func
	Code   map[string]bool   // sections that hold code
	Owner  map[uint32]uint32 // instruction start -> function that owns it
	Rounds int

	a *analyzer
}

// Sorted returns the functions in address order.
func (p *Program) Sorted() []*Func {
	out := make([]*Func, 0, len(p.Funcs))
	for _, fn := range p.Funcs {
		out = append(out, fn)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Addr < out[j].Addr })
	return out
}

type analyzer struct {
	f      *xbe.File
	starts map[uint32]Source
	code   map[string]bool
}

// Analyze discovers the code in f. Seeds are extra function starts known
// from elsewhere, such as library signature matches.
func Analyze(f *xbe.File, seeds ...uint32) *Program {
	a := &analyzer{f: f, starts: map[uint32]Source{}, code: map[string]bool{}}
	a.addStart(f.EntryPoint, FromEntry)
	for _, va := range seeds {
		a.addStart(va, FromSignature)
	}

	p := &Program{File: f, Code: a.code}
	for {
		p.Rounds++
		before := len(a.starts)
		funcs, owner := a.descendAll()
		a.scanPrologues(owner)
		a.scanDataRefs(owner)
		a.scanImmediates(owner)
		if len(a.starts) == before {
			p.Funcs, p.Owner, p.a = funcs, owner, a
			return p
		}
	}
}

func (a *analyzer) addStart(va uint32, src Source) {
	s := a.f.SectionAt(va)
	if s == nil {
		return
	}
	if old, ok := a.starts[va]; ok && old <= src {
		return
	}
	a.starts[va] = src
	a.code[s.Name] = true
}

// descendAll rebuilds every function from the current set of starts. New
// call targets found on the way are added and descended in the same pass.
func (a *analyzer) descendAll() (map[uint32]*Func, map[uint32]uint32) {
	funcs := map[uint32]*Func{}
	owner := map[uint32]uint32{}
	for {
		pending := []uint32{}
		for va := range a.starts {
			if funcs[va] == nil {
				pending = append(pending, va)
			}
		}
		if len(pending) == 0 {
			return funcs, owner
		}
		sort.Slice(pending, func(i, j int) bool { return pending[i] < pending[j] })
		for _, va := range pending {
			funcs[va] = a.descend(va, owner)
		}
	}
}

// decode reads one instruction at va, never past the section's file data.
func (a *analyzer) decode(va uint32) (x86asm.Inst, bool) {
	s := a.f.SectionAt(va)
	if s == nil {
		return x86asm.Inst{}, false
	}
	if va >= s.VirtualAddr+s.RawSize {
		return x86asm.Inst{}, false
	}
	// An instruction may end in the section's zero-filled tail: Forza's
	// FZFULLUI section stores one byte less than it maps, and its last
	// instruction (ret 0x1c, C2 1C 00) ends in that byte. The loader
	// fills it with zeros, so decode with the same zeros.
	end := s.VirtualAddr + s.VirtualSize
	if raw := s.VirtualAddr + s.RawSize; raw > end {
		end = raw
	}
	n := end - va
	if n > 15 {
		n = 15
	}
	b := make([]byte, n)
	have := s.VirtualAddr + s.RawSize - va
	if have > n {
		have = n
	}
	data, err := a.f.Bytes(va, have)
	if err != nil {
		return x86asm.Inst{}, false
	}
	copy(b, data)
	in, err := x86asm.Decode(b, 32)
	if err != nil {
		return x86asm.Inst{}, false
	}
	return in, true
}

func (a *analyzer) descend(start uint32, owner map[uint32]uint32) *Func {
	fn := &Func{Addr: start, End: start, Source: a.starts[start]}
	if s := a.f.SectionAt(start); s != nil {
		fn.Section = s.Name
	}
	seen := map[uint32]bool{}
	work := []uint32{start}
	branchHist := map[uint32]recent{} // the path so far, at each branch target
	for len(work) > 0 {
		va := work[len(work)-1]
		work = work[:len(work)-1]
		hist := branchHist[va]
	path:
		for !seen[va] {
			if va != start {
				if _, isFunc := a.starts[va]; isFunc {
					fn.TailCalls = append(fn.TailCalls, va)
					break path
				}
			}
			if o, taken := owner[va]; taken && o != start {
				// Shared tail code another function already owns.
				break path
			}
			in, ok := a.decode(va)
			if !ok {
				fn.BadDecode = true
				break path
			}
			seen[va] = true
			owner[va] = start
			fn.Insns++
			fn.Bytes += in.Len
			next := va + uint32(in.Len)
			if next > fn.End {
				fn.End = next
			}

			switch in.Op {
			case x86asm.RET, x86asm.IRET, x86asm.HLT, x86asm.UD2, x86asm.INT:
				break path
			case x86asm.CALL:
				if t, ok := relTarget(in, next); ok {
					a.addStart(t, FromCall)
					fn.Calls = append(fn.Calls, t)
				} else if k, ok := a.thunkRef(in); ok {
					fn.KernelCalls = append(fn.KernelCalls, k.Ordinal)
				} else {
					fn.IndirectCalls++
				}
			case x86asm.JMP:
				if t, ok := relTarget(in, next); ok {
					if a.f.SectionAt(t) != a.f.SectionAt(start) {
						a.addStart(t, FromTailJump)
						fn.TailCalls = append(fn.TailCalls, t)
					} else {
						work = append(work, t)
					}
				} else if k, ok := a.thunkRef(in); ok {
					fn.KernelCalls = append(fn.KernelCalls, k.Ordinal)
				} else if targets := a.jumpTable(in, &hist, start); len(targets) > 0 {
					fn.JumpTables++
					work = append(work, targets...)
				} else {
					fn.Unresolved++
				}
				break path
			default:
				if isCondBranch(in.Op) {
					if t, ok := relTarget(in, next); ok {
						work = append(work, t)
						if _, ok := branchHist[t]; !ok {
							h := hist
							h.add(in)
							branchHist[t] = h
						}
					}
				}
			}
			hist.add(in)
			va = next
		}
	}
	return fn
}

func relTarget(in x86asm.Inst, next uint32) (uint32, bool) {
	if r, ok := in.Args[0].(x86asm.Rel); ok {
		return next + uint32(int32(r)), true
	}
	return 0, false
}

// thunkRef matches `call/jmp dword ptr [slot]` where slot is in the kernel
// thunk table.
func (a *analyzer) thunkRef(in x86asm.Inst) (xbe.KernelImport, bool) {
	m, ok := in.Args[0].(x86asm.Mem)
	if !ok || m.Base != 0 || m.Index != 0 || m.Segment != 0 {
		return xbe.KernelImport{}, false
	}
	return a.f.KernelBySlot(uint32(m.Disp))
}

// recent keeps the last few instructions of the straight-line path being
// walked, for the jump table reader.
type recent struct {
	in [4]x86asm.Inst
	n  int
}

func (r *recent) add(in x86asm.Inst) { r.in[r.n%len(r.in)] = in; r.n++ }

// lastOp is the opcode of the latest instruction on the path, 0 if none.
func (r *recent) lastOp() x86asm.Op {
	if r.n == 0 {
		return 0
	}
	return r.in[(r.n-1)%len(r.in)].Op
}

// indexSetter finds the latest instruction on the path that writes reg,
// looking back a few instructions.
func (r *recent) indexSetter(reg x86asm.Reg) (x86asm.Inst, bool) {
	for k := 1; k <= len(r.in) && k <= r.n; k++ {
		in := r.in[(r.n-k)%len(r.in)]
		if dst, ok := in.Args[0].(x86asm.Reg); ok && dst == reg {
			return in, in.Op != x86asm.CMP && in.Op != x86asm.TEST
		}
	}
	return x86asm.Inst{}, false
}

// jumpTable reads an MSVC switch table, `jmp dword ptr [table + reg*4]`.
// Entries are taken while they point into the function's own section; MSVC
// puts the table right after the function, so the first non-code value ends
// it. Three forms in the CRT's hand-written memcpy/memmove need the code
// before the jump: after `and reg, mask` the table has exactly mask+1
// slots, some of which may never be used (slot 0 can overlap code); after
// `neg reg` the table is indexed backwards from its end; after `sub reg,
// k` taken on a borrow (jb) the index is -k..-1, the k slots below it.
func (a *analyzer) jumpTable(in x86asm.Inst, hist *recent, fnStart uint32) []uint32 {
	m, ok := in.Args[0].(x86asm.Mem)
	if !ok || m.Base != 0 || m.Index == 0 || m.Scale != 4 {
		return nil
	}
	sec := a.f.SectionAt(fnStart)
	table := uint32(m.Disp)
	entry := func(addr uint32) (uint32, bool) {
		v, err := a.f.Uint32(addr)
		return v, err == nil && sec != nil && sec.Contains(v)
	}
	var out []uint32
	if set, ok := hist.indexSetter(m.Index); ok {
		switch set.Op {
		case x86asm.NEG:
			for i := uint32(0); i < 64; i++ {
				v, ok := entry(table - 4*i)
				if !ok {
					break
				}
				out = append(out, v)
			}
			return out
		case x86asm.SUB:
			if k, ok := set.Args[1].(x86asm.Imm); ok && k > 0 && k <= 16 && hist.lastOp() == x86asm.JB {
				for i := uint32(1); i <= uint32(k); i++ {
					if v, ok := entry(table - 4*i); ok {
						out = append(out, v)
					}
				}
				if len(out) > 0 {
					return out
				}
			}
		case x86asm.AND:
			if mask, ok := set.Args[1].(x86asm.Imm); ok && mask >= 0 && mask < 1024 {
				for i := uint32(0); i <= uint32(mask); i++ {
					if v, ok := entry(table + 4*i); ok {
						out = append(out, v)
					}
				}
				return out
			}
		}
	}
	for i := uint32(0); i < 1024; i++ {
		v, ok := entry(table + 4*i)
		if !ok {
			break
		}
		out = append(out, v)
	}
	return out
}

func isCondBranch(op x86asm.Op) bool {
	switch op {
	case x86asm.JA, x86asm.JAE, x86asm.JB, x86asm.JBE, x86asm.JE, x86asm.JNE,
		x86asm.JG, x86asm.JGE, x86asm.JL, x86asm.JLE, x86asm.JO, x86asm.JNO,
		x86asm.JP, x86asm.JNP, x86asm.JS, x86asm.JNS,
		x86asm.JCXZ, x86asm.JECXZ, x86asm.LOOP, x86asm.LOOPE, x86asm.LOOPNE:
		return true
	}
	return false
}

// implausible are instructions MSVC does not emit in game code. Data that
// happens to decode as x86 is full of them.
var implausible = map[x86asm.Op]bool{
	x86asm.AAA: true, x86asm.AAD: true, x86asm.AAM: true, x86asm.AAS: true, x86asm.DAA: true, x86asm.DAS: true,
	x86asm.LES: true, x86asm.LDS: true, x86asm.INTO: true, x86asm.BOUND: true, x86asm.ARPL: true,
	x86asm.IN: true, x86asm.OUT: true, x86asm.INSB: true, x86asm.INSD: true, x86asm.INSW: true,
	x86asm.OUTSB: true, x86asm.OUTSD: true, x86asm.OUTSW: true, x86asm.HLT: true, x86asm.ICEBP: true,
	x86asm.LRET: true, x86asm.LJMP: true, x86asm.LCALL: true, x86asm.IRET: true, x86asm.IRETD: true,
	x86asm.CLI: true, x86asm.STI: true, x86asm.XLATB: true, x86asm.ENTER: true,
	x86asm.SLDT: true, x86asm.STR: true, x86asm.LLDT: true, x86asm.SGDT: true, x86asm.LSL: true,
}

// DriverSections hold the XDK's hardware drivers, whose real code does port
// I/O (the GPU's interrupt handler reads a GPIO port, for one).
var DriverSections = map[string]bool{"D3D": true, "DSOUND": true}

func (a *analyzer) implausibleAt(in x86asm.Inst, va uint32) bool {
	if !implausible[in.Op] {
		return false
	}
	if in.Op == x86asm.IN || in.Op == x86asm.OUT {
		s := a.f.SectionAt(va)
		return s == nil || !DriverSections[s.Name]
	}
	return true
}

// plausible reports whether va looks like the start of real code: a short
// walk of it decodes cleanly, uses no implausible instruction, and never
// jumps into the middle of an instruction it decoded or outside the image.
func (a *analyzer) plausible(va uint32) bool {
	starts := map[uint32]bool{}
	var targets []uint32
	work := []uint32{va}
	for n := 0; len(work) > 0 && n < 256; {
		pc := work[len(work)-1]
		work = work[:len(work)-1]
		for !starts[pc] && n < 256 {
			in, ok := a.decode(pc)
			if !ok || a.implausibleAt(in, pc) || in.Op == 0 {
				return false
			}
			starts[pc] = true
			n++
			next := pc + uint32(in.Len)
			if t, ok := relTarget(in, next); ok && (in.Op == x86asm.JMP || isCondBranch(in.Op) || in.Op == x86asm.CALL) {
				if a.f.SectionAt(t) == nil {
					return false
				}
				targets = append(targets, t)
				if in.Op != x86asm.CALL && a.f.SectionAt(t) == a.f.SectionAt(va) {
					work = append(work, t)
				}
			}
			if in.Op == x86asm.RET || in.Op == x86asm.JMP || in.Op == x86asm.INT || in.Op == x86asm.UD2 {
				break
			}
			pc = next
		}
	}
	// A jump landing inside an instruction this walk decoded means the
	// bytes were never code.
	for _, t := range targets {
		if starts[t] {
			continue
		}
		for back := uint32(1); back < 15 && t >= back; back++ {
			if starts[t-back] {
				if in, ok := a.decode(t - back); ok && t-back+uint32(in.Len) > t {
					return false
				}
				break
			}
		}
	}
	return true
}

// scanImmediates seeds functions from code addresses used as immediate
// operands, as in push offset callback or mov [obj], offset method: how
// atexit handlers, C++ initializers and callbacks are passed around. The
// same plausibility test as data references applies.
func (a *analyzer) scanImmediates(owner map[uint32]uint32) {
	for va := range owner {
		in, ok := a.decode(va)
		if !ok {
			continue
		}
		for _, arg := range in.Args {
			imm, isImm := arg.(x86asm.Imm)
			if !isImm {
				continue
			}
			t := uint32(imm)
			s := a.f.SectionAt(t)
			if s == nil || !a.code[s.Name] || t >= s.VirtualAddr+s.RawSize {
				continue
			}
			if _, known := a.starts[t]; known {
				continue
			}
			if _, taken := owner[t]; !taken && a.looksLikeStart(t) && a.plausible(t) {
				a.addStart(t, FromDataRef)
			}
		}
	}
}

// looksLikeStart reports whether va sits where MSVC puts functions: 16-byte
// aligned, or right after int3/nop padding, a ret or a ret imm16. In
// Forza's .text 89% of call targets are aligned and nearly all follow 0xCC
// padding.
func (a *analyzer) looksLikeStart(va uint32) bool {
	if va%16 == 0 {
		return true
	}
	b, err := a.f.Bytes(va-1, 1)
	if err != nil {
		return false
	}
	if b[0] == 0xCC || b[0] == 0x90 || b[0] == 0xC3 {
		return true
	}
	// Right after ret imm16 (C2 xx xx), which MSVC packs functions behind.
	r, err := a.f.Bytes(va-3, 1)
	if err == nil && r[0] == 0xC2 {
		return true
	}
	// Right after a function that ends in an unconditional jump (EB xx or
	// E9 xx xx xx xx): DSOUND packs functions behind those too.
	if j, err := a.f.Bytes(va-2, 1); err == nil && j[0] == 0xEB {
		return true
	}
	j, err := a.f.Bytes(va-5, 1)
	return err == nil && j[0] == 0xE9
}

// scanPrologues seeds `push ebp; mov ebp, esp` (55 8B EC) found in unowned
// bytes of code sections, where the position also looks like a function
// start.
func (a *analyzer) scanPrologues(owner map[uint32]uint32) {
	for i := range a.f.Sections {
		s := &a.f.Sections[i]
		if !a.code[s.Name] {
			continue
		}
		d := a.f.SectionData(s)
		for off := 1; off+3 <= len(d); off++ {
			if d[off] != 0x55 || d[off+1] != 0x8B || d[off+2] != 0xEC {
				continue
			}
			va := s.VirtualAddr + uint32(off)
			if _, taken := owner[va]; !taken && a.looksLikeStart(va) {
				a.addStart(va, FromPrologue)
			}
		}
	}
}

// scanDataRefs seeds functions from pointers to code found in data,
// including data inside code sections (XPP keeps its device tables next to
// its code; bytes of decoded instructions are skipped, scanImmediates
// covers those). A run of two or more pointers is a table: vtables,
// initializer lists, callback tables. A pointer that has a known function
// as a neighbour vouches for the others. Lone pointers and unvouched
// tables must also sit where MSVC aligns functions, and every candidate
// must pass plausible. Pointers into the middle of a known function are
// skipped: those are SEH scope-table handlers and similar labels.
//
// Generosity is safe here: a false start only adds translated code that
// never runs, and even one inside a real function stays correct, because a
// jump to it becomes a tail call into the same code.
func (a *analyzer) scanDataRefs(owner map[uint32]uint32) {
	isCode := func(v uint32) bool {
		s := a.f.SectionAt(v)
		return s != nil && a.code[s.Name] && v < s.VirtualAddr+s.RawSize
	}
	covered := map[uint32]bool{} // bytes of decoded instructions
	for va := range owner {
		if in, ok := a.decode(va); ok {
			for k := 0; k < in.Len; k++ {
				covered[va+uint32(k)] = true
			}
		}
	}
	for i := range a.f.Sections {
		s := &a.f.Sections[i]
		d := a.f.SectionData(s)
		inCode := a.code[s.Name]
		var run []uint32
		flush := func() {
			vouched := false
			for _, v := range run {
				if _, known := a.starts[v]; known && len(run) >= 2 {
					vouched = true
				}
			}
			for _, v := range run {
				if _, known := a.starts[v]; known {
					continue
				}
				if _, taken := owner[v]; taken || (!vouched && !a.looksLikeStart(v)) {
					continue
				}
				if a.plausible(v) {
					a.addStart(v, FromDataRef)
				}
			}
			run = run[:0]
		}
		for off := 0; off+4 <= len(d); off += 4 {
			va := s.VirtualAddr + uint32(off)
			if inCode && (covered[va] || covered[va+3]) {
				flush()
				continue
			}
			v := binary.LittleEndian.Uint32(d[off:])
			if isCode(v) {
				run = append(run, v)
			} else {
				flush()
			}
		}
		flush()
	}
}

// Inst is one decoded instruction at its address.
type Inst struct {
	Addr uint32
	x86asm.Inst
}

// Next is the address just after the instruction.
func (in Inst) Next() uint32 { return in.Addr + uint32(in.Len) }

// Body is everything reachable from a function's entry without passing
// through another function's entry: the code a translator must emit for it.
type Body struct {
	Start  uint32
	Insts  []Inst              // in address order
	Tables map[uint32][]uint32 // jmp address -> switch table targets
	Bad    []uint32            // addresses that would not decode
}

// Body walks a function the way discovery does, but ignores ownership.
// Code that several functions share (MSVC merges common tails) appears in
// each of them, which a translator needs because it cannot jump between
// host functions.
func (p *Program) Body(start uint32) Body {
	a := p.a
	b := Body{Start: start, Tables: map[uint32][]uint32{}}
	seen := map[uint32]bool{}
	work := []uint32{start}
	branchHist := map[uint32]recent{} // the path so far, at each branch target
	for len(work) > 0 {
		va := work[len(work)-1]
		work = work[:len(work)-1]
		hist := branchHist[va]
	path:
		for !seen[va] {
			if va != start {
				if _, isFunc := a.starts[va]; isFunc {
					break // tail call; the translator emits it as a call
				}
			}
			in, ok := a.decode(va)
			if !ok {
				b.Bad = append(b.Bad, va)
				break
			}
			seen[va] = true
			b.Insts = append(b.Insts, Inst{Addr: va, Inst: in})
			next := va + uint32(in.Len)
			switch in.Op {
			case x86asm.RET, x86asm.IRET, x86asm.HLT, x86asm.UD2, x86asm.INT:
				break path
			case x86asm.JMP:
				if t, ok := relTarget(in, next); ok {
					if a.f.SectionAt(t) == a.f.SectionAt(start) {
						work = append(work, t)
					}
				} else if _, ok := a.thunkRef(in); !ok {
					if targets := a.jumpTable(in, &hist, start); len(targets) > 0 {
						b.Tables[va] = targets
						work = append(work, targets...)
					}
				}
				break path
			default:
				if isCondBranch(in.Op) {
					if t, ok := relTarget(in, next); ok {
						work = append(work, t)
						if _, ok := branchHist[t]; !ok {
							h := hist
							h.add(in)
							branchHist[t] = h
						}
					}
				}
			}
			hist.add(in)
			va = next
		}
	}
	sort.Slice(b.Insts, func(i, j int) bool { return b.Insts[i].Addr < b.Insts[j].Addr })
	return b
}

// IsFunc reports whether va is a discovered function start.
func (p *Program) IsFunc(va uint32) bool {
	_, ok := p.a.starts[va]
	return ok
}
