@@ figures racecar-settle
{
  "diagram": {"kind": "diagram", "model": "racecar-settle"},
  "scene": {"kind": "scene", "model": "racecar-settle", "t": 1.0},
  "run": {
    "kind": "plot", "model": "racecar-settle", "xlim": [0, 1.5],
    "rows": [
      {"ylabel": "CG height [m]", "series": [{"signal": "Pose/pz", "label": "Pose/pz"}], "hlines": [{"y": 0.3, "label": "static ride height 0.30 m"}], "legend": true},
      {"ylabel": "tyre load [kN]", "series": [{"signal": "FL/Tyre/Fz", "label": "FL", "scale": 0.001}, {"signal": "RL/Tyre/Fz", "label": "RL", "scale": 0.001}], "hlines": [{"y": 1.527, "label": "static FL"}, {"y": 2.0242, "label": "static RL"}], "legend": true}
    ]
  }
}
@@ page racecar-settle overview - | Overview
# Race car: drop test

The electric race car of the **cars** example, released 3 cm above its static ride height onto flat ground. Heave and pitch ring down on the springs, the asymmetric dampers and the tyres, and the four tyre loads settle on the static corner loads.

![The model canvas|900](@fig:diagram)

The canvas is the whole vehicle: the chassis [Chassis](block:Chassis) on its pose integrator, the four corners [FL](block:FL), [FR](block:FR), [RL](block:RL), [RR](block:RR), instances of the library subsystems `RacecarFrontCorner` and `RacecarRearCorner` (suspension slider, strut, carrier, wheel spin, [Tyre](block:FL/Tyre), brake), the steering, the brake system, the aero wrench and the electric driveline from the [Battery](block:Battery) through the motor [MachineR](block:MachineR) to the rear differential.

![3D view at t = 1 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page racecar-settle results overview | Results
# Results

![CG height and tyre loads|900](@fig:run)

The reference is a 7-DOF ride model (heave, roll, pitch and four wheel hops with the same springs, asymmetric dampers, bump stops and tyre springs) integrated with scipy in `design/reference.py`. The CG height [Pose/pz](signal:Pose/pz) agrees to 0.02 mm at every sample from 0.05 to 3 s, the tyre loads to 0.5 % from 0.3 s on and the static loads (1527 N front, 2024 N rear per wheel) to 0.1 %.
@@ figures racecar-skidpad
{
  "diagram": {"kind": "diagram", "model": "racecar-skidpad"},
  "scene": {"kind": "scene", "model": "racecar-skidpad", "t": 18.0},
  "run": {
    "kind": "plot", "model": "racecar-skidpad", "xlim": [0, 19],
    "rows": [
      {"ylabel": "yaw rate [rad/s]", "series": [{"signal": "Telemetry/r", "label": "Telemetry/r"}], "hlines": [{"y": 0.11582, "label": "reference"}, {"y": 0.2274}, {"y": 0.32990}], "legend": true},
      {"ylabel": "tyre load [kN]", "series": [{"signal": "FL/Tyre/Fz", "label": "FL", "scale": 0.001}, {"signal": "FR/Tyre/Fz", "label": "FR", "scale": 0.001}, {"signal": "RL/Tyre/Fz", "label": "RL", "scale": 0.001}, {"signal": "RR/Tyre/Fz", "label": "RR", "scale": 0.001}], "legend": true},
      {"ylabel": "body slip [deg]", "series": [{"signal": "Telemetry/beta", "label": "Telemetry/beta", "scale": 57.29577951308232}]}
    ]
  }
}
@@ page racecar-skidpad overview - | Overview
# Race car: skid pad

25 m/s with three left steering levels (0.04, 0.08 and 0.12 of full lock, held for 6 s each). A PI on the accelerator ([Throttle](block:Throttle)) holds the speed. The lateral acceleration reaches 0.85 g at the last level; the loads move to the right-hand tyres and the rear motor drives through the open differential with its viscous limited-slip coupling.

![The model canvas|900](@fig:diagram)

## What to try

- Plot [Telemetry/ay](signal:Telemetry/ay), [Telemetry/r](signal:Telemetry/r) and the slip angles `FL/Tyre/alpha` .. `RR/Tyre/alpha`.
- Change `values` of [Steer](block:Steer) for more lock: near 0.16 the rear tyres saturate first and the car spins.

![3D view at t = 18 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page racecar-skidpad results overview | Results
# Results

![Yaw rate, tyre loads and body slip|900](@fig:run)

The reference is a nonlinear four-wheel steady state (`design/reference.py`): combined-slip tyres with the same formulas, lateral and longitudinal load transfer from a static solve of the suspension, aero, the open differential with its viscous coupling, the free-rolling front wheels with rolling resistance, the unsprung masses' centripetal forces and the wheels' gyroscopic moment.

| steer | yaw rate [rad/s] | body slip [mrad] | lateral acceleration [g] |
| --- | --- | --- | --- |
| 0.04 | 0.11565 / 0.11582 | -11.28 / -11.32 | 0.298 / 0.295 |
| 0.08 | 0.22704 / 0.22742 | -23.26 / -23.35 | 0.585 / 0.579 |
| 0.12 | 0.32935 / 0.32993 | -36.47 / -36.62 | 0.848 / 0.840 |

Each cell is bg-sim / reference.

The four tyre loads agree to 0.7 %. The linear bicycle model (understeer gradient -0.25 deg/g at 25 m/s) predicts 0.35 g at the first level; the four-wheel model is lower because the cornering stiffness falls with load transfer.
@@ figures racecar-launch
{
  "diagram": {"kind": "diagram", "model": "racecar-launch"},
  "scene": {"kind": "scene", "model": "racecar-launch", "t": 4.0},
  "run": {
    "kind": "plot", "model": "racecar-launch", "xlim": [0, 12],
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "Telemetry/speed", "label": "Telemetry/speed"}]},
      {"ylabel": "motor torque [N m]", "series": [{"signal": "MotorR/tau", "label": "MotorR/tau"}, {"signal": "MotorR/tlim", "label": "limit MotorR/tlim", "style": "--"}], "legend": true},
      {"ylabel": "battery", "series": [{"signal": "Battery/I", "label": "current [100 A]", "scale": 0.01}, {"signal": "Battery/soc", "label": "SOC [-]"}], "legend": true}
    ]
  }
}
@@ page racecar-launch overview - | Overview
# Race car: launch

Full accelerator from rest for 12 s. The rear motor ([MotorR](block:MotorR), [MachineR](block:MachineR)) gives its 300 N m torque limit up to the base speed $P_{max}/T_{max} = 867$ rad/s (8280 rpm, 38 m/s, reached after about 5 s), then its 260 kW power limit. The traction control trims the torque in the first 0.1 s while the slicks take up the load. The battery current rises to 740 A and the state of charge falls by 2 % in 12 s.

![The model canvas|900](@fig:diagram)

## What to try

- Move the torque and power limits on the dashboard (globals `T_max` and `P_max_kw`).
- Plot [MotorR/tc](signal:MotorR/tc), the traction-control factor, with `RL/Tyre/kappa`.

![3D view at t = 4 s|600](@fig:scene)

Continue with [the electric drive](page:drive) and [the results](page:results).
@@ page racecar-launch drive overview | The electric drive
# The electric drive

    Battery -- 0 (bus) -- MachineR (modulated TF) -- 1 (rotor) -- elastic shaft -- 1 -- TF 1/7 -- 0 (differential) -- TF 2 -- RL, RR spin

| block | role |
| --- | --- |
| [Battery](block:Battery) | `TractionBattery`: open-circuit voltage from 340 V (empty) to 403 V (full), 60 mOhm, 100 Ah; the state is the charge |
| [MachineR](block:MachineR) | `TractionMachine`: the inverter and the motor as a power-conserving modulated transformer, rotor torque $u\,V$, bus current $u\,\omega$ |
| [MotorR](block:MotorR) | `EMotorControl`: the torque envelope, the accelerator, traction control, regeneration, and the modulus $u = \tau / V_{bus}$ |
| [RotorR](block:RotorR), [RotorRJ](block:RotorRJ), [RotorRDrag](block:RotorRDrag), [RotorRSpeed](block:RotorRSpeed) | the rotor's 1-junction, its inertia, its drag and the speed sensor the controller reads |
| [ShaftR](block:ShaftR) | the elastic drive shaft (1500 N m/rad, 8 N m s/rad) |
| [ReductionR](block:ReductionR), [DiffR](block:DiffR), [LsdR](block:LsdR) | the 7:1 reduction, the open differential (a 0-junction) and its viscous coupling |

The envelope is

$$T_{lim}(\omega) = \min\!\Big(T_{max},\ \frac{P_{max}}{|\omega|}\Big)\,\tfrac12\Big(1 - \tanh\frac{|\omega| - \omega_{max}}{\omega_c}\Big)$$

and the bus voltage at the commanded power $P = \tau\omega$ is the root of $V^2 - V_{oc} V + R P = 0$, so $u = \tau/V$ gives exactly the commanded torque with no algebraic loop.
@@ page racecar-launch results overview | Results
# Results

![Speed, motor torque and battery|900](@fig:run)

The reference is a 1-D longitudinal model (`design/reference.py`): the vehicle, the front and rear wheel spins, the rotor and the elastic shaft, the battery charge, the same envelope, traction control and tyre formulas with a quasi-static load transfer, integrated with scipy.

| t [s] | speed bg-sim / reference [m/s] | motor torque [N m] | SOC |
| --- | --- | --- | --- |
| 2 | 16.03 / 16.25 | 300 / 300 | 0.89920 / 0.89918 |
| 4 | 31.54 / 31.74 | 300 / 300 | 0.89670 / 0.89665 |
| 8 | 53.73 / 53.76 | 213.0 / 212.9 | 0.88864 / 0.88858 |
| 12 | 63.92 / 63.84 | 179.2 / 179.4 | 0.88042 / 0.88036 |

The 0.2 m/s lag comes from the first 0.1 s: the model's tyres have a contact-patch deflection, so the wheels spin up briefly before the car moves and the traction control cuts in. The 1-D reference uses steady-state slip. After that, both accelerate at 7.75 m/s² at the torque limit and follow the same power-limited curve.
@@ figures racecar-straight
{
  "diagram": {"kind": "diagram", "model": "racecar-straight"},
  "scene": {"kind": "scene", "model": "racecar-straight", "t": 11.0},
  "run": {
    "kind": "plot", "model": "racecar-straight", "xlim": [0, 14],
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "Telemetry/speed", "label": "Telemetry/speed"}], "hlines": [{"y": 73.662, "label": "top speed (reference) 73.66 m/s"}], "legend": true},
      {"ylabel": "motor torque [N m]", "series": [{"signal": "MotorR/tau", "label": "MotorR/tau"}, {"signal": "MotorR/tlim", "label": "MotorR/tlim", "style": "--"}], "legend": true},
      {"ylabel": "battery current [A]", "series": [{"signal": "Battery/I", "label": "Battery/I"}]}
    ]
  }
}
@@ page racecar-straight overview - | Overview
# Race car: top speed and regenerative braking

The race car starts at the top speed of the reference: 260 kW against the drag, the rolling resistance and the tyre slip. At 10 s the accelerator comes off and the brake pedal goes to 50 % (a 55 ms ramp). The rear motor takes what it can of the rear brake demand. Above about 50 m/s its 200 kW regen power limit caps it, and the rear friction brakes take the rest ([Brakes](block:Brakes)). Below that speed the motor covers the whole rear demand (185.7 N m at the rotor) and the rear friction brakes are idle. The front axle has no motor, so its friction brakes take their full share. The battery current reverses and the state of charge rises.

![The model canvas|900](@fig:diagram)

## What to try

- Move the brake pedal and the regen power limit on the dashboard (globals `brake_set` and `P_regen_kw`). With the regen limit at 0 the friction brakes do all the work and the charge does not rise.
- Plot [Brakes/rl](signal:Brakes/rl) (the rear friction torque) against [MotorR/regen](signal:MotorR/regen).

![3D view at t = 11 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page racecar-straight results overview | Results
# Results

![Speed, motor torque and battery current|900](@fig:run)

The reference is the 1-D longitudinal model of `racecar-launch` with the same brake blend, started at its top speed (motor at 260 kW, 16 012 rpm, 155.1 N m). The model's pedal ramp is a step at the middle of the ramp (10.0275 s) in the reference.

| t [s] | speed [m/s] | motor torque [N m] | battery current [A] |
| --- | --- | --- | --- |
| 9.9 | 73.89 / 73.66 | 154.6 / 155.1 | 740.8 / 740.8 |
| 10.25 | 70.28 / 70.05 | -130.7 / -131.0 | -472.0 / -472.0 |
| 11 | 58.06 / 57.89 | -160.4 / -160.8 | -471.9 / -471.9 |
| 12 | 43.06 / 42.92 | -185.7 / -185.7 | -402.0 / -401.1 |
| 14 | 15.77 / 15.67 | -185.7 / -185.7 | -148.1 / -147.4 |

Each cell is bg-sim / reference. bg-sim settles 0.3 % above the reference's top speed (the reference holds the load transfer quasi-static and the tyre slip in steady state). The car then loses speed at the same rate, 58.1 and 58.0 m/s from 10 to 14 s. While the power limit is active, the regen current holds at 472 A.
@@ figures buggy-settle
{
  "diagram": {"kind": "diagram", "model": "buggy-settle"},
  "scene": {"kind": "scene", "model": "buggy-settle", "t": 1.0},
  "run": {
    "kind": "plot", "model": "buggy-settle", "xlim": [0, 2],
    "rows": [
      {"ylabel": "CG height [m]", "series": [{"signal": "Pose/pz", "label": "Pose/pz"}], "hlines": [{"y": 0.75, "label": "static ride height 0.75 m"}], "legend": true},
      {"ylabel": "tyre load [kN]", "series": [{"signal": "FL/Tyre/Fz", "label": "FL", "scale": 0.001}, {"signal": "RL/Tyre/Fz", "label": "RL", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page buggy-settle overview - | Overview
# Buggy: drop test

The electric buggy of the **cars** example, released 3 cm above its static ride height. Its soft, long-travel suspension (heave 1.4 Hz, pitch 1.7 Hz) settles in about a second.

![The model canvas|900](@fig:diagram)

![3D view at t = 1 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page buggy-settle results overview | Results
# Results

![CG height and tyre loads|900](@fig:run)

Against the 7-DOF ride model of `design/reference.py`: the CG height [Pose/pz](signal:Pose/pz) agrees to 0.02 mm at every sample, the static loads (2004 N front, 2450 N rear per wheel) to 0.1 %.
@@ figures buggy-grade
{
  "diagram": {"kind": "diagram", "model": "buggy-grade"},
  "scene": {"kind": "scene", "model": "buggy-grade", "t": 8.0},
  "run": {
    "kind": "plot", "model": "buggy-grade", "xlim": [0, 12],
    "rows": [
      {"ylabel": "accelerator", "series": [{"signal": "Throttle/y", "label": "Throttle/y"}], "hlines": [{"y": 0.3237, "label": "reference 0.3237"}], "legend": true},
      {"ylabel": "motor torque [N m]", "series": [{"signal": "MotorF/tau", "label": "MotorF/tau"}, {"signal": "MotorR/tau", "label": "MotorR/tau", "style": "--"}], "legend": true},
      {"ylabel": "tyre load [kN]", "series": [{"signal": "FL/Tyre/Fz", "label": "FL", "scale": 0.001}, {"signal": "RL/Tyre/Fz", "label": "RL", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page buggy-grade overview - | Overview
# Buggy: 25 % grade

The buggy holds 5 m/s up a 25 % (14 deg) plane. The ground is a `TerrainSurface` with a constant slope. Both motors ([MotorF](block:MotorF), [MotorR](block:MotorR)) are on the same accelerator, and a PI ([Throttle](block:Throttle)) holds the speed.

![The model canvas|900](@fig:diagram)

![3D view at t = 8 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page buggy-grade results overview | Results
# Results

![Accelerator, motor torques and tyre loads|900](@fig:run)

The reference (`design/reference.py`) solves the climb's equilibrium: grade resistance, rolling resistance and drag against the four tyre forces, the slips of the front and rear axles, and the load transfer to the rear on the slope.

| quantity | bg-sim | reference |
| --- | --- | --- |
| accelerator | 0.3238 | 0.3237 |
| motor torque (each) | 48.56 N m | 48.56 N m |
| front / rear tyre load | 1642 / 2679 N | 1649 / 2672 N |
| battery current | 30.84 A | 30.82 A |
@@ figures buggy-hills
{
  "diagram": {"kind": "diagram", "model": "buggy-hills"},
  "scene": {"kind": "scene", "model": "buggy-hills", "t": 12.0},
  "run": {
    "kind": "plot", "model": "buggy-hills", "xlim": [0, 30],
    "rows": [
      {"ylabel": "height [m]", "series": [{"signal": "FL/Tyre/zc", "label": "FL contact FL/Tyre/zc"}, {"signal": "TerrainProbe/hq", "label": "terrain TerrainProbe/hq", "style": "--"}], "legend": true},
      {"ylabel": "travel [cm]", "series": [{"signal": "FL/Strut/travel", "label": "FL", "scale": 100}, {"signal": "RR/Strut/travel", "label": "RR", "scale": 100}], "legend": true},
      {"ylabel": "tyre load [kN]", "series": [{"signal": "FL/Tyre/Fz", "label": "FL", "scale": 0.001}, {"signal": "RR/Tyre/Fz", "label": "RR", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page buggy-hills overview - | Overview
# Buggy: rolling hills

The buggy at 8 m/s over rolling hills: an analytic height field $h(x, y) = \sum_i a_i \cos(k_{x,i} x + k_{y,i} y + \varphi_i)$ with six components (wavelengths 25 to 140 m, up to 2.2 m amplitude), with a few steering inputs. Each corner has its own `TerrainSurface` that gives the tyre the tangent plane below the wheel centre.

![The model canvas|900](@fig:diagram)

A second `TerrainSurface`, [TerrainProbe](block:TerrainProbe), evaluates the terrain at the point where the FL tyre says it touches ([FL/Tyre/zc](signal:FL/Tyre/zc)): the two heights agree to a few micrometres. The same table (`design/hills.json`) draws the hills in the 3D view and in the `apps/car-sim` host.

![3D view at t = 12 s|600](@fig:scene)

Continue with [the results](page:results).
@@ page buggy-hills results overview | Results
# Results

![Contact height, suspension travel and tyre loads|900](@fig:run)

After the drop onto the terrain (the first 0.5 s) the contact point lies on the terrain to within 0.07 mm (the check in `expected.json` allows 2 mm), and the wheels stay on the ground: no tyre load falls below 870 N. Change the speed on the dashboard (global `v_set`) to see the suspension work harder.
@@ figures racecar-sim
{
  "diagram": {"kind": "diagram", "model": "racecar-sim"},
  "scene": {"kind": "scene", "model": "racecar-sim", "t": 8.0}
}
@@ page racecar-sim overview - | Overview
# Race car: the FMU source

The race car with the interface of the `apps/car-sim` driving simulator, on the race track (flat, z = 0).

![The model canvas|900](@fig:diagram)

- **Inputs** (`ExportInputPass`): [steer](block:steer), [throttle](block:throttle), [brake](block:brake), [reverse](block:reverse), [handbrake](block:handbrake) and the friction scale under each tyre, [mu_fl](block:mu_fl) .. [mu_rr](block:mu_rr). In bg-sim they pass a short test drive through; in the FMU the host supplies them.
- **Outputs** (`ExportOutput`): the chassis and carrier poses, the spin angles, the tyre and suspension states, the contact points, the telemetry, the motor and the battery.
- **FMU parameters**: the globals `x0`, `y0`, `z0`, `yaw0`, `soc0` (the start state is a set of expressions of them) and the motor and brake limits.

Export it with `julia --project=julia/BGSim examples/export_cars.jl <out> racecar` or from the Export dialog. It uses fixed-step RK4 at 5 ms per communication step.

![3D view at t = 8 s|600](@fig:scene)
@@ figures buggy-sim
{
  "diagram": {"kind": "diagram", "model": "buggy-sim"},
  "scene": {"kind": "scene", "model": "buggy-sim", "t": 8.0}
}
@@ page buggy-sim overview - | Overview
# Buggy: the FMU source

The buggy with the interface of the `apps/car-sim` driving simulator, on the rolling hills of `buggy-hills`. The interface is the race car's (see `racecar-sim`), with a front and a rear motor.

![The model canvas|900](@fig:diagram)

The host draws the same height field the four `TerrainSurface` blocks evaluate, so the wheels sit on the drawn ground.

![3D view at t = 8 s|600](@fig:scene)
