# segway: a two-wheeled self-balancing transporter with a rider

A Segway-class personal transporter as a **3D bond graph**: a body (rider, platform, frame, batteries) pivoting on the axle
of two driven wheels that roll on the ground. The motors torque the wheels against the body, so the reaction torque
righting the rider is in the model, not assumed. An LQR holds the vehicle upright and follows a speed set-point, and a
PD heading loop steers with differential wheel torque.

```
Ground (ContactSurface) --o,fr--> TyreL / TyreR (RollingDisk) <--bond-- WheelL / WheelR (RigidBody3D)
Body (RigidBody3D) <-- Pose (PoseIntegrator3D)     Push (ExternalWrenchSpatial) --> Body
Body.p == MountL / MountR (FixedTransform3DNeutral) == AxleL / AxleR (Revolute3D, axis = body y) == WheelL / WheelR
MotorL / MotorR (MSe torque) --> AxleL.drive / AxleR.drive        (the joint carries the reaction on the body)
Sense (SegwaySense) -> Ctrl (SegwayCtrl) -> MotorL, MotorR;   Plan or VRef -> Ctrl
```

## Models

| model | what it shows |
| --- | --- |
| `balance` | released 0.03 rad off upright, speed ramp to 1.5 m/s from t = 3 s, a 150 N push at t = 9 s |
| `open-loop` | no control, released 0.002 rad off upright: the fall with the unstable pole +5.23 1/s |
| `top-speed` | ramp to the published top speed of the Segway i2, 20 km/h, and hold it; the motors' voltage demand against the bus |
| `figure-eight` | 1.5 m/s along two circles of opposite sense (heading set-point +2 pi then -2 pi), steered by differential torque |

All four have the same plant, scene (`scenes/segway.sdf`, a rider on a Segway PT on a tiled floor, the wheels visibly roll)
and controller; only the mission differs. Parameters are global parameters (Equations manager), so mass, centre-of-mass
height, gains and the push are tunable.

## Build and checks

```
uv run examples/segway/design/design.py          # open-loop pole, Riccati gains, reference simulations -> design.json
uv run examples/segway/design/build_model.py     # models/*.bgmodel.json
uv run examples/segway/design/build_scene.py     # scenes/segway.sdf
uv run examples/segway/design/build_expected.py  # expected.json
uv run examples/run_checks.py --only segway
```

`design/design.py` linearises the Lagrange model analytically at upright (state `[x, v, theta, theta']`, input the total wheel
torque, wheel and body inertia and the rolling constraint included), solves the continuous Riccati equation with scipy
(Bryson weights, see the file) and integrates the **non-linear** closed loop with RK4 as an independent reference. The checks
compare the bond graph with it: pitch, speed and position at fixed times, the peak torque and voltage, the statics of the
tyre loads, the closed-loop heading and path of the figure of eight, and the open-loop fall (the unstable pole
+5.2287 1/s). The 3D bond graph reproduces the planar reference to four digits.

## Parameters

Values marked **published** are quoted from a source; the rest are **estimates** (no complete parameter set for a Segway PT
with a rider was found, and no flight or test log, so there is no measured data to compare the time response with).

| parameter | value | status |
| --- | --- | --- |
| rider + platform mass | 75 kg of the 105 kg body | published as a model parameter: person + platform 75 kg in Moore, *Modeling, Simulation, and Control of a Segway* (EME 171, Cal Poly), moorepants.github.io/eme171; frame and batteries (30 kg) are an estimate |
| body pitch inertia `J_by` | 16 kg m² | estimate; Moore's person + platform value is 14 kg m² (published) |
| body mass `m_b` | 105 kg | estimate |
| centre of mass above the axle `l` | 0.52 m | estimate (rider at about 0.7 m, batteries low); Moore uses 0.9 m for a taller rider |
| roll and yaw inertia | 12, 3 kg m² | estimate |
| wheel radius `r` | 0.24 m | estimate (the Segway PT tyre is about 19 in) |
| wheel mass, spin and diameter inertia | 5 kg, 0.15 and 0.08 kg m² | estimate (Moore uses 6 kg, m r² = 0.24 kg m² for a 0.4 m wheel) |
| distance between the wheels `b` | 0.45 m | estimate (the PT's overall width is 0.635 m) |
| gear ratio, torque constant | 24, 0.12 N m/A | estimate: 2.88 N m/A at the wheel (Moore uses 12 N m/A for one motor, a different drive) |
| winding resistance | 0.15 Ω | estimate |
| torque limit | 80 N m per wheel | estimate |
| battery bus | 72 V | estimate (recalled for the PT, not verified in a source) |
| top speed | 20 km/h | **published**, Segway i2 specification (Segway i2 reference manual / training manual) |
| rider and cargo limits | 45 to 118 kg | **published**, same source (the default 105 kg body, 75 kg rider, is inside it) |
| gravity | 9.81 m/s² | standard |
| tyre contact | k = 5e5 N/m, xref 1 mm, c = 1 s/m, mu = 0.9 | estimate |
| joint stiffness and damping | kr = kt = 1e6, br = 200, bt = 4000 | numerical (held directions of the joints) |
| LQR weights | sigma: 0.4 m, 0.4 m/s, 0.15 rad, 0.6 rad/s, 150 N m | design choice |

The motors are ideal torque sources with a current-limited, 80 N m per wheel torque; a **rotor inertia is neglected**
(reflected through the 24:1 gear it would be 0.1 kg m² for both motors, 2 % of the translational mass), because a rotor on the
joint rate is a derivative-causal store beside the body and wheel inertias. The terminal voltage each motor would need,
`R i + k_t n (joint rate)`, is computed in the controller and checked against the bus.

## What to try

- `open-loop`: change the body mass or the height of the centre of mass. The fall time barely depends on the mass but a lower
  centre of mass falls more slowly.
- `balance`: raise the push to 400 N, or change the body mass to 70 or 140 kg without re-running `design.py`. The gains are
  fixed for 105 kg, which shows the margin of the design.
- `top-speed`: raise the cruise speed past 20 km/h in the Equations manager (`v_slope`); `Ctrl/vreq_l` crosses the 72 V bus.
- `figure-eight`: shorten the circle time (global `t_loop`) or raise the speed; the lateral acceleration `v psi'` approaches
  the friction limit, and the pitch loop and tyre creep show it.

## Notes on the formulation

A planar (pitch plus forward motion) formulation was not needed: the 3D bond graph with two wheels runs in 15 to 40 s per
model and has no derivative-causal elements. The planar Lagrange equations are the independent reference in `design/design.py`.
