@@ figures baseline
{
  "diagram": {"kind": "diagram", "model": "baseline"},
  "scene": {"kind": "scene", "model": "baseline", "t": 0.3},
  "run": {
    "kind": "plot", "model": "baseline", "xlim": [0, 1.2],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/p.f", "label": "WmSens/p.f"}], "hlines": [{"y": 100, "label": "speed step 100 rad/s"}], "legend": true},
      {"ylabel": "position Theta/y [rad]", "series": [{"signal": "Theta/y", "label": "Theta/y", "color": "#d95f02"}]},
      {"ylabel": "q-axis current [A]", "series": [{"signal": "Iq/p.f", "label": "Iq/p.f", "color": "#1b9e77"}], "hlines": [{"y": 15, "label": "limit 15 A"}], "legend": true}
    ]
  },
  "step": {
    "kind": "plot", "model": "baseline", "xlim": [0.04, 0.12],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/p.f", "label": "WmSens/p.f"}], "hlines": [{"y": 100, "label": "100 rad/s"}], "legend": true},
      {"ylabel": "q-axis current [A]", "series": [{"signal": "Iq/p.f", "label": "Iq/p.f", "color": "#1b9e77"}], "hlines": [{"y": 15, "label": "limit 15 A"}], "legend": true}
    ]
  }
}
@@ page baseline overview - | Overview
# PMSM servo drive: five fidelity variants

Plan 9.6b's industrial servo sample. One Delta-ASDA-A3-style permanent-magnet synchronous motor drive with a **bond graph dq plant** (D28), a sampled cascaded current/speed/position firmware and an inverter. The same scenario is simulated at five fidelity levels, one model each, so every refinement can be compared with the baseline:

| model | inverter | mechanics | feedback |
| --- | --- | --- | --- |
| `baseline` (this model) | averaged, limited to $V_{dc}/\sqrt3$ | rigid inertia | ideal angle and speed |
| `two-mass` | averaged | flexible coupling and speed-loop notch | ideal |
| `switching` | two-level PWM, dead time, device drops | rigid | ideal |
| `encoder` | averaged | rigid | 24-bit encoder and differenced speed estimate |
| `full` | PWM, dead time, drops | flexible coupling and notch | encoder and estimated speed |

The run is one combined scenario of 1.2 s: a **100 rad/s speed step at 0.05 s**, **position mode at 0.15 s** (the shaft returns from about 9.4 to 9.7 rad to 0) and a **resisting 2 N·m load step at 0.9 s**. The acceptance checks each variant's step response, current and torque limit, steady-state error, switching ripple, encoder quantisation and, for the flexible variants, the resonance and notch attenuation, plus baseline-versus-variant comparisons.

![The baseline model canvas|900](@fig:diagram)

## What to try

- Press **Run** and open the preconfigured plots: "Phase current" ([Iphase/y](signal:Iphase/y), [Iq/p.f](signal:Iq/p.f)), "Speed" ([WmSens/p.f](signal:WmSens/p.f), [SpeedLoop/w_err](signal:SpeedLoop/w_err)), "Position" ([Theta/y](signal:Theta/y), [PosLoop/pos_err](signal:PosLoop/pos_err)) and "Voltage".
- Open `two-mass`, `switching`, `encoder` and `full` from the Open dialog's model selector and compare the same signals; each variant's page of this documentation lists what differs.
- Edit the constants at the top of `design/design.py` and re-run it (`uv run examples/industrial-servo/design/design.py`) to regenerate all five model files (the committed models are the generated result).

## 3D view

`scenes/industrial-servo.sdf` shows the motor with its rotor disc and a load disc behind a coupling. The joint `rotor_joint` follows the motor angle [Theta/y](signal:Theta/y) in all five variants; in `two-mass` and `full` the joint `coupling_joint` follows the coupling twist `Kc/q`. The rigid variants have no coupling state, so the load disc moves with the rotor.

![3D view at t = 0.3 s|500](@fig:scene)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
@@ page baseline plant overview | Plant (bond graph dq model)
# Plant: a PMSM as a bond graph

```
Vd(MSe) -> DJ(1) -- Rd(R_s) -- Id(L_d) -- IdSens -- MGY(u = w_e L_q)
Vq(MSe) -> QJ(1) -- Rq(R_s) -- Iq(L_q) -- IqSens -- Bemf(MSe, +k_e w_m)
                    |                                '-- GY(r = k_t) -> MJ(1)
Iq(IqSens) -- IqSrc(MSf, -1) -- GY.p1
MJ(1) -- Jm(I) -- Bm(R) -- WmSens -- Theta(integrator)
```

The dq equations are exactly plan 9.6b, with electrical speed $\omega_e = p\,\omega_m$:

$$v_d = R_s\,i_d + L_d\,\frac{di_d}{dt} - \omega_e L_q\,i_q, \qquad v_q = R_s\,i_q + L_q\,\frac{di_q}{dt} + \omega_e\,(L_d\,i_d + \psi_m),$$

$$T_e = \tfrac32\,p\,\psi_m\,i_q, \qquad J\,\frac{d\omega_m}{dt} = T_e - B\,\omega_m - T_{load}.$$

## Elements and signs

- [DJ](block:DJ) and [QJ](block:QJ) are the d and q 1-junctions; [Rd](block:Rd)/[Id](block:Id) and [Rq](block:Rq)/[Iq](block:Iq) are stator resistance and inductance; [IdSens](block:IdSens), [IqSens](block:IqSens) are flow sensors.
- [MGY](block:MGY) (`p1` on `DJ`, `p2` on `QJ`) has the signal modulus $\omega_e L_q$ from the gain [WeL](block:WeL) ($p\,L = 0.024$) of the measured speed. It produces the cross terms $-\omega_e L_q i_q$ and $+\omega_e L_d i_d$ (the surface-mount assumption $L_d = L_q = L$ makes one gyrator exact).
- [Bemf](block:Bemf) is an `MSe` on `QJ` with gain $k_e$ = 0.32 and input $\omega_m$; the junction sees $-k_e\omega_m$, i.e. the $+\omega_e\psi_m$ back-EMF of the q equation.
- [GY](block:GY) has $r = k_t = 1.5\,p\,\psi_m = 0.48$ N·m/A; its p2 torque is $+k_t i_q$ into [MJ](block:MJ). The measured $i_q$ drives its p1 through [IqSrc](block:IqSrc), an `MSf` with gain -1. This `MSf` is the **dq 3/2 power-scale interface**: the per-axis dq electrical bond carries $v_d i_d + v_q i_q$ while the shaft carries $T_e\,\omega_m = 1.5\,k_e\,i_q\,\omega_m$; the gyrator supplies the torque and the `MSf` absorbs the difference.
- `MJ` carries the rotor inertia [Jm](block:Jm), viscous [Bm](block:Bm), the speed sensor [WmSens](block:WmSens) and the load torque source [Load](block:Load) (driven by [LoadStep](block:LoadStep): 0 to -2 at 0.9 s, a 2 N·m resisting torque). [Theta](block:Theta) is a kinematic integrator of the measured speed (the D28 sensor exception) used by the controller.

## Parameters

| quantity | value |
| --- | --- |
| DC bus, voltage limit | $V_{dc} = 300$ V, $V_{dc}/\sqrt3 = 173.205$ V |
| stator | $R_s = 0.5\ \Omega$, $L_d = L_q = 6$ mH |
| magnet, pole pairs | $\psi_m = 0.08$ Wb, $p = 4$ ($k_t = 0.48$ N·m/A, $k_e = 0.32$ V·s/rad) |
| rotor | $J_m = 0.44\cdot10^{-3}$ kg·m², $B_m = 10^{-4}$ N·m·s/rad |
| current | rated 5 A peak, limit 15 A peak (7.2 N·m) |
| run | 1.2 s, `solver` auto, 6001 points, `reltol` 1e-8, `event_limit` 200000 |

The only code nodes of the plant are sensors (allowed by D28): the flow sensors, the `Theta` integrator and the recording sensor `Iphase`, the peak phase-current amplitude $\sqrt{i_d^2 + i_q^2}$ (amplitude-invariant Park transform), which is not part of the plant.
@@ page baseline controller overview | Cascaded firmware
# Controller: current, speed and position loops

The cascade is tuned inner to outer; `design/design.py` computes and writes all gains into the five model documents.

| loop | block | rate | law | gains |
| --- | --- | --- | --- | --- |
| current | [CurLoop](block:CurLoop) | 8 kHz (`sample_period` 125 µs) | PI on $i_d$, $i_q$, dq decoupling, back-EMF feedforward, vector voltage limit | $K_p = L\,\omega_{ci} = 18.85$ V/A, $K_i = R\,\omega_{ci} = 1570.8$ V/(A·s), $\omega_{ci} = 2\pi\cdot500$ |
| speed | [SpeedLoop](block:SpeedLoop) | 1 kHz | PI on the speed error, output $i_q$ limited to $\pm15$ A | $K_p = J\,\omega_{cs}/k_t = 0.4608$ A/(rad/s), $K_i = 46.32$, zero at $\omega_{cs}/5$, $\omega_{cs} = 2\pi\cdot80$ |
| position | [PosLoop](block:PosLoop) | 200 Hz (5 ms) | P on the position error, speed limit $\pm200$ rad/s | $K_p = 20$ 1/s |

The current PI cancels the electrical pole ($K_i/K_p = R/L$); the speed PI places its zero at one fifth of the 80 Hz crossover. A one-sample `UnitDelay` at 8 kHz ([Udd](block:Udd), [Udq](block:Udq)) sits between the current loop and the inverter in every variant. [RefSpeed](block:RefSpeed) steps to 100 rad/s at 0.05 s; [Mode](block:Mode) switches the position loop on at 0.15 s with [PosRef](block:PosRef) = 0.

$$K_p^{(c)} = L\,\omega_{ci},\quad K_i^{(c)} = R\,\omega_{ci}, \qquad K_p^{(s)} = \frac{J\,\omega_{cs}}{k_t},\quad K_i^{(s)} = K_p^{(s)}\,\frac{\omega_{cs}}{5}.$$

**Why these values.** 500 Hz is a comfortable 16 samples per period at the 8 kHz current sample with the one-sample delay. The speed crossover of 80 Hz is a decade below the 303.5 Hz coupling resonance (see the `two-mass` model). A position gain of 20 1/s gives a 50 ms time constant; the 200 rad/s limit bounds the move and the 15 A limit bounds the acceleration.

At 0.05 s the 100 rad/s error saturates $i_q$ at 15 A: this is the current-loop step used by the acceptance. At 0.15 s the accumulated position (about 9.5 rad) is put on the position loop, and the 0.9 s load step tests the speed integrator's load rejection.
@@ page baseline results overview | Results and checks
# Results and checks

![Speed, position and q-axis current of the baseline run|900](@fig:run)

Zoom on the speed step at 0.05 s (the current saturates at the 15 A limit):

![Speed step and current|900](@fig:step)

## Measured results (README, `expected.json`)

| check | baseline |
| --- | --- |
| speed 100 rad/s: rise / overshoot / settle | 5.1 ms / 3.4 % / 15 ms |
| position step (about 9.5 rad to 0): rise / overshoot / settle (5 mrad) | 106 ms / 0 % / 380 ms |
| current 15 A: rise / overshoot / settle (0.8 A) | 0.44 ms / 4.2 % / 0.63 ms |
| peak $i_q$ / torque | 15.80 A / 7.585 N·m |
| peak voltage vector | 173.205 V |
| phase-current ripple (RMS) | 0.00064 A |
| position at 1.15 s | -6.6e-4 rad |
| speed at 1.15 s | 0.014 rad/s |

The current and torque checks allow 16 A / 7.7 N·m although the command limit is 15 A / 7.2 N·m: the measured $i_q$ overshoots the reference by up to 5 % with the 500 Hz current loop. The averaged $V_{dc}/\sqrt3$ limit is exact (173.205 V). The run reports only W205 (the dimensionless Generic bond island, expected for a bond graph without a concrete domain); E900, E901, E103, E104, E105, E106 and W206 are forbidden by `no_diagnostics`.

The five variants have 12 / 15 / 13 / 15 / 19 model checks and 8 baseline-versus-variant comparisons (82 checks in total); the whole example lane reported 170 passed, 0 failed in 155.8 s.
@@ figures two-mass
{
  "diagram": {"kind": "diagram", "model": "two-mass"},
  "run": {
    "kind": "plot", "model": "two-mass", "xlim": [0.04, 0.12],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/p.f", "label": "motor WmSens/p.f"}, {"signal": "WlSens/p.f", "label": "load WlSens/p.f", "style": "--"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "notch [rad/s]", "series": [{"signal": "Notch/u", "label": "Notch/u (input)"}, {"signal": "Notch/y", "label": "Notch/y (output)"}], "legend": true, "legend_loc": "lower right"}
    ]
  }
}
@@ page two-mass overview - | Overview
# Servo with a flexible coupling and notch filter

The `baseline` drive with a flexible motor-to-load coupling and a notch in the speed feedback path. Everything else (plant equations, three loops, averaged inverter, ideal sensors) is unchanged; see the `baseline` model for the PMSM and the controller.

![The two-mass model canvas|900](@fig:diagram)

## What differs

`MJ -- TF(1) -> S0(0) <- TF(1) -- LJ` with a parallel spring and damper on a 1-junction `KJ`: [TFm](block:TFm), [S0](block:S0), [TFl](block:TFl), [KJ](block:KJ), [Kc](block:Kc), [Dc](block:Dc). The 0-junction forms the relative velocity $\omega_m - \omega_L$; the 1-junction gives spring and damper the same relative flow and **adds** their efforts, so the coupling torque is

$$T_c = k_c\,\Delta\theta + c_c\,(\omega_m - \omega_L).$$

(Putting both C and R on the 0-junction would be a series Maxwell element, which lets the load creep under a constant load.) The load is [LJ](block:LJ) with [Jl](block:Jl) = 4.4e-4 kg·m², [Bl](block:Bl) = 1e-4, the load speed sensor [WlSens](block:WlSens), and the load torque source on `LJ`. The coupling is $k_c = 800$ N·m/rad (the `Kc` compliance is 1/800 = 0.00125) and $c_c = 0.02$ N·m·s/rad ([Dc](block:Dc)). The undamped resonance is

$$f_r = \frac{1}{2\pi}\sqrt{k_c\left(\frac{1}{J_m} + \frac{1}{J_L}\right)} = \frac{1}{2\pi}\sqrt{800\cdot 2\cdot\frac{1}{4.4\cdot10^{-4}}} = 303.5\ \mathrm{Hz}.$$

The speed feedback passes through a second-order **notch at 303.5 Hz** ($Q = 4$, $f_s = 1$ kHz), the `DiscreteTF` [Notch](block:Notch) with $b = (0.8045, 0.5307, 0.8045)$ and $a = (1, 0.5307, 0.6090)$ (from `iirnotch`):

$$H(z) = \frac{0.8045 + 0.5307\,z^{-1} + 0.8045\,z^{-2}}{1 + 0.5307\,z^{-1} + 0.6090\,z^{-2}}.$$

## Results

![Motor and load speed ring at the coupling resonance, and the notch input and output|900](@fig:run)

The motor and load speeds ring at 303.5 Hz after the speed step; the notch output [Notch/y](signal:Notch/y) has visibly less high-frequency content than its input [Notch/u](signal:Notch/u): the 250 Hz high-pass RMS drops from 1.099 to 0.827 (README; the load-side ringing is 1.181). The speed step has a rise / overshoot / settle of 11.1 ms / 6.0 % / 32 ms, the position step 107 ms / 0 % / 396 ms, the peak $i_q$ is 15.80 A (7.586 N·m).
@@ figures switching
{
  "diagram": {"kind": "diagram", "model": "switching"},
  "run": {
    "kind": "plot", "model": "switching", "xlim": [1.0, 1.01],
    "rows": [
      {"ylabel": "phase-current amplitude [A]", "series": [{"signal": "Iphase/y", "label": "Iphase/y"}], "legend": true},
      {"ylabel": "applied Vd, Vq [V]", "series": [{"signal": "Vd/p.e", "label": "Vd/p.e"}, {"signal": "Vq/p.e", "label": "Vq/p.e"}], "legend": true}
    ]
  }
}
@@ page switching overview - | Overview
# Servo with a switching inverter

The `baseline` drive with the averaged voltage source replaced by a **two-level PWM inverter** with dead time and device drops; plant and the three loops are unchanged (see the `baseline` model).

![The switching model canvas|900](@fig:diagram)

The project block [PWM](block:PWM) (`library/PwmInverter.jl`) turns the commanded $v_d$, $v_q$ into three leg voltages with the min-max (SVPWM) zero-sequence, a sampled centre-aligned carrier, dead time and a conduction drop on the sign of each phase current, then transforms the applied leg voltages back to dq ($v_{d,app}$, $v_{q,app}$ drive [Vd](block:Vd), [Vq](block:Vq)). The electrical angle $\theta_e = p\,\theta$ comes from the gain [ThetaE](block:ThetaE) ($k = 4$).

| parameter | value |
| --- | --- |
| `Vdc` | 300 V |
| `Tpwm` | 250 µs (4 kHz carrier; 8 kHz was requested in the variant spec, 4 kHz keeps the run at about 850k solver steps) |
| comparator | sampled at 100 kHz (`sample_period` 10 µs, 25 levels per carrier) |
| `Td` (dead time) | 2 µs |
| `Vdrop` | 1.2 V |
| solver settings | `reltol` 1e-4, `abstol` 1e-7, output every 10 µs (up to 244k rows) |

The switching ripple is a *sampled* PWM, so the recorded ripple is a faithful staircase approximation, not an analogue edge.

## Results

![Phase-current amplitude ripple and the applied voltages between 1.00 and 1.01 s|900](@fig:run)

The phase-current amplitude [Iphase/y](signal:Iphase/y) shows the 4 kHz ripple: RMS 0.170 A and peak-to-peak 0.692 A in the steady window (the averaged baseline: 0.00064 A). Speed step 5.1 ms / 3.6 % / 17 ms, position step 106 ms / 0.04 % / 394 ms, peak $i_q$ 15.66 A / 7.515 N·m. The dead time and the 1.2 V drop add low-order distortion; the position step leaves a residual of about 4 mrad at 0.88 s, which is why the acceptance uses a 5 mrad band.
@@ figures encoder
{
  "diagram": {"kind": "diagram", "model": "encoder"},
  "run": {
    "kind": "plot", "model": "encoder", "xlim": [0.04, 0.2],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/p.f", "label": "true WmSens/p.f"}, {"signal": "SpeedEst/w", "label": "estimate SpeedEst/w", "style": "--"}], "legend": true, "legend_loc": "lower right"}
    ]
  }
}
@@ page encoder overview - | Overview
# Servo with a 24-bit encoder and estimated speed

The `baseline` drive, but the loops no longer see the ideal angle and speed: the angle goes through a 24-bit absolute encoder and the speed is estimated by differencing it. The plant, inverter (averaged) and mechanics are unchanged (see `baseline`).

![The encoder model canvas|900](@fig:diagram)

- [Enc](block:Enc): a `Quantizer` at 8 kHz with resolution $2\pi/2^{24} = 3.745\cdot10^{-7}$ rad on the angle [Theta](block:Theta);
- [SpeedEst](block:SpeedEst): a 1 kHz backward difference of the quantised angle plus a first-order low-pass with $\alpha = 0.8$; its output `SpeedEst/w` replaces the measured speed in the speed loop and in the current loop's decoupling; `Enc/y` replaces the angle in the position loop;
- [EncMon](block:EncMon): records the quantisation error at the encoder tick (the half-LSB error is $1.872\cdot10^{-7}$ rad).

## Results

![True and estimated speed during the speed step|900](@fig:run)

The speed-loop overshoot is larger (10.5 %, against 3.4 % for the baseline) because the 1 kHz differenced estimate lags the true speed by up to one sample plus the low-pass; rise 5.1 ms, settle 11 ms. The estimate still tracks the steady speed: its RMS error is 0.0038 rad/s over $[1.0, 1.15]$ s. Position step 108 ms / 0 % / 386 ms, peak $i_q$ 15.78 A / 7.574 N·m, position at 1.15 s -6.8e-4 rad.
@@ figures full
{
  "diagram": {"kind": "diagram", "model": "full"},
  "scene": {"kind": "scene", "model": "full", "t": 0.1},
  "run": {
    "kind": "plot", "model": "full", "xlim": [0, 1.2],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/p.f", "label": "motor WmSens/p.f"}, {"signal": "WlSens/p.f", "label": "load WlSens/p.f", "style": "--"}], "legend": true},
      {"ylabel": "position Theta/y [rad]", "series": [{"signal": "Theta/y", "label": "Theta/y", "color": "#d95f02"}]}
    ]
  }
}
@@ page full overview - | Overview
# Servo with every refinement

The realistic drive model: all three forks of the `baseline` together.

![The full model canvas|900](@fig:diagram)

| fork | what |
| --- | --- |
| switching inverter | [PWM](block:PWM): two-level, 4 kHz carrier, dead time 2 µs, drop 1.2 V |
| flexible coupling | [Kc](block:Kc) = 800 N·m/rad, [Dc](block:Dc) = 0.02 N·m·s/rad, load inertia [Jl](block:Jl), resonance 303.5 Hz, speed-feedback [Notch](block:Notch) |
| encoder | [Enc](block:Enc) 24 bit, [SpeedEst](block:SpeedEst), monitor [EncMon](block:EncMon); the notch sits behind the speed estimate |

The solver uses `reltol` 1e-4 and `abstol` 1e-7 with a 10 µs output interval.

![Speed of motor and load, and position|900](@fig:run)

## Results (README, `expected.json`)

| quantity | full |
| --- | --- |
| speed step: rise / overshoot / settle | 11.1 ms / 7.2 % / 28 ms |
| position step: rise / overshoot / settle (5 mrad) | 108 ms / 0.05 % / 549 ms |
| current step: rise / overshoot / settle (0.8 A) | 0.49 ms / 4.4 % / 2.2 ms |
| peak $i_q$ / torque | 15.74 A / 7.556 N·m |
| phase-current ripple (RMS / peak-to-peak) | 0.166 A / 0.686 A |
| position / speed at 1.15 s | -6.1e-4 rad / 0.027 rad/s |
| speed-estimate RMS error ($[1.0, 1.15]$ s) | 0.046 rad/s |
| notch input to output ripple (250 Hz high-pass) | 1.067 to 0.875 |
| load-side ringing (250 Hz high-pass) | 1.173 |

The check set has 19 model checks, the most of any variant. See the `baseline` model for the physics and the controller.

## 3D view

The joints `rotor_joint` ([Theta/y](signal:Theta/y)) and `coupling_joint` (`Kc/q`) are bound: the load marker lags and rings against the rotor marker.

![3D view at t = 0.1 s|500](@fig:scene)
