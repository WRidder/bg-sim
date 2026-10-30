# Rotary triple inverted pendulum

A Quanser-style **rotary arm** turns about the vertical axis; a chain of 3 pendulum links hangs from the arm tip and swings in the plane **perpendicular to the arm**. A single input drives the arm: the voltage of an SRV02-like DC servo with a 70:1 gearbox, limited to $\pm 15$ V. The arm, the servo and the links are those of the Quanser rotary double inverted pendulum, chained short + short + medium: **this triple is not a Quanser product**, and its amplifier limit is raised from 10 V to 15 V (see [structure](page:structure)).

![The whole run|700](assets/cbe4ebdd456f.png)

## Scenario

1. $t < 1$ s: the chain hangs straight down at rest, the motor voltage is 0 (phase 0). Nothing moves.
2. $t = 1$ s: the swing-up starts (phase 1): a feed-forward trajectory from offline direct collocation, tracked by a discrete time-varying LQR. It takes $T_s = 4$ s; all links are within 3 deg of upright at $t = 3.82$ s.
3. Catch at $t = 5.00$ s: the infinite-horizon LQR takes over (phase 2, latched) and balances all 3 links upright (inside 0.001 deg before the disturbance).
4. $t = 8.5$ s (3.5 s after the catch): a 0.1 N force pulse of 50 ms hits the tip of link 3. The tip link deflects by 3.5 deg (the lower links more, the controller moves them first) and the LQR recovers within 1.3 s (to 0.5 deg).
5. The run ends at $t = 12$ s.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Angles/phi3](signal:Angles/phi3)), "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) and "Controller phase" ([Ctrl/phase](signal:Ctrl/phase)).
- Open the **3D View**: the arm and the links follow [J1/qout](signal:J1/qout), [J2/qout](signal:J2/qout), [J3/qout](signal:J3/qout) and [J4/qout](signal:J4/qout).
- Raise the disturbance amplitude ([DistPulse](block:DistPulse)): on the design model the balance loop recovers pulses up to 0.149 N (50 ms); beyond that the 15 V limit is reached for too long and the chain falls.
- Run `pendulum-triple-rotary-free`: the design check, the plant released from a non-trivial pose with the controller off.

![3D view during the swing-up|600](assets/c3fe233f0773.png)

The pages: [multibond structure](page:structure), [equations of motion](page:equations), [trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control), [results](page:results).
