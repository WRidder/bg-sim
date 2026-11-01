# Envelope protection

At 900 ft/s (Mach 0.82) and 5000 ft the pilot pulls the stick fully aft from 1 s and lights the afterburner. The stick gearing asks for 11 g. **Protected** has the alpha/g limiter on; **Unprotected** has it off.

![The model canvas|900](assets/ce936c1987dd.png)

| block | role |
| --- | --- |
| [Stick](block:Stick) | full aft stick, ramped in over 0.5 s |
| [ProtectedCmd](block:ProtectedCmd) | `GCommand`: stick → load factor → pitch rate, and the min-select limiter |
| [ProtectedLaw](block:ProtectedLaw), [ProtectedAct](block:ProtectedAct) | the scheduled law and the servo of `f16-fbw` |

The command path:

$$q_{stick} = \frac{g_0}{V_t}\big(1 + 10\,\delta_{stick} - \cos\gamma\cos\phi\big), \quad q_{cmd} = \min\Big(q_{stick},\; 3(25 - \alpha),\; \frac{g_0}{V_t}(9 - \cos\gamma\cos\phi) + 4 (9 - n_z)\Big)$$

so the commanded pitch rate fades out as alpha approaches 25 deg or the load factor 9 g.

## What to try

1. Press **Run** and watch the gauges: Protected stays in the green, Unprotected passes 10 g and later departs.
2. Set the limiter slider to 0: both aircraft depart.
3. Pull less (stick 0.5): neither limit is reached.

![3D view at t = 5 s|600](assets/0aded2c57b81.png)

Continue with [the results](page:results).
