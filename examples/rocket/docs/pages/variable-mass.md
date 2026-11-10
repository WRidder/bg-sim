# Variable mass on a bond graph

Two launch vehicles share one 3D (multibond) bond graph of a body that loses mass:

| model | vehicle | flight |
| --- | --- | --- |
| [V-2](model:rocket-v2) | V-2 (A4), one stage, 12.5 t | vertical shot: 65 s burn, apogee 142 km, back down at 400 s |
| [Saturn V](model:rocket-saturn-v) | Saturn V AS-506 (Apollo 11), 2,900 t | lift-off to parking orbit: S-IC, S-II, first S-IVB burn, four jettisons, pitch program flown by the gimballed engines |

![The V-2 model: the bond graph on top, the mass budget, engine, atmosphere, gravity and drag below|900](assets/8f7bf3ef746f.png)

## The bond graph

- A `Free3D` joint ties the vehicle's 1-junction `Body` to the ground (`World`).
- `Inertia` (`VariableInertia3D`, a project block) is a **modulated spatial inertia**. Its state is the body-frame momentum $P = [h; p]$, as in the stdlib `ISpatial`, but the mass $m(t)$ and the principal moments $J(t)$ are input signals: the flow is $[h/J;\ p/m]$.
- `Coriolis` adds the gyroscopic terms, `Twist` taps the body twist.
- Three `ExternalWrenchSpatial` sources carry the thrust, the gravity and the drag.
- Six `MR` elements `Out1..Out6` sit on the joint's drive ports (the body-frame twist components). Their resistance is $r = -\dot m$ on the linear and $r = -\dot J_k$ on the angular components.

At constant momentum, a falling mass would *raise* the speed $p/m$. The MRs are the mass leaving the vehicle with the vehicle's own velocity: each takes the momentum $|\dot m|\,v$ with it. Together the two give

$$m\,\dot v = F_\text{thrust} + F_\text{gravity} + F_\text{drag}$$

with the thrust as its own wrench, $T = \dot m\,c_\text{vac} - p_a A_e$. The energy balance holds too: the modulation gives the I element $|\dot m| v^2/2$, the MR dissipates $|\dot m| v^2$, and the difference is the kinetic energy that leaves with the exhaust. A jettisoned stage leaves through the same MRs, as a 0.2 s mass ramp, so the speed does not jump at staging.

**The check.** Set drag, gravity and atmosphere to 0 (the globals `drag_scale`, `gravity_scale` and `ambient_scale`). The V-2's burnout speed then equals Tsiolkovsky's $c \ln(m_0/m_f)$ = 2380.557 m/s to 1e-6, and the Saturn V's ideal velocity gain through the S-IC matches as well.

## The signal side

| block | role |
| --- | --- |
| `FlightSequence` | the mass budget: engine phases (flow with a first-order lag, exhaust velocity, exit area), jettisons, inertia and gimbal arm per configuration, the MR resistances |
| `RocketEngine3D` | thrust $\max(\dot m c_\text{vac} - p_a A_e, 0)$ and the gimbal geometry |
| `Atmosphere1976` | U.S. Standard Atmosphere 1976 (ln p, ln ρ, T tabulated to 300 km) |
| `CentralGravity3D` | inverse-square gravity of a sphere on the variable mass |
| `AxialDrag3D` | drag against the air velocity, with a Mach table |
| `AirData3D`, `FlightStatus` | altitude, surface range, flight-path angle, Mach; sensed acceleration and the ideal velocity gain |
| `PitchAutopilot` | the Saturn V's attitude loop through the gimbal |
| `RocketView`, `SpentStage` | the 3D view: the vehicle stays at the origin, the Earth and the dropped stages move |

## What is published, what is estimated

The README of the example lists every parameter with its source. In short:

- **Published:** the V-2's mass, propellant load, flow and sea-level and vacuum thrust (Wikipedia). For the Saturn V, the *Saturn V Flight Evaluation Report AS-506* (NASA MSFC, MPR-SAT-FE-69-9, 1969) gives the masses at every event, the event times, the F-1, J-2 and S-IVB performance, and the trajectory at every cutoff.
- **Estimated:** both drag tables (no flight-derived Cd(M) is online), the radii of gyration and gimbal arms, and the attitude loop.
- **Fitted:** the Saturn V's pitch program, fitted to the published altitude, flight-path angle and range at the five cutoffs.

**Limits.** The flight stays in one vertical plane over a non-rotating sphere; the pad's eastward speed is resolved into that plane, and the air turns with it. The model has drag only (no lift, no aerodynamic moment), no centre-of-mass shift and no jet damping.
