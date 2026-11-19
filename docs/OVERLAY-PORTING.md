# The F1 settings overlay in another host

For anyone running this runtime under a different launcher, or lifting the overlay into another runtime
(written 19 Nov 2026 with xrevive in mind). The overlay is the F1 / Back+Start menu: settings, achievements,
Mayhem Moments.

## If the runtime is used whole

It works as it is. Three things it expects, each with a switch:

| Needs | Default | Switch |
|---|---|---|
| The OpenGL renderer (4.3) | software renderer, which has no overlay | `XBRT_GPU=gl` |
| The settings file | `forza.ini` in the working directory | `XBRT_SETTINGS=<path>` |
| The game's font cache (`<hdd>/Partition*/fontcache/euro/*.abc`, `.sbm`) | `hdd` in the working directory | `XBRT_HDD=<path>` |

Without the font cache the menu draws its text in Segoe UI (`rt_gl_host_font`, gl.c) and logs
`xbrt: overlay: no font cache under ...`. `XBRT_OVERLAY_HOSTFONT=1` forces that for testing;
`XBRT_OVERLAY=1` opens the menu at start-up.

Other paths it reads: `XBRT_MODS` (the Moments' photographs), `XBRT_ACHIEVEMENTS` (the achievements file).

## Keys and buttons

- Keyboard (display.c): F1 opens and closes; arrows move; Enter changes; Esc backs out; Q / E, Tab, PgUp / PgDn
  switch tabs. While it is open the game sees no input.
- Pad (overlay.c, `rt_overlay_pad`): Back+Start opens and closes; D-pad or left stick; A, B; the triggers switch tabs.
- A launcher that maps keyboard keys to pad buttons should leave F1 alone, and should know that Q also opens Prize
  Match on the career menus. xrevive's default key list includes Q, E, Enter, Esc and the arrows: with its keyboard
  mapping on, those reach the overlay as pad presses only if the launcher sends them as such, so check the tab keys.

## If only the overlay is lifted into another runtime

Two files hold it: `overlay.c` (the menu: items, tabs, input, applying a change) and `glover.c` (the drawing).
What they call in the rest of the runtime:

1. **A draw call at the end of each frame.** `gl_overlay_draw(x, y, w, h)` builds a list of coloured quads
   (`OvVert`: position, uv, colour, kind) and draws them with one small shader (`ov_vs` / `ov_fs`) in a 640x480
   (or 853x480) coordinate space. Porting to another API means replacing `ov_init` and `ov_submit` only.
2. **Four font atlases.** `ov_font_load` makes an R8 texture of 16 x 6 cells of 34 px, with each character's A, B, C
   widths. Any source of glyphs will do.
3. **Input.** `rt_overlay_key(RT_OV_*)` takes abstract keys; `rt_overlay_pad` takes the Xbox pad's state and
   returns 1 when the game should not see it.
4. **Settings.** `rt_settings_get(name)` / `rt_settings_set(name, value)` (settings.c: a flat ini). `apply()` in
   overlay.c sets the runtime's own globals for the ones that take effect at once; those lines are specific to this
   runtime and are what a port would rewrite.

The race HUD's additions (`gl_tt_hud_draw`), the Quick Race menu and Prize Match share the same quad list and
shader. `XBRT_HUD_DEMO=1..7` (9 cycles through them) shows each HUD piece with sample figures.
