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
    RECT r;
    GetClientRect(wnd, &r);
    *W = r.right > 0 ? r.right : 0, *H = r.bottom > 0 ? r.bottom : 0;
    return 1;
}

void rt_gl_window_swap(void) {
    if (win_dc) SwapBuffers(win_dc);
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
#else
int rt_gl_window_begin(int *W, int *H) { (void)W, (void)H; return 0; }
void rt_gl_window_swap(void) {}
int rt_gl_init(void) {
    fprintf(stderr, "xbrt: XBRT_GPU=gl is Windows-only for now; drawing in software\n");
    return 0;
}
#endif
