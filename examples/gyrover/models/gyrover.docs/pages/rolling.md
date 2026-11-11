# The rolling contact

**Choice.** The wheel touches the floor through a **compliant contact with regularised Coulomb friction** (`RollingDisk`), not through a rolling constraint. Reasons:

- a rolling constraint is nonholonomic: it cannot be written as a bond-graph element on the wheel's spatial port without a constraint solver, and a stiff penalty is the bond-graph way (as `ContactPoint` does for a point);
- the compliant contact keeps everything an ODE, so the same model exports to C and an FMU;
- it shows the losses that an ideal constraint hides: side slip, rolling losses and lift-off would appear if the robot overloaded the tyre.

**Geometry.** The contact point is not fixed in the wheel: at every instant it is the lowest point of the rim, $u = -(n - (n\cdot a)a)/\lVert\cdot\rVert$, $r = R\,u$, with $a$ the axle and $n$ the floor normal. The normal force is a smooth Hertz/Hunt-Crossley law ($k = 10^6$ N/m at 1 mm, $c = 2$ s/m); the friction acts on the slip $s$ of the rim material point, $F_t = -\mu f_n\, s/\sqrt{s^2 + v_s^2}$ with $\mu = 0.9$ and $v_s = 1$ mm/s.

**Slip, quantified.** A rolling wheel under a side force $F$ creeps at $s \approx v_s F/(\mu f_n)$. In the showcase:

| quantity | measured | checked |
| --- | --- | --- |
| lateral slip | at most 0.043 mm/s | below 0.1 mm/s |
| longitudinal slip | at most 0.076 mm/s | below 0.2 mm/s |
| use of the friction cone $\lvert f_{lat}\rvert/f_n$ | at most 3.8 % | |
| normal force | 62.0 to 79.1 N (weight 68.8 N) | above 50 N (no lift-off) |
| penetration | at most 0.185 mm | below 0.25 mm |
| contact loss over the 30 s mission | 2.7 mJ (motor work 5.5 J) | |

So the wheel rolls: the creep is five orders of magnitude below the speed, and the bond graph follows the exact-rolling reference to 0.27 mm over the 33 m loop. The one systematic difference is the rolling radius, smaller by the static penetration (0.18 mm).

![Slip and contact forces in the mission|1000](assets/b274aa91f4b4.png)

Where the model departs from exact rolling: when the uncontrolled robot (model `free`) nutates after about 3 s, the tyre side-slips (up to 0.05 m/s) and the contact dissipates 1.18 J by 6 s; the reference model cannot show this.
