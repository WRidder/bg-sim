@@ figures pendulum-double-fixed
{
 "diagram": {
  "kind": "diagram",
  "model": "pendulum-double-fixed"
 },
 "scene-swing": {
  "kind": "scene",
  "model": "pendulum-double-fixed",
  "t": 2.25
 },
 "scene-up": {
  "kind": "scene",
  "model": "pendulum-double-fixed",
  "t": 6.0
 },
 "run": {
  "kind": "plot",
  "model": "pendulum-double-fixed",
  "width": 1000,
  "rows": [
   {
    "ylabel": "angle from upright [deg]",
    "legend": true,
    "series": [
     {
      "signal": "Upright/a1",
      "label": "Upright/a1",
      "scale": 57.29577951308232
     },
     {
      "signal": "Upright/a2",
      "label": "Upright/a2",
      "scale": 57.29577951308232
     }
    ],
    "vlines": [
     {
      "x": 1.0,
      "label": "swing-up starts"
     },
     {
      "x": 7.0,
      "label": "disturbance"
     }
    ]
   },
   {
    "ylabel": "motor voltage [V]",
    "legend": true,
    "series": [
     {
      "signal": "Ctrl/u",
      "label": "Ctrl/u",
      "color": "#1b9e77"
     }
    ],
    "hlines": [
     {
      "y": 12.0,
      "label": "supply limit 12 V"
     },
     {
      "y": -12.0
     }
    ]
   },
   {
    "ylabel": "controller phase",
    "series": [
     {
      "signal": "Ctrl/phase",
      "label": "Ctrl/phase",
      "color": "#7570b3"
     }
    ]
   }
  ]
 },
 "swing": {
  "kind": "plot",
  "model": "pendulum-double-fixed",
  "xlim": [
   0.8,
   4.3
  ],
  "width": 1000,
  "rows": [
   {
    "ylabel": "angle from upright [deg]",
    "legend": true,
    "series": [
     {
      "signal": "Upright/a1",
      "label": "Upright/a1",
      "scale": 57.29577951308232
     },
     {
      "signal": "Upright/a2",
      "label": "Upright/a2",
      "scale": 57.29577951308232
     }
    ]
   },
   {
    "ylabel": "motor voltage [V]",
    "series": [
     {
      "signal": "Ctrl/u",
      "label": "Ctrl/u",
      "color": "#1b9e77"
     }
    ],
    "hlines": [
     {
      "y": 12.0
     },
     {
      "y": -12.0
     }
    ],
    "vlines": [
     {
      "x": 3.302,
      "label": "catch at 3.30 s"
     }
    ],
    "legend": true
   }
  ]
 },
 "dist": {
  "kind": "plot",
  "model": "pendulum-double-fixed",
  "xlim": [
   6.5,
   10.0
  ],
  "width": 1000,
  "rows": [
   {
    "ylabel": "angle from upright [deg]",
    "legend": true,
    "series": [
     {
      "signal": "Upright/a1",
      "label": "Upright/a1",
      "scale": 57.29577951308232
     },
     {
      "signal": "Upright/a2",
      "label": "Upright/a2",
      "scale": 57.29577951308232
     }
    ]
   },
   {
    "ylabel": "motor voltage [V]",
    "series": [
     {
      "signal": "Ctrl/u",
      "label": "Ctrl/u",
      "color": "#1b9e77"
     }
    ]
   },
   {
    "ylabel": "tip force [N]",
    "series": [
     {
      "signal": "DistForce/y",
      "label": "DistForce/y",
      "color": "#d95f02"
     }
    ]
   }
  ]
 },
 "free": {
  "kind": "plot",
  "model": "free",
  "width": 1000,
  "rows": [
   {
    "ylabel": "joint angle [rad]",
    "legend": true,
    "series": [
     {
      "signal": "Joint1/qout",
      "label": "Joint1/qout"
     },
     {
      "signal": "Joint2/qout",
      "label": "Joint2/qout"
     }
    ]
   }
  ]
 }
}
@@ page pendulum-double-fixed overview - | Overview
# Double pendulum on a fixed pivot

A planar double pendulum hangs from a fixed pivot. A DC gearmotor drives the **first joint only** (the pendubot arrangement); the other 1 joint is passive. The chain starts hanging straight down at rest with 0 V on the motor, swings up along an optimised trajectory, is caught by an LQR near the upright, balances, and recovers from a force pulse at the tip link.

![The model canvas|900](@fig:diagram)

## Scenario

| time | phase | what happens |
| --- | --- | --- |
| 0 to 1 s | 0 | hanging at rest, voltage 0 ([Ctrl/phase](signal:Ctrl/phase) = 0), nothing moves |
| 1 s | 1 | the swing-up starts: feed-forward voltage from the trajectory optimisation plus time-varying LQR feedback |
| 3.30 s | 2 | the state enters the LQR region ($V(x) < 3.3$): the balance LQR takes over (the trajectory ends at 3.5 s) |
| 7 s | 2 | a 0.4 N force pulse of 50 ms hits the tip link ([DistForce/y](signal:DistForce/y)) |
| 8.05 to 10.55 s | 2 | back at upright: every link inside 1 deg from 8.04 s on |

The chain is built as a **multibond bond graph**: [Body1](block:Body1), [Body2](block:Body2) are `RigidBody2D` composites with a mass and an inertia about the centre of mass, joined by `Revolute2DCompliant` joints ([Joint1](block:Joint1), [Joint2](block:Joint2)). The motor ([Motor](block:Motor)), the shaft ([Shaft](block:Shaft)) and the gearbox ([Gear](block:Gear)) are stdlib drive blocks; the controller [Ctrl](block:Ctrl) is project firmware sampled at 1 kHz.

![Mid swing-up|600](@fig:scene-swing)

![Balanced before the disturbance|600](@fig:scene-up)

## Pages

- [The multibond structure](page:structure): blocks, bonds, poses and the drive train.
- [Equations of motion](page:dynamics): the design model, the parameters and the check against the bond graph.
- [Trajectory optimisation](page:trajectory): the direct-collocation formulation of the swing-up.
- [TVLQR and LQR](page:control): the feedback around the trajectory, the catch rule and the balance.
- [Results](page:results): plots of the run and the acceptance checks.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Upright/a1](signal:Upright/a1) and the others) shows the swing-up, the catch and the recovery; "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) the use of the supply.
- Raise `DistForce/amplitude` and `DistTorque/amplitude` together (the torque is the force times the 0.18 m lever arm to the tip): the recovery needs more voltage, and a large enough pulse saturates the 12 V supply and tips the chain over.
- Open the **3D View** tab to watch the swing-up; the joint bindings follow the joint angles.
- Change a link mass without re-running `design/design.py`: the gains are matched to the design plant, which shows the margin of the design.
@@ page pendulum-double-fixed structure overview | The multibond structure
# The multibond structure

Planar multibond elements (`stdlib:planar/*`, `stdlib:multibond/*Planar`) carry a three-component twist and wrench $(\omega, v_x, v_y)$ on every bond. The power path is a chain of bonds from the ground to the last link:

```
Ground ─ Joint1 ─ Link1 ─ BodyJ1 ─ Joint2 ─ Link2 ─ BodyJ2
```

| instance | block | role |
| --- | --- | --- |
| [Ground](block:Ground) | `stdlib:multibond/GroundPlanar` | world flow source, $f = 0$ |
| [Joint1](block:Joint1) | `stdlib:planar/Revolute2DCompliant` | joint 1: pivot at $r_x = 0$ m in the parent CoM frame, `kt` = 1e8 N/m, `bt` = 2000 N·s/m, viscous friction $b = 0.002$ N·m·s/rad; drive: the motor drive port (rotation), see below |
| [Link1](block:Link1) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass of link 1, $x = 0.15$ m |
| [BodyJ1](block:BodyJ1) | 1-junction | the common twist of link 1: its body and the next joint |
| [Body1](block:Body1) | `stdlib:planar/RigidBody2D` | $m = 0.22$ kg, $J = m L^2/12 = 0.00165$ kg·m², $L = 0.3$ m |
| [Joint2](block:Joint2) | `stdlib:planar/Revolute2DCompliant` | joint 2: pivot at $r_x = 0.15$ m in the parent CoM frame, `kt` = 1e8 N/m, `bt` = 2000 N·s/m, viscous friction $b = 0.0008$ N·m·s/rad; drive: a zero-torque `Se` (**passive joint**) |
| [Link2](block:Link2) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass of link 2, $x = 0.18$ m |
| [BodyJ2](block:BodyJ2) | 1-junction | the common twist of link 2: its body and the disturbance source |
| [Body2](block:Body2) | `stdlib:planar/RigidBody2D` | $m = 0.14$ kg, $J = m L^2/12 = 0.001512$ kg·m², $L = 0.36$ m |
| [Motor](block:Motor) | `stdlib:drives/ElectricDrive` | DC motor: $R_w$ = 2.5 Ω, $L$ = 0.5 mH, $k_t$ = 0.03 N·m/A, rotor $J_m$ = 5e-06 kg·m² |
| [Shaft](block:Shaft) | `stdlib:rotation/ElasticShaft` | the drive-train compliance $k$ = 5000 N·m/rad, $d$ = 0.2 N·m·s/rad on the motor side |
| [Gear](block:Gear) | `stdlib:drives/Gearbox` | ideal ratio $N = 5$ (motor rate $= N\,\dot q_1$) |
| [Hit](block:Hit) | `stdlib:multibond/ExternalWrenchPlanar` | the disturbance wrench on the last link, from [DistTorque](block:DistTorque), [DistAxial](block:DistAxial) and [DistForce](block:DistForce) (`stdlib:sources/Pulse`) |
| [Ctrl](block:Ctrl) | `project:DoublePendCtrl` | the 1 kHz firmware: swing-up, catch, balance; [Clock](block:Clock) supplies the time |
| [Upright](block:Upright) | inline block | the absolute link angles from upright, $a_k = q_1 + \dots + q_k - \pi/2$ |

## Joints

A rigid revolute on a three-degree-of-freedom body is index 3 (the two pivot translations are hard constraints; `Revolute2DRigid` ends in a derivative-causal DAE that does not run). `Revolute2DCompliant` keeps the **rotation exact** and lets the two pivot translations be stiff spring-dampers ($k_t = 10^8$ N/m): the pivot moves by about $m g / k_t \approx 10^{-8}$ m, and the free-swing check below shows the plant agrees with the rigid design model to 2.9e-06 rad over a 3 s swing. All states are integral, so the run reports no W201.

The joint angle `q` of joint 1 is the absolute angle of link 1 (hanging: $-\pi/2$, upright: $+\pi/2$); the angles of the other joints are relative, so the absolute angle of link $k$ is $\theta_k = q_1 + \dots + q_k$.

## Poses and gravity

The poses are composed, never integrated: `JointPose2D` turns a joint angle into an SE(2) pose, `LocalPose2D` holds the constant offsets and `ComposePose2D` multiplies them along the chain ([PoseB1](block:PoseB1), [PoseB2](block:PoseB2), [PoseTip](block:PoseTip)). Each `RigidBody2D` reads its world pose to resolve gravity in the body frame, so the weight acts at the true centre of mass.

## Drive train

[Motor](block:Motor) turns the voltage $u$ from [Ctrl](block:Ctrl) into a shaft torque; [Shaft](block:Shaft) is a stiff elastic shaft that keeps the rotor inertia integral-causal (an ideal gear between the rotor and a joint that imposes its rate would give a derivative-causal pair); [Gear](block:Gear) multiplies the torque by $N = 5$ and the rotor inertia appears at the joint as $N^2 J_m = 0.000125$ kg·m². The joint carries the reaction torque, so the motor housing is the fixed base. Taps: the winding current [Motor/isense/y](signal:Motor/isense/y), the motor speed [Motor/wsense/y](signal:Motor/wsense/y).

## Bond direction

Every bond of the chain points from the port into the junction (`Joint.parent → BodyJ`, `Link.child → BodyJ`, `Body.p → BodyJ`, `Hit.p → BodyJ`). The direction is the power orientation of the bond; reversing one of them flips the sign convention of that junction and the pendulum no longer matches its equations of motion.
@@ page pendulum-double-fixed dynamics overview | Equations of motion
# Equations of motion

With $q = (q_1, \dots, q_2)$ the joint angles, link $k$ has the absolute angle $\theta_k = \sum_{j \le k} q_j$, its centre of mass at $c_k = p_k + \ell_k (\cos\theta_k, \sin\theta_k)$ and the next pivot at $p_{k+1} = p_k + L_k (\cos\theta_k, \sin\theta_k)$. The kinetic and potential energy are

$$T = \sum_k \tfrac12 m_k \lVert \dot c_k \rVert^2 + \tfrac12 J_k \dot\theta_k^2 + \tfrac12 N^2 J_m \dot q_1^2, \qquad V = \sum_k m_k g\, c_{k,y},$$

and the Lagrange equations give

$$M(q)\,\ddot q + c(q, \dot q) + g(q) = \tau, \qquad \tau_1 = N k_t\, i - b_1 \dot q_1, \quad \tau_k = -b_k \dot q_k \ (k \ge 2).$$

The motor current follows $L\,\dot i = u - R_w\, i - N k_t\, \dot q_1$. The design neglects $L$ for the optimisation and the LQR ($L/R_w = 0.20$ ms), so $i = (u - N k_t \dot q_1)/R_w$ and the input enters through

$$\tau_1 = \frac{N k_t}{R_w}\,u - \frac{N^2 k_t^2}{R_w}\,\dot q_1 - b_1 \dot q_1 ,$$

a torque proportional to the voltage and a back-EMF damping. The sampled-data simulation in `design.py` that predicts the whole run keeps the winding inductance.

## Parameters

The values are assumed (no datasheet part); the links are aluminium rods with the centre of mass at the middle.

| link | $m$ [kg] | $L$ [m] | $\ell$ [m] | $J = m L^2/12$ [kg·m²] | $b$ [N·m·s/rad] |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.22 | 0.3 | 0.15 | 0.00165 | 0.002 |
| 2 | 0.14 | 0.36 | 0.18 | 0.001512 | 0.0008 |

Motor and drive: $R_w = 2.5\ \Omega$, $L = 0.5$ mH, $k_t = 0.03$ N·m/A, $J_m = 5e-06$ kg·m², gear ratio $N = 5$, supply limit $\pm 12$ V (stall torque at the joint $N k_t U/R_w = 0.72$ N·m). Gravity $g = 9.81$ m/s².

## Linearisation at upright

With the state $x = (q_1 - \pi/2, q_2, \dots, \dot q_1, \dots)$ the open-loop poles at upright are $-12.22, -4.91, 4.72, 10.75$ s$^{-1}$: 2 unstable poles (up to 10.8 s$^{-1}$). Because only joint 1 is driven, the passive links are stabilised through the dynamic coupling.

## Check against the bond graph

`models/free.bgmodel.json` is the same plant with the motor terminals at 0 V, started at the non-trivial angles $-0.3708, 1.0000$ rad. `design.py --compare` integrates the design ODE (the full model with the winding current, Radau, tolerance $10^{-11}$) from the same start and compares it with the bond-graph run: the maximum difference of any joint angle over the 3 s swing is **2.91e-06 rad**, and `expected.json` repeats the comparison at six times. ![Free swing of the bond graph|800](@fig:free)

The swing covers a large part of the working range, so this proves the masses, inertias, lengths, gravity, the reflected rotor inertia and the back-EMF damping of the design model.
@@ page pendulum-double-fixed trajectory overview | Trajectory optimisation
# Trajectory optimisation

`design/design.py` computes the swing-up offline by **direct collocation** on the design model, including the motor and its voltage limit. The problem is to move from all links hanging at rest to all links upright at rest in the fixed time $T_s = 2.5$ s:

$$\min_{x(\cdot),\,u(\cdot)} \int_0^{T_s} \Big(\frac{u}{u_{lim}}\Big)^2 + \epsilon\,\lVert \dot q \rVert^2 \, dt \quad \text{s.t.} \quad \dot x = f(x, u),\ \ x(0) = x_{down},\ \ x(T_s) = x_{up},\ \ \lvert u \rvert \le u_{lim},$$

with $x = (q, \dot q)$, $x_{down} = (-\pi/2, 0, \dots, 0)$, $x_{up} = (\pi/2, 0, \dots, 0)$, $u_{lim} = 11$ V (the rest of the 12 V supply is margin for the feedback) and $\epsilon = 10^{-4}$.

**Discretisation.** 100 intervals of $h = 25$ ms. The voltage is piecewise linear between the knots. Each interval carries the Hermite–Simpson defect

$$x_{k+1} - x_k = \tfrac{h}{6}\big(f_k + 4 f_m + f_{k+1}\big), \qquad x_m = \tfrac12 (x_k + x_{k+1}) + \tfrac{h}{8}(f_k - f_{k+1}),\quad u_m = \tfrac12 (u_k + u_{k+1}),$$

which is fourth order in $h$. CasADi builds the exact derivatives of the Lagrangian dynamics; IPOPT solves the resulting nonlinear program (101 knots, 4 states and one input each) in about two seconds from a sinusoidal voltage guess.

**Result.** The optimum uses a peak voltage of 11.00 V (the limit of the problem). The nominal states are the collocation knots, interpolated with a cubic Hermite spline at 1 kHz, not a forward integration: the swing-up is open-loop unstable (poles up to 10.8 s$^{-1}$ amplify a 1e-10 integration error by $e^{27}$ over the trajectory), so only the feedback can follow it.

The trajectory is written into `DoublePendCtrl` as constant tables of 251 rows at 10 ms spacing: the nominal voltage `u_ff`, the nominal states `xr_*` and the time-varying gains `k_*`.
@@ page pendulum-double-fixed control overview | TVLQR and LQR
# TVLQR and LQR

[Ctrl](block:Ctrl) is the project block `DoublePendCtrl` (`library/DoublePendCtrl.jl`), a `@discrete Ts = 1e-3` scope that reads the joint angles and rates and the time and holds the voltage until the next tick.

## Phases

| phase | condition | law |
| --- | --- | --- |
| 0 | $t < t_{on} = 1$ s | $u = 0$ |
| 1 | swing-up, not caught | $u = u_{ff}(\tau) - K(\tau)\,\big(x - x_{ref}(\tau)\big)$, $\tau = t - t_{on}$ |
| 2 | caught (latched) | $u = -K_{lqr}\,(x - x_{up})$ |

The output is clamped to $\pm 12$ V. The table lookup is linear interpolation: the weights are the hat functions $\max(0, 1 - \lvert s - (k-1) \rvert)$ of the row position $s = \tau/\Delta t$ over the rows $k$, and the last row is held after the trajectory.

## Time-varying LQR

Along the nominal trajectory $(x^*, u^*)$ the linearisation is discretised exactly (zero-order hold at 1 ms) at every sample, $x_{k+1} = A_k x_k + B_k u_k$, and the gains come from the backward Riccati recursion

$$K_k = (R + B_k^T S_{k+1} B_k)^{-1} B_k^T S_{k+1} A_k, \qquad S_k = Q + A_k^T S_{k+1} (A_k - B_k K_k),$$

terminated by the Riccati matrix $S_N = P$ of the balance LQR, so the gain schedule ends in the LQR gain. The weights are $Q = \mathrm{diag}(100, 100, 1, 1)$ (angles in rad, rates in rad/s) and $R = 1$ V$^{-2}$.

## Balance LQR

At upright the 1 ms zero-order-hold model gives the discrete Riccati solution $P$ and the gain

$$K_{lqr} = (-99.69,\ -93.59,\ -24.43,\ -13.59)\ \text{ in V/rad and V·s/rad,}$$

for $u = -K_{lqr}(x - x_{up})$. The same $Q$ and $R$ are used for the TVLQR.

## Switching rule

The catch is a state test, not a timer: the first tick of phase 1 at which the LQR cost-to-go $V(x) = (x - x_{up})^T P\,(x - x_{up})$ is below $V_{catch} = 3.3$ latches phase 2 (`caught` is a discrete state of the block). $V_{catch}$ is the value of $V$ on the nominal trajectory 0.2 s before its end, so the LQR takes over inside the region where it is verified to hold the pendulum; the nominal trajectory itself reaches upright at 3.5 s. The block outputs the phase ([Ctrl/phase](signal:Ctrl/phase): 0, 1, 2) and the cost-to-go ([Ctrl/V](signal:Ctrl/V)).

## Disturbance

At $t = 7$ s, 3.7 s after the catch, [Hit](block:Hit) applies a force of 0.4 N for 50 ms to the last link, perpendicular to it at the tip: the force $F$ on the body $y$ axis and the torque $F \cdot 0.18$ m about the centre of mass (the lever arm from the centre of mass to the tip). The balance LQR recovers it with no change of controller.
@@ page pendulum-double-fixed results overview | Results and checks
# Results and checks

![Link angles, motor voltage and controller phase over the whole run|900](@fig:run)

## Swing-up and catch

![Swing-up from hanging, first seconds|900](@fig:swing)

## Disturbance and recovery

![The tip force pulse and the recovery|900](@fig:dist)

## Numbers

The reference numbers are the independent sampled-data integration of `design.py`; the bond-graph run reproduces the link angles to better than 1e-4 rad over the whole scenario.

| quantity | value |
| --- | --- |
| swing-up | starts at 1 s, trajectory time 2.5 s, caught at 3.30 s |
| upright band before the disturbance | 0.0058 deg (all links, from 0.5 s after the catch) |
| disturbance | 0.4 N, 50 ms, at 7 s |
| peak deflection after the pulse | link 1: 16.6 deg, link 2: 8.7 deg |
| recovered (every link inside 1 deg) | from 8.04 s, 1.04 s after the pulse starts |
| peak motor voltage | 11.64 V of 12 V (recovery: 8.29 V) |
| design versus bond graph, free swing | 2.9e-06 rad |

## Acceptance checks (`expected.json`)

- hanging at rest before $t_{on}$: the angles [Upright/a1](signal:Upright/a1)… equal $-\pi$, the joint rates and the voltage [Ctrl/u](signal:Ctrl/u) stay 0, [Ctrl/phase](signal:Ctrl/phase) = 0;
- phase 1 during the swing-up, the catch time from the phase signal, phase 2 before the disturbance; the link angles at a quarter, half and three quarters of the trajectory against `design.py` (2 mrad);
- upright by $t_{on} + T_s = 3.5$ s: every link within 0.2 deg until the disturbance (measured 0.0058 deg);
- the pulse [DistForce/y](signal:DistForce/y) is 0.4 N for 50 ms; the peak deflection of each link after it against `design.py` (5 %), which makes the disturbance a checked, visible event;
- recovered: inside 1 deg from 8.04 s and inside 1e-3 rad over the last second;
- [Ctrl/u](signal:Ctrl/u) within the 12 V supply, [Motor/isense/y](signal:Motor/isense/y) below the stall current 4.8 A;
- model `free`: 2 joint angles at six times against the design ODE (1e-4 rad);
- 3D: every binding resolves and the link poses from the joint bindings equal the composed poses of the model ([PoseB1](block:PoseB1)…, [PoseTip](block:PoseTip)) to 1e-6 m;
- no E901, E106, W201, W202, W205, W206, E101 or E103.

## Reproduce

```
uv run examples/pendulum-double-fixed/design/design.py          # trajectory, gains, library/DoublePendCtrl.jl, expected.json
uv run examples/pendulum-double-fixed/design/build_model.py     # models/*.bgmodel.json and the scene
uv run examples/run_checks.py --only pendulum-double-fixed
```
