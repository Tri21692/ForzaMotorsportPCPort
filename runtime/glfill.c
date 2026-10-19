/* Filling on the host GPU (docs/GPU.md, steps 2-4, first cut).
 *
 * Included by raster.c, whose types it shares. The CPU still transforms
 * vertices (project(), on the fill workers); what moves to the GPU is the
 * filling, three quarters of the software rasteriser's time:
 *
 *   - Triangles go up as they come out of setup_tri: screen position in
 *     samples, depth, 1/w (so the GPU interpolates perspective-correctly),
 *     colours, four texture coordinates.
 *   - One fragment shader does what combine() does, driven by the combiner
 *     methods as uniforms: no shader per state, so nothing compiles mid-race.
 *   - Each surface the game draws to is a framebuffer: colour plus depth
 *     (and stencil). Its RAM copy is uploaded when it changed since the GPU
 *     last saw it (a hash), and the GPU's result is read back into RAM at
 *     the points raster.c already flushes at: surface changes and flips,
 *     clears, semaphores and notifies, textures that overlap the surface.
 *     Everything else (display, screenshots, the CPU) keeps working on RAM.
 *   - Textures are uploaded from raster.c's decoded copies, once per decode.
 *
 * GL rows run bottom-up; Xbox row 0 is drawn at GL row 0 too (y is not
 * flipped), so uploads and read-backs copy rows straight through.
 */

static const char *vs_src =
    "#version 430\n"
    "layout(location = 0) in vec4 a_pos;\n" /* x, y in samples; z in depth units; 1/w */
    "layout(location = 1) in vec4 a_c0;\n"
    "layout(location = 2) in vec4 a_c1;\n"
    "layout(location = 3) in vec4 a_t0;\n"
    "layout(location = 4) in vec4 a_t1;\n"
    "layout(location = 5) in vec4 a_t2;\n"
    "layout(location = 6) in vec4 a_t3;\n"
    "layout(location = 7) in float a_fog;\n"
    "uniform vec2 u_size;\n"
    "uniform float u_zmax;\n"
    "out vec4 v_c0, v_c1, v_t0, v_t1, v_t2, v_t3;\n"
    "out float v_fog;\n"
    "void main() {\n"
    "    float w = a_pos.w != 0.0 ? 1.0 / a_pos.w : 1.0;\n"
    "    vec3 ndc = vec3(a_pos.x / u_size.x * 2.0 - 1.0, a_pos.y / u_size.y * 2.0 - 1.0,\n"
    "                    clamp(a_pos.z / u_zmax, 0.0, 1.0) * 2.0 - 1.0);\n"
    "    gl_Position = vec4(ndc * w, w);\n"
    "    v_c0 = a_c0; v_c1 = a_c1; v_t0 = a_t0; v_t1 = a_t1; v_t2 = a_t2; v_t3 = a_t3; v_fog = a_fog;\n"
    "}\n";

/* combine() from raster.c, in GLSL. */
static const char *fs_src =
    "#version 430\n"
    "in vec4 v_c0, v_c1, v_t0, v_t1, v_t2, v_t3;\n"
    "in float v_fog;\n"
    "out vec4 o_color;\n"
    "uniform vec3 u_fogc;\n"
    "uniform uint u_cicw[8], u_cocw[8], u_aicw[8], u_aocw[8];\n"
    "uniform vec4 u_c0[8], u_c1[8], u_fc0, u_fc1;\n"
    "uniform uint u_ctl, u_f0, u_f1;\n"
    "uniform int u_mode[4];\n"      /* 0 off, 1-3 sample, 4 pass-through */
    "uniform int u_kind[4];\n"      /* 0 none, 1 2D, 2 cube, 3 depth (from RAM), 4 depth (a framebuffer's) */
    "uniform vec2 u_scale[4];\n"    /* 1 / size for linear textures (texel coordinates), else 1 */
    "uniform float u_dmax[4];\n"
    "uniform int u_shadow_func;\n"
    "uniform int u_alpha_func;\n"   /* 0 off, else NV2A/GL 0x200-0x207 */
    "uniform float u_alpha_ref;\n"
    "uniform sampler2D u_tex0, u_tex1, u_tex2, u_tex3;\n"
    "uniform samplerCube u_cube0, u_cube1, u_cube2, u_cube3;\n"
    "vec4 R[16];\n"
    "vec3 E, F;\n"
    "float map_in(float x, uint m) {\n"
    "    switch (m >> 5) {\n"
    "    case 0u: return max(x, 0.0);\n"
    "    case 1u: return 1.0 - clamp(x, 0.0, 1.0);\n"
    "    case 2u: return 2.0 * max(x, 0.0) - 1.0;\n"
    "    case 3u: return 1.0 - 2.0 * max(x, 0.0);\n"
    "    case 4u: return max(x, 0.0) - 0.5;\n"
    "    case 5u: return 0.5 - max(x, 0.0);\n"
    "    case 6u: return x;\n"
    "    }\n"
    "    return -x;\n"
    "}\n"
    "vec4 reg(uint r) { return r == 15u ? vec4(E * F, 0.0) : R[r]; }\n"
    "vec3 in_rgb(uint i) {\n"
    "    vec4 v = reg(i & 15u);\n"
    "    vec3 x = (i & 16u) != 0u ? v.aaa : v.rgb;\n"
    "    uint m = i & 0xE0u;\n"
    "    return vec3(map_in(x.r, m), map_in(x.g, m), map_in(x.b, m));\n"
    "}\n"
    "float in_a(uint i) {\n"
    "    vec4 v = reg(i & 15u);\n"
    "    return map_in((i & 16u) != 0u ? v.a : v.b, i & 0xE0u);\n"
    "}\n"
    "float map_out(float x, uint m) {\n"
    "    if (m == 0x08u) x -= 0.5; else if (m == 0x10u) x *= 2.0; else if (m == 0x18u) x = (x - 0.5) * 2.0;\n"
    "    else if (m == 0x20u) x *= 4.0; else if (m == 0x30u) x *= 0.5;\n"
    "    return clamp(x, -1.0, 1.0);\n"
    "}\n"
    "vec3 map_out3(vec3 v, uint m) { return vec3(map_out(v.r, m), map_out(v.g, m), map_out(v.b, m)); }\n"
    "bool mux_sel(bool msb) { float r0a = R[12].a; return msb ? r0a >= 0.5 : (int(r0a * 255.0) & 1) != 0; }\n"
    "void stage_rgb(uint icw, uint ocw, bool msb) {\n"
    "    vec3 a = in_rgb(icw >> 24 & 255u), b = in_rgb(icw >> 16 & 255u), c = in_rgb(icw >> 8 & 255u), d = in_rgb(icw & 255u);\n"
    "    uint fl = ocw >> 12, m = fl & 0x38u;\n"
    "    vec3 x = (fl & 2u) != 0u ? vec3(dot(a, b)) : a * b;\n"
    "    vec3 y = (fl & 1u) != 0u ? vec3(dot(c, d)) : c * d;\n"
    "    vec3 ms = map_out3((fl & 4u) != 0u ? (mux_sel(msb) ? y : x) : x + y, m), ab = map_out3(x, m), cd = map_out3(y, m);\n"
    "    uint dab = ocw >> 4 & 15u, dcd = ocw & 15u, dms = ocw >> 8 & 15u;\n"
    "    if (dab != 0u) R[dab].rgb = ab;\n"
    "    if (dcd != 0u) R[dcd].rgb = cd;\n"
    "    if (dms != 0u) R[dms].rgb = ms;\n"
    "    if (dab != 0u && (fl & 0x80u) != 0u) R[dab].a = ab.b;\n"
    "    if (dcd != 0u && (fl & 0x40u) != 0u) R[dcd].a = cd.b;\n"
    "}\n"
    "void stage_a(uint icw, uint ocw, bool msb) {\n"
    "    float a = in_a(icw >> 24 & 255u), b = in_a(icw >> 16 & 255u), c = in_a(icw >> 8 & 255u), d = in_a(icw & 255u);\n"
    "    uint fl = ocw >> 12, m = fl & 0x38u;\n"
    "    float x = a * b, y = c * d;\n"
    "    float ms = map_out((fl & 4u) != 0u ? (mux_sel(msb) ? y : x) : x + y, m), ab = map_out(x, m), cd = map_out(y, m);\n"
    "    uint dab = ocw >> 4 & 15u, dcd = ocw & 15u, dms = ocw >> 8 & 15u;\n"
    "    if (dab != 0u) R[dab].a = ab;\n"
    "    if (dcd != 0u) R[dcd].a = cd;\n"
    "    if (dms != 0u) R[dms].a = ms;\n"
    "}\n"
    "bool compare(int f, float a, float b) {\n"
    "    switch (f) { case 0: return false; case 1: return a < b; case 2: return a == b; case 3: return a <= b;\n"
    "    case 4: return a > b; case 5: return a != b; case 6: return a >= b; }\n"
    "    return true;\n"
    "}\n"
    "vec4 fetch(int i, vec4 q, sampler2D t, samplerCube cube) {\n"
    "    if (u_mode[i] == 0) return vec4(0.0);\n"
    "    if (u_mode[i] == 4) return clamp(q, 0.0, 1.0);\n"
    "    if (u_kind[i] == 0) return vec4(0.0);\n"
    "    if (u_kind[i] == 2) return texture(cube, q.xyz);\n"
    "    if (u_kind[i] == 3 || u_kind[i] == 4) {\n" /* a shadow map: compare, as xemu does */
    "        float qw = q.w != 0.0 ? q.w : 1.0;\n"
    "        float d = texture(t, q.xy / qw * u_scale[i]).r;\n"
    "        if (u_kind[i] == 4) d = floor(d * u_dmax[i] + 0.5);\n" /* GL's depth is 0..1: back to the Xbox's units */
    "        float r = u_mode[i] == 2 ? clamp(q.z / qw, 0.0, u_dmax[i]) : 0.0;\n"
    "        return vec4(compare(u_shadow_func, d, r) ? 1.0 : 0.0);\n"
    "    }\n"
    "    vec2 st = q.w != 0.0 && q.w != 1.0 ? q.xy / q.w : q.xy;\n"
    "    return texture(t, st * u_scale[i]);\n"
    "}\n"
    "void main() {\n"
    "    for (int i = 0; i < 16; i++) R[i] = vec4(0.0);\n"
    "    E = vec3(0.0); F = vec3(0.0);\n"
    "    R[3] = vec4(u_fogc, clamp(v_fog, 0.0, 1.0));\n"
    "    R[4] = v_c0; R[5] = v_c1;\n"
    "    R[8] = fetch(0, v_t0, u_tex0, u_cube0);\n"
    "    R[9] = fetch(1, v_t1, u_tex1, u_cube1);\n"
    "    R[10] = fetch(2, v_t2, u_tex2, u_cube2);\n"
    "    R[11] = fetch(3, v_t3, u_tex3, u_cube3);\n"
    "    R[12].a = u_mode[0] != 0 ? R[8].a : 1.0;\n" /* R0.a starts as T0.a */
    "    int stages = min(int(u_ctl & 255u), 8);\n"
    "    bool msb = (u_ctl & 256u) != 0u;\n"
    "    for (int i = 0; i < stages; i++) {\n"
    "        R[1] = u_c0[(u_ctl & 0x1000u) != 0u ? i : 0];\n"
    "        R[2] = u_c1[(u_ctl & 0x10000u) != 0u ? i : 0];\n"
    "        stage_rgb(u_cicw[i], u_cocw[i], msb);\n"
    "        stage_a(u_aicw[i], u_aocw[i], msb);\n"
    "    }\n"
    "    vec4 o;\n"
    "    if (u_f0 == 0u && u_f1 == 0u) {\n"
    "        o = clamp(R[12], 0.0, 1.0);\n"
    "    } else {\n"
    "        R[1] = u_fc0; R[2] = u_fc1;\n"
    "        vec3 v1 = (u_f1 & 0x40u) != 0u ? 1.0 - R[5].rgb : R[5].rgb, r0 = (u_f1 & 0x20u) != 0u ? 1.0 - R[12].rgb : R[12].rgb;\n"
    "        R[14].rgb = (u_f1 & 0x80u) != 0u ? clamp(v1 + r0, 0.0, 1.0) : v1 + r0;\n"
    "        vec3 e = in_rgb(u_f1 >> 24 & 255u), f = in_rgb(u_f1 >> 16 & 255u);\n"
    "        E = e; F = f;\n"
    "        vec3 a = in_rgb(u_f0 >> 24 & 255u), b = in_rgb(u_f0 >> 16 & 255u), c = in_rgb(u_f0 >> 8 & 255u), d = in_rgb(u_f0 & 255u);\n"
    "        o.rgb = clamp(d + a * b + (1.0 - a) * c, 0.0, 1.0);\n"
    "        o.a = clamp(in_a(u_f1 >> 8 & 255u), 0.0, 1.0);\n"
    "    }\n"
    "    if (u_alpha_func != 0 && !compare(u_alpha_func - 0x200, o.a, u_alpha_ref)) discard;\n"
    "    o_color = o;\n"
    "}\n";

#define GL_VERT 29 /* floats per vertex */

static int gl_ready = -1; /* -1 not set up, 0 failed, 1 ready */
static GLuint gl_fs, gl_vao, gl_vbo, gl_dummy2d, gl_dummycube;
static GLint u_size, u_zmax, u_cicw, u_cocw, u_aicw, u_aocw, u_c0, u_c1, u_fc0, u_fc1, u_ctl, u_f0, u_f1;
static GLint u_fogc, u_mode, u_kind, u_scale, u_dmax, u_shadow_func, u_alpha_func, u_alpha_ref, u_tex[4], u_cube[4];

/* A linked program and its uniforms' locations: the CPU path's vertex
 * shader, or one made from a vertex program (glvsh.c), each with the one
 * fragment shader. gl_use makes the u_* names above refer to its own. */
static GLint *const gl_loc_var[] = {&u_size, &u_zmax, &u_cicw, &u_cocw, &u_aicw, &u_aocw, &u_c0, &u_c1, &u_fc0, &u_fc1,
                                    &u_ctl, &u_f0, &u_f1, &u_fogc, &u_mode, &u_kind, &u_scale, &u_dmax, &u_shadow_func,
                                    &u_alpha_func, &u_alpha_ref, &u_tex[0], &u_tex[1], &u_tex[2], &u_tex[3], &u_cube[0],
                                    &u_cube[1], &u_cube[2], &u_cube[3]};
static const char *const gl_loc_name[] = {"u_size", "u_zmax", "u_cicw", "u_cocw", "u_aicw", "u_aocw", "u_c0", "u_c1", "u_fc0",
                                          "u_fc1", "u_ctl", "u_f0", "u_f1", "u_fogc", "u_mode", "u_kind", "u_scale", "u_dmax",
                                          "u_shadow_func", "u_alpha_func", "u_alpha_ref", "u_tex0", "u_tex1", "u_tex2", "u_tex3",
                                          "u_cube0", "u_cube1", "u_cube2", "u_cube3"};
#define GL_NLOC (int)(sizeof gl_loc_var / sizeof gl_loc_var[0])

typedef struct {
    GLuint prog;
    GLint loc[GL_NLOC];
    GLint vc, sxy, fog; /* a vertex program's: constants, sample scale, fog */
} GlProg;

static GlProg gl_main, *gl_using;

static GLuint compile(GLenum type, const char *src) {
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok = 0;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetShaderInfoLog(s, sizeof log, NULL, log);
        fprintf(stderr, "xbrt: GL shader does not compile:\n%s\n", log);
        return 0;
    }
    return s;
}

/* Links vs with the fragment shader into p. */
static int gl_link(GlProg *p, GLuint vs) {
    p->prog = glCreateProgram();
    glAttachShader(p->prog, vs);
    glAttachShader(p->prog, gl_fs);
    glLinkProgram(p->prog);
    GLint ok = 0;
    glGetProgramiv(p->prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetProgramInfoLog(p->prog, sizeof log, NULL, log);
        fprintf(stderr, "xbrt: GL program does not link:\n%s\n", log);
        return 0;
    }
    for (int i = 0; i < GL_NLOC; i++) p->loc[i] = glGetUniformLocation(p->prog, gl_loc_name[i]);
    p->vc = glGetUniformLocation(p->prog, "u_vc"), p->sxy = glGetUniformLocation(p->prog, "u_sxy");
    p->fog = glGetUniformLocation(p->prog, "u_fog");
    glUseProgram(p->prog);
    gl_using = NULL;
    for (int i = 0; i < 4; i++) /* 2D on units 0-3, cubes on 4-7 */
        glUniform1i(p->loc[21 + i], i), glUniform1i(p->loc[25 + i], 4 + i);
    return 1;
}

static void gl_use(GlProg *p) {
    if (gl_using == p) return;
    glUseProgram(p->prog);
    for (int i = 0; i < GL_NLOC; i++) *gl_loc_var[i] = p->loc[i];
    gl_using = p;
}

static int gl_setup(void) {
    GLuint vs = compile(GL_VERTEX_SHADER, vs_src);
    gl_fs = compile(GL_FRAGMENT_SHADER, fs_src);
    if (!vs || !gl_fs || !gl_link(&gl_main, vs)) return 0;
    gl_use(&gl_main);
    glGenVertexArrays(1, &gl_vao);
    glBindVertexArray(gl_vao);
    glGenBuffers(1, &gl_vbo);
    glBindBuffer(GL_ARRAY_BUFFER, gl_vbo);
    for (int i = 0; i < 8; i++) { /* position, two colours, four texture coordinates, fog */
        glVertexAttribPointer((GLuint)i, i < 7 ? 4 : 1, GL_FLOAT, GL_FALSE, GL_VERT * sizeof(float), (void *)(uintptr_t)(i * 4 * sizeof(float)));
        glEnableVertexAttribArray((GLuint)i);
    }
    /* Something valid on every unit a shader might read. */
    uint32_t black = 0;
    glGenTextures(1, &gl_dummy2d);
    glBindTexture(GL_TEXTURE_2D, gl_dummy2d);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, 1, 1);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 1, 1, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, &black);
    glGenTextures(1, &gl_dummycube);
    glBindTexture(GL_TEXTURE_CUBE_MAP, gl_dummycube);
    glTexStorage2D(GL_TEXTURE_CUBE_MAP, 1, GL_RGBA8, 1, 1);
    for (int f = 0; f < 6; f++)
        glTexSubImage2D(GL_TEXTURE_CUBE_MAP_POSITIVE_X + (GLenum)f, 0, 0, 0, 1, 1, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, &black);
    fprintf(stderr, "xbrt: drawing on the GPU\n");
    return 1;
}

/* ---- surfaces ---- */

typedef struct {
    uint32_t cbase, cpitch, cfmt, zbase, zpitch, zfmt; /* the key, with w and h */
    int w, h, bpp, zbpp;
    GLuint fbo, ctex, ztex;
    uint64_t chash, zhash; /* of RAM as the GPU last left it or saw it */
    int dirty;             /* the GPU has drawn since the last read-back */
    int cdirty;            /* ... colour not read back (or on its way, gl_pending) */
    int zdirty;            /* ... depth or stencil written and not read back */
    int check;             /* RAM may have changed: compare hashes before the next draw (only when not dirty) */
    unsigned used;
    unsigned seq;          /* when it last drew, in gl_seq's order */
    int zgpu;              /* a shadow map sampled where it was drawn: its depth lives only on the GPU (gl_depth_stays) */
} GlSurf;

#define GL_SURFS 32 /* a race frame draws to about 21 */
static GlSurf gl_surf[GL_SURFS];
static GlSurf *gl_cur;
static unsigned gl_tick, gl_seq;

static int gl_fits(uint32_t base, uint32_t pitch, int h) {
    return (uint64_t)(base & (RT_PHYS_SIZE - 1)) + (uint64_t)pitch * (uint64_t)h <= RT_PHYS_SIZE;
}

static int gl_overlaps(const GlSurf *s, uint32_t base, uint32_t size);
static int gl_aliases(const GlSurf *a, const GlSurf *b);
static int gl_span_hit(uint32_t a, uint32_t an, uint32_t b, uint32_t bn);
static void gl_complete(void);

static void gl_readback_one(GlSurf *s) {
    gl_complete();
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
    if (s->cdirty && gl_fits(s->cbase, s->cpitch, s->h)) { /* colour already read back, or on its way, is not read again */
        glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, phys(s->cbase));
        else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, phys(s->cbase));
        s->chash = hash_bytes(phys(s->cbase), s->cpitch * (uint32_t)s->h);
    }
    /* Depth only when something wrote it: Forza's 2D passes keep the depth
     * mask on with no depth buffer (zeta offset 0), which made a 1.2 MB
     * "depth buffer" at physical address 0 that was read back over RAM. */
    if (s->ztex && s->zdirty && gl_fits(s->zbase, s->zpitch, s->h)) {
        glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->zpitch / (uint32_t)s->zbpp));
        if (s->zbpp == 4) glReadPixels(0, 0, s->w, s->h, GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8, phys(s->zbase));
        else glReadPixels(0, 0, s->w, s->h, GL_DEPTH_COMPONENT, GL_UNSIGNED_SHORT, phys(s->zbase));
        s->zhash = hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h);
    }
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    s->dirty = s->cdirty = s->zdirty = 0;
}

/* Several framebuffers can cover the same bytes (gl_aliases); each one,
 * when it is bound, takes in what the others drew since it last drew
 * (gl_bind), so the one that drew last holds the newest picture of the
 * bytes it covers. Read-backs therefore go oldest first: older drawing
 * over the same bytes reaches RAM before this one does. Clean framebuffers
 * over these bytes then compare RAM with their copy before they draw. */
static void gl_readback(GlSurf *s) {
    for (;;) {
        GlSurf *older = NULL;
        for (int i = 0; i < GL_SURFS; i++) {
            GlSurf *e = &gl_surf[i];
            if (e != s && e->fbo && e->dirty && e->seq < s->seq && gl_aliases(e, s) && (!older || e->seq < older->seq)) older = e;
        }
        if (!older) break;
        gl_readback(older);
    }
    gl_readback_one(s);
    for (int i = 0; i < GL_SURFS; i++)
        if (&gl_surf[i] != s && gl_surf[i].fbo && !gl_surf[i].dirty && gl_aliases(&gl_surf[i], s)) gl_surf[i].check = 1;
}

static int gl_overlaps(const GlSurf *s, uint32_t base, uint32_t size) {
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + size;
    uint32_t c0 = s->cbase & (RT_PHYS_SIZE - 1), c1 = c0 + s->cpitch * (uint32_t)s->h;
    uint32_t z0 = s->zbase & (RT_PHYS_SIZE - 1), z1 = z0 + s->zpitch * (uint32_t)s->h;
    return (lo < c1 && c0 < hi) || (s->ztex && lo < z1 && z0 < hi);
}

/* Has the GPU drawn into these bytes through this framebuffer since its
 * last read-back? */
static int gl_drew(const GlSurf *s, uint32_t base, uint32_t size) {
    if (!s->fbo || !s->dirty) return 0;
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + size;
    uint32_t c0 = s->cbase & (RT_PHYS_SIZE - 1), c1 = c0 + s->cpitch * (uint32_t)s->h;
    uint32_t z0 = s->zbase & (RT_PHYS_SIZE - 1), z1 = z0 + s->zpitch * (uint32_t)s->h;
    return (s->cdirty && lo < c1 && c0 < hi) || (s->zdirty && lo < z1 && z0 < hi);
}

/* Do two framebuffers cover some of the same bytes? Forza draws to the
 * same buffer with and without a depth buffer, and its bloom passes draw
 * into a quarter of a front buffer (320x240 at its start, 320x120 at row
 * 240) between frames: each combination is a framebuffer of its own. */
static int gl_aliases(const GlSurf *a, const GlSurf *b) {
    return gl_overlaps(a, b->cbase, b->cpitch * (uint32_t)b->h) || (b->ztex && gl_overlaps(a, b->zbase, b->zpitch * (uint32_t)b->h));
}

/* Brings RAM up to date with what the GPU drew, on every surface it drew
 * to: switching surfaces does not read back, only something that can look
 * at RAM does (a texture over a surface, the CPU after a fence or a flip). */
static void gl_sync(void) {
    gl_complete();
    for (int i = 0; i < GL_SURFS; i++)
        if (gl_surf[i].fbo && gl_surf[i].dirty) gl_readback(&gl_surf[i]); /* older ones over the same bytes first */
}

/* After a point where the CPU may write RAM (a fence, a notify, a flip) or
 * a clear that works on RAM, each surface is checked against its hash
 * before it is drawn to again. Between those points nothing else writes
 * them; hashing before every draw cost more than the drawing. */
static void gl_sync_cpu(void) {
    gl_sync();
    for (int i = 0; i < GL_SURFS; i++) gl_surf[i].check = 1;
}

/* ---- read-backs that do not wait ----
 * The buffers the CRTC shows are read back into pixel buffer objects
 * when D3D's frame notify comes (see trap_method), and copied to RAM at
 * the next vertical blank, before D3D's handler can point the CRTC at
 * them, or earlier when anything else is about to look at RAM (any other
 * read-back, a hash check, a texture). Waiting for each read-back where
 * it was asked for kept the CPU and the GPU taking turns: ~20 fps in the
 * race, ~30 without. In issue order, so older drawing reaches RAM first. */
typedef struct {
    GlSurf *s;
    uint32_t base, size;
    GLuint pbo;
} GlPending;

static GlPending gl_pend[16];
static int gl_npend;

static void gl_complete(void) {
    if (!gl_npend) return;
    for (int i = 0; i < gl_npend; i++) {
        GlPending *p = &gl_pend[i];
        glBindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
        const void *m = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, p->size, GL_MAP_READ_BIT);
        if (m) memcpy(phys(p->base), m, p->size);
        glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
        if (!p->s->cdirty) p->s->chash = hash_bytes(phys(p->base), p->size);
    }
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    gl_npend = 0;
}

/* A framebuffer's colour into a pixel buffer object, older colour over
 * the same bytes first; its depth stays on the GPU. */
static void gl_readback_color_async(GlSurf *s) {
    uint32_t c = s->cpitch * (uint32_t)s->h;
    for (;;) {
        GlSurf *older = NULL;
        for (int i = 0; i < GL_SURFS; i++) {
            GlSurf *e = &gl_surf[i];
            if (e != s && e->fbo && e->seq < s->seq && gl_drew(e, s->cbase, c) && (!older || e->seq < older->seq)) older = e;
        }
        if (!older) break;
        if (older->zdirty && gl_span_hit(older->zbase, older->zpitch * (uint32_t)older->h, s->cbase, c)) gl_readback(older);
        else gl_readback_color_async(older);
    }
    if (!gl_fits(s->cbase, s->cpitch, s->h)) return;
    if (gl_npend == 16) gl_complete();
    GlPending *p = &gl_pend[gl_npend++];
    p->s = s, p->base = s->cbase, p->size = c;
    if (!p->pbo) glGenBuffers(1, &p->pbo);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
    glBufferData(GL_PIXEL_PACK_BUFFER, c, NULL, GL_STREAM_READ);
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
    glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, NULL);
    else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, NULL);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    s->cdirty = 0;
    s->dirty = s->zdirty;
    for (int i = 0; i < GL_SURFS; i++)
        if (&gl_surf[i] != s && gl_surf[i].fbo && !gl_surf[i].dirty && gl_aliases(&gl_surf[i], s)) gl_surf[i].check = 1;
}

/* A shadow map sampled on the GPU, where it was drawn, never goes to RAM:
 * nothing on the CPU reads Forza's. It is marked clean instead, with the
 * hash of the bytes now in RAM, so that nothing reads it back later
 * either: the 768x768 one at 02ad1000 shares its bytes with something of
 * the CPU's, and when it stayed dirty, later read-backs (gl_sync) wrote old
 * shadow depth over them (the car flew off upside down, or stuck in the
 * ground under yellow light shafts). The GPU keeps sampling its own copy
 * until the next depth write, or uploads RAM if the CPU writes it
 * (gl_upload_if_changed). Its colour, at the same bytes, goes with it. */
static void gl_depth_stays(GlSurf *s) {
    if (!s->ztex || !gl_fits(s->zbase, s->zpitch, s->h)) return;
    s->zgpu = 1, s->zdirty = 0;
    s->zhash = hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h);
    if (s->cbase == s->zbase && s->cpitch == s->zpitch) s->cdirty = 0, s->chash = s->zhash;
    s->dirty = s->cdirty;
}

/* The colour drawn over these bytes on its way to RAM (the shown buffers). */
static void gl_sync_color_async(uint32_t base, uint32_t size) {
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (e->fbo && e->cdirty && gl_span_hit(e->cbase, e->cpitch * (uint32_t)e->h, base, size)) gl_readback_color_async(e);
    }
}

/* A flip. The framebuffers stay on the GPU: the display gets its buffers
 * through the read-backs above, textures theirs when they are read, and
 * nothing else turned out to look (reading everything back here was a
 * wait for the GPU every frame). The CPU may write RAM under the clean
 * ones. Then at most two frames stay queued on the GPU: with nothing
 * waiting for it, the front end presents thousands of frames a second and
 * the Intel driver's queue grew until it blocked for good. */
static void gl_flip(void) {
    static GLsync fence[2];
    static int next;
    for (int i = 0; i < GL_SURFS; i++)
        if (!gl_surf[i].dirty) gl_surf[i].check = 1;
    if (gl_ready <= 0) return;
    if (fence[next]) {
        glClientWaitSync(fence[next], GL_SYNC_FLUSH_COMMANDS_BIT, 1000000000ull);
        glDeleteSync(fence[next]);
    }
    fence[next] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    next = (next + 1) % 2;
}

/* RAM up to date in these bytes: the framebuffers that drew into them are
 * read back (with older drawing over the same bytes first), the rest stay
 * on the GPU. Reading back everything whenever a texture was a render
 * target cost a third of the device thread. */
static void gl_sync_range(uint32_t base, uint32_t size) {
    gl_complete();
    for (int i = 0; i < GL_SURFS; i++)
        if (gl_drew(&gl_surf[i], base, size)) gl_readback(&gl_surf[i]);
}

static void gl_upload_if_changed(GlSurf *s) {
    gl_complete(); /* RAM as the GPU left it, before comparing */
    if (gl_fits(s->cbase, s->cpitch, s->h)) {
        uint64_t h = hash_bytes(phys(s->cbase), s->cpitch * (uint32_t)s->h);
        if (h != s->chash) {
            glBindTexture(GL_TEXTURE_2D, s->ctex);
            glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
            if (s->bpp == 4) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, phys(s->cbase));
            else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, phys(s->cbase));
            s->chash = h;
        }
    }
    if (s->ztex && gl_fits(s->zbase, s->zpitch, s->h)) {
        uint64_t h = hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h);
        if (h != s->zhash) {
            glBindTexture(GL_TEXTURE_2D, s->ztex);
            glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(s->zpitch / (uint32_t)s->zbpp));
            if (s->zbpp == 4) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8, phys(s->zbase));
            else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_DEPTH_COMPONENT, GL_UNSIGNED_SHORT, phys(s->zbase));
            s->zhash = h;
        }
    }
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
}

/* Can what e drew reach s by copying texels on the GPU? Only where the
 * bytes line up: the same pitch and format, a whole number of rows apart,
 * colour over colour and depth over depth. */
static int gl_row_offset(uint32_t from, uint32_t to, uint32_t pitch, int *rows) {
    int64_t d = (int64_t)(from & (RT_PHYS_SIZE - 1)) - (int64_t)(to & (RT_PHYS_SIZE - 1));
    if (!pitch || d % pitch) return 0;
    *rows = (int)(d / pitch);
    return 1;
}

/* Do [a, a + an) and [b, b + bn) share bytes? */
static int gl_span_hit(uint32_t a, uint32_t an, uint32_t b, uint32_t bn) {
    a &= RT_PHYS_SIZE - 1, b &= RT_PHYS_SIZE - 1;
    return an && bn && a < b + bn && b < a + an;
}

static int gl_can_copy(const GlSurf *e, const GlSurf *s) {
    int dy;
    uint32_t ec = e->cpitch * (uint32_t)e->h, ez = e->ztex && e->zdirty ? e->zpitch * (uint32_t)e->h : 0;
    uint32_t sc = s->cpitch * (uint32_t)s->h, sz = s->ztex ? s->zpitch * (uint32_t)s->h : 0;
    if (gl_span_hit(e->cbase, ec, s->cbase, sc) &&
        (e->cpitch != s->cpitch || e->bpp != s->bpp || !gl_row_offset(e->cbase, s->cbase, s->cpitch, &dy)))
        return 0;
    if (gl_span_hit(e->cbase, ec, s->zbase, sz) || gl_span_hit(e->zbase, ez, s->cbase, sc)) return 0;
    if (gl_span_hit(e->zbase, ez, s->zbase, sz) &&
        (e->zpitch != s->zpitch || e->zbpp != s->zbpp || !gl_row_offset(e->zbase, s->zbase, s->zpitch, &dy)))
        return 0;
    return 1;
}

static void gl_copy_rows(GLuint from, int from_h, uint32_t from_base, GLuint to, int to_h, uint32_t to_base, uint32_t pitch, int w) {
    int dy;
    if (!gl_row_offset(from_base, to_base, pitch, &dy)) return;
    int sy = dy < 0 ? -dy : 0, ty = dy > 0 ? dy : 0, rows = from_h - sy < to_h - ty ? from_h - sy : to_h - ty;
    if (rows > 0) glCopyImageSubData(from, GL_TEXTURE_2D, 0, 0, sy, 0, to, GL_TEXTURE_2D, 0, 0, ty, 0, w, rows, 1);
}

static void gl_copy(const GlSurf *e, GlSurf *s) {
    int w = e->w < s->w ? e->w : s->w;
    gl_copy_rows(e->ctex, e->h, e->cbase, s->ctex, s->h, s->cbase, s->cpitch, w);
    if (e->zdirty && e->ztex && s->ztex) gl_copy_rows(e->ztex, e->h, e->zbase, s->ztex, s->h, s->zbase, s->zpitch, w);
}

static void gl_free_surf(GlSurf *s) {
    if (s->fbo) glDeleteFramebuffers(1, &s->fbo);
    if (s->ctex) glDeleteTextures(1, &s->ctex);
    if (s->ztex) glDeleteTextures(1, &s->ztex);
    memset(s, 0, sizeof *s);
}

/* Brings what other framebuffers over these bytes drew since s last drew
 * into s, oldest first: copied on the GPU where the bytes line up
 * (Forza's bloom quarters of a front buffer, the same buffer with and
 * without depth), else through RAM. */
static void gl_take_newer(GlSurf *s) {
    GlSurf *newer[GL_SURFS];
    int n = 0, copy = 1;
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (e != s && e->seq > s->seq &&
            (gl_drew(e, s->cbase, s->cpitch * (uint32_t)s->h) || (s->ztex && gl_drew(e, s->zbase, s->zpitch * (uint32_t)s->h)))) {
            newer[n++] = e;
            copy &= gl_can_copy(e, s);
        }
    }
    for (int i = 1; i < n; i++) /* by seq */
        for (int j = i; j > 0 && newer[j - 1]->seq > newer[j]->seq; j--) {
            GlSurf *t = newer[j];
            newer[j] = newer[j - 1], newer[j - 1] = t;
        }
    if (copy) {
        for (int i = 0; i < n; i++) gl_copy(newer[i], s);
    } else if (n) {
        for (int i = 0; i < n; i++)
            if (newer[i]->dirty) gl_readback(newer[i]); /* s too, first, if it drew earlier */
        if (s->dirty) gl_readback(s);
        gl_upload_if_changed(s);
        s->check = 0;
    }
}

static GlSurf *gl_bind(const DrawState *d) {
    uint32_t fmt = K(SET_SURFACE_FORMAT);
    uint32_t cfmt = fmt & 15, zfmt = d->ztest || K(SET_DEPTH_MASK) ? (fmt >> 4) & 15 : 0;
    int w = (int)(d->pitch / (uint32_t)d->bpp), h = d->cy0 + d->ch; /* exact: rounded up to 16, a 160x120 one covered the cube map after it */
    uint32_t zbase = zfmt ? dma_base(SET_CONTEXT_DMA_ZETA) + K(SET_SURFACE_ZETA_OFFSET) : 0, zpitch = zfmt ? K(SET_SURFACE_PITCH) >> 16 : 0;
    if (zfmt && (zfmt > 2 || !zpitch || (uint32_t)w * (zfmt == 1 ? 2u : 4u) > zpitch)) zfmt = 0, zbase = 0, zpitch = 0;
    GlSurf *s = gl_cur;
    if (!s || s->cbase != d->base || s->cpitch != d->pitch || s->cfmt != cfmt || s->zbase != zbase || s->zfmt != zfmt ||
        s->zpitch != zpitch || s->w != w || s->h < h) {
        s = NULL;
        GlSurf *lru = &gl_surf[0];
        for (int i = 0; i < GL_SURFS && !s; i++) {
            GlSurf *e = &gl_surf[i];
            if (e->fbo && e->cbase == d->base && e->cpitch == d->pitch && e->cfmt == cfmt && e->zbase == zbase && e->zfmt == zfmt &&
                e->zpitch == zpitch && e->w == w && e->h >= h)
                s = e;
            else if (e->used < lru->used)
                lru = e;
        }
        if (!s) {
            s = lru;
            if (s->fbo && s->dirty) gl_readback(s);
            gl_complete(); /* nothing on its way refers to the slot */
            gl_free_surf(s);
            s->cbase = d->base, s->cpitch = d->pitch, s->cfmt = cfmt, s->zbase = zbase, s->zfmt = zfmt, s->zpitch = zpitch;
            s->w = w, s->h = h, s->bpp = d->bpp, s->zbpp = zfmt == 1 ? 2 : 4;
            glGenTextures(1, &s->ctex);
            glBindTexture(GL_TEXTURE_2D, s->ctex);
            glTexStorage2D(GL_TEXTURE_2D, 1, d->bpp == 4 ? GL_RGBA8 : GL_RGB565, w, h);
            glGenFramebuffers(1, &s->fbo);
            glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, s->ctex, 0);
            if (zfmt) {
                glGenTextures(1, &s->ztex);
                glBindTexture(GL_TEXTURE_2D, s->ztex);
                glTexStorage2D(GL_TEXTURE_2D, 1, zfmt == 1 ? GL_DEPTH_COMPONENT16 : GL_DEPTH24_STENCIL8, w, h);
                glFramebufferTexture2D(GL_FRAMEBUFFER, zfmt == 1 ? GL_DEPTH_ATTACHMENT : GL_DEPTH_STENCIL_ATTACHMENT, GL_TEXTURE_2D, s->ztex, 0);
            }
            if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
                fprintf(stderr, "xbrt: GL framebuffer for surface %08x (%dx%d, format %x/%x) is incomplete\n", d->base, w, h, cfmt, zfmt);
            s->chash = s->zhash = 1; /* never matches: upload */
            s->check = 1;
        }
        gl_cur = s;
        s->used = ++gl_tick;
        if (s->check && !s->dirty) gl_upload_if_changed(s);
        s->check = 0;
        gl_take_newer(s);
    }
    s->used = ++gl_tick;
    if (s->check && !s->dirty) gl_upload_if_changed(s);
    s->check = 0;
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
    glViewport(0, 0, s->w, s->h);
    return s;
}

/* A linear colour texture over a framebuffer the GPU drew (docs/GPU.md,
 * step 5): the framebuffer's own texture is sampled instead of reading it
 * back, hashing and decoding it, which Forza's downsample of the
 * anti-aliased buffer and its bloom passes did every frame. Only where
 * the bytes line up (same address, pitch and texel size, inside the
 * framebuffer), and not when the draw itself writes those bytes (GL
 * cannot read a texture it is drawing into). NULL: decode as usual. */
static Texture *gl_rt_texture(int i, uint32_t base, uint32_t pitch, uint32_t color, int w, int h) {
    static Texture rt[4];
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || w <= 0 || h <= 0) return NULL;
    int bpp = color == 0x11 ? 2 : 4;
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + pitch * (uint32_t)h;
    if (lo < draw_hi && draw_lo < hi) return NULL;
    if (lo < draw_zhi && draw_zlo < hi) return NULL; /* GL cannot sample what it draws into */
    if (color == 0x2E) { /* a shadow map: the depth of a framebuffer the GPU drew */
        GlSurf *s = NULL;
        for (int k = 0; k < GL_SURFS; k++) {
            GlSurf *e = &gl_surf[k];
            if (e->fbo && e->ztex && e->zbpp == 4 && (e->zbase & (RT_PHYS_SIZE - 1)) == lo && e->zpitch == pitch && e->w >= w &&
                e->h >= h && (!s || e->seq > s->seq))
                s = e;
        }
        if (!s || !(s->zdirty || s->zgpu)) return NULL; /* not drawn on the GPU: decode from RAM */
        if (s->check && !s->dirty) gl_upload_if_changed(s); /* the CPU may have written it since */
        s->check = 0;
        gl_take_newer(s);
        if (s->zdirty) gl_depth_stays(s);
        Texture *t = &rt[i];
        memset(t, 0, sizeof *t);
        t->w = s->w, t->h = s->h, t->linear = 1, t->levels = 1;
        t->gl = s->ztex, t->surface = 1, t->depth = 0xFFFFFF;
        t->gl_version = t->version;
        return t;
    }
    GlSurf *s = NULL;
    for (int k = 0; k < GL_SURFS; k++) {
        GlSurf *e = &gl_surf[k];
        if (e->fbo && (e->cbase & (RT_PHYS_SIZE - 1)) == lo && e->cpitch == pitch && e->bpp == bpp && e->w >= w && e->h >= h &&
            (!s || e->seq > s->seq))
            s = e;
    }
    if (!s) return NULL;
    for (int k = 0; k < GL_SURFS; k++) { /* depth drawn over these bytes after their colour (or with it, as a shadow map's): through RAM */
        GlSurf *e = &gl_surf[k];
        if (e->fbo && e->ztex && e->zdirty && (e == s || e->seq > s->seq) && gl_span_hit(e->zbase, e->zpitch * (uint32_t)e->h, lo, hi - lo))
            return NULL;
    }
    if (s->check && !s->dirty) gl_upload_if_changed(s);
    s->check = 0;
    gl_take_newer(s);
    Texture *t = &rt[i];
    memset(t, 0, sizeof *t);
    t->w = s->w, t->h = s->h, t->linear = 1, t->levels = 1;
    t->gl = s->ctex, t->surface = 1, t->alpha_one = color == 0x1E;
    t->gl_version = t->version; /* gl_texture has nothing to upload */
    return t;
}

/* CLEAR_SURFACE on the GPU: the clear rectangle (inclusive, in samples on
 * an anti-aliased surface), the channels and depth/stencil it names, from
 * SET_COLOR_CLEAR_VALUE and SET_ZSTENCIL_CLEAR_VALUE. Returns 0 for a
 * surface it cannot handle, which kelvin.c then clears in RAM. */
static int gl_clear(uint32_t flags) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready) return 0;
    uint32_t fmt = K(SET_SURFACE_FORMAT), color = fmt & 15, type = (fmt >> 8) & 15, aa = (fmt >> 12) & 15;
    DrawState d;
    memset(&d, 0, sizeof d);
    d.bpp = (color >= 4 && color <= 8) ? 4 : (color == 3) ? 2 : 0;
    if (type != 1 || !d.bpp) return 0;
    d.sx = (aa == 1 || aa == 2) ? 2 : 1, d.sy = aa == 2 ? 2 : 1;
    d.cx0 = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) & 0xFFFF) * d.sx, d.cw = (int)(K(SET_SURFACE_CLIP_HORIZONTAL) >> 16) * d.sx;
    d.cy0 = (int)(K(SET_SURFACE_CLIP_VERTICAL) & 0xFFFF) * d.sy, d.ch = (int)(K(SET_SURFACE_CLIP_VERTICAL) >> 16) * d.sy;
    d.pitch = K(SET_SURFACE_PITCH) & 0xFFFF;
    d.base = dma_base(SET_CONTEXT_DMA_COLOR) + K(SET_SURFACE_COLOR_OFFSET);
    if (!d.pitch || (uint32_t)(d.cx0 + d.cw) * (uint32_t)d.bpp > d.pitch) return 0;
    d.ztest = (flags & 3) != 0; /* attach the depth buffer */
    GlSurf *s = gl_bind(&d);
    if ((flags & 3) && !s->ztex) return 0;
    uint32_t x1 = K(SET_CLEAR_RECT_HORIZONTAL) & 0xFFFF, x2 = K(SET_CLEAR_RECT_HORIZONTAL) >> 16;
    uint32_t y1 = K(SET_CLEAR_RECT_VERTICAL) & 0xFFFF, y2 = K(SET_CLEAR_RECT_VERTICAL) >> 16;
    if (x2 < x1 || y2 < y1) return 1;
    glEnable(GL_SCISSOR_TEST);
    glScissor((GLint)x1 * d.sx, (GLint)y1 * d.sy, (GLsizei)(x2 - x1 + 1) * d.sx, (GLsizei)(y2 - y1 + 1) * d.sy);
    GLbitfield bits = 0;
    if (flags & 0xF0) {
        float c[4];
        argb(K(SET_COLOR_CLEAR_VALUE), c);
        glColorMask((flags & 0x10) != 0, (flags & 0x20) != 0, (flags & 0x40) != 0, (flags & 0x80) != 0);
        glClearColor(c[0], c[1], c[2], c[3]);
        bits |= GL_COLOR_BUFFER_BIT;
    }
    uint32_t zv = K(SET_ZSTENCIL_CLEAR_VALUE);
    if (flags & 1) {
        glDepthMask(GL_TRUE);
        glClearDepth(s->zbpp == 4 ? (double)(zv >> 8) / 16777215.0 : (double)(zv & 0xFFFF) / 65535.0);
        bits |= GL_DEPTH_BUFFER_BIT;
    }
    if ((flags & 2) && s->zbpp == 4) {
        glClearStencil((GLint)(zv & 0xFF));
        bits |= GL_STENCIL_BUFFER_BIT;
    }
    glClear(bits);
    s->dirty = s->cdirty = 1, s->seq = ++gl_seq;
    if (flags & 3) s->zdirty = 1, s->zgpu = 0;
    return 1;
}

/* ---- textures ---- */

static GLuint gl_texture(Texture *t) {
    if (t->gl && t->gl_version == t->version) return t->gl;
    if (t->gl) glDeleteTextures(1, &t->gl);
    glGenTextures(1, &t->gl);
    GLenum target = t->cube ? GL_TEXTURE_CUBE_MAP : GL_TEXTURE_2D;
    glBindTexture(target, t->gl);
    if (t->depth) { /* depth values, compared in the shader */
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_R32F, t->w, t->h);
        float *f = malloc((size_t)t->w * t->h * sizeof *f);
        for (int i = 0; i < t->w * t->h; i++) f[i] = (float)t->texels[i];
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, t->w, t->h, GL_RED, GL_FLOAT, f);
        free(f);
    } else { /* with the game's own mipmaps, as texture() decoded them */
        glTexStorage2D(target, t->levels, GL_RGBA8, t->w, t->h);
        for (int f = 0; f < (t->cube ? 6 : 1); f++) {
            const uint32_t *p = t->texels + (size_t)f * t->face_texels;
            for (int l = 0; l < t->levels; l++) {
                int lw = t->w >> l > 1 ? t->w >> l : 1, lh = t->h >> l > 1 ? t->h >> l : 1;
                glTexSubImage2D(t->cube ? GL_TEXTURE_CUBE_MAP_POSITIVE_X + (GLenum)f : GL_TEXTURE_2D, l, 0, 0, lw, lh, GL_BGRA,
                                GL_UNSIGNED_INT_8_8_8_8_REV, p);
                p += (size_t)lw * lh;
            }
        }
    }
    glTexParameteri(target, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(target, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    t->gl_version = t->version;
    return t->gl;
}

/* SET_TEXTURE_FILTER: the LOD bias in bits 0-12 (signed, 8 fraction bits),
 * the minifying filter in 16-21 and the magnifying one in 24-27, numbered
 * as xemu reads them (NV_PGRAPH_TEXFILTER0): 1 nearest, 2 linear, 3-6 the
 * four mipmap combinations in OpenGL's order, 7 (min) or 4 (mag) the
 * Gaussian "convolution" filter, which linear stands in for. Depth
 * textures stay point sampled: the shader compares each texel itself. */
static void gl_filter(GLenum target, const Texture *t, uint32_t filt) {
    static const GLint mins[8] = {GL_NEAREST, GL_NEAREST, GL_LINEAR, GL_NEAREST_MIPMAP_NEAREST, GL_LINEAR_MIPMAP_NEAREST,
                                  GL_NEAREST_MIPMAP_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_LINEAR};
    uint32_t mn = (filt >> 16) & 0x3F, mg = (filt >> 24) & 15;
    GLint min = t->depth ? GL_NEAREST : mn < 8 ? mins[mn] : GL_LINEAR;
    GLint mag = t->depth || mg <= 1 ? GL_NEAREST : GL_LINEAR;
    int32_t bias = (int32_t)(filt << 19) >> 19;
    glTexParameteri(target, GL_TEXTURE_MIN_FILTER, min);
    glTexParameteri(target, GL_TEXTURE_MAG_FILTER, mag);
    glTexParameterf(target, GL_TEXTURE_LOD_BIAS, (float)bias / 256.0f);
}

static GLint gl_wrap(uint32_t mode) {
    return mode == 2 ? GL_MIRRORED_REPEAT : (mode == 1 || mode == 0) ? GL_REPEAT : GL_CLAMP_TO_EDGE;
}

/* ---- drawing ---- */

static float *gl_verts;
static int gl_verts_cap;

static void gl_put(float *v, const Pt *p) {
    v[0] = p->x, v[1] = p->y, v[2] = p->z, v[3] = p->iw;
    memcpy(v + 4, p->c, 4 * sizeof(float));
    memcpy(v + 8, p->c1, 4 * sizeof(float));
    memcpy(v + 12, p->tc, 16 * sizeof(float));
    v[28] = p->fog;
}

static void gl_uniform_argb(GLint loc, uint32_t v) {
    float f[4];
    argb(v, f);
    glUniform4fv(loc, 1, f);
}

static void gl_frag_state(const DrawState *d, const GlSurf *s);

static void gl_draw(const DrawState *d, const Tri *tri, int n) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || !n) return;
    GlSurf *s = gl_bind(d);
    gl_use(&gl_main);

    if (n * 3 * GL_VERT > gl_verts_cap) {
        gl_verts_cap = n * 3 * GL_VERT * 2;
        gl_verts = realloc(gl_verts, (size_t)gl_verts_cap * sizeof *gl_verts);
    }
    for (int i = 0; i < n; i++) {
        gl_put(gl_verts + (i * 3 + 0) * GL_VERT, &tri[i].a);
        gl_put(gl_verts + (i * 3 + 1) * GL_VERT, &tri[i].b);
        gl_put(gl_verts + (i * 3 + 2) * GL_VERT, &tri[i].c);
    }
    glBindVertexArray(gl_vao);
    glBindBuffer(GL_ARRAY_BUFFER, gl_vbo);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)n * 3 * GL_VERT * sizeof(float), gl_verts, GL_STREAM_DRAW);
    gl_frag_state(d, s);
    glDrawArrays(GL_TRIANGLES, 0, n * 3);
    s->dirty = s->cdirty = 1, s->seq = ++gl_seq;
    if (d->ztest && d->zwrite && s->ztex) s->zdirty = 1, s->zgpu = 0;
}

/* The program's uniforms for the pixel side (the combiners, the texture
 * stages, alpha test, fog colour) and the fixed-function state, from the
 * methods, for a draw to s. */
static void gl_frag_state(const DrawState *d, const GlSurf *s) {
    float size[2] = {(float)s->w, (float)s->h};
    glUniform2fv(u_size, 1, size);
    glUniform1f(u_zmax, d->zmax);

    /* The combiners, as combine() reads them. */
    GLuint cicw[8], cocw[8], aicw[8], aocw[8];
    float c0[8][4], c1[8][4];
    for (int i = 0; i < 8; i++) {
        cicw[i] = K(SET_COMBINER_COLOR_ICW + 4 * i), cocw[i] = K(SET_COMBINER_COLOR_OCW + 4 * i);
        aicw[i] = K(SET_COMBINER_ALPHA_ICW + 4 * i), aocw[i] = K(SET_COMBINER_ALPHA_OCW + 4 * i);
        argb(K(SET_COMBINER_FACTOR0 + 4 * i), c0[i]);
        argb(K(SET_COMBINER_FACTOR1 + 4 * i), c1[i]);
    }
    glUniform1uiv(u_cicw, 8, cicw), glUniform1uiv(u_cocw, 8, cocw), glUniform1uiv(u_aicw, 8, aicw), glUniform1uiv(u_aocw, 8, aocw);
    glUniform4fv(u_c0, 8, &c0[0][0]), glUniform4fv(u_c1, 8, &c1[0][0]);
    gl_uniform_argb(u_fc0, K(SET_SPECULAR_FOG_FACTOR)), gl_uniform_argb(u_fc1, K(SET_SPECULAR_FOG_FACTOR + 4));
    glUniform1ui(u_ctl, K(SET_COMBINER_CONTROL));
    glUniform1ui(u_f0, K(SET_COMBINER_SPECULAR_FOG_CW0)), glUniform1ui(u_f1, K(SET_COMBINER_SPECULAR_FOG_CW1));

    /* Texture stages. */
    GLint mode[4], kind[4];
    float scale[8], dmax[4];
    for (int i = 0; i < 4; i++) {
        Texture *t = d->tex[i];
        mode[i] = d->mode[i];
        kind[i] = !t ? 0 : t->depth ? (t->surface ? 4 : 3) : t->cube ? 2 : 1;
        scale[2 * i] = t && t->linear ? 1.0f / (float)t->w : 1.0f;
        scale[2 * i + 1] = t && t->linear ? 1.0f / (float)t->h : 1.0f;
        dmax[i] = t ? (float)t->depth : 0;
        glActiveTexture(GL_TEXTURE0 + (GLenum)i);
        glBindTexture(GL_TEXTURE_2D, t && !t->cube ? gl_texture(t) : gl_dummy2d);
        if (t && t->surface && !t->depth) /* X8R8G8B8 over a framebuffer that keeps alpha */
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_A, t->alpha_one ? GL_ONE : GL_ALPHA);
        if (t && !t->cube) {
            uint32_t addr = KT(SET_TEXTURE_ADDRESS);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, gl_wrap(addr & 15));
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, gl_wrap((addr >> 8) & 15));
            gl_filter(GL_TEXTURE_2D, t, KT(SET_TEXTURE_FILTER));
        }
        glActiveTexture(GL_TEXTURE4 + (GLenum)i);
        glBindTexture(GL_TEXTURE_CUBE_MAP, t && t->cube ? gl_texture(t) : gl_dummycube);
        if (t && t->cube) gl_filter(GL_TEXTURE_CUBE_MAP, t, KT(SET_TEXTURE_FILTER));
    }
    glActiveTexture(GL_TEXTURE0);
    glUniform1iv(u_mode, 4, mode), glUniform1iv(u_kind, 4, kind), glUniform2fv(u_scale, 4, scale), glUniform1fv(u_dmax, 4, dmax);
    glUniform1i(u_shadow_func, (GLint)(K(SET_SHADOW_DEPTH_FUNC) & 7));
    glUniform1i(u_alpha_func, K(SET_ALPHA_TEST_ENABLE) ? (GLint)K(SET_ALPHA_FUNC) : 0);
    glUniform1f(u_alpha_ref, (float)(K(SET_ALPHA_REF) & 255) / 255.0f);
    float fogc[3];
    fog_color(fogc);
    glUniform3fv(u_fogc, 1, fogc);

    /* Fixed-function state: the NV2A uses OpenGL's own values. */
    if (d->blend) {
        glEnable(GL_BLEND);
        glBlendFuncSeparate(d->sf, d->df, d->sf, d->df);
        glBlendEquation(d->eq ? d->eq : GL_FUNC_ADD);
        glBlendColor(d->cc[0], d->cc[1], d->cc[2], d->cc[3]);
    } else {
        glDisable(GL_BLEND);
    }
    if (d->ztest && s->ztex) {
        glEnable(GL_DEPTH_TEST);
        glDepthFunc(d->zfunc);
        glDepthMask(d->zwrite ? GL_TRUE : GL_FALSE);
    } else {
        glDisable(GL_DEPTH_TEST);
    }
    glColorMask((d->wm & 0x00FF0000u) != 0, (d->wm & 0x0000FF00u) != 0, (d->wm & 0x000000FFu) != 0, (d->wm & 0xFF000000u) != 0);
    glDisable(GL_CULL_FACE);
    glEnable(GL_SCISSOR_TEST);
    glScissor(d->cx0, d->cy0, d->cw, d->ch);
}
