# F-16

The nonlinear F-16 of Stevens & Lewis on a multibond rigid body: open-loop modes against the book, a gain-scheduled pitch fly-by-wire, envelope protection and a pilot-induced oscillation.

The airframe is the model of B. L. Stevens and F. L. Lewis, *Aircraft Control and Simulation*
(2nd ed., Section 3.6 and Appendix A), built on the low-speed wind-tunnel data of NASA TP-1538
(Nguyen et al., 1979): the book's mass and inertia, the NASA coefficient tables, the F100 engine
with its power-level lag, and the book's standard-atmosphere fit. Everything is in SI inside
bg-sim; the design scripts work in the book's ft/slug units and convert.

## Models

| model | what it shows |
| --- | --- |
| `f16-open-loop` | Three aircraft trimmed at the book's point (502 ft/s, sea level) with the CG at 0.30, 0.35 and 0.38 of the mean chord, each released on its own mode. A30 (forward CG) has a stable short period, A35 and A38 a real unstable pole (+0.102 and +0.657 1/s), read live by `GrowthRate` blocks. A30 also carries an energy ledger. |
| `f16-fbw` | The aft-CG (0.38, statically unstable) F-16 at 400 ft/s, 25 000 ft under a pitch-rate command law whose gains are scheduled on dynamic pressure and Mach (three stdlib `Lookup2D` tables), next to the same law with the gains of a 1000 ft/s, 2000 ft point frozen. Sliders for the step and the CG. |
| `f16-envelope` | Full aft stick (11 g asked) at 900 ft/s, 5000 ft through a g-command path with a min-select alpha/g limiter, on and off. Protected: alpha stays below 17.3 deg and nz below 8.84 g through the loop. Unprotected: 10.1 g, then the slow top of the loop departs to more than 80 deg alpha. Sliders for the stick and the limiter; gauges. |
| `f16-pio` | An aggressive pilot (gain 3/s on the pitch-attitude error, 0.25 s delay) captures a 7 deg attitude change through the 60 deg/s rate-limited stabilator. Plain rate limit: a growing, rate-saturated oscillation (attitude error 29 -> 36 -> 41 deg peak-to-peak per 2 s). With a phase-compensated rate limiter: damped (7 -> 2.2 -> 0.45 -> 0.14 deg). |

Every model has a 3D scene: an F-16 built from simple solids (`design/make_meshes.py`: lofted
fuselage, chin intake, bubble canopy, cropped-delta wing with the leading-edge extension, wingtip
missiles, single fin, ventral fins) whose stabilators turn with the servo, a scrolling reference
floor and a trail of the flight path. The view keeps the first aircraft framed by moving the world
around it (blocks `F16View` and `F16Trail`), so the camera never has to chase an aircraft that
covers kilometres.

## Validation (design/design.py, an independent scipy implementation)

| quantity | here | book / reference |
| --- | --- | --- |
| state derivatives at the book's check point (Table 3.5-2, xcg 0.4) | all 13 within 3.9e-7 relative | Stevens & Lewis |
| trim 502 ft/s, sea level, xcg 0.30: alpha, throttle, elevator | 0.03936 rad, 0.1485, -1.931 deg | 0.03936, 0.1485, -1.931 (Table 3.6-3) |
| trim xcg 0.35 | 0.03691, 0.1385, -0.7588 | 0.03691, 0.1385, -0.7588 |
| trim xcg 0.38 | 0.03544, 0.1325, -0.0559 | 0.03544, 0.1325, -0.0559 |
| short period, xcg 0.30 | -1.2038 +- 1.4922j | -1.2039 +- 1.4922j |
| phugoid, xcg 0.30 (4-state) | -0.0087 +- 0.0740j | -0.0087 +- 0.0740j |
| xcg 0.35 / 0.38, 6-state | real poles +0.1021 / +0.6572 1/s | statically unstable |
| bg-sim open loop vs scipy | alpha, q within 1e-4 deg over 5 s; growth rate 0.65723 at 1 s | 0.65722 |
| bg-sim closed loops vs scipy | FBW 3e-5 deg/s; envelope and PIO within 0.1 % of the range | |

The xcg = 0.35 airframe is *not* stable in the 6-state linearisation (a slow real pole at
+0.102 1/s; the short period itself has split into two real poles). The stable case of the
open-loop model is therefore the forward CG 0.30.

The book's mass is 636.94 slug = 9295.4 kg (weight 20 500 lb); the inertias are Jxx = 9496,
Jyy = 55 814, Jzz = 63 100, Jxz = 982 slug ft^2. The product of inertia tilts the principal axes
1.05 deg about y, so the `RigidBody3D` sits on its principal axes and a `FixedTransform3DNeutral`
applies the aerodynamic wrench in the geometric body frame.

## Fly-by-wire

    q_stick = g0/Vt (1 + 10 stick - cos(gamma) cos(phi))          g-command (deg/s)
    q_cmd   = min(q_stick, 3 (25 - alpha), g0/Vt (9 - cos gamma cos phi) + 4 (9 - nz))   limiter on
    u       = Ka alpha + Kq (q - 0.5 q_cmd) + xi,   xi' = Ki (q - q_cmd) + (sat(u) - u)/0.1
    servo   x' = clamp(20.2 (clamp(u, +-25) - x), +-60)

Ka, Kq, Ki come from an LQR design on the short-period model plus the integral of the pitch-rate
error, at 5 x 5 points over qbar = 80..1400 psf and Mach 0.2..1.0 (`design/fbw.py`). The control
weight is normalised by the elevator effectiveness, so the gains fall roughly as 1/qbar. Every
grid point: closed-loop poles left of -0.068, pitch-rate step rise 0.21..0.60 s, overshoot below
5.2 %. The PIO compensator is `y' = clamp(du/dt + k (u - y), +-60 deg/s)`, k = 0.5 1/s: the output
reverses as soon as the command does, where a plain rate limiter waits for the command to cross it.

## Limitations

* The NASA TP-1538 data are low speed: there is no Mach dependence in the aerodynamics (the
  book says so). The Mach axis of the gain schedule still matters, because qbar/Vt sets the lift
  and damping terms. Above about Mach 0.6 the results are those of the book's model, not of a real
  F-16.
* The tables end at alpha 45 deg and beta 30 deg; bg-sim's `Lookup2D` holds the edge values
  beyond, so the post-departure motion of the unprotected aircraft and of the plain PIO case is
  qualitative only.
* The lateral-directional axes are open loop (aileron and rudder at zero). All scenarios are
  symmetric pull-ups, so they stay wings level.
* Commands change over 0.05 s ramps (the throttle over 0.2 s) rather than steps: a step that
  pushes a saturation across its corner at the same instant makes bg-sim's event handling
  chatter (W206). The engine's RTAU is written as a `clamp` on the two continuous branches for the
  same reason.
* The CG slider of `f16-fbw` keeps the start state of the 0.38 trim: another CG starts slightly out
  of trim and the integrator takes it out.
* The wing-bending notch of the plan is not part of this example.

## Files

| file | content |
| --- | --- |
| `design/f16_data.py` | the NASA tables (AeroBenchVV transcription, with the textbook values of CL at alpha 15..25 and CZ at alpha 5 and 20 restored) |
| `design/f16_ref.py` | the book's F16 subroutine in ft units (the reference model) |
| `design/f16_si.py`, `f16_lin.py` | SI conversion, principal axes, start states; trim and linearisation |
| `design/fbw.py`, `closedloop.py`, `scenarios.py` | the gain design and the nonlinear closed-loop references |
| `design/design.py` | runs everything and writes `design/design.json` |
| `design/build_model.py` | writes the models, scenes, `library/F16Trail.jl` and `expected.json` |
| `design/make_meshes.py` | writes `meshes/*.glb` |
| `library/` | `F16AirData`, `F16Forces`, `F16Engine`, `F16Energy`, `GrowthRate`, `GCommand`, `PitchFBW`, `F16View`, `F16Trail` |

    uv run examples/f16/design/design.py
    uv run examples/f16/design/build_model.py
    uv run examples/f16/design/make_meshes.py
    uv run examples/run_checks.py --only f16
