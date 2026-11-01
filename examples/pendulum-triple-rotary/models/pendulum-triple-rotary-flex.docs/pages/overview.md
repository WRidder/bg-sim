# Triple rotary pendulum on a flexible arm

The rig of [pendulum-triple-rotary](page:overview), with one change: the horizontal arm that the motor turns is no longer rigid. It is a [FlexibleBeam3D](block:Arm) (assumed modes, clamped at the motor hub): a **3 x 50 mm stainless-steel strip on edge**, 0.2159 m long, with the density set so it weighs exactly the rigid arm's 0.257 kg. The pendulum chain, the servo, the swing-up trajectory and the disturbance are the rigid example's.

| model | arm | firmware | result |
| --- | --- | --- | --- |
| `pendulum-triple-rotary` | rigid | `RotaryCtrl` | catches at 5.0 s, recovers from the push |
| `pendulum-triple-rotary-flex` (this model) | flexible | `RotaryCtrl`, unchanged | **fails**: the loop drives the arm's first bending mode unstable near the top of the swing-up (15 V from 2.88 s); it never catches |
| `pendulum-triple-rotary-flex-lowpass` | flexible | `RotaryCtrlLP`: the same weights, a 12 Hz low-pass in the loop | catches at 5.00 s, recovers from the push |
| `pendulum-triple-rotary-flex-free` | flexible | off | free swing (energy, tap test, stiff limit) |

![The rigid firmware on the flexible arm, against the rigid arm|700](assets/b38b5f6cc07d.png)

## In short

- **The arm.** Bending in the horizontal plane (the plane of the motor torque) is soft: 51.3 Hz as a bare cantilever, **42.7 Hz** clamped with the pendulum on its hinge, about 75 Hz in the running rig (the hub is not clamped). Vertical bending (111 Hz) and torsion (418 Hz) are stiff. See [the arm](page:arm).
- **The rigid controller does not survive it.** Its loop gain has no roll-off: on the rigid arm it is still 0.22 at 76 Hz, and the arm's resonance lifts that to 4.3. At the upright the closed loop has a pole at +277 1/s, 65.5 Hz. A notch or a gentler LQR does not help; the gains would need an arm about 23 times stiffer. See [the controller](page:controller).
- **The fix** is roll-off: the LQR and the TVLQR are designed with a second-order 12 Hz low-pass between the feedback and the motor. The swing-up nominal is unchanged. It catches, holds and recovers on the flexible arm, for an arm half as stiff up to a rigid one. See [results](page:results).

## What to try

- Open the **3D View**: the strip bends ([Arm/eta_y[1]](signal:Arm/eta_y[1])) and twists ([Arm/eta_t[1]](signal:Arm/eta_t[1])) with the deformation bindings; the view opens with exaggeration x10.
- Open the **Dashboard**: link angles, tip deflection ([Arm/dB[2]](signal:Arm/dB[2])), modal coordinates and the voltage. Set the arm's Young's modulus to 5e12 Pa (about 26 times the steel) and run again: the rigid firmware now catches.
- Run `pendulum-triple-rotary-flex-lowpass`, the fixed controller, and compare.

The pages: [the arm](page:arm), [the controller](page:controller), [results and checks](page:results).
