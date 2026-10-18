/* Controllers: XAPI's input functions, replaced (HLE).
 *
 * The Xbox talks to controllers through its USB host controller, which
 * XAPI drives directly. The runtime replaces XAPI's input API instead: one
 * standard gamepad on port 1 (index 0). The state is neutral until host
 * input is wired up.
 *
 * Each replacement is a stdcall function: it reads its arguments from the
 * guest stack and pops them, as the code it replaces would.
 */
#include <string.h>

#include "names.h"
#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

static void ret(XbCtx *c, uint32_t eax, uint32_t argbytes) {
    c->eax = eax;
    c->esp += 4 + argbytes;
}

#define GAMEPAD_HANDLE 0x58500001u /* "XP", port 0 */

#ifdef XB_VAR_g_DeviceType_Gamepad
static int is_gamepad(uint32_t type) { return type == XB_VAR_g_DeviceType_Gamepad; }
#else
static int is_gamepad(uint32_t type) { (void)type; return 1; }
#endif

static int reported_insertion;
static uint32_t packet;

#ifdef XB_FN_XInitDevices
/* VOID XInitDevices(DWORD dwPreallocTypeCount, PXDEVICE_PREALLOC_TYPE PreallocTypes) */
void XB_FN_XInitDevices(XbCtx *c) {
    rt_log("XInitDevices (HLE): one gamepad on port 1\n");
    ret(c, 0, 8);
}
#endif

#ifdef XB_FN_XGetDevices
/* DWORD XGetDevices(PXPP_DEVICE_TYPE DeviceType): bitmask of occupied ports */
void XB_FN_XGetDevices(XbCtx *c) { ret(c, is_gamepad(ARG(0)) ? 1 : 0, 4); }
#endif

#ifdef XB_FN_XGetDeviceChanges
/* BOOL XGetDeviceChanges(PXPP_DEVICE_TYPE, PDWORD pdwInsertions, PDWORD pdwRemovals) */
void XB_FN_XGetDeviceChanges(XbCtx *c) {
    int report = is_gamepad(ARG(0)) && !reported_insertion;
    if (report) reported_insertion = 1;
    xb_wr32(ARG(1), report ? 1 : 0);
    xb_wr32(ARG(2), 0);
    ret(c, report, 12);
}
#endif

#ifdef XB_FN_XInputOpen
/* HANDLE XInputOpen(PXPP_DEVICE_TYPE, DWORD dwPort, DWORD dwSlot, PXINPUT_POLLING_PARAMETERS) */
void XB_FN_XInputOpen(XbCtx *c) {
    uint32_t h = is_gamepad(ARG(0)) && ARG(1) == 0 ? GAMEPAD_HANDLE : 0;
    rt_log("XInputOpen(port %u) -> %08x\n", ARG(1), h);
    ret(c, h, 16);
}
#endif

#ifdef XB_FN_XInputClose
void XB_FN_XInputClose(XbCtx *c) { ret(c, 0, 4); }
#endif

#ifdef XB_FN_XInputGetCapabilities
/* DWORD XInputGetCapabilities(HANDLE, PXINPUT_CAPABILITIES): SubType (u8),
 * then In.Gamepad (+4, 18 bytes) and Out.Rumble (+22), filled with the
 * ranges a standard controller supports. */
void XB_FN_XInputGetCapabilities(XbCtx *c) {
    uint32_t caps = ARG(1);
    memset(xb_mem + caps, 0, 26);
    xb_wr8(caps, 1);                        /* XINPUT_DEVSUBTYPE_GC_GAMEPAD */
    xb_wr16(caps + 4, 0xFFFF);              /* wButtons */
    memset(xb_mem + caps + 6, 0xFF, 8);     /* bAnalogButtons */
    for (int i = 0; i < 4; i++) xb_wr16(caps + 14 + 2 * i, 0xFFFF); /* thumbsticks */
    xb_wr16(caps + 22, 0xFFFF);             /* rumble motors */
    xb_wr16(caps + 24, 0xFFFF);
    ret(c, ARG(0) == GAMEPAD_HANDLE ? 0 : 1167 /* ERROR_DEVICE_NOT_CONNECTED */, 8);
}
#endif

#ifdef XB_FN_XInputGetState
/* DWORD XInputGetState(HANDLE, PXINPUT_STATE): dwPacketNumber, then the
 * gamepad: wButtons (+4), bAnalogButtons[8] (+6), four thumbstick axes
 * (+14). */
void XB_FN_XInputGetState(XbCtx *c) {
    uint32_t s = ARG(1);
    if (ARG(0) != GAMEPAD_HANDLE) {
        ret(c, 1167, 8);
        return;
    }
    memset(xb_mem + s, 0, 22);
    xb_wr32(s, ++packet);
    ret(c, 0, 8);
}
#endif

#ifdef XB_FN_XInputSetState
/* DWORD XInputSetState(HANDLE, PXINPUT_FEEDBACK): rumble. Completes at
 * once: Header.dwStatus (+0) = 0 and the event (+4), if any, signalled. */
void XB_FN_XInputSetState(XbCtx *c) {
    uint32_t fb = ARG(1);
    xb_wr32(fb, 0);
    RtObject *e = rt_handle_get(xb_rd32(fb + 4));
    if (e) {
        e->signaled = 1;
        pthread_cond_broadcast(&rt_changed);
    }
    ret(c, 997 /* ERROR_IO_PENDING, as the real call returns */, 8);
}
#endif
