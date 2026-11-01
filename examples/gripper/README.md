# gripper — grip-force sizing of an electric parallel gripper in a fast pick-and-place move

An electric parallel-jaw gripper on a pick-and-place carriage picks a part from a source fixture,
lifts it, moves it 0.4 m sideways with a fast jerk-limited transfer (20 m/s²), sets it down on the
target and lets go. The question is the one every gripper selection starts with: **what grip force
does the part need, and does the gripper deliver it?** The part is a free 3D rigid body held only
by compliant contacts with regularised Coulomb friction, so holding, creeping, slipping and
dropping all come out of the contact physics.

Two models share the drive train, the carriage and the monitor:

| model | part | grip setting | what it shows |
| --- | --- | --- | --- |
| `ball-gripper` | 50 mm steel ball, 0.514 kg | 46 N per jaw (sized, S = 2) | the force analysis, the friction band of the drive, the closing impact |
| `block-gripper` | 40 × 40 × 80 mm aluminium block, 0.346 kg, gripped 28 mm above its centre of mass | 123 N per jaw (sized with the tilting moment) | the moment of the transfer acceleration about the jaw axis |

`expected.json` also runs both models with parameter overrides (the dashboard mechanism): an
under-gripped ball, a slip-threshold run, three closing speeds and the block sized for the force
only. Everything numeric comes from `design/design.py`; `design/build_model.py` writes the models
and the two scenes from it:

```
uv run examples/gripper/design/design.py        # the sizing and every reference value
uv run examples/gripper/design/build_model.py   # models/*.bgmodel.json and scenes/*.sdf
uv run examples/run_checks.py --only gripper
```

## Mechanism

```
Ctrl (GripController) --i_ref--> Motor (CurrentControlledDrive, k_t 0.012 N m/A, J_m 1.5e-6 kg m^2)
  -> Gearhead (IdealGear, 3:1) -> Spindle (LeadScrew, 3 mm lead, eta 0.7 / eta_back 0.571)
  -> Wedge (WedgeHook, jaw speed = 0.5 nut speed) -> jaw node (both jaws, closing travel x)
       |-- Guides (JawGuides: Stribeck friction of both jaw guides) -- Frame
       |-- JawPos / JawVel (sensors) --> Ctrl, contacts
       |-- JawA.j, JawB.j  (MovingPlaneContact: the jaw pads)  <-- Carriage pc, vc
Carriage (Carriage) <-- Lift, Transfer, Lower, Retreat (SCurveProfile)
Ball (RigidBody3D) <-> BallPose (PoseIntegrator3D)   p --> MountA/B/T --> JawA, JawB, Table
Grip (GripMonitor): requirement, delivered friction, slip, holds
```

* **Drive train (translation and rotation bond graph).** The motor is current controlled (the
  current loop is ideal: `i = i_ref`). The gearhead and the spindle make a transformer with
  `G = 2π N / (lead · 2 i_w) = 6283 N per N m` of motor torque **per jaw** (both jaws share one
  nut through the wedge hook). The lead screw is a transformer with **direction-dependent
  efficiency**: driving (power from the screw to the nut) it loses `1 - η = 30 %`, back-driven
  it passes `η_back = 2 - 1/η = 0.571` (the thread relation of a sliding screw; `η_back ≤ 0`
  would be self-locking). The switch is smoothed by `tanh(ω/w_eps)`, `w_eps = 1e-3 rad/s`, so a
  stalled drive creeps at most at that speed. The reflected rotor inertia on the jaw travel is
  `J_m (2π N/(lead i_w))² = 237 kg`.
* **Controller.** Position-limited speed loop with a current clamp (`library/GripController.jl`):
  travel at 30 mm/s with the full 2.5 A, then a **grip zone** from 1 mm before the part where the
  speed limit blends to `v_grip` (3 mm/s for the ball, 1 mm/s for the block) and the current limit
  to the **grip current** `I_grip = F_set / (η k_t G)`. On the part the speed error saturates the
  current at `I_grip`, so the setting `F_set` is the force a closing drive reaches. The open/close
  command ramps over 2 ms.
* **Contacts.** `stdlib:contact/MovingPlaneContact` (new in this example): a sphere (or a point,
  `r = 0`) of a spatial body against a finite rectangular face that is carried by the carriage
  (`pc`, `vc`) and slid along the jaw axis by the Translation port `j`. Hunt-Crossley normal force
  `k x sqrt(x/xref) (1 + c ẋ)` with a no-pull clamp, an edge gate on the face half-widths, and
  isotropic regularised Coulomb friction `μ f_n tanh(|s|/vs) s/|s|` on the slip `s` at the contact
  point. The reaction goes to the jaw as `j.e = F·a`. Ball pads: polyurethane, `K = 1.2e7 N/m^1.5`
  (Hertz for the 50 mm ball), `μ = 0.25`, `vs = 1 mm/s`. Block: four point contacts per pad at
  ±6 mm, `k = 3e5 N/m` at `xref = 0.1 mm`; four on the table at the bottom corners.
* **Motion.** Four `SCurveProfile` blocks: lift 0.1 m (4 m/s², 80 m/s³) at 0.55 s, transfer 0.4 m
  (2 m/s, 20 m/s², 600 m/s³) at 0.95 s, lower to 0.5 mm above the target at 1.40 s, open at 1.85 s,
  retreat at 2.20 s. The project block `Carriage` sums them into the carriage position, velocity,
  acceleration and the pose of the 3D view.

## Sizing

Two jaws with the grip force `F` each carry at most `2μF` of friction. The part must follow the
carriage, so the jaws must supply `m(a - g)`; with the jaw normal horizontal all of it is friction:

    F ≥ S · m · sqrt((g + a_v)² + a_h²) / (2 μ)

| case | `a_v`, `a_h` (m/s²) | `F` per jaw, S = 1 |
| --- | --- | --- |
| at rest | 0, 0 | 10.08 N |
| lift | 4, 0 | 14.19 N |
| transfer | 0, 20 | **22.89 N** |

With `S = 2`: **46 N**, grip current `46 / (0.7 · 0.012 · 6283) = 0.872 A`, motor torque 10.5 mN m.

For the block the transfer acceleration acts at the centre of mass, `e = 28 mm` below the grip
line, and turns the block about the jaw axis with `M = m a_h e`. The pad's four points at the
torsion lever `r = 8.5 mm` carry it by friction too. The sizing rule adds it linearly (every point
safe for any direction):

    F ≥ S · (m |a - g| + M/r) / (2 μ):   15.40 N (force only) → 61.01 N with the moment, S = 2: 123 N

The limit surface of a pad that slides as a whole is closer to `sqrt(F_t² + (M/r)²)`, 48.1 N:
less conservative, still three times the force-only value.

## What the gripper delivers: the friction band and the locked-in impact

The setting is a lower bound, not the grip force. A stalled drive with friction holds any jaw
force between the forward value `η G k_t I` (46 N) and the back-driving value `G k_t I / η_back`
(115 N): inside this band nothing moves. The closing speed decides where the force ends: the
reflected inertia (237 kg at 3 mm/s, 1 mJ) compresses the pads beyond the forward value and the
drive friction keeps it. A reduced 1-DOF model of the closing in `design.py` (jaw mass `η·237 kg`,
the speed loop, Hertz pads, guide friction) predicts the peak and the force at the stop:

| `v_grip` | reduced model peak | simulation peak | after the impact |
| --- | --- | --- | --- |
| 3 mm/s (ball default) | 57.39 N | 56.86 N | 56.8 N (locked in) |
| 10 mm/s | 93.12 N | 92.56 N | 92.4 N (locked in) |
| 20 mm/s | 148.45 N | 147.45 N | 92.0 N (back-driven into the band) |
| 30 mm/s | 207.28 N | 205.79 N | 50.9 N (back-driven into the band) |

So the sized ball is held at 56.8 N, a safety in effect of 2.48 (minimum of `Grip/S_act`), and the
12 N setting holds 21.8 N: enough for the lift (14.2 N), not for the transfer (22.9 N).

## Validation (the checks in `expected.json`)

* **(a) Static slip threshold and regularisation error.** With the transfer, lowering and opening
  moved past the end, the grip setting falls at 10 N/s from 0.8 s while the ball hangs in the
  jaws. The slip ODE `m ṡ = m g - 2μF(t) tanh(s/vs)` with the back-driven force rate
  `F' = -10/(η η_back)` reaches the detection speed 2 mm/s at **10.4242 N**; the simulation
  latches **10.4249 N**. The Coulomb threshold is `m g/(2μ) = 10.080 N`: the regularised
  friction slips 3.4 % early. While held the ball creeps at `vs atanh(need/(2μF))`, 0.149 mm/s at
  0.9 s (checked to 1 %).
* **(b) Friction demand vs requirement.** The friction the two contacts deliver (`Grip/demand`)
  follows `m sqrt((g + a_v)² + a_h²)` (`Grip/need`) to 6 mN over the whole move; its peak is
  11.445 N in the transfer.
* **(c) Under-gripped vs sized.** Setting 12 N: the ball survives the lift and starts to slip at
  0.98 s, as the transfer acceleration builds up (`Grip/holds` → 0, 3.8 mm displacement). Setting
  46 N: it holds, moving less than 0.25 mm in the jaws. The block sized for the force only (31 N,
  held at 36.9 N) swings by 26° in the transfer; sized with the moment (123 N) it tilts 0.26°.
* **(d) Motor current and torque.** 0.872 A and 10.46 mN m for the ball (2.33 A for the block,
  near the 2.5 A limit). The delivered force stays inside the friction band [46, 115] N.
* **(e) Closing impact.** The table above: peaks within 1 % of the reduced model.

## 3D view

`scenes/gripper.sdf` (ball) and `scenes/gripper-block.sdf` (block): a table with the blue source
and green target fixtures, a gantry, the carriage with the gripper housing, the two jaws on
prismatic joints bound to `JawPos/y`, and the part on its pose. The pads are coloured by the
friction utilisation `|F_t|/(μ f_n)` (`coolwarm` from 0, blue, to 1, red: sliding) and the status
light on the housing by `Grip/holds` (blue while it holds, red after a slip).

## Dashboard

`ball-gripper` has sliders for the grip setting, the transfer acceleration and the closing speed
at the part, the holds light, the time of the first slip (with an alarm zone), the grip force at
the slip, the grip current, and the force and friction plots. Lower the setting to about 12 N and
the ball slips in the transfer: the light goes out, the first-slip time shows the alarm, and the
status light in the 3D view turns red. At 8 N (17.4 N delivered) the ball falls out of the jaws.
Raising the transfer acceleration raises the requirement; the sized setting still holds at the
40 m/s² end of the slider (the 56.8 N locked in by the closing carry up to about 54 m/s²).

## Files

* `library/`: `GripController`, `LeadScrew`, `WedgeHook`, `JawGuides`, `Carriage`,
  `StaticCarrier`, `GripMonitor` (the analysis), `PadSum` (four point contacts of a block pad).
* `design/design.py`, `design/build_model.py`: the numbers and the generator.
* `models/*.docs`: the docs pages (mechanism, contact model, derivation, sizing, validation),
  built by `tools/example_docs/build.py` from `tools/example_docs/src/gripper.md`.
