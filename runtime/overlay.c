/* The settings overlay: F1 (or Back+Start on the pad) opens a menu over
 * the game, drawn by glfill.c (gl_overlay_draw) in the style of Forza's
 * own menus and with its fonts. Up and down pick a setting, left and right
 * (or A / Enter) change it, B / Esc / F1 close it. Every change is saved
 * to forza.ini at once (settings.c); volume, edge smoothing and fullscreen
 * apply at once, the rest when the game next starts. While it is open the
 * game sees no input. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"

typedef struct {
    const char *setting, *label;
    const char *values[12], *shown[12];
    int live; /* applies at once */
    const char *help;
} OvItem;

static const OvItem items[] = {
    {"fps", "Frame Rate", {"30", "60"}, {"30 FPS", "60 FPS"}, 0, "Forza runs its physics once a frame, so 60 is the most it can do."},
    {"scale", "Resolution", {"1", "2", "3", "4"}, {"1x  (640x480)", "2x  (1280x960)", "3x  (1920x1440)", "4x  (2560x1920)"}, 0,
     "Draws the game at a multiple of the Xbox's 640x480. 3x and 4x need a strong GPU."},
    {"widescreen", "Widescreen", {"0", "1"}, {"Off  (4:3)", "On  (16:9)"}, 0, "Forza draws a wider 16:9 view of the track itself."},
    {"fullscreen", "Fullscreen", {"0", "1"}, {"Off", "On"}, 1, "Borderless fullscreen. Alt+Enter or F11 switches at any time."},
    {"window", "Window Size", {"auto", "1280x960", "1600x1200", "1280x720", "1920x1080", "2560x1440"},
     {"Auto", "1280 x 960", "1600 x 1200", "1280 x 720", "1920 x 1080", "2560 x 1440"}, 0,
     "The window's size when not fullscreen. Auto fits it to the screen."},
    {"antialiasing", "Anti-Aliasing", {"off", "fxaa"}, {"Off", "FXAA"}, 1, "FXAA smooths jagged edges at almost no cost."},
    {"anisotropic", "Texture Filtering", {"1", "2", "4", "8", "16"}, {"Off", "2x Anisotropic", "4x Anisotropic", "8x Anisotropic", "16x Anisotropic"}, 0,
     "Keeps the road and verges sharp when seen at a shallow angle."},
    {"vsync", "V-Sync", {"0", "1"}, {"Off", "On"}, 0, "Waits for the monitor's refresh to show a frame. Can add delay."},
    {"volume", "Volume", {"0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"},
     {"0", "10", "20", "30", "40", "50", "60", "70", "80", "90", "100"}, 1, "Sound volume."},
};
#define NITEMS (int)(sizeof items / sizeof items[0])

static volatile int open_, sel;
static int changed_restart; /* something changed that needs a restart */

int rt_overlay_open(void) {
    static int checked; /* XBRT_OVERLAY=1: open from the start (for looking at it) */
    if (!checked) checked = 1, open_ = getenv("XBRT_OVERLAY") && atoi(getenv("XBRT_OVERLAY"));
    return open_;
}
int rt_overlay_items(void) { return NITEMS; }
int rt_overlay_selected(void) { return sel; }
int rt_overlay_needs_restart(void) { return changed_restart; }

static int nvalues(const OvItem *it) {
    int n = 0;
    while (n < 12 && it->values[n]) n++;
    return n;
}

static int current(const OvItem *it) {
    const char *v = rt_settings_get(it->setting);
    for (int i = 0; i < nvalues(it); i++)
        if (v && !strcmp(v, it->values[i])) return i;
    if (v && !strcmp(it->setting, "volume")) { /* nearest step */
        int i = (int)(atof(v) * 10 + 0.5);
        return i < 0 ? 0 : i > 10 ? 10 : i;
    }
    return -1;
}

void rt_overlay_item(int i, const char **label, const char **value, int *live) {
    const OvItem *it = &items[i];
    int c = current(it);
    *label = it->label;
    *value = c >= 0 ? it->shown[c] : rt_settings_get(it->setting);
    *live = it->live;
}

const char *rt_overlay_help(int i) { return items[i].help; }

static void apply(const OvItem *it, const char *v) {
    rt_settings_set(it->setting, v);
    if (!strcmp(it->setting, "volume")) rt_apu_set_volume((float)atof(v));
    else if (!strcmp(it->setting, "antialiasing")) rt_display_fxaa = strcmp(v, "off") != 0;
    else if (!strcmp(it->setting, "fullscreen")) rt_display_set_fullscreen(atoi(v));
    else changed_restart = 1;
}

void rt_overlay_toggle(void) { open_ = !open_; }

void rt_overlay_key(int key) {
    if (!open_) return;
    const OvItem *it = &items[sel];
    int n = nvalues(it), c = current(it);
    switch (key) {
    case RT_OV_UP: sel = (sel + NITEMS - 1) % NITEMS; break;
    case RT_OV_DOWN: sel = (sel + 1) % NITEMS; break;
    case RT_OV_LEFT: apply(it, it->values[c <= 0 ? 0 : c - 1]); break;
    case RT_OV_RIGHT: apply(it, it->values[c < 0 ? 0 : c + 1 < n ? c + 1 : n - 1]); break;
    case RT_OV_OK: apply(it, it->values[(c + 1) % n]); break; /* A cycles */
    case RT_OV_BACK: open_ = 0; break;
    }
}

/* The pad, from the game's input poll (hle_input.c): Back+Start opens
 * the overlay; while open, the D-pad, the left stick, A and B drive it and
 * the game sees nothing. 1: swallowed. */
int rt_overlay_pad(uint16_t buttons, const uint8_t analog[8], const int16_t thumbs[4]) {
    static uint16_t was;
    static int stick_was;
    int combo = (buttons & 0x30) == 0x30, combo_was = (was & 0x30) == 0x30;
    if (combo && !combo_was) rt_overlay_toggle();
    if (!open_) {
        was = buttons;
        return 0;
    }
    uint16_t down = buttons & ~was;
    int stick = thumbs[1] > 20000 ? 1 : thumbs[1] < -20000 ? 2 : thumbs[0] < -20000 ? 3 : thumbs[0] > 20000 ? 4 : 0;
    static int a_was, b_was;
    int a = analog[0] > 128, b = analog[1] > 128; /* A, B are analog buttons on the Xbox pad */
    if ((down & 0x1) || (stick == 1 && stick_was != 1)) rt_overlay_key(RT_OV_UP);
    if ((down & 0x2) || (stick == 2 && stick_was != 2)) rt_overlay_key(RT_OV_DOWN);
    if ((down & 0x4) || (stick == 3 && stick_was != 3)) rt_overlay_key(RT_OV_LEFT);
    if ((down & 0x8) || (stick == 4 && stick_was != 4)) rt_overlay_key(RT_OV_RIGHT);
    if (a && !a_was) rt_overlay_key(RT_OV_OK);
    if (b && !b_was) rt_overlay_key(RT_OV_BACK);
    a_was = a, b_was = b, stick_was = stick, was = buttons;
    return 1;
}
