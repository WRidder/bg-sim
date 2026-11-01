# pendulum-triple-rotary — a rotary triple inverted pendulum (X5.13)

The rotary arm of `pendulum-double-rotary` with a **three-link** chain: a horizontal arm turns about the vertical axis, driven by an SRV02-like DC servo (70:1 gearbox, ±15 V), and the chain hangs from the arm tip and swings in the plane **perpendicular to the arm**. The plant is a **spatial multibond bond graph** (`Revolute3D`, `RigidBody3D`, `GroundSpatial`, `ComposePose3D`, `ExternalWrenchSpatial`), as in the double. **This triple is not a Quanser product.**

Scenario (model `pendulum-triple-rotary`, 12 s):

1. 0 to 1 s: hanging at rest, motor voltage 0.
2. 1 s: swing-up, a collocation trajectory (CasADi/IPOPT, includes the motor and its voltage limit) tracked by a discrete time-varying LQR, T_s = 4 s.
3. 5.0 s: catch, the 1 kHz firmware (`library/RotaryCtrl.jl`) latches the infinite-horizon LQR once the LQR cost-to-go x'Px is below its threshold.
4. 8.5 s: 0.1 N, 50 ms force pulse on the tip link (about 2/3 of the largest pulse the loop recovers, 0.149 N); the LQR recovers.

Model `pendulum-triple-rotary-free` is the same bond graph released from rest at a non-trivial pose with the controller off; `expected.json` compares it with the Lagrangian design model.

## Files

| file | content |
| --- | --- |
| `design/design.py` | uv script: feasibility numbers, discrete LQR, trajectory optimisation, discrete TVLQR, closed-loop validation (nominal and six perturbed models), free swing; writes `design/design.json` (the collocation result is cached in `design/_swingup.npz`, `--fresh` recomputes it) |
| `design/build_model.py` | writes the models, `library/RotaryCtrl.jl` (the gain and trajectory tables are its parameter defaults), `library/LinkAngles.jl`, the scene |
| `design/finish.py` | runs both models on the real backend, compares with the design, writes `expected.json`; `--docs` writes the model docs |
| `design/triple_lib.py` | the model, the implicit collocation, the discrete TVLQR, the firmware and the closed loop |
| `design/triple_build.py`, `triple_finish.py`, `triple_docs.py` | adapted copies of the double's `rotary_build.py`, `rotary_finish.py`, `rotary_docs.py`; the backend runner is the double's `runner.py`, imported unchanged |

Order: `design.py`, `build_model.py`, `finish.py`, then the e2e spec (its 3D screenshot goes to `design/_shots/3d.png`), `finish.py --docs`.

## What differs from the double, and why

| choice | double | triple | why |
| --- | --- | --- | --- |
| chain | short 20.0 cm / 0.097 kg + medium 33.65 cm / 0.127 kg | short + short + medium | a second Quanser short pendulum inserted between the double's two links |
| amplifier limit | 10 V | **15 V** | at 10 V the back-EMF caps the arm at 4.2 rad/s; the smooth triple swing-up needs 4.4–5 rad/s (6.3 rad/s are available at 15 V). At 10 V IPOPT only found whip-like trajectories (link rates 40–60 rad/s) that no feedback tracked |
| joint compliance | 1e6 | **1e8** N/m, N·m/rad | the chaotic swing-up amplifies any design-model mismatch |
| gear shaft | 1000 N·m/rad | **1e7** N·m/rad, 200 N·m·s/rad (at the load) | a stand-in for a rigid gearbox (keeps the rotor inertia integral); also integrates 3x faster than 1e5 |
| winding in the design model | neglected | **first-order lag as an inertia** −L n² k_t²/R² = −8.9e-5 kg·m² | the 0.14 ms winding lag was the largest mismatch: 1.5 mrad over 2 s without it, 0.011 mrad with it |
| collocation | explicit, symbolic M⁻¹ | **implicit** (accelerations as variables), piecewise-linear voltage, cost ∫u² + 0.01 u̇² + 0.05 \|link rates\|² | sparse and fast: every solve takes seconds to a minute |
| continuation | voltage bound, grid | link-rate weight 1.0 → 0.05, grid 100 → 250, voltage 15 → 14 V | the heavy first weight picks a smooth basin; the last step leaves 1 V for feedback |
| TVLQR | continuous Riccati ODE | **discrete** Riccati recursion on the 1 kHz zero-order-hold model, P_N = discrete LQR P; nominal = one roll-out of the sampled model | stable for any weights; the nominal is consistent with the sampled model |
| catch rule | weighted norm | LQR cost-to-go x'Px < 3e4 after T_s | the last table row is the LQR gain, so the switch is seamless |

Feasibility estimate (`design.json` → `feasibility`): raising the chain takes 2.18 J, 0.54 W on average over 4 s; the winding gives at most V²/(4R) = 6.7 W at 15 V (3.0 W at 10 V) and 4.2 N·m stall torque at the arm. Energy is not the limit, arm speed is (see above). RMS winding current over the run 0.13 A.

## Parameters

Quanser product page (arm 21.59 cm, 0.2570 kg; short pendulum 20.0 cm / 0.097 kg, medium 33.65 cm / 0.127 kg) and SRV02 manual (R 8.4 Ω, L 1.16 mH, k_t 0.0333 N·m/A, J_m 3.87e-7 kg·m², 70:1, load friction 0.015 N·m·s/rad; recalled, not re-read), as in the double. Assumed: the three-link chain, the 15 V limit, centre of mass at the bar middle, bar radii for the axial inertia, bearing friction 3e-5 N·m·s/rad, efficiencies folded into the load friction.

Controller: Q = diag(20, 200, 200, 200, 1, 5, 5, 5), R = 5 V⁻² for both the TVLQR and the balance LQR (equivalent poles −131 … −0.83 1/s). Validated in `design.py` with the firmware logic on the design model and on six perturbed models (link masses ±3 %, lengths +1 %, bearing friction ×3, k_t −3 %, load friction ×1.5): all are caught at 5.0 s and recover the pulse.

## Measured (bond graph, Rodas5P, rtol 1e-6; free model rtol 1e-9)

| quantity | bond graph | design.py |
| --- | --- | --- |
| design model against bond graph, free swing over 2 s | 0.011 mrad max | |
| all links within 3 deg | 3.82 s | 3.82 s |
| catch | 5.00 s | 5.00 s |
| upright band before the disturbance | 0.001 deg | 0.001 deg |
| tip deflection after the pulse | 3.55 deg | 3.55 deg |
| recovery inside 0.5 deg | 1.35 s | 1.35 s |
| peak voltage | 14.15 V (limit 15 V) | 14.15 V |
| largest arm angle | 2.50 rad | 2.50 rad |
| run time (real worker) | 37.5 s (free model 82.6 s) | |

Trajectory optimisation 124 s (four warm-started solves), discrete TVLQR 40 s.

## The flexible arm (`-flex`, `-flex-lowpass`, `-flex-free`)

The same rig with a flexible arm: the rigid arm body is replaced by a `stdlib:spatial/FlexibleBeam3D` (assumed modes, clamped at the motor hub, `ny` = 2, `nz` = 2, `nt` = 1). The pendulum chain hangs from the beam's end B.

| model | arm | firmware | result |
| --- | --- | --- | --- |
| `pendulum-triple-rotary-flex` | flexible | `RotaryCtrl` (the rigid design, unchanged) | fails: the arm mode goes unstable near the top of the swing-up, the voltage saturates from 2.88 s, the chain is never caught |
| `pendulum-triple-rotary-flex-lowpass` | flexible | `RotaryCtrlLP` (the same weights, designed with a 12 Hz low-pass in the loop) | caught at 5.0 s, recovers from the push in 2.24 s |
| `pendulum-triple-rotary-flex-free` | flexible | off | free swing; with overrides also the tap test and the stiff limit |

**Choice of arm.** A 3 × 50 mm AISI 304 strip on edge (E 193 GPa, ν 0.29), 0.2159 m long. The density, 7936 kg/m³, is set so the strip weighs the rigid arm's 0.257 kg, and its rigid inertia about the motor axis matches the rigid arm's to 0.1 %. Flexibility is then the only difference. A flat strip on edge, like the Quanser rotary flexible link, bends easily in the plane of the motor torque (EI 21.7 N·m²) and hardly at all under the pendulum's weight (EI 6031 N·m²). Torsion is included (GJ 32.4 N·m²) but stays tiny, because the pendulum hinge passes no moment about the arm axis. The first horizontal mode was placed a few times above the controller's fastest closed-loop pole (131 1/s, 21 Hz) and the pendulum's fastest unstable pole (3.8 Hz), where a rigid-arm design may or may not cope with it.

**Frequencies** (`flex_design.py`; the exact values solve the Euler-Bernoulli frequency equation of a clamped beam with the pendulum assembly at the tip):

| mode | Hz |
| --- | --- |
| bare strip, clamped-free: horizontal / vertical / torsion | 51.27 / 854.5 / 417.7 |
| hub clamped, chain hanging, horizontal: exact, with the hinged chain as a frequency-dependent tip mass M(ω) (28.1 g at high frequency) | **42.68** |
| the same: Rayleigh with M(∞) / assumed modes (2) / bond-graph tap test | 43.00 / 42.69 / 42.66 |
| the same with the whole 0.321 kg chain as a rigid tip mass (wrong: the hinge decouples the chain) | 20.71 |
| hub clamped, vertical: exact (tip mass 0.321 kg, 0.0526 kg·m² about the tip, gravity) / assumed modes (2) / tap test | 111.4 / 122.3 / 121.9 |
| running rig (hub on the motor, no control) | 74.7 |

**Controller finding.** The rigid firmware has no roll-off: at the upright its loop gain on the rigid arm is still 0.22 at 76 Hz, and the arm's resonance lifts that to 4.3. The closed loop on the flexible arm has the pole pair +277 ± 412j 1/s (65.5 Hz). A notch (55 to 90 Hz) or a gentler LQR (R up to 5e4) does not stabilise it, and the linear loop needs an arm about 23 times stiffer. In the run, the swing-up rings the arm mode at about 106 Hz. Near the top, where the TVLQR gains grow towards the balance gains, the frozen-time loop goes unstable at 2.88 s and the 15 V limit is reached at the same moment. The swing-up is lost, and the saturated motor ends up driving the arm round (49 rad by 12 s). The fix keeps Q, R and the swing-up nominal, but designs the LQR and the discrete TVLQR for the rigid model followed by a second-order 12 Hz low-pass (ζ 0.707) between the feedback and the motor. The filter state is part of the controller state, so the Riccati design compensates the filter lag. The loop gain then crosses 1 at about 7 Hz and is 0.21 at the arm resonance (gain-stabilised). Validated on the design model (rigid, flexible, E × 0.5 and × 2, perturbed links, friction and k_t) and linearly stable for E × 0.5 to × 100. The price is a slower balance loop: 5.7 deg tip-link deflection after the push (rigid: 3.5 deg), recovery 2.24 s (rigid: 1.35 s).

**Measured** (bond graph, `flex_finish.py`): the flexible design model follows the bond graph to a few µm of modal coordinate until the first saturation. Tap test 42.66 Hz (exact 42.68 Hz, 0.05 %) and 121.9 Hz vertically (two assumed modes 122.3 Hz). Stiff limit (E × 1e4) against the rigid free model: at most 1.6e-5 rad over the first second of the chaotic free swing. Low-pass firmware: caught at 5.00 s, band 0.0014 deg, peak voltage 14.9 V, largest sideways tip deflection 1.62 mm in the swing-up, 0.65 mm after the push, 14 nm while balancing. Run times: 143 s (`-flex-lowpass`), 67 s (`-flex`), 114 s (`-flex-free`).

**3D view.** The arm visual is a 3 × 50 mm box (`visual:arm_strip`) on the link that follows `Arm/pose`, with three deformation bindings (bending-y with `eta_y[1..2]`, bending-z with `eta_z[1..2]`, torsion with `eta_t[1]`; clamped-free basis, beam axis +x, y +y, length 0.2159 m). The pendulum hinge follows `Arm/poseB`, the deformed tip. The dashboards plot the tip deflection `Arm/dB[2..3]`, the modal coordinates and the twist.

| file | content |
| --- | --- |
| `design/flex_lib.py` | the beam (sections, modes, frequencies), the flexible design model (Lagrange, the rigid triple plus assumed modes), the frequency equations, the chain's frequency-dependent tip mass |
| `design/flex_design.py` | frequencies, the rigid firmware on the flexible arm (linear and the whole scenario), the low-pass LQR/TVLQR and its validation; writes `design/flex_design.json` |
| `design/flex_build.py` | writes the three models, `library/RotaryCtrlLP.jl`, `scenes/pendulum-triple-rotary-flex.sdf` (the rigid models are not touched) |
| `design/flex_finish.py` | runs the flexible models, the tap test, the stiff limit, E × 100 and the rigid references on the real backend; adds their checks to `expected.json`; `--docs` writes the model docs (`flex_docs.py`) |

Order: `design.py`, `build_model.py`, `finish.py`, then `flex_design.py`, `flex_build.py`, `flex_finish.py`, `tools/video/capture-flexarm.mjs --shots design/_shots` (3D screenshots for the docs), `flex_finish.py --docs`.
