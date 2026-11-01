# System identification

Each procedure has a model that produces its data. `design/actilink_sysid.py` fits the parameters back from **CSV** in the layout of bg-sim's run export, so the same script runs on lab logs recorded under the same signal names. `design/actilink_finish.py` runs all seven experiments and fits them. It compares each fit with the value the model was built with, and stops with an error when a fit is outside its tolerance.

| # | model | rig setup | excitation | identified |
| --- | --- | --- | --- | --- |
| 1 | `actilink-sysid-current` | output clamped | 5 N·m CST step, 16 kHz log of $u_q$, $i_q$ | R, L (ZOH least squares $i_{k+1} = a i_k + b(u_k - k_e w_k)$) |
| 2 | `actilink-sysid-friction` | links locked to the arm | CSV staircase ±0.05 … ±8 rad/s | Stribeck curve $F_c, F_s, v_s, F_v$; back-EMF $k_e$, hence $k_t$ |
| 3 | `actilink-sysid-gear` | output clamped | ±12 N·m CST triangle | backlash, $k_1$, $k_3$, knee, motor-side friction (hysteresis) |
| 4 | `actilink-sysid-swing1` | arm clamped, links locked together | released at 40° | $J$ about joint 1, bearing friction (ODE fit of period and decay) |
| 5 | `actilink-sysid-swing2` | arm and link 1 clamped | link 2 released at 40° | $J$ about joint 2, bearing friction |
| 6 | `actilink-sysid-encoder` | an AS5048 on the actuator output | one turn at ±4 rad/s (CSV) | latency, INL harmonics, noise ($d = c_0 - w\,\mathrm{lat} + \mathrm{INL}(\theta)$) |
| 7 | `actilink-sysid-chirp` | pendulum locked hanging | 1 N·m chirp 0.3 to 3 Hz | $J_{out}$: regression of $\tau - F(w)$ on the arm acceleration, minus the rig inertia |

Not identified: the gear ratio, the link masses (weigh them) and the COM distances (balance point). Finally, calibrate the AS5048 zeros with the pendulum balanced upright (2 s average with the arm centred). This removes the INL bias that a calibration at the hanging rest leaves at upright.

## Fits on the bg-sim data

| experiment | parameter | fit | model | error | tolerance |
| --- | --- | --- | --- | --- | --- |
| 1 | R, L (phase) | 0.1950 Ω, 107.8 µH | 0.195 Ω, 110 µH | −0.0 %, −2.0 % | 3 %, 5 % |
| 2 | $k_t$ from the back-EMF | 0.2417 N·m/A_rms | 0.2417 | −0.0 % | 3 % |
| 2 | $F_c$, $F_s$ | 0.264, 0.363 N·m | 0.26, 0.36 | +1.4 %, +1.0 % | 10 % |
| 2 | $v_s$, $F_v$ | 0.53 rad/s, 0.0123 N·m·s/rad | 0.5, 0.012 | +6.1 %, +2.4 % | 25 %, 15 % |
| 3 | $k_1$, $k_3$ | 3593, 8854 N·m/rad | 3500, 9000 | +2.7 %, −1.6 % | 15 %, 10 % |
| 3 | backlash | 13.1′ | 13.0′ | +1.0 % | 15 % |
| 4 | $J$ about joint 1, bearing $F_c$ | 0.2478 kg·m², 1.18 mN·m | 0.2477, 1.0 | +0.0 %, +18 % | 2 %, 25 % |
| 5 | $J$ about joint 2, bearing $F_c$ | 0.02197 kg·m², 1.05 mN·m | 0.02197, 1.0 | +0.0 %, +4.9 % | 2 %, 25 % |
| 6 | latency (SPI chain) | 0.191 ms | 0.1875 ms | +1.9 % | 10 % |
| 6 | INL 1st / 2nd harmonic, noise | 0.251°, 0.150°, 0.061° rms | 0.25, 0.15, 0.06 | +0.5 %, −0.1 %, +2.0 % | 10 %, 15 %, 10 % |
| 7 | $J_{out}$ | 0.0198 kg·m² | 0.020 | −0.9 % | 15 % |

The weakest fit is the 1 mN·m bearing friction of the passive joints. Over 8 s it costs only 6 mrad of swing amplitude, which is comparable to the INL.

The first version of experiment 7 let the pendulum swing freely. It fitted $J_{out}$ 37 % low: a 1 N·m chirp drives the free double pendulum into chaotic motion, and a simulation fit over 10 s of chaos is ill-posed. With the links locked, the experiment becomes a one-degree-of-freedom regression.
