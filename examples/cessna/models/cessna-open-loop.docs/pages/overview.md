# Cessna 172 open loop

A Cessna 172P built from the data of JSBSim's c172p, released on each of its five rigid-body modes. Five copies of the aircraft are trimmed in level flight at 100 KTAS and 5000 ft. Each starts displaced along the eigenvector of one mode of the linearised aircraft: the short period (1 deg of alpha), the phugoid (2 m/s of speed), the dutch roll (1 deg of sideslip), the roll mode (2 deg of bank) and the spiral (5 deg of bank).

![The model canvas|900](assets/0be5e93d16c1.png)

| block | role |
| --- | --- |
| [SP](block:SP), [Ph](block:Ph), [DR](block:DR), [Ro](block:Ro), [Sl](block:Sl) | one aircraft each (a subsystem): the airframe, the engine and propeller, the aerodynamics and the controls held at the trim |
| [RateRo](block:RateRo), [RateSl](block:RateSl) | $\lambda = \dot\phi/\phi$ of the bank angle: on a real mode this is its eigenvalue |

## What to try

1. Press **Run**. The short period dies out in about a second. The phugoid trades speed for height with a 25 s period. The dutch roll rings for about 10 s.
2. Plot [RateRo/lambda](signal:RateRo/lambda). It reads the roll-mode eigenvalue, $-5.57$ 1/s, while the bank decays.
3. The spiral is stable but slow: half the bank is gone after about 65 s.

## 3D view

The five aircraft fly side by side over a striped reference floor. The ailerons, elevator, rudder and flaps are separate meshes on their hinge lines, and the propeller turns at the engine's speed. Picture at 4 s:

![3D view at t = 4 s|600](assets/eb38053ca3dc.png)

Continue with [the aircraft](page:aircraft) and [the results](page:results).
