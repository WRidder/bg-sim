# DHC-2 Beaver

The nonlinear DHC-2 Beaver of the TU Delft FDC toolbox: validated modes and control steps, a
bond-graph drivetrain and a flyable model with the FDC autopilot. The
model is the de Havilland DHC-2 'Beaver' of the *Flight Dynamics and Control* toolbox (FDC, by
M. O. Rauw), on the flight-test aerodynamic and engine model of Tjee & Mulder, built in bg-sim on
the multibond rigid body. Its modes and control steps are validated against the thesis and the
toolbox's own linear models. A rotational bond-graph drivetrain is added, and the flyable model
exports as an FMU.

## Sources and licence

| tag | source | used for |
| --- | --- | --- |
| [THESIS] | M. O. Rauw, *A Simulink environment for flight dynamics and control analysis: application to the DHC-2 'Beaver'*, MSc thesis, Delft University of Technology, 1993, parts I and II (NASA NTRS 19950008401) | Table 5-1 (trim), Table 5-2 (linear model), Table 5-3 (modes), figures 5-2 to 5-7 (the control inputs of `beaver-steps`), the aircraft data (Table 2-1) |
| [FDC] | M. O. Rauw, *FDC 1.4 beta 3* (2005), dutchroll.sourceforge.net: `aircraft/modbuild.m`, the Simulink libraries `fdclib1/3/5.mdl` and `apilot/aplib.mdl`, `data/cr4520.lin`, `cr4560.lin`, `actmod35/45/55.dat` | the coefficients, the equations, the trims and linear models at 2000 and 6000 ft, the autopilot, the actuator models |
| [REP] | M. O. Rauw, *FDC 1.2: a Simulink toolbox for flight dynamics and control analysis*, 2nd ed., 2001 | the model equations (chapter 3, appendix C), the autopilot (chapter 11), sign conventions |
| [TM88] | R. T. H. Tjee, J. A. Mulder, *Stability and control derivatives of the De Havilland DHC-2 'Beaver' aircraft*, TU Delft report LR-556, 1988 | the flight-test identification behind every coefficient. Not consulted directly (the TU Delft repository was unreachable); [FDC] and [REP] cite it and agree with each other to every digit. |

FDC 1.4 is © 1994-2005 M. O. Rauw and licensed under the Open Software License 2.1
(`doc/license.txt`, `doc/copying.txt`). No FDC code is used, run or redistributed here. The
coefficients, constants and equations are published data and were transcribed by hand, each
with its source, into `design/beaver_data.py`; the scipy reference and the bg-sim blocks are
written from the equations. `design/fdc_lin.json` holds the trim points and the A and B matrices
read from FDC's `data/cr4520.lin` and `cr4560.lin` (numbers only), for the validation. The report
[REP] is under the Apple Common Documentation License; the thesis is a public NTRS document.

The model is valid where it was identified: 35-55 m/s true airspeed, flaps up to the range of
the flight tests (not stated in the sources; the slider stops at 20 deg), the normal flight
envelope. There is no stall, no ground or water contact (the floats of the 3D model are
decoration) and no ground effect: none is in the source, and none is added.

## Models

| model | what it shows |
| --- | --- |
| `beaver-modes` | Five Beavers at the thesis' trim point (45 m/s, 6000 ft, flaps up, 1800 rpm), each released on one eigenvector of the coupled linear model: phugoid, short period, Dutch roll, roll and spiral. `damping` fits read the oscillatory modes from the run, `GrowthRate` blocks read the real ones as phidot/phi. |
| `beaver-steps` | Six Beavers at the same trim, each with one of the thesis' inputs (figures 5-2 to 5-7): 3 deg blocks of elevator, ailerons and rudder for 2 s, 3 deg of flap in 3 s, +200 rpm in 4 s and +2 inch Hg of manifold pressure in 2 s. Sliders for the sizes and the drivetrain. |
| `beaver-sim` | The flyable Beaver: cockpit controls (column, pedals, flaps, elevator trim, manifold pressure, rpm), the FDC autopilot (pitch attitude and altitude hold, roll attitude and heading hold, turn coordinator) with its servos, the drivetrain on, wind inputs, and the FMU interface as export markers. The default run is a climb, a turn to 090 and a level-off. |

Every model has a 3D scene: a Beaver from simple solids (`design/make_meshes.py`): a boxy
fuselage behind the radial-engine cowling with its nine cylinder heads, the high constant-chord
wing on top of the cabin with a strut each side, the tailplane and fin, and two floats on struts.
The elevator, the ailerons, the flaps and the rudder are separate meshes that turn on their hinge
lines, and the two-blade propeller turns at 1/20 of the shaft speed (the real 30 rev/s would alias
at the display rate). The view keeps the first aircraft framed by moving the world around it
(`BeaverView`, `BeaverTrail`, as in the f16 example).

## The airframe

`airframe()` in `design/build_model.py` is the same subsystem in every model:

* **Rigid body.** `stdlib:spatial/RigidBody3D` on `Free3D`: m = 2288.231 kg, Ix = 5368.39,
  Iy = 6928.93, Iz = 11158.75, Jxz = 117.64 kg m^2 [FDC, REP Table C.2]. The product of inertia
  tilts the principal axes 1.16 deg about y, so the body sits on its principal axes and a
  `FixedTransform3DNeutral` (Mount) applies the wrench in the geometric body frame.
* **Air data** (`BeaverAirData`): airspeed, alpha, beta, body rates (FRD), Euler angles, altitude
  and the FDC atmosphere: T = 288.15 - 0.0065 H, g = 9.80665 (6371020/(6371020 + H))^2,
  ps = 101325 (T/288.15)^(g/1.86584), rho = ps/(287.053 T); calibrated airspeed as FDC's airdata.
* **Aerodynamics** (`BeaverAero`, generated from `design/beaver_data.py`): the polynomial model of
  Tjee & Mulder in alpha, beta, the non-dimensional rates and the deflections [REP Table C.3].
* **Propulsion** (`BeaverPropulsion`): the forces and moments of engine operation, polynomials in
  dpt = 0.08696 + 191.18 P/(rho V^3/2) [REP Table C.4].
* **Wrench** (`BeaverWrench`): the forces and moments as a modulated source on the body
  (`ExternalWrenchSpatial`), plus two corrections that make the rigid body (uniform gravity g0)
  follow FDC's equations exactly: m (g(H) - g0) along the vertical, and FDC's treatment of the
  beta-dot side force (CYbdot): FDC divides the beta-dot equation by 1 - k,
  k = cos(beta) rho b S CYbdot/(4 m) = -0.0061, and leaves V-dot and alpha-dot alone. Here the
  force m V bdot0 k/(1 - k) acts along the one direction that changes only beta.
* **Drivetrain** (a rotational bond graph, our addition): a 1-junction `Crank` with the engine
  torque Te = P(pz, n, rho)/w as an MSe (`BeaverEngine`), the crank and propeller inertia
  `Inertia` (I, J = 12 kg m^2), the propeller's torque -Q as a second MSe from the governor of the
  constant-speed propeller (`PropGovernor`: Q = Cq rho n^2 D^5 with a PI governor on Cq), and a
  speed sensor `Tacho` (`stdlib:converters/SpeedSensor`) that reads the shaft speed.

### Where the model stays algebraic

The source identified the thrust and the slipstream effects together, as polynomials in dpt, from
the engine power. There is no separate thrust force, propeller efficiency or slipstream model
to put on a bond, so the propulsive forces and moments stay coefficient algebra on the wrench
source, exactly as [REP Table C.4]. The bond graph ends at the shaft: its power Q w (drivetrain
on) or the source's algebraic power P(pz, n_cmd, rho) (drivetrain off) drives dpt. The engine
power polynomial itself is also algebraic in the source (no manifold or engine dynamics); it
becomes the torque source of the crank. The aerodynamic forces are the modulated wrench source on
the rigid body; air data, tables, the autopilot and the cockpit are signal blocks.

### Two modes of the propulsion

The global `drivetrain` selects the power that drives dpt:

* `drivetrain = 0`, **exact source mode** (the default in `beaver-modes` and `beaver-steps`): the
  rpm is a prescribed input and the power is algebraic, P(pz, n_cmd, rho), as in FDC. All the
  validation below runs in this mode.
* `drivetrain = 1` (the default in `beaver-sim`): the thrust comes from the shaft power of the
  bond graph. The rpm lever sets the governor's target; the shaft speed follows with the crank
  inertia and the governor's dynamics, and a manifold-pressure change first accelerates the shaft
  until the governor has re-pitched the propeller.

The drivetrain's numbers are ours (labelled assumptions, see Limitations): J = 12 kg m^2 for the
crank and the Hamilton Standard two-blade propeller, the propeller diameter 2.59 m [THESIS Table
2-1], and the governor gains Kp = 0.0483, Ki = 0.0842 1/s, placed so that the linearised
shaft-speed loop has wn = 2 rad/s, zeta = 0.7 at the trim point (`drive_gains` in
`design/beaver_ref.py`). The torque coefficient does not depend on the advance ratio, so the
absorbed power is independent of the airspeed, as the source's power is. At the trim the shaft
power equals the source's power, so both modes have the same trim.

How much the drivetrain changes the modes (coupled 9-state linearisation at 45 m/s, 6000 ft):

| mode | drivetrain off (source) | drivetrain on | change |
| --- | --- | --- | --- |
| phugoid | -0.017566 +- 0.265127j | -0.017577 +- 0.265127j | real part +0.06 %, zeta 0.06611 -> 0.06615 |
| short period | -2.158371 +- 2.420703j | -2.158305 +- 2.420819j | 3e-5 relative |
| Dutch roll | -0.479144 +- 0.966229j | -0.479149 +- 0.966229j | 1e-5 relative |
| roll | -5.133197 | -5.133197 | < 1e-9 |
| spiral | -0.0428948 | -0.0428949 | 4e-6 relative |
| shaft speed | (prescribed) | -1.4000 +- 1.4281j | the governor loop, wn 2.0 rad/s, zeta 0.70 |

The shaft mode is fast and well damped compared with the phugoid and far from the short period,
so it hardly couples into the flight modes: the drivetrain changes the response to the engine
levers (the shaft lags the rpm command by about a second), not the aircraft's modes.

## Validation (design/design.py, exact source mode)

The scipy reference `design/beaver_ref.py` is written from the FDC equations. Its trim solves the
six force and moment equations as FDC's ACTRIM does (wings level, phi = 0, zero rates; unknowns
alpha, beta, de, da, dr, pz).

Trim at 45 m/s, 6000 ft, flaps up, 1800 rpm:

| quantity | here | FDC `cr4560.lin` | THESIS Table 5-1 |
| --- | --- | --- | --- |
| alpha = theta (rad) | 0.144388057 | 0.144388760 | 0.1444 |
| beta (rad) | -0.014712749 | -0.014713301 | -0.0147 |
| de (rad) | -0.042521583 | -0.042522083 | -0.0425 |
| da (rad) | 0.009141132 | 0.009141448 | 0.0091 |
| dr (rad) | -0.045970933 | -0.045971379 | -0.0460 |
| pz (inch Hg) | 21.0715888 | 21.0716256 | 21.072 |
| largest state derivative at the trim | 1.6e-16 | 9.2e-7 | |

FDC's trim stops at fminsearch's tolerance (its state derivatives are about 1e-6); ours is
converged, and the two agree to 5e-7 rad. At 2000 ft (`cr4520.lin`) the agreement is the same.

Linearisation (central differences) against FDC's A and B matrices: largest |dA| 2.5e-4 (6000 ft)
and 5.5e-4 (2000 ft), largest |dB| 4.7e-6 and 1.5e-5. The differences are FDC's forward
differences with a 1e-5 perturbation (for example FDC's A[xe, alpha] = -2.25e-4 where the
derivative is 0).

Modes of the decoupled 4-state models (longitudinal V, alpha, q, theta; lateral beta, p, r, phi),
as THESIS Table 5-3:

| mode | here | from FDC's A (`cr4560.lin`) | THESIS Table 5-3 |
| --- | --- | --- | --- |
| phugoid | -0.016140 +- 0.263072j | -0.016140 +- 0.263073j | -0.01614 +- 0.2631j |
| short period | -2.160601 +- 2.411133j | -2.160600 +- 2.411160j | -2.1606 +- 2.4112j |
| Dutch roll | -0.476339 +- 0.969199j | -0.476339 +- 0.969198j | -0.4770 +- 0.9763j |
| roll | -5.134133 | -5.134132 | -5.1351 |
| spiral | -0.0457515 | -0.0457516 | -0.04573 |

The longitudinal modes and the whole A matrix of FDC 1.4 agree. The thesis' lateral modes
differ in the third digit. The difference is explained exactly: the thesis' Table 5-2 lateral
matrix equals ours with the beta row multiplied by (1 - k)/(1 + k). In other words, the 1993
thesis model applied the beta-dot correction with the opposite sign; FDC 1.4 and its data files
have it as in [REP]. With the thesis' sign the reference gives Dutch roll -0.47697 +- 0.97637j,
roll -5.135073, spiral -0.045733 (Table 5-3: -0.4770 +- 0.9763j, -5.1351, -0.04573). Its beta row
[-0.18069, 0.14002, -0.98163, 0.21683] is Table 5-2's to the printed digits. `design.json` keeps
both (`modes_thesis_bdot`); the models use FDC 1.4's sign.

The coupled model (all of V, alpha, beta, p, q, r, theta, phi, H) is what the nonlinear aircraft
does. The thesis notes that the Beaver's longitudinal-lateral cross-coupling is strong (the trim
has beta, da and dr non-zero from the propeller's slipstream). The coupled modes are phugoid
-0.017566 +- 0.265127j, short period -2.158371 +- 2.420703j, Dutch roll -0.479144 +- 0.966229j,
roll -5.133197 and spiral -0.042895, and a very slow altitude mode +2.1e-4 1/s (the density and
gravity gradients). `beaver-modes` releases the aircraft on these.

### bg-sim against the reference (`expected.json`)

`uv run examples/run_checks.py --only beaver` runs the three models, plus `beaver-steps` with the
drivetrain on and `beaver-sim` with it off (594 checks). Every trajectory is compared with the
scipy reference of `design/design.py` (DOP853, tolerance 1e-11) at several times:

| run | checks | largest difference from scipy |
| --- | --- | --- |
| `beaver-modes` (drivetrain off) | 136 | 1.9e-9 (V in m/s, angles in deg) |
| `beaver-steps` (drivetrain off) | 332 | 3.5e-8 |
| `beaver-steps`, drivetrain on | 31 | 2.7e-8 (including the shaft rpm) |
| `beaver-sim` (drivetrain on) | 52 | 1.7e-6 |
| `beaver-sim`, drivetrain off | 43 | 4.9e-7 |

The modes read from the bg-sim runs, against the coupled linear model:

| mode | bg-sim | coupled linear model | read by |
| --- | --- | --- | --- |
| phugoid | zeta 0.0658, wn 0.2658 rad/s | zeta 0.0661, wn 0.2657 rad/s | `damping` fit of V over 0-150 s (residual 0.5 %) |
| short period | zeta 0.6629, wn 3.2513 rad/s | zeta 0.6655, wn 3.2432 rad/s | fit of alpha over 0-3 s |
| Dutch roll | zeta 0.4445, wn 1.0793 rad/s | zeta 0.4443, wn 1.0785 rad/s | fit of beta over 0-12 s |
| roll | -5.1323 1/s | -5.1332 1/s | `GrowRoll` phidot/phi at 0.3 s |
| spiral | -0.042894 1/s | -0.042895 1/s | `GrowSpiral` at 1 s |

The fits differ from the eigenvalues by the fit itself (a small nonlinear start and the other
modes the release excites), not by the model: the trajectories agree with scipy to 1e-9. Later in
the run the spiral rate drifts (-0.0444 at 20 s, -0.0360 at 60 s, in both bg-sim and scipy):
the release also excites the lightly damped phugoid through the nonlinear coupling.

The control steps show the cross-coupling of the thesis' figures 5-2 to 5-7. After 60 s, for
example, the flap aircraft flies at 41.1 m/s banked -11.8 deg and the manifold aircraft is
banked -7.0 deg: the slipstream's rolling moment grows with alpha^2 dpt. With the drivetrain on,
the Rpm aircraft's shaft lags the +200 rpm ramp: 1893.7 rpm at 3 s and 1995.1 rpm at 5 s where
the prescribed rpm is 1900 and 2000, settling to 2000.0 by 10 s.

## The flyable Beaver (beaver-sim)

### Cockpit (`BeaverControls`, ours)

The source has deflections in radians and no cockpit. Here the column (pitch and roll) and the
pedals (-1..1) move the surfaces by 15 deg at full travel, around the trim offsets; the travel is
limited to +-20 deg, the flaps to 0..20 deg, the manifold pressure to 10..30 inch Hg and the rpm
lever to 1600..2300 rpm. FDC's sign conventions [REP]: de positive trailing edge down; da =
da_right - da_left, positive rolls left; dr positive trailing edge left; df positive down. The
column aft gives trailing edge up, the wheel right gives the right aileron up, the right pedal
gives the trailing edge right. The elevator trim is an input; the aileron and rudder offsets that
trim the propeller's roll and yaw at 45 m/s are globals (`ail_trim`, `rud_trim`), standing in for
trim tabs.

### Autopilot (`BeaverPitchAP`, `BeaverRollAP`, `BeaverServo`)

The autopilot is FDC's [FDC apilot/aplib.mdl, REP chapter 11]. FDC 1.4 works in radians with
1 V of servo command = 1 deg, so the gains are rad/rad. They are scheduled on the true airspeed:

* **Pitch attitude hold (PAH):** u1 = clamp(Ktheta (dtheta_ref - (theta - theta0)), +-2 deg), an
  integrator 0.5 u1 limited to +-10 deg, and the elevator command u1 + I - Kq (q - tc). The turn
  compensation tc = r tan(phi) + Ktc (1/cos(phi + dphi) - 1) keeps the nose up in a bank. At
  45 m/s, Ktheta = -0.500 and Kq = -0.125 s.
* **Altitude hold (ALH)**, the outer loop: dtheta_ref = KH (H_ref - H)/Ktheta, with the pitch
  attitude fed back through a washout (Kd = 0.175 1/s), so the integrator holds the altitude.
* **Roll attitude hold (RAH):** u1 = clamp(Kphi (dphi_ref - phi), +-3.75 deg), an integrator
  0.25 u1 limited to +-1 deg, and the aileron command u1 + I + 0.165 r. Kphi = -0.550 at 45 m/s.
  The turn coordinator on the rudder: -4 (g/V) sin(phi) + (drr + 4) r.
* **Heading hold (HH)**, the outer loop: dphi_ref = Kpsi (psi_ref - psi), limited to +-30 deg.
* **Servos** (our fit): FDC models the servo and the control cables of each surface as a
  third-order system per airspeed (`data/actmod35/45/55.dat`). They reach 63 % of a step in
  0.08-0.11 s, and their DC gain from the command to the deflection depends on the airspeed:
  elevator 1.85/1.90/1.96, ailerons 1.66/1.43/1.20, rudder 0.78/0.66/0.58 at 35/45/55 m/s.
  `BeaverServo` is a first-order lag of 0.09 s with that DC gain, fitted as a quadratic in V
  through the three points.

What is ours in the autopilot: mode 0 (off, the integrators bleed to zero in 0.5 s); absolute
references (theta_ref, phi_ref, psi_ref, H_ref) instead of FDC's deviations, with the heading
error wrapped to +-180 deg; the limited integrators as back-calculation integrators (50 ms); the
servo fit; and the turn compensation of the ALH mode in ALH. FDC's Simulink switch for the last
one has threshold 0 on a 0/1 flag, so it always picks the PAH formula; [REP] gives the ALH formula
for the outer loops, and we follow the report.

### The demo

At 5 s climb power (25 inch Hg, 2000 rpm) and the attitude hold 4 deg up: the Beaver climbs at
about 2.3 m/s and 41 m/s. At 30 s the heading hold turns it to 090 at the 30 deg bank limit, in
a climbing turn. At 70 s the altitude hold captures 150 m above the start, and at 85 s the power
goes back to the trim setting. After 150 s it flies level at 150.1 m, heading 89.96 deg,
45.0 m/s. At climb power the propeller's roll and yaw need more aileron than the roll hold's
+-1 deg integrator gives, so the bank sits 3 deg off and the heading 3-4 deg short until the
power comes back: FDC's autopilot does the same.

The milestones of the bg-sim run (start at 1828.8 m, heading 000; drivetrain on):

| t (s) | altitude (m) | V (m/s) | theta (deg) | phi (deg) | heading (deg) | rpm |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 1835.8 | 44.21 | 12.58 | -0.36 | -0.8 | 2000.8 |
| 30 | 1885.7 | 41.41 | 12.23 | -0.53 | -13.0 | 2000.1 |
| 50 | 1914.8 | 41.48 | 12.57 | 5.34 | 86.1 | 2000.1 |
| 70 | 1955.4 | 41.26 | 12.27 | 2.70 | 86.6 | 2000.1 |
| 90 | 1985.7 | 42.48 | 8.67 | 3.19 | 87.7 | 1799.3 |
| 150 | 1978.9 | 45.02 | 8.39 | 0.05 | 89.96 | 1800.0 |

Before the heading hold engages at 30 s, the roll attitude hold lets the heading drift 13 deg
left under climb power, for the same reason. The largest bank is 30.9 deg (in the turn at 44 s),
the lowest airspeed 39.9 m/s and the largest alpha 10.7 deg. With the drivetrain off
(`beaver-sim-source`) the run ends at 150.15 m above the start, 89.96 deg and 44.97 m/s: the
drivetrain changes the demo by less than 0.1 m/s.

## The FMU

`beaver-sim` has the host interface as export markers:

* Inputs (`ExportInputPass`, which pass the model's demo stimulus through in bg-sim):
  `col_pitch`, `col_roll`, `pedals` (-1..1), `flaps_deg`, `elev_trim_deg`, `pz_inhg`, `rpm`, the
  autopilot modes `ap_pitch` (0 off, 1 PAH, 2 ALH) and `ap_roll` (0 off, 1 RAH, 2 HH), the
  references `theta_ref_deg`, `phi_ref_deg`, `psi_ref_deg`, `h_ref_m`, and the wind `wind_n`,
  `wind_e`, `wind_d` (m/s).
* Outputs (`ExportOutput`): position (north, east, altitude), quaternion, Euler and path angles,
  body rates, TAS, CAS, alpha, beta, vertical speed, nz, the four surfaces, engine rpm, power, dpt
  and the propeller's display angle.
* FMU parameters: `drivetrain` (0..1), `ail_trim`, `rud_trim` (-5..5 deg).

    uv run examples/export_beaver_check.py        # export, references, build, fmpy comparison

The check exports `beaver-sim` (RK4, 5 ms, 16 inputs, 28 outputs, the three tunables with their
ranges), builds the binary, validates it with fmpy and compares three host runs with bg-sim runs
of the same stimulus (`export_beaver.jl`): the demo (150 s), a hand-flown run with the autopilot
off (column, wheel and pedal pulses, 30 s) and a run on the autopilot with 10 deg of flap, a wind
change and the rpm lever back to 1700 (40 s). The largest deviation, relative to each output's
peak:

| run | worst output | alpha | phi | psi | altitude | TAS | rpm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| demo | 6.6e-5 (aileron) | 3.6e-6 | 5.5e-5 | 2.5e-5 | 6.2e-6 | 1.1e-6 | 7.2e-8 |
| hand-flown | 8.8e-10 (p) | 1.1e-9 | 9.9e-10 | 3.0e-10 | 8.4e-10 | 1.0e-10 | 5.0e-12 |
| flaps and wind | 1.3e-8 (r) | 2.1e-9 | 4.3e-10 | 8.1e-10 | 2.3e-10 | 9.3e-11 | 3.5e-9 |

The demo's larger figure is the fixed step against bg-sim's adaptive one at the autopilot's
limits (the bank limit, the integrator limits and the mode switches act once per step in the
FMU). `doStep` takes 3.4 us on average, with no allocation after instantiation and no forbidden
symbols, and `drivetrain = 2` (outside 0..1) is refused.

## Limitations

* Valid for 35-55 m/s in the normal flight envelope [FDC, REP]: no stall, no ground or water
  contact, no ground effect. The flap range of the identification is not given in the sources.
* Ours, labelled as assumptions: the drivetrain (J = 12 kg m^2, the governor and its gains, Cq
  independent of the advance ratio), the servo fit, the cockpit mapping and the travel limits,
  the autopilot's mode logic and back-calculation integrators. The control-surface travel of the
  real aircraft is not in the sources.
* The wind enters the air data (airspeed, alpha, beta). FDC's wind terms in the equations of
  motion (its uwind/xdotcorr inputs) are not modelled; a constant wind is handled exactly, a
  changing one without the wind-rate terms. Turbulence (FDC's Dryden blocks) is not included.
* The beta-dot term follows FDC 1.4 (see Validation), not the 1993 thesis.
* The 3D propeller turns at 1/20 of its speed; the floats are decoration.

## Files

| file | content |
| --- | --- |
| `design/beaver_data.py` | every coefficient and reference value, with its source |
| `design/fdc_lin.json` | FDC's trim points and A, B matrices at 2000 and 6000 ft (numbers from `data/cr4520.lin`, `cr4560.lin`) |
| `design/beaver_ref.py` | the scipy reference of the FDC model: atmosphere, coefficients, equations of motion, trim, linearisation, modes, and the drivetrain |
| `design/beaver_sim.py` | the closed-loop reference of `beaver-sim`: cockpit, autopilot, servos |
| `design/beaver_si.py` | principal axes and the bg-sim start states |
| `design/design.py` | the validation, the modes, the reference runs; writes `design/design.json` |
| `design/build_model.py` | writes the models, scenes, `library/BeaverAero.jl`, `BeaverTrail.jl`, `PoseQuat.jl` and `expected.json` |
| `design/make_meshes.py` | writes `meshes/*.glb` |
| `library/` | `BeaverAirData`, `BeaverAero`, `BeaverPropulsion`, `BeaverWrench`, `BeaverEngine`, `PropGovernor`, `BeaverControls`, `BeaverPitchAP`, `BeaverRollAP`, `BeaverServo`, `GrowthRate`, `BeaverView`, `BeaverTrail`, `PoseQuat` |
| `../export_beaver.jl`, `../export_beaver_check.py` | the beaver-sim FMU: export, references and the fmpy acceptance |

    uv run examples/beaver/design/design.py
    uv run examples/beaver/design/build_model.py
    uv run examples/beaver/design/make_meshes.py
    uv run examples/run_checks.py --only beaver
    uv run examples/export_beaver_check.py
