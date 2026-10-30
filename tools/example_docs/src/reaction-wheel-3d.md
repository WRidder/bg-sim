@@ figures gravity-off
{
  "diagram": {"kind": "diagram", "model": "gravity-off"},
  "run": {
    "kind": "plot", "model": "gravity-off", "xlim": [0, 4],
    "rows": [
      {"ylabel": "body H about pivot [kg m²/s]", "series": [{"signal": "MeasBody/H[1]", "label": "Hx"}, {"signal": "MeasBody/H[2]", "label": "Hy"}, {"signal": "MeasBody/H[3]", "label": "Hz"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WJoint1/qdout", "label": "wheel 1"}, {"signal": "WJoint2/qdout", "label": "wheel 2"}, {"signal": "WJoint3/qdout", "label": "wheel 3"}, {"signal": "WJoint4/qdout", "label": "wheel 4"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "body torque [N m]", "series": [{"signal": "Tap/Tbx", "label": "Tbx"}, {"signal": "Tap/Tby", "label": "Tby"}, {"signal": "Tap/Tbz", "label": "Tbz"}], "legend": true}
    ]
  }
}
@@ page gravity-off overview - | Overview
# Four-wheel pyramid on a spherical pivot

A rigid body hangs on a compliant **spherical pivot** and carries **four reaction wheels** in a pyramid. Every wheel is a real `RigidBody3D` on a `Revolute3D`, driven by a `CurrentControlledDrive`, so the gyroscopic coupling between the tumbling body and the spinning wheels is physical, not assumed. It is the 3D twin of `reaction-wheel-2d` (X-MB2) and the actuator half of plan 9.10 / X-MB4. With gravity off (this model) the **total angular momentum about the pivot**, body plus four wheels in the world frame, is constant. The model `gravity-on` releases the body 0.5 rad off the vertical; there the derivative of the angular momentum equals the gravity torque.

![The model canvas (flat graph)|900](@fig:diagram)

```
World -- Pivot -- Link ------+-- Body            (RigidBody3D: m 2, J 0.06/0.05/0.04)
(ground) (Spherical3D) (CoM 0.2 m below)
                             +-- WMount_k -- WJoint_k -- WLink_k -- Wheel_k   (k = 1..4)
                             |   (Revolute3D, axis = z)  (identity)  (RigidBody3D)
                             |                      Shaft_k -- Drv_k <-- Alloc.i_k
 TxCmd/TyCmd/TzCmd (Sine) + Lambda --> Alloc (1 ms) --> Drv_k      Drv_k.tau_m --> Tap
```

The pages of this documentation: [construction](page:construction), [allocation and momentum balance](page:allocation), [results](page:results).

## Run it

Press **Run**: 4 s, 801 output points, about three minutes with the first compile. Plot [MeasBody/H[1]](signal:MeasBody/H[1]) to see the body exchange momentum with the wheels, [WJoint1/qdout](signal:WJoint1/qdout) to [WJoint4/qdout](signal:WJoint4/qdout) for the wheel speeds, and [Tap/nsp](signal:Tap/nsp) for the null-space tap.
@@ page gravity-off construction overview | Construction
# Construction

- **Pivot.** [World](block:World) (`GroundSpatial`) to [Pivot](block:Pivot) (`Spherical3D`, $k_t = 10^9$ N/m, $b_t = 5\cdot10^3$ N·s/m) to [Link](block:Link) (`FixedTransform3DNeutral`, CoM at $(0, 0, -0.2)$ m in the joint child frame) to [Body](block:Body) (`RigidBody3D`, $m = 2$ kg, $J = (0.06, 0.05, 0.04)$ kg·m²). The three rotational drive ports carry unpowered `Se` sources ([PivotSe1](block:PivotSe1) to `PivotSe3`, $e = 0$).
- **Wheels.** Wheel $k$ has the unit axis $a_k = (\sin\beta\cos\varphi_k,\ \sin\beta\sin\varphi_k,\ \cos\beta)$ with $\beta = \arctan\sqrt2 = 54.74^\circ$ (`beta` = 0.9553166 rad) and $\varphi_k = 0, 90, 180, 270^\circ$, so that $A A^T = \tfrac43 I$ (isotropic) for $A = [a_1\ a_2\ a_3\ a_4]$. The wheel centre sits 0.1 m from the body CoM at azimuth $\varphi_k$. `Revolute3D` spins about the local $z$ of its joint frame; [WMount1](block:WMount1) (`FixedTransform3DNeutral`) turns that $z$ into $a_k$. [WLink1](block:WLink1) is the identity transform every body mount needs for the frame check (E007). Wheel: $m = 0.3$ kg, $J = (10^{-3}, 10^{-3}, 2\cdot10^{-3})$ kg·m² ([Wheel1](block:Wheel1)). Both bonds `WMount_k.b -> Body.p` and `WLink_k.b -> Wheel_k.p` run transform-to-body; the reverse orientation flips the sign of the relative rate.
- **Joints and drives.** [WJoint1](block:WJoint1) is compliant in its five held directions ($k_r = 10^5$ N·m/rad, $b_r = 10$, $k_t = 10^7$ N/m, $b_t = 10^3$). The drive is [Drv1](block:Drv1) (`CurrentControlledDrive`, $k_t = 0.05$ N·m/A, rotor $J_m = 10^{-8}$ kg·m²) behind a stiff [Shaft1](block:Shaft1) (`ElasticShaft`, $k = 100$ N·m/rad, $d = 2\cdot10^{-3}$): a rotor rigidly bonded to a joint that imposes its rate would be derivative-causal (W201); the shaft keeps every state integral. The motor torque is $\tau_k = k_t\,i_k$ and the reaction $-\tau_k a_k$ goes to the body through the joint.
- **Poses are composed, never integrated** (D-MB6): the body pose is [PoseBody](block:PoseBody) $=$ `Pivot.pose` $\circ$ [BodyLocal](block:BodyLocal); wheel $k$ is $\text{PoseBody} \circ \text{WLocal}_k \circ \text{WJoint}_k.\text{pose}$ ([PoseW1](block:PoseW1)).
- **Firmware** (D28: the only code besides sensors): [Alloc](block:Alloc) (`Allocator`, 1 ms, discrete) turns a scripted three-axis body torque (three `Sine` sources [TxCmd](block:TxCmd), [TyCmd](block:TyCmd), [TzCmd](block:TzCmd): amplitudes 0.04 / 0.03 / 0.05 N·m at 1.5 / 2.1 / 1.1 Hz, phases 0 / 0.7 / 1.9 rad) and a null-space request [Lambda](block:Lambda) (0.01 N·m) into the four motor currents. [MeasBody](block:MeasBody), `MeasW1..4` (`BodyMeasure`) and [Tap](block:Tap) (`WheelTap`) are algebraic sensors.

## The two models

| | `gravity-off` | `gravity-on` |
| --- | --- | --- |
| `g0` | 0 in all five bodies | 9.81 in all five bodies |
| start | upright, spin $(0.3, -0.2, 0.5)$ rad/s (consistent CoM velocity) | released 0.5 rad off the vertical about $(1, 1, 0)$, at rest |
| wheels | at rest relative to the body, driven by the same scripted torques | same |

Both run 4 s with 801 output points (`reltol` 1e-9, `abstol` 1e-11, `solver` auto).
@@ page gravity-off allocation overview | Allocation and momentum balance
# Allocation and momentum balance

## Allocation with a null space

A motor torque $\tau_k$ on wheel $k$ puts $-\tau_k a_k$ on the body, so the body torque is $T = -A\,\tau$. The firmware solves the desired torque with the minimum-norm solution plus a free null-space component:

$$\tau = -A^{+}\,T_{des} + \lambda\,n, \qquad A^{+} = A^T (A A^T)^{-1}, \qquad n = \tfrac12\,(1, -1, 1, -1)^T, \qquad A\,n = 0.$$

Three orthogonal wheels have an empty null space; the four-wheel pyramid has a one-dimensional one, which is what makes wheel-speed bias and momentum management possible without touching the body. The tap [Tap](block:Tap) reads the **measured** motor torques `Drv_k.tau_m`, not the firmware's intent:

| output | meaning |
| --- | --- |
| [Tap/Tbx](signal:Tap/Tbx), `Tbz`, `Tby` | $-A\tau$: the torque the four motors really put on the body |
| [Tap/nsp](signal:Tap/nsp) | $n\cdot\tau$: the null-space component (here $\lambda = 0.01$ N·m) |
| `Tap/ntau`, `Tap/proj` | $\lvert\tau\rvert^2$ and $\lvert A^{+}A\tau\rvert^2$, the part that reaches the body |
| `Tap/resid` | `ntau` $-$ `proj` $-$ `nsp`$^2$, identically 0 (range orthogonal to null) |
| `Alloc/nsp`, `Alloc/Tbx`... | the same two quantities from the firmware side |

The null component is visible in the wheel speeds (a constant $\lambda$ drives the pyramid mode $(1, -1, 1, -1)$ at $\lambda/(2 J_w) = 2.5$ rad/s²) and never in the body torque.

## Measurement (not plant physics)

[MeasBody](block:MeasBody) gets a body's momentum $P = [J\omega;\ m v]$ and world pose $g$ and gives, about the world origin (the pivot), the angular momentum, the gravity torque and its integral:

$$H = R\,P_{ang} + p \times (R\,P_{lin}), \qquad \tau_g = p \times (0, 0, -m g_0), \qquad I_g = \int \tau_g\,dt .$$

Summed over the five bodies:

- gravity off: $H_{total}(t)$ is constant;
- gravity on: $H_{total}(t) - I_{g,total}(t)$ is constant, i.e. $\dot H = \tau_{gravity}$.

## Why four wheels, and why the elastic shaft

Four wheels instead of the work-package's three orthogonal ones give the null-space tap something to show (and prepare X-MB5). The drive reaches the joint through an `ElasticShaft` with a tiny rotor inertia: the rotor is relative to the joint, not an inertial body, and a rigid rotor would give W201. The rotor's own momentum (at most $J_m\omega = 2.5\cdot10^{-7}$ kg·m²/s) is the only thing the world $H$ leaves out.
@@ page gravity-off results overview | Results and checks
# Results and checks

![World angular momentum of the body, wheel speeds and realised body torque|900](@fig:run)

## Measured (README, real worker)

| quantity | gravity-off |
| --- | --- |
| $\max\lvert H - H_0\rvert / \max\lvert H\rvert$ per axis | 3.1e-14 / 7.1e-14 / 3.2e-14 ($H_0 = (0.0598, -0.03787, 0.02867)$ kg·m²/s) |
| the body alone | $H_z$ goes 0.020 to 0.0516 (the wheels carry the difference); body rate $\lvert\omega_z\rvert$ up to 1.195 rad/s |
| wheel speeds at 4 s (relative) | (23.58, -4.19, 23.31, 11.10) rad/s; peak 25.0 rad/s |
| motor torque (max over the four wheels) | 0.0481 N·m (limit 0.06) |
| null-space tap | `Tap/nsp` = 0.01 N·m exactly ($\max\lvert nsp - \lambda\rvert = 8.7\cdot10^{-18}$); `Tap/resid` 1.3e-18 |
| realised body torque | `Tap/Tb*` = `Alloc/Tb*` to 2.1e-17 N·m; against the continuous command within the zero-order-hold error $A\omega T_s$ (at most 6.3e-5 N·m, limit 1e-4) |
| quaternion norm drift | 2.3e-14 |
| pivot deflection | 1.5e-10 m |
| states | 79 by count (pivot 7, body momentum 6, per wheel 14, 10 gravity-impulse integrals) |

**Momentum tolerance.** The checks use `tol` = 1e-9 of the invariant's own scale. The compliant pivot is the only place the momentum balance can leak and its error scales as $1/k_t$: measured 7e-14 relative at $k_t = 10^9$ N/m and 3.5e-9 at a soft $k_t = 10^6$ N/m (scratch run), so the checks would fail for a pivot softer than about $10^7$ N/m.

## Checks (`expected.json`)

Initial quaternion and body momentum; the three components of the world angular momentum are invariant; the body alone exchanges momentum and tumbles ([MeasBody/H[3]](signal:MeasBody/H[3]) and `Pivot/omega[3]` peaks); wheel speeds below 30 rad/s and their 4 s values; the null-space tap; the realised body torque equals the firmware allocation and follows the command within the hold error; motor torque below 0.06 N·m; no W201, E101, E102, E103, E106, E007 or W206.
@@ figures gravity-on
{
  "diagram": {"kind": "diagram", "model": "gravity-on"},
  "scene": {"kind": "scene", "model": "gravity-on", "t": 1.0},
  "run": {
    "kind": "plot", "model": "gravity-on", "xlim": [0, 4],
    "rows": [
      {"ylabel": "body H about pivot [kg m²/s]", "series": [{"signal": "MeasBody/H[1]", "label": "Hx"}, {"signal": "MeasBody/H[2]", "label": "Hy"}, {"signal": "MeasBody/H[3]", "label": "Hz"}], "legend": true},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "WJoint1/qdout", "label": "wheel 1"}, {"signal": "WJoint2/qdout", "label": "wheel 2"}, {"signal": "WJoint3/qdout", "label": "wheel 3"}, {"signal": "WJoint4/qdout", "label": "wheel 4"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page gravity-on overview - | Overview
# Four-wheel pyramid with gravity

The pyramid of `gravity-off` with $g_0 = 9.81$ m/s² in all five bodies. The body hangs 0.2 m below the pivot, starts tilted 0.5 rad about the world axis $(1, 1, 0)$ (the start quaternion of [Pivot](block:Pivot) is (0.96891, 0.17494, 0.17494, 0)) and swings while the wheels are driven by the same scripted torques. See the `gravity-off` model for the construction, the allocation and the checks.

![The model canvas|900](@fig:diagram)

## Momentum balance with gravity

With gravity the torque about the pivot is the gravity torque, so

$$\frac{d H_{total}}{dt} = \tau_{gravity}, \qquad H_{total}(t) - \int_0^t \tau_{gravity}\,dt' = \text{const},$$

which the check verifies for the x and y components (explicit scales 0.4 and 0.44, `tol` 1e-9) while $H_z$ stays 0 (no vertical torque).

![Body angular momentum and wheel speeds of the swinging body|900](@fig:run)

| quantity | gravity-on (README) |
| --- | --- |
| $\max\lvert H - \int\tau_g\rvert$ (x / y) | 2.0e-12 / 2.2e-12 kg·m²/s against $H$ peaks of 0.399 / 0.432 (5.0e-12 / 4.9e-12 relative) |
| $H_z$ | 3.9e-13 |
| gravity torque of the body alone | up to 1.34 N·m; its impulse reaches 0.250 / 0.270 kg·m²/s |
| wheel speeds at 4 s (relative) | (22.86, -4.37, 24.65, 11.89) rad/s; peak 27.9 rad/s |
| pivot deflection | 3.6e-8 m |
| quaternion norm drift | 1.0e-14 |

Further checks: initial tilt; the pendulum really swings and the gravity impulse is non-zero; wheel speeds below 35 rad/s and their 4 s values; the same tap checks; no diagnostics.

## 3D view

`scenes/reaction-wheel-3d.sdf` shows the translucent body hanging from the spherical pivot with the four pyramid wheels inside. The body and each wheel are bound by their world pose (`PoseBody`, `PoseW1..4`, quaternion first); a marker on each disc rim shows the wheel spin.

![3D view at t = 1.0 s|500](@fig:scene)
