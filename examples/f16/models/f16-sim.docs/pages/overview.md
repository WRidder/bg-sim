# Three-axis fly-by-wire

The flyable F-16: the Stevens & Lewis airframe of the other models under a full three-axis fly-by-wire, trimmed at 500 ft/s (Mach 0.46) and 10 000 ft with the CG at 0.35. Its inputs and outputs are export markers, so the same model is the FMU of the browser game Island Sortie (`apps/web` in the repository). In bg-sim the markers pass a test input through: by default a roll-stick pulse that banks the aircraft to 60 deg, then a coordinated level turn with the stick centred.

![The model canvas|900](assets/32f59a899750.png)

| block | role |
| --- | --- |
| [stick_pitch](block:stick_pitch), [stick_roll](block:stick_roll), [pedals](block:pedals), [throttle](block:throttle) | `ExportInputPass`: the test input here, the pilot's controls in the FMU |
| [PitchCmd](block:PitchCmd) | `PitchCommand`: stick → load factor with turn compensation, the alpha/g limiter |
| [PitchLaw](block:PitchLaw) | `PitchFBW` with Ka, Kq, Ki over (qbar, Mach), as in `f16-fbw` |
| [LatLaw](block:LatLaw) | `LateralFBW`: roll-rate command about the velocity vector, yaw damper, ARI, sideslip command |
| [Kp](block:Kp), [Kip](block:Kip), [Kr](block:Kr), [Kb](block:Kb), [Kib](block:Kib), [Kari](block:Kari) | the lateral gains: `Lookup2D` over (qbar, Mach), the ARI a `Lookup1D` over alpha |
| [StabAct](block:StabAct), [AilAct](block:AilAct), [RdrAct](block:RdrAct) | servos: ±25 deg 60 deg/s, ±21.5 deg 80 deg/s, ±30 deg 120 deg/s, all 20.2 rad/s |
| [Status](block:Status) | `F16Status`: the quaternion, Euler angles, calibrated airspeed, departure and ground flags for the host |
| `F16` gear blocks | the landing gear inside the `F16` subsystem: three legs, the retraction, steering and weight on wheels (see [the landing gear](page:gear)) |

## What to try

1. Press **Run**: the aircraft rolls to 60 deg in about a second, pulls 2 g and turns with less than 0.6 deg of sideslip. Over the 30 s turn the path sags by 45 m.
2. Set the roll pulse to 10 s and the roll stick to 1: continuous rolls at the 210 deg/s limit.
3. Pull the pitch stick to 1: the limiter holds alpha near 25 deg; the HUD flag `PitchCmd/lim_active` comes on.
4. Switch the yaw damper off and kick the pedals: the dutch roll comes back.
5. For a run on the wheels, set the start globals as in the entry `f16-sim-rest` of `expected.json` (`vt0` 0, `h0` 1.6232 m, `alpha0` -0.0707 deg, `gear0` 1, `gear_set` 1).

The flaperons (the ailerons), the rudder and the stabilators of the 3D view move with their servos.

![3D view at t = 1.8 s|600](assets/07074e11d8ca.png)

Continue with [the control laws](page:laws), [the results](page:results), [the landing gear](page:gear) and [the FMU](page:fmu).
