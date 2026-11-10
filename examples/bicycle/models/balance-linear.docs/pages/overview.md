# The balance controller on the linear model

The controller of [balance](model:balance) on the linearised benchmark ([linear](model:linear)) at 3 m/s: the model the controller was designed on. It runs in a fraction of a second.

![Lean and steer torque|900](assets/b2e07065ca52.png)

Here the turn settles exactly on the set-point: lean 0.1 rad, steer 0.1196 rad, heading rate 0.3346 rad/s and a holding torque of −0.635 N m, the steady turn computed in `design/design.py`. The 3D model of [balance](model:balance) follows this run to within 0.0016 rad of lean.
