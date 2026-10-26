/* Fragment shaders made for each combination of the draw's fragment state
 * (the register combiners' words, the texture stages' kinds and modes, the
 * alpha test, the shadow compare), as xemu does: the one shader in
 * glfill.c (fs_src) reads all of that from uniforms and works it out for
 * every pixel, which held the GPU back at 3x and 4x (25 fps at the race
 * start at 4x; 60 with a trivial shader). Here it is decided when the
 * shader is made, and the registers become plain variables. The arithmetic
 * is fs_src's, step for step. Included by raster.c after glfill.c.
 *
 * Each is compiled once and linked with each vertex program it is drawn
 * with (gl_fs_program). XBRT_GL_SPECIALIZE=0: fs_src. */

typedef struct {
    uint32_t cicw[8], cocw[8], aicw[8], aocw[8], ctl, f0, f1;
    uint8_t mode[4], kind[4];
    uint16_t alpha_func; /* 0 off, else 0x200-0x207 */
    uint8_t shadow_func, depth; /* depth: writes gl_FragDepth (polygon offset, w-buffer) */
} FsKey;

typedef struct {
    FsKey key;
    GLuint fs;   /* the compiled shader */
    int ok;      /* 1 compiled, 0 still compiling (rt_gl_parallel), -1 failed */
} GlFs;

static GlFs *gl_fs_cache;
static int gl_nfs, gl_fs_cap;

typedef struct {
    char *p;
    size_t n, cap;
} FsStr;

static void fsput(FsStr *s, const char *fmt, ...) {
    va_list ap;
    for (;;) {
        va_start(ap, fmt);
        int k = vsnprintf(s->p + s->n, s->cap - s->n, fmt, ap);
        va_end(ap);
        if (k >= 0 && s->n + (size_t)k < s->cap) {
            s->n += (size_t)k;
            return;
        }
        s->cap *= 2;
        s->p = realloc(s->p, s->cap);
    }
}

/* map_in, by the input mapping (bits 5-7 of an input's byte). */
static void fs_map_in(char *out, size_t n, uint32_t m, const char *x) {
    switch (m) {
    case 0: snprintf(out, n, "max(%s, 0.0)", x); break;
    case 1: snprintf(out, n, "(1.0 - clamp(%s, 0.0, 1.0))", x); break;
    case 2: snprintf(out, n, "(2.0 * max(%s, 0.0) - 1.0)", x); break;
    case 3: snprintf(out, n, "(1.0 - 2.0 * max(%s, 0.0))", x); break;
    case 4: snprintf(out, n, "(max(%s, 0.0) - 0.5)", x); break;
    case 5: snprintf(out, n, "(0.5 - max(%s, 0.0))", x); break;
    case 6: snprintf(out, n, "(%s)", x); break;
    default: snprintf(out, n, "(-(%s))", x); break;
    }
}

/* A register as an input: r15 is E*F, which is zero except in the final
 * combiner's A-D (ef: the expression for it there). */
static void fs_reg(char *out, size_t n, uint32_t r, const char *ef) {
    if (r == 15) snprintf(out, n, "%s", ef ? ef : "vec4(0.0)");
    else snprintf(out, n, "P%u", r);
}

static void fs_in_rgb(char *out, size_t n, uint32_t i, const char *ef) {
    char reg[64], x[96];
    fs_reg(reg, sizeof reg, i & 15, ef);
    snprintf(x, sizeof x, "%s.%s", reg, (i & 16) ? "aaa" : "rgb");
    fs_map_in(out, n, (i >> 5) & 7, x);
}

static void fs_in_a(char *out, size_t n, uint32_t i, const char *ef) {
    char reg[64], x[96];
    fs_reg(reg, sizeof reg, i & 15, ef);
    snprintf(x, sizeof x, "%s.%s", reg, (i & 16) ? "a" : "b");
    fs_map_in(out, n, (i >> 5) & 7, x);
}

static void fs_map_out(char *out, size_t n, uint32_t m, const char *x) {
    char y[400];
    if (m == 0x08) snprintf(y, sizeof y, "(%s - 0.5)", x);
    else if (m == 0x10) snprintf(y, sizeof y, "(%s * 2.0)", x);
    else if (m == 0x18) snprintf(y, sizeof y, "((%s - 0.5) * 2.0)", x);
    else if (m == 0x20) snprintf(y, sizeof y, "(%s * 4.0)", x);
    else if (m == 0x30) snprintf(y, sizeof y, "(%s * 0.5)", x);
    else snprintf(y, sizeof y, "%s", x);
    snprintf(out, n, "clamp(%s, -1.0, 1.0)", y);
}

static const char *fs_cmp(int f) {
    static const char *ops[8] = {"false", "(a < b)", "(a == b)", "(a <= b)", "(a > b)", "(a != b)", "(a >= b)", "true"};
    return ops[f & 7];
}

static char *fs_generate(const FsKey *k) {
    FsStr s = {malloc(32768), 0, 32768};
    fsput(&s, "%s", gl_fs_head());
    fsput(&s, "in vec4 v_c0, v_c1, v_t0, v_t1, v_t2, v_t3;\n"
              "in float v_fog;\nnoperspective in float v_zs;\nin float v_w;\n"
              "#ifdef WBARY\npervertexNV in float v_wv[3];\n#endif\n"
              "out vec4 o_color;\n"
              "uniform vec4 u_zr;\nuniform vec3 u_zoff;\nuniform vec3 u_fogc;\n"
              "uniform vec4 u_c0[8], u_c1[8], u_fc0, u_fc1;\n"
              "uniform vec2 u_scale[4];\nuniform float u_dmax[4];\nuniform float u_alpha_ref;\n"
              "uniform sampler2D u_tex0, u_tex1, u_tex2, u_tex3;\n"
              "uniform samplerCube u_cube0, u_cube1, u_cube2, u_cube3;\n"
              "void main() {\n");
    for (int i = 0; i < 16; i++) fsput(&s, "    vec4 R%d = vec4(0.0), P%d;\n", i, i);
    fsput(&s, "    R3 = vec4(u_fogc, clamp(v_fog, 0.0, 1.0));\n    R4 = v_c0; R5 = v_c1;\n");
    /* The texture stages. */
    for (int i = 0; i < 4; i++) {
        int mode = k->mode[i], kind = k->kind[i];
        if (mode == 0 || (mode != 4 && kind == 0)) continue; /* zero */
        if (mode == 4) {
            fsput(&s, "    R%d = clamp(v_t%d, 0.0, 1.0);\n", 8 + i, i);
        } else if (kind == 2) {
            fsput(&s, "    R%d = texture(u_cube%d, v_t%d.xyz);\n", 8 + i, i, i);
        } else if (kind == 3 || kind == 4) {
            char bexpr[64] = "0.0", fl4[96] = "";
            if (mode == 2) snprintf(bexpr, sizeof bexpr, "clamp(q.z / qw, 0.0, u_dmax[%d])", i);
            if (kind == 4) snprintf(fl4, sizeof fl4, "          a = floor(a * u_dmax[%d] + 0.5);\n", i); /* GL's 0..1 depth back to the Xbox's units */
            fsput(&s, "    { vec4 q = v_t%d; float qw = q.w != 0.0 ? q.w : 1.0;\n"
                      "      float b = %s;\n"
                      "      vec2 sz = vec2(textureSize(u_tex%d, 0));\n"
                      "      vec2 uv = q.xy / qw * u_scale[%d] * sz - 0.5, f = fract(uv), base = (floor(uv) + 0.5) / sz;\n"
                      "      float c[4];\n"
                      "      for (int k = 0; k < 4; k++) {\n"
                      "          float a = texture(u_tex%d, base + vec2(k & 1, k >> 1) / sz).r;\n"
                      "%s"
                      "          c[k] = %s ? 1.0 : 0.0;\n"
                      "      }\n"
                      "      R%d = vec4(mix(mix(c[0], c[1], f.x), mix(c[2], c[3], f.x), f.y)); }\n",
                   i, bexpr, i, i, i, fl4, getenv("XBRT_GL_NO_SHADOW") ? "true" : fs_cmp(k->shadow_func), 8 + i);
        } else if ((mode == 0x0F || mode == 0x10) && i > 0) { /* dependent: looked up at the stage before's alpha and red, or green and blue */
            fsput(&s, "    R%d = texture(u_tex%d, R%d.%s);\n", 8 + i, i, 7 + i, mode == 0x0F ? "ar" : "gb"); /* (0..1 already) */
        } else {
            fsput(&s, "    { vec4 q = v_t%d; vec2 st = q.w != 0.0 && q.w != 1.0 ? q.xy / q.w : q.xy;\n"
                      "      R%d = texture(u_tex%d, st * u_scale[%d]); }\n", i, 8 + i, i, i);
        }
    }
    fsput(&s, "    R12.a = %s;\n", k->mode[0] != 0 ? "R8.a" : "1.0");
    /* The combiner stages. */
    int stages = (int)(k->ctl & 255) < 8 ? (int)(k->ctl & 255) : 8;
    int msb = (k->ctl & 256) != 0;
    const char *mux = msb ? "(P12.a >= 0.5)" : "((int(P12.a * 255.0) & 1) != 0)";
    char A[256], B[256], C[256], D[256], x[512], y[512];
    for (int st = 0; st < stages; st++) {
        fsput(&s, "    // stage %d\n    R1 = u_c0[%d]; R2 = u_c1[%d];\n", st, (k->ctl & 0x1000) ? st : 0, (k->ctl & 0x10000) ? st : 0);
        for (int i = 0; i < 16; i++) fsput(&s, "    P%d = R%d;\n", i, i);
        for (int half = 0; half < 2; half++) {
            uint32_t icw = half ? k->aicw[st] : k->cicw[st], ocw = half ? k->aocw[st] : k->cocw[st];
            uint32_t fl = ocw >> 12, m = fl & 0x38, dab = (ocw >> 4) & 15, dcd = ocw & 15, dms = (ocw >> 8) & 15;
            if (!dab && !dcd && !dms) continue;
            if (!half) {
                fs_in_rgb(A, sizeof A, icw >> 24 & 255, NULL), fs_in_rgb(B, sizeof B, icw >> 16 & 255, NULL);
                fs_in_rgb(C, sizeof C, icw >> 8 & 255, NULL), fs_in_rgb(D, sizeof D, icw & 255, NULL);
                fsput(&s, "    { vec3 a = %s, b = %s, c = %s, d = %s;\n", A, B, C, D);
                fsput(&s, "      vec3 x = %s, y = %s;\n", (fl & 2) ? "vec3(dot(a, b))" : "a * b", (fl & 1) ? "vec3(dot(c, d))" : "c * d");
                fs_map_out(x, sizeof x, m, (fl & 4) ? "(MUX ? y : x)" : "(x + y)");
                char ms[1024];
                snprintf(ms, sizeof ms, "%s", x);
                char *mx = strstr(ms, "MUX");
                if (mx) { /* splice the mux condition in */
                    char t[1400];
                    snprintf(t, sizeof t, "%.*s%s%s", (int)(mx - ms), ms, mux, mx + 3);
                    snprintf(ms, sizeof ms, "%s", t);
                }
                fs_map_out(x, sizeof x, m, "x"), fs_map_out(y, sizeof y, m, "y");
                fsput(&s, "      vec3 ab = %s, cd = %s, ms = %s;\n", x, y, ms);
                if (dab) fsput(&s, "      R%u.rgb = ab;\n", dab);
                if (dcd) fsput(&s, "      R%u.rgb = cd;\n", dcd);
                if (dms) fsput(&s, "      R%u.rgb = ms;\n", dms);
                if (dab && (fl & 0x80)) fsput(&s, "      R%u.a = ab.b;\n", dab);
                if (dcd && (fl & 0x40)) fsput(&s, "      R%u.a = cd.b;\n", dcd);
                fsput(&s, "    }\n");
            } else {
                fs_in_a(A, sizeof A, icw >> 24 & 255, NULL), fs_in_a(B, sizeof B, icw >> 16 & 255, NULL);
                fs_in_a(C, sizeof C, icw >> 8 & 255, NULL), fs_in_a(D, sizeof D, icw & 255, NULL);
                fsput(&s, "    { float a = %s, b = %s, c = %s, d = %s;\n      float x = a * b, y = c * d;\n", A, B, C, D);
                char ms[1024];
                fs_map_out(x, sizeof x, m, (fl & 4) ? "(MUX ? y : x)" : "(x + y)");
                snprintf(ms, sizeof ms, "%s", x);
                char *mx = strstr(ms, "MUX");
                if (mx) {
                    char t[1400];
                    snprintf(t, sizeof t, "%.*s%s%s", (int)(mx - ms), ms, mux, mx + 3);
                    snprintf(ms, sizeof ms, "%s", t);
                }
                fs_map_out(x, sizeof x, m, "x"), fs_map_out(y, sizeof y, m, "y");
                fsput(&s, "      float ab = %s, cd = %s, ms = %s;\n", x, y, ms);
                if (dab) fsput(&s, "      R%u.a = ab;\n", dab);
                if (dcd) fsput(&s, "      R%u.a = cd;\n", dcd);
                if (dms) fsput(&s, "      R%u.a = ms;\n", dms);
                fsput(&s, "    }\n");
            }
        }
    }
    /* The final combiner. */
    if (!k->f0 && !k->f1) {
        fsput(&s, "    vec4 o = clamp(R12, 0.0, 1.0);\n");
    } else {
        uint32_t f0 = k->f0, f1 = k->f1;
        fsput(&s, "    R1 = u_fc0; R2 = u_fc1;\n");
        fsput(&s, "    vec3 v1 = %s, r0 = %s;\n", (f1 & 0x40) ? "1.0 - R5.rgb" : "R5.rgb", (f1 & 0x20) ? "1.0 - R12.rgb" : "R12.rgb");
        fsput(&s, "    R14.rgb = %s;\n", (f1 & 0x80) ? "clamp(v1 + r0, 0.0, 1.0)" : "v1 + r0");
        for (int i = 0; i < 16; i++) fsput(&s, "    P%d = R%d;\n", i, i);
        fs_in_rgb(A, sizeof A, f1 >> 24 & 255, NULL), fs_in_rgb(B, sizeof B, f1 >> 16 & 255, NULL);
        fsput(&s, "    vec3 E = %s, F = %s;\n", A, B);
        const char *ef = "vec4(E * F, 0.0)";
        fs_in_rgb(A, sizeof A, f0 >> 24 & 255, ef), fs_in_rgb(B, sizeof B, f0 >> 16 & 255, ef);
        fs_in_rgb(C, sizeof C, f0 >> 8 & 255, ef), fs_in_rgb(D, sizeof D, f0 & 255, ef);
        fsput(&s, "    vec3 fa = %s, fb = %s, fc = %s, fd = %s;\n", A, B, C, D);
        fs_in_a(A, sizeof A, f1 >> 8 & 255, ef);
        fsput(&s, "    vec4 o;\n    o.rgb = clamp(fd + fa * fb + (1.0 - fa) * fc, 0.0, 1.0);\n    o.a = clamp(%s, 0.0, 1.0);\n", A);
    }
    if (k->alpha_func) fsput(&s, "    { float a = o.a, b = u_alpha_ref; if (!%s) discard; }\n", fs_cmp(k->alpha_func - 0x200));
    fsput(&s, "    o_color = o;\n");
    if (k->depth)
        fsput(&s, "#ifdef WBARY\n    float zw = dot(gl_BaryCoordNoPerspNV, vec3(v_wv[0], v_wv[1], v_wv[2]));\n#else\n    float zw = v_w;\n#endif\n"
                  "    float z = u_zr.w > 0.5 ? zw : gl_FragCoord.z * u_zr.x;\n"
                  "    if (u_zoff.x != 0.0 || u_zoff.y != 0.0) {\n"
                  "        float slope = max(abs(dFdx(z)), abs(dFdy(z))) * u_zoff.z;\n"
                  "        z += u_zoff.x + (isinf(slope) || isnan(slope) ? 0.0 : u_zoff.y * slope);\n"
                  "    }\n"
                  "    if (u_zr.w > 1.5 && (z < u_zr.y || z > u_zr.z || isnan(z))) discard;\n"
                  "    if (u_zr.w > 0.5 || u_zoff.x != 0.0 || u_zoff.y != 0.0) z = clamp(z, u_zr.y, u_zr.z);\n"
                  "    gl_FragDepth = isnan(z) ? gl_FragCoord.z : clamp(z / u_zr.x, 0.0, 1.0);\n");
    fsput(&s, "}\n");
    return s.p;
}

/* The key for the draw about to be made: fs_src's uniforms that change
 * what it does, as gl_frag_state sets them. */
static void gl_fs_key(const DrawState *d, FsKey *k) {
    memset(k, 0, sizeof *k);
    k->ctl = K(SET_COMBINER_CONTROL);
    int stages = (int)(k->ctl & 255) < 8 ? (int)(k->ctl & 255) : 8;
    for (int i = 0; i < stages; i++) {
        k->cicw[i] = K(SET_COMBINER_COLOR_ICW + 4 * i), k->cocw[i] = K(SET_COMBINER_COLOR_OCW + 4 * i);
        k->aicw[i] = K(SET_COMBINER_ALPHA_ICW + 4 * i), k->aocw[i] = K(SET_COMBINER_ALPHA_OCW + 4 * i);
    }
    k->f0 = K(SET_COMBINER_SPECULAR_FOG_CW0), k->f1 = K(SET_COMBINER_SPECULAR_FOG_CW1);
    int shadow = 0;
    for (int i = 0; i < 4; i++) {
        Texture *t = d->tex[i];
        k->mode[i] = (uint8_t)d->mode[i];
        k->kind[i] = !t ? 0 : t->depth ? (t->surface ? 4 : 3) : t->cube ? 2 : 1;
        if (k->kind[i] >= 3) shadow = 1;
    }
    if (shadow) k->shadow_func = (uint8_t)(K(SET_SHADOW_DEPTH_FUNC) & 7);
    k->alpha_func = K(SET_ALPHA_TEST_ENABLE) && !(rt_debug_keys & RT_DBG_NO_ALPHA) ? (uint16_t)K(SET_ALPHA_FUNC) : 0;
    k->depth = !(gl_frag_variant() & 1);
}

static int gl_fs_on(void) {
    static int on = -1;
    if (on < 0) on = !getenv("XBRT_GL_SPECIALIZE") || atoi(getenv("XBRT_GL_SPECIALIZE"));
    return on;
}

/* The shader for k, compiled the first time it is asked for. NULL: it does
 * not compile (fs_src then). */
static GlFs *gl_fs_get(const FsKey *k) {
    static GlFs *last;
    GlFs *f = NULL;
    if (last && !memcmp(&last->key, k, sizeof *k)) f = last;
    for (int i = 0; i < gl_nfs && !f; i++)
        if (!memcmp(&gl_fs_cache[i].key, k, sizeof *k)) f = last = &gl_fs_cache[i];
    if (f) {
        if (!f->ok) { /* compiling: done yet? */
            GLint done = 1, ok = 0;
            glGetShaderiv(f->fs, GL_COMPLETION_STATUS, &done);
            if (!done) return NULL;
            glGetShaderiv(f->fs, GL_COMPILE_STATUS, &ok);
            f->ok = ok ? 1 : -1;
            if (!ok) {
                char log[4096];
                glGetShaderInfoLog(f->fs, sizeof log, NULL, log);
                fprintf(stderr, "xbrt: a specialised shader does not compile:\n%s\n", log);
            }
        }
        return f->ok > 0 ? f : NULL;
    }
    if (gl_nfs == gl_fs_cap) {
        gl_fs_cap = gl_fs_cap ? gl_fs_cap * 2 : 128;
        gl_fs_cache = realloc(gl_fs_cache, (size_t)gl_fs_cap * sizeof *gl_fs_cache);
        last = NULL; /* it pointed into the old array */
    }
    f = &gl_fs_cache[gl_nfs++];
    memset(f, 0, sizeof *f);
    f->key = *k;
    last = f;
    char *src = fs_generate(k);
    if (rt_gl_parallel) { /* asked again at the next draw that needs it */
        f->fs = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(f->fs, 1, (const char *const *)&src, NULL);
        glCompileShader(f->fs);
        free(src);
        return NULL;
    }
    f->fs = compile(GL_FRAGMENT_SHADER, src);
    free(src);
    f->ok = f->fs ? 1 : -1;
    return f->ok > 0 ? f : NULL;
}

/* Vertex shader vs linked with the fragment shader made for this draw:
 * linked the first time the pair meets, then kept (an open-addressed table
 * by the two). Separable programs in a pipeline would have spared the
 * links, but on this driver the cars came out black through them. NULL:
 * use the shader that reads the state from uniforms. */
static GlProg *gl_fs_program(GLuint vs, const DrawState *d) {
    static struct {
        GLuint vs;
        int fs, state; /* state: 1 linked, 0 linking, -1 failed */
        GlProg *p;
    } pairs[8192];
    if (!vs || !gl_fs_on()) return NULL;
    FsKey k;
    gl_fs_key(d, &k);
    GlFs *f = gl_fs_get(&k);
    if (!f) return NULL;
    int fi = (int)(f - gl_fs_cache);
    uint32_t h = ((uint32_t)vs * 2654435761u ^ (uint32_t)fi * 40503u) & 8191;
    for (int n = 0; n < 8192; n++, h = (h + 1) & 8191) {
        if (pairs[h].p && pairs[h].vs == vs && pairs[h].fs == fi) {
            if (pairs[h].state == 0 && gl_link_done(pairs[h].p)) pairs[h].state = gl_link_finish(pairs[h].p) ? 1 : -1;
            return pairs[h].state > 0 ? pairs[h].p : NULL;
        }
        if (!pairs[h].p) break;
    }
    if (pairs[h].p) return NULL; /* full: tens of thousands of pairs never happen */
    GlProg *p = calloc(1, sizeof *p);
    gl_link_start(p, vs, f->fs);
    pairs[h].vs = vs, pairs[h].fs = fi, pairs[h].p = p, pairs[h].state = 0;
    if (!rt_gl_parallel) pairs[h].state = gl_link_finish(p) ? 1 : -1;
    return pairs[h].state > 0 ? p : NULL;
}
