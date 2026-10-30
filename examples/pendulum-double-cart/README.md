# pendulum-double-cart — a double pendulum on a belt-driven cart: swing-up, catch, balance and recovery

A cart on a ±0.40 m rail carries a double pendulum. A DC motor drives the cart through a gearbox and a belt
on a pulley; the two pendulum joints are **passive**. The plant is a planar multibond bond graph
(`stdlib:planar/*`, `stdlib:multibond/*`), the controller a 1 kHz firmware. The run starts with everything
hanging down at rest, swings the pendulum up with an offline-optimised trajectory, catches it with an LQR,
and hits the tip link with a force pulse after 3.5 s of stable balance. It is the cart version of the
pendulum family (X5.11 fixed pivot, X5.12 cart, X5.13 rotary base) and the planar-multibond counterpart of
`inverted-pendulum-cart` (which uses a point-mass equation-style bond graph and a single pole).

| time | phase (`Ctrl/phase`) | what happens |
| --- | --- | --- |
| 0 – 1 s | 0, hold | hanging at rest, motor voltage 0 (checked: nothing moves) |
| 1 s | 1, swing-up | trajectory feed-forward from the offline optimisation, tracked by a time-varying LQR (TVLQR) |
| 3.4 s | 2, balance | after T_s = 2.4 s the nominal ends upright; the 1 kHz discrete LQR takes over |
| 7.0 s | 2 | 40 ms, 0.28 N force pulse on the tip link |
| to 12 s | 2 | recovery, then 3 s of quiet balance |

## Rig (assumed values)

There is no published data for a belt-driven double pendulum rig of this size, so the values are assumed
(`design/design.py`, the single place they are set):

| part | value |
| --- | --- |
| cart | 0.8 kg carriage, J = 1.5e-3 kg m², rail travel ±0.40 m |
| link 1, link 2 | aluminium rods 0.25 m, 0.10 kg / 0.08 kg, centre of mass at the middle, J = m L²/12, joint friction 2e-4 N m s/rad |
| motor | 24 V supply limit, R = 1.5 Ω, L = 0.5 mH, k_t = k_e = 0.0302 N m/A, rotor 1.4e-5 kg m², bearing loss 2e-6 N m s/rad (a 90 W-class brushed servo) |
| transmission | 3:1 gearbox, 16 mm pulley radius, belt 4e5 N/m with 60 N s/m |
| derived | force per volt 3.77 N/V, stall force 90 N, rotor inertia reflected to the cart 0.49 kg |

## Plant (bond graph)

```
Ground -- Rail(Prismatic2D) -- CartJ(1) -- Cart(RigidBody2D)
              |                  `-- Joint1 -- Link1 -- N1(1) -- Body1(RigidBody2D)
         drive (Translation)                      `-- Joint2 -- Link2 -- N2(1) -- Body2(RigidBody2D) -- Push
Motor(ElectricDrive) -- Gear -- Pulley(RackAndPinion) -- Belt(SpringDamper) -- Rail.drive
```

- **Bodies**: `RigidBody2D` (mass, inertia about the centre of mass, Coriolis, gravity) for the cart and each
  rod; the rods' centre of mass is a `FixedJoint2D` (`Link`) away from the pivot.
- **Joints**: the cart is a `Prismatic2D` (exact translation along x, stiff in rotation and in the
  perpendicular direction); the links are `Revolute2DCompliant` joints whose pivot translations are very stiff
  springs (`kt = 1e8 N/m`, `bt = 1e3 N s/m`) and whose `b` is the viscous joint friction. That is the DEC-MB-2 route
  to a (practically) rigid revolute joint on a 3-DOF body: the angle is exact, every state stays integral, no
  W201, and the trajectory error is O(1/kt). The passive joints' drive ports close on `Se` with `e = 0`.
- **Drive**: `ElectricDrive` (winding resistance and inductance, back-EMF, rotor inertia) → `Gearbox` →
  `RackAndPinion` (the pulley) → `SpringDamper` (the belt) → the rail's force port. The belt keeps the rotor
  inertia from being a derivative-causal store; domain-concrete ports are joined by wires, junctions by bonds.
- **Poses** are composed, never integrated (`ComposePose2D`/`LocalPose2D`); gravity reads the composed pose.
- **Disturbance**: `ExternalWrenchPlanar` (`Push`) on the tip link's 1-junction, fed by a `Pulse` source: a
  force perpendicular to the link and its moment about the centre of mass (lever L − c).
- **Bond directions matter.** A bond's half arrow sets the sign of the junction equations, so every joint's
  `parent` port is bonded *towards* the junction of the body it hangs from (`Joint.parent → N`). Bonded the
  other way (junction → `parent`) the reaction forces of the joint on a *moving* parent (the cart) have the
  wrong sign; a fixed base cannot show it.

## Design (`design/design.py`, `uv run`, CasADi + IPOPT + SciPy)

`design/cartpend.py` holds the maths shared with `pendulum-triple-cart`; `design/design.py` sets the parameters.

1. **Design model**: the Lagrangian of the same mechanism, states `[x, θ1, θ2, ẋ, θ̇1, θ̇2]` (θ absolute from
   upright), motor force `F = αV − βẋ` with the armature inductance neglected and the rotor inertia reflected
   (`m_eff = 1.29 kg`). 
2. **Trajectory optimisation**: Hermite-Simpson direct collocation (60 intervals, T_s = 2.4 s), IPOPT, minimum
   `∫V² dt` from hanging to upright at rest, **|x| ≤ 0.30 m** (rail ±0.40 m) and **|V| ≤ 16 V** as constraints.
   Result: peak feed-forward 12.9 V, cart reaches ±0.278 m.
3. **TVLQR**: the Riccati equation integrated backward along the trajectory from the infinite-horizon solution,
   Q = diag(300, 400, 400, 10, 8, 8), R = 0.3 V⁻².
4. **Balance LQR**: discrete (ZOH, 1 ms) LQR with the same weights.
5. `--write` writes the tables into `library/DoubleCartTraj.jl` (continuous lookup, because `interp1` is an
   equation-scope intrinsic) and the gains into `library/DoubleCartCtrl.jl` (the `@discrete Ts = 1e-3`
   firmware: phase latch, TVLQR, LQR, clamp ±24 V) and generates `models/*.bgmodel.json` through
   `design/cartmodel.py`.
6. `design/docsgen.py` + `design/build_docs.py` write `models/pendulum-double-cart.docs/` from two real runs.

```
uv run examples/pendulum-double-cart/design/design.py --write
uv run examples/pendulum-double-cart/design/design.py --compare-free <run dir of pendulum-double-cart-free>
uv run examples/pendulum-double-cart/design/build_docs.py <run dir of the full model> <run dir of the free model>
```

## Results (real worker, Rodas5P, reltol 1e-8)

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| design vs bond graph, free swing 2 s (max angle difference / cart) | **7.1e-4 rad** / 1.9e-5 m | — |
| at rest before 1 s | exactly (0 motion) | |
| swing-up time (all links inside 2° for good) | 1.92 s after the start | |
| catch (phase 2) | 3.40 s | 3.40 s |
| upright band from 0.1 s after the catch to the pulse | 0.0097° (cart 1.1 mm) | 0.011° |
| pulse: peak deflection link 1 / link 2 | 17.8° / 6.0° | 17.8° / 6.0° |
| recovery, inside 1° / 0.5° after the pulse | 0.96 s / 2.11 s | 2.12 s (0.5°) |
| peak motor voltage | 20.06 V of 24 V | 19.84 V |
| peak cart travel | 0.281 m of ±0.40 m | 0.281 m |
| closed loop, max difference design vs bond graph (angles / cart) | 2.8e-3 rad / 0.7 mm | |
| compile / run (cold, one Julia process) | 2.2 s / 31 s (72 905 steps, 22 206 rows) | |

## Checks (`expected.json`)

Machine-checked by `uv run examples/run_checks.py --only pendulum-double-cart`: at rest before 1 s; the
phase signal 0 / 1 / 2; swing-up cursors against the design closed loop; every link within 0.2° of upright
from 0.1 s after the catch to the pulse and the cart within 1 cm of the centre; peak deflection after the pulse
(the disturbance is real: 17.8° and 6.0°); back inside 0.5° after the recovery and within 0.2° over the last
second; |V| ≤ 24 V and the cart inside the ±0.40 m rail; the free-swing model against the design ODE at eight
times; `scene_bindings` (the SDF kinematic tree reproduces the composed poses); no diagnostics.

## What to try

- **Plots**: "Link angles from upright" (`Ctrl/th1`, `Ctrl/th2`), "Cart position" (`Rail/qout`), "Motor voltage and
  phase" (`Ctrl/u`, `Ctrl/phase`), "Motor current".
- **3D view**: the cart rides between the red end stops, joints `rail`, `hinge1`, `hinge2` follow `Rail/qout`,
  `Joint1/qout`, `Joint2/qout`.
- Raise `PushPulse/amplitude` above ≈ 0.35 N: the LQR loses the pendulum (design-model limit for a 40 ms pulse).
- Run `pendulum-double-cart-free` to see the design check (motor shorted, released from a non-trivial pose).

## 3D view

`scenes/pendulum-double-cart.sdf` shows the rail with two end stops, the motor and pulleys, the cart and two
links of different colours with joint hubs; the model's x-y plane is the scene's X-Z plane.
