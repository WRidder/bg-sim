@@ figures drivetrain-position
{
  "diagram": {"kind": "diagram", "model": "drivetrain-position"},
  "scene": {"kind": "scene", "model": "drivetrain-position", "t": 1.5},
  "run": {
    "kind": "plot", "model": "drivetrain-position", "xlim": [0, 3.2],
    "rows": [
      {"ylabel": "load position [rad]", "series": [{"signal": "ThetaL/y", "label": "load ThetaL/y"}, {"signal": "Ctrl/r_traj", "label": "trajectory Ctrl/r_traj", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "V/p.e", "label": "V/p.e", "color": "#1b9e77"}], "hlines": [{"y": 24, "label": "limit 24 V"}, {"y": -24}], "legend": true},
      {"ylabel": "shaft twist [rad]", "series": [{"signal": "C/q", "label": "C/q", "color": "#7570b3"}]}
    ]
  },
  "estimator": {
    "kind": "plot", "model": "drivetrain-position", "xlim": [0, 3.2],
    "rows": [
      {"ylabel": "load position [rad]", "xlim": [2.0, 3.2], "series": [{"signal": "ThetaL/y", "label": "plant ThetaL/y"}, {"signal": "Ctrl/theta_L_hat", "label": "estimate", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "load torque [N m]", "series": [{"signal": "Ctrl/T_hat", "label": "estimate Ctrl/T_hat", "color": "#d95f02"}], "hlines": [{"y": 0.2, "label": "applied 0.2 N m"}], "legend": true, "legend_loc": "lower right"}
    ]
  },
  "versus": {
    "kind": "plot", "model": "drivetrain-position", "xlim": [0, 3.2],
    "rows": [
      {"ylabel": "load position [rad]", "series": [{"signal": "naive:ThetaL/y", "model": "naive", "signal_in": "ThetaL/y", "label": "naive PID", "color": "#d95f02"}, {"signal": "ThetaL/y", "label": "drivetrain-position", "color": "#1f77b4"}], "hlines": [{"y": 1.0, "label": "command 1 rad"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "naive:V/p.e", "model": "naive", "signal_in": "V/p.e", "label": "naive PID", "color": "#d95f02"}, {"signal": "V/p.e", "label": "drivetrain-position", "color": "#1f77b4"}], "hlines": [{"y": 24, "label": "limit 24 V"}, {"y": -24}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "shaft twist [rad]", "series": [{"signal": "naive:C/q", "model": "naive", "signal_in": "C/q", "label": "naive PID", "color": "#d95f02"}, {"signal": "C/q", "label": "drivetrain-position", "color": "#1f77b4"}], "legend": true, "legend_loc": "lower right"}
    ]
  }
}
@@ page drivetrain-position overview - | Overview
# Load-position servo on a compliant drivetrain

A DC motor drives a load wheel through a 10:1 gear and a **soft shaft** (1.2 N·m/rad, 40 times softer than the shaft of `drivetrain-kalman`). The task is a **position step of the load wheel**: 1 rad at 0.2 s, then a 0.2 N·m load torque at 2.2 s, with a 24 V motor supply.

The shaft and the load wheel form a torsional mode at **3.9 Hz with damping 0.034**. A position loop that is fast enough to be useful has to cross over right there, so the loop cannot ignore the mode. This model shows how a controller that knows about it behaves. The model `naive` runs the same plant with a textbook PID tuned for a rigid drivetrain: it overshoots by 104 % and rings at the mode for seconds.

![The model canvas|900](@fig:diagram)

The plant is a **pure bond graph**: the voltage source [V](block:V) on the electrical 1-junction [Elec](block:Elec) with [R](block:R) and [IL](block:IL), the gyrator [GY](block:GY) into the motor junction [MotorJ](block:MotorJ) with [IJm](block:IJm) and [Rd](block:Rd), the gear [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1) with [IW1](block:IW1), the 0-junction [S1](block:S1) with the shaft 1-junction [Shaft](block:Shaft) (compliance [C](block:C), damper [D](block:D)), and [WheelJ2](block:WheelJ2) with [IW2](block:IW2) and the load source [Load](block:Load). The firmware is [Ctrl](block:Ctrl).

## What to try

- **Plots**, "Load position": [ThetaL/y](signal:ThetaL/y) follows the smooth trajectory [Ctrl/r_traj](signal:Ctrl/r_traj) and settles without ringing.
- Plot [C/q](signal:C/q): the shaft twists by up to 0.33 rad during the move and the twist returns to its resting value without ringing.
- Plot [V/p.e](signal:V/p.e): the voltage stays below 14 V, far below the 24 V limit.
- Open the model `naive` and compare the same plots.
- Shorten `Ttraj` of [Ctrl](block:Ctrl) (it is a plain parameter) and watch the shaft twist and the voltage: a faster trajectory has more energy at the mode and the feedback has to work harder.

## 3D view

`scenes/drivetrain-position.sdf` shows the motor, the gearbox, wheel 1, a thin 0.7 m shaft with a red stripe, and wheel 2. Wheel 1 turns by $0.1\,$[Theta/y](signal:Theta/y), wheel 2 by [ThetaL/y](signal:ThetaL/y), and the shaft is four segments that each twist by a quarter of [C/q](signal:C/q). The markers on the wheels and the stripe on the shaft show the rotation and the twist.

![3D view at t = 1.5 s, the load wheel 1 rad ahead of the start|500](@fig:scene)

Continue with [the structure](page:structure), [the equations](page:equations), [the controller](page:controller) and [the results](page:results).
@@ page drivetrain-position structure overview | Structure (bond graph)
# Structure: the bond graph

```
MSe(V) -> 1( R=1 Ohm, I=L=1 mH ) -> GY(k_t=0.1) -> 1( I=J_m=5e-5, R=R_d=1e-4 )
      -> TF(1) * TF(0.1) (10:1) -> 1( I=J1=1e-3 ) -> 0 ---------- 1( C=1/k, R=c ) (the shaft)
                                                      '-> 1( I=J2=2e-3 ) <- MSe(load)
```

| element | node | value |
| --- | --- | --- |
| voltage source | [V](block:V) | `MSe`, effort = firmware voltage |
| armature | [R](block:R), [IL](block:IL) | $R = 1\ \Omega$, $L = 1$ mH on the 1-junction [Elec](block:Elec) |
| motor constant | [GY](block:GY) | $k_t = 0.1$ N·m/A = V·s/rad |
| rotor | [IJm](block:IJm), [Rd](block:Rd) | $J_m = 5\cdot10^{-5}$ kg·m², $R_d = 10^{-4}$ N·m·s/rad on [MotorJ](block:MotorJ) |
| gear | [TFa](block:TFa), [TFb](block:TFb) | $n = 10$: `TF(1)` then `TF(0.1)` (a TF reverses the flow, so the pair is +10:1) |
| wheel 1 | [IW1](block:IW1) | $J_1 = 10^{-3}$ kg·m² on [WheelJ1](block:WheelJ1) |
| shaft | [C](block:C), [D](block:D) | $k = 1.2$ N·m/rad ($C = 1/k$), $c = 10^{-3}$ N·m·s/rad on the 1-junction [Shaft](block:Shaft) |
| wheel 2 | [IW2](block:IW2) | $J_2 = 2\cdot10^{-3}$ kg·m² on [WheelJ2](block:WheelJ2) |
| load | [Load](block:Load), [LoadStep](block:LoadStep) | `MSe`, effort $-0.2$ N·m from 2.2 s (a resisting torque) |

The shaft is a spring and a damper that carry the same flow (the relative speed of the wheels), so they sit on a 1-junction. That junction is connected to the 0-junction [S1](block:S1), whose flows add and whose torque is common to wheel 1, the shaft and wheel 2. [C](block:C)'s state `C/q` is the twist.

The ideal gear welds wheel 1 to the rotor, so the compiler reports W201 (`IW1` and `IJm` in derivative causality) and the run uses a DAE solver. The compliance of the shaft is the only compliance: the rotor and wheel 1 are one rigid body.

## Sensors

- [MotorSpeed](block:MotorSpeed): a flow sensor on the motor junction; [Theta](block:Theta) integrates it to the motor angle; [Encoder](block:Encoder) samples it at 1 ms with $2\pi/4096$ rad (12 bit).
- [LoadSpeed](block:LoadSpeed), [ThetaL](block:ThetaL) and [EncoderL](block:EncoderL): the same for the load wheel, with $2\pi/16384$ rad (14 bit).
- [Current](block:Current): a flow sensor on the electrical junction, recorded only.

The load encoder is a deliberate choice: the controlled variable is the load angle, and with only a motor encoder the load angle and a load torque cannot be told apart for slow changes (see [the controller](page:controller)).
@@ page drivetrain-position equations overview | Equations
# Equations

With the ideal gear, $J_{eq} = J_m + J_1/n^2 = 6\cdot10^{-5}$ kg·m². The state is $x = (\theta_m, \omega_m, i, \theta_L, \omega_L)$, the shaft twist $\delta = \theta_m/n - \theta_L$ and the shaft torque $\tau = k\,\delta + c\,\dot\delta$:

$$L\,\dot i = V - R\,i - k_t\,\omega_m,$$

$$J_{eq}\,\dot\omega_m = k_t\,i - R_d\,\omega_m - \frac{\tau}{n}, \qquad J_2\,\dot\omega_L = \tau - T_{load}.$$

These are the equations of the bond graph; `design/design.py` integrates them (exactly, with a zero-order hold) and the model `drivetrain-position-open-loop` checks the bond graph against them to $10^{-8}$ rad.

## The mode

With the motor held by its back-EMF, the load wheel hangs on the shaft spring:

$$f_{mode} = \frac{1}{2\pi}\sqrt{\frac{k}{J_2}} = 3.90\ \text{Hz}.$$

The poles of the voltage-driven plant are $-0.84 \pm 24.5\,j$ (3.91 Hz, $\zeta = 0.034$), two real poles at $-213$ and $-788$ rad/s (the mechanical and the electrical time constant) and one pole at zero (the position). With the motor free instead (shaft damping alone) the mode is 4.50 Hz with $\zeta = 0.012$; the back-EMF damps it a little and keeps it near 3.9 Hz.

A position loop with a bandwidth of 5 Hz or more, which a rigid-body design asks for, has to cross over beside this mode.

## Design model

For the controller the electrical pole at 160 Hz is treated as quasi-static ($i = (V - k_t\omega_m)/R$):

$$\dot\delta = \frac{\omega_m}{n} - \omega_L, \quad J_{eq}\dot\omega_m = -\Big(\frac{k_t^2}{R} + R_d + \frac{c}{n^2}\Big)\omega_m - \frac{k}{n}\,\delta + \frac{c}{n}\,\omega_L + \frac{k_t}{R}\,V, \quad J_2\dot\omega_L = k\,\delta + \frac{c}{n}\,\omega_m - c\,\omega_L - T_{load}.$$

The firmware discretizes this model with a zero-order hold at 1 ms. The prediction in `design/design.py` uses the full 5-state model with the inductance, so the difference between the two is part of what `expected.json` checks.
@@ page drivetrain-position controller overview | Controller design
# Controller design

[Ctrl](block:Ctrl) is one `@discrete Ts = 1e-3` block (`library/PositionController.jl`); `design/design.py` writes its gains between the `GAINS` markers. Every tick it does four things.

## 1. Smooth trajectory

A change of the command [Ref](block:Ref) starts a **septic smoothstep** from the old to the new value over $T = 0.8$ s:

$$r(t) = r_0 + (r_1 - r_0)\,s(\tau),\quad s = 35\tau^4 - 84\tau^5 + 70\tau^6 - 20\tau^7,\quad \tau = t/T,$$

with zero velocity, acceleration and jerk at both ends. A raw step has energy at every frequency, including 3.9 Hz; the smoothstep has almost none above $1/T$ = 1.25 Hz, so the command does not excite the mode, and the feedback is left with errors and disturbances. A first-order or critically damped linear prefilter would also do, but its derivatives are not exact, and the feedforward below needs $\dot r$, $\ddot r$ and $\dddot r$ in closed form. The trajectory is the output [Ctrl/r_traj](signal:Ctrl/r_traj).

## 2. Observer

A steady-state Kalman filter on $\hat x = (\theta_m, \omega_m, \theta_L, \omega_L, T_{load})$ (the load torque is a random walk, $Q = 3\cdot10^{-8}$ (N·m)² per sample) updates with **both encoders**,

$$\hat x \leftarrow \hat x + L_m\,(y_m - \hat\theta_m) + L_l\,(y_l - \hat\theta_L), \qquad \hat x \leftarrow \Phi\,\hat x + B_d\,u,$$

with the noise of the encoder quantization, $R_n = \operatorname{diag}\big((2\pi/4096)^2/12,\ (2\pi/16384)^2/12\big)$.

*Why the load encoder?* The load angle is the controlled variable, and the soft shaft decouples it from the motor: with the motor encoder alone, the load angle is only a model output, and a slow load torque ($T/k$ = 0.17 rad of twist) and a slow motion of the load look alike. The 14-bit load encoder resolves that, at the price of one cheap sensor (dual-loop servo practice). The 12-bit motor encoder gives the fast, collocated signal that the damping needs. The observer poles are at $-167$, $-88$, $-47 \pm 82j$ and $-14$ rad/s. Its load torque estimate [Ctrl/T_hat](signal:Ctrl/T_hat) and angle estimate [Ctrl/theta_L_hat](signal:Ctrl/theta_L_hat) are outputs.

## 3. Feedforward by model inversion

For the trajectory, the shaft has to carry $\tau_r = J_2\ddot r + c J_2\dddot r/k + \hat T_{load}$. From that the firmware computes the twist $\delta_r = \tau_r/k$, the motor speed $\omega_{m,r} = n(\dot r + J_2\dddot r/k)$, the motor torque $J_{eq}n\ddot r + R_d\omega_{m,r} + \tau_r/n$ and the voltage

$$u_{ff} = \frac{R}{k_t}\big(J_{eq}\,n\,\ddot r + R_d\,\omega_{m,r} + \tau_r/n\big) + k_t\,\omega_{m,r}.$$

The estimated load torque is part of $\tau_r$, so a torque step is answered at once and the integrator only trims.

## 4. LQR with integral action

The feedback acts on the error of $(\delta,\ \omega_m,\ \omega_L,\ \theta_L)$ against the reference above and on the integral $z = \int(\hat\theta_L - r)\,dt$:

$$v = u_{ff} - K\,(\delta - \delta_r,\ \hat\omega_m - \omega_{m,r},\ \hat\omega_L - \dot r,\ \hat\theta_L - r,\ z), \qquad u = \operatorname{clamp}(v, -24, 24).$$

If $\lvert v\rvert > 24$ the integration of $z$ in that tick is undone (anti-windup). $K$ is the discrete LQR (ZOH at 1 ms, quasi-static electrics) with Bryson weights $q_i = 1/\sigma_i^2$ and $R = 1/24^2$:

| state | $\sigma$ | gain in $K$ |
| --- | --- | --- |
| twist $\delta$ | 0.15 rad | 399 V/rad |
| motor speed error | 100 rad/s | 0.211 V·s/rad |
| load speed error | 0.5 rad/s | 42.9 V·s/rad |
| load position error | 0.05 rad | 458 V/rad |
| integral $z$ | 0.03 rad·s | 647 V/(rad·s) |

The LQR sees the twist and both speeds, so it **damps the shaft mode by feedback**: the closed-loop poles are $-427$, $-9.9$, $-1.7$ rad/s and a pair $-78 \pm 71j$ (16.8 Hz, $\zeta = 0.74$) where the plant had the 3.9 Hz pair with $\zeta = 0.034$. The slow poles belong to the integrator.

Since the observer sits in the loop, the quantization noise of the encoders reaches the voltage: $K_{\omega_L}$ is the largest cause. That is why the load speed weight is moderate (the voltage has a ripple of 1.3 V peak to peak at rest, 5 % of the supply). A faster design is possible, and this one is a balance between speed, noise and the margin to the limit.
@@ page drivetrain-position results overview | Results and checks
# Results and checks

The three plots come from real runs of this project. The first shows the showcase run.

![Load position, voltage and shaft twist of drivetrain-position|900](@fig:run)

The same signals with the `naive` model overlaid. The textbook PID overshoots by 104 %, rings at the shaft mode (3.8 Hz), saturates the supply on the step and still swings by 0.73 rad when the disturbance arrives:

![naive against drivetrain-position|900](@fig:versus)

The estimator after the load torque step at 2.2 s (the estimate follows the load angle within 3 mrad RMS; the torque estimate converges in about 0.1 s):

![The Kalman filter after the load step|900](@fig:estimator)

## Measured numbers

| | `naive` (PID) | `drivetrain-position` |
| --- | --- | --- |
| overshoot of the 1 rad step | 104.4 % (peak 2.044 rad at 0.36 s) | 0.02 % |
| time to stay inside the 2 % band | never (rings until the end of the step phase) | 0.66 s after the command (the trajectory takes 0.8 s) |
| oscillation 1.4 to 2.2 s | 1.15 rad peak to peak | 0.39 mrad peak to peak |
| dip at the 0.2 N·m disturbance | 0.73 rad | 0.058 rad, back inside 20 mrad in 0.13 s |
| peak voltage | 24.00 V (saturated at the step) | 13.3 V (at the disturbance) |
| maximum shaft twist | 0.90 rad | 0.33 rad |

## Checks (`expected.json`)

- rest before the step: [ThetaL/y](signal:ThetaL/y) and [IW2/p.f](signal:IW2/p.f) are zero before 0.19 s;
- settling inside 0.02 rad within 0.9 s, overshoot below 2 %, value at 2.15 s within 5 mrad of 1 rad;
- peak-to-peak below 4 mrad between 1.4 and 2.15 s (residual oscillation after settling);
- disturbance: dip of at most 0.092 rad, back within 10 mrad at 3.2 s, [Ctrl/T_hat](signal:Ctrl/T_hat) at 0.2 N·m within 5 %;
- the voltage [V/p.e](signal:V/p.e) is at most 24 V;
- seven `cursor_value` checks of [ThetaL/y](signal:ThetaL/y) against the closed-loop prediction of `design/design.py` (4 mrad tolerance; the largest difference is 2.7 mrad, in the first 100 ms after the disturbance);
- no error diagnostics.

The model `drivetrain-position-open-loop` runs the plant alone (+2 V at 0.05 s and a load step at 0.6 s) and compares load and motor angle with the ODE at eight times: the largest difference is $1.4\cdot10^{-8}$ rad.
@@ figures naive
{
  "diagram": {"kind": "diagram", "model": "naive"},
  "run": {
    "kind": "plot", "model": "naive", "xlim": [0, 3.2],
    "rows": [
      {"ylabel": "load position [rad]", "series": [{"signal": "ThetaL/y", "label": "load ThetaL/y"}, {"signal": "Ref/y", "label": "command Ref/y", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "V/p.e", "label": "V/p.e", "color": "#1b9e77"}], "hlines": [{"y": 24, "label": "limit 24 V"}, {"y": -24}], "legend": true},
      {"ylabel": "shaft twist [rad]", "series": [{"signal": "C/q", "label": "C/q", "color": "#7570b3"}]}
    ]
  }
}
@@ page naive overview - | Overview
# Naive: a textbook PID on the motor position

The same compliant drivetrain as in `drivetrain-position` (1.2 N·m/rad shaft, first mode 3.9 Hz with damping 0.034), controlled the way a rigid drivetrain would be: a **PID on the motor-side position**, reference $n\,r$, tuned for the rigid-body plant. It is here as the contrast to the showcase: it overshoots the 1 rad step by 104 % and rings for seconds.

![The model canvas|900](@fig:diagram)

The plant is the bond graph described in the other model: [V](block:V), [Elec](block:Elec), [GY](block:GY), [MotorJ](block:MotorJ), the gear [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1), the shaft ([S1](block:S1), [Shaft](block:Shaft), [C](block:C), [D](block:D)), [WheelJ2](block:WheelJ2) and the load source [Load](block:Load). The reference [Ref](block:Ref) is multiplied by the gear ratio in [ToMotor](block:ToMotor) and goes with the motor angle [Theta](block:Theta) into [PID](block:PID).

Continue with [the structure](page:structure), [the PID](page:controller) and [the results](page:results).
@@ page naive structure overview | Structure (bond graph)
# Structure: the bond graph

The plant is the same pure bond graph as in `drivetrain-position`:

```
MSe(V) -> 1( R, L ) -> GY(0.1) -> 1( J_m, R_d ) -> TF(1) * TF(0.1) -> 1( J1 ) -> 0 -- 1( C=1/1.2, R=0.001 )
                                                                              '-> 1( J2 ) <- MSe(load)
```

[V](block:V) is the voltage `MSe`, [Elec](block:Elec) and [MotorJ](block:MotorJ) are the electrical and the motor 1-junctions, the shaft is the spring [C](block:C) and the damper [D](block:D) on the 1-junction [Shaft](block:Shaft), which hangs on the 0-junction [S1](block:S1) between the wheels [WheelJ1](block:WheelJ1) and [WheelJ2](block:WheelJ2), and [Load](block:Load) is the load torque `MSe` driven by [LoadStep](block:LoadStep) (effort $-0.2$ N·m at 2.2 s).

[PID](block:PID) is a signal-domain block that writes the voltage; the controller is a 1 kHz digital PID (`library/PositionPID.jl`) fed by the motor angle [Theta](block:Theta). It does not use any load-side sensor.
@@ page naive controller overview | The PID
# The textbook PID

The design looks at the plant as a **rigid body**. With everything welded together, the motor-side inertia is $J_{tot} = J_m + (J_1 + J_2)/n^2 = 8\cdot10^{-5}$ kg·m² and the motor angle follows the voltage through the first-order lag

$$\frac{\dot\theta_m}{V} = \frac{K_g}{\tau s + 1}, \qquad K_g = \frac{k_t/R}{k_t^2/R + R_d} = 9.9\ \frac{\text{rad/s}}{\text{V}},\quad \tau = \frac{J_{tot}}{k_t^2/R + R_d} = 7.9\ \text{ms}.$$

The textbook recipe for such a plant: cancel the lag with the derivative time, $T_d = \tau$, choose the crossover $\omega_c$ and put the integral time at four times the crossover period, $T_i = 4/\omega_c$:

$$K_p = \frac{\omega_c}{K_g}, \qquad T_i = \frac{4}{\omega_c}, \qquad T_d = \tau.$$

With $\omega_c = 30$ rad/s (about 5 Hz, a modest bandwidth for a servo) this gives $K_p$ = 3.03 V/rad (of the motor angle), $T_i$ = 0.133 s, $T_d$ = 7.9 ms, a derivative filter $N = 10$ and back-calculation anti-windup against the 24 V clamp. [PID](block:PID) implements

$$v = K_p\,e + x_i - K_p T_d N\,(y - x_d), \quad u = \operatorname{clamp}(v, -24, 24), \quad \dot x_i = \frac{K_p}{T_i}\,e + \frac{u - v}{\sqrt{T_i T_d}}$$

(with the stdlib `PID` the integral gain would be $K_p/T_i^2$ and the derivative gain $T_d$, so the textbook form is a small project block).

## Why the load rings

The motor-side loop is collocated, hence stable, and it holds the motor tightly: the load wheel then hangs on the shaft spring against a stiff base and rings at $\sqrt{k/J_2}$ = 3.9 Hz with the damping of the shaft alone. The loop does not see the load, so it cannot damp it. The step of 1 rad (10 rad on the motor) saturates the supply and throws the load past the target.
@@ page naive results overview | Results and checks
# Results and checks

![Load position, voltage and shaft twist of the naive PID|900](@fig:run)

| quantity | measured |
| --- | --- |
| overshoot of the 1 rad step | 104.4 % (peak 2.044 rad at 0.36 s) |
| ringing frequency | 3.83 Hz (the shaft mode) |
| oscillation 1.4 to 2.2 s | 1.15 rad peak to peak, peaks of 1.45 rad at 1.9 s |
| dip at the 0.2 N·m disturbance | 0.73 rad |
| peak voltage | 24.00 V (saturated at the step) |
| maximum shaft twist | 0.90 rad |

`expected.json` checks the contrast, not a good response: the first load peak is above 1.835 rad (a peak lower bound, measured 2.015 over the window around the peak), the peak near 1.93 s is still above 1.281 rad (measured 1.453), the ringing frequency is 3.83 Hz $\pm 6$ %, the voltage is at most 24 V ([V/p.e](signal:V/p.e)) and there are no error diagnostics. The load position is [ThetaL/y](signal:ThetaL/y) and the shaft twist [C/q](signal:C/q).

The model `drivetrain-position` runs the same task with the firmware that handles the mode.
