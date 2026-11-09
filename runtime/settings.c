/* The player's settings: forza.ini in the working folder (run\ for the
 * launchers), one "name = value" a line, '#' or ';' starting a comment.
 * Each setting stands for one of the runtime's XBRT_* switches, which the
 * code reads with getenv: a setting fills its switch unless the
 * environment already sets it, so test runs can still override any of
 * them. A missing file is written out with the defaults. rt_settings_set
 * changes one and saves the file (the overlay menu, display.c); most take
 * effect at the next start. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"

/* forza.ini, or the file XBRT_SETTINGS names (a launcher with settings of its own: the graphics test) */
#define SETTINGS_FILE (getenv("XBRT_SETTINGS") && *getenv("XBRT_SETTINGS") ? getenv("XBRT_SETTINGS") : "forza.ini")

static RtSetting settings[] = {
    {"fps", "XBRT_FPS", "60", "Frame rate: 30 or 60 (the game runs its physics once a frame, so no higher)"},
    {"scale", "XBRT_GL_SCALE", "4", "Render scale over the Xbox's 640x480: 1 to 6 (2 = 1280x960, 3 = 1920x1440, 4 = 2560x1920, 5 = 3200x2400, 6 = 3840x2880)"},
    {"widescreen", "XBRT_WIDESCREEN", "0", "16:9 picture: 1 on, 0 off (4:3). Forza draws a wider view itself"},
    {"fullscreen", "XBRT_FULLSCREEN", "0", "Borderless fullscreen: 1 on, 0 off (Alt+Enter or F11 switches while playing)"},
    {"window", "XBRT_WINDOW_SIZE", "auto", "Window size in pixels, as 1280x960, or auto (twice the Xbox picture, fitted to the screen)"},
    {"antialiasing", "XBRT_AA", "fxaa", "Edge smoothing: fxaa or off. A higher scale than the window also smooths edges"},
    {"anisotropic", "XBRT_GL_ANISO", "16", "Texture sharpness at angles: 1 (off) to 16"},
    {"texture_upscale", "XBRT_TEX_UPSCALE", "2", "Textures drawn larger as they load (sharper close up, no cost a frame): 2 or 4 times, 0 off (4x up to 512 a side, larger ones 2x)"},
    {"hdr", "XBRT_HDR", "0", "HDR output: 1 on, 0 off (needs Use HDR on in Windows' display settings; a restart)"},
    {"hdr_paper_white", "XBRT_HDR_PAPER", "200", "HDR: how bright white is, in nits (Windows' own SDR content brightness is about 80 to 480)"},
    {"hdr_peak", "XBRT_HDR_PEAK", "auto", "HDR: the brightest highlights (sky, sun, lamps) in nits, or auto (the screen's peak)"},
    {"texture_pack", "XBRT_TEX_PACK_ON", "1", "The HD texture pack (the mods folder's textures, tools/texpack.py): 1 on, 0 off"},
    {"screenshot_format", "XBRT_SCREENSHOT_FORMAT", "png", "F12 screenshots as png (made by ffmpeg in the background, a third of the size) or bmp"},
    {"skip_intro", "XBRT_SKIP_INTRO", "1", "The intro video at the start skipped (A pressed for you): 1 on, 0 off"},
    {"fast_loading", "XBRT_FAST_LOADING", "1", "Races load without the game's least time on the loading screen (1 to 3 s a load): 1 on, 0 off"},
    {"show_fps", "XBRT_SHOW_FPS", "0", "The frame rate in the top left corner: 1 on, 0 off"},
    {"soft_shadows", "XBRT_SOFT_SHADOWS", "1", "Shadows' edges smoothed over a few texels of the shadow map, not stepped: 1 on, 0 off"},
    {"sharpen", "XBRT_SHARPEN", "0.5", "Sharpening of the shown picture (contrast-adaptive): 0 off to 1"},
    {"bloom", "XBRT_BLOOM", "0.3", "Glow round bright light (sky, sun on paint, lamps): 0 off to 1"},
    {"vibrance", "XBRT_VIBRANCE", "0.25", "More colour in dull tones (saturated ones are left): 0 off to 1"},
    {"brightness", "XBRT_BRIGHTNESS", "0.7", "How much of Forza's exposure (its gamma ramp) the picture gets: 0 none to 1 as on the Xbox"},
    {"zone_lead", "XBRT_ZONE_LEAD", "3", "Track zones ahead of the car kept loaded: 1 (as on the Xbox, scenery appears in view) to 8"},
    {"vsync", "XBRT_VSYNC", "1", "Wait for the monitor's refresh when showing a frame (no tearing): 1 on, 0 off"},
    {"volume", "XBRT_VOLUME", "0.7", "Sound volume: 0 to 1"},
    {"background_mute", "XBRT_BACKGROUND_MUTE", "1", "Silent while the window is not in front: 1 on, 0 off"},
    {"spotify", "XBRT_SPOTIFY", "0", "Spotify: the song playing shown when it changes, and controls (hold Back + the D-pad; keys M , . - = /): 1 on, 0 off. Signs in through the browser once"},
    {"spotify_client_id", "XBRT_SPOTIFY_ID", "", "Spotify: the Client ID of your app on developer.spotify.com (its redirect URI: http://127.0.0.1:8888/callback)"},
    {"spotify_popup", "XBRT_SPOTIFY_POPUP", "1", "Spotify: the song's name for a few seconds when a new one starts: 1 on, 0 off"},
    {"music", "XBRT_MUSIC", "music", "Folder of your own songs for Forza's custom soundtracks: one subfolder per soundtrack (mp3, flac, wav, ogg, m4a, wma)"},
    {"mods", "XBRT_MODS", "mods", "Folder of mods: a file there at the same path as on the disc (media\\cabs\\car_nissan240sx.cab) is read instead of the disc's; a .ca2 archive there passes the installer's check and is installed to the cache"},
    {"ffmpeg", "XBRT_FFMPEG", "ffmpeg", "ffmpeg.exe, which converts the songs once (and records clips); the full path if it is not on the PATH"},
};
#define NSETTINGS (int)(sizeof settings / sizeof settings[0])

static char values[NSETTINGS][512]; /* paths, too */

static void put_env(const char *name, const char *value) {
    static char buf[NSETTINGS][600]; /* putenv keeps the string */
    for (int i = 0; i < NSETTINGS; i++)
        if (!strcmp(settings[i].env, name)) {
            snprintf(buf[i], sizeof buf[i], "%.31s=%.511s", name, value);
            putenv(buf[i]);
            return;
        }
}

static void trim(char *s) {
    char *e = s + strlen(s);
    while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) *--e = 0;
    char *b = s;
    while (*b == ' ' || *b == '\t') b++;
    memmove(s, b, strlen(b) + 1);
}

int rt_settings_count(void) { return NSETTINGS; }
const RtSetting *rt_setting(int i) { return i >= 0 && i < NSETTINGS ? &settings[i] : NULL; }

const char *rt_settings_get(const char *name) {
    for (int i = 0; i < NSETTINGS; i++)
        if (!strcmp(settings[i].name, name)) return values[i];
    return NULL;
}

static void save(void) {
    FILE *f = fopen(SETTINGS_FILE, "w");
    if (!f) return;
    fprintf(f, "# Forza Motorsport PC port settings. Most take effect the next time the game starts.\n"
               "# In the game, F1 opens the settings overlay.\n");
    for (int i = 0; i < NSETTINGS; i++) fprintf(f, "\n# %s\n%s = %s\n", settings[i].help, settings[i].name, values[i]);
    fclose(f);
}

void rt_settings_set(const char *name, const char *value) {
    for (int i = 0; i < NSETTINGS; i++)
        if (!strcmp(settings[i].name, name)) {
            snprintf(values[i], sizeof values[i], "%s", value);
            save();
            return;
        }
}

void rt_settings_load(void) {
    for (int i = 0; i < NSETTINGS; i++) snprintf(values[i], sizeof values[i], "%s", settings[i].def);
    FILE *f = fopen(SETTINGS_FILE, "r");
    if (f) {
        char line[1024];
        while (fgets(line, sizeof line, f)) {
            char *c = strpbrk(line, "#;");
            if (c) *c = 0;
            char *eq = strchr(line, '=');
            if (!eq) continue;
            *eq = 0;
            char *k = line, *v = eq + 1;
            trim(k), trim(v);
            for (int i = 0; i < NSETTINGS; i++)
                if (!strcmp(settings[i].name, k)) snprintf(values[i], sizeof values[i], "%s", v);
        }
        fclose(f);
    } else {
        save();
    }
    for (int i = 0; i < NSETTINGS; i++) {
        const char *cur = getenv(settings[i].env);
        if (cur && *cur) continue; /* the environment wins */
        if (!strcmp(settings[i].name, "window") && !strcmp(values[i], "auto")) continue;
        put_env(settings[i].env, values[i]);
    }
}
