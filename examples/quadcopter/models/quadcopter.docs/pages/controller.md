# Flight controller

| block | rate | role |
| --- | --- | --- |
| [Pos](block:Pos) `PositionCtrl` | 50 Hz | position P with velocity feed-forward and speed limits, velocity PI with acceleration feed-forward and D on the measurement, thrust vector $F = m\,(a + g\,e_z)$ limited to 25 degrees of tilt; outputs the collective thrust and the desired attitude (body $z$ along $F$, heading $\psi_{sp}$) |
| [Att](block:Att) `AttitudeCtrl` | 250 Hz | quaternion-error P (PX4 `AttitudeControl`), rate limits |
| [Rate](block:Rate) `RateCtrl` | 500 Hz | PID with D on the filtered measurement, conditional-integration anti-windup, torque limits; the yaw axis has a first-order torque low-pass |
| [Mix](block:Mix) `QuadMixer` | 500 Hz | the pseudo-inverse of the allocation matrix; attitude has priority over collective thrust when a rotor would saturate (scale the torque part, then shift the collective part); speed command $\omega = \sqrt{T/k_T}$ |
| [Esc1](block:Esc1) `Esc` | 500 Hz | rotor speed PI plus the steady-state voltage of the motor model as feed-forward, limited to $0.98\,V_{bat}$ and to $k_e\omega + R\,i_{lim}$ ($i_{lim}$ = 25 A, the current limit of the spin-up) |

The mixer's `Minv` is the pseudo-inverse of the matrix with rows $(1,\ r_y,\ -r_x,\ -\mathrm{spin}\,k_Q/k_T)$ (`design.py` asserts $M\,M^{-1} = I$).

## Design (`design/design.py`)

| loop | design | result |
| --- | --- | --- |
| ESC speed (500 Hz) | PI plus feed-forward on the linearised motor | $K_p = 0.06$ V·s/rad, $K_i = 3$ V/rad: crossover 121 rad/s, PM 62 deg, closed-loop -3 dB at 197 rad/s |
| roll/pitch rate | $K_p = J\,\omega_r$ ($\omega_r = 38$ rad/s), $T_i = 0.3$ s, $T_d = 6$ ms, with the 80 Hz Butterworth, the ESC lag and the holds | $K_p = 0.437$, $K_i = 1.46$, $K_d = 0.0026$: crossover 40 rad/s, PM 73 deg, GM 13 dB |
| yaw rate | largest gain meeting PM $\ge$ 55 deg, GM $\ge$ 14 dB with the rotor-acceleration lead and the torque low-pass | $K_p = 0.13$, $K_i = 0.087$: crossover 37 rad/s, PM 100 deg, GM 14.3 dB |
| attitude | P on the quaternion error, $K$ = 6.5 /s (roll/pitch), 2.8 /s (yaw) | crossover 6.3 rad/s, PM 76 deg |
| velocity (xy) | PI, $K_v$ = 3 /s, $K_i$ = 1.5 /s² | crossover 2.9 rad/s, PM 50 deg, GM 13 dB |
| position (xy) | P, 1 /s | crossover 1.2 rad/s, PM 69 deg |
| vertical | velocity $K_v$ = 5 /s, $K_i$ = 4 /s²; position 1.5 /s | crossovers 5.1 and 1.7 rad/s, PM 71 and 73 deg |
| navigation filter | $L_1$ = 6, $L_2$ = 9, $L_3$ = 8 /s, $k_\theta$ = 12 /s², $k_b$ = 0.8 /s | error poles $-6.3 \pm 3.3\mathrm{j}$, $-0.66 \pm 0.83\mathrm{j}$ |

The cascade keeps a factor of 3 to 6 between the loops (rate 38, attitude 6.3, velocity 2.9, position 1.2 rad/s). The mass knowledge is 4 % off on purpose (controller 1.30 kg, plant 1.35 kg): the velocity integrator carries the difference.

## The yaw actuator

The yaw torque on the airframe is the rotors' reaction torque $\sum \mathrm{spin}\,(Q + J_m\dot\omega)$. Above $Q'/J_m = 3.8$ rad/s the acceleration torque dominates, so a yaw command acts through a lead with plateau gain $K_p J_m/(J_z Q')$. The first version with a roll-like yaw gain oscillated at 45 Hz. `design.py` models this actuator, searches the largest yaw gain with PM $\ge$ 55 deg and GM $\ge$ 14 dB ($K_p = 0.13$ N·m·s/rad, crossover 37 rad/s) and sets the torque low-pass (30 rad/s) of `RateCtrl`.
