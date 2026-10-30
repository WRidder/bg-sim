# Planar reaction-wheel balancer (gravity on)

An inverted planar body on a compliant pivot with a reaction wheel on its axis. A 1 ms PD controller on the body angle commands the wheel torque, and the wheel's reaction holds the body upright while the wheel spins up. This is the planar-balancer half of X-MB2 (plan 9.10) and Gate B's arm-and-balancer pair with `robot-arm-2d`. The body starts 0.01 rad off upright, the controller recovers it in about 0.5 s, then a 0.012 rad reference pulse (0.5 s to 1.5 s) tilts it and it returns. The sibling model `balancer-free` has gravity off.

![The model canvas|900](assets/434b4a799915.png)

```
Ground -- Pivot -- LinkB -- BodyJ -+- Body  (RigidBody2D, m 1.5, J 0.02, CoM 0.3 m)
         (kt, bt)  (0.3 m) (1-junc) '- WheelJ -- Wheel (RigidBody2D, J 0.002)
                          (rx = 0.2)   (kt, bt)   (its centre on the axis)
       Motor: MSe(tau) --------> WheelJ.drive
       Ref (Pulse 0.012 rad, 0.5-1.5 s) -> Balancer (1 ms) -> tau
```

## What to try

- Open **Plots**: "Body angle and reference", "Wheel speed", "Motor torque and momentum". The wheel spins up to 47 rad/s and keeps 46.2 rad/s at the end: gravity has delivered a net angular impulse that the wheel must store, the momentum-management story a real reaction wheel has to unload.
- Set `Ctrl/tau_max` to 0.05 N·m: the initial tilt already needs $G\sin(0.01) + K_p\cdot0.01 = 0.224$ N·m, so the motor cannot arrest it and the body falls (the 0.02 rad band check would fail).
- Set `Pivot/bt` and `WheelJ/bt` to 0 and rerun: the 1 ms sampled drive pumps the 3.6 kHz pivot mode and the run stops with E901 (MaxIters) at $t = 2.29$ s; the damper is part of the model.

## 3D view

`scenes/reaction-wheel-2d.sdf` draws the body bar on its pivot with the wheel at its top in the vertical X-Z plane. Joint `pivot` follows [Pivot/qout](signal:Pivot/qout) and `wheel_axis` follows [WheelJ/qout](signal:WheelJ/qout); the spoke makes the wheel spin visible.

![3D view at t = 1.0 s|500](assets/6be58514f045.png)

Continue with [the physics](page:physics), [the controller](page:controller) and [the results](page:results).
