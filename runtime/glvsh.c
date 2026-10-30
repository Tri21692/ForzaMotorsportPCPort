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
    int ok, linking; /* linking: started, not finished (gl_link_done) */
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
            /* A surface drawn again by another program (Forza's lighting
             * passes) must land on exactly the same depth: compiled apart,
             * the same arithmetic could round differently, and the passes
             * fought (flicker on overlapping surfaces). */
            "invariant gl_Position;\n"
            "layout(location = 0) in vec4 a_in[16];\n"
            "uniform vec4 u_vc[192];\n"
            "uniform vec2 u_size, u_sxy;\n"
            "uniform float u_zmax;\n"
            "uniform vec4 u_fog;\n" /* enable, mode, param 0, param 1 */
            "out vec4 v_c0, v_c1, v_t0, v_t1, v_t2, v_t3;\n"
            "out float v_fog;\n"
            "noperspective out float v_zs;\n"
            "out float v_w;\nout float v_wv;\n"
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
            if ((d->o_addr & 15) == 5) /* oFog: the last masked component lands in x, where fog is read (as xemu) */
                put(&s, "    o[5].x = %c.%c;\n", d->o_mux ? 'l' : 'm', mk[strlen(mk) - 1]);
            else
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
            "    v_zs = P.z; v_w = w; v_wv = w;\n"
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
    if (getenv("XBRT_GL_VSH_DUMP")) { /* debugging: each program's GLSL, to <folder>/vsh<n>.glsl */
        char path[600];
        snprintf(path, sizeof path, "%s/vsh%d.glsl", getenv("XBRT_GL_VSH_DUMP"), gl_nvsh);
        FILE *f = fopen(path, "w");
        if (f) fputs(src, f), fclose(f);
    }
    GLuint vs = rt_gl_parallel ? compile_nowait(GL_VERTEX_SHADER, src) : compile(GL_VERTEX_SHADER, src);
    free(src);
    if (vs) { /* linked on the driver's threads where it can: gl_draw_vsh draws on the CPU until it is */
        v->prog.vs = vs, v->prog.var[0] = &v->prog;
        gl_link_start(&v->prog, vs, gl_fs);
        v->linking = 1;
    }
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

/* The vertex cache: a draw from the arrays (its indices recorded by vert_index) keeps its fetched,
 * packed vertices and its index list in GPU buffers, found again by the indices, the attributes'
 * places and formats (and the constant ones' values), and used while the bytes they come from
 * hash the same. The scenery draws the same each frame: fetching every vertex again (fetch_attr,
 * vert_index) and uploading it was a fifth of the device thread on the circuit's slow stretches.
 * A draw whose bytes change three times running (particles, the car's own) is left out for a
 * while. XBRT_GL_VCACHE=0: off. */
#define VC_SLOTS 16384
#define VC_REACH (1u << 20) /* a draw reading more than this much memory is not checked each time */
typedef struct {
    uint64_t key, src, sparse, last;
    GLuint vbo, ibo;
    int k, misses, skip, uses;
    size_t bytes;
} VcEntry;
static VcEntry vc[VC_SLOTS];
static uint64_t vc_clock;
uint64_t vc_bytes, vc_hits, vc_fills, vc_skips, vc_far, vc_first; /* for the stats line (nv2a.c) */
static uint32_t vc_lo, vc_hi; /* the indices' range, from vc_find for vc_source */

static uint64_t vc_mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    return h * 0xFF51AFD7ED558CCDull;
}

static void vc_drop(VcEntry *e) {
    if (e->vbo) glDeleteBuffers(1, &e->vbo), glDeleteBuffers(1, &e->ibo), vc_bytes -= e->bytes;
    memset(e, 0, sizeof *e);
}

/* The draw's entry (found, or a free or least recently used one to fill), or NULL: off, or left
 * out for now. */
static VcEntry *vc_find(int n, int prim, const int *used, int m) {
    static int on = -1;
    if (on < 0) on = !getenv("XBRT_GL_VCACHE") || atoi(getenv("XBRT_GL_VCACHE"));
    if (!on || n < 16) return NULL;
    uint64_t key = vc_mix(hash_bytes((const uint8_t *)vidx, (uint32_t)n * 4), (uint64_t)n << 8 | (uint64_t)prim);
    for (int j = 0; j < m; j++) {
        int f = fattr_of[used[j]];
        if (f < 0) {
            key = vc_mix(key, hash_bytes((const uint8_t *)cur.a[used[j]], 16) ^ (uint64_t)used[j] << 56);
            continue;
        }
        key = vc_mix(key, (uint64_t)fattr[f].base << 32 | fattr[f].stride);
        key = vc_mix(key, (uint64_t)used[j] << 16 | (uint64_t)fattr[f].type << 8 | fattr[f].size);
    }
    vc_clock++;
    VcEntry *pick = NULL;
    for (int p = 0; p < 8; p++) {
        VcEntry *e = &vc[(key + (uint64_t)p) & (VC_SLOTS - 1)];
        if (e->key == key && e->last) {
            e->last = vc_clock;
            if (e->skip) return vc_skips++, e->skip--, NULL;
            return e;
        }
        if (!pick || e->last < pick->last) pick = e;
    }
    /* A draw is let in the second time it is seen: some 50 a frame came new each time (geometry
     * the game writes afresh, at another place each frame) and filled the cache for nothing. */
    static uint64_t seen[VC_SLOTS];
    uint64_t *was_seen = &seen[(key ^ key >> 29) & (VC_SLOTS - 1)];
    if (*was_seen != key) {
        *was_seen = key, vc_first++;
        return NULL;
    }
    if (vc_bytes > (512u << 20)) { /* too much on the GPU: what was not drawn lately goes */
        static int said;
        size_t was = vc_bytes;
        for (int i = 0; i < VC_SLOTS; i++)
            if (vc[i].last && vc[i].last + 40000 < vc_clock) vc_drop(&vc[i]); /* some 20 frames */
        if (vc_bytes > (384u << 20))
            for (int i = 0; i < VC_SLOTS; i++) vc_drop(&vc[i]);
        if (said++ < 20) fprintf(stderr, "xbrt: vertex cache: %zu MB on the GPU, %zu MB after dropping the oldest\n", was >> 20, (size_t)vc_bytes >> 20);
    }
    vc_drop(pick);
    pick->key = key, pick->last = vc_clock;
    uint32_t lo = UINT32_MAX, hi = 0;
    for (int i = 0; i < n; i++) {
        if (vidx[i] < lo) lo = vidx[i];
        if (vidx[i] > hi) hi = vidx[i];
    }
    vc_lo = lo, vc_hi = hi;
    return pick;
}

/* The hash of the memory the draw's attributes come from (each attribute's span over the indices'
 * range, overlapping spans once), or 0 when that is more than VC_REACH: all of it, or (sparse) 64
 * bytes of every 2 KB, as textures are checked. Hashing all of it at every draw was half of what
 * the cache saved. */
static uint64_t vc_source(int n, const int *used, int m, int sparse) {
    if (!vc_hi && !vc_lo) { /* found, not filled now: the range again */
        uint32_t lo = UINT32_MAX, hi = 0;
        for (int i = 0; i < n; i++) {
            if (vidx[i] < lo) lo = vidx[i];
            if (vidx[i] > hi) hi = vidx[i];
        }
        vc_lo = lo, vc_hi = hi;
    }
    uint32_t a[16], b[16];
    int nr = 0;
    for (int j = 0; j < m; j++) {
        int f = fattr_of[used[j]];
        if (f < 0) continue;
        uint32_t s0 = fattr[f].base + vc_lo * fattr[f].stride, s1 = fattr[f].base + vc_hi * fattr[f].stride + 16;
        int r = 0;
        for (; r < nr; r++)
            if (s0 <= b[r] && s1 >= a[r]) break;
        if (r < nr) a[r] = s0 < a[r] ? s0 : a[r], b[r] = s1 > b[r] ? s1 : b[r];
        else a[nr] = s0, b[nr] = s1, nr++;
    }
    vc_lo = vc_hi = 0;
    uint64_t h = 0x84222325CBF29CE4ull;
    uint32_t total = 0;
    for (int r = 0; r < nr; r++) {
        if (b[r] - a[r] > VC_REACH || (total += b[r] - a[r]) > VC_REACH) return 0;
        h = vc_mix(h, sparse ? hash_sparse(phys(a[r]), b[r] - a[r]) : hash_bytes(phys(a[r]), b[r] - a[r]));
    }
    return h | 1;
}

static void vc_store(VcEntry *e, uint64_t src, uint64_t sparse, const float *packed, size_t bytes, const GLuint *idx, int k) {
    if (!e->vbo) glGenBuffers(1, &e->vbo), glGenBuffers(1, &e->ibo);
    else vc_bytes -= e->bytes;
    glBindBuffer(GL_ARRAY_BUFFER, e->vbo);
    glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)bytes, packed, e->misses ? GL_DYNAMIC_DRAW : GL_STATIC_DRAW);
    glBindVertexArray(gl_vsh_vao); /* the element buffer is the vertex array's */
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, e->ibo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, (GLsizeiptr)k * (GLsizeiptr)sizeof(GLuint), idx, GL_STATIC_DRAW);
    e->src = src, e->sparse = sparse, e->uses = 0, e->k = k, e->bytes = bytes + (size_t)k * sizeof(GLuint);
    vc_bytes += e->bytes;
}

static int gl_draw_vsh(const DrawState *d, const Vertex *vs, int n, int prim) {
    if (gl_ready < 0) gl_ready = gl_setup();
    if (!gl_ready || n < 1) return gl_ready ? 1 : 0;
    uint32_t len;
    if (!vsh_extent(&len)) return 0;
    uint64_t p0 = rt_now_100ns();
    GlVsh *v = gl_vsh_get(len);
    static int dumping = -1;
    if (dumping < 0) dumping = getenv("XBRT_GL_VSH_DUMP") != NULL;
    if (dumping) { /* debugging: which program each draw ran, to <folder>/use.txt */
        static FILE *use;
        if (!use) {
            char path[600];
            snprintf(path, sizeof path, "%s/use.txt", getenv("XBRT_GL_VSH_DUMP"));
            use = fopen(path, "w");
        }
        if (use) fprintf(use, "%u %u %d %d\n", nv2a.flips, nv2a.draws, (int)(v - gl_vsh) + 1, n);
    }
    if (v->linking && gl_link_done(&v->prog)) v->linking = 0, v->ok = gl_link_finish(&v->prog);
    if (!v->ok) return 0; /* not linked yet (or not at all): the CPU runs it */
    /* Forza's suggested line: chevrons written straight into the push
     * buffer as an inline triangle list of a position and a colour, whose
     * program samples the anti-aliased scene through projective texture
     * coordinates. Run on the GPU they sampled black and the line never
     * showed; the CPU path draws it right, and it is 162 vertices a frame. */
    if (prim == 5 && ninline && (K(SET_VERTEX_DATA_ARRAY_FORMAT) & 0xFF) == 0x32 && (K(SET_VERTEX_DATA_ARRAY_FORMAT + 12) & 0xFF) == 0x40) {
        int other = 0;
        for (int a = 1; a < 16; a++)
            if (a != 3 && (K(SET_VERTEX_DATA_ARRAY_FORMAT + 4 * a) & 0xF0)) other = 1;
        if (!other) return 0;
    }

    /* The index list, in add_tri's order. */
    static GLuint *idx;
    static int idx_cap;
    if (n * 6 > idx_cap) idx_cap = n * 6, idx = realloc(idx, (size_t)idx_cap * sizeof *idx);
    int k = 0;
    GLenum mode = GL_TRIANGLES;
#define TRI(a, b, c) (idx[k++] = (GLuint)(a), idx[k++] = (GLuint)(b), idx[k++] = (GLuint)(c))
    switch (prim) {
    /* Points and lines, as GL draws them: Forza draws ~30 line strips a
     * frame in a race, the cars' panel seams, and they were dropped. */
    case 1: mode = GL_POINTS; for (int i = 0; i < n; i++) idx[k++] = (GLuint)i; break;
    case 2: mode = GL_LINES; for (int i = 0; i + 1 < n; i += 2) idx[k++] = (GLuint)i, idx[k++] = (GLuint)(i + 1); break;
    case 3: mode = GL_LINE_LOOP; for (int i = 0; i < n; i++) idx[k++] = (GLuint)i; break;
    case 4: mode = GL_LINE_STRIP; for (int i = 0; i < n; i++) idx[k++] = (GLuint)i; break;
    case 5: for (int i = 0; i + 2 < n; i += 3) TRI(i, i + 1, i + 2); break;
    case 6: for (int i = 0; i + 2 < n; i++) i & 1 ? TRI(i + 1, i, i + 2) : TRI(i, i + 1, i + 2); break;
    case 7: case 10: for (int i = 1; i + 1 < n; i++) TRI(0, i, i + 1); break;
    case 8: for (int i = 0; i + 3 < n; i += 4) TRI(i, i + 1, i + 2), TRI(i, i + 2, i + 3); break;
    case 9: for (int i = 0; i + 3 < n; i += 2) TRI(i, i + 1, i + 3), TRI(i, i + 3, i + 2); break;
    default: return 1;
    }
#undef TRI
    if (!k) return 1;
    uint64_t p1 = rt_now_100ns();
    GlSurf *s = gl_bind(d);
    uint64_t p2 = rt_now_100ns();
    /* With the fragment shader made for this draw (glfs.c), else the one
     * that reads the state from uniforms. */
    GlProg *p = gl_fs_program(v->prog.vs, d);
    if (!p) p = rt_gl_parallel ? &v->prog : gl_variant(&v->prog, gl_frag_variant()); /* not the variants: linked when first asked for, they would wait */
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
    /* Only the attributes the program reads, packed: all sixteen were
     * 256 bytes a vertex, some 60 MB a frame in a race. */
    static float *packed;
    static int packed_cap;
    static int last_inputs = -1;
    int used[16], m = 0;
    for (int a = 0; a < NATTR; a++)
        if (v->inputs & (1u << a)) used[m++] = a;
    if (!m) used[m++] = 0;
    /* A draw from the arrays that drew the same last time takes its vertices and indices from the
     * cache, already on the GPU (vc_find). */
    VcEntry *ce = deferred ? vc_find(n, prim, used, m) : NULL;
    uint64_t src = 0;
    int hit = 0;
    uint64_t sparse = 0;
    if (ce) {
        /* a sample of the bytes at each use, all of them every 16th (and when filling) */
        int full = !ce->vbo || ++ce->uses % 16 == 0;
        sparse = vc_source(n, used, m, 1);
        if (full) src = vc_source(n, used, m, 0);
        if (!sparse || (full && !src)) ce = NULL, vc_far++; /* too much of memory to check each time */
        else if (ce->vbo && ce->sparse == sparse && (!full || ce->src == src) && ce->k == k) hit = 1, ce->misses = 0, vc_hits++;
        else if (ce->vbo && ++ce->misses >= 3) ce->skip = 64, ce = NULL; /* changing every time: drawn as before for a while */
        else if (!full) src = vc_source(n, used, m, 0);
    }
    if (!hit) {
        if (n * m * 4 > packed_cap) packed_cap = n * m * 4, packed = realloc(packed, (size_t)packed_cap * sizeof *packed);
        if (deferred) { /* straight from the arrays (raster.c, vert_index) */
            for (int j = 0; j < m; j++) {
                int f = fattr_of[used[j]];
                float *out = packed + j * 4;
                if (f < 0)
                    for (int i = 0; i < n; i++) memcpy(out + i * m * 4, cur.a[used[j]], 16);
                else
                    for (int i = 0; i < n; i++) fetch_attr(&fattr[f], phys(fattr[f].base + vidx[i] * fattr[f].stride), out + i * m * 4);
            }
        } else
            for (int i = 0; i < n; i++)
                for (int j = 0; j < m; j++) memcpy(packed + (i * m + j) * 4, vs[i].a[used[j]], 16);
    }
    if (ce) {
        if (!hit) vc_fills++, vc_store(ce, src, sparse, packed, (size_t)n * m * 16, idx, k);
        glBindBuffer(GL_ARRAY_BUFFER, ce->vbo);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ce->ibo);
    } else {
        glBindBuffer(GL_ARRAY_BUFFER, gl_vsh_vbo);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, gl_vsh_ibo);
        glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)n * m * 16, packed, GL_STREAM_DRAW);
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, (GLsizeiptr)k * (GLsizeiptr)sizeof(GLuint), idx, GL_STREAM_DRAW);
    }
    if (v->inputs != last_inputs) {
        for (int a = 0; a < NATTR; a++) glDisableVertexAttribArray((GLuint)a);
        for (int j = 0; j < m; j++) glEnableVertexAttribArray((GLuint)used[j]);
        last_inputs = v->inputs;
    }
    /* the attributes in the buffer bound now (the cache's or the stream's) */
    for (int j = 0; j < m; j++) glVertexAttribPointer((GLuint)used[j], 4, GL_FLOAT, GL_FALSE, m * 16, (void *)(uintptr_t)(j * 16));
    uint64_t p3 = rt_now_100ns();

    float c[192][4];
    for (int i = 0; i < 192; i++)
        for (int j = 0; j < 4; j++) c[i][j] = f32(constants[i][j]);
    gl_shadow_sync(d, s, c);
    /* Only the rows that changed since this program last got them: a draw changes a few (the
     * world matrix), and sending all 192 at every draw was the driver's work on the circuit's
     * busiest stretch. A program keeps its uniforms, so what it was given last still holds. */
    if (!p->vc_last) {
        p->vc_last = calloc(192, sizeof *p->vc_last); /* zeros, as a new program's uniforms are */
        p->vc_rows = p->vc >= 0 && glGetUniformLocation(p->prog, "u_vc[1]") == p->vc + 1 && glGetUniformLocation(p->prog, "u_vc[191]") == p->vc + 191 ? 1 : -1;
    }
    int lo = 0, hi = 191;
    while (lo <= hi && !memcmp(c[lo], p->vc_last[lo], 16)) lo++;
    while (hi >= lo && !memcmp(c[hi], p->vc_last[hi], 16)) hi--;
    if (lo <= hi) {
        if (p->vc_rows < 0) lo = 0, hi = 191;
        glUniform4fv(p->vc + lo, hi - lo + 1, &c[lo][0]);
        memcpy(p->vc_last[lo], c[lo], (size_t)(hi - lo + 1) * 16);
    }
    float sxy[2] = {(float)d->sx, (float)d->sy};
    glUniform2fv(p->sxy, 1, sxy);
    float fog[4] = {K(SET_FOG_ENABLE) ? 1.0f : 0.0f, (float)K(SET_FOG_MODE), f32(K(SET_FOG_PARAMS)), f32(K(SET_FOG_PARAMS + 4))};
    glUniform4fv(p->fog, 1, fog);
    uint64_t p4 = rt_now_100ns();
    gl_frag_state(d, s);
    uint64_t p5 = rt_now_100ns();
    if (mode != GL_TRIANGLES) { /* an Xbox pixel wide, at the render scale */
        float lw = (float)(K(0x380) & 0x1FF) / 8.0f; /* SET_LINE_WIDTH, 6.3 fixed point */
        if (lw < 1.0f) lw = 1.0f;
        glLineWidth(lw * (float)s->k), glPointSize(lw * (float)s->k);
    }
    glDrawElements(mode, k, GL_UNSIGNED_INT, NULL);
    uint64_t p6 = rt_now_100ns();
    prof_t[0] += p1 - p0, prof_t[1] += p2 - p1, prof_t[2] += p3 - p2, prof_t[3] += p4 - p3, prof_t[4] += p5 - p4, prof_t[5] += p6 - p5;
    prof_n++, prof_verts += (uint64_t)n;
    glBindVertexArray(gl_vao);
    s->dirty = s->cdirty = 1, s->seq = ++gl_seq;
    if (d->ztest && d->zwrite && s->ztex) s->zdirty = 1, s->zgpu = 0;
    gl_drawn(s, d->cx0, d->cy0, d->cx0 + d->cw, d->cy0 + d->ch);
    return 1;
}
