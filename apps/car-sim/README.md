# car-sim: drive the bg-sim race car and buggy FMUs

A small, standalone real-time driving simulator around the two FMUs that bg-sim exports from the
cars example (`examples/cars`): `racecar-sim`, an electric single-seater on a race track, and
`buggy-sim`, an electric four-wheel-drive buggy on rolling hills. Each FMU is the whole vehicle (a
3D multibond bond graph: chassis, four suspended corners with combined-slip tyres, steering, the
electric drivetrain with regenerative braking, the battery, the brakes, aerodynamics); this app
adds the driver's inputs, the world, the cameras and the dashboard. It follows `apps/f16-sim`.

The vehicle meshes are the example's own (`examples/cars/meshes`, written by
`examples/cars/design/make_scenes.py`); the track ribbons, the terrain, the trees and the sky are
procedural, from the same data the models use (`examples/cars/design/track.json`, `hills.json`).

## Install and build

Needs [uv](https://docs.astral.sh/uv/), Julia (`julia` on the PATH, as for bg-sim) and a C
compiler (gcc, as for the bg-sim FMU export).

    cd apps/car-sim
    uv sync                      # the app's environment (Python 3.13)
    uv run build_fmu.py          # export + build both FMUs, write the start lists

`build_fmu.py` runs `julia --project=julia/BGSim examples/export_cars.jl <tmp> racecar buggy
--no-reference` (the export of both `*-sim` models with the host interface), builds each FMU
with `bgsim_server.fmu_build` (the hot-path checks: no allocation after instantiate, no forbidden
symbol, the doStep timing) and writes into `build/` (not committed):

| file | content |
| --- | --- |
| `build/racecar_sim.fmu`, `build/buggy_sim.fmu` | the FMUs |
| `build/build.json` | per vehicle: method, internal step, doStep cost, compiler, parameter ranges |
| `build/starts.json` | the start menus: track positions (the chassis at its static ride height on z = 0) and hill positions (the highest ground under the four wheels plus the ride height), checked against the FMUs' parameter ranges |

`uv run build_fmu.py racecar` rebuilds one; `--skip-export` rewrites only the starts.

## Drive

    uv run carsim                        # the race car on the track
    uv run carsim --vehicle buggy        # the buggy on the hills
    uv run carsim --start 2              # another start (0-based; the list is under F1)
    uv run carsim --list-devices         # wheels, pedals and gamepads SDL sees

| key | action |
| --- | --- |
| left/right or A/D | steer (returns to the centre when released) |
| up or W | accelerator |
| down or S | brake (the motor regenerates first, the friction brakes add the rest) |
| space | handbrake (rear wheels) |
| V | forward / reverse (only below 1 m/s) |
| C | view: chase, cockpit, track side |
| P | pause |
| R | reset to the current start |
| 1 .. 5 | reset to start N |
| F1 | help |
| Esc | quit |

### Devices

`config/devices.toml` maps steer, throttle and brake to one axis each (a part of the device name
or its index, inversion, dead zone, expo, `bipolar` for the wheel, `unipolar` for pedals and
triggers) and the handbrake and reverse to buttons. The defaults suit an XInput gamepad (left
stick, triggers); a wheel's pedal set is a separate device whose name goes into `[throttle]` and
`[brake]`. The keyboard works next to a bound device: per control the input touched last wins (a
held key takes over, the device takes back when its axis moves), so an idle device cannot lock
out the arrow keys. `--no-joystick` ignores all devices.

## The dashboard

Bottom left: the speed (km/h), D or R, the throttle, brake and steering bars. Bottom right, the
electric drive: per motor its speed (rpm), torque (N m) and mechanical power (kW, negative while
regenerating), the battery voltage, current and power (`REGEN` while it charges), a bar of the
motor torque against its present limit (the torque limit up to the base speed, the power limit
above; to the left while regenerating) and the state of charge. Top right on the track: the lap
number, the current, last and best lap times (the timer starts at the first crossing of the
start/finish line), the surface under each wheel. Top left: frame rate, real-time factor, sim time,
vehicle, view, start, frames whose backlog was dropped. Warnings: rolled over, the edge of the map.

## The worlds

* **Race track** (`racecar`): the 1735 m circuit of `examples/cars/design/track.py`, 12 m of
  asphalt, red and white kerbs (1.4 m) in the corners, asphalt run-off (14 m) on their outside,
  grass elsewhere, the chequered start/finish line under a gantry, grandstands and trees. The FMU's
  ground is a flat plane at z = 0 and all of it is drawn exactly there: the layers are separated
  by Panda3D depth offsets (grass 0, pavement 1, paint 2), not by height, so the tyres sit on the
  drawn surface and nothing z-fights at a distance. Before every step the host sets each wheel's
  friction scale (the FMU inputs `mu_fl` .. `mu_rr`) from the surface under that wheel's contact
  point (`<w>_xc`, `<w>_yc`): asphalt 1.0, run-off 0.95, kerb 0.85, grass 0.6.
* **Hills** (`buggy`): the height field `h(x, y) = sum a_i cos(kx_i x + ky_i y + ph_i)` of
  `hills.json`, the parameters of the buggy model's four `TerrainSurface` elements (a test checks
  that the table and the model agree). The drawn grid has 2 m cells over the drivable 800 m square
  and its vertices lie exactly on the function the tyres roll on (between vertices within 2 cm;
  the shortest wavelength is 25 m); a 10 m ring continues it to the horizon. Flags mark the demo
  loop.

## Architecture

    devices.toml -> inputs.py (SDL joysticks, keyboard, mixer) --+
    scripts.py (pure-pursuit driver) ----------------------------+--> core.Simulation --> fmu.VehicleModel --> FMU (fmpy)
                                                                       |  pacer, friction per wheel, laps, warnings
    game.py (Panda3D ShowBase, one thread) <---------------------------+
       world.py (track or hills, sky), vehicle.py (meshes, poses), hud.py

* **One thread, fixed steps.** The FMUs are exported for a 5 ms communication step (200 Hz; the
  export analysis picks the integrator and the internal step, `build/build.json`). Each frame the
  pacer adds the frame time to an accumulator and runs the whole steps in it, keeping the
  remainder; a frame later than 100 ms runs 20 steps and drops the rest of the backlog (`behind`).
* **Interpolation.** The chassis, carrier and wheel poses are interpolated between the last two
  steps (positions linearly, quaternions by nlerp, spin angles linearly).
* **Inputs** are held over each step (zero-order hold), as in the FMUs' reference runs.
* **Coordinates.** The FMU's world is x, y horizontal and z up, the same as Panda3D's. The body
  mesh is in the chassis frame (x forward, y left, z up), the wheel and hub meshes in the carrier
  frame of each corner (z the axle); the wheel is the carrier turned by its spin angle.
* **Reset** re-instantiates the FMU: the start pose (`x0`, `y0`, `z0`, `yaw0`) and the charge
  (`soc0`) are FMU parameters set before initialisation.

## Tests

    uv run pytest                                          # core, track, hills, the FMUs in closed loop
    uv run carsim --headless --script smoke                # 10 s scripted race car, rendered offscreen
    uv run carsim --headless --script smoke-buggy          # the same for the buggy
    uv run carsim --quit-after 8                           # the real-time window for 8 s, with a summary

The FMU tests skip without `build/`. They check the race car at rest on the grid, the launch at the
torque limit, regeneration when braking (negative motor torque and battery current, the charge
rising), reverse only at rest, the friction scale on the grass, the buggy's contact points on the
drawn height field and its climb with both motors driving.

## Video

    uv run carsim --record out.mp4 --script demo --ffmpeg <path to ffmpeg>
    uv run carsim --record buggy.mp4 --script demo-buggy --ffmpeg <path to ffmpeg>

renders a script offscreen at fixed 1/60 s frames, at twice the size, and pipes them to ffmpeg. The
scripted driver (`scripts.py`) follows the track's centre line (or an ellipse over the hills) with
pure pursuit and a speed profile from the curvature ahead. A folder instead of an `.mp4` writes PNG
frames.

## Limitations

* The tyre model has no aligning moment, camber thrust or relaxation length; the suspension is a
  slider per corner (no camber or toe change with travel). On the hills the tyre uses the tangent
  plane below the wheel centre.
* The motor losses are the rotor drag and the battery resistance only; there is no thermal model
  and no inverter current limit apart from the torque and power limits. The traction control uses
  the true vehicle speed.
* Collisions: there are no barriers or obstacles, and nothing stops a car from leaving the map
  (the hills continue analytically; the host warns at the edge of the drawn square).
