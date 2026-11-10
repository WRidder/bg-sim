# bicycle — the Whipple/Carvallo benchmark bicycle: self-stability, a 3D multibond bond graph and a low-speed balance controller

The uncontrolled bicycle of

> J. P. Meijaard, J. M. Papadopoulos, A. Ruina and A. L. Schwab, *Linearized dynamics equations
> for the balance and steer of a bicycle: a benchmark and review*, Proc. R. Soc. A 463 (2007)
> 1955–1982, doi:10.1098/rspa.2007.1857

with the paper's benchmark parameter set (table 1): four rigid bodies (rear frame with a rigid
rider, front fork with handlebar, two knife-edge wheels), hands off, rolling without slip on a
level floor. Between the **weave speed 4.29 m/s** and the **capsize speed 6.02 m/s** the bicycle
balances itself.

| model | what it is |
| --- | --- |
| `whipple` | the full nonlinear bicycle as a **3D multibond bond graph** (four `RigidBody3D`, three `Revolute3D`, two knife-edge `RollingDisk` tyres), hands off. Started like the paper's figure 4: 4.6 m/s and a lean rate of 0.5 rad/s; the weave dies out. Globals `v` and `phid0` |
| `linear` | the paper's linearised equations `M q'' + v C1 q' + (g K0 + v² K2) q = f` as a signal diagram (integrators, gains, sums), the gains being expressions of the global `v` |
| `balance` | the 3D bicycle at 3 m/s, below the weave speed where it falls over hands off, balanced by a steer torque (LQR on the linear model) and turned by a lean set-point |
| `balance-linear` | the same controller on the linear model |

Everything is generated:

    uv run examples/bicycle/design/design.py        # design.json: matrices, eigenvalues, LQR, references
    uv run examples/bicycle/design/build_model.py   # models/*.bgmodel.json and expected.json
    uv run examples/bicycle/design/build_scene.py   # scenes/bicycle.sdf (straight runs), bicycle-turn.sdf (balance)

## Structure of the 3D model

* **Bodies.** `RearFrame` (rear frame and rider, 85 kg), `Fork` (4 kg), `RearWheel` (2 kg) and
  `FrontWheel` (3 kg), each a `stdlib:spatial/RigidBody3D` in its principal axes at its centre of
  mass (the paper's frame and fork inertias have products of inertia; `design/build_model.py`
  diagonalises them and places the body frames accordingly).
* **Joints.** Three compliant `stdlib:spatial/Revolute3D`: the rear hub, the steer axis (tilted
  18° back, its joint axis pointing *down* the steer axis so that the joint angle is the paper's
  steer angle) and the front hub. `FixedTransform3DNeutral` mounts place the joint frames;
  `LocalPose3D` and `ComposePose3D` compose the fork and wheel poses from the rear frame pose.
  Hub and steer drives are `Se` (zero torque) in the hands-off model and an `MSe` (steer torque)
  in `balance`.
* **Floating base.** The rear frame's pose is the only integrated pose (`PoseIntegrator3D`).
* **Tyres.** Two `stdlib:contact/RollingDisk` with `crown = 0`, i.e. the benchmark's knife-edge
  wheels, on a `ContactSurface`. The contact is compliant (Hertz law) with regularised Coulomb
  friction, so rolling without slip holds up to a creep of a fraction of a millimetre per
  second. The rolling radius is the wheel radius plus the static tyre deflection, so the loaded
  wheel centres sit exactly at the paper's heights.
* **Project blocks** (`library/`): `BikeSense` (measurement only: the paper's lean, steer,
  heading and their rates from the rear frame pose and twist) and `BikeEnergy` (energy book).
  No custom block contains dynamics.

The linear model is a signal diagram, not a bond graph: the benchmark's linearised equations
contain the non-symmetric velocity terms `v C1` and `v² K2` of the nonholonomic rolling
constraint, which are neither storage nor dissipation; written as a bond graph they would be
modulated sources wired to the states, i.e. the same signal diagram in disguise. The 3D bond
graph is the physical model; the linear model is the reference it is checked against.

## Parameters: published or estimated

| parameter | value | source |
| --- | --- | --- |
| wheel base w, trail c, steer axis tilt λ | 1.02 m, 0.08 m, π/10 | Meijaard et al. 2007, table 1 |
| gravity g | 9.81 N/kg | table 1 |
| rear wheel: radius, mass, inertias (I_xx, I_yy) | 0.3 m, 2 kg, (0.0603, 0.12) kg m² | table 1 |
| rear frame + rider: centre of mass (x, z), mass | (0.3, −0.9) m, 85 kg | table 1 |
| rear frame + rider: inertia (I_xx, I_yy, I_zz, I_xz) | (9.2, 11, 2.8, 2.4) kg m² | table 1 |
| fork + handlebar: centre of mass, mass | (0.9, −0.7) m, 4 kg | table 1 |
| fork + handlebar: inertia (I_xx, I_yy, I_zz, I_xz) | (0.05892, 0.06, 0.00708, −0.00756) kg m² | table 1 |
| front wheel: radius, mass, inertias | 0.35 m, 3 kg, (0.1405, 0.28) kg m² | table 1 |
| tyre contact stiffness k (Hertz, at x_ref = 1 mm) | 10⁶ N/m | **estimate** (numerical stand-in for the rigid knife edge; static deflection 0.72 mm rear, 0.46 mm front) |
| tyre contact damping c (Hunt-Crossley) | 2 s/m | **estimate** |
| tyre friction μ, regularisation v_s | 0.9, 1 mm/s | **estimate** (stand-in for no slip) |
| joint compliance k_r, k_t of the held directions | 10⁶ N m/rad, 10⁶ N/m | **estimate** (library default; stand-in for rigid joints) |
| joint damping b_r, b_t of the held directions | 20 N m s/rad, 500 N s/m | **estimate** (as in the gyrover example) |
| balance controller weights Q, R | diag(100, 10, 10, 1), 1 | **design choice** (`design/design.py`) |

The benchmark is an idealisation: knife-edge wheels, no tyre slip, a rigid rider, no friction.
The contact and joint numbers above are not bicycle data; they only make the bond graph's
constraints stiff enough that it behaves like the ideal model (see the checks).

## Validation data

* **Meijaard et al. 2007, equations (6.1)–(6.4) and table 2** (in `design/meijaard2007_table2.json`,
  transcribed digit for digit). `design/design.py` evaluates the paper's appendix A from the table
  1 parameters and reproduces the printed matrices to 1.4e-14 and the table 2 eigenvalues to
  6e-13, the weave speed 4.292382536341 m/s and the capsize speed 6.024262015388 m/s.
* The **3D bond graph** reproduces the table 2 weave eigenvalues from fitted time responses at 3,
  4, 5 and 6 m/s (unstable and stable weave), the slow capsize growth at 8 m/s (within 0.7 % of the linear model), and agrees
  with the linear model to about 1 % of the motion for a small push at 5 m/s.
* **The paper's figure 4** (nonlinear response at 4.6 m/s from a lean rate of 0.5 rad/s) is the
  start of model `whipple`. The figure is not tabulated, so it is reproduced qualitatively only:
  the weave decays and the speed stays between 4.60 and 4.70 m/s, the figure's axis range.
* **Not used.** Basu-Mandal, Chatterjee and Papadopoulos (Proc. R. Soc. A 463, 2007) tabulate
  the accelerations of the nonlinear benchmark at one generic state; the compliant contacts of
  the bond graph make an instantaneous acceleration comparison meaningless, so it is not a check
  here. Kooijman, Schwab and Meijaard (Multibody Syst. Dyn. 19, 2008) measured weave eigenvalues
  on an instrumented bicycle, but for a different bicycle (their own measured parameters), so the
  benchmark parameter set has no measured data to compare with.

## What to try

* `whipple`: the dashboard's speed slider. Below 4.29 m/s the weave grows and the bicycle falls;
  between 4.29 and 6.02 m/s it rights itself; above 6.02 m/s it slowly capsizes (the 3D view shows
  it lean into an ever-tighter turn after many seconds).
* `linear`: the same in the linear model (runs in a fraction of a second); compare the lean with
  `whipple` at a small push.
* `balance`: change the lean set-point; the bicycle turns right for a positive lean. Note the
  counter-steer: to lean right, the controller first steers left.
