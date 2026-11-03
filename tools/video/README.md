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
- `capture-bridge-pier.mjs <out-dir> [--fps 25] [--max-frames n] [--zoom 9] [--compose-only]`: the `bridge-pier` example, the
  dashboard (library, inspector and dock hidden) next to the detached 3D viewer, in two segments: the 40 t lorry buckles the slender
  diagonal and the redundant truss holds, then the strength slider at 0.5 and the bridge collapses. Every run happens off camera;
  frame k sets the playback time to k*s/fps (fixed dt). Writes `bridge-pier.mp4` and stills (before the run, mid and end of each
  segment); `--compose-only` composes again from the saved frames.
- `capture-vdp-belt.mjs <out-dir> [--fps 30] [--zoom 2] [--zoom-at 0.5,0.55] [--wheel 120] [--orbit 0,-35] [--stills] [--compose-only]`:
  the `vdp-belt` model of `van-der-pol`, the dashboard next to the detached 3D viewer, in real time (frame k at t = k/fps) for
  three runs set on the dashboard sliders: mu = 0.5 growing onto the limit cycle, mu = 1.0, and mu = 0.5 shrinking from x0 = 2.5.
  The caption bar shows the simulation time. `--stills` writes only the framing stills (`camera-fit.png`, `camera.png`, segment ends).
- `capture-suction-cup.mjs <out-dir> [--fps 30] [--zoom 6] [--zoom-at 0.5,0.55] [--orbit 0,-40] [--only a,b] [--stills] [--compose-only]`:
  the `suction-cup` example, the dashboard next to the detached 3D viewer, one segment per model (hold and release, bounce,
  steps, swing, chirp, overload, linear vs nonlinear), each in real time (frame k at t = k/fps). Every run happens off camera.
  The caption bar names the motion and shows the simulation time. Writes `suction-cup.mp4` and stills per model (dashboard
  before the run, camera framing, mid and end of the segment).
- `capture-quad-pendulum.mjs <out-dir> [--set main|travel] [--fps 30] [--max-frames n] [--only cart,rotary,push] [--stills] [--compose-only]`: the
  `quad-pendulum` example in the same layout as `capture-vdp-belt.mjs` (dashboard plus detached 3D viewer, real time): the cart
  swing-up and balance, the rotary-arm swing-up (`QP_ROTARY_MODEL` picks another rotary model) and the cart balance with 3 ms of
  actuator delay and a tip push. Writes `quad-pendulum.mp4` and per segment `<id>-camera.png`, `<id>-3d-mid|end.png`,
  `<id>-dashboard-mid|end.png`. `--set travel` records the two cart controllers instead: the full-travel swing-up, the
  switch of the dashboard's Controller select (highlighted, 2 s) and the short-travel swing-up on the same page; writes
  `quad-pendulum-short-travel.mp4` (phases are `cart0`, `cart1`).
- `capture-beams.mjs <out-dir>`: stills of the `cantilever-sections` example: the settled static bend (x10 and true scale), a
  close-up at the wall, the step peak, the dashboard with load "1 · sine" selected and run, and two opposite crests of the
  round bar's resonance.
- `capture-ball-and-plate.mjs <out-dir> [--fps 30] [--seconds 30] [--zoom 6] [--zoom-at 0.5,0.5] [--orbit 0,0] [--stills] [--compose-only]`:
  the `ball-and-plate-track` model (LQR with a Kalman filter tracking the figure-8), the dashboard next to the detached 3D
  viewer, in real time (frame k at t = k/fps). The run happens off camera. Writes `ball-and-plate.mp4`, `camera-fit.png`,
  `camera.png` and the end stills; the 30 s video uses `--zoom 2 --orbit 0,-30`.

## Recorded showcases (Playwright `recordVideo`, 25 fps)

- `capture-suction.mjs <out.mp4>`: the suction-gripper video.
- `capture-flexarm.mjs <out.mp4> [--shots <dir>]`: the triple rotary pendulum on a rigid arm, on the flexible arm with the rigid
  firmware (slow motion of the arm mode), and with the low-pass firmware. The 3D stage runs full screen; the model runs are cut.
  `--shots examples/pendulum-triple-rotary/design/_shots` also writes the paused close-ups that `flex_finish.py --docs` puts in the docs.
- `capture-fanuc.mjs <out.mp4> [--shots <dir>] [--theme dark|light]`: the `fanuc-pick` example. Every pick plays at 1x and is
  labelled "1x real time"; slow-motion repeats carry their factor. Side-by-side pairs start together at 1x: the level optimum
  against the waiter tilt (`pick-place-best` / `pick-place-tilt-best`) and the old optimum against the free optimum
  (`*-best` / `*-opt`). The runs and model switches are cut. `--shots` writes a 3D-view and a dashboard screenshot per model.
