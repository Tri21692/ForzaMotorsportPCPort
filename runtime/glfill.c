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
    "uniform int u_kind[4];\n"      /* 0 none, 1 2D, 2 cube, 3 depth */
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
    "    if (u_kind[i] == 3) {\n" /* a shadow map: compare, as xemu does */
    "        float qw = q.w != 0.0 ? q.w : 1.0;\n"
    "        float d = texture(t, q.xy / qw * u_scale[i]).r;\n"
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
static GLuint gl_prog, gl_vao, gl_vbo, gl_dummy2d, gl_dummycube;
static GLint u_size, u_zmax, u_cicw, u_cocw, u_aicw, u_aocw, u_c0, u_c1, u_fc0, u_fc1, u_ctl, u_f0, u_f1;
static GLint u_fogc, u_mode, u_kind, u_scale, u_dmax, u_shadow_func, u_alpha_func, u_alpha_ref, u_tex[4], u_cube[4];

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

static int gl_setup(void) {
    GLuint vs = compile(GL_VERTEX_SHADER, vs_src), fs = compile(GL_FRAGMENT_SHADER, fs_src);
    if (!vs || !fs) return 0;
    gl_prog = glCreateProgram();
    glAttachShader(gl_prog, vs);
    glAttachShader(gl_prog, fs);
    glLinkProgram(gl_prog);
    GLint ok = 0;
    glGetProgramiv(gl_prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetProgramInfoLog(gl_prog, sizeof log, NULL, log);
        fprintf(stderr, "xbrt: GL program does not link:\n%s\n", log);
        return 0;
    }
#define LOC(v, n) v = glGetUniformLocation(gl_prog, n)
    LOC(u_size, "u_size"), LOC(u_zmax, "u_zmax"), LOC(u_cicw, "u_cicw"), LOC(u_cocw, "u_cocw"), LOC(u_aicw, "u_aicw");
    LOC(u_aocw, "u_aocw"), LOC(u_c0, "u_c0"), LOC(u_c1, "u_c1"), LOC(u_fc0, "u_fc0"), LOC(u_fc1, "u_fc1"), LOC(u_ctl, "u_ctl");
    LOC(u_f0, "u_f0"), LOC(u_f1, "u_f1"), LOC(u_mode, "u_mode"), LOC(u_kind, "u_kind"), LOC(u_scale, "u_scale");
    LOC(u_dmax, "u_dmax"), LOC(u_shadow_func, "u_shadow_func"), LOC(u_alpha_func, "u_alpha_func"), LOC(u_alpha_ref, "u_alpha_ref"), LOC(u_fogc, "u_fogc");
    LOC(u_tex[0], "u_tex0"), LOC(u_tex[1], "u_tex1"), LOC(u_tex[2], "u_tex2"), LOC(u_tex[3], "u_tex3");
    LOC(u_cube[0], "u_cube0"), LOC(u_cube[1], "u_cube1"), LOC(u_cube[2], "u_cube2"), LOC(u_cube[3], "u_cube3");
#undef LOC
    glUseProgram(gl_prog);
    for (int i = 0; i < 4; i++) glUniform1i(u_tex[i], i), glUniform1i(u_cube[i], 4 + i); /* 2D on units 0-3, cubes on 4-7 */
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
    int check;             /* RAM may have changed: compare hashes before the next draw */
    unsigned used;
} GlSurf;

static GlSurf gl_surf[16];
static GlSurf *gl_cur;
static unsigned gl_tick;

static uint64_t hash_bytes(const uint8_t *p, uint32_t n) {
    uint64_t h = 0x9E3779B97F4A7C15ull ^ n;
    uint32_t k = 0;
    for (; k + 8 <= n; k += 8) {
        uint64_t v;
        memcpy(&v, p + k, 8);
        h = (h ^ v) * 0x100000001B3ull;
        h ^= h >> 29;
    }
    for (; k < n; k++) h = (h ^ p[k]) * 0x100000001B3ull;
    return h;
}

static int gl_fits(uint32_t base, uint32_t pitch, int h) {
    return (uint64_t)(base & (RT_PHYS_SIZE - 1)) + (uint64_t)pitch * (uint64_t)h <= RT_PHYS_SIZE;
}

static void gl_readback(GlSurf *s) {
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
    if (gl_fits(s->cbase, s->cpitch, s->h)) {
        glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, phys(s->cbase));
        else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, phys(s->cbase));
        s->chash = hash_bytes(phys(s->cbase), s->cpitch * (uint32_t)s->h);
    }
    if (s->ztex && gl_fits(s->zbase, s->zpitch, s->h)) {
        glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->zpitch / (uint32_t)s->zbpp));
        if (s->zbpp == 4) glReadPixels(0, 0, s->w, s->h, GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8, phys(s->zbase));
        else glReadPixels(0, 0, s->w, s->h, GL_DEPTH_COMPONENT, GL_UNSIGNED_SHORT, phys(s->zbase));
        s->zhash = hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h);
    }
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    s->dirty = 0;
}

static int gl_overlaps(const GlSurf *s, uint32_t base, uint32_t size) {
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + size;
    uint32_t c0 = s->cbase & (RT_PHYS_SIZE - 1), c1 = c0 + s->cpitch * (uint32_t)s->h;
    uint32_t z0 = s->zbase & (RT_PHYS_SIZE - 1), z1 = z0 + s->zpitch * (uint32_t)s->h;
    return (lo < c1 && c0 < hi) || (s->ztex && lo < z1 && z0 < hi);
}

/* Brings RAM up to date with what the GPU drew, on every surface it drew
 * to: switching surfaces does not read back, only something that can look
 * at RAM does (a texture over a surface, the CPU after a fence or a flip). */
static void gl_sync(void) {
    for (int i = 0; i < 16; i++)
        if (gl_surf[i].fbo && gl_surf[i].dirty) gl_readback(&gl_surf[i]);
}

/* After a point where the CPU may write RAM (a fence, a notify, a flip) or
 * a clear that works on RAM, each surface is checked against its hash
 * before it is drawn to again. Between those points nothing else writes
 * them; hashing before every draw cost more than the drawing. */
static void gl_sync_cpu(void) {
    gl_sync();
    for (int i = 0; i < 16; i++) gl_surf[i].check = 1;
}

/* Would reading these bytes see what the GPU has drawn but not read back? */
static int gl_writes(uint32_t base, uint32_t size) {
    for (int i = 0; i < 16; i++)
        if (gl_surf[i].fbo && gl_surf[i].dirty && gl_overlaps(&gl_surf[i], base, size)) return 1;
    return 0;
}

static void gl_upload_if_changed(GlSurf *s) {
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

static void gl_free_surf(GlSurf *s) {
    if (s->fbo) glDeleteFramebuffers(1, &s->fbo);
    if (s->ctex) glDeleteTextures(1, &s->ctex);
    if (s->ztex) glDeleteTextures(1, &s->ztex);
    memset(s, 0, sizeof *s);
}

static GlSurf *gl_bind(const DrawState *d) {
    uint32_t fmt = K(SET_SURFACE_FORMAT);
    uint32_t cfmt = fmt & 15, zfmt = d->ztest || K(SET_DEPTH_MASK) ? (fmt >> 4) & 15 : 0;
    int w = (int)(d->pitch / (uint32_t)d->bpp), h = (d->cy0 + d->ch + 15) & ~15;
    uint32_t zbase = zfmt ? dma_base(SET_CONTEXT_DMA_ZETA) + K(SET_SURFACE_ZETA_OFFSET) : 0, zpitch = zfmt ? K(SET_SURFACE_PITCH) >> 16 : 0;
    if (zfmt && (zfmt > 2 || !zpitch || (uint32_t)w * (zfmt == 1 ? 2u : 4u) > zpitch)) zfmt = 0, zbase = 0, zpitch = 0;
    GlSurf *s = gl_cur;
    if (!s || s->cbase != d->base || s->cpitch != d->pitch || s->cfmt != cfmt || s->zbase != zbase || s->zfmt != zfmt ||
        s->zpitch != zpitch || s->w != w || s->h < h) {
        s = NULL;
        GlSurf *lru = &gl_surf[0];
        for (int i = 0; i < 16 && !s; i++) {
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
    }
    s->used = ++gl_tick;
    if (s->check) gl_upload_if_changed(s), s->check = 0;
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
    glViewport(0, 0, s->w, s->h);
    return s;
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
    s->dirty = 1;
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

static void gl_draw(const DrawState *d, const Tri *tri, int n) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || !n) return;
    GlSurf *s = gl_bind(d);
    glUseProgram(gl_prog);

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
        kind[i] = !t ? 0 : t->depth ? 3 : t->cube ? 2 : 1;
        scale[2 * i] = t && t->linear ? 1.0f / (float)t->w : 1.0f;
        scale[2 * i + 1] = t && t->linear ? 1.0f / (float)t->h : 1.0f;
        dmax[i] = t ? (float)t->depth : 0;
        glActiveTexture(GL_TEXTURE0 + (GLenum)i);
        glBindTexture(GL_TEXTURE_2D, t && !t->cube ? gl_texture(t) : gl_dummy2d);
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

    glDrawArrays(GL_TRIANGLES, 0, n * 3);
    s->dirty = 1;
}
