# Checks and limits

`uv run examples/run_checks.py --only excavator` runs every model and checks `expected.json` (50 checks):

| check | bond graph | reference (design.py) |
| --- | --- | --- |
| bucket tip at 6.5 s / 12.5 s (kinematics) | (7.38335, 2.77970) / (2.97815, −1.87711) m | scipy FK from the cylinder lengths, agreement < 4·10⁻⁷ m |
| static boom cylinder force, 1.5 t payload | 274.4 kN | 275.2 kN (moment balance) |
| static arm / bucket cylinder force | 10.6 / 81.0 kN | 10.4 / 81.1 kN (within the Coulomb band) |
| boom hydraulic mode | 2.483 Hz (FFT) | 2.489 Hz (3-DOF eig); 1-DOF formula 2.596 Hz |
| LS margin stand-by / in the lift / in the dig cycle | 27.0 / 26.2 / 22.6–27.0 bar | 25 bar + 2 bar regulation |
| boom section flow, joystick 0.5 | 145 l/min | 150 l/min |
| relief flow in the dig cycle | < 2·10⁻⁹ m³/s | closed |
| bucket fill after the curl / after the dump | 0.75 / 0.004 | > 0.6 / < 0.05 |
| engine energy of the cycle, LS / constant pressure | 0.57 / 1.52 MJ | < 0.7 / > 1.2 MJ |
| port-power ledger | closes (Tellegen) | |

Every model also checks for no causality warnings (no derivative causality, no algebraic loop), no solver
failure and the 3D bindings.

**Solver.** FBDF, reltol = abstol = 10⁻⁶ for the hydraulic models (10⁻⁸ / 10⁻⁹ for the kinematics), 100 output
points per second. Run times on a desktop PC (warm / first run including compilation): kinematics 1.6 / 15 s,
lift 4.8 / 9 s, dig cycle 4.5 / 30 s, no-LS about 23 s first run.

**Simplifications.**

- The cylinder drives its joint through a virtual-work transformer (MTF with r = dL/dq): the joint torque and the
  motion are exact, the pin reaction forces are not modelled.
- The rocker and the H-link are massless; the soil in the bucket has weight but no inertia.
- In the lift model the payload is folded into the bucket body.
- The boom lowers on its meter-out edge: the speed depends on the load (no regeneration, no load-holding valve).
- The shuttle network is a set of check valves into one LS line with a bleed; the pump regulator is static
  (no regulator dynamics).
- The pump's friction torque grows with the pressure even at zero stroke (stdlib pump law): this is why the
  constant-pressure supply idles at about 25 kW.
- The swing is fixed and the ground is flat. In the kinematics model the tip passes below the soil surface (no
  soil there).
- "Cylinder work / engine energy" is the net cylinder work (lifting minus lowering) over the engine shaft energy.
