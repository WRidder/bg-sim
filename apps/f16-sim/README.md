# f16-sim: fly the bg-sim F-16 FMU

A small, standalone real-time flight simulator around the FMU that bg-sim exports from the
`f16-sim` model of the F-16 example (`examples/f16/models/f16-sim`: the Stevens & Lewis nonlinear
F-16 with a three-axis fly-by-wire). The FMU is the flight model; this app adds the pilot's inputs,
the world, the cameras and the HUD. Start airborne, fly, crash, press R.

Everything you see is generated here or comes from the example: the aircraft meshes are the
example's own (`examples/f16/meshes`, written by `examples/f16/design/make_meshes.py`), the
terrain, airfield, town, masts, wind turbines, clouds and rings are procedural.

## Why here, and why these libraries

* **`apps/f16-sim`**, not under `examples/`: creating a project from an example copies the whole
  example folder, and this app has its own virtual environment and build output. It is not part
  of the backend or the web app either: it only consumes the exported FMU. Its own
  `pyproject.toml` and `uv.lock` keep its dependencies (Panda3D, pygame-ce, fmpy) out of the
  bg-sim workspace.
* **fmpy** loads and steps the FMU (FMI 2.0 co-simulation) through ctypes.
* **Panda3D** (+ `panda3d-gltf`) renders: pip wheels for Windows, Linux and macOS (no engine to
  install), a glTF loader for the example's GLB meshes, offscreen buffers for headless runs and
  fixed-step video capture, and a 2D layer for the HUD, all driven from Python with one call per
  frame. A game engine with an editor (Godot, Unity) would need a second language and a plugin
  for the FMU; pygame/OpenGL by hand would need a loader, a scene graph and text rendering.
* **pygame-ce** (SDL2) reads joysticks, pedals and throttles. Only its joystick API is used: the
  window is Panda3D's, SDL runs with the dummy video driver and reads devices in the background.

## Install and build

Needs [uv](https://docs.astral.sh/uv/), Julia (`julia` on the PATH, as for bg-sim) and a C
compiler (gcc, as for the bg-sim FMU export).

    cd apps/f16-sim
    uv sync                      # the app's environment (Python 3.13)
    uv run build_fmu.py          # export + build the FMU, write the start list

`build_fmu.py` runs `julia --project=julia/BGSim examples/export_f16.jl <tmp> --no-reference`
(the export of `f16-sim` with the host interface), builds the FMU with
`bgsim_server.fmu_build` (the hot-path checks: no allocation after instantiate, no forbidden
symbol, the doStep timing), and writes into `build/` (not committed):

| file | content |
| --- | --- |
| `build/f16_sim.fmu` | the FMU (about 120 KB) |
| `build/build.json` | method, internal step, doStep cost, compiler |
| `build/starts.json` | the start conditions: level-flight trims from `examples/f16/design/simscen.trim_globals`, checked against the FMU's parameter ranges |

Rebuild after changing the model. `uv run build_fmu.py --skip-export` rewrites only the starts.

## Fly

    uv run f16sim                    # start condition 1; --start N picks another (0-based)
    uv run f16sim --rings            # with the ring course
    uv run f16sim --list-devices     # joysticks, pedals and throttles SDL sees

| key | action |
| --- | --- |
| arrows, or W/S and A/D | stick (spring back to the centre when released); down/S = pull |
| Q/E or Z/X | pedals (left/right) |
| PgUp/PgDn or +/- | throttle (0 idle, 77 % military, 100 % full afterburner) |
| C | chase view / cockpit (HUD) view |
| P | pause |
| R | reset to the current start condition |
| 1 .. 6 | reset to start condition N (the list is under F1) |
| G | ring course on/off (gates ahead of you; the next one pulses yellow, an amber circle on the HUD points to it) |
| T | turbulence on/off |
| L, V, Y | alpha/g limiter, velocity-vector roll, yaw damper on/off: FMU parameters, so the flight restarts |
| F1 | help |
| Esc | quit |

Start conditions (`build/starts.json`): cruise 500 ft/s at 10 000 ft, slow 300 ft/s at 10 000 ft,
700 ft/s at 5 000 ft, 900 ft/s at 2 000 ft, 600 ft/s at 20 000 ft, 350 ft/s at 2 000 ft, all trimmed
level, heading north, CG 0.35.

### Devices

`config/devices.toml` maps each control (pitch, roll, yaw, throttle) to one axis of one device,
matched by a part of the device name or by index, with inversion, dead zone, expo and the range
(`bipolar` for sticks and pedals, `unipolar` for a throttle). Rudder pedals are a separate device
(`[yaw] device = "pedal"` by default); a throttle quadrant too (`[throttle] device = "throttle"`).
A control without a matching device falls back to the keyboard. Use `--config other.toml` for
another set, `--no-joystick` to ignore all devices. Run `--list-devices` and move each axis to find
its number.

## The HUD

Cockpit view (conformal: one degree on the HUD is one degree of the view): pitch ladder (solid
above, dashed below the horizon) rolled with the bank, waterline, flight-path marker (where the
aircraft goes: alpha below and beta beside the nose), heading tape, CAS (kt) and altitude (ft)
boxes, vertical speed, Mach, g, alpha, beta, throttle and engine power (AB above military), bank.
The chase view keeps the numbers, the tape and the warnings.

Warnings (blinking): `DEPARTED` (the model's departure flag: alpha beyond -15..35 deg or |beta| >
15 deg), `PULL UP` (below 600 m above the terrain and less than 8 s to impact), `STALL` (alpha above
22 deg or CAS below 130 kt), `G LIMIT` / `ALPHA/G LIMIT` (the limiter cuts the pilot's command:
the model's `limiter_active`). `CRASHED` freezes the flight (the FMU's ground contact, or the
terrain's hills, which the FMU does not know); R resets. The top line shows the frame rate, the
real-time factor, the sim time, the view, the start condition, frames whose backlog was dropped
and the law switches that are off.

## Architecture

    devices.toml -> inputs.py (SDL joysticks, keyboard) --+
    scripts.py (scripted inputs) -------------------------+--> core.Simulation --> fmu.FlightModel --> FMU (fmpy)
                                                                   |   pacer, crash, rings, wind
    game.py (Panda3D ShowBase, one thread) <-----------------------+
       world.py (terrain, airfield, landmarks, sky, clouds, rings), aircraft.py (meshes, surfaces), hud.py

* **One thread, fixed steps.** The FMU is exported for a 5 ms communication step (RK4 with a 5 ms
  internal step: the export analysis picks both; one doStep costs about 4 µs in the C harness and
  about 25 µs through fmpy's ctypes). Each frame the pacer (`core.Pacer`) adds the frame time to
  an accumulator and runs the whole steps in it, keeping the remainder: at 60 fps that is 3 or 4
  steps a frame, 200 a second. Rendering and stepping are decoupled; a thread would add locking
  for no gain at this cost.
* **Bounded catch-up.** A frame later than 100 ms (a window drag, a slow machine) runs 20 steps
  and drops the rest of the backlog: the flight slows down instead of spiralling. The top line
  counts those frames (`behind`).
* **Interpolation.** The drawn position, attitude and surfaces are interpolated between the last
  two steps by the accumulator's fraction, so the picture moves evenly although the steps per
  frame alternate between 3 and 4 (the state shown lags the newest step by less than 5 ms).
* **Inputs** are held over each step (zero-order hold), as in the FMU's reference runs.
* **Coordinates.** The FMU gives NED position and the body-to-NED quaternion (body x forward, y
  right, z down). Panda3D's world is x east, y north, z up; the meshes are x forward, y left, z
  up. `aircraft.world_matrix` composes the three. The control surfaces turn about the hinge lines
  of the bg-sim scene (`examples/f16/scenes/f16-sim.sdf`).
* **Reset** re-instantiates the FMU: the trim (vt0, h0, alpha0, el0, thtl0), the CG and the law
  switches are FMU parameters that can only be set before initialisation.

## Tests

    uv run pytest                                     # core: pacer, input shaping, FMU in closed loop
    uv run f16sim --headless --seconds 10             # smoke: 10 s scripted, rendered offscreen
    uv run f16sim --quit-after 8                      # the real-time window for 8 s, with a summary

The FMU tests skip without `build/f16_sim.fmu`. They check that the trim holds level flight, that
right roll stick rolls and turns right with |beta| < 1 deg, that full aft stick sets the limiter
flag below 9.3 g and 26 deg alpha, that the quaternion matches the Euler angles and that a reset
restarts at the trim.

## Video

    uv run f16sim --record out.mp4 --script demo --fps 60 --ffmpeg <path to ffmpeg>

renders the `demo` script (`scripts.py`: a full-stick roll, a coordinated 60 deg turn, a hard pull
into the limiter in an 80 deg bank, chase and cockpit views) offscreen at fixed 1/60 s frames, at
twice the size, and pipes the frames to ffmpeg (H.264, yuv420p, downscaled). A folder instead of an
`.mp4` writes PNG frames.

## Landing gear and takeoff (not built)

The flight starts airborne; there is no gear. Taking off would need, in the bg-sim model:

* three gear legs as spring-damper struts between the airframe and the ground (compression from
  the leg's height above the terrain), with stroke limits and tyre contact forces: a normal force
  from the strut and a friction force from the slip of each wheel (rolling resistance, cornering
  stiffness, brake torque), switching cleanly on touchdown and lift-off (an event per wheel);
* inputs for nose-wheel steering (from the pedals below a speed) and the wheel brakes;
* weight-on-wheels logic in the control laws: on the ground the integrators held at zero, the
  pitch law in a direct stick-to-stabilator mode, the roll law off; switching at lift-off;
* the ground and the runway as terrain in the model (now the FMU knows only a flat ground at 0 m),
  plus the gear and flap animations and a landing-capable trim (low speed, high alpha) here.

## Limitations

* The aerodynamics are the book's low-speed NASA TP-1538 data (no Mach effects): above about
  Mach 0.6 it flies like the model, not like an F-16. Beyond alpha 45 deg or beta 30 deg the tables
  hold their edge values, so post-departure motion is qualitative.
* The hills are the host's: the FMU's ground is flat at 0 m (its `ground_contact` output), the
  host checks the terrain height itself. Wind and turbulence are a steady wind plus filtered
  noise, not a Dryden model.
* Changing the mass (an FMU parameter) without a new trim starts the flight out of trim.
* With vertical sync on, a window in the background may be throttled by the desktop compositor
  (seen here: 26 fps unfocused, 135 fps with `--vsync 0`); the pacer keeps the simulation in
  real time either way.
