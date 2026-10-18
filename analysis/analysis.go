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
	FromTailJump
	FromPrologue
	FromDataRef
)

func (s Source) String() string {
	return [...]string{"entry", "call", "tailjump", "prologue", "dataref"}[s]
}

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

// Analyze discovers the code in f.
func Analyze(f *xbe.File) *Program {
	a := &analyzer{f: f, starts: map[uint32]Source{}, code: map[string]bool{}}
	a.addStart(f.EntryPoint, FromEntry)

	p := &Program{File: f, Code: a.code}
	for {
		p.Rounds++
		before := len(a.starts)
		funcs, owner := a.descendAll()
		a.scanPrologues(owner)
		a.scanDataRefs(owner)
		if len(a.starts) == before {
			p.Funcs, p.Owner = funcs, owner
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
	n := s.VirtualAddr + s.RawSize - va
	if va >= s.VirtualAddr+s.RawSize {
		return x86asm.Inst{}, false
	}
	if n > 15 {
		n = 15
	}
	b, err := a.f.Bytes(va, n)
	if err != nil {
		return x86asm.Inst{}, false
	}
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
	for len(work) > 0 {
		va := work[len(work)-1]
		work = work[:len(work)-1]
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
				} else if targets := a.jumpTable(in, start); len(targets) > 0 {
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
					}
				}
			}
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

// jumpTable reads an MSVC switch table, `jmp dword ptr [table + reg*4]`.
// Entries are taken while they point into the function's own section; MSVC
// puts the table right after the function, so the first non-code value ends
// it.
func (a *analyzer) jumpTable(in x86asm.Inst, fnStart uint32) []uint32 {
	m, ok := in.Args[0].(x86asm.Mem)
	if !ok || m.Base != 0 || m.Index == 0 || m.Scale != 4 {
		return nil
	}
	sec := a.f.SectionAt(fnStart)
	table := uint32(m.Disp)
	var out []uint32
	for i := uint32(0); i < 1024; i++ {
		v, err := a.f.Uint32(table + 4*i)
		if err != nil || sec == nil || !sec.Contains(v) {
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

// looksLikeStart reports whether va sits where MSVC puts functions: 16-byte
// aligned, or right after int3/nop padding or a ret. In Forza's .text 89% of
// call targets are aligned and nearly all follow 0xCC padding.
func (a *analyzer) looksLikeStart(va uint32) bool {
	if va%16 == 0 {
		return true
	}
	b, err := a.f.Bytes(va-1, 1)
	if err != nil {
		return false
	}
	return b[0] == 0xCC || b[0] == 0x90 || b[0] == 0xC3
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

// scanDataRefs seeds functions from runs of at least two consecutive aligned
// pointers to code in non-code sections (vtables, callback tables). Single
// pointers are too often coincidences to trust. Pointers into the middle of
// a known function are skipped: those are SEH scope-table handlers and
// similar labels, not new functions.
func (a *analyzer) scanDataRefs(owner map[uint32]uint32) {
	isCode := func(v uint32) bool {
		s := a.f.SectionAt(v)
		return s != nil && a.code[s.Name] && v < s.VirtualAddr+s.RawSize
	}
	for i := range a.f.Sections {
		s := &a.f.Sections[i]
		if a.code[s.Name] {
			continue
		}
		d := a.f.SectionData(s)
		var run []uint32
		flush := func() {
			if len(run) >= 2 {
				for _, v := range run {
					if _, known := a.starts[v]; known {
						continue
					}
					if _, taken := owner[v]; taken || !a.looksLikeStart(v) {
						continue
					}
					if _, ok := a.decode(v); ok {
						a.addStart(v, FromDataRef)
					}
				}
			}
			run = run[:0]
		}
		for off := 0; off+4 <= len(d); off += 4 {
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
