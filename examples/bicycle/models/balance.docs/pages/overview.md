# Balancing the bicycle at low speed

At **3 m/s** the benchmark bicycle is too slow to balance itself: the weave grows by a factor of e every 0.6 s. Here a **steer torque** keeps it up, as a rider's hands would, and a **lean set-point** turns it.

![The 3D view at 7 s: a steady right turn at 0.1 rad lean|800](assets/a0e4ea4a8eb4.png)

The plant is the 3D bond graph of [whipple](model:whipple) with an `MSe` on the steer joint ([SteerMotor](block:SteerMotor)). The run starts with a sideways push (lean rate 0.3 rad/s); at 2 s the lean set-point steps to 0.1 rad to the right ([LeanRef](block:LeanRef), global `lean_ref`).

![Lean, steer angle and steer torque|900](assets/8ecc87a41a71.png)

The push is caught within a second. For the right turn, the controller first steers **left** (counter-steering): the wheels run out to the left, the bicycle falls to the right, and then the handlebar follows into the turn. In the steady turn the rider holds the handlebar with a small torque *against* the turn (−0.55 N m).

![Path of the rear hub: a right turn of 9 m radius|500](assets/1789dc4c838c.png)

## Run it

Press **Run** (10 s, about 15 s of solving). The dashboard sets the lean set-point (global `lean_ref`, negative for a left turn) and the push `phid0`.

Pages: [controller](page:controller).
