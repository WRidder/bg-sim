@@ figures @project
{
  "diagram": {"kind": "diagram", "model": "rocket-v2"}
}
@@ page @project variable-mass - | Variable mass on a bond graph
# Variable mass on a bond graph

Two launch vehicles share one 3D (multibond) bond graph of a body that loses mass:

| model | vehicle | flight |
| --- | --- | --- |
| [V-2](model:rocket-v2) | V-2 (A4), one stage, 12.5 t | vertical shot: 65 s burn, apogee 142 km, back down at 400 s |
| [Saturn V](model:rocket-saturn-v) | Saturn V AS-506 (Apollo 11), 2,900 t | lift-off to parking orbit: S-IC, S-II, first S-IVB burn, four jettisons, pitch program flown by the gimballed engines |

![The V-2 model: the bond graph on top, the mass budget, engine, atmosphere, gravity and drag below|900](@fig:diagram)

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
@@ figures rocket-v2
{
  "diagram": {"kind": "diagram", "model": "rocket-v2"},
  "scene": {"kind": "scene", "model": "rocket-v2", "t": 2.0, "zoom": 8},
  "flight": {
    "kind": "plot", "model": "rocket-v2", "xlim": [0, 400],
    "rows": [
      {"ylabel": "altitude [km]", "series": [{"signal": "Air/h_km", "label": "h"}]},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Air/speed", "label": "speed"}, {"signal": "Status/dv", "label": "ideal velocity gain", "style": "--"}], "legend": true},
      {"ylabel": "mass [kg]", "series": [{"signal": "Seq/m", "label": "m"}]}
    ]
  },
  "ascent": {
    "kind": "plot", "model": "rocket-v2", "xlim": [0, 80],
    "rows": [
      {"ylabel": "force [N]", "series": [{"signal": "Engine/T", "label": "thrust"}, {"signal": "Drag/D", "label": "drag"}], "legend": true},
      {"ylabel": "Mach", "series": [{"signal": "Drag/mach", "label": "Mach"}]},
      {"ylabel": "q [Pa]", "series": [{"signal": "Drag/qbar", "label": "dynamic pressure"}]},
      {"ylabel": "acceleration [g]", "series": [{"signal": "Status/acc_g", "label": "sensed"}]}
    ]
  },
  "vacuum": {
    "kind": "plot", "model": "rocket-v2", "xlim": [0, 80],
    "settings": {"t_end": 80.0, "output": {"points": 801}},
    "overrides": {"global:drag_scale": 0.0, "global:gravity_scale": 0.0, "global:ambient_scale": 0.0},
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "Air/speed", "label": "speed, vacuum"}, {"signal": "Status/dv", "label": "c ln(m0/m)", "style": "--"}], "legend": true}
    ]
  }
}
@@ page rocket-v2 overview - | Overview
# V-2, vertical shot

The V-2 (A4) launched straight up, as in the post-war sounding flights:

* 12,500 kg at launch, 8,720 kg of propellant, 123 kg/s for 65 s;
* 25 t of thrust at sea level, rising to 29 t in vacuum as the ambient pressure falls (the nozzle's exit area is 0.39 m²);
* U.S. Standard Atmosphere 1976, drag with a Mach table, inverse-square gravity.

![The model canvas|900](@fig:diagram)

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

![3D view at t = 2 s: lift-off|600](@fig:scene)

Continue with [the results](page:results).
@@ page rocket-v2 results overview | Results
# Results

![Flight: altitude, speed and mass|900](@fig:flight)

The thrust climbs from 25 t to 29 t as the air thins. The drag peaks near Mach 1.2, where the dynamic pressure is still high:

![Ascent: thrust and drag, Mach, dynamic pressure, acceleration|900](@fig:ascent)

In vacuum, without gravity and drag, the speed is Tsiolkovsky's ideal velocity gain. At 80 s it is 2380.557 m/s, $c \ln(m_0/m_f)$ to 1e-6:

![Vacuum: speed and Tsiolkovsky|900](@fig:vacuum)

## Against the published data

| | published | model |
| --- | --- | --- |
| burnout speed | about 1,500 m/s | 1,422 m/s (−5 %) |
| apogee, vertical | about 160 km (design); 174.6 km and 206 km were flown | 141.7 km (−11 %) |

The model is low on both counts. The published figures are "about" values from flights with different payloads and burn times. The drag table is an estimate: no digitised V-2 drag curve is online. The checks compare loosely with the published figures (10 % and 15 %) and tightly (1e-4) with an independent scipy model of the same equations (`design/reference.py`).
@@ figures rocket-saturn-v
{
  "diagram": {"kind": "diagram", "model": "rocket-saturn-v"},
  "scene": {"kind": "scene", "model": "rocket-saturn-v", "t": 6.0, "zoom": 8},
  "traj": {
    "kind": "plot", "model": "rocket-saturn-v", "xlim": [0, 712],
    "rows": [
      {"ylabel": "altitude [km]", "series": [{"signal": "Air/h_km", "label": "h"}]},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Air/speed", "label": "space-fixed"}, {"signal": "Air/v_rel", "label": "Earth-fixed", "style": "--"}], "legend": true},
      {"ylabel": "mass [t]", "series": [{"signal": "Seq/m", "label": "m", "scale": 0.001}]},
      {"ylabel": "acceleration [g]", "series": [{"signal": "Status/acc_g", "label": "sensed"}]}
    ]
  },
  "pitch": {
    "kind": "plot", "model": "rocket-saturn-v", "xlim": [0, 712],
    "rows": [
      {"ylabel": "angle [deg]", "series": [{"signal": "Pitch/y", "label": "pitch command"}, {"signal": "Air/theta_deg", "label": "attitude", "style": "--"}, {"signal": "Air/fpa_deg", "label": "flight-path angle"}], "legend": true},
      {"ylabel": "gimbal [deg]", "series": [{"signal": "AP/delta_deg", "label": "delta"}]}
    ]
  },
  "maxq": {
    "kind": "plot", "model": "rocket-saturn-v", "xlim": [0, 170],
    "rows": [
      {"ylabel": "Mach", "series": [{"signal": "Drag/mach", "label": "Mach"}]},
      {"ylabel": "q [Pa]", "series": [{"signal": "Drag/qbar", "label": "dynamic pressure"}]},
      {"ylabel": "thrust [N]", "series": [{"signal": "Engine/T", "label": "T"}]}
    ]
  }
}
@@ page rocket-saturn-v overview - | Overview
# Saturn V, Apollo 11 to orbit

The Saturn V of Apollo 11 (AS-506, 16 July 1969) from lift-off to the parking orbit, with the
masses, event times and engine performance of the *Saturn V Flight Evaluation Report AS-506*:

| range time | event |
| --- | --- |
| 0 | lift-off, 2,899 t, five F-1 engines |
| 135.2 s | centre engine cutoff (CECO) |
| 161.6 s | outboard engine cutoff (OECO) |
| 162.3 s | S-IC separation (165 t) |
| 165.5 s | five J-2 engines of the S-II |
| 192.3 s | S-II aft interstage dropped |
| 197.9 s | launch escape tower jettisoned |
| 460.6 s | S-II centre engine cutoff |
| 491.2 s | mixture-ratio shift (thrust 4.1 → 3.1 MN) |
| 548.2 s | S-II cutoff, separation (47 t) at 549.0 s |
| 552.2 s | S-IVB ignition |
| 699.3 s | S-IVB cutoff, insertion at 709.3 s |

The vehicle is the variable-mass bond graph of [variable mass on a bond graph](project:variable-mass). A pitch program (`Lookup1D` over time) commands the attitude, and a PD loop turns the engines through ±6°.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Seq](block:Seq) | `FlightSequence`: nine engine phases, four jettisons, five inertia configurations |
| [Pitch](block:Pitch), [AP](block:AP) | the pitch program and the attitude loop (gimbal angle to [Engine](block:Engine)) |
| [Air](block:Air) | altitude, surface range on the turning Earth, flight-path angle, the air velocity |
| [SpentSIC](block:SpentSIC), [SpentIS](block:SpentIS), [SpentLET](block:SpentLET), [SpentSII](block:SpentSII) | the dropped parts, flying ballistically from their separation (for the 3D view) |

## What to try

1. Press **Run** (about 20 s). Watch the 3D view: the S-IC falls away at 162 s, the interstage ring at 192 s, the escape tower shoots ahead at 198 s, and the S-II drops at 549 s.
2. Set **tilt** to 0.95 or 1.05: the vehicle pitches over less or more, and misses the orbit.
3. Double the drag, or slow the attitude loop (**ap_wn**).

![3D view at t = 6 s: clearing the tower|600](@fig:scene)

Continue with [the results](page:results).
@@ page rocket-saturn-v results overview | Results
# Results

![Altitude, speed, mass and acceleration|900](@fig:traj)

The acceleration climbs to 3.9 g before the S-IC's outboard cutoff, drops at each staging, and steps down at the S-II's mixture-ratio shift.

![Pitch program, attitude and flight-path angle; the gimbal angle|900](@fig:pitch)

![Mach, dynamic pressure and thrust in the S-IC burn|900](@fig:maxq)

## Against the flight evaluation report

| | AS-506 | model |
| --- | --- | --- |
| speed at S-IC CECO / OECO | 1,979.0 / 2,764.1 m/s | 1,965.0 / 2,750.7 |
| at S-II CECO / OECO | 5,707.5 / 6,917.3 m/s | 5,722.2 / 6,939.1 |
| at S-IVB cutoff | 7,791.2 m/s | 7,826.9 |
| maximum acceleration S-IC / S-II / S-IVB | 38.61 / 17.84 / 6.73 m/s² | 38.53 / 18.01 / 6.78 |
| mass at S-IC OECO / S-II OECO / S-IVB cutoff | 827.3 / 213.9 / 135.2 t | 826.4 / 211.7 / 132.9 |
| Mach 1 | 66.3 s | 64.4 s |
| max Q | 35.2 kPa at 83.0 s | 31.7 kPa at 75.3 s |
| altitude, flight-path angle, range at the cutoffs | | within 0.7 km, 0.1°, 7 km (fitted) |

The pitch program is fitted to the altitude, flight-path angle and range. The speeds, accelerations, masses, Mach 1 and max Q are not fitted: they test the propulsion, mass and drag data. Max Q comes 8 s early and 10 % low. The drag table is an estimate, and the report's dynamic pressure uses the measured atmosphere and winds of the day. The S-II flow, computed from the published thrust and specific impulse, burns about 2 t more than the report's mass history shows. So the masses after the S-II are 1 to 2 % low and the speeds 0.3 to 0.5 % high.

The checks compare the run tightly with an independent scipy model of the same equations (`design/reference.py`). They compare it loosely with the report, with each tolerance stating what is fitted and what is not.
