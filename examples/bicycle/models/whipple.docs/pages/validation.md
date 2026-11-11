# Validation

## Against the paper's eigenvalues

The paper's table 2 lists the eigenvalues of the linearised bicycle at each whole speed. A run of this nonlinear model after a small push shows the same modes; a damped-oscillation fit of the steer (or lean) rate gives the weave's damping ratio $\zeta$ and natural frequency $\omega_n$:

| speed | push | table 2 weave pair | $\zeta$, $\omega_n$ (table 2) | $\zeta$, $\omega_n$ (3D bond graph) |
| --- | --- | --- | --- | --- |
| 3 m/s | 0.002 rad/s | 1.7068 ± 2.3158 i | −0.5933, 2.8768 | −0.5935, 2.8801 |
| 4 m/s | 0.01 rad/s | 0.4133 ± 3.0791 i | −0.1330, 3.1067 | −0.1353, 3.1045 |
| 5 m/s | 0.05 rad/s | −0.7753 ± 4.4649 i | 0.1711, 4.5317 | 0.1702, 4.5153 |
| 6 m/s | 0.05 rad/s | −1.5264 ± 5.8767 i | 0.2514, 6.0717 | 0.2508, 6.0596 |

A negative $\zeta$ is a growing oscillation. The fit itself is accurate to about 0.2 % (it gives 4.526 rad/s on the exact linear response at 5 m/s), so the bond graph agrees with the benchmark to the accuracy of the fit.

![At 5 m/s the weave dies out|900](assets/409003de6596.png)

![At 3 m/s it grows: below the weave speed the bicycle falls|900](assets/b341691aa01b.png)

Above the capsize speed the bicycle falls over slowly: at 8 m/s the capsize eigenvalue is +0.143/s. The lean of the bond graph at 6 s and 12 s is within 0.7 % of the linearised benchmark from the same start (0.3 % and 0.6 % low).

![At 8 m/s the weave dies out within a second, then the lean grows slowly (capsize)|900](assets/c85cb8b7e47f.png)

## Against the linear model

After a 0.05 rad/s push at 5 m/s, the lean and steer angles of this model and of model [linear](model:linear) differ by less than 8e-5 rad over 6 s, on a motion of 0.011 rad (0.7 %). The difference is the nonlinearity and the compliance of tyres and joints.

## Energy

The Whipple bicycle has no friction, so its energy is constant. [Energy](block:Energy) adds the kinetic energy $\tfrac12 V\cdot P$ and the potential energy of the four bodies, the tyre and joint springs and the energy dissipated in the tyres (`loss`). With the joint dampers off, `Ebal` stays constant to 0.07 mJ out of 1837 J:

![Energy book with the joint dampers off|900](assets/1d514354c27c.png)

Without their dampers the stiff joints keep a high-frequency vibration alive, and the tyres dissipate 2.8 J of it in 5 s. This is why the models keep the dampers on; they take 0.24 J in this run, which the book does not count.

## What is not the paper's model

- Tyres and joints are stiff springs, not rigid constraints. The static tyre deflection is under a millimetre, the side creep under 0.5 mm/s.
- The contact radius is 0.7 mm (rear) and 0.5 mm (front) larger than the wheel radius, so the wheels spin 0.2 % slower than in the paper for the same speed. This changes the gyroscopic terms by 0.2 %.
