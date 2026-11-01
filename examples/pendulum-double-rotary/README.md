# pendulum-double-rotary — a Quanser-style rotary double inverted pendulum (X5.13)

A horizontal arm turns about the vertical axis, driven by an SRV02-like DC servo (70:1 gearbox, ±10 V). A two-link pendulum hangs from the arm tip and swings in the plane **perpendicular to the arm**. The plant is a **spatial multibond bond graph** (`Revolute3D`, `RigidBody3D`, `GroundSpatial`, `ComposePose3D`, `ExternalWrenchSpatial`), as in `robot-arm-3d` and `cube-3d`.

Scenario (model `pendulum-double-rotary`, 12 s):

1. 0 to 1 s: hanging at rest, motor voltage 0.
2. 1 s: swing-up, a collocation trajectory (CasADi/IPOPT, includes the motor and its voltage limit) tracked by a time-varying LQR, T_s = 4 s.
3. 5.02 s: catch, the 1 kHz firmware (`library/RotaryCtrl.jl`) latches the infinite-horizon LQR.
4. 8.5 s: 0.35 N, 50 ms force pulse on the tip link; the LQR recovers.

The project also holds the **ACTILINK-JD hardware models** (`actilink-*`, [below](#actilink-jd-hardware-models-actilink-)). They are the same rig scaled up: a Synapticon actuator, AS5048 encoders, an EtherCAT controller, and system identification.

Model `pendulum-double-rotary-free` is the same bond graph released from rest at a non-trivial pose with the controller off; `expected.json` compares it with the Lagrangian design model.

## Files

| file | content |
| --- | --- |
| `design/design.py` | uv script: Lagrangian model (CasADi), LQR, trajectory optimisation, TVLQR, closed-loop simulation; writes `design/design.json` |
| `design/build_model.py` | writes the models, `library/RotaryCtrl.jl` (the gain and trajectory tables are its parameter defaults), `library/LinkAngles.jl`, the scene |
| `design/finish.py` | runs both models on the real backend, compares with the design, writes `expected.json`; `--docs` writes the model docs |
| `design/rotary_lib.py`, `rotary_design.py`, `rotary_build.py`, `rotary_finish.py`, `rotary_docs.py`, `runner.py` | shared with `pendulum-triple-rotary` |

Order: `design.py`, `build_model.py`, `finish.py`, `finish.py --docs`.

## Parameters

Quanser product page (arm 21.59 cm, 0.2570 kg; links 20.0 cm / 0.097 kg and 33.65 cm / 0.127 kg) and SRV02 manual (R 8.4 Ω, L 1.16 mH, k_t 0.0333 N·m/A, J_m 3.87e-7 kg·m², 70:1, load friction 0.015 N·m·s/rad; recalled, not re-read). Assumed: centre of mass at the bar middle, bar radii for the axial inertia, gear stiffness 1000 N·m/rad, bearing friction 3e-5 N·m·s/rad, 10 V limit, efficiencies folded into the load friction.

## Measured (bond graph, Rodas5P, rtol 1e-6)

| quantity | value |
| --- | --- |
| design model against bond graph, free swing over 3 s | 2.4 mrad max |
| all links within 3 deg | 4.98 s |
| catch | 5.02 s |
| upright band before the disturbance | 0.05 deg |
| tip deflection after the pulse | 7.2 deg |
| recovery inside 0.5 deg | 1.9 s |
| peak voltage | 10.0 V (limit 10 V) |
| largest arm angle | 1.57 rad |

---

# ACTILINK-JD hardware models (`actilink-*`)

The same rotary double pendulum built from purchasable parts:

- A **Synapticon ACTILINK-JD10** on the vertical axis turns a **0.3 m arm**.
- A passive joint at the arm tip carries **link 1 (0.6 m)**, and **link 2 (0.6 m)** hangs from the tip of link 1.
- Each passive joint has an **ams AS5048** magnetic encoder: A (SPI) or B (I2C), 14 bit.
- The outer controller runs at **1 kHz on an EtherCAT master**. It estimates the six states from the drive's 20-bit output encoder and the two AS5048 readings, then swings the pendulum up and balances it.
- The drive runs CST (cyclic synchronous torque).

All numbers live in `design/actilink_hardware.json`, and every entry there names its source:

- S1 to S7 and A1: the Synapticon online datasheet, the product PDF of 2026-10-12, the Circulo brochure, the firmware docs and the AS5048 datasheet.
- `est`: an engineering estimate where the datasheet is silent. The identification procedures below replace these with measured values.

## Datasheet numbers

| | JD08 | **JD10** | JD12 | source |
| --- | --- | --- | --- | --- |
| gear ratio (single-stage planetary) | 7.75 | **9** | 9 | S1, S3 |
| rated / max. acceleration torque [N·m] | 7 / 17 | **21 / 68** | 29 / 102 | S1, S3 |
| no-load output speed at 48 V [rpm] | 400 | **210** | 200 | S1, S3 |
| backlash [arcmin] | < 22 | **< 13** | < 11 | S1, S3 |
| rotor inertia at the output [kg·m²] | 0.0042 | **0.020** | 0.040 | S1, S3 |
| mass [kg] / Ø × length [mm] | 0.64 / 80 × 73 | **1.255 / 106 × 86.3** | 1.87 / 120 × 85.5 | S1, S3 |
| pole pairs, k_t [N·m/A_rms], R, L (phase) | 14, 0.1564, 0.27 Ω, 167 µH | **20, 0.2417, 0.195 Ω, 110 µH** | 21, 0.2339, 0.085 Ω, 90 µH | S1, S3 |
| drive (SOMANET Circulo), I_cont / I_max [A_rms] | 7: 8 / 24 | **9: 20 / 60** | 9: 20 / 60 | S4 |
| motor / output encoder | 19 / 20 bit | **20 / 20 bit** | 20 / 20 bit | S1, S3 |
| permissible tilting moment of the output bearing [N·m] | K × 3.2 | **K × 24.5** | K × 30.6 | S1, S3 |
| gear stiffness below / above the knee [N·m/rad], knee [N·m] | 1500 / 4000, 1.5 | **3500 / 9000, 4** | 5000 / 13000, 6 | est |
| motor-side friction at the output: Coulomb / breakaway [N·m], Stribeck speed [rad/s], viscous [N·m·s/rad] | 0.10 / 0.15, 0.5, 0.004 | **0.20 / 0.30, 0.5, 0.010** | 0.30 / 0.45, 0.5, 0.015 | est |
| output bearing: Coulomb [N·m] / viscous [N·m·s/rad] | 0.03 / 0.001 | **0.06 / 0.002** | 0.08 / 0.003 | est |

Common to all sizes:

- **Drive:**
  - V_dc is 48 V, so the linear SVPWM limit is u_q ≤ 0.95·V_dc/√3 = 26.3 V.
  - Current loop at 16 kHz (S6).
  - Velocity/position layer at 4 kHz (S7, interpreted as the loop rate).
  - EtherCAT at 1 kHz with a one-cycle master delay (est).
  - Current-loop bandwidth 1.5 kHz (est, the tuning target).
- **AS5048 (A1):**
  - 14 bit (0.022°/LSB), 11.25 kHz internal sampling, 100 µs propagation delay, 0.06° rms noise.
  - INL ±0.8°, modelled as a first and a second harmonic: 0.25° + 0.15° on link 1 and 0.20° + 0.12° on link 2 (est).
  - Chain latency at the cycle (derived): A/SPI 0.19 ms, B/I2C 0.44 ms. It adds up the propagation delay, the mean sample age, the bus transfer (10 MHz SPI; 400 kHz I2C for two sensors) and the copy into the process image.
- **Rig (est, a design proposal):**
  - Arm: an aluminium 30 × 30 × 2 tube on a clamp hub, 0.53 kg with the joint-1 bearing block and the AS5048 PCB.
  - Links: 20 × 2 aluminium tubes on steel shafts. Link 1 is 0.413 kg with the joint-2 housing. Link 2 is 0.233 kg and runs 40 mm beside link 1, so both links can turn through.
  - Passive joints: two shielded 6001 bearings each, with 1 mN·m Coulomb friction.

## Choice of size: JD10

`design/actilink_design.py` (without `--no-sizing`) compares the three sizes. For each size it:

- optimises the same swing-up: Hermite-Simpson collocation, a 3 s horizon, a 6 N·m torque bound and a ±3 rad arm;
- designs the 1 kHz LQR;
- computes the moment that tilts the output bearing along the trajectory: the horizontal part of dL/dt − Σ r × m g about the flange.

| | JD08 | **JD10** | JD12 |
| --- | --- | --- | --- |
| swing-up peak / rms torque [N·m] | 2.77 / 0.88 | **2.38 / 1.03** | 2.63 / 1.19 |
| peak output speed [rad/s] | 10.6 | **6.6** | 8.0 |
| rotor share of the axis inertia (upright) | 5 % | **20 %** | 33 % |
| bearing tilting moment, static / swing-up peak [N·m] | 2.7 / 35.0 | **2.7 / 32.6** | 2.7 / 24.9 |
| permissible tilting moment with the static K (2.21 / 1.92 / 1.72) [N·m] | 7.1: **exceeded 5×** | **47.0** | 52.6 |
| LQR phase margin / crossover / delay margin | 73° / 11.1 Hz / 18.3 ms | **70° / 8.7 Hz / 22.5 ms** | 68° / 7.2 Hz / 26.4 ms |
| backlash | 22′ | **13′** | 11′ |

Torque does not decide the size. All three sizes swing the pendulum up with less than 3 N·m, a tenth of their rating.

The **output bearing** decides it. During the swing-up, the links' centrifugal and inertial loads act 0.3 m from the axis and tilt the flange with up to 33 N·m.

- **JD08:** its bearing permits only K × 3.2 N·m, so it would need an external support bearing.
- **JD10:** it carries the load inside its static rating and has 13′ backlash instead of the JD08's 22′. The cost is 20 % extra axis inertia.
- **JD12:** it only adds mass and rotor inertia, which brings nothing for this rig.

The Python twin with the JD08 drive balances in the same band, with twice the gear deflection and twice the current.

## Models

| model | what it shows |
| --- | --- |
| `actilink-swingup` | hanging at rest and idle until 1 s; swing-up along the collocation trajectory (3 s) under a time-varying LQR; catch into the balance LQR; balance |
| `actilink-balance` | balance from a disturbed upright (+2.9° / −2.9°), with the LQR active from the first cycle |
| `actilink-push` | balancing; at 2 s, a 0.3 N, 50 ms push on the link-2 tip |
| `actilink-free` | the drive enabled with zero torque and the arm back-driven; the twin check of `expected.json` |
| `actilink-sysid-*` | the seven identification experiments (below) |

Every model has a dashboard:

- **Readouts:** the mode, a balancing lamp, the deviation from upright, the q current as a gauge against the 44 A peak, and the gear deflection.
- **Plots:** the angles, the arm, the torque, the current, the quantised reading against the true angle and the estimate, and the energy.
- **Controls:**
  - the **A/B toggle** (`Ctrl/bus`): AS5048B over I2C with 0.44 ms latency instead of AS5048A over SPI;
  - a slider for the **AS5048 read interval** (global `enc_nrd`, 1 to 8 EtherCAT cycles);
  - a **backlash** slider;
  - in `actilink-push`, the **push force** slider.

The 3D view (`scenes/actilink.sdf`) shows:

- the actuator as a Ø106 × 86 mm cylinder on a column;
- the hub, the arm tube, and the joint-1 bearing block with the AS5048 board;
- the link tubes, the joint-2 housing and the tip.

### Bond graph

```
Uq (MSe, the drive's u_q) -> One_e -> Rw (R = R/1.5), Lw (I = L/1.5), Isense (Df), EMF (GY, p*lambda) -> One_m
One_m -> Rotor (I, J_m = J_out/N^2), FricIn (ALFriction, motor side), Wm (Df), Gear (TF 1/N) -> Zero_g
Zero_g -> GearSpring (ALGearSpring) and Zero_g -> One_o -> FricOut (ALFriction, output bearing), J1.drive (Revolute3D)
J2.drive, J3.drive -> 1-junctions with ALFriction (bearings) [and ALClamp in the identification fixtures]
```

- **Winding:** the dq winding is an equivalent DC circuit in the amplitude-invariant frame.
  - The flow is ie = 1.5·i_q, so u_q·ie is the electrical power.
  - R_eq = R/1.5 and L_eq = L/1.5.
  - The gyrator modulus is k_t,q/1.5, with k_t,q = k_t,rms/√2 = 0.171 N·m/A per ampere of q-current amplitude.
- **`ALGearSpring`:**
  - A smooth dead zone D(φ) = s(φ − b) − s(−φ − b), with s(x) = (x + √(x² + ε²))/2 and b half the backlash. It has no `abs`/`max` kink and no tangent at zero.
  - A hardening spring: k3·D − (k3 − k1)·D_k·tanh(D/D_k).
  - Contact damping d·w·D′(φ), which vanishes inside the gap.
  - It reports the deflection, the stored energy and the loss.
- **`ALFriction`:** Coulomb, Stribeck and viscous friction: (F_c + (F_s − F_c) e^{−(w/v_s)²}) tanh(w/v_ε) + F_v w.
- **Multibody:** spatial, as in the Quanser model: `Revolute3D` joints (compliance 10⁶) and `RigidBody3D` composite bodies.

### Firmware and sensors

- **Current loop:** two blocks.
  - `ALCurrentLoop` is the 16 kHz digital PI. Its zero sits on the winding pole, the output is clamped to 26.3 V, and anti-windup uses conditional integration.
  - `ALCurrentLoopC` is its continuous equivalent: the same PI and clamp, back-calculation anti-windup, and the 1.5-period loop delay as a lag.
  - The current-step experiment uses the digital loop and every other model the continuous one. A 16 kHz held output records 32 000 event rows per simulated second (1.4 GB for the 8 s swing-up). With a 1.5 kHz loop bandwidth against a 9 Hz mechanical crossover, the mechanics do not see the difference. The free-swing twin check, against the digital loop in Python, agrees to 0.9 mrad.
- **`ALDriveLoop` (4 kHz):**
  - CST passes the torque target to the current loop: i_ref = τ/(N k_t,q), clamped to the 68 N·m acceleration-torque limit (44.2 A).
  - CSV runs a PI on the speed taken from the motor encoder. Only the identification experiments use it.
- **Drive encoders:** the stdlib `Encoder`, 20 bit on the motor and 20 bit on the output, read in the 1 kHz cycle.
- **`AS5048`:**
  - It models the INL (two harmonics), noise from a seeded `Noise` block, 14-bit quantisation and the modulo turn.
  - The register reads the angle `lat` before the cycle, θ − w·lat. `lat` is a parameter, so the A/B toggle needs no recompile.
  - Both chains (A and B) always run, with independent noise.
- **`ALCtrl`** (1 kHz, generated by `actilink_build.py`):
  - **Readings:** it unwraps the registers and removes the calibration offsets. They are taken at the hanging rest, so they include the INL at that angle. At upright this leaves a 0.24° bias on link 1 and a static arm offset of about 6° in balance. An upright calibration removes it.
  - **Estimator:** one α-β-γ filter per angle (the steady-state Kalman filter of a white-jerk model) gives the angle and the rate.
  - **Swing-up:** a TVLQR around the trajectory table. The catch triggers when the weighted state norm drops below 0.35.
  - **Balance:** a discrete LQR designed with the one-cycle EtherCAT delay as an extra state, K = [1.37, −42.6, −126.3, 2.29, −20.9, −21.7, 0.056]. Phase margin 70°, crossover 8.7 Hz, delay margin 22.5 ms.
  - **Output:** the torque command, clamped to ±12 N·m.
- **`ALEnergy`:** H = E_mech + E_drive + W_loss − W_in.
  - E_drive covers the rotor, the winding and the gear spring.
  - W_loss covers every friction, copper and contact loss.
  - H is constant except for the energy taken by the joint-compliance regularisation of the three `Revolute3D` joints. The `energy_ledger` check closes that balance exactly.

## System identification

Each experiment is a model that produces the data. Two scripts process it:

- `design/actilink_sysid.py` fits the parameters back from **CSV** in the column layout of bg-sim's run export (`t,<signal id>,...`). The same script runs on lab logs recorded under the same names.
- `design/actilink_finish.py`:
  - runs the models and writes the CSVs (`<temp>/bgsim-actilink-runs/csv/` or `--runs DIR`, outside the example folder because the runs take a few GB);
  - fits them;
  - compares each fit with the parameters the model was built with (`design/actilink_sysid_fit.json`).

Known inputs, not identified:

- the gear ratio (datasheet) and the drive's loop periods;
- the link masses (weigh them) and the COM distances (balance point);
- the AS5048 zero at the hanging rest.

Recommended order on the rig:

1. **Winding and current loop** (`actilink-sysid-current`):
   - Setup: output clamped, a 5 N·m CST step.
   - Log u_q and i_q at 16 kHz (Circulo data logger).
   - A ZOH least-squares fit, i[k+1] = a i[k] + b (u[k] − k_e w[k]), gives R and L.
2. **Friction and back-EMF** (`actilink-sysid-friction`):
   - Setup: links locked to the arm, a CSV staircase from ±0.05 to ±8 rad/s, 0.4 s per level.
   - The mean torque per level fits the Stribeck curve (F_c, F_s, v_s, F_v).
   - The mean u_q − R i_q against the motor speed gives k_e, and from it k_t.
3. **Gear stiffness and backlash** (`actilink-sysid-gear`):
   - Setup: output clamped, a ±12 N·m CST triangle.
   - Plot the motor encoder / N minus the output encoder against the torque.
   - The backlash is the flat part, k1 the slope below the knee, k3 the slope above it, and the motor-side friction the hysteresis.
4. **Link 1 + 2 pendulum** (`actilink-sysid-swing1`):
   - Setup: arm clamped, links locked together, released at 40° from hanging. Record an 8 s free swing on the AS5048.
   - An ODE fit of the period and the decay gives J about joint 1 and the bearing friction.
5. **Link 2** (`actilink-sysid-swing2`): link 1 locked hanging and link 2 released; the same fit.
6. **AS5048 latency, INL and noise** (`actilink-sysid-encoder`):
   - Setup: an AS5048 on the actuator output, read in the 1 kHz cycle against the 20-bit output encoder. One turn at ±4 rad/s (CSV).
   - Linear least squares: d = c0 − w·lat + the INL harmonics.
   - The two directions separate the latency from the offset, and the residual gives the noise.
7. **Rotor inertia** (`actilink-sysid-chirp`):
   - Setup: pendulum locked hanging, a 1 N·m torque chirp from 0.3 to 3 Hz on the arm.
   - Regress torque minus the friction from step 2 on the arm acceleration (Savitzky-Golay derivatives of the 20-bit output encoder). This gives the total inertia.
   - Subtract the locked rig's inertia (the design model at hanging, built on the masses and steps 4 and 5) to get J_out.
   - A first attempt with the pendulum swinging freely failed (J_out off by 37 %). A 1 N·m chirp drives the free double pendulum into chaotic motion, and a simulation fit over 10 s of chaos is ill-posed.

Then:

1. Put the identified numbers into `actilink_hardware.json` and rerun `actilink_design.py`.
2. Calibrate the AS5048 zeros with the pendulum balanced: hold it upright with the arm centred and average over 2 s. This removes the INL bias at upright.

### Fits on the bg-sim data

The fits below come from `design/actilink_sysid_fit.json`. `actilink_finish.py` fails when a fit is outside its tolerance.

| experiment | parameter | fit | model | error | tolerance |
| --- | --- | --- | --- | --- | --- |
| winding | R (phase) | 0.1950 Ω | 0.195 Ω | −0.0 % | 3 % |
| winding | L (phase) | 107.8 µH | 110 µH | −2.0 % | 5 % |
| friction | k_t from the back-EMF | 0.2417 N·m/A_rms | 0.2417 | −0.0 % | 3 % |
| friction | F_c / F_s | 0.264 / 0.363 N·m | 0.26 / 0.36 | +1.4 / +1.0 % | 10 % |
| friction | v_s / F_v | 0.53 rad/s / 0.0123 N·m·s/rad | 0.5 / 0.012 | +6.1 / +2.4 % | 25 / 15 % |
| gear | k1 / k3 | 3593 / 8854 N·m/rad | 3500 / 9000 | +2.7 / −1.6 % | 15 / 10 % |
| gear | backlash | 13.1′ | 13.0′ | +1.0 % | 15 % |
| swing 1 | J about joint 1 / bearing F_c | 0.2478 kg·m² / 1.18 mN·m | 0.2477 / 1.0 | +0.0 / +18 % | 2 / 25 % |
| swing 2 | J about joint 2 / bearing F_c | 0.02197 kg·m² / 1.05 mN·m | 0.02197 / 1.0 | +0.0 / +4.9 % | 2 / 25 % |
| encoder | latency (SPI chain) | 0.191 ms | 0.1875 ms | +1.9 % | 10 % |
| encoder | INL harmonics / noise | 0.251° / 0.150° / 0.061° rms | 0.25 / 0.15 / 0.06 | +0.5 / −0.1 / +2.0 % | 10 / 15 / 10 % |
| chirp | J_out (rotor at the output) | 0.0198 kg·m² | 0.020 | −0.9 % | 15 % |

The bearing Coulomb friction of the passive joints (1 mN·m) is the weakest fit. Over 8 s it costs only 6 mrad of amplitude, which is comparable to the INL; the viscous term trades off against it.

## Results

Bond graph (bg-sim, Rodas5P, rtol 1e-6) against the Python twin (`actilink_lib.py`: the same physics with the 16 kHz digital current loop, RK4 at 32 kHz):

| quantity | bond graph | Python twin |
| --- | --- | --- |
| free swing over 3 s, twin against bond graph (arm / link 1 / link 2) | 0.86 / 0.15 / 0.27 mrad max | |
| swing-up: catch (balance LQR latched) | 4.00 s | 4.00 s |
| swing-up: largest arm angle | 2.98 rad | 2.98 rad |
| swing-up: peak torque target / q current / q voltage | 12.0 N·m (clamp 12) / 8.3 A (limit 44.2) / 7.4 V (limit 26.3) | 12.0 / 8.3 / 8.5 |
| swing-up: upright band from catch + 1.5 s; final deviation | 0.41°; 0.012° | 0.33° (last 1 s); 0.017° |
| swing-up: peak gear deflection (half backlash 1.89 mrad) | 6.3 mrad | 6.3 mrad |
| balance (AS5048A): band after 1.5 s; arm limit cycle | 0.33°; 1.2° p-p | 0.37°; 1.7° p-p |
| balance: peak torque / current | 6.9 N·m / 4.6 A | 7.2 / 4.4 |
| push 0.3 N, 50 ms: link-2 peak; arm excursion; back inside 1° | 4.7°; 55°; 1.40 s | 4.5°; 53°; 1.40 s |
| balance with AS5048B (I2C) | | 0.32°; arm 1.4° p-p |
| energy invariant H, balance run: drift = joint-compliance work | 0.161 J = 0.161 J (throughput 3.5 J) | |

Notes on the results:

- **Push limit.** A 0.4 N push is still recovered. At 0.5 N the arm runs away: the voltage saturates and the arm needs more than one turn.
- **Cabling.** In swing-up, balance and push, the arm stays within ±3 rad, so a cable loop to the AS5048 boards suffices. The friction staircase and the encoder bench turn continuously; run them with the arm cables unplugged or through a slip ring.
- **Arm limit cycle.** The 1 to 2° limit cycle in balance comes from the backlash and the friction at the arm.
- **Static arm offset.** The arm settles about 6° off centre. This is the INL bias of the hanging calibration (above).
- **I2C bus.** At 1 kHz the I2C chain (0.44 ms latency) balances as well as SPI. Its 0.25 ms of extra latency is small against the 22.5 ms delay margin.

Checks in `expected.json` (11 `actilink-*` entries, written by `actilink_finish.py`):

- **All models:** no diagnostics (W201, W206, E901) and the scene bindings.
- **Free swing:** the twin samples every 0.5 s, within 2× the measured difference. The energy invariant H holds to 2.4e-4 of the throughput.
- **Balance, push and swing-up:**
  - the q current inside the 44.2 A peak;
  - the torque target inside the 12 N·m clamp;
  - u_q inside 26.3 V;
  - the gear deflection bounded;
  - the mode at catch;
  - the upright band, measured on the 14-bit encoders;
  - the push deflection and the recovery;
  - the energy invariant H. Its tolerance is the measured joint-compliance work, because `ALEnergy` cannot see inside the `Revolute3D` joints.
  - the Tellegen `energy_ledger`, which balances to 1e-6 with every element.
- **Identification models:** one check per experiment (current-step level, swing period, locked links, CSV speed, deflection and arm amplitude). The fits themselves are verified by `actilink_finish.py`.

## Files

| file | content |
| --- | --- |
| `design/actilink_hardware.json` | every datasheet number with its source; estimates marked `est` |
| `design/actilink_lib.py` | drive and rig data; the kinematics and Lagrangian (CasADi); the 9-state twin (multibody, gear with backlash, friction, rotor, winding); the firmware replica; the closed-loop simulator |
| `design/actilink_design.py` | sizing of JD08/10/12 (`actilink_sizing.json`), swing-up, TVLQR, LQR with the delay, margins, estimator and the Python closed-loop runs; writes `actilink_design.json` |
| `design/actilink_build.py`, `actilink_models.py` | the bond graph, `library/ALCtrl.jl`, the scene, the scenarios and their dashboards |
| `design/actilink_run.jl` | runs several models in one Julia process (`julia --project=julia/BGSim ... <out> <model>[:t_end] ...`) |
| `design/actilink_sysid.py` | the identification fits from CSV |
| `design/actilink_finish.py` | runs everything, fits, measures, and writes the `actilink-*` entries of `expected.json` |
| `library/AL*.jl`, `library/AS5048.jl` | the hardware blocks |

Order: `actilink_design.py`, `actilink_models.py`, `actilink_finish.py`.
