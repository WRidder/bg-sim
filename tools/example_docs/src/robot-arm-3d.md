@@ figures arm
{
  "diagram": {"kind": "diagram", "model": "arm"},
  "scene": {"kind": "scene", "model": "arm", "t": 0.6},
  "run": {
    "kind": "plot", "model": "arm", "xlim": [0, 2],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "J1/qout", "label": "q1"}, {"signal": "J2/qout", "label": "q2"}, {"signal": "J3/qout", "label": "q3"}, {"signal": "J4/qout", "label": "q4"}, {"signal": "J5/qout", "label": "q5"}, {"signal": "J6/qout", "label": "q6"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "joint torque [N m]", "series": [{"signal": "Ctrl/u1", "label": "u1"}, {"signal": "Ctrl/u2", "label": "u2"}, {"signal": "Ctrl/u3", "label": "u3"}, {"signal": "Ctrl/u4", "label": "u4"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "TCP position [m]", "series": [{"signal": "TCP/g[5]", "label": "x"}, {"signal": "TCP/g[6]", "label": "y"}, {"signal": "TCP/g[7]", "label": "z"}], "legend": true}
    ]
  }
}
@@ page arm overview - | Overview
# Six-axis arm with PD and gravity feedforward

A UR5-like six-axis serial arm moves from a home pose to a target pose under a 1 ms sampled **PD + gravity-feedforward** controller. It is built from the J-MB9 spatial composites (`Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`, `LocalPose3D`, `ComposePose3D`) with the geometry and inertias of the J-MB10 six-axis golden test, and it is the 3D twin of `robot-arm-2d` (plan 9 / X-MB3, Gate C). Every power bond between the joints and the links is a `Power{Spatial}` bundle, drawn as **three strokes**.

This example folder also holds the X5.3 RRR arm models (`rrr`, `rrr-free`, `rrr-torque`, `rrr-multibond`, `rrr-multibond-soft`, `rrr-multibond-stiff`) which are documented in their own models.

![The model canvas (three-stroke spatial bonds)|900](@fig:diagram)

```
World - Mount - J1 - Link1 - BJ1 -+- B1 (RigidBody3D)
               (Revolute3D)  (CoM) '- T2 - J2 - Link2 - BJ2 -+- B2
                                        (standard-DH offset)  '- T3 - J3 - ... - J6 - Link6 - BJ6 - B6
D1..D6 (MSe torque sources) -> J1..J6.drive          Ctrl (ArmPD6, 1 ms) -> D1..D6
```

The run: 2 s with `Rodas5P`, `reltol` 1e-6, `abstol` 1e-8, 201 output points; the solver is set explicitly because `auto` fails here (see [the notes](page:notes)). Expect about two minutes of solve time on first run.

## What to look at

- the joint angles [J1/qout](signal:J1/qout) to `J6/qout` settling on the target;
- the controller torques [Ctrl/u2](signal:Ctrl/u2) (about -45.9 N·m settled: the gravity torque of the shoulder) and the tracking errors `Ctrl/e1..6`;
- the tool centre point [TCP/g[5]](signal:TCP/g[5]), [TCP/g[6]](signal:TCP/g[6]), [TCP/g[7]](signal:TCP/g[7]) (pose is quaternion first, so entries 5 to 7 are x, y, z).

## 3D view

`scenes/arm.sdf` draws the six-axis arm: every link is bound by its world pose to the model's composed body pose `P<i>/g[1..7]` (quaternion first), so the viewer needs no joint axes or kinematics of its own. A hub cylinder marks each joint axis and the bars run to the next joint; the red sphere is the tool centre point.

![3D view at t = 0.6 s|500](@fig:scene)

Continue with [the construction](page:construction), [the controller](page:controller), [the results](page:results) and [the notes](page:notes).
@@ page arm construction overview | Construction
# Construction

- **Joints** ([J1](block:J1) to `J6`). `Revolute3D` rotates exactly about the local $z$ of its joint frame; the other five directions are compliant ($k_t = k_r = 10^7$ N/m and N·m/rad), so every state stays integral (no W201). The held-direction damping is 0.7 of critical for the distal mass (translations) and for a 0.3 kg·m² reference inertia (rotations), so the stiff modes die in milliseconds.
- **Geometry.** Joint $i+1$ sits at the standard-DH fixed part $T_z(d)\,T_x(a)\,R_x(\alpha)$ of link $i$ (UR5-like):

| link | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| $d$ (m) | 0.0892 | 0 | 0 | 0.1092 | 0.0947 | 0.0823 |
| $a$ (m) | 0 | -0.425 | -0.392 | 0 | 0 | 0 |
| $\alpha$ | $\pi/2$ | 0 | 0 | $\pi/2$ | $-\pi/2$ | 0 |
| mass (kg) | 3.7 | 8.4 | 2.3 | 1.2 | 1.2 | 0.74 |

  The body 1-junction frame is the link's centre of mass ([B1](block:B1) has $m = 3.7$ kg, $J = (0.0103, 0.0103, 0.0067)$ kg·m²), so the next joint offset is $N - c_i$ in that frame ([T2](block:T2) to `T6`).
- **Drives.** One `MSe` torque source per joint ([D1](block:D1) to `D6`) on the joint's `Rotation` drive port, fed by the controller. A flow source cannot impose the joint motion (derivative causality, W201), so the joints are torque driven.
- **Poses** are composed, never integrated: $W_i = W_{i-1} \circ LN_i \circ J_i.\text{pose}$, the body pose is $W_i \circ LC_i$ (it feeds `B_i.g`, which gravity reads), and the tool centre point is $W_6 \circ L_{tool}$ with a $0.0823 + 0.1 = 0.1823$ m flange-plus-tool offset along the flange $z$.
- **Start.** The arm is released at rest at the home pose $q = (0, -1.2, 1.2, -1.5, -1.5, 0)$ on its **consistent deflections** (the `starts` of `dth`, `dl` from the independent Newton-Euler reference), so the held directions carry the static gravity load from $t = 0$ and the start does not excite the stiff modes.
@@ page arm controller overview | Controller
# Controller: minimum-jerk reference with PD and gravity feedforward

[Ctrl](block:Ctrl) is the discrete code block `library/ArmPD6.jl` (D28). With $t_0 = 0.1$ s and $T_m = 0.8$ s:

$$\tau = \operatorname{clamp}\!\Big(\frac{t - t_0}{T_m},\,0,\,1\Big), \qquad s = \tau^3\,(10 - 15\tau + 6\tau^2),$$

$$q_{r,i} = q_{h,i} + (q_{t,i} - q_{h,i})\,s, \qquad \dot q_{r,i} = (q_{t,i} - q_{h,i})\,\frac{30\,\tau^2 (1 - \tau)^2}{T_m},$$

$$u_i = \operatorname{clamp}\big(K_{p,i}\,(q_{r,i} - q_i) + K_{d,i}\,(\dot q_{r,i} - \dot q_i) + G_i(q),\ -u_{max,i},\ u_{max,i}\big).$$

The firmware samples the six angles and rates (and the clock) every 1 ms and holds the torques (zero-order hold, so no algebraic loop closes through the plant). **The gravity feedforward is computed inside the controller from the same geometry as the plant**: the forward kinematics of the standard-DH chain is unrolled in the block (generated code, no arrays) and

$$G_i = g_0 \sum_{j \ge i} m_j\; z_i \cdot \big((w_j - o_i) \times e_z\big),$$

the torque that holds the arm static. It agrees with the independent Newton-Euler gravity torque of J-MB10 to 7e-15 N·m at four test poses, so the settled error is zero instead of the PD droop $G/K_p$. The gains come from the largest mass-matrix diagonal entry $M_{ii}$ over five poses between home and target: $K_{p,i} = M_{ii}\,\omega_n^2$, $K_{d,i} = 2\,M_{ii}\,\omega_n$ (critical damping of the decoupled joint) with $\omega_n = 10, 10, 12, 20, 20, 20$ rad/s:

| joint | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 274 | 331 | 107 | 6.23 | 1.5 | 0.2 |
| $K_d$ (N·m·s/rad) | 54.9 | 66.2 | 17.9 | 0.623 | 0.15 | 0.02 |
| limit (N·m) | 150 | 150 | 150 | 28 | 28 | 28 |

The target is $q = (0.8, -0.8, 0.9, -1.9, -1.2, 0.6)$. There is no inertia feedforward, so the tracking error during the move is about $M\ddot q / K_p$.
@@ page arm results overview | Results and checks
# Results and checks

![Joint angles, controller torques and TCP position|900](@fig:run)

## Measured (README, 2 s run)

| quantity | value |
| --- | --- |
| settled joint-angle error at 2.0 s | 1.0e-5, 3.4e-5, 1.3e-5, 9.6e-5, 7.8e-5, 2.0e-5 rad |
| TCP error against analytic FK of the target angles | 9.9e-5 m (target (-0.44364, -0.70827, 0.21091) m) |
| peak torque | 19.8, 54.6, 20.7, 1.53, 0.20, 0.0013 N·m (limits never reached) |
| peak tracking error | 0.038, 0.018, 0.016, 0.029, 0.105, 0.0053 rad |
| settled torque minus target gravity torque | under 7e-3 N·m |
| states of the compiled system | 72 |
| accepted steps | 8973 |
| compile | 9.6 s with a structural cache hit; a cold first compile about 90 s |
| solve | 113 s for 2.0 s of simulated time |
| `uv run examples/run_checks.py --only robot-arm-3d` | 43 checks for `arm` in the original X-MB3 run |

The check bounds are 5x the measured errors. The TCP position differs from the rigid-body forward kinematics by the compliant joints' sag (about 1e-5 m per joint under gravity) plus the angle error times the 0.9 m reach.

## Checks (`expected.json`)

Start joint angles (home pose) and settled angles at 2 s (within 0.5 mrad); joint rates at 2 s below 0.005 rad/s; the TCP at the start (-0.6278019, -0.1220454, 0.2971925) m and at 2 s (-0.4436411, -0.7082700, 0.2109132) m; the settled controller torques [Ctrl/u2](signal:Ctrl/u2) = -45.85 N·m and [Ctrl/u3](signal:Ctrl/u3) = -17.83 N·m; torque limits (150 N·m for joints 1 to 3, 28 N·m for 4 to 6); tracking errors bounded; no W201, E101, E102, E103, E106, E007 or W206.
@@ page arm notes overview | Solver and tolerance
# Solver and tolerance

The solver is set to `Rodas5P`. With `solver = "auto"` (automatic stiff/non-stiff switching) the run exhausts its $10^6$ steps at $t = 0.485$ s (E901, MaxIters): the $k_t = 10^7$ held directions make the system stiff and the default switching algorithm does not get through it. `Rodas5P` takes 8973 steps for the 2 s run. At `reltol` 1e-9 / `abstol` 1e-11 (the J-MB10 setting) a 2.5 s run took 43711 steps and 178 s of solve time; 1e-6 / 1e-8 is enough here because the checks are at the 1e-4 level. The cost per step (about 13 ms) is the Jacobian of the 72-state, 2339-equation system, so the horizon is kept at 2 s; `expected.json` sets `run_timeout` to 900 s.
@@ figures rrr
{
  "diagram": {"kind": "diagram", "model": "rrr"},
  "scene": {"kind": "scene", "model": "rrr", "t": 1.2},
  "run": {
    "kind": "plot", "model": "rrr", "xlim": [0, 5],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Arm/q1", "label": "q1"}, {"signal": "Arm/q2", "label": "q2"}, {"signal": "Arm/q3", "label": "q3"}, {"signal": "Ref1/y", "label": "refs", "style": ":", "color": "#888888"}, {"signal": "Ref2/y", "label": "_nolegend_", "style": ":", "color": "#888888"}, {"signal": "Ref3/y", "label": "_nolegend_", "style": ":", "color": "#888888"}], "legend": true},
      {"ylabel": "tracking error [rad]", "series": [{"signal": "Ctrl/e1", "label": "e1"}, {"signal": "Ctrl/e2", "label": "e2"}, {"signal": "Ctrl/e3", "label": "e3"}], "legend": true},
      {"ylabel": "motor voltage [V]", "series": [{"signal": "Ctrl/u1", "label": "u1"}, {"signal": "Ctrl/u2", "label": "u2"}, {"signal": "Ctrl/u3", "label": "u3"}], "hlines": [{"y": 48}, {"y": -48}], "legend": true}
    ]
  }
}
@@ page rrr overview - | Overview
# RRR arm as an equation block (plan 9.8)

A three-joint arm: a hand-derived Hamiltonian equation block ([Arm](block:Arm), `ArmDynamics3R`) behind three DC motors and 50:1 gears, a 1 ms discrete PD controller with gravity compensation ([Ctrl](block:Ctrl), `ArmCtrl3R`) and minimum-jerk `TimeTable` references ([Ref1](block:Ref1), [Ref2](block:Ref2), [Ref3](block:Ref3)). The same geometry is rebuilt from the spatial multibond stdlib in `rrr-multibond` and compared joint by joint (DEC-M5-2). The six-axis arm is the model `arm`.

![The model canvas|900](@fig:diagram)

```
Ref1..3 (TimeTable) -> Ctrl (ArmCtrl3R, 1 ms) -u_i-> Amp - Motor - Gear (n = 50) -> Arm (ArmDynamics3R: j1 j2 j3)
                          ^                                                              |
                          +------------ q1..3, qd1..3 (Arm outputs) <-------------------+
```

The family of models of this example:

| model | what it is | run |
| --- | --- | --- |
| `rrr` (this model) | `ArmDynamics3R` + 3 x (`VoltageSource` to `DCMotor` to `IdealGear` n = 50) + `ArmCtrl3R` + 3 `TimeTable` | 5 s, solver `auto`, 1e-8 / 1e-10, 2001 points |
| `rrr-free` | the arm alone: zero-torque `Se` on every joint, $g = 0$, released with rates (2, -1.5, 2.5) rad/s; `Arm/E` is the total energy | 5 s, 1e-10 / 1e-12 |
| `rrr-torque` | the arm driven by ideal joint-torque sources (`MSe`) from the same controller and references | 5 s |
| `rrr-multibond` | the same geometry from `Revolute3D` + `RigidBody3D` + `FixedTransform3DNeutral`, same torque sources, controller and references | 5 s, `Rodas5P`, 1e-8 / 1e-10 |
| `rrr-multibond-soft`, `-stiff` | the same with $k_t = k_r = 10^6$ and $10^8$ (the error scaling measurement) | |

## 3D view

`scenes/rrr.sdf` (Z-up, metres) has a base cylinder, a turret link (the joint-1 rotation carrier with a small counterweight so the yaw is visible), an upper-arm box and a forearm box with small spheres marking the point masses. `joint1` has axis $(0, 0, 1)$; `joint2` and `joint3` have axis $(0, -1, 0)$ (rotating $+x$ towards $+z$ is a rotation about $-y$). The models bind `joint:joint1..3` to `Arm/q1..q3`. The picture is taken at 1.2 s, at the end of the first move.

![3D view at t = 1.2 s|500](@fig:scene)

Continue with [the equation block](page:block), [the drives and controller](page:controller) and [the results](page:results).
@@ page rrr block overview | ArmDynamics3R
# The equation block `ArmDynamics3R`

The base yaw $q_1$ is about world $z$ (inertia $J_b$), the shoulder $q_2$ is the elevation of the upper arm above horizontal, the elbow $q_3$ is relative to the upper arm; point masses $m_2$ at the elbow and $m_3$ at the tip. The states are $q$ and the momenta $p = M(q)\,\dot q$; every joint is a `Power{Rotation}` port with `j.f` $= \dot q_i$ and `j.e` $= \tau_i$ into the arm:

$$\dot q = \dot q, \quad p = M\,\dot q, \quad \dot p = \tau + \frac{\partial T}{\partial q} - \frac{\partial V}{\partial q},$$

$$M_{11} = J_b + m_2 r_e^2 + m_3 r_t^2, \quad M_{22} = m_2 l_2^2 + m_3\,(l_2^2 + l_3^2 + 2 l_2 l_3\cos q_3), \quad M_{23} = m_3\,(l_3^2 + l_2 l_3\cos q_3), \quad M_{33} = m_3 l_3^2,$$

with $M_{12} = M_{13} = 0$, and $r_e, z_e, r_t, z_t$ and the three $\partial M/\partial q$ terms and $\partial V/\partial q$ exactly as in the plan. Parameters of [Arm](block:Arm): $l_2 = 0.4$ m, $l_3 = 0.3$ m, $m_2 = 2$ kg, $m_3 = 1$ kg, $J_b = 0.05$ kg·m², $g = 9.81$ m/s². Start $q = (0, 0.6, -0.9)$ rad. The formulas were verified symbolically (a sympy script built $T = \tfrac12 \dot q^T M \dot q$ and $V = g\,(m_2 z_e + m_3 z_t)$ from the geometry and checked $M$, $\partial T/\partial q$, $\partial V/\partial q$ against the plan's expressions; all differences simplify to zero). The total energy $E = \tfrac12 \dot q\cdot p + V$ is a block output (`Arm/E`).
@@ page rrr controller overview | Drives and controller
# Drives and controller

[Ctrl](block:Ctrl) (`ArmCtrl3R`, $T_s = 1$ ms) samples $q$, $\dot q$ and the three references and computes the joint torque command and the motor voltage:

$$t_{c,i} = K_{p,i}\,(\mathrm{ref}_i - q_i) + K_{d,i}\,(\dot r_i - \dot q_i) + \frac{\partial V}{\partial q_i}(q), \qquad \dot r_i = \frac{\mathrm{ref}_i - \mathrm{ref}_i^{prev}}{T_s},$$

$$u_i = \operatorname{clamp}\!\Big(\frac{R\,t_{c,i}}{n\,k_t} + n\,k_t\,\dot q_i,\ -48,\ 48\Big).$$

$\partial V/\partial q$ is the plant's gravity term evaluated at the measured $q$ (a code block, not a copy of the arm), so a settled arm sits exactly on its reference. The motors ([Motor1](block:Motor1) to `Motor3`) have $R = 1\ \Omega$, $L = 0.5$ mH, $k_t = 0.1$ N·m/A, $J_m = 10^{-5}$ kg·m² (reflected inertia $n^2 J_m = 0.025$ kg·m² per joint) behind [Gear1](block:Gear1) to `Gear3` ($n = 50$). The gains come from `design/design.py`: critical damping of the decoupled joint at the largest effective inertia $M_{ii} + n^2 J_m$ over the workspace, $\omega_n = 20$ rad/s:

| joint | 1 | 2 | 3 |
| --- | --- | --- | --- |
| $K_p$ (N·m/rad) | 354 | 334 | 46 |
| $K_d$ (N·m·s/rad) | 35.4 | 33.4 | 4.6 |

$t_{c,i}$ is also an output of the block, which the torque-source models use. The references are `TimeTable`s (linear interpolation, 50 ms sample time) of two minimum-jerk moves $q(t) = q_0 + (q_1 - q_0)(10 s^3 - 15 s^4 + 6 s^5)$: from $(0, 0.6, -0.9)$ to $(1.2, 1.0, -0.4)$ over 0.2 to 1.2 s, and then to $(-0.6, 0.3, -1.3)$ over 1.8 to 3.0 s. `design/design.py` generates the tables and also integrates a numpy RK4 **replica of the whole sampled closed loop** (plant, motor electrics, gears, controller) that the checks compare the Julia run with. `design/build_models.py` writes the model documents.
@@ page rrr results overview | Results and checks
# Results and checks

![Joint angles, tracking errors and motor voltages of the RRR arm|900](@fig:run)

| check | measured (README) |
| --- | --- |
| tracking error after the moves settle (plan: below 0.01 rad), from 4.0 s | 1.5e-8, 9.1e-9, 2.0e-8 rad; from 3.5 s: 1.2e-5, 1.5e-6, 1.5e-5 rad |
| tracking error during the moves | 0.0145, 0.0088, 0.0203 rad |
| peak motor voltage (limit 48 V) | 14.8, 6.6, 6.6 V |
| Julia run against the numpy closed-loop replica, `Arm/q1..q3` over the whole run | 6.4e-11, 5.6e-11, 1.7e-9 rad |
| diagnostics | W201 only: the motor rotors behind the rigid gears are derivative-causal with the arm inertia (the reduction handles it) |

One detail of the replica: the Julia run holds the controller output at its default (0 V) through the first period, so the first command lands at 1 ms; the replica does the same (`first_tick = 1`); with the command at $t = 0$ it differs by 4e-4 rad during the first 0.2 s.
@@ figures rrr-free
{
  "diagram": {"kind": "diagram", "model": "rrr-free"},
  "run": {
    "kind": "plot", "model": "rrr-free", "xlim": [0, 5],
    "rows": [
      {"ylabel": "joint rate [rad/s]", "series": [{"signal": "Arm/qd1", "label": "qd1"}, {"signal": "Arm/qd2", "label": "qd2"}, {"signal": "Arm/qd3", "label": "qd3"}], "legend": true},
      {"ylabel": "total energy Arm/E [J]", "series": [{"signal": "Arm/E", "label": "Arm/E", "color": "#1b9e77"}], "ylim": [1.7, 1.84], "legend": true}
    ]
  }
}
@@ page rrr-free overview - | Overview
# RRR arm without motors: energy conservation

The energy test of plan 9.8: [Arm](block:Arm) (`ArmDynamics3R`) with the motors removed (zero-torque `Se` on every joint: [Free1](block:Free1), [Free2](block:Free2), [Free3](block:Free3)) and $g = 0$, released with the joint rates $(2, -1.5, 2.5)$ rad/s (the start momenta of the block). The total energy $E = T + V$ is the block output [Arm/E](signal:Arm/E) and must stay constant. The block and the full model are described in the `rrr` model.

![The model canvas|900](@fig:diagram)

![Free motion: joint rates and total energy|900](@fig:run)

Measured (README): $\max\lvert E - E_0\rvert/\max\lvert E\rvert = 3.2\cdot10^{-13}$ over 5 s (the plan asks below 1e-6), with $E_0 = 1.769789$ J (absolute drift 5.6e-13 J), and the free motion agrees with the numpy RK4 replica to 3.1e-12 rad in $q$ after 5 s. The run uses `reltol` 1e-10, `abstol` 1e-12 and 1001 points.
@@ figures rrr-torque
{
  "diagram": {"kind": "diagram", "model": "rrr-torque"},
  "run": {
    "kind": "plot", "model": "rrr-torque", "xlim": [0, 5],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Arm/q1", "label": "q1"}, {"signal": "Arm/q2", "label": "q2"}, {"signal": "Arm/q3", "label": "q3"}], "legend": true},
      {"ylabel": "torque command [N m]", "series": [{"signal": "Ctrl/tc1", "label": "tc1"}, {"signal": "Ctrl/tc2", "label": "tc2"}, {"signal": "Ctrl/tc3", "label": "tc3"}], "legend": true}
    ]
  }
}
@@ page rrr-torque overview - | Overview
# RRR arm with ideal torque sources

The equation-block arm [Arm](block:Arm) driven by ideal joint-torque sources ([Drive1](block:Drive1), [Drive2](block:Drive2), [Drive3](block:Drive3), `MSe` with gain 1) from the same `ArmCtrl3R` firmware ([Ctrl](block:Ctrl)) and the same `TimeTable` references as `rrr-multibond`. It is the comparison partner of the multibond arm (DEC-M5-2): a clean comparison needs the plants to be the only difference, and the motors cannot be shared because a rotor inertia rigidly coupled to the multibond joint's rate is derivative-causal with the body inertia; the multibond arm behind the `DCMotor` and `IdealGear` chain compiled with W201 on every body momentum and then stopped at $t = 0$ with E901 (retcode `Unstable`), measured. The controller's `tc` output (joint torque command, [Ctrl/tc1](signal:Ctrl/tc1)) drives the sources.

![The model canvas|900](@fig:diagram)

![Joint angles and torque commands|900](@fig:run)

The closed loop pulls both arms to the same references, so the comparison is of the dynamics under the same feedback. This model is the reference for the `compare` checks of `rrr-multibond`; see that model for the tolerances. The run lasts 5 s with `reltol` 1e-8, `abstol` 1e-10 and 2001 points.
@@ figures rrr-multibond
{
  "diagram": {"kind": "diagram", "model": "rrr-multibond"},
  "run": {
    "kind": "plot", "model": "rrr-multibond", "xlim": [0, 5],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "J1/qout", "label": "q1"}, {"signal": "J2/qout", "label": "q2"}, {"signal": "J3/qout", "label": "q3"}], "legend": true},
      {"ylabel": "tracking error [rad]", "series": [{"signal": "Ctrl/e1", "label": "e1"}, {"signal": "Ctrl/e2", "label": "e2"}, {"signal": "Ctrl/e3", "label": "e3"}], "legend": true}
    ]
  }
}
@@ page rrr-multibond overview - | Overview
# RRR arm on the spatial multibond stdlib

The same three-joint arm as `rrr-torque`, built from the M3 spatial stdlib following the patterns of the six-axis `arm`, driven by the same torque sources, controller and references (DEC-M5-2). The two are compared joint by joint.

![The model canvas|900](@fig:diagram)

## Construction

- a base body (1 kg at the pivot, isotropic inertia $J_b$ = 0.05 kg·m², so its yaw inertia is the plan's $J_b$; [B1](block:B1)) on a compliant `Revolute3D` about world $z$ ([J1](block:J1));
- joints 2 and 3 about world $-y$: the joint frame is $R_x(90^\circ)$ (local $z = -y$), so a positive $q$ raises the arm; `LN2` places joint 2 at the shoulder, `LN3` places joint 3 $l_2$ along the upper arm, `T2` and `T3` are $LN^{-1}\circ LC$;
- point masses as `RigidBody3D` bodies ($m_2$ at the elbow, $m_3$ at the tip, $10^{-8}$ kg·m² principal moments because a point has none), links $l_2$ and $l_3$ as `FixedTransform3DNeutral`; the body poses for gravity come from a `ComposePose3D` chain as in the six-axis arm;
- held directions $k_t = k_r = 10^7$ with 0.7-critical damping, released on their **static deflections** (`dth`, `dl` from the weight of everything distal; `design/build_models.py`);
- the settings: 5 s with `Rodas5P`, `reltol` 1e-8, `abstol` 1e-10, 2001 points.

The joint angles are [J1/qout](signal:J1/qout), [J2/qout](signal:J2/qout), [J3/qout](signal:J3/qout); the controller [Ctrl](block:Ctrl) is the `ArmCtrl3R` of `rrr` (gains 354/334/46 and 35.4/33.4/4.6).

![Joint angles and tracking errors of the multibond arm|900](@fig:run)

## Tolerance of the comparison

The difference between the models is the compliance of the held directions (and the $10^{-8}$ point-mass inertias), an $O(1/k)$ effect: the static sag $m g/k$ of the held translations (3 to 4e-6 m at $k = 10^7$) moves the masses by a fraction of a link length. The maximum difference $\max\lvert\Delta q\rvert$ over the whole 5 s motion (the `compare` entries of `expected.json`, bound $C_i/k$ with $C = 820, 500, 250$ N·m/rad, 5x the measurement at $k = 10^7$):

| $k$ (N/m, N·m/rad) | joint 1 | joint 2 | joint 3 |
| --- | --- | --- | --- |
| $10^6$ (`rrr-multibond-soft`) | 1.11e-4 | 4.4e-5 | 2.7e-5 |
| $10^7$ (`rrr-multibond`) | 1.64e-5 | 1.00e-5 | 4.98e-6 |
| $10^8$ (`rrr-multibond-stiff`) | 1.81e-6 | 1.32e-6 | 6.7e-7 |

The error falls with $k$ (ratios of 4 to 9.5 per decade; the soft case carries second-order terms, and the largest joint 2 and 3 values sit in the first millisecond, when the arm is released and the controller's first command is still to come). From 0.1 s on, joints 2 and 3 differ by 2.4e-5 / 2.7e-5, 4.0e-6 / 3.5e-6 and 5.4e-7 / 4.3e-7 rad at the three stiffnesses. The settled values agree to 1e-8 rad.

The run times in the README (loaded machine, including the first compile) are 224 s for `rrr-multibond`, 103 s for `-soft` and 114 s for `-stiff`.
@@ figures rrr-multibond-soft
{
  "diagram": {"kind": "diagram", "model": "rrr-multibond-soft"}
}
@@ page rrr-multibond-soft overview - | Overview
# Soft held directions ($k = 10^6$)

The `rrr-multibond` arm with all held directions ten times softer: $k_t = k_r = 10^6$ (N/m and N·m/rad), damping scaled with it (for example `bt` = 2800 for [J1](block:J1) against 8854 at $10^7$) and the static deflection starts scaled by ten. Everything else is as in `rrr-multibond`. It exists for the error-scaling measurement: the maximum joint-angle difference to the `rrr-torque` arm is 1.11e-4, 4.4e-5 and 2.7e-5 rad for joints 1 to 3 (see the table of the `rrr-multibond` model), ten times the stiff-case order. Plot [J1/qout](signal:J1/qout) and compare with the other stiffnesses.

![The model canvas|900](@fig:diagram)
@@ figures rrr-multibond-stiff
{
  "diagram": {"kind": "diagram", "model": "rrr-multibond-stiff"}
}
@@ page rrr-multibond-stiff overview - | Overview
# Stiff held directions ($k = 10^8$)

The `rrr-multibond` arm with all held directions ten times stiffer: $k_t = k_r = 10^8$, damping scaled with it (for example `bt` = 28000 for [J1](block:J1)) and the static deflection starts scaled by a tenth. Everything else is as in `rrr-multibond`. The maximum joint-angle difference to the `rrr-torque` arm is 1.81e-6, 1.32e-6 and 6.7e-7 rad for joints 1 to 3 (see the table of the `rrr-multibond` model). Plot [J1/qout](signal:J1/qout) and compare.

![The model canvas|900](@fig:diagram)
