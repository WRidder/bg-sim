# Conventions: from the script to the bond graph

## The mapping

The script feeds its trajectory through `transform_joint_data` ("to get the right output compared to Coppelia/Drake") before it evaluates $\tau(q, \dot q, \ddot q)$ and `rne_python`. With the trajectory $(q^t, \dot q^t, \ddot q^t)$ of `quintic`/`jtraj` (from 0 to 1 rad in 1 s) that is

$$
q_1 = -q_1^t - \tfrac{\pi}{2},\quad q_{j>1} = -q_j^t,\qquad \dot q = -\dot q^t,\quad \ddot q = -\ddot q^t .
$$

**The CSV files and the bond-graph model use exactly these transformed values.** In the model the joint angle is the counter-clockwise angle from $+x$ in the $x$-$y$ plane, which is the **horizontal plane** of the 3D scene (the joint axes point along the world $z$ axis, up), there is **no gravity**, and each $q_j$ is the *relative* angle between link $j-1$ and link $j$ (the first one is absolute). At $t = 0$ the first link points along $-y$ ($q_1 = -\pi/2$; the angle offset of the script is kept, it is only a starting direction now, not a hanging pose), the others are stretched, and the arm then swings clockwise by 1 rad in every joint. The torques are joint-side torques including the reflected motor terms $G^2 J_m \ddot q + B G^2 \dot q$; the model initial angles are the `q0` of the joints (`-1.5707963...` for joint 1) and the starts are at rest.

| quantity | script | CSV column | bond-graph signal |
| --- | --- | --- | --- |
| angle, rate, acceleration | after `transform_joint_data` | `q1..`, `qd1..`, `qdd1..` | [A3_Joint1/qout](signal:A3_Joint1/qout), `qdout` |
| torque (closed form) | `OneLinkRobot.tau` etc. | `tau_analytical1..` | `A3_TauErr*/ref_an` |
| torque (Robotics Toolbox) | `DHRobot.rne_python` | `tau_rtb1..` | `A3_TauErr*/ref_rtb` |
| torque of the model | | | [A3_Torque1/y](signal:A3_Torque1/y) |

## Parameters

The link parameters of `main()` are used unchanged: $a$ = 0.675 / 0.525 / 0.370 m, $m$ = 3.815 / 3.690 / 4.0 kg, $r$ = −0.291 / −0.182 / −0.360 m (centre of mass measured from the link **end**, so the distance from the joint is $a + r$), $I_{zz}$ = 0.310 / 0.146 / 0.016 kg·m² about the centre of mass, $B$ = 0.02 / 0.02 / 0.01, $G$ = 12 / 9.33 / 9.25 and $J_m$ = 4.92e-4 / 4.845e-4 / 1.859e-4. The payload is 1 kg at 0.1 m beyond the end of link 3.

## Things the script does that the example takes into account

- **No gravity for any arm** (user decision of 2026-10-30, X5.9b: the arms lie in the horizontal plane). The script sets `gravity=0` for the 1-link arm only and uses 9.81 m/s² along $-y$ for the 2- and 3-link analytical classes and Robotics Toolbox robots. `reference/generate.py` deviates from that: it passes `gravity=0` to every analytical class and sets `r.gravity = [0, 0, 0]` on every Robotics Toolbox robot (`planar_robot.py` itself is unchanged), and every body has `g0 = 0`. The torques are the inertial, Coriolis and drive-train terms only; peak torques dropped from 45 / 17 (2-link) to 39 / 13.5 N·m, from 99 / 43 / 2.3 (3-link) to 88 / 35 / 2.0 N·m and from 131 / 62 / 12 (payload) to 118 / 53 / 10 N·m.
- **`transform_joint_data` on a 1-D array** (the 1-link case) adds the $-\pi/2$ offset to element 0 only (`q[0] += offset`), i.e. to the first *sample*. The generator keeps the intended convention (the offset on the whole joint-1 trajectory); the torque does not depend on it, which the generator asserts.
- **`get_total_mass`** adds a list to a number (`total_mass += self.payload`); it is never called, and the copy of the script in `reference/` is unchanged.
- The 2-link analytical class has **no payload** (its `tau` ignores `pay_*`), the 3-link class is evaluated without payload for the main model and with it for `planar-links-payload`, which the Robotics Toolbox models as a fourth link with the 4th joint held at 0.

## Analytical against Robotics Toolbox

The generator also prints the user's own comparison on the dense 1 kHz grid:

| arm | max abs difference, joints 1, 2, 3 [N·m] |
| --- | --- |
| 1-link | 3.6e-15 |
| 2-link | 2.8e-14, 5.3e-15 |
| 3-link | 5.7e-14, 2.1e-14, 4.4e-16 |
| 3-link + payload | 5.7e-14, 2.1e-14, 5.3e-15 |

The two references are the same model to rounding, so the bond-graph model is compared against two independent implementations of one set of equations.
