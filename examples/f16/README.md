# F-16

The nonlinear F-16 of Stevens & Lewis on a multibond rigid body: open-loop modes against the book, a gain-scheduled pitch fly-by-wire, envelope protection, a pilot-induced oscillation, and a flyable three-axis fly-by-wire F-16 that exports as the FMU of a flight-simulator host.

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
| `f16-sim` | The flyable F-16: a three-axis fly-by-wire at 500 ft/s, 10 000 ft (CG 0.35). Pitch: g command with turn compensation and the alpha/g limiter. Roll: roll-rate command about the velocity vector, with a limit that falls with nz and at low qbar. Yaw: yaw damper, aileron-rudder interconnect and a pedal sideslip command. All gains are scheduled on qbar and Mach. Its inputs, outputs, trim, CG, mass and law switches are the FMU interface of `apps/f16-sim`. The default run is a coordinated 60 deg turn. Sliders for the sticks, pedals, throttle and switches; the flaperons and the rudder move in 3D. |
| `f16-pio` | An aggressive pilot (gain 3/s on the pitch-attitude error, 0.25 s delay) captures a 7 deg attitude change through the 60 deg/s rate-limited stabilator. Plain rate limit: a growing, rate-saturated oscillation (attitude error 29 -> 36 -> 41 deg peak-to-peak per 2 s). With a phase-compensated rate limiter: damped (7 -> 2.2 -> 0.45 -> 0.14 deg). |

Every model has a 3D scene: an F-16 built from simple solids (`design/make_meshes.py`: lofted
fuselage, chin intake, bubble canopy, cropped-delta wing with the leading-edge extension, wingtip
missiles, single fin, ventral fins) whose stabilators turn with the servo, a scrolling reference
floor and a trail of the flight path. The view keeps the first aircraft framed by moving the world
around it (blocks `F16View` and `F16Trail`), so the camera never has to chase an aircraft that
covers kilometres. In `f16-sim` the wing and the fin have cut-outs, and the flaperons (the
ailerons) and the rudder are separate meshes (`meshes/f16sim_*.glb`) that turn on their hinge lines.

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

## Three-axis law (f16-sim)

    pitch   n_cmd  = 1 + 10 stick (aft) or 1 + 4 stick (forward) + tc,  tc = 1/cos(phi) - 1 (faded beyond 60 deg)
            q_stick = g0/Vt (dn_cmd + 2 clamp(dn_cmd - dn, +-0.5)),  dn_cmd = n_cmd - cos(gamma) cos(phi),
                                                                     dn = nz - cos(theta) cos(phi)
            q_cmd  = max(min(q_stick, q_alpha, q_g), q_neg)   then PitchFBW (Ka, Kq, Ki over qbar, Mach)
    roll    ps = p cos(alpha) + r sin(alpha)                   (stability axis: roll about the velocity vector)
            p_lim = 240 clamp(qbar/12 kPa, 0.3, 1) clamp(1 - 0.075 (nz - 1), 0.4, 1)   deg/s
            ail = Kp (ps - 0.5 p_lim stick) + xi_p,   xi_p' = Kip (ps - p_cmd) + anti-windup
    yaw     rdr = Kari(alpha) ail + Kr r_wo + Kb (beta - beta_cmd) + xi_b,   xi_b' = Kib (beta - beta_cmd) + anti-windup
            r_wo = rs through a 1 s washout,  beta_cmd = -6 deg per unit pedal
    servos  stabilator +-25 deg 60 deg/s, ailerons +-21.5 deg 80 deg/s, rudder +-30 deg 120 deg/s, all 20.2 rad/s

`design/lateral.py` designs the lateral gains at the 5 x 5 points of the pitch schedule (CG 0.38).
`Kp` and `Kip` place the roll loop at 4 rad/s, damping 0.8. `Kr`, `Kb` and `Kib` come from a joint
Nelder-Mead optimisation on the 9-state closed loop: the integrated error of a sideslip step, plus
the sideslip of a roll, with a penalty when the dutch-roll damping falls below 0.6. The ARI gain is
`(tan(alpha) L'da - N'da) / (N'dr - tan(alpha) L'dr)` over alpha, clamped to [-1, 2].

Over the grid, the full law gives a dutch-roll damping of at least 0.6 and a roll-rate rise of
0.35..0.55 s. The g-error term of the pitch command builds the load factor of a turn in about half
a second, which cuts the altitude loss of a 60 deg turn over 30 s from about 160 m to 45 m. The
clamp keeps full-stick pulls from overdriving the alpha limiter.

`design/sim3.py` is the nonlinear three-axis reference: RK4 at 1 ms, the stimulus at the stage
times, central-difference linearisation. `design/simscen.py` runs the scenarios that
`expected.json` checks bg-sim against. At 500 ft/s and 10 000 ft:

| check | reference | in bg-sim |
| --- | --- | --- |
| dutch roll, airframe alone (linearised) | zeta 0.124, wn 2.76 rad/s | fitted to beta after a 5 deg rudder kick: 0.124, 2.764 |
| dutch roll, yaw damper alone | zeta 0.524, wn 1.31 rad/s | 0.524, 1.312 |
| dutch roll, full law (without the yaw damper) | zeta 0.909, wn 3.28 (-0.044: unstable) | the kick has died out after 3 s |
| roll-rate step, quarter stick (52.6 deg/s) | | rise 0.45 s, overshoot 2.2 % |
| full-stick roll | 217 deg/s, limit 219; peak sideslip 1.5 deg | |
| coordinated 60 deg turn, stick centred, throttle 0.33 | peak sideslip 0.57 deg, 2 g, altitude -45 m in 30 s | cursor values within 0.01 g, 1 m |
| full-stick roll at 260 ft/s (alpha 15.7 deg) | peak sideslip 3.1 deg about the velocity vector, 7.1 deg about the body axis without ARI | |
| full aft stick | alpha peak 26.6 deg, 5.7 g | |

`dutch roll` uses the run-check kind `damping`: a damped sinusoid fitted to a signal by variable
projection (`examples/run_checks.py`).

## The FMU

`f16-sim` has the host interface as export markers:

* Inputs (`ExportInputPass`, which pass the model's test stimulus through in bg-sim): `stick_pitch`,
  `stick_roll`, `pedals` (-1..1), `throttle` (0..1), and the wind `wind_n`, `wind_e`, `wind_d` (m/s).
* Outputs (`ExportOutput`): position (north, east, altitude), quaternion, Euler and path angles,
  body rates and velocities, vertical speed, TAS, CAS, Mach, qbar, alpha, beta, nz, ny, the three
  surfaces, power, thrust, the roll-rate limit, the commanded nz, and the limiter, departure and
  ground flags.
* FMU parameters (exposed globals with ranges): `vt0`, `h0`, `alpha0`, `el0`, `thtl0` (a trim:
  set them together), `xcg`, `mass`, and the switches `limiter`, `turn_comp`, `roll_law`,
  `yaw_damper`, `beta_hold`, `ari`, `vv_roll`. The start state (quaternion, momenta, engine power)
  is a set of expressions of these globals, recomputed at initialization.

    uv run examples/export_f16_check.py        # export, references, build, fmpy comparison

The analysis picks RK4 with one 5 ms step per 5 ms communication step. `doStep` takes 3.5 us on
average (95 us at most), with no allocations after instantiation. fmpy drives the FMU through four
manoeuvres and compares it with bg-sim runs that the same inputs drive. The worst deviation is
relative to each signal's peak:

| manoeuvre | worst output | alpha | phi | nz | altitude |
| --- | --- | --- | --- | --- | --- |
| pitch doublet | 8.3e-4 (stabilator) | 1.2e-3 deg | 9e-7 deg | 5.3e-4 g | 4.8 mm |
| roll and roll back | 1.3e-3 (stabilator) | 3.9e-4 deg | 6.5e-4 deg | 2.7e-4 g | 0.2 mm |
| coordinated turn | 5.6e-4 (aileron) | 2.5e-5 deg | 6.8e-4 deg | 1.1e-5 g | 0.8 mm |
| throttle step and pedals | 7.4e-3 (power) | 5.7e-4 deg | 2.9e-4 deg | 5.8e-5 g | 1 cm |

The power level crosses military power, where the engine lag switches its rate. The FMU evaluates
that switch once per step, so it can come up to 5 ms late (W203). `apps/f16-sim` is the host: see
its README.

## Limitations

* The NASA TP-1538 data are low speed: there is no Mach dependence in the aerodynamics (the
  book says so). The Mach axis of the gain schedule still matters, because qbar/Vt sets the lift
  and damping terms. Above about Mach 0.6 the results are those of the book's model, not of a real
  F-16.
* The tables end at alpha 45 deg and beta 30 deg; bg-sim's `Lookup2D` holds the edge values
  beyond, so the post-departure motion of the unprotected aircraft and of the plain PIO case is
  qualitative only.
* In `f16-open-loop`, `f16-fbw`, `f16-envelope` and `f16-pio` the lateral-directional axes are
  open loop (aileron and rudder at zero). These scenarios are symmetric pull-ups, so they stay
  wings level. `f16-sim` closes all three axes.
* `f16-sim`: a centred stick holds the load factor of a level turn, not the altitude, so the path
  of a steep turn sags slowly (45 m in 30 s at 60 deg). There is no autopilot. At low speed (260
  ft/s) a full-stick roll saturates the rudder; the departure flag of `F16Status` (alpha above 35
  or below -15 deg, |beta| above 15 deg) is only an indication for the host. The trim globals must
  come from a trim (`design/simscen.py`, or the host's start list): another combination starts out
  of trim.
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
| `design/lateral.py`, `sim3.py`, `simscen.py` | f16-sim: the lateral gain design, the three-axis reference and its scenarios |
| `design/design.py` | runs everything and writes `design/design.json` |
| `design/build_model.py` | writes the models, scenes, `library/F16Trail.jl` and `expected.json` |
| `design/make_meshes.py` | writes `meshes/*.glb` |
| `library/` | `F16AirData` (with wind inputs), `F16Forces`, `F16Engine`, `F16Energy`, `GrowthRate`, `GCommand`, `PitchFBW`, `F16View`, `F16Trail`; for f16-sim `PitchCommand`, `LateralFBW`, `F16Status` |
| `../export_f16.jl`, `../export_f16_check.py` | the f16-sim FMU: export, references and the fmpy acceptance |

    uv run examples/f16/design/design.py
    uv run examples/f16/design/build_model.py
    uv run examples/f16/design/make_meshes.py
    uv run examples/run_checks.py --only f16
    uv run examples/export_f16_check.py
