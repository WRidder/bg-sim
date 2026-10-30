# Stop-motion videos of bg-sim (X5.V)

Two MP4s (H.264, 1920x1080, yuv420p, no audio) built from Playwright stills of the real app:

- `media/video/bg-sim-intro.mp4`: the software and its key features (12 scenes).
- `media/video/bg-sim-examples.mp4`: a tour of every example (card, diagram, 3D view and plots stepping through the run).

Intermediate frames go to `media/video/frames/` (git-ignored).

## Regenerate

Prerequisites: `web/dist` is built (the backend serves it), `npm install` was run in `web/`, Julia is set up,
and ffmpeg is on PATH (otherwise `uv run --with imageio-ffmpeg` supplies the binary).

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
