# Drawing on the host GPU

The software rasteriser (`runtime/raster.c`) draws everything Forza needs,
but on the CPU: a race runs at 2-3 frames a second, three quarters of the
device thread's time spent filling pixels even on twelve cores. This is
the plan for drawing on the PC's graphics card instead. `raster.c` stays
as the reference: every step can be checked against it pixel for pixel.

## API: OpenGL 4.3 core

- Nothing to install: `opengl32.dll` and the driver are on every Windows
  PC, and w64devkit ships the headers (`GL/glcorearb.h`, `GL/wglext.h`).
- GLSL is compiled by the driver at run time, which suits shaders
  generated from the game's own vertex programs and combiner settings.
- xemu draws the NV2A with OpenGL too, so its behaviour is a reference
  for the hardware's quirks. Its code is GPL and is not copied here.

Vulkan or Direct3D 12 can come later if driver overhead matters.

## Threads

The context belongs to the device thread (`nv2a.c`, `device_main`), which
already runs the push buffer: every Kelvin method reaches GL from that one
thread. The window thread (`display.c`) keeps showing what the CRTC scans
out of Xbox RAM until presenting moves to the GPU (step 5).

## Steps

1. **Context.** A hidden window, a 4.3 core context made current on the
   device thread, GL functions loaded through `wglGetProcAddress`
   (`runtime/gl.c`). `XBRT_GPU=gl` selects it; the default stays the
   software rasteriser until the GPU path is as good.
2. **Hybrid mode.** Each colour/zeta surface the game draws to gets a
   framebuffer of the same size (samples, for anti-aliased surfaces).
   Draws go to it; at the points where anything else could look at
   memory (flips, semaphore releases, notifies, surface changes, clears
   are done on the GPU too) the surface is read back into Xbox RAM. The
   rest of the runtime keeps working on RAM unchanged: display,
   screenshots, CPU-written textures, render targets read as textures.
3. **Shaders.**
   - Vertex programs: the 136-slot microcode translated to GLSL (MAC and
     ILU ops, swizzles, masks, A0 relative addressing, the 192
     constants as a uniform array), cached by a hash of the program.
   - Fixed function: one shader for the composite-matrix path the game
     uses (no lighting yet, as in `raster.c`).
   - Pixels: the register combiners generated as GLSL from the
     combiner methods (general stages and the final combiner), the four
     texture stages with their modes (2D, cube, pass-through, shadow
     compare), alpha test. Cached by a hash of that state.
   - Fixed-function state maps to GL state: blending, depth test and
     mask, colour mask, culling, clip rectangle as the scissor.
4. **Textures.** Uploaded once, re-uploaded when the hash of their bytes
   changes (the check `raster.c` already does), with the game's filter
   and address modes and mipmaps: this ends the blocky look as well.
5. **Fewer read-backs.** Track which surfaces the CPU actually reads
   (scan-out, the downsample's source as a texture can stay on the GPU)
   and keep the rest there; present the front buffer from the GPU.

Each step ends with the race rendered through it and compared with the
software rasteriser's screenshots.
