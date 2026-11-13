@@ figures @project
{
  "diagram": {"kind": "diagram", "model": "lm-descent"}
}
@@ page @project vehicle - | The Apollo 11 lunar module
# The Apollo 11 lunar module

Three models of Eagle, the lunar module of Apollo 11, on one 3D (multibond) bond graph of a rigid body that loses mass:

| model | flight |
| --- | --- |
| [Powered descent](model:lm-descent) | descent-engine ignition (PDI) 15 km up at 1,695 m/s, to touchdown on four footpads 12.6 min later |
| [Landing by hand](model:lm-hover) | the landing phase (P66) flown from the dashboard, with Armstrong's propellant |
| [Ascent](model:lm-ascent) | lift-off from the descent stage to orbit insertion, 7 min 17 s |

![The descent model: the variable-mass body on top, propulsion, guidance and attitude in the middle, the landing gear below|900](@fig:diagram)

## The bond graph

- A `Free3D` joint ties the vehicle's 1-junction `Body` to the ground (`World`).
- `Inertia` (`VariableInertia3D`, a project block) is a **modulated spatial inertia**: its state is the body-frame momentum $P = [h; p]$, and the mass $m(t)$ and principal moments $J(t)$ are input signals from the propellant tank.
- `Coriolis` adds the gyroscopic terms, `Twist` taps the body twist.
- Three `ExternalWrenchSpatial` sources carry the engine thrust, the RCS torques and inverse-square lunar gravity.
- Six `MR` elements `Out1..Out6` on the joint's drive ports have the resistance $r = -\dot m$ (linear) and $r = -\dot J_k$ (angular): the propellant that leaves takes its momentum with it, so $m\,\dot v = F$.
- The descent and hover models add the **landing gear**: four `ContactPoint`s, one per footpad, mounted on `Body` through `FixedTransform3DNeutral`s. Each pad meets the tangent plane of the lunar sphere straight below it (`LunarSurface3D`).

The flight runs in the landing-site frame: x downrange, z up, the Moon's centre at $(0, 0, -R)$. The body axes are the LM's own: X up the thrust axis, Z forward through the hatch.

Continue with [parameters and sources](page:parameters) and [validation](page:validation).
@@ page @project parameters vehicle | Parameters and sources
# Parameters and sources

The README of the example lists every number with its source; `design/data.py` holds them.

- **Published.** Apollo 11 Mission Report (MSC-00171): masses and moments of inertia at PDI, landing, lift-off and insertion; event times; ascent engine thrust and specific impulse; touchdown velocities. *Apollo by the Numbers* (SP-2000-4029): the descent propellant budget (17,414 lb consumed, 770 lb left, 674 lb of it usable). TN D-6846: the throttle logic (10 to 60 %, recovery at 57 %, 26 s at trim), the premission descent profile, the ascent targets. TN D-6850: the footpad radius (167.57 in), the probes, the touchdown envelope, the strut cartridges. Descent engine: rated 10,500 lbf, fixed throttle position 9,870 lbf, specific impulse 305 s.
- **Estimated.** Thrust lags, the attitude loop, the RCS moment arm, the centre of mass above the pads (put at the guidance's 6.4 ft altitude reference), the pad damping.
- **Fitted.** The PDI range to the landing site (481 km; the report says about 260 n mi = 482 km) is fitted to the throttle recovery at 386 s. The braking-phase target is fitted to high gate (7,129 ft at 125 ft/s descent, 507 s). The approach-phase target is fitted to Aldrin's first four callouts. The pad stiffness is chosen so that the LM settles 3 in into the soil (MR: 2.5 to 3.5 in).
- **Pilot model.** In the landing phase the LM follows Aldrin's called descent rates and forward speeds as functions of altitude.

**Limits.** A non-rotating spherical Moon of the mean radius; no centre-of-mass shift and no products of inertia; an ideal saturated RCS loop with no jet logic; no gimbal trim, no slosh, no RCS propellant; rigid struts (the gear is four compliant pads). The 2.1 ft/s lateral drift at touchdown is not modelled.
@@ page @project validation vehicle | Validation
# Validation

`expected.json` checks three things, and every note says which:

1. **An independent integration.** `design/reference.py` integrates the same equations as a 6-DOF rigid body in scipy (quaternion attitude, DOP853 at rtol 1e-10, mode switches as events). The bond-graph models match it to 2e-4 in altitude and speed, 2e-5 in mass, and within 0.1 s in the event times.
2. **Analytic cases.** In vacuum with the thrust held vertical, the ascent stage's speed is Tsiolkovsky's $c \ln(m_0/m)$ to 1e-6. A hover burns $m(t) = m_0 e^{-g t / c}$, so it runs dry at $(c/g)\ln(m_0/m_\text{empty})$ to 0.01 s.
3. **Apollo 11.** Fitted quantities are marked as such; the rest are independent:

| quantity | published | model |
| --- | --- | --- |
| landing | 754.9 s after ignition | 758.3 s |
| mass at engine cutoff | 7,374 kg | 7,427 kg (+0.7 %) |
| usable propellant left | 674 lb = 306 kg | 358 kg |
| velocity gained to touchdown | about 6,775 ft/s | 6,997 ft/s (+3 %) |
| velocity gained to high gate / low gate (premission) | 5,375 / 6,176 ft/s | 5,411 / 6,157 ft/s |
| inertial speed at 176, 258, 384, 402 s (premission) | 4,000, 3,065, 1,456, 1,315 ft/s | within 4 % |
| Aldrin's altitude callouts, 400 ft to 20 ft | ALSJ | within 35 ft at the called times |
| ascent burn | 434.9 s | 437.4 s |
| ascent stage at insertion | 2,689 kg | 2,666 kg |
| orbit after the ascent burn | 88.9 × 16.9 km | 88.3 × 16.9 km |

The descent burns 0.7 % less propellant than Eagle did and gains 3 % more velocity: the model has no gimbal trim, no slosh and no attitude jitter, and Armstrong's 140 s landing phase (104 s nominal) flew pitch and roll excursions that the pilot model leaves out.
@@ figures lm-descent
{
  "diagram": {"kind": "diagram", "model": "lm-descent"},
  "scene": {"kind": "scene", "model": "lm-descent", "t": 757.0, "zoom": 14},
  "profile": {
    "kind": "plot", "model": "lm-descent", "xlim": [0, 775],
    "rows": [
      {"ylabel": "altitude [ft]", "series": [{"signal": "State/h_ft", "label": "h"}],
       "vlines": [{"x": 386.0, "label": "throttle recovery"}, {"x": 507.0, "label": "P64"}, {"x": 617.0, "label": "P66"}]},
      {"ylabel": "velocity [ft/s]", "series": [{"signal": "State/vh_fps", "label": "horizontal"}, {"signal": "State/rdot_fps", "label": "vertical", "style": "--"}], "legend": true},
      {"ylabel": "throttle", "series": [{"signal": "Throttle/throttle", "label": "T / T_rated"}]},
      {"ylabel": "mass [kg]", "series": [{"signal": "Tank/m", "label": "m"}]}
    ]
  },
  "trajectory": {
    "kind": "plot", "model": "lm-descent",
    "rows": [
      {"ylabel": "altitude [km]", "x": "State/s_km", "xlabel": "range to the landing site [km]",
       "series": [{"signal": "State/h_km", "label": "trajectory"}]}
    ]
  },
  "landing": {
    "kind": "plot", "model": "lm-descent", "xlim": [590, 775],
    "rows": [
      {"ylabel": "altitude [ft]", "ylim": [0, 800], "series": [{"signal": "State/h_ft", "label": "model"}],
       "hlines": [{"y": 750, "label": "750"}, {"y": 400, "label": "400"}, {"y": 100, "label": "100"}, {"y": 20, "label": "20"}],
       "vlines": [{"x": 596.0, "label": "callout 750 ft"}, {"x": 621.0, "label": "callout 400 ft"}, {"x": 700.0, "label": "callout 100 ft"}, {"x": 740.0, "label": "callout 20 ft"}, {"x": 754.9, "label": "landing"}]},
      {"ylabel": "descent rate [ft/s]", "series": [{"signal": "State/rdot_fps", "label": "vertical"}, {"signal": "State/vh_fps", "label": "forward", "style": "--"}], "legend": true},
      {"ylabel": "propellant [kg]", "series": [{"signal": "Tank/prop", "label": "usable"}]},
      {"ylabel": "hover time [s]", "series": [{"signal": "Status/hover_left", "label": "left"}]}
    ]
  },
  "touchdown": {
    "kind": "plot", "model": "lm-descent", "xlim": [755, 775],
    "rows": [
      {"ylabel": "pad force [N]", "series": [{"signal": "Pad1/Contact/f_n", "label": "+Y"}, {"signal": "Pad2/Contact/f_n", "label": "-Y", "style": "--"}, {"signal": "Pad3/Contact/f_n", "label": "+Z (forward)"}, {"signal": "Pad4/Contact/f_n", "label": "-Z"}], "legend": true},
      {"ylabel": "tilt [deg]", "series": [{"signal": "State/tilt_deg", "label": "tilt"}]},
      {"ylabel": "pad height [m]", "series": [{"signal": "State/h_pad", "label": "lowest pad"}]}
    ]
  }
}
@@ page lm-descent overview - | Overview
# Powered descent, PDI to touchdown

Eagle's descent engine lit at 102:33:05 GET, 15 km up at 1,695 m/s. Twelve and a half minutes later the LM stood in the Sea of Tranquility. The model flies the three phases of Apollo's descent:

* **Braking (P63).** 26 s at trim thrust, then the fixed throttle position (94 %) until the guidance asks for less than 57 %: the throttle recovery at 386 s. The LM yaws to windows up between 232 and 294 s.
* **Approach (P64)** from high gate at 507 s, 7,129 ft.
* **Landing (P66)** from 617 s, flown by a pilot model that holds Aldrin's called descent rates and forward speeds.

Both P63 and P64 use Apollo's quadratic guidance, $a = a_T + 12 (r_T - r)/t_{go}^2 - 6 (v + v_T)/t_{go}$. The engine stops when a footpad touches the surface.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Free](block:Free), [Body](block:Body), [Inertia](block:Inertia), [Out1](block:Out1)..[Out6](block:Out6) | the variable-mass rigid body (see [the bond graph](project:vehicle)) |
| [Tank](block:Tank), [Engine](block:Engine) | propellant and mass properties; the descent engine with its lag |
| [Throttle](block:Throttle) | trim, fixed throttle position, throttle recovery, shutdown at touchdown |
| [Guid](block:Guid), [Att](block:Att) | the descent guidance and the RCS attitude loop |
| [PilotRate](block:PilotRate), [PilotFwd](block:PilotFwd) | the P66 pilot model from Aldrin's callouts |
| [Windows](block:Windows) | the yaw to windows up |
| [Pad1](block:Pad1)..[Pad4](block:Pad4) | the footpads on the lunar surface (instances of the library subsystem `LunarFoot`) |
| [State](block:State), [Status](block:Status) | altitude, velocities, tilt, pad height; velocity gained, hover time left |

## What to try

1. Press **Run** (about a minute). Watch the throttle drop from the fixed position at 386 s, and the altitude reach high gate at 507 s.
2. Scale the P66 descent rates with `rate_scale`. A slower landing phase burns more of the last propellant: watch the usable propellant and the hover time left at touchdown.
3. Lower the attitude loop's `att_wn` and watch the tilt lag behind the guidance.

![3D view 1.5 s before touchdown|600](@fig:scene)

Continue with [the results](page:results).
@@ page lm-descent results overview | Results
# Results

![Descent: altitude, velocities, throttle, mass|900](@fig:profile)

The braking phase covers 470 km of range and loses most of the 1,695 m/s; the approach phase starts 8.5 km out:

![Trajectory over range|700](@fig:trajectory)

In the landing phase the model follows Aldrin's calls. The vertical lines mark the time of four callouts; the model passes those altitudes close to the calls:

![Landing phase: altitude, rates, propellant, hover time|900](@fig:landing)

At touchdown the LM tilts 4.5° as the horizontal-velocity loop brakes the forward drift. One aft pad touches first, then the LM rocks onto the forward pad and settles level, 3 in into the soil:

![Touchdown: pad forces, tilt, pad height|900](@fig:touchdown)

## Against the published data

| quantity | published | model |
| --- | --- | --- |
| throttle recovery | 386 s | 386.0 s (fitted) |
| high gate | 7,129 ft at −125 ft/s | 7,160 ft at −124 ft/s (fitted) |
| landing | 754.9 s | 758.3 s |
| touchdown vertical / horizontal | 1.7 / 2.1 ft/s | 1.6 / 2.6 ft/s |
| mass at engine cutoff | 7,374 kg | 7,427 kg |
| usable propellant left | 306 kg | 358 kg |
| velocity gained | about 6,775 ft/s | 6,997 ft/s |

The checks compare tightly (2e-4) with the independent scipy integration in `design/reference.py`, and with honest tolerances with the mission data. The forward pad's peak force is about 10 % above the 4,500 lb at which the primary strut's first honeycomb cartridge would crush; on Apollo 11 no primary strut stroked. The model's rigid struts and its 4.5° tilt at contact make that peak; the check holds it against the 9,500 lb second cartridge.
@@ figures lm-hover
{
  "diagram": {"kind": "diagram", "model": "lm-hover"},
  "scene": {"kind": "scene", "model": "lm-hover", "t": 150.0, "zoom": 14},
  "flight": {
    "kind": "plot", "model": "lm-hover", "xlim": [0, 200],
    "rows": [
      {"ylabel": "altitude [ft]", "series": [{"signal": "State/h_ft", "label": "h"}]},
      {"ylabel": "velocity [ft/s]", "series": [{"signal": "State/rdot_fps", "label": "vertical"}, {"signal": "State/vh_fps", "label": "forward", "style": "--"}], "legend": true},
      {"ylabel": "hover time [s]", "series": [{"signal": "Status/hover_left", "label": "left"}]},
      {"ylabel": "pad force [N]", "series": [{"signal": "Pad1/Contact/f_n", "label": "+Y"}, {"signal": "Pad3/Contact/f_n", "label": "+Z", "style": "--"}], "legend": true}
    ]
  },
  "dry": {
    "kind": "plot", "model": "lm-hover", "xlim": [0, 120],
    "settings": {"t_end": 120.0, "output": {"points": 1201}},
    "overrides": {"global:h0_ft": 100.0, "global:rod_fps": 0.0, "global:td_fps": 0.0, "global:fwd_fps": 0.0, "global:prop_start": 300.0},
    "rows": [
      {"ylabel": "altitude [ft]", "series": [{"signal": "State/h_ft", "label": "h"}]},
      {"ylabel": "propellant [kg]", "series": [{"signal": "Tank/prop", "label": "usable"}]},
      {"ylabel": "pad force [N]", "series": [{"signal": "Pad1/Contact/f_n", "label": "+Y"}]}
    ]
  }
}
@@ page lm-hover overview - | Overview
# Landing by hand

The landing phase (P66, "rate of descent") was flown by hand: each click of the commander's switch changed the descent rate by 1 ft/s, and the hand controller tilted the LM to move it. This model starts in a hover with the usable propellant Eagle had at P66 entry (about 960 kg, from the descent model) and lets you fly it from the dashboard:

* the **descent rate** above 100 ft, and the rate at touchdown (the command ramps between them below 100 ft);
* a **forward translation** at a set speed for a set time, then the forward speed is nulled;
* the **hover time left**: how long the usable propellant would hold the LM in a hover.

The guidance is the descent model's P66 loop: the throttle holds the commanded descent rate, and the attitude tilts the thrust to reach the commanded forward speed. The engine stops at touchdown or when the usable propellant is gone.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [RateCmd](block:RateCmd), [FwdCmd](block:FwdCmd) | the pilot's commands from the dashboard |
| [Guid](block:Guid), [Throttle](block:Throttle), [Att](block:Att) | the P66 loops, the engine and the RCS |
| [Pad1](block:Pad1)..[Pad4](block:Pad4) | the footpads (instances of the library subsystem `LunarFoot`) |
| [Status](block:Status) | hover time left, thrust-to-weight ratio |

![3D view after the landing|600](@fig:scene)

Continue with [the results](page:results).
@@ page lm-hover results overview | Results
# Results

The default flight descends at 3.5 ft/s and translates 30 s at 20 ft/s to clear the craters, then lands at 1.7 ft/s with about 107 s of hover time left:

![Default flight|900](@fig:flight)

Hover at 100 ft with 300 kg of usable propellant, and the engine quits after $(c/g)\ln(m_0/m_\text{empty})$ = 76.6 s: the rocket equation of a hover, $m(t) = m_0 e^{-g t/c}$. The LM then falls 100 ft and lands hard on the pads:

![Running dry at 100 ft|900](@fig:dry)
@@ figures lm-ascent
{
  "diagram": {"kind": "diagram", "model": "lm-ascent"},
  "scene": {"kind": "scene", "model": "lm-ascent", "t": 3.0, "zoom": 14},
  "profile": {
    "kind": "plot", "model": "lm-ascent", "xlim": [0, 460],
    "rows": [
      {"ylabel": "altitude [ft]", "series": [{"signal": "State/h_ft", "label": "h"}]},
      {"ylabel": "velocity [ft/s]", "series": [{"signal": "State/vh_fps", "label": "horizontal"}, {"signal": "State/rdot_fps", "label": "radial", "style": "--"}], "legend": true},
      {"ylabel": "tilt [deg]", "series": [{"signal": "State/tilt_deg", "label": "thrust axis from vertical"}]},
      {"ylabel": "mass [kg]", "series": [{"signal": "Tank/m", "label": "m"}]}
    ]
  },
  "orbit": {
    "kind": "plot", "model": "lm-ascent", "xlim": [300, 460],
    "rows": [
      {"ylabel": "height [km]", "ylim": [-50, 120], "series": [{"signal": "Orbit/apolune_km", "label": "apolune"}, {"signal": "Orbit/perilune_km", "label": "perilune", "style": "--"}], "legend": true,
       "hlines": [{"y": 88.9, "label": "MR: 88.9 km"}, {"y": 16.9, "label": "MR: 16.9 km"}]}
    ]
  },
  "vacuum": {
    "kind": "plot", "model": "lm-ascent", "xlim": [0, 300],
    "settings": {"t_end": 300.0, "output": {"points": 601}},
    "overrides": {"global:gravity_scale": 0.0, "global:steer": 0.0},
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "State/speed", "label": "speed, no gravity"}, {"signal": "Status/dv", "label": "c ln(m0/m)", "style": "--"}], "legend": true}
    ]
  }
}
@@ page lm-ascent overview - | Overview
# Ascent to orbit

At 124:22:00 GET the ascent engine fired and the ascent stage left the descent stage on the surface. The model flies TN D-6846's ascent:

* a **vertical rise** until the radial rate reaches 40 ft/s (about 10 s), to clear the descent stage and the terrain;
* the **insertion phase** on Apollo's linear guidance: a radial acceleration that meets 60,000 ft and 32.2 ft/s radial rate when the downrange velocity reaches 5,534.9 ft/s; the ascent engine is not throttleable, so whatever thrust is left goes downrange;
* engine cutoff on the target velocity, anticipating the 0.2 s thrust tail-off.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Tank](block:Tank), [Engine](block:Engine) | the ascent stage's propellant and mass properties; the ascent engine (3,464 lbf, 309.4 s) |
| [Guid](block:Guid), [Att](block:Att) | the ascent guidance and the RCS attitude loop |
| [Orbit](block:Orbit) | apolune and perilune of the current state |
| [State](block:State), [Status](block:Status) | altitude, velocities, tilt; velocity gained |

Set `steer` and `gravity_scale` to 0 and the thrust stays vertical in empty space: the speed is then Tsiolkovsky's $c \ln(m_0/m)$.

![3D view at lift-off: the descent stage stays behind|600](@fig:scene)

Continue with [the results](page:results).
@@ page lm-ascent results overview | Results
# Results

![Ascent: altitude, velocities, tilt, mass|900](@fig:profile)

The orbit's apolune and perilune settle at cutoff, 437 s after lift-off:

![Orbit after insertion|800](@fig:orbit)

| quantity | published | model |
| --- | --- | --- |
| burn time | 434.88 s | 437.4 s |
| mass at insertion | 2,689 kg | 2,666 kg |
| velocity change | 6,070.1 ft/s | 6,036 ft/s |
| orbit | 48.0 × 9.1 n mi (88.9 × 16.9 km) | 88.3 × 16.9 km |

In vacuum, with the thrust held vertical, the speed is $c \ln(m_0/m)$ to 1e-6, which checks the variable-mass bond graph:

![Vacuum: speed and Tsiolkovsky|900](@fig:vacuum)
