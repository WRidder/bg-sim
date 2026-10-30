# Double pendulum on a fixed pivot

A planar double pendulum hangs from a fixed pivot. A DC gearmotor drives the **first joint only** (the pendubot arrangement); the other 1 joint is passive. The chain starts hanging straight down at rest with 0 V on the motor, swings up along an optimised trajectory, is caught by an LQR near the upright, balances, and recovers from a force pulse at the tip link.

![The model canvas|900](assets/26d50de9f4ee.png)

## Scenario

| time | phase | what happens |
| --- | --- | --- |
| 0 to 1 s | 0 | hanging at rest, voltage 0 ([Ctrl/phase](signal:Ctrl/phase) = 0), nothing moves |
| 1 s | 1 | the swing-up starts: feed-forward voltage from the trajectory optimisation plus time-varying LQR feedback |
| 3.30 s | 2 | the state enters the LQR region ($V(x) < 3.3$): the balance LQR takes over (the trajectory ends at 3.5 s) |
| 7 s | 2 | a 0.4 N force pulse of 50 ms hits the tip link ([DistForce/y](signal:DistForce/y)) |
| 8.05 to 10.55 s | 2 | back at upright: every link inside 1 deg from 8.04 s on |

The chain is built as a **multibond bond graph**: [Body1](block:Body1), [Body2](block:Body2) are `RigidBody2D` composites with a mass and an inertia about the centre of mass, joined by `Revolute2DCompliant` joints ([Joint1](block:Joint1), [Joint2](block:Joint2)). The motor ([Motor](block:Motor)), the shaft ([Shaft](block:Shaft)) and the gearbox ([Gear](block:Gear)) are stdlib drive blocks; the controller [Ctrl](block:Ctrl) is project firmware sampled at 1 kHz.

![Mid swing-up|600](assets/5fc10ec16eaa.png)

![Balanced before the disturbance|600](assets/670d6c38b8c9.png)

## Pages

- [The multibond structure](page:structure): blocks, bonds, poses and the drive train.
- [Equations of motion](page:dynamics): the design model, the parameters and the check against the bond graph.
- [Trajectory optimisation](page:trajectory): the direct-collocation formulation of the swing-up.
- [TVLQR and LQR](page:control): the feedback around the trajectory, the catch rule and the balance.
- [Results](page:results): plots of the run and the acceptance checks.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Upright/a1](signal:Upright/a1) and the others) shows the swing-up, the catch and the recovery; "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) the use of the supply.
- Raise `DistForce/amplitude` and `DistTorque/amplitude` together (the torque is the force times the 0.18 m lever arm to the tip): the recovery needs more voltage, and a large enough pulse saturates the 12 V supply and tips the chain over.
- Open the **3D View** tab to watch the swing-up; the joint bindings follow the joint angles.
- Change a link mass without re-running `design/design.py`: the gains are matched to the design plant, which shows the margin of the design.
