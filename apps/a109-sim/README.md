# a109-sim: fly the bg-sim A109 helicopter FMU

A small, standalone real-time helicopter simulator around the FMU that bg-sim exports from the
`a109-sim` model of the A109 example (`examples/a109/models/a109-sim`). That model is the
Heffley and Mnich minimum-complexity A109 (NASA CR-177476), built in bg-sim as a bond graph:

* a multibond airframe on a tricycle gear of three stdlib `ContactPoint`s;
* the main and tail rotor as modulated sources on that airframe;
* the drivetrain with its governor on a rotational bond graph;
* the rigging from the sticks to the blade angles, and a SCAS.

The FMU is the whole helicopter, including the gear. This app adds the pilot's controls, the
world, the cameras and the instrument panel. You start on the helipad with the rotor at 100 %,
pull the collective, hover, fly a circuit and land on the "H". If you crash, press R.

The helicopter is drawn from the example's own scene (`examples/a109/scenes/a109-sim.sdf`): the
cabin, the boom, the fins, the gear, the main rotor tilted with the flapping, and the tail rotor.
Everything else is procedural:

* the heliport: two pads with the "H", edge lights and markings, an apron, a hangar, the tower,
  a fuel truck, a parked helicopter, a windsock and rows of marker posts;
* fine grass around the pads (it repeats every 6 m, so a drift in the hover shows);
* the countryside, the roads, the village, the trees and the clouds of `apps/cessna-sim`.

## Why here, and why these libraries

The app sits in `apps/a109-sim`, not under `examples/`, for the same reasons as
`apps/cessna-sim`: it has its own virtual environment and build output, and it consumes only the
exported FMU. Its `pyproject.toml` and `uv.lock` keep Panda3D, pygame-ce and fmpy out of the
bg-sim workspace.

* **fmpy** loads and steps the FMU (FMI 2.0 co-simulation) through ctypes.
* **Panda3D** renders. It has offscreen buffers for headless runs and video capture, and a 2D
  layer for the panel, all driven from Python.
* **pygame-ce** (SDL2) reads the cyclic stick, the collective lever (a throttle axis) and the
  pedals. Only its joystick API is used: the window is Panda3D's, and SDL runs with the dummy
  video driver.

## Install and build

You need [uv](https://docs.astral.sh/uv/), Julia (`julia` on the PATH, as for bg-sim) and a C
compiler (gcc, as for the bg-sim FMU export).

    cd apps/a109-sim
    uv sync                      # the app's environment (Python 3.13)
    uv run build_fmu.py          # export and build the FMU, write the start list

`build_fmu.py` does three things:

1. It runs `julia --project=julia/BGSim apps/a109-sim/export_fmu.jl <tmp>`. That script flattens
   `a109-sim`, applies the host interface (`BGSim.Export.host_inputs`) and exports it with the
   17 start parameters as tunables.
2. It builds the FMU with `bgsim_server.fmu_build`. That checks the hot path (no allocation after
   instantiate, no forbidden symbol) and times doStep.
3. It writes these files into `build/` (not committed):

| file | content |
| --- | --- |
| `build/a109_sim.fmu` | the FMU (115 KB): RK4 at 1.25 ms, 4 substeps in the 5 ms communication step |
| `build/build.json` | method, internal step, doStep cost, compiler |
| `build/starts.json` | the start conditions, checked against the FMU's parameter ranges |

The airborne starts are trims of the example's Python mirror (`examples/a109/design/heli_si.py`),
turned and placed in the world. The parked start is the gear's static deflection, then 6 s of
settling in the FMU. The 15 m hover start is compared with the model's own default start.

On this machine the FMU's doStep takes 11.8 µs on average and 101 µs at most. That is 0.24 % of
real time, with 0 allocations after instantiate.

The integrator is RK4 at 1.25 ms, set by hand (`--method`, `--dt`). The automatic step analysis
would size the step at the model's default start (a hover), not over the whole flight envelope.

Rebuild after changing the model. `uv run build_fmu.py --skip-export` rewrites only the starts.

## Fly

    uv run a109sim                 # on the helipad; --start N picks another start (0-based)
    uv run a109sim --list-devices  # the joysticks, throttles and pedals SDL sees

| key | action |
| --- | --- |
| arrows, or W/S and A/D | cyclic (springs back to its trim when released); up or W is forward |
| Q/E or Z/X | pedals (left/right; spring back) |
| PgUp/PgDn or +/- | collective up/down (stays where it is put) |
| Space | force trim: the cyclic's centre moves to where the stick is now |
| Backspace | trim release: the cyclic trim back to the centre |
| Home/End or [ / ] | cyclic trim forward/aft |
| H | SCAS on/off |
| C | view: chase, cockpit, ground |
| I | panel on/off |
| T | turbulence on/off |
| Shift+W | wind: calm, 10 kt from the west, 15 kt from the north |
| P | pause |
| R | reset to the current start |
| 1 .. 8 | reset to start N |
| F1 | help |
| Esc | quit |

The eight starts (`build/starts.json`):

1. on helipad H, parked: the rotor at 100 %, the collective down;
2. a hover at 3 m over the pad (in ground effect);
3. a hover at 15 m over the pad (the model's default start);
4. short final: 30 kt, 30 m, 300 m south of the pad;
5. final approach: 40 kt, 60 m, 900 m south of the pad;
6. downwind: 60 kt, 100 m, heading south;
7. cruise: 100 kt, 300 m, heading east;
8. short final: 20 kt, 15 m, 150 m south of the pad (the demo's approach).

Each airborne start is trimmed with the collective alone: with the SCAS on, the centred cyclic
and pedals hold the trim's attitude.

### The SCAS

The SCAS is the model's (`examples/a109/library/Scas.jl`), and the FMU input `scas` switches it.

* **On** (the default; the panel shows `SCAS ON`), the cyclic commands attitude:
  * full forward is 15 deg nose down from the speed's trim attitude;
  * full right is 30 deg of bank;
  * the pedals command a yaw rate of 30 deg/s, with turn coordination above 10 to 20 m/s.
* **Weight on the wheels:** the SCAS fades out, so on the pad the rigging is direct
  (`STANDBY: on the gear`). It engages as the gear unloads, so you can lift off with the SCAS on.
* **Off** (H), the cyclic and pedals move the blade angles directly through the rigging. The bare
  helicopter is unstable, as the real one is: you have to fly it.

### Devices

`config/devices.toml` maps each control to one axis of one device: the cyclic (longitudinal and
lateral), the pedals and the collective. A device is matched by a part of its name or by index.
Each mapping has an inversion, a dead zone, an expo and a range: `bipolar` for the cyclic and
pedals, `unipolar` for the collective (the axis' -1..1 becomes 0..1).

The defaults expect:

* a joystick as the cyclic (axes 1 and 0);
* the joystick's throttle lever (axis 2) as the collective, with lever forward as collective up;
* rudder pedals named `pedal` (axis 2).

Without pedals, put the stick's twist axis under `[pedals]`.

Joystick buttons for the SCAS, the force trim, the trim release and the view can be bound in
`[buttons]`. After a force trim with a joystick, the cyclic holds the trimmed position until the
stick comes back near its centre. From then on it works about the new centre.

A control without a matching device falls back to the keyboard. The keyboard also works next to a
bound device: per control, the input touched last wins. The bindings are printed at start. Use
`--config other.toml` for another set and `--no-joystick` to ignore all devices.

## The cameras

* **chase**: behind and above the helicopter. It follows the heading with a lag and tilts with
  the flight path.
* **cockpit**: the right seat, looking down 14 deg so that the ground ahead shows in a hover.
* **ground**: an observer at the corner of the apron. The view zooms so that the helicopter
  stays about a third of the picture high.

## The panel

The panel has three parts:

* **Top row:**
  * airspeed (kt), with the green arc to 150 kt, the yellow arc and the red line at 168 kt
    (VNE);
  * the attitude indicator;
  * the altimeter (ft above the field, at sea level);
  * the torque, in % of the 740 hp take-off rating at 100 % NR.
* **Bottom row:**
  * rotor speed (NR, % of 385 rpm), with the green arc 95 to 100 % and the yellow and red
    limits;
  * the heading card;
  * vertical speed (×100 fpm);
  * the **hover display**: the velocity over the ground in body axes, forward up and right
    right, with 10 kt at the rim. The dot is green below 1 kt, and the number is the ground
    speed in knots.
* **Right side:**
  * the collective lever, with the hover mark (`HOV`, about 60 %) and its position in %;
  * the cyclic position in its box, with the trim's centre as a ring;
  * the pedals;
  * the SCAS state;
  * a data block: radar altitude of the lowest wheel, ground speed and track, weight on wheels
    and the three wheel loads, engine power and rotor thrust, the blade angles (collective,
    B1, A1, tail rotor) and the flapping (a1, b1).

Warnings:

* `LOW ROTOR RPM` below 95 % NR, and `HIGH ROTOR RPM` above 106 %;
* `TORQUE LIMIT`: within 5 hp of the 740 hp the governor can give;
* `VNE`: above 168 kt;
* `VRS: SINK AT LOW SPEED`: sinking faster than 3 m/s below 25 kt, the vortex-ring corner. The
  model has no vortex-ring state. Its inflow balance does not lose thrust there.
* `PULL UP`: below 60 m and sinking faster than 4 m/s;
* `BANK ON THE GROUND`: more than 8 deg with weight on the wheels.

Touchdowns are rated from the sink rate over the last 0.1 s: smooth below 0.5 m/s, firm, hard,
and very hard above 2 m/s. The touchdown line also gives the drift over the ground and the
distance from the centre of the "H". The pad's touchdown area has a radius of 12 m.

A crash freezes the flight; R resets. These things count as a crash:

* a main-rotor tip, the tail-rotor tip, the tail, the nose or the belly below the ground;
* a touchdown sinking faster than 3 m/s, or a wheel load above 2.5 times the weight (the gear
  collapses);
* the rotor below 80 % NR (a stall the governor cannot recover);
* more than 25 deg of bank with weight on the wheels (dynamic rollover);
* a non-finite FMU state.

## The FMU interface

Inputs (held over each 5 ms step):

| FMI name | meaning |
| --- | --- |
| `collective` | 0 full down .. 1 full up |
| `cyclic_lon` | -1 full aft .. +1 full forward |
| `cyclic_lat` | -1 full left .. +1 full right |
| `pedals` | -1 full left .. +1 full right |
| `wind_n`, `wind_e`, `wind_d` | the wind, towards north, east and down (m/s) |
| `scas` | 1 on (engaged in the air), 0 off (the rigging direct) |

Outputs:

| FMI name | meaning |
| --- | --- |
| `north_m`, `east_m`, `alt_m` | the CG's position; the ground is at 0 |
| `phi_deg`, `theta_deg`, `psi_deg` | bank, pitch and heading |
| `p_dps`, `q_dps`, `r_dps` | body rates (FRD) |
| `u_mps`, `v_mps`, `w_mps` | body velocities over the ground (FRD) |
| `vs_mps`, `tas_mps`, `kts`, `beta_deg` | climb rate, true airspeed, airspeed in knots, sideslip |
| `rotor_pct`, `power_hp`, `thrust_n` | rotor speed (% of 385 rpm), engine power, rotor thrust |
| `a1_deg`, `b1_deg` | the main rotor's flapping (aft, right) |
| `theta0_deg`, `B1_deg`, `A1_deg`, `theta_tr_deg` | the blade angles after the rigging and the SCAS |
| `fn_nose`, `fn_left`, `fn_right` | the normal forces of the three wheels (N) |
| `wow` | weight on wheels, 0 airborne .. 1 above 20 % of the weight |

The start parameters (set before initialisation, `build/starts.json`):

| FMI name | meaning |
| --- | --- |
| `qw0`, `qx0`, `qy0`, `qz0` | the orientation of the principal frame (a quaternion) |
| `x0`, `y0`, `z0` | the position (x north, y west, z up; m) |
| `Pwx0`, `Pwy0`, `Pwz0`, `Pvx0`, `Pvy0`, `Pvz0` | the body momentum in the principal frame: angular, then linear |
| `a10`, `b10` | the flapping (rad) |
| `Lrot0` | the rotor's angular momentum (N m s) |
| `xi0` | the governor's integrator (N m) |

## Architecture

    devices.toml -> inputs.py (SDL joysticks, keyboard, Mixer, CyclicTrim) --+
    pilot.py (scripted pilot, scripts) --------------------------------------+--> core.Simulation --> fmu.FlightModel --> FMU (fmpy)
                                                                              |  pacer, wind, crash, touchdowns
    game.py (Panda3D ShowBase, one thread) <----------------------------------+
       world.py (heliport, countryside, sky), heli.py (the SDF's solids, rotors), panel.py

* **One thread, fixed steps.** Each frame the pacer (`core.Pacer`) runs the whole 5 ms steps in
  the frame time and keeps the remainder: at 60 fps that is 3 or 4 steps a frame. A frame later
  than 100 ms runs 20 steps and drops the rest, so the flight slows down instead of spiralling.
  The drawn state is interpolated between the last two steps.
* **Inputs** are held over each step (zero-order hold), as in the FMU's reference runs.
* **Wind** is a host input of the FMU. `core.Turbulence` makes a steady wind that falls off near
  the ground (a 1/7 power law below 100 m), plus first-order filtered gusts.
* **Coordinates.** The FMU's world is x north, y west, z up, with the ground at z = 0. The body
  is x forward, y left, z up. Panda3D's world is x east, y north, z up, and `heli.world_matrix`
  maps one into the other. The main rotor is tilted by the shaft and by the FMU's flapping. The
  rotors turn at a tenth of their speed, so they do not strobe.
* **Reset** re-instantiates the FMU. The start state (pose, momenta, flapping, rotor momentum,
  governor) is FMU parameters, which can only be set before initialisation.
* **The scripted pilot** (`pilot.py`) flies with the SCAS on and the same inputs as you do. It
  covers:
  * the lift-off and the hover check over the pad;
  * the transition with the climb;
  * a rectangular circuit at 100 m and 60 kt, with the turns anticipated;
  * the approach on a 7 deg path, with the speed bleeding off as sqrt(2 a d);
  * the hover over the pad and the vertical descent onto the gear.

  The headless runs, the tests and the video use it.

## Tests

    uv run pytest                                  # pacer, inputs, trim, wind, FMU in closed loop, a headless run
    uv run a109sim --headless --script smoke       # 40 s from the pad: lift-off, hover, transition
    uv run a109sim --headless --script landing     # the approach from the short final and the landing
    uv run a109sim --headless --script circuit     # the whole circuit: pad to pad (touchdown at about 200 s)
    uv run a109sim --quit-after 8                  # the real-time window for 8 s, with a summary

The FMU tests skip without `build/a109_sim.fmu`. They check these things:

* the FMU loads and a step runs;
* the parked start rests on its gear;
* the scripted pilot lifts off without counting a touchdown;
* the hover starts hold hands off;
* a reset restarts at the start;
* the SCAS switch changes the blade angles;
* the scripted landing touches down smoothly on the pad;
* a collective dumped in a hover, and a roll into the ground, are crashes;
* the whole app runs the `smoke` script headless (Panda3D offscreen).

Rendered offscreen, the scripts run at about 1.5 times real time. The `circuit` script ends in a
smooth touchdown (0.16 m/s) 1 m from the centre of the "H".

## Video

    uv run a109sim --record out.mp4 --script demo --ffmpeg <path to ffmpeg>

This renders the `demo` script offscreen at fixed 1/30 s frames, at twice the size, and pipes the
frames to ffmpeg (H.264, downscaled to 1280x720). The script lasts 58 s and has two legs:

1. from the pad: the lift-off, the hover check and the transition;
2. from the 20 kt short final: the approach, the hover over the pad and the landing.

Both legs switch between the chase, cockpit and ground views. A folder instead of an `.mp4`
writes PNG frames.

## Limitations

* The flight model is the example's: the minimum-complexity model, without blade dynamics,
  vortex-ring state, retreating-blade stall or fuel burn. `examples/a109/README.md` gives the
  validation and the assumptions.
* The ground is flat at z = 0 everywhere. The hills are scenery beyond the heliport, and the FMU
  does not know them. The crash check only looks at the airframe points against z = 0.
* The gear's tyres are stdlib contact points with Coulomb friction smoothed at 2 cm/s, and there
  are no wheel brakes. The parked helicopter's heading therefore creeps slowly, about 0.1 deg/s.
* The engine always runs: there is no start-up, no engine failure and no autorotation.
* The wind is a steady wind plus filtered noise, not a Dryden model.
