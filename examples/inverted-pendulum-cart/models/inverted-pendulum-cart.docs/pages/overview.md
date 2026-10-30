# Cart-pole with an LQR balance controller

The classic cart-pole stabiliser (plan 9.6c). A cart on a rail balances a rod with a point mass at its tip. The run starts with the rod tilted by 0.1 rad, the controller catches it, and at $t = 1.5$ s the cart is asked to move 0.2 m. The continuous plant is a **pure bond graph** (D28); the controller is a linear-quadratic state feedback sampled at 1 ms, whose gains come from `design/design.py`.

![The model canvas|900](assets/8cac58967cad.png)

## Run it

- Press **Run** and open the **Plots** tab: "Pendulum angle" ([ThetaInt/y](signal:ThetaInt/y)) shows the 0.1 rad recovery and the swing caused by the step, "Cart position" overlays [XInt/y](signal:XInt/y) and [XRef/y](signal:XRef/y), "Controller force" shows [MSe1/p.e](signal:MSe1/p.e), which peaks at 17.9 N, inside the 20 N limit.
- Change `LQR1.K_x` (or any `K_*`) and run again: the recovery becomes slower and the cart error grows.
- Raise the initial tilt (the start `x` of [ThetaInt](block:ThetaInt) to 0.2 rad): the force then hits the 20 N clamp exactly and the cart still settles at 0.2 m.

## 3D view

`scenes/inverted-pendulum-cart.sdf` shows the cart on its rail and the rod with the tip mass. Joint `rail` follows [XInt/y](signal:XInt/y) and joint `hinge` follows [ThetaInt/y](signal:ThetaInt/y) (positive towards +X). The picture is taken at 1.7 s, just after the cart reference step.

![3D view at t = 1.7 s|500](assets/200810c96d06.png)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
