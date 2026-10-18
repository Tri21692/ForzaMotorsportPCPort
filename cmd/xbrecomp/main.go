// xbrecomp translates every discovered function in an XBE to C and reports
// how much of the game the translator can handle.
//
//	xbrecomp default.xbe                    # coverage report only
//	xbrecomp -o out/ default.xbe            # also write the C files
//	xbrecomp -xbsdb ~/XbSymbolDatabase -o out/ default.xbe
//
// The output is funcs.h, dispatch.c, code_NNNN.c and the runtime header
// xbrt.h. Unsupported instructions are compiled as traps, so the files
// build even while coverage is incomplete.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/Tri21692/ForzaMotorsportPC/analysis"
	"github.com/Tri21692/ForzaMotorsportPC/recomp"
	"github.com/Tri21692/ForzaMotorsportPC/sigdb"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func main() {
	outDir := flag.String("o", "", "write C files to this directory")
	dbDir := flag.String("xbsdb", "", "XbSymbolDatabase checkout, to name library functions")
	top := flag.Int("top", 25, "how many unsupported instructions to list")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: xbrecomp [-xbsdb dir] [-o dir] default.xbe")
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
	syms := sigdb.ScanCRT(f)
	if *dbDir != "" {
		db, err := sigdb.Load(*dbDir)
		if err != nil {
			fail(err)
		}
		syms = append(syms, sigdb.Scan(f, db)...)
	}
	names, vars := map[uint32]string{}, map[uint32]string{}
	var seeds []uint32
	for _, m := range syms {
		if m.Kind == sigdb.Function {
			names[m.Addr] = m.Name
			seeds = append(seeds, m.Addr)
		} else if f.SectionAt(m.Addr) != nil {
			vars[m.Addr] = m.Name // a real global, not a derived struct offset
		}
	}
	p := analysis.Analyze(f, seeds...)
	var funcs []uint32
	for va := range p.Funcs {
		funcs = append(funcs, va)
	}

	t := &recomp.Translator{P: p, F: f, Names: names, Vars: vars}
	files, out := t.Program(funcs, 500)
	report(out, *top)

	if *outDir != "" {
		if err := os.MkdirAll(*outDir, 0o755); err != nil {
			fail(err)
		}
		hdr, err := recomp.Runtime.ReadFile("runtime/xbrt.h")
		if err != nil {
			fail(err)
		}
		files["xbrt.h"] = string(hdr)
		for name, body := range files {
			if err := os.WriteFile(filepath.Join(*outDir, name), []byte(body), 0o644); err != nil {
				fail(err)
			}
		}
		fmt.Printf("\nwrote %d files to %s\n", len(files), *outDir)
	}
}

func report(out []recomp.Func, top int) {
	clean, insts, cleanInsts := 0, 0, 0
	ops := map[string]int{}
	funcsWith := map[string]int{}
	for _, fn := range out {
		insts += fn.Insts
		if len(fn.Unsupported) == 0 {
			clean++
			cleanInsts += fn.Insts
		}
		for op, n := range fn.Unsupported {
			ops[op] += n
			funcsWith[op]++
		}
	}
	fmt.Printf("%d functions, %d instructions\n", len(out), insts)
	fmt.Printf("fully translated: %d functions (%.1f%%), %d instructions (%.1f%%)\n",
		clean, pct(clean, len(out)), cleanInsts, pct(cleanInsts, insts))

	type kv struct {
		op string
		n  int
	}
	var l []kv
	for op, n := range ops {
		l = append(l, kv{op, n})
	}
	sort.Slice(l, func(i, j int) bool {
		if funcsWith[l[i].op] != funcsWith[l[j].op] {
			return funcsWith[l[i].op] > funcsWith[l[j].op]
		}
		return l[i].op < l[j].op
	})
	fmt.Printf("\nunsupported, by functions affected:\n")
	for i, x := range l {
		if i == top {
			fmt.Printf("  ... %d more\n", len(l)-top)
			break
		}
		fmt.Printf("  %-28s %6d functions %7d uses\n", x.op, funcsWith[x.op], x.n)
	}
}

func pct(a, b int) float64 {
	if b == 0 {
		return 0
	}
	return 100 * float64(a) / float64(b)
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
