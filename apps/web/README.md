# Browser games

Island Sortie (F-16), Short Final (Cessna), Island Lift (A109) and Apex & Dust (race car and buggy), and the Microduck demo (below).

The bg-sim FMU apps as web games: the flight or vehicle model compiled to WebAssembly, the world drawn with three.js, no backend. A static file server is enough, and each game also builds into one HTML file that opens from disk.

```
npm ci
uv run build_wasm.py f16 ../f16-sim/build/f16_sim.fmu
uv run build_wasm.py cessna ../cessna-sim/build/cessna_sim.fmu
uv run build_wasm.py a109 ../a109-sim/build/a109_sim.fmu
uv run build_wasm.py cars ../car-sim/build/racecar_sim.fmu racecar.gen.ts
uv run build_wasm.py cars ../car-sim/build/buggy_sim.fmu buggy.gen.ts
npm run dev -- --host 127.0.0.1 --port 8831
```

Then open http://127.0.0.1:8831/.

- `npm run build` writes a static site to `dist/`.
- `GAME=f16 npm run build:single` writes one self-contained file to `dist-single/f16/index.html`. Also for `cessna`, `a109` and `cars`.
- `npx vitest run` runs the unit tests and the scripted pilots.
- `node tests/keys.mjs out.png` flies with real key presses against the dev server.
- `node tests/cessna-keys.mjs`, `tests/a109-keys.mjs` and `tests/cars-keys.mjs` do the same for the other games.

## In the game

- `T` shows and hides the telemetry: gauges, plots, bars and readouts of what the model is doing.
- `Y` shows and hides the setup: a slider for each parameter the FMU exposes, in the F-16 and the cars. A change counts from the next start or restart (`R`), and is remembered in the browser. Stock puts everything back.
- Only one of the two is open at a time. `Shift+T` and `Shift+Y` move it to the other side, and the HUD makes room.

In the F-16, `G` works the gear and `B` or `Space` holds the brakes. Start on the runway or on final from the Start list, or come back from anywhere: a landing that stops on the airfield gets a marked sheet. Anywhere else, the ground is still a crash, and so is the runway with the gear up.

The Cessna and the A109 export only start values, so they have no setup until their exports expose parameters.

The design and its reasons are in `plan/WEB_APPS_PLAN.md`.

## Microduck

`microduck/`, code in `src/microduck/`. Drive Pollen Robotics' microduck (https://github.com/pollen-robotics/microduck) with a gamepad: the sticks make a command, the command and the robot's sensors make the 61-wide observation, the robot's own published walking policy (`velstand.onnx`) runs in the browser on ONNX Runtime Web, and its 14 actions become joint targets for the plant, 50 times a second. The policy loop (observation, scaling, the trained low-pass, the network choice, the command smoothing, the pad mapping) is re-implemented from the robot's Rust sources, each file citing the one it follows.

**The plant is the bg-sim model when `src/microduck/model.gen.ts` has been built, and a stand-in otherwise; the page says which.** The model is `examples/microduck/models/microduck-policy` (rigid joints, `XL330Rigid` servos, contacts at the soles and bumpers), exported as an FMU by `examples/export_microduck.jl` and compiled to WebAssembly by `build_wasm.py`. Nothing in it is checked against a real robot, and what velstand does on it is no evidence about the robot. One 10 s run per command (`tests/microduck.test.ts`): at zero command it stands (the trunk 1 mm lower, tilt at most 2.24 deg, no drift); at half forward (0.2 m/s asked) it shifts its weight and stands; at full forward (0.4 m/s asked) it walks, 1.82 m in 10 s at 0.24 m/s along the path, curving right (heading -56 deg at the end), 20 and 21 lift-offs, tilt at most 5 deg, no fall. The FMU completes every step of the three runs. If the plant does stop (a failed FMU step, or an output that is no longer a number), the banner turns red and says when (the step from t to t + 20 ms) and what the FMU returned, the policy is no longer run, the HUD says "stopped", and the duck is drawn in its last good state; R starts again. The differences from the simulator the policy was trained in are listed in `examples/microduck/README.md` (*Limits*): no backlash, a fixed 20 ms latency, an ideal supply, action scale 0.9, no joint-velocity lag, a flat floor, the contact and friction laws.

The stand-in has no physics: the joints follow their targets through a 60 ms lag, the trunk is kept level and moved at the asked speed, or with `K` carried round the stance foot; the duck cannot fall. velstand stands calmly on it and steps when asked to move, but the steps do not take the trunk where the stick asks: it is far outside what it was trained on.

```
npm ci
npm run dev -- --host 127.0.0.1 --port 8831        # then http://127.0.0.1:8831/microduck/
uv run ../../examples/export_microduck_check.py --out <dir>   # export, build and check the FMU (about 8 min)
uv run build_wasm.py microduck <dir>/fmu/microduck_policy.fmu  # the page then uses it
node tests/microduck-keys.mjs out.png                # keys, a synthetic DualSense, the one-shots (stand-in)
node tests/microduck-fmu.mjs out.png                 # the page on the FMU: timing, standing, W held
npx vitest run tests/microduck.test.ts               # with the FMU: velstand on it in Node (MICRODUCK_SECONDS, MICRODUCK_TRACE)
```

`?standin` keeps the stand-in even with an FMU built; `?carry=foot` starts it round the stance foot.

- **Gamepad.** Any pad the browser reports with the standard mapping; a PS5 DualSense does in Chrome and Edge, by USB or Bluetooth (press a button once for the browser to show it). The mapping is the robot's (`padd`): the D-pad picks what the sticks mean (left: walk, strafe, turn; up: head; right: head + walk; down: body + head), Cross sits and stands, Circle picks from the ground, L2/R2 open the beak, Options turns the policy on and off. Where the robot has no equivalent here the demo differs, and the screen says so: Square (held) rolls, L1/R1 kick, Create starts again, Triangle changes the camera. Keyboard: W A S D left stick, arrows (and Q E) right stick, 1 to 4 the modes, Space, G, V, Z, X, B, Enter, R, C. H hides the controls, T the telemetry, P pauses.
- **Policies** are in `src/microduck/policies/`, at a pinned revision of https://huggingface.co/pollen-robotics/microduck-policies (Apache-2.0); their README has the revision, the hashes and how to fetch them again. The walk policy loads first; the sit-stand, ground pick, roulade and kicks follow in the background.
- **ONNX Runtime Web** (`onnxruntime-web`, the plain WebAssembly backend, one thread, so no cross-origin isolation is needed) is imported only by this page and only when it starts: 75 kB of script and a 14.8 MB Wasm (3.9 MB gzipped), which no other game loads. A recurrent export (`h_in`/`c_in`) works too.
- **Single file: not supported.** `GAME=microduck npm run build:single` makes a 66 MB file (the runtime's Wasm and the six policies as base64), and in it the runtime does not even start (Vite's preload helper is missing once dynamic imports are inlined): the page runs with the policy off and says so. Serve `dist/` instead.

### The FMU the page expects

`src/microduck/fmuPlant.ts` names every variable in one table, `FMU_INTERFACE`; `examples/export_microduck.jl` exports these names, so the two agree. An export that lacks a required variable is refused with the names it lacks, and the page falls back to the stand-in. `<joint>` runs over the robot's 15 joints in its order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `neck_pitch`, `head_pitch`, `head_yaw`, `head_roll`, `mouth`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`.

| Role | Variables | Causality | Unit | Frame and meaning |
|---|---|---|---|---|
| Joint targets | `<joint>_target` (14, no mouth) | input | rad | Position target per joint, the robot's joint convention (MJCF hinge axes, home pose `DEFAULT_POSITION` in `robot.ts`). Held constant for 20 ms. |
| Gain (optional) | `kp` | input | 1 | The servos' Position P Gain register: 200 walking, 160 standing, set every tick. |
| Joint positions | `<joint>_q` (15) | output | rad | Same convention. |
| Joint velocities | `<joint>_qd` (15) | output | rad/s | |
| Trunk angular velocity | `trunk_wx`, `trunk_wy`, `trunk_wz` | output | rad/s | In the trunk frame (x forward, y left, z up, at the MJCF's `trunk_base`), as the IMU's gyro reads it. |
| Trunk orientation | `trunk_qw`, `trunk_qx`, `trunk_qy`, `trunk_qz` | output | 1 | Trunk → world, w first. World: x forward at the start, y left, z up. |
| Trunk position | `trunk_x`, `trunk_y`, `trunk_z` | output | m | Origin of the trunk frame in the world; the floor is z = 0. |
| Projected gravity (optional) | `gravity_x`, `gravity_y`, `gravity_z` | output | 1 | Gravity's direction in the trunk frame, (0, 0, −1) upright. Worked out from the quaternion when absent. |
| Foot contact (optional) | `left_foot_contact`, `right_foot_contact` | output | N | The sole's summed normal force; above 0.05 N counts as touching (`CONTACT_FORCE_N`: the model's smooth contact leaves about 1e-15 N on a lifted sole). Draws the footprints. |

- The mouth's three variables may be missing (the export has no mouth): it is in no policy, and the page then draws it where it was asked to be.
- Step: the FMU's own fixed step (ROS34PW2, 1 ms), which divides 20 ms; `engine/sim.ts` runs 20 steps after each control tick. Parameters (`v_bat`, `i_limit`) are left at the export's start values.
- Start: standing at the home pose with both soles loaded on the floor, at rest (`trunk_base` 0.1167 m up).
- 15 inputs and 43 outputs, well inside `fmu.ts`'s 256 values a call.
- The servos are XL330s in position control (BAM's model, 20 ms latency, 1.75 A limit), without the gear backlash the policies were trained with.
- Cost (340 states, 41 of them differential; this machine with other jobs running, so the numbers move by about 20 %): 2.2 to 2.7 ms of Wasm per 20 ms tick in Node standing and 5.0 to 5.7 ms walking (the contact changes cost Newton iterations), 4.2 ms in headless Chromium with the page running and 5.0 ms mean after a few seconds of walking (real-time factor 0.11 to 0.29); natively 4.1 ms per tick in the build harness, standing. Single ticks reach tens of ms when the machine is busy; the page holds 50 ticks a second.
