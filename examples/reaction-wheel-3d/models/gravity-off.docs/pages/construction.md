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
