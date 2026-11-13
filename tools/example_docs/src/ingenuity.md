@@ figures @project
{
  "diagram": {"kind": "diagram", "model": "ingenuity"},
  "scene": {"kind": "scene", "model": "ingenuity", "t": 12.0, "zoom": 1}
}
@@ page @project vehicle - | Ingenuity Mars Helicopter
# Ingenuity Mars Helicopter

NASA/JPL's Ingenuity made the first powered, controlled flight on another planet on 19 April 2021. This example models it as a bond graph: a 3D multibond airframe on four landing-gear contacts, two counter-rotating rotors driven by motor bond graphs, blade-element/momentum rotor aerodynamics and the flight-control structure of the published guidance-and-control paper. Mars: $g$ = 3.71 m/s², CO2 at 0.012 to 0.02 kg/m³. Ingenuity flies at a fixed rotor speed and controls thrust with the blade pitch alone.

| model | what it shows |
| --- | --- |
| [ingenuity](model:ingenuity) | a demonstration flight: take off, 3 m hover, 5 m east, a 90 deg turn, landing; dashboard with density, rotor speed and wind |
| [ingenuity-flight-one](model:ingenuity-flight-one) | a replica of Flight One, checked against the published flight figures |
| [ingenuity-rotor-stand](model:ingenuity-rotor-stand) | the rotor on a stand in the JPL Space Simulator: thrust sweep and cyclic steps against the test data |

![The demonstration flight, 12 s in: flying east at 3 m|600](@fig:scene)

![The model canvas|900](@fig:diagram)

## The bond graph

- **Airframe (3D multibond).** `GroundSpatial` -> `Free3D` -> `RigidBody3D` (1.8 kg, Mars gravity, apparent roll/pitch inertia). The rotors (`Rotor3D`), the hub wrenches and the drag wrench (`ExternalWrenchSpatial` through `FixedTransform3DNeutral` mounts) and four `ContactPoint` feet are all bonded to the body. The same model rests on the ground, takes off and lands.
- **Propulsion.** Per rotor an electrical 1-junction (`MSe` winding voltage, `R` losses, `Df` current, `GY` motor) and a shaft 1-junction (motor, the rotor's spin momentum in `Rotor3D`, the rotor aerodynamics `RotorBEMT` as a nonlinear R). The rotor's torque reaction and gyroscopic moment reach the airframe through `Rotor3D`.
- **Aerodynamics.** `RotorBEMT` balances blade-element lift and annulus momentum at 16 stations of the published blade (chord and twist, Koning et al. 2018), with the published lift slope, a 20 % induced-velocity correction and tip loss. The lower rotor sees the upper rotor's inflow. The hub moments are quasi-steady: cyclic, edgewise flow (Pitt-Peters times 2.5) and the identified rate moment (Grip et al. 2017).
- **Flight software.** `FlightPlan` (minimum-jerk moves, 1 m/s climb and descent) and `FlightControl` at 500 Hz: heave on the symmetric collective, yaw on the antisymmetric collective, roll and pitch on cyclic, horizontal position as an outer loop (the loop structure of Grip et al. 2018). Servos: 12 Hz, 85 % damping (published). Navigation is taken as perfect.

Continue with [the parameters](project:parameters) and [the validation](project:validation).
@@ page @project parameters vehicle | Parameters and sources
# Parameters and sources

Every number is **published** (source), **digitised** from a published figure, **fitted** to the JPL hover test, or an **estimate** of this example. `design/ingenuity_data.py` tags each one; the README has the full table and references.

| quantity | value | status |
| --- | --- | --- |
| mass, gravity | 1.8 kg, 3.71 m/s² | published |
| rotor | 2 x 2 blades, R = 0.605 m, 17 % R apart | published |
| blade chord and twist | 8 stations | published (Koning et al. 2018) |
| lift slope, zero-lift angle | 5.5 /rad, -3.9 deg | digitised (Grip et al. 2017) |
| induced-velocity factor, edgewise gain, rate moment, apparent inertia | 1.2, 2.5, +0.4 1/s, x 1.6 | published (Grip et al. 2017) |
| profile drag polar | $d_0$ = 0.0428, $d_2$ = 0.0510 | **fitted** to the JPL hover test |
| collective / cyclic range, servos | -4.5..17.5 deg / ±10 deg, 12 Hz | published (Balaram 2018, Grip 2018) |
| rotor speed, density | 2537 rpm, 0.0165 kg/m³ (Flight One) | published |
| motor + drive efficiency | 78 % | published (Koning 2018) |
| airframe drag area | 0.065 m² | digitised (Dull et al. 2022) |
| mass distribution, inertia, rotor heights, motor constant, gains | | estimates (`design/design.py`) |

The only fit is the profile-drag polar ($c_d = d_0 + d_2 (c_l - 0.25)^2$) to the measured power of the JPL hover test (rms 2.8 %, max 4.7 %).
@@ page @project validation vehicle | Validation
# Validation

Published data the checks compare against (`design/validation_data.json`, `design/jpl_hover_test.json`):

| quantity | published | model | check |
| --- | --- | --- | --- |
| Flight One hover rotor power | about 210 W (electrical) | 208 W | ±10 % |
| Flight One collectives, upper / lower | 8.2 / 9.2 deg (JPL pre-flight model: 9.0 / 9.9) | 8.61 / 9.87 deg | ±0.8 deg |
| hover thrust | weight 1.8 x 3.71 = 6.678 N | 6.678 N | 0.5 % |
| cyclic in 4-6 m/s wind | generally below 3 deg | 3.3 deg at a steady 5 m/s | at most 3.5 deg |
| 5 deg cyclic step, lower rotor hub torque | about 0.55 N m (JPL test) | 0.634 N m | ±20 % |
| JPL hover test $C_P(C_T)$ | 20 measured points | within 5 % | ±6 % (a fit check) |

**Not checked.** The CAMRAD II collective sweep of Dull et al. (2022) at Mars condition 2: the model is 4 % below it at 15 deg collective but makes 75 % more thrust at 4 deg, and it has no stall above about 18 deg. Forward-flight trim (2.2 deg pitch at 5 m/s, Dull et al.) is not reproduced: the model's rotor has no H-force from induced drag. Wind changes the hover power very little in the model, because the BEMT inflow only sees the axial airspeed.
@@ figures ingenuity
{
  "diagram": {"kind": "diagram", "model": "ingenuity"},
  "takeoff": {"kind": "scene", "model": "ingenuity", "t": 4.0, "zoom": 4},
  "east": {"kind": "scene", "model": "ingenuity", "t": 13.0, "zoom": 1},
  "turn": {"kind": "scene", "model": "ingenuity", "t": 19.0, "zoom": 1},
  "flight": {
    "kind": "plot", "model": "ingenuity", "xlim": [0, 30],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Nav/alt", "label": "altitude"}, {"signal": "Nav/x", "label": "east"}, {"signal": "Plan/alt_sp", "label": "altitude set-point", "style": ":"}], "legend": true, "legend_loc": "upper left"},
      {"ylabel": "heading [deg]", "series": [{"signal": "Nav/yaw_deg", "label": "heading"}]},
      {"ylabel": "collective [deg]", "series": [{"signal": "Telem/coll_u_deg", "label": "upper"}, {"signal": "Telem/coll_l_deg", "label": "lower"}], "legend": true},
      {"ylabel": "power [W]", "series": [{"signal": "Telem/P_el", "label": "electrical"}, {"signal": "Telem/P_shaft", "label": "shaft"}], "hlines": [{"y": 210.0, "label": "Flight One: 210 W"}], "legend": true}
    ]
  }
}
@@ page ingenuity overview - | Overview
# Ingenuity: a demonstration flight

Ingenuity takes off at 1 s, climbs at 1 m/s to 3 m, flies 5 m east in 8 s, turns 90 deg, descends at 1 m/s and lands on the yellow pad, all at Flight One's density (0.0165 kg/m³) and rotor speed (2537 rpm). See [the vehicle](project:vehicle) for the model and [the validation](project:validation) for the published data.

![The model canvas|900](@fig:diagram)

![Climbing: t = 4 s|300](@fig:takeoff) ![Flying east: t = 13 s|300](@fig:east) ![Turning: t = 19 s|300](@fig:turn)

![The flight|900](@fig:flight)

## What you see

- On the ground the rotors spin at ground-idle collective: the four feet ([Foot1](block:Foot1) to `Foot4`, instances of the library subsystem `ContactFoot`) carry 90 % of the weight ([Foot1/Contact/f_n](signal:Foot1/Contact/f_n)).
- In hover the collectives are 8.6 deg (upper) and 9.9 deg (lower) ([Telem/coll_u_deg](signal:Telem/coll_u_deg), [Telem/coll_l_deg](signal:Telem/coll_l_deg)): the lower rotor works in the upper rotor's wake and needs more pitch for the same torque. The rotors take 208 W of electrical power ([Telem/P_el](signal:Telem/P_el)), Flight One measured about 210 W.
- The heading turn is made with the antisymmetric collective alone; the rotor speed ([GovL/speed_rpm](signal:GovL/speed_rpm)) never changes.
- In the 3D view the rotors turn at 1/40 of their real speed (42 rev/s), so the counter-rotation is visible; the orange blade tips mark it.

## What to try

- Lower the **air density** to 0.012 kg/m³ (the late-mission Martian summer): the collective climbs towards its 17.5 deg limit. Then raise the **rotor speed** to 2700 rpm, as the team did.
- Add **wind**: the controller holds position with cyclic, the airframe barely tilts (the drag on Mars is tiny).

## Key parameters

The globals `rho`, `rpm_set`, `wind_e`, `wind_n`, `alt` and `dist` are on the dashboard.
@@ figures ingenuity-flight-one
{
  "diagram": {"kind": "diagram", "model": "ingenuity-flight-one"},
  "hover": {"kind": "scene", "model": "ingenuity-flight-one", "t": 25.0, "zoom": 1},
  "flight": {
    "kind": "plot", "model": "ingenuity-flight-one", "xlim": [0, 44],
    "rows": [
      {"ylabel": "altitude [m]", "series": [{"signal": "Nav/alt", "label": "altitude"}], "hlines": [{"y": 3.0, "label": "3 m"}]},
      {"ylabel": "heading [deg]", "series": [{"signal": "Nav/yaw_deg", "label": "heading"}], "hlines": [{"y": 96.0, "label": "96 deg"}]},
      {"ylabel": "collective [deg]", "series": [{"signal": "Telem/coll_u_deg", "label": "upper"}, {"signal": "Telem/coll_l_deg", "label": "lower"}], "hlines": [{"y": 8.2, "label": "flight: upper 8.2"}, {"y": 9.2, "label": "flight: lower 9.2"}], "legend": true},
      {"ylabel": "power [W]", "series": [{"signal": "Telem/P_el", "label": "electrical"}], "hlines": [{"y": 210.0, "label": "flight: 210 W"}], "legend": true},
      {"ylabel": "cyclic [deg]", "series": [{"signal": "Telem/cyc_deg", "label": "cyclic"}], "hlines": [{"y": 3.0, "label": "flight: below 3 deg"}]}
    ]
  }
}
@@ page ingenuity-flight-one overview - | Overview
# Flight One, 19 April 2021

The first flight on Mars: climb at 1 m/s to 3 m, hover, turn 96 deg, descend at 1 m/s and touch down, 39.1 s in the air, at 0.0165 kg/m³ and 2537 rpm. The model flies it in a steady 5 m/s wind from the east-south-east (the weather station saw 4-6 m/s, gusting to 8). See [the validation](project:validation) for the published figures.

![The model canvas|900](@fig:diagram)

![Hovering after the turn: t = 25 s|500](@fig:hover)

![Flight One against the published figures|900](@fig:flight)

## What you see

- Hover power [Telem/P_el](signal:Telem/P_el) 208 W against the published 210 W.
- Collectives [Telem/coll_u_deg](signal:Telem/coll_u_deg) 8.6 deg and [Telem/coll_l_deg](signal:Telem/coll_l_deg) 9.9 deg against the flown 8.2 and 9.2 deg. JPL's pre-flight model predicted 9.0 and 9.9 deg; the flight needed 0.7 to 0.8 deg less, so the real rotor makes a little more thrust than both models.
- The wind needs 3.3 deg of cyclic ([Telem/cyc_deg](signal:Telem/cyc_deg)) to cancel the edgewise-flow moment; the published cyclic was "generally below 3 deg".
- Heading [Nav/yaw_deg](signal:Nav/yaw_deg) settles on 96 deg.

## What to try

Change the wind on the dashboard; set it to zero and the cyclic drops to zero, the power stays the same.
@@ figures ingenuity-rotor-stand
{
  "diagram": {"kind": "diagram", "model": "ingenuity-rotor-stand"},
  "sweep": {
    "kind": "plot", "model": "ingenuity-rotor-stand", "xlim": [0, 38],
    "rows": [
      {"ylabel": "C_T", "series": [{"signal": "Telem/CT", "label": "C_T"}, {"signal": "Stand/ct_sp", "label": "target", "style": ":"}], "legend": true},
      {"ylabel": "C_P", "series": [{"signal": "Telem/CP", "label": "C_P"}]},
      {"ylabel": "collective [deg]", "series": [{"signal": "Telem/coll_u_deg", "label": "upper"}, {"signal": "Telem/coll_l_deg", "label": "lower"}], "legend": true},
      {"ylabel": "hub moment [N m]", "series": [{"signal": "AeroL/tx", "label": "roll (x)"}, {"signal": "AeroL/ty", "label": "pitch (y)"}], "hlines": [{"y": 0.55, "label": "JPL test: 0.55"}, {"y": -0.55, "label": "_nolegend_"}], "legend": true}
    ]
  }
}
@@ page ingenuity-rotor-stand overview - | Overview
# The rotor on the JPL test stand

The coaxial rotor on a fixed stand in the JPL 25-ft Space Simulator: CO2 at 0.0175 kg/m³, 2600 rpm (Koning et al. 2019). [Stand](block:Stand) steps the thrust coefficient through the measured range with a PI law on the symmetric collective and trims the pair torque-free with the differential collective. From 16 s it applies 5 deg cyclic steps on the lower rotor (pitch, then roll), the system-identification sequence of Grip et al. (2017).

![The model canvas|900](@fig:diagram)

![Thrust sweep and cyclic steps|900](@fig:sweep)

## What you see

- [Telem/CP](signal:Telem/CP) on each plateau of [Telem/CT](signal:Telem/CT) lies within 5 % of the measured hover test. This is where the profile-drag polar was fitted, so it is a consistency check.
- The 5 deg cyclic steps give 0.634 N m of hub moment ([AeroL/ty](signal:AeroL/ty), [AeroL/tx](signal:AeroL/tx)); the test measured about 0.55 N m. The quasi-steady model has no first-harmonic inflow, which would oppose the cyclic moment.
- The electrical power ([Telem/P_el](signal:Telem/P_el)) reaches 590 W at the highest thrust; the stand's supply is set to 25.2 V, the pack's full-charge voltage.

## What to try

Plot [Telem/CP](signal:Telem/CP) against [Telem/CT](signal:Telem/CT) and compare it with `design/jpl_hover_test.json`. Lower the chamber density on the dashboard: the coefficients stay the same, the forces scale with the density.
