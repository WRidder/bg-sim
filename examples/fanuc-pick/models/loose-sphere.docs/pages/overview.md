# A loose ball in the carton

A 0.6 kg carton shell with a loose 0.5 kg ball (80 mm), on the default trajectory (family 3). The ball is a second rigid body. [Walls](block:Walls) (`library/SphereInBox.jl`, generated) gives it a compliant contact with the six inner walls. Each wall has a Hertz spring with Hunt–Crossley damping and regularised Coulomb friction, unrolled per wall, with no events. The carton is drawn see-through (diffuse alpha 0.35) so the ball shows.

When the gripper accelerates, the carton moves and the ball lags. It rolls to the trailing wall, hits it, and rolls back at the deceleration. Each impact is a short force peak on the carton (up to 150 N), which the cups have to carry. The soft bellows also let the carton tilt a little, so the ball keeps rolling and ends against a wall. That is a static shift of the centre of mass, like `offset-com`. Even at a crawl, the most loaded cup reaches U ≈ 0.6, so for the loose contents the optimiser asks a margin of 0.3 (safety factor 1.4) instead of 0.5. On this default trajectory the margin is 0.09: it holds, without reserve.

![The ball moving in the see-through carton|700](assets/27902466199d.png)

![Ball position in the carton, wall force and cup utilisation|900](assets/b8087f299ed2.png)

![Path of the ball centre in the carton (top view)|500](assets/cb0f3b19a6dc.png)
