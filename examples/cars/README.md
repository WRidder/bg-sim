# Cars

An electric race car and an electric four-wheel-drive buggy as full 3D multibond bond graphs: suspension, combined-slip tyres, Ackermann steering, electric drive with regenerative braking, battery, brakes and aero, checked against independent vehicle-dynamics references and exported as the FMUs of a driving simulator.

Both vehicles are the same bond graph (`design/car.py`) with different parameter tables
(`design/vehicles.py`):

| | race car | buggy |
| --- | --- | --- |
| mass | 724 kg (sprung 620 kg) | 908 kg (sprung 750 kg) |
| wheelbase, track | 2.80 m, 1.60 / 1.55 m | 2.70 m, 1.75 m |
| suspension | stiff, short travel (45 mm bump, 60 mm droop), anti-roll bars front and rear | soft, long travel (200 mm bump, 170 mm droop), front anti-roll bar |
| tyres | slicks, R0 0.33 m, mu 1.65 / 1.60 | off-road, R0 0.42 m, mu 1.00 / 0.95 |
| steering | Ackermann, 20 deg at full lock | Ackermann, 30 deg |
| drive | one 300 N m / 260 kW motor, 7:1 to an open rear differential with a viscous LSD | one 150 N m / 60 kW motor per axle, 10:1, open differentials with viscous couplings |
| battery | 100 Ah, 340..403 V, 60 mOhm | 60 Ah, 80 mOhm |
| aero | ClA 2.6 (42 % front), CdA 0.95 | CdA 1.30, no downforce |

## The bond graph

Chassis: a `RigidBody3D` at the sprung CG on a `PoseIntegrator3D`, with the aerodynamic wrench
(drag and downforce, split front/rear by the aero balance) from the project block `Aero`. Each
corner is a subsystem (`FL`, `FR`, `RL`, `RR`):

* `Mount` (a fixed transform to the corner) and `Susp`, a `Prismatic3D` along the chassis z: the
  suspension travel is its drive port on a 1-junction with the `Strut` (a C for the spring with
  its preload and bump/rebound stops, an R for the asymmetric damper) and the anti-roll bar
  (a C between the two corners of an axle);
* front corners: an `Upright` body and a `Revolute3D` about the kingpin, turned by a stiff
  steering servo (`SteerServo`) to the angle of the Ackermann linkage (`Steering`);
* the `Carrier` (wheel and hub, `RigidBody3D`) with the axle along its z, the `Wheel` spin
  (`Rotor3D`) and the stdlib `Tyre` on the ground (`ContactSurface`, or `TerrainSurface` on the
  hills): the wheel spin is a 1-junction with the tyre's spin port, the friction `Brake` and, on
  a driven wheel, the half shaft.

The electric driveline is a 1-D bond graph between the battery and the four spin junctions:

    TractionBattery -- 0 (DC bus) -- TractionMachine (modulated TF, u = tau / V_bus)
      -- 1 (rotor: I J_m, R drag, speed sensor) -- elastic shaft (C, R) -- 1
      -- TF (reduction 1/n) -- 0 (differential carrier) -- TF 2 -- 1 (wheel spin), x 2

* `TractionBattery`: open-circuit voltage linear in the state of charge, internal resistance R,
  SOC = charge / capacity (outputs `soc`, `ocv`, `V`, `I`, `P`).
* `TractionMachine`: the inverter and the motor as one power-conserving modulated transformer
  (`shaft.e = u dc.e`, `dc.f = -u shaft.f`) between the electrical bus and the rotor. Its losses
  are the rotor drag and the battery resistance.
* `EMotorControl`: the torque command and the modulus. The envelope is the torque limit up to the
  base speed P_max / T_max, the power limit above it and a soft speed limit. The accelerator asks
  a share of it; traction control fades the torque out when the driven wheels run more than 10 %
  (plus 1 m/s) faster than the vehicle. The modulus `u = tau / V_bus` uses the bus voltage at the
  commanded power, the root of `V^2 - ocv V + R P = 0`, so the rotor torque is exactly the command
  with no algebraic loop.
* Regenerative braking: `BrakeSystem` turns the pedal into the friction torque per wheel and the
  demand per axle. The axle's motor takes what it can of that demand (its regen torque and power
  limits, nothing above 98 % charge, fading out below 30 rad/s), and the friction brakes take the
  rest. The battery current reverses and the charge rises.
* The buggy has one motor per axle on the same bus (each motor's power enters the other's
  bus-voltage root); there is no centre differential.

## Models

| model | what it shows |
| --- | --- |
| `racecar-settle`, `buggy-settle` | Dropped from 3 cm above the static ride height: heave and pitch settle to the static corner loads. |
| `racecar-skidpad` | 25 m/s with three left steering levels (0.04, 0.08, 0.12 of full lock), the speed held by a PI on the accelerator: yaw rate, body slip, the four tyre loads. |
| `racecar-launch` | Full accelerator from rest for 12 s: the motor at its torque limit up to the base speed, then at its power limit. Sliders for both limits. |
| `racecar-straight` | 10 s flat out at the top speed, then the accelerator released and the brake pedal at 50 %: regeneration within the motor's limits, the friction brakes for the rest. Sliders for the pedal and the regen power. |
| `buggy-grade` | 5 m/s up a 25 % grade (14 deg) with both motors. |
| `buggy-hills` | 30 s over rolling hills (an analytic height field, wavelengths 25..140 m) with a few steering inputs. A second `TerrainSurface` checks that the FL contact point lies on the terrain. Slider for the speed. |
| `racecar-sim`, `buggy-sim` | The FMU sources of `apps/car-sim` (below). In bg-sim a short test drive feeds the inputs. |

Every model has a 3D scene (`design/make_scenes.py`): the car stays near the origin and the
ground moves under it (block `CarView`). There are four scenes: a test pad with a 2 km straight,
the race track (kerbs, run-off, start/finish line), a 25 % ramp and the hills.

## Validation (design/reference.py, independent scipy models)

The references share only the parameter tables and the steady-state tyre formulas
(`design/tyre.py`, a numpy rewrite of the stdlib `Tyre`) with the bond graph.

| model | reference | bg-sim / reference |
| --- | --- | --- |
| `racecar-settle` | 7-DOF ride model (heave, roll, pitch, four wheel hops, asymmetric dampers, bump stops) | CG height 0.29672 / 0.29674 m at 0.15 s, static loads 1527 / 1527 N front, 2024 / 2024 N rear |
| `buggy-settle` | the same | CG height 0.76464 / 0.76466 m at 0.15 s, static loads 2004 / 2004 N front, 2450 / 2450 N rear |
| `racecar-skidpad` | nonlinear four-wheel steady state (load transfer, open differential with coupling, aero) | yaw rate 0.11565 / 0.11582, 0.22704 / 0.22742, 0.32935 / 0.32993 rad/s; body slip within 0.4 %; tyre loads within 0.7 % |
| `racecar-launch` | 1-D longitudinal model (wheel spins, rotor, elastic shaft, battery, the same envelope and traction control) | 300 N m to the base speed; at 12 s 63.92 / 63.84 m/s, 179.2 / 179.4 N m, SOC 0.88042 / 0.88036 |
| `racecar-straight` | the same, from its top speed (260 kW: 73.66 m/s, 265 km/h) | top speed 73.89 / 73.66 m/s; regen 130.7 / 131.0 N m at 10.25 s (power limit), 185.7 / 185.7 N m from 11.5 s (whole demand); speed at 14 s 15.77 / 15.67 m/s |
| `buggy-grade` | climb equilibrium on 25 % (slips per axle, load transfer on the slope) | accelerator 0.3238 / 0.3237, motor torque 48.56 / 48.56 N m, tyre loads 1642 / 1649 N front, 2679 / 2672 N rear, battery 30.84 / 30.82 A |
| `buggy-hills` | the terrain itself (a second `TerrainSurface` at the contact point) | contact on the terrain to 0.07 mm after the drop, every tyre load above 870 N |

The launch is 0.2 m/s behind the reference after the first 0.1 s. The model's tyre has a
contact-patch deflection, so the traction control briefly sees the wheels spin up before the car
moves, while the 1-D reference uses steady-state slip. After that the two accelerate alike.

## The FMUs

`racecar-sim` and `buggy-sim` carry the host interface as export markers:

* Inputs (`ExportInputPass`): `steer` (-1 full left .. +1 full right), `throttle`, `brake`,
  `handbrake` (0..1), `reverse` (0/1) and `mu_fl` .. `mu_rr`, the friction scale under each
  tyre (the host sets it from the surface it draws).
* Outputs (`ExportOutput`): the chassis pose (`chassis_px` .. `chassis_qz`); per corner the
  carrier pose, the spin angle and speed, the tyre load, slip, slip angle, the suspension travel
  and the contact point (`fl_xc`, `fl_yc`, `fl_zc`, ...); the road-wheel angles; the speed, the
  accelerations, the attitude, yaw rate and body slip; per motor its speed, torque, limit, power
  and regen torque; the battery's state of charge, voltage, current and power.
* FMU parameters with ranges: the start pose `x0`, `y0`, `z0`, `yaw0` and charge `soc0`
  (globals whose expressions set the start state), the motor limits and the brake torques.

    uv run examples/export_cars_check.py       # export, references, build, fmpy comparison

FMU_TABLE

`apps/car-sim` is the host (Panda3D, fmpy, wheel/pedal/gamepad input): see its README.

## Limitations

* The tyre has no aligning moment, camber thrust or relaxation length beyond the contact-patch
  deflection. The suspension is a slider per corner, so there is no camber or toe change with
  travel and no roll centre height: the lateral load transfer goes through the springs and the
  anti-roll bars only.
* Motor losses are only the rotor drag and the battery resistance. There is no thermal model or
  inverter current limit, and the traction control reads the true vehicle speed.
* On the hills the tyre uses the tangent plane below the wheel centre (exact for long waves; the
  shortest wavelength is 25 m).
* Three workarounds for bg-sim's event handling, each of which otherwise stops a run at the
  event limit (W206):
  * While the motor covers the whole brake demand, the friction share of that axle is zero up
    to rounding. `BrakeSystem` adds a floor of 1 mN (`f_min`) to every clamping force, so the
    `max(f_n, 0)` kink of the stdlib `Brake` does not fire at every sign flip of the noise.
  * Pedal changes are ramps (0.055 s in `racecar-straight`, 0.205 s in the sims) whose ends lie
    between the 10 ms output instants: a time kink a few ulps from an output instant
    (10.0 + 0.05 against 10.049999...) traps the root finder there.
  * The motor and brake blocks do not clamp the pedals, so a released pedal resting at exactly 0
    does not sit on a clamp corner. The pedals must stay within 0..1; the host and the stimuli
    guarantee that.

## Files

| file | content |
| --- | --- |
| `design/vehicles.py` | the two parameter tables and derived quantities (static loads, preloads, ride heights) |
| `design/tyre.py` | the steady-state tyre formulas of the stdlib `Tyre` in numpy |
| `design/reference.py` | the references, written to `design/design.json` |
| `design/bg.py`, `design/car.py` | the diagram builder and the vehicle bond graph |
| `design/track.py` | the race track's centre line (a periodic spline through control points), written to `design/track.json` |
| `design/build_model.py` | writes the models, `bgsim.project.json`, `design/hills.json` and `expected.json` |
| `design/make_scenes.py` | writes `meshes/*.glb` and `scenes/*.sdf` |
| `library/` | `TractionBattery`, `TractionMachine`, `EMotorControl`, `BrakeSystem`, `Strut`, `AntiRollBar`, `Steering`, `SteerServo`, `Aero`, `Telemetry`, `SpeedHold`, `CarView`, `PoseSplit`, `XYPose` |
| `../export_cars.jl`, `../export_cars_check.py` | the two FMUs: export, references and the fmpy acceptance |

    uv run examples/cars/design/track.py
    uv run examples/cars/design/reference.py
    uv run examples/cars/design/build_model.py
    uv run examples/cars/design/make_scenes.py
    uv run examples/run_checks.py --only cars
    uv run examples/export_cars_check.py
