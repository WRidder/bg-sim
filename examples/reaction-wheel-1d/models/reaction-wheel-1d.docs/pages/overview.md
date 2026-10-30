# Cube on an edge with a reaction wheel (1D)

A 0.12 m cube stands on one edge (a body diagonal vertical) and starts 0.05 rad (2.9 deg) off upright. A DC motor with its housing on the cube spins a wheel inside it; the wheel's reaction torque holds the cube up. A 2 ms **discrete LQR** on $[\theta, \dot\theta, \omega_{rel}]$ sets the motor voltage, clamped to $\pm 12$ V. This is the 1D, iconic-Rotation counterpart of `reaction-wheel-2d` and `reaction-wheel-3d` (plan 9.7).

![The model canvas|900](assets/2665c7ac0b54.png)

Signal flow: the angle sensor [AngleSens](block:AngleSens) and speed sensor [SpeedSens](block:SpeedSens) read the cube [Body](block:Body); [RelSpeed](block:RelSpeed) forms the wheel speed relative to the cube from the drive's own wheel-speed tap; [LQR1](block:LQR1) sets the voltage of [Drive](block:Drive), the motor with wheel whose housing sits on the cube.

## What to try

- Open the **Plots** tab: "Cube angle" ([Body/theta](signal:Body/theta)) shows the saturated start-up and the small overshoot, "Wheel speed" ([Drive/wsense/y](signal:Drive/wsense/y), [RelSpeed/y](signal:RelSpeed/y)) the wheel absorbing the cube's momentum, "Motor voltage" ([LQR1/u](signal:LQR1/u)) the 12 V samples at the start.
- Raise the initial tilt (the start `theta` of `Body` and the start `phi` of `AngleSens`, together): the clamp stays active longer and the wheel spins faster. The 12 V limit and the wheel inertia set the largest tilt that can still be caught.
- Change `Body/m` without re-running `design.py`: the gains are no longer matched to the plant, which shows the margin of the design.

## 3D view

`scenes/reaction-wheel-1d.sdf` is a 0.12 m semi-transparent cube whose lowest edge is the world Y axis, with an orange wheel disc and a dark spoke on its centre. The cube link is pitched by 45 deg so that an edge points down; the centre is then $0.12\sqrt2/2 = 0.0849$ m above the edge, the model's $l$. The binding `joint:edge` follows [Body/theta](signal:Body/theta) and `joint:wheel_joint` follows `Drive/phi_rel` (wheel angle relative to the cube, about half a turn over the run).

![3D view at t = 0.3 s|500](assets/624f8ca7e9eb.png)

Continue with [the plant](page:plant), [the controller design](page:controller) and [the results](page:results).
