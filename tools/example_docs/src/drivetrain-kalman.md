@@ figures drivetrain-kalman
{
  "diagram": {"kind": "diagram", "model": "drivetrain-kalman"},
  "scene": {"kind": "scene", "model": "drivetrain-kalman", "t": 0.5},
  "run": {
    "kind": "plot", "model": "drivetrain-kalman", "xlim": [0, 2],
    "rows": [
      {"ylabel": "load speed [rad/s]", "series": [{"signal": "IW2/p.f", "label": "plant IW2/p.f"}, {"signal": "LQG/w_load_hat", "label": "estimate LQG/w_load_hat", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "V/p.e", "label": "V/p.e", "color": "#1b9e77"}], "hlines": [{"y": 24, "label": "clamp 24 V"}, {"y": -24}], "legend": true}
    ]
  },
  "zoom": {
    "kind": "plot", "model": "drivetrain-kalman", "xlim": [0.9, 1.5],
    "rows": [
      {"ylabel": "load speed [rad/s]", "series": [{"signal": "IW2/p.f", "label": "plant IW2/p.f"}, {"signal": "LQG/w_load_hat", "label": "estimate LQG/w_load_hat", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "rod segment speeds [rad/s]", "series": [{"signal": "IW1/p.f", "label": "IW1"}, {"signal": "IM1/p.f", "label": "IM1"}, {"signal": "IM2/p.f", "label": "IM2"}, {"signal": "IW2/p.f", "label": "IW2"}], "legend": true}
    ]
  }
}
@@ page drivetrain-kalman overview - | Overview
# LQG on a flexible two-inertia drivetrain

Plan 9.5's multi-domain control sample. A **pure bond graph plant** (D28), made of a DC motor, a 10:1 gearbox, two wheel inertias and a flexible three-segment rod, is driven by a **1 ms discrete LQG firmware**: an LQR with integral action and a steady-state Kalman filter that reconstructs the load speed from the motor encoder alone. A 10 rad/s reference steps at 0.1 s and a -0.5 N·m load torque steps at 1 s. The model `drivetrain-backlash` swaps the ideal gear for a backlash composite.

![The model canvas|900](@fig:diagram)

Parts: the electrical 1-junction [Elec](block:Elec) with [R](block:R) and [IL](block:IL), the gyrator [GY](block:GY), the motor junction [MotorJ](block:MotorJ) with [IJm](block:IJm) and [Rd](block:Rd), the gear transformers [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1), the three rod segments ([Rod1](block:Rod1), [Rod2](block:Rod2), [Rod3](block:Rod3)), [WheelJ2](block:WheelJ2) with the load source [Load](block:Load), the sensors [MotorSpeed](block:MotorSpeed), [Theta](block:Theta), [Encoder](block:Encoder), [Current](block:Current) and the firmware [LQG](block:LQG).

## What to try

- **Plots** tab: "Load speed" overlays [IW2/p.f](signal:IW2/p.f) with [LQG/w_load_hat](signal:LQG/w_load_hat); zoom into $t = 1$ s to see the load step, the 9.0 rad/s dip and the 0.3 s recovery.
- Plot [V/p.e](signal:V/p.e) to see the $\pm 24$ V saturation on the reference step.
- Plot [IW1/p.f](signal:IW1/p.f), [IM1/p.f](signal:IM1/p.f), [IM2/p.f](signal:IM2/p.f) and [IW2/p.f](signal:IW2/p.f) together: the three rod segments ring at about 25 Hz during the step and settle in phase.
- Re-run `design/design.py` with a different `Q`: the gains are plain JSON parameters of `LQG` (the script rewrites them in both model files).

## 3D view

`scenes/drivetrain-kalman.sdf` has the motor rotor, the gearbox output, wheel 1, the two intermediate inertias of the rod and wheel 2. Only the motor angle [Theta/y](signal:Theta/y) is measured, so the gearbox output is $0.1\times$ `Theta/y` and each rod segment is a joint bound to its twist `C1/q`, `C2/q`, `C3/q`; wheel 2 lags wheel 1 by their sum.

![3D view at t = 0.5 s|500](@fig:scene)

Continue with [the plant](page:plant), [the LQG design](page:controller) and [the results](page:results). The variant with a backlash gear is documented in the model `drivetrain-backlash`.
@@ page drivetrain-kalman plant overview | Plant
# Plant

```
MSe(V) -> 1-junction( R=1 Ohm, L=1 mH ) -> GY(k=0.1) -> 1-junction( J_m=5e-5, R_d=1e-4 )
      -> TF(1) * TF(0.1) (10:1) -> WheelJ1( I=1e-3 ) -> S1(0) -+- Rod1(1): C=1/150, R=0.02
                                                              '- MidJ1( I=6.7e-5 ) -> S2(0) ...
      ... -> S3(0) -> WheelJ2( I=2e-3 ) -> Load( MSe, -0.5 N m at 1 s )
```

| quantity | value |
| --- | --- |
| motor | $R = 1\ \Omega$, $L = 1$ mH, $k_t = 0.1$ N·m/A, $J_m = 5\cdot10^{-5}$ kg·m², $R_d = 10^{-4}$ N·m·s/rad |
| gearbox | $n = 10$: `TFa` ($n = 1$) then `TFb` ($n = 0.1$); a TF reverses the flow, so the pair gives +10:1 |
| wheels | $J_1 = 10^{-3}$, $J_2 = 2\cdot10^{-3}$ kg·m² |
| rod | three segments, each $C = 1/150$ (= 0.00667) and $R = 0.02$ N·m·s/rad, with two intermediate inertias $6.7\cdot10^{-5}$ kg·m² (`IM1`, `IM2`); three 150 N·m/rad springs in series give 50 N·m/rad |
| load | -0.5 N·m effort source at $t = 1$ s (a +0.5 N·m resisting torque) |
| run | 2 s, 4001 points, `solver` auto (the ideal gear makes IW1 a dependent store, so the problem is a DAE), `reltol` 1e-8 |

The rod is the real three-segment rod, not a lumped equivalent: each segment is a 0-junction (the relative speed) with a 1-junction carrying the C and R in parallel, chained through the two intermediate inertias. The equations are those of the `drivetrain` example,

$$L\,\dot i = V - R\,i - k_t\,\omega_m, \qquad J_m\,\dot\omega_m = k_t\,i - R_d\,\omega_m - T_g,$$

with the rod modelled as three torsion springs $k_i = 150$ N·m/rad and dampers $c_i = 0.02$ N·m·s/rad in series.

## Sensors

The controller sees **one** measurement, the motor angle:

- [MotorSpeed](block:MotorSpeed): a `FlowSensor` on the motor junction;
- [Theta](block:Theta): a kinematic integrator of that speed (the D28 sensor exception);
- [Encoder](block:Encoder): a `Quantizer` at 1 ms with resolution $2\pi/4096 = 0.0015340$ rad (12 bit);
- [Current](block:Current): a `FlowSensor` on the electrical junction (recorded, not used by the controller).

There is no load-side sensor: $\omega_L$ is reconstructed by the Kalman filter.
@@ page drivetrain-kalman controller overview | LQG controller
# LQG controller

[LQG](block:LQG) is one `@discrete Ts = 1e-3` block (`library/LQGController.jl`). Its state estimate is

$$\hat x = (\theta_m,\ \omega_m,\ \theta_L,\ \omega_L,\ T_{load}),$$

the plan's four states plus the load torque. At every tick the block executes

$$\hat x \leftarrow \hat x + L\,(y - C_d\hat x), \qquad z \leftarrow z + T_s\,(w_{ref} - \hat\omega_L),$$

$$v = -K\hat x + K_i\,z + K_{ff}\,w_{ref}, \qquad u = \operatorname{clamp}(v,\ -u_{max},\ u_{max}), \qquad \hat x \leftarrow \Phi\,\hat x + B_d\,u,$$

where $y$ is the quantised encoder angle and `w_load_hat` is $\hat\omega_L$. If $\lvert v\rvert > u_{max}$ the integration of $z$ in that tick is undone (anti-windup). The matrices are written by `design/design.py`:

| parameter | value |
| --- | --- |
| `Phi` | 5x5 zero-order-hold model at 1 ms |
| `Bd` | (7.88e-4, 1.53, 2.6e-7, 9.3e-4, 0) |
| `Cd` | (1, 0, 0, 0, 0) |
| `L` | (0.214, 25.71, 0.0803, 0.9596, -2.002) |
| `K` | (176.25, 0.3955, -1762.5, 11.99, 0) |
| `Ki` | 223.31 |
| `Kff` | 16.95 V/(rad/s) |
| `umax` | 24 V |

(The discrete matrix is called `Phi` because `Ad` is the library's adjoint builtin.)

## Two deviations from the plan's literal code

1. **The reference is fed forward.** The plan's $v = -K\hat x + K_i z$ has no reference term, so at 10 rad/s its own state feedback would ask for more than 150 V. $K_{ff} = n K_2 + K_4 + k_t n$ cancels the speed feedback at the reference point and adds the back-EMF $k_t n\,w_{ref}$; the integral then only trims the load torque (the measured steady voltage is 10.5 to 10.7 V).
2. **The Kalman filter has five states.** A four-state filter keeps a steady bias of about 1.3 rad/s in $\omega_L$ while the load acts (the model cannot tell a load torque from a voltage offset). The fifth state is a random walk with $Q_n = 10^{-6}$ (N·m)² per sample, so the 0.5 N·m step is learned in a few tens of ms.

## Design (`design/design.py`)

The design linearises a 4-state model (quasi-static electrics, one lumped rod spring of 50 N·m/rad, the motor damping), discretises it with ZOH at 1 ms, solves an LQR with integral action and the steady-state Kalman filter, writes the matrices into both model documents and integrates the sampled closed loop against a 9-state reference (three-segment rod and the 1 mH electrics, RK4 at 2e-5) to print the acceptance values.

It designs in the relative coordinates $(\delta, \omega_m, \omega_L, z)$ with $\delta = \theta_m/n - \theta_L$ and $\dot z = w_{ref} - \omega_L$: in absolute angles the integral augmentation is not controllable ($z = w_{ref}t - \theta_L$ is a linear combination of the states). The gain maps back with $K = (k_\delta/n,\ k_{\omega_m},\ -k_\delta,\ k_{\omega_L})$ and $K_i = -k_z$.

Weights with $Q_{ii} = 1/\sigma_i^2$, $R = 1/\sigma_u^2$:

| state | $\sigma$ | weight |
| --- | --- | --- |
| rod twist $\delta$ | 0.32 rad | $q = 10$ |
| motor speed error $\omega_m - n\,w_{ref}$ | 100 rad/s | $q = 10^{-4}$ |
| load speed error $\omega_L - w_{ref}$ | 1 rad/s | $q = 1$ |
| integral $z$ | 0.07 rad | $q = 200$ |
| voltage | 24 V | $R = 1/576$ |

The twist is deliberately cheap: a stiff loop would fight the 25 Hz rod mode; $q_z = 200$ sets $K_i$ and the 0.3 s load recovery. The Kalman filter uses the encoder quantisation noise $R_n = (2\pi/4096)^2/12 = 1.96\cdot10^{-7}$ rad² and the torque random walk above (the four plant states carry a $10^{-12}$ numerical floor). The Riccati equations are solved by a Newton-Kleinman iteration from a stabilising seed because `scipy.linalg.solve_discrete_are` returns the anti-stabilising root with the pure integrator.
@@ page drivetrain-kalman results overview | Results and checks
# Results and checks

![Load speed, voltage and the estimate over the whole run|900](@fig:run)

The zoom on the load step at 1 s shows the dip, the recovery and the rod segments ringing:

![Zoom on the load step|900](@fig:zoom)

## Acceptance checks (`expected.json`, README measurements)

| check | limit | measured (README) |
| --- | --- | --- |
| [IW2/p.f](signal:IW2/p.f) at 0.6 s | 10 +- 2 % | 10.130 rad/s |
| [IW2/p.f](signal:IW2/p.f) at 1.3 s (0.3 s after the load step) | 10 +- 2 % | 10.112 rad/s |
| [IW2/p.f](signal:IW2/p.f) at 2.0 s | 10 +- 2 % | 10.123 rad/s |
| [LQG/w_load_hat](signal:LQG/w_load_hat) at 2.0 s | 10 +- 1 % | 9.9987 rad/s |
| RMS of `w_load_hat` minus `IW2/p.f` over $[0.5, 2]$ s | below 0.2 rad/s | 0.181 rad/s |
| largest $\lvert$ [V/p.e](signal:V/p.e) $\rvert$ | at most 24 V | 24.000 V (the clamp is active on the step) |
| diagnostics | no E901, E106, W206 | W201 (IW1/IJm in derivative causality) and W205 only |

The RMS residual is the encoder's 12-bit staircase at the 1 ms sampling phase plus the three-segment rod's two mid inertias, which the 4-state design model lumps away; the estimator has no load-side measurement.
@@ figures drivetrain-backlash
{
  "diagram": {"kind": "diagram", "model": "drivetrain-backlash"},
  "run": {
    "kind": "plot", "model": "drivetrain-backlash", "xlim": [0, 2],
    "rows": [
      {"ylabel": "load speed [rad/s]", "series": [{"signal": "IW2/p.f", "label": "plant IW2/p.f"}, {"signal": "LQG/w_load_hat", "label": "estimate LQG/w_load_hat", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "V/p.e", "label": "V/p.e", "color": "#1b9e77"}], "hlines": [{"y": 24}, {"y": -24}]}
    ]
  }
}
@@ page drivetrain-backlash overview - | Overview
# LQG drivetrain with gear backlash

The same plant, firmware and signals as `drivetrain-kalman`, but the ideal gear (`TFa` and `TFb`) is replaced by the [GearWithBacklash](block:Gear) composite from library `library/GearWithBacklash.jl`: a `LossyGear` ($n = 10$, $\eta = 1$) in series with a `GearBacklash` play. The controller is **the same LQG firmware designed for the ideal gear** (the design script writes identical matrices into both models), so this variant shows how the loop behaves when the model it was designed on is wrong.

![The model canvas|900](@fig:diagram)

## The backlash

`GearBacklash` has the tooth stiffness $k = 10^4$ N·m/rad, damping $d = 5$ N·m·s/rad and total play $\mathrm{gap} = 0.02$ rad. With the relative angle $\varphi$ and speed $w$ across the gear the torque is

$$T = \begin{cases} \max\big(k\,(\varphi - \tfrac{gap}{2}) + d\,w,\ 0\big) & \varphi > gap/2 \\ \min\big(k\,(\varphi + \tfrac{gap}{2}) + d\,w,\ 0\big) & \varphi < -gap/2 \\ 0 & \text{otherwise (flanks apart)} \end{cases}$$

and the ports apply $a.e = T$, $b.e = -T$.

## What changes

- The run completes (2 s, 4001 points) and the check only demands that the voltage stays within 24 V and that no E901, E106 or W206 appears. Plot [IW2/p.f](signal:IW2/p.f) against [LQG/w_load_hat](signal:LQG/w_load_hat): the loop settles into a limit cycle around 10 rad/s; the README gives an RMS of 0.43 rad/s between the estimate and the plant.
- Compare with the ideal-gear model: its estimate error RMS is 0.181 rad/s.
- The 3D scene additionally binds the gear play `Gear/play/phi` (gain -1) between the gear output and wheel 1.

![Load speed and voltage with backlash|900](@fig:run)

## Modelling notes

- The composite's `LossyGear` is ideal ($\eta = 1$): the fixture's 0.9 efficiency is a loss model, and with the phase-shifted algebraic switch the stiff DAE failed the solver (E901).
- The composite's ports declare `Rotation`, so the stdlib `GY` (two `Generic` ports) would straddle a Rotation and a Generic island (E102). The variant therefore uses `library/MotorGY.jl` ([GY](block:GY)), the same gyrator equations with explicit Electrical and Rotation ports. The final bond runs wheel 1 to the gear so that the single transformer inside the composite has the same +10:1 sign as the ideal `TF(1)·TF(0.1)` chain.
