/* HDR output (the user's, 2026-11-02). OpenGL has no HDR window on Windows: HDR goes to the screen
 * through a DXGI swap chain. So with hdr = 1 (XBRT_HDR) and Windows' HDR on for the game's screen,
 * the window is a D3D11 flip-model swap chain in scRGB (16-bit float, linear, 1.0 = 80 nits) and
 * OpenGL never takes it over: glfill.c's gl_window_show draws the frame as before into an 8-bit
 * framebuffer, then its HDR pass writes it, expanded (SDR white at the paper white, the brightest
 * tones toward the peak), into a D3D11 texture OpenGL shares (WGL_NV_DX_interop2), which is copied
 * into the swap chain's buffer and presented. Otherwise (hdr = 0, no HDR screen, no interop) the
 * window is OpenGL's as before.
 *
 * The D3D11 device is made on the adapter OpenGL draws with (a laptop's discrete GPU: the shared
 * texture can't cross adapters); the screen may hang off the other one, DXGI copies across. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "gl.h"

#ifdef _WIN32
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_6.h>
#include <GL/wglext.h>

volatile float rt_hdr_paper = 200.0f, rt_hdr_peak = 0.0f; /* nits (hdr_paper_white, hdr_peak: F1); peak 0: the screen's own */
float rt_hdr_screen_peak = 800.0f;                         /* the screen's peak brightness, as Windows reports it */

static int state;            /* 0 not tried, 1 on, -1 off */
static ID3D11Device *dev;
static ID3D11DeviceContext *ctx;
static IDXGISwapChain1 *chain;
static ID3D11Texture2D *shared;
static HANDLE gl_dev, gl_obj;
static GLuint gl_tex;
static int sw, sh, locked;
static PFNWGLDXOPENDEVICENVPROC dx_open;
static PFNWGLDXREGISTEROBJECTNVPROC dx_register;
static PFNWGLDXUNREGISTEROBJECTNVPROC dx_unregister;
static PFNWGLDXLOCKOBJECTSNVPROC dx_lock;
static PFNWGLDXUNLOCKOBJECTSNVPROC dx_unlock;

static int off(const char *why) {
    fprintf(stderr, "xbrt: HDR off (the picture stays SDR): %s\n", why);
    if (chain) IDXGISwapChain1_Release(chain), chain = NULL;
    if (ctx) ID3D11DeviceContext_Release(ctx), ctx = NULL;
    if (dev) ID3D11Device_Release(dev), dev = NULL;
    state = -1;
    return 0;
}

/* The adapter OpenGL draws with: the first whose vendor matches GL_VENDOR's. */
static IDXGIAdapter1 *gl_adapter(IDXGIFactory2 *f) {
    const char *v = (const char *)glGetString(GL_VENDOR);
    UINT want = !v ? 0 : strstr(v, "NVIDIA") ? 0x10DE : (strstr(v, "ATI") || strstr(v, "AMD")) ? 0x1002 : strstr(v, "Intel") ? 0x8086 : 0;
    IDXGIAdapter1 *a, *first = NULL;
    for (UINT i = 0; IDXGIFactory2_EnumAdapters1(f, i, &a) == S_OK; i++) {
        DXGI_ADAPTER_DESC1 d;
        IDXGIAdapter1_GetDesc1(a, &d);
        if (want && d.VendorId == want) {
            if (first) IDXGIAdapter1_Release(first);
            return a;
        }
        if (!first) first = a;
        else IDXGIAdapter1_Release(a);
    }
    return first;
}

/* 1 if Windows has HDR on for the screen the window is on (its peak brightness in rt_hdr_screen_peak). */
static int screen_hdr(IDXGIFactory2 *f, HWND wnd) {
    HMONITOR mon = MonitorFromWindow(wnd, MONITOR_DEFAULTTONEAREST);
    IDXGIAdapter1 *a;
    int hdr = 0;
    for (UINT i = 0; IDXGIFactory2_EnumAdapters1(f, i, &a) == S_OK; i++) {
        IDXGIOutput *o;
        for (UINT j = 0; IDXGIAdapter1_EnumOutputs(a, j, &o) == S_OK; j++) {
            IDXGIOutput6 *o6;
            if (IDXGIOutput_QueryInterface(o, &IID_IDXGIOutput6, (void **)&o6) == S_OK) {
                DXGI_OUTPUT_DESC1 d;
                if (IDXGIOutput6_GetDesc1(o6, &d) == S_OK && d.Monitor == mon) {
                    hdr = d.ColorSpace == DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020;
                    if (d.MaxLuminance > 100) rt_hdr_screen_peak = d.MaxLuminance;
                    fprintf(stderr, "xbrt: HDR: the screen %ls: %s, peak %.0f nits\n", d.DeviceName, hdr ? "HDR on" : "HDR off in Windows", d.MaxLuminance);
                }
                IDXGIOutput6_Release(o6);
            }
            IDXGIOutput_Release(o);
        }
        IDXGIAdapter1_Release(a);
    }
    return hdr;
}

/* Once, before OpenGL takes the window: 1 if the window is now the HDR swap chain's. */
int rt_hdr_start(void *hwnd, int W, int H) {
    if (state) return state > 0;
    state = -1;
    const char *s = getenv("XBRT_HDR");
    if (!s || !atoi(s)) return 0;
    if (getenv("XBRT_HDR_PAPER") && atof(getenv("XBRT_HDR_PAPER")) > 0) rt_hdr_paper = (float)atof(getenv("XBRT_HDR_PAPER"));
    if (getenv("XBRT_HDR_PEAK")) rt_hdr_peak = (float)atof(getenv("XBRT_HDR_PEAK")); /* ("auto": 0, the screen's) */
    dx_open = (PFNWGLDXOPENDEVICENVPROC)(void *)wglGetProcAddress("wglDXOpenDeviceNV");
    dx_register = (PFNWGLDXREGISTEROBJECTNVPROC)(void *)wglGetProcAddress("wglDXRegisterObjectNV");
    dx_unregister = (PFNWGLDXUNREGISTEROBJECTNVPROC)(void *)wglGetProcAddress("wglDXUnregisterObjectNV");
    dx_lock = (PFNWGLDXLOCKOBJECTSNVPROC)(void *)wglGetProcAddress("wglDXLockObjectsNV");
    dx_unlock = (PFNWGLDXUNLOCKOBJECTSNVPROC)(void *)wglGetProcAddress("wglDXUnlockObjectsNV");
    if (!dx_open || !dx_register || !dx_unregister || !dx_lock || !dx_unlock) return off("the GPU's OpenGL has no WGL_NV_DX_interop2");
    IDXGIFactory2 *f;
    if (CreateDXGIFactory1(&IID_IDXGIFactory2, (void **)&f) != S_OK) return off("no DXGI 1.2");
    if (!screen_hdr(f, (HWND)hwnd) && !getenv("XBRT_HDR_FORCE")) { /* (XBRT_HDR_FORCE: testing on an SDR screen, Windows clips it) */
        IDXGIFactory2_Release(f);
        return off("turn on Use HDR in Windows' display settings for this screen");
    }
    IDXGIAdapter1 *a = gl_adapter(f);
    HRESULT hr = D3D11CreateDevice((IDXGIAdapter *)a, a ? D3D_DRIVER_TYPE_UNKNOWN : D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
                                   D3D11_SDK_VERSION, &dev, NULL, &ctx);
    if (a) IDXGIAdapter1_Release(a);
    if (hr != S_OK) {
        IDXGIFactory2_Release(f);
        return off("no D3D11 device");
    }
    DXGI_SWAP_CHAIN_DESC1 d;
    memset(&d, 0, sizeof d);
    d.Width = (UINT)W, d.Height = (UINT)H, d.Format = DXGI_FORMAT_R16G16B16A16_FLOAT;
    d.SampleDesc.Count = 1, d.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT, d.BufferCount = 2;
    d.Scaling = DXGI_SCALING_STRETCH, d.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD, d.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
    hr = IDXGIFactory2_CreateSwapChainForHwnd(f, (IUnknown *)dev, (HWND)hwnd, &d, NULL, NULL, &chain);
    IDXGIFactory2_MakeWindowAssociation(f, (HWND)hwnd, DXGI_MWA_NO_ALT_ENTER); /* (display.c's Alt+Enter: borderless) */
    IDXGIFactory2_Release(f);
    if (hr != S_OK) return off("no swap chain for the window");
    IDXGISwapChain3 *c3;
    UINT ok = 0;
    if (IDXGISwapChain1_QueryInterface(chain, &IID_IDXGISwapChain3, (void **)&c3) == S_OK) {
        IDXGISwapChain3_CheckColorSpaceSupport(c3, DXGI_COLOR_SPACE_RGB_FULL_G10_NONE_P709, &ok);
        if (ok & DXGI_SWAP_CHAIN_COLOR_SPACE_SUPPORT_FLAG_PRESENT) IDXGISwapChain3_SetColorSpace1(c3, DXGI_COLOR_SPACE_RGB_FULL_G10_NONE_P709);
        IDXGISwapChain3_Release(c3);
    }
    if (!(ok & DXGI_SWAP_CHAIN_COLOR_SPACE_SUPPORT_FLAG_PRESENT)) return off("the swap chain can't show scRGB");
    if (!(gl_dev = dx_open(dev))) return off("OpenGL can't share with D3D11 (wglDXOpenDeviceNV)");
    sw = W, sh = H;
    state = 1;
    fprintf(stderr, "xbrt: HDR on: paper white %.0f nits, peak %.0f nits%s\n", rt_hdr_paper, rt_hdr_peak > 0 ? rt_hdr_peak : rt_hdr_screen_peak,
            rt_hdr_peak > 0 ? "" : " (the screen's)");
    return 1;
}

int rt_hdr_on(void) { return state > 0; }

/* The frame's HDR texture (W x H, OpenGL's name for the shared one), held for OpenGL to draw in
 * until rt_hdr_present; 0 if it can't be had. Made again when the window's size changes. */
unsigned rt_hdr_frame(int W, int H) {
    if (state <= 0) return 0;
    if (W != sw || H != sh || !shared) {
        if (gl_obj) dx_unregister(gl_dev, gl_obj), gl_obj = NULL;
        if (gl_tex) glDeleteTextures(1, &gl_tex), gl_tex = 0;
        if (shared) ID3D11Texture2D_Release(shared), shared = NULL;
        if ((W != sw || H != sh) && IDXGISwapChain1_ResizeBuffers(chain, 0, (UINT)W, (UINT)H, DXGI_FORMAT_UNKNOWN, 0) != S_OK) return 0;
        sw = W, sh = H;
        D3D11_TEXTURE2D_DESC t;
        memset(&t, 0, sizeof t);
        t.Width = (UINT)W, t.Height = (UINT)H, t.MipLevels = 1, t.ArraySize = 1, t.Format = DXGI_FORMAT_R16G16B16A16_FLOAT;
        t.SampleDesc.Count = 1, t.Usage = D3D11_USAGE_DEFAULT, t.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        if (ID3D11Device_CreateTexture2D(dev, &t, NULL, &shared) != S_OK) return 0;
        glGenTextures(1, &gl_tex);
        if (!(gl_obj = dx_register(gl_dev, shared, gl_tex, GL_TEXTURE_2D, WGL_ACCESS_WRITE_DISCARD_NV))) {
            fprintf(stderr, "xbrt: HDR: OpenGL can't take the D3D11 texture (%dx%d)\n", W, H);
            return 0;
        }
    }
    if (!locked && !dx_lock(gl_dev, 1, &gl_obj)) return 0;
    locked = 1;
    return gl_tex;
}

/* The frame to the screen: OpenGL lets the texture go, D3D11 copies it into the swap chain's buffer. */
void rt_hdr_present(int vsync) {
    if (state <= 0 || !locked) return;
    dx_unlock(gl_dev, 1, &gl_obj);
    locked = 0;
    ID3D11Texture2D *bb;
    if (IDXGISwapChain1_GetBuffer(chain, 0, &IID_ID3D11Texture2D, (void **)&bb) == S_OK) {
        ID3D11DeviceContext_CopyResource(ctx, (ID3D11Resource *)bb, (ID3D11Resource *)shared);
        ID3D11Texture2D_Release(bb);
    }
    IDXGISwapChain1_Present(chain, vsync ? 1 : 0, 0);
}
#else
volatile float rt_hdr_paper = 200.0f, rt_hdr_peak = 0.0f;
float rt_hdr_screen_peak = 800.0f;
int rt_hdr_start(void *hwnd, int W, int H) { (void)hwnd, (void)W, (void)H; return 0; }
int rt_hdr_on(void) { return 0; }
unsigned rt_hdr_frame(int W, int H) { (void)W, (void)H; return 0; }
void rt_hdr_present(int vsync) { (void)vsync; }
#endif
