# The flyable Beaver

The FDC Beaver with the bond-graph drivetrain on, cockpit controls and the FDC autopilot. Its inputs and outputs are export markers, so it exports as an FMU for a flight-simulator host.

![The model canvas|900](assets/244e9c496a0f.png)

| block | role |
| --- | --- |
| [Beaver](block:Beaver) | the airframe subsystem, with wind inputs |
| [Controls](block:Controls) | the cockpit: column, pedals, flaps, elevator trim, manifold pressure, rpm lever; travel limits |
| [PitchAP](block:PitchAP) | the pitch attitude hold (PAH) and the altitude hold (ALH) |
| [RollAP](block:RollAP) | the roll attitude hold (RAH), the heading hold (HH) and the turn coordinator |
| [ElevServo](block:ElevServo), [AilServo](block:AilServo), [RudServo](block:RudServo) | the autopilot servos: a 0.09 s lag with the airspeed-dependent gain of FDC's actuator and cable models |
| `col_pitch` ... `wind_d` | the FMU inputs (`ExportInputPass`): they pass the demo stimulus through in BG-Sim |

## The demo

1. At 5 s: climb power (25 inch Hg, 2000 rpm), and the attitude hold 4° up.
2. At 30 s: the heading hold turns the aircraft to 090 at the 30° bank limit.
3. At 70 s: the altitude hold captures 150 m above the start.
4. At 85 s: the power goes back to the trim setting.

![The demo|900](assets/b041b2e42bf5.png)

## What to try

- Move the climb, heading and altitude sliders.
- Set the pitch or roll autopilot to 0 and fly the column pulses by hand.
- Switch the **drivetrain** off: the rpm then follows the lever exactly, as in the source.

The elevator, ailerons, flaps and rudder move in the 3D view, and the propeller turns at 1/20 of the shaft speed.

![3D view at t = 45 s, in the turn|600](assets/43d963eb7e59.png)
