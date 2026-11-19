/* The OpenGL context for drawing on the host GPU (docs/GPU.md, step 1).
 *
 * XBRT_GPU=gl asks for it; the software rasteriser stays the default until
 * the GPU path draws as well. The context lives on the device thread, in a
 * hidden window of its own, as a 4.3 core profile. Functions come from
 * wglGetProcAddress, or from opengl32.dll itself for the OpenGL 1.1 ones
 * that wglGetProcAddress does not return.
 */
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "gl.h"

int rt_gl_on;

#define GL_DEFINE(type, name) type p_##name;
GL_FUNCTIONS(GL_DEFINE)
#undef GL_DEFINE
PFNGLBUFFERSTORAGEPROC p_glBufferStorage;
int rt_gl_parallel;

#ifdef _WIN32
#include <windows.h>
#include <GL/wglext.h>

/* On a laptop with two GPUs, these ask the NVIDIA (Optimus) and AMD
 * (PowerXpress) drivers to give this program the fast one; otherwise
 * OpenGL ran on the integrated GPU. Windows' per-app graphics setting
 * still overrides them. */
__declspec(dllexport) DWORD NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;

static void *load(HMODULE gl, const char *name) {
    void *p = (void *)wglGetProcAddress(name);
    /* Some drivers return 1, 2, 3 or -1 instead of NULL for a miss. */
    if (p == NULL || p == (void *)1 || p == (void *)2 || p == (void *)3 || p == (void *)-1)
        p = (void *)GetProcAddress(gl, name);
    return p;
}

static void APIENTRY debug_message(GLenum source, GLenum type, GLuint id, GLenum severity, GLsizei length, const GLchar *message,
                                   const void *user) {
    (void)source, (void)id, (void)length, (void)user;
    if (severity == GL_DEBUG_SEVERITY_NOTIFICATION) return;
    fprintf(stderr, "xbrt: GL %s: %s\n", type == GL_DEBUG_TYPE_ERROR ? "error" : "message", message);
}

/* Clears a small framebuffer to a known colour and reads it back: proves
 * the context, framebuffers and read-back all work before anything uses
 * them. */
static int self_test(void) {
    GLuint tex, fbo;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, 16, 16);
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    int ok = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
    uint32_t px = 0;
    if (ok) {
        glViewport(0, 0, 16, 16);
        glClearColor(1.0f, 0.5f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        glReadPixels(3, 3, 1, 1, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, &px);
        ok = (px & 0xFFFFFF00u) == 0xFFFF8000u || (px & 0xFFFF0000u) == 0xFFFF0000u; /* A8R8G8B8: ff ff 7f/80 00 */
    }
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDeleteFramebuffers(1, &fbo);
    glDeleteTextures(1, &tex);
    rt_log("gl: self-test %s (read back %08x)\n", ok ? "passed" : "FAILED", px);
    if (!ok) fprintf(stderr, "xbrt: the OpenGL self-test failed (read back %08x)\n", px);
    return ok;
}

static HGLRC gl_ctx;
static int gl_format;
static PIXELFORMATDESCRIPTOR gl_pfd;

/* Straight into the window: the caller draws into its back buffer
 * (glfill.c, gl_window_show) and rt_gl_window_swap shows it, without
 * waiting for the screen unless XBRT_VSYNC=1. Reading the picture back for
 * the window to draw with GDI held the device thread at every vertical
 * blank. The context moves to the window's DC the first time (same pixel
 * format as the hidden window it was made on). 0: not possible, the
 * caller reads back instead; else the client area's size in *W, *H (0
 * when minimised). */
static HDC win_dc;

int rt_gl_window_begin(int *W, int *H) {
    static HWND shown;
    static HDC dc;
    static int failed;
    HWND wnd = (HWND)rt_display_hwnd();
    if (!wnd || failed) return 0;
    RECT r;
    GetClientRect(wnd, &r);
    *W = r.right > 0 ? r.right : 0, *H = r.bottom > 0 ? r.bottom : 0;
    /* HDR (hdr.c): the window a DXGI swap chain's, OpenGL drawing off it (glfill.c presents) */
    if (rt_hdr_on() || (wnd != shown && *W > 0 && *H > 0 && rt_hdr_start(wnd, *W, *H))) {
        shown = wnd, win_dc = NULL;
        return 1;
    }
    if (wnd != shown) {
        dc = GetDC(wnd);
        if (!dc || (GetPixelFormat(dc) != gl_format && !SetPixelFormat(dc, gl_format, &gl_pfd)) || !wglMakeCurrent(dc, gl_ctx)) {
            fprintf(stderr, "xbrt: cannot draw into the window with OpenGL; it shows read-backs instead\n");
            failed = 1;
            return 0;
        }
        shown = wnd;
        PFNWGLSWAPINTERVALEXTPROC interval = (PFNWGLSWAPINTERVALEXTPROC)(void *)wglGetProcAddress("wglSwapIntervalEXT");
        if (interval) interval(getenv("XBRT_VSYNC") && atoi(getenv("XBRT_VSYNC")) ? 1 : 0);
    }
    win_dc = dc;
    return 1;
}

/* Track audits (2026-11-02): run through RenderDoc (renderdoccmd capture), XBRT_RDOC_EVERY=<s> takes
 * a capture every that many seconds, through its in-app API (RENDERDOC_GetAPI 1.1.2: a table of
 * functions, StartFrameCapture the 20th, EndFrameCapture the 22nd). A capture spans RDOC_SWAPS
 * swaps: one swap's (TriggerCapture's) held only the picture shown again, the game's drawing fell
 * between others. Nothing without RenderDoc. */
#define RDOC_SWAPS 4
static void **rdoc_api;
static int rdoc_open; /* 0 none; 1 to begin after this swap; 2.. swaps into a capture */

/* Before a swap: the capture ended once it spans RDOC_SWAPS; another due every XBRT_RDOC_EVERY s. */
static void rdoc_tick(void) {
    static int every = -1;
    static uint64_t next;
    void **api = rdoc_api;
    if (rdoc_open >= 2 && ++rdoc_open > RDOC_SWAPS + 1) {
        ((uint32_t(__cdecl *)(void *, void *))api[21])(NULL, NULL);
        rdoc_open = 0;
    }
    if (every < 0) {
        every = getenv("XBRT_RDOC_EVERY") ? atoi(getenv("XBRT_RDOC_EVERY")) : 0;
        HMODULE m = every > 0 ? GetModuleHandleA("renderdoc.dll") : NULL;
        typedef int(__cdecl * GetApi)(int, void **);
        GetApi get = m ? (GetApi)(void *)GetProcAddress(m, "RENDERDOC_GetAPI") : NULL;
        if (!get || !get(10102, (void **)&api)) every = 0, api = NULL;
        rdoc_api = api;
        fprintf(stderr, "xbrt: RenderDoc %s\n", api ? "found: a capture every XBRT_RDOC_EVERY seconds" : "not loaded (XBRT_RDOC_EVERY ignored)");
    }
    if (!api || !every || rdoc_open) return;
    uint64_t now = rt_now_100ns();
    if (!next) next = now + (uint64_t)every * 10000000;
    if (now < next) return;
    next = now + (uint64_t)every * 10000000;
    rdoc_open = 1;
}

/* After a swap: a capture due begins (StartFrameCapture, any device and window). */
static void rdoc_begin(void) {
    if (rdoc_open != 1 || !rdoc_api) return;
    ((void(__cdecl *)(void *, void *))rdoc_api[19])(NULL, NULL);
    rdoc_open = 2;
}

void rt_gl_window_swap(void) {
    static int rdoc = -1;
    if (rdoc < 0) rdoc = getenv("XBRT_RDOC_EVERY") != NULL;
    if (rdoc) rdoc_tick();
    if (win_dc) SwapBuffers(win_dc);
    if (rdoc) rdoc_begin();
}

int rt_gl_init(void) {
    HINSTANCE inst = GetModuleHandleA(NULL);
    WNDCLASSA wc = {0};
    wc.lpfnWndProc = DefWindowProcA;
    wc.hInstance = inst;
    wc.lpszClassName = "ForzaPCGL";
    RegisterClassA(&wc);
    HWND w = CreateWindowA("ForzaPCGL", "gl", WS_OVERLAPPEDWINDOW, 0, 0, 16, 16, NULL, NULL, inst, NULL); /* never shown */
    HDC dc = w ? GetDC(w) : NULL;
    PIXELFORMATDESCRIPTOR pfd;
    memset(&pfd, 0, sizeof pfd);
    pfd.nSize = sizeof pfd, pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA, pfd.cColorBits = 32, pfd.cDepthBits = 24, pfd.cStencilBits = 8;
    int format = dc ? ChoosePixelFormat(dc, &pfd) : 0;
    if (!format || !SetPixelFormat(dc, format, &pfd)) {
        fprintf(stderr, "xbrt: XBRT_GPU=gl: no OpenGL pixel format; drawing in software\n");
        return 0;
    }
    /* A legacy context first, only to find wglCreateContextAttribsARB. */
    HGLRC legacy = wglCreateContext(dc);
    if (!legacy || !wglMakeCurrent(dc, legacy)) {
        fprintf(stderr, "xbrt: XBRT_GPU=gl: no OpenGL context; drawing in software\n");
        return 0;
    }
    PFNWGLCREATECONTEXTATTRIBSARBPROC create = (PFNWGLCREATECONTEXTATTRIBSARBPROC)(void *)wglGetProcAddress("wglCreateContextAttribsARB");
    int attribs[] = {WGL_CONTEXT_MAJOR_VERSION_ARB, 4, WGL_CONTEXT_MINOR_VERSION_ARB, 3, WGL_CONTEXT_PROFILE_MASK_ARB,
                     WGL_CONTEXT_CORE_PROFILE_BIT_ARB, WGL_CONTEXT_FLAGS_ARB, getenv("XBRT_GL_DEBUG") ? WGL_CONTEXT_DEBUG_BIT_ARB : 0, 0};
    HGLRC ctx = create ? create(dc, NULL, attribs) : NULL;
    gl_ctx = ctx, gl_format = format, gl_pfd = pfd;
    wglMakeCurrent(NULL, NULL);
    wglDeleteContext(legacy);
    if (!ctx || !wglMakeCurrent(dc, ctx)) {
        fprintf(stderr, "xbrt: XBRT_GPU=gl: this GPU or driver has no OpenGL 4.3; drawing in software\n");
        return 0;
    }
    HMODULE gl = GetModuleHandleA("opengl32.dll");
    int missing = 0;
#define GL_LOAD(type, name)                                                                                                 \
    if (!(p_##name = (type)load(gl, #name))) missing++, fprintf(stderr, "xbrt: GL function %s is missing\n", #name);
    GL_FUNCTIONS(GL_LOAD)
    p_glBufferStorage = (PFNGLBUFFERSTORAGEPROC)load(gl, "glBufferStorage"); /* optional */
    { /* optional: compiling and linking on the driver's own threads (glfs.c asks without waiting) */
        typedef void(APIENTRY * MaxThreads)(GLuint);
        MaxThreads mt = (MaxThreads)load(gl, "glMaxShaderCompilerThreadsKHR");
        if (!mt) mt = (MaxThreads)load(gl, "glMaxShaderCompilerThreadsARB");
        if (mt && !(getenv("XBRT_GL_PARALLEL") && !atoi(getenv("XBRT_GL_PARALLEL")))) mt(0xFFFFFFFFu), rt_gl_parallel = 1;
    }
#undef GL_LOAD
    if (missing) {
        fprintf(stderr, "xbrt: XBRT_GPU=gl: %d GL functions missing; drawing in software\n", missing);
        return 0;
    }
    fprintf(stderr, "xbrt: OpenGL %s on %s (%s)\n", (const char *)glGetString(GL_VERSION), (const char *)glGetString(GL_RENDERER),
            (const char *)glGetString(GL_VENDOR));
    if (getenv("XBRT_GL_DEBUG")) {
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS);
        glDebugMessageCallback(debug_message, NULL);
    }
    if (!self_test()) return 0;
    rt_gl_on = 1;
    return 1;
}

/* A font of Windows' own drawn as the overlay's atlas (glover.c: 16 x 6 cells of 34x34, characters 32-127, a glyph's
 * ink from its cell's left edge, with its A, B and C widths): for when the game's font cache is not where the overlay
 * looks (another launcher's disk layout, or the menu opened before the game has made it): the menu showed its bars
 * and no words. px the letters' height, bold, slanted. 1 if it was drawn. */
int rt_gl_host_font(int px, int bold, int slant, unsigned char *atlas, signed char *wa, unsigned char *wb, signed char *wc) {
    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) return 0;
    BITMAPINFO bi = {0};
    bi.bmiHeader.biSize = sizeof bi.bmiHeader, bi.bmiHeader.biWidth = 32, bi.bmiHeader.biHeight = -32;
    bi.bmiHeader.biPlanes = 1, bi.bmiHeader.biBitCount = 32, bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bm = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    HFONT font = CreateFontA(-px, 0, 0, 0, bold ? FW_BOLD : FW_SEMIBOLD, slant ? TRUE : FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_TT_PRECIS,
                             CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_SWISS, "Segoe UI");
    if (!bm || !bits || !font) {
        if (bm) DeleteObject(bm);
        if (font) DeleteObject(font);
        DeleteDC(dc);
        return 0;
    }
    HGDIOBJ bm0 = SelectObject(dc, bm), f0 = SelectObject(dc, font);
    SetBkMode(dc, OPAQUE), SetBkColor(dc, RGB(0, 0, 0)), SetTextColor(dc, RGB(255, 255, 255));
    memset(atlas, 0, 6 * 34 * 16 * 34);
    for (int ch = 32; ch < 128; ch++) {
        ABC abc = {0, 0, 0};
        char c = (char)ch;
        int k = ch - 32;
        if (!GetCharABCWidthsA(dc, (UINT)ch, (UINT)ch, &abc)) {
            SIZE sz = {0, 0};
            GetTextExtentPoint32A(dc, &c, 1, &sz), abc.abcB = (UINT)sz.cx;
        }
        memset(bits, 0, 32 * 32 * 4);
        TextOutA(dc, -abc.abcA, (32 - px) / 2 - 2, &c, 1);
        GdiFlush();
        wa[k] = (signed char)abc.abcA, wb[k] = (unsigned char)(abc.abcB > 32 ? 32 : abc.abcB), wc[k] = (signed char)abc.abcC;
        const unsigned char *p = bits;
        for (int y = 0; y < 32; y++)
            for (int x = 0; x < 32; x++) atlas[(k / 16 * 34 + 1 + y) * (16 * 34) + k % 16 * 34 + 1 + x] = p[(y * 32 + x) * 4 + 1];
    }
    SelectObject(dc, f0), SelectObject(dc, bm0);
    DeleteObject(font), DeleteObject(bm), DeleteDC(dc);
    return 1;
}
#else
int rt_gl_host_font(int px, int bold, int slant, unsigned char *atlas, signed char *wa, unsigned char *wb, signed char *wc) {
    (void)px, (void)bold, (void)slant, (void)atlas, (void)wa, (void)wb, (void)wc;
    return 0;
}
int rt_gl_window_begin(int *W, int *H) { (void)W, (void)H; return 0; }
void rt_gl_window_swap(void) {}
int rt_gl_init(void) {
    fprintf(stderr, "xbrt: XBRT_GPU=gl is Windows-only for now; drawing in software\n");
    return 0;
}
#endif
