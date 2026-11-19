/* Spotify (the user's, 9 Nov: "integrate spotify api for the game"): the song playing in the player's Spotify,
 * shown for a few seconds when it changes, and play/pause, next, previous and volume from the game.
 *
 * forza.ini: spotify = 1 turns it on (F1's Audio tab too). Two ways to reach it (spotify_mode):
 *   desktop (the default): the Spotify app on this PC, through Windows (its window's title, media commands, its
 *     volume in the mixer). Anyone, no sign-in, free accounts too; music playing on a phone is not seen.
 *   web: Spotify's Web API, any device, signed in: spotify_client_id is the Client ID of an app on
 *     developer.spotify.com (redirect URI http://127.0.0.1:8888/callback). Its development mode lets in only the
 *     accounts added to that app (up to 25); controls need Premium.
 * Race music (spotify_race_music, on): paused in the menus, the next song as each race starts (follow_tick).
 * Spotify plays the music itself: its terms let nothing else stream it.
 *
 * Web sign-in, once: the authorization code flow with PKCE (no client secret). The browser opens Spotify's page; it
 * comes back to a listener on 127.0.0.1:8888, the code is traded for tokens, and the refresh token is kept in
 * spotify_token.txt (in run\, beside forza.ini; delete it to sign out). Later starts sign in from it unseen.
 *
 * Controls: hold Back and press the D-pad (Up play/pause, Right next, Left previous, Down the song again; the
 * game sees no D-pad while Back is held), or on the keyboard M play/pause, . next, , previous, = and - the
 * volume, / the song again. Off in automated runs (XBRT_INPUT_LIVE / XBRT_INPUT_SCRIPT), so a test never opens
 * a browser. Everything runs on a thread of its own: the game never waits for the network. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define COBJMACROS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <bcrypt.h>
#include <shellapi.h>
#include <winhttp.h>
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <wchar.h>
#endif

#include "rt.h"

#ifdef _WIN32

#define PORT 8888
#define REDIRECT "http://127.0.0.1:8888/callback"
#define REDIRECT_ENC "http%3A%2F%2F127.0.0.1%3A8888%2Fcallback"
#define SCOPES "user-read-playback-state%20user-modify-playback-state%20user-read-currently-playing"
#define TOKEN_FILE "spotify_token.txt"

enum { CMD_TOGGLE = 1, CMD_NEXT = 2, CMD_PREV = 4, CMD_VOLUP = 8, CMD_VOLDN = 16, CMD_SHOW = 32, CMD_SIGNIN = 64 };

static CRITICAL_SECTION lock;
static int started;
static volatile int enabled;
static volatile LONG cmds;
static char client_id[80];
static char access_tok[1024], refresh_tok[1024];
static DWORD access_until; /* GetTickCount */
static char cur_id[96], cur_title[128], cur_artist[128]; /* the song (ASCII for the game's fonts), under lock */
static int cur_playing, cur_device, cur_volume = -1;
static int web; /* spotify_mode = web: the Web API, signed in; else the app on this PC */
static uint64_t card_until; /* 100 ns */
static HINTERNET session;

/* ---- text ---- */

/* UTF-8 to what the game's fonts have (ASCII 32-126): accented Latin letters to their base, quotes and dashes to
 * ASCII ones, anything else to '?' (one for a run). */
static void ascii(char *out, size_t n, const char *s) {
    static const char latin1[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYTsaaaaaaaceeeeiiiidnooooo/ouuuuyty"; /* U+00C0..U+00FF */
    static const char extA[] = "AaAaAaCcCcCcCcDdDdEeEeEeEeEeGgGgGgGgHhHhIiIiIiIiIiJjJjKkkLlLlLlLlLlNnNnNnnNnOoOo"
                               "OoOoRrRrRrSsSsSsSsTtTtTtUuUuUuUuUuUuWwYyYZzZzZzs"; /* U+0100..U+017F */
    size_t o = 0;
    const unsigned char *p = (const unsigned char *)s;
    while (*p && o + 4 < n) {
        unsigned c = *p++;
        if (c >= 0x80) { /* decode */
            int more = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
            c &= more == 3 ? 0x07 : more == 2 ? 0x0F : 0x1F;
            for (int i = 0; i < more && (*p & 0xC0) == 0x80; i++) c = c << 6 | (*p++ & 0x3F);
        }
        const char *put = NULL;
        char one[2] = {0, 0};
        if (c >= 32 && c < 127) one[0] = (char)c, put = one;
        else if (c == 0xA0 || c == 0x3000) put = " ";
        else if (c >= 0xC0 && c <= 0xFF) one[0] = latin1[c - 0xC0], put = one;
        else if (c >= 0x100 && c <= 0x17F) one[0] = extA[c - 0x100], put = one;
        else if (c == 0x2018 || c == 0x2019 || c == 0x2032) put = "'";
        else if (c == 0x201C || c == 0x201D) put = "\"";
        else if (c >= 0x2010 && c <= 0x2015) put = "-";
        else if (c == 0x2026) put = "...";
        else if (c == 0xD7) put = "x";
        else if (c < 32) put = " ";
        else put = o && out[o - 1] == '?' ? "" : "?";
        for (; *put && o + 1 < n; put++) out[o++] = *put;
    }
    out[o] = 0;
}

/* ---- JSON: just enough to read a few fields of Spotify's answers ---- */

static const char *js_ws(const char *p) {
    while (p && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++;
    return p;
}

static void put_utf8(char *out, size_t n, size_t *o, unsigned c) {
    char b[4];
    int k = 0;
    if (c < 0x80) b[k++] = (char)c;
    else if (c < 0x800) b[k++] = (char)(0xC0 | c >> 6), b[k++] = (char)(0x80 | (c & 0x3F));
    else if (c < 0x10000) b[k++] = (char)(0xE0 | c >> 12), b[k++] = (char)(0x80 | (c >> 6 & 0x3F)), b[k++] = (char)(0x80 | (c & 0x3F));
    else b[k++] = (char)(0xF0 | c >> 18), b[k++] = (char)(0x80 | (c >> 12 & 0x3F)), b[k++] = (char)(0x80 | (c >> 6 & 0x3F)), b[k++] = (char)(0x80 | (c & 0x3F));
    for (int i = 0; i < k && *o + 1 < n; i++) out[(*o)++] = b[i];
}

/* A string at p (its opening quote), decoded into out (may be NULL); the character after it, or NULL. */
static const char *js_str(const char *p, char *out, size_t n) {
    size_t o = 0;
    if (!p || *p != '"') return NULL;
    for (p++; *p && *p != '"'; p++) {
        unsigned c = (unsigned char)*p;
        if (c == '\\') {
            p++;
            if (!*p) return NULL;
            switch (*p) {
            case 'b': c = '\b'; break;
            case 'f': c = '\f'; break;
            case 'n': c = '\n'; break;
            case 'r': c = '\r'; break;
            case 't': c = '\t'; break;
            case 'u': {
                unsigned v = 0;
                for (int i = 1; i <= 4; i++) {
                    char h = p[i];
                    if (!h) return NULL;
                    v = v << 4 | (unsigned)(h <= '9' ? h - '0' : (h | 32) - 'a' + 10);
                }
                p += 4;
                if (v >= 0xD800 && v < 0xDC00 && p[1] == '\\' && p[2] == 'u') { /* a surrogate pair */
                    unsigned lo = 0;
                    for (int i = 3; i <= 6; i++) {
                        char h = p[i];
                        if (!h) return NULL;
                        lo = lo << 4 | (unsigned)(h <= '9' ? h - '0' : (h | 32) - 'a' + 10);
                    }
                    if (lo >= 0xDC00 && lo < 0xE000) v = 0x10000 + ((v - 0xD800) << 10) + (lo - 0xDC00), p += 6;
                }
                if (out) put_utf8(out, n, &o, v);
                continue;
            }
            default: c = (unsigned char)*p; break; /* \" \\ \/ */
            }
        }
        if (out && o + 1 < n) out[o++] = (char)c;
    }
    if (out && n) out[o] = 0;
    return *p == '"' ? p + 1 : NULL;
}

/* Past the value at p (whitespace first); NULL if malformed. */
static const char *js_skip(const char *p) {
    p = js_ws(p);
    if (!p || !*p) return NULL;
    if (*p == '"') return js_str(p, NULL, 0);
    if (*p == '{' || *p == '[') {
        int depth = 0;
        while (*p) {
            if (*p == '"') {
                p = js_str(p, NULL, 0);
                if (!p) return NULL;
                continue;
            }
            if (*p == '{' || *p == '[') depth++;
            else if (*p == '}' || *p == ']') {
                if (--depth == 0) return p + 1;
            }
            p++;
        }
        return NULL;
    }
    while (*p && !strchr(",}] \t\r\n", *p)) p++;
    return p;
}

/* The value at a path of keys and indexes ("item.artists.0.name") from the value at p, or NULL. */
static const char *js_find(const char *p, const char *path) {
    char seg[64];
    while (*path) {
        size_t k = strcspn(path, ".");
        if (k >= sizeof seg) return NULL;
        memcpy(seg, path, k), seg[k] = 0;
        path += k + (path[k] == '.');
        p = js_ws(p);
        if (!p) return NULL;
        if (*p == '{') {
            const char *found = NULL;
            p = js_ws(p + 1);
            while (p && *p == '"') {
                char key[64];
                p = js_ws(js_str(p, key, sizeof key));
                if (!p || *p != ':') return NULL;
                const char *v = js_ws(p + 1);
                if (!strcmp(key, seg)) {
                    found = v;
                    break;
                }
                p = js_ws(js_skip(v));
                if (p && *p == ',') p = js_ws(p + 1);
            }
            if (!found) return NULL;
            p = found;
        } else if (*p == '[') {
            int want = atoi(seg), i = 0;
            p = js_ws(p + 1);
            while (p && *p != ']' && i < want) {
                p = js_ws(js_skip(p));
                if (p && *p == ',') p = js_ws(p + 1);
                i++;
            }
            if (!p || *p == ']') return NULL;
        } else
            return NULL;
    }
    return js_ws(p);
}

static int js_get_str(const char *json, const char *path, char *out, size_t n) {
    const char *v = js_find(json, path);
    if (!v || *v != '"') return 0;
    return js_str(v, out, n) != NULL;
}

static int js_get_int(const char *json, const char *path, int def) {
    const char *v = js_find(json, path);
    return v && (*v == '-' || (*v >= '0' && *v <= '9')) ? atoi(v) : def;
}

static int js_get_bool(const char *json, const char *path) {
    const char *v = js_find(json, path);
    return v && !strncmp(v, "true", 4);
}

/* ---- HTTPS (WinHTTP) ---- */

/* A request; the answer's status (0 when it never got one), its body in out. Retry-After in *retry (seconds). */
static int https(const char *host, const char *method, const char *path, const char *headers, const char *body, char *out, int outn,
                 int *retry) {
    if (out && outn) out[0] = 0;
    if (retry) *retry = 0;
    if (!session) {
        session = WinHttpOpen(L"ForzaPC/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
        if (!session) return 0;
        WinHttpSetTimeouts(session, 5000, 5000, 8000, 8000);
    }
    wchar_t whost[128], wmethod[16], wpath[1024], wheaders[2048];
    MultiByteToWideChar(CP_UTF8, 0, host, -1, whost, 128);
    MultiByteToWideChar(CP_UTF8, 0, method, -1, wmethod, 16);
    MultiByteToWideChar(CP_UTF8, 0, path, -1, wpath, 1024);
    MultiByteToWideChar(CP_UTF8, 0, headers ? headers : "", -1, wheaders, 2048);
    int status = 0;
    HINTERNET conn = WinHttpConnect(session, whost, INTERNET_DEFAULT_HTTPS_PORT, 0);
    HINTERNET req = conn ? WinHttpOpenRequest(conn, wmethod, wpath, NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE) : NULL;
    DWORD blen = body ? (DWORD)strlen(body) : 0;
    if (req && WinHttpSendRequest(req, wheaders[0] ? wheaders : WINHTTP_NO_ADDITIONAL_HEADERS, wheaders[0] ? (DWORD)-1L : 0,
                                  body ? (LPVOID)body : WINHTTP_NO_REQUEST_DATA, blen, blen, 0) &&
        WinHttpReceiveResponse(req, NULL)) {
        DWORD code = 0, sz = sizeof code;
        if (WinHttpQueryHeaders(req, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &code, &sz,
                                WINHTTP_NO_HEADER_INDEX))
            status = (int)code;
        DWORD ra = 0;
        sz = sizeof ra;
        if (retry && WinHttpQueryHeaders(req, WINHTTP_QUERY_RETRY_AFTER | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &ra, &sz,
                                         WINHTTP_NO_HEADER_INDEX))
            *retry = (int)ra;
        int got = 0;
        for (;;) {
            DWORD avail = 0, rd = 0;
            if (!WinHttpQueryDataAvailable(req, &avail) || !avail) break;
            char tmp[4096];
            if (avail > sizeof tmp) avail = sizeof tmp;
            if (!WinHttpReadData(req, tmp, avail, &rd) || !rd) break;
            if (out && got + 1 < outn) {
                int take = (int)rd < outn - 1 - got ? (int)rd : outn - 1 - got;
                memcpy(out + got, tmp, (size_t)take);
                got += take;
            }
        }
        if (out && outn) out[got] = 0;
    }
    if (req) WinHttpCloseHandle(req);
    if (conn) WinHttpCloseHandle(conn);
    return status;
}

/* ---- tokens ---- */

static void say(const char *m) {
    char t[64];
    snprintf(t, sizeof t, "Spotify: %s", m);
    rt_toast(t);
    fprintf(stderr, "xbrt: spotify: %s\n", m);
}

static void token_save(void) {
    FILE *f = fopen(TOKEN_FILE, "w");
    if (f) fprintf(f, "%s\n", refresh_tok), fclose(f);
}

static void token_load(void) {
    FILE *f = fopen(TOKEN_FILE, "r");
    if (!f) return;
    if (fgets(refresh_tok, sizeof refresh_tok, f)) refresh_tok[strcspn(refresh_tok, "\r\n")] = 0;
    fclose(f);
}

/* Takes access_token (and a new refresh_token, when Spotify sends one) from a token answer. */
static int token_take(const char *json) {
    char a[1024], r[1024];
    if (!js_get_str(json, "access_token", a, sizeof a)) return 0;
    int exp = js_get_int(json, "expires_in", 3600);
    snprintf(access_tok, sizeof access_tok, "%s", a);
    access_until = GetTickCount() + (DWORD)(exp > 120 ? exp - 60 : exp) * 1000u;
    if (js_get_str(json, "refresh_token", r, sizeof r) && strcmp(r, refresh_tok)) {
        snprintf(refresh_tok, sizeof refresh_tok, "%s", r);
        token_save();
    }
    return 1;
}

/* A new access token from the refresh token: 1 done, 0 failed for now, -1 the sign-in is no longer good. */
static int token_refresh(void) {
    char body[1400], out[4096];
    snprintf(body, sizeof body, "grant_type=refresh_token&refresh_token=%s&client_id=%s", refresh_tok, client_id);
    int st = https("accounts.spotify.com", "POST", "/api/token", "Content-Type: application/x-www-form-urlencoded\r\n", body, out, sizeof out, NULL);
    if (st == 200 && token_take(out)) return 1;
    fprintf(stderr, "xbrt: spotify: token refresh: %d %.200s\n", st, out);
    return st == 400 || st == 401 ? -1 : 0;
}

/* ---- sign-in ---- */

static void b64url(const unsigned char *in, int n, char *out) {
    static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    int o = 0;
    for (int i = 0; i < n; i += 3) {
        unsigned v = (unsigned)in[i] << 16 | (i + 1 < n ? (unsigned)in[i + 1] << 8 : 0) | (i + 2 < n ? in[i + 2] : 0);
        out[o++] = t[v >> 18 & 63], out[o++] = t[v >> 12 & 63];
        if (i + 1 < n) out[o++] = t[v >> 6 & 63];
        if (i + 2 < n) out[o++] = t[v & 63];
    }
    out[o] = 0;
}

static int sha256(const void *data, unsigned n, unsigned char out[32]) {
    BCRYPT_ALG_HANDLE alg;
    BCRYPT_HASH_HANDLE h;
    int ok = 0;
    if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, NULL, 0))) return 0;
    if (BCRYPT_SUCCESS(BCryptCreateHash(alg, &h, NULL, 0, NULL, 0, 0))) {
        ok = BCRYPT_SUCCESS(BCryptHashData(h, (PUCHAR)data, n, 0)) && BCRYPT_SUCCESS(BCryptFinishHash(h, out, 32, 0));
        BCryptDestroyHash(h);
    }
    BCryptCloseAlgorithmProvider(alg, 0);
    return ok;
}

/* The value of a query parameter in a request line ("GET /callback?code=..&state=.. HTTP/1.1"). */
static int query_param(const char *line, const char *name, char *out, size_t n) {
    const char *q = strchr(line, '?');
    size_t k = strlen(name);
    while (q) {
        q++;
        if (!strncmp(q, name, k) && q[k] == '=') {
            q += k + 1;
            size_t o = 0;
            while (*q && *q != '&' && *q != ' ' && o + 1 < n) out[o++] = *q++;
            out[o] = 0;
            return 1;
        }
        q = strpbrk(q, "& ");
        if (q && *q == ' ') break;
    }
    return 0;
}

static void reply(SOCKET c, int ok, const char *msg) {
    char page[1024], all[1400];
    snprintf(page, sizeof page,
             "<!doctype html><html><head><meta charset=utf-8><title>Forza: Spotify</title></head>"
             "<body style=\"font-family:sans-serif;background:#121212;color:#eee;text-align:center;padding-top:80px\">"
             "<h2 style=\"color:%s\">%s</h2><p>You can close this tab and go back to the game.</p></body></html>",
             ok ? "#1db954" : "#e05050", msg);
    snprintf(all, sizeof all, "HTTP/1.1 %s\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: %u\r\nConnection: close\r\n\r\n%s",
             ok ? "200 OK" : "400 Bad Request", (unsigned)strlen(page), page);
    send(c, all, (int)strlen(all), 0);
}

/* The browser sign-in: 1 signed in. Waits for the browser for up to 5 minutes. */
static int sign_in(void) {
    static int wsa;
    if (!wsa) {
        WSADATA d;
        if (WSAStartup(MAKEWORD(2, 2), &d)) return 0;
        wsa = 1;
    }
    unsigned char rnd[48], hash[32];
    char verifier[80], challenge[64], state[24];
    if (!BCRYPT_SUCCESS(BCryptGenRandom(NULL, rnd, sizeof rnd, BCRYPT_USE_SYSTEM_PREFERRED_RNG))) return 0;
    b64url(rnd, 48, verifier); /* 64 characters of [A-Za-z0-9-_] */
    if (!sha256(verifier, (unsigned)strlen(verifier), hash)) return 0;
    b64url(hash, 32, challenge);
    b64url(rnd + 36, 12, state);

    SOCKET ls = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (ls == INVALID_SOCKET) return 0;
    BOOL excl = TRUE;
    setsockopt(ls, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, (const char *)&excl, sizeof excl);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET, a.sin_port = htons(PORT), a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(ls, (struct sockaddr *)&a, sizeof a) || listen(ls, 4)) {
        closesocket(ls);
        say("port 8888 is busy, can't sign in");
        return 0;
    }
    char url[1024];
    snprintf(url, sizeof url,
             "https://accounts.spotify.com/authorize?response_type=code&client_id=%s&scope=%s&redirect_uri=%s"
             "&code_challenge_method=S256&code_challenge=%s&state=%s",
             client_id, SCOPES, REDIRECT_ENC, challenge, state);
    ShellExecuteA(NULL, "open", url, NULL, NULL, SW_SHOWNORMAL);
    say("sign in in your browser");

    char code[1024] = "";
    DWORD until = GetTickCount() + 300000;
    while (!code[0] && enabled && (int)(until - GetTickCount()) > 0) {
        fd_set rs;
        FD_ZERO(&rs);
        FD_SET(ls, &rs);
        struct timeval tv = {1, 0};
        if (select(0, &rs, NULL, NULL, &tv) <= 0) continue;
        SOCKET c = accept(ls, NULL, NULL);
        if (c == INVALID_SOCKET) continue;
        DWORD to = 3000;
        setsockopt(c, SOL_SOCKET, SO_RCVTIMEO, (const char *)&to, sizeof to);
        char req[4096];
        int got = recv(c, req, sizeof req - 1, 0);
        req[got > 0 ? got : 0] = 0;
        req[strcspn(req, "\r\n")] = 0; /* the request line */
        char st[64] = "", err[64] = "";
        if (strncmp(req, "GET /callback", 13)) {
            static const char nf[] = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
            send(c, nf, (int)sizeof nf - 1, 0);
        } else if (query_param(req, "error", err, sizeof err)) {
            reply(c, 0, "Spotify sign-in was cancelled.");
            closesocket(c);
            break;
        } else if (!query_param(req, "state", st, sizeof st) || strcmp(st, state) || !query_param(req, "code", code, sizeof code)) {
            code[0] = 0;
            reply(c, 0, "That sign-in didn't match. Try again from the game.");
        } else
            reply(c, 1, "Signed in to Spotify.");
        closesocket(c);
    }
    closesocket(ls);
    if (!code[0]) {
        say("not signed in");
        return 0;
    }
    char body[2400], out[4096];
    snprintf(body, sizeof body, "grant_type=authorization_code&code=%s&redirect_uri=%s&client_id=%s&code_verifier=%s", code, REDIRECT_ENC,
             client_id, verifier);
    int status = https("accounts.spotify.com", "POST", "/api/token", "Content-Type: application/x-www-form-urlencoded\r\n", body, out, sizeof out, NULL);
    if (status != 200 || !token_take(out)) {
        fprintf(stderr, "xbrt: spotify: token: %d %.300s\n", status, out);
        say("sign-in failed");
        return 0;
    }
    if (!refresh_tok[0]) return 0;
    token_save();
    say("signed in");
    return 1;
}

/* ---- the Web API ---- */

static int api(const char *method, const char *path, char *out, int outn) {
    for (int attempt = 0; attempt < 2; attempt++) {
        if (!access_tok[0] || (int)(access_until - GetTickCount()) < 0) {
            int r = token_refresh();
            if (r < 0) {
                refresh_tok[0] = access_tok[0] = 0;
                remove(TOKEN_FILE);
                say("signed out, sign in again (F1, Audio)");
                return 0;
            }
            if (!r) return 0;
        }
        char hdr[1200];
        snprintf(hdr, sizeof hdr, "Authorization: Bearer %s\r\n%s", access_tok, strcmp(method, "GET") ? "Content-Length: 0\r\n" : "");
        int retry = 0;
        int st = https("api.spotify.com", method, path, hdr, NULL, out, outn, &retry);
        if (st == 401) {
            access_tok[0] = 0;
            continue;
        }
        if (st == 429) Sleep((DWORD)(retry > 0 && retry < 30 ? retry : 5) * 1000u);
        return st;
    }
    return 401;
}

/* A control's answer: what went wrong, said once. */
static int control_ok(int st) {
    if (st >= 200 && st < 300) return 1;
    if (st == 403) say("controls need Spotify Premium");
    else if (st == 404) say("start Spotify on a device first");
    else if (st) {
        char m[48];
        snprintf(m, sizeof m, "that didn't work (%d)", st);
        say(m);
    } else
        say("no connection");
    return 0;
}

/* ---- the web backend (spotify_mode = web) ---- */

static void web_poll(void) {
    static char out[65536]; /* (a track's answer lists its markets: 20 KB and more) */
    int st = api("GET", "/v1/me/player?additional_types=episode", out, sizeof out);
    if (st == 204 || (st == 200 && !out[0])) { /* no device playing */
        EnterCriticalSection(&lock);
        cur_playing = 0, cur_device = 0;
        LeaveCriticalSection(&lock);
        return;
    }
    if (st != 200) return;
    char id[96] = "", name[256] = "", artist[256] = "";
    int playing = js_get_bool(out, "is_playing");
    int vol = js_get_int(out, "device.volume_percent", -1);
    js_get_str(out, "item.id", id, sizeof id);
    js_get_str(out, "item.name", name, sizeof name);
    if (!js_get_str(out, "item.artists.0.name", artist, sizeof artist)) js_get_str(out, "item.show.name", artist, sizeof artist); /* a podcast */
    char a2[128];
    if (js_get_str(out, "item.artists.1.name", a2, sizeof a2) && strlen(artist) + strlen(a2) + 3 < sizeof artist)
        strcat(artist, ", "), strcat(artist, a2);
    EnterCriticalSection(&lock);
    int changed = id[0] && strcmp(id, cur_id);
    if (id[0]) {
        snprintf(cur_id, sizeof cur_id, "%s", id);
        ascii(cur_title, sizeof cur_title, name);
        ascii(cur_artist, sizeof cur_artist, artist);
    }
    cur_playing = playing, cur_volume = vol, cur_device = 1;
    const char *pop = rt_settings_get("spotify_popup");
    if (changed && playing && (!pop || atoi(pop))) card_until = rt_now_100ns() + 60000000; /* 6 s */
    LeaveCriticalSection(&lock);
    if (changed) fprintf(stderr, "xbrt: spotify: now playing \"%s\" by %s\n", cur_title, cur_artist);
}

static int web_play(int on) {
    char out[2048];
    return control_ok(api("PUT", on ? "/v1/me/player/play" : "/v1/me/player/pause", out, sizeof out));
}

static int web_skip(int dir) {
    char out[2048];
    return control_ok(api("POST", dir > 0 ? "/v1/me/player/next" : "/v1/me/player/previous", out, sizeof out));
}

static void web_volume(int delta) {
    char out[2048], path[96];
    int v = cur_volume < 0 ? 50 : cur_volume;
    v += delta;
    v = v < 0 ? 0 : v > 100 ? 100 : v;
    snprintf(path, sizeof path, "/v1/me/player/volume?volume_percent=%d", v);
    if (control_ok(api("PUT", path, out, sizeof out))) {
        cur_volume = v;
        char m[40];
        snprintf(m, sizeof m, "volume %d%%", v);
        say(m);
    }
}

/* ---- the desktop backend (spotify_mode = desktop, the default) ----
 * The Spotify app on this PC, through Windows: its main window's title is "Artist - Song" while a song plays and
 * "Spotify Premium" / "Spotify Free" while paused; WM_APPCOMMAND's media commands posted to it play, pause and skip
 * (as a keyboard's media keys would, but to Spotify alone); its volume is its own in the Windows mixer. No sign-in
 * and no Premium. */

static HWND sp_wnd;

static int is_spotify(DWORD pid) {
    static DWORD yes;
    if (pid && pid == yes) return 1;
    int r = 0;
    HANDLE p = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (p) {
        wchar_t path[MAX_PATH];
        DWORD n = MAX_PATH;
        if (QueryFullProcessImageNameW(p, 0, path, &n)) {
            const wchar_t *b = wcsrchr(path, L'\\');
            r = !_wcsicmp(b ? b + 1 : path, L"Spotify.exe");
        }
        CloseHandle(p);
    }
    if (r) yes = pid;
    return r;
}

typedef struct {
    HWND best;
    int score;
} FindSp;

static BOOL CALLBACK find_cb(HWND h, LPARAM lp) {
    FindSp *f = (FindSp *)lp;
    wchar_t cls[64];
    if (!GetClassNameW(h, cls, 64) || wcsncmp(cls, L"Chrome_WidgetWin_", 17)) return TRUE;
    if (GetWindow(h, GW_OWNER) || GetWindowTextLengthW(h) <= 0) return TRUE;
    DWORD pid = 0;
    GetWindowThreadProcessId(h, &pid);
    if (!is_spotify(pid)) return TRUE;
    int score = 1 + (IsWindowVisible(h) ? 2 : 0);
    if (score > f->score) f->best = h, f->score = score;
    return TRUE;
}

static HWND desk_window(void) {
    if (sp_wnd && IsWindow(sp_wnd) && GetWindowTextLengthW(sp_wnd) > 0) return sp_wnd;
    FindSp f = {NULL, 0};
    EnumWindows(find_cb, (LPARAM)&f);
    return sp_wnd = f.best;
}

static void desk_poll(void) {
    HWND w = desk_window();
    wchar_t wt[512] = L"";
    char t[1024] = "";
    if (w) GetWindowTextW(w, wt, 512), WideCharToMultiByte(CP_UTF8, 0, wt, -1, t, sizeof t, NULL, NULL);
    const char *dash = strstr(t, " - ");
    int ad = strstr(t, "Advertisement") != NULL;
    int song = w && dash && strncmp(t, "Spotify", 7) && !ad;
    EnterCriticalSection(&lock);
    int changed = song && strcmp(t, cur_id);
    if (song) {
        snprintf(cur_id, sizeof cur_id, "%.95s", t); /* (the title itself: a song's id here) */
        char artist[512];
        snprintf(artist, sizeof artist, "%.*s", (int)(dash - t), t);
        ascii(cur_artist, sizeof cur_artist, artist);
        ascii(cur_title, sizeof cur_title, dash + 3);
    }
    cur_playing = song || (w && ad), cur_device = w != NULL;
    const char *pop = rt_settings_get("spotify_popup");
    if (changed && (!pop || atoi(pop))) card_until = rt_now_100ns() + 60000000;
    LeaveCriticalSection(&lock);
    if (changed) fprintf(stderr, "xbrt: spotify: now playing \"%s\" by %s\n", cur_title, cur_artist);
}

static int desk_send(int cmd) {
    HWND w = desk_window();
    if (!w) {
        say("open the Spotify app");
        return 0;
    }
    PostMessageW(w, WM_APPCOMMAND, (WPARAM)w, MAKELPARAM(0, cmd));
    return 1;
}

static int desk_play(int on) {
    desk_poll();
    if (!cur_device) return desk_send(0);
    if (cur_playing != on) desk_send(APPCOMMAND_MEDIA_PLAY_PAUSE);
    return 1;
}

static int desk_skip(int dir) { return desk_send(dir > 0 ? APPCOMMAND_MEDIA_NEXTTRACK : APPCOMMAND_MEDIA_PREVIOUSTRACK); }

static const GUID sp_CLSID_MMDeviceEnumerator = {0xBCDE0395, 0xE52F, 0x467C, {0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E}};
static const GUID sp_IID_IMMDeviceEnumerator = {0xA95664D2, 0x9614, 0x4F35, {0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6}};
static const GUID sp_IID_IAudioSessionManager2 = {0x77AA99A0, 0x1BD6, 0x484F, {0x8B, 0xC7, 0x2C, 0x65, 0x4C, 0x9A, 0x9B, 0x6F}};
static const GUID sp_IID_IAudioSessionControl2 = {0xBFB7FF88, 0x7239, 0x4FC9, {0x8F, 0xA2, 0x07, 0xC9, 0x50, 0xBE, 0x9C, 0x6D}};
static const GUID sp_IID_ISimpleAudioVolume = {0x87CE5498, 0x68D6, 0x44E5, {0x92, 0x15, 0x6D, 0xA4, 0x7E, 0xF8, 0x83, 0xD8}};

/* Spotify's volume in the Windows mixer, moved by delta percent: the new one, or -1 (no Spotify sound yet). */
static int desk_volume(int delta) {
    IMMDeviceEnumerator *en = NULL;
    IMMDevice *dev = NULL;
    IAudioSessionManager2 *mgr = NULL;
    IAudioSessionEnumerator *se = NULL;
    float nv = -1;
    if (FAILED(CoCreateInstance(&sp_CLSID_MMDeviceEnumerator, NULL, CLSCTX_ALL, &sp_IID_IMMDeviceEnumerator, (void **)&en))) return -1;
    if (SUCCEEDED(IMMDeviceEnumerator_GetDefaultAudioEndpoint(en, eRender, eMultimedia, &dev)) &&
        SUCCEEDED(IMMDevice_Activate(dev, &sp_IID_IAudioSessionManager2, CLSCTX_ALL, NULL, (void **)&mgr)) &&
        SUCCEEDED(IAudioSessionManager2_GetSessionEnumerator(mgr, &se))) {
        int n = 0;
        IAudioSessionEnumerator_GetCount(se, &n);
        for (int i = 0; i < n; i++) {
            IAudioSessionControl *c = NULL;
            IAudioSessionControl2 *c2 = NULL;
            ISimpleAudioVolume *v = NULL;
            if (FAILED(IAudioSessionEnumerator_GetSession(se, i, &c))) continue;
            DWORD pid = 0;
            if (SUCCEEDED(IAudioSessionControl_QueryInterface(c, &sp_IID_IAudioSessionControl2, (void **)&c2))) {
                IAudioSessionControl2_GetProcessId(c2, &pid);
                if (pid && is_spotify(pid) && SUCCEEDED(IAudioSessionControl_QueryInterface(c, &sp_IID_ISimpleAudioVolume, (void **)&v))) {
                    if (nv < 0) {
                        float cur = 1;
                        ISimpleAudioVolume_GetMasterVolume(v, &cur);
                        nv = cur + (float)delta / 100.0f;
                        nv = nv < 0 ? 0 : nv > 1 ? 1 : nv;
                    }
                    ISimpleAudioVolume_SetMasterVolume(v, nv, NULL);
                    ISimpleAudioVolume_Release(v);
                }
                IAudioSessionControl2_Release(c2);
            }
            IAudioSessionControl_Release(c);
        }
    }
    if (se) IAudioSessionEnumerator_Release(se);
    if (mgr) IAudioSessionManager2_Release(mgr);
    if (dev) IMMDevice_Release(dev);
    IMMDeviceEnumerator_Release(en);
    return nv < 0 ? -1 : (int)(nv * 100 + 0.5f);
}

/* ---- either ---- */

static void be_poll(void) {
    if (web) web_poll();
    else desk_poll();
}
static int be_play(int on) { return web ? web_play(on) : desk_play(on); }
static int be_skip(int dir) { return web ? web_skip(dir) : desk_skip(dir); }
static void be_volume(int delta) {
    if (web) {
        web_volume(delta);
        return;
    }
    int v = desk_volume(delta);
    char m[40];
    if (v < 0) snprintf(m, sizeof m, "play something first");
    else snprintf(m, sizeof m, "volume %d%%", v);
    say(m);
}

static void run_commands(void) {
    LONG c = InterlockedExchange(&cmds, 0);
    if (c & CMD_SHOW) {
        EnterCriticalSection(&lock);
        if (cur_title[0]) card_until = rt_now_100ns() + 60000000;
        LeaveCriticalSection(&lock);
        if (!cur_title[0]) say("nothing playing");
    }
    if (c & CMD_TOGGLE) {
        be_poll();
        int was = cur_playing;
        if (be_play(!was)) {
            EnterCriticalSection(&lock);
            cur_playing = !was;
            if (!was && cur_title[0]) card_until = rt_now_100ns() + 60000000;
            LeaveCriticalSection(&lock);
            if (was) say("paused");
        }
    }
    if (c & CMD_NEXT) be_skip(1);
    if (c & CMD_PREV) be_skip(-1);
    if (c & CMD_VOLUP) be_volume(10);
    if (c & CMD_VOLDN) be_volume(-10);
}

/* Race music (spotify_race_music, the user's: "It'll pause when we're in the menus. Once we start another race, it'll
 * skip the song and go to the next, similar to how the music in the game works"): paused as the menus, the pause menu
 * or a race's end come up; on again on leaving the pause menu; the next song as each race starts (a restart too).
 * Only what it paused itself is played again, and nothing is said when Spotify isn't there. */
static void follow_tick(void) {
    static int st_was = -1, ours;
    static unsigned serial_was;
    const char *f = rt_settings_get("spotify_race_music");
    unsigned serial;
    int st = rt_qr_music(&serial);
    if (f && !atoi(f)) {
        st_was = st, serial_was = serial;
        return;
    }
    if (st_was < 0) serial_was = serial;
    if (st == st_was && serial == serial_was) return;
    be_poll();
    if (cur_device) {
        if (st == 1 && serial != serial_was) { /* a race started */
            fprintf(stderr, "xbrt: spotify: a race started: the next song\n");
            be_skip(1);
            Sleep(web ? 500 : 800);
            be_poll();
            if (!cur_playing) be_play(1);
            ours = 0;
        } else if (st == 1) { /* back from the pause menu */
            if (ours) be_play(1);
            ours = 0;
        } else if (st_was == 1 || st_was < 0) { /* the menus, the pause menu, the race over (or the game just started) */
            if (cur_playing && be_play(0)) ours = 1;
        }
    }
    st_was = st, serial_was = serial;
}

static void *worker(void *arg) {
    (void)arg;
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
    CoInitializeEx(NULL, COINIT_MULTITHREADED); /* (the mixer's volume) */
    if (web) token_load();
    DWORD next_poll = 0;
    int asked = 0; /* the browser opened this session: not again unless asked (F1, Audio, Spotify off and on) */
    for (;;) {
        if (!enabled) {
            Sleep(250);
            continue;
        }
        if (web && !refresh_tok[0]) {
            LONG c = InterlockedAnd(&cmds, ~CMD_SIGNIN);
            if (asked && !(c & CMD_SIGNIN)) {
                if (c & ~CMD_SIGNIN) InterlockedExchange(&cmds, 0), say("not signed in (F1, Audio, Spotify)");
                Sleep(250);
                continue;
            }
            asked = 1;
            if (!sign_in()) continue;
            next_poll = 0;
        }
        if (cmds) {
            run_commands();
            next_poll = GetTickCount() + (web ? 600 : 250); /* the change, seen soon after */
        }
        follow_tick();
        if ((int)(GetTickCount() - next_poll) >= 0) {
            be_poll();
            next_poll = GetTickCount() + (web ? (rt_display_focused() ? 3000 : 15000) : 1000);
        }
        Sleep(50);
    }
    return NULL;
}

void rt_spotify_init(void) {
    const char *on = getenv("XBRT_SPOTIFY"), *id = getenv("XBRT_SPOTIFY_ID"), *mode = getenv("XBRT_SPOTIFY_MODE");
    if ((getenv("XBRT_INPUT_LIVE") && *getenv("XBRT_INPUT_LIVE")) || (getenv("XBRT_INPUT_SCRIPT") && *getenv("XBRT_INPUT_SCRIPT"))) return; /* tests */
    web = mode && !strcmp(mode, "web");
    snprintf(client_id, sizeof client_id, "%s", id ? id : "");
    for (char *p = client_id; *p; p++)
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z'))) *p = 0; /* (hex as Spotify gives it) */
    InitializeCriticalSection(&lock);
    started = 1;
    enabled = on && atoi(on) && (!web || client_id[0]);
    if (on && atoi(on) && web && !client_id[0]) fprintf(stderr, "xbrt: spotify: web mode, but forza.ini has no spotify_client_id\n");
    fprintf(stderr, "xbrt: spotify: %s, %s\n", enabled ? "on" : "off", web ? "web (signed in)" : "desktop (the app on this PC)");
    pthread_t h;
    if (pthread_create(&h, NULL, worker, NULL) == 0) rt_host_thread("spotify", h);
}

void rt_spotify_enable(int on) {
    if (!started) return;
    if (on && web && !client_id[0]) {
        say("add spotify_client_id to forza.ini");
        return;
    }
    if (on && !enabled) InterlockedOr(&cmds, CMD_SIGNIN); /* (turned on again: sign in again if not signed in) */
    enabled = on;
}

static void command(LONG c) {
    if (started && enabled) InterlockedOr(&cmds, c);
}

int rt_spotify_key(int vk) {
    if (!started || !enabled) return 0;
    switch (vk) {
    case 'M': command(CMD_TOGGLE); return 1;
    case VK_OEM_PERIOD: command(CMD_NEXT); return 1;
    case VK_OEM_COMMA: command(CMD_PREV); return 1;
    case VK_OEM_PLUS: command(CMD_VOLUP); return 1;
    case VK_OEM_MINUS: command(CMD_VOLDN); return 1;
    case VK_OEM_2: command(CMD_SHOW); return 1;
    }
    return 0;
}

void rt_spotify_pad(uint16_t *buttons) {
    static uint16_t was;
    if (!started || !enabled) return;
    uint16_t b = *buttons, down = b & ~was;
    was = b;
    if (!(b & 0x20)) return; /* Back held */
    if (down & 0x1) command(CMD_TOGGLE);
    if (down & 0x8) command(CMD_NEXT);
    if (down & 0x4) command(CMD_PREV);
    if (down & 0x2) command(CMD_SHOW);
    *buttons &= (uint16_t)~0xF; /* the game sees no D-pad meanwhile */
}

int rt_spotify_card(char *title, int tn, char *artist, int an, float *alpha) {
    if (!started || !enabled) return 0;
    uint64_t now = rt_now_100ns();
    EnterCriticalSection(&lock);
    int on = card_until && now < card_until && cur_title[0];
    if (on) {
        snprintf(title, (size_t)tn, "%s", cur_title);
        snprintf(artist, (size_t)an, "%s", cur_artist);
        double left = (double)(card_until - now) / 1e7, since = 6.0 - left;
        *alpha = (float)(left < 0.4 ? left / 0.4 : since < 0.25 ? since / 0.25 : 1.0);
    }
    LeaveCriticalSection(&lock);
    return on;
}

#else
void rt_spotify_init(void) {}
void rt_spotify_enable(int on) { (void)on; }
int rt_spotify_key(int vk) { (void)vk; return 0; }
void rt_spotify_pad(uint16_t *buttons) { (void)buttons; }
int rt_spotify_card(char *title, int tn, char *artist, int an, float *alpha) { (void)title, (void)tn, (void)artist, (void)an, (void)alpha; return 0; }
#endif
