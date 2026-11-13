@@ figures aim9x-airframe
{
  "diagram": {"kind": "diagram", "model": "aim9x-airframe"},
  "scene": {"kind": "scene", "model": "aim9x-airframe", "t": 1.0, "zoom": 2},
  "run": {
    "kind": "plot", "model": "aim9x-airframe", "xlim": [0, 8],
    "rows": [
      {"ylabel": "alpha [deg]", "series": [{"signal": "Air/alpha_deg", "label": "alpha"}]},
      {"ylabel": "q [deg/s]", "series": [{"signal": "Air/q_deg", "label": "q"}]},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Air/vt", "label": "V"}]},
      {"ylabel": "canard [deg]", "series": [{"signal": "Fin1/y", "label": "Fin1"}, {"signal": "Fin4/y", "label": "Fin4"}]}
    ]
  }
}
@@ page aim9x-airframe overview - | Overview
# AIM-9X airframe

The open-loop plant of the AIM-9X: a six-degree-of-freedom rigid body on a multibond bond graph, with a burning solid rocket motor, the four cruciform canards and the standard atmosphere. A short pitch doublet at 0.53 s and a yaw doublet at 4 s excite the airframe; there is no autopilot in this model.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Free](block:Free), [Inertia](block:Inertia), [Motor](block:Motor) | the 6-DOF body, its modulated inertia and the Mk. 36 motor with the propellant outflow `MR`s |
| [Aero](block:Aero) | lift, drag, the canard force and moment, the pitch/yaw/roll damping |
| [CNa](block:CNa), [CD0](block:CD0) | the Mach tables of the normal-force slope and the zero-lift drag |
| [Fin1](block:Fin1) .. [Fin4](block:Fin4) | the four canard servos (position limit before the lag, 200 deg/s rate limit) |
| [Mixer](block:Mixer) | virtual pitch/yaw/roll to the four canards |

The plant is the same in the [autopilot model](model:aim9x-control/overview) and in the [intercept](model:aim9x-intercept/overview).

## What to try

1. Press **Run**: the pitch doublet starts a short-period ring at about 1 Hz, which dies out as the motor burns; the yaw doublet shows the weathercock stability.
2. Raise `dp_amp` on the dashboard: the ring is linear for a few tenths of a degree, then the cubic lift terms show.
3. Set `tvc_on` to 0 or 1: the open-loop model has no TVC command, so this only matters in the closed-loop models.

![alpha, q, speed and the canards|900](@fig:run)

## 3D view

The scene shows the missile at the origin, 3.02 m long, with the seeker window, the fixed tail fins and the olive band in one lofted mesh; the four canards are separate meshes on their hinge axes, so they turn with the servo signals. The nozzle plume scales with the motor thrust and a warm glow sits at the exit. The viewer's reference grid gives the scale.

![The missile at t = 1 s|600](@fig:scene)
@@ page aim9x-airframe results overview | Results
# Results

The short-period mode at the start, from `design/design.py`:

| quantity | value |
| --- | --- |
| natural frequency | 3.44 rad/s |
| damping ratio | 0.128 |
| lift coefficient at alpha 2 deg | 0.1106 |
| load factor at launch, 600 m/s at 3000 m | 0.274 g |

The ring-down in the run is read at the mean condition of the window (500 kPa, 1050 m/s); the fitted mode is 6.28 rad/s and zeta 0.206 against the linear 6.11 rad/s and 0.146. The difference is the thrust and the falling mass, which the linearisation holds fixed.

The motor's ideal vacuum delta-v is 620 m/s (`c ln(m0/mf)`); drag and gravity take most of it back in level flight. The `expected.json` checks the thrust, the burnout mass, the lift, the drag, the atmosphere and the fitted mode.
@@ figures aim9x-control
{
  "diagram": {"kind": "diagram", "model": "aim9x-control"},
  "run": {
    "kind": "plot", "model": "aim9x-control", "xlim": [0, 8],
    "rows": [
      {"ylabel": "acceleration [g]", "series": [{"signal": "Aero/n_z", "label": "n_z"}, {"signal": "Aero/n_y", "label": "n_y"}]},
      {"ylabel": "command [m/s2]", "series": [{"signal": "AP/a_z_cmd_out", "label": "a_z cmd"}, {"signal": "AP/a_y_cmd_out", "label": "a_y cmd"}]},
      {"ylabel": "canard [deg]", "series": [{"signal": "Fin1/y", "label": "Fin1"}, {"signal": "Fin4/y", "label": "Fin4"}]},
      {"ylabel": "TVC [deg]", "series": [{"signal": "AP/tvc_p", "label": "pitch"}, {"signal": "AP/tvc_y", "label": "yaw"}]}
    ]
  }
}
@@ page aim9x-control overview - | Overview
# Rate-command autopilot and TVC

The same airframe under the skid-to-turn autopilot. The guidance command is a specific force; the autopilot turns it into a body-rate command `a/V` and a fast rate loop moves the canards. The gain is scheduled on the square root of dynamic pressure, so the loop stays roughly constant over the boost. A two-axis thrust-vector augmentation takes a small share of the acceleration error while the motor burns.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [AP](block:AP) | roll-angle loop, pitch/yaw rate loop, gain schedule, TVC allocation |
| [AzCmd](block:AzCmd), [AyCmd](block:AyCmd) | a 40 m/s^2 pitch step at 0.5 s and a 20 m/s^2 yaw step at 3 s |
| [Mixer](block:Mixer) | virtual commands to the four canards |
| [Fin1](block:Fin1) .. [Fin4](block:Fin4) | the servos |

## What to try

1. Press **Run**: the pitch step builds about 2.9 g and the yaw step about 0.6 g; the roll loop holds wings level to 0.01 deg.
2. Set `tvc_on` to 0: the boost still flies on the canards alone; the `AP/tvc_p` trace goes to zero.
3. Lower `K_q` in [AP](block:AP): the rate loop slows and the acceleration response lags.

![acceleration, commands, canards and TVC|900](@fig:run)

The `expected.json` checks the command and deflection limits, the roll hold, the fin stops and the TVC gimbal stop.
@@ figures aim9x-intercept
{
  "diagram": {"kind": "diagram", "model": "aim9x-intercept"},
  "run": {
    "kind": "plot", "model": "aim9x-intercept", "xlim": [0, 3.4],
    "rows": [
      {"ylabel": "range [m]", "series": [{"signal": "Seeker/range", "label": "range"}, {"signal": "Status/min_range", "label": "closest so far"}]},
      {"ylabel": "acceleration [g]", "series": [{"signal": "Aero/n_z", "label": "n_z"}, {"signal": "Guide/a_z_cmd", "label": "a_z cmd / g", "scale": 0.10197}]},
      {"ylabel": "speed [m/s]", "series": [{"signal": "Air/vt", "label": "V"}]},
      {"ylabel": "lock", "series": [{"signal": "Seeker/lock", "label": "seeker lock"}]}
    ]
  }
}
@@ page aim9x-intercept overview - | Overview
# Intercept

The full weapon: the airframe and autopilot of the other models, an imaging infrared seeker, proportional navigation and a proximity fuze, against a target aircraft 2 km ahead at 150 m/s. The missile is launched at 400 m/s, 40 m above the target; the motor boosts it to about 970 m/s and the seeker guides it to a proximity kill in 3.3 s.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Target](block:Target) | the target aircraft, its heading and its rear-aspect infrared intensity |
| [Seeker](block:Seeker) | gimbal, field of view, inertial LOS rates, range and closing speed |
| [Guide](block:Guide) | proportional navigation `a = N V_c (omega x u)` with a 15 m/s^2 aerodynamic limit |
| [AP](block:AP) | the rate-command autopilot of the control model |
| [Status](block:Status) | closest approach, proximity fuze and warhead |

## What to try

1. Press **Run**: the range falls from 2 km to the 15 m fuze in 3.3 s; `Status/hit` goes to 1.
2. Set `nav_N` to 2 or 6: the command and the miss distance change; the seeker field of view and the acceleration limit are what finally bound the miss.
3. Move the target with `tgt_x`, `tgt_y`, `tgt_z` or give it a turn with `turn_rate`: the seeker gimbal and the LOS rates move and the fuze time changes.

The 3D view of the airframe and control models shows the missile itself: the canards move with their servos and the plume follows the motor. The target is tracked in the range and seeker plots above.

![range, acceleration, speed and seeker lock|900](@fig:run)

The miss is a **proximity** miss: the fuze fires at 15 m (the continuous-rod warhead's envelope), and the unfuzed trajectory passes inside 13 m of the target.
@@ page @project models - | Models and data
# The AIM-9X example

Four views of one missile:

| model | what it shows |
| --- | --- |
| `aim9x-airframe` | open-loop 6-DOF plant: cubic lift, Mach tables, canards, variable mass and the short-period mode |
| `aim9x-control` | the rate-command autopilot, roll hold, gain schedule and two-axis TVC |
| `aim9x-intercept` | imaging seeker, proportional navigation, proximity fuze and a target |
| `aim9x-fmu` | the host-interface variant for `apps/web`: target inputs, missile outputs, no fuze stop |

The airframe is a slender cruciform missile with **cubic lift** `CN = cna alpha + CN3 alpha^3`, a small static margin (`Cm = -0.8 CN`), Mach-dependent drag and canard control. The motor is a Mk. 36-class boost: 21 kg of propellant in 2.4 s, 235 s vacuum Isp, with the ambient-pressure correction on the nozzle. The body is a `Free3D` joint, a modulated spatial inertia and six outflow `MR` elements, so the mass loss carries its momentum away with it.

The autopilot is deliberately a **rate-command** law: it is robust over the launch envelope, and the guidance limit `a_frac qbar S CN_MAX / m` keeps the demand inside what the airframe can actually deliver. The checks are analytic (thrust, mass, lift, drag, atmosphere, seeker range and irradiance, the PN gain) and a fitted short-period mode, not numbers copied from a run.
