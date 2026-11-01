# A loose ball in the carton

A 0.6 kg carton shell with a loose 0.5 kg ball (80 mm), on the default trajectory (family 3). The ball is a second rigid body. [Walls](block:Walls) (`library/SphereInBox.jl`, generated) gives it a compliant contact with the six inner walls. Each wall has a Hertz spring with Hunt–Crossley damping and regularised Coulomb friction, unrolled per wall, with no events. The carton is drawn see-through (diffuse alpha 0.35) so the ball shows.

When the gripper accelerates, the carton moves and the ball lags. It rolls to the trailing wall, hits it, and rolls back at the deceleration. Each impact is a short force peak on the carton, which the cups have to carry. The soft bellows also let the carton tilt a little, so the ball keeps rolling and ends against a wall. That is a static shift of the centre of mass, like `offset-com`. For the loose contents `optimize.py` therefore asks a margin of 0.3 (safety factor 1.4) instead of 0.5; `optimize_free.py` shows that 0.5 is reachable too (see Highest pick rate). On this default trajectory the margin is −0.20 (bg-sim −0.21): the most loaded cup briefly goes past its capacity, yet the carton stays on.

![The ball moving in the see-through carton|700](assets/89e23fb8bdd1.png)

![Ball position in the carton, wall force and cup utilisation|900](assets/a03e3c0110ab.png)

![Path of the ball centre in the carton (top view)|500](assets/b51442f0a580.png)
