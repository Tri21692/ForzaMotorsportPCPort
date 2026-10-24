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
    X(PFNGLBLITFRAMEBUFFERPROC, glBlitFramebuffer)                                                                          \
    X(PFNGLSTENCILMASKPROC, glStencilMask)                                                                                  \
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
    X(PFNGLTEXPARAMETERFPROC, glTexParameterf)                                                                              \
    X(PFNGLTEXPARAMETERFVPROC, glTexParameterfv)                                                                            \
    X(PFNGLGENSAMPLERSPROC, glGenSamplers)                                                                                  \
    X(PFNGLBINDSAMPLERPROC, glBindSampler)                                                                                  \
    X(PFNGLSAMPLERPARAMETERIPROC, glSamplerParameteri)                                                                      \
    X(PFNGLSAMPLERPARAMETERFPROC, glSamplerParameterf)                                                                      \
    X(PFNGLSAMPLERPARAMETERFVPROC, glSamplerParameterfv)                                                                            \
    X(PFNGLGENFRAMEBUFFERSPROC, glGenFramebuffers)                                                                          \
    X(PFNGLDELETEFRAMEBUFFERSPROC, glDeleteFramebuffers)                                                                    \
    X(PFNGLBINDFRAMEBUFFERPROC, glBindFramebuffer)                                                                          \
    X(PFNGLFRAMEBUFFERTEXTURE2DPROC, glFramebufferTexture2D)                                                                \
    X(PFNGLCOPYIMAGESUBDATAPROC, glCopyImageSubData)                                                                        \
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
    X(PFNGLPROGRAMUNIFORM1IVPROC, glProgramUniform1iv)                                                                      \
    X(PFNGLPROGRAMUNIFORM1UIVPROC, glProgramUniform1uiv)                                                                    \
    X(PFNGLPROGRAMUNIFORM1UIPROC, glProgramUniform1ui)                                                                      \
    X(PFNGLPROGRAMUNIFORM1FVPROC, glProgramUniform1fv)                                                                      \
    X(PFNGLPROGRAMUNIFORM3FVPROC, glProgramUniform3fv)                                                                      \
    X(PFNGLVALIDATEPROGRAMPIPELINEPROC, glValidateProgramPipeline)                                                          \
    X(PFNGLGETPROGRAMPIPELINEINFOLOGPROC, glGetProgramPipelineInfoLog)                                                      \
    X(PFNGLCREATESHADERPROGRAMVPROC, glCreateShaderProgramv)                                                                \
    X(PFNGLGENPROGRAMPIPELINESPROC, glGenProgramPipelines)                                                                  \
    X(PFNGLBINDPROGRAMPIPELINEPROC, glBindProgramPipeline)                                                                  \
    X(PFNGLUSEPROGRAMSTAGESPROC, glUseProgramStages)                                                                        \
    X(PFNGLACTIVESHADERPROGRAMPROC, glActiveShaderProgram)                                                                  \
    X(PFNGLPROGRAMUNIFORM1IPROC, glProgramUniform1i)                                                                        \
    X(PFNGLPROGRAMUNIFORM1FPROC, glProgramUniform1f)                                                                        \
    X(PFNGLPROGRAMUNIFORM2FVPROC, glProgramUniform2fv)                                                                      \
    X(PFNGLPROGRAMUNIFORM4FVPROC, glProgramUniform4fv)                                                                      \
    X(PFNGLDELETEPROGRAMPROC, glDeleteProgram)                                                                              \
    X(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation)                                                                    \
    X(PFNGLUNIFORM1IPROC, glUniform1i)                                                                                      \
    X(PFNGLUNIFORM4FVPROC, glUniform4fv)                                                                                    \
    X(PFNGLUNIFORM1UIPROC, glUniform1ui)                                                                                    \
    X(PFNGLUNIFORM1UIVPROC, glUniform1uiv)                                                                                  \
    X(PFNGLUNIFORM1IVPROC, glUniform1iv)                                                                                    \
    X(PFNGLUNIFORM1FPROC, glUniform1f)                                                                                      \
    X(PFNGLUNIFORM1FVPROC, glUniform1fv)                                                                                    \
    X(PFNGLUNIFORM2FVPROC, glUniform2fv)                                                                                    \
    X(PFNGLUNIFORM3FVPROC, glUniform3fv)                                                                                    \
    X(PFNGLGENVERTEXARRAYSPROC, glGenVertexArrays)                                                                          \
    X(PFNGLBINDVERTEXARRAYPROC, glBindVertexArray)                                                                          \
    X(PFNGLGENBUFFERSPROC, glGenBuffers)                                                                                    \
    X(PFNGLDELETEBUFFERSPROC, glDeleteBuffers)                                                                                    \
    X(PFNGLBINDBUFFERPROC, glBindBuffer)                                                                                    \
    X(PFNGLBUFFERDATAPROC, glBufferData)                                                                                    \
    X(PFNGLVERTEXATTRIBPOINTERPROC, glVertexAttribPointer)                                                                  \
    X(PFNGLENABLEVERTEXATTRIBARRAYPROC, glEnableVertexAttribArray)                                                          \
    X(PFNGLDISABLEVERTEXATTRIBARRAYPROC, glDisableVertexAttribArray)                                                          \
    X(PFNGLDRAWARRAYSPROC, glDrawArrays)                                                                                    \
    X(PFNGLFENCESYNCPROC, glFenceSync)                                                                                      \
    X(PFNGLCLIENTWAITSYNCPROC, glClientWaitSync)                                                                            \
    X(PFNGLDELETESYNCPROC, glDeleteSync)                                                                                    \
    X(PFNGLMAPBUFFERRANGEPROC, glMapBufferRange)                                                                            \
    X(PFNGLUNMAPBUFFERPROC, glUnmapBuffer)                                                                                  \
    X(PFNGLDRAWELEMENTSPROC, glDrawElements)                                                                                \
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
#define glBlitFramebuffer p_glBlitFramebuffer
#define glStencilMask p_glStencilMask
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
#define glTexParameterf p_glTexParameterf
#define glTexParameterfv p_glTexParameterfv
#define glGenSamplers p_glGenSamplers
#define glBindSampler p_glBindSampler
#define glSamplerParameteri p_glSamplerParameteri
#define glSamplerParameterf p_glSamplerParameterf
#define glSamplerParameterfv p_glSamplerParameterfv
#define glGenFramebuffers p_glGenFramebuffers
#define glDeleteFramebuffers p_glDeleteFramebuffers
#define glBindFramebuffer p_glBindFramebuffer
#define glFramebufferTexture2D p_glFramebufferTexture2D
#define glCopyImageSubData p_glCopyImageSubData
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
#define glProgramUniform1iv p_glProgramUniform1iv
#define glProgramUniform1uiv p_glProgramUniform1uiv
#define glProgramUniform1ui p_glProgramUniform1ui
#define glProgramUniform1fv p_glProgramUniform1fv
#define glProgramUniform3fv p_glProgramUniform3fv
#define glValidateProgramPipeline p_glValidateProgramPipeline
#define glGetProgramPipelineInfoLog p_glGetProgramPipelineInfoLog
#define glCreateShaderProgramv p_glCreateShaderProgramv
#define glGenProgramPipelines p_glGenProgramPipelines
#define glBindProgramPipeline p_glBindProgramPipeline
#define glUseProgramStages p_glUseProgramStages
#define glActiveShaderProgram p_glActiveShaderProgram
#define glProgramUniform1i p_glProgramUniform1i
#define glProgramUniform1f p_glProgramUniform1f
#define glProgramUniform2fv p_glProgramUniform2fv
#define glProgramUniform4fv p_glProgramUniform4fv
#define glDeleteProgram p_glDeleteProgram
#define glGetUniformLocation p_glGetUniformLocation
#define glUniform1i p_glUniform1i
#define glUniform4fv p_glUniform4fv
#define glUniform1ui p_glUniform1ui
#define glUniform1uiv p_glUniform1uiv
#define glUniform1iv p_glUniform1iv
#define glUniform1f p_glUniform1f
#define glUniform1fv p_glUniform1fv
#define glUniform2fv p_glUniform2fv
#define glUniform3fv p_glUniform3fv
#define glGenVertexArrays p_glGenVertexArrays
#define glBindVertexArray p_glBindVertexArray
#define glGenBuffers p_glGenBuffers
#define glDeleteBuffers p_glDeleteBuffers
#define glBindBuffer p_glBindBuffer
#define glBufferData p_glBufferData
#define glVertexAttribPointer p_glVertexAttribPointer
#define glEnableVertexAttribArray p_glEnableVertexAttribArray
#define glDisableVertexAttribArray p_glDisableVertexAttribArray
#define glDrawArrays p_glDrawArrays
#define glFenceSync p_glFenceSync
#define glClientWaitSync p_glClientWaitSync
#define glDeleteSync p_glDeleteSync
#define glMapBufferRange p_glMapBufferRange
#define glUnmapBuffer p_glUnmapBuffer
#define glDrawElements p_glDrawElements
#define glDebugMessageCallback p_glDebugMessageCallback

extern int rt_gl_on; /* XBRT_GPU=gl and the context came up */
extern PFNGLBUFFERSTORAGEPROC p_glBufferStorage; /* GL 4.4 / ARB_buffer_storage: NULL without it */
#define glBufferStorage p_glBufferStorage

/* On the device thread: make the context and load the functions. Returns 0
 * (and says why) if the host has no OpenGL 4.3. */
int rt_gl_init(void);
int rt_gl_window_begin(int *W, int *H); /* draw into the game's window from here; its size */
void rt_gl_window_swap(void);           /* and show what was drawn */

#endif
