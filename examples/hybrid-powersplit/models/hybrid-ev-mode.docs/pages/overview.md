# EV launch

MG2 alone pulls the Prius away from rest. A step of the tractive force demand at 0.5 s asks for
150 N·m at the ring. The energy manager is replaced by constants (engine off, speed reference 0),
so MG1 holds the engine at rest through the sun gear while the sun turns backwards.

![Diagram of the plant: engine and damper, planetary subsystem, MG1 and MG2 with their inverters, driveline, vehicle and battery|1000](assets/2128a77e6503.png)

Plant blocks: [EngineTorque](block:EngineTorque) and [EngineDrag](block:EngineDrag) on the
engine inertia; [Damper](block:Damper) onto the carrier; [Planetary](block:Planetary); MG1
([Inv1](block:Inv1), [Rs1](block:Rs1), [Ls1](block:Ls1), [MG1](block:MG1)) on the [Sun](block:Sun);
MG2 ([Inv2](block:Inv2), [Rs2](block:Rs2), [Ls2](block:Ls2), [MG2](block:MG2)) on the
[Ring](block:Ring) with the [SpinLoss](block:SpinLoss); [FinalDrive](block:FinalDrive), the half
shafts ([ShaftK](block:ShaftK), [ShaftD](block:ShaftD)), [Brakes](block:Brakes),
[Tyre](block:Tyre) and the [VehicleMass](block:VehicleMass) with [Aero](block:Aero),
[Rolling](block:Rolling) and [Grade](block:Grade); the [Battery](block:Battery), [DCLink](block:DCLink)
and [Aux](block:Aux) on the DC bus. The controller is [HCU](block:HCU) (`PowerSplitControl`).

## What it shows

- **Launch time**: [VehicleSpeed/y](signal:VehicleSpeed/y) reaches 30 km/h at 6.86 s. A rigid
  1-DOF ODE with the same losses gives 6.855 s (the closed form without losses gives 6.730 s).
- **MG1 holds the engine**: [EngineSpeed/y](signal:EngineSpeed/y) stays within 3.5 rad/s of rest,
  and [SunSpeed/y](signal:SunSpeed/y) = −2.6 × [RingSpeed/y](signal:RingSpeed/y).
- **Battery limit**: above about 30 km/h, MG2's electrical power ($T\omega + R_s T^2/k^2$) reaches
  the 21 kW battery rating. The HCU then lowers the torque, so [PBat/y](signal:PBat/y) stays at
  the rating.

![Speed, shaft speeds and battery power|900](assets/a167475e7c94.png)

## What to try

- Raise the mass or the grade on the dashboard. At 10 % grade the launch is about three times
  slower.
- Plot [HCU/T_m](signal:HCU/T_m) (MG2 torque) and [HCU/T_g](signal:HCU/T_g) (the small MG1
  torque that holds the engine).
