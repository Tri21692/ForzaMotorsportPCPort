// xbemap finds the functions in an XBE and writes a symbol map.
//
//	xbemap default.xbe                 # summary on stdout
//	xbemap -o forza.map default.xbe    # also write the full function list
//
// Map lines are: address, size, section, how it was found, name, then the
// kernel imports the function calls directly.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func main() {
	out := flag.String("o", "", "write the function map to this file")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: xbemap [-o file.map] default.xbe")
		flag.PrintDefaults()
	}
	flag.Parse()
	if flag.NArg() != 1 {
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
	p := analysis.Analyze(f)
	summary(p)
	if *out != "" {
		if err := writeMap(p, *out); err != nil {
			fail(err)
		}
		fmt.Printf("\nwrote %s\n", *out)
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}

func summary(p *analysis.Program) {
	type secStat struct {
		funcs, bytes int
		bySrc        [5]int
	}
	stats := map[string]*secStat{}
	var bad, unresolved, tables, indirect int
	for _, fn := range p.Funcs {
		st := stats[fn.Section]
		if st == nil {
			st = &secStat{}
			stats[fn.Section] = st
		}
		st.funcs++
		st.bytes += fn.Bytes
		st.bySrc[fn.Source]++
		if fn.BadDecode {
			bad++
		}
		unresolved += fn.Unresolved
		tables += fn.JumpTables
		indirect += fn.IndirectCalls
	}

	fmt.Printf("%d functions after %d discovery rounds\n\n", len(p.Funcs), p.Rounds)
	fmt.Printf("  %-10s %6s %9s %6s   %s\n", "section", "funcs", "code", "cover", "found by entry/call/tailjump/prologue/dataref")
	// Several sections share a name (BINKYUY2), so sum their sizes per name.
	size := map[string]uint32{}
	var names []string
	for _, s := range p.File.Sections {
		if p.Code[s.Name] {
			if _, ok := size[s.Name]; !ok {
				names = append(names, s.Name)
			}
			size[s.Name] += s.RawSize
		}
	}
	for _, name := range names {
		st := stats[name]
		if st == nil {
			st = &secStat{}
		}
		fmt.Printf("  %-10s %6d %9d %5.1f%%   %v\n", name, st.funcs, st.bytes,
			100*float64(st.bytes)/float64(size[name]), st.bySrc)
	}
	fmt.Printf("\n  jump tables resolved   %d\n", tables)
	fmt.Printf("  unresolved jumps       %d\n", unresolved)
	fmt.Printf("  indirect calls         %d\n", indirect)
	fmt.Printf("  functions w/ bad bytes %d\n", bad)

	used := map[uint32]int{}
	for _, fn := range p.Funcs {
		seen := map[uint32]bool{}
		for _, k := range fn.KernelCalls {
			if !seen[k] {
				used[k]++
				seen[k] = true
			}
		}
	}
	var never []string
	for _, k := range p.File.Kernel {
		if k.Conv != xbe.Data && used[k.Ordinal] == 0 {
			never = append(never, k.Name)
		}
	}
	fmt.Printf("\n%d of %d kernel imports are called directly from found code\n", len(used), len(p.File.Kernel))
	if len(never) > 0 {
		sort.Strings(never)
		fmt.Printf("functions imported but not seen called (%d): %s\n", len(never), strings.Join(never, ", "))
	}
}

func writeMap(p *analysis.Program, path string) error {
	fh, err := os.Create(path)
	if err != nil {
		return err
	}
	w := bufio.NewWriter(fh)
	fmt.Fprintf(w, "# %s (%08X) function map from xbemap\n", p.File.Certificate.TitleName, p.File.Certificate.TitleID)
	fmt.Fprintln(w, "# addr     size     section    source    name  [kernel calls]")
	for _, fn := range p.Sorted() {
		name := fmt.Sprintf("sub_%08X", fn.Addr)
		if fn.Source == analysis.FromEntry {
			name = "entry"
		}
		fmt.Fprintf(w, "%08X %08X %-10s %-9s %s", fn.Addr, fn.End-fn.Addr, fn.Section, fn.Source, name)
		if len(fn.KernelCalls) > 0 {
			seen := map[uint32]bool{}
			var ks []string
			for _, o := range fn.KernelCalls {
				if !seen[o] {
					seen[o] = true
					k, _ := xbe.LookupKernel(o)
					ks = append(ks, k.Name)
				}
			}
			fmt.Fprintf(w, "  [%s]", strings.Join(ks, " "))
		}
		fmt.Fprintln(w)
	}
	if err := w.Flush(); err != nil {
		fh.Close()
		return err
	}
	return fh.Close()
}
