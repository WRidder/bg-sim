# A loose bottle in the carton

A 0.6 kg carton shell with a loose 0.5 kg bottle: a cylinder of 70 x 120 mm lying along the carton's length. [Walls](block:Walls) (`library/CylinderInBox.jl`, generated) puts contacts at both end rims of the cylinder. For each wall, the contact point is the rim point deepest towards that wall, so the bottle slides, tips and rolls against the walls. The carton is drawn see-through.

The bottle moves about 11 cm along the carton and 6 cm across, sliding on the floor and hitting the walls. Like the ball, it ends against a wall. On the default trajectory the margin is −0.07 (bg-sim; reduced model −0.11): a cup briefly goes past its capacity, yet the carton stays on.

![The bottle in the see-through carton|700](assets/20fc1d6b8612.png)

![Bottle position in the carton, wall force and cup utilisation|900](assets/d45181a2206a.png)
