# cessna-sim: fly the bg-sim Cessna 172P FMU

A small, standalone real-time flight simulator around the FMU that bg-sim exports from the
`cessna-sim` model of the Cessna example (`examples/cessna/models/cessna-sim`). That model is a
Cessna 172P from JSBSim's c172p data, built as a bond graph: a multibond airframe on three gear
legs, the engine and propeller on a rotational bond graph, and an autopilot. The propeller's
low-speed thrust and power are fitted to the POH's static rpm, climb and take-off (see the
example's README), so its sea-level climb and take-off roll are close to the handbook's. The
FMU is the whole aircraft, including the landing gear. This app adds the pilot's controls, the
world, the cameras and the instrument panel. You start on the runway, take off, fly the circuit
and land. If you crash, press R.

The aircraft meshes are the example's own (`examples/cessna/meshes`, written by
`examples/cessna/design/make_meshes.py`). Everything else is procedural:

* the airfield: runway 36/18, taxiway, apron, hangars, tower, windsock and parked aircraft;
* the fields, hills, village, roads, lake, trees, mast, wind turbines and clouds.

## Why here, and why these libraries

* **`apps/cessna-sim`**, not under `examples/`. Creating a project from an example copies the
  whole example folder, and this app has its own virtual environment and build output. It
  consumes only the exported FMU. Its own `pyproject.toml` and `uv.lock` keep Panda3D,
  pygame-ce and fmpy out of the bg-sim workspace. The layout is that of `apps/f16-sim`.
* **fmpy** loads and steps the FMU (FMI 2.0 co-simulation) through ctypes.
* **Panda3D** (with `panda3d-gltf`) renders. It installs from pip wheels and loads the glTF
  meshes. It also has offscreen buffers for headless runs and video capture, and a 2D layer for
  the panel, all driven from Python.
* **pygame-ce** (SDL2) reads the yoke, the rudder pedals with their toe brakes, and the throttle
  quadrant. Only its joystick API is used: the window is Panda3D's, and SDL runs with the dummy
  video driver.

## Install and build

You need [uv](https://docs.astral.sh/uv/), Julia (`julia` on the PATH, as for bg-sim) and a C
compiler (gcc, as for the bg-sim FMU export).

    cd apps/cessna-sim
    uv sync                      # the app's environment (Python 3.13)
    uv run build_fmu.py          # export and build the FMU, write the start list

`build_fmu.py` does three things:

1. It runs `julia --project=julia/BGSim examples/export_cessna.jl <tmp> --no-reference`, the
   export of `cessna-sim` with the host interface.
2. It builds the FMU with `bgsim_server.fmu_build`, which checks the hot path (no allocation
   after instantiate, no forbidden symbol) and times doStep.
3. It writes these files into `build/` (not committed):

| file | content |
| --- | --- |
| `build/cessna_sim.fmu` | the FMU (about 120 KB): RK4 at 2.5 ms inside the 5 ms communication step, doStep about 10 µs |
| `build/build.json` | method, internal step, doStep cost, compiler |
| `build/starts.json` | the start conditions, checked against the FMU's parameter ranges. The runway one is the gear equilibrium of `examples/cessna/design/perf.py`; the airborne ones are trims of `design/c172_lin.py`, turned and placed in the world |

Rebuild after changing the model. `uv run build_fmu.py --skip-export` rewrites only the starts.

## Fly

    uv run cessnasim                 # on runway 36; --start N picks another start (0-based)
    uv run cessnasim --list-devices  # joysticks, pedals and throttles SDL sees

| key | action |
| --- | --- |
| arrows, or W/S and A/D | yoke (springs back to the centre when released); down or S pulls |
| Q/E or Z/X | rudder pedals, which also steer the nose wheel on the ground |
| PgUp/PgDn or +/- | throttle |
| M/N | mixture rich/lean |
| F/V | flaps one detent down/up (0, 10, 20, 30 deg) |
| Home/End or [ / ] | elevator trim nose down/up |
| B, or `,` and `.` | both toe brakes, or the left and right brake |
| H | autopilot roll: off, then wing leveller, then heading hold (the bug set to the heading now) |
| J | autopilot altitude hold on/off (at the altitude now) |
| K/L | heading bug -5/+5 deg |
| C | view: chase, cockpit, tower |
| I | panel on/off |
| T | turbulence on/off |
| Shift+W | wind: calm, 10 kt from the west (a crosswind on runway 36), 15 kt from the north |
| P | pause |
| R | reset to the current start |
| 1 .. 6 | reset to start N |
| F1 | help |
| Esc | quit |

The six starts (`build/starts.json`):

1. runway 36, engine idle, flaps 10;
2. left downwind, 1000 ft, 90 KIAS;
3. final for runway 36, 2 nm out, flaps 30, 65 KIAS on a 3 deg glide path;
4. short final, 300 ft;
5. cruise at 4500 ft and 100 KIAS, heading east;
6. a full-throttle climb at 76 KIAS.

The airborne starts are trimmed with throttle and elevator trim. The yoke and pedals start
centred, so a slow roll-off has to be held, as in the real airplane.

The autopilot is the model's own `C172Autopilot`. It adds to the yoke with limited authority, so
you can always override it.

### Devices

`config/devices.toml` maps each control to one axis of one device: the pitch, roll, yaw, throttle
and mixture axes and the two toe brakes. A device is matched by a part of its name or by index.
Each mapping has an inversion, a dead zone, an expo and a range: `bipolar` for the yoke and
pedals, `unipolar` for levers and brakes.

The defaults expect:

* a yoke as the first joystick;
* rudder pedals named `pedal`, with the toe brakes on axes 0 and 1;
* a throttle quadrant named `throttle`.

Joystick buttons for the flaps, the trim, the brakes and the autopilot can be bound in `[buttons]`.

A control without a matching device falls back to the keyboard. The keyboard also works next to a
bound device: per control, the input touched last wins. The bindings are printed at start. Use
`--config other.toml` for another set and `--no-joystick` to ignore all devices.

## The panel

The panel has three parts:

* **The six-pack:**
  * the airspeed indicator, with the white, green and yellow arcs of the POH;
  * the attitude indicator;
  * the altimeter (ft; the runway is at sea level);
  * the turn coordinator, with the slip ball;
  * the heading indicator, with the autopilot's bug;
  * the vertical speed indicator.
* **Gauges and levers:**
  * the tachometer;
  * the flap position against the detents;
  * the trim, throttle and mixture levers;
  * the autopilot mode.
* **The engine line:** manifold pressure, power, fuel flow, thrust, angle of attack and ground
  speed.

Warnings:

* `STALL`: the model's stall flag, or alpha above 15.5 deg in the air;
* `PULL UP`: below 400 ft and sinking faster than 1500 fpm;
* `ON THE GRASS`;
* `OVERSPEED`: above 2700 rpm.

Touchdowns are rated from the sink rate over the last 0.1 s: smooth below 200 fpm, firm, hard,
and very hard above 800 fpm. The touchdown line also gives the distance past the threshold and
the offset from the centre line.

A crash freezes the flight; R resets. Three things count as a crash:

* a wing tip, the tail or the propeller below the ground;
* a wheel load above 3.5 g (the gear collapses);
* a non-finite FMU state.

## Architecture

    devices.toml -> inputs.py (SDL joysticks, keyboard, Mixer) --+
    pilot.py (scripted circuit pilot, scripts) ------------------+--> core.Simulation --> fmu.FlightModel --> FMU (fmpy)
                                                                     |  pacer, wind, crash, touchdowns
    game.py (Panda3D ShowBase, one thread) <-------------------------+
       world.py (airfield, countryside, sky), aircraft.py (meshes, surfaces, propeller), panel.py

* **One thread, fixed steps.** Each frame the pacer (`core.Pacer`) runs the whole 5 ms steps in
  the frame time and keeps the remainder: at 60 fps that is 3 or 4 steps a frame. A frame later
  than 100 ms runs 20 steps and drops the rest, so the flight slows down instead of spiralling.
  The drawn state is interpolated between the last two steps.
* **Inputs** are held over each step (zero-order hold), as in the FMU's reference runs.
* **Wind** is a host input of the FMU. `core.Turbulence` makes a steady wind that falls off near
  the ground (a 1/7 power law below 100 m), plus first-order filtered gusts.
* **Coordinates.** The FMU's world is x north, y west, z up, with the runway surface at z = 0. Its
  quaternion turns the body (x forward, y left, z up) into that world. Panda3D's world is x east,
  y north, z up. `aircraft.world_matrix` maps one into the other. The control surfaces turn about
  the hinge lines of the bg-sim scene (`examples/cessna/scenes/cessna-sim.sdf`). The propeller
  turns with the FMU's `prop_angle` and gets a blurred disc at speed.
* **Reset** re-instantiates the FMU. The start state (pose, momenta, rotor momentum, manifold
  pressure, flap angle, strut compressions) is FMU parameters, which can only be set before
  initialisation.
* **The scripted pilot** (`pilot.py`) flies with the same inputs as you do. It covers the take-off
  roll with centre-line hold, the rotation and the climb, and a left-hand circuit with the
  autopilot on downwind. It also flies the base turn, the final on the glide path, the flare and
  the braked landing roll. The headless runs, the tests and the video use it.

## Tests

    uv run pytest                                     # pacer, inputs, wind, FMU in closed loop
    uv run cessnasim --headless --script smoke        # 40 s take-off, rendered offscreen
    uv run cessnasim --headless --script landing      # the approach from 2 nm and the landing
    uv run cessnasim --headless --script circuit      # the whole circuit: take-off to landing (440 s)
    uv run cessnasim --quit-after 8                   # the real-time window for 8 s, with a summary

The FMU tests skip without `build/cessna_sim.fmu`. They check these things:

* the runway start rests on its gear, with the wheel loads summing to the weight;
* full power takes off, and the lift-off is not counted as a touchdown;
* the airborne trims hold speed and altitude;
* a reset restarts at the start;
* the FMU's quaternion matches its Euler angles;
* the approach from 2 nm ends in a smooth or firm touchdown on the runway;
* a dive into the ground is detected as a crash.

The `circuit` script runs 440 s in about 10 s of wall time without rendering. With rendering it
runs at about 2 times real time.

## Video

    uv run cessnasim --record out.mp4 --script demo --ffmpeg <path to ffmpeg>

This renders the `demo` script offscreen at fixed 1/30 s frames, at twice the size, and pipes the
frames to ffmpeg (H.264, downscaled to 1280x720). The script has two legs:

1. the take-off from runway 36, the climb and a climbing left turn;
2. from the 2 nm final start, the approach, the flare, the touchdown and the landing roll.

Both legs switch between the chase, tower and cockpit views. A folder instead of an `.mp4` writes
PNG frames.

## Limitations

* The flight model is the example's. Climb and take-off are weaker than the POH, from the c172p
  propeller's low static thrust at the rated 160 hp. There is no p-factor and no fuel burn.
  `examples/cessna/README.md` gives the validation and the assumptions.
* The ground is flat at z = 0 everywhere. The hills are scenery beyond the airfield, and the FMU
  does not know them. The crash check only looks at the airframe points against z = 0.
* The engine always runs: there is no starter, magneto or carburettor icing, and idle is
  throttle 0.
* The wind is a steady wind plus filtered noise, not a Dryden model.
