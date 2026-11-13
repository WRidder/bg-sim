# Humanoid dual arm: the dynamic bimanual hold

The firmware of `humanoid-ik` on the **dynamic** robot. Two multibody arms carry a 1.5 kg box on stiff grasp springs:

- **Arms** ([LArm1](block:LArm1) to `LArm7`, `RArm1` to `RArm7`): every link is an instance of the library subsystem `RevoluteLink3D` (`library/RevoluteLink3D.bgsub.json`: the offset from the body below, the joint `J`, the offset to the centre of mass, the body `B` on its junction and the pose band). The joints (`LArm1/J` ...) are `Revolute3D` with the page's axes and offsets, and the five other directions compliant ($10^6$, damped at 0.7 of critical). The link bodies (`LArm1/B` ...) are `RigidBody3D` solid cylinders with **illustrative** masses: 1.0, 1.0, 2.0, 0.8, 1.2, 0.4 and 0.6 kg.
- **Drives**, one per joint: the motor torque `MSe` ([LMotor1](block:LMotor1)) on the reflected rotor inertia ([LRotor1](block:LRotor1)), then a torque sensor ([LTauSense1](block:LTauSense1)) and an elastic gear ([LSpring1](block:LSpring1), [LDamper1](block:LDamper1)) on the relative rate, then joint friction ([LFriction1](block:LFriction1)) into the joint's drive port. The springs start preloaded with the holding torque.
- **Grasp**: per hand, a `Revolute3D` weld ([LWeld](block:LWeld)) with all six directions sprung at $10^5$ N/m and $10^3$ N·m/rad, between the hand and the box ([Box](block:Box)).
- **Firmware** at 1 kHz: [Traj](block:Traj) → [IKL](block:IKL)/[IKR](block:IKR) → [ServoL](block:ServoL)/[ServoR](block:ServoR) (PID with integral and the holding-torque feedforward, torque limits 80 / 20 N·m).

![The model canvas|900](assets/6d7eb241d25f.png)

The run: 6.5 s, `FBDF` with `reltol` 1e-4 and `abstol` 1e-6, 1301 output points. The system has 46 states and 6416 equations. It takes about 31 s of solve time and 66 s in total.

![3D view at t = 4 s: the box at the commanded pose|500](assets/2ff8272b1004.png)

Continue with [the results](page:hold-results).
