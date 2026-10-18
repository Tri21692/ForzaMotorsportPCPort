// xbesyms lists the XDK library symbols found in an XBE.
//
//	xbesyms default.xbe                            # C runtime only
//	xbesyms -xbsdb ~/XbSymbolDatabase default.xbe  # plus XDK libraries
//
// Each line is: address, library, signature revision, kind, name.
package main

import (
	"flag"
	"fmt"
	"os"
	"sort"

	"github.com/Tri21692/ForzaMotorsportPC/sigdb"
	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func main() {
	dbDir := flag.String("xbsdb", "", "XbSymbolDatabase checkout, to name XDK library symbols")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: xbesyms [-xbsdb dir] default.xbe")
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
	sort.Slice(syms, func(i, j int) bool { return syms[i].Addr < syms[j].Addr })
	for _, m := range syms {
		lib := m.Library
		if lib == "" {
			lib = "-"
		}
		fmt.Printf("%08X %-8s %4d %-8s %s\n", m.Addr, lib, m.Version, m.Kind, m.Name)
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
