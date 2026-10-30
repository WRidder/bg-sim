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

![The baseline model canvas|900](assets/ef2818e01102.png)

## What to try

- Press **Run** and open the preconfigured plots: "Phase current" ([Iphase/y](signal:Iphase/y), [Iq/p.f](signal:Iq/p.f)), "Speed" ([WmSens/p.f](signal:WmSens/p.f), [SpeedLoop/w_err](signal:SpeedLoop/w_err)), "Position" ([Theta/y](signal:Theta/y), [PosLoop/pos_err](signal:PosLoop/pos_err)) and "Voltage".
- Open `two-mass`, `switching`, `encoder` and `full` from the Open dialog's model selector and compare the same signals; each variant's page of this documentation lists what differs.
- Edit the constants at the top of `design/design.py` and re-run it (`uv run examples/industrial-servo/design/design.py`) to regenerate all five model files (the committed models are the generated result).

## 3D view

`scenes/industrial-servo.sdf` shows the motor with its rotor disc and a load disc behind a coupling. The joint `rotor_joint` follows the motor angle [Theta/y](signal:Theta/y) in all five variants; in `two-mass` and `full` the joint `coupling_joint` follows the coupling twist `Kc/q`. The rigid variants have no coupling state, so the load disc moves with the rotor.

![3D view at t = 0.3 s|500](assets/1ab0c01e7dbc.png)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
