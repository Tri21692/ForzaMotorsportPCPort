// xbedis disassembles one function from an XBE, in Intel syntax, with call
// targets, kernel imports and library symbols named.
//
//	xbedis default.xbe 0x268EB5
//	xbedis -xbsdb ~/XbSymbolDatabase default.xbe D3DDevice_Clear
//
// A function is printed as the instructions function discovery assigned
// to it, in address order; a blank line marks a jump to a separate chunk.
package main

import (
	"flag"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"

	"golang.org/x/arch/x86/x86asm"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/sigdb"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func main() {
	dbDir := flag.String("xbsdb", "", "XbSymbolDatabase checkout, to name library symbols")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: xbedis [-xbsdb dir] default.xbe address|name")
		flag.PrintDefaults()
	}
	flag.Parse()
	if flag.NArg() != 2 {
		flag.Usage()
		os.Exit(2)
	}
	raw, err := os.ReadFile(flag.Arg(0))
	if err != nil {
		fail(err)
	}
	f, err := xbe.Parse(raw)
	if err != nil {
		fail(err)
	}

	syms := sigdb.ScanCRT(f)
	if *dbDir != "" {
		db, err := sigdb.Load(*dbDir)
		if err != nil {
			fail(err)
		}
		syms = append(syms, sigdb.Scan(f, db)...)
	}
	names := map[uint32]string{}
	var seeds []uint32
	for _, m := range syms {
		names[m.Addr] = m.Name
		if m.Kind == sigdb.Function {
			seeds = append(seeds, m.Addr)
		}
	}
	for _, k := range f.Kernel {
		names[k.Slot] = "__imp_" + k.Name
	}
	p := analysis.Analyze(f, seeds...)
	for va := range p.Funcs {
		if _, ok := names[va]; !ok {
			names[va] = fmt.Sprintf("sub_%08X", va)
		}
	}

	start, err := resolve(flag.Arg(1), names)
	if err != nil {
		fail(err)
	}
	fn := p.Funcs[start]
	if fn == nil {
		fail(fmt.Errorf("no function starts at %#x (is it inside another one? owner %#x)", start, p.Owner[start]))
	}

	var addrs []uint32
	for va, owner := range p.Owner {
		if owner == start {
			addrs = append(addrs, va)
		}
	}
	sort.Slice(addrs, func(i, j int) bool { return addrs[i] < addrs[j] })

	symname := func(a uint64) (string, uint64) {
		if n, ok := names[uint32(a)]; ok {
			return n, a
		}
		return "", 0
	}
	fmt.Printf("; %s  %s  found by %s, %d instructions\n", names[start], fn.Section, fn.Source, fn.Insns)
	var next uint32
	for i, va := range addrs {
		if i > 0 && va != next {
			fmt.Println()
		}
		b, err := f.Bytes(va, min(15, fn.End-va+15))
		if err != nil {
			b, _ = f.Bytes(va, 1)
		}
		in, err := x86asm.Decode(b, 32)
		if err != nil {
			fmt.Printf("%08X  (bad)\n", va)
			next = va + 1
			continue
		}
		label := ""
		if n, ok := names[va]; ok && va != start {
			label = "  ; " + n
		}
		fmt.Printf("%08X  %-20x  %s%s\n", va, b[:in.Len], x86asm.IntelSyntax(in, uint64(va), symname), label)
		next = va + uint32(in.Len)
	}
}

func resolve(arg string, names map[uint32]string) (uint32, error) {
	if v, err := strconv.ParseUint(strings.TrimPrefix(strings.ToLower(arg), "0x"), 16, 32); err == nil {
		return uint32(v), nil
	}
	for va, n := range names {
		if n == arg {
			return va, nil
		}
	}
	return 0, fmt.Errorf("no symbol named %q (pass -xbsdb to load library names)", arg)
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
