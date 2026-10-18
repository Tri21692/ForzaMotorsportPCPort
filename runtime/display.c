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

/* ---- screenshots: 24-bit BMP, bottom-up ---- */

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v, p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v), put16(p + 2, (uint16_t)(v >> 16)); }

static void save_bmp(const char *path, const uint32_t *px) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    uint8_t h[54] = {'B', 'M'};
    uint32_t row = DISP_W * 3, size = 54 + row * DISP_H;
    put32(h + 2, size), put32(h + 10, 54), put32(h + 14, 40), put32(h + 18, DISP_W), put32(h + 22, DISP_H);
    put16(h + 26, 1), put16(h + 28, 24), put32(h + 34, row * DISP_H);
    fwrite(h, 1, 54, f);
    uint8_t *line = malloc(row);
    for (int y = DISP_H - 1; y >= 0; y--) {
        for (int x = 0; x < DISP_W; x++) {
            uint32_t p = px[y * DISP_W + x];
            line[3 * x] = (uint8_t)p, line[3 * x + 1] = (uint8_t)(p >> 8), line[3 * x + 2] = (uint8_t)(p >> 16);
        }
        fwrite(line, 1, row, f);
    }
    free(line);
    fclose(f);
}

static const char *shot_dir;
static double shot_every = 5;
static int shot_count;
static uint64_t next_shot;

static void maybe_screenshot(const uint32_t *px) {
    if (!shot_dir) return;
    uint64_t now = rt_now_100ns();
    if (now < next_shot) return;
    next_shot = now + (uint64_t)(shot_every * 1e7);
    char path[1024];
    snprintf(path, sizeof path, "%s/shot_%04d_%06.1fs.bmp", shot_dir, shot_count++, now / 1e7);
    save_bmp(path, px);
}

/* ---- the window ---- */

#ifdef _WIN32
#include <windows.h>

static HWND window;
static uint32_t frame[DISP_W * DISP_H];

static LRESULT CALLBACK wndproc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd, &ps);
        RECT r;
        GetClientRect(hwnd, &r);
        BITMAPINFO bi = {0};
        bi.bmiHeader.biSize = sizeof bi.bmiHeader;
        bi.bmiHeader.biWidth = DISP_W, bi.bmiHeader.biHeight = -DISP_H; /* top-down */
        bi.bmiHeader.biPlanes = 1, bi.bmiHeader.biBitCount = 32, bi.bmiHeader.biCompression = BI_RGB;
        SetStretchBltMode(dc, HALFTONE);
        StretchDIBits(dc, 0, 0, r.right, r.bottom, 0, 0, DISP_W, DISP_H, frame, &bi, DIB_RGB_COLORS, SRCCOPY);
        EndPaint(hwnd, &ps);
        return 0;
    }
    case WM_TIMER:
        rt_display_compose(frame);
        maybe_screenshot(frame);
        InvalidateRect(hwnd, NULL, FALSE);
        return 0;
    case WM_CLOSE:
        ExitProcess(0);
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

static DWORD WINAPI window_main(LPVOID arg) {
    (void)arg;
    WNDCLASSA wc = {0};
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = "ForzaPC";
    RegisterClassA(&wc);
    RECT r = {0, 0, DISP_W * 2, DISP_H * 2};
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    window = CreateWindowA("ForzaPC", "Forza Motorsport (PC port, work in progress)", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    SetTimer(window, 1, 16, NULL);
    MSG m;
    while (GetMessageA(&m, NULL, 0, 0) > 0) {
        TranslateMessage(&m);
        DispatchMessageA(&m);
    }
    return 0;
}

int rt_display_focused(void) { return window && GetForegroundWindow() == window; }
#else
int rt_display_focused(void) { return 1; }
#endif

/* Without a window, screenshots come from a thread of their own. */
static void *shot_main(void *arg) {
    (void)arg;
    static uint32_t px[DISP_W * DISP_H];
    for (;;) {
        rt_display_compose(px);
        maybe_screenshot(px);
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
