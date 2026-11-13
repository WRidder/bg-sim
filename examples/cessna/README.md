# Cessna 172

A Cessna 172P as a bond graph: a multibond rigid-body airframe on three landing-gear legs with strut, tyre and brake elements, a piston engine and fixed-pitch propeller on a rotational bond graph, and aerodynamic forces as modulated sources. The open-loop modes are compared with an independent scipy model, and a flyable version with an autopilot exports as the FMU of a flight-simulator host.

The aircraft data is JSBSim's c172p, transcribed with attribution under the LGPL-2.1 (see
[Sources and licence](#sources-and-licence)). One part is not JSBSim data: the propeller's
thrust and power tables carry a low-speed correction fitted to the POH (see
[The propeller fit](#the-propeller-fit)). The model is checked against the Pilot's Operating
Handbook (POH) and the type-certificate data. Everything is in SI inside bg-sim. The design
scripts work in SI too: `design/c172_si.py` converts JSBSim's ft, lb and slug.

## Models

| model | what it shows |
| --- | --- |
| `cessna-open-loop` | Five aircraft trimmed in level flight at 100 KTAS and 5000 ft. Each is released along the eigenvector of one rigid-body mode: the short period (1 deg of alpha), the phugoid (2 m/s of speed), the dutch roll (1 deg of sideslip), the roll mode (2 deg of bank) and the spiral (5 deg of bank). The five aircraft are instances of the library subsystem `C172Airframe` (`library/C172Airframe.bgsub.json`, the airframe without landing gear in calm air); each sets only its own start state. Two `ModeRate` blocks read the live rate (dphi/dt)/phi of the roll and spiral modes. Every curve is checked against the scipy reference (`design/c172_ref.py`). |
| `cessna-sim` | The flyable Cessna, standing on runway 36 with the engine at idle and flaps 10. A scripted pilot (`DemoPilot`, smooth phase switches with no events) applies full power and rotates at 45 KCAS. It climbs at 75 KCAS, raises the flaps at 65 ft and turns right to east at 75 s. The 16 pilot inputs (yoke, pedals, throttle, mixture, flap detent, trim, toe brakes, the autopilot switches, the heading bug and altitude, and the wind) are `ExportInputPass` markers. The 38 outputs are `ExportOutput` markers. The start state is 20 globals. The dashboard has sliders for every control. The 3D scene shows the airfield, the moving control surfaces, the flaps, the steered nose wheel and the spinning propeller. |

`expected.json` also runs `cessna-sim` with overrides as three more scenarios:

* `cessna-sim-autopilot`: 1000 m, heading hold to 60 deg and altitude hold;
* `cessna-sim-climb`: the full-throttle climb at the best-rate speed;
* `cessna-sim-cruise`: full throttle at 8000 ft.

## The bond graph

**Airframe.** The airframe is a `RigidBody3D` on a `Free3D` joint to `GroundSpatial`. Its mass is
1088.6 kg (2400 lb). Its inertia is c172p's empty tensor plus its point masses, with the products
of inertia dropped. Gravity is in the body. Each external force enters
as an `ExternalWrenchSpatial`:

* the aerodynamic wrench of `C172Aero`: the c172p build-up with lift, drag, side force and three
  moments, the flap and ground-effect tables, the alpha-dot and rate terms, and the stall
  hysteresis;
* the propeller's thrust and torque at the hub;
* the three gear legs.

`C172AirData` reads the body twist and pose, the wind and the altitude. From them it computes
alpha, beta, the true and calibrated airspeed, the dynamic pressure, the Euler angles, and the
height above the runway for ground effect.

**Engine and propeller.** These form a rotational bond graph on the crankshaft's 1-junction. A
`Rotor3D` (the crank plus the propeller, axial inertia 2.26 kg m^2 = 1.67 slug ft^2) is mounted on the airframe
through a `FixedTransform3DNeutral`, so the shaft's gyroscopic moment and its torque reaction act
on the body. Two elements sit on the junction:

* `PistonEngine`: an MSe with JSBSim's FGPiston without the starter, the magnetos or the
  temperatures. Its manifold pressure is a state with impedances, and it models volumetric
  efficiency, the mixture-efficiency table, and pumping and friction losses.
* `Propeller`: an R whose torque is CP(J) rho n^2 D^5 / 2 pi, from the prop_75in2f tables with
  the tip-Mach factors, and C_T and C_P corrected at low advance ratio by a fit to the POH. Its thrust CT(J) rho n^2 D^4 is the hub force, and it gives the induced
  velocity over the tail.

**Landing gear.** Each leg (nose, left, right) is a `GearContact`. It is a power-conserving
modulated transformer from the airframe's multibond to three translational bonds:

* the runway normal, with a `StrutSpring` C and a `StrutDamper` R on its 1-junction (c172p's
  spring and damping coefficients, with a smooth unloading);
* the rolling direction, with a `WheelFriction` R: the rolling resistance plus the brake, using
  the toe brakes on the main wheels and a tanh regularisation at standstill;
* the cross direction, with a `WheelSide` R: the cornering force from JSBSim's magic formula of
  the slip angle.

The nose leg's rolling direction is turned by the steering angle: 10 deg at full pedal.

**Signal blocks.** These are used only where the physics isn't energetic:

* the controls (`C172Controls`: yoke, pedals and trim to the surface angles at c172p's limits);
* the flap actuator: a rate-limited first-order lag to the detent;
* the alpha-dot filter;
* the stall hysteresis;
* the autopilot (`C172Autopilot`):
  * a wing leveller, or heading hold through a bank command up to 20 deg;
  * altitude hold through a pitch command: a clamped (plus or minus 30 m) altitude error,
    vertical-speed damping and an integrator;
  * both acting on the yoke as a pilot would;
* the status outputs (`C172Status`: KIAS, vertical speed, slip ball, turn rate, wheel loads);
* the demo pilot.

## Validation

`design/design.py` writes `design/design.json` from the scipy reference model. This model is
independent of bg-sim and implements the same physics (`design/c172_ref.py`, linearised in
`design/c172_lin.py`). `design/perf.py` computes the performance figures. The POH and
type-certificate values are in `design/poh.py`, each with its source.

### Performance (2400 lb, standard day, free air except take-off)

The model's propeller is **not** JSBSim's: its C_T and C_P tables are fitted to the POH at low
advance ratio (see [The propeller fit](#the-propeller-fit)). The first column is the same model
with JSBSim's prop_75in2f tables, as the example was first built.

| quantity | JSBSim propeller | POH-fitted propeller (the model) | POH / spec |
| --- | --- | --- | --- |
| stall, flaps up, power off | 55.4 KCAS | 55.4 KCAS | 51 (aft CG) to 52 (fwd CG) KCAS |
| stall, flaps 10 | 51.8 KCAS | 51.8 KCAS | 48 to 49 KCAS |
| stall, flaps 30 | 49.5 KCAS | 49.5 KCAS | 46 KCAS |
| static run-up, full throttle (flaps 10) | 2195 rpm, 1577 N | 2366 rpm, 2674 N | 2300 to 2420 rpm |
| best rate of climb, sea level | 601 fpm at 93 KCAS (512 fpm at 76) | 711 fpm at 84 KCAS (689 fpm at 76) | 700 fpm at 76 KIAS |
| best rate of climb, 8000 ft | 326 fpm at 83 KCAS (267 fpm at 72) | 395 fpm at 80 KCAS (395 fpm at 72) | 332 fpm at 72 KIAS |
| maximum speed, sea level | 126.2 KTAS (162 hp, 2676 rpm) | 126.2 KTAS (162 hp, 2677 rpm) | 123 kt |
| full throttle, 8000 ft | 124.0 KTAS (130 hp = 81 %) | 124.1 KTAS (130 hp = 81 %) | 120 KTAS at 75 % power |
| glide (propeller windmilling) | 9.9 at 83 KCAS; 8.0 at 65 KCAS | same | about 9.1 at 65 KIAS (flagged) |
| take-off ground roll (flaps 10) | 1492 ft, lift-off 54.9 KCAS | 855 ft, lift-off 54.5 KCAS | 892 ft, lift-off 51 KIAS |
| take-off over 50 ft | 4118 ft | 1819 ft (59 KCAS at 50 ft) | 1628 ft (56 KIAS at 50 ft) |

Both columns use FGPiston's own ISFC calibration, 0.418. The engine file's choice is the other
open question:

* **0.32** is the `bsfc` that `eng_io320.xml` sets. With it the engine makes about 205 hp at
  full throttle at sea level, well over its 160 hp rating. That excess power hides the JSBSim
  propeller's weak static thrust: with the JSBSim tables it gives 2538 rpm static, 1155 fpm at
  95 KCAS, 137.8 KTAS, a 958 ft ground roll and 1868 ft over 50 ft (`design.json`, performance
  `file`).
* **0.418** is FGPiston's own default calibration. It gives the rated 160 hp at 2700 rpm and
  28.5 inHg, and the bg-sim model uses it.

With the honest engine the JSBSim propeller limits climb and take-off: the static rpm is under
the POH range, the climb at 76 KIAS is 27 % short and the ground roll 67 % long. The fitted
propeller keeps the 160 hp and fixes the low-speed end:

* The sea-level climb at 76 KIAS is 2 % under the POH, and the static rpm is inside its range.
* The ground roll is 4 % short and the distance over 50 ft 12 % long (next section).
* The maximum and full-throttle cruise speeds are unchanged, 3 % over the POH. 75 % power is not
  reachable at 8000 ft, since full throttle gives 81 % at the model's higher speed.
* **The 8000 ft climb is now 19 % over the POH** (it was 20 % under at 72 KIAS). The model loses
  less climb with altitude than the airplane: 689 to 395 fpm from sea level to 8000 ft, where the
  POH loses 700 to 332. The propeller works at the same advance ratio in both climbs, so no
  propeller table can fix both; the fit puts the sea-level climb first. The likely causes are
  the engine's altitude lapse and the drag polar, which the fit does not touch.

The clean stall is 7 % high: c172p's CLmax with the hysteresis. The glide is better than the
commonly quoted 9:1, and its best speed (83 KCAS) is higher than the POH's 65 KIAS.

### The take-off

`design/perf.py` (`takeoff`) flies the POH's short-field take-off (Section 4, Figure 5-5) at sea
level:

* flaps 10, full throttle against the brakes, released at t = 0 (as the POH);
* the yoke neutral until 45 KCAS, then a pitch-attitude hold at 9.7 deg (the POH holds the
  elevator "slightly tail low" from the start);
* the aircraft lifts off when it flies, at 54.5 KCAS: the model's flaps-10 stall is 51.8 KCAS
  against the POH's 48 to 49, so it cannot lift off at the POH's 51 KIAS;
* after lift-off it pitches for 58 KCAS (the POH climbs at 56 KIAS; the model works in CAS and
  does not model the POH's airspeed calibration).

The ground roll is the distance to the instant the last wheel leaves the runway; the 50 ft point
is the CG 50 ft above its height at rest. The extra 50 ft distance comes mostly from the higher
lift-off speed: after lift-off the model accelerates in ground effect to its climb speed before
it climbs. The ground roll with the JSBSim tables was 1492 ft in the same technique.

The `cessna-sim` demo pilot does not fly this technique: it rotates at 45 KCAS, climbs at
75 KCAS and raises the flaps at 65 ft. It passes 50 ft at 37.0 s, 2657 ft from brake release.

### The propeller fit

`design/c172_data.py` keeps JSBSim's tables (`C_THRUST_JSBSIM`, `C_POWER_JSBSIM`) and scales both
by a cosine taper in the advance ratio J:

    w(J) = (1 + cos(pi J / J1)) / 2 for J < J1, else 0
    C_T(J) = C_T,JSBSim(J) (1 + kT w(J)),   C_P(J) = C_P,JSBSim(J) (1 + kP w(J))

`design/prop_fit.py` fits kT, kP and the two tapers' J1 by weighted least squares, on the
scipy reference model, to:

| target | POH | weight |
| --- | --- | --- |
| climb at 76 KIAS, sea level | 700 fpm (Fig. 5-6) | 3 |
| static run-up rpm | 2360, the middle of 2300 to 2420 (p. 2-5) | 4 |
| take-off ground roll | 892 ft (Fig. 5-5) | 1 |
| take-off over 50 ft | 1628 ft (Fig. 5-5) | 0.5 |
| climb at 72 KIAS, 8000 ft | 332 fpm (Fig. 5-6) | 0.5 |
| maximum speed, sea level | not above the JSBSim tables' 126.2 KTAS (one-sided) | 3 |

The two half weights are targets the propeller is not the main cause of (above). The fit gives
kT 0.4595, J1 0.7247 (thrust), kP -0.152, J1 0.7253 (power). `c172_data.PROP_FIT` rounds them to
(0.460, 0.725, -0.152, 0.725):

| J | 0 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.725 and up |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C_T scale | 1.460 | 1.439 | 1.379 | 1.292 | 1.193 | 1.101 | 1.033 | 1.001 | 1 |
| C_P scale | 0.848 | 0.855 | 0.875 | 0.904 | 0.936 | 0.967 | 0.989 | 1.000 | 1 |

Take-off runs at J 0 to 0.4, the climbs at about 0.5, cruise and maximum speed at 0.7 to 0.8. The
change stays physically plausible:

* the efficiency J C_T / C_P rises monotonically to the unchanged cruise peak of 0.85 (it is 0.71
  at J = 0.5, was 0.62);
* the static figure of merit, C_T^1.5 / (C_P sqrt(pi / 2)), goes from 0.24 to 0.50, typical of a
  fixed-pitch cruise propeller (a good static propeller reaches about 0.7);
* the static thrust is 2674 N (601 lbf) at 2366 rpm.

`uv run examples/cessna/design/prop_fit.py --check` evaluates both table sets.

### Modes (100 KTAS, 5000 ft, the trim of `cessna-open-loop`)

| mode | scipy (linearised) | bg-sim (fitted on the nonlinear run) |
| --- | --- | --- |
| short period | zeta 0.604, wn 5.96 rad/s | 0.602, 5.97 (alpha over 3 s) |
| phugoid | zeta 0.085, wn 0.254 rad/s (period 24.9 s) | 0.085, 0.2535 (airspeed over 120 s) |
| dutch roll | zeta 0.183, wn 2.16 rad/s | 0.183, 2.158 (sideslip over 12 s) |
| roll | -5.57 1/s (tau 0.18 s) | (dphi/dt)/phi -5.573 at 0.3 s |
| spiral | -0.0107 1/s (stable, half-life 65 s) | -0.0107 at 0 s; the phugoid it excites modulates it later |

Beyond the fits, `expected.json` compares every mode's curve with the nonlinear scipy run at
several instants. They agree to between 1e-8 and 1e-12.

## Sources and licence

* **JSBSim c172p** (https://github.com/JSBSim-Team/jsbsim, read November 2026):
  * the aircraft data, `aircraft/c172p/c172p.xml`: mass balance, ground reactions, control
    limits, flaps and the aerodynamics;
  * the engine, `engine/eng_io320.xml`;
  * the propeller, `engine/prop_75in2f.xml` (the model scales its tables by the POH fit of
    `design/prop_fit.py`; the transcribed tables are kept unchanged);
  * the equations, from `FGPiston.cpp`, `FGPropeller.cpp` and `FGLGear.cpp`.

  The repository is LGPL-2.1. `c172p.xml` says it was built from public data and "guesses",
  contains no proprietary data, is not endorsed by the manufacturer and "is not to be sold".
  `design/c172_data.py` transcribes the numbers (not the files) with this attribution. That data
  file and the model blocks derived from it are distributed under the same LGPL-2.1. Many of the
  stability derivatives are those of the Cessna 182 in J. Roskam, *Airplane Flight Dynamics and
  Automatic Flight Controls*, Appendix B.
* **POH**: the Cessna Model 172P Pilot's Operating Handbook (1981). This covers Figures 5-3
  (stall), 5-5 (take-off), 5-6 (climb), 5-11 (landing) and 3-1 (glide), the Section 1
  specifications, and the static run-up range of the Section 2 powerplant limitations (page 2-5:
  2300 to 2420 rpm at full throttle, carburettor heat off, mixture leaned to maximum rpm).
* **TCDS**: EASA IM.A.051 (Model 172, issue 11) for the geometry, CG limits and control-surface
  travels shared by the 172R/S. The 172P itself is on FAA 3A12, which was not read.

`design/poh.py` lists every reference value with its source and a note.

## Assumptions and simplifications

* There is no p-factor and no slipstream swirl on the fin. The propeller's torque reaction and
  gyroscopic moment are modelled through the rotor.
* The products of inertia are neglected. c172p's empty tensor has none, and the point masses add
  only a small Ixz.
* The elevator and rudder act on the whole propwash dynamic pressure (c172p's build-up). With the
  fitted propeller the static propwash is strong (about 39 m/s at full throttle): with nose-up
  trim, full throttle on the brakes lifts the nose wheel, and since only the wheels touch the
  runway (no tail contact) the aircraft then pitches far up. Keep the trim neutral or nose down
  for a full-power run-up. The FMU check's run-up trims nose down for this reason.
* There is no fuel burn: the mass and CG are fixed at 2400 lb.
* There are no engine temperatures, starter or magnetos. The engine always runs, and idle is
  throttle 0.
* The runway is flat at z = 0 everywhere, with no slope or terrain.
* The wind is a host input. In bg-sim it is calm by default.
* The glide ratio of the POH chart could not be read from the scan. The commonly quoted 9.1 is
  flagged in `design/poh.py`.
* Smoothing constants regularise every switch except the stall hysteresis: the speed and
  shaft-speed floors, the tanh friction and the smooth strut unloading. They are block
  parameters, and the scipy model uses the same values.

## The FMU

`examples/export_cessna.jl` exports `cessna-sim` with the host interface:

* the 16 inputs;
* the 38 outputs: position, quaternion, Euler angles, KIAS, KTAS, vertical speed, altitude and
  height, turn rate, slip, the on-ground flag, alpha and beta, ground speed, rpm, hp, manifold
  pressure, fuel flow, thrust, the surfaces, the steering, the propeller angle, the stall flag,
  the three wheel loads and the autopilot commands;
* the 20 start globals as parameters with ranges.

The analysis picks RK4 at 2.5 ms (2 substeps per 5 ms communication step). doStep takes about
9.5 us, with zero allocations after instantiate.

`uv run examples/export_cessna_check.py` builds the FMU and drives three ground scenarios in fmpy
against bg-sim references: the take-off roll with a rotation, a braked run-up, and nose-wheel
steering in a crosswind. Every output agrees to about 1e-4 of its peak. The one exception is the
stall flag: its threshold switch is evaluated once per step (W203), so it can come one step late.

The host is `apps/cessna-sim`: a Panda3D flight simulator with an airfield, three cameras, a
six-pack panel, and keyboard or joystick, pedal and throttle input.

## Files

| path | what |
| --- | --- |
| `design/c172_data.py`, `c172_si.py` | the transcribed c172p data (LGPL-2.1), the propeller's POH fit, and the SI conversion |
| `design/prop_fit.py` | the least-squares fit of the propeller correction to the POH |
| `design/poh.py` | POH and TCDS reference values with sources |
| `design/c172_ref.py`, `c172_lin.py` | the scipy reference: the full nonlinear model, the trim and the linearisation |
| `design/perf.py`, `demo.py`, `design.py` | performance, the runway start and the demo, and all results into `design.json` |
| `design/build_model.py` | writes both models, the library subsystem `C172Airframe`, the scenes, `bgsim.project.json` and `expected.json` |
| `design/make_meshes.py` | the Cessna meshes (`meshes/*.glb`): the body and the separate control surfaces, nose wheel and propeller |
| `library/*.jl` | the project blocks |
| `library/C172Airframe.bgsub.json` | the open-loop aircraft as a library subsystem (written by `design/build_model.py`) |
