# web/scripts

Node tools that drive the built app in headless Chromium. Each one starts its own backend (`uv run bgsim`, a
temporary projects root) and serves the existing `web/dist`, so run `npm run build` first. Nothing is
written into `examples/`.

- `render-models.mjs`: draws the models of an example as the editor does and prints a layout lint (see the
  comment at the top of the script).
- `capture-thumbnails.mjs`: the example gallery thumbnails and `src/examples/gallery.json` (below).
- `serve_render.py`: the backend wrapper of `render-models.mjs`.

## capture-thumbnails.mjs

```powershell
npm run capture-thumbnails                                   # every example, real Julia worker
npm run capture-thumbnails -- --example beaver --example f16 # only these
node scripts/capture-thumbnails.mjs --example beaver --out $env:TEMP/thumbs   # try a shot without touching the committed files
```

For each example it imports the example through `POST /api/projects`, opens one model, screenshots the
fitted diagram and, for a model with a scene, the 3D view as an inset, and writes
`src/examples/thumbnails/<example>.png` (480 x 300, stepped down until it is under 80 kB) and the
example's `gallery.json` entry (title and description from the README, `hasScene`, `models`).

| Option | Meaning |
| --- | --- |
| `--example NAME` | Capture only this example (repeatable). Default: every example the backend lists. |
| `--out DIR` | Write the PNGs and a `gallery.json` copy to `DIR` instead of `src/examples/`. Use it to try settings; the committed thumbnails are only replaced without it. |
| `--port N` | The backend port (it also binds `N + 1`). Default: a free port. |
| `--fake` | The fixture worker: fast, but blocks beyond the minimal catalog draw without ports, and `--run` cannot run real models. |
| `--model NAME` | The model to shoot. Default: the first model with a scene. |
| `--run` / `--no-run` | Run the model before the 3D shot and frame the scene on the run (below). Default: no run. |
| `--at FRACTION` | With `--run`: seek the playback to this fraction of the run (0..1, default 0.5). |
| `--time SECONDS` | With `--run`: seek the playback to this simulation time (wins over `--at`). |
| `--view iso\|top\|front\|side` | With `--run`: camera preset before the fit. |
| `--zoom NOTCHES` | With `--run`: mouse-wheel notches toward the scene point at the view centre after the fit (each notch 20 % closer; negative zooms out). |
| `--orbit DX,DY` | With `--run`: after the zoom, a left drag of that many pixels from the view centre, which orbits the camera around the scene point there. A negative `DY` tilts a top view toward the horizon. |

### Scenes framed after a run

Without a run the 3D view shows the scene at its rest poses. A scene whose objects are placed by bindings
(aircraft, vehicles, anything on a free joint far from the origin) then frames the whole floor and the
objects come out as dots. With `--run` the tool clicks Run, waits until the run is done (the run bar says
`done`; a failed run or a 3D stream error stops the tool with that message), makes the window taller (so the
3D view is closer to the inset's aspect and its centre crop keeps the framed objects), opens the 3D View,
pauses the playback, seeks to `--at`/`--time`, applies `--view`, clicks Fit, zooms `--zoom` notches, drags
`--orbit` and only then shoots the inset.

The zoom and the orbit aim at whatever is under the view centre after the fit. Fit frames the bounds of the
whole scene, which is not always where the objects are: pick a time at which the object you want sits in the
middle (for the Beaver an early time, before the control steps spread the formation), and try settings with
`--out` before committing them.

Settings that belong to an example go in its `gallery.json` entry as `capture`, so a full
`npm run capture-thumbnails` reproduces the shot. The tool keeps the object when it rewrites the entry, and
command-line options override it. The Beaver's:

```json
"beaver": {
  "title": "DHC-2 Beaver",
  "...": "...",
  "capture": { "model": "beaver-steps", "run": true, "time": 8, "view": "top", "zoom": 6, "orbit": [0, -80] }
}
```

Keys: `model`, `run`, `at`, `time`, `view`, `zoom`, `orbit` (as the options above) and `runTimeout` (seconds
to wait for the run, default 900). `thumbnail-capture-settings.mjs` checks them: an unknown key or a bad value
stops the tool, and `tests/gallery-thumbnails.test.ts` checks the committed ones. The committed
`thumbnails/beaver.png` predates these settings (it was composed by hand); regenerate it with
`npm run capture-thumbnails -- --example beaver` if the framed shot is preferred.
