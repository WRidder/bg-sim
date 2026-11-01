@@ figures actilink-swingup
{
 "diagram": {"kind": "diagram", "model": "actilink-swingup"},
 "scene-up": {"kind": "scene", "model": "actilink-swingup", "t": 7.5},
 "scene-swing": {"kind": "scene", "model": "actilink-swingup", "t": 3.2},
 "run": {
  "kind": "plot", "model": "actilink-swingup", "width": 1000, "xlim": [0, 8],
  "rows": [
   {"ylabel": "link angle [deg]", "legend": true, "series": [
     {"signal": "Angles/phi1", "label": "link 1 (from upright)", "scale": 57.29577951308232},
     {"signal": "Angles/phi2", "label": "link 2 (from upright)", "scale": 57.29577951308232}],
    "vlines": [{"x": 1.0, "label": "swing-up"}, {"x": 4.0, "label": "catch"}]},
   {"ylabel": "arm [deg]", "series": [{"signal": "J1/qout", "label": "arm", "scale": 57.29577951308232}]},
   {"ylabel": "torque [N m]", "legend": true, "series": [
     {"signal": "Ctrl/tau", "label": "target (EtherCAT)"}, {"signal": "DriveLoop/tau_ref", "label": "drive reference"}],
    "hlines": [{"y": 12, "label": "firmware clamp"}, {"y": -12, "label": ""}]},
   {"ylabel": "q current [A]", "series": [{"signal": "CurrentLoop/iq", "label": "i_q"}]},
   {"ylabel": "gear deflection [mrad]", "series": [{"signal": "GearSpring/defl", "label": "defl", "scale": 1000.0}],
    "hlines": [{"y": 1.89, "label": "half backlash"}, {"y": -1.89, "label": ""}]},
   {"ylabel": "mode", "series": [{"signal": "Ctrl/mode", "label": "mode"}]}
  ]
 },
 "enc": {
  "kind": "plot", "model": "actilink-swingup", "width": 1000, "xlim": [6.0, 6.4],
  "rows": [
   {"ylabel": "link 1 joint angle [deg]", "legend": true, "series": [
     {"signal": "J2/qout", "label": "true", "scale": 57.29577951308232},
     {"signal": "Ctrl/th1", "label": "AS5048A reading (unwrapped, calibrated)", "scale": 57.29577951308232},
     {"signal": "Ctrl/q2e", "label": "estimate (alpha-beta-gamma)", "scale": 57.29577951308232}]},
   {"ylabel": "arm [deg]", "legend": true, "series": [
     {"signal": "J1/qout", "label": "true", "scale": 57.29577951308232},
     {"signal": "Ctrl/q1e", "label": "estimate", "scale": 57.29577951308232}]}
  ]
 },
 "push": {
  "kind": "plot", "model": "actilink-push", "width": 1000, "xlim": [0, 6],
  "rows": [
   {"ylabel": "link angle [deg]", "legend": true, "series": [
     {"signal": "Angles/phi1", "label": "link 1", "scale": 57.29577951308232},
     {"signal": "Angles/phi2", "label": "link 2", "scale": 57.29577951308232}],
    "vlines": [{"x": 2.0, "label": "push 0.3 N, 50 ms"}]},
   {"ylabel": "arm [deg]", "series": [{"signal": "J1/qout", "label": "arm", "scale": 57.29577951308232}]},
   {"ylabel": "torque [N m]", "series": [{"signal": "DriveLoop/tau_ref", "label": "drive reference"}]},
   {"ylabel": "gear deflection [mrad]", "series": [{"signal": "GearSpring/defl", "label": "defl", "scale": 1000.0}]}
  ]
 }
}
@@ page actilink-swingup overview - | Overview
# ACTILINK-JD10 rotary double pendulum

This is the rotary double pendulum of this project built from purchasable hardware:

- A **Synapticon ACTILINK-JD10** stands on the vertical axis and turns a **0.3 m arm**.
- A passive joint at the arm tip carries **link 1 (0.6 m)**, and **link 2 (0.6 m)** hangs from the tip of link 1.
- Each passive joint has an **ams AS5048** 14-bit magnetic encoder: A over SPI, or B over I2C.
- A **1 kHz EtherCAT master** reads the drive's 20-bit output encoder and the two AS5048, estimates the states, swings the pendulum up and balances it. The drive runs CST (cyclic synchronous torque).

The scenario of this model (8 s):

1. 0 to 1 s: hanging at rest, drive enabled with zero torque.
2. 1 to 4 s: swing-up along a collocation trajectory, tracked by a time-varying LQR.
3. Catch: the 1 kHz firmware latches the balance LQR.
4. Balance until the end.

![The model canvas|900](@fig:diagram)

Every block is either datasheet hardware or an explicit estimate. [Hardware and size](page:hardware) lists the numbers and explains why the JD10 was chosen over the JD08 and the JD12.

The other models of the project are:

| model | |
| --- | --- |
| `actilink-balance` | balance from a disturbed upright |
| `actilink-push` | a push on the link-2 tip while balancing |
| `actilink-free` | the zero-torque free swing, compared with the Python twin |
| `actilink-sysid-*` | seven identification experiments, see [System identification](page:sysid) |

## Dashboard

- **Readouts:** the controller mode and a balancing lamp; the deviation from upright; the q current as a gauge against the drive's 44 A peak; and the gear deflection.
- **Controls:**
  - the **A/B toggle** (AS5048B over I2C with 0.44 ms latency, instead of AS5048A over SPI with 0.19 ms);
  - a slider for the **AS5048 read interval** in EtherCAT cycles (a slower bus);
  - a slider for the **gear backlash**.
- **Plots:**
  - the link angles and the arm;
  - the torque target and the drive reference;
  - the current;
  - link 1 as true, quantised and estimated angle;
  - the gear deflection;
  - the energy.

## 3D view

The actuator is a Ø106 × 86 mm cylinder on a column, with an orange output flange. On top sit the clamp hub, the 30 × 30 mm arm tube and the joint-1 bearing block with its AS5048 board. The two link tubes and the joint-2 housing follow; link 2 runs 40 mm beside link 1.

![3D view at t = 7.5 s, balancing|500](@fig:scene-up)

Continue with [Hardware and size](page:hardware), [Model](page:model), [Control](page:control), [System identification](page:sysid) and [Results](page:results).
@@ page actilink-swingup hardware overview | Hardware and size
# Hardware and the choice of size

`design/actilink_hardware.json` holds every number together with its source:

- the Synapticon datasheet and product PDF (S1, S3);
- the Circulo brochure (S4);
- the firmware and EtherCAT docs (S6, S7);
- the ams AS5048 datasheet (A1).

Numbers the datasheets do not give are marked `est`. The identification experiments measure them.

| | JD08 | **JD10** | JD12 |
| --- | --- | --- | --- |
| ratio, rated / peak torque | 7.75, 7 / 17 N·m | **9, 21 / 68 N·m** | 9, 29 / 102 N·m |
| no-load speed, backlash | 400 rpm, < 22′ | **210 rpm, < 13′** | 200 rpm, < 11′ |
| rotor inertia at the output | 0.0042 kg·m² | **0.020 kg·m²** | 0.040 kg·m² |
| motor: pole pairs, k_t, R, L | 14, 0.156 N·m/A, 0.27 Ω, 167 µH | **20, 0.242 N·m/A, 0.195 Ω, 110 µH** | 21, 0.234 N·m/A, 0.085 Ω, 90 µH |
| drive | Circulo 7 (8 / 24 A_rms) | **Circulo 9 (20 / 60 A_rms)** | Circulo 9 |
| permissible bearing tilting moment | K × 3.2 N·m | **K × 24.5 N·m** | K × 30.6 N·m |
| gear stiffness (est) | 1500 / 4000 N·m/rad | **3500 / 9000 N·m/rad** | 5000 / 13000 N·m/rad |

**Estimates (est):** the gear stiffness below and above the knee, and the friction in the gear and the bearing. The friction is Coulomb, breakaway and viscous; for the JD10 it is 0.20 / 0.30 N·m with 0.01 N·m·s/rad, plus 0.06 N·m in the output bearing. The rig itself is also estimated: aluminium tubes, bearing blocks and the masses of the AS5048 boards.

## Sizing

`actilink_design.py` optimises the swing-up for each size: collocation over 3 s, 6 N·m bound, arm within ±3 rad. Along the trajectory it computes the moment that tilts the output bearing, the horizontal part of $\dot L - \sum r \times m g$ about the flange.

| | JD08 | **JD10** | JD12 |
| --- | --- | --- | --- |
| swing-up peak torque | 2.77 N·m | **2.38 N·m** | 2.63 N·m |
| bearing tilting moment, peak | 35.0 N·m | **32.6 N·m** | 24.9 N·m |
| permissible, static K | **7.1 N·m (exceeded)** | 47.0 N·m | 52.6 N·m |
| LQR phase margin, delay margin | 73°, 18.3 ms | **70°, 22.5 ms** | 68°, 26.4 ms |
| rotor share of the axis inertia | 5 % | **20 %** | 33 % |

**Torque does not decide the size.** All three sizes swing the pendulum up with less than 3 N·m.

**The output bearing does.** The links swing 0.3 m from the axis, and their centrifugal and inertial loads tilt the flange with more than 30 N·m. That is five times what the JD08 bearing permits, so the JD08 would need an external support bearing.

**JD10:**
- carries the tilting moment within its static rating;
- has 13′ backlash instead of the JD08's 22′;
- costs 20 % extra axis inertia.

The **JD12** adds mass and rotor inertia without a gain.
@@ page actilink-swingup model overview | Model
# The bond graph

## Drive

The winding is the dq model in the amplitude-invariant frame, as an equivalent DC circuit:

- [Uq](block:Uq) is an `MSe` driven by the current loop's $u_q$.
- [Rw](block:Rw) and [Lw](block:Lw) are $R/1.5$ and $L/1.5$.
- [EMF](block:EMF) is a gyrator with the modulus $p\lambda = k_{t,q}/1.5$.

The flow is $i_e = 1.5\, i_q$, so $u_q i_e$ is the electrical power, and $k_{t,q} = k_{t,rms}/\sqrt2 = 0.171$ N·m/A.

The mechanical path runs from [Rotor](block:Rotor) ($J_m = J_{out}/N^2$) and the motor-side friction [FricIn](block:FricIn) through [Gear](block:Gear) (TF $1/N$) to a 0-junction. That junction carries the gear compliance [GearSpring](block:GearSpring). After it come the output bearing friction [FricOut](block:FricOut) and the arm joint [J1](block:J1).

**Gear spring.** The backlash is a smooth dead zone, with no `abs`/`max` kink and no tangent at zero:

$$D(\varphi) = s(\varphi - b) - s(-\varphi - b),\qquad s(x) = \tfrac12\big(x + \sqrt{x^2 + \varepsilon^2}\big)$$

$b$ is half of the 13′ backlash. The torque is a hardening spring plus contact damping that vanishes in the gap:

$$\tau = k_3 D - (k_3 - k_1)\, D_k \tanh(D/D_k) + d\,\dot\varphi\, D'(\varphi)$$

**Friction.** All friction is Coulomb, Stribeck and viscous, with a smooth sign:

$$\tau_f = \big(F_c + (F_s - F_c)\,e^{-(w/v_s)^2}\big)\tanh(w/v_\varepsilon) + F_v w$$

## Mechanics

The mechanics is the spatial multibond bond graph of the Quanser model:

- `Revolute3D` joints [J1](block:J1), [J2](block:J2) and [J3](block:J3) with $10^6$ compliance;
- `RigidBody3D` composite bodies [Arm](block:Arm), [Link1](block:Link1) and [Link2](block:Link2). Each combines its tube, shaft, bearing housing and AS5048 board with its own COM and inertia.

The passive joints have bearing friction ([FricJ2](block:FricJ2), [FricJ3](block:FricJ3)).

## Drive firmware and sensors

- **Current loop.** [CurrentLoop](block:CurrentLoop) is the continuous equivalent `ALCurrentLoopC` of the 16 kHz digital PI.
  - It keeps the zero on the winding pole, the 26.3 V clamp ($0.95\,V_{dc}/\sqrt3$), anti-windup and the 1.5-period delay as a lag.
  - The digital loop itself (`ALCurrentLoop`) runs in the current-step identification.
  - The continuous form is used here because a 16 kHz held output would record 32 000 event rows per simulated second.
- **Drive loop.** [DriveLoop](block:DriveLoop) runs at 4 kHz.
  - In CST it passes the target torque to the current loop: $i_{ref} = \tau/(N k_{t,q})$, clamped at the 68 N·m acceleration torque (44.2 A).
  - In CSV it runs a speed PI.
- **Drive encoders.** [MotorEnc](block:MotorEnc) and [OutputEnc](block:OutputEnc) are 20-bit encoders, read in the 1 kHz cycle.
- **AS5048 encoders.** [Enc1A](block:Enc1A), [Enc1B](block:Enc1B), [Enc2A](block:Enc2A) and [Enc2B](block:Enc2B) are the two chains on the two joints. Each reading:
  - is taken at the angle $\theta - w\,\mathrm{lat}$, where lat is 0.19 ms over SPI and 0.44 ms over I2C;
  - adds the INL as two harmonics, plus 0.06° rms noise from a seeded `Noise` block;
  - is quantised to 14 bit, modulo one turn.
@@ page actilink-swingup control overview | Control
# Control at 1 kHz over EtherCAT

[Ctrl](block:Ctrl) (`ALCtrl`, generated by `design/actilink_build.py`) works on the readings of one EtherCAT cycle.

**Readings.**
- The AS5048 registers are unwrapped, and the calibration offset is subtracted. The offset is taken at the hanging rest, so it includes the INL at that angle.
- At upright, that leaves a 0.24° bias on link 1, and the LQR holds the arm about 6° off centre to balance it. An upright calibration removes the bias (see [System identification](page:sysid)).
- The arm comes from the drive's 20-bit output encoder.

**Estimator.** Each angle has an α-β-γ filter: the steady-state Kalman filter of a white-jerk model, tuned to the sensor noise. It gives the angles and the rates.

![Link 1 and the arm during balance: true angle, quantised AS5048 reading and estimate|900](@fig:enc)

**Balance.** A discrete LQR at 1 kHz, designed with the one-cycle EtherCAT delay as an extra state:

$$K = [1.37,\ -42.6,\ -126.3,\ 2.29,\ -20.9,\ -21.7,\ 0.056]$$

The state is the arm, link 1 and link 2 (angles, then rates), followed by the last command. The margins at the drive input are 70° phase, 8.7 Hz crossover and 22.5 ms delay margin.

**Swing-up.** A Hermite-Simpson collocation trajectory (CasADi/IPOPT, 3 s, |τ| ≤ 6 N·m, |arm| ≤ 3 rad), tracked by a time-varying LQR. The firmware latches the balance LQR once the weighted state error drops below 0.35. The torque target is clamped to ±12 N·m.

![Swing-up and balance: link angles, arm, torque, current, gear deflection and mode|900](@fig:run)

![3D view at t = 3.2 s, during the swing-up|500](@fig:scene-swing)

**Disturbance** (model `actilink-push`). While the pendulum balances, a 0.3 N, 50 ms push on the link-2 tip deflects link 2 by about 5°. The arm swings out by 55°, and the LQR recovers within 1.4 s. A 0.4 N push is still recovered; at 0.5 N the arm runs away.

![Push on link 2 at 2 s|900](@fig:push)
@@ page actilink-swingup sysid overview | System identification
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
@@ page actilink-swingup results overview | Results
# Results and checks

The table compares the bond graph (Rodas5P, rtol 1e-6) with the Python twin of `design/actilink_lib.py`. The twin has the same physics, but with the 16 kHz digital current loop, integrated by RK4 at 32 kHz.

| quantity | bond graph | Python twin |
| --- | --- | --- |
| free swing over 3 s (arm / link 1 / link 2) | 0.86 / 0.15 / 0.27 mrad max difference | |
| swing-up: catch | 4.00 s | 4.00 s |
| swing-up: largest arm angle | 2.98 rad | 2.98 rad |
| swing-up: peak torque target / $i_q$ / $u_q$ | 12.0 N·m (clamp) / 8.3 A (limit 44.2) / 7.4 V (limit 26.3) | 12.0 / 8.3 / 8.5 |
| swing-up: band from catch + 1.5 s; final deviation | 0.41°; 0.012° | 0.33°; 0.017° |
| swing-up: peak gear deflection | 6.3 mrad | 6.3 mrad |
| balance (AS5048A): band after 1.5 s; arm limit cycle | 0.33°; 1.2° p-p | 0.37°; 1.7° p-p |
| push 0.3 N, 50 ms: link 2 peak; arm; back inside 1° | 4.7°; 55°; 1.40 s | 4.5°; 53°; 1.40 s |
| balance with AS5048B (I2C) | | 0.32°; arm 1.4° p-p |

**Energy.** `ALEnergy` computes $H = E_{mech} + E_{drive} + W_{loss} - W_{in}$. In the free swing it stays constant to $2.4\cdot10^{-4}$ of the throughput.

In closed loop, $H$ falls by the energy the three `Revolute3D` joints absorb in their compliance regularisation ($10^6$ with damping, excited by the drive's torque ripple). In the balance run that is 0.161 J of 3.5 J; the integral of the joints' port powers matches the drift to $2\cdot10^{-4}$ J. The `energy_ledger` check closes the balance over every element to $10^{-6}$.

**Checks** (`expected.json`, written by `design/actilink_finish.py`):

- no diagnostics, and the scene bindings;
- the twin samples of the free swing;
- the q current, the torque target and $u_q$ inside their limits, and the gear deflection bounded;
- the controller mode at the catch and the upright band, on the quantised encoders;
- the push deflection and the recovery;
- the energy invariant and the Tellegen ledger;
- one sanity check per identification experiment.

**Hardware notes:**

- **Cabling.** The arm stays within ±3 rad (171°) during swing-up, balance and push, so a cable loop to the AS5048 boards suffices. The friction staircase and the encoder bench turn continuously: run them with the arm cables unplugged (the links are locked anyway) or through a slip ring.
- **Calibration.** Calibrate the AS5048 zeros upright, not hanging, to remove the INL bias.
- **JD08.** It needs an external bearing for the tilting moment.
