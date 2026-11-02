# Landing gear

Each leg (nose, left, right) is a `GearContact`: a power-conserving modulated transformer between the airframe's multibond and three translational bonds, one per contact direction.

| direction | flow | elements on its 1-junction |
| --- | --- | --- |
| runway normal | the penetration rate of the contact point | `StrutSpring` (C) and `StrutDamper` (R): c172p's strut coefficients, with a smooth unloading |
| along the wheel | the rolling speed | `WheelFriction` (R): the rolling resistance plus the toe brake (main wheels) |
| across the wheel | the side-slip speed | `WheelSide` (R): the cornering force from JSBSim's magic formula of the slip angle |

The nose wheel's rolling direction is turned by the steering angle, 10 deg at full pedal. The transformer keeps

$$p.e \cdot p.f + n.e\, n.f + x.e\, x.f + y.e\, y.f = 0$$

so the gear only exchanges energy with its elements: the springs store it, the dampers, the tyres and the brakes dissipate it.

At rest the CG sits 1.2546 m above the runway, with the nose-up attitude of the tricycle gear. The model's start globals hold this equilibrium, computed by `design/perf.py` (`ground_state`).
