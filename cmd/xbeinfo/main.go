// xbeinfo prints what an XBE contains: header, certificate, sections,
// linked XDK libraries, TLS and kernel imports.
//
//	xbeinfo default.xbe
//	xbeinfo -kernel default.xbe   # also list every kernel import
package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

func main() {
	listKernel := flag.Bool("kernel", false, "list every kernel import")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "usage: xbeinfo [-kernel] default.xbe")
		flag.PrintDefaults()
	}
	flag.Parse()
	if flag.NArg() != 1 {
		flag.Usage()
		os.Exit(2)
	}
	raw, err := os.ReadFile(flag.Arg(0))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	f, err := xbe.Parse(raw)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	h, c := f.Header, f.Certificate
	kind := "retail"
	if f.Debug {
		kind = "debug"
	}
	fmt.Printf("Title        %s (%08X), version %d, disc %d\n", c.TitleName, c.TitleID, c.Version, c.DiskNumber)
	fmt.Printf("Region       %#x   Media %#x   Ratings %#x\n", c.GameRegion, c.AllowedMedia, c.GameRatings)
	fmt.Printf("Built        %s\n", time.Unix(int64(h.TimeDate), 0).UTC().Format(time.RFC3339))
	fmt.Printf("Build kind   %s\n", kind)
	fmt.Printf("Base         %#08x   image size %#x   headers %#x\n", h.BaseAddress, h.SizeOfImage, h.SizeOfHeaders)
	fmt.Printf("Entry point  %#08x\n", f.EntryPoint)
	fmt.Printf("Kernel thunk %#08x (%d imports)\n", f.KernelThunk, len(f.Kernel))
	fmt.Printf("Stack commit %#x   heap reserve %#x   heap commit %#x\n", h.StackCommit, h.HeapReserve, h.HeapCommit)
	fmt.Printf("Init flags   %#x\n", h.InitFlags)
	if t := f.TLS; t != nil {
		fmt.Printf("TLS          data %#08x-%#08x  index %#08x  callbacks %#08x  zero-fill %#x\n",
			t.DataStart, t.DataEnd, t.IndexAddr, t.CallbacksAddr, t.SizeOfZeroFill)
	}

	fmt.Printf("\nSections (%d)\n", len(f.Sections))
	fmt.Printf("  %-10s %-10s %-10s %-10s %-6s %s\n", "name", "vaddr", "vsize", "rawsize", "flags", "sha1")
	for i := range f.Sections {
		s := &f.Sections[i]
		ok := "ok"
		if !f.VerifyDigest(s) {
			ok = "MISMATCH"
		}
		fmt.Printf("  %-10s %#08x %#08x %#08x %-6s %s\n", s.Name, s.VirtualAddr, s.VirtualSize, s.RawSize, flags(s.Flags), ok)
	}

	fmt.Printf("\nXDK libraries (%d)\n", len(f.Libraries))
	for _, l := range f.Libraries {
		fmt.Printf("  %s\n", l)
	}

	if *listKernel {
		fmt.Printf("\nKernel imports (%d)\n", len(f.Kernel))
		for _, k := range f.Kernel {
			fmt.Printf("  %#08x  %3d  %-40s %s/%d\n", k.Slot, k.Ordinal, k.Name, k.Conv, k.ArgBytes)
		}
	}
}

// flags renders section flags as W P X I H T (writable, preload, executable,
// inserted file, head page RO, tail page RO).
func flags(v uint32) string {
	out := []byte("------")
	for i, c := range "WPXIHT" {
		if v&(1<<i) != 0 {
			out[i] = byte(c)
		}
	}
	return string(out)
}
