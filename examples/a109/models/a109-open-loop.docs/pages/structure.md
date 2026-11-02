# Structure

## Rigid body and components

The report's mass is 5401 lb (2450 kg), with $I_x = 1300$, $I_y = 6760$, $I_z = 6407$ and $I_{xz} = 800$ slug ft². The product of inertia tilts the principal axes by 10.49 deg about the body y axis, so the `RigidBody3D` sits on them.

Each component's force is a modulated source: an `ExternalWrenchSpatial` bonded through its own `FixedTransform3DNeutral` at the component's point (hub, fuselage, tail-rotor hub, tailplane, fin). The bond graph therefore forms $r \times F$. The component blocks compute the report's equations in SI:

* `MainRotor`: first-order tip-path-plane flapping and the thrust/inflow balance, eight unrolled Newton steps. It also applies the A109 revisions:
  * decoupled flapping;
  * the low-speed magnification of the dihedral effect below 30 kt.
* `Fuselage`: the drag areas, with the downwash centre of pressure magnified 3x.
* `TailRotor`: the tail rotor's thrust and inflow.
* `Tailplane` and `Fin`: the wake edge on the tailplane, the downwash factor, and stall at $|w_a| > 0.3|u|$.

## Drivetrain (ours)

The report holds the rotor speed constant. Here the rotor speed is a bond-graph degree of freedom:

* **Rotor 1-junction.** The rotor inertia $J$ = 1265 kg m², the aerodynamic torque $Q = P/\Omega$ of the report's power method (`RotorPower`) as a modulated effort source, and a flow sensor.
* **Mast 0-junction.** `ShaftAxis` couples the mast to the airframe's spatial port. The rotor's absolute speed is $\Omega_{rel} + k \cdot \omega$, and the mast torque acts back on the airframe.
* **Gearbox 1-junction.** The engine source driven by the `Governor` (a PI, $\omega_n$ = 2.5 rad/s, $\zeta$ = 0.8, at most 740 shp), the 90 hp transmission loss, and a TF ($n$ = 5.40) to the tail-rotor junction with the tail-rotor torque.

The global `rpm_mode` sets the speed the rotor aerodynamics see: the drivetrain's (1) or the nominal 385 rpm (0, the report's model).

Flapping, inflow and air data are signal blocks: the report's flapping is a first-order lag without blade inertia, so it stores no energy.
