/* The settings overlay: F1 (or Back+Start on the pad; L3 for a while on 7 Nov, the user's
 * "I prefer back + start") opens a menu over
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

/* Tab by tab (the user's, 2026-11-02: "sections in the F1 menu"): an entry with no setting starts a tab, its label
 * the tab's name. */
static const OvItem items[] = {
    {NULL, "Display", {NULL}, {NULL}, 0, NULL},
    {"scale", "Resolution", {"1", "2", "3", "4", "5", "6"},
     {"1x  (640x480)", "2x  (1280x960)", "3x  (1920x1440)", "4x  (2560x1920)", "5x  (3200x2400)", "6x  (3840x2880)"}, 0,
     "A multiple of the Xbox's 640x480. Lower it on slower GPUs; 5x and 6x need a fast one."},
    {"widescreen", "Widescreen", {"0", "1"}, {"Off  (4:3)", "On  (16:9)"}, 0, "Forza draws a wider 16:9 view of the track itself."},
    {"fullscreen", "Fullscreen", {"0", "1"}, {"Off", "On"}, 1, "Borderless fullscreen. Alt+Enter or F11 switches at any time."},
    {"window", "Window Size", {"auto", "1280x960", "1600x1200", "1280x720", "1920x1080", "2560x1440"},
     {"Auto", "1280 x 960", "1600 x 1200", "1280 x 720", "1920 x 1080", "2560 x 1440"}, 0,
     "The window's size when not fullscreen. Auto fits it to the screen."},
    {"fps", "Frame Rate", {"30", "60"}, {"30 FPS", "60 FPS"}, 0, "Forza runs its physics once a frame, so 60 is the most it can do."},
    {"vsync", "V-Sync", {"0", "1"}, {"Off", "On"}, 0, "Waits for the monitor's refresh to show a frame. Can add delay."},
    {NULL, "Graphics", {NULL}, {NULL}, 0, NULL},
    {"antialiasing", "Anti-Aliasing", {"off", "fxaa"}, {"Off", "FXAA"}, 1, "FXAA smooths jagged edges at almost no cost."},
    {"anisotropic", "Texture Filtering", {"1", "2", "4", "8", "16"}, {"Off", "2x Anisotropic", "4x Anisotropic", "8x Anisotropic", "16x Anisotropic"}, 0,
     "Keeps the road and verges sharp when seen at a shallow angle."},
    {"texture_pack", "HD Texture Pack", {"0", "1"}, {"Off", "On"}, 1,
     "AI-upscaled textures from the mods folder, where the pack has them. Changing it reloads the textures."},
    {"texture_upscale", "Texture Upscaling", {"0", "2", "4"}, {"Off", "2x", "4x"}, 1,
     "Redraws the other textures larger as they load: sharper up close. 4x uses more video memory. Changing it reloads the textures."},
    {"soft_shadows", "Soft Shadows", {"0", "1"}, {"Off", "On"}, 0, "Smooth shadow edges instead of the Xbox's stepped ones."},
    {"sharpen", "Sharpening", {"0", "0.25", "0.5", "0.75", "1"}, {"Off", "Low", "Medium", "High", "Maximum"}, 1,
     "Crisper detail on the road, cars and signs. Contrast-adaptive, so edges do not ring."},
    {"bloom", "Bloom", {"0", "0.15", "0.3", "0.5", "0.75"}, {"Off", "Subtle", "Medium", "Strong", "Very Strong"}, 1,
     "A soft glow round the sky, sun on paint and lamps."},
    {"vibrance", "Vibrance", {"0", "0.15", "0.25", "0.4", "0.6"}, {"Off", "Subtle", "Medium", "Strong", "Very Strong"}, 1,
     "Richer colour in dull tones (asphalt, grass, muted paint); saturated colours are left alone."},
    {"brightness", "Brightness", {"0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"}, {"40%", "50%", "60%", "70%", "80%", "90%", "100%  (Xbox)"}, 1,
     "How strongly Forza's exposure brightens the picture. 100% is as on the Xbox."},
    {NULL, "HDR", {NULL}, {NULL}, 0, NULL},
    {"hdr", "HDR", {"0", "1"}, {"Off", "On"}, 0,
     "HDR output on an HDR screen. Turn on Use HDR in Windows' display settings first."},
    {"hdr_paper_white", "HDR White Level", {"120", "160", "200", "250", "300", "400"}, {"120 nits", "160 nits", "200 nits", "250 nits", "300 nits", "400 nits"}, 1,
     "How bright white is with HDR on (menus, the HUD, white paint)."},
    {"hdr_peak", "HDR Peak Brightness", {"auto", "400", "600", "800", "1000", "1500"}, {"Auto  (the screen's)", "400 nits", "600 nits", "800 nits", "1000 nits", "1500 nits"}, 1,
     "How bright the sky, sun and lamps get with HDR on."},
    {NULL, "Game", {NULL}, {NULL}, 0, NULL},
    {"show_fps", "Show Frame Rate", {"0", "1"}, {"Off", "On"}, 1, "The frame rate, small in the top left corner."},
    {"skip_intro", "Skip Intro Video", {"0", "1"}, {"Off", "On"}, 0, "Skips the intro video when the game starts."},
    {"fast_loading", "Fast Loading", {"0", "1"}, {"Off", "On"}, 1,
     "Skips the game's least time on loading screens: races start and restart about a second sooner."},
    {NULL, "Audio", {NULL}, {NULL}, 0, NULL},
    {"volume", "Volume", {"0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1"},
     {"0", "10", "20", "30", "40", "50", "60", "70", "80", "90", "100"}, 1, "Sound volume."},
    {"background_mute", "Mute in Background", {"0", "1"}, {"Off", "On"}, 1, "Silent while the game's window is not in front."},
    {NULL, "Achievements", {NULL}, {NULL}, 0, NULL}, /* (no settings: glover.c lists rt_ach_get's) */
    {NULL, "Moments", {NULL}, {NULL}, 0, NULL}, /* (none either: glover.c shows rt_mm_get's, with their photographs) */
};
#define NITEMS (int)(sizeof items / sizeof items[0])

static volatile int open_, sel, tab, scroll; /* sel: within the tab; scroll: a tab with no settings (the achievements) */
static int changed_restart; /* something changed that needs a restart */

/* The tabs: each one's header entry, the first of its settings and how many. */
#define MAXTABS 8
static int ntabs, tab_head[MAXTABS], tab_first[MAXTABS], tab_n[MAXTABS];
static void tabs_init(void) {
    if (ntabs) return;
    for (int i = 0; i < NITEMS && ntabs < MAXTABS; i++)
        if (!items[i].setting) tab_head[ntabs] = i, tab_first[ntabs] = i + 1, tab_n[ntabs++] = 0;
        else if (ntabs) tab_n[ntabs - 1]++;
}
static const OvItem *at(int i) { return &items[tab_first[tab] + i]; } /* the tab's i-th setting */

int rt_overlay_open(void) {
    static int checked; /* XBRT_OVERLAY=1: open from the start (for looking at it) */
    if (!checked) checked = 1, open_ = getenv("XBRT_OVERLAY") && atoi(getenv("XBRT_OVERLAY"));
    return open_;
}
int rt_overlay_items(void) { tabs_init(); return tab_n[tab]; }
int rt_overlay_tabs(const char **names, int max, int *cur) {
    tabs_init();
    for (int i = 0; i < ntabs && i < max; i++) names[i] = items[tab_head[i]].label;
    *cur = tab;
    return ntabs;
}
int rt_overlay_selected(void) { return sel; }
/* the page shown: 0 settings, 1 the achievements, 2 the Mayhem Moments */
int rt_overlay_page(void) { tabs_init(); return tab_n[tab] ? 0 : strcmp(items[tab_head[tab]].label, "Moments") ? 1 : 2; /* (the Mayhem Moments: "Moments", all the tabs in 4:3) */ }
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
    tabs_init();
    const OvItem *it = at(i);
    int c = current(it);
    *label = it->label;
    *value = c >= 0 ? it->shown[c] : rt_settings_get(it->setting);
    *live = it->live;
}

const char *rt_overlay_help(int i) {
    tabs_init();
    if (tab_n[tab]) return at(i)->help;
    return rt_overlay_page() == 2 ? "Take an opponent down at each place in a Mayhem race to light its photograph up."
                                  : "What you have earned so far. Up and down scroll the list.";
}
int rt_overlay_scroll(void) { return scroll; }

static void apply(const OvItem *it, const char *v) {
    rt_settings_set(it->setting, v);
    if (!strcmp(it->setting, "volume")) rt_apu_set_volume((float)atof(v));
    else if (!strcmp(it->setting, "antialiasing")) rt_display_fxaa = strcmp(v, "off") != 0;
    else if (!strcmp(it->setting, "fullscreen")) rt_display_set_fullscreen(atoi(v));
    else if (!strcmp(it->setting, "brightness")) rt_brightness = (float)atof(v);
    else if (!strcmp(it->setting, "show_fps")) rt_show_fps = atoi(v);
    else if (!strcmp(it->setting, "fast_loading")) rt_fast_loading = atoi(v);
    else if (!strcmp(it->setting, "texture_pack")) rt_tex_pack_on = atoi(v), rt_tex_reload = 1;
    else if (!strcmp(it->setting, "texture_upscale")) rt_tex_upscale = atoi(v) >= 4 ? 4 : atoi(v) >= 2 ? 2 : 0, rt_tex_reload = 1;
    else if (!strcmp(it->setting, "hdr_paper_white")) rt_hdr_paper = (float)atof(v);
    else if (!strcmp(it->setting, "hdr_peak")) rt_hdr_peak = (float)atof(v); /* ("auto": 0, the screen's) */
    else if (!strcmp(it->setting, "sharpen")) rt_post_sharpen = (float)atof(v);
    else if (!strcmp(it->setting, "bloom")) rt_post_bloom = (float)atof(v);
    else if (!strcmp(it->setting, "vibrance")) rt_post_vibrance = (float)atof(v);
    else if (!strcmp(it->setting, "background_mute")) { if (!atoi(v)) rt_apu_set_muted(0); } /* (display.c mutes on the next switch away) */
    else changed_restart = 1;
}

void rt_overlay_toggle(void) { open_ = !open_; }

void rt_overlay_key(int key) {
    if (!open_) return;
    tabs_init();
    int m = tab_n[tab];
    if (!m && rt_overlay_page() == 2) { /* the Mayhem Moments: a photograph picked, four a row */
        int nm = rt_mm_count(), s = scroll < nm ? scroll : 0;
        if (key == RT_OV_LEFT && s > 0) s--;
        else if (key == RT_OV_RIGHT && s + 1 < nm) s++;
        else if (key == RT_OV_UP && s >= 4) s -= 4;
        else if (key == RT_OV_DOWN && s + 4 < nm) s += 4;
        else if (key == RT_OV_TAB_PREV) tab = (tab + ntabs - 1) % ntabs, sel = 0, s = 0;
        else if (key == RT_OV_TAB_NEXT) tab = (tab + 1) % ntabs, sel = 0, s = 0;
        else if (key == RT_OV_BACK) open_ = 0;
        scroll = s;
        return;
    }
    if (!m) { /* the achievements' tab: scrolled, or another tab */
        if (key == RT_OV_UP && scroll > 0) scroll--;
        else if (key == RT_OV_DOWN && scroll < rt_ach_count() - 1) scroll++;
        else if (key == RT_OV_TAB_PREV) tab = (tab + ntabs - 1) % ntabs, sel = 0, scroll = 0;
        else if (key == RT_OV_TAB_NEXT) tab = (tab + 1) % ntabs, sel = 0, scroll = 0;
        else if (key == RT_OV_BACK) open_ = 0;
        return;
    }
    const OvItem *it = at(sel);
    int n = nvalues(it), c = current(it);
    switch (key) {
    case RT_OV_UP: sel = (sel + m - 1) % m; break;
    case RT_OV_DOWN: sel = (sel + 1) % m; break;
    case RT_OV_TAB_PREV: tab = (tab + ntabs - 1) % ntabs, sel = 0; break;
    case RT_OV_TAB_NEXT: tab = (tab + 1) % ntabs, sel = 0; break;
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
    static int lt_was, rt_was;
    int lt = analog[6] > 128, rt = analog[7] > 128; /* the triggers: the tabs */
    if (lt && !lt_was) rt_overlay_key(RT_OV_TAB_PREV);
    if (rt && !rt_was) rt_overlay_key(RT_OV_TAB_NEXT);
    lt_was = lt, rt_was = rt;
    if ((down & 0x1) || (stick == 1 && stick_was != 1)) rt_overlay_key(RT_OV_UP);
    if ((down & 0x2) || (stick == 2 && stick_was != 2)) rt_overlay_key(RT_OV_DOWN);
    if ((down & 0x4) || (stick == 3 && stick_was != 3)) rt_overlay_key(RT_OV_LEFT);
    if ((down & 0x8) || (stick == 4 && stick_was != 4)) rt_overlay_key(RT_OV_RIGHT);
    if (a && !a_was) rt_overlay_key(RT_OV_OK);
    if (b && !b_was) rt_overlay_key(RT_OV_BACK);
    a_was = a, b_was = b, stick_was = stick, was = buttons;
    return 1;
}
