# Balance, speed and a push

**Scenario.** The rider stands on the transporter, released **0.03 rad (1.7°)** off upright. The LQR catches it in about a second. From **3 s** the speed set-point ramps to **1.5 m/s** in 1.5 s, so the body leans forward (up to 10.8°) to accelerate, then settles back upright. At **9 s** a **150 N push** lasting 0.15 s on the centre of mass shoves the vehicle; the controller steps forward under it and recovers.

![The model canvas|1000](assets/01c290e4ec4e.png)

The motors ([MotorL](block:MotorL), [MotorR](block:MotorR)) turn the wheels against the body through the axle joints [AxleL](block:AxleL) and [AxleR](block:AxleR); the wheels roll on the ground through [TyreL](block:TyreL) and [TyreR](block:TyreR). [SegwayCtrl](block:Ctrl) reads the pitch and pitch rate from [Sense](block:Sense) and the joint rates from the axles.

![Pitch, speed, wheel torque and the voltage the motors need|900](assets/5ac2c0e1feaa.png)

**Checks.** The bond graph agrees with the independent non-linear Lagrange simulation of `design/design.py` (same controller, RK4) to four digits: the pitch ([Sense/theta](signal:Sense/theta)) and speed ([Ctrl/v](signal:Ctrl/v)) at the times in `expected.json`, the peak torque 42.8 N m per wheel (limit 80) and peak voltage 23 V (bus 72 V). The load on each wheel at rest is the static 564 N ([TyreL/f_n](signal:TyreL/f_n)).

![3D view while accelerating (t = 4.6 s)|500](assets/09010f902ff5.png)

**Dashboard.** The push force and the rider's mass (the gains stay designed for 105 kg, so a different mass shows the margin of the design), the pitch gauge, speed, torque and voltage, and the plots of speed and pitch.

**Try:** raise the push to 400 N; the controller still recovers, with a larger torque. Change the body mass to 70 or 140 kg without re-running `design.py`. Increase the push until the torque limit saturates and the vehicle falls.
