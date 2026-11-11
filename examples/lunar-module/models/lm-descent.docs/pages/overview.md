# Powered descent, PDI to touchdown

Eagle's descent engine lit at 102:33:05 GET, 15 km up at 1,695 m/s. Twelve and a half minutes later the LM stood in the Sea of Tranquility. The model flies the three phases of Apollo's descent:

* **Braking (P63).** 26 s at trim thrust, then the fixed throttle position (94 %) until the guidance asks for less than 57 %: the throttle recovery at 386 s. The LM yaws to windows up between 232 and 294 s.
* **Approach (P64)** from high gate at 507 s, 7,129 ft.
* **Landing (P66)** from 617 s, flown by a pilot model that holds Aldrin's called descent rates and forward speeds.

Both P63 and P64 use Apollo's quadratic guidance, $a = a_T + 12 (r_T - r)/t_{go}^2 - 6 (v + v_T)/t_{go}$. The engine stops when a footpad touches the surface.

![The model canvas|900](assets/6fbe89803b25.png)

| block | role |
| --- | --- |
| [Free](block:Free), [Body](block:Body), [Inertia](block:Inertia), [Out1](block:Out1)..[Out6](block:Out6) | the variable-mass rigid body (see [the bond graph](project:vehicle)) |
| [Tank](block:Tank), [Engine](block:Engine) | propellant and mass properties; the descent engine with its lag |
| [Throttle](block:Throttle) | trim, fixed throttle position, throttle recovery, shutdown at touchdown |
| [Guid](block:Guid), [Att](block:Att) | the descent guidance and the RCS attitude loop |
| [PilotRate](block:PilotRate), [PilotFwd](block:PilotFwd) | the P66 pilot model from Aldrin's callouts |
| [Windows](block:Windows) | the yaw to windows up |
| [Pad1](block:Pad1)..[Pad4](block:Pad4) | the footpads on the lunar surface |
| [State](block:State), [Status](block:Status) | altitude, velocities, tilt, pad height; velocity gained, hover time left |

## What to try

1. Press **Run** (about a minute). Watch the throttle drop from the fixed position at 386 s, and the altitude reach high gate at 507 s.
2. Scale the P66 descent rates with `rate_scale`. A slower landing phase burns more of the last propellant: watch the usable propellant and the hover time left at touchdown.
3. Lower the attitude loop's `att_wn` and watch the tilt lag behind the guidance.

![3D view 1.5 s before touchdown|600](assets/0757dc825899.png)

Continue with [the results](page:results).
