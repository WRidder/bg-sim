# Double pendulum on a belt-driven cart

A cart on a rail with a finite travel (±0.4 m) carries a double pendulum. A DC motor drives the cart through a gearbox and a belt on a pulley; the 2 pendulum joints are **passive**. The plant is a planar multibond bond graph: a prismatic joint for the cart, revolute joints for the links, one rigid body per link, gravity inside every body. This is the cart version of the pendulum family (fixed pivot, cart, rotary base), built from the same planar elements as `robot-arm-2d` and the cart scenario of `inverted-pendulum-cart`.

![Link angles, cart position and motor voltage over the whole run|900](assets/bc7ea645e6b0.png)

## The scenario

| time | phase ([Ctrl/phase](signal:Ctrl/phase)) | what happens |
| --- | --- | --- |
| 0 to 1 s | 0, hold | everything hangs straight down at rest; the motor voltage is 0 (nothing moves, the pivots start at their static deflection) |
| 1 s | 1, swing-up | the feed-forward trajectory of an offline trajectory optimisation starts, tracked by a time-varying LQR (TVLQR) |
| 3.4 s | 2, balance | after 2.4 s the nominal trajectory ends upright at rest and the 1 kHz discrete LQR takes over |
| 7 s | 2 | a 40 ms force pulse of 0.28 N hits the tip link ([Push](block:Push)) after 3.6 s of stable balance |
| to 12 s | 2 | recovery, then 2.9 s of quiet balance |

The firmware is the pair [Traj](block:Traj) (table lookup) and [Ctrl](block:Ctrl) (1 kHz firmware), and the angles it sees are the joint encoders [Joint1](block:Joint1), [Joint2](block:Joint2). The absolute link angles from the upward vertical are recorded as [Ctrl/th1](signal:Ctrl/th1), [Ctrl/th2](signal:Ctrl/th2); [Rail/qout](signal:Rail/qout) is the cart position and [Ctrl/u](signal:Ctrl/u) the motor voltage.

## The rig (assumed values)

No published data exists for a belt-driven double pendulum rig of this size, so the values are assumed and stated here; the motor and gearbox are in the range of a small 90 W brushed servo.

| part | value | note |
| --- | --- | --- |
| cart | 0.8 kg, $J = 0.0015$ kg m² | carriage with the belt clamp |
| rail | ±0.4 m of travel of the cart centre | the swing-up is optimised inside ±0.3 m |
| link 1 | 0.25 m rod, 0.1 kg, centre of mass 0.125 m, $J = 0.0005208$ kg m² | joint friction 0.0002 N m s/rad |
| link 2 | 0.25 m rod, 0.08 kg, centre of mass 0.125 m, $J = 0.0004167$ kg m² | joint friction 0.0002 N m s/rad |
| motor | 24 V supply limit, $R = 1.5\ \Omega$, $L = 0.5$ mH, $k_t = k_e = 0.0302$ N m/A | rotor $J_m = 1.4e-05$ kg m², bearing loss 2e-06 N m s/rad |
| transmission | gearbox 3:1, pulley radius 16 mm, belt 400000 N/m, 60 N s/m | force per volt $\alpha = 3.77$ N/V, stall force 91 N, rotor inertia reflected to the cart 0.49 kg |

## What to try

- Open the **Plots** tab: the link angles ([Ctrl/th1](signal:Ctrl/th1), [Ctrl/th2](signal:Ctrl/th2)), the cart ([Rail/qout](signal:Rail/qout)) and the voltage ([Ctrl/u](signal:Ctrl/u)) tell the story of the run.
- In the 3D view the cart rides on its rail between the two red end stops and the links swing up; the joints follow `Rail/qout` and `Joint1/qout` to `Joint2/qout`.
- Raise the `amplitude` of [PushPulse](block:PushPulse) (the pulse force) until the balance controller loses the pendulum: the limit is about 0.35 N for a 40 ms pulse in the design model.
- Run `pendulum-double-cart-free`: the same plant with the motor shorted, released from a non-trivial pose; it is the design-model check (see [the results](page:results)).

Continue with [the multibond structure](page:structure), [the equations of motion](page:dynamics), [the trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control) and [the results](page:results).
