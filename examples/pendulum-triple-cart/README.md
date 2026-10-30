# pendulum-triple-cart — a triple pendulum on a belt-driven cart: swing-up, catch, balance and recovery

The `pendulum-double-cart` rig with a third link: a cart on a ±0.40 m rail carries a triple pendulum, driven by a
DC motor through a gearbox and a belt on a pulley; the three pendulum joints are **passive**. The plant is a
planar multibond bond graph (`stdlib:planar/*`, `stdlib:multibond/*`), the controller a 1 kHz firmware. The run
starts with everything hanging down at rest, swings the pendulum up with an offline-optimised trajectory,
catches it with an LQR and hits the tip link with a force pulse after 3.5 s of stable balance. It is the cart
version of the pendulum family (X5.11 fixed pivot, X5.12 cart, X5.13 rotary base).

| time | phase (`Ctrl/phase`) | what happens |
| --- | --- | --- |
| 0 – 1 s | 0, hold | hanging at rest, motor voltage 0 (checked: nothing moves) |
| 1 s | 1, swing-up | trajectory feed-forward from the offline optimisation, tracked by a time-varying LQR (TVLQR) |
| 4.5 s | 2, balance | after T_s = 3.5 s the nominal ends upright; the 1 kHz discrete LQR takes over |
| 8.0 s | 2 | 40 ms, 0.065 N force pulse on the tip link |
| to 14.5 s | 2 | recovery, then 4 s of quiet balance |

## Rig (assumed values)

The cart, rail, motor and transmission of `pendulum-double-cart` (cart 0.8 kg on ±0.40 m, 24 V / 90 W-class motor,
R = 1.5 Ω, k_t = 0.0302 N m/A, 3:1 gearbox, 16 mm pulley, belt 4e5 N/m; force per volt 3.77 N/V, stall 90 N) with
three aluminium rods of 0.25 m and 0.10 / 0.08 / 0.06 kg (centre of mass at the middle, J = m L²/12, joint friction
2e-4 N m s/rad). All values are assumed (`design/design.py`); there is no published rig of this size.

## Plant (bond graph)

```
Ground -- Rail(Prismatic2D) -- CartJ(1) -- Cart(RigidBody2D)
              |                  `-- Joint1 -- Link1 -- N1(1) -- Body1 (RigidBody2D)
         drive (Translation)                      `-- Joint2 -- Link2 -- N2(1) -- Body2
                                                                      `-- Joint3 -- Link3 -- N3(1) -- Body3 -- Push
Motor(ElectricDrive) -- Gear -- Pulley(RackAndPinion) -- Belt(SpringDamper) -- Rail.drive
```

Same elements and conventions as `pendulum-double-cart` (see its README): `RigidBody2D` bodies, a `Prismatic2D`
cart, `Revolute2DCompliant` joints with `kt = 1e8 N/m` pivots and viscous friction `b`, composed poses, an
`ExternalWrenchPlanar` disturbance fed by a `Pulse`, the drive train with the belt as a spring-damper so that no
store is derivative-causal. Bond directions matter: every joint's `parent` port is bonded *towards* the junction
of the body it hangs from.

## Design (`design/design.py`, `uv run`, CasADi + IPOPT + SciPy)

The maths (`cartpend.py`), the model generator (`cartmodel.py`) and the docs writer are shared with the double
pendulum and live in `../pendulum-double-cart/design/`; this folder's `design.py` sets the parameters.

1. **Design model**: the Lagrangian of the same mechanism, 8 states `[x, θ1..θ3, ẋ, θ̇1..θ̇3]`, motor force
   `F = αV − βẋ`, inductance neglected, rotor inertia reflected.
2. **Trajectory optimisation**: Hermite-Simpson direct collocation, **350 intervals of 10 ms** (60 intervals tracked
   badly for this fast system: the swing-up must be integrated finely enough that the TVLQR only has to correct small
   errors), T_s = 3.5 s, IPOPT; minimum `∫V² dt`, **|x| ≤ 0.30 m** (rail ±0.40 m, the bound is active) and **|V| ≤ 16 V**.
   Peak feed-forward 13.0 V.
3. **TVLQR** along the trajectory, Q = diag(300, 400, 400, 400, 10, 8, 8, 8), R = 3 V⁻²; **balance LQR**: discrete
   (ZOH, 1 ms), same weights.
4. `--write` writes `library/TripleCartTraj.jl` (the 10 ms tables, a continuous `interp1` lookup) and
   `library/TripleCartCtrl.jl` (the `@discrete Ts = 1e-3` firmware: phase latch, TVLQR, LQR, clamp ±24 V) and
   `models/*.bgmodel.json`.

```
uv run examples/pendulum-triple-cart/design/design.py --write
uv run examples/pendulum-triple-cart/design/design.py --compare-free <run dir of pendulum-triple-cart-free>
uv run examples/pendulum-triple-cart/design/build_docs.py <run dir of the full model> <run dir of the free model>
```

## Results (real worker, Rodas5P, reltol 1e-8)

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| design vs bond graph, free swing 1.5 s (max angle difference / cart) | **4.2e-4 rad** / 2.2e-5 m | — |
| at rest before 1 s | exactly (0 motion) | |
| swing-up time (all links inside 2° for good) | 2.38 s after the start | |
| catch (phase 2) | 4.50 s | 4.50 s |
| upright band from 0.1 s after the catch to the pulse | 0.097° (cart 8 mm) | 0.097° |
| pulse: peak deflection link 1 / 2 / 3 | 14.8° / 6.7° / 4.0° | 14.8° / 6.7° / 4.1° |
| recovery, inside 1° / 0.5° after the pulse | 1.36 s / 2.45 s | 2.46 s (0.5°) |
| peak motor voltage | 19.36 V of 24 V | 18.89 V |
| peak cart travel | 0.300 m of ±0.40 m | 0.300 m |
| compile / run (cold, one Julia process) | 2.9 s / 77 s (95 320 steps) | |

The tip deflection is small (4°) because the controller reacts at once; link 1 swings 14.8°. The pulse (0.065 N,
40 ms) is about 80 % of the largest pulse the design closed loop catches.

## Checks (`expected.json`)

`uv run examples/run_checks.py --only pendulum-triple-cart`: at rest before 1 s; the phase signal 0 / 1 / 2;
swing-up cursors against the design closed loop; every link within 0.2° of upright from 0.1 s after the catch to
the pulse and the cart within 1 cm; peak deflection after the pulse (the disturbance is real); back inside 0.5°
after the recovery and within 0.2° over the last second; |V| ≤ 24 V and the cart inside the ±0.40 m rail; the
free-swing model against the design ODE at six times; `scene_bindings`; no diagnostics.

## What to try

- **Plots**: "Link angles from upright" (`Ctrl/th1..th3`), "Cart position", "Motor voltage and phase".
- **3D view**: joints `rail`, `hinge1`, `hinge2`, `hinge3` follow `Rail/qout` and `Joint1..3/qout`.
- Raise `PushPulse/amplitude` above ≈ 0.08 N: the LQR loses the pendulum.
- Run `pendulum-triple-cart-free` to see the design check (motor shorted, released from a non-trivial pose).

## 3D view

`scenes/pendulum-triple-cart.sdf`: the rail with its end stops, motor and pulleys, the cart and three links of
different colours and widths with joint hubs; the model's x-y plane is the scene's X-Z plane.
