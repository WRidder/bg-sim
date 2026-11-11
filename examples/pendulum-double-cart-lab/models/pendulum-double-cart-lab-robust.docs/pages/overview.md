# Robust classical firmware, timed scenario

**Scenario.** The nominal model's: hanging at rest with 0 V until **1 s**, the swing-up, the timed catch at
**4.0 s**, a **0.45 N, 40 ms** tip push ([PushPulse](block:PushPulse)) at **7.5 s**, end **12.5 s**.

**Controller.** [Ctrl](block:Ctrl) is the robust firmware `library/DoubleCartLabRobustCtrl.jl` with
`rearm = 0` (timed): the C1 multi-model LQR balance $u = -K\,[\hat x;\ u_{k-1};\ u_{k-2}]$ on an observer (the
steady-state EKF gain on the encoder angles and the cart), and the rig's **2 ms loop delay inside the block**
(the output is the command of two ticks ago). [Traj](block:Traj) (`DoubleCartLabRobustTraj.jl`) holds the C2
multi-model TVLQR tables, read at the plan time `tau` that the firmware publishes. See
[robust classical control](project:robust).

**Dashboard.** The phase (0 hold, 1 swing-up, 2 balance), the peak cart travel, the link angles in degrees,
voltage and current; the fourth plot shows the phase, the links' energy (0 hanging, about 3.3 J upright) and
the push. Sliders: the push, its time and the mass of link 2. **3D view:** as the nominal model.

![Link angles, cart, voltage and phase over the run|900](assets/a5f06908f1dd.png)

**Expected outcome:**

| quantity | robust firmware | nominal firmware (no delay) |
| --- | --- | --- |
| phases | 0 until 1 s, 1 from 1 s, 2 from 4.0 s | the same |
| before the push | within 0.2° (0.005°) | 0.002° |
| push: link 1 / link 2, cart | **12.9°** / 4.9°, 0.208 m | 10.7° / 4.0°, 0.173 m |
| last second | within 0.2° | within 0.2° |
| peak voltage, travel | 15.0 V, 0.387 m | 15.0 V, 0.387 m |

The multi-model LQR is softer (lower gains, more deflection and travel for the push), which buys its margins:
a 32-sample delay margin against 6 and half the voltage noise on the realistic plant. A Python replica on the
twin (`design/robustmodels.py --replica`) agrees to 3e-4 m and 7e-4 rad.
