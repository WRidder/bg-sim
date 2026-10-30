@@ figures reaction-wheel-1d
{
  "diagram": {"kind": "diagram", "model": "reaction-wheel-1d"},
  "scene": {"kind": "scene", "model": "reaction-wheel-1d", "t": 0.3},
  "run": {
    "kind": "plot", "model": "reaction-wheel-1d", "xlim": [0, 2],
    "rows": [
      {"ylabel": "cube angle [deg]", "series": [{"signal": "Body/theta", "label": "Body/theta", "scale": 57.29577951308232}]},
      {"ylabel": "wheel speed [rad/s]", "series": [{"signal": "Drive/wsense/y", "label": "absolute (Drive/wsense/y)"}, {"signal": "RelSpeed/y", "label": "relative to the cube (RelSpeed/y)", "style": "--"}], "legend": true},
      {"ylabel": "voltage [V]", "series": [{"signal": "LQR1/u", "label": "LQR1/u", "color": "#1b9e77"}], "hlines": [{"y": 12, "label": "clamp +-12 V"}, {"y": -12}], "legend": true}
    ]
  }
}
@@ page reaction-wheel-1d overview - | Overview
# Cube on an edge with a reaction wheel (1D)

A 0.12 m cube stands on one edge (a body diagonal vertical) and starts 0.05 rad (2.9 deg) off upright. A DC motor with its housing on the cube spins a wheel inside it; the wheel's reaction torque holds the cube up. A 2 ms **discrete LQR** on $[\theta, \dot\theta, \omega_{rel}]$ sets the motor voltage, clamped to $\pm 12$ V. This is the 1D, iconic-Rotation counterpart of `reaction-wheel-2d` and `reaction-wheel-3d` (plan 9.7).

![The model canvas|900](@fig:diagram)

Signal flow: the angle sensor [AngleSens](block:AngleSens) and speed sensor [SpeedSens](block:SpeedSens) read the cube [Body](block:Body); [RelSpeed](block:RelSpeed) forms the wheel speed relative to the cube from the drive's own wheel-speed tap; [LQR1](block:LQR1) sets the voltage of [Drive](block:Drive), the motor with wheel whose housing sits on the cube.

## What to try

- Open the **Plots** tab: "Cube angle" ([Body/theta](signal:Body/theta)) shows the saturated start-up and the small overshoot, "Wheel speed" ([Drive/wsense/y](signal:Drive/wsense/y), [RelSpeed/y](signal:RelSpeed/y)) the wheel absorbing the cube's momentum, "Motor voltage" ([LQR1/u](signal:LQR1/u)) the 12 V samples at the start.
- Raise the initial tilt (the start `theta` of `Body` and the start `phi` of `AngleSens`, together): the clamp stays active longer and the wheel spins faster. The 12 V limit and the wheel inertia set the largest tilt that can still be caught.
- Change `Body/m` without re-running `design.py`: the gains are no longer matched to the plant, which shows the margin of the design.

## 3D view

`scenes/reaction-wheel-1d.sdf` is a 0.12 m semi-transparent cube whose lowest edge is the world Y axis, with an orange wheel disc and a dark spoke on its centre. The cube link is pitched by 45 deg so that an edge points down; the centre is then $0.12\sqrt2/2 = 0.0849$ m above the edge, the model's $l$. The binding `joint:edge` follows [Body/theta](signal:Body/theta) and `joint:wheel_joint` follows `Drive/phi_rel` (wheel angle relative to the cube, about half a turn over the run).

![3D view at t = 0.3 s|500](@fig:scene)

Continue with [the plant](page:plant), [the controller design](page:controller) and [the results](page:results).
@@ page reaction-wheel-1d plant overview | Plant
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
@@ page reaction-wheel-1d controller overview | Discrete LQR design
# Discrete LQR design

[LQR1](block:LQR1) (`library/LQR.jl`) applies

$$u_k = \operatorname{clamp}\!\big(-(K_\theta\,\theta + K_{\dot\theta}\,\dot\theta + K_w\,\omega_{rel}),\ -12,\ 12\big)$$

in a `@discrete Ts = 2e-3` scope: it samples the state at each tick and holds $u$ until the next one (the declared 0 V output is held before the first tick at $t = T_s$).

## Design (`design/design.py`)

With $x = (\theta, \dot\theta, \omega_{rel})$, $a = m g l$ and the winding inductance neglected in the design ($L/R = 0.1$ ms is 20 times shorter than $T_s$; the non-linear check in the script keeps it):

$$A = \begin{pmatrix} 0 & 1 & 0 \\ a/J & 0 & k^2/(R J) \\ -a/J & 0 & -\frac{k^2}{R}\left(\frac{1}{J_w} + \frac{1}{J}\right) \end{pmatrix}, \qquad B = \begin{pmatrix} 0 \\ -k/(R J) \\ \frac{k}{R}\left(\frac{1}{J_w} + \frac{1}{J}\right) \end{pmatrix}.$$

$(A, B)$ is discretised exactly with a zero-order hold at $T_s = 2$ ms; the discrete Riccati equation gives $K = (R + B_d^T P B_d)^{-1} B_d^T P A_d$ for $u_k = -K x_k$.

Weights with the normalisation $q_i = 1/\sigma_i^2$:

| state / input | scale $\sigma$ | weight |
| --- | --- | --- |
| $\theta$ | 0.02 rad | $q = 2500$ |
| $\dot\theta$ | 0.2 rad/s | $q = 25$ |
| $\omega_{rel}$ | 10 rad/s | $q = 0.01$ |
| $u$ | 12 V | $r = 1/144$ |

Result written into `K_theta`, `K_thetadot`, `K_wheel` of `LQR1`:

$$K = (-446.597400,\ -43.875365,\ -0.762835)\ \text{(V/rad, V s/rad, V s/rad)}.$$

Discrete closed-loop poles 0.3762, 0.9802, 0.9967, i.e. $-488.8$, $-10.0$, $-1.65$ s$^{-1}$ continuous equivalents. The unclamped demand at the initial tilt is 22.3 V, so the 12 V clamp is active for the first three samples and never again: after 0.1 s the voltage stays below 0.083 V.

Re-run `uv run examples/reaction-wheel-1d/design/design.py` after changing a weight; it writes the new gains into `LQR1`.
@@ page reaction-wheel-1d results overview | Results and checks
# Results and checks

![Cube angle, wheel speeds and motor voltage, first two seconds|900](@fig:run)

`design.py` also integrates the non-linear closed loop (with $\sin\theta$, the winding inductance, the 2 ms hold and the clamp); the model run reproduces it to better than 1e-5 rad.

| quantity | design.py and model run |
| --- | --- |
| peak $\lvert u \rvert$ | 12.000 V |
| peak wheel speed (absolute / relative to the cube) | 4.165 / 4.684 rad/s |
| $\theta(0.1\ \mathrm{s})$ | 0.014607 rad |
| $\lvert\theta\rvert$ over $t \ge 2$ s | 3.8929e-4 rad (0.0223 deg) |
| inside 0.2 deg from | 0.654 s |
| $\theta(4\ \mathrm{s})$ | -1.44e-5 rad |
| wheel angle relative to the cube at 4 s | 3.075 rad |

## Acceptance checks (22, `expected.json`)

- [Body/theta](signal:Body/theta): 0.05 at $t = 0$; below 0.2 deg (0.0034906585 rad) from 0.7 s and over $[2, 4]$ s; values at 0.1, 0.5, 1 and 4 s: 0.014607, -0.004185, -0.002021, -1.4395e-5 rad (tolerance 2e-5); the angle sensor [AngleSens/y](signal:AngleSens/y) agrees with the body's own angle to 1e-6;
- [LQR1/u](signal:LQR1/u): $\lvert u\rvert \le 12$, exactly 12 in $[0, 0.01]$ s, below 0.1 V after 0.1 s, 0 at $t = 0$;
- wheel speed [Drive/wsense/y](signal:Drive/wsense/y) at most 300 rad/s (peak 4.1652 within 0.01), [RelSpeed/y](signal:RelSpeed/y) peak 4.6839, 0.9983 at 1 s, 0.0071 at 4 s, wheel angle `Drive/phi_rel` 3.075 rad at 4 s;
- no E901, E106, W201, W202, W205 or W206 (the run reports no diagnostics at all).
