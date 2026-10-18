package sigdb

// Ports of XbSymbolDatabase's hand-written scans (src/lib/manual_*.h, MIT).
// They find symbols that a signature alone cannot pin down: globals read
// out of instructions, vtable slots, and the D3D render state block. Each
// function mirrors its C counterpart and is named after it.

// symByXRef is XbSDBi_FindByReferenceHelper: a manual-scan symbol by xref.
func symByXRef(t *LibraryDB, xref string) *Symbol {
	for _, sym := range t.Symbols {
		if sym.XRef == xref && sym.Scan&ScanManual != 0 {
			return sym
		}
	}
	return nil
}

// scanRef is XbSDBi_SymbolDatabaseList_ScanByReference: scan one region for
// the manual-scan symbols filling xref, registering the first found.
func (s *scanner) scanRef(t *LibraryDB, lib string, build uint16, r *region, xref string, firstPass, reg bool) (uint32, *Symbol, uint16, bool) {
	for _, sym := range t.Symbols {
		if sym.XRef != xref || sym.Scan&ScanManual == 0 {
			continue
		}
		if addr, ver, ok := s.scanIn(sym, build, r, firstPass); ok {
			if reg {
				s.register(sym, "", lib, ver, addr)
			}
			return addr, sym, ver, true
		}
	}
	return 0, nil, 0, false
}

// registerRef registers xref under its manual symbol's name, if the table
// has one; values with no symbol entry are still reported by results().
func (s *scanner) registerRef(t *LibraryDB, lib, xref string, addr uint32) {
	if sym := symByXRef(t, xref); sym != nil {
		s.register(sym, "", lib, 0, addr)
		return
	}
	s.set(xref, addr)
}

// claim records an xref that is already known (found by derivation) as a
// named symbol, like XbSDBi_RegisterSelfValidXRefAddr.
func (s *scanner) claim(t *LibraryDB, lib, xref string, ver uint16) {
	sym := symByXRef(t, xref)
	if sym == nil || !s.known(xref) || s.found[xref] != nil {
		return
	}
	s.found[xref] = &Match{Addr: s.addr(xref), Name: sym.Name, XRef: xref, Library: lib,
		Version: ver, Kind: sym.Kind, Conv: sym.Conv, Params: sym.Params}
}

// manual runs the hand-written scan for one XBE library, the way
// XbSDBContext_ScanManual does.
func (s *scanner) manual(lib string, build uint16) {
	type scanFunc func(t *LibraryDB, lib string, build uint16, r *region) bool
	run := func(table string, tries int, fn scanFunc) {
		t := s.db.Table(table)
		if t == nil {
			return
		}
		for try := 0; try < tries; try++ {
			for _, r := range s.tableRegions(t) {
				if fn(t, lib, build, r) {
					return
				}
			}
		}
	}
	switch lib {
	case "D3D8":
		// Twice, since sections can be in either order.
		run("D3D8_OOVPA_Table", 2, s.dx8)
	case "DSOUND":
		run("DSound_OOVPA_manual_Table", 2, s.dsound)
	case "XAPILIB":
		run("XAPILIB_OOVPA_Table", 1, s.xapilib)
	}
}

// ---- XAPILIB (manual_xapilib.h) ----

func (s *scanner) xapilib(t *LibraryDB, lib string, build uint16, r *region) bool {
	a := s.xapiXGetSectionSize(t, lib, build, r)
	b := s.xapiDeviceTypeMU(t, lib, build, r)
	c := s.xapiDeviceTypes(t, lib, build, r)
	return a && b && c
}

// xapiXGetSectionSize: XapiMapLetterToDirectory calls XGetSectionSize; the
// signature derives the call's rel32, which becomes an address here.
func (s *scanner) xapiXGetSectionSize(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.known("XapiMapLetterToDirectory") {
		return true
	}
	addr, sym, ver, ok := s.scanRef(t, lib, build, r, "XapiMapLetterToDirectory", true, true)
	if !ok {
		return true
	}
	if !s.known("XGetSectionSize") {
		return false
	}
	var off uint16
	found := false
	for _, rev := range sym.Revisions {
		if rev.Version != ver {
			continue
		}
		for _, x := range rev.Sig.XRefs {
			if x.Name == "XGetSectionSize" {
				off, found = x.Off, true
			}
		}
	}
	if !found {
		return false
	}
	s.force("XGetSectionSize", addr+uint32(off)+s.addr("XGetSectionSize")+4)
	s.claim(t, lib, "XGetSectionSize", ver)
	return true
}

// xapiDeviceTypeMU: MU_Init pushes &g_DeviceType_MU right before calling
// IUsbInit::GetMaxDeviceTypeCount.
func (s *scanner) xapiDeviceTypeMU(t *LibraryDB, lib string, build uint16, r *region) bool {
	if !s.known("MU_Init") {
		s.scanRef(t, lib, build, r, "MU_Init", true, true)
	}
	if !s.known("MU_Init") {
		return false
	}
	if !s.known("IUsbInit_GetMaxDeviceTypeCount") {
		if _, _, _, ok := s.scanRef(t, lib, build, r, "IUsbInit_GetMaxDeviceTypeCount", true, true); !ok {
			return false
		}
	}
	mu := s.addr("MU_Init")
	if !r.contains(mu) {
		return false
	}
	target := s.addr("IUsbInit_GetMaxDeviceTypeCount")
	d := r.data
	for off := mu - r.va; int(off)+10 <= len(d); off++ {
		if d[off] == 0xC9 && d[off+1] == 0xC2 && d[off+2] == 0x04 { // leave; ret 4
			return false
		}
		if d[off] == 0x68 && d[off+5] == 0xE8 && matchRef(r, off+6, target) { // push imm; call
			if !s.known("g_DeviceType_MU") {
				s.registerRef(t, lib, "g_DeviceType_MU", leU32(d[off+1:]))
			}
			return true
		}
	}
	return false
}

// xapiDeviceTypes walks the XID device type table that GetTypeInformation
// indexes, naming the gamepad, keyboard and other device descriptors.
func (s *scanner) xapiDeviceTypes(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.known("GetTypeInformation") {
		return false
	}
	_, _, _, ok := s.scanRef(t, lib, build, r, "GetTypeInformation", true, true)
	if !ok {
		_, _, _, ok = s.scanRef(t, lib, build, r, "GetTypeInformation2", true, true)
	}
	if !ok {
		if !s.known("XInputOpen") {
			s.scanRef(t, lib, build, r, "XInputOpen", true, true)
		}
		return false
	}
	s.claim(t, lib, "g_DeviceTypeInfoTableBegin", 4242)
	s.claim(t, lib, "g_DeviceTypeInfoTableEnd", 4242)
	begin, end := s.addr("g_DeviceTypeInfoTableBegin"), s.addr("g_DeviceTypeInfoTableEnd")
	names := map[byte]string{
		1: "g_DeviceType_Gamepad", 2: "g_DeviceType_Keyboard", 3: "g_DeviceType_IRDongle",
		4: "g_DeviceType_Mouse", 128: "g_DeviceType_SBC",
	}
	for p := begin; p < end; p += 4 {
		info, ok := s.u32(p)
		if !ok {
			continue
		}
		typ, ok1 := s.u8(info)
		xpp, ok2 := s.u32(info + 4)
		if !ok1 || !ok2 {
			continue
		}
		if name, known := names[typ]; known {
			s.registerRef(t, lib, name, xpp)
		}
	}
	return true
}

// ---- DSOUND (manual_dsound.h) ----

// dsound finds CDirectSoundStream's constructor, reads the two vtables it
// installs, and names the stream vtable's first seven methods.
func (s *scanner) dsound(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.get("CDirectSoundStream_Constructor").state == stateUnknown {
		addr, _, _, ok := s.scanRef(t, lib, build, r, "CDirectSoundStream_Constructor", true, true)
		if !ok {
			return false
		}
		voice, ok1 := s.u32(addr + 0x14)
		stream, ok2 := s.u32(addr + 0x1B)
		if !ok1 || !ok2 {
			return false
		}
		s.force("DSS_VOICE_VTABLE", voice)
		s.force("DSS_STREAM_VTABLE", stream)
	}
	if !s.known("DSS_STREAM_VTABLE") || !s.known("DSS_VOICE_VTABLE") {
		return false
	}
	if s.get("CDirectSoundStream_AddRef").state != stateUnknown {
		return true
	}
	vtable := s.addr("DSS_STREAM_VTABLE")
	if !r.contains(vtable) {
		return false
	}
	methods := []string{
		"CDirectSoundStream_AddRef", "CDirectSoundStream_Release", "CDirectSoundStream_GetInfo",
		"CDirectSoundStream_GetStatus", "CDirectSoundStream_Process",
		"CDirectSoundStream_Discontinuity", "CDirectSoundStream_Flush",
	}
	for i, xref := range methods {
		fn, ok := s.u32(vtable + uint32(4*i))
		sym := symByXRef(t, xref)
		if !ok || sym == nil {
			continue
		}
		name, ver := "", uint16(3911)
		if xref == "CDirectSoundStream_GetStatus" {
			name = "CDirectSoundStream_GetStatus__r1"
			if build >= 4134 {
				name, ver = "CDirectSoundStream_GetStatus__r2", 4134
			}
		}
		s.register(sym, name, lib, ver, fn)
	}
	return true
}

// ---- D3D8 (manual_d3d8__ltcg.h) ----

func (s *scanner) dx8(t *LibraryDB, lib string, build uint16, r *region) bool {
	ok := s.dx8EndOfList(t, lib, build, r)
	ok = s.dx8RenderState(t, lib, build, r) && ok
	ok = s.dx8ComplexRenderState(t, lib, build, r) && ok
	ok = s.dx8StencilsAndOcclusion(t, lib, build, r) && ok
	if !ok {
		return false
	}
	s.dx8RenderStateVars(build)
	if build < 3911 {
		return true
	}

	if _, _, _, found := s.scanRef(t, lib, build, r, "D3DDevice_SetTextureState_TexCoordIndex", true, true); found {
		s.force("D3D_g_DeferredTextureState", s.addr("D3DTSS_TEXCOORDINDEX")-0x70)
	}
	if _, _, _, found := s.scanRef(t, lib, build, r, "D3DDevice_SetStreamSource", true, true); found {
		vb := s.addr("D3D_g_Stream_i_pVertexBuffer")
		if vb-s.addr("D3D_g_Stream") != 8 {
			s.force("D3D_g_Stream", vb-8)
		}
	}
	return s.dx8Callbacks(t, lib, build, r)
}

// dx8EndOfList: D3D_CommonSetDebugRegisters derives D3D_g_pDevice and the
// last render states.
func (s *scanner) dx8EndOfList(t *LibraryDB, lib string, build uint16, r *region) bool {
	if !s.unset("D3DRS_DoNotCullUncompressed") {
		return true
	}
	derived := []string{"D3D_g_pDevice", "D3DRS_RopZCmpAlwaysRead", "D3DRS_RopZRead", "D3DRS_DoNotCullUncompressed"}
	for _, x := range derived {
		s.setState(x, stateDerive)
	}
	if _, _, _, ok := s.scanRef(t, lib, build, r, "D3D_CommonSetDebugRegisters", false, true); !ok {
		for _, x := range derived {
			s.setState(x, stateUnknown)
		}
		return false
	}
	s.claim(t, lib, "D3D_g_pDevice", 0)
	return true
}

// dx8RenderState finds D3D_g_RenderState via SetRenderStateNotInline, and
// the deferred block from the index its cmp instruction tests against.
func (s *scanner) dx8RenderState(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.unset("D3DDevice_SetRenderState_Simple") {
		if _, _, _, ok := s.scanRef(t, lib, build, r, "D3DDevice_SetRenderState_Simple", true, true); !ok {
			return false
		}
	}
	if !s.unset("D3D_g_RenderState") {
		return true
	}
	s.setState("D3D_g_RenderState", stateDerive)
	addr, _, _, ok := s.scanRef(t, lib, build, r, "D3DDevice_SetRenderStateNotInline", true, true)
	if !ok {
		// LTCG builds have an inline fragment to fall back on; Forza's
		// standard D3D8 does not, like the original's non-LTCG path.
		s.setState("D3D_g_RenderState", stateUnknown)
		return false
	}
	idx, ok := s.u8(addr + 7)
	if !ok {
		return false
	}
	deferred := s.addr("D3D_g_RenderState") + uint32(idx)*4
	s.force("D3D_g_DeferredRenderState", deferred)
	s.force("D3DRS_FogEnable", deferred)
	return true
}

// dx8ComplexRenderState: SetRenderState_FillMode derives the first complex
// states; the complex block starts three slots before FillMode.
func (s *scanner) dx8ComplexRenderState(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.unset("D3DRS_FillMode") {
		derived := []string{"D3DRS_FillMode", "D3DRS_BackFillMode", "D3DRS_TwoSidedLighting"}
		for _, x := range derived {
			s.setState(x, stateDerive)
		}
		if _, _, _, ok := s.scanRef(t, lib, build, r, "D3DDevice_SetRenderState_FillMode", false, true); !ok {
			for _, x := range derived {
				s.setState(x, stateUnknown)
			}
			return false
		}
	}
	complex := s.addr("D3DRS_FillMode") - 3*4
	s.force("D3D_g_ComplexRenderState", complex)
	s.force("D3DRS_PSTextureModes", complex)
	return true
}

func (s *scanner) dx8StencilsAndOcclusion(t *LibraryDB, lib string, build uint16, r *region) bool {
	if !s.unset("D3DRS_StencilEnable") {
		return true
	}
	derived := []string{"D3DRS_StencilEnable", "D3DRS_StencilFail", "D3DRS_OcclusionCullEnable", "D3DRS_StencilCullEnable"}
	for _, x := range derived {
		s.setState(x, stateDerive)
	}
	if _, _, _, ok := s.scanRef(t, lib, build, r, "D3DRS_Stencils_and_Occlusion__GenericFragment", false, false); !ok {
		for _, x := range derived {
			s.setState(x, stateUnknown)
		}
		return false
	}
	return true
}

// dx8RenderStateVars places every named render state that no signature
// derived at its slot in the render state block, using the table layout
// for this D3D8 build.
func (s *scanner) dx8RenderStateVars(build uint16) {
	base := s.addr("D3D_g_RenderState")
	i := uint32(0)
	for _, rs := range s.db.RenderStates {
		if !rs.Available(build) {
			continue
		}
		if rs.XRef != "" && s.get(rs.XRef).state == stateUnknown {
			s.force(rs.XRef, base+4*i)
		}
		i++
	}
}

// dx8Callbacks: the vertical blank event's offset in the D3D device gives
// the swap and vblank callback offsets just before it.
func (s *scanner) dx8Callbacks(t *LibraryDB, lib string, build uint16, r *region) bool {
	if s.get("D3D_g_pDevice").state == stateDerive || s.get("D3DDevice__m_SwapCallback_OFFSET").state != stateUnknown {
		return false
	}
	if s.get("D3DDevice__m_VerticalBlankEvent_OFFSET").state == stateDerive {
		s.scanRef(t, lib, build, r, "D3DDevice__m_VerticalBlankEvent__GenericFragment", true, false)
	}
	if !s.known("D3DDevice__m_VerticalBlankEvent_OFFSET") {
		return false
	}
	ev := s.addr("D3DDevice__m_VerticalBlankEvent_OFFSET")
	s.claim(t, lib, "D3DDevice__m_VerticalBlankEvent_OFFSET", 0)
	s.registerRef(t, lib, "D3DDevice__m_SwapCallback_OFFSET", ev-8)
	s.registerRef(t, lib, "D3DDevice__m_VBlankCallback_OFFSET", ev-4)
	return true
}

func leU32(b []byte) uint32 {
	return uint32(b[0]) | uint32(b[1])<<8 | uint32(b[2])<<16 | uint32(b[3])<<24
}
