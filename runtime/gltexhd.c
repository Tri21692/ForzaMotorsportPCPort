/* Sharper textures (the user's, 2026-11-01): every texture the game samples reaches the GPU through
 * gl_texture (glfill.c), decoded; here, before that upload, it can be
 *
 *   - replaced from a pack: <pack>/<key>.hd ('XHD1', u32 width, u32 height, then the texels as the
 *     decoder makes them, A8R8G8B8 rows), made offline (tools/texpack.py: an AI upscaler over
 *     exported textures). XBRT_TEX_PACK names the folder, else <mods>/textures;
 *   - drawn at 2 or 4 times its size on the GPU (XBRT_TEX_UPSCALE=2 or 4, texture_upscale in forza.ini): a
 *     compute pass of Catmull-Rom interpolation held within its four nearest texels (no ringing),
 *     then the mipmaps made again. Once per texture, so nothing a frame;
 *   - exported (XBRT_TEX_EXPORT=<folder>): <key>.bmp, level 0 with alpha, once each, for a pack.
 *
 * The game keeps the texture's size (the shaders' texel scale comes from it, glfill.c's u_scale), so
 * a bigger GL texture is sampled as the smaller one was. Depth textures and cube maps are left as
 * they are. The key is hd_key over level 0 and the size: fixed, as the packs' file names are made
 * with it (not hash_bytes, whose function the CPU picks).
 *
 * Included by raster.c (Texture) before glfill.c. */
#include <dirent.h>
#include <strings.h>

static GLuint compile(GLenum type, const char *src); /* glfill.c */

static uint64_t hd_key(const uint32_t *px, int w, int h) {
    const uint8_t *p = (const uint8_t *)px;
    size_t n = (size_t)w * h * 4;
    uint64_t a[4] = {0x9E3779B97F4A7C15ull ^ n, 0xC2B2AE3D27D4EB4Full, 0x165667B19E3779F9ull, 0x27D4EB2F165667C5ull};
    size_t k = 0;
    for (; k + 32 <= n; k += 32)
        for (int j = 0; j < 4; j++) {
            uint64_t v;
            memcpy(&v, p + k + 8 * j, 8);
            a[j] = (a[j] ^ v) * 0x100000001B3ull;
            a[j] ^= a[j] >> 29;
        }
    uint64_t r = a[0] ^ (a[1] * 3) ^ (a[2] * 5) ^ (a[3] * 7);
    for (; k < n; k++) r = (r ^ p[k]) * 0x100000001B3ull;
    return r ^ ((uint64_t)w << 48) ^ ((uint64_t)h << 32);
}

static int hd_on = -1, hd_scale;
static const char *hd_export;
static char hd_dir[1100];
static uint64_t *hd_pack;
static int hd_npack;
static uint64_t hd_seen[1 << 16]; /* keys exported (or found there), open addressing; 0 is empty */
static int hd_nseen;

/* 1 if k was already in the set (it is in it after). */
static int hd_seen_add(uint64_t k) {
    if (!k) k = 1;
    for (uint32_t i = (uint32_t)(k ^ k >> 32) & 0xFFFF;; i = (i + 1) & 0xFFFF) {
        if (hd_seen[i] == k) return 1;
        if (!hd_seen[i]) {
            if (hd_nseen >= 50000) return 1; /* (full: export no more) */
            hd_seen[i] = k, hd_nseen++;
            return 0;
        }
    }
}

static int hd_cmp(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return x < y ? -1 : x > y;
}

static void hd_init(void) {
    hd_on = 1;
    if (rt_tex_upscale < 0) {
        const char *s = getenv("XBRT_TEX_UPSCALE");
        rt_tex_upscale = !s ? 0 : atoi(s) >= 4 ? 4 : atoi(s) >= 2 ? 2 : 0;
    }
    if (rt_tex_pack_on < 0) rt_tex_pack_on = !(getenv("XBRT_TEX_PACK_ON") && !atoi(getenv("XBRT_TEX_PACK_ON")));
    hd_scale = rt_tex_upscale;
    free(hd_pack), hd_pack = NULL, hd_npack = 0; /* (again after F1's switches: the pack may have grown) */
    hd_export = getenv("XBRT_TEX_EXPORT");
    if (hd_export && !*hd_export) hd_export = NULL;
    if (hd_export && !hd_nseen) { /* what earlier sessions exported, so each is checked in memory, not on disk */
        CreateDirectoryA(hd_export, NULL);
        DIR *x = opendir(hd_export);
        struct dirent *e;
        while (x && (e = readdir(x)))
            if (strlen(e->d_name) == 20 && !strcasecmp(e->d_name + 16, ".bmp")) hd_seen_add(strtoull(e->d_name, NULL, 16));
        if (x) closedir(x);
    }
    const char *pack = getenv("XBRT_TEX_PACK");
    if (pack && *pack) snprintf(hd_dir, sizeof hd_dir, "%s", pack);
    else snprintf(hd_dir, sizeof hd_dir, "%s/textures", getenv("XBRT_MODS") && *getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    DIR *d = opendir(hd_dir);
    struct dirent *e;
    int cap = 0;
    while (d && (e = readdir(d))) {
        size_t n = strlen(e->d_name);
        if (n != 19 || strcasecmp(e->d_name + 16, ".hd")) continue;
        if (hd_npack == cap) cap = cap ? cap * 2 : 256, hd_pack = realloc(hd_pack, (size_t)cap * sizeof *hd_pack);
        hd_pack[hd_npack++] = strtoull(e->d_name, NULL, 16);
    }
    if (d) closedir(d);
    if (hd_npack) qsort(hd_pack, (size_t)hd_npack, sizeof *hd_pack, hd_cmp);
    fprintf(stderr, "xbrt: textures: %d in the pack %s (%s), upscale %s%s%s\n", hd_npack, hd_dir, rt_tex_pack_on ? "on" : "off", hd_scale == 4 ? "4x" : hd_scale ? "2x" : "off",
            hd_export ? ", exported to " : "", hd_export ? hd_export : "");
}

static int hd_in_pack(uint64_t k) {
    return hd_npack && bsearch(&k, hd_pack, (size_t)hd_npack, sizeof k, hd_cmp) != NULL;
}

/* The files are written by a thread of their own (the user's, 8 Nov: "Tsukuba has horrible fps ... slow as soon
 * as the race started": a track new to the export folder saved about 1,000 textures, 112 MB, in its first lap,
 * each written by the render thread in the middle of a frame). The render thread only copies the texels. Each
 * is written as .tmp and renamed, so a game closed mid-write leaves no half file for the pack. */
typedef struct HdJob { struct HdJob *next; uint64_t k; int w, h; uint32_t px[]; } HdJob;
static HdJob *hd_q_head, *hd_q_tail;
static size_t hd_q_bytes;
static CRITICAL_SECTION hd_q_cs;
static CONDITION_VARIABLE hd_q_cv;
static int hd_q_up;
#define HD_Q_MAX ((size_t)256 << 20) /* (more waiting than this: the rest are exported another session) */

static void hd_write_bmp(const HdJob *j) {
    char path[1200], tmp[1210];
    snprintf(path, sizeof path, "%s/%016llx.bmp", hd_export, (unsigned long long)j->k);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f) return;
    uint8_t h[54] = {'B', 'M'};
    uint32_t size = 54 + (uint32_t)j->w * j->h * 4;
    uint32_t vals[] = {size, 0, 54, 40, (uint32_t)j->w, (uint32_t)-j->h};
    memcpy(h + 2, &vals[0], 4), memcpy(h + 10, &vals[2], 4), memcpy(h + 14, &vals[3], 4), memcpy(h + 18, &vals[4], 4), memcpy(h + 22, &vals[5], 4);
    h[26] = 1, h[28] = 32;
    int ok = fwrite(h, 1, 54, f) == 54 && fwrite(j->px, 4, (size_t)j->w * j->h, f) == (size_t)j->w * j->h; /* (BGRA as the decoder lays A8R8G8B8 out) */
    ok = fclose(f) == 0 && ok;
    if (!ok || !MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING)) DeleteFileA(tmp);
}

static DWORD WINAPI hd_writer(LPVOID unused) {
    (void)unused;
    for (;;) {
        EnterCriticalSection(&hd_q_cs);
        while (!hd_q_head) SleepConditionVariableCS(&hd_q_cv, &hd_q_cs, INFINITE);
        HdJob *j = hd_q_head;
        if (!(hd_q_head = j->next)) hd_q_tail = NULL;
        LeaveCriticalSection(&hd_q_cs);
        hd_write_bmp(j);
        EnterCriticalSection(&hd_q_cs);
        hd_q_bytes -= (size_t)j->w * j->h * 4;
        LeaveCriticalSection(&hd_q_cs);
        free(j);
    }
    return 0;
}

static void hd_export_one(const Texture *t, uint64_t k) {
    if (t->w * t->h < 16 * 16) return;
    size_t n = (size_t)t->w * t->h * 4;
    if (!hd_q_up) {
        InitializeCriticalSection(&hd_q_cs), InitializeConditionVariable(&hd_q_cv), hd_q_up = 1;
        HANDLE th = CreateThread(NULL, 0, hd_writer, NULL, 0, NULL);
        if (th) SetThreadPriority(th, THREAD_PRIORITY_BELOW_NORMAL), CloseHandle(th);
        else hd_q_up = -1;
    }
    if (hd_q_up < 0) return;
    EnterCriticalSection(&hd_q_cs);
    size_t queued = hd_q_bytes;
    LeaveCriticalSection(&hd_q_cs);
    if (queued + n > HD_Q_MAX || hd_seen_add(k)) return;
    HdJob *j = malloc(sizeof *j + n);
    if (!j) return;
    j->next = NULL, j->k = k, j->w = t->w, j->h = t->h;
    memcpy(j->px, t->texels, n);
    EnterCriticalSection(&hd_q_cs);
    if (hd_q_tail) hd_q_tail->next = j; else hd_q_head = j;
    hd_q_tail = j, hd_q_bytes += n;
    WakeConditionVariable(&hd_q_cv);
    LeaveCriticalSection(&hd_q_cs);
}

static int hd_levels(int w, int h) {
    int l = 1;
    while ((w >> l) || (h >> l)) l++;
    return l;
}

/* The GPU's memory kept for the rest (the user's, 8 Nov: Alpine Ring's Mayhem race slowed to 30-48 fps and the game
 * froze loading the next: the 4x copies, 2048x2048 with their mipmaps, 22 MB each, took 6.8 GB of the laptop's 8 in
 * two laps, and the driver moved textures out of the GPU's memory as it drew). A sharper copy is made only while at
 * least this much would be left free (GL_NVX_gpu_memory_info, read every half second, less what was made since):
 * else at 2x, else at its own size. XBRT_TEX_VRAM_RESERVE=<MB>, default 1536; without NVIDIA's reading, no limit. */
static int hd_fits(int64_t bytes) {
    static int reserve = -1, said;
    extern int rt_vram_free_mb;
    if (reserve < 0) reserve = getenv("XBRT_TEX_VRAM_RESERVE") ? atoi(getenv("XBRT_TEX_VRAM_RESERVE")) : 1536;
    if (rt_vram_free_mb < 0) return 1;
    if ((int64_t)rt_vram_free_mb * 1048576 - hd_since_poll - bytes < (int64_t)reserve * 1048576) {
        if (!said++) fprintf(stderr, "xbrt: textures: the GPU's memory is low (%d MB free): new textures less sharp until there is room%s", rt_vram_free_mb, "\n");
        return 0;
    }
    hd_since_poll += bytes;
    return 1;
}

/* Level 0 of a pack's file into a new texture (bound to the current unit), every mip level made. */
static int hd_load(GLuint tex, uint64_t k) {
    char path[1200];
    snprintf(path, sizeof path, "%s/%016llx.hd", hd_dir, (unsigned long long)k);
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    uint32_t hd[3] = {0};
    int ok = fread(hd, 4, 3, f) == 3 && hd[0] == 0x31444858 /* XHD1 */ && hd[1] && hd[2] && hd[1] <= 8192 && hd[2] <= 8192;
    ok = ok && hd_fits((int64_t)hd[1] * hd[2] * 16 / 3); /* (with its mipmaps: a third more) */
    uint32_t *px = ok ? malloc((size_t)hd[1] * hd[2] * 4) : NULL;
    ok = px && fread(px, 4, (size_t)hd[1] * hd[2], f) == (size_t)hd[1] * hd[2];
    fclose(f);
    if (ok) {
        glBindTexture(GL_TEXTURE_2D, tex);
        glTexStorage2D(GL_TEXTURE_2D, hd_levels((int)hd[1], (int)hd[2]), GL_RGBA8, (int)hd[1], (int)hd[2]);
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (int)hd[1], (int)hd[2], GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, px);
        glGenerateMipmap(GL_TEXTURE_2D);
    }
    free(px);
    return ok;
}

static const char *hd_cs =
    "#version 430\n"
    "layout(local_size_x = 8, local_size_y = 8) in;\n"
    "layout(rgba8, binding = 0) uniform writeonly image2D u_dst;\n"
    "uniform sampler2D u_src;\n"
    "uniform vec2 u_sizef;\n"
    "uniform int u_wrap;\n" /* a tiling (power of two) texture wraps at its edges, a picture (linear) is held at them */
    "uniform int u_k;\n" /* the new size over the old: 2 or 4 */
    "ivec2 u_size;\n"
    "vec4 at(ivec2 p) {\n"
    "    p = u_wrap == 1 ? (p % u_size + u_size) % u_size : clamp(p, ivec2(0), u_size - 1);\n"
    "    return texelFetch(u_src, p, 0);\n"
    "}\n"
    "void main() {\n"
    "    u_size = ivec2(u_sizef);\n"
    "    ivec2 o = ivec2(gl_GlobalInvocationID.xy);\n"
    "    if (o.x >= u_k * u_size.x || o.y >= u_k * u_size.y) return;\n"
    "    vec2 s = (vec2(o) + 0.5) / float(u_k) - 0.5;\n" /* the new texel's centre in the old texels */
    "    ivec2 b = ivec2(floor(s));\n"
    "    vec2 f = s - vec2(b);\n"
    "    vec4 wx = vec4(((-0.5 * f.x + 1.0) * f.x - 0.5) * f.x, (1.5 * f.x - 2.5) * f.x * f.x + 1.0,\n"
    "                   ((-1.5 * f.x + 2.0) * f.x + 0.5) * f.x, (0.5 * f.x - 0.5) * f.x * f.x);\n"
    "    vec4 wy = vec4(((-0.5 * f.y + 1.0) * f.y - 0.5) * f.y, (1.5 * f.y - 2.5) * f.y * f.y + 1.0,\n"
    "                   ((-1.5 * f.y + 2.0) * f.y + 0.5) * f.y, (0.5 * f.y - 0.5) * f.y * f.y);\n"
    "    vec4 c = vec4(0.0);\n"
    "    for (int y = 0; y < 4; y++) {\n"
    "        vec4 row = vec4(0.0);\n"
    "        for (int x = 0; x < 4; x++) row += at(b + ivec2(x - 1, y - 1)) * wx[x];\n"
    "        c += row * wy[y];\n"
    "    }\n"
    "    vec4 n0 = at(b), n1 = at(b + ivec2(1, 0)), n2 = at(b + ivec2(0, 1)), n3 = at(b + ivec2(1, 1));\n"
    "    c = clamp(c, min(min(n0, n1), min(n2, n3)), max(max(n0, n1), max(n2, n3)));\n" /* no overshoot: no halos */
    "    imageStore(u_dst, o, c);\n"
    "}\n";

/* t's level 0 at k times the size (2 or 4) into tex (bound to the current unit), every mip level made. The
 * renderer's program and active unit are put back: this runs while a draw binds its textures. */
static int hd_upscale(GLuint tex, const Texture *t, int k) {
    static GLuint prog, src;
    static GLint u_size, u_wrap, u_src, u_k;
    static int failed;
    if (failed) return 0;
    if (!prog) {
        GLuint cs = compile(GL_COMPUTE_SHADER, hd_cs);
        prog = glCreateProgram();
        if (cs) glAttachShader(prog, cs);
        glLinkProgram(prog);
        GLint ok = 0;
        glGetProgramiv(prog, GL_LINK_STATUS, &ok);
        if (!cs || !ok) {
            fprintf(stderr, "xbrt: textures: the upscaling shader did not build; textures stay at their size\n");
            failed = 1;
            return 0;
        }
        u_size = glGetUniformLocation(prog, "u_sizef"), u_wrap = glGetUniformLocation(prog, "u_wrap"), u_src = glGetUniformLocation(prog, "u_src");
        u_k = glGetUniformLocation(prog, "u_k");
        glGenTextures(1, &src);
    }
    GLint was_prog = 0, was_unit = 0;
    glGetIntegerv(GL_CURRENT_PROGRAM, &was_prog);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &was_unit);
    /* the original, on unit 15 (the renderer uses 0-7) */
    glActiveTexture(GL_TEXTURE15);
    glBindTexture(GL_TEXTURE_2D, src);
    glBindSampler(15, 0);
    {
        static int sw, sh;
        if (sw < t->w || sh < t->h) { /* room for the largest so far (storage can't shrink or grow: made again) */
            glDeleteTextures(1, &src), glGenTextures(1, &src);
            glBindTexture(GL_TEXTURE_2D, src);
            sw = sw > t->w ? sw : t->w, sh = sh > t->h ? sh : t->h;
            glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, sw, sh);
        }
    }
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, t->w, t->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, t->texels);
    glActiveTexture((GLenum)was_unit);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexStorage2D(GL_TEXTURE_2D, hd_levels(k * t->w, k * t->h), GL_RGBA8, k * t->w, k * t->h);
    glUseProgram(prog);
    glUniform1i(u_src, 15), glUniform1i(u_wrap, !t->linear), glUniform1i(u_k, k);
    glUniform2fv(u_size, 1, (float[2]){(float)t->w, (float)t->h});
    glBindImageTexture(0, tex, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA8);
    glDispatchCompute((GLuint)(k * t->w + 7) / 8, (GLuint)(k * t->h + 7) / 8, 1);
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT | GL_SHADER_IMAGE_ACCESS_BARRIER_BIT | GL_TEXTURE_UPDATE_BARRIER_BIT);
    glBindImageTexture(0, 0, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA8);
    glGenerateMipmap(GL_TEXTURE_2D);
    glUseProgram((GLuint)was_prog);
    return 1;
}

/* From gl_texture, for a 2D colour texture: 1 when tex (bound) holds it, from the pack or upscaled. */
static int hd_upload(GLuint tex, Texture *t) {
    if (hd_on < 0) hd_init();
    t->hd = 0;
    if (t->cube || t->depth || !t->texels || t->texels == tex_dropped || t->w < 8 || t->h < 8) return 0;
    int pack = hd_npack && rt_tex_pack_on > 0;
    if (!hd_export && !pack && !hd_scale) return 0;
    uint64_t k = hd_key(t->texels, t->w, t->h);
    if (hd_export && t->decodes <= 2) hd_export_one(t, k); /* (not each frame of a video) */
    if (pack && hd_in_pack(k) && hd_load(tex, k)) return t->hd = 1;
    /* not one the CPU redraws over and over (its re-uploads: a compute pass each), nor huge (memory) */
    /* (4x only up to 512 a side: none past 2048, as at 2x) */
    if (hd_scale && t->decodes <= 4 && t->w <= 1024 && t->h <= 1024) {
        int k = hd_scale == 4 && t->w <= 512 && t->h <= 512 ? 4 : 2;
        int64_t one = (int64_t)t->w * t->h * 16 / 3; /* (its size, with mipmaps) */
        if (k == 4 && !hd_fits(one * 16)) k = 2;
        if (!hd_fits(one * k * k)) return 0;
        return t->hd = hd_upscale(tex, t, k);
    }
    return 0;
}
