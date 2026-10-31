# Stop-motion videos of bg-sim (X5.V)

Two MP4s (H.264, 1920x1080, yuv420p, no audio) built from Playwright stills of the real app:

- `media/video/bg-sim-intro.mp4`: the software and its key features (12 scenes).
- `media/video/bg-sim-examples.mp4`: a tour of every example (card, diagram, 3D view and plots stepping through the run).

Intermediate frames go to `media/video/frames/` (git-ignored).

## Regenerate

Prerequisites: `web/dist` is built (the backend serves it), `npm install` was run in `web/`, Julia is set up,
and ffmpeg is on PATH (otherwise `uv run --with imageio-ffmpeg` supplies the binary).
The scripts launch Chromium through `launchBrowser()` in `lib.mjs`, which passes ANGLE on D3D11 so the headless
browser renders WebGL on the GPU. Plain `chromium.launch()` falls back to SwiftShader (WebGL on the CPU): the 3D
view then renders a few frames per second, and recordings of it stutter and flash.

1. Start a private backend (real Julia worker) on port 8810 with a temporary projects root:

   ```powershell
   $env:BGSIM_PORT_HTTP = "8810"; $env:BGSIM_PROJECTS_ROOT = "$env:TEMP/bgsim-video-proj"
   uv run bgsim          # wait until /api/health reports worker: ready; it also binds port 8811
   ```

2. Capture (each script creates and deletes its own project copies through `POST /api/projects`):

   ```powershell
   node tools/video/capture-examples.mjs [--only a,b] [--skip a,b] [--steps 6]   # video 2, ~25 min
   node tools/video/capture-intro.mjs [--scene s02,s05,...]                      # video 1, ~10 min
   ```

   `examples.json` holds per-example camera overrides (`zoom` mouse-wheel notches, `view` preset, `model`, `signals`, `tend`).
   Plotted signals default to the ones named by the checks in the example's `expected.json`.

3. Compose and encode (HTML cards and frames screenshotted by Playwright, then ffmpeg):

   ```powershell
   node tools/video/compose-examples.mjs      # card texts live in tools/video/cards.json
   node tools/video/compose-intro.mjs         # scene list and captions are at the top of the script
   ```

4. Stop the backend: `taskkill /PID <pid> /T /F` (find it with `netstat -ano | findstr :8810`).

Files: `lib.mjs` (helpers), `theme.mjs` (look: dark background, amber accent, Segoe UI), `encode.mjs` (ffmpeg),
`_sheet.mjs` (debugging helper, e.g. `node tools/video/_sheet.mjs v-3` makes a contact sheet).

## Real-motion pipeline (v2: 30 fps intro, 60 fps examples)

- Intro (30 fps): `capture-intro30.mjs` records each scene in real time with the CDP screencast (`rec.mjs`: JPEG q92 at 1920x1080,
  every frame, a virtual clock that is paused during page loads and long waits, an injected cursor overlay and paced, smooth mouse
  and keyboard actions). `compose-intro30.mjs` resamples the variable-rate frames to a constant 30 fps with ffmpeg (concat list with
  per-frame durations plus `fps=30`), burns the caption bar in (marks of the capture script and captions of `intro-plan.mjs`) and
  joins the title cards. Pop-out windows are inserted as short stills.
- Examples (60 fps): `capture-sim60.mjs` runs the model, detaches the 3D viewer into a pop-out window and, for frame k, sets the
  playback time to k*s/60 on the slider of the viewer (the plot cursor of the main window follows), waits two animation frames and
  screenshots the 3D canvas and the plot panels. It is resumable (cached per example in `frames/sim60/<example>/done.json`).
  Playback speed s = T/L with L = clamp(T, 6, 10) seconds of video. `compose-sim60.mjs` lays out diagram, plots and 3D with one
  ffmpeg filter graph per example (t and speed in the header, progress bar), then joins the cards and clips.
- Order: `compose-examples.mjs --no-encode` (cards, comparison frames), `compose-intro.mjs --no-encode` (title and scene cards), then
  the two v2 composers. `capture-examples.mjs` still provides the diagram images and the plotted signals per example.

## Robird video and extras

- `capture-robird.mjs --seg lap|close` (60 fps playback segments of the `robird` model, parametrised at the top; `--scan` writes a camera zoom scan),
  `capture-robird-ui.mjs` (30 fps UI recording of the diagram and the Docs tab), `compose-robird.mjs` -> `media/video/robird.mp4`.
- `capture-sim60.mjs` accepts per-example camera settings in `examples.json`: `view` (preset), `orbitX` (pixels of horizontal orbit drag), `zoom` (wheel notches), `--scan` (zoom scan).
  aerial-contact uses the iso preset orbited to the drone side (orbitX 3000, zoom 11) so the hexarotor and the wall contact fill the panel.
- `_sheet2.mjs <dir> [regex]` makes a contact sheet of scan images.
