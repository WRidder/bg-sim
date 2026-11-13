# Browser games

Island Sortie (F-16), Short Final (Cessna), Island Lift (A109) and Apex & Dust (race car and buggy), and the Microduck demo (below).

The bg-sim FMU apps as web games: the flight or vehicle model compiled to WebAssembly, the world drawn with three.js, no backend. A static file server is enough, and each game also builds into one HTML file that opens from disk.

```
npm ci
uv run build_fmu.py
npm run dev -- --host 127.0.0.1 --port 8831
```

Then open http://127.0.0.1:8831/.

`build_fmu.py` builds the models of the games, once after cloning and again when a model changes. For each of `f16`, `missile`, `cessna`, `a109`, `racecar` and `buggy` (name some to build only those) it exports the example's model from bg-sim (`examples/export_*.jl`, needs Julia), compiles and checks the FMU with gcc into `build/`, and has `build_wasm.py` turn it into `src/<game>/*.gen.ts`, the module the game imports. Neither `build/` nor the generated modules are committed. `uv run build_wasm.py <game> <fmu> [<name>.gen.ts]` does the last step alone, for an FMU built elsewhere.

The start lists of the F-16, the Cessna and the A109 (`src/<game>/starts.json`) are committed. They are trims from the design scripts of the examples; `uv run build_fmu.py --starts` writes them again, which is needed only when a model's trim changes.

- `npm run build` writes a static site to `dist/`.
- `npm run build:single` writes each game as one self-contained file: `dist-single/f16.html`, `cessna.html`, `a109.html` and `cars.html`. `node build_single.mjs f16` builds one.
- `npx vitest run` runs the unit tests and the scripted pilots.
- `node tests/keys.mjs out.png` flies with real key presses against the dev server.
- `node tests/weapons-keys.mjs out.png` selects Intercept, waits for the lock and fires.
- `node tests/weapons-perf.mjs` does the same with the frame rate uncapped and prints the frame times round each launch, the long frames and the shader programs built (`PERF_TIER=0` fixes the quality tier, `PERF_SIZE=1920x1080` the window).
- `node tests/f16-pad.mjs` flies the F-16 with a synthetic gamepad: sticks, bumpers, triggers and buttons.
- `node tests/cessna-keys.mjs`, `tests/a109-keys.mjs` and `tests/cars-keys.mjs` do the same for the other games.

## In the game

- `T` shows and hides the telemetry: gauges, plots, bars and readouts of what the model is doing.
- `Y` shows and hides the setup: a slider for each parameter the FMU exposes, in the F-16 and the cars. A change counts from the next start or restart (`R`), and is remembered in the browser. Stock puts everything back.
- Only one of the two is open at a time. `Shift+T` and `Shift+Y` move it to the other side, and the HUD makes room.

In the F-16, `G` works the gear and `B` or `Space` holds the brakes. Start on the runway or on final from the Start list, or come back from anywhere: a landing that stops on the airfield gets a marked sheet. Anywhere else, the ground is still a crash, and so is the runway with the gear up.

The F-16's Intercept mode puts up to three target drones in the play area. `Tab` or `N` selects one; the seeker cue builds a lock in about one second when the target is within 45 degrees of the nose and about 7 km. `M` fires the next AIM-9X (two per sortie), and `Shift+M` toggles the sound. The tactical scope at the top left shows the drones, the selected target and the lock; a hit removes the drone and a replacement enters after four seconds. A round in flight leaves smoke with a lit and a shaded edge, never thinner than about a pixel, and its motor shows as a point of light while it burns; the HUD puts a caret on each round with its seconds to go (amber and `LOST` once the seeker has lost the target), and the scope shows it as a dot. Not every shot can hit: a target far off the nose at short range, or one that crosses fast, is outside what the round can turn. A round that has lost the target for 7 seconds on end destroys itself, and so does any round after 30 seconds of flight: a small burst where it was.

The F-16 takes a gamepad with the browser's standard mapping, laid out as in Ace Combat 7 (expert handling): left stick pitch and roll (back is nose up), LB and RB (L1, R1) rudder, RT and LT (R2, L2) throttle up and down with LT also the wheel brakes, right stick to look round, B (Circle) fires, Y (Triangle) takes the next target, R3 changes the view, Start (Options) pauses, and Start or A (Cross) answers a menu. The gear, which that game does not have, is on D-pad down. A flight started from the pad is silent until a key or a click, because a browser does not let a pad button start the sound.

The Cessna has the same layout: left stick for the yoke (back is nose up), LB and RB rudder, RT and LT throttle up and down with LT also the wheel brakes, right stick to look round (the pilot's head in the cockpit), R3 for the view, Start to pause, and Start or A from a menu. Ace Combat has no flaps or trim, so they are on the D-pad: right and left for the flaps, up and down for the trim (up is nose down).

The A109 follows them, which is also how console games fly a helicopter: left stick cyclic, RT and LT lever up and down, LB and RB pedals, right stick to look round, A (Cross) as the space bar (brake to a hover with the aid, cyclic trim without), Y (Triangle) stability on and off, R3 for the view, Start to pause, and Start or A from a menu. A flight stick without the standard mapping keeps its twist for the pedals and its fourth axis for the lever.

The car games are laid out as in Gran Turismo: left stick or D-pad to steer, RT (R2) accelerator, LT (L2) brake, B (Circle) handbrake, Y (Triangle) reverse, LB (L1) look behind, RB (R1) change the view, right stick to look round, Start (Options) pause, A (Cross) to start from a menu or drive on from a pause, Back (Create) restart.

The Cessna and the A109 export only start values, so they have no setup until their exports expose parameters.

The design and its reasons are in `plan/WEB_APPS_PLAN.md`.

## Microduck

`microduck/`, code in `src/microduck/`. Drive Pollen Robotics' microduck (https://github.com/pollen-robotics/microduck) with a gamepad: the sticks make a command, the command and the robot's sensors make the 61-wide observation, the robot's own published walking policy (`velstand.onnx`) runs in the browser on ONNX Runtime Web, and its 14 actions become joint targets for the plant, 50 times a second. The policy loop (observation, scaling, the trained low-pass, the network choice, the command smoothing, the pad mapping) is re-implemented from the robot's Rust sources, each file citing the one it follows.

**The plant is the bg-sim model when `src/microduck/model.gen.ts` has been built, and a stand-in otherwise; the page says which.** The model is `examples/microduck/models/microduck-policy` (rigid joints, `XL330Rigid` servos, contacts at the soles and bumpers), exported as an FMU by `examples/export_microduck.jl` and compiled to WebAssembly by `build_wasm.py`. Nothing in it is checked against a real robot, and what velstand does on it is no evidence about the robot. The policy reads joint velocities one control tick old, as in training (`TRAINING_VELOCITY_LAG` in `src/microduck/loop.ts`; `DuckLoop`'s third argument, 0 for none). One 10 s run per command (`tests/microduck.test.ts`): at zero command it stands (the trunk 1 mm lower, tilt at most 2.31 deg, no drift); up to 0.24 m/s asked (half forward is 0.2 m/s) it shifts its weight and stands; from 0.28 m/s it walks, slower than asked and on a curve: at full forward (0.4 m/s asked) 1.85 m in 10 s, 0.195 m/s straight-line over the last 5 s, turning at -0.053 rad/s (heading -38 deg at the end), 19 and 19 lift-offs, tilt at most 5.7 deg, no fall. The FMU completes every step of the runs. If the plant does stop (a failed FMU step, or an output that is no longer a number), the banner turns red and says when (the step from t to t + 20 ms) and what the FMU returned, the policy is no longer run, the HUD says "stopped", and the duck is drawn in its last good state; R starts again. The differences from the simulator the policy was trained in are listed in `examples/microduck/README.md` (*Limits*): no backlash, a fixed 20 ms latency, an ideal supply, action scale 0.9, a flat floor, the contact and friction laws. The robot with the training's gear play, `microduck-policy-backlash`, exists in bg-sim, but its FMU is not usable in the page yet: it disagrees with bg-sim beyond the export gates, falls apart under velstand when walking (the FMU stops), and takes 10 to 19 ms of a 20 ms tick in Node (`examples/microduck/README.md`, *The XL330Backlash subsystem*).

The stand-in has no physics: the joints follow their targets through a 60 ms lag, the trunk is kept level and moved at the asked speed, or with `K` carried round the stance foot; the duck cannot fall. velstand stands calmly on it and steps when asked to move, but the steps do not take the trunk where the stick asks: it is far outside what it was trained on.

```
npm ci
npm run dev -- --host 127.0.0.1 --port 8831        # then http://127.0.0.1:8831/microduck/
uv run ../../examples/export_microduck_check.py --out <dir>   # export, build and check the FMU (about 8 min)
uv run build_wasm.py microduck <dir>/fmu/microduck_policy.fmu  # the page then uses it
node tests/microduck-keys.mjs out.png                # keys, a synthetic DualSense, the one-shots (stand-in)
node tests/microduck-fmu.mjs out.png                 # the page on the FMU: timing, standing, W held
npx vitest run tests/microduck.test.ts --silent=false   # with the FMU: velstand on it in Node, one JSON line per run
```

The velstand run in `tests/microduck.test.ts` reads `MICRODUCK_SECONDS` (run length, default 3), `MICRODUCK_COMMANDS` (forward sticks, comma-separated, 0..1, full stick 0.4 m/s; default `0,0.5,1`), `MICRODUCK_LAG` (joint-velocity lag in ticks, default 1), `MICRODUCK_TRACE` (a JSON file for the per-tick trace and the inputs sent) and `MICRODUCK_MODEL` (another generated model module in place of `src/microduck/model.gen.ts`, e.g. the gear-play robot: `export_microduck_check.py --model microduck-policy-backlash --out <dir>`, then `build_wasm.py microduck <dir>/fmu/microduck_policy_backlash.fmu backlash.gen.ts` and `MICRODUCK_MODEL=src/microduck/backlash.gen.ts`).

`?standin` keeps the stand-in even with an FMU built; `?carry=foot` starts it round the stance foot.

- **Gamepad.** Any pad the browser reports with the standard mapping; a PS5 DualSense does in Chrome and Edge, by USB or Bluetooth (press a button once for the browser to show it). The mapping is the robot's (`padd`): the D-pad picks what the sticks mean (left: walk, strafe, turn; up: head; right: head + walk; down: body + head), and the page starts in head + walk (left stick walks and turns, right stick moves the head), Cross sits and stands, Circle picks from the ground, L2/R2 open the beak, Options turns the policy on and off. Where the robot has no equivalent here the demo differs, and the screen says so: Square (held) rolls, L1/R1 kick, Create starts again, Triangle changes the camera. The camera follows the duck's heading and stays level; while the trunk is tipped more than 45 degrees (a roulade, a fall) it keeps the heading it had. Keyboard: W A S D left stick, arrows (and Q E) right stick, 1 to 4 the modes, Space, G, V, Z, X, B, Enter, R, C. H hides the controls, T the telemetry, P pauses.
- **Policies** are in `src/microduck/policies/`, at a pinned revision of https://huggingface.co/pollen-robotics/microduck-policies (Apache-2.0); their README has the revision, the hashes and how to fetch them again. The walk policy loads first; the sit-stand, ground pick, roulade and kicks follow in the background.
- **The duck** is drawn with Pollen Robotics' CAD parts from microduck_rl (`src/microduck/duck.glb`, 77k triangles, 2.4 MB: a node per body and the lower beak on the mouth servo's axis), written by `examples/microduck/design/build_visuals.py`. **These meshes are CC BY-NC-SA 4.0, non-commercial only** (`src/microduck/duck.glb.NOTICE`). If the file does not load, the page draws the procedural duck (shapes sized to the joints) and logs a warning.
- **ONNX Runtime Web** (`onnxruntime-web`, the plain WebAssembly backend, one thread, so no cross-origin isolation is needed) is imported only by this page and only when it starts: 75 kB of script and a 14.8 MB Wasm (3.9 MB gzipped), which no other game loads. A recurrent export (`h_in`/`c_in`) works too.
- **Single file: not supported.** A single-file build of it (`GAME=microduck npx vite build --mode single`) makes a 66 MB file (the runtime's Wasm and the six policies as base64), and in it the runtime does not even start (Vite's preload helper is missing once dynamic imports are inlined): the page runs with the policy off and says so. Serve `dist/` instead.

### The FMU the page expects

`src/microduck/fmuPlant.ts` names every variable in one table, `FMU_INTERFACE`; `examples/export_microduck.jl` exports these names, so the two agree. An export that lacks a required variable is refused with the names it lacks, and the page falls back to the stand-in. `<joint>` runs over the robot's 15 joints in its order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `neck_pitch`, `head_pitch`, `head_yaw`, `head_roll`, `mouth`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`.

| Role | Variables | Causality | Unit | Frame and meaning |
|---|---|---|---|---|
| Joint targets | `<joint>_target` (14, no mouth) | input | rad | Position target per joint, the robot's joint convention (MJCF hinge axes, home pose `DEFAULT_POSITION` in `robot.ts`). Held constant for 20 ms. |
| Gain (optional) | `kp` | input | 1 | The servos' Position P Gain register: 200 walking, 160 standing, set every tick. |
| Joint positions | `<joint>_q` (15) | output | rad | Same convention. |
| Joint velocities | `<joint>_qd` (15) | output | rad/s | |
| Trunk angular velocity | `trunk_wx`, `trunk_wy`, `trunk_wz` | output | rad/s | In the trunk frame (x forward, y left, z up, at the MJCF's `trunk_base`), as the IMU's gyro reads it. |
| Trunk orientation | `trunk_qw`, `trunk_qx`, `trunk_qy`, `trunk_qz` | output | 1 | Trunk Ã¢â€ â€™ world, w first. World: x forward at the start, y left, z up. |
| Trunk position | `trunk_x`, `trunk_y`, `trunk_z` | output | m | Origin of the trunk frame in the world; the floor is z = 0. |
| Projected gravity (optional) | `gravity_x`, `gravity_y`, `gravity_z` | output | 1 | Gravity's direction in the trunk frame, (0, 0, Ã¢Ë†â€™1) upright. Worked out from the quaternion when absent. |
| Foot contact (optional) | `left_foot_contact`, `right_foot_contact` | output | N | The sole's summed normal force; above 0.05 N counts as touching (`CONTACT_FORCE_N`: the model's smooth contact leaves about 1e-15 N on a lifted sole). Draws the footprints. |

- The mouth's three variables may be missing (the export has no mouth): it is in no policy, and the page then draws it where it was asked to be.
- Step: the FMU's own fixed step (ROS34PW2, 1 ms), which divides 20 ms; `engine/sim.ts` runs 20 steps after each control tick. Parameters (`v_bat`, `i_limit`) are left at the export's start values.
- Start: standing at the home pose with both soles loaded on the floor, at rest (`trunk_base` 0.1167 m up).
- 15 inputs and 43 outputs, well inside `fmu.ts`'s 256 values a call.
- The servos are XL330s in position control (BAM's model, 20 ms latency, 1.75 A limit), without the gear backlash the policies were trained with (the gear-play robot's FMU is not usable yet, see above).
- Cost (340 states, 41 of them differential; this machine with other jobs running, so the numbers move by about 20 %): 2.2 to 2.7 ms of Wasm per 20 ms tick in Node standing and 5.0 to 5.7 ms walking (the contact changes cost Newton iterations), 4.2 ms in headless Chromium with the page running and 5.0 ms mean after a few seconds of walking (real-time factor 0.11 to 0.29); natively 4.1 ms per tick in the build harness, standing. Single ticks reach tens of ms when the machine is busy; the page holds 50 ticks a second.
