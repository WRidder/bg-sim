# Rotary double inverted pendulum

A Quanser-style **rotary arm** turns about the vertical axis; a chain of 2 pendulum links hangs from the arm tip and swings in the plane **perpendicular to the arm**. A single input drives the arm: the voltage of an SRV02-like DC servo with a 70:1 gearbox, limited to $\pm 10$ V. The arm, the two links and the SRV02 servo follow the Quanser rotary double inverted pendulum (product page and SRV02 manual, see *Parameters*).

![The whole run|700](assets/df720dd64335.png)

## Scenario

1. $t < 1$ s: the chain hangs straight down at rest, the motor voltage is 0 (phase 0). Nothing moves.
2. $t = 1$ s: the swing-up starts (phase 1): a feed-forward trajectory from offline direct collocation, tracked by a time-varying LQR. It takes $T_s = 4$ s.
3. Catch at $t = 5.02$ s: the infinite-horizon LQR takes over (phase 2, latched) and balances all 2 links upright.
4. $t = 8.5$ s (3.5 s after the catch): a 0.35 N force pulse of 50 ms hits the tip of link 2. The tip link deflects by 7.2 deg and the LQR recovers within 1.9 s (to 0.5 deg).
5. The run ends at $t = 12$ s.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Angles/phi2](signal:Angles/phi2)), "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) and "Controller phase" ([Ctrl/phase](signal:Ctrl/phase)).
- Open the **3D View**: the arm and the links follow [J1/qout](signal:J1/qout) and [J2/qout](signal:J2/qout).
- Raise the disturbance amplitude ([DistPulse](block:DistPulse)): the chain is caught up to a limit and falls beyond it, because the 10 V limit of the amplifier is reached.

![3D view during the swing-up|600](assets/3087652b0c56.png)

The pages: [multibond structure](page:structure), [equations of motion](page:equations), [trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control), [results](page:results).
