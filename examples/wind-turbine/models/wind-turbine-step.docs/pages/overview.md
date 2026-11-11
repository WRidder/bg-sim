# Wind steps across rated

The wind steps every 60 s: 10, 12, 14, 18, 14, 12 and 10 m/s. See [the turbine](project:turbine) and [the controller](project:controller).

![The step responses|900](assets/f6a3c4658bcb.png)

## What you see

- At 10 m/s the turbine is in region 2. The step to 12 m/s takes it to rated: [Torque/region](signal:Torque/region) switches to 3 and the pitch starts to act.
- Each step up overspeeds the rotor ([RotorRPM/y](signal:RotorRPM/y)) for a few seconds until the pitch PI has caught up. The power follows the speed, because the torque law holds constant power, not constant torque.
- The thrust step sets the tower swinging at 0.32 Hz ([TowerSpring/q](signal:TowerSpring/q)). The aerodynamic damping stops it within a few cycles.

## What to try

- Lower the PI gain `kp` on the dashboard and compare the overspeed after the step to 18 m/s.
- Move `v_low` below 8 m/s to see region 2 and region 1½.

![The model canvas|900](assets/45010aceca2f.png)
