# Plant

| part | block |
| --- | --- |
| cube | project block `InvertedPendulumBody` ([Body](block:Body)): the stdlib `Inertia` with gravity. $J = 4\cdot10^{-3}$ kg·m² about the edge (wheel excluded), $m = 0.6$ kg, $l = 0.085$ m, $\theta(0) = 0.05$ rad. Both ports sit on the same absolute rotation: port `b` carries the sensors, port `a` the motor housing |
| motor and wheel | stdlib `drives/ReactionWheel` ([Drive](block:Drive)): $k_t = 0.0335$ N·m/A, $R = 1\ \Omega$, $L = 0.1$ mH, absolute wheel inertia $J_w = 6\cdot10^{-4}$ kg·m² (rotor included), housing on the cube |
| sensors | [AngleSens](block:AngleSens) (starts at $\varphi = \theta(0) = 0.05$) and [SpeedSens](block:SpeedSens) on the cube |
| controller | project block `LQR` ([LQR1](block:LQR1)), sampled every 2 ms |

## Equations

With the cube angle $\theta$ from upright, the wheel speed relative to the cube $\omega_{rel}$ and the motor torque $\tau = k_t\,i$ on the wheel (the reaction $-\tau$ acts on the cube):

$$J\,\ddot\theta = m g l \sin\theta - \tau, \qquad J_w\,(\ddot\theta + \dot\omega_{rel}) = \tau, \qquad L\,\dot i + R\,i + k_t\,\omega_{rel} = u .$$

The cube is an inverted pendulum with unstable pole $\sqrt{m g l / J} \approx 11.1$ s$^{-1}$ (open-loop eigenvalues +11.06, -11.35, -1.86 s$^{-1}$ of the linear design model).

## Two deviations from the plan's wording

1. **`ReactionWheel` instead of `DCMotor` plus a wheel `Inertia`.** The stdlib `DCMotor` is referenced to an inertial shaft frame: its electromagnetic torque has no stator reaction and its back-EMF is $k\,\omega_{shaft}$, not $k\,(\omega_{shaft} - \omega_{housing})$. A cube driven through it was measured to tip the wrong way, so angular momentum was not conserved and no controller could balance it. `drives/ReactionWheel` is the same motor written as an action/reaction pair ($+k i$ on the wheel, $-k i$ on the housing, back-EMF on the relative rate). It is a composite of stdlib blocks, so the plant is still iconic Rotation. Its taps give the wheel speed (`Drive/wsense/y`), the winding current (`Drive/isense/y`) and the wheel angle relative to the cube (`Drive/phi_rel`).
2. **`RelSpeed` is an inline two-input block, not the stdlib `Sum`**, which takes one vector input that a JSON signal graph cannot assemble from scalar outputs.
