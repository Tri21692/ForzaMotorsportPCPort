package xbe

import "fmt"

//go:generate go run gen_kernel.go

// CallConv is how a kernel export is called, which decides who pops the
// arguments. The HLE kernel needs this to return to the game correctly.
type CallConv int

const (
	Stdcall  CallConv = iota // callee pops ArgBytes
	Fastcall                 // first two dword args in ECX/EDX, callee pops the rest
	Cdecl                    // caller pops (only DbgPrint)
	Data                     // not a function: the thunk holds a variable's address
)

func (c CallConv) String() string {
	switch c {
	case Stdcall:
		return "stdcall"
	case Fastcall:
		return "fastcall"
	case Cdecl:
		return "cdecl"
	case Data:
		return "data"
	}
	return fmt.Sprintf("CallConv(%d)", int(c))
}

// KernelExport is one xboxkrnl.exe export, identified by ordinal.
type KernelExport struct {
	Ordinal  uint32
	Name     string
	Conv     CallConv
	ArgBytes int // total argument bytes from the decorated name; for fastcall this includes the ECX/EDX args
}

// LookupKernel returns the export for an ordinal. Unknown ordinals get a
// placeholder name so callers never have to special-case them.
func LookupKernel(ordinal uint32) (KernelExport, bool) {
	e, ok := kernelExports[ordinal]
	if !ok {
		return KernelExport{Ordinal: ordinal, Name: fmt.Sprintf("KernelOrdinal%d", ordinal)}, false
	}
	return e, true
}

// KernelByName finds an export by its undecorated name.
func KernelByName(name string) (KernelExport, bool) {
	for _, e := range kernelExports {
		if e.Name == name {
			return e, true
		}
	}
	return KernelExport{}, false
}
