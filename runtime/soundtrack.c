/* Custom soundtracks from a folder on the PC (forza.ini: music, default
 * the "music" folder beside the game's run folder). Each subfolder is a
 * soundtrack named after it, loose files make one called "PC Music". At
 * start, songs not converted yet are turned into WMA the way the Xbox
 * dashboard rips them (WMA v2, 128 kbps, 44.1 kHz, stereo) with ffmpeg
 * (forza.ini: ffmpeg), into the hard disk where the dashboard keeps them,
 * E:\TDATA\FFFE0000\MUSIC\<soundtrack id>\<song id>.wma (both hex), and
 * the dashboard's index of them, ST.DB, is written; Forza finds them
 * through XAPI's soundtrack calls and decodes them itself. Converted songs
 * are kept (index.txt beside ST.DB), so later starts cost nothing.
 *
 * ST.DB, as xboxdevwiki's "Soundtracks" and stdbtool have it: a 512-byte
 * header, 100 soundtrack slots of 512 bytes from 0x200, then song groups of
 * 512 bytes from 0xCA00, six songs each; names in UTF-16. */
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#ifdef _WIN32
#include <direct.h>
#define mkdir(p) _mkdir(p)
#else
#define mkdir(p) mkdir(p, 0755)
#endif

#include "rt.h"

#define MAX_TRACKS 100
#define MAX_SONGS 500 /* per soundtrack, as the dashboard allows */

typedef struct {
    char src[512], name[64];
    char conv[512]; /* the file ffmpeg reads, when src cannot be given to it (a copy with an ASCII name) */
    long long size, mtime;
    uint32_t id, ms;
} Song;

typedef struct {
    char name[64];
    Song *songs;
    int n, cap;
} Track;

static Track tracks[MAX_TRACKS];
static int ntracks;

static int is_audio(const char *name) {
    const char *dot = strrchr(name, '.');
    if (!dot) return 0;
    static const char *ext[] = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma", ".opus"};
    for (unsigned i = 0; i < sizeof ext / sizeof ext[0]; i++)
        if (!strcasecmp(dot, ext[i])) return 1;
    return 0;
}

/* A name for the Xbox's 32 characters: "00 - Artist - Title.wma" shows
 * as "Title", "Artist - unknown album" as "Artist". */
static void tidy(char *out, size_t n, const char *in, int song) {
    char t[512];
    snprintf(t, sizeof t, "%s", in);
    char *dot = song ? strrchr(t, '.') : NULL;
    if (dot) *dot = 0;
    char *p = t;
    if (song) {
        while (*p >= '0' && *p <= '9') p++;
        if (p != t && !strncmp(p, " - ", 3)) p += 3; else p = t; /* a leading track number */
        char *last = NULL;
        for (char *q = strstr(p, " - "); q; q = strstr(q + 3, " - ")) last = q;
        if (last && last[3]) p = last + 3;
    } else {
        char *u = strstr(t, " - unknown album");
        if (u) *u = 0;
    }
    snprintf(out, n, "%s", p);
}

static void add_song(Track *t, const char *path, const char *file) {
    if (t->n >= MAX_SONGS) return;
    struct stat st = {0};
    if (path && stat(path, &st) != 0) return; /* NULL: the caller fills it in */
    if (t->n == t->cap) t->cap = t->cap ? t->cap * 2 : 16, t->songs = realloc(t->songs, (size_t)t->cap * sizeof *t->songs);
    Song *s = &t->songs[t->n++];
    memset(s, 0, sizeof *s);
    snprintf(s->src, sizeof s->src, "%s", path);
    tidy(s->name, sizeof s->name, file, 1);
    s->size = st.st_size, s->mtime = st.st_mtime;
}

static int cmp_song(const void *a, const void *b) { return strcasecmp(((const Song *)a)->name, ((const Song *)b)->name); }

#ifdef _WIN32
#include <windows.h>

/* A file name as the Xbox can show it: ASCII, full-width forms (U+FF1F and
 * the like) as their ASCII twins, anything else as '?'. */
static void ascii_name(char *out, size_t n, const wchar_t *w) {
    size_t k = 0;
    for (; *w && k + 1 < n; w++) {
        wchar_t c = *w;
        if (c >= 0xFF01 && c <= 0xFF5E) c = (wchar_t)(c - 0xFEE0);
        out[k++] = c < 128 ? (char)c : '?';
    }
    out[k] = 0;
}

/* The path the narrow file calls and ffmpeg's command line can take: the
 * short (8.3) name, which is ASCII, when the long one is not. */
static int narrow_path(char *out, size_t n, const wchar_t *w) {
    wchar_t sh[MAX_PATH];
    const wchar_t *use = w;
    for (const wchar_t *c = w; *c; c++)
        if (*c >= 128) {
            if (GetShortPathNameW(w, sh, MAX_PATH)) use = sh;
            break;
        }
    return WideCharToMultiByte(CP_ACP, 0, use, -1, out, (int)n, NULL, NULL) > 0 && !strchr(out, '?');
}

/* The folder through Windows' Unicode calls: songs with names outside the
 * ANSI code page were not seen at all through readdir. */
static void scan_w(const wchar_t *dir, const char *name, int depth) {
    wchar_t pat[MAX_PATH];
    _snwprintf(pat, MAX_PATH, L"%ls\\*", dir);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    Track *loose = NULL;
    do {
        if (fd.cFileName[0] == L'.') continue;
        wchar_t full[MAX_PATH];
        _snwprintf(full, MAX_PATH, L"%ls\\%ls", dir, fd.cFileName);
        char shown[256], path[512];
        ascii_name(shown, sizeof shown, fd.cFileName);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            if (depth == 0) {
                char tn[64];
                tidy(tn, sizeof tn, shown, 0);
                scan_w(full, tn, 1);
            }
        } else if (is_audio(shown)) {
            /* No ASCII path (8.3 names are often off): converted from a copy
             * with one, the cache still keyed by the name as shown. */
            int direct = narrow_path(path, sizeof path, full);
            if (!direct) {
                char dirn[512];
                WideCharToMultiByte(CP_ACP, 0, dir, -1, dirn, sizeof dirn, NULL, NULL);
                snprintf(path, sizeof path, "%s\\%s", dirn, shown);
            }
            if (!loose) {
                if (ntracks == MAX_TRACKS) break;
                loose = &tracks[ntracks++];
                snprintf(loose->name, sizeof loose->name, "%s", name);
            }
            int before = loose->n;
            add_song(loose, direct ? path : NULL, shown);
            if (loose->n > before && !direct) {
                Song *sg = &loose->songs[loose->n - 1];
                snprintf(sg->src, sizeof sg->src, "%s", path);
                sg->size = (long long)fd.nFileSizeHigh << 32 | fd.nFileSizeLow;
                sg->mtime = (long long)(((unsigned long long)fd.ftLastWriteTime.dwHighDateTime << 32 | fd.ftLastWriteTime.dwLowDateTime) / 10000000ull);
                wchar_t tmpw[MAX_PATH], copyw[MAX_PATH];
                GetTempPathW(MAX_PATH, tmpw);
                const wchar_t *ext = wcsrchr(fd.cFileName, L'.');
                _snwprintf(copyw, MAX_PATH, L"%lsxbrt_song_%d%ls", tmpw, loose->n, ext ? ext : L"");
                if (CopyFileW(full, copyw, FALSE)) WideCharToMultiByte(CP_ACP, 0, copyw, -1, sg->conv, sizeof sg->conv, NULL, NULL);
                else loose->n--;
            }
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    if (loose) qsort(loose->songs, (size_t)loose->n, sizeof *loose->songs, cmp_song);
}

static void scan(const char *dir, const char *name, int depth) {
    wchar_t w[MAX_PATH];
    if (MultiByteToWideChar(CP_ACP, 0, dir, -1, w, MAX_PATH)) scan_w(w, name, depth);
}
#else
static void scan(const char *dir, const char *name, int depth) {
    DIR *d = opendir(dir);
    if (!d) return;
    Track *loose = NULL;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char path[512];
        snprintf(path, sizeof path, "%s/%s", dir, e->d_name);
        struct stat st;
        if (stat(path, &st) != 0) continue;
        if (S_ISDIR(st.st_mode)) {
            char tn[64];
            tidy(tn, sizeof tn, e->d_name, 0);
            if (depth == 0) scan(path, tn, 1);
        } else if (is_audio(e->d_name)) {
            if (!loose) {
                if (ntracks == MAX_TRACKS) break;
                loose = &tracks[ntracks++];
                snprintf(loose->name, sizeof loose->name, "%s", name);
            }
            add_song(loose, path, e->d_name);
        }
    }
    closedir(d);
    if (loose) qsort(loose->songs, (size_t)loose->n, sizeof *loose->songs, cmp_song);
}
#endif

/* "Duration: 00:03:21.45" in ffmpeg's report, in milliseconds. */
static uint32_t duration_ms(const char *report) {
    const char *p = strstr(report, "Duration: ");
    int h, m;
    double s;
    if (!p || sscanf(p + 10, "%d:%d:%lf", &h, &m, &s) != 3) return 0;
    return (uint32_t)((h * 3600 + m * 60 + s) * 1000);
}

static void put_utf16(uint8_t *dst, const char *s, int chars) {
    for (int i = 0; i < chars - 1 && s[i]; i++) dst[2 * i] = (uint8_t)s[i], dst[2 * i + 1] = 0; /* names as ASCII */
}

static void wr32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v, p[1] = (uint8_t)(v >> 8), p[2] = (uint8_t)(v >> 16), p[3] = (uint8_t)(v >> 24); }

void rt_soundtracks_init(void) {
    const char *music = getenv("XBRT_MUSIC");
    if (!music || !*music) return;
    mkdir(music); /* there to be found and filled */
    scan(music, "PC Music", 0); /* none: an empty ST.DB, so songs taken out are gone */
    const char *hdd = getenv("XBRT_HDD") ? getenv("XBRT_HDD") : "hdd";
    const char *ff = getenv("XBRT_FFMPEG") && *getenv("XBRT_FFMPEG") ? getenv("XBRT_FFMPEG") : "ffmpeg";
    char root[512], path[1024];
    snprintf(root, sizeof root, "%s/Partition1/TDATA/FFFE0000/MUSIC", hdd);
    snprintf(path, sizeof path, "%s/Partition1/TDATA", hdd), mkdir(path);
    snprintf(path, sizeof path, "%s/Partition1/TDATA/FFFE0000", hdd), mkdir(path);
    mkdir(root);

    /* What was converted before: source, size, time -> song id, length. */
    typedef struct {
        char src[512];
        long long size, mtime;
        uint32_t track, id, ms;
    } Known;
    Known *known = NULL;
    int nknown = 0, capknown = 0;
    uint32_t next_id = 1;
    snprintf(path, sizeof path, "%s/index.txt", root);
    FILE *f = fopen(path, "r");
    char line[1024];
    while (f && fgets(line, sizeof line, f)) {
        Known k;
        if (sscanf(line, "%lld|%lld|%u|%u|%u|%511[^\n]", &k.size, &k.mtime, &k.track, &k.id, &k.ms, k.src) != 6) continue;
        if (nknown == capknown) capknown = capknown ? capknown * 2 : 64, known = realloc(known, (size_t)capknown * sizeof *known);
        known[nknown++] = k;
        if (k.id >= next_id) next_id = k.id + 1;
    }
    if (f) fclose(f);

    int converted = 0;
    for (int t = 0; t < ntracks; t++) {
        char dir[600];
        snprintf(dir, sizeof dir, "%s/%04x", root, t);
        mkdir(dir);
        for (int i = 0; i < tracks[t].n; i++) {
            Song *s = &tracks[t].songs[i];
            Known *k = NULL;
            for (int j = 0; j < nknown && !k; j++)
                if (!strcmp(known[j].src, s->src) && known[j].size == s->size && known[j].mtime == s->mtime && known[j].track == (uint32_t)t) k = &known[j];
            char wma[700];
            if (k) {
                snprintf(wma, sizeof wma, "%s/%08x.wma", dir, k->id);
                struct stat st;
                if (stat(wma, &st) == 0) {
                    s->id = k->id, s->ms = k->ms;
                    continue;
                }
            }
            s->id = next_id++;
            snprintf(wma, sizeof wma, "%s/%08x.wma", dir, s->id);
            if (!converted++) fprintf(stderr, "xbrt: converting new songs for the custom soundtracks (once)...\n");
            fprintf(stderr, "xbrt:   %s / %s\n", tracks[t].name, s->name);
            char cmd[2400], ffw[512], srcw[600], wmaw[700]; /* cmd.exe takes '/' in a program's path for a switch */
            snprintf(ffw, sizeof ffw, "%s", ff), snprintf(srcw, sizeof srcw, "%s", s->conv[0] ? s->conv : s->src), snprintf(wmaw, sizeof wmaw, "%s", wma);
#ifdef _WIN32
            for (char *c = ffw; *c; c++) if (*c == '/') *c = '\\';
            for (char *c = srcw; *c; c++) if (*c == '/') *c = '\\';
            for (char *c = wmaw; *c; c++) if (*c == '/') *c = '\\';
#endif
            snprintf(cmd, sizeof cmd, "\"\"%s\" -hide_banner -nostdin -y -i \"%s\" -vn -map_metadata -1 -c:a wmav2 -b:a 128k -ar 44100 -ac 2 \"%s\" 2>&1\"", ffw, srcw, wmaw);
            FILE *p = popen(cmd, "r");
            char report[8192] = "";
            size_t got = 0;
            while (p && got < sizeof report - 1 && fgets(report + got, (int)(sizeof report - got), p)) got = strlen(report);
            int rc = p ? pclose(p) : -1;
            if (s->conv[0]) remove(s->conv);
            struct stat st;
            if (rc != 0 || stat(wma, &st) != 0 || st.st_size == 0) {
                static int said; /* ffmpeg's own words, the first time */
                fprintf(stderr, "xbrt:   could not convert it (is ffmpeg installed? forza.ini: ffmpeg)\n%s", said ? "" : report);
                said = 1;
                remove(wma);
                s->id = 0;
                continue;
            }
            s->ms = duration_ms(report);
            if (nknown == capknown) capknown = capknown ? capknown * 2 : 64, known = realloc(known, (size_t)capknown * sizeof *known);
            Known nk = {"", s->size, s->mtime, (uint32_t)t, s->id, s->ms};
            snprintf(nk.src, sizeof nk.src, "%s", s->src);
            known[nknown++] = nk;
        }
    }

    /* The index of what is converted, for the next start. */
    f = fopen(path, "w");
    for (int j = 0; f && j < nknown; j++)
        fprintf(f, "%lld|%lld|%u|%u|%u|%s\n", known[j].size, known[j].mtime, known[j].track, known[j].id, known[j].ms, known[j].src);
    if (f) fclose(f);
    free(known);

    /* ST.DB */
    int ngroups_total = 0;
    for (int t = 0; t < ntracks; t++) ngroups_total += (tracks[t].n + 5) / 6;
    size_t size = 0xCA00 + (size_t)ngroups_total * 0x200;
    uint8_t *db = calloc(1, size);
    wr32(db, 1);
    wr32(db + 4, (uint32_t)ntracks);
    wr32(db + 8, (uint32_t)ntracks);
    uint32_t group = 0, songs_total = 0;
    for (int t = 0; t < ntracks; t++) {
        wr32(db + 0xC + 4 * t, (uint32_t)t);
        uint8_t *st = db + 0x200 + 0x200 * t;
        wr32(st, 0x00021371), wr32(st + 4, (uint32_t)t);
        uint32_t total = 0;
        int n = 0;
        uint8_t *g = NULL;
        for (int i = 0; i < tracks[t].n; i++) {
            Song *s = &tracks[t].songs[i];
            if (!s->id) continue;
            if (n % 6 == 0) {
                if (n / 6 >= 84) break;
                g = db + 0xCA00 + 0x200 * group;
                wr32(g, 0x00031073), wr32(g + 4, (uint32_t)t), wr32(g + 8, group), wr32(g + 12, 1);
                wr32(st + 0xC + 4 * (n / 6), group);
                group++;
            }
            wr32(g + 0x10 + 4 * (n % 6), s->id);
            wr32(g + 0x28 + 4 * (n % 6), s->ms);
            put_utf16(g + 0x40 + 64 * (n % 6), s->name, 32);
            total += s->ms, n++, songs_total++;
        }
        wr32(st + 8, (uint32_t)n);
        wr32(st + 0x15C, total);
        put_utf16(st + 0x160, tracks[t].name, 32);
    }
    wr32(db + 0x19C, next_id);
    snprintf(path, sizeof path, "%s/ST.DB", root);
    f = fopen(path, "wb");
    if (f) fwrite(db, 1, 0xCA00 + (size_t)group * 0x200, f), fclose(f);
    free(db);
    fprintf(stderr, "xbrt: custom soundtracks: %d with %u songs\n", ntracks, songs_total);
}
