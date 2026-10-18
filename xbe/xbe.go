// Package xbe reads original Xbox executables (.xbe).
//
// Layout notes come from the XboxDev wiki and Caustik's XBE format notes.
// Every address in the header is a virtual address relative to BaseAddress
// (0x10000 on retail titles); the image header itself is mapped there.
package xbe

import (
	"crypto/sha1"
	"encoding/binary"
	"errors"
	"fmt"
	"unicode/utf16"
)

// XOR keys that hide the entry point and kernel thunk address.
const (
	EntryRetailKey = 0xA8FC57AB
	EntryDebugKey  = 0x94859D4B
	ThunkRetailKey = 0x5B6D40B6
	ThunkDebugKey  = 0xEFB1F152
)

// Section flags.
const (
	SecWritable         = 0x01
	SecPreload          = 0x02
	SecExecutable       = 0x04
	SecInsertedFile     = 0x08
	SecHeadPageReadOnly = 0x10
	SecTailPageReadOnly = 0x20
)

type Header struct {
	BaseAddress        uint32
	SizeOfHeaders      uint32
	SizeOfImage        uint32
	SizeOfImageHeader  uint32
	TimeDate           uint32
	CertificateAddr    uint32
	NumSections        uint32
	SectionHeadersAddr uint32
	InitFlags          uint32
	EntryPointRaw      uint32
	TLSAddr            uint32
	StackCommit        uint32
	HeapReserve        uint32
	HeapCommit         uint32
	PEBaseAddr         uint32
	PESizeOfImage      uint32
	PEChecksum         uint32
	PETimeDate         uint32
	DebugPathAddr      uint32
	DebugFileAddr      uint32
	DebugUnicodeAddr   uint32
	KernelThunkRaw     uint32
	NonKernelImportDir uint32
	NumLibraries       uint32
	LibrariesAddr      uint32
	KernelLibAddr      uint32
	XAPILibAddr        uint32
	LogoAddr           uint32
	LogoSize           uint32
}

type Certificate struct {
	TitleID          uint32
	TitleName        string
	AllowedMedia     uint32
	GameRegion       uint32
	GameRatings      uint32
	DiskNumber       uint32
	Version          uint32
	AlternateTitleID [16]uint32
}

type Section struct {
	Name        string
	Flags       uint32
	VirtualAddr uint32
	VirtualSize uint32
	RawAddr     uint32
	RawSize     uint32
	Digest      [20]byte
}

func (s *Section) Contains(va uint32) bool {
	return va >= s.VirtualAddr && va-s.VirtualAddr < s.VirtualSize
}

func (s *Section) End() uint32 { return s.VirtualAddr + s.VirtualSize }

// Library is one statically linked XDK library and its version.
type Library struct {
	Name                string
	Major, Minor, Build uint16
	Flags               uint16
}

func (l Library) String() string {
	return fmt.Sprintf("%s %d.%d.%d", l.Name, l.Major, l.Minor, l.Build)
}

// TLS is the image's thread-local storage directory.
type TLS struct {
	DataStart, DataEnd uint32
	IndexAddr          uint32
	CallbacksAddr      uint32
	SizeOfZeroFill     uint32
	Characteristics    uint32
}

// KernelImport is one slot of the kernel thunk table. The loader overwrites
// Slot with the address of the export; game code calls through it.
type KernelImport struct {
	Slot uint32 // virtual address of the thunk slot
	KernelExport
}

type File struct {
	Header      Header
	Certificate Certificate
	Sections    []Section
	Libraries   []Library
	TLS         *TLS
	Debug       bool   // entry point decoded with the debug key
	EntryPoint  uint32 // decoded
	KernelThunk uint32 // decoded address of the thunk table
	Kernel      []KernelImport

	raw []byte
}

// Parse decodes an XBE held in memory. The slice is kept, not copied.
func Parse(raw []byte) (*File, error) {
	if len(raw) < 0x178 || string(raw[:4]) != "XBEH" {
		return nil, errors.New("xbe: not an XBE (missing XBEH magic)")
	}
	f := &File{raw: raw}
	h := &f.Header
	fields := []*uint32{
		&h.BaseAddress, &h.SizeOfHeaders, &h.SizeOfImage, &h.SizeOfImageHeader,
		&h.TimeDate, &h.CertificateAddr, &h.NumSections, &h.SectionHeadersAddr,
		&h.InitFlags, &h.EntryPointRaw, &h.TLSAddr, &h.StackCommit,
		&h.HeapReserve, &h.HeapCommit, &h.PEBaseAddr, &h.PESizeOfImage,
		&h.PEChecksum, &h.PETimeDate, &h.DebugPathAddr, &h.DebugFileAddr,
		&h.DebugUnicodeAddr, &h.KernelThunkRaw, &h.NonKernelImportDir,
		&h.NumLibraries, &h.LibrariesAddr, &h.KernelLibAddr, &h.XAPILibAddr,
		&h.LogoAddr, &h.LogoSize,
	}
	for i, p := range fields {
		*p = binary.LittleEndian.Uint32(raw[0x104+4*i:])
	}
	if h.SizeOfHeaders > uint32(len(raw)) {
		return nil, fmt.Errorf("xbe: header size %#x past end of file", h.SizeOfHeaders)
	}

	if err := f.parseSections(); err != nil {
		return nil, err
	}
	f.decodeKeys()
	if err := f.parseCertificate(); err != nil {
		return nil, err
	}
	if err := f.parseLibraries(); err != nil {
		return nil, err
	}
	if err := f.parseKernelThunks(); err != nil {
		return nil, err
	}
	if h.TLSAddr != 0 {
		var t TLS
		if err := f.readStruct(h.TLSAddr, []*uint32{&t.DataStart, &t.DataEnd, &t.IndexAddr,
			&t.CallbacksAddr, &t.SizeOfZeroFill, &t.Characteristics}); err != nil {
			return nil, fmt.Errorf("xbe: TLS directory: %w", err)
		}
		f.TLS = &t
	}
	return f, nil
}

// header reads n bytes of the image header at virtual address va.
func (f *File) header(va, n uint32) ([]byte, error) {
	off := va - f.Header.BaseAddress
	if va < f.Header.BaseAddress || off+n > f.Header.SizeOfHeaders || off+n < off {
		return nil, fmt.Errorf("xbe: %#x+%#x outside image header", va, n)
	}
	return f.raw[off : off+n], nil
}

func (f *File) headerString(va uint32) (string, error) {
	if _, err := f.header(va, 1); err != nil {
		return "", err
	}
	start := va - f.Header.BaseAddress
	end := start
	for end < f.Header.SizeOfHeaders && f.raw[end] != 0 {
		end++
	}
	return string(f.raw[start:end]), nil
}

func (f *File) parseSections() error {
	h := &f.Header
	if h.NumSections > 256 {
		return fmt.Errorf("xbe: implausible section count %d", h.NumSections)
	}
	b, err := f.header(h.SectionHeadersAddr, h.NumSections*0x38)
	if err != nil {
		return fmt.Errorf("xbe: section headers: %w", err)
	}
	for i := uint32(0); i < h.NumSections; i++ {
		e := b[i*0x38:]
		s := Section{
			Flags:       binary.LittleEndian.Uint32(e[0:]),
			VirtualAddr: binary.LittleEndian.Uint32(e[4:]),
			VirtualSize: binary.LittleEndian.Uint32(e[8:]),
			RawAddr:     binary.LittleEndian.Uint32(e[12:]),
			RawSize:     binary.LittleEndian.Uint32(e[16:]),
		}
		copy(s.Digest[:], e[0x24:0x38])
		if uint64(s.RawAddr)+uint64(s.RawSize) > uint64(len(f.raw)) {
			return fmt.Errorf("xbe: section %d raw data past end of file", i)
		}
		if s.RawSize > s.VirtualSize {
			return fmt.Errorf("xbe: section %d raw size %#x exceeds virtual size %#x", i, s.RawSize, s.VirtualSize)
		}
		if s.Name, err = f.headerString(binary.LittleEndian.Uint32(e[20:])); err != nil {
			return fmt.Errorf("xbe: section %d name: %w", i, err)
		}
		f.Sections = append(f.Sections, s)
	}
	return nil
}

// decodeKeys un-XORs the entry point and thunk address. Retail and debug
// keys are both tried; the right one lands inside a section.
func (f *File) decodeKeys() {
	h := &f.Header
	f.EntryPoint = h.EntryPointRaw ^ EntryRetailKey
	f.KernelThunk = h.KernelThunkRaw ^ ThunkRetailKey
	if f.SectionAt(f.EntryPoint) == nil {
		if ep := h.EntryPointRaw ^ EntryDebugKey; f.SectionAt(ep) != nil {
			f.EntryPoint = ep
			f.KernelThunk = h.KernelThunkRaw ^ ThunkDebugKey
			f.Debug = true
		}
	}
}

func (f *File) parseCertificate() error {
	b, err := f.header(f.Header.CertificateAddr, 0xB0)
	if err != nil {
		return fmt.Errorf("xbe: certificate: %w", err)
	}
	c := &f.Certificate
	c.TitleID = binary.LittleEndian.Uint32(b[8:])
	u := make([]uint16, 0, 40)
	for i := 0; i < 40; i++ {
		r := binary.LittleEndian.Uint16(b[12+2*i:])
		if r == 0 {
			break
		}
		u = append(u, r)
	}
	c.TitleName = string(utf16.Decode(u))
	for i := range c.AlternateTitleID {
		c.AlternateTitleID[i] = binary.LittleEndian.Uint32(b[0x5C+4*i:])
	}
	c.AllowedMedia = binary.LittleEndian.Uint32(b[0x9C:])
	c.GameRegion = binary.LittleEndian.Uint32(b[0xA0:])
	c.GameRatings = binary.LittleEndian.Uint32(b[0xA4:])
	c.DiskNumber = binary.LittleEndian.Uint32(b[0xA8:])
	c.Version = binary.LittleEndian.Uint32(b[0xAC:])
	return nil
}

func (f *File) parseLibraries() error {
	h := &f.Header
	if h.NumLibraries > 1024 {
		return fmt.Errorf("xbe: implausible library count %d", h.NumLibraries)
	}
	b, err := f.header(h.LibrariesAddr, h.NumLibraries*16)
	if err != nil {
		return fmt.Errorf("xbe: library versions: %w", err)
	}
	for i := uint32(0); i < h.NumLibraries; i++ {
		e := b[i*16:]
		name := e[:8]
		for j, c := range name {
			if c == 0 {
				name = name[:j]
				break
			}
		}
		f.Libraries = append(f.Libraries, Library{
			Name:  string(name),
			Major: binary.LittleEndian.Uint16(e[8:]),
			Minor: binary.LittleEndian.Uint16(e[10:]),
			Build: binary.LittleEndian.Uint16(e[12:]),
			Flags: binary.LittleEndian.Uint16(e[14:]),
		})
	}
	return nil
}

func (f *File) parseKernelThunks() error {
	for slot := f.KernelThunk; ; slot += 4 {
		v, err := f.Uint32(slot)
		if err != nil {
			return fmt.Errorf("xbe: kernel thunk table: %w", err)
		}
		if v == 0 {
			return nil
		}
		if v&0x80000000 == 0 {
			return fmt.Errorf("xbe: kernel thunk %#x imports by name (%#x), not by ordinal", slot, v)
		}
		e, _ := LookupKernel(v &^ 0x80000000)
		f.Kernel = append(f.Kernel, KernelImport{Slot: slot, KernelExport: e})
		if len(f.Kernel) > 1024 {
			return errors.New("xbe: kernel thunk table not terminated")
		}
	}
}

func (f *File) readStruct(va uint32, out []*uint32) error {
	b, err := f.Bytes(va, uint32(4*len(out)))
	if err != nil {
		return err
	}
	for i, p := range out {
		*p = binary.LittleEndian.Uint32(b[4*i:])
	}
	return nil
}

// SectionAt returns the section that maps va, or nil.
func (f *File) SectionAt(va uint32) *Section {
	for i := range f.Sections {
		if f.Sections[i].Contains(va) {
			return &f.Sections[i]
		}
	}
	return nil
}

// Bytes returns n bytes of the loaded image at va. Data past a section's raw
// size is zero-fill (BSS); Bytes returns ErrZeroFill for it rather than
// inventing zeros, since callers usually want to know.
func (f *File) Bytes(va, n uint32) ([]byte, error) {
	if b, err := f.header(va, n); err == nil {
		return b, nil
	}
	s := f.SectionAt(va)
	if s == nil {
		return nil, fmt.Errorf("xbe: %#x not mapped", va)
	}
	off := va - s.VirtualAddr
	if off+n > s.RawSize || off+n < off {
		if off+n <= s.VirtualSize {
			return nil, ErrZeroFill
		}
		return nil, fmt.Errorf("xbe: %#x+%#x crosses the end of %s", va, n, s.Name)
	}
	return f.raw[s.RawAddr+off : s.RawAddr+off+n], nil
}

var ErrZeroFill = errors.New("xbe: address is in zero-filled (uninitialized) data")

func (f *File) Uint32(va uint32) (uint32, error) {
	b, err := f.Bytes(va, 4)
	if err != nil {
		return 0, err
	}
	return binary.LittleEndian.Uint32(b), nil
}

// SectionData returns a section's raw (file-backed) bytes.
func (f *File) SectionData(s *Section) []byte {
	return f.raw[s.RawAddr : s.RawAddr+s.RawSize]
}

// VerifyDigest reports whether a section's bytes match the SHA-1 in its
// header. The digest covers the raw size (little-endian) then the data.
func (f *File) VerifyDigest(s *Section) bool {
	h := sha1.New()
	var n [4]byte
	binary.LittleEndian.PutUint32(n[:], s.RawSize)
	h.Write(n[:])
	h.Write(f.SectionData(s))
	var sum [20]byte
	copy(sum[:], h.Sum(nil))
	return sum == s.Digest
}

// KernelBySlot finds the kernel import whose thunk slot is at va.
func (f *File) KernelBySlot(va uint32) (KernelImport, bool) {
	if va < f.KernelThunk || (va-f.KernelThunk)%4 != 0 {
		return KernelImport{}, false
	}
	i := (va - f.KernelThunk) / 4
	if int(i) >= len(f.Kernel) {
		return KernelImport{}, false
	}
	return f.Kernel[i], true
}
