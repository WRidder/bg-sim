# reaction-wheel-3d — a four-wheel pyramid on a spherical pivot

A rigid body hangs on a compliant **spherical pivot** and carries **four reaction wheels** in
a pyramid. Every wheel is a real `RigidBody3D` on a `Revolute3D`, driven by a
`CurrentControlledDrive`, so the gyroscopic coupling between the tumbling body and the
spinning wheels is physical, not assumed. It is the 3D twin of `reaction-wheel-2d` (X-MB2)
and the actuator half of plan 9.10 / X-MB4. With gravity off the **total angular momentum
about the pivot** (body plus four wheels, in the world frame) is constant; with gravity on its
derivative equals the **gravity torque** about the pivot.

```
World ── Pivot ── Link ──────────┬── Body            (RigidBody3D: m 2, J 0.06/0.05/0.04)
(ground) (Spherical3D) (CoM 0.2 m below) │
                                 ├── WMount_k ── WJoint_k ── WLink_k ── Wheel_k   (k = 1..4)
                                 │   (pose of    (Revolute3D,  (identity)  (RigidBody3D)
                                 │    joint frame) axis = z)       ▲
                                 │                          Shaft_k ── Drv_k ◄── Alloc.i_k
                                 │                      (ElasticShaft) (CurrentControlledDrive)
 TxCmd/TyCmd/TzCmd (Sine) + Lambda ──► Alloc (1 ms) ──► Drv_k      Drv_k.tau_m ──► Tap
 Pivot.pose ∘ Local ──► PoseBody ──► Body.g, MeasBody;  PoseBody ∘ WLocal_k ∘ WJoint_k.pose ──► Wheel_k.g, MeasW_k
```

## The construction

* **Pivot.** `GroundSpatial` → `Spherical3D` (`kt = 1e9 N/m`, `bt = 5e3 N·s/m`) → `Link`
  (`FixedTransform3DNeutral`, CoM at `(0, 0, −0.2)` in the joint child frame) →
  `RigidBody3D`. The three rotational drive ports carry an unpowered `Se` (`e = 0`).
* **Wheels.** Wheel `k` has the unit axis `a_k = (sin β cos φ_k, sin β sin φ_k, cos β)` with
  `β = atan √2 = 54.74°` and `φ_k = 0, 90, 180, 270°`, so `A Aᵀ = 4/3 I` (isotropic) for
  `A = [a_1 a_2 a_3 a_4]`. The wheel centre sits 0.1 m from the body CoM at azimuth `φ_k`.
  `Revolute3D` spins about the local `z` of its joint frame, so `WMount_k`
  (`FixedTransform3DNeutral`, `a` on the joint, `b` on the body, `g` = body in joint frame
  = the inverse of the joint-in-body pose `qz(φ_k) ⊗ qy(β)`) turns that `z` into `a_k`.
  `WLink_k` is the identity transform that every body mount needs for the frame check
  (E007). Wheel: `m = 0.3 kg`, `J = (1e-3, 1e-3, 2e-3) kg·m²` (axial `2e-3` about its `z`).
  Both bonds `WMount_k.b → Body.p` and `WLink_k.b → Wheel_k.p` run transform-to-body;
  the reverse orientation flips the sign of the relative rate.
* **Joints and drives.** `Revolute3D` is compliant in its five held directions
  (`kr = 1e5 N·m/rad`, `br = 10`, `kt = 1e7 N/m`, `bt = 1e3`). The drive is the library
  `CurrentControlledDrive` (`k_t = 0.05 N·m/A`, rotor `J_m = 1e-8 kg·m²`) behind a stiff
  `ElasticShaft` (`k = 100 N·m/rad`, `d = 2e-3`): a rotor rigidly bonded to a joint that
  imposes its rate would be derivative-causal (W201), the shaft keeps every state integral.
  The motor torque on wheel `k` is `τ_k = k_t i_k` and the reaction `−τ_k a_k` goes to the body
  through the joint.
* **Poses are composed, never integrated** (D-MB6): the body pose is `Pivot.pose ∘ BodyLocal`,
  wheel `k` is `PoseBody ∘ WLocal_k ∘ WJoint_k.pose`, and each `RigidBody3D.g` reads its own.
* **Firmware (D28: the only code nodes besides sensors).** `Allocator` (1 ms, discrete)
  turns a scripted three-axis body torque `T_des` (three `Sine` sources, 0.04/0.03/0.05 N·m at
  1.5/2.1/1.1 rad/s) and a null-space request `lam` into the four motor currents
  `i_k = τ_k/k_t`. `BodyMeasure` (one per body, five in all) and `WheelTap` are algebraic sensors.

## The allocation and its null-space tap

A motor torque `τ_k` on wheel `k` puts `−τ_k a_k` on the body, so the body torque is
`T = −A τ`. The firmware solves `T_des` with the minimum-norm solution plus a free
null-space component:

```
τ = −A⁺ T_des + lam n,     A⁺ = Aᵀ (A Aᵀ)⁻¹,     n = (1, −1, 1, −1)/2,     A n = 0
```

Three orthogonal wheels would have an empty null space; the four-wheel pyramid has a
one-dimensional one (`n`), which is what makes wheel-speed bias and momentum management
possible without touching the body. The tap is `WheelTap`, which reads the **measured**
motor torques `Drv_k.tau_m` (not the firmware's intent):

| output | meaning |
| --- | --- |
| `Tap/Tbx,Tby,Tbz` | `−A τ`: the torque the four motors really put on the body |
| `Tap/nsp` | `n·τ`: the null-space component (here `lam = 0.01 N·m`) |
| `Tap/ntau`, `Tap/proj` | `|τ|²` and `|A⁺A τ|²`, the part that reaches the body |
| `Tap/resid` | `ntau − proj − nsp²`, identically 0 (range ⟂ null) |
| `Alloc/nsp`, `Alloc/Tbx…` | the same two quantities from the firmware side |

The null component is fully visible in the wheel speeds (a constant `lam` drives the
pyramid's `(1, −1, 1, −1)` mode at `lam/(2 J_w) = 2.5 rad/s²`) and never in the body torque.

## Measurement (not plant physics)

`BodyMeasure` gets a body's momentum `P = [J w; m v]` and world pose `g` and gives, about
the world origin (the pivot): `H = R P_ang + p × (R P_lin)`, the gravity torque
`tg = p × (0, 0, −m g0)` and its integral `Ig`. Summed over the five bodies:

* gravity off: `H_total(t)` is constant;
* gravity on: `H_total(t) − Ig_total(t)` is constant, i.e. `dH/dt = τ_gravity`.

## The two models

| | `gravity-off` | `gravity-on` |
| --- | --- | --- |
| `g0` | 0 in all five bodies | 9.81 in all five bodies |
| start | upright, spin `(0.3, −0.2, 0.5) rad/s` (consistent CoM velocity) | released 0.5 rad off the vertical about `(1, 1, 0)`, at rest |
| wheels | at rest relative to the body, driven by the same scripted torques | same |

Both run 4 s, 801 output points, `reltol 1e-9`, `abstol 1e-11`, solver `auto`.

## Measured (this example, the real worker)

| quantity | value |
| --- | --- |
| `gravity-off`: `max|H − H0| / max|H|` per axis | **3.1e-14 / 7.1e-14 / 3.2e-14** (`H0 = (0.0598, −0.03787, 0.02867) kg·m²/s`; absolute 1.8e-15 / 2.7e-15 / 9.1e-16) |
| the body alone, `gravity-off` | `H_z` goes 0.020 → 0.0516 (the wheels carry the difference); body rate `|ω_z|` up to 1.195 rad/s |
| `gravity-on`: `max|H − ∫τ_g|` (x / y) | **2.0e-12 / 2.2e-12** kg·m²/s against `H` peaks of 0.399 / 0.432 (5.0e-12 / 4.9e-12 relative) |
| `gravity-on`: `H_z` (no vertical torque) | 3.9e-13 |
| gravity torque of the body alone | up to 1.34 N·m; its impulse reaches 0.250 / 0.270 kg·m²/s |
| wheel speeds (relative) at 4 s, off / on | (23.58, −4.19, 23.31, 11.10) / (22.86, −4.37, 24.65, 11.89) rad/s; peaks 25.0 / 27.9 rad/s |
| motor torque (max over the four wheels) | 0.0481 N·m (limit 0.06); `i_ref` up to 0.96 A |
| null-space tap | `Tap/nsp = 0.01 N·m` exactly (`max|nsp − lam| = 8.7e-18`); `Tap/resid` 1.3e-18 |
| realised body torque vs command | `Tap/Tb* = Alloc/Tb*` to 2.1e-17 N·m; vs the continuous command within the zero-order-hold error `A ω Ts` (≤ 6.3e-5 N·m, limit 1e-4) |
| quaternion norm drift | 2.3e-14 (off), 1.0e-14 (on) |
| pivot deflection `max|dl|` | 1.5e-10 m (off), 3.6e-8 m (on) |
| states | 79 by count: pivot 7 (quaternion 4, dl 3), body momentum 6, per wheel 14 (momentum 6, q, dth 2, dl 3, shaft angle, rotor momentum), 10 gravity-impulse integrals |
| run cost | 801 rows, 2088 recorded signals; both runs plus the backend start in **168 s** wall time (`run_checks.py --only reaction-wheel-3d`) |
| diagnostics | none (`W201`, `E101`, `E102`, `E103`, `E106`, `E007`, `W206` absent) |

**Momentum tolerance.** The checks use `tol = 1e-9` of the invariant's own scale. The
compliant pivot is the only place the momentum balance can leak, and its error scales as
`1/kt`: the measured error is 7e-14 relative at `kt = 1e9 N/m` (4 s) and 3.5e-9 relative at a
soft `kt = 1e6 N/m` (scratch run, 1 s, same model), so `1e-9` is a safe bound for `kt = 1e9` and the
checks would fail for a pivot softer than about `1e7 N/m`.

## Checks (`expected.json`)

`gravity-off`: initial quaternion and body momentum; the three components of the world
angular momentum are invariant (`tol 1e-9`); the body alone does exchange momentum and
tumbles (`MeasBody/H[3]`, `Pivot/omega[3]` peaks); wheel speeds under 30 rad/s and their
4 s values; the null-space tap (`nsp` value, `nsp − lam`, `resid`); the realised body torque
equals the firmware allocation and follows the command within the zero-order-hold error; the
motor torque stays under 0.06 N·m; no diagnostics.
`gravity-on`: initial tilt; the pendulum really swings and the gravity impulse is non-zero;
`H_x − ∫τ_g,x` and `H_y − ∫τ_g,y` are constant (explicit scales 0.4 and 0.44, `tol 1e-9`) and
`H_z` stays 0; wheel speeds under 35 rad/s and their 4 s values; the same tap checks; no
diagnostics.

## Deviations from the work-package text

* Four wheels in a pyramid instead of three orthogonal ones, so that the null-space tap
  shows something (prepares X-MB5). Three orthogonal wheels have `A = I` and no null space.
* The drive reaches the joint through an `ElasticShaft` with a tiny rotor inertia
  (`J_m = 1e-8`): the rotor is relative to the joint, not an inertial body, and a rigid rotor
  would give W201. The rotor's own momentum (≤ `J_m ω` = 2.5e-7 kg·m²/s) is the only thing
  the world `H` leaves out.

## Run it

```
uv run bgsim
```

then **Open** → **Samples** → **reaction-wheel-3d** and press **Run**. The acceptance checks:

```
uv run examples/run_checks.py --only reaction-wheel-3d
```

## 3D view

`scenes/reaction-wheel-3d.sdf` shows the translucent body hanging from the spherical pivot with the four pyramid wheels inside. The body and each wheel are bound by their world pose (`PoseBody`, `PoseW1..4`, quaternion first); a marker on each disc rim shows the wheel spin and the discs are drawn smaller than the 0.115 m the inertia suggests, so that they do not touch.
