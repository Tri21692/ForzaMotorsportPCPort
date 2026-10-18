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
#include <stdlib.h>
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

/* ---- host input ----
 * XINPUT_GAMEPAD on the Xbox: wButtons (D-pad 0x1-0x8, START 0x10, BACK
 * 0x20, thumb clicks 0x40/0x80), then eight analog buttons (A, B, X, Y,
 * BLACK, WHITE, left trigger, right trigger; 0-255), then the thumbsticks.
 * A PC controller maps one to one, with the shoulder buttons as WHITE
 * (left) and BLACK (right). XBRT_AUTOPRESS=1 taps START and A every two
 * seconds, for running without anyone at the controls. */
enum { A_A, A_B, A_X, A_Y, A_BLACK, A_WHITE, A_LT, A_RT };

static void set_pad(uint32_t pad, uint16_t buttons, const uint8_t analog[8], const int16_t thumbs[4]) {
    xb_wr16(pad, buttons);
    for (int i = 0; i < 8; i++) xb_wr8(pad + 2 + i, analog[i]);
    for (int i = 0; i < 4; i++) xb_wr16(pad + 10 + 2 * i, (uint16_t)thumbs[i]);
}

#ifdef _WIN32
#include <windows.h>

typedef struct {
    uint16_t wButtons;
    uint8_t bLeftTrigger, bRightTrigger;
    int16_t sThumbLX, sThumbLY, sThumbRX, sThumbRY;
} PcPad;
typedef struct {
    uint32_t dwPacketNumber;
    PcPad Gamepad;
} PcPadState;
typedef DWORD(WINAPI *XInputGetStateFn)(DWORD, PcPadState *);

static int pc_pad(uint16_t *buttons, uint8_t analog[8], int16_t thumbs[4]) {
    static XInputGetStateFn get;
    static int tried;
    if (!tried) {
        tried = 1;
        HMODULE m = LoadLibraryA("xinput1_4.dll");
        if (!m) m = LoadLibraryA("xinput9_1_0.dll");
        if (m) get = (XInputGetStateFn)(void *)GetProcAddress(m, "XInputGetState");
        rt_log("input: %s\n", get ? "XInput controllers" : "no XInput; keyboard only");
    }
    PcPadState st;
    if (!get || get(0, &st) != 0) return 0;
    const PcPad *g = &st.Gamepad;
    *buttons = g->wButtons & 0xFF; /* D-pad, START, BACK, thumb clicks: same bits */
    analog[A_A] = g->wButtons & 0x1000 ? 255 : 0;
    analog[A_B] = g->wButtons & 0x2000 ? 255 : 0;
    analog[A_X] = g->wButtons & 0x4000 ? 255 : 0;
    analog[A_Y] = g->wButtons & 0x8000 ? 255 : 0;
    analog[A_WHITE] = g->wButtons & 0x0100 ? 255 : 0;
    analog[A_BLACK] = g->wButtons & 0x0200 ? 255 : 0;
    analog[A_LT] = g->bLeftTrigger;
    analog[A_RT] = g->bRightTrigger;
    thumbs[0] = g->sThumbLX, thumbs[1] = g->sThumbLY, thumbs[2] = g->sThumbRX, thumbs[3] = g->sThumbRY;
    return 1;
}

/* Keyboard: arrows steer (D-pad and left stick), Enter START, Escape
 * BACK, Space/Z A, X B, C X, V Y, W/S throttle and brake. Until the game
 * has a window this reads the keyboard whatever has focus. */
static void keyboard(uint16_t *buttons, uint8_t analog[8], int16_t thumbs[4]) {
#define DOWN(vk) ((GetAsyncKeyState(vk) & 0x8000) != 0)
    if (DOWN(VK_UP)) *buttons |= 0x1, thumbs[1] = 32767;
    if (DOWN(VK_DOWN)) *buttons |= 0x2, thumbs[1] = -32768;
    if (DOWN(VK_LEFT)) *buttons |= 0x4, thumbs[0] = -32768;
    if (DOWN(VK_RIGHT)) *buttons |= 0x8, thumbs[0] = 32767;
    if (DOWN(VK_RETURN)) *buttons |= 0x10;
    if (DOWN(VK_ESCAPE)) *buttons |= 0x20;
    if (DOWN(VK_SPACE) || DOWN('Z')) analog[A_A] = 255;
    if (DOWN('X')) analog[A_B] = 255;
    if (DOWN('C')) analog[A_X] = 255;
    if (DOWN('V')) analog[A_Y] = 255;
    if (DOWN('W')) analog[A_RT] = 255;
    if (DOWN('S')) analog[A_LT] = 255;
#undef DOWN
}
#else
static int pc_pad(uint16_t *buttons, uint8_t analog[8], int16_t thumbs[4]) {
    (void)buttons, (void)analog, (void)thumbs;
    return 0;
}
static void keyboard(uint16_t *buttons, uint8_t analog[8], int16_t thumbs[4]) { (void)buttons, (void)analog, (void)thumbs; }
#endif

static void host_pad(uint32_t pad) {
    static int autopress = -1;
    if (autopress < 0) {
        const char *e = getenv("XBRT_AUTOPRESS");
        autopress = e && atoi(e);
    }
    uint16_t buttons = 0;
    uint8_t analog[8] = {0};
    int16_t thumbs[4] = {0};
    if (!pc_pad(&buttons, analog, thumbs)) keyboard(&buttons, analog, thumbs);
    if (autopress && rt_now_100ns() % 20000000 < 2000000) { /* 0.2 s of every 2 s */
        buttons |= 0x10;
        analog[A_A] = 255;
    }
    set_pad(pad, buttons, analog, thumbs);
}

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
    if (report) rt_log("XGetDeviceChanges: gamepad inserted on port 1\n");
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
    static int logged;
    if (!logged++) rt_log("XInputGetState(%08x) first called\n", ARG(0));
    if (ARG(0) != GAMEPAD_HANDLE) {
        ret(c, 1167, 8);
        return;
    }
    memset(xb_mem + s, 0, 22);
    host_pad(s + 4);
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
