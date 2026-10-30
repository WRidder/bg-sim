# pendulum-double-rotary — a Quanser-style rotary double inverted pendulum (X5.13)

A horizontal arm turns about the vertical axis, driven by an SRV02-like DC servo (70:1 gearbox, ±10 V). A two-link pendulum hangs from the arm tip and swings in the plane **perpendicular to the arm**. The plant is a **spatial multibond bond graph** (`Revolute3D`, `RigidBody3D`, `GroundSpatial`, `ComposePose3D`, `ExternalWrenchSpatial`), as in `robot-arm-3d` and `cube-3d`.

Scenario (model `pendulum-double-rotary`, 12 s):

1. 0 to 1 s: hanging at rest, motor voltage 0.
2. 1 s: swing-up, a collocation trajectory (CasADi/IPOPT, includes the motor and its voltage limit) tracked by a time-varying LQR, T_s = 4 s.
3. 5.02 s: catch, the 1 kHz firmware (`library/RotaryCtrl.jl`) latches the infinite-horizon LQR.
4. 8.5 s: 0.35 N, 50 ms force pulse on the tip link; the LQR recovers.

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
