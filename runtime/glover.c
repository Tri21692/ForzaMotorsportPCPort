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

static float ov_width(const OvFont *f, const char *s) {
    float w = 0;
    for (; *s; s++) {
        int k = (unsigned char)*s - 32;
        if (k < 0 || k >= 96) continue;
        w += (float)(f->a[k] + f->b[k] + f->c[k]) * f->scale;
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
        float gx = x + (float)f->a[k] * f->scale, sz = 32 * f->scale;
        float u0 = (float)(k % 16 * 34 + 1) / (16 * 34), v0 = (float)(k / 16 * 34 + 1) / (6 * 34);
        if (*s != ' ') ov_quad(gx, y, gx + sz, y + sz, u0, v0, u0 + 32.0f / (16 * 34), v0 + 32.0f / (6 * 34), c, 1 + font);
        x += (float)(f->a[k] + f->b[k] + f->c[k]) * f->scale;
    }
}

/* A round button prompt like the game's: a coloured disc with its letter. */
static void ov_button(float x, float y, const char *letter, const float col[4], const char *label) {
    static const float white[4] = {1, 1, 1, 1};
    ov_quad(x, y, x + 18, y + 18, 0, 0, 1, 1, col, 9);
    ov_text(OVF_ITEM, x + 9, y - 1, letter, white, 2);
    ov_text(OVF_MENU, x + 24, y - 3, label, white, 0);
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
    "uniform sampler2D u_f0, u_f1, u_f2, u_f3;\n"
    "void main() {\n"
    "    vec4 c = v_c;\n"
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
        static const char *fn[4] = {"u_f0", "u_f1", "u_f2", "u_f3"};
        for (int i = 0; i < 4; i++) glUniform1i(glGetUniformLocation(prog, fn[i]), i);
        glGenVertexArrays(1, &vao), glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
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
    glActiveTexture(GL_TEXTURE0);
    glBindVertexArray(ov_vao);
    glBindBuffer(GL_ARRAY_BUFFER, ov_vbo);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)ov_n * (GLsizeiptr)sizeof(OvVert), ov_v, GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, ov_n);
    glBindVertexArray(gl_vao);
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
    ov_text(OVF_MENU, X0 + 590, 26, "PC Settings", white, 1);
    int n = rt_overlay_items(), sel = rt_overlay_selected();
    float y = 82, row = 30;
    /* Eight rows at a time, scrolled to keep the chosen one in view: all of
     * them ran over the help text and the bottom bar. */
    enum { VISIBLE = 8 };
    int first = 0;
    if (n > VISIBLE) {
        first = sel - VISIBLE / 2;
        if (first > n - VISIBLE) first = n - VISIBLE;
        if (first < 0) first = 0;
        float top = y - 2, len = VISIBLE * row - 2;
        ov_rect(X0 + 598, top, X0 + 602, top + len, grey); /* the scroll bar: the whole list, and the part shown */
        ov_rect(X0 + 597, top + len * (float)first / (float)n, X0 + 603, top + len * (float)(first + VISIBLE) / (float)n, green);
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
    /* What the chosen setting does, and whether it waits for a restart. */
    ov_text(OVF_TEXT, X0 + 64, 362, rt_overlay_help(sel), grey, 0);
    if (rt_overlay_needs_restart()) ov_text(OVF_TEXT, X0 + 64, 378, "Restart the game for the new settings to take effect.", amber, 0);
    ov_button(X0 + 64, 428, "A", green, "Change");
    ov_button(X0 + 190, 428, "B", red, "Back");
    ov_text(OVF_MENU, X0 + 590, 425, "F1  Close", white, 1);
    ov_submit(vx, vy, vw, vh, W, H);
}

/* During a career time trial (hle_career.c), its three target times under the game's lap timer
 * (top right): gold, silver and bronze, each struck dim once the clock has passed it, and when the
 * lap is done the place it earned picked out. */
static void gl_tt_hud_draw(int vx, int vy, int vw, int vh) {
    uint32_t target[3], elapsed;
    int done;
    if (!rt_tt_hud(target, &elapsed, &done) || !ov_init()) return;
    float W = rt_display_widescreen() ? 853 : 640, H = 480, R = W - 40; /* the game's HUD keeps 40 from the right */
    static const float box[4] = {0, 0, 0, 0.45f}, medal[3][4] = {{0.98f, 0.80f, 0.20f, 1}, {0.82f, 0.84f, 0.88f, 1}, {0.85f, 0.55f, 0.30f, 1}},
                       gone[4] = {0.55f, 0.55f, 0.55f, 0.75f}, white[4] = {1, 1, 1, 1};
    static const char *place[3] = {"1ST", "2ND", "3RD"};
    ov_n = 0;
    float y = 146, row = 19;
    ov_rect(R - 150, y - 4, R + 6, y + 3 * row + 2, box);
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
    ov_submit(vx, vy, vw, vh, W, H);
}
