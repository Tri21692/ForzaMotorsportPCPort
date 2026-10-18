// Package xbetest builds small synthetic XBEs for tests, so the test suite
// never needs a copy of the game.
package xbetest

import (
	"crypto/sha1"
	"encoding/binary"
	"unicode/utf16"

	"github.com/Tri21692/ForzaMotorsportPC/xbe"
)

const Base = 0x10000

type Section struct {
	Name  string
	VA    uint32
	Data  []byte
	Flags uint32
	BSS   uint32 // extra zero-fill past Data
}

type Image struct {
	Title    string
	TitleID  uint32
	Entry    uint32
	Thunk    uint32 // address of the kernel thunk table
	Debug    bool   // encode keys with the debug XOR values
	Sections []Section
}

// Build lays the image out the way the XDK linker does: a 0x1000-byte
// header page followed by page-aligned raw section data.
func (im Image) Build() []byte {
	const hdrSize = 0x1000
	hdr := make([]byte, hdrSize)
	le := binary.LittleEndian
	put := func(off int, v uint32) { le.PutUint32(hdr[off:], v) }

	copy(hdr, "XBEH")
	const (
		certOff = 0x180
		libOff  = 0x240
		secOff  = 0x260
		nameOff = 0x600
	)
	ek, tk := uint32(xbe.EntryRetailKey), uint32(xbe.ThunkRetailKey)
	if im.Debug {
		ek, tk = xbe.EntryDebugKey, xbe.ThunkDebugKey
	}
	put(0x104, Base)
	put(0x108, hdrSize)
	put(0x110, 0x178)
	put(0x114, 0x4248d27b)
	put(0x118, Base+certOff)
	put(0x11C, uint32(len(im.Sections)))
	put(0x120, Base+secOff)
	put(0x128, im.Entry^ek)
	put(0x158, im.Thunk^tk)
	put(0x160, 1)
	put(0x164, Base+libOff)

	put(certOff, 0x1D0)
	put(certOff+8, im.TitleID)
	for i, r := range utf16.Encode([]rune(im.Title)) {
		le.PutUint16(hdr[certOff+12+2*i:], r)
	}
	put(certOff+0xA0, 7)

	copy(hdr[libOff:], "XAPILIB\x00")
	le.PutUint16(hdr[libOff+8:], 1)
	le.PutUint16(hdr[libOff+12:], 5849)

	out := make([]byte, hdrSize)
	nameAt := nameOff
	var imgEnd uint32
	for i, s := range im.Sections {
		raw := uint32(len(out))
		out = append(out, s.Data...)
		for len(out)%0x1000 != 0 {
			out = append(out, 0)
		}
		e := hdr[secOff+i*0x38:]
		le.PutUint32(e[0:], s.Flags)
		le.PutUint32(e[4:], s.VA)
		le.PutUint32(e[8:], uint32(len(s.Data))+s.BSS)
		le.PutUint32(e[12:], raw)
		le.PutUint32(e[16:], uint32(len(s.Data)))
		le.PutUint32(e[20:], Base+uint32(nameAt))
		nameAt += copy(hdr[nameAt:], s.Name) + 1

		h := sha1.New()
		var n [4]byte
		le.PutUint32(n[:], uint32(len(s.Data)))
		h.Write(n[:])
		h.Write(s.Data)
		copy(e[0x24:], h.Sum(nil))
		if end := s.VA + uint32(len(s.Data)) + s.BSS; end > imgEnd {
			imgEnd = end
		}
	}
	put(0x10C, imgEnd-Base)
	copy(out, hdr)
	return out
}

// Thunks encodes a kernel thunk table importing the given ordinals.
func Thunks(ordinals ...uint32) []byte {
	b := make([]byte, 4*(len(ordinals)+1))
	for i, o := range ordinals {
		binary.LittleEndian.PutUint32(b[4*i:], o|0x80000000)
	}
	return b
}

// Le32 appends v little-endian.
func Le32(b []byte, v uint32) []byte {
	return binary.LittleEndian.AppendUint32(b, v)
}
