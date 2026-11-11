# Race car: drop test

The electric race car of the **cars** example, released 3 cm above its static ride height onto flat ground. Heave and pitch ring down on the springs, the asymmetric dampers and the tyres, and the four tyre loads settle on the static corner loads.

![The model canvas|900](assets/81c4ad97e1d1.png)

The canvas is the whole vehicle: the chassis [Chassis](block:Chassis) on its pose integrator, the four corner subsystems [FL](block:FL), [FR](block:FR), [RL](block:RL), [RR](block:RR) (suspension slider, strut, carrier, wheel spin, [Tyre](block:FL/Tyre), brake), the steering, the brake system, the aero wrench and the electric driveline from the [Battery](block:Battery) through the motor [MachineR](block:MachineR) to the rear differential.

![3D view at t = 1 s|600](assets/60ff7f4709ec.png)

Continue with [the results](page:results).
