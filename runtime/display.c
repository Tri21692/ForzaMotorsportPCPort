/* What the Xbox would put on the TV: the front buffer the CRTC scans out,
 * with the video overlay (PVIDEO) composited on top, as xemu does it
 * (hw/xbox/nv2a/pgraph/gl/display.c).
 *
 * The front buffer is wherever D3D last pointed PCRTC_START (it flips by
 * moving it), in the format AvSetDisplayMode set. The overlay shows a
 * YUY2 image from memory, scaled into a rectangle: Bink plays movies that
 * way, decoding on the CPU, so movies show even though nothing is drawn by
 * the GPU yet.
 *
 * On Windows a window shows it, refreshed at 60 Hz. XBRT_WINDOW=0 turns
 * the window off. XBRT_SCREENSHOT=<folder> saves a BMP every
 * XBRT_SCREENSHOT_EVERY seconds (default 5) on any platform.
 */
#include <stdlib.h>
#include <string.h>

#include "rt.h"

#define DISP_W 640
#define DISP_H 480

#define REG(off) (*(volatile uint32_t *)(xb_mem + RT_NV2A_BASE + (off)))
#define PCRTC_START 0x600800
#define PVIDEO_BUFFER 0x008700
#define PVIDEO_BASE 0x008900
#define PVIDEO_LIMIT 0x008908
#define PVIDEO_OFFSET 0x008920
#define PVIDEO_SIZE_IN 0x008928
#define PVIDEO_POINT_IN 0x008930
#define PVIDEO_DS_DX 0x008938
#define PVIDEO_DT_DY 0x008940
#define PVIDEO_POINT_OUT 0x008948
#define PVIDEO_SIZE_OUT 0x008950
#define PVIDEO_FORMAT 0x008958

static inline const uint8_t *phys(uint32_t pa) { return xb_mem + RT_PHYS_VIEW + (pa & (RT_PHYS_SIZE - 1)); }

static uint8_t clamp8(int v) { return v < 0 ? 0 : v > 255 ? 255 : (uint8_t)v; }

/* BT.601, limited range, as a TV decodes it. */
static uint32_t yuv(int y, int u, int v) {
    int c = y - 16, d = u - 128, e = v - 128;
    int r = (298 * c + 409 * e + 128) >> 8, g = (298 * c - 100 * d - 208 * e + 128) >> 8, b = (298 * c + 516 * d + 128) >> 8;
    return (uint32_t)clamp8(r) << 16 | (uint32_t)clamp8(g) << 8 | clamp8(b);
}

static void overlay(uint32_t *out) {
    if (!(REG(PVIDEO_BUFFER) & 1) || REG(PVIDEO_SIZE_IN) == 0xFFFFFFFFu) return;
    uint32_t base = REG(PVIDEO_BASE), offset = REG(PVIDEO_OFFSET), limit = REG(PVIDEO_LIMIT);
    int in_w = REG(PVIDEO_SIZE_IN) & 0x7FF, in_h = (REG(PVIDEO_SIZE_IN) >> 16) & 0x7FF;
    int pitch = REG(PVIDEO_FORMAT) & 0x1FFF;
    int out_x = REG(PVIDEO_POINT_OUT) & 0xFFF, out_y = (REG(PVIDEO_POINT_OUT) >> 16) & 0xFFF;
    int out_w = REG(PVIDEO_SIZE_OUT) & 0xFFF, out_h = (REG(PVIDEO_SIZE_OUT) >> 16) & 0xFFF;
    int in_s = (REG(PVIDEO_POINT_IN) & 0x7FFF) / 16, in_t = (int)(REG(PVIDEO_POINT_IN) >> 17) / 8;
    uint32_t dsdx = REG(PVIDEO_DS_DX), dtdy = REG(PVIDEO_DT_DY); /* input per output pixel, 12.20 fixed point */
    if (!in_w || !in_h || !out_w || !out_h || !pitch || !dsdx || !dtdy) return;
    if ((uint64_t)offset + (uint64_t)pitch * in_h > (uint64_t)limit + 1) return;
    const uint8_t *src = phys(base + offset);
    for (int y = 0; y < out_h; y++) {
        int dy = out_y + y;
        if (dy < 0 || dy >= DISP_H) continue;
        int sy = in_t + (int)(((uint64_t)y * dtdy) >> 20);
        if (sy >= in_h) break;
        const uint8_t *line = src + (size_t)sy * pitch;
        for (int x = 0; x < out_w; x++) {
            int dx = out_x + x;
            if (dx < 0 || dx >= DISP_W) continue;
            int sx = in_s + (int)(((uint64_t)x * dsdx) >> 20);
            if (sx >= in_w) break;
            const uint8_t *p = line + (sx & ~1) * 2; /* Y0 U Y1 V */
            out[dy * DISP_W + dx] = yuv(p[(sx & 1) * 2], p[1], p[3]);
        }
    }
}

/* The picture as the TV would show it, 640x480 xRGB. */
void rt_display_compose(uint32_t *out) {
    uint32_t fb = REG(PCRTC_START);
    if (!fb) fb = rt_display_fb;
    uint32_t pitch = rt_display_pitch ? rt_display_pitch : DISP_W * 4;
    memset(out, 0, DISP_W * DISP_H * 4);
    if (fb) {
        for (int y = 0; y < DISP_H; y++) {
            const uint8_t *row = phys(fb + (uint32_t)y * pitch);
            if (pitch >= DISP_W * 4) {
                memcpy(out + y * DISP_W, row, DISP_W * 4);
            } else { /* 16-bit R5G6B5 */
                for (int x = 0; x < DISP_W; x++) {
                    uint16_t p = (uint16_t)(row[2 * x] | row[2 * x + 1] << 8);
                    out[y * DISP_W + x] = (uint32_t)((p >> 11) * 255 / 31) << 16 | (uint32_t)(((p >> 5) & 63) * 255 / 63) << 8 |
                                     (uint32_t)((p & 31) * 255 / 31);
                }
            }
        }
    }
    overlay(out);
}

int rt_display_video_on(void) { return (REG(PVIDEO_BUFFER) & 1) && REG(PVIDEO_SIZE_IN) != 0xFFFFFFFFu; }

void rt_display_compose_best(uint32_t *out, int *w, int *h) {
    int video = rt_display_video_on(); /* a movie through the overlay */
    uint32_t fb = REG(PCRTC_START);
    if (!video && fb && rt_gl_frame(fb, out, RT_DISPLAY_MAX, w, h)) return;
    rt_display_compose(out);
    *w = DISP_W, *h = DISP_H;
}

/* ---- screenshots: 24-bit BMP, bottom-up ---- */

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v, p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v), put16(p + 2, (uint16_t)(v >> 16)); }

static void save_bmp(const char *path, const uint32_t *px, int W, int H) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    uint8_t h[54] = {'B', 'M'};
    uint32_t row = (uint32_t)W * 3, size = 54 + row * (uint32_t)H;
    put32(h + 2, size), put32(h + 10, 54), put32(h + 14, 40), put32(h + 18, (uint32_t)W), put32(h + 22, (uint32_t)H);
    put16(h + 26, 1), put16(h + 28, 24), put32(h + 34, row * (uint32_t)H);
    fwrite(h, 1, 54, f);
    uint8_t *line = malloc(row);
    for (int y = H - 1; y >= 0; y--) {
        for (int x = 0; x < W; x++) {
            uint32_t p = px[y * W + x];
            line[3 * x] = (uint8_t)p, line[3 * x + 1] = (uint8_t)(p >> 8), line[3 * x + 2] = (uint8_t)(p >> 16);
        }
        fwrite(line, 1, row, f);
    }
    free(line);
    fclose(f);
}

volatile uint32_t rt_debug_keys;

volatile int rt_display_fxaa = 1;

int rt_display_widescreen(void) {
    static int w = -1;
    if (w < 0) w = getenv("XBRT_WIDESCREEN") && atoi(getenv("XBRT_WIDESCREEN"));
    return w;
}

/* The largest 4:3 (or 16:9) rectangle centred in W x H. */
void rt_display_fit(int W, int H, int *x, int *y, int *w, int *h) {
    int aw = rt_display_widescreen() ? 16 : 4, ah = rt_display_widescreen() ? 9 : 3;
    if ((long)W * ah > (long)H * aw) *h = H, *w = H * aw / ah;
    else *w = W, *h = W * ah / aw;
    *x = (W - *w) / 2, *y = (H - *h) / 2;
}
volatile uint64_t rt_gl_shown;

/* The GPU draws the window (rt_gl_show) until it says RAM shows what is on
 * screen (menus at 1x, movies); else GDI draws it from frame[]. Not on a
 * timeout: in a hitch the window went to frame[], which nothing keeps up
 * to date then, and flashed grey. */
static int gl_showing(void) { return rt_gl_shown != 0; }

static int recording(void) {
    static int r = -1;
    if (r < 0) r = getenv("XBRT_RECORD") && *getenv("XBRT_RECORD");
    return r;
}

static const char *shot_dir;
static double shot_every = 5;
static int shot_count;
static uint64_t next_shot;

static void maybe_screenshot(const uint32_t *px, int w, int h) {
    if (!shot_dir) return;
    uint64_t now = rt_now_100ns();
    if (now < next_shot) return;
    next_shot = now + (uint64_t)(shot_every * 1e7);
    char path[1024];
    snprintf(path, sizeof path, "%s/shot_%04d_%06.1fs.bmp", shot_dir, shot_count++, now / 1e7);
    save_bmp(path, px, w, h);
}

/* ---- the window ---- */

#ifdef _WIN32
#include <windows.h>

static HWND window;
static HANDLE new_frame; /* set by rt_display_new_frame */
static volatile int shot_wanted; /* F12 pressed, with the window drawn by the GPU: the next picture read back is saved */

void rt_display_new_frame(void) {
    if (new_frame) SetEvent(new_frame);
}
static uint32_t frame[RT_DISPLAY_MAX];
static int frame_w = DISP_W, frame_h = DISP_H;

/* F5-F9 flip rt_debug_keys (the title says which are on); F12 saves the
 * picture to screenshots/ beside the game, whether XBRT_SCREENSHOT is set
 * or not. */
static void debug_key(WPARAM vk) {
    static const char *names[] = {"no culling", "no depth test", "no alpha test", "no depth clip", "CPU vertex programs"};
    if (vk == VK_F12) {
        if (rt_gl_shown) { /* the window is drawn by the GPU: frame[] is not kept up to date */
            shot_wanted = 1;
            return;
        }
        CreateDirectoryA("screenshots", NULL);
        char path[256];
        snprintf(path, sizeof path, "screenshots/shot_%06.1fs.bmp", rt_now_100ns() / 1e7);
        save_bmp(path, frame, frame_w, frame_h);
        return;
    }
    if (vk < VK_F5 || vk > VK_F9) return;
    rt_debug_keys ^= 1u << (vk - VK_F5);
    char title[512];
    int n = snprintf(title, sizeof title, "Forza Motorsport (PC port, work in progress)");
    for (int i = 0; i < 5; i++)
        if (rt_debug_keys & (1u << i)) n += snprintf(title + n, sizeof title - n, " | F%d %s", 5 + i, names[i]);
    SetWindowTextA(window, title);
}

static void set_fullscreen(int on);

static LRESULT CALLBACK wndproc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd, &ps);
        if (gl_showing()) { /* the GPU draws the window itself */
            EndPaint(hwnd, &ps);
            return 0;
        }
        RECT r;
        GetClientRect(hwnd, &r);
        BITMAPINFO bi = {0};
        bi.bmiHeader.biSize = sizeof bi.bmiHeader;
        bi.bmiHeader.biWidth = frame_w, bi.bmiHeader.biHeight = -frame_h; /* top-down */
        bi.bmiHeader.biPlanes = 1, bi.bmiHeader.biBitCount = 32, bi.bmiHeader.biCompression = BI_RGB;
        int x, y, w, h;
        rt_display_fit(r.right, r.bottom, &x, &y, &w, &h);
        PatBlt(dc, 0, 0, r.right, y, BLACKNESS), PatBlt(dc, 0, y + h, r.right, r.bottom - y - h, BLACKNESS);
        PatBlt(dc, 0, y, x, h, BLACKNESS), PatBlt(dc, x + w, y, r.right - x - w, h, BLACKNESS);
        SetStretchBltMode(dc, HALFTONE);
        StretchDIBits(dc, x, y, w, h, 0, 0, frame_w, frame_h, frame, &bi, DIB_RGB_COLORS, SRCCOPY);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_TIMER:
        if (gl_showing() && !rt_display_wants_pixels()) return 0;
        rt_display_compose_best(frame, &frame_w, &frame_h);
        maybe_screenshot(frame, frame_w, frame_h);
        if (shot_wanted && wp == 2) { /* a picture just read back for F12 */
            shot_wanted = 0;
            rt_gl_shown = 0, debug_key(VK_F12), rt_gl_shown = rt_now_100ns();
        }
        if (!gl_showing()) InvalidateRect(hwnd, NULL, FALSE);
        return 0;
    case WM_APP: /* rt_display_set_fullscreen, from another thread */
        set_fullscreen((int)wp);
        return 0;
    case WM_KEYDOWN:
        if (wp == VK_F1) {
            rt_overlay_toggle();
            return 0;
        }
        if (rt_overlay_open()) {
            int k = wp == VK_UP ? RT_OV_UP : wp == VK_DOWN ? RT_OV_DOWN : wp == VK_LEFT ? RT_OV_LEFT : wp == VK_RIGHT ? RT_OV_RIGHT
                  : wp == VK_RETURN || wp == VK_SPACE ? RT_OV_OK : wp == VK_ESCAPE || wp == VK_BACK ? RT_OV_BACK : -1;
            if (k >= 0) rt_overlay_key(k);
            return 0;
        }
        if (wp == VK_F11) {
            static int fs = -1;
            if (fs < 0) fs = getenv("XBRT_FULLSCREEN") && atoi(getenv("XBRT_FULLSCREEN"));
            set_fullscreen(fs = !fs);
            return 0;
        }
        debug_key(wp);
        break;
    case WM_SYSKEYDOWN: /* Alt+Enter */
        if (wp == VK_RETURN && (lp & (1 << 29))) {
            SendMessageA(hwnd, WM_KEYDOWN, VK_F11, 0);
            return 0;
        }
        break;
    case WM_ERASEBKGND:
        return 1;
    case WM_CLOSE:
        ExitProcess(0);
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

/* Borderless fullscreen on the monitor the window is on, or back to the
 * window as it was (Alt+Enter, F11, XBRT_FULLSCREEN=1 at the start). */
static void set_fullscreen(int on) {
    static int is;
    static WINDOWPLACEMENT was;
    was.length = sizeof was;
    if (on == is) return;
    if (on) {
        GetWindowPlacement(window, &was);
        MONITORINFO mi;
        memset(&mi, 0, sizeof mi), mi.cbSize = sizeof mi;
        GetMonitorInfoA(MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST), &mi);
        SetWindowLongA(window, GWL_STYLE, WS_POPUP | WS_VISIBLE);
        SetWindowPos(window, HWND_TOP, mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right - mi.rcMonitor.left,
                     mi.rcMonitor.bottom - mi.rcMonitor.top, SWP_FRAMECHANGED | SWP_SHOWWINDOW);
    } else {
        SetWindowLongA(window, GWL_STYLE, WS_OVERLAPPEDWINDOW | WS_VISIBLE);
        SetWindowPlacement(window, &was);
        SetWindowPos(window, NULL, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
    }
    is = on;
}

static DWORD WINAPI window_main(LPVOID arg) {
    (void)arg;
    new_frame = CreateEventA(NULL, FALSE, FALSE, NULL);
    WNDCLASSA wc = {0};
    wc.style = CS_OWNDC; /* OpenGL draws into it */
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = "ForzaPC";
    RegisterClassA(&wc);
    /* XBRT_WINDOW_SIZE=<w>x<h>, else twice the Xbox picture at its aspect
     * (1280x960, or 1280x720 for 16:9), shrunk to fit the screen. */
    int cw = DISP_W * 2, ch = rt_display_widescreen() ? DISP_W * 2 * 9 / 16 : DISP_H * 2;
    const char *ws = getenv("XBRT_WINDOW_SIZE");
    int ww, wh;
    if (ws && sscanf(ws, "%dx%d", &ww, &wh) == 2 && ww >= 320 && wh >= 240) cw = ww, ch = wh;
    RECT work;
    SystemParametersInfoA(SPI_GETWORKAREA, 0, &work, 0);
    int maxw = (work.right - work.left) * 9 / 10, maxh = (work.bottom - work.top) * 9 / 10;
    if (cw > maxw) ch = ch * maxw / cw, cw = maxw;
    if (ch > maxh) cw = cw * maxh / ch, ch = maxh;
    RECT r = {0, 0, cw, ch};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    window = CreateWindowA("ForzaPC", "Forza Motorsport (PC port, work in progress)", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    if (getenv("XBRT_FULLSCREEN") && atoi(getenv("XBRT_FULLSCREEN"))) set_fullscreen(1);
    SetTimer(window, 1, 16, NULL); /* the picture from RAM (menus' 1x frames, movies) */
    for (;;) { /* and a new GPU picture as soon as it arrives */
        DWORD r = MsgWaitForMultipleObjects(1, &new_frame, FALSE, INFINITE, QS_ALLINPUT);
        if (r == WAIT_OBJECT_0) SendMessageA(window, WM_TIMER, 2, 0), UpdateWindow(window);
        MSG m;
        while (PeekMessageA(&m, NULL, 0, 0, PM_REMOVE)) {
            if (m.message == WM_QUIT) return 0;
            TranslateMessage(&m);
            DispatchMessageA(&m);
        }
    }
    return 0;
}

int rt_display_focused(void) { return window && GetForegroundWindow() == window; }
void rt_display_set_fullscreen(int on) {
    if (window) PostMessageA(window, WM_APP, (WPARAM)on, 0);
}
void *rt_display_hwnd(void) { return window; }
int rt_display_wants_pixels(void) { return shot_dir || shot_wanted || recording(); }
#else
int rt_display_focused(void) { return 1; }
void rt_display_set_fullscreen(int on) { (void)on; }
void *rt_display_hwnd(void) { return NULL; }
int rt_display_wants_pixels(void) { return shot_dir || recording(); }
void rt_display_new_frame(void) {}
#endif

/* Without a window, screenshots come from a thread of their own. */
static void *shot_main(void *arg) {
    (void)arg;
    static uint32_t px[RT_DISPLAY_MAX];
    for (;;) {
        int w, h;
        rt_display_compose_best(px, &w, &h);
        maybe_screenshot(px, w, h);
        struct timespec ts = {0, 100000000};
        nanosleep(&ts, NULL);
    }
    return NULL;
}

void rt_display_init(void) {
    shot_dir = getenv("XBRT_SCREENSHOT");
    if (shot_dir && !*shot_dir) shot_dir = NULL;
    const char *every = getenv("XBRT_SCREENSHOT_EVERY");
    if (every && atof(every) > 0) shot_every = atof(every);
    const char *w = getenv("XBRT_WINDOW");
    int want_window = !w || atoi(w);
#ifdef _WIN32
    if (want_window) {
        CreateThread(NULL, 0, window_main, NULL, 0, NULL);
        return;
    }
#endif
    (void)want_window;
    if (shot_dir) {
        pthread_t t;
        pthread_create(&t, NULL, shot_main, NULL);
    }
}
