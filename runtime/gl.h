/* OpenGL for drawing the NV2A's work on the host GPU (docs/GPU.md).
 *
 * Every function is loaded at start-up into a pointer named p_<name>, and
 * <name> is #defined to it, so code reads like plain GL. Add a function by
 * adding a line to GL_FUNCTIONS. Only the device thread calls GL: the
 * context is current there.
 */
#ifndef RT_GL_H
#define RT_GL_H

#include <GL/glcorearb.h>

#define GL_FUNCTIONS(X)                                                                                                     \
    X(PFNGLGETSTRINGPROC, glGetString)                                                                                      \
    X(PFNGLGETINTEGERVPROC, glGetIntegerv)                                                                                  \
    X(PFNGLGETERRORPROC, glGetError)                                                                                        \
    X(PFNGLVIEWPORTPROC, glViewport)                                                                                        \
    X(PFNGLSCISSORPROC, glScissor)                                                                                          \
    X(PFNGLENABLEPROC, glEnable)                                                                                            \
    X(PFNGLDISABLEPROC, glDisable)                                                                                          \
    X(PFNGLCLEARCOLORPROC, glClearColor)                                                                                    \
    X(PFNGLCLEARDEPTHPROC, glClearDepth)                                                                                    \
    X(PFNGLCLEARSTENCILPROC, glClearStencil)                                                                                \
    X(PFNGLCLEARPROC, glClear)                                                                                              \
    X(PFNGLCOLORMASKPROC, glColorMask)                                                                                      \
    X(PFNGLDEPTHMASKPROC, glDepthMask)                                                                                      \
    X(PFNGLDEPTHFUNCPROC, glDepthFunc)                                                                                      \
    X(PFNGLBLENDFUNCSEPARATEPROC, glBlendFuncSeparate)                                                                      \
    X(PFNGLBLENDEQUATIONPROC, glBlendEquation)                                                                              \
    X(PFNGLBLENDCOLORPROC, glBlendColor)                                                                                    \
    X(PFNGLCULLFACEPROC, glCullFace)                                                                                        \
    X(PFNGLFRONTFACEPROC, glFrontFace)                                                                                      \
    X(PFNGLPIXELSTOREIPROC, glPixelStorei)                                                                                  \
    X(PFNGLREADPIXELSPROC, glReadPixels)                                                                                    \
    X(PFNGLFINISHPROC, glFinish)                                                                                            \
    X(PFNGLGENTEXTURESPROC, glGenTextures)                                                                                  \
    X(PFNGLDELETETEXTURESPROC, glDeleteTextures)                                                                            \
    X(PFNGLBINDTEXTUREPROC, glBindTexture)                                                                                  \
    X(PFNGLACTIVETEXTUREPROC, glActiveTexture)                                                                              \
    X(PFNGLTEXSTORAGE2DPROC, glTexStorage2D)                                                                                \
    X(PFNGLTEXSUBIMAGE2DPROC, glTexSubImage2D)                                                                              \
    X(PFNGLTEXPARAMETERIPROC, glTexParameteri)                                                                              \
    X(PFNGLGENFRAMEBUFFERSPROC, glGenFramebuffers)                                                                          \
    X(PFNGLDELETEFRAMEBUFFERSPROC, glDeleteFramebuffers)                                                                    \
    X(PFNGLBINDFRAMEBUFFERPROC, glBindFramebuffer)                                                                          \
    X(PFNGLFRAMEBUFFERTEXTURE2DPROC, glFramebufferTexture2D)                                                                \
    X(PFNGLCHECKFRAMEBUFFERSTATUSPROC, glCheckFramebufferStatus)                                                            \
    X(PFNGLCREATESHADERPROC, glCreateShader)                                                                                \
    X(PFNGLDELETESHADERPROC, glDeleteShader)                                                                                \
    X(PFNGLSHADERSOURCEPROC, glShaderSource)                                                                                \
    X(PFNGLCOMPILESHADERPROC, glCompileShader)                                                                              \
    X(PFNGLGETSHADERIVPROC, glGetShaderiv)                                                                                  \
    X(PFNGLGETSHADERINFOLOGPROC, glGetShaderInfoLog)                                                                        \
    X(PFNGLCREATEPROGRAMPROC, glCreateProgram)                                                                              \
    X(PFNGLATTACHSHADERPROC, glAttachShader)                                                                                \
    X(PFNGLLINKPROGRAMPROC, glLinkProgram)                                                                                  \
    X(PFNGLGETPROGRAMIVPROC, glGetProgramiv)                                                                                \
    X(PFNGLGETPROGRAMINFOLOGPROC, glGetProgramInfoLog)                                                                      \
    X(PFNGLUSEPROGRAMPROC, glUseProgram)                                                                                    \
    X(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation)                                                                    \
    X(PFNGLUNIFORM1IPROC, glUniform1i)                                                                                      \
    X(PFNGLUNIFORM4FVPROC, glUniform4fv)                                                                                    \
    X(PFNGLUNIFORM1UIPROC, glUniform1ui)                                                                                    \
    X(PFNGLUNIFORM1UIVPROC, glUniform1uiv)                                                                                  \
    X(PFNGLUNIFORM1IVPROC, glUniform1iv)                                                                                    \
    X(PFNGLUNIFORM1FPROC, glUniform1f)                                                                                      \
    X(PFNGLUNIFORM1FVPROC, glUniform1fv)                                                                                    \
    X(PFNGLUNIFORM2FVPROC, glUniform2fv)                                                                                    \
    X(PFNGLGENVERTEXARRAYSPROC, glGenVertexArrays)                                                                          \
    X(PFNGLBINDVERTEXARRAYPROC, glBindVertexArray)                                                                          \
    X(PFNGLGENBUFFERSPROC, glGenBuffers)                                                                                    \
    X(PFNGLBINDBUFFERPROC, glBindBuffer)                                                                                    \
    X(PFNGLBUFFERDATAPROC, glBufferData)                                                                                    \
    X(PFNGLVERTEXATTRIBPOINTERPROC, glVertexAttribPointer)                                                                  \
    X(PFNGLENABLEVERTEXATTRIBARRAYPROC, glEnableVertexAttribArray)                                                          \
    X(PFNGLDRAWARRAYSPROC, glDrawArrays)                                                                                    \
    X(PFNGLDEBUGMESSAGECALLBACKPROC, glDebugMessageCallback)

#define GL_DECLARE(type, name) extern type p_##name;
GL_FUNCTIONS(GL_DECLARE)
#undef GL_DECLARE
/* Each <name> to its pointer (C has no way to generate these from the list). */
#define glGetString p_glGetString
#define glGetIntegerv p_glGetIntegerv
#define glGetError p_glGetError
#define glViewport p_glViewport
#define glScissor p_glScissor
#define glEnable p_glEnable
#define glDisable p_glDisable
#define glClearColor p_glClearColor
#define glClearDepth p_glClearDepth
#define glClearStencil p_glClearStencil
#define glClear p_glClear
#define glColorMask p_glColorMask
#define glDepthMask p_glDepthMask
#define glDepthFunc p_glDepthFunc
#define glBlendFuncSeparate p_glBlendFuncSeparate
#define glBlendEquation p_glBlendEquation
#define glBlendColor p_glBlendColor
#define glCullFace p_glCullFace
#define glFrontFace p_glFrontFace
#define glPixelStorei p_glPixelStorei
#define glReadPixels p_glReadPixels
#define glFinish p_glFinish
#define glGenTextures p_glGenTextures
#define glDeleteTextures p_glDeleteTextures
#define glBindTexture p_glBindTexture
#define glActiveTexture p_glActiveTexture
#define glTexStorage2D p_glTexStorage2D
#define glTexSubImage2D p_glTexSubImage2D
#define glTexParameteri p_glTexParameteri
#define glGenFramebuffers p_glGenFramebuffers
#define glDeleteFramebuffers p_glDeleteFramebuffers
#define glBindFramebuffer p_glBindFramebuffer
#define glFramebufferTexture2D p_glFramebufferTexture2D
#define glCheckFramebufferStatus p_glCheckFramebufferStatus
#define glCreateShader p_glCreateShader
#define glDeleteShader p_glDeleteShader
#define glShaderSource p_glShaderSource
#define glCompileShader p_glCompileShader
#define glGetShaderiv p_glGetShaderiv
#define glGetShaderInfoLog p_glGetShaderInfoLog
#define glCreateProgram p_glCreateProgram
#define glAttachShader p_glAttachShader
#define glLinkProgram p_glLinkProgram
#define glGetProgramiv p_glGetProgramiv
#define glGetProgramInfoLog p_glGetProgramInfoLog
#define glUseProgram p_glUseProgram
#define glGetUniformLocation p_glGetUniformLocation
#define glUniform1i p_glUniform1i
#define glUniform4fv p_glUniform4fv
#define glUniform1ui p_glUniform1ui
#define glUniform1uiv p_glUniform1uiv
#define glUniform1iv p_glUniform1iv
#define glUniform1f p_glUniform1f
#define glUniform1fv p_glUniform1fv
#define glUniform2fv p_glUniform2fv
#define glGenVertexArrays p_glGenVertexArrays
#define glBindVertexArray p_glBindVertexArray
#define glGenBuffers p_glGenBuffers
#define glBindBuffer p_glBindBuffer
#define glBufferData p_glBufferData
#define glVertexAttribPointer p_glVertexAttribPointer
#define glEnableVertexAttribArray p_glEnableVertexAttribArray
#define glDrawArrays p_glDrawArrays
#define glDebugMessageCallback p_glDebugMessageCallback

extern int rt_gl_on; /* XBRT_GPU=gl and the context came up */

/* On the device thread: make the context and load the functions. Returns 0
 * (and says why) if the host has no OpenGL 4.3. */
int rt_gl_init(void);

#endif
