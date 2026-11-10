# Rocket: variable-mass launch vehicles on a 3D bond graph

Two launch vehicles, both built on the same 3D (multibond) bond graph of a body that loses mass:

| model | what it is |
| --- | --- |
| `rocket-v2` | a **V-2 (A4)** launched vertically: one stage, 65 s burn, thrust with the ambient-pressure correction, US Standard Atmosphere 1976, Mach-dependent drag and inverse-square gravity, up to apogee (142 km) and back down |
| `rocket-saturn-v` | the **Saturn V of Apollo 11 (AS-506)** from lift-off to parking-orbit insertion: S-IC, S-II and the first S-IVB burn, centre-engine cutoffs, the S-II mixture-ratio shift, four jettisons (S-IC, S-II aft interstage, escape tower, S-II), a pitch program flown by thrust vector control (gimballed engines), flight over a round Earth with the atmosphere turning with it |

Why these two: the V-2 is the classic single-stage liquid rocket with public mass, flow and thrust figures (sea level and vacuum); the Saturn V has the best public flight data of any launcher, the **Saturn V Flight Evaluation Report AS-506** (MPR-SAT-FE-69-9, NASA MSFC, 1969), which gives the event times, the trajectory at every cutoff, the vehicle mass at every event and the engine performance reconstructed from telemetry. Falcon 9 and Electron were not chosen: their stage masses are estimates, not published.

## Variable mass on a bond graph

The vehicle is a `stdlib:spatial/Free3D` joint from the ground (`World`) to the vehicle's 1-junction `Body`. On the junction sit:

- `Inertia`, project block `VariableInertia3D`: a **modulated spatial inertia** (an MI). Its state is the body-frame momentum `P = [h; p]`, as in `stdlib:multibond/ISpatial`, but the mass `m(t)` and the principal moments `J(t)` are signals: `p.f = [h/J; p/m]`.
- `Coriolis` (`CoriolisSpatial`, the gyroscopic terms), `Twist` (`DfSpatial`, the twist tap).
- three `ExternalWrenchSpatial` sources: thrust (`Engine`), gravity (`Gravity`), drag (`Drag`).
- six `stdlib:bondgraph/MR` elements `Out1..Out6` on the joint's drive ports (the body-frame twist components), with resistance `r = -dm/dt` on the three linear and `r = -dJk/dt` on the three angular components.

At constant momentum a falling mass would *raise* the speed `p/m`. The MRs are the mass leaving the vehicle with its own velocity and taking its momentum `|dm/dt| v` with it; together the two give the variable-mass law

    m dv/dt = F_thrust + F_gravity + F_drag,        J dw/dt = M (+ gyroscopic terms)

with the thrust as its own wrench (`T = mdot c_vac - p_a A_e`). The energy bookkeeping is honest as well: the modulated I gains `|dm/dt| v^2 / 2` from the modulation, the MR removes `|dm/dt| v^2`, and the difference is the kinetic energy carried away by the leaving mass. A jettisoned stage leaves through the same MR (a 0.2 s mass ramp), so the vehicle's speed does not jump at staging. The **vacuum checks** prove it: without gravity, drag and atmosphere the V-2's burnout speed equals Tsiolkovsky's `c ln(m0/mf)` to 1e-6.

Limitations: the body frame stays at the centre of mass (the CoM shift as propellant drains is not modelled), the propellant leaves at the CoM (no jet damping), the aerodynamics are drag only along the air velocity at the CoM (no lift, no aerodynamic moment), the Earth is a non-rotating sphere with the pad's eastward speed resolved into the launch plane, and both flights stay in that vertical plane (the Saturn V's roll and yaw manoeuvres and the out-of-plane steering are not modelled).

## Custom library blocks (`library/`)

| block | why it is needed |
| --- | --- |
| `VariableInertia3D` | the stdlib `ISpatial` has a constant mass and inertia; this is the same element with them as inputs (a modulated I) |
| `FlightSequence` | the mass budget: engine phases (flow command with a first-order lag, exhaust velocity, exit area), jettisons as short mass ramps, inertia and gimbal arm per configuration; it outputs the MR resistances |
| `RocketEngine3D` | the thrust law `max(mdot c_vac - p_a A_e, 0)` and the gimbal geometry (a wrench) |
| `CentralGravity3D` | inverse-square gravity of a sphere on a variable mass (`GravitySpatial` is uniform with a constant mass) |
| `Atmosphere1976` | the U.S. Standard Atmosphere 1976 as a table (ln p, ln rho, T) |
| `AxialDrag3D` | drag with a Mach table (a wrench) |
| `AirData3D`, `FlightStatus` | taps: altitude, range, flight-path angle, air velocity, pitch; sensed acceleration, ideal velocity gain |
| `PitchAutopilot` | the pitch loop through the gimbal (Saturn V) |
| `RocketView`, `SpentStage` | the 3D view: the vehicle stays at the origin, the world and the jettisoned parts move |

## Parameters and their sources

`[pub]` published, `[der]` derived from published numbers, `[est]` estimate. All numbers live in `design/data.py` with the same tags.

### V-2

| parameter | value | source |
| --- | --- | --- |
| launch mass | 12,500 kg | [pub] Wikipedia, V-2 rocket (infobox) |
| propellant loaded | 3,810 kg ethanol/water + 4,910 kg LOX | [pub] Wikipedia, V-2 rocket |
| propellant flow | 55 kg/s alcohol + 68 kg/s LOX = 123 kg/s | [pub] Wikipedia, V-2 rocket |
| burn time | 65 s (7,995 kg burned; the remaining 725 kg are residual) | [pub] "up to 65 s"; the residual is [der] |
| thrust | 25 t at sea level, 29 t in vacuum | [pub] Wikipedia, V-2 rocket |
| vacuum exhaust velocity | 2,312 m/s (Isp 236 s) | [der] T_vac / mdot |
| nozzle exit area | 0.387 m² (0.70 m diameter) | [der] (T_vac − T_sl) / p0 |
| diameter, reference area | 1.65 m, 2.14 m² | [pub] Wikipedia |
| drag coefficient vs Mach | 0.16 subsonic, peak 0.42 at M 1.1, 0.19 at M 5 | [est] no digitised V-2 table found (the 1941 Peenemünde tables are archived at UAH but not online) |
| radii of gyration | pitch 3.5 m, roll 0.5 m | [est] (no effect on a vertical flight) |

### Saturn V (AS-506, Apollo 11)

| parameter | value | source |
| --- | --- | --- |
| mass at holddown release | 2,899,008 kg (at range time 0.3 s; +0.3 s of S-IC flow for t = 0) | [pub] AS-506 Table 20-1 |
| S-IC flow, 5 engines / 4 engines | 13,260 kg/s / 10,704 kg/s | [der] AS-506 mass history (Table 20-1) between holddown release, CECO and OECO |
| F-1 specific impulse at sea level | 2,594.4 N·s/kg | [pub] AS-506 Table 5-1 (reconstruction, average of five) |
| F-1 exit area | 9.87 m² per engine | [der] Wikipedia, Rocketdyne F-1: (7,770 − 6,770 kN) / p0 |
| F-1 vacuum exhaust velocity | 2,980.6 m/s | [der] Isp_sl + p0 A_e / mdot_sl (Table 5-1 flow) |
| S-II thrust: 5 engines, 4 engines, low EMR | 5,141,516 / 4,093,107 / 3,082,769 N | [pub] AS-506 section 6.3 |
| J-2 specific impulse, high EMR | 4,165.3 N·s/kg | [pub] AS-506 Table 6-1 (average of five) |
| J-2 specific impulse, low EMR | 4,205 N·s/kg | [est] about 1 % above high EMR |
| J-2 exit area | 3.02 m² | [der] Wikipedia, Rocketdyne J-2: exit diameter 1.96 m |
| S-IVB thrust, specific impulse | 901,223 N, 4,204 N·s/kg | [pub] AS-506 Table 7-2 |
| event times (CECO, OECO, separations, S-II start, EMR shift, LET jettison, S-IVB ignition and cutoff) | 135.20 … 699.34 s | [pub] AS-506 Tables 2-2, 20-1, 20-3, 20-5 |
| jettisoned masses: S-IC 165,262 kg, interstage 3,982 kg, LET 4,042 kg, S-II 47,186 kg | | [der] differences of the published vehicle masses (Tables 20-1, 20-3, 20-5) |
| thrust decay time constant | 0.33 s | [der] outboard cutoff impulse 10.6 MN·s (AS-506 5.4) / 31.9 MN |
| launch azimuth, pad latitude | 72.058°, 28.608° N | [pub] AS-506 |
| Earth radius, µ | 6,378,165 m, 3.986004418e14 m³/s² | [pub] AS-506 Table 4-5 note; WGS 84 |
| diameter | 10.06 m | [pub] |
| drag coefficient vs Mach | 0.30 subsonic, peak 0.66 at M 1.2, 0.27 at M 8 | [est] no flight-derived table online (Boeing D5-15796-1 is not public) |
| radii of gyration, gimbal arm per configuration | 30 / 19 / 18.5 / 17 / 11 m, 35 / 21 / 20 / 19 / 14 m | [est] the AS-506 inertia table (20-10) is unreadable in the scan |
| attitude loop | wn 1.5 rad/s, zeta 0.8, gimbal ±6° | [est]; ±6° is the F-1 gimbal range [pub] |
| pitch program | piecewise linear, 20 knots | **fitted** (design.py) to the published altitude, flight-path angle and range at the five cutoffs and the altitude at Mach 1 and max Q |

## Reference values and checks (`expected.json`)

- **scipy reference** (`design/reference.py`): the same equations as a planar point mass with a pitch degree of freedom, integrated with DOP853 at rtol 1e-10. The bond-graph runs agree to about 1e-6.
- **Tsiolkovsky** (analytic): the V-2 in vacuum (`rocket-v2-vacuum`, globals `drag_scale`, `gravity_scale`, `ambient_scale` = 0) reaches c ln(m0/mf) = 2380.557 m/s; the Saturn V's ideal velocity gain through the S-IC in vacuum is c ln(m0/m) at 160 s.
- **Published data** (honest tolerances, each note says what is fitted and what is not):

| quantity | published | model | |
| --- | --- | --- | --- |
| V-2 burnout speed | about 1,500 m/s | 1,422 m/s | −5 % |
| V-2 apogee (vertical) | about 160 km design, 174.6 km wartime maximum, 206 km maximum | 141.7 km | −11 % vs 160 km |
| Saturn V speed at S-IC CECO / OECO | 1,979.0 / 2,764.1 m/s | 1,965.0 / 2,750.7 | −0.7 % / −0.5 % |
| at S-II CECO / OECO | 5,707.5 / 6,917.3 m/s | 5,722.2 / 6,939.1 | +0.3 % / +0.3 % |
| at S-IVB cutoff / insertion | 7,791.2 / 7,793.1 m/s | 7,826.9 / 7,829.1 | +0.5 % |
| maximum acceleration S-IC / S-II / S-IVB | 38.61 / 17.84 / 6.73 m/s² | 38.53 / 18.01 / 6.78 | |
| mass at S-IC OECO / S-II OECO / S-IVB cutoff | 827,292 / 213,888 / 135,182 kg | 826,448 / 211,663 / 132,871 | −0.1 / −1.0 / −1.7 % |
| Mach 1 | 66.3 s | 64.4 s | |
| max Q | 35.2 kPa at 83.0 s, 13.6 km | 31.7 kPa at 75.3 s, 11.0 km | −10 % |
| altitude, flight-path angle, range at the cutoffs | Table 4-2 | within 0.7 km, 0.1°, 7 km | fitted |

What does not match, and why: the V-2's numbers are "about" values for rockets with different payloads, and the drag table is an estimate. The Saturn V's max Q comes 8 s early and 10 % low: the model's drag table is an estimate and the report's Q uses the measured atmosphere and winds of the day. The S-II flow from the published thrust and specific impulse burns about 2 t more than the mass history shows, so the masses after the S-II are 1 to 2 % low and the speeds 0.3 to 0.5 % high.

## What to try

- `rocket-v2`: set drag, gravity and atmosphere to 0 on the dashboard and compare the burnout speed with c ln(m0/mf); shorten the burn; raise the launch mass.
- `rocket-saturn-v`: scale the tilt of the pitch program (0.95 or 1.05) and watch the insertion miss; raise the drag; slow the attitude loop.
- Watch the 3D view: the S-IC falls away at 162 s, the interstage ring at 192 s, the escape tower shoots ahead at 198 s, the S-II drops at 549 s.

## Rebuild

    uv run examples/rocket/design/design.py            # reference numbers (design.json), --refit refits the pitch program
    uv run examples/rocket/design/build_model.py       # models, scenes, expected.json
    uv run examples/run_checks.py --only rocket
    uv run tools/example_docs/build.py --only rocket

`design/run_model.jl` and `design/readrun.py` run a model through BGSim directly and print signals, for iterating without the backend.
