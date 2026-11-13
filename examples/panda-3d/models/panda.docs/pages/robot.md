# The Robot subsystem

## Mechanics

- **Kinematics.** Modified DH (Craig) of Franka, identical to the joint origins of the URDF (`franka_arm.xacro`, checked to 1e-16): link frame $i$ is `panda_link<i>`, joint $i$ turns about its $z$.

| joint | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| $a_{i-1}$ (m) | 0 | 0 | 0 | 0.0825 | -0.0825 | 0 | 0.088 |
| $d_i$ (m) | 0.333 | 0 | 0.316 | 0 | 0.384 | 0 | 0 |
| $\alpha_{i-1}$ | 0 | $-\pi/2$ | $\pi/2$ | $\pi/2$ | $-\pi/2$ | $\pi/2$ | $\pi/2$ |
| mass (kg) | 4.971 | 0.6469 | 3.229 | 3.588 | 1.226 | 1.667 | 0.7355 |

  The flange is 0.107 m along $z_7$ ([TCP](block:Robot/TCP)).
- **Links** ([L1](block:Robot/L1) to `L7`). Each link is an instance of the library subsystem `RevoluteLink3D` (`library/RevoluteLink3D.bgsub.json`): the offset `T` from the previous body (for `L1` the base mount), the joint `J`, the offset `Link` to the body's centre of mass, the body `B` on its 1-junction `BJ` and the pose band `CA`, `W`, `P`. Every value is pinned per instance, so joint 4 is `Robot/L4/J` and its angle `Robot/L4/J/qout`.
- **Bodies** ([B](block:Robot/L1/B) in `L1` to `L7`). Masses, centres of mass and inertia tensors are the physically feasible set of Gaz et al. 2019. `RigidBody3D` takes principal moments, so each tensor is diagonalised and the body 1-junction frame is the centre of mass turned to the principal axes (`LC` of each link).
- **Joints** ([J](block:Robot/L1/J) in `L1` to `L7`). `Revolute3D` with the five other directions compliant ($k = 10^7$), damped at 0.7 of critical. The arm starts at rest at the ready pose on the consistent deflections of the joint reactions, so nothing rings at $t = 0$.

## Drives (per joint)

```
tau_k -> Limit_k (+-87 / +-12 N m) -> Motor_k (MSe, 1/N) -> 1 [Rotor_k: I = J_m]
      -> Gear_k (TF, n = 1/N) -> 0 [TauSense_k: De] -> 1 [Spring_k: C = 1/k, Damper_k: R]
      -> 1 [Friction_k: Gaz] -> J_k.drive
```

The command is the link-side torque. The motor applies $\tau/N$ to the rotor, the gear multiplies it back by $N$, and the elastic gear (spring and damper on the 1-junction of the relative rate) carries it to the link 1-junction, where the Gaz friction acts. The [TauSense1](block:Robot/TauSense1) effort detector on the gear-output 0-junction measures the spring-plus-damper torque, which is the link-side torque sensor of the real arm. The springs start preloaded with the gravity torque of the ready pose.

| quantity | joints 1-4 | joints 5-7 | source |
| --- | --- | --- | --- |
| torque limit | 87 N·m | 12 N·m | Franka (`joint_limits.yaml`) |
| gear ratio $N$ | 100 | 100 | **assumed** (harmonic drive) |
| rotor inertia $J_m$ | 5e-5 kg·m² | 1e-5 kg·m² | **assumed** (reflected $N^2 J_m$ = 0.5 / 0.1 kg·m²) |
| gear stiffness $k$ | 1e4 N·m/rad | 5e3 N·m/rad | **assumed** |
| gear damping | 28.3 N·m·s/rad | 8.94 N·m·s/rad | damping ratio 0.2 of the rotor-on-spring mode |

Gaz friction (supplementary Table I), [Friction1](block:Robot/Friction1) to `Friction7`:

$$\tau_f(\dot q) = \frac{\varphi_1}{1 + e^{-\varphi_2(\dot q + \varphi_3)}} - \frac{\varphi_1}{1 + e^{-\varphi_2 \varphi_3}}.$$

## Sensors

- [Encoder1](block:Robot/Encoder1) to `Encoder7`: link-side angle quantized to $2\pi / 2^{20}$ (6 µrad) and sampled every 1 ms (`Quantizer`), the ports `q1..q7`;
- the joint rates `dq1..dq7` straight from `J_k.qdout`;
- the torque sensors `tauJ1..tauJ7`.
