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
    "invariant gl_Position;\n" /* the same position from every program: see vsh_glsl */
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
    "noperspective out float v_zs;\n" /* screen z, Xbox units */
    "out float v_w;\n"                /* w, interpolated with perspective: the w-buffer's depth */
    "void main() {\n"
    "    float w = a_pos.w != 0.0 ? 1.0 / a_pos.w : 1.0;\n"
    "    v_zs = a_pos.z; v_w = w;\n"
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
    "noperspective in float v_zs;\n"
    "in float v_w;\n"
    "out vec4 o_color;\n"
    "uniform vec4 u_zr;\n"   /* depth: units in the buffer (65535 or 16777215), clip min, clip max, w-buffer on */
    "uniform vec3 u_zoff;\n" /* polygon offset: bias, factor, the render scale (slopes are per Xbox pixel) */
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
    "vec4 R[16], P[16];\n" /* P: the registers before the stage, which both its halves read */
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
    "vec4 reg(uint r) { return r == 15u ? vec4(E * F, 0.0) : P[r]; }\n"
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
    "bool mux_sel(bool msb) { float r0a = P[12].a; return msb ? r0a >= 0.5 : (int(r0a * 255.0) & 1) != 0; }\n"
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
    "        float r = u_mode[i] == 2 ? clamp(q.z / qw, 0.0, u_dmax[i]) : 0.0;\n"
    /* Four texels compared and blended by position (bilinear percentage-
     * closer filtering), as the NV2A does with a linear filter: one
     * nearest texel made shadow edges crawl as the camera moved. (The
     * buildings and signs flickering in the race are the 60 fps patch's:
     * at XBRT_FPS=30 they do not.) */
    "        vec2 sz = vec2(textureSize(t, 0));\n"
    "        vec2 uv = q.xy / qw * u_scale[i] * sz - 0.5, f = fract(uv), base = (floor(uv) + 0.5) / sz;\n"
    "        float c[4];\n"
    "        for (int k = 0; k < 4; k++) {\n"
    "            float d = texture(t, base + vec2(k & 1, k >> 1) / sz).r;\n"
    "            if (u_kind[i] == 4) d = floor(d * u_dmax[i] + 0.5);\n" /* GL's depth is 0..1: back to the Xbox's units */
    "            c[k] = compare(u_shadow_func, d, r) ? 1.0 : 0.0;\n"
    "        }\n"
    "        return vec4(mix(mix(c[0], c[1], f.x), mix(c[2], c[3], f.x), f.y));\n"
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
    "        P = R;\n" /* the alpha half reading what the RGB half just wrote took the car paint's unshadowed light (0.7 x T2.b) from a dot product */
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
    "        P = R;\n"
    "        vec3 e = in_rgb(u_f1 >> 24 & 255u), f = in_rgb(u_f1 >> 16 & 255u);\n"
    "        E = e; F = f;\n"
    "        vec3 a = in_rgb(u_f0 >> 24 & 255u), b = in_rgb(u_f0 >> 16 & 255u), c = in_rgb(u_f0 >> 8 & 255u), d = in_rgb(u_f0 & 255u);\n"
    "        o.rgb = clamp(d + a * b + (1.0 - a) * c, 0.0, 1.0);\n"
    "        o.a = clamp(in_a(u_f1 >> 8 & 255u), 0.0, 1.0);\n"
    "    }\n"
    "#ifndef NO_ALPHA_TEST\n"
    "    if (u_alpha_func != 0 && !compare(u_alpha_func - 0x200, o.a, u_alpha_ref)) discard;\n"
    "#endif\n"
    "    o_color = o;\n"
    "#ifndef NO_FRAG_DEPTH\n"
    /* The NV2A's depth, as xemu works it out: screen z, or w when the
     * w-buffer is on (CONTROL0 Z_PERSPECTIVE), plus the polygon offset
     * (bias, and factor times the depth slope), clamped to the clip range.
     * Forza draws road markings, kerbs and skid marks with offsets; without
     * them they fought the road and flickered. */
    "    float z = u_zr.w > 0.5 ? v_w : gl_FragCoord.z * u_zr.x;\n" /* the GPU's own depth unless w-buffering: passes must match exactly */
    "    if (u_zoff.x != 0.0 || u_zoff.y != 0.0) {\n"
    "        float slope = max(abs(dFdx(z)), abs(dFdy(z))) * u_zoff.z;\n"
    "        z += u_zoff.x + (isinf(slope) || isnan(slope) ? 0.0 : u_zoff.y * slope);\n"
    "    }\n"
    "    if (u_zr.w > 0.5 || u_zoff.x != 0.0 || u_zoff.y != 0.0) z = clamp(z, u_zr.y, u_zr.z);\n"
    "    gl_FragDepth = isnan(z) ? gl_FragCoord.z : clamp(z / u_zr.x, 0.0, 1.0);\n"
    "#endif\n"
    "}\n";

#define GL_VERT 29 /* floats per vertex */

static int gl_ready = -1; /* -1 not set up, 0 failed, 1 ready */
static GLuint gl_fs, gl_vao, gl_vbo, gl_dummy2d, gl_dummycube;
static int gl_k = 1; /* XBRT_GL_SCALE: see gl_proxy */
static GLint u_size, u_zmax, u_cicw, u_cocw, u_aicw, u_aocw, u_c0, u_c1, u_fc0, u_fc1, u_ctl, u_f0, u_f1;
static GLint u_fogc, u_mode, u_kind, u_scale, u_dmax, u_shadow_func, u_alpha_func, u_alpha_ref, u_tex[4], u_cube[4], u_zr, u_zoff;

/* A linked program and its uniforms' locations: the CPU path's vertex
 * shader, or one made from a vertex program (glvsh.c), each with the one
 * fragment shader. gl_use makes the u_* names above refer to its own. */
static GLint *const gl_loc_var[] = {&u_size, &u_zmax, &u_cicw, &u_cocw, &u_aicw, &u_aocw, &u_c0, &u_c1, &u_fc0, &u_fc1,
                                    &u_ctl, &u_f0, &u_f1, &u_fogc, &u_mode, &u_kind, &u_scale, &u_dmax, &u_shadow_func,
                                    &u_alpha_func, &u_alpha_ref, &u_tex[0], &u_tex[1], &u_tex[2], &u_tex[3], &u_cube[0],
                                    &u_cube[1], &u_cube[2], &u_cube[3], &u_zr, &u_zoff};
static const char *const gl_loc_name[] = {"u_size", "u_zmax", "u_cicw", "u_cocw", "u_aicw", "u_aocw", "u_c0", "u_c1", "u_fc0",
                                          "u_fc1", "u_ctl", "u_f0", "u_f1", "u_fogc", "u_mode", "u_kind", "u_scale", "u_dmax",
                                          "u_shadow_func", "u_alpha_func", "u_alpha_ref", "u_tex0", "u_tex1", "u_tex2", "u_tex3",
                                          "u_cube0", "u_cube1", "u_cube2", "u_cube3", "u_zr", "u_zoff"};
#define GL_NLOC (int)(sizeof gl_loc_var / sizeof gl_loc_var[0])

typedef struct GlProg GlProg;
struct GlProg {
    GLuint prog, vs;
    GLint loc[GL_NLOC];
    GLint vc, sxy, fog; /* a vertex program's: constants, sample scale, fog */
    GlProg *var[4];     /* by gl_frag_variant(), linked when first used; [0] is this one */
};

static GlProg gl_main, *gl_using;

/* Compiled on the driver's threads (rt_gl_parallel); a failure shows when
 * the program it is linked into does not link. */
static GLuint compile_nowait(GLenum type, const char *src) {
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    return s;
}

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

/* The fragment shader without what a draw does not need, by bit: 1 no
 * gl_FragDepth (the depth is the GPU's own: no polygon offset, no
 * w-buffer), 2 no alpha test. Writing gl_FragDepth, or discarding, turns
 * the GPU's early depth test off: every hidden pixel was shaded, and the
 * race at 2x was held back by the GPU (60 fps at 1x, ~45 at 2x). */
static GLuint gl_fs_var[4];

static GLuint gl_fs_variant(int var) {
    if (!var) return gl_fs;
    if (!gl_fs_var[var]) {
        char head[128];
        snprintf(head, sizeof head, "#version 430\n%s%s", var & 1 ? "#define NO_FRAG_DEPTH\n" : "",
                 var & 2 ? "#define NO_ALPHA_TEST\n" : "");
        size_t n = strlen(head) + strlen(fs_src);
        char *src = malloc(n + 1);
        strcpy(src, head), strcat(src, fs_src + strlen("#version 430\n"));
        gl_fs_var[var] = compile(GL_FRAGMENT_SHADER, src);
        free(src);
    }
    return gl_fs_var[var];
}

static int gl_link_fs(GlProg *p, GLuint vs, GLuint fs);

/* Links vs with the fragment shader into p. */
static int gl_link(GlProg *p, GLuint vs) {
    p->vs = vs, p->var[0] = p;
    return gl_link_fs(p, vs, gl_fs);
}

/* p's variant var (gl_fs_variant), or p itself if it cannot be made. */
static GlProg *gl_variant(GlProg *p, int var) {
    if (!var || !p->vs) return p;
    if (!p->var[var]) {
        GlProg *v = calloc(1, sizeof *v);
        GLuint fs = gl_fs_variant(var);
        if (!fs || !gl_link_fs(v, p->vs, fs)) {
            free(v);
            p->vs = 0; /* no more tries */
            return p;
        }
        p->var[var] = v;
    }
    return p->var[var];
}

/* Linking in two halves: started (the driver may link on its own thread,
 * rt_gl_parallel), then finished when gl_link_done says it is, without
 * waiting in between. */
static void gl_link_start(GlProg *p, GLuint vs, GLuint fs) {
    p->prog = glCreateProgram();
    glAttachShader(p->prog, vs);
    glAttachShader(p->prog, fs);
    glLinkProgram(p->prog);
}

static int gl_link_done(const GlProg *p) {
    GLint done = 1;
    if (rt_gl_parallel) glGetProgramiv(p->prog, GL_COMPLETION_STATUS, &done);
    return done;
}

static int gl_link_finish(GlProg *p);

static int gl_link_fs(GlProg *p, GLuint vs, GLuint fs) {
    gl_link_start(p, vs, fs);
    return gl_link_finish(p);
}

static int gl_link_finish(GlProg *p) {
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
    /* The NV2A clamps depth and does not clip at the near and far planes.
     * Without this, geometry at the far plane (Forza's sky) sat on the clip
     * boundary, and NVIDIA's GL dropped it: black patches over the sky. */
    glEnable(GL_DEPTH_CLAMP);
    gl_k = getenv("XBRT_GL_SCALE") ? atoi(getenv("XBRT_GL_SCALE")) : 2;
    if (gl_k < 1) gl_k = 1;
    if (gl_k > 4) gl_k = 4;
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
    uint64_t csig, zsig;   /* hash_sparse of RAM at the last full comparison (gl_upload_if_changed) */
    uint32_t sig_checks;
    int swz;               /* a swizzled surface: its colour is in Morton order in RAM (gl_to_ram, gl_from_ram) */
    int k;                 /* drawn at k times its size (XBRT_GL_SCALE); RAM sees it through the proxy below */
    GLuint pfbo, ptex, pztex; /* the proxy: the same surface at its own size, for read-backs and uploads */
    int rx0, ry0, rx1, ry1; /* what it ever drew (clip rectangles, in its pixels): all another framebuffer takes from it */
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
static void gl_ram_written(const void *by, uint32_t base, uint32_t size);
static void gl_complete_range(uint32_t base, uint32_t size);
static void gl_sync_range(uint32_t base, uint32_t size);

/* ---- drawing at a higher resolution (XBRT_GL_SCALE=<k>, default 2) ----
 * Every framebuffer the game draws, except swizzled ones, is k times its
 * size on the GPU. Whatever goes to RAM is filtered down to the surface's
 * own size first (a proxy framebuffer, blitted into), and whatever comes
 * from RAM is uploaded to the proxy and blitted up. The shown picture
 * reaches RAM at 640x480 as before, so this is supersampling: edges and
 * thin geometry (fences, wires, distant trees) come out smooth. */

static void gl_proxy(GlSurf *s) {
    if (s->pfbo) return;
    glGenFramebuffers(1, &s->pfbo);
    glBindFramebuffer(GL_FRAMEBUFFER, s->pfbo);
    glGenTextures(1, &s->ptex);
    glBindTexture(GL_TEXTURE_2D, s->ptex);
    glTexStorage2D(GL_TEXTURE_2D, 1, s->bpp == 4 ? GL_RGBA8 : GL_RGB565, s->w, s->h);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, s->ptex, 0);
    if (s->ztex) {
        glGenTextures(1, &s->pztex);
        glBindTexture(GL_TEXTURE_2D, s->pztex);
        glTexStorage2D(GL_TEXTURE_2D, 1, s->zbpp == 2 ? GL_DEPTH_COMPONENT16 : GL_DEPTH24_STENCIL8, s->w, s->h);
        glFramebufferTexture2D(GL_FRAMEBUFFER, s->zbpp == 2 ? GL_DEPTH_ATTACHMENT : GL_DEPTH_STENCIL_ATTACHMENT, GL_TEXTURE_2D, s->pztex, 0);
    }
}

static GLbitfield gl_zbits(const GlSurf *s) { return s->zbpp == 4 ? GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT : GL_DEPTH_BUFFER_BIT; }

/* Blits between a surface and its proxy, with nothing masked off. Colour
 * is filtered (box, by blitting through LINEAR at an integer ratio: each
 * proxy pixel averages its k x k samples when k is 2), depth is sampled. */
static void gl_blit(GLuint from, int fw, int fh, GLuint to, int tw, int th, GLbitfield bits) {
    glDisable(GL_SCISSOR_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDepthMask(GL_TRUE);
    glStencilMask(0xFF);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, from);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, to);
    if (bits & GL_COLOR_BUFFER_BIT) glBlitFramebuffer(0, 0, fw, fh, 0, 0, tw, th, GL_COLOR_BUFFER_BIT, GL_LINEAR);
    if (bits & ~GL_COLOR_BUFFER_BIT) glBlitFramebuffer(0, 0, fw, fh, 0, 0, tw, th, bits & ~GL_COLOR_BUFFER_BIT, GL_NEAREST);
}

/* Binds what glReadPixels should read s from: s itself, or its proxy with
 * these buffers brought down to it. */
static void gl_read_bind(GlSurf *s, GLbitfield bits) {
    if (s->k == 1) {
        glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
        return;
    }
    gl_proxy(s);
    gl_blit(s->fbo, s->w * s->k, s->h * s->k, s->pfbo, s->w, s->h, bits);
    glBindFramebuffer(GL_FRAMEBUFFER, s->pfbo);
}

/* The texture an upload from RAM goes into, and the blit that brings it to s. */
static GLuint gl_up_tex(GlSurf *s, int depth) {
    if (s->k == 1) return depth ? s->ztex : s->ctex;
    gl_proxy(s);
    return depth ? s->pztex : s->ptex;
}

static void gl_up_done(GlSurf *s, GLbitfield bits) {
    if (s->k == 1) return;
    gl_blit(s->pfbo, s->w, s->h, s->fbo, s->w * s->k, s->h * s->k, bits);
    glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
}

/* ---- presenting at the drawn resolution ----
 * At each vertical blank the buffer the CRTC shows is read from its
 * framebuffer at the size it was drawn (640k x 480k), into a pixel buffer
 * object, and handed to the display one blank later (rt_gl_frame): the
 * window, screenshots and recordings show the 2x picture instead of RAM's
 * 640x480. Only while the GPU keeps drawing that buffer; otherwise (and
 * for movies, which come through the video overlay) the display takes RAM. */
typedef struct {
    uint32_t base;
    GLuint tex, fbo;
    int w, h;
    unsigned seq;
} GlSnap;
#define GL_SNAPS 8
static GlSnap gl_snap[GL_SNAPS];

/* The frames to show, in the order they were finished (copied at their
 * flips), one taken at each vertical blank that takes a frame off the
 * queue (nv2a.drained). Showing whatever buffer the CRTC pointed at
 * instead skipped and repeated frames whenever two flipped within one
 * blank: menus and the camera turning around the car judder. Four slots:
 * two frames queued at most, the one shown, and one spare. */
#define GL_FIFO 4
static GlSnap gl_fifo[GL_FIFO];
static int gl_fifo_head, gl_fifo_n, gl_fifo_shown = -1;

static pthread_mutex_t hi_lock = PTHREAD_MUTEX_INITIALIZER;
static uint32_t *hi_frame;
static int hi_w, hi_h;
static uint32_t hi_fb;
static uint64_t hi_when;
static GLuint hi_pbo;
static int hi_pend, hi_pw, hi_ph;
static uint32_t hi_pfb;

static GLsync hi_sync;

/* The copy started at the last vertical blank, as soon as the GPU has
 * finished it (polled from the device loop): waiting for the next blank
 * to collect it put another 16 ms between the game and the screen. */
static void gl_present_poll(int wait) {
    if (!hi_pend) return;
    if (hi_sync) {
        GLenum r = glClientWaitSync(hi_sync, GL_SYNC_FLUSH_COMMANDS_BIT, wait ? 100000000ull : 0);
        if (r == GL_TIMEOUT_EXPIRED) return;
        glDeleteSync(hi_sync), hi_sync = 0;
    }
    {
        glBindBuffer(GL_PIXEL_PACK_BUFFER, hi_pbo);
        const void *m = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, (GLsizeiptr)hi_pw * hi_ph * 4, GL_MAP_READ_BIT);
        if (m) {
            pthread_mutex_lock(&hi_lock);
            if (hi_w * hi_h < hi_pw * hi_ph) free(hi_frame), hi_frame = malloc((size_t)hi_pw * hi_ph * 4);
            memcpy(hi_frame, m, (size_t)hi_pw * hi_ph * 4);
            hi_w = hi_pw, hi_h = hi_ph, hi_fb = hi_pfb, hi_when = rt_now_100ns();
            pthread_mutex_unlock(&hi_lock);
        }
        glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
        glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
        hi_pend = 0;
        if (m) rt_display_new_frame();
    }
}

/* The picture into the game's window: letterboxed to 4:3 or 16:9
 * (rt_display_fit), through FXAA (XBRT_AA=fxaa, the default) or scaled
 * as it is. tex is the picture (w x h, rows running down), fbo the same
 * as a framebuffer. 0: the window cannot be drawn with OpenGL. */
static const char *present_vs =
    "#version 430\n"
    "out vec2 v_uv;\n"
    "void main() {\n"
    "    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);\n" /* one triangle over the viewport */
    "    v_uv = vec2(p.x, 1.0 - p.y) * vec2(1.0, 1.0);\n"         /* our rows run down */
    "    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);\n"
    "}\n";
/* FXAA: the edge-finding blur of NVIDIA's console version (Lottes): along
 * the edge's direction where contrast says there is one, else the pixel. */
static const char *present_fs =
    "#version 430\n"
    "in vec2 v_uv;\n"
    "out vec4 o;\n"
    "uniform sampler2D u_src;\n"
    "uniform vec2 u_rcp;\n" /* one texel */
    "uniform int u_fxaa;\n"
    "float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }\n"
    "void main() {\n"
    "    vec3 m = texture(u_src, v_uv).rgb;\n"
    "    if (u_fxaa == 0) { o = vec4(m, 1.0); return; }\n"
    "    vec3 nw = texture(u_src, v_uv + vec2(-1.0, -1.0) * u_rcp).rgb, ne = texture(u_src, v_uv + vec2(1.0, -1.0) * u_rcp).rgb;\n"
    "    vec3 sw = texture(u_src, v_uv + vec2(-1.0, 1.0) * u_rcp).rgb, se = texture(u_src, v_uv + vec2(1.0, 1.0) * u_rcp).rgb;\n"
    "    float lnw = luma(nw), lne = luma(ne), lsw = luma(sw), lse = luma(se), lm = luma(m);\n"
    "    float lmin = min(lm, min(min(lnw, lne), min(lsw, lse))), lmax = max(lm, max(max(lnw, lne), max(lsw, lse)));\n"
    "    vec2 dir = vec2(-((lnw + lne) - (lsw + lse)), (lnw + lsw) - (lne + lse));\n"
    "    float reduce = max((lnw + lne + lsw + lse) * 0.03125, 1.0 / 128.0);\n"
    "    dir = clamp(dir / (min(abs(dir.x), abs(dir.y)) + reduce), vec2(-8.0), vec2(8.0)) * u_rcp;\n"
    "    vec3 a = 0.5 * (texture(u_src, v_uv + dir * (1.0 / 3.0 - 0.5)).rgb + texture(u_src, v_uv + dir * (2.0 / 3.0 - 0.5)).rgb);\n"
    "    vec3 b = a * 0.5 + 0.25 * (texture(u_src, v_uv - dir * 0.5).rgb + texture(u_src, v_uv + dir * 0.5).rgb);\n"
    "    float lb = luma(b);\n"
    "    o = vec4(lb < lmin || lb > lmax ? a : b, 1.0);\n"
    "}\n";

static void gl_overlay_draw(int vx, int vy, int vw, int vh);

static int gl_window_show(GLuint tex, GLuint fbo, int w, int h) {
    static GLuint prog, empty_vao;
    static GLint u_src, u_rcp, u_fxaa;
    static int fxaa = -1;
    int W, H;
    if (!rt_gl_window_begin(&W, &H)) return 0;
    if (W <= 0 || H <= 0) return 1; /* minimised */
    if (fxaa < 0) fxaa = 1, rt_display_fxaa = !getenv("XBRT_AA") || strcmp(getenv("XBRT_AA"), "off") != 0;
    if (!prog) {
        GLuint vs = compile(GL_VERTEX_SHADER, present_vs), fs = compile(GL_FRAGMENT_SHADER, present_fs);
        prog = glCreateProgram();
        if (vs && fs) glAttachShader(prog, vs), glAttachShader(prog, fs), glLinkProgram(prog);
        u_src = glGetUniformLocation(prog, "u_src"), u_rcp = glGetUniformLocation(prog, "u_rcp"), u_fxaa = glGetUniformLocation(prog, "u_fxaa");
        glGenVertexArrays(1, &empty_vao);
    }
    int x, y, cw, ch;
    rt_display_fit(W, H, &x, &y, &cw, &ch);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glDisable(GL_SCISSOR_TEST), glDisable(GL_DEPTH_TEST), glDisable(GL_BLEND), glDisable(GL_CULL_FACE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glViewport(0, 0, W, H);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    GLint linked = 0;
    glGetProgramiv(prog, GL_LINK_STATUS, &linked);
    if (tex && linked) {
        glViewport(x, H - y - ch, cw, ch);
        glUseProgram(prog);
        gl_using = NULL; /* the next draw sets its own program again */
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, tex);
        glBindSampler(0, 0);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        /* Not on the 640x480 pictures from RAM (boot, menus, movies):
         * smoothing edges that small smeared text and logos. */
        glUniform1i(u_src, 0), glUniform2fv(u_rcp, 1, (float[2]){1.0f / (float)w, 1.0f / (float)h}), glUniform1i(u_fxaa, rt_display_fxaa && w > 640);
        glBindVertexArray(empty_vao);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        glBindVertexArray(gl_vao);
    } else { /* no shader: scaled as it is */
        glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo);
        glBlitFramebuffer(0, 0, w, h, x, H - y, x + cw, H - y - ch, GL_COLOR_BUFFER_BIT, GL_LINEAR);
    }
    if (rt_overlay_open()) gl_overlay_draw(x, H - y - ch, cw, ch);
    rt_gl_window_swap();
    return 1;
}

/* What RAM shows (menus at 1x, movies through the overlay), into the
 * window through OpenGL too: once OpenGL has drawn a window, GDI's
 * pictures no longer show in it. */
static int gl_show_ram(void) {
    static GLuint tex, fbo;
    static uint32_t *px;
    if (!px) px = malloc(640 * 480 * 4);
    if (!tex) {
        glGenTextures(1, &tex);
        glBindTexture(GL_TEXTURE_2D, tex);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, 640, 480);
        glGenFramebuffers(1, &fbo);
        glBindFramebuffer(GL_FRAMEBUFFER, fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    }
    rt_display_compose(px);
    glBindTexture(GL_TEXTURE_2D, tex);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 640, 480, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, px);
    int ok = gl_window_show(tex, fbo, 640, 480);
    glBindFramebuffer(GL_FRAMEBUFFER, gl_cur ? gl_cur->fbo : 0);
    return ok;
}

static void gl_present_vblank(uint32_t fb) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (gl_ready <= 0) return;
    gl_present_poll(0);
    fb &= RT_PHYS_SIZE - 1;
    GlSurf *s = NULL;
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (e->fbo && e->k > 1 && e->bpp == 4 && !e->swz && (e->cbase & (RT_PHYS_SIZE - 1)) == fb && e->w == 640 && e->h >= 480 &&
            (!s || e->seq > s->seq))
            s = e;
    }
    /* Only a buffer the GPU drew lately: a stale one would show an old picture. */
    static unsigned last_seq;
    static int same;
    if (s && s->seq == last_seq) {
        if (++same > 6) s = NULL; /* loading screens: their text and icon are drawn on the CPU, into RAM */
    } else if (s) {
        last_seq = s->seq, same = 0;
    }
    if (rt_display_video_on()) s = NULL; /* a movie: the overlay is composited from RAM */
    if (!s) gl_fifo_n = 0, gl_fifo_shown = -1; /* RAM shows the screen: what was queued is old */
    if (!s && fb) gl_sync_range(fb, (rt_display_pitch ? rt_display_pitch : 640 * 4) * 480); /* what the GPU drew there, not read back at the notifies */
    if (!s) { /* RAM shows what is on screen now: the display goes back to it at once */
        pthread_mutex_lock(&hi_lock);
        hi_when = 0;
        pthread_mutex_unlock(&hi_lock);
        rt_gl_shown = rt_display_hwnd() && gl_show_ram() ? rt_now_100ns() : 0;
        return;
    }
    int w = 640 * s->k, h = 480 * s->k;
    GlSnap *snap = NULL;
    for (int i = 0; i < GL_SNAPS; i++)
        if (gl_snap[i].fbo && gl_snap[i].base == s->cbase && gl_snap[i].w == w && gl_snap[i].h == h) snap = &gl_snap[i];
    static int fifo_on = -1;
    if (fifo_on < 0) fifo_on = !getenv("XBRT_GL_FIFO") || atoi(getenv("XBRT_GL_FIFO"));
    if (fifo_on && nv2a.drained && gl_fifo_n)
        gl_fifo_shown = gl_fifo_head, gl_fifo_head = (gl_fifo_head + 1) % GL_FIFO, gl_fifo_n--, nv2a_trace('D', gl_fifo[gl_fifo_shown].seq);
    GlSnap *fs = fifo_on && gl_fifo_shown >= 0 && gl_fifo[gl_fifo_shown].w == w ? &gl_fifo[gl_fifo_shown] : NULL;
    if (gl_window_show(fs ? fs->tex : snap ? snap->tex : s->ctex, fs ? fs->fbo : snap ? snap->fbo : s->fbo, w, h)) {
        rt_gl_shown = rt_now_100ns();
        glBindFramebuffer(GL_FRAMEBUFFER, gl_cur ? gl_cur->fbo : 0);
        if (!rt_display_wants_pixels()) return;
    }
    if (!rt_display_hwnd() && !rt_display_wants_pixels()) return; /* no window, no screenshots: nobody looks */
    if (hi_pend) return; /* the last copy is not done: this blank's picture is skipped rather than waited for */
    if (!hi_pbo) glGenBuffers(1, &hi_pbo);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, hi_pbo);
    glBufferData(GL_PIXEL_PACK_BUFFER, (GLsizeiptr)w * h * 4, NULL, GL_STREAM_READ);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, s->fbo);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, NULL);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, gl_cur ? gl_cur->fbo : 0);
    hi_sync = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0); /* polled with GL_SYNC_FLUSH_COMMANDS_BIT */
    hi_pend = 1, hi_pw = w, hi_ph = h, hi_pfb = fb;
}

/* The latest drawn-resolution picture, if there is a fresh one. */
int rt_gl_frame(uint32_t fb, uint32_t *out, int max_pixels, int *w, int *h) {
    int ok = 0;
    pthread_mutex_lock(&hi_lock);
    (void)fb; /* not compared: the copy is one blank late, and the buffers swap every frame */
    if (hi_frame && hi_when && rt_now_100ns() - hi_when < 500000 && hi_w * hi_h <= max_pixels) {
        memcpy(out, hi_frame, (size_t)hi_w * hi_h * 4);
        *w = hi_w, *h = hi_h, ok = 1;
    }
    pthread_mutex_unlock(&hi_lock);
    return ok;
}

/* A swizzled surface's colour to and from RAM, through a linear copy:
 * the NV2A writes it in Morton order, as textures read it (swizzle()). */
static void gl_to_ram(GlSurf *s) {
    size_t n = (size_t)s->w * (size_t)s->h;
    uint8_t *tmp = malloc(n * (size_t)s->bpp), *dst = phys(s->cbase);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, tmp);
    else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, tmp);
    for (int y = 0; y < s->h; y++)
        for (int x = 0; x < s->w; x++)
            memcpy(dst + (size_t)swizzle((uint32_t)x, (uint32_t)y, s->w, s->h) * (size_t)s->bpp, tmp + ((size_t)y * (size_t)s->w + (size_t)x) * (size_t)s->bpp,
                   (size_t)s->bpp);
    free(tmp);
}

static void gl_from_ram(GlSurf *s) {
    size_t n = (size_t)s->w * (size_t)s->h;
    uint8_t *tmp = malloc(n * (size_t)s->bpp);
    const uint8_t *src = phys(s->cbase);
    for (int y = 0; y < s->h; y++)
        for (int x = 0; x < s->w; x++)
            memcpy(tmp + ((size_t)y * (size_t)s->w + (size_t)x) * (size_t)s->bpp, src + (size_t)swizzle((uint32_t)x, (uint32_t)y, s->w, s->h) * (size_t)s->bpp,
                   (size_t)s->bpp);
    glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    if (s->bpp == 4) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, tmp);
    else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, tmp);
    free(tmp);
}

/* Our own read-back wrote these bytes of RAM. Other framebuffers over them
 * that have not drawn since take the hash of what RAM holds now, instead of
 * being marked to compare and upload it: RAM is what the GPU drew (at 1x),
 * and the newer framebuffer reaches them on the GPU, at full resolution,
 * when they next draw (gl_take_newer). Uploading it was flicker: the
 * shown buffers' read-backs reloaded the other framebuffers over the same
 * buffer with the older, softer picture, and Forza's glow and speed blur,
 * which feed on the previous frame, built up and dropped back over and over. */
static void gl_ram_written(const void *by, uint32_t base, uint32_t size) {
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (e == by || !e->fbo || e->dirty) continue;
        uint32_t c = e->cpitch * (uint32_t)e->h, z = e->ztex ? e->zpitch * (uint32_t)e->h : 0;
        if (gl_span_hit(e->cbase, c, base, size)) e->chash = 0; /* 0: adopt what RAM holds at the next check (gl_upload_if_changed) */
        if (z && gl_span_hit(e->zbase, z, base, size)) e->zhash = 0;
    }
}

static void gl_readback_one(GlSurf *s) {
    gl_complete_range(s->cbase, s->cpitch * (uint32_t)s->h); /* older colour on its way must not land over this */
    if (s->ztex) gl_complete_range(s->zbase, s->zpitch * (uint32_t)s->h);
    gl_read_bind(s, (s->cdirty ? GL_COLOR_BUFFER_BIT : 0) | (s->ztex && s->zdirty ? gl_zbits(s) : 0));
    if (s->cdirty && gl_fits(s->cbase, s->cpitch, s->h)) { /* colour already read back, or on its way, is not read again */
        glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        if (s->swz) gl_to_ram(s);
        else if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, phys(s->cbase));
        else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, phys(s->cbase));
        s->chash = hash_bytes(phys(s->cbase), s->cpitch * (uint32_t)s->h);
    }
    /* Depth only when something wrote it: Forza's 2D passes keep the depth
     * mask on with no depth buffer (zeta offset 0), which made a 1.2 MB
     * "depth buffer" at physical address 0 that was read back over RAM. */
    /* Unless the CPU wrote those bytes since they were last in step (RAM no
     * longer hashes to what the GPU left or saw there): the game reuses its
     * depth buffer's memory for other data between races (the loading
     * screen's picture), and reading the old depth back over it turned the
     * picture into yellow stripes. The CPU's write is the newer one; the
     * framebuffer takes it from RAM before it next draws. */
    if (s->ztex && s->zdirty && s->zhash > 1 && gl_fits(s->zbase, s->zpitch, s->h) &&
        hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h) != s->zhash) {
        s->zdirty = 0, s->check = 1;
    }
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
    gl_ram_written(s, s->cbase, s->cpitch * (uint32_t)s->h);
    if (s->ztex) gl_ram_written(s, s->zbase, s->zpitch * (uint32_t)s->h);
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
    GLsync sync; /* passed when the copy is done */
    void *map;   /* the buffer in the CPU's memory, mapped for good (glBufferStorage) */
    uint32_t cap;
    uint64_t ram_sig; /* hash_sparse of the bytes in RAM when it was asked for */
} GlPending;

static GlPending gl_pend[16];
static int gl_npend;

/* The first n read-backs on their way, in issue order, into RAM. */
static void gl_complete_first(int n) {
    for (int i = 0; i < n; i++) {
        GlPending *p = &gl_pend[i];
        /* The bytes changed since it was asked for, and not by us: the game
         * has used that memory for something else (a menu's track logo,
         * freshly read from disc, came out as a white block under a late
         * frame read-back). RAM keeps what the game put there. */
        int reused = hash_sparse(phys(p->base), p->size) != p->ram_sig;
        if (reused) {
            if (p->sync) glDeleteSync(p->sync), p->sync = 0;
            static int said; if (said++ < 10) fprintf(stderr, "xbrt: read-back of %08x dropped: the memory was reused\n", p->base);
            continue;
        }
        if (p->map) { /* persistent: the copy is there once the fence passes */
            if (p->sync) glClientWaitSync(p->sync, GL_SYNC_FLUSH_COMMANDS_BIT, 1000000000ull);
            memcpy(phys(p->base), p->map, p->size);
        } else {
            glBindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
            const void *m = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, p->size, GL_MAP_READ_BIT);
            if (m) memcpy(phys(p->base), m, p->size);
            glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
        }
        if (p->sync) glDeleteSync(p->sync), p->sync = 0;
        if (!p->s->cdirty) p->s->chash = 0; /* RAM is what the GPU drew: adopted at the next check */
        gl_ram_written(p->s, p->base, p->size);
        for (int j = i + 1; j < gl_npend; j++) /* later ones over these bytes: this write was ours */
            if (gl_span_hit(gl_pend[j].base, gl_pend[j].size, p->base, p->size)) gl_pend[j].ram_sig = hash_sparse(phys(gl_pend[j].base), gl_pend[j].size);
    }
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    for (int i = n; i < gl_npend; i++) { /* the rest move up, keeping their buffers apart */
        GlPending t = gl_pend[i - n];
        gl_pend[i - n] = gl_pend[i], gl_pend[i] = t;
    }
    gl_npend -= n;
}

static void gl_complete(void) {
    if (gl_npend) gl_complete_first(gl_npend);
}

/* At a vertical blank: only the read-backs the GPU has finished. Waiting
 * there for the rest (the GPU still drawing the frame queued before them)
 * held the device thread most of each blank; nothing needs them yet, and
 * whatever looks at those bytes first collects them (gl_complete_range). */
static void gl_complete_ready(void) {
    int n = 0;
    while (n < gl_npend && (!gl_pend[n].sync ||
                            glClientWaitSync(gl_pend[n].sync, GL_SYNC_FLUSH_COMMANDS_BIT, 0) != GL_TIMEOUT_EXPIRED))
        n++;
    if (n) gl_complete_first(n);
}

/* Only those over these bytes, and whatever went before them: waiting for
 * all of them before every texture and every surface's hash check was
 * half the device thread in a race. */
static void gl_complete_range(uint32_t base, uint32_t size) {
    int last = -1;
    for (int i = 0; i < gl_npend; i++)
        if (gl_span_hit(gl_pend[i].base, gl_pend[i].size, base, size)) last = i;
    if (last >= 0) gl_complete_first(last + 1);
}

/* A framebuffer's colour into a pixel buffer object, older colour over
 * the same bytes first; its depth stays on the GPU. */
static void gl_readback_color_async(GlSurf *s) {
    if (s->swz) { /* never a shown buffer; it needs swizzling on the way */
        gl_readback(s);
        return;
    }
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
    p->ram_sig = hash_sparse(phys(p->base), c);
    /* Into the CPU's memory where the driver allows (client storage,
     * mapped for good): mapping a GL_STREAM_READ buffer at each completion
     * copied it out of video memory then, and that was most of the cost of
     * reading the shown frames back. */
    if (glBufferStorage && p->cap < c) {
        if (p->pbo) glDeleteBuffers(1, &p->pbo), p->pbo = 0, p->map = NULL;
        glGenBuffers(1, &p->pbo);
        glBindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
        GLbitfield fl = GL_MAP_READ_BIT | GL_MAP_PERSISTENT_BIT | GL_MAP_COHERENT_BIT;
        glBufferStorage(GL_PIXEL_PACK_BUFFER, c, NULL, fl | GL_CLIENT_STORAGE_BIT);
        p->map = glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, c, fl);
        p->cap = p->map ? c : 0;
    }
    if (!p->pbo) glGenBuffers(1, &p->pbo);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
    if (!p->map) glBufferData(GL_PIXEL_PACK_BUFFER, c, NULL, GL_STREAM_READ);
    gl_read_bind(s, GL_COLOR_BUFFER_BIT);
    glPixelStorei(GL_PACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    if (s->bpp == 4) glReadPixels(0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, NULL);
    else glReadPixels(0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, NULL);
    p->sync = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    s->cdirty = 0;
    s->dirty = s->zdirty;
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
/* When frames come seconds apart (a loading screen), the read-back lands
 * at once instead of at the next vertical blank: there is no frame rate to
 * keep, and Forza's loading thread draws its turbo icon on the CPU into
 * the shown buffer, blending it over the picture in RAM. When it got there
 * before the read-back, it blended over black and kept redrawing the icon
 * in a black square. */
/* The frames the window shows, copied on the GPU at each flip, when the
 * frame is done: at the vertical blank the buffer the CRTC points at may
 * already hold part of the next frame (a flip stall the watchdog let go),
 * and showing it as it stood flickered. Not at D3D's notifies: there are
 * about two a frame, and the second can come with the next frame begun. */
static void gl_snap_into(GlSnap *n, GlSurf *e);

static void gl_snapshot(GlSurf *e) {
    if (e->k < 2 || e->bpp != 4 || e->swz || e->w != 640 || e->h < 480) return;
    GlSnap *n = NULL;
    for (int i = 0; i < GL_SNAPS && !n; i++)
        if (gl_snap[i].base == e->cbase) n = &gl_snap[i];
    if (!n) /* the oldest */
        for (int i = 0; i < GL_SNAPS; i++)
            if (!n || gl_snap[i].seq < n->seq) n = &gl_snap[i];
    gl_snap_into(n, e);
}

/* e's colour into n (made or remade at e's size). */
static void gl_snap_into(GlSnap *n, GlSurf *e) {
    int w = 640 * e->k, h = 480 * e->k;
    if (n->w != w || n->h != h) {
        if (n->fbo) glDeleteFramebuffers(1, &n->fbo), glDeleteTextures(1, &n->tex);
        glGenTextures(1, &n->tex);
        glBindTexture(GL_TEXTURE_2D, n->tex);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, w, h);
        glGenFramebuffers(1, &n->fbo);
        glBindFramebuffer(GL_FRAMEBUFFER, n->fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, n->tex, 0);
        n->w = w, n->h = h;
    }
    n->base = e->cbase, n->seq = e->seq;
    glDisable(GL_SCISSOR_TEST);
    gl_blit(e->fbo, w, h, n->fbo, w, h, GL_COLOR_BUFFER_BIT);
    glBindFramebuffer(GL_FRAMEBUFFER, gl_cur ? gl_cur->fbo : 0);
}

/* Only then: the window shows the GPU's own copies of the frames, and
 * whatever reads these bytes later collects them (gl_sync_range), as
 * does the display when it goes back to RAM (gl_present_vblank). Reading
 * every shown frame back was a third of the device thread in a race.
 * XBRT_GL_SHOWN_READBACK=1: every frame, as before. */
static void gl_sync_color_async(uint32_t base, uint32_t size) {
    static uint64_t last, prev;
    static int every = -1;
    if (every < 0) every = !getenv("XBRT_GL_SHOWN_READBACK") || atoi(getenv("XBRT_GL_SHOWN_READBACK"));
    uint64_t now = rt_now_100ns();
    if (now - last > 50000) prev = last, last = now; /* a notify: one call per shown buffer */
    int slow = last - prev > 1000000; /* 100 ms since the last frame */
    if (!slow && !every && !rt_display_wants_pixels() && !glBufferStorage) return;
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (e->fbo && e->cdirty && gl_span_hit(e->cbase, e->cpitch * (uint32_t)e->h, base, size)) gl_readback_color_async(e);
    }
    if (slow) gl_complete_range(base, size);
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
    /* Every screen-sized buffer drawn since its last copy: not only the
     * one drawn last, which in the menus is often a buffer of their own
     * (the shown one's copy then stayed frames old, and flashed up). */
    for (int i = 0; i < GL_SURFS; i++) {
        GlSurf *e = &gl_surf[i];
        if (!e->fbo || e->k < 2 || e->bpp != 4 || e->swz || e->w != 640 || e->h < 480) continue;
        int newer = 0; /* framebuffers over the same bytes (with and without depth): only the one drawn last */
        for (int j = 0; j < GL_SURFS; j++)
            if (gl_surf[j].fbo && gl_surf[j].cbase == e->cbase && gl_surf[j].seq > e->seq) newer = 1;
        if (newer) continue;
        int fresh = 0;
        for (int j = 0; j < GL_SNAPS; j++)
            if (gl_snap[j].base == e->cbase && gl_snap[j].seq == e->seq) fresh = 1;
        if (!fresh) gl_snapshot(e);
    }
    { /* the frame just finished: the newest drawing over a buffer the CRTC shows */
        GlSurf *f = NULL;
        for (int i = 0; i < GL_SURFS; i++) {
            GlSurf *e = &gl_surf[i];
            if (e->fbo && e->k > 1 && e->bpp == 4 && !e->swz && e->w == 640 && e->h >= 480 && nv2a_is_scanout(e->cbase) &&
                (!f || e->seq > f->seq))
                f = e;
        }
        static unsigned pushed;
        if (f && f->seq != pushed) {
            if (gl_fifo_n == GL_FIFO - 1) gl_fifo_head = (gl_fifo_head + 1) % GL_FIFO, gl_fifo_n--; /* behind: drop the oldest */
            int slot = (gl_fifo_head + gl_fifo_n) % GL_FIFO;
            if (slot == gl_fifo_shown) gl_fifo_shown = -1;
            gl_snap_into(&gl_fifo[slot], f);
            gl_fifo_n++, pushed = f->seq;
        }
    }
    /* XBRT_GL_QUEUE=<1|2> frames may be queued on the GPU (default 1): each
     * one queued is a frame between the controller and the screen. */
    static int depth = 0;
    if (!depth) depth = getenv("XBRT_GL_QUEUE") && atoi(getenv("XBRT_GL_QUEUE")) == 2 ? 2 : 1;
    if (fence[next]) {
        glClientWaitSync(fence[next], GL_SYNC_FLUSH_COMMANDS_BIT, 1000000000ull);
        glDeleteSync(fence[next]);
    }
    fence[next] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    next = (next + 1) % depth;
}

/* RAM up to date in these bytes: the framebuffers that drew into them are
 * read back (with older drawing over the same bytes first), the rest stay
 * on the GPU. Reading back everything whenever a texture was a render
 * target cost a third of the device thread. */
static void gl_sync_range(uint32_t base, uint32_t size) {
    gl_complete_range(base, size);
    static int log = -1; /* XBRT_GL_SYNC_LOG=1: which texture made which framebuffer wait, every 30 s */
    if (log < 0) log = getenv("XBRT_GL_SYNC_LOG") && atoi(getenv("XBRT_GL_SYNC_LOG"));
    /* A compressed (DXT) texture over a depth buffer's bytes is the CPU's:
     * no game samples its depth as DXT. Forza loads its loading screen's
     * picture into the race's depth buffer memory (01e98000); the read-
     * back's own check (gl_readback_one) misses the case where that buffer
     * was drawn with RAM's state unknown (after another framebuffer's
     * read-back over it), and old depth turned the picture yellow. The
     * depth is dropped, and RAM uploaded before it next draws. */
    uint32_t color = (gl_sync_fmt >> 8) & 0xFF;
    if (color >= 0x0C && color <= 0x0F)
        for (int i = 0; i < GL_SURFS; i++) {
            GlSurf *e = &gl_surf[i];
            if (!e->fbo || !e->zdirty || !gl_span_hit(e->zbase, e->zpitch * (uint32_t)e->h, base, size)) continue;
            e->zdirty = 0, e->dirty = e->cdirty, e->zhash = 1, e->check = 1; /* 1: never matches, so RAM is uploaded */
        }
    for (int i = 0; i < GL_SURFS; i++)
        if (gl_drew(&gl_surf[i], base, size)) {
            if (!log) {
                gl_readback(&gl_surf[i]);
                continue;
            }
            static struct { uint32_t base, size, cbase, zbase, fmt; int w, h, cd, zd; unsigned n; uint64_t t; } tab[64];
            static int nt;
            static uint64_t last;
            GlSurf *e = &gl_surf[i];
            int k = 0;
            while (k < nt && !(tab[k].base == base && tab[k].size == size && tab[k].cbase == e->cbase && tab[k].zbase == e->zbase)) k++;
            if (k == nt && nt < 64) {
                tab[nt].base = base, tab[nt].size = size, tab[nt].cbase = e->cbase, tab[nt].zbase = e->zbase, tab[nt].w = e->w, tab[nt].h = e->h, tab[nt].fmt = gl_sync_fmt;
                nt++;
            }
            int cd = e->cdirty, zd = e->zdirty;
            uint64_t t0 = rt_now_100ns();
            gl_readback(e);
            if (k < 64) tab[k].n++, tab[k].t += rt_now_100ns() - t0, tab[k].cd += cd, tab[k].zd += zd;
            if (t0 - last > 300000000ull) {
                last = t0;
                fprintf(stderr, "[%9.3f] gl sync log:\n", t0 / 1e7);
                for (int j = 0; j < nt; j++)
                    fprintf(stderr, "  texture %08x+%u (format %08x) waits for %dx%d at colour %08x depth %08x: %ux (colour %d, depth %d), %.2f s\n", tab[j].base,
                            tab[j].size, tab[j].fmt, tab[j].w, tab[j].h, tab[j].cbase, tab[j].zbase, tab[j].n, tab[j].cd, tab[j].zd, tab[j].t / 1e7);
            }
        }
}

static void gl_upload_if_changed(GlSurf *s) {
    gl_complete_range(s->cbase, s->cpitch * (uint32_t)s->h); /* RAM as the GPU left it, before comparing */
    if (s->ztex) gl_complete_range(s->zbase, s->zpitch * (uint32_t)s->h);
    /* RAM as it was at the last full comparison (sparse signature): almost
     * always the case, and then the whole is hashed only every 32nd time. */
    int full = s->sig_checks++ % 32 == 0;
    uint64_t cs = gl_fits(s->cbase, s->cpitch, s->h) ? hash_sparse(phys(s->cbase), s->cpitch * (uint32_t)s->h) : 0;
    uint64_t zs = s->ztex && gl_fits(s->zbase, s->zpitch, s->h) ? hash_sparse(phys(s->zbase), s->zpitch * (uint32_t)s->h) : 0;
    if (!full && cs == s->csig && zs == s->zsig) return;
    s->csig = cs, s->zsig = zs;
    if (gl_fits(s->cbase, s->cpitch, s->h)) {
        uint64_t h = hash_bytes(phys(s->cbase), s->cpitch * (uint32_t)s->h);
        if (!s->chash) s->chash = h; /* our own read-back put it there */
        if (h != s->chash) {
            glBindTexture(GL_TEXTURE_2D, gl_up_tex(s, 0));
            glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(s->cpitch / (uint32_t)s->bpp));
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
            if (s->swz) gl_from_ram(s);
            else if (s->bpp == 4) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, phys(s->cbase));
            else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_RGB, GL_UNSIGNED_SHORT_5_6_5, phys(s->cbase));
            s->chash = h;
            gl_up_done(s, GL_COLOR_BUFFER_BIT);
        }
    }
    if (s->ztex && gl_fits(s->zbase, s->zpitch, s->h)) {
        uint64_t h = hash_bytes(phys(s->zbase), s->zpitch * (uint32_t)s->h);
        if (!s->zhash) s->zhash = h;
        if (h != s->zhash) {
            glBindTexture(GL_TEXTURE_2D, gl_up_tex(s, 1));
            glPixelStorei(GL_UNPACK_ROW_LENGTH, (GLint)(s->zpitch / (uint32_t)s->zbpp));
            if (s->zbpp == 4) glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_DEPTH_STENCIL, GL_UNSIGNED_INT_24_8, phys(s->zbase));
            else glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, s->w, s->h, GL_DEPTH_COMPONENT, GL_UNSIGNED_SHORT, phys(s->zbase));
            s->zhash = h;
            gl_up_done(s, gl_zbits(s));
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
    if (e->k != s->k) return 0;
    uint32_t ec = e->cpitch * (uint32_t)e->h, ez = e->ztex && e->zdirty ? e->zpitch * (uint32_t)e->h : 0;
    uint32_t sc = s->cpitch * (uint32_t)s->h, sz = s->ztex ? s->zpitch * (uint32_t)s->h : 0;
    if (gl_span_hit(e->cbase, ec, s->cbase, sc) && (e->swz || s->swz) &&
        (e->swz != s->swz || e->cbase != s->cbase || e->w != s->w || e->h != s->h)) /* Morton order does not shift by rows */
        return 0;
    if (gl_span_hit(e->cbase, ec, s->cbase, sc) &&
        (e->cpitch != s->cpitch || e->bpp != s->bpp || !gl_row_offset(e->cbase, s->cbase, s->cpitch, &dy)))
        return 0;
    if (gl_span_hit(e->cbase, ec, s->zbase, sz) || gl_span_hit(e->zbase, ez, s->cbase, sc)) return 0;
    if (gl_span_hit(e->zbase, ez, s->zbase, sz) &&
        (e->zpitch != s->zpitch || e->zbpp != s->zbpp || !gl_row_offset(e->zbase, s->zbase, s->zpitch, &dy)))
        return 0;
    return 1;
}

/* Copies the part of e that e drew (rx0..rx1, ry0..ry1) into s, where the
 * bytes line up a whole number of rows apart. Whole rows, as before, put
 * what a bloom quarter (left 320 columns of a 640-wide surface) never drew
 * over the front buffer's right half: black on NVIDIA, where those texels
 * were never written. */
static void gl_copy_rows(const GlSurf *e, GLuint from, uint32_t from_base, GLuint to, int to_h, uint32_t to_base, uint32_t pitch, int w) {
    int dy;
    if (!gl_row_offset(from_base, to_base, pitch, &dy)) return;
    int y0 = e->ry0 > (dy < 0 ? -dy : 0) ? e->ry0 : (dy < 0 ? -dy : 0), y1 = e->ry1 < e->h ? e->ry1 : e->h;
    if (y1 + dy > to_h) y1 = to_h - dy;
    int x1 = e->rx1 < w ? e->rx1 : w;
    int k = e->k;
    if (y1 > y0 && x1 > e->rx0)
        glCopyImageSubData(from, GL_TEXTURE_2D, 0, e->rx0 * k, y0 * k, 0, to, GL_TEXTURE_2D, 0, e->rx0 * k, (y0 + dy) * k, 0, (x1 - e->rx0) * k,
                           (y1 - y0) * k, 1);
}

static void gl_copy(const GlSurf *e, GlSurf *s) {
    int w = e->w < s->w ? e->w : s->w;
    gl_copy_rows(e, e->ctex, e->cbase, s->ctex, s->h, s->cbase, s->cpitch, w);
    /* Not depth: Forza's shown buffers share the scene's depth memory (a 640
     * wide view of 1280-wide depth), and the scene's depth copied in made
     * the passes drawn there fail their depth test: black patches on NVIDIA.
     * Intel's driver evidently never did the copy, and looked right. */
}

/* A draw or clear into s over this rectangle (clipped to s). */
static void gl_drawn(GlSurf *s, int x0, int y0, int x1, int y1) {
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > s->w) x1 = s->w;
    if (y1 > s->h) y1 = s->h;
    if (x1 <= x0 || y1 <= y0) return;
    if (s->rx1 <= s->rx0) s->rx0 = x0, s->ry0 = y0, s->rx1 = x1, s->ry1 = y1;
    else {
        if (x0 < s->rx0) s->rx0 = x0;
        if (y0 < s->ry0) s->ry0 = y0;
        if (x1 > s->rx1) s->rx1 = x1;
        if (y1 > s->ry1) s->ry1 = y1;
    }
}

static void gl_free_surf(GlSurf *s) {
    if (s->fbo) glDeleteFramebuffers(1, &s->fbo);
    if (s->ctex) glDeleteTextures(1, &s->ctex);
    if (s->ztex) glDeleteTextures(1, &s->ztex);
    if (s->pfbo) glDeleteFramebuffers(1, &s->pfbo);
    if (s->ptex) glDeleteTextures(1, &s->ptex);
    if (s->pztex) glDeleteTextures(1, &s->pztex);
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
        /* Read back or not: a framebuffer that drew later holds newer pixels
         * than s, which (dirty itself) will not take them from RAM. Taking
         * only the dirty ones left a front buffer's texture with texels
         * nothing wrote: black patches on NVIDIA. */
        if (e != s && e->fbo && e->seq > s->seq &&
            (gl_overlaps(e, s->cbase, s->cpitch * (uint32_t)s->h) || (s->ztex && gl_overlaps(e, s->zbase, s->zpitch * (uint32_t)s->h)))) {
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
    int swz = ((fmt >> 8) & 15) == 2;
    int w = (int)(d->pitch / (uint32_t)d->bpp), h = d->cy0 + d->ch; /* exact: rounded up to 16, a 160x120 one covered the cube map after it */
    if (swz) w = 1 << ((fmt >> 16) & 15), h = 1 << ((fmt >> 24) & 15); /* the Morton order runs over the whole of it */
    uint32_t zbase = zfmt ? dma_base(SET_CONTEXT_DMA_ZETA) + K(SET_SURFACE_ZETA_OFFSET) : 0, zpitch = zfmt ? K(SET_SURFACE_PITCH) >> 16 : 0;
    if (zfmt && (zfmt > 2 || !zpitch || (uint32_t)w * (zfmt == 1 ? 2u : 4u) > zpitch)) zfmt = 0, zbase = 0, zpitch = 0;
    GlSurf *s = gl_cur;
    if (!s || s->cbase != d->base || s->cpitch != d->pitch || s->cfmt != cfmt || s->zbase != zbase || s->zfmt != zfmt ||
        s->zpitch != zpitch || s->w != w || s->h < h || s->swz != swz) {
        s = NULL;
        GlSurf *lru = &gl_surf[0];
        for (int i = 0; i < GL_SURFS && !s; i++) {
            GlSurf *e = &gl_surf[i];
            if (e->fbo && e->cbase == d->base && e->cpitch == d->pitch && e->cfmt == cfmt && e->zbase == zbase && e->zfmt == zfmt &&
                e->zpitch == zpitch && e->w == w && e->h >= h && e->swz == swz)
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
            s->w = w, s->h = h, s->bpp = d->bpp, s->zbpp = zfmt == 1 ? 2 : 4, s->swz = swz;
            s->k = swz ? 1 : gl_k;
            glGenTextures(1, &s->ctex);
            glBindTexture(GL_TEXTURE_2D, s->ctex);
            glTexStorage2D(GL_TEXTURE_2D, 1, d->bpp == 4 ? GL_RGBA8 : GL_RGB565, w * s->k, h * s->k);
            glGenFramebuffers(1, &s->fbo);
            glBindFramebuffer(GL_FRAMEBUFFER, s->fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, s->ctex, 0);
            if (zfmt) {
                glGenTextures(1, &s->ztex);
                glBindTexture(GL_TEXTURE_2D, s->ztex);
                glTexStorage2D(GL_TEXTURE_2D, 1, zfmt == 1 ? GL_DEPTH_COMPONENT16 : GL_DEPTH24_STENCIL8, w * s->k, h * s->k);
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
    glViewport(0, 0, s->w * s->k, s->h * s->k);
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
        t->gl = s->ztex, t->surface = 1, t->depth = 0xFFFFFF, t->zaddr = lo;
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

/* A swizzled A8R8G8B8/X8R8G8B8 texture over framebuffers the GPU drew
 * (Forza's car reflections: a 256x256 one and a 128x128 cube map drawn
 * face by face) is sampled from them, as xemu does: their image is the
 * texture's. Forza draws them as pitch surfaces (with the swizzled size
 * fields set), so read back through RAM they decoded scrambled: the
 * speckled car paint. And reading them back each frame, waiting for the
 * GPU every time, was most of what was left of the device thread's waits. A cube map needs all six faces as framebuffers; they are
 * copied into a cube texture on the GPU. NULL: decode as usual. */
static Texture *gl_rt_swizzled(int i, uint32_t base, uint32_t color, int w, int h, int cube) {
    static Texture rt[4];
    static struct { uint32_t base; int w, k; GLuint tex, from[6]; unsigned seq[6]; } cubes[8]; /* from, seq: what each face was copied from */
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || w <= 0 || h <= 0) return NULL;
    static int cubes_on = -1; /* XBRT_GL_RT_CUBE=0: not cube maps (copying the faces took Intel's GPU to ~13 fps; NVIDIA's is faster with them) */
    if (cubes_on < 0) cubes_on = !getenv("XBRT_GL_RT_CUBE") || atoi(getenv("XBRT_GL_RT_CUBE"));
    if (cube && !cubes_on) return NULL;
    uint32_t face = ((uint32_t)w * (uint32_t)h * 4 + 127) & ~127u;
    uint32_t lo = base & (RT_PHYS_SIZE - 1), hi = lo + face * (cube ? 6u : 1u);
    if ((lo < draw_hi && draw_lo < hi) || (lo < draw_zhi && draw_zlo < hi)) return NULL; /* GL cannot sample what it draws into */
    GlSurf *f[6] = {0};
    for (int k = 0; k < (cube ? 6 : 1); k++) {
        for (int j = 0; j < GL_SURFS; j++) {
            GlSurf *e = &gl_surf[j];
            if (e->fbo && e->bpp == 4 && (e->cbase & (RT_PHYS_SIZE - 1)) == lo + face * (uint32_t)k && e->w == w && e->h == h &&
                (!f[k] || e->seq > f[k]->seq))
                f[k] = e;
        }
        if (!f[k]) return NULL;
    }
    for (int k = 0; k < (cube ? 6 : 1); k++) {
        if (f[k]->check && !f[k]->dirty) gl_upload_if_changed(f[k]);
        f[k]->check = 0;
        gl_take_newer(f[k]);
    }
    Texture *t = &rt[i];
    memset(t, 0, sizeof *t);
    t->w = w, t->h = h, t->levels = 1, t->surface = 1, t->alpha_one = color == 0x07;
    if (!cube) {
        t->gl = f[0]->ctex;
        return t;
    }
    int c = 0;
    while (c < 8 && cubes[c].tex && !(cubes[c].base == lo && cubes[c].w == w)) c++;
    if (c == 8) c = 0, glDeleteTextures(1, &cubes[0].tex), memset(&cubes[0], 0, sizeof cubes[0]);
    int fk = f[0]->k;
    for (int k = 1; k < 6; k++)
        if (f[k]->k != fk) return NULL;
    if (cubes[c].tex && cubes[c].k != fk) glDeleteTextures(1, &cubes[c].tex), memset(&cubes[c], 0, sizeof cubes[c]);
    if (!cubes[c].tex) {
        glGenTextures(1, &cubes[c].tex);
        glBindTexture(GL_TEXTURE_CUBE_MAP, cubes[c].tex);
        glTexStorage2D(GL_TEXTURE_CUBE_MAP, 1, GL_RGBA8, w * fk, h * fk);
        cubes[c].base = lo, cubes[c].w = w, cubes[c].k = fk;
    }
    for (int k = 0; k < 6; k++) /* only faces drawn since (every car draw samples it) */
        if (cubes[c].from[k] != f[k]->ctex || cubes[c].seq[k] != f[k]->seq) {
            glCopyImageSubData(f[k]->ctex, GL_TEXTURE_2D, 0, 0, 0, 0, cubes[c].tex, GL_TEXTURE_CUBE_MAP, 0, 0, 0, k, w * fk, h * fk, 1);
            cubes[c].from[k] = f[k]->ctex, cubes[c].seq[k] = f[k]->seq;
        }
    t->cube = 1, t->gl = cubes[c].tex;
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
    if ((type != 1 && type != 2) || !d.bpp) return 0; /* 2: swizzled, which the RAM clear cannot do */
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
    glScissor((GLint)x1 * d.sx * s->k, (GLint)y1 * d.sy * s->k, (GLsizei)(x2 - x1 + 1) * d.sx * s->k, (GLsizei)(y2 - y1 + 1) * d.sy * s->k);
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
    gl_drawn(s, (int)x1 * d.sx, (int)y1 * d.sy, (int)(x2 + 1) * d.sx, (int)(y2 + 1) * d.sy);
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
/* A texture stage's sampling, as a sampler object: setting wrap, filter
 * and LOD bias on the textures themselves at every draw made the driver
 * check them all again at every draw (about 10 us a draw of the ~22). */
typedef struct {
    GLint ws, wt, min, mag;
    float bias, aniso, border[4];
} GlSampling;

static GLuint gl_sampler(const GlSampling *k) {
    static GlSampling keys[512];
    static GLuint ids[512];
    static int n;
    for (int i = n - 1; i >= 0; i--)
        if (!memcmp(&keys[i], k, sizeof *k)) return ids[i];
    if (n == 512) n = 0; /* reused oldest first: the game uses a few dozen */
    if (!ids[n]) glGenSamplers(1, &ids[n]);
    GLuint id = ids[n];
    keys[n++] = *k;
    glSamplerParameteri(id, GL_TEXTURE_WRAP_S, k->ws), glSamplerParameteri(id, GL_TEXTURE_WRAP_T, k->wt);
    glSamplerParameteri(id, GL_TEXTURE_WRAP_R, k->ws);
    glSamplerParameteri(id, GL_TEXTURE_MIN_FILTER, k->min), glSamplerParameteri(id, GL_TEXTURE_MAG_FILTER, k->mag);
    glSamplerParameterf(id, GL_TEXTURE_LOD_BIAS, k->bias);
    glSamplerParameterf(id, 0x84FE /* GL_TEXTURE_MAX_ANISOTROPY */, k->aniso);
    glSamplerParameterfv(id, GL_TEXTURE_BORDER_COLOR, k->border);
    return id;
}

static void gl_filter_of(GlSampling *k, const Texture *t, uint32_t filt);

static void gl_filter_of(GlSampling *k, const Texture *t, uint32_t filt) {
    static const GLint mins[8] = {GL_NEAREST, GL_NEAREST, GL_LINEAR, GL_NEAREST_MIPMAP_NEAREST, GL_LINEAR_MIPMAP_NEAREST,
                                  GL_NEAREST_MIPMAP_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_LINEAR};
    uint32_t mn = (filt >> 16) & 0x3F, mg = (filt >> 24) & 15;
    GLint min = t->depth ? GL_NEAREST : mn < 8 ? mins[mn] : GL_LINEAR;
    GLint mag = t->depth || mg <= 1 ? GL_NEAREST : GL_LINEAR;
    int32_t bias = (int32_t)(filt << 19) >> 19;
    /* PC enhancements for mipmapped textures (XBRT_GL_ANISO=<1..16>, default
     * 16; 1 turns both off): trilinear where the game asked for bilinear
     * between mipmaps, and anisotropic filtering, which keeps the road and
     * the verges sharp at grazing angles instead of smearing them. */
    static float aniso = -1;
    if (aniso < 0) {
        aniso = getenv("XBRT_GL_ANISO") ? (float)atof(getenv("XBRT_GL_ANISO")) : 16.0f;
        if (aniso < 1) aniso = 1;
    }
    k->aniso = 1;
    if (aniso > 1 && !t->depth && t->levels > 1 && min != GL_NEAREST && min != GL_LINEAR) min = GL_LINEAR_MIPMAP_LINEAR, k->aniso = aniso;
    k->min = min, k->mag = mag, k->bias = (float)bias / 256.0f;
}

/* Address modes: 1 wrap, 2 mirror, 3 clamp to edge, 4 border, 5 clamp
 * (OpenGL's). Border was taken as clamp to edge; Forza's shadow-map
 * lookups use it (address 00040404, border ffffffff: outside the map is
 * far, so lit). */
static GLint gl_wrap(uint32_t mode) {
    return mode == 2 ? GL_MIRRORED_REPEAT : (mode == 1 || mode == 0) ? GL_REPEAT : mode == 4 ? GL_CLAMP_TO_BORDER : GL_CLAMP_TO_EDGE;
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

/* Which fragment shader variant this draw can use (gl_fs_variant): the
 * same conditions as gl_frag_state's depth and alpha test. */
static int gl_frag_variant(void) {
    static int wbuf = -1, on = -1;
    if (wbuf < 0) wbuf = getenv("XBRT_GL_WBUFFER") && atoi(getenv("XBRT_GL_WBUFFER"));
    if (on < 0) on = !getenv("XBRT_GL_EARLY_Z") || atoi(getenv("XBRT_GL_EARLY_Z"));
    if (!on) return 0;
    int var = 0;
    int offset = (K(0x338) & 1) && (K(0x388) != 0 || K(0x384) != 0); /* POLY_OFFSET_FILL_ENABLE with a bias or a factor */
    if (!offset && !(wbuf && (K(0x290) & (1u << 16)))) var |= 1;
    if (!K(SET_ALPHA_TEST_ENABLE) || (rt_debug_keys & RT_DBG_NO_ALPHA)) var |= 2;
    return var;
}

static void gl_draw(const DrawState *d, const Tri *tri, int n) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || !n) return;
    GlSurf *s = gl_bind(d);
    gl_use(gl_variant(&gl_main, gl_frag_variant()));

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
    gl_drawn(s, d->cx0, d->cy0, d->cx0 + d->cw, d->cy0 + d->ch);
}

/* The program's uniforms for the pixel side (the combiners, the texture
 * stages, alpha test, fog colour) and the fixed-function state, from the
 * methods, for a draw to s. */
/* A texture that is also attached to the framebuffer being drawn (another
 * part of the same surface: Forza's bloom reads one band of a buffer while
 * drawing into another) is a feedback loop, undefined in GL even when the
 * texels and the pixels differ. Intel's driver gave the right picture;
 * NVIDIA's gave black patches. Such a draw samples a copy instead. */
static GLuint gl_unalias(int stage, GLuint tex, const GlSurf *s) {
    static struct { GLuint tex; int w, h; GLenum fmt; } scratch[4];
    if (!s || !tex || (tex != s->ctex && tex != s->ztex)) return tex;
    GLenum fmt = tex == s->ctex ? (s->bpp == 4 ? GL_RGBA8 : GL_RGB565) : (s->zbpp == 4 ? GL_DEPTH24_STENCIL8 : GL_DEPTH_COMPONENT16);
    int w = s->w * s->k, h = s->h * s->k;
    if (!scratch[stage].tex || scratch[stage].w != w || scratch[stage].h != h || scratch[stage].fmt != fmt) {
        if (scratch[stage].tex) glDeleteTextures(1, &scratch[stage].tex);
        glGenTextures(1, &scratch[stage].tex);
        glBindTexture(GL_TEXTURE_2D, scratch[stage].tex);
        glTexStorage2D(GL_TEXTURE_2D, 1, fmt, w, h);
        scratch[stage].w = w, scratch[stage].h = h, scratch[stage].fmt = fmt;
    }
    glCopyImageSubData(tex, GL_TEXTURE_2D, 0, 0, 0, 0, scratch[stage].tex, GL_TEXTURE_2D, 0, 0, 0, 0, w, h, 1);
    return scratch[stage].tex;
}

static void gl_frag_state(const DrawState *d, const GlSurf *s) {
    float size[2] = {(float)s->w, (float)s->h};
    glUniform2fv(u_size, 1, size);
    glUniform1f(u_zmax, d->zmax);
    {
        uint32_t cmin = K(0x394), cmax = K(0x398); /* SET_CLIP_MIN / MAX, floats in depth units */
        float lo, hi;
        memcpy(&lo, &cmin, 4), memcpy(&hi, &cmax, 4);
        if (!(hi > lo) || (rt_debug_keys & RT_DBG_NO_CLIP)) lo = 0, hi = d->zmax;
        float zr[4] = {d->zmax, lo, hi, (K(0x290) & (1u << 16)) ? 1.0f : 0.0f}; /* CONTROL0 Z_PERSPECTIVE */
        uint32_t fb = K(0x388), ff = K(0x384); /* POLYGON_OFFSET_BIAS / SCALE_FACTOR, if POLY_OFFSET_FILL_ENABLE */
        float zoff[3] = {0, 0, (float)s->k}; /* slopes per Xbox pixel: k GL pixels each */
        if (K(0x338) & 1) memcpy(&zoff[0], &fb, 4), memcpy(&zoff[1], &ff, 4);
        /* W-buffering only with XBRT_GL_WBUFFER=1: taking the program's w as
         * the depth left the lower half of the cars dark (their passes
         * failed the depth test), so its scale is not understood yet. */
        static int wbuf = -1;
        if (wbuf < 0) wbuf = getenv("XBRT_GL_WBUFFER") && atoi(getenv("XBRT_GL_WBUFFER"));
        if (!wbuf) zr[3] = 0;
        glUniform4fv(u_zr, 1, zr);
        glUniform3fv(u_zoff, 1, zoff);
    }

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
        GLuint tid = t && !t->cube ? (t->surface ? gl_unalias(i, gl_texture(t), s) : gl_texture(t)) : gl_dummy2d;
        glBindTexture(GL_TEXTURE_2D, tid);
        if (t && t->surface && !t->depth && !t->cube) /* X8R8G8B8 over a framebuffer that keeps alpha */
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_A, t->alpha_one ? GL_ONE : GL_ALPHA);
        GlSampling k = {GL_REPEAT, GL_REPEAT, GL_NEAREST, GL_NEAREST, 0, 1, {0, 0, 0, 0}};
        if (t && !t->cube) {
            uint32_t addr = KT(SET_TEXTURE_ADDRESS);
            k.ws = gl_wrap(addr & 15), k.wt = gl_wrap((addr >> 8) & 15);
            if ((addr & 15) == 4 || ((addr >> 8) & 15) == 4) { /* the border colour: ARGB; a depth map's (R32F, Xbox units) scaled up */
                uint32_t bc = KT(0x1B24);
                k.border[0] = (float)((bc >> 16) & 255) / 255.0f, k.border[1] = (float)((bc >> 8) & 255) / 255.0f;
                k.border[2] = (float)(bc & 255) / 255.0f, k.border[3] = (float)(bc >> 24) / 255.0f;
                if (t->depth && !t->surface) k.border[0] *= (float)t->depth;
            }
            gl_filter_of(&k, t, KT(SET_TEXTURE_FILTER));
        }
        glBindSampler((GLuint)i, gl_sampler(&k));
        glActiveTexture(GL_TEXTURE4 + (GLenum)i);
        glBindTexture(GL_TEXTURE_CUBE_MAP, t && t->cube ? gl_texture(t) : gl_dummycube);
        GlSampling kc = {GL_REPEAT, GL_REPEAT, GL_NEAREST, GL_NEAREST, 0, 1, {0, 0, 0, 0}};
        if (t && t->cube) gl_filter_of(&kc, t, KT(SET_TEXTURE_FILTER));
        glBindSampler(4 + (GLuint)i, gl_sampler(&kc));
    }
    glActiveTexture(GL_TEXTURE0);
    glUniform1iv(u_mode, 4, mode), glUniform1iv(u_kind, 4, kind), glUniform2fv(u_scale, 4, scale), glUniform1fv(u_dmax, 4, dmax);
    glUniform1i(u_shadow_func, (GLint)(K(SET_SHADOW_DEPTH_FUNC) & 7));
    glUniform1i(u_alpha_func, K(SET_ALPHA_TEST_ENABLE) && !(rt_debug_keys & RT_DBG_NO_ALPHA) ? (GLint)K(SET_ALPHA_FUNC) : 0);
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
    if (d->ztest && s->ztex && !(rt_debug_keys & RT_DBG_NO_DEPTH)) {
        glEnable(GL_DEPTH_TEST);
        glDepthFunc(d->zfunc);
        glDepthMask(d->zwrite ? GL_TRUE : GL_FALSE);
    } else {
        glDisable(GL_DEPTH_TEST);
    }
    glColorMask((d->wm & 0x00FF0000u) != 0, (d->wm & 0x0000FF00u) != 0, (d->wm & 0x000000FFu) != 0, (d->wm & 0xFF000000u) != 0);
    /* Face culling, as the game sets it (SET_CULL_FACE_ENABLE, SET_CULL_FACE,
     * SET_FRONT_FACE; GL's own values). Our y runs down the screen where
     * GL's NDC runs up, which mirrors the winding: CW and CCW swap (unswapped
     * the scene lost most of its faces). XBRT_GL_CULL=0 turns it off. */
    static int cull = -1;
    if (cull < 0) cull = getenv("XBRT_GL_CULL") ? atoi(getenv("XBRT_GL_CULL")) : 1;
    if (cull && !(rt_debug_keys & RT_DBG_NO_CULL) && K(0x308) && (K(0x39C) == GL_FRONT || K(0x39C) == GL_BACK || K(0x39C) == GL_FRONT_AND_BACK)) {
        glEnable(GL_CULL_FACE);
        glCullFace((GLenum)K(0x39C));
        GLenum ff = K(0x3A0) == GL_CW ? GL_CW : GL_CCW;
        if (cull == 1) ff = ff == GL_CW ? GL_CCW : GL_CW;
        glFrontFace(ff);
    } else {
        glDisable(GL_CULL_FACE);
    }
    glEnable(GL_SCISSOR_TEST);
    glScissor(d->cx0 * s->k, d->cy0 * s->k, d->cw * s->k, d->ch * s->k);
}
