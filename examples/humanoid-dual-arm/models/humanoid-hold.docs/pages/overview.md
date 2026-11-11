# Humanoid dual arm: the dynamic bimanual hold

The firmware of `humanoid-ik` on the **dynamic** robot. Two multibody arms carry a 1.5 kg box on stiff grasp springs:

- **Arms** ([LJ1](block:LJ1) to `LJ7`, `RJ1` to `RJ7`): `Revolute3D` joints with the page's axes and offsets, and the five other directions compliant ($10^6$, damped at 0.7 of critical). The links ([LB1](block:LB1) to `LB7`) are `RigidBody3D` solid cylinders with **illustrative** masses: 1.0, 1.0, 2.0, 0.8, 1.2, 0.4 and 0.6 kg.
- **Drives**, one per joint: the motor torque `MSe` ([LMotor1](block:LMotor1)) on the reflected rotor inertia ([LRotor1](block:LRotor1)), then a torque sensor ([LTauSense1](block:LTauSense1)) and an elastic gear ([LSpring1](block:LSpring1), [LDamper1](block:LDamper1)) on the relative rate, then joint friction ([LFriction1](block:LFriction1)) into the joint's drive port. The springs start preloaded with the holding torque.
- **Grasp**: per hand, a `Revolute3D` weld ([LWeld](block:LWeld)) with all six directions sprung at $10^5$ N/m and $10^3$ N·m/rad, between the hand and the box ([Box](block:Box)).
- **Firmware** at 1 kHz: [Traj](block:Traj) → [IKL](block:IKL)/[IKR](block:IKR) → [ServoL](block:ServoL)/[ServoR](block:ServoR) (PID with integral and the holding-torque feedforward, torque limits 80 / 20 N·m).

![The model canvas|900](assets/7164e8b1a67e.png)

The run: 6.5 s, `FBDF` with `reltol` 1e-4 and `abstol` 1e-6, 1301 output points. The system has 46 states and 6416 equations. It takes about 31 s of solve time and 66 s in total.

![3D view at t = 4 s: the box at the commanded pose|500](assets/55a0023ba60f.png)

Continue with [the results](page:hold-results).
