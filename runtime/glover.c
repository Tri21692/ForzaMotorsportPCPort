/* The settings overlay's drawing (overlay.c has the menu itself), with
 * Forza's own fonts, in the style of its menus: black bars top and bottom
 * edged in olive green, a light striped panel, the chosen row in white
 * with a green edge, and the game's round button prompts. Included by
 * raster.c after glfill.c.
 *
 * The fonts are the game's: it renders them into z:\fontcache\euro when
 * it first starts (Partition5 of the hard disk). Each .abc file has 8
 * bytes per UTF-16 character: the offset of a 1 KB block in the .sbm, the
 * slot in that block, and the character's A, B and C widths (signed
 * lead-in, ink width, signed lead-out). Each block is a 32x32 cell in
 * Morton order holding four characters, two bits each, one per slot. */

typedef struct {
    GLuint tex;               /* 16 x 6 cells of 34x34 (a glyph and a blank edge), characters 32-127, alpha */
    signed char a[96], c[96]; /* lead-in, lead-out */
    unsigned char b[96];      /* ink width */
    float scale;              /* as the game's metafont.ini draws it */
    int ok;
} OvFont;

enum { OVF_TITLE, OVF_MENU, OVF_ITEM, OVF_TEXT, OVF_N };
static OvFont ov_font[OVF_N];

static int ov_morton(int x, int y) {
    int r = 0;
    for (int i = 0; i < 5; i++) r |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1);
    return r;
}

static uint8_t *ov_read(const char *path, long *n) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *p = malloc((size_t)*n);
    if (p && fread(p, 1, (size_t)*n, f) != (size_t)*n) free(p), p = NULL;
    fclose(f);
    return p;
}

static void ov_font_load(OvFont *f, const char *name, float scale) {
    const char *hdd = getenv("XBRT_HDD") ? getenv("XBRT_HDD") : "hdd";
    char path[512];
    long na = 0, ns = 0;
    uint8_t *abc = NULL, *sbm = NULL;
    for (int part = 1; part <= 6 && !abc; part++) {
        snprintf(path, sizeof path, "%s/Partition%d/fontcache/euro/%s.abc", hdd, part, name);
        abc = ov_read(path, &na);
        snprintf(path, sizeof path, "%s/Partition%d/fontcache/euro/%s.sbm", hdd, part, name);
        if (abc) sbm = ov_read(path, &ns);
    }
    if (!abc || !sbm || na < 128 * 8) {
        free(abc), free(sbm);
        return;
    }
    static uint8_t atlas[6 * 34][16 * 34]; /* the blank edges keep filtering from taking in the next glyph */
    memset(atlas, 0, sizeof atlas);
    for (int ch = 32; ch < 128; ch++) {
        const uint8_t *e = abc + ch * 8;
        uint32_t off = (uint32_t)e[0] | (uint32_t)e[1] << 8 | (uint32_t)e[2] << 16 | (uint32_t)e[3] << 24;
        int slot = e[4] & 3, k = ch - 32;
        f->a[k] = (signed char)e[5], f->b[k] = e[6], f->c[k] = (signed char)e[7];
        if (off + 1024 > (uint32_t)ns) continue;
        for (int y = 0; y < 32; y++)
            for (int x = 0; x < 32; x++)
                atlas[k / 16 * 34 + 1 + y][k % 16 * 34 + 1 + x] = (uint8_t)(((sbm[off + ov_morton(x, y)] >> (2 * slot)) & 3) * 85);
    }
    free(abc), free(sbm);
    glGenTextures(1, &f->tex);
    glBindTexture(GL_TEXTURE_2D, f->tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_R8, 16 * 34, 6 * 34);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 16 * 34, 6 * 34, GL_RED, GL_UNSIGNED_BYTE, atlas);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    f->scale = scale, f->ok = 1;
}

/* Quads in the menu's own coordinates (640 wide, or 853 for 16:9, by
 * 480), each solid, a glyph, a disc (button prompt) or the striped panel. */
typedef struct {
    float x, y, u, v, r, g, b, a, kind;
} OvVert;

static OvVert *ov_v;
static int ov_n, ov_cap;

static void ov_quad(float x0, float y0, float x1, float y1, float u0, float v0, float u1, float v1, const float c[4], float kind) {
    if (ov_n + 6 > ov_cap) ov_cap = ov_cap ? ov_cap * 2 : 1024, ov_v = realloc(ov_v, (size_t)ov_cap * sizeof *ov_v);
    float xs[6] = {x0, x1, x1, x0, x1, x0}, ys[6] = {y0, y0, y1, y0, y1, y1};
    float us[6] = {u0, u1, u1, u0, u1, u0}, vs[6] = {v0, v0, v1, v0, v1, v1};
    for (int i = 0; i < 6; i++) ov_v[ov_n++] = (OvVert){xs[i], ys[i], us[i], vs[i], c[0], c[1], c[2], c[3], kind};
}

static void ov_rect(float x0, float y0, float x1, float y1, const float c[4]) { ov_quad(x0, y0, x1, y1, 0, 0, 1, 1, c, 0); }

static float ov_mul = 1; /* (text drawn bigger: the Mayhem Moment's name) */
static float ov_width(const OvFont *f, const char *s) {
    float w = 0;
    for (; *s; s++) {
        int k = (unsigned char)*s - 32;
        if (k < 0 || k >= 96) continue;
        w += (float)(f->a[k] + f->b[k] + f->c[k]) * f->scale * ov_mul;
    }
    return w;
}

/* Text with its baseline cell top at y; align: 0 left, 1 right, 2 centre. */
static void ov_text(int font, float x, float y, const char *s, const float c[4], int align) {
    const OvFont *f = &ov_font[font];
    if (!f->ok) return;
    if (align == 1) x -= ov_width(f, s);
    else if (align == 2) x -= ov_width(f, s) / 2;
    for (; *s; s++) {
        int k = (unsigned char)*s - 32;
        if (k < 0 || k >= 96) continue;
        float gx = x + (float)f->a[k] * f->scale * ov_mul, sz = 32 * f->scale * ov_mul;
        float u0 = (float)(k % 16 * 34 + 1) / (16 * 34), v0 = (float)(k / 16 * 34 + 1) / (6 * 34);
        if (*s != ' ') ov_quad(gx, y, gx + sz, y + sz, u0, v0, u0 + 32.0f / (16 * 34), v0 + 32.0f / (6 * 34), c, 1 + font);
        x += (float)(f->a[k] + f->b[k] + f->c[k]) * f->scale * ov_mul;
    }
}

/* A round button prompt like the game's: a coloured disc with its letter. */
static void ov_button(float x, float y, const char *letter, const float col[4], const char *label) {
    static const float white[4] = {1, 1, 1, 1};
    ov_quad(x, y, x + 18, y + 18, 0, 0, 1, 1, col, 9);
    ov_text(OVF_ITEM, x + 9, y - 1, letter, white, 2);
    ov_text(OVF_MENU, x + 24, y - 3, label, white, 0);
}

/* A pad button's name in a rounded pill (LT, RT, BACK, START: the user's, 7 Nov, "add controller icons for the
 * settings menu"), the width it took. */
static float ov_pill(float x, float y, const char *name, const float col[4]) {
    static const float white[4] = {1, 1, 1, 1};
    float w = ov_width(&ov_font[OVF_TEXT], name) + 12;
    if (w < 18) w = 18;
    ov_quad(x, y, x + 18, y + 18, 0, 0, 1, 1, col, 9);
    ov_quad(x + w - 18, y, x + w, y + 18, 0, 0, 1, 1, col, 9);
    ov_rect(x + 9, y, x + w - 9, y + 18, col);
    ov_text(OVF_TEXT, x + w / 2, y + 1, name, white, 2);
    return w;
}

static const char *ov_vs =
    "#version 430\n"
    "layout(location = 0) in vec2 a_p;\n"
    "layout(location = 1) in vec2 a_uv;\n"
    "layout(location = 2) in vec4 a_c;\n"
    "layout(location = 3) in float a_k;\n"
    "uniform vec2 u_size;\n" /* the menu's coordinate space */
    "out vec2 v_uv; out vec4 v_c; flat out int v_k; out vec2 v_p;\n"
    "void main() {\n"
    "    v_uv = a_uv, v_c = a_c, v_k = int(a_k + 0.5), v_p = a_p;\n"
    "    gl_Position = vec4(a_p.x / u_size.x * 2.0 - 1.0, 1.0 - a_p.y / u_size.y * 2.0, 0.0, 1.0);\n"
    "}\n";
static const char *ov_fs =
    "#version 430\n"
    "in vec2 v_uv; in vec4 v_c; flat in int v_k; in vec2 v_p;\n"
    "out vec4 o;\n"
    "uniform sampler2D u_f0, u_f1, u_f2, u_f3, u_f4;\n"
    "void main() {\n"
    "    vec4 c = v_c;\n"
    "    if (v_k == 5 || v_k == 6) {\n" /* a Mayhem Moment's photograph (u_f4, the photographs' sheet): lit, or grey and dark */
    "        vec3 p = texture(u_f4, v_uv).rgb;\n"
    "        if (v_k == 6) p = vec3(dot(p, vec3(0.299, 0.587, 0.114))) * 0.45;\n"
    "        o = vec4(p * c.rgb, c.a * texture(u_f4, v_uv).a);\n"
    "        return;\n"
    "    }\n"
    "    if (v_k == 1) c.a *= texture(u_f0, v_uv).r;\n"
    "    else if (v_k == 2) c.a *= texture(u_f1, v_uv).r;\n"
    "    else if (v_k == 3) c.a *= texture(u_f2, v_uv).r;\n"
    "    else if (v_k == 4) c.a *= texture(u_f3, v_uv).r;\n"
    "    else if (v_k == 9) { float d = length(v_uv - 0.5) * 2.0; c.a *= clamp((1.0 - d) * 9.0, 0.0, 1.0); }\n" /* disc */
    "    else if (v_k == 8) {\n" /* the panel: light grey, fading to white on the right, with faint diagonal stripes */
    "        float s = step(0.5, fract((v_p.x + v_p.y) / 9.0));\n"
    "        c.rgb = mix(c.rgb, vec3(1.0), smoothstep(0.0, 1.0, v_uv.x) * 0.35) - s * 0.035;\n"
    "    }\n"
    "    o = c;\n"
    "}\n";

static GLuint ov_prog, ov_vao, ov_vbo;
static GLint ov_u_size;

/* The Mayhem Moments' photographs: one sheet, <mods>/moments/photos.rgba (tools/mayhemphotos.py: "MMPH", then
 * u32s width, height, columns, rows, then RGBA rows top first), a tile a Moment in order; loaded once. */
static GLuint ov_photos;
static int ov_photo_cols = 1, ov_photo_rows = 1;
static void ov_photos_load(void) {
    static int tried;
    if (tried) return;
    tried = 1;
    char path[512];
    snprintf(path, sizeof path, "%s/moments/photos.rgba", getenv("XBRT_MODS") && *getenv("XBRT_MODS") ? getenv("XBRT_MODS") : "mods");
    long n = 0;
    uint8_t *d = ov_read(path, &n);
    uint32_t hd[5];
    if (!d || n < 24 || memcmp(d, "MMPH", 4)) { free(d); return; }
    memcpy(hd, d + 4, sizeof hd);
    if (!hd[0] || !hd[1] || hd[0] > 4096 || hd[1] > 4096 || (long)(24 + (size_t)hd[0] * hd[1] * 4) > n) { free(d); return; }
    glGenTextures(1, &ov_photos);
    glBindTexture(GL_TEXTURE_2D, ov_photos);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, (GLsizei)hd[0], (GLsizei)hd[1]);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)hd[0], (GLsizei)hd[1], GL_RGBA, GL_UNSIGNED_BYTE, d + 24);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    ov_photo_cols = (int)hd[2] ? (int)hd[2] : 1, ov_photo_rows = (int)hd[3] ? (int)hd[3] : 1;
    free(d);
}

/* The shader, buffers and fonts, made once: 0 if they could not be. */
static int ov_init(void) {
    GLuint prog = ov_prog, vao, vbo;
    if (!prog) {
        GLuint vs = compile(GL_VERTEX_SHADER, ov_vs), fs = compile(GL_FRAGMENT_SHADER, ov_fs);
        if (!vs || !fs) return 0;
        prog = glCreateProgram();
        glAttachShader(prog, vs), glAttachShader(prog, fs), glLinkProgram(prog);
        ov_u_size = glGetUniformLocation(prog, "u_size");
        glUseProgram(prog);
        static const char *fn[5] = {"u_f0", "u_f1", "u_f2", "u_f3", "u_f4"};
        for (int i = 0; i < 5; i++) glUniform1i(glGetUniformLocation(prog, fn[i]), i);
        glGenVertexArrays(1, &vao), glGenBuffers(1, &vbo);
        gl_vao_bind(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, sizeof(OvVert), (void *)0);
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(OvVert), (void *)(2 * sizeof(float)));
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, sizeof(OvVert), (void *)(4 * sizeof(float)));
        glVertexAttribPointer(3, 1, GL_FLOAT, GL_FALSE, sizeof(OvVert), (void *)(8 * sizeof(float)));
        for (int i = 0; i < 4; i++) glEnableVertexAttribArray((GLuint)i);
        /* The game's metafont.ini scales: title bar and menu 0.571, item
         * 0.64, text 0.76 (as the heading font). */
        ov_font_load(&ov_font[OVF_TITLE], "titlebar_font_-28", 0.75f);
        ov_font_load(&ov_font[OVF_MENU], "menu_font_-28", 0.62f);
        ov_font_load(&ov_font[OVF_ITEM], "item_font_-25", 0.64f);
        ov_font_load(&ov_font[OVF_TEXT], "text_font_-25", 0.56f);
        ov_prog = prog, ov_vao = vao, ov_vbo = vbo;
    }
    return 1;
}

/* The quads built (ov_v) drawn over the window rectangle x, y, w, h (GL's lower-left origin for
 * y), in coordinates W by H. */
static void ov_submit(int vx, int vy, int vw, int vh, float W, float H) {
    glViewport(vx, vy, vw, vh);
    glDisable(GL_SCISSOR_TEST), glDisable(GL_DEPTH_TEST), glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE);
    glBlendEquation(GL_FUNC_ADD);
    glUseProgram(ov_prog);
    gl_using = NULL;
    glUniform2fv(ov_u_size, 1, (float[2]){W, H});
    for (int i = 0; i < 4; i++) {
        glActiveTexture(GL_TEXTURE0 + (GLenum)i);
        glBindTexture(GL_TEXTURE_2D, ov_font[i].tex ? ov_font[i].tex : gl_dummy2d);
        glBindSampler((GLuint)i, 0);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    }
    glActiveTexture(GL_TEXTURE4);
    glBindTexture(GL_TEXTURE_2D, ov_photos ? ov_photos : gl_dummy2d);
    glBindSampler(4, 0);
    glActiveTexture(GL_TEXTURE0);
    gl_vao_bind(ov_vao);
    glBindBuffer(GL_ARRAY_BUFFER, ov_vbo);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)ov_n * (GLsizeiptr)sizeof(OvVert), ov_v, GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, ov_n);
    gl_vao_bind(gl_vao);
    glDisable(GL_BLEND);
}

/* The settings overlay over the picture, in the window rectangle x, y, w, h. */
static void gl_overlay_draw(int vx, int vy, int vw, int vh) {
    if (!ov_init()) return;
    float W = rt_display_widescreen() ? 853 : 640, H = 480, X0 = rt_display_widescreen() ? 106 : 0; /* the 4:3 menu, centred */
    static const float black[4] = {0, 0, 0, 0.92f}, dim[4] = {0, 0, 0, 0.55f}, olive[4] = {0.42f, 0.53f, 0.16f, 1},
                       panel[4] = {0.86f, 0.87f, 0.88f, 0.97f}, white[4] = {1, 1, 1, 1}, ink[4] = {0.13f, 0.14f, 0.15f, 1},
                       grey[4] = {0.38f, 0.40f, 0.42f, 1}, hi[4] = {1, 1, 1, 1}, green[4] = {0.30f, 0.62f, 0.12f, 1},
                       red[4] = {0.80f, 0.16f, 0.12f, 1}, amber[4] = {0.86f, 0.55f, 0.08f, 1};
    ov_n = 0;
    ov_rect(0, 0, W, H, dim);
    /* Title bar, panel, bottom bar: the game's layout. */
    ov_rect(0, 0, W, 62, black);
    ov_rect(0, 62, W, 66, olive);
    ov_quad(0, 66, W, 400, 0, 0, 1, 1, panel, 8);
    ov_rect(0, 400, W, 404, olive);
    ov_rect(0, 404, W, H, black);
    ov_text(OVF_TITLE, X0 + 64, 22, "OPTIONS", white, 0);
    if (rt_overlay_page() != 2) ov_text(OVF_MENU, X0 + 590, 26, "PC Settings", white, 1);
    int n = rt_overlay_items(), sel = rt_overlay_selected();
    /* The tabs (Display, Graphics, HDR, Game, Audio), the one shown picked out; Q / E, Tab or the triggers switch */
    const char *tabs[10];
    int cur, nt = rt_overlay_tabs(tabs, 10, &cur);
    float tx = X0 + 56;
    for (int i = 0; i < nt; i++) {
        float w = ov_width(&ov_font[OVF_ITEM], tabs[i]) + (nt > 7 ? 6 : nt > 6 ? 14 : 28); /* (narrower with many: all in 4:3) */
        if (i == cur) ov_rect(tx, 72, tx + w, 96, ink), ov_rect(tx, 94, tx + w, 97, green);
        ov_text(OVF_ITEM, tx + (nt > 7 ? 3 : nt > 6 ? 7 : 14), 74, tabs[i], i == cur ? white : grey, 0);
        tx += w + (nt > 7 ? 3 : 6);
    }
    float y = 106, row = 30;
    /* Eight rows at a time, scrolled to keep the chosen one in view: all of
     * them ran over the help text and the bottom bar. */
    enum { VISIBLE = 8 }; /* (106 + 8 rows: clear of the help text at 362) */
    int first = 0;
    if (n > VISIBLE) {
        first = sel - VISIBLE / 2;
        if (first > n - VISIBLE) first = n - VISIBLE;
        if (first < 0) first = 0;
        float top = y - 2, len = VISIBLE * row - 2;
        ov_rect(X0 + 598, top, X0 + 602, top + len, grey); /* the scroll bar: the whole list, and the part shown */
        ov_rect(X0 + 597, top + len * (float)first / (float)n, X0 + 603, top + len * (float)(first + VISIBLE) / (float)n, green);
    }
    if (!n && rt_overlay_page() == 2) { /* the Mayhem Moments: their photographs, four a row, lit once made (the user's:
                                        * "It can be seen prior to unlocking it, but once you unlock it, it lights up") */
        ov_photos_load();
        int nm = rt_mm_count(), pick = rt_overlay_scroll(), got = 0;
        float pw = 116, ph = 116; /* (the instant photos: square tiles, tilted inside them, see-through about) */
        /* Two rows at a time, scrolled to the one picked (the user's, 7 Nov: with 12 Moments the third row ran over
         * the description and off the panel) */
        int rows = (nm + 3) / 4, top = pick / 4 < 1 ? 0 : pick / 4 - 1;
        if (top > rows - 2) top = rows - 2;
        if (top < 0) top = 0;
        if (rows > 2) {
            float st = y - 6, len = 2 * (ph + 2) - 4;
            ov_rect(X0 + 598, st, X0 + 602, st + len, grey);
            ov_rect(X0 + 597, st + len * (float)top / (float)rows, X0 + 603, st + len * (float)(top + 2) / (float)rows, green);
        }
        for (int i = 0; i < nm; i++) {
            const char *nmn, *todo;
            int e;
            rt_mm_get(i, &nmn, &todo, &e);
            got += e;
            if (i / 4 < top || i / 4 >= top + 2) continue;
            float px = X0 + 66 + (i % 4) * (pw + 14), py = y - 6 + (i / 4 - top) * (ph + 2), g = i == pick ? 8 : 0; /* (the one picked a little bigger) */
            if (i == pick) ov_rect(px + 10, py + ph + 1, px + pw - 10, py + ph + 4, green);
            float u0 = (float)(i % ov_photo_cols) / ov_photo_cols, v0 = (float)(i / ov_photo_cols) / ov_photo_rows;
            if (ov_photos) ov_quad(px - g, py - g, px + pw + g, py + ph + g, u0, v0, u0 + 1.0f / ov_photo_cols, v0 + 1.0f / ov_photo_rows, white, e ? 5 : 6);
            else ov_rect(px - g + 8, py - g + 8, px + pw + g - 8, py + ph + g - 8, e ? amber : grey); /* (no photographs: a card) */
            if (!e) ov_text(OVF_ITEM, px + pw / 2, py + ph / 2 - 9, "LOCKED", white, 2);
            if (!ov_photos) ov_text(OVF_TEXT, px + pw / 2, py + ph - 20, nmn, e ? ink : grey, 2); /* (no photographs: the names) */
        }
        if (pick < nm) {
            const char *nmn, *todo;
            int e;
            rt_mm_get(pick, &nmn, &todo, &e);
            ov_text(OVF_TEXT, X0 + 66, 338, todo, e ? ink : grey, 0);
        }
        char t[48];
        snprintf(t, sizeof t, "%d of %d unlocked", got, nm);
        ov_text(OVF_MENU, X0 + 590, 26, t, white, 1); /* (in the title bar, for PC Settings: by the tabs it ran over them) */
    } else if (!n) { /* the achievements' tab: each one's name and what it asks, earned or how far along */
        int na = rt_ach_count(), top = rt_overlay_scroll(), got = 0;
        for (int i = 0; i < na; i++) {
            const char *nm, *ds;
            int pr, gl, e;
            rt_ach_get(i, &nm, &ds, &pr, &gl, &e);
            got += e;
            if (i < top || i >= top + 6) continue;
            float yy = y + (i - top) * 40;
            if (e) ov_rect(X0 + 56, yy - 2, X0 + 62, yy + 34, green);
            ov_text(OVF_MENU, X0 + 72, yy - 2, nm, e ? ink : grey, 0);
            ov_text(OVF_TEXT, X0 + 72, yy + 19, ds, grey, 0);
            char t[32];
            if (e) snprintf(t, sizeof t, "Earned");
            else snprintf(t, sizeof t, "%d / %d", pr, gl);
            ov_text(OVF_ITEM, X0 + 574, yy + 6, t, e ? green : grey, 1);
        }
        char t[48];
        snprintf(t, sizeof t, "%d of %d earned", got, na);
        ov_text(OVF_ITEM, X0 + 574, 342, t, ink, 1);
    }
    for (int i = first; i < n && i < first + VISIBLE; i++) {
        const char *label, *value;
        int live;
        rt_overlay_item(i, &label, &value, &live);
        if (i == sel) {
            ov_rect(X0 + 56, y - 2, X0 + 590, y + row - 4, hi);
            ov_rect(X0 + 56, y - 2, X0 + 62, y + row - 4, green);
            ov_text(OVF_MENU, X0 + 72, y, label, ink, 0);
            ov_text(OVF_ITEM, X0 + 574, y + 1, value, ink, 1);
            ov_text(OVF_ITEM, X0 + 574 - ov_width(&ov_font[OVF_ITEM], value) - 14, y + 1, "<", grey, 1);
        } else {
            ov_text(OVF_MENU, X0 + 72, y, label, grey, 0);
            ov_text(OVF_ITEM, X0 + 574, y + 1, value, grey, 1);
        }
        y += row;
    }
    { /* a tab's own text under its settings (Kaizo Mode's rules) */
        int nn;
        const char *const *notes = rt_overlay_notes(&nn);
        for (int i = 0; notes && i < nn; i++) ov_text(OVF_TEXT, X0 + 72, y + 12 + 20 * (float)i, notes[i], ink, 0);
    }
    /* What the chosen setting does, and whether it waits for a restart. */
    ov_text(OVF_TEXT, X0 + 64, 362, rt_overlay_help(sel), grey, 0);
    if (rt_overlay_needs_restart()) ov_text(OVF_TEXT, X0 + 64, 378, "Restart the game for the new settings to take effect.", amber, 0);
    if (n) ov_button(X0 + 64, 428, "A", green, "Change"); /* (none on the pages without settings: achievements, Moments) */
    ov_button(X0 + 190, 428, "B", red, "Back");
    { /* the pad's: the triggers switch tabs, Back+Start closes (F1, Q / E and Esc on the keyboard as before) */
        static const float pad[4] = {0.30f, 0.32f, 0.36f, 1};
        float x = X0 + 290;
        x += ov_pill(x, 428, "LT", pad) + 4;
        x += ov_pill(x, 428, "RT", pad) + 6;
        ov_text(OVF_MENU, x, 425, "Tabs", white, 0);
        x = X0 + 590 - ov_width(&ov_font[OVF_MENU], "Close") - 6;
        x -= ov_width(&ov_font[OVF_TEXT], "START") + 12;
        float bw = ov_width(&ov_font[OVF_TEXT], "BACK") + 12, plus = ov_width(&ov_font[OVF_MENU], "+") + 6;
        x -= plus + bw;
        x += ov_pill(x, 428, "BACK", pad) + 3;
        ov_text(OVF_MENU, x, 425, "+", white, 0);
        x += plus - 3;
        x += ov_pill(x, 428, "START", pad) + 6;
        ov_text(OVF_MENU, x, 425, "Close", white, 0);
    }
    ov_submit(vx, vy, vw, vh, W, H);
}

/* The race HUD's additions, under the game's lap timer (top right). During a career time trial
 * (hle_career.c): its three target times, gold, silver and bronze, each struck dim once the clock
 * has passed it, the place earned picked out when the lap is done, and the best time driven in it.
 * In a Catch-Up race: how far ahead of the opponent (or behind). And for a moment, a note (rt_toast:
 * "Screenshot saved"), low in the middle. */
/* Quick Race's menu (hle_quickrace.c): the game's menu style, a row each, the chosen one picked out. */
static void gl_qr_draw(int vx, int vy, int vw, int vh) {
    if (!ov_init()) return;
    float W = rt_display_widescreen() ? 853 : 640, H = 480, X0 = rt_display_widescreen() ? 106 : 0;
    static const float black[4] = {0, 0, 0, 0.92f}, dim[4] = {0, 0, 0, 0.55f}, olive[4] = {0.42f, 0.53f, 0.16f, 1},
                       panel[4] = {0.86f, 0.87f, 0.88f, 0.97f}, white[4] = {1, 1, 1, 1}, ink[4] = {0.13f, 0.14f, 0.15f, 1},
                       grey[4] = {0.38f, 0.40f, 0.42f, 1}, green[4] = {0.30f, 0.62f, 0.12f, 1}, red[4] = {0.80f, 0.16f, 0.12f, 1},
                       gold[4] = {0.86f, 0.55f, 0.08f, 1};
    ov_n = 0;
    ov_rect(0, 0, W, H, dim);
    ov_rect(0, 0, W, 62, black);
    ov_rect(0, 62, W, 66, olive);
    ov_quad(0, 66, W, 400, 0, 0, 1, 1, panel, 8);
    ov_rect(0, 400, W, 404, olive);
    ov_rect(0, 404, W, H, black);
    ov_text(OVF_TITLE, X0 + 64, 22, "QUICK RACE", white, 0);
    ov_text(OVF_MENU, X0 + 590, 26, "Arcade", white, 1);
    const char *label;
    char value[64];
    int sel, n = rt_qr_menu_row(-1, &label, value, sizeof value, &sel);
    float y = 80, row = 30;
    for (int i = 0; i < n; i++) {
        rt_qr_menu_row(i, &label, value, sizeof value, &sel);
        if (i == 7) y += 6; /* (the actions apart) */
        if (i == sel) {
            ov_rect(X0 + 56, y - 2, X0 + 590, y + row - 4, white);
            ov_rect(X0 + 56, y - 2, X0 + 62, y + row - 4, green);
        }
        ov_text(OVF_MENU, X0 + 72, y, label, i == sel ? ink : grey, 0);
        ov_text(OVF_ITEM, X0 + 574, y + 1, value, i == 7 ? gold : i == sel ? ink : grey, 1);
        y += row;
    }
    ov_text(OVF_TEXT, X0 + 64, 362, "Start Quick Race turns Series 1 - Race 1 into it: pick that event next.", grey, 0);
    ov_text(OVF_TEXT, X0 + 64, 378, "Takedowns: cars are light, wrecks respawn on the line. 1 opponent is the Catch-Up event's.", grey, 0);
    ov_button(X0 + 64, 428, "A", green, "Change");
    ov_button(X0 + 190, 428, "B", red, "Back");
    ov_submit(vx, vy, vw, vh, W, H);
}

/* Prize Match (hle_minigame.c): 16 cards, 4 by 4, face down olive with a "?", face up their prize;
 * the cursor's card outlined; the misses left, and once over the prize won. */
static void credits_text(char *t, size_t n, int v) {
    if (v >= 1000000) snprintf(t, n, "%d,%03d,%03d CR", v / 1000000, v / 1000 % 1000, v % 1000);
    else if (v >= 1000) snprintf(t, n, "%d,%03d CR", v / 1000, v % 1000);
    else snprintf(t, n, "%d CR", v);
}
static void gl_mg_draw(int vx, int vy, int vw, int vh) {
    if (!ov_init()) return;
    RtMatch m;
    rt_mg_state(&m);
    float W = rt_display_widescreen() ? 853 : 640, H = 480, X0 = rt_display_widescreen() ? 106 : 0;
    static const float dim[4] = {0, 0, 0, 0.9f}, black[4] = {0, 0, 0, 0.92f}, olive[4] = {0.42f, 0.53f, 0.16f, 1},
                       card[4] = {0.30f, 0.38f, 0.12f, 1}, face[4] = {0.93f, 0.93f, 0.90f, 1}, ink[4] = {0.13f, 0.14f, 0.15f, 1},
                       white[4] = {1, 1, 1, 1}, gold[4] = {0.98f, 0.80f, 0.20f, 1}, grey[4] = {0.6f, 0.62f, 0.64f, 1},
                       green[4] = {0.30f, 0.62f, 0.12f, 1}, red[4] = {0.80f, 0.16f, 0.12f, 1};
    ov_n = 0;
    ov_rect(0, 0, W, H, dim);
    ov_rect(0, 0, W, 62, black);
    ov_rect(0, 62, W, 66, olive);
    ov_text(OVF_TITLE, X0 + 64, 22, "PRIZE MATCH", white, 0);
    char t[64];
    if (m.done) snprintf(t, sizeof t, "Turns left: %d", rt_mg_turns());
    else snprintf(t, sizeof t, "Misses left: %d", m.misses_left);
    ov_text(OVF_MENU, X0 + 590, 26, t, white, 1);
    float cw = 112, chh = 62, gap = 10, gx = X0 + (640 - (4 * cw + 3 * gap)) / 2, gy = 82;
    for (int i = 0; i < 16; i++) {
        float x = gx + (i & 3) * (cw + gap), y = gy + (i >> 2) * (chh + gap);
        int matched = m.done && m.won == m.prize[i] && m.face[i];
        if (i == m.cursor && !m.done) ov_rect(x - 4, y - 4, x + cw + 4, y + chh + 4, gold);
        if (m.face[i]) {
            ov_rect(x, y, x + cw, y + chh, matched ? gold : face);
            credits_text(t, sizeof t, m.prize[i]);
            ov_text(OVF_ITEM, x + cw / 2, y + chh / 2 - 10, t, ink, 2);
        } else {
            ov_rect(x, y, x + cw, y + chh, card);
            ov_text(OVF_TITLE, x + cw / 2, y + chh / 2 - 16, "?", white, 2);
        }
    }
    ov_rect(0, 400, W, 404, olive);
    ov_rect(0, 404, W, H, black);
    if (m.done) {
        credits_text(t, sizeof t, m.won);
        char w[96];
        snprintf(w, sizeof w, m.misses_left > 0 ? "A match! You won %s" : "Out of misses: %s for trying", t);
        ov_text(OVF_MENU, W / 2, 372, w, gold, 2);
        ov_button(X0 + 64, 428, "A", green, "Done");
    } else {
        ov_text(OVF_TEXT, W / 2, 374, "Turn two cards at a time. The first pair you match is your prize.", white, 2);
        ov_button(X0 + 64, 428, "A", green, "Turn card");
        if (!m.flips) ov_button(X0 + 230, 428, "B", red, "Later");
    }
    (void)grey;
    ov_submit(vx, vy, vw, vh, W, H);
}

static void gl_tt_hud_draw(int vx, int vy, int vw, int vh) {
    uint32_t target[3], elapsed;
    int done, metres;
    int tt = rt_tt_hud(target, &elapsed, &done);
    int cu = !tt && rt_catchup_hud(&metres);
    RtDriftHud dh;
    int drift = !tt && !cu && rt_drift_hud(&dh);
    int toast = rt_toast_until && rt_now_100ns() < rt_toast_until;
    const char *ach = rt_ach_banner();
    int mg = rt_mg_hint();
    static int photo = -1; /* (the Moments' photo runs, XBRT_MM_PHOTO: none of our race HUD in the pictures) */
    if (photo < 0) photo = getenv("XBRT_MM_PHOTO") != NULL;
    const char *qn = photo ? NULL : rt_qr_note();
    int qtd = photo ? 0 : rt_qr_takedowns();
    float tank = rt_qr_tank();
    int qr_hud = ((rt_qr_mods & QR_NITRO) || rt_qr_mayhem()) && tank < 0.999f;
    int qcam = photo ? 0 : rt_qr_cam_active(); /* (the photo runs' wreck camera: no bars in the picture) */
    float fpos[3], fback[3], fpow;
    int flame = rt_qr_flame(fpos, fback, &fpow);
    if (rt_show_fps < 0) rt_show_fps = getenv("XBRT_SHOW_FPS") && atoi(getenv("XBRT_SHOW_FPS"));
    int fps = rt_show_fps && rt_fps_shown > 0;
    char sp_title[128], sp_artist[128];
    float sp_a = 0;
    int sp = !photo && rt_spotify_card(sp_title, sizeof sp_title, sp_artist, sizeof sp_artist, &sp_a); /* spotify.c: a new song */
    if (!(tt || cu || drift || toast || fps || ach || mg || qn || qtd || qr_hud || qcam || flame || sp) || !ov_init()) return;
    float W = rt_display_widescreen() ? 853 : 640, H = 480, R = W - 40; /* the game's HUD keeps 40 from the right */
    static const float box[4] = {0, 0, 0, 0.45f}, medal[3][4] = {{0.98f, 0.80f, 0.20f, 1}, {0.82f, 0.84f, 0.88f, 1}, {0.85f, 0.55f, 0.30f, 1}},
                       gone[4] = {0.55f, 0.55f, 0.55f, 0.75f}, white[4] = {1, 1, 1, 1},
                       ahead[4] = {0.45f, 0.95f, 0.45f, 1}, behind[4] = {1.0f, 0.55f, 0.35f, 1};
    static const char *place[3] = {"1ST", "2ND", "3RD"};
    ov_n = 0;
    float y = 146, row = 19;
    if (tt) {
        uint32_t best = rt_tt_best();
        ov_rect(R - 150, y - 4, R + 6, y + (best ? 4 : 3) * row + 2, box);
        int earned = 3;
        for (int k = 2; k >= 0; k--)
            if (elapsed <= target[k]) earned = k;
        for (int k = 0; k < 3; k++) {
            char t[32];
            snprintf(t, sizeof t, "%02u:%02u.%03u", target[k] / 60000, target[k] / 1000 % 60, target[k] % 1000);
            int missed = elapsed > target[k];
            const float *c = missed ? gone : medal[k];
            if (done && k == earned) ov_rect(R - 150, y + k * row - 2, R + 6, y + (k + 1) * row - 2, (float[4]){medal[k][0], medal[k][1], medal[k][2], 0.35f});
            ov_text(OVF_ITEM, R - 144, y + k * row - 3, place[k], c, 0);
            ov_text(OVF_ITEM, R, y + k * row - 3, t, done && k == earned ? white : c, 1);
        }
        if (best) {
            char t[32];
            snprintf(t, sizeof t, "%02u:%02u.%03u", best / 60000, best / 1000 % 60, best % 1000);
            ov_text(OVF_ITEM, R - 144, y + 3 * row - 3, "BEST", white, 0);
            ov_text(OVF_ITEM, R, y + 3 * row - 3, t, white, 1);
        }
    }
    if (cu) {
        char t[32];
        snprintf(t, sizeof t, "%d m", metres < 0 ? -metres : metres);
        ov_rect(R - 150, y - 4, R + 6, y + row + 2, box);
        ov_text(OVF_ITEM, R - 144, y - 3, metres >= 0 ? "AHEAD" : "BEHIND", metres >= 0 ? ahead : behind, 0);
        ov_text(OVF_ITEM, R, y - 3, t, white, 1);
    }
    if (drift) { /* the score and the places' targets (lit once reached), the drift now and its angle */
        static const float yellow[4] = {1.0f, 0.85f, 0.25f, 1}, bar[4] = {1.0f, 0.55f, 0.15f, 0.9f}, track[4] = {1, 1, 1, 0.18f};
        char t[48];
        ov_rect(R - 150, y - 4, R + 6, y + 4 * row + 2, box);
        ov_text(OVF_ITEM, R - 144, y - 3, "DRIFT", white, 0);
        snprintf(t, sizeof t, "%u", dh.total);
        ov_text(OVF_ITEM, R, y - 3, t, white, 1);
        for (int k = 0; k < 3; k++) {
            int got = dh.total >= dh.target[k];
            snprintf(t, sizeof t, "%u", dh.target[k]);
            if (dh.done && got && (k == 0 || dh.total < dh.target[k - 1]))
                ov_rect(R - 150, y + (k + 1) * row - 2, R + 6, y + (k + 2) * row - 2, (float[4]){medal[k][0], medal[k][1], medal[k][2], 0.35f});
            ov_text(OVF_ITEM, R - 144, y + (k + 1) * row - 3, place[k], got ? medal[k] : gone, 0);
            ov_text(OVF_ITEM, R, y + (k + 1) * row - 3, t, got ? medal[k] : gone, 1);
        }
        if (dh.drifting) { /* under the box, on no background (the user's): the drift's points with its length bonus, the angle as a bar (to 90 degrees) */
            float yd = y + 4 * row + 8;
            static const float shade[4] = {0, 0, 0, 0.7f};
            snprintf(t, sizeof t, "+%u", dh.drift);
            ov_text(OVF_ITEM, R - 142, yd - 1, t, shade, 0);
            ov_text(OVF_ITEM, R - 144, yd - 3, t, yellow, 0);
            snprintf(t, sizeof t, "x%.1f", dh.mult);
            ov_text(OVF_ITEM, R + 2, yd - 1, t, shade, 1);
            ov_text(OVF_ITEM, R, yd - 3, t, yellow, 1);
            float a = dh.angle > 90 ? 90 : dh.angle;
            ov_rect(R - 144, yd + row + 2, R, yd + row + 10, track);
            ov_rect(R - 144, yd + row + 2, R - 144 + 144 * a / 90, yd + row + 10, bar);
        }
        if (dh.msg) { /* on no background (the user's), a shadow under it to read on bright sky or paint */
            static const float shade[4] = {0, 0, 0, 0.7f};
            ov_text(OVF_ITEM, W / 2 + 2, 335, dh.msg, shade, 2);
            ov_text(OVF_ITEM, W / 2, 333, dh.msg, dh.msg[0] == '+' ? yellow : behind, 2);
        }
    }
    if (fps) { /* the frame rate, small in the top left corner, green at 58 or more, amber, red under 40 */
        static const float good[4] = {0.45f, 0.95f, 0.45f, 1}, fair[4] = {1.0f, 0.75f, 0.25f, 1}, poor[4] = {1.0f, 0.4f, 0.3f, 1};
        char t[16];
        snprintf(t, sizeof t, "%.0f FPS", rt_fps_shown);
        ov_rect(8, 8, 74, 26, box);
        ov_text(OVF_ITEM, 14, 8, t, rt_fps_shown >= 58 ? good : rt_fps_shown >= 40 ? fair : poor, 0);
    }
    if (mg) { /* Prize Match turns waiting, on the career's menus: top right, under the title bar (low it hid the dealer's cars) */
        static const float gold[4] = {0.98f, 0.80f, 0.20f, 1}, bg[4] = {0, 0, 0, 0.62f};
        char t[64];
        snprintf(t, sizeof t, "PRIZE MATCH x%d   Q / White: play", rt_mg_turns());
        ov_rect(W - 300, 72, W - 20, 98, bg);
        ov_text(OVF_ITEM, W - 160, 76, t, gold, 2);
    }
    if (flame) { /* Mayhem's boost: a flame at the exhaust, the point and one 1.2 m behind it through the frame's camera
                  * (rows 166-169: clip space), drawn as flickering bands, white-hot at the pipe to red at the tip */
        float pts[2][2], ws[2];
        int ok = 1;
        for (int e = 0; e < 2 && ok; e++) {
            float q[3] = {fpos[0] + fback[0] * 1.2f * e, fpos[1] + fback[1] * 1.2f * e, fpos[2] + fback[2] * 1.2f * e};
            float cx = rt_cam_vp[0][0] * q[0] + rt_cam_vp[0][1] * q[1] + rt_cam_vp[0][2] * q[2] + rt_cam_vp[0][3];
            float cy = rt_cam_vp[1][0] * q[0] + rt_cam_vp[1][1] * q[1] + rt_cam_vp[1][2] * q[2] + rt_cam_vp[1][3];
            float cw = rt_cam_vp[3][0] * q[0] + rt_cam_vp[3][1] * q[1] + rt_cam_vp[3][2] * q[2] + rt_cam_vp[3][3];
            if (!(cw > 0.1f)) { ok = 0; break; }
            float sx = cx / cw, sy = cy / cw;
            static int flog = -1;
            if (flog < 0) flog = getenv("XBRT_FLAMELOG") != NULL;
            if (flog) fprintf(stderr, "xbrt: flame %d: (%.2f %.2f %.2f) clip %.3f %.3f %.3f -> %.3f %.3f (W %g H %g)\n", e, q[0], q[1], q[2], cx, cy, cw, sx, sy, (double)W, (double)H);
            if (sx > -1.6f && sx < 1.6f && sy > -1.6f && sy < 1.6f) pts[e][0] = (sx + 1) * 0.5f * W, pts[e][1] = (1 - sy) * 0.5f * H; /* (normalised) */
            else pts[e][0] = sx * W / 640, pts[e][1] = sy; /* (already the screen's) */
            ws[e] = cw;
        }
        { /* the frame's camera rows never put the pipe on the screen (the first tests): drawn where the chase
           * camera shows the car's tail, the bottom middle, and only with the camera there, 2-15 m behind the car
           * (in the other views and the look back, none) */
            float dx = rt_cam_pos[0] - fpos[0], dy = rt_cam_pos[1] - fpos[1], dz = rt_cam_pos[2] - fpos[2];
            float d = sqrtf(dx * dx + dy * dy + dz * dz), along = dx * fback[0] + dy * fback[1] + dz * fback[2];
            ok = d > 2 && d < 15 && along > 0.7f * d;
            pts[0][0] = W * 0.5f, pts[0][1] = H * 0.8f, pts[1][0] = W * 0.5f, pts[1][1] = H * 0.8f + 46;
            ws[0] = 4;
        }
        if (ok) {
            static const float core[4] = {1, 0.97f, 0.75f, 0.95f}, mid[4] = {1, 0.62f, 0.12f, 0.85f}, tip[4] = {0.9f, 0.18f, 0.05f, 0.6f};
            float len = sqrtf((pts[1][0] - pts[0][0]) * (pts[1][0] - pts[0][0]) + (pts[1][1] - pts[0][1]) * (pts[1][1] - pts[0][1]));
            float r = 26.0f / (ws[0] > 1 ? ws[0] : 1) * 4; /* (the pipe's flame about 0.3 m across) */
            if (r > 26) r = 26;
            if (r < 3) r = 3;
            uint64_t t = rt_now_100ns() / 300000; /* (a flicker 33 times a second) */
            float jit = (float)((t * 2654435761u >> 13) % 100) / 100.0f;
            for (int b = 0; b < 6; b++) { /* bands from the pipe back to the tip, each narrower and redder */
                float u = b / 6.0f, x = pts[0][0] + (pts[1][0] - pts[0][0]) * u, y = pts[0][1] + (pts[1][1] - pts[0][1]) * u;
                float rr = r * (1.0f - u * 0.7f) * (0.85f + 0.3f * jit), hh = rr * 0.7f + len / 12;
                const float *col = b < 2 ? core : b < 4 ? mid : tip;
                ov_rect(x - rr, y - hh, x + rr, y + hh, col);
            }
        }
    }
    if (qn || qtd || qr_hud || qcam) { /* Quick Race: a TAKEDOWN! / RESPAWN note, the takedowns so far, the nitro left */
        static const float orange[4] = {1.0f, 0.55f, 0.15f, 1}, shade[4] = {0, 0, 0, 0.7f}, track[4] = {1, 1, 1, 0.18f}, blue[4] = {0.35f, 0.75f, 1, 0.9f},
                           bars[4] = {0, 0, 0, 1}, red[4] = {0.85f, 0.12f, 0.10f, 1}, white2[4] = {1, 1, 1, 1};
        char t[32];
        if (qcam) { /* the takedown camera (the user's: an overlay "like in the video", our own): bars top and bottom,
                     * an IMPACT tag in the top one, the takedown's name large in the bottom one */
            const char *mmf = rt_mm_flash();
            ov_rect(0, 0, W, 54, bars), ov_rect(0, H - (mmf ? 104 : 64), W, H, bars);
            ov_rect(R - 120, 16, R, 40, red);
            ov_text(OVF_ITEM, R - 60, 18, "IMPACT", white2, 2);
            if (qn && !mmf) ov_text(OVF_TITLE, W / 2 + 2, H - 50, qn, shade, 2), ov_text(OVF_TITLE, W / 2, H - 52, qn, orange, 2);
        } else if (qn && !rt_mm_flash()) ov_text(OVF_TITLE, W / 2 + 2, 152, qn, shade, 2), ov_text(OVF_TITLE, W / 2, 150, qn, orange, 2);
        const char *mmf = photo ? NULL : rt_mm_flash();
        if (mmf) { /* a Mayhem Moment (the user's: bigger, bottom left, "make it known that you got it"): a white flash,
                    * MAYHEM MOMENT! over its name large in gold, popping in, and UNLOCKED! the first time */
            static const float gold[4] = {0.98f, 0.80f, 0.20f, 1}, lime[4] = {0.30f, 0.80f, 0.20f, 1};
            int is_new;
            float age = rt_mm_flash_age(&is_new), x0 = 26, by = qcam ? H - 100 : H - 170;
            if (age < 0.35f) { float fl[4] = {1, 1, 1, 0.75f * (1 - age / 0.35f)}; ov_rect(0, 0, W, H, fl); }
            ov_text(OVF_TITLE, x0 + 2, by + 2, "MAYHEM MOMENT!", shade, 0), ov_text(OVF_TITLE, x0, by, "MAYHEM MOMENT!", orange, 0);
            ov_mul = age < 0.25f ? 2.6f - 0.8f * (age / 0.25f) : 1.8f; /* (a pop: big, then settled) */
            ov_text(OVF_TITLE, x0 + 3, by + 31, mmf, shade, 0), ov_text(OVF_TITLE, x0, by + 28, mmf, gold, 0);
            float nw = ov_width(&ov_font[OVF_TITLE], mmf);
            ov_mul = 1;
            if (is_new && age > 0.4f && fmodf(age, 0.6f) < 0.45f) { /* (blinking) */
                float tx = x0 + nw + 16, ty = by + 40;
                ov_rect(tx, ty, tx + 112, ty + 26, lime);
                ov_text(OVF_ITEM, tx + 56, ty + 3, "UNLOCKED!", white2, 2);
            }
        }
        if (qtd) { /* top left, large: the run's takedowns (in the bar while the camera is on a wreck) */
            snprintf(t, sizeof t, "TAKEDOWNS  %d", qtd);
            float ty = qcam ? 16 : 70;
            ov_text(OVF_MENU, 46, ty + 2, t, shade, 0), ov_text(OVF_MENU, 44, ty, t, orange, 0);
        }
        if (qr_hud) {
            ov_rect(R - 144, 170, R, 178, track);
            ov_rect(R - 144, 170, R - 144 + 144 * tank, 178, blue);
        }
    }
    if (ach) { /* an achievement just earned: a banner at the top, in the middle */
        static const float gold[4] = {0.98f, 0.80f, 0.20f, 1}, bg[4] = {0, 0, 0, 0.62f};
        float w = 190;
        ov_rect(W / 2 - w, 60, W / 2 + w, 112, bg);
        ov_rect(W / 2 - w, 60, W / 2 + w, 63, gold);
        ov_text(OVF_ITEM, W / 2, 67, "ACHIEVEMENT UNLOCKED", gold, 2);
        ov_text(OVF_MENU, W / 2, 85, ach, white, 2);
    }
    if (sp) { /* the song Spotify started: a card at the bottom, in the middle, clear of the toast below it */
        static const float green[4] = {0.11f, 0.73f, 0.33f, 1}, bg[4] = {0, 0, 0, 0.62f}, soft[4] = {0.80f, 0.82f, 0.84f, 1};
        float g[4] = {green[0], green[1], green[2], sp_a}, b[4] = {0, 0, 0, bg[3] * sp_a}, t[4] = {1, 1, 1, sp_a}, s[4] = {soft[0], soft[1], soft[2], sp_a};
        float most = 330; /* half the widest: long names cut with "..." */
        for (char *p = sp_title; ov_width(&ov_font[OVF_MENU], sp_title) > 2 * most - 30 && strlen(sp_title) > 4;)
            p = sp_title + strlen(sp_title) - 4, strcpy(p, "...");
        for (char *p = sp_artist; ov_width(&ov_font[OVF_TEXT], sp_artist) > 2 * most - 30 && strlen(sp_artist) > 4;)
            p = sp_artist + strlen(sp_artist) - 4, strcpy(p, "...");
        float wt = ov_width(&ov_font[OVF_MENU], sp_title), wa = ov_width(&ov_font[OVF_TEXT], sp_artist);
        float w = (wt > wa ? wt : wa) / 2 + 20;
        if (w < 120) w = 120;
        ov_rect(W / 2 - w, 344, W / 2 + w, 394, b);
        ov_rect(W / 2 - w, 391, W / 2 + w, 394, g);
        ov_text(OVF_MENU, W / 2, 347, sp_title, t, 2);
        ov_text(OVF_TEXT, W / 2, 369, sp_artist, s, 2);
    }
    if (toast) {
        float w = 150;
        ov_rect(W / 2 - w, 400, W / 2 + w, 424, box);
        ov_text(OVF_ITEM, W / 2, 403, rt_toast_text, white, 2);
    }
    ov_submit(vx, vy, vw, vh, W, H);
}
