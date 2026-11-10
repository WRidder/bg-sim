# Ingenuity Mars Helicopter

NASA/JPL's Ingenuity, the first aircraft to fly on another planet (19 April 2021), as a bond graph:
a 3D multibond airframe on four landing-gear contacts, two counter-rotating rotors driven by
motor bond graphs, blade-element/momentum (BEMT) rotor aerodynamics fitted to the published JPL
hover test, the flight-control structure of the published guidance-and-control paper, and the
flight of Flight One.

Every number in the model is either **published** (with its source), **digitised** from a published
figure, **fitted** to the JPL hover test, or an **estimate** of this example. The tables below say
which. Mars is $g$ = 3.71 m/s², CO2 at 0.0145 to 0.02 kg/m³; the flights flew at a fixed rotor
speed and controlled thrust with the blade pitch alone.

## Models

| model | what it shows |
| --- | --- |
| `ingenuity` | A demonstration flight on Mars (0.0165 kg/m³, 2537 rpm): take off at 1 s, climb at 1 m/s to 3 m, fly 5 m east, turn 90 deg, descend at 1 m/s and land. Dashboard: density, rotor speed, wind, hover altitude and distance. 3D view with the two counter-rotating rotors. |
| `ingenuity-flight-one` | A replica of Flight One: climb to 3 m, hover, the 96 deg turn, descent at 1 m/s and touchdown, 39 s in the air, in a steady 5 m/s wind from the east-south-east (published: 4-6 m/s, gusting to 8). Checked against the published flight figures (rotor power, collectives, heading). |
| `ingenuity-rotor-stand` | The coaxial rotor on a fixed stand in the JPL 25-ft Space Simulator (CO2 at 0.0175 kg/m³, 2600 rpm): a thrust sweep through the measured range and 5 deg cyclic steps on the lower rotor, the system-identification sequence of the JPL tests. |

Generate everything with

```
uv run examples/ingenuity/design/design.py        # prints the derivation, writes design/design.json
uv run examples/ingenuity/design/build_model.py   # writes models/, scenes/ingenuity.sdf, expected.json
```

## The bond graph

**Airframe (3D multibond).** `World` (`GroundSpatial`) -> `Free` (`Free3D`, quaternion pose) ->
`Body` (`RigidBody3D`, 1.8 kg, Mars gravity in the body). Body frame: $x$ forward (east at
take-off), $y$ left (north), $z$ up, origin at the centre of mass. Everything that acts on the
airframe is bonded to the body's 1-junction:

* the two rotors (`RotorU`, `RotorL`: `Rotor3D`, the spin momentum of each rotor; their torque
  reaction and gyroscopic moment act on the airframe);
* the rotor hub wrenches (`HubWrenchU/L`, `ExternalWrenchSpatial` through `FixedTransform3DNeutral`
  mounts at the hubs): thrust, H-force, cyclic and edgewise-flow hub moments, the aerodynamic torque;
* the airframe drag (`DragWrench` at the fuselage centre, from `Air`);
* four landing-gear feet (`Foot1..4`, Hertz `ContactPoint` with friction on the `Ground`
  `ContactSurface`) through mounts at the feet. They carry the vehicle before take-off and after
  touchdown, so the same model rests, takes off and lands.

**Propulsion (one chain per rotor).** Electrical 1-junction: the winding voltage `Supply` (`MSe`,
set by the rotor-speed governor), the winding and drive losses `Rw` (`R`), a current detector `Amp`
(`Df`) and the motor gyrator `Motor` (`GY`, $k_t$). Mechanical 1-junction `Shaft` at the rotor
speed relative to the airframe: the motor, the rotor's spin momentum (`Rotor3D.drive`) and the
rotor aerodynamics `Aero` (`RotorBEMT`, a nonlinear R with fixed effort-out causality). The motor
inductance is left out (its time constant is far below every other one).

**Aerodynamics.** `RotorBEMT` balances blade-element lift against annulus momentum at 16 stations
along the published blade (chord and twist of Koning et al. 2018), with tip loss, the published
lift slope and zero-lift angle, and an induced-velocity factor of 1.2 (Grip et al. 2017: momentum
theory under-predicts the measured inflow by about 20 %). The lower rotor sees the upper rotor's
uniform inflow (`AeroU.v0 -> AeroL.vext`), the one-way coupling of the JPL flight-dynamics model.
The profile drag polar is the only fitted part (below). The hub moments are quasi-steady: cyclic
($k_c$, the stiff hingeless rotor's 1/rev lift), edgewise flow (the Pitt-Peters inflow gradient
times the factor 2.5 Grip et al. needed to match the swinging-arm test) and the identified on-axis
rate moment ($L_p = M_q \approx$ +0.4 1/s).

**Flight software (signal blocks).** `Plan` (`FlightPlan`, 50 Hz, minimum-jerk moves) ->
`Ctrl` (`FlightControl`, 500 Hz): heave on the symmetric collective, yaw on the antisymmetric
collective, roll and pitch on cyclic (both rotors), horizontal position as an outer loop that
commands roll and pitch. This is the loop structure of Grip et al. (2018); the gains are plain
PID with all poles placed (`design.py`), not the paper's loop shaping. The swashplate servos are
second-order, 12 Hz, 85 % damping (published). `Nav` reads the true pose: the IMU/altimeter/camera
navigation is taken as perfect. `GovU/L` (`RotorGovernor`) hold the rotor speed with a PI law and
back-EMF feedforward, limited to the battery voltage.

## Custom blocks and why

| block | why it is not a stdlib composition |
| --- | --- |
| `RotorBEMT` | a nonlinear constitutive law (a closed-form BEMT annulus balance at 16 stations, profile drag, hub moments): the rotor's R and its hub wrench |
| `AirDrag` | the airframe's air-relative velocity in body axes (pose rotation of the wind) and the quadratic drag law |
| `RotorGovernor` | the rotor-speed controller (PI, feedforward, clamp and anti-windup) |
| `FlightPlan`, `FlightControl`, `StandControl` | guidance and control with real algorithmic content (500 Hz discrete) |
| `Nav`, `Telemetry` | read-outs: Euler angles from the quaternion, coefficients and totals for the plots and checks |

## Parameters and where they come from

References: **Grip17** Grip, Johnson, Malpica, Scharf, Mandić, Young, Allan, Mettler, San Martin,
"Flight Dynamics of a Mars Helicopter", 43rd European Rotorcraft Forum, 2017.
**Grip18** Grip, Scharf, Malpica, Johnson, Mandić, Singh, Young, "Guidance and Control for a Mars
Helicopter", AIAA GNC 2018, AIAA 2018-1849. **Bal18** Balaram, Canham, Duncan, Grip, Johnson, Maki,
Quon, Stern, Zhu, "Mars Helicopter Technology Demonstrator", AIAA SciTech 2018, AIAA 2018-0023.
**Kon18** Koning, Johnson, Allan, "Generation of Mars Helicopter Rotor Model for Comprehensive
Analyses", AHS Specialists' Meeting 2018. **Kon19** Koning, Johnson, Grip, "Improved Mars Helicopter
Aerodynamic Rotor Model for Comprehensive Analyses", AIAA Journal 57(9), 2019. **Dull22** Dull,
Wagner, Young, Johnson, "Hover and Forward Flight Performance Modeling of the Ingenuity Mars
Helicopter", VFS Aeromechanics 2022. **JPLqf** JPL Ingenuity press kit, quick facts (2021).
**NASA21** Grip, "What we're learning about Ingenuity's flight control and aerodynamic
performance", NASA Mars Helicopter blog, 2021. **NASA22** NASA Mars Helicopter blog posts on the
air density and rotor-speed changes (2021-2022).

| parameter | value | status |
| --- | --- | --- |
| mass | 1.8 kg | published (JPLqf, Kon19, Dull22) |
| Mars gravity | 3.71 m/s² | published (Kon19) |
| fuselage box | 13.6 x 19.5 x 16.3 cm | published (JPLqf) |
| leg length, ground clearance, overall height | 0.384 m, 0.13 m, 0.49 m | published (JPLqf) |
| rotor radius, blades | 0.605 m, 2 per rotor, hingeless | published (Grip17, Bal18) |
| rotor spacing | 17 % of R = 0.103 m | published (Grip17) |
| blade chord and twist at 8 stations | Kon18 Table 2 | published (Kon18); tip value extrapolated (estimate) |
| blade mass | 28 g | published (Dull22) |
| lift slope, zero-lift angle | 5.5 /rad, -3.9 deg | digitised (Grip17 Fig. 5) |
| tip loss | lift dropped outboard of 0.97 R | estimate (HeliCAT practice, Grip17) |
| induced-velocity factor | 1.2 | published (Grip17: momentum under-predicts by ~20 %) |
| profile drag polar $c_d = d_0 + d_2 (c_l - 0.25)^2$ | $d_0$ = 0.0428, $d_2$ = 0.0510 | **fitted** to the JPL hover test (Kon19 Fig. 25, digitised: `design/jpl_hover_test.json`); rms 2.8 %, max 4.7 % |
| edgewise-flow gain | 2.5 x Pitt-Peters | published (Grip17) |
| on-axis rate moment | $L_p = M_q$ = +0.4 1/s | published (Grip17, identified 0.4-0.45) |
| apparent roll/pitch inertia | rigid x 1.6 | published (Grip17: flap compliance adds ~60 %) |
| collective range, cyclic range | -4.5..17.5 deg, ±10 deg | published (Bal18) |
| servo dynamics | 2nd order, 12 Hz, ζ 0.85 | published (Grip18) |
| GNC rate | 500 Hz | published (Grip18, Bal18) |
| rotor speed | 2537 rpm (flights 1-13), 2600 rpm (JPL test) | published (NASA21, NASA22, Kon19) |
| air density | 0.0165 (Flight One), 0.0175 (JPL test) kg/m³ | published (NASA21, Kon19) |
| motor + drive efficiency | 78 % | published (Kon18); sets the winding resistance $R_w$ = 0.614 Ω |
| airframe drag area | 0.065 m² | digitised (Dull22 Fig. 20) |
| battery voltage limit | 22 V | estimate inside the published 15-25.2 V range (Bal18) |
| mass distribution, CoM height (0.271 m), inertia | $J$ = (0.0507, 0.0490, 0.0123) kg m² with the 1.6 factor | estimate: component budget around the published total, blade mass and dimensions (`design.py`) |
| rotor plane heights | lower 0.327 m, upper 0.430 m above ground | estimate (from the overall height and the published spacing) |
| rotor spin inertia | 0.00648 kg m² per rotor | estimate (published blade mass along the chord distribution, plus 2e-4 hub) |
| motor torque constant | 0.05 N m/A | estimate (13 V back-EMF at 2537 rpm) |
| governor, flight-controller gains | `design/design.json` | design of this example (pole placement) |
| ground contacts | $k$ = 2e4 N/m (Hertz), $\mu$ = 0.8 | estimate |
| spin directions | upper clockwise, lower counter-clockwise seen from above | estimate (convention; does not change the physics) |

## Validation data and checks

`design/jpl_hover_test.json` (the fit) and `design/validation_data.json` (everything else) hold the
published data with the source of each value. The JPL hover test is used **only** for the polar
fit; the other checks compare against data the model was never tuned to.

| check | published / reference | model (measured on the worker) | tolerance |
| --- | --- | --- | --- |
| Flight One hover rotor power (electrical) | about 210 W (NASA21) | 207.9 W | ±10 % |
| Flight One collective, upper | 8.2 deg (NASA21; JPL pre-flight model 9.0) | 8.61 deg | ±0.8 deg |
| Flight One collective, lower | 9.2 deg (NASA21; JPL pre-flight model 9.9) | 9.87 deg | ±0.8 deg |
| hover thrust | weight 1.8 kg x 3.71 m/s² = 6.678 N | 6.678 N | 0.5 % |
| rotor speed | 2537 rpm | 2537.0 rpm | 0.2 % |
| altitude hold | within about 1 cm | 0.1 mm (perfect navigation) | 1 cm bound |
| heading after the turn | 96 deg, held within 1.5 deg | 96.0 deg | ±1.5 deg |
| position in the wind | variations about 25 cm | 3 cm (steady wind, perfect navigation) | 25 cm bound |
| cyclic in 4-6 m/s wind | generally below 3 deg | 3.29 deg in a steady 5 m/s | 3.5 deg bound |
| flight time | 39.1 s | 39.13 s lift-off to touchdown (the plan is laid out to it) | ±0.5 s |
| peak rotor power | battery peak 510 W (Bal18) | 259 W at take-off (Flight Two's spike: 310 W) | 510 W bound |
| 5 deg cyclic step, lower-rotor hub moment | about 0.55 N m (Grip17 Fig. 15, digitised) | 0.634 N m | ±20 % |
| JPL hover test, $C_P$ on 6 thrust plateaus | Kon19 Fig. 25 (digitised) | within -4.6 % .. +3.3 % | ±6 % (**fit check**) |
| hover trim of `ingenuity` | numpy BEMT trim, `design/rotor_ref.py`: 207.8 W, 8.60 / 9.86 deg | 207.8 W, 8.61 / 9.86 deg | 1 %, 0.05 deg |
| statics on the gear | (W - 0.1 W)/4 per foot, Hertz compression 0.178 mm | 1.508 N, 0.178 mm | 1 %, 0.02 mm |

The power is the electrical power of the two rotor motors; Balaram et al. (2018) budget the whole
vehicle at 360 W for 80 % of a flight and 510 W for 20 %, so the ~210 W of the rotors in hover sits
in that "few hundred watt" class with the avionics and the take-off transients on top.

**Where there is no validation data.** The mass distribution and inertia, the rotor plane heights,
the motor constant, the ground contact and the controller gains are estimates; nothing published
checks them directly (the flight checks depend on them only weakly). No published time history of
a flight is available in numbers, so the flight checks compare steady values and bounds, not
trajectories.

**Cross-checks that are reported, not checked.**

* CAMRAD II collective sweep at Mars condition 2 (Dull22 Fig. 4, `validation_data.json`): the
  model's $C_T$ is 4 % below CAMRAD at 15 deg collective, but 75 % above it at 4 deg (0.0071
  against about 0.004), and it does not stall (0.035 at 24 deg against 0.028). The model's thrust
  slope is about 20 % lower than CAMRAD's.
* Forward flight: Dull et al. trim the vehicle at 2.2 deg pitch at 5 m/s. The model barely tilts
  in wind (0.3 deg): its airframe drag is the published D/q, but the rotors have only the
  profile-drag H-force, not the induced-drag part, so the pitch trim of forward flight is not
  reproduced.
* The power hardly changes with wind in the model: the BEMT inflow sees only the axial airspeed
  (no edgewise inflow reduction). Ingenuity's measured forward-flight power savings are therefore
  not in the model.

## 3D multibond and where it is not used

The airframe is fully 3D multibond (`GroundSpatial`, `Free3D`, `RigidBody3D`), the rotors are
`Rotor3D` elements on the airframe (spin momentum, torque reaction and gyroscopic moment), the
hub and drag forces are `ExternalWrenchSpatial` wrenches through `FixedTransform3DNeutral` mounts,
and the landing gear is four 3D `ContactPoint` feet. There is no planar or scalar variant. Three
things are not multibond elements:

* the blades: their flapping (80-90 Hz, a hingeless rotor) is folded into the apparent inertia
  and the quasi-steady hub moments, as in the published flight-dynamics model; a multibody blade
  model would need the full aeroelastic rotor;
* the rotor aerodynamics: a nonlinear R on the rotor's shaft bond plus a hub wrench (signals into
  `ExternalWrenchSpatial`), because no stdlib element computes rotor aerodynamics;
* the rotor stand: the two `Rotor3D` elements are mounted on `GroundSpatial` through fixed
  mounts, so the stand model is 3D too, but nothing moves except the spin.

## Known limitations

* Navigation is perfect (the controller reads the true pose); Ingenuity's IMU, laser altimeter
  and camera navigation are not modelled.
* The control laws are plain PID/PD with placed poles, not the loop-shaped controllers of
  Grip et al. (2018). All three closed-loop poles of each loop sit at -p (p = 3.5, 4.5, 6 and
  1 rad/s); the crossovers are heave 1.7 Hz, yaw 2.2 Hz, inner roll/pitch 2.9 Hz and position
  0.5 Hz, against the published 1.2, 1.9, 2.6 and 0.3 Hz.
* The cyclic moment has no first-harmonic (Pitt-Peters) inflow: 15 % above the JPL test.
* The motor losses are one resistance, set so that the drive efficiency is the published 78 %
  in hover; at higher load the efficiency drops below 78 % (the JPL test assumed a constant 78 %).
* The 3D view turns the rotors at 1/40 of their speed so the counter-rotation is visible.

## Run time

On the real worker: `ingenuity` (30 s) about 45 s including the compile, `ingenuity-flight-one`
(44 s) about 25 s, `ingenuity-rotor-stand` (38 s) about 10 s; `run_checks.py --only ingenuity`
about 80 s.

## What to try

* `ingenuity`: lower the **air density** towards 0.012 kg/m³ (the density later in the mission).
  The collective climbs towards its 17.5 deg limit; this is why the team raised the rotor speed
  to 2700 rpm. Then raise the **rotor speed** to 2700 rpm and fly again.
* Add **wind** (Flight One saw 4-6 m/s, gusting to 8): the controller holds the attitude with
  cyclic against the edgewise-flow moment; the airframe hardly tilts, because the drag in the thin
  CO2 is tiny, and the power stays the same (see the limitations).
* Compare the collectives in `ingenuity-flight-one` with the published 8.2 / 9.2 deg.
* In `ingenuity-rotor-stand`, plot `Telem/CP` against `Telem/CT` and compare with the measured
  points of `design/jpl_hover_test.json`.
