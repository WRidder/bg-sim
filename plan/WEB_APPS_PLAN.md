# Web games

The FMU-based desktop apps (`apps/f16-sim`, `cessna-sim`, `a109-sim`, `car-sim`) as browser games, in `apps/web`. They have nothing to do with the bg-sim editor: no backend, no Python, no Julia at run time. A static file server is enough, and each game also builds into one HTML file that opens from disk and can be mailed around.

## Decisions

| | Decision | Why |
|---|---|---|
| W1 | FMU compiled to WebAssembly with Zig (through `uv`) | The FMU's C sources need no change. Zero imports, 60 KB, about 2 µs per step for the F-16. A 30 s manoeuvre matched the native FMU to 6e-12 m. |
| W2 | three.js WebGLRenderer, TypeScript, Vite, no React | 156 KB gzipped against 635 KB for Babylon. The look comes from hand-written shaders either way. |
| W3 | The simulation runs on the main thread, in a fixed-step accumulator on `requestAnimationFrame` | SharedArrayBuffer needs COOP/COEP headers, which `file://` and a plain server do not give. A step costs microseconds, so no worker is needed. |
| W4 | The Wasm sits in a generated TypeScript module as base64 | The static site and the single file load it the same way, without a fetch. |
| W5 | Everything is procedural: meshes, textures, sound, the world | Keeps the single file small and means no asset pipeline and no licences. |
| W6 | Not bit-for-bit with the desktop apps | The user's call: the games are redesigned, only the flight and vehicle models carry over. |
| W7 | Terrain and shadows are computed in an inline worker | Two seconds of noise must not freeze the page, and an inline worker also works from `file://`. |
| W8 | Telemetry and the setup are side windows in the engine (`side.ts`), described by each game as data | One window at a time on one side, with the keys, the memory and the room on the HUD in one place, so a new game writes a list and no drawing. |
| W9 | What can be set is what the FMU declares | `build_wasm.py` carries each parameter's start, range, unit and description into `model.gen.ts`, every `Sim` has a `Tuning`, and `Sim.restart` passes it on. The game's own values win over it. A game needs no code to get the feature, only labels to get it nicely. |
| W10 | A change counts from the next start, and the window says so | FMU parameters are `fixed`: settable before initialisation only (D-EX10), so a slider cannot move a running model. The FMU refuses a value out of range, so `Tuning` holds values to the range and drops a stored value that no longer fits. |
| W11 | The airfield is shared, in `src/island/` | The F-16 and the Cessna land on one runway. The code for it (`airfield.ts`, `field.ts`, `landing.ts`) moved out of the Cessna, because importing it from there would pull the Cessna's model into the F-16's bundle. `markLanding` takes the aeroplane's own `Marks`. |
| W12 | The F-16's `Frame` turns the FMU's north down the runway, and `lift` lays its plane on the runway | The FMU has no heading parameter and starts north at z = 0, and that plane has to be the sea at sea and the runway at the runway. `lift` is the height of the runway on the airfield and eases to 0 over 3 km, so the sea stays exact wherever the aircraft can reach it. |
| W13 | The FMU flies, the game judges | The FMU gives wheels and a flat plane. Whether a surface is there, whether a wing touched and whether the gear folded (320 kN a main leg, about 6 m/s of sink) is decided in `flight.ts` from the height of the airframe's points, as in the Cessna. |

## Layout

```
apps/web/
  build_wasm.py        FMU to src/<game>/model.gen.ts (gitignored, regenerate after an FMU changes)
  shim/                the C glue between the FMU and JavaScript
  index.html           landing page
  f16/ cessna/ a109/ cars/   one folder per game, each an index.html
  src/engine/          shared by all: Stage, Sim, gates, camera, overlay, sound, input, effects,
                       side (the side windows), telemetry, tuning
  src/<game>/telemetry.ts   what the game's panel shows, and the labels of its setup
  src/island/          the island the aircraft share
  src/<game>/          what is the game's own
  tests/               Vitest (unit, scripted pilots) and Playwright scripts (real keys, screenshots)
```

## Rendering

World (sky, terrain, sea, ground objects) into a multisampled HDR target, half-resolution ray-marched clouds over it, then the near scene (the vehicle and its effects) so that it stays sharp in front of them, then bloom, ACES and a little grading. The sky panorama is shared by the dome, the water and aerial perspective. Quality drops by itself in four tiers when frames run long.

## Telemetry and setup

`Panel` is a list of sections, each a list of items, and each item is the form that suits the quantity:

| Item | For |
|---|---|
| `gauge` | one quantity with a working range and limits: prop speed, rotor speed, motor rpm |
| `plot` | what matters as a shape over the last 12 s: pedals, body slip, load factor, angle of attack |
| `bar` | a share of a range, from the middle if it can go negative: control surfaces, torque against the limit, charge |
| `scatter` | two quantities that mean something together: the g-g diagram, rotor flapping |
| `corners` | one figure per wheel, where the wheel is, three for a tricycle: load, travel, slip |
| `value` | what only has to be read |

A value the FMU does not output is worked out in the panel from what it does: the cars' downforce is the Aero block's formula with the `ClA` in use, and slip over peak is the Tyre block's normalised slip (`normalisedSlip`, the same as `design/tyre.py`). To add a game: write a `Panel`, make a `SideBar` with `hud.room` as its callback, a `Telemetry`, and `new Setup(side).use(sim.tuning, title, knobs)`. Without `knobs` the setup lists every parameter with a range whose name does not end in 0, the exports' convention for start values.

What the race car's parameters do, floored out of a steady turn (`peak body slip`, constant steering, as a keyboard driver holds it; a spin is 90 degrees):

| Setup | 60 km/h | 100 km/h | 0.5 s later at 60 km/h |
|---|---|---|---|
| Stock (10 % slip, 300 N m) | 90 | 90 | 69 km/h |
| Traction control slip 5 % | 11 | 10 | 68 km/h |
| Traction control slip 3 % | 7 | 6 | 67 km/h |
| Torque 250 N m | 90 | 28 | 67 km/h |
| Torque 200 N m | 10 | 6 | 64 km/h |
| Limited slip 0 | 19 | 27 | 68 km/h |
| Limited slip 150 | 90 | 90 | 69 km/h |
| Aero balance 32 % front | 90 | 8 | 69 km/h |
| Downforce 4 m², or either anti-roll bar | 90 | 90 | 69 km/h |

At stock the motor gives 6.4 kN at the road below 147 km/h against about 6.7 kN of rear grip at rest, so full throttle leaves the rear tyres almost nothing to corner with. Half throttle does not spin. Traction control slip is the setting to reach for: it costs almost no acceleration, where 200 N m takes 0-100 km/h from 3.6 s to 5.4 s. Exposing these parameters changed nothing at stock: the old and new FMUs agree to 4e-8 on 14 s of driving, 1e-3 N on wheel load, and neither the method nor the step moved.

## Running

```
cd apps/web
npm ci
uv run build_wasm.py f16 ../f16-sim/build/f16_sim.fmu    # once per game, needs the FMU built
npm run dev                                              # or: npm run build, then serve dist/
GAME=f16 npm run build:single                            # dist-single/f16/index.html
npx vitest run
node tests/keys.mjs out.png                              # real key presses against the dev server
```

Port 8831 is the dev server the scripts expect (`GAMES_PORT` overrides it). Never 8765.

## Rules the games taught us

- Check every mesh with the signed volume test in `tests/aircraft.test.ts`. Three of the four games shipped inside-out parts from a first draft: a loft's winding depends on which way its sections run, and a mapping with a negative determinant mirrors what it moves.
- A float render target clamps nothing. With MSAA a varying is read outside its triangle where a triangle is edge-on or partly covered, so a value used in `exp`, or as a blend alpha, needs a `clamp` or `centroid`. The bloom now drops any pixel that is not finite and positive, but the source still shows as a wrong pixel.

## Not done

- On the F-16: no flaps, ground effect or anti-skid in the model, gear limits and steering assumed (`examples/f16/README.md`), and no gamepad button for the brakes.
- Touch controls.
- Device mapping beyond the standard gamepad layout: the desktop apps' per-device configuration did not carry over.
- Setup for the Cessna and the A109: their exports have start values only. Mass and the like need new tunables, and the start states are trimmed for one mass.
- More of the cars' setup: springs and dampers are four parameters a corner (one slider per axle needs a way to tie them), and wheelbase, weight distribution and the tyres are in the model's structure or tables. Tyre grip per axle could use the `mu_*` inputs.
- Lap records do not know the setup, so a tuned car's time counts against a stock one.
- Real frame rates on a discrete GPU. On the Arc integrated GPU at 1600x900 and top quality the flight games take about 21 ms of GPU time a frame and the cars 14 ms; the automatic quality step was not seen to react in a headless browser.
