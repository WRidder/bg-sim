# RRR arm as an equation block (plan 9.8)

A three-joint arm: a hand-derived Hamiltonian equation block ([Arm](block:Arm), `ArmDynamics3R`) behind three DC motors and 50:1 gears, a 1 ms discrete PD controller with gravity compensation ([Ctrl](block:Ctrl), `ArmCtrl3R`) and minimum-jerk `TimeTable` references ([Ref1](block:Ref1), [Ref2](block:Ref2), [Ref3](block:Ref3)). The same geometry is rebuilt from the spatial multibond stdlib in `rrr-multibond` and compared joint by joint (DEC-M5-2). The six-axis arm is the model `arm`.

![The model canvas|900](assets/a228ea2039d0.png)

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

![3D view at t = 1.2 s|500](assets/52197b298cb0.png)

Continue with [the equation block](page:block), [the drives and controller](page:controller) and [the results](page:results).
