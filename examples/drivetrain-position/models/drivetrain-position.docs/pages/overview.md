# Load-position servo on a compliant drivetrain

A DC motor drives a load wheel through a 10:1 gear and a **soft shaft** (1.2 N·m/rad, 40 times softer than the shaft of `drivetrain-kalman`). The task is a **position step of the load wheel**: 1 rad at 0.2 s, then a 0.2 N·m load torque at 2.2 s, with a 24 V motor supply.

The shaft and the load wheel form a torsional mode at **3.9 Hz with damping 0.034**. A position loop that is fast enough to be useful has to cross over right there, so the loop cannot ignore the mode. This model shows how a controller that knows about it behaves. The model `naive` runs the same plant with a textbook PID tuned for a rigid drivetrain: it overshoots by 104 % and rings at the mode for seconds.

![The model canvas|900](assets/1c3061cfee6d.png)

The plant is a **pure bond graph**: the voltage source [V](block:V) on the electrical 1-junction [Elec](block:Elec) with [R](block:R) and [IL](block:IL), the gyrator [GY](block:GY) into the motor junction [MotorJ](block:MotorJ) with [IJm](block:IJm) and [Rd](block:Rd), the gear [TFa](block:TFa) and [TFb](block:TFb), [WheelJ1](block:WheelJ1) with [IW1](block:IW1), the 0-junction [S1](block:S1) with the shaft 1-junction [Shaft](block:Shaft) (compliance [C](block:C), damper [D](block:D)), and [WheelJ2](block:WheelJ2) with [IW2](block:IW2) and the load source [Load](block:Load). The firmware is [Ctrl](block:Ctrl).

## What to try

- **Plots**, "Load position": [ThetaL/y](signal:ThetaL/y) follows the smooth trajectory [Ctrl/r_traj](signal:Ctrl/r_traj) and settles without ringing.
- Plot [C/q](signal:C/q): the shaft twists by up to 0.33 rad during the move and the twist returns to its resting value without ringing.
- Plot [V/p.e](signal:V/p.e): the voltage stays below 14 V, far below the 24 V limit.
- Open the model `naive` and compare the same plots.
- Shorten `Ttraj` of [Ctrl](block:Ctrl) (it is a plain parameter) and watch the shaft twist and the voltage: a faster trajectory has more energy at the mode and the feedback has to work harder.

## 3D view

`scenes/drivetrain-position.sdf` shows the motor, the gearbox, wheel 1, a thin 0.705 m shaft from the face of wheel 1 to the face of wheel 2, and wheel 2. Wheel 1 turns by $0.1\,$[Theta/y](signal:Theta/y), wheel 2 by [ThetaL/y](signal:ThetaL/y). The shaft belongs to wheel 1, so it turns with it, and twists towards wheel 2 through a torsion deformation binding with the **linear** basis, $\theta(s) = (s/L)\,$[C/q](signal:C/q): the lumped spring's twist is linear along the shaft, so its far end sits at the wheel-2 angle. The twist is up to 0.33 rad in the move and 0.17 rad under the load; the wheel markers show it at true scale, but on the shaft it only shows as the stripes winding round it, by radius × angle (1.4 mm for 0.17 rad), so the view opens with the deformation drawn **×10** (`scene.exaggeration`).

![3D view at t = 1.5 s, the load wheel 1 rad ahead of the start|500](assets/0c6b27d6634f.png)

Continue with [the structure](page:structure), [the equations](page:equations), [the controller](page:controller) and [the results](page:results).
