# Knock-down and recovery (C3)

**Scenario.** Hanging at rest with 0 V until **1 s**, the state-driven swing-up and catch, then a **1.5 N,
100 ms** knock-down push on the tip ([PushPulse](block:PushPulse)) at **7 s**, end **20 s**.

**Controller.** [Ctrl](block:Ctrl) is the robust firmware `library/DoubleCartLabRobustCtrl.jl` with
`rearm = 1`: the C3 state machine around the C1 balance and the C2 swing-up tables of [Traj](block:Traj). Its
phase output tells what it does:

| time | phase | what happens |
| --- | --- | --- |
| 0 to 1 s | 0 hold | 0 V |
| 1.0 s | 3 settle | the links already hang at rest |
| 1.05 s | 1 swing-up | 50 ms at the hanging rest arm the TVLQR swing-up |
| 3.75 s | 2 balance | region catch ($z^T P z <$ tol) |
| 7.0 s | 2 | the 1.5 N, 100 ms knock-down |
| 7.10 s | 3 settle | a link passes 20°: the drop; the energy (peak 5.2 J) is removed through the cart, the rail guard brakes, the hanging LQR settles |
| 9.88 s | 1 swing-up | re-armed at the hanging rest, the plan shifted to the cart position and the turn count |
| 12.58 s | 2 balance | re-caught; upright until the end |

See [robust classical control](project:robust) for the design.

**Dashboard.** The phase (colour by phase: settle in red), the peak cart travel (yellow above 0.8 m), the link
angles in degrees, voltage and current; the fourth plot shows the phase, the links' energy and the push.
Sliders: the knock-down push and its time. **3D view:** the links fall, the cart brakes and swings them down,
they come to rest and swing up again.

![Link angles, cart, voltage, phase and energy over the run|900](assets/5f090f16c073.png)

**Expected outcome:** one drop and one recovery (`Ctrl/drops` = 1), upright within 0.2° over the last 2 s, a
peak travel of **0.767 m** after the knock-down, inside the robustness test's 0.95 m, and |V| ≤ 24 V. The
timed nominal firmware recovers none of the 64 knock-downs of the robustness test; this firmware recovers all 64.
A Python replica on the twin switches phase at the same ticks (within 1 ms) and agrees to 6e-3 m and 1.6e-2 rad
over the 20 s, through both swing-ups.
