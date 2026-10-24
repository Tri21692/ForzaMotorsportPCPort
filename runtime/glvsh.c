/* Vertex programs on the host GPU (docs/GPU.md, step 3), with XBRT_GPU=gl;
 * XBRT_GPU_VSH=0 leaves them to the CPU (run_program), for comparison.
 *
 * Included by raster.c after glfill.c. A draw whose transform mode is a
 * vertex program goes up as the vertices D3D fetched (all sixteen
 * attributes) and an index list from the primitive type; a vertex shader
 * generated from the decoded program (vprog, see vsh_decode) does what
 * run_program and project() do on the CPU, then hands the fragment shader
 * the same values the CPU path's vertex shader does. One GL program per
 * vertex program, made the first time it is drawn with.
 *
 * Programs that write the constants (an output to c[], not to o[]) stay
 * on the CPU: those writes would have to reach later vertices and draws.
 */

typedef struct {
    uint64_t key;          /* hash of the decoded instructions it was made from */
    uint32_t start, n;     /* slots */
    VshIns ins[136];
    GlProg prog;
    int ok;
    uint16_t inputs; /* the attributes it reads (bit per v register) */
} GlVsh;

static GlVsh *gl_vsh;
static int gl_nvsh, gl_vsh_cap;
static GLuint gl_vsh_vao, gl_vsh_vbo, gl_vsh_ibo;

/* The decoded program's extent and whether the GPU can run it. */
static int vsh_extent(uint32_t *n_out) {
    uint32_t n = 0;
    for (uint32_t slot = vprog_start; slot < 136; slot++) {
        const VshIns *d = &vprog[slot];
        n++;
        if (d->o_mask && d->orb == 0 && ((d->o_mux == 0 && d->mac && d->mac != 13) || (d->o_mux == 1 && d->ilu))) return 0;
        if (d->final) break;
    }
    *n_out = n;
    return 1;
}

static uint64_t vsh_key(uint32_t n) {
    return hash_bytes((const uint8_t *)&vprog[vprog_start], n * (uint32_t)sizeof(VshIns)) ^ vprog_start;
}

/* ---- GLSL from the decoded program ---- */

typedef struct {
    char *p;
    size_t n, cap;
} Str;

static void put(Str *s, const char *fmt, ...) {
    va_list ap;
    for (;;) {
        va_start(ap, fmt);
        int k = vsnprintf(s->p + s->n, s->cap - s->n, fmt, ap);
        va_end(ap);
        if (k >= 0 && s->n + (size_t)k < s->cap) {
            s->n += (size_t)k;
            return;
        }
        s->cap = s->cap * 2 + (size_t)(k > 0 ? k : 256);
        s->p = realloc(s->p, s->cap);
    }
}

static void vsh_glsl_in(Str *s, const VshIns *ins, const VshIn *d) {
    static const char xyzw[] = "xyzw";
    char sw[5] = {xyzw[d->sel[0]], xyzw[d->sel[1]], xyzw[d->sel[2]], xyzw[d->sel[3]], 0};
    const char *neg = d->neg ? "-" : "";
    if (d->mux == 1 && d->reg == 12) put(s, "%so[0].%s", neg, sw);
    else if (d->mux == 1 && d->reg < 12) put(s, "%sr[%d].%s", neg, d->reg, sw);
    else if (d->mux == 2) put(s, "%sa_in[%d].%s", neg, ins->attr, sw);
    else if (d->mux == 3 && ins->rel) put(s, "%scon(%d + a0).%s", neg, ins->c, sw);
    else if (d->mux == 3) put(s, "%scon(%d).%s", neg, ins->c, sw);
    else put(s, "vec4(0.0)");
}

static void vsh_mask(Str *s, uint32_t mask, char *out) {
    (void)s;
    int k = 0;
    for (int i = 0; i < 4; i++)
        if (mask & (8u >> i)) out[k++] = "xyzw"[i];
    out[k] = 0;
}

static char *vsh_glsl(const VshIns *prog, uint32_t n) {
    Str s = {malloc(16384), 0, 16384};
    put(&s, "#version 430\n"
            "layout(location = 0) in vec4 a_in[16];\n"
            "uniform vec4 u_vc[192];\n"
            "uniform vec2 u_size, u_sxy;\n"
            "uniform float u_zmax;\n"
            "uniform vec4 u_fog;\n" /* enable, mode, param 0, param 1 */
            "out vec4 v_c0, v_c1, v_t0, v_t1, v_t2, v_t3;\n"
            "out float v_fog;\n"
            "noperspective out float v_zs;\n"
            "out float v_w;\n"
            "vec4 con(int i) { return i >= 0 && i < 192 ? u_vc[i] : vec4(0.0); }\n"
            /* The NV2A's multiply: zero times anything (infinity too) is zero. */
            "vec4 mulz(vec4 a, vec4 b) { vec4 m = a * b;\n"
            "    for (int k = 0; k < 4; k++) if (a[k] == 0.0 || b[k] == 0.0) m[k] = 0.0; return m; }\n"
            "float fogf(float d) {\n"
            "    if (u_fog.x == 0.0) return 1.0;\n"
            "    int m = int(u_fog.y); float f;\n"
            "    if (m == 0x800 || m == 0x802) f = u_fog.z + exp2(d * u_fog.w * 16.0) - 1.5;\n"
            "    else if (m == 0x801 || m == 0x803) f = u_fog.z + exp2(-d * d * u_fog.w * u_fog.w * 32.0) - 1.5;\n"
            "    else f = u_fog.z + d * u_fog.w - 1.0;\n"
            "    if (m == 0x802 || m == 0x803 || m == 0x804) f = abs(f);\n"
            "    return isnan(f) ? 1.0 : f;\n"
            "}\n"
            "float clampc(float x, float nan_as) { return isnan(x) ? nan_as : clamp(x, 0.0, 1.0); }\n"
            "void main() {\n"
            "    vec4 r[12];\n"
            "    for (int i = 0; i < 12; i++) r[i] = vec4(0.0);\n"
            "    vec4 o[16];\n"
            "    for (int i = 0; i < 16; i++) o[i] = vec4(0.0);\n"
            "    o[3].w = 1.0; o[4].w = 1.0; o[9].w = 1.0; o[10].w = 1.0; o[11].w = 1.0; o[12].w = 1.0;\n"
            "    int a0 = 0;\n"
            "    vec4 A, B, C, m, l; float x;\n");
    for (uint32_t i = 0; i < n; i++) {
        const VshIns *d = &prog[i];
        put(&s, "    A = "), vsh_glsl_in(&s, d, &d->in[0]), put(&s, "; B = "), vsh_glsl_in(&s, d, &d->in[1]);
        put(&s, "; C = "), vsh_glsl_in(&s, d, &d->in[2]), put(&s, "; x = C.x;\n");
        switch (d->mac) {
        case 1: put(&s, "    m = A;\n"); break;
        case 2: put(&s, "    m = mulz(A, B);\n"); break;
        case 3: put(&s, "    m = A + C;\n"); break;
        case 4: put(&s, "    m = mulz(A, B) + C;\n"); break;
        case 5: put(&s, "    m = vec4(A.x * B.x + A.y * B.y + A.z * B.z);\n"); break;
        case 6: put(&s, "    m = vec4(A.x * B.x + A.y * B.y + A.z * B.z + B.w);\n"); break;
        case 7: put(&s, "    m = vec4(A.x * B.x + A.y * B.y + A.z * B.z + A.w * B.w);\n"); break;
        case 8: put(&s, "    m = vec4(1.0, A.y * B.y, A.z, B.w);\n"); break;
        case 9: put(&s, "    m = min(A, B);\n"); break;
        case 10: put(&s, "    m = max(A, B);\n"); break;
        case 11: put(&s, "    m = vec4(lessThan(A, B));\n"); break;
        case 12: put(&s, "    m = vec4(greaterThanEqual(A, B));\n"); break;
        default: put(&s, "    m = vec4(0.0);\n");
        }
        switch (d->ilu) {
        case 1: put(&s, "    l = C;\n"); break;
        case 2: put(&s, "    l = vec4(1.0 / x);\n"); break;
        case 3: put(&s, "    { float v = 1.0 / x; if (abs(v) < 5.42101e-20) v = v < 0.0 ? -5.42101e-20 : 5.42101e-20;\n"
                        "      if (abs(v) > 1.884467e+19) v = v < 0.0 ? -1.884467e+19 : 1.884467e+19; l = vec4(v); }\n"); break;
        case 4: put(&s, "    l = vec4(x == 0.0 ? uintBitsToFloat(0x7F800000u) : inversesqrt(abs(x)));\n"); break;
        case 5: put(&s, "    l = vec4(exp2(floor(x)), x - floor(x), exp2(x), 1.0);\n"); break;
        case 6: put(&s, "    { float a = abs(x); if (a == 0.0) l = vec4(uintBitsToFloat(0xFF800000u), 1.0, uintBitsToFloat(0xFF800000u), 1.0);\n"
                        "      else l = vec4(floor(log2(a)), a / exp2(floor(log2(a))), log2(a), 1.0); }\n"); break;
        case 7: put(&s, "    { float dd = max(C.x, 0.0), ss = max(C.y, 0.0), pp = clamp(C.w, -127.9961, 127.9961);\n"
                        "      l = vec4(1.0, dd, dd > 0.0 ? pow(ss, pp) : 0.0, 1.0); }\n"); break;
        default: put(&s, "    l = vec4(0.0);\n");
        }
        char mk[5];
        if (d->mac == 13) {
            put(&s, "    a0 = int(floor(A.x + 0.001));\n");
        } else if (d->mac) {
            vsh_mask(&s, d->mac_mask, mk);
            if (*mk && !(d->ilu && d->out_reg == 1) && d->out_reg < 12) put(&s, "    r[%d].%s = m.%s;\n", d->out_reg, mk, mk);
            if (*mk && d->out_reg == 12) put(&s, "    o[0].%s = m.%s;\n", mk, mk);
        }
        if (d->ilu) {
            uint32_t reg = d->mac ? 1 : d->out_reg;
            vsh_mask(&s, d->ilu_mask, mk);
            if (*mk && reg < 12) put(&s, "    r[%u].%s = l.%s;\n", reg, mk, mk);
            else if (*mk && reg == 12) put(&s, "    o[0].%s = l.%s;\n", mk, mk);
        }
        if (d->o_mask && (d->mac || d->ilu) && d->orb == 1 &&
            ((d->o_mux == 0 && d->mac && d->mac != 13) || (d->o_mux == 1 && d->ilu))) {
            vsh_mask(&s, d->o_mask, mk);
            put(&s, "    o[%d].%s = %c.%s;\n", d->o_addr & 15, mk, d->o_mux ? 'l' : 'm', mk);
        }
    }
    /* What project() and the CPU path's vertex shader do with the outputs:
     * oPos in surface coordinates (pixels; samples once scaled), D3D's
     * programs having divided by w themselves. */
    put(&s, "    vec4 P = o[0];\n"
            "    float w = abs(P.w) < 1e-20 ? 1.0 : P.w;\n"
            "    vec3 ndc = vec3(P.x * u_sxy.x / u_size.x * 2.0 - 1.0, P.y * u_sxy.y / u_size.y * 2.0 - 1.0,\n"
            "                    clamp(P.z / u_zmax, 0.0, 1.0) * 2.0 - 1.0);\n"
            "    gl_Position = vec4(ndc * w, w);\n"
            "    v_zs = P.z; v_w = w;\n"
            "    v_c0 = vec4(clampc(o[3].x, 1.0), clampc(o[3].y, 1.0), clampc(o[3].z, 1.0), clampc(o[3].w, 1.0));\n"
            "    v_c1 = vec4(clampc(o[4].x, 0.0), clampc(o[4].y, 0.0), clampc(o[4].z, 0.0), clampc(o[4].w, 0.0));\n"
            "    v_t0 = o[9]; v_t1 = o[10]; v_t2 = o[11]; v_t3 = o[12];\n"
            "    v_fog = fogf(o[5].x);\n"
            "}\n");
    return s.p;
}

/* ---- programs ---- */

static GlVsh *gl_vsh_get(uint32_t n) {
    uint64_t key = vsh_key(n);
    static GlVsh *last;
    if (last && last->key == key && last->start == vprog_start && last->n == n &&
        !memcmp(last->ins, &vprog[vprog_start], n * sizeof(VshIns)))
        return last;
    for (int i = 0; i < gl_nvsh; i++) {
        GlVsh *v = &gl_vsh[i];
        if (v->key == key && v->start == vprog_start && v->n == n && !memcmp(v->ins, &vprog[vprog_start], n * sizeof(VshIns)))
            return last = v;
    }
    if (gl_nvsh == gl_vsh_cap) {
        gl_vsh_cap = gl_vsh_cap ? gl_vsh_cap * 2 : 64;
        gl_vsh = realloc(gl_vsh, (size_t)gl_vsh_cap * sizeof *gl_vsh);
        last = NULL;
    }
    GlVsh *v = &gl_vsh[gl_nvsh++];
    memset(v, 0, sizeof *v);
    v->key = key, v->start = vprog_start, v->n = n;
    memcpy(v->ins, &vprog[vprog_start], n * sizeof(VshIns));
    for (uint32_t i = 0; i < n; i++)
        for (int k = 0; k < 3; k++)
            if (v->ins[i].in[k].mux == 2) v->inputs |= (uint16_t)(1u << (v->ins[i].attr & 15));
    char *src = vsh_glsl(v->ins, n);
    GLuint vs = compile(GL_VERTEX_SHADER, src);
    free(src);
    v->ok = vs && gl_link(&v->prog, vs);
    if (vs) glDeleteShader(vs);
    if (rt_log_level) rt_log("gl: vertex program %d (%u slots from %u)%s\n", gl_nvsh, n, vprog_start, v->ok ? "" : " does not compile");
    return last = v;
}

static int gl_vsh_on(void) {
    static int on = -1;
    if (on < 0) on = !getenv("XBRT_GPU_VSH") || atoi(getenv("XBRT_GPU_VSH"));
    return on;
}

/* Forza's shadow matrices and the 60 fps patch. Each frame draws the
 * surfaces that receive shadows first and the shadow map last; the
 * receivers look the map up with the light matrix in c92-c95 (and its
 * scale in c90.xyz). With the patch the game presents every frame where it
 * used to present every other one, and on the odd frames the receivers
 * carry the next light matrix while the map they read was drawn with the
 * previous one: whole objects turned from lit to shadowed and back, the
 * flicker of the buildings and signs at 60 fps. So a draw that samples a
 * shadow map takes those rows as the map's own draws had them. At 30 fps
 * they already match. XBRT_SHADOW_SYNC=0 turns it off. */
#define SHADOW_ROWS_FIRST 90
#define SHADOW_ROWS_LAST 95
typedef struct {
    uint32_t zaddr;
    float rows[SHADOW_ROWS_LAST - SHADOW_ROWS_FIRST + 1][4];
} ShadowRows;
static ShadowRows shadow_rows[4];

static void gl_shadow_sync(const DrawState *d, const GlSurf *s, float c[192][4]) {
    static int on = -1;
    if (on < 0) on = !getenv("XBRT_SHADOW_SYNC") || atoi(getenv("XBRT_SHADOW_SYNC"));
    if (!on) return;
    if (s->ztex && s->cbase == s->zbase) { /* drawing a shadow map (colour and depth at one address): remember its rows */
        uint32_t z = s->zbase & (RT_PHYS_SIZE - 1);
        int k = 0;
        while (k < 3 && shadow_rows[k].zaddr && shadow_rows[k].zaddr != z) k++;
        shadow_rows[k].zaddr = z;
        memcpy(shadow_rows[k].rows, c[SHADOW_ROWS_FIRST], sizeof shadow_rows[k].rows);
        return;
    }
    for (int i = 0; i < 4; i++) {
        const Texture *t = d->tex[i];
        if (!t || !t->depth || !t->zaddr) continue;
        for (int k = 0; k < 4; k++)
            if (shadow_rows[k].zaddr == t->zaddr) {
                const float(*r)[4] = shadow_rows[k].rows;
                for (int j = 0; j < 3; j++) c[SHADOW_ROWS_FIRST][j] = r[0][j]; /* c90: the scale, not its w */
                memcpy(c[92], r[92 - SHADOW_ROWS_FIRST], 4 * 4 * sizeof(float));
                return;
            }
    }
}

/* Draws verts[0..n) as primitive prim with the current vertex program on
 * the GPU. 0: not handled here (the CPU path draws it). */
/* XBRT_STATS: where a draw's time goes (program and indices, gl_bind,
 * vertex upload, constants, gl_frag_state, the draw call). */
uint64_t prof_t[6], prof_n, prof_verts;

static int gl_draw_vsh(const DrawState *d, const Vertex *vs, int n, int prim) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || n < 3) return gl_ready ? 1 : 0;
    uint32_t len;
    if (!vsh_extent(&len)) return 0;
    uint64_t p0 = rt_now_100ns();
    GlVsh *v = gl_vsh_get(len);
    if (!v->ok) return 0;

    /* The index list, in add_tri's order. */
    static GLuint *idx;
    static int idx_cap;
    if (n * 6 > idx_cap) idx_cap = n * 6, idx = realloc(idx, (size_t)idx_cap * sizeof *idx);
    int k = 0;
#define TRI(a, b, c) (idx[k++] = (GLuint)(a), idx[k++] = (GLuint)(b), idx[k++] = (GLuint)(c))
    switch (prim) {
    case 5: for (int i = 0; i + 2 < n; i += 3) TRI(i, i + 1, i + 2); break;
    case 6: for (int i = 0; i + 2 < n; i++) i & 1 ? TRI(i + 1, i, i + 2) : TRI(i, i + 1, i + 2); break;
    case 7: case 10: for (int i = 1; i + 1 < n; i++) TRI(0, i, i + 1); break;
    case 8: for (int i = 0; i + 3 < n; i += 4) TRI(i, i + 1, i + 2), TRI(i, i + 2, i + 3); break;
    case 9: for (int i = 0; i + 3 < n; i += 2) TRI(i, i + 1, i + 3), TRI(i, i + 3, i + 2); break;
    default: return 1; /* points and lines: not drawn, as on the CPU path */
    }
#undef TRI
    if (!k) return 1;
    uint64_t p1 = rt_now_100ns();
    GlSurf *s = gl_bind(d);
    uint64_t p2 = rt_now_100ns();
    GlProg *p = gl_variant(&v->prog, gl_frag_variant());
    gl_use(p);
    if (!gl_vsh_vao) {
        glGenVertexArrays(1, &gl_vsh_vao);
        glBindVertexArray(gl_vsh_vao);
        glGenBuffers(1, &gl_vsh_vbo);
        glGenBuffers(1, &gl_vsh_ibo);
        glBindBuffer(GL_ARRAY_BUFFER, gl_vsh_vbo);
        for (int a = 0; a < NATTR; a++) {
            glVertexAttribPointer((GLuint)a, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void *)(uintptr_t)(a * 4 * sizeof(float)));
            glEnableVertexAttribArray((GLuint)a);
        }
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, gl_vsh_ibo);
    }
    glBindVertexArray(gl_vsh_vao);
    glBindBuffer(GL_ARRAY_BUFFER, gl_vsh_vbo);
    /* Only the attributes the program reads, packed: all sixteen were
     * 256 bytes a vertex, some 60 MB a frame in a race. */
    static float *packed;
    static int packed_cap;
    static int last_inputs = -1;
    int used[16], m = 0;
    for (int a = 0; a < NATTR; a++)
        if (v->inputs & (1u << a)) used[m++] = a;
    if (!m) used[m++] = 0;
    if (n * m * 4 > packed_cap) packed_cap = n * m * 4, packed = realloc(packed, (size_t)packed_cap * sizeof *packed);
    for (int i = 0; i < n; i++)
        for (int j = 0; j < m; j++) memcpy(packed + (i * m + j) * 4, vs[i].a[used[j]], 16);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)n * m * 16, packed, GL_STREAM_DRAW);
    if (v->inputs != last_inputs) {
        for (int a = 0; a < NATTR; a++) glDisableVertexAttribArray((GLuint)a);
        for (int j = 0; j < m; j++) {
            glVertexAttribPointer((GLuint)used[j], 4, GL_FLOAT, GL_FALSE, m * 16, (void *)(uintptr_t)(j * 16));
            glEnableVertexAttribArray((GLuint)used[j]);
        }
        last_inputs = v->inputs;
    }
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, (GLsizeiptr)k * (GLsizeiptr)sizeof(GLuint), idx, GL_STREAM_DRAW);
    uint64_t p3 = rt_now_100ns();

    float c[192][4];
    for (int i = 0; i < 192; i++)
        for (int j = 0; j < 4; j++) c[i][j] = f32(constants[i][j]);
    gl_shadow_sync(d, s, c);
    glUniform4fv(p->vc, 192, &c[0][0]);
    float sxy[2] = {(float)d->sx, (float)d->sy};
    glUniform2fv(p->sxy, 1, sxy);
    float fog[4] = {K(SET_FOG_ENABLE) ? 1.0f : 0.0f, (float)K(SET_FOG_MODE), f32(K(SET_FOG_PARAMS)), f32(K(SET_FOG_PARAMS + 4))};
    glUniform4fv(p->fog, 1, fog);
    uint64_t p4 = rt_now_100ns();
    gl_frag_state(d, s);
    uint64_t p5 = rt_now_100ns();
    glDrawElements(GL_TRIANGLES, k, GL_UNSIGNED_INT, NULL);
    uint64_t p6 = rt_now_100ns();
    prof_t[0] += p1 - p0, prof_t[1] += p2 - p1, prof_t[2] += p3 - p2, prof_t[3] += p4 - p3, prof_t[4] += p5 - p4, prof_t[5] += p6 - p5;
    prof_n++, prof_verts += (uint64_t)n;
    glBindVertexArray(gl_vao);
    s->dirty = s->cdirty = 1, s->seq = ++gl_seq;
    if (d->ztest && d->zwrite && s->ztex) s->zdirty = 1, s->zgpu = 0;
    gl_drawn(s, d->cx0, d->cy0, d->cx0 + d->cw, d->cy0 + d->ch);
    return 1;
}
