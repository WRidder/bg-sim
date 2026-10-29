# industrial-servo — a PMSM servo drive in five fidelity variants

Plan 9.6b's industrial servo sample (X2.6). One Delta-ASDA-A3-style permanent-magnet
synchronous motor drive, with a **bond-graph dq plant** (D28), a sampled cascaded
current/speed/position firmware and an inverter. The same case is simulated at five
fidelity levels so every refinement can be compared with the baseline:

| model | inverter | mechanics | feedback |
| --- | --- | --- | --- |
| `baseline` | averaged, limited to `V_dc/√3` | rigid inertia | ideal angle and speed |
| `two-mass` | averaged | flexible I–C–R coupling + speed-loop notch | ideal |
| `switching` | two-level PWM, dead time, device drops | rigid | ideal |
| `encoder` | averaged | rigid | 24-bit encoder + differenced speed estimate |
| `full` | two-level PWM, dead time, device drops | flexible I–C–R coupling + notch | 24-bit encoder + estimated speed |

The run is one combined scenario: a 100 rad/s speed step at 0.05 s, position mode at
0.15 s (the shaft returns from about 9.4–9.7 rad to 0), and a resisting 2 N·m load
step at 0.9 s. It ends at 1.2 s. The acceptance checks every variant's step
response, current/torque limit, steady-state error, switching ripple, encoder
quantization and (for the flexible variants) the resonance/notch attenuation, plus
baseline-vs-variant comparisons.

## Plant (bond graph)

```
Vd(MSe) → DJ(1) ── Rd(R_s) ── Id(L_d) ── IdSens ── MGY(u = ω_e L_q)
Vq(MSe) → QJ(1) ── Rq(R_s) ── Iq(L_q) ── IqSens ── Bemf(MSe, +k_e ω_m)
                 └─ MGY ← DJ          └─ GY(r = k_t = 1.5·p·ψ_m) → MJ(1)
Iq(IqSens) ── MSf(−1) ── GY.p1
MJ(1) ── Jm(I) ── Bm(R) ── WmSens ── Theta(integrator)
```

The dq equations are exactly plan 9.6b:

```
v_d = R_s·i_d + L_d·di_d/dt − ω_e·L_q·i_q
v_q = R_s·i_q + L_q·di_q/dt + ω_e·(L_d·i_d + ψ_m)
ω_e = p·ω_m,   T_e = 1.5·p·ψ_m·i_q,   J·dω_m/dt = T_e − B·ω_m − T_load
```

**Elements and signs**

- `DJ` / `QJ` are the d and q 1-junctions. `Rd`/`Id` and `Rq`/`Iq` are the stator
  resistance and inductance; `IdSens`/`IqSens` are `FlowSensor`s.
- `MGY` (`p1` on `DJ`, `p2` on `QJ`) has the signal modulus `u = ω_e·L_q`, from the
  `WeL` gain `p·L` of the measured speed. Its two equations give the
  `−ω_e L_q i_q` and `+ω_e L_d i_d` cross terms (the surface-mount assumption
  `L_d = L_q = L` makes one gyrator exact; a salient machine would add the
  `ω_e(L_d−L_q)i_d` term as an MSe).
- `Bemf` is an `MSe` on `QJ` with gain `+k_e` and input `ω_m`. With the bond from the
  junction to the MSe, the junction sees `−k_e ω_m`, i.e. the `+ω_e ψ_m` back-EMF of
  the q equation.
- `GY` has `r = k_t = 1.5·p·ψ_m = 0.48 N·m/A`; its p2 torque is `+k_t i_q` into `MJ`.
  The measured `i_q` drives its p1 through `IqSrc`, an `MSf` with gain `−1` (the
  flow sign of a port on the `from` end). This `MSf` is the **dq 3/2 power-scale
  interface**: the per-axis dq electrical bond carries `v_d i_d + v_q i_q` while the
  shaft carries `T_e ω_m = 1.5 k_e i_q ω_m`; the gyrator supplies the torque and the
  MSf absorbs the difference. It is a bond-graph element driven by a sensor, not a
  code node; the plant equations above are reproduced in actual dq variables.
- `MJ` carries the rotor inertia `J_m = 4.4e-4 kg·m²`, the viscous `B_m = 1e-4` and
  the speed sensor. `Theta` is a kinematic integrator of the measured speed (D28
  sensor exception) used by the controller and the encoder.

**Two-mass variants.** `MJ —TF(1)→ S0(0) ←TF(1)— LJ` with a **parallel**
spring/damper on a 1-junction `KJ`: `S0 → KJ`, `Kc` and `Dc` on `KJ`. The 0-junction
forms the relative velocity `ω_m − ω_L`; the 1-junction gives the spring and damper
the same relative flow and **adds their efforts**, so the coupling torque is
`k_c·Δθ + c_c·(ω_m−ω_L)`. (Putting both C and R on the 0-junction would be a series
Maxwell element, which lets the load creep under a constant load.) The load is
`J_L = 4.4e-4`, `B_L = 1e-4`, `k_c = 800 N·m/rad`, `c_c = 0.02 N·m·s/rad`; the
undamped resonance `√(k_c(1/J_m + 1/J_L))/2π = 303.5 Hz`. The load torque MSe is on
`LJ`; the rigid variants put it directly on `MJ`.

| quantity | value |
| --- | --- |
| DC bus / voltage limit | `V_dc = 300 V`, `V_dc/√3 = 173.205 V` |
| stator | `R_s = 0.5 Ω`, `L_d = L_q = 6 mH` |
| magnet / poles | `ψ_m = 0.08 Wb`, `p = 4` (`k_t = 0.48 N·m/A`, `k_e = 0.32 V·s/rad`) |
| rotor / load | `J_m = 0.44e-3`, `B_m = 1e-4`; `J_L = 0.44e-3`, `B_L = 1e-4` |
| coupling | `k_c = 800 N·m/rad`, `c_c = 0.02 N·m·s/rad` (303.5 Hz) |
| current | rated 5 A peak, limit 15 A peak (`7.2 N·m`) |
| encoder | 24-bit absolute, `2π/2^24 = 3.745e-7 rad` |
| PWM | 8 kHz requested in the variant spec; this sample uses a **4 kHz** carrier with a 100 kHz sampled comparator (25 levels per carrier), `T_d = 2 µs`, `V_drop = 1.2 V` |
| run | 1.2 s, `solver = auto` (Tsit5), 6001 points (averaged) or 10 µs (switching/full) |

**Sensors only** (allowed by D28): `FlowSensor`s, the `Theta` integrator, the
`Quantizer`, the `SpeedEstimator` (1 kHz backward difference of the quantized angle
plus a first-order low-pass, `α = 0.8`) and the `EncoderMonitor` (records the
quantization error at the encoder tick). The `PwmInverter` and the three loop
blocks are the only controller/switching code.

## Controller

The cascade is tuned inner-to-outer; `design/design.py` computes and writes all
gains into the five model documents:

| loop | rate | law | gains |
| --- | --- | --- | --- |
| current | 8 kHz | PI on `i_d`, `i_q`, dq decoupling, back-EMF feedforward, vector voltage limit | `Kp = L·ω_ci = 18.85 V/A`, `Ki = R·ω_ci = 1570.8 V/(A·s)`, `ω_ci = 2π·500` |
| speed | 1 kHz | PI on the speed error, output `i_q` limited to ±15 A | `Kp = J·ω_cs/k_t = 0.4608 A/(rad/s)`, `Ki = 46.32 A/(rad/s²)`, zero at `ω_cs/5` (`ω_cs = 2π·80`) |
| position | 200 Hz | P on the position error, output speed limit ±200 rad/s | `Kp = 20 1/s` |

The current PI cancels the electrical pole (`Ki/Kp = R/L`); the speed PI places its
zero at one fifth of the 80 Hz crossover. The position loop uses a 200 rad/s speed
limit. A one-sample `UnitDelay` at 8 kHz sits between the current loop and the
inverter in every variant. The `two-mass`/`full` speed feedback passes through a
second-order **notch at 303.5 Hz, Q = 4, fs = 1 kHz** (`DiscreteTF`, coefficients
from `iirnotch`). The switching inverter adds the min–max (SVPWM) zero-sequence,
a sampled center-aligned carrier, dead time and a conduction drop on the sign of
each phase current, then transforms the applied leg voltages back to dq.

The `baseline`/`switching` current loop is fed by the speed loop; at 0.05 s the
100 rad/s speed error saturates `i_q` at 15 A, which is the current-loop step used
by the acceptance. The 0.15 s mode switch puts the accumulated position (about
9.5 rad) on the position loop, and the 0.9 s load step tests the speed-loop
integrator's load rejection.

## Design and model generation

`design/design.py` is both the design record and the generator of the five
`models/*.bgmodel.json` files and `bgsim.project.json`:

```text
uv run examples/industrial-servo/design/design.py
```

It prints the gains, the notch coefficients, the resonance and the PWM data, then
rewrites the models. The committed models are the generated result. The script
also keeps the plant and firmware parameters in one place; edit the constants at
the top and re-run to regenerate.

**Why these values.** `ω_ci = 2π·500` is a 500 Hz crossover at the 8 kHz current
sample (a comfortable 16 samples per period with the one-sample delay). The speed
crossover of 80 Hz is a decade below the 303.5 Hz coupling resonance, so the notch
is only needed to keep the resonance out of the feedback path; without it the
resonance is still excited by the torque step, but the loop does not amplify it.
The position P at 20 1/s gives a 50 ms position time constant; the 200 rad/s limit
bounds the move and the 15 A current limit bounds the acceleration. The 24-bit
encoder is far finer than the position band; its 1.872e-7 rad half-LSB error is
recorded directly by `EncoderMonitor`.

## Variants

- **`baseline`** — the averaged inverter (`V_dc/√3` limit), a rigid rotor/load,
  ideal angle and speed. The reference for every comparison.
- **`two-mass`** — the same drive with the flexible coupling and the speed-loop
  notch. The motor and load speeds ring at 303.5 Hz after the speed step; the
  notch output (`Notch/y`) has visibly less high-frequency content than its input
  (`Notch/u`).
- **`switching`** — the two-level inverter replaces the averaged source. The
  phase current shows the 4 kHz ripple; the dead time and the 1.2 V drop add the
  usual low-order distortion. The plant and the three loops are unchanged.
- **`encoder`** — a 24-bit `Quantizer` at 8 kHz on the angle, a 1 kHz differenced
  speed estimate with a first-order low-pass, and the quantized angle in the
  position loop (and in the switching variants' Park transforms). The
  `EncoderMonitor` records the half-LSB quantization error.
- **`full`** — all three forks together: PWM/dead time/drop, the flexible
  two-mass mechanics with the notch, and the 24-bit encoder with the estimated
  speed. This is the realistic drive model.

## Checks and measured results

`expected.json` is the machine-readable acceptance; `uv run examples/run_checks.py`
runs it through the real Julia worker. The new runner kinds for this sample are
`step_response` (rise/overshoot/settling/final error from a step window) and
`ripple` (RMS or peak-to-peak of the high-frequency component over a steady
window). Existing check kinds are unchanged.

The five variants have **12 / 15 / 13 / 15 / 19 model checks** and **8
baseline-vs-variant compares** (82 industrial-servo checks in total). The whole
example lane reports **170 passed, 0 failed in 155.8 s**; with a warm worker the
five servo runs take about 10, 7, 34, 4 and 37 s respectively (the switching
variants simulate about 850k solver steps; the 10 µs output grid records up to
244k rows, and the first run pays the ~1 s Julia compile).

| check | baseline | two-mass | switching | encoder | full |
| --- | --- | --- | --- | --- | --- |
| speed 100 rad/s: rise / overshoot / settle | 5.1 ms / 3.4 % / 15 ms | 11.1 ms / 6.0 % / 32 ms | 5.1 ms / 3.6 % / 17 ms | 5.1 ms / 10.5 % / 11 ms | 11.1 ms / 7.2 % / 28 ms |
| position step (≈9.5 rad → 0): rise / overshoot / settle (5 mrad) | 106 ms / 0 % / 380 ms | 107 ms / 0 % / 396 ms | 106 ms / 0.04 % / 394 ms | 108 ms / 0 % / 386 ms | 108 ms / 0.05 % / 549 ms |
| current 15 A: rise / overshoot / settle (0.8 A) | 0.44 ms / 4.2 % / 0.63 ms | 0.44 ms / 4.2 % / 0.63 ms | 0.49 ms / 4.4 % / 2.4 ms | 0.44 ms / 3.9 % / 0.63 ms | 0.49 ms / 4.4 % / 2.2 ms |
| peak `i_q` / torque | 15.80 A / 7.585 N·m | 15.80 / 7.586 | 15.66 / 7.515 | 15.78 / 7.574 | 15.74 / 7.556 |
| peak voltage vector | 173.205 V | 173.205 | 173.205 | 173.205 | 173.205 |
| phase-current ripple (RMS / p-p) | 0.00064 A | 0.00059 A | **0.170 A / 0.692 A** | 0.00058 A | **0.166 A / 0.686 A** |
| position at 1.15 s | −6.6e-4 rad | −6.7e-4 | −6.9e-4 | −6.8e-4 | −6.1e-4 |
| speed at 1.15 s | 0.014 rad/s | 0.014 | 0.014 | 0.014 | 0.027 |
| `EncMon/err` | — | — | — | 1.872e-7 rad | 1.872e-7 rad |
| speed-estimate RMS error (1.0–1.15 s) | — | — | — | 0.0038 rad/s | 0.046 rad/s |
| notch input → output ripple (250 Hz HP) | — | 1.099 → 0.827 | — | — | 1.067 → 0.875 |
| load-side ringing (250 Hz HP) | — | 1.181 | — | — | 1.173 |

All variants report only **W205** (the dimensionless Generic bond island, which is
expected for a bond graph without a concrete domain); `E900/E901/E103/E104/E105/
E106/W206` are forbidden by `no_diagnostics`.

Notes on the measurements:

- The speed-loop overshoot is larger in the encoder variants (10.5 %) because the
  1 kHz differenced estimate lags the true speed by up to one sample plus the
  low-pass; the same estimate still tracks the steady speed to 0.0038 rad/s.
- The switching/full position step leaves a small residual (about 4 mrad) at
  0.88 s from the dead-time/drop asymmetry; the acceptance uses a 5 mrad band for
  the step and checks the final position to 1.5 mrad after the load step.
- The current/torque checks allow 16 A / 7.7 N·m although the command limit is
  15 A / 7.2 N·m: the measured `i_q` overshoots the reference by up to 5 % with
  the 500 Hz current loop. The averaged `V_dc/√3` limit is exact (173.205 V).
- The switching ripple is a *sampled* PWM: the comparator runs at 100 kHz on a
  4 kHz carrier (25 levels per carrier), so the recorded ripple is a faithful
  staircase approximation, not an analog edge. The 4 kHz low-carrier setting keeps
  the simulation at ~850k steps; an 8/16 kHz carrier would scale the ripple down
  and the run time up.
- The `IqSrc` MSf and the `Bemf`/`GY` pair realize the plan's `MSe back-EMF + GY`
  split while keeping the q equation and the torque exact; see the plant section
  for the 3/2 dq power-scale explanation.

## Playwright

`web/tests/e2e/industrial-servo.spec.ts` creates the sample through
`POST /api/projects {example: "industrial-servo"}`, opens `baseline`, asserts the
dq bond-graph nodes and the three firmware blocks, runs it, plots `Iphase/y` and
`WmSens/p.f`, and reads the legends at about t = 1.15 s (speed ≈ 0, current ≈
4.17 A). It then switches to `full` through the Open dialog's model selector, runs
the combined variant and checks the same two signals. The spec starts its own real
worker on a free port unless the suite runs with `BGSIM_E2E_REAL=1`; it reports
**1 passed in 59.7 s** in this environment.

## Read-only sample

This directory is a **sample**: it is copied into the user's projects folder on
import. The files here are never written by the editor (only
`design/design.py` writes the models, when invoked by hand). `expected.json` is
the machine-readable acceptance used by `examples/run_checks.py` and
`tools/check.py --lane x`.

## 3D view

`scenes/industrial-servo.sdf` shows the motor with its rotor disc and a load disc behind a coupling. Joint `rotor_joint` follows the motor angle `Theta/y` in all five variants; in `two-mass` and `full` the joint `coupling_joint` follows the coupling twist `Kc/q`, so the load marker lags and rings against the rotor marker. The rigid variants (`baseline`, `switching`, `encoder`) have no coupling state, so the load disc moves with the rotor.
