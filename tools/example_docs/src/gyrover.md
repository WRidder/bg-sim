@@ figures gyrover
{
  "diagram": {"kind": "diagram", "model": "gyrover"},
  "scene-turn": {"kind": "scene", "model": "gyrover", "t": 9.0},
  "mission": {
    "kind": "plot", "model": "gyrover", "xlim": [0, 30],
    "rows": [
      {"ylabel": "heading [rad]", "series": [{"signal": "Sense/heading", "label": "heading"}, {"signal": "Plan/psi_ref", "label": "set-point", "style": "--"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "angle [rad]", "series": [{"signal": "Sense/lean", "label": "lean"}, {"signal": "Sense/th2", "label": "tilt theta2"}, {"signal": "Ctrl/lean_ref", "label": "lean set-point", "style": "--"}], "legend": true, "legend_loc": "lower left"},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Sense/v", "label": "v"}, {"signal": "Plan/v_ref", "label": "set-point", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "torque [N m]", "series": [{"signal": "Ctrl/tau1", "label": "drive tau1"}, {"signal": "Ctrl/tau2", "label": "tilt tau2"}, {"signal": "Ctrl/tau3", "label": "flywheel tau3"}], "legend": true, "legend_loc": "upper right"}
    ]
  },
  "path": {
    "kind": "plot", "model": "gyrover", "width": 620, "row_height": 5.2,
    "rows": [
      {"ylabel": "y [m]", "x": "Sense/xc", "xlabel": "x [m]", "equal": true, "series": [{"signal": "Sense/yc", "label": "wheel centre"}]}
    ]
  },
  "contact": {
    "kind": "plot", "model": "gyrover", "xlim": [0, 30],
    "rows": [
      {"ylabel": "slip [mm/s]", "series": [{"signal": "Tyre/s_lat", "label": "lateral", "scale": 1000.0}, {"signal": "Tyre/s_lon", "label": "longitudinal", "scale": 1000.0}], "legend": true},
      {"ylabel": "force [N]", "series": [{"signal": "Tyre/f_n", "label": "normal f_n"}, {"signal": "Tyre/f_lat", "label": "lateral f_lat"}], "hlines": [{"y": 68.84, "label": "weight 68.8 N"}], "legend": true, "legend_loc": "center right"}
    ]
  },
  "energy": {
    "kind": "plot", "model": "gyrover", "xlim": [0, 30],
    "rows": [
      {"ylabel": "motor work [J]", "series": [{"signal": "Energy/work", "label": "drive + tilt + flywheel motors"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "contact loss [mJ]", "series": [{"signal": "Energy/loss", "label": "contact loss", "scale": 1000.0}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "Ebal [J]", "series": [{"signal": "Energy/Ebal", "label": "stored + loss - work (constant to 2.8 mJ; the flywheel holds 3.7 kJ)"}], "legend": true}
    ]
  },
  "free-bg": {
    "kind": "plot", "model": "free", "xlim": [0, 6],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Sense/lean", "label": "bond graph lean"}], "legend": true},
      {"ylabel": "heading [rad]", "series": [{"signal": "Sense/heading", "label": "bond graph heading"}], "legend": true},
      {"ylabel": "contact loss [J]", "series": [{"signal": "Energy/loss", "label": "contact loss"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "Ebal [J]", "series": [{"signal": "Energy/Ebal", "label": "stored + loss (constant to 3.4 mJ)"}], "legend": true}
    ]
  },
  "free-ref": {
    "kind": "plot", "model": "reference", "xlim": [0, 6],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Gyrover/lean", "label": "reference lean", "color": "#444444"}], "legend": true},
      {"ylabel": "heading [rad]", "series": [{"signal": "Gyrover/heading", "label": "reference heading", "color": "#444444"}], "legend": true}
    ]
  },
  "turn": {
    "kind": "plot", "model": "steady-turn", "xlim": [0, 10],
    "rows": [
      {"ylabel": "heading rate [rad/s]", "series": [{"signal": "Sense/yaw_rate", "label": "bond graph"}], "hlines": [{"y": -0.335157, "label": "exact steady turn -0.335157"}], "ylim": [-0.36, -0.30], "legend": true},
      {"ylabel": "angle [rad]", "series": [{"signal": "Sense/lean", "label": "lean"}, {"signal": "Sense/th2", "label": "tilt"}], "legend": true}
    ]
  },
  "spin": {
    "kind": "plot", "model": "spin", "xlim": [0, 5],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Sense/lean", "label": "flywheel at 15 000 rpm"}], "ylim": [0.0, 0.1], "legend": true},
      {"ylabel": "heading [rad]", "series": [{"signal": "Sense/heading", "label": "slow precession"}], "legend": true}
    ]
  },
  "nospin": {
    "kind": "plot", "model": "no-spin", "xlim": [0, 0.6],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Sense/lean", "label": "flywheel stopped"}], "legend": true}
    ]
  },
  "fig3": {
    "kind": "plot", "model": "fig3", "xlim": [0, 4],
    "rows": [
      {"ylabel": "angle [rad]", "series": [{"signal": "Sense/th1", "label": "pendulum theta1"}, {"signal": "Sense/th2", "label": "tilt theta2"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "rate [rad/s]", "series": [{"signal": "Sense/wx", "label": "roll rate omega0x"}, {"signal": "Sense/wz", "label": "wheel rate omega0z"}], "legend": true},
      {"ylabel": "[rad], [rad/s]", "series": [{"signal": "Sense/lean", "label": "lean"}, {"signal": "Sense/yaw_rate", "label": "heading rate"}], "legend": true, "legend_loc": "lower right"}
    ]
  },
  "drill": {
    "kind": "plot", "model": "fig3-drill", "xlim": [0, 8],
    "rows": [
      {"ylabel": "lean [rad]", "series": [{"signal": "Gyrover/lean", "label": "with drilling damping 0.3 N m s/rad"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page gyrover overview - | Overview
# Gyrover: a single wheel that balances with a flywheel

The **Gyrover** (Carnegie Mellon) is a robot that is nothing but a wheel. Inside the tyre a drive unit hangs from the axle like a pendulum, and it carries a **flywheel spinning at about 15 000 rpm** in a gimbal. Three motors act:

- the **drive motor** turns the wheel against the hanging pendulum (speed);
- the **tilt motor** turns the flywheel gimbal about the forward axis; the gyroscopic reaction leans the wheel, and a leaning wheel turns (steering and balance);
- the **flywheel motor** keeps the spin speed.

This example rebuilds the robot after

> S.-J. Tsai, E. D. Ferreira and C. J. J. Paredis, *Control of the Gyrover: a single-wheel gyroscopically stabilized robot*, IEEE/RSJ IROS 1999.

as a physical bond graph from library blocks, checks it against an independent equation-based model, and closes the paper's balance loops plus speed and heading loops around it. In the showcase run the robot starts at rest, speeds up to 1.2 m/s and drives a rounded square of four 90-degree turns on the 10 m floor.

![The 3D view at 9 s, in the first turn: the wheel leans into the turn, the gimbal is tilted|900](@fig:scene-turn)

![Path of the wheel centre|500](@fig:path)

## Run it

Press **Run** (30 s, about 25 s of solving). The **3D View** tab replays the run: tyre with tread and spokes, translucent side covers, the drive unit (hub motor, battery, fork, red tilt motor), the gimbal ring and the brass flywheel (drawn 200 times slower than it turns). The orange discs on the floor are the path of the run, every 0.5 m.

The **dashboard** has sliders for the cruise speed ([Plan](block:Plan) `v_cruise`) and the heading change of each turn (`dpsi`), gauges for the lean and the tilt and the heading against its set-point. Change a slider and press **Run** again.

Default plots: lean and tilt, heading, wheel rate and speed, flywheel speed, the x-y path, the three motor torques and the energy book.

## Models of the project

| model | what it shows |
| --- | --- |
| `gyrover` | the showcase: bond graph, all loops closed, 30 s mission (this page) |
| `gyrover-ref` | the same mission on the equation-based reference model |
| `free`, `reference` | uncontrolled rolling, bond graph and reference, energy book |
| `steady-turn`, `steady-turn-ref` | a steady turn against its exact solution |
| `spin`, `no-spin` | standing on the rim: the flywheel keeps the robot up, without it it falls |
| `fig3`, `fig3-ref` | the paper's figure 3 (recovery with the paper's gains) |
| `fig3-drill` | figure 3 with tyre drilling damping: the slow mode turns unstable |

Pages: [model and bond graph](page:model), [the rolling contact](page:rolling), [parameters](page:parameters), [validation](page:validation), [control design](page:control).
@@ page gyrover model overview | Model and bond graph
# Model and bond graph

![The model canvas|1000](@fig:diagram)

Three rigid bodies, two joints, a rotor and a contact, all library blocks:

```
Ground (ContactSurface) --o,fr--> Tyre (RollingDisk) <--bond-- Wheel (RigidBody3D) <-- Pose (PoseIntegrator3D)
Wheel.p == MountA (identity) == Axle (Revolute3D, axle) == LinkP == Pendulum (RigidBody3D)
Pendulum.p == MountT == Tilt (Revolute3D, forward axis) == LinkG == Gimbal (RigidBody3D) -- Flywheel (Rotor3D)
Drive (MSe) -> Axle.drive     TiltMotor (MSe) -> Tilt.drive     SpinMotor (MSe) -> Flywheel.drive
Sense (GyroSense) -> Ctrl (GyroCtrl) -> Drive, TiltMotor, SpinMotor;   Plan (GyroPlan) -> Ctrl;   Energy (GyroEnergy)
```

- **Wheel** ([Wheel](block:Wheel)): the only floating body; its pose is integrated by [Pose](block:Pose) from its twist. Body frame at the centre, axle = body z.
- **Contact** ([Tyre](block:Tyre)): a `RollingDisk` on the floor plane ([Ground](block:Ground)). Bonded straight to the wheel body; see [the rolling contact](page:rolling).
- **Pendulum** ([Pendulum](block:Pendulum)): the drive unit, on the compliant axle joint [Axle](block:Axle) whose drive port is the drive motor. Its pose is composed (`ComposePose3D`) from the wheel pose and the joint, so it is not a state.
- **Gimbal** ([Gimbal](block:Gimbal)): on the tilt joint [Tilt](block:Tilt) (axis = forward axis of the pendulum), carrying the flywheel's mass and transverse inertia.
- **Flywheel** ([Flywheel](block:Flywheel)): a `Rotor3D` on the gimbal. Only its axial momentum is a state, so the 1571 rad/s spin costs nothing; a `RigidBody3D` on a third joint would make the solver resolve every revolution.
- The joints are the default compliant `Revolute3D` (held directions $k = 10^6$, damped by $b_r = 20$, $b_t = 500$ in the controlled runs and undamped in the energy run `free`).

Example blocks (in `library/`):

| block | role |
| --- | --- |
| [Sense](block:Sense) `GyroSense` | the paper's coordinates from the wheel pose and twist: lean, pendulum angle `th1`, tilt `th2`, roll rate `wx`, `wy`, wheel rate `wz`, heading (integrated heading rate), speed, position |
| [Ctrl](block:Ctrl) `GyroCtrl` | the paper's two state feedbacks, the tilt servo and our speed and heading loops; see [control design](page:control) |
| [Plan](block:Plan) `GyroPlan` | the mission: smooth speed and heading set-points |
| [Energy](block:Energy) `GyroEnergy` | stored energy, contact loss, motor work and the balance `Ebal` |
| `GyroverRef` | the equation-based reference model (models `*-ref`, `reference`) |

**Reference model.** `GyroverRef` is generated by `design/gen_ref.py` from a symbolic derivation (`design/eom.py`, Kane's method in sympy): the same three bodies and rotor, **exact rolling without slip** (a nonholonomic constraint, no contact compliance), the coordinates heading $\psi$, lean $\phi$, wheel angle $\gamma$, pendulum angle $\beta$, tilt $\theta_2$ and their rates. The bond graph and the reference share nothing but the parameters.
@@ page gyrover rolling overview | The rolling contact
# The rolling contact

**Choice.** The wheel touches the floor through a **compliant contact with regularised Coulomb friction** (`RollingDisk`), not through a rolling constraint. Reasons:

- a rolling constraint is nonholonomic: it cannot be written as a bond-graph element on the wheel's spatial port without a constraint solver, and a stiff penalty is the bond-graph way (as `ContactPoint` does for a point);
- the compliant contact keeps everything an ODE, so the same model exports to C and an FMU;
- it shows the losses that an ideal constraint hides: side slip, rolling losses and lift-off would appear if the robot overloaded the tyre.

**Geometry.** The contact point is not fixed in the wheel: at every instant it is the lowest point of the rim, $u = -(n - (n\cdot a)a)/\lVert\cdot\rVert$, $r = R\,u$, with $a$ the axle and $n$ the floor normal. The normal force is a smooth Hertz/Hunt-Crossley law ($k = 10^6$ N/m at 1 mm, $c = 2$ s/m); the friction acts on the slip $s$ of the rim material point, $F_t = -\mu f_n\, s/\sqrt{s^2 + v_s^2}$ with $\mu = 0.9$ and $v_s = 1$ mm/s.

**Slip, quantified.** A rolling wheel under a side force $F$ creeps at $s \approx v_s F/(\mu f_n)$. In the showcase:

| quantity | measured | checked |
| --- | --- | --- |
| lateral slip | at most 0.043 mm/s | below 0.1 mm/s |
| longitudinal slip | at most 0.076 mm/s | below 0.2 mm/s |
| use of the friction cone $\lvert f_{lat}\rvert/f_n$ | at most 3.8 % | |
| normal force | 62.0 to 79.1 N (weight 68.8 N) | above 50 N (no lift-off) |
| penetration | at most 0.185 mm | below 0.25 mm |
| contact loss over the 30 s mission | 2.7 mJ (motor work 5.5 J) | |

So the wheel rolls: the creep is five orders of magnitude below the speed, and the bond graph follows the exact-rolling reference to 0.27 mm over the 33 m loop. The one systematic difference is the rolling radius, smaller by the static penetration (0.18 mm).

![Slip and contact forces in the mission|1000](@fig:contact)

Where the model departs from exact rolling: when the uncontrolled robot (model `free`) nutates after about 3 s, the tyre side-slips (up to 0.05 m/s) and the contact dissipates 1.18 J by 6 s; the reference model cannot show this.
@@ page gyrover parameters overview | Parameters
# Parameters

The paper gives the linearised equations about the upright rest, the tilt-servo model and the two gains, but **no masses or inertias**. The physical parameters were chosen so that the linearisation of our nonlinear model reproduces the paper's matrices (`design/paper_lin.py` prints the comparison).

| parameter | value | source |
| --- | --- | --- |
| flywheel speed | 15 000 rpm = 1571 rad/s | paper |
| tilt servo | $\ddot\theta_2 = \omega_c^2(u_2 - \theta_2) - \sqrt2\,\omega_c\dot\theta_2$, $\omega_c = 20\pi$ | paper, eq. 7 (the $-400\pi^2$, $-88.86$ entries of $A_2$) |
| gains $K_1 = (-18.44, -3.31, 1.16)$, $K_2 = (-0.0077, 1.001, 0.0019, 0.0179, -0.0022)$ | | paper, section 4 |
| wheel radius $R$ | 0.197 m | chosen to match $A_1$, $B_1$ |
| wheel mass, axial / transverse inertia | 2.0 kg, 0.0249 / 0.0146 kg m² | chosen (plausible) and $A_1$ |
| pendulum mass, CoM below the axle | 3.417 kg, 0.0939 m | chosen to match $A_1$ (gravity stiffness) |
| pendulum inertia (principal axes 45 deg off) | 0.0371 / 0.0353 / 0.0091 kg m² | chosen to match $A_1$, $B_1$ and $A_2$ |
| gimbal mass and inertia, CoM on the axle | 0.4 kg, 0.00087 / 0.0006 / 0.0007 kg m² | assumed |
| flywheel mass, axial / transverse inertia | 1.2 kg, 0.00301 / 0.00166 kg m² | axial inertia from the gyroscopic entries of $A_2$ (momentum $H$ = 4.73 N m s) |
| contact | $k = 10^6$ N/m at 1 mm, $c$ = 2 s/m, $\mu$ = 0.9, $v_s$ = 1 mm/s | assumed |

Total mass 7.0 kg. Our linearisation against the paper's:

| entry | ours | paper |
| --- | --- | --- |
| $A_1$ gravity terms | -44.58, -12.04 | -44.32, -11.91 |
| $B_1$ | 14.51, -0.353 | 14.52, -0.37 |
| $A_2$ row 4 | 49.3, -47.3, 6.75, -7.82, 22.4 | 51.5, -49.3, 6.5, -8.7, 23.37 |
| $A_2$ row 5 | 17.2, -16.5, 120.4, -120.8, 7.82 | 19.17, -28.3, 102.5, -103.7, 8.7 |
| $B_2$ | 47.3, 16.5 | 49.3, 28.3 |

The longitudinal subsystem matches to about 1 % and the lateral one to 5-17 %, except the tilt coupling of the heading-rate row (-16.5 against -28.3). Closed-loop poles with the paper's gains:

| loop | ours | paper's matrices | paper text |
| --- | --- | --- | --- |
| longitudinal ($K_1$) | -41.25, -3.60 ± 2.77j | -41.31, -3.59 ± 2.76j | |
| lateral ($K_2$, ideal servo) | -35.2 ± 33.3j, -9.27, -0.90, 0 | -34.3 ± 25.1j, -11.2, -0.86, 0 | -34.45 ± 25.18i, -10.34, -1.37, -0.1 |

The pole at zero is the conserved vertical angular momentum (a heading/precession mode that the lateral feedback cannot move at rest). The paper's -0.1 does not come out of its own printed matrices with the printed four-digit gains either: its $A_2$ is nearly singular.
@@ page gyrover validation overview | Validation
# Validation

Every number below is a check in `expected.json`, run by `uv run examples/run_checks.py --only gyrover`.

## Bond graph against the reference model

| run | quantity | largest difference |
| --- | --- | --- |
| showcase (30 s, all loops) | heading, lean, tilt | 2.1e-5, 2.0e-5, 2.8e-5 rad |
| | path x, y; speed | 0.27 mm, 0.17 mm; 0.15 mm/s |
| steady turn (after 3 s) | heading rate, lean | 5.1e-6 rad/s, 3.9e-6 rad |
| paper's figure 3 | pendulum angle, tilt, lean | 3.6e-5, 3.8e-5, 4.1e-5 rad |
| uncontrolled rolling (to 2 s) | heading, lean, path | 7.3e-3 rad, 3.5e-3 rad, 0.53 mm |

The uncontrolled rolling (`free` against `reference`, 1.5 m/s, 0.05 rad lean, no motor) is the sensitive case: the free robot has a slowly growing nutation, and the two models separate after about 2.5 s, which the slip and the joint compliance of the bond graph are enough to cause.

![Uncontrolled rolling, bond graph|1000](@fig:free-bg)

![Uncontrolled rolling, reference model|1000](@fig:free-ref)

## Energy

Without damping and drive (model `free`: undamped joints, the tilt held by a spring) the bond graph's energy book `Energy/Ebal` = kinetic + potential + contact spring energy + integrated contact loss stays constant to 3.4 mJ over 6 s. The contact losses are **2.6 mJ in the first 2 s** of clean rolling and **1.18 J by 6 s**, once the nutation makes the tyre side-slip. The reference model (no contact) conserves its energy to 0.3 mJ over 2 s. In the showcase, `Ebal` (with the motor work subtracted) holds to 2.8 mJ against 5.5 J of motor work.

![Energy book of the showcase|1000](@fig:energy)

## The steady turn

A wheel that leans by $\phi$ while rolling at speed $v$ turns. The balance of moments about the contact line (gravity against the gyroscopic moment of the flywheel and the centrifugal and spin moments of the robot) gives, to first order in the transverse inertias,

$$\dot\psi = -\frac{mgh\,\sin\phi}{H\cos(\phi - \theta_2) + m h\, v\cos\phi}$$

with $mgh = g\,(m_{tot}R - m_p l_p - m_{gr} l_g) = 10.41$ N m, the flywheel momentum $H = J_{ra}\,\omega_3 = 4.73$ N m s and $mh = m_{tot}R - m_p l_p + J_{wa}/R = 1.19$ kg m. `design.steady_turn` solves the full equations of the reference model for the exact steady turn.

Model `steady-turn` holds a lean set-point with the lateral loop at 1.5 m/s. It settles at lean 0.2088 rad, tilt 0.1114 rad, speed 1.4902 m/s and heading rate **-0.335169 rad/s**; the exact solution at that state is **-0.335157** (the formula: -0.335292). The radius $v/\dot\psi$ = 4.446 m agrees with a circle fitted to the path (4.445 m). In the showcase turns the formula gives 0.31251 rad/s against the measured 0.3126.

![Steady turn|1000](@fig:turn)

## Gyroscopic stabilisation

Released at rest, standing on the rim at a 0.05 rad lean with the tilt held:

- **flywheel at 15 000 rpm** (model `spin`): the lean stays between 0.050 and 0.0519 rad for 5 s (a nutation of 1.9 mrad); the gravity moment makes the robot precess slowly about the vertical instead (heading rate -0.054 rad/s).
- **flywheel stopped** (model `no-spin`): the robot falls over. The lean grows as $e^{6.2 t}$ and passes 0.5 rad after 0.43 s.

![Flywheel spinning|1000](@fig:spin)

![Flywheel stopped|1000](@fig:nospin)
@@ page gyrover control overview | Control design
# Control design

## The paper's loops

The paper splits the linearised robot into a **longitudinal** part (pendulum angle $\theta_1$, pendulum rate $w_1$, wheel rate $\omega_{0z}$; input the drive torque $\tau_1$) and a **lateral** part (lean, tilt $\theta_2$, tilt rate $w_2$, roll rate $\omega_{0x}$, heading-rate component $\omega_{0y}$; input the tilt servo reference $u_2$), and closes each with a state feedback, $u = K x$. Block [Ctrl](block:Ctrl) does the same with true states (the paper used a Kalman filter):

- **balance and speed**: $\tau_1 = K_1 (x_1 - x_{1r})$ with the reference $x_{1r} = (0, -\omega_r, \omega_r)$, $\omega_r = v_{ref}/R$, so the same gain rolls the wheel at the set speed; saturated at 4 N m;
- **lean via the tilt**: $u_2 = K_2 (x_2 - x_{2r})$, saturated at 0.8 rad, feeds the paper's servo (eq. 7). The servo is realised by a stiff PD on the tilt motor, $\tau_2 = 40000\,(r - \theta_2) + 20\,(\dot r - w_2)$, which tracks the servo model's state $r$; a softer PD (gain 400) is destabilised by the gyroscopic load on the tilt axis;
- **flywheel speed**: $\tau_3 = 0.05\,(\omega_{3,ref} - \omega_3)$.

## Steering (ours)

The paper stabilises the robot; it does not steer it. Heading control works through the lean: a lean set-point $\phi_r = -0.35\tanh((\psi_r - \psi)/0.35)$ with a feed-forward of the steady-turn heading rate in the $\omega_{0y}$ reference, and a pre-scale of 2.04 (the inverse of the lean that the $K_2$ loop realises in steady state). With the mission of [Plan](block:Plan) the robot turns at 0.31 rad/s (radius 3.8 m) and closes the square within 0.025 rad of heading.

![Mission: heading, lean, speed and the motor torques|1000](@fig:mission)

## The paper's figure 3

Recovery from rest with $\theta_1(0) = 0.075$ rad and $\theta_2(0) = -0.2$ rad (model `fig3`):

| feature | paper (fig. 3, read from the plot) | here |
| --- | --- | --- |
| pendulum $\theta_1$ | dips to about -0.025 near 0.5 s, settled by about 1 s | crosses 0 at 0.31 s, minimum -0.008 at 0.72 s, within 0.002 after 1.24 s |
| wheel rate dip | about -0.08 to -0.1 rad/s near 0.2 s | -0.085 rad/s at 0.17 s |
| roll rate peak | about 0.22 rad/s near 0.3 s | 0.80 rad/s at 0.13 s |
| tilt $\theta_2$ | returns to 0 by about 2 s | -0.2 to -0.056 at 0.39 s, then settles at **-0.089 rad** |

![Figure 3 scenario|1000](@fig:fig3)

**What could not be reproduced.** The longitudinal response matches in shape and time scale. The lateral one does not end at upright: our robot settles in a slow steady precession (lean 0.112 rad, heading rate -0.252 rad/s) with the tilt at -0.089 rad. The reason is physical: standing on the rim, the vertical angular momentum about the contact is conserved (no yaw friction), so a start with the flywheel tilted cannot return to tilt 0 without turning. The paper's own linear model has the same zero pole; its matrices give the final tilt -0.30 rad. The larger roll-rate peak follows from the larger tilt coupling of our parameters in the roll row.

**Dissipation destabilises.** Adding drilling damping to the tyre (0.3 N m s/rad, model `fig3-drill`) makes the slow precession **unstable** under $K_2$: the lean grows to 0.29 rad at 4 s and 0.53 rad at 8 s. This is the Kelvin-Tait-Chetaev effect: a mode held only by gyroscopic coupling is lost when damping is added. A heading-rate loop around $K_2$ (as in the showcase) removes it.

![Figure 3 with drilling damping|1000](@fig:drill)
