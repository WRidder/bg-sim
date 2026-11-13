# Web games

The FMU-based apps as browser games, in `apps/web`. They began as desktop apps (`f16-sim`, `cessna-sim`, `a109-sim` and `car-sim`, on Panda3D and fmpy), which were removed once the games covered them; their FMU build step is now `apps/web/build_fmu.py`. They have nothing to do with the bg-sim editor: no backend, no Python, no Julia at run time. A static file server is enough, and each game also builds into one HTML file that opens from disk and can be mailed around.

## Decisions

| | Decision | Why |
|---|---|---|
| W1 | FMU compiled to WebAssembly with Zig (through `uv`) | The FMU's C sources need no change. Zero imports, 60 KB, about 2 Ã‚Âµs per step for the F-16. A 30 s manoeuvre matched the native FMU to 6e-12 m. |
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
| W14 | The microduck's policy runs on ONNX Runtime Web: the plain Wasm backend, one thread, imported by its page alone and only when it starts | No COOP/COEP needed (W3), and no other game's bundle grows. The runtime is 75 kB of script and a 14.8 MB Wasm (3.9 MB gzipped); a 61 Ã¢â€ â€™ 14 MLP takes about 1.5 ms a tick in a headless browser. |
| W15 | The microduck drives a `Plant`: the bg-sim FMU when `model.gen.ts` exists, otherwise a stand-in that says on screen that it is one | The FMU (`microduck-policy`, `examples/export_microduck.jl`) is generated and gitignored, so a fresh checkout has none. Its variable names sit in one table (`FMU_INTERFACE`), so wiring it is that table and `build_wasm.py`. The stand-in has no physics: joints lag their targets, the trunk is carried and kept level. A stopped FMU keeps its last good state on screen. |
| W16 | The policy loop is the robot's, re-implemented from its Rust sources and tested against their cases, not approximated | A wrong observation offset or a scaled previous action does not fail loudly; it gives a robot that walks badly (`duck-control/src/obs.rs`). |
| W17 | The F-16's AIM-9X is a second generated FMU (`missile.gen.ts`), one Wasm instance per wingtip; the drones are a small kinematic game layer | The weapon model already has a host-interface FMU (`aim9x-fmu`) with launch-relative target inputs. `build_wasm.py` compiles it unchanged, and separate `Fmu` instances give independent shots without a shared library. The drones are not worth 15 more states and a second flight model; the lock is a 45 deg, 7 km, one-second seeker cue in `targets.ts`. |

## Layout

```
apps/web/
  build_wasm.py        FMU to src/<game>/model.gen.ts (gitignored, regenerate after an FMU changes)
  shim/                the C glue between the FMU and JavaScript
  index.html           landing page
  f16/ cessna/ a109/ cars/ microduck/   one folder per page, each an index.html
  src/microduck/policies/    the robot's ONNX policies at a pinned revision (Apache-2.0, README beside them)
  src/engine/          shared by all: Stage, Sim, gates, camera, overlay, sound, input, effects,
                       side (the side windows), telemetry, tuning
  src/<game>/telemetry.ts   what the game's panel shows, and the labels of its setup
  src/f16/targets.ts missiles.ts weapons.ts   drones, lock, AIM-9X FMUs and procedural weapons
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
| Downforce 4 mÃ‚Â², or either anti-roll bar | 90 | 90 | 69 km/h |

At stock the motor gives 6.4 kN at the road below 147 km/h against about 6.7 kN of rear grip at rest, so full throttle leaves the rear tyres almost nothing to corner with. Half throttle does not spin. Traction control slip is the setting to reach for: it costs almost no acceleration, where 200 N m takes 0-100 km/h from 3.6 s to 5.4 s. Exposing these parameters changed nothing at stock: the old and new FMUs agree to 4e-8 on 14 s of driving, 1e-3 N on wheel load, and neither the method nor the step moved.

## Microduck

A robot demo rather than a game: Pollen Robotics' microduck (https://github.com/pollen-robotics/microduck) driven with a gamepad, its own learned policy run in the page. Pad Ã¢â€ â€™ command (the robot's `padd` mapping, `robotd`'s per-tick EMA) Ã¢â€ â€™ 61-wide observation Ã¢â€ â€™ ONNX Ã¢â€ â€™ home + 0.9 Ãƒâ€” action Ã¢â€ â€™ the trained low-pass (0.7 legs, 0.5 head) Ã¢â€ â€™ plant, at 50 Hz on plant time. The control tick awaits the inference, so plant and policy stay in lockstep; a slow frame drops time rather than ticks. It breaks two rules the games keep, knowingly: it carries binary assets under a licence (the policies, W5, and the duck's meshes: Pollen's CAD parts from microduck_rl in `duck.glb`, CC BY-NC-SA 4.0, non-commercial only, 2.4 MB, written by `examples/microduck/design/build_visuals.py`, with the procedural duck as fallback), and it has no single-file build (the runtime's Wasm alone is 14.8 MB).

What velstand does on the stand-in, measured: with a 25 ms joint lag it flails even at zero command, from about 40 ms it stands calmly (joints within 0.15 rad of home) and steps under any command, so the stand-in uses 60 ms. Carried round the stance foot, those steps do not take the trunk where the stick asks at any lag tried (40 to 120 ms); the default carries the trunk at the asked speed and says so. On the bg-sim FMU (`microduck-policy`: 340 states, 41 differential, ROS34PW2 at 1 ms, 1.12 MB of Wasm) the tick costs 2.2 to 2.7 ms standing and 5.0 to 5.7 ms walking in Node, and 4.2 to 5.0 ms in headless Chromium (machine loaded), so the plant runs 3.5 to 9 times faster than real time and the page holds 50 ticks a second. One 10 s run per command: velstand stands on it at zero command (tilt at most 2.24 deg, no drift), shifts its weight and stands at half forward (0.2 m/s asked), and walks at full forward (0.4 m/s asked): 1.82 m in 10 s, 0.24 m/s along the path, curving right to a heading of -56 deg, no fall. The loop now feeds the policy joint velocities one tick old, as training does (`TRAINING_VELOCITY_LAG`); with it, one run each: standing up to 0.24 m/s asked, walking from 0.28 m/s, at 0.4 m/s 1.85 m in 10 s, 0.195 m/s over the last 5 s, turning at -0.053 rad/s (heading -38 deg). The FMU used to stop 0.7 s after a forward command. The cause was not the export's static LU and not a lift-off: index reduction had kept 20 body-momentum components instead of the 14 joint rates (every `ISpatial` momentum preferred itself at the joint rate's priority, and MTK broke the tie by name), and recovering the rates from those momenta became singular; bg-sim's own solver failed at the same instant (E901). bg-sim now passes no `state = :prefer` on from a storage element in derivative causality (W201), so the tree keeps its joint angles and rates (41 states, minimal coordinates), and W219 reports a preferred variable index reduction drops. The page shows a stopped plant in red with the step and the FMU's status, stops running the policy and says "stopped" in the HUD. `apps/web/README.md` has the FMU interface and the numbers; nothing is checked against a real robot.

## Running

```
cd apps/web
npm ci
uv run build_fmu.py                                      # once: exports the FMUs and compiles them to Wasm
npm run dev                                              # or: npm run build, then serve dist/
npm run build:single                                     # dist-single/<game>.html, one file per game
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
- The microduck on the bg-sim model walks only from 0.28 m/s asked (0.7 of full stick) and then at about half the asked speed, on a curve; at half command it stands. The model differs from the training simulator (no backlash in the page's plant, fixed 20 ms latency, ideal supply, action scale 0.9 against 1.0, flat floor, contact law, friction smoothing; `examples/microduck/README.md`), and nothing is compared with a real robot. The robot with the training's gear play (`microduck-policy-backlash`, `XL330Backlash`: MuJoCo's play hinge and soft limit, checked against MuJoCo on the bench) runs in bg-sim, but its FMU fails the export gates against bg-sim (1 ms and 0.5 ms), falls apart under velstand when walking and costs 10 to 19 ms per tick in Node; open: why the fixed-step export goes wrong with the play.
- The microduck's emotions (yes, no, excited), sounds, the idle head and the pad's IMU head control: the robot's, not ported. Its fall detection is meaningless on the stand-in.
- Device mapping beyond the standard gamepad layout: the desktop apps' per-device configuration did not carry over.
- Setup for the Cessna and the A109: their exports have start values only. Mass and the like need new tunables, and the start states are trimmed for one mass.
- More of the cars' setup: springs and dampers are four parameters a corner (one slider per axle needs a way to tie them), and wheelbase, weight distribution and the tyres are in the model's structure or tables. Tyre grip per axle could use the `mu_*` inputs.
- Lap records do not know the setup, so a tuned car's time counts against a stock one.
- Real frame rates on a discrete GPU. On the Arc integrated GPU at 1600x900 and top quality the flight games take about 21 ms of GPU time a frame and the cars 14 ms; the automatic quality step was not seen to react in a headless browser.
