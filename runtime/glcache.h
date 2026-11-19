/* A shadow of the GL state the draws set over and over (the user's, 7 Nov: frame drops with the rivals in view): every
 * draw set its four texture stages (a 2D and a cube texture, a sampler each, the active unit switched for each) and
 * the blend, depth, colour mask and culling state again, some 40 driver calls a draw at ~1,700 draws a frame, most
 * changing nothing; the GL driver was the device thread's biggest cost (25%), and seven cars in view added ~600
 * draws. Each call here goes to the driver only when it changes what this context holds.
 *
 * Included by raster.c before the GL files it includes (gltexhd.c, glfill.c, glover.c, glfs.c, glvsh.c), so every
 * call of these in that unit goes through the shadow and it never goes stale; gl.c's self-test runs before any draw
 * and leaves nothing bound. A deleted texture's name, which GL may hand out again, is forgotten where it was bound
 * (deleting unbinds it). XBRT_GL_STATECACHE=0: every call made, as before. */
#ifndef GLCACHE_H
#define GLCACHE_H

#define GLC_UNITS 32
static int glc_on = -1;
static GLenum glc_unit;          /* GL_TEXTURE0 + n; 0: not known */
static GLuint glc_tex[GLC_UNITS][2]; /* [unit][0 2D, 1 cube]; ~0: not known */
static GLuint glc_samp[GLC_UNITS];
static int glc_cap[5];           /* blend, depth test, cull face, stencil test, scissor test: -1 not known */
static GLenum glc_bf[4], glc_beq, glc_dfunc, glc_cull, glc_front;
static GLfloat glc_bc[4];
static int glc_bf_ok, glc_beq_ok, glc_bc_ok, glc_dfunc_ok, glc_dmask = -1, glc_cmask = -1, glc_cull_ok, glc_front_ok;

static int glc_ready(void) {
    if (glc_on < 0) {
        glc_on = !getenv("XBRT_GL_STATECACHE") || atoi(getenv("XBRT_GL_STATECACHE"));
        memset(glc_tex, 0xFF, sizeof glc_tex), memset(glc_samp, 0xFF, sizeof glc_samp);
        for (int i = 0; i < 5; i++) glc_cap[i] = -1;
    }
    return glc_on;
}
static void glc_active(GLenum u) {
    if (glc_ready() && glc_unit == u) return;
    p_glActiveTexture(u), glc_unit = u;
}
static void glc_bind_tex(GLenum target, GLuint id) {
    int k = target == GL_TEXTURE_2D ? 0 : target == GL_TEXTURE_CUBE_MAP ? 1 : -1;
    unsigned u = glc_unit - GL_TEXTURE0;
    if (glc_ready() && k >= 0 && glc_unit && u < GLC_UNITS) {
        if (glc_tex[u][k] == id) return;
        glc_tex[u][k] = id;
    }
    p_glBindTexture(target, id);
}
static void glc_delete_tex(GLsizei n, const GLuint *ids) {
    for (GLsizei i = 0; i < n; i++)
        for (int u = 0; u < GLC_UNITS; u++)
            for (int k = 0; k < 2; k++)
                if (glc_tex[u][k] == ids[i]) glc_tex[u][k] = 0; /* (unbound by the delete: 0 is bound there now) */
    p_glDeleteTextures(n, ids);
}
static void glc_bind_sampler(GLuint unit, GLuint s) {
    if (glc_ready() && unit < GLC_UNITS) {
        if (glc_samp[unit] == s) return;
        glc_samp[unit] = s;
    }
    p_glBindSampler(unit, s);
}
static int glc_cap_of(GLenum cap) {
    return cap == GL_BLEND ? 0 : cap == GL_DEPTH_TEST ? 1 : cap == GL_CULL_FACE ? 2 : cap == GL_STENCIL_TEST ? 3 : cap == GL_SCISSOR_TEST ? 4 : -1;
}
static void glc_enable(GLenum cap) {
    int i = glc_cap_of(cap);
    if (glc_ready() && i >= 0) {
        if (glc_cap[i] == 1) return;
        glc_cap[i] = 1;
    }
    p_glEnable(cap);
}
static void glc_disable(GLenum cap) {
    int i = glc_cap_of(cap);
    if (glc_ready() && i >= 0) {
        if (glc_cap[i] == 0) return;
        glc_cap[i] = 0;
    }
    p_glDisable(cap);
}
static void glc_blend_func_sep(GLenum a, GLenum b, GLenum c, GLenum d) {
    if (glc_ready() && glc_bf_ok && glc_bf[0] == a && glc_bf[1] == b && glc_bf[2] == c && glc_bf[3] == d) return;
    glc_bf[0] = a, glc_bf[1] = b, glc_bf[2] = c, glc_bf[3] = d, glc_bf_ok = 1;
    p_glBlendFuncSeparate(a, b, c, d);
}
static void glc_blend_eq(GLenum e) {
    if (glc_ready() && glc_beq_ok && glc_beq == e) return;
    glc_beq = e, glc_beq_ok = 1;
    p_glBlendEquation(e);
}
static void glc_blend_color(GLfloat r, GLfloat g, GLfloat b, GLfloat a) {
    if (glc_ready() && glc_bc_ok && glc_bc[0] == r && glc_bc[1] == g && glc_bc[2] == b && glc_bc[3] == a) return;
    glc_bc[0] = r, glc_bc[1] = g, glc_bc[2] = b, glc_bc[3] = a, glc_bc_ok = 1;
    p_glBlendColor(r, g, b, a);
}
static void glc_depth_func(GLenum f) {
    if (glc_ready() && glc_dfunc_ok && glc_dfunc == f) return;
    glc_dfunc = f, glc_dfunc_ok = 1;
    p_glDepthFunc(f);
}
static void glc_depth_mask(GLboolean m) {
    if (glc_ready() && glc_dmask == (int)m) return;
    glc_dmask = m;
    p_glDepthMask(m);
}
static void glc_color_mask(GLboolean r, GLboolean g, GLboolean b, GLboolean a) {
    int m = (r ? 1 : 0) | (g ? 2 : 0) | (b ? 4 : 0) | (a ? 8 : 0);
    if (glc_ready() && glc_cmask == m) return;
    glc_cmask = m;
    p_glColorMask(r, g, b, a);
}
static void glc_cull_face(GLenum f) {
    if (glc_ready() && glc_cull_ok && glc_cull == f) return;
    glc_cull = f, glc_cull_ok = 1;
    p_glCullFace(f);
}
static void glc_front_face(GLenum f) {
    if (glc_ready() && glc_front_ok && glc_front == f) return;
    glc_front = f, glc_front_ok = 1;
    p_glFrontFace(f);
}

#undef glActiveTexture
#undef glBindTexture
#undef glDeleteTextures
#undef glBindSampler
#undef glEnable
#undef glDisable
#undef glBlendFuncSeparate
#undef glBlendEquation
#undef glBlendColor
#undef glDepthFunc
#undef glDepthMask
#undef glColorMask
#undef glCullFace
#undef glFrontFace
#define glActiveTexture glc_active
#define glBindTexture glc_bind_tex
#define glDeleteTextures glc_delete_tex
#define glBindSampler glc_bind_sampler
#define glEnable glc_enable
#define glDisable glc_disable
#define glBlendFuncSeparate glc_blend_func_sep
#define glBlendEquation glc_blend_eq
#define glBlendColor glc_blend_color
#define glDepthFunc glc_depth_func
#define glDepthMask glc_depth_mask
#define glColorMask glc_color_mask
#define glCullFace glc_cull_face
#define glFrontFace glc_front_face

#endif
