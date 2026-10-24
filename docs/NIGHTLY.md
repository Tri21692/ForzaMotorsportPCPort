# Nightly runs

Unattended work sessions run on the maintainer's Windows PC between 11 pm
and 8 am Eastern. Each one reads this file first and updates it before it
stops. It is the handoff between sessions: what works, the current lead,
and how to reproduce it.

## Setup on this machine

| what | where |
|---|---|
| Go 1.27 | `C:\Program Files\Go\bin` |
| gcc, make, gdb (w64devkit) | `C:\Users\maste\Downloads\w64devkit\bin` |
| XbSymbolDatabase | `C:\Users\maste\XbSymbolDatabase` |
| extracted disc (`default.xbe` + `media`) | `C:\Users\maste\Downloads\extract-xiso-win32-release\Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso` |
| working folder for runs (git-ignored) | `run/`, with the hard disk in `run/hdd` |

In Git Bash:

```sh
export PATH="/c/Program Files/Go/bin:/c/Users/maste/Downloads/w64devkit/bin:$PATH"
X="/c/Users/maste/Downloads/extract-xiso-win32-release/Forza Motorsport (World) (En,Ja,Fr,De,Es,It,Zh,Ko).xiso/default.xbe"
rm -f out/*.c                                   # xbrecomp does not delete files it no longer writes
go run ./cmd/xbrecomp -xbsdb /c/Users/maste/XbSymbolDatabase -o out/ "$X"
make -C runtime GEN=../out -j20
cd run && XBRT_LOG=1 XBRT_HDD=hdd timeout 120 ../runtime/forza.exe "$X" > log.txt 2>&1
```

Tests: `FORZA_XBE="$X" XBSDB=/c/Users/maste/XbSymbolDatabase go test ./...`

## Debugging techniques that worked

- `XBRT_LOG=1` (kernel calls) and `2` (also file read/write contents,
  push buffer); the GPU logs a counts line every 300 vblanks.
- Sample where the game is: run it in the background, then
  `gdb -q -batch -p <pid> -ex "thread apply all bt 24"` a few times. Host
  frames named `f_XXXXXXXX` are guest functions at that address.
- Under gdb from the start, first `handle SIGSEGV nostop noprint pass`:
  the runtime commits guest memory on first touch through access
  violations. Break on runtime functions (`rt_open`, `k_file_*`), not on
  the generated weak symbols, which did not trigger.
- Live guest registers from gdb: `frame function thread_main`, then
  `p/x *(XbCtx*)arg` (also `p/x *(unsigned*)(xb_mem + 0xADDR)` for guest
  memory and device registers).
- `XBRT_TRACE_OPEN=<substring>` prints a guest backtrace when a matching
  file is opened; `XBRT_DEBUG_BADHANDLE=1` does so when an invalid handle
  reaches ObReferenceObjectByHandle.
- `go run ./cmd/xbedis -xbsdb ... "$X" 0xADDR` disassembles one function;
  `go run ./cmd/xbemap -xbsdb ... -o forza.map "$X"` writes the map.
- The installer manifest is the `BKGDINST` section (37 files, 4 MB zlib
  chunks with SHA-1s).
- Profiling: `tools/sample.sh 40 samples.txt` while the game runs (gdb,
  every thread's stack), then `python tools/samples.py samples.txt` for
  the device thread (innermost frames, by line). For guest threads, map
  the `f_XXXXXXXX` frames to names with `run/forza.map` (xbemap):
  tonight that found DSOUND resetting its DSPs. A thread "waiting" inside
  the GL driver (glReadPixels) is waiting for the GPU, not idle.
- `XBRT_STATS=1` lines: texture decodes and hashing, the device thread's
  time by phase, and the time spent waiting for the driver after trapped
  notifies.
- `XBRT_GPU_DUMP=<file>:<first flip>:<flips>` dumps every method; with
  awk over methods 0210 (colour offset), 1d94 (clear), 17fc (draws),
  0100 with a parameter (notifies), 012c/0130 (flips) a frame's passes
  read like a list (see the Log for what Forza's frame looks like).
- Reading guest memory from gdb: `p/x *(unsigned*)(xb_mem + 0xADDR)`
  works for device memory too (`xb_mem + 0xFE85A000` is the EP DSP's
  P memory).
- The Makefile now rebuilds raster.o when glfill.c or glvsh.c change
  (they are #included); before tonight it did not, and edits to glfill.c
  alone were silently not built.
- Editing through the Bash tool: backslash escapes inside a heredoc
  (`\n` in a C string) arrive as real newlines. Write edit scripts to
  the scratch folder with the Write tool and run them, or use Edit.

## Current lead (2026-10-19, nightly)

**Races run at about 15-20 fps with `XBRT_GPU=gl`**, with the game's mipmaps
and filters (no more blocky or swimming textures), and without the
black top-left quarter / grey flyby frames. `tools/input/race.txt` gets
to lap 1, race clock ~1:08, at 400 s (at the start of the night it read
~0:21 at 360 s).

    XBRT_GPU=gl XBRT_STATS=1 XBRT_INPUT_SCRIPT=../tools/input/race.txt \
      XBRT_WINDOW=0 XBRT_SCREENSHOT=shots XBRT_SCREENSHOT_EVERY=20 \
      XBRT_HDD=hdd timeout 420 ../runtime/forza.exe <default.xbe>

Benchmark: the stats line's flip count at 415 s of that run (~8500 at
the end of the night; it was ~3050 at the start). Runs vary by ±7%, so
compare over two runs before believing a small change.

How the GPU path works now (docs/GPU.md steps 2-5, `runtime/glfill.c`,
`runtime/glvsh.c`):
- Vertex programs run on the GPU (GLSL generated from the decoded
  program, one GL program per vertex program); `XBRT_GPU_VSH=0` puts
  them back on the CPU for comparison. Fixed-function draws and programs
  that write constants stay on the CPU.
- Each surface combination (colour/depth, height) is a framebuffer.
  Framebuffers over the same bytes exchange pixels on the GPU
  (`gl_take_newer`, `glCopyImageSubData`) and are read back oldest
  first (`seq`), so RAM ends with the newest drawing.
- A linear colour texture over a framebuffer is sampled from the
  framebuffer's texture (`gl_rt_texture`); everything else is decoded
  from RAM (with its mipmaps) after the framebuffers that drew into it
  are read back (`gl_sync_range`).
- Nothing is read back at flips. At every trapped notify
  (`trap_method`) the colour of the buffers the CRTC has shown goes into
  pixel buffer objects; it reaches RAM at the next vertical blank (before
  D3D's handler can flip to it) or when anything else looks at RAM
  (`gl_complete`). D3D's notify after a frame's last draw lets its
  vertical blank handler show the frame long before
  FLIP_INCREMENT_WRITE. Depth is read back only when something reads it.
- At each flip the device thread waits for the GPU to finish the frame
  before last (`gl_flip`, a GL fence). Without some wait on the GPU the
  front end's thousands of frames a second filled the Intel driver's
  queue until it blocked for good (the device thread stuck in
  NtGdiDdDDIWaitForSynchronizationObjectFromCpu, the process unkillable
  for a minute): that, not the game reading the front buffer, is what
  the "boot spin" experiments below ran into.

What limits the race now (`tools/sample.sh` + `tools/samples.py`):
- The device thread's "draw state" time went up with the asynchronous
  read-backs (148 s of 334 s over the run): textures over framebuffers
  that cannot be sampled on the GPU are read back synchronously in
  texture(), most likely the shadow maps (depth textures, decoded from
  RAM). Sampling depth framebuffers on the GPU (`gl_rt_texture` for
  depth, comparing in the shader) is the next speed step; profile first.
- With every read-back skipped (wrong pictures, as an experiment) the
  race ran at ~30 fps, so read-backs still cost about a third.
- **Tried at the end, reverted:** sampling the shadow map from its
  framebuffer's depth texture (texture kind 4 in the shader, normalised
  depth times dmax; the only match was stage 1, the 768x768 map at
  02ad1000 that is colour and depth at once, shadow compare GREATER),
  together with keeping textures off the draw's own depth range. 11583
  flips (from 8680) and ~28 fps in the race, but the scene was wrong:
  the world upside down in the top half, the bottom half black, the car
  and HUD fine. Without the depth-range exclusion it looks the same
  (11797 flips), so it is the shadow-map sampling itself. Suspects: the
  map's colour and depth share an address (02ad1000), so something else
  may read that memory as colour; or what the GL depth texture holds
  differs from what the readback path gives (depth from the
  anti-aliased 2x2 grid, the D24S8 layout). Compare the two paths'
  texels for one frame (read the GL depth texture back and diff it with
  texture()'s decode) before trying again.
- **2026-10-19 (interactive): GPU shadow maps on by default; exact
  framebuffer heights. Race start ~20 -> ~25-28 fps.**
  - Profile (gdb samples, race): half the device thread waited in
    synchronous `glReadPixels` for textures over GPU-drawn bytes, almost
    all of it two textures once a frame: the track's 512x512 shadow map
    (format 0x2E; 02a64800 or 029d5800, it moves), and a 64x64 Y8 cube
    map at 01706000.
  - The cube map was a false overlap: framebuffer heights were rounded up
    to 16, so a 160x120 one at 016f3000 "covered" the cube's first 4 KB
    (and its read-backs wrote 8 junk rows over it). Heights are now the
    clip's.
  - Shadow maps (format 0x2E) are sampled on the GPU from the framebuffer
    whose depth they are (shader kind 4: GL's 0..1 depth times 0xFFFFFF,
    rounded, then the same compare as kind 3), and are never read back:
    they are marked clean with the hash of what RAM holds
    (`gl_depth_stays`). Nothing on the CPU reads them. What broke the
    earlier tries (and the nightly's) was the opposite: left dirty, the
    768x768 map at 02ad1000 was read back later (`gl_sync`) over bytes the
    CPU uses by then; the car flew off upside down at 170+ mph, or sat in
    the ground under yellow light shafts. Reading its depth back
    asynchronously, holding GET and landing it at semaphores was tried:
    correct but no faster. `XBRT_GL_RT_DEPTH=0` goes back to RAM.
  - A linear colour texture over a framebuffer is no longer sampled from
    it when depth drawn after it covers the bytes (Forza reads the main
    depth buffer's memory, 01e98000, as a 720x480 A8R8G8B8 texture).
  - Measured as fps in fixed windows of the race (`tools/fps_windows.py`:
    flips between the 5 s stats lines), since totals depend on where the
    car ends up: 170-230 s, baseline 19.9, exact heights 23.6, both
    25.3-27.6; later windows 25-32 depending on the scene (draws per
    frame range 600-1250).
  - Then (profile again): the waits were `gl_complete` landing the shown
    buffers' read-backs before every texture and every surface's hash
    check. It now lands only those over the bytes in question and what
    was issued before them (`gl_complete_range`): 25.3 -> 28.8 fps at the
    start, 23.7 -> 26.6 in the forest section.
  - **The xbe in Downloads is the user's 60 fps mod.** The disc image
    (`...xiso.iso`) has the retail one; they differ in one dword of .data
    at 00554944, the frame interval in vertical blanks: 2 (retail, 30 fps)
    or 1 (60 fps). `XBRT_FPS=30` / `XBRT_FPS=60` sets it at load (only
    where the neighbouring bytes are Forza's); without it, the xbe's own
    value is used. The game steps its world once per frame, so below the
    target it runs in slow motion: at 60 the race clock ran ~9 s per 20 s
    at ~28 fps, at 30 it runs ~88-93% of real time. Judge speed by the
    race clock against wall time, not by fps alone.
  - Vertical blanks were ~45 Hz in a race, not 59.94: the device loop
    raises them between push-buffer passes, and passes ran long. A pass
    now stops when one is due (every 128 words it checks): 58.3 Hz. At
    `XBRT_FPS=30` the race start reaches the cap (30.2 fps).
  - Seen at `XBRT_FPS=30`, not looked into yet: one screenshot per run
    near the start of lap 2 is grey and untextured (sky and ground flat
    grey, the car's shadow only).
- **2026-10-19 afternoon (interactive): the NVIDIA GPU; car reflections
  on the GPU.**
  - The PC has an RTX 5070 Laptop GPU besides the Intel one, and OpenGL
    ran on the Intel. `forza.exe` now exports `NvOptimusEnablement` (and
    AMD's equivalent), so the drivers give it the fast GPU (Windows'
    per-app graphics setting still overrides). Race at 60-88 fps where
    Intel gave 27-29; with the 60 fps mod the race clock keeps real time.
  - `XBRT_GL_SYNC_LOG=1` (kept): every 30 s, which texture made which
    framebuffer wait for a read-back, with counts and time.
  - Car reflections: a 256x256 texture and a 128x128 cube map, format
    0x06 (swizzled A8R8G8B8), at the same bytes as pitch surfaces Forza
    draws (with the swizzled size fields set). Read back and decoded as
    swizzled they came out scrambled (the speckled car paint), and the
    256x256 one was a wait for the GPU every frame (96 s of a race).
    Now sampled from the framebuffer, as xemu does (`gl_rt_swizzled`):
    27 -> 34 fps on Intel. Cube maps copy their six faces into a GL cube
    texture; that took Intel to 13 fps, so it is off unless
    `XBRT_GL_RT_CUBE=1` (not yet measured on NVIDIA). Real swizzled
    surfaces (type 2) now swizzle on read-back and upload, and clear on
    the GPU (the RAM clear skipped them).
  - `GL_DEPTH_CLAMP`: the NV2A clamps depth; without it NVIDIA clipped
    the sky (on the far plane) and left black patches above the horizon.
  - Framebuffers over the same bytes now copy each other only the
    rectangle they drew (bloom quarters drew 320 of 640 columns), and a
    framebuffer takes from later ones even when those were read back.
  - **Fixed: black patches and grey frames on NVIDIA.** Framebuffers over
    the same bytes copied each other's depth too (`gl_copy`). Forza's shown
    buffers (640x480) share the scene's depth memory (01e98000, 1280 wide),
    so the scene's depth landed in theirs and the passes drawn there
    failed their depth test: black patches, and frames where only the
    car-shadow image Forza draws in the back buffer showed (the grey
    frames). Intel's driver evidently never did the depth copy and looked
    right. Depth is no longer copied between framebuffers. Ruled out on the
    way: shadow maps, vertex programs, the swizzled path, feedback loops,
    GPU timing (`glFinish`), the bloom quarters, sub-rectangle clamping.
    Race: 68-94 fps, no patches, no grey frames.
  - Cube-map reflections on the GPU are now the default (NVIDIA: 71-74 fps
    in scenes of ~970 draws a frame, no waits left for them);
    `XBRT_GL_RT_CUBE=0` turns them off (for Intel, which fell to 13 fps).
    `XBRT_GL_RT_SHOWN` is gone. A grey frame still turns up now and then
    (1 of 10 screenshots in that run): the car-shadow image on screen.
  - **Frame pacing: FLIP_STALL.** It was ignored, so the GPU ran ahead of
    the display, and since Forza steps its world once a frame the race ran
    1.5x real time at ~90 fps. Now FLIP_STALL parks the push buffer while
    FLIP_READ == FLIP_WRITE, until D3D's vertical-blank handler writes
    NV_PGRAPH_INCREMENT (bit 1 moves FLIP_READ on), as xemu does. Race at
    58-59 fps, race clock 0.98x real time (60 fps mod). XBRT_NO_FLIP_STALL=1
    goes back to running free (benchmarks).
- **2026-10-19 evening (interactive): first sound.** `runtime/apu_vp.c`:
  the APU's voice processor, written from xemu's vp.c as the hardware
  reference. DSOUND's PIO methods (0xFE820000) now build voices in the
  voice structures at NV_PAPU_VPVADDR and link them into the 2D/3D/MP
  lists; every 32-sample frame the lists are walked: PCM (8/16/24/32-bit)
  and Xbox ADPCM, buffers (SGE) and streams (SSL segments, done
  notifications), envelopes, pitch (linear interpolation), the DLS2
  low-pass filter, per-bin volumes, multipass sub-mixes, idle voices handed
  back by front-end trap (SE2FE_IDLE_VOICE, IRQ 5). No GP DSP: speaker bins
  0-5 are mixed to stereo; reverb sends, parametric EQ and HRTF are not
  done. Output through waveOut (48 kHz), whose clock paces the frames;
  XGSCNT counts frames made. `XBRT_AUDIO=0` silent, `XBRT_VOLUME`,
  `XBRT_AUDIO_DUMP=<file>` (raw s16le 48 kHz stereo; mux with a recording
  using the logged start time). KeSynchronizeExecution implemented (DSOUND
  calls it). Without the low-pass filter Forza's wind/road noise voice
  (looped 16-bit PCM noise) was a full-band hiss over the whole race.
- **2026-10-19 evening: picture polish (PC enhancements, on by default).**
  - 16x anisotropic + trilinear filtering on mipmapped textures
    (`XBRT_GL_ANISO=1` off): road and walls sharp at grazing angles.
  - Render scale `XBRT_GL_SCALE=<1..4>`, default 2: every non-swizzled
    framebuffer is k times its size on the GPU; read-backs blit (LINEAR for
    colour, NEAREST for depth) into a 1x proxy framebuffer first, uploads
    go to the proxy and are blitted up; copies between framebuffers,
    scissors, viewport and the reflection cube map scale with k. The shown
    picture still reaches RAM at 640x480, so this is supersampling: clean
    edges, and the speckle on car paint (aliasing in the reflections) is
    mostly gone. No frame-rate cost on the RTX 5070 at the 60 fps cap.
  - **Volume textures.** Forza's car textures (body, lights atlas: formats
    with dimensionality 3, two slices; e.g. 19910f3a, 26610f3a, 28890f3a)
    were decoded as 2D. DXT volumes store each 4x4 block's slices together
    (up to four), so the two slices came out interleaved: striped
    taillights, a blocky grid over the paint (what looked like speckled
    reflections). Slice 0 is now decoded (block stride x slices; Morton
    order over x, y, z for uncompressed ones) and level sizes count the
    slices. Sampling the second slice (damage?) as a real 3D texture is
    not done.
  - The window, screenshots and recordings show the picture at the drawn
    resolution (1280x960 at 2x): the shown buffer is read from its
    framebuffer at each vertical blank (pixel buffer object, one blank
    late), while the GPU keeps drawing it; RAM otherwise and for movies.
  - Still open: the cars' lower bodies are very dark (no reference yet to
    say whether that is right), taillight lenses look striped; presenting
    the picture at the higher resolution (window and recordings) needs the
    display to come from the GPU instead of RAM.
- **2026-10-19 night: the world's lighting flickers, only at 60 fps.**
  Most objects but the cars switch between shadowed and lit from one frame
  to the next. Measured with a per-pixel flicker map of headless recordings
  (pixels that jump by >18 and straight back, duplicate frames dropped):
  ~10,800 flickering pixels with the 60 fps patch, ~330 (noise) at
  `XBRT_FPS=30`; forcing every shadow test to pass also removed it. The
  shadow map itself is steady (1 clear, 64 draws, ~60 samples every frame,
  all on the GPU), so the patch evidently leaves part of the shadow/light
  setup on the original 30 Hz rhythm: every other frame pairs a new map
  with old matrices. Fixing that means finding and patching that game code.
  **Found and fixed (2026-10-20):** a frame draws the shadow receivers
  first and the shadow map last. The map's draws always carry light
  matrix L1 in c92-c95 (scale in c90.xyz); the receivers carry L1 on even
  frames and the next one, L2, on odd frames (the camera itself, c0-c3,
  only changes every other frame: the game still runs its camera at 30 Hz).
  At 30 fps only even frames were shown. glvsh.c now remembers each shadow
  map's c90.xyz/c92-c95 from its own draws and gives them to draws that
  sample it (`XBRT_SHADOW_SYNC=0` turns it off): flicker map at 60 fps 8374
  -> 2036 pixels, the rest moving railings and the timer. Found by dumping
  the program and constants of every shadow-map and receiver draw over 12
  frames and looking for rows that toggle A/B/A between frames.
  Also done: bilinear PCF for shadow compares (as the NV2A filters), the
  polygon offset's slope term per Xbox pixel (x render scale), and our own
  read-backs no longer make aliasing framebuffers re-upload RAM.
- **2026-10-20 (interactive, later): where things stand. Next up.**
  - Done: cars' paint (combiner stage halves read the registers before
    the stage), yellow loading screen (DXT texture over a depth buffer
    drops the GPU depth), boot splash turbo icon in a black square (the
    loading thread blends it on the CPU into the shown buffer; on slow
    frames the read-back now lands at once), keyboard controls (stopgap:
    W/S throttle and brake, A/D or arrows steer, Space/Z A, X B, C X, V Y,
    Q/E white/black, Enter start, Esc back).
  - **Open, the user's top item: lighting flicker on static scenery at
    60 fps** (pit building wall, stands, grass; seen with the car stopped,
    so not motion). User: "better than last time, but still a glaring
    issue". First look: with shadow lookups forced lit (a temporary
    u_noshadow), the large flickering areas went and only thin edges
    shimmered, so it is mostly the shadow maps alternating A/B under the
    60 fps patch, which shadow sync (rows 90-95) does not fully cover.
    Runs are not deterministic (the car takes a different line), so the
    next step needs a fixed view: record the grid (before the throttle)
    or the stopped car at ~100 s, at XBRT_FPS=60 vs 30, with and without
    shadows, and flickmap2-style counts (pixels that go up then straight
    back down). Then dump each frame's shadow-map draws and receivers'
    texture/zaddr/c92-95 over a few frames, as for the first shadow sync.
    **Later the same day, still open; what was learned:**
    - The "shadows off removes it" result above is not sound. The pop count
      (pixels that jump by >20 for one frame and come back within 6;
      scratch pops.py) swings 4-8x between identical runs (7.5 to 57 per
      frame) because the car takes a different line. Three runs at once
      also slow each other and hide it (0 pops), so record one at a time.
      Shadows off gave 52 vs 57 run alone, so not the shadows.
    - Not the cause, each measured: frames presented out of order (never),
      the display falling back to RAM (never, headless or windowed),
      colour/depth uploads from RAM over the GPU's frames (only at the race
      start), the speed blur's previous-frame input (steady; skipping
      those 26 draws/frame: 13.6/7.5 vs 25.3/9.2 pops, no change), the
      160x120 glow buffer (always from the GPU, steady).
    - Shadow receivers: every frame they sample the GPU map with its own
      rows (shadow sync works). Rows 90-95 still toggle A/B/A every frame
      (1.823/0.998), in draws that sample no shadow map, so probably
      unused there. Toggle analysis: dump c[192] per vertex-program draw
      for 12 frames (cdump.bin, scratch toggle.py/toggle2.py).
    - Looking at frames of the user's clip: lighting is steady frame to
      frame; what pops is thin detail (window bars, railings, crowd)
      shimmering as the camera moves. Need from the user: a phone clip
      or exactly where/what flickers, to know whether that shimmer is it.
  - **Frame drop at the start of the race:** first race of a session: 33
    vertex programs built at once, one 239 ms frame (~106 ms of it the
    builds; the NVIDIA driver caches them on disk, so later runs mostly
    skip it). In the race's first seconds, with the cars together, the
    frame rate falls from ~59 to ~39-50 fps with 40-64 ms frames, while
    the device thread is mostly idle (pusher 1.5 s of 5 s against 4.2 s
    at a smooth 59 fps). Stack samples: the game's threads wait in
    NtWaitForSingleObjectEx (ordinal 234, handle 688, from f_00264D8F <-
    f_00264EA5 <- f_0042D94E), i.e. on something we signal late. A wait
    log found no long waits there, but that run may not have reached the
    race: redo it (XBRT_FRAMELOG-style timestamps with the waits) and
    find what sets that handle.
  - `clips/forza-progress-2026-10-20*.mp4` (ignored): the build at this
    point; `run/race-rec.txt` reaches the race without the pause menu.
- **2026-10-20 (interactive): loading screen, race-start audio, speed.**
  - Loading screen was yellow stripes: Forza puts its picture (1024x512
    DXT5) in the race's depth-buffer memory (01e98000) and our old GPU
    depth was read back over it. A dirty depth buffer whose RAM no longer
    hashes to what the GPU left there is now dropped (CPU wins).
  - Race-start audio: silent 32-sample frames while DSOUND's ISR took an
    idle voice back (the mixer stopped while trapped, and stopped the
    rest of the frame on handing back): up to ~90 clicks/s, bimodal per run.
    Voices now keep playing while trapped. Plus a compressor (2 ms / 250
    ms) instead of per-sample soft clipping (the start is ~5x louder), and
    volume ramps per frame. Clicks 3-7/s.
  - Speed (windowed, 60 fps mode): race start 45 -> 58 fps. Sparse change
    signatures (64 B per 2 KB) instead of full hashes of every texture and
    framebuffer each frame (36 GB -> 1.8 GB hashed per run); lazy hashes
    after our own read-backs; vertex fetch with one loop per format.
  - Latency: picture collected when its copy finishes (not at the next
    vblank), window repaints on a new picture (event, not the 16 ms timer),
    one frame queued on the GPU (`XBRT_GL_QUEUE=2` for two): ~2 frames less.
  - **Cars' dark rear/lower body: a confirmed bug** (the user's reference
    shot of the same start shows the rear lit). Narrowed down with a debug
    view of the car paint's inputs: diffuse vertex colour is lit, texture
    stage 0 (the car atlas) is right, **texture stage 1 is black over the
    lower body**: it is a shadow-map lookup (format 2E, mode 2 = project3d
    compare, SHADOW_DEPTH_FUNC GREATER), and the car fails it on its own
    body. Our compare matches xemu's (map depth > fragment's z/w). Ruled
    out: shadow maps through RAM, shadow-matrix sync, cube maps, CPU vertex
    programs, culling. Next: which map the car samples (512 or 768) and
    whether its own draws into that map (depth, polygon offset) or the
    receiver's q.z (c90.w bias term differs between casters and receivers)
    are off. **2026-10-20 later:** the car samples BOTH maps (768x768 at
    02ad1000 and 512x512 at 02a64800), and no car draw goes into either
    (casters: car 0, zwrite on, zfunc LEQUAL, polygon offset on with bias
    -2000 and factor 1, cull back faces). So the car is shadowed by the
    track/world casters, not by itself: next, check the depth range those
    casters write (bias -2000 in depth units, our offset applies it per
    fragment in the shader) against the car's q.z.
    **Then:** a debug view of the lookup on the car (inside the map? passes?
    its z against the map's depth) shows the car's lower body is inside the
    512x512 map and well behind what the map holds there (~1% of the depth
    range, car-sized), and the map seen on the car has car-shaped shapes:
    the cars are drawn into it (untextured casters, so not caught by the
    'volume texture' test above). The car's front, toward the low sun,
    shadows its rear: plausible. What differs from the console is the
    effect: there the rear keeps its paint (only direct sun goes), here the
    whole surface goes black. Next: look at how the car's combiner stages
    use stage 1's result (which registers/channels; whether the shadow
    should scale only one term) against xemu's combiner code. Ruled out
    since: the casters' polygon offset (off, bias only, factor only,
    negated: no change). Also added: texture address mode 4 (border, with
    SET_TEXTURE_BORDER_COLOR), which the shadow lookups use.
    **Then: the combiners.** The car paint (8 stages; T0 a 3D texture,
    T1 the shadow map, T2 2D, T3 a cube map) does, in alpha:
    `v1.a *= T2.a`, then `v1.a *= T1.b` (the shadow) and
    `r0.a = 0.70 * T2.b`; then rgb `v0 = v0 * (v1.a + r0.a)`. So the
    shadow only removes the v1.a term; `0.70 * T2.b` should stay. A debug
    view (rgb = T2.b, T2.a, shadow) shows T2's blue and alpha are ~0 over
    the whole car except the tail-lights, while v0 is fine (white): that
    is why shadowed paint is black, not the shadow. T2 is not a texture
    from RAM: it is a 256x256 framebuffer the game draws itself each
    frame (`surface` 1, sampled on the GPU, address wrap). Next: find
    what is drawn into that 256x256 target (its format: X8R8G8B8 alpha?
    is it written at all, or read before it is drawn?) and what the car's
    T2 coordinates are.
    **Fixed (and the above corrected):** T2 is fine: dumped on every
    frame it is all white (A8R8G8B8 256x256 at 02a..-02b..). The debug
    view read R[10] after the stages had run, and stage 1's RGB half
    writes R[10] (a dot product). That was the bug itself: both halves of
    a combiner stage read the registers as they were before the stage,
    but ours ran RGB first and the alpha half read what it had just
    written, so `r0.a = 0.70 * T2.b` took the dot product (~0 on the rear
    and lower body). Both the shader and the CPU combine() now read a
    copy taken before each stage. The cars keep their paint in the sun's
    shadow, as on the console.
    Found on the way, both kept: CMP packed normals (vertex type
    6, attribute 2) were read as zeros; face culling (SET_CULL_FACE_ENABLE
    etc.) was never applied on the GPU path (winding swapped for our y).
  - Was: the cars' rear/lower body is near black in races (same with
    shadow maps from RAM, no shadow sync, cube map from RAM, CPU vertex
    programs: so it is the game's lighting maths as we run it, right or
    shared-wrong); needs a reference shot (xemu or console). Foliage
    edges look dotted at 2x: the leaves' alpha test, would need
    alpha-to-coverage. The hill corner's missing scenery is unseen here
    (the throttle-only script never gets there).
  - `XBRT_RECORD=<file.mp4>` (with `XBRT_RECORD_FROM`, `XBRT_RECORD_FOR`
    seconds and `XBRT_FFMPEG`): the picture at every vertical blank piped
    into ffmpeg, H.264 at 59.94 fps, scaled 2x. `tools/input/race-fast.txt`
    reaches the race on NVIDIA and starts driving at ~63 s; record from
    55 s. Clips go in `clips/` (ignored: game footage is never pushed).
  - The input script's timings were made for ~30 fps: on NVIDIA the
    menus run far faster and `race.txt` sometimes ends in the pause menu.
  - Beware when judging runs: `race.txt` holds the throttle and never
    steers, and the grid slot changes from run to run (4th to 8th). From
    the inner slots the car ends against the pit-lane pillar or the
    grandstand wall at 0 mph with the wheels spinning, with or without
    any of this. Compare the start (shot 8, 160 s), not where it ends up.
- **Tried and failed:** reading back only the buffer PCRTC_START is
  pointed at (a request to the device thread from the vertical blank
  handler's register write) left the game stuck in boot with 100,000+
  flips: the driver-queue problem above, before the fence existed.
- The game's render thread waits in D3DDevice_BlockOnFence most of the
  time; DSOUND/XACT threads (DirectSoundDoWork, deferred commands that
  never complete because no voice is ever processed) are most of the
  guest CPU and hold the big lock at DISPATCH_LEVEL.

Fixed tonight that mattered most: DSOUND reset both audio DSPs ~33
times a second (P:6 of the EP did not hold its image's 0xCCCCCC, because
nothing bootstrapped the DSPs), each time stalling 10 ms with the big
lock held. `apu.c` now copies the boot words like the DSP boot ROM.

When the runtime stops with `indirect call to X, which is not a
translated function`, add X to `tools/entries.txt` and regenerate:
discovery cannot see functions only reached through computed pointers
(always regenerate with `-entries tools/entries.txt`).

Open bugs, in order:

1. Flip pacing: a real FLIP_STALL (NV_PGRAPH_SURFACE read/write
   indices, D3D's handler moving the read index through
   NV_PGRAPH_INCREMENT) was tried and reverted: one run froze at a flip
   with get != put. The handler moved the read index once more than
   there were frames around loads. Understand its bookkeeping (it flips
   on the frame notify, see above) before trying again.
2. Software rasteriser (no `XBRT_GPU`): in the race, triangles that
   cross the near plane are drawn stretched across the screen, with
   smeared textures (no clipping against w); the same before tonight.
   `XBRT_BATCH=1` there leaves the race view black.
3. Rendering: no stencil, no fixed-function fog (`SET_FOG_GEN_MODE`),
   depth textures (shadow maps) are still decoded from RAM, anisotropic
   filtering and LOD clamps ignored.
4. Audio: none. DSOUND's voices are never processed, which also makes
   it busy (above). The register layout is in xemu's
   hw/xbox/mcpx/apu/apu_regs.h; the voice processor is apu/vp/.

## Next after that

1. Speed: depth textures (shadow maps) sampled from their framebuffer
   on the GPU instead of read back in texture(); then batched draws
   (~1300 a frame in the race). With the fence now bounding the queue,
   pacing flips to the vertical blank (FLIP_STALL) can be tried again.
2. Audio: the voice processor (front-end methods into voice memory,
   voice lists, sample fetch, pitch and volume into the mixbins, voice
   notifications), even before any sound comes out, so DSOUND's deferred
   commands complete.
3. Drawing: stencil, fixed-function fog, depth textures on the GPU, 3D
   textures. See the phase 4 list in [ROADMAP.md](ROADMAP.md).

## Log

- **2026-10-24 (interactive, the user driving): speed, pacing, hangs.**
  - Hill-corner scenery: draws over 4096 vertices were cut off (fixed
    arrays); now they grow. The user confirmed the cliff shows.
  - Race-start hang: the GPU parked in a FLIP_STALL that D3D's vertical
    blank handler never released (XBRT_FRAME_TRACE showed S with no R).
    FLIP_STALL no longer follows FLIP_READ/WRITE: it waits only while two
    finished frames wait to be shown (three-buffer pacing, max 60 a
    second). Releasing stalls by hand instead desynced D3D (bunched
    frames, sluggish menus); two-buffer waiting gave ~40 fps.
  - The window is drawn by OpenGL from copies of finished frames taken at
    flips (newest framebuffer per shown address); menus, movies and
    loading screens from RAM (rt_display_compose) the same way. Once GL
    has drawn a window, GDI pictures no longer show in it.
  - Per GPU draw (XBRT_STATS): ~16 us in a race, ~900-1500 draws a
    frame, the device thread 80-100% busy: fetch 5-8 us, gl_bind 4-5 us
    (hash checks after sync points), upload ~1.3 us (attributes packed),
    frag ~1 us (sampler objects). Next: fetch (each vertex starts as a
    256-byte copy of `cur`) and gl_bind.
  - Race 52-57 fps headless at the heavy start; the user reports smooth,
    no flicker, pause no longer locks up.

- 2026-10-19 (nightly, branch nightly/2026-10-18): GPU path from 9-10
  to ~15-20 fps in the race (3055 -> 8500-8700 flips over the 415 s run).
  Texture mipmaps, filters and LOD bias from SET_TEXTURE_FILTER; fog
  (register 3) on both paths. Framebuffers over the same bytes exchange
  pixels on the GPU and read back in drawing order; depth read back only
  when written (a 1.2 MB "depth buffer" at physical 0 was being read back
  over low RAM). Render targets sampled from their framebuffer (step 5).
  Vertex programs decoded once per change (bit-identical over 300M
  vertices) and run on the GPU by default (step 3). Vertex array layout
  once per Begin; RAMHT lookups remembered; interrupts wake the DPC
  thread. The black top-left quarter and grey flyby frames: D3D's
  per-frame notify lets its vblank handler show a frame before
  FLIP_INCREMENT_WRITE, and RAM still held the frame's environment and
  bloom passes; scanout buffers are now read back before notifies. The
  APU bootstraps its DSPs (P memory from scratch memory), which stopped
  DSOUND resetting them 33 times a second with 10 ms stalls under the
  big lock. The shown buffers are read back through pixel buffer objects
  without waiting, nothing at flips, and a fence keeps two frames queued
  at most (without it the Intel driver's queue filled and blocked).
  Tried and reverted: a real FLIP_STALL (one hang), GL state caching and
  a streaming vertex buffer (no gain), syncing only at PCRTC_START (the
  driver-queue block, before the fence). Forza's race frame, for
  reference: an environment pass into the coming front buffer, the scene
  into the 1280x480 anti-aliased buffer (01c40000, depth 01e98000),
  bloom: a 320x240 downsample into the front buffer's top-left, 320x120
  below it, 160x120 elsewhere, the resolve into the front buffer, the
  notify (0x33d00121 / 0x36280121), then shadow and reflection maps for
  the next frame, FLIP_INCREMENT_WRITE and FLIP_STALL.
- 2026-10-18 (interactive): Windows port; boot through install, DSOUND,
  font cache and front end to the main loop. See the commit for detail.
- 2026-10-18 (interactive, afternoon): branches now pushed to GitHub as
  backups. Fixed: decoding of an instruction that ends in a section's
  zero-filled tail (FZFULLUI's last byte; found 0x3A98C0 and ~25 more);
  prologues after a function's final jmp count as starts (~740 more
  functions); AC'97 controller model (channel reset); GP DSP command
  mailbox acknowledged (effects not run); MmLockUnlock*; threads created
  suspended plus NtResumeThread/NtSuspendThread; MMIO range widened to
  everything from 0xFD000000. The game now reaches the attract movie.
- 2026-10-18 (interactive, evening): software rasteriser (raster.c):
  vertex program interpreter, viewport and matrices in the transform
  constants (c58/c59 were zero, so every program put vertices at 0),
  anti-aliasing scale, register combiners (the downsample pass was black
  because texture times diffuse is not what its combiners say). Menus
  draw, without text.
- 2026-10-18 (interactive, night): text. Forza's text is rendered from a
  glyph cache (a 512x512 palettised texture with four glyph layers in
  its R, G, B and A channels; glyphs come from `Z:\fontcache`, which
  the game unpacks from `euro.SXWad` with zlib, read on demand through
  ReadFileEx). Each glyph quad picks its layer with a dot product
  against texture stage 1 in pass-through mode, whose "texture" is the
  texture coordinate itself. The rasteriser only had stage 0; with all
  four stages and the pass-through mode, menus have their text. New
  debugging aids: `XBRT_TEX_DUMP`, `XBRT_RAM_DUMP=<file>:<seconds>`,
  user APCs and pixel-state combinations logged at level 2.
- 2026-10-18 (interactive, night): profile saving and the main menu.
  "Unable to save player profile" came from the recompiler, not the
  runtime: a data reference had made a false function start at
  0x7B649, the instruction after a `cmp` in the save routine, and the
  generated code reached it through a host call, so the `jnz` there read
  fresh flags and took the failure path. `analysis.Body` now walks
  through a known start that code falls into or branches to
  conditionally (3,198 functions in Forza do), stopping only where a
  `jmp` reaches it. Also: NtFlushBuffersFile, `XBRT_INPUT_SCRIPT` for
  timed button presses, `XBRT_LOG_FROM` to log only late in a run, and
  `xbrecomp -trace a,b,...` to make chosen functions log their arguments
  and results (it rewrites only changed C files, so a rebuild with a
  trace takes about a minute).
- 2026-10-18 (interactive, evening): into a race. Saves: with XboxHDKey
  zeroed XAPI keys signatures with the whole EEPROM, which the runtime
  left as stack garbage ("profile is damaged" on the next boot); now a
  fixed image. Fibers: a deleted fiber's host thread could be woken for a
  new fiber at the same address (KeBugCheck); MmDeleteKernelStack now
  forgets them. Files: ObfDereferenceObject did nothing, so closed files
  kept their share access and an exclusive reopen of a track file failed
  (the race load hung reading INVALID_HANDLE_VALUE). XLATB translated.
  Rasteriser: depth buffers, perspective-correct interpolation, the
  specular colour (V1). New aids: `XBRT_THREAD_DUMP=<s>[,<s>...]`, and
  sharing violations, reads past EOF and reads on bad handles print
  without a log.
- 2026-10-18 (interactive, night): races run and drive. Freezes: D3D
  learns GPU progress from PATT_COLOR0 (0x400B10), which the image
  pattern object's SET_MONOCHROME_COLOR0 (class 0x44, 0x310) sets; the
  old guess lost the lap bits, so D3D overwrote unread commands. The
  pusher now reads PUT every word, publishes GET as it goes and parks on
  a jump to itself (it spun forever before, starving vertical blanks).
  CancelIo's walk of IdexChannelObject+0x28 needs an empty list, not
  zeros. Rendering: cube maps, shadow maps (depth textures with the
  shadow compare). Speed 0.35 -> ~2.8 fps: filling on worker threads by
  rows, vertices once per draw and in parallel, a texture cache kept
  across surface changes (hash-checked). XBRT_STATS, XBRT_BATCH,
  XBRT_RASTER_THREADS; host crashes print their address.
- 2026-10-18 (interactive, evening): CPU detection (pushfd/popfd keep
  AC/ID, cpuid answers as the Xbox's Pentium III), so Bink finds MMX;
  CVTPS2PI/CVTTPS2PI/CVTPI2PS; the video overlay's STOP register; the
  directory listing (NtQueryDirectoryFile); fibers (SwitchToFiber on
  host threads, MmCreate/DeleteKernelStack); SHA-1, HMAC and RC4 for save
  signing. The game now runs its front end; no boot blocker left.
- 2026-10-18 (interactive, night): a window and screenshots (front
  buffer plus the video overlay); colour clears. First pictures: the
  loading spinner, the attract movie and the intro movie with the Forza
  Motorsport logo.
