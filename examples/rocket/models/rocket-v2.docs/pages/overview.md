# V-2, vertical shot

The V-2 (A4) launched straight up, as in the post-war sounding flights:

* 12,500 kg at launch, 8,720 kg of propellant, 123 kg/s for 65 s;
* 25 t of thrust at sea level, rising to 29 t in vacuum as the ambient pressure falls (the nozzle's exit area is 0.39 m²);
* U.S. Standard Atmosphere 1976, drag with a Mach table, inverse-square gravity.

![The model canvas|900](assets/8c9cdffcd693.png)

| block | role |
| --- | --- |
| [Free](block:Free), [Body](block:Body), [Inertia](block:Inertia), [Out1](block:Out1)..[Out6](block:Out6) | the variable-mass rigid body (see [variable mass on a bond graph](project:variable-mass)) |
| [Seq](block:Seq) | `FlightSequence`: one burn of 65 s, then a 0.33 s thrust decay |
| [Engine](block:Engine) | thrust with the ambient-pressure term |
| [Atm](block:Atm), [Gravity](block:Gravity), [Drag](block:Drag) | atmosphere, gravity, drag |
| [Air](block:Air), [Status](block:Status) | altitude, speed, Mach; sensed acceleration, ideal velocity gain |

## What to try

1. Press **Run**. The V-2 goes supersonic at 26 s, passes maximum dynamic pressure (65 kPa) at 41 s and burns out at 33 km and 1,422 m/s. It coasts to 142 km at 217 s.
2. Set drag, gravity and atmosphere to 0. The speed now follows the ideal velocity gain $c \ln(m_0/m)$ exactly.
3. Shorten the burn or add launch mass, and watch the apogee.

![3D view at t = 2 s: lift-off|600](assets/2500868a9756.png)

Continue with [the results](page:results).
