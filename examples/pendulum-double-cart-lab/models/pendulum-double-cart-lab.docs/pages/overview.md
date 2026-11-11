# Swing-up, balance and a push (nominal firmware)

**Scenario.** The links hang at rest with 0 V until **1 s**. Then the planned swing-up runs for 3.0 s, the LQR
catches the pendulum at **4.0 s** and balances it, a **0.45 N, 40 ms** push on the tip
([PushPulse](block:PushPulse)) hits at **7.5 s**, and the run ends at **12.5 s** after 3 s of quiet balance.

**Controller.** [Ctrl](block:Ctrl) is the nominal 1 kHz firmware `library/DoubleCartLabCtrl.jl`: phase 0
hold, phase 1 the swing-up (feed-forward plus time-varying LQR from the tables of [Traj](block:Traj),
`library/DoubleCartLabTraj.jl`), phase 2 the discrete LQR. It sees the ideal joint and cart states, with no
delay. The design is on the project page [design and margins](project:design).

![The model canvas: the bond graph, the firmware and the dashboard monitor|900](assets/1f27c86e276a.png)

**Dashboard.** The phase, the peak cart travel, both link angles from upright in degrees (green within 2°),
voltage and current; plots of the angles, the cart with the end stops (±1.0 m) and the test limit (±0.95 m),
voltage and current, and the phase with the tip push. The sliders set the push, its time and the mass of link 2
for the next run. [Mon](block:Mon) (`DoubleCartLabMonitor`) computes the degrees and the peak travel. **3D
view:** the cart on the 2 m rail between the red rubber stops; the green posts mark the ±0.8 m plan.

![Link angles, cart, voltage, current and phase over the run|900](assets/78e79d820565.png)

**Expected outcome** (checked by `expected.json`):

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| at rest before 1 s | no motion, 0 V | |
| upright for good (inside 2°) / catch | 2.55 s after the start / 4.00 s | 2.55 s / 4.00 s |
| upright band before the push | 0.0023° (cart 0.04 mm) | 0.0017° |
| push: link 1 / link 2, cart | 10.71° / 3.98°, 0.173 m | 10.70° / 3.98° |
| back inside 0.5° after the push | 2.12 s | 2.12 s |
| peak voltage, current, travel | **15.01 V** (plan bound 16.8 V), 5.97 A, **0.387 m** (plan ±0.8 m) | 15.02 V, 5.98 A, 0.387 m |

The end stops are never touched. Raise the push above about 0.9 N to see the limit of the design (see
[-balance](model:pendulum-double-cart-lab-balance)). The rig itself: [the double-cart lab rig](project:rig).
