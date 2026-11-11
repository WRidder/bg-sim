# robird — a flapping-wing robotic falcon flying a Lissajous figure of eight (X5.15)

A 0.70 kg, 1.1 m span robotic peregrine falcon (the **Robird** of Clear Flight Solutions) as a multibond / bond-graph model, flying a
**220 m x 84 m horizontal 1:2 figure of eight with a gentle altitude Lissajous component at 12 m/s in 60 s** under a discrete,
cycle-averaged flight controller. Nothing is kinematic: a free 6-DOF fuselage, four flexible wing segments, three tail flaps, a motor-gear-crank
flapping drive and strip-theory aerodynamics on every surface. Z is up, units are SI.

| model | what it is |
| --- | --- |
| `robird` | the 60 s mission: start in trimmed level flight on the path, 3 s straight, then the figure of eight (1.2 laps); reltol 1e-4, abstol 1e-6, 20 points/s plus the 100 Hz ticks |
| `robird-trim` | open loop, 3 s: the straight-flight trim command (flapping frequency, elevator) with constant commands, dense output; the comparison of the trim with the full closed-loop model |

The models and the 3D scene are **generated**: `uv run examples/robird/design/build_model.py` writes `models/*.bgmodel.json` and `scenes/robird.sdf` from `design/params.py` and `design/design.py`.

## Source and what is from the thesis

> B. A. van der Grinten, G. A. Folkertsma, N. Nijenhuis, S. Stramigioli, *The bird is the word: port based Hamiltonian modelling of flapping wing
> aeroelasticity using vacuum chamber and wind tunnel measurements*, MSc thesis, University of Twente (RaM), 2015 (`vanderGrinten_MA_EWI.pdf`).

The document available here is the paper form of the thesis (method, results, the measurement appendix). It contains the **structure** of the model and
ranges but **not the fitted numbers**: the structural and aerodynamic parameters were estimated by a genetic algorithm with bounds 0.2 x to 5 x of a rough estimate,
and the paper reports no values, and says that the largest model errors (about 2 cm at the markers) come from the actuation and the base of the wing and that the models "are currently not suited for quantitative simulations"
and that it "is not known whether any of these models can be used to fly a simulated bird". This example takes that last step, with every number below the *thesis structure* either taken from the thesis or **assumed** and flagged.

| item | source | value here |
| --- | --- | --- |
| multi-rigid-body wing, bodies joined by 6D spring-damper (6D $R$, compliance $K_o$, $K_t$, $K_c$), screw-theory bodies | T, sec. III-A to III-C | `RigidBody3D`, `Revolute3DCompliant`-based `WingJoint` (a 6D connector with the other directions held stiff); diagonal $K_o$, $K_t$, $K_c = 0$ as in the "simplified view" of IV-C |
| 4 / 11 / 24 bodies per wing (grid of Fig. 7) | T | **2 spanwise segments per wing** (the 4-body class reduced: the chordwise division is replaced by the torsion degree of freedom of the root joints; the thesis expects the 11-body model to be the sufficient one, the 4-body one "easy to understand") |
| modified strip theory, $F_L = \frac12\rho v^2 S C_L$, $F_{ID} = \frac12\rho v^2 S C_{ID}$, $C_L$, $C_{ID}$ affine in $\alpha$ up to 15 deg | T, III-E, eq. 8-11 | `StripAero`, 3 strips per segment; $C_D$ affine in $\|\alpha\|$ (smoothed), stall limit 0.45 rad |
| actuation by two rods, the rear one with a phase lag, velocity controlled; four-bar flapping drive | T, III-F and appendix | `Crank`: crank-rocker map with a second harmonic for the front rod, the rear rod as the rest angle of the root torsion spring (`pitL`, `pitR`) |
| flapping frequency 2 to 4 Hz; wing length about 50 cm | T, appendix | 3.7 to 4.5 Hz (slightly above the thesis' range: the model needs it); wing length 0.5 m (inner 0.2 + outer 0.3 m) |
| tail flaps used for steering | T, introduction | two elevon halves and a rudder on first-order servos; asymmetric wing amplitude as an extra roll input (not needed) |
| stiffness of the wing from foam and carbon rods, $E_f I_x + E_r I_r$ (eq. 15), $G_f A + G_r A_r$ (eq. 16), damping $D_E I$, $D_G A$ (eq. 17) | T form, numbers **assumed** | bend $k = EI/L$ with $EI$ = 2.4 N m$^2$ of two carbon rods (12 N m/rad), torsion 0.6 and 0.5 N m/rad, sweep 40 N m/rad, pivot 2e4 N/m, dampers estimated |
| aerodynamic coefficients $L_a, L_b, ID_a, ID_b$ and the distribution $L_i, ID_i$ along the strip | T form, numbers **assumed** | $L_a$ = 4.4 /rad, $L_b$ = 0.25, $D_a$ = 0.2 /rad, $D_b$ = 0.04; constant distribution along the chord (centre of pressure at 25 % chord, torsion axis at 10 %) |
| **mass 0.70 kg, span 1.1 m** | public Robird figures (assumed) | fuselage 0.55 kg, wing segments 0.035 + 0.030 kg, flaps 3 x 0.006 kg; span 1.1 m, wing area 0.134 m$^2$ |
| body inertia, tail geometry, drag areas, cruise speed 12 m/s, motor and pack | **assumed** | see `design/params.py`; 6S pack 22.2 V, motor 0.0125 N m/A, 28:1 gear, 4e-6 kg m$^2$ rotor |

## Architecture

```
 Clock -> Guide (Guidance, 50 Hz) --psid, z_ref, vz_ff--> Fctl (FlightCtrl, 100 Hz) --f--> FlapCtl (motor speed PI) --V--> Drv (ElectricDrive)
   Truth (state read-out) ------------------------------>   |  |  |                                                       | shaft
                                                            |  |  +-- aL, aR (wing amplitude asymmetry) -> Crank <-- Gear (28:1) <--+
                                                            |  +----- sp (rudder) -> ServoTV -> JTV                       |  -> ShaftL/R (ElasticShaft) -> JL1/JR1 (WingJoint)
                                                            +-------- sp (elevons) -> ServoTL/TR -> JTL/JTR
 World -- Free (Free3D) -- Body (RigidBody3D) -- Mount -- JL1 -- Link -- BL1 -- Mount -- JL2 -- Link -- BL2      (right wing, tail flaps alike)
 every body: ExternalWrenchSpatial <- StripAero (wing segments, flaps), FuselageAero (fuselage); Air = constant wind
```

* **Airframe.** `GroundSpatial -> Free3D -> RigidBody3D` (13 states), gravity inside every body (the wing and tail bodies read their world pose from a `ComposePose3D` chain),
  fuselage drag by `FuselageAero`. Body frame: x forward, y left, z up, origin at the centre of mass.
* **Wings** (2 x 2 bodies). The flap joint `JL1` turns about the forward axis (up positive); `WingJoint` (library) is the stdlib `Revolute3DCompliant` with an anisotropic held rotation:
  the rotation about the span axis is a soft torsion spring ($k_{r,p}$) with a rest angle input (the rear rod and the rigging incidence), the sweep and the pivot translations stay stiff. `JL2` bends the outer segment against the inner
  one (spring $EI/L$). All states are integral, no W201.
* **Aerodynamics** (`StripAero`, example-local). Per strip: speed relative to the air $w = v + \omega\times r - R^T v_{wind}$, angle of attack, $C_L = L_a\alpha + L_b$, $C_D = D_b + D_a|\alpha|$, dynamic pressure, area;
  the wrench goes in through `ExternalWrenchSpatial`, so the power given to the air is exactly $\sum -F_i\cdot w_i$ (`Pa`, summed by `PaSum`). Fuselage drag: quadratic per axis (`FuselageAero`).
* **Flapping drive.** `ElectricDrive` (R 0.15 Ohm, L 0.1 mH, k_t 0.0125 N m/A) -> `IdealGear` 28:1 -> `Crank` (power-conserving 3-port modulated transformer, stroke $\Phi\,[\sin\psi + h_2\sin(2\psi + \varphi_2)]$, amplitude 0.5 rad) -> an `ElasticShaft`
  (120 N m/rad) per wing -> the flap joints. The elastic shafts are physical (the compliance of the linkage) and structural: a rigid coupling of the motor inertia to a multibond joint rate is derivative-causal (W201).
* **Tail.** Two all-moving elevon halves and a rudder on `Revolute3DCompliant` hinges, driven through effort sources by `TailServo`: a 40 ms first-order command lag and a PD torque with a stall limit.
* **Controller.** `Guidance` (50 Hz) and `FlightCtrl` (100 Hz), both `@discrete`; `FlapMotorCtrl` is the analogue speed regulator of the motor (a continuous PI with back-calculation, i.e. the "ESC"). Details under Design.

## Design (`design/design.py`)

1. **Figure from a turn-radius estimate** (`design.py sizing`): $x = A\sin\vartheta$, $y = B\sin2\vartheta$; $A$ = 110 m, $B$ = 42 m: lap 596 m, smallest radius 26.5 m at the crossing, a coordinated turn at 12 m/s needs 29.0 deg of bank,
   period 49.7 s (60 s run = 1.2 laps). The altitude component is $z = 25 + 1.5\sin\vartheta$ m (climb rate at most 0.2 m/s).
2. **Cycle-averaged trim from the full flapping model** (`design.py trim`, writes `trim.json`): the closed loop without path following flies straight for 34 s; the cycle averages of the last 10 s: flapping frequency **3.97 Hz**, pitch attitude 7.4 deg,
   elevator -0.126 rad, speed 11.94 m/s, climb rate 0.01 m/s, electrical 21.8 W, aerodynamic 15.6 W (the trim values seed the integrators of `FlightCtrl`).
3. **Sensitivities from the full model** (`design.py identify`, writes `identify.json`): open-loop runs of 0.3 s settling plus two flapping cycles around the trim; the change of the world velocity and the body rates over the cycles per unit of each input:

   | input (step) | $\dot u$ (m/s$^2$) | $\dot w$ (m/s$^2$) | $\dot v$ (m/s$^2$) | $\dot q_{up}$ (rad/s$^2$) | $\dot p$ (rad/s$^2$) | $\dot r$ (rad/s$^2$) | $\partial P_{air}$ (W) |
   | --- | --- | --- | --- | --- | --- | --- | --- |
   | flapping frequency (per Hz) | 0.66 | 0.41 | 0 | -0.05 | 0 | 0 | 2.1 |
   | pitch attitude (per rad) | -6.8 | -4.8 | 0 | -0.71 | 0 | 0 | -14.4 |
   | elevator (per rad) | 11.4 | -22.4 | 0 | -3.46 | 0 | 0 | 2.8 |
   | differential tail (per rad) | -0.40 | -1.55 | -11.1 | 0.32 | -1.22 | -4.70 | 6.3 |
   | rudder (per rad) | -0.14 | -0.37 | -9.6 | 0.27 | -6.71 | 5.86 | 1.2 |
   | wing amplitude asymmetry (per unit) | 0.05 | -0.14 | 1.9 | 0.04 | -0.49 | 1.12 | 0.16 |

   These windows carry the strong aerodynamic damping of the flapping wings and a start-up transient (the open-loop base case itself has $\dot u$ = -0.9 m/s$^2$), so they fix the **signs and the order of magnitude** of every loop but are not an accurate
   linear model. **The gains were tuned by iterating in the full closed-loop flapping model** (state feedback from `Truth`, no sensor model); no loop margins are claimed.
4. **Controller** (defaults of `library/FlightCtrl.jl`, 100 Hz; nose-up pitch $\theta$, roll $\phi$ left wing up positive, $n = 1/\cos\phi$):
   * speed: $f = f_0 + 0.3\,(U_c - U) + I_u + 3\,(n-1)$ Hz, $K_{iu}$ = 0.15 Hz/m, clamped to 2.0 to 4.5 Hz;
   * altitude: $v_{z,c} = 0.25\,(z_c - z) + v_{z,ff}$; $\theta_c = \theta_0 + 0.1\,(n-1) + 0.06\,(v_{z,c} - v_z) + I_{vz}$ ($K_{iv}$ = 0.04), pitch: $\delta_e = \delta_{e0} - 1.2\,(\theta_c - \theta) + 0.12\,q_{up}$;
   * bank: $\phi_c = -\arctan(U\dot\psi/g)$ (limit 0.6 rad), $\delta_a = 0.8\,(\phi_c - \phi) - 0.05\,p + I_\phi$ ($K_{i\phi}$ = 0.1), rudder $\delta_r = -0.15\,(\dot\psi\cos\phi - r)$;
   * all feedback signals pass two **notch filters at the flapping frequency and its second harmonic** (centre = commanded frequency, pole radius 0.95, unit DC gain): the cycle average of the loop;
   * guidance (50 Hz): nearest point of the 2 m path table, cross-track error $e$, heading error $\chi$; $\dot\psi_c = U\kappa(s + 0.6\,U) + 1.0\,(\chi_{des} - \chi)$, $\chi_{des} = -\arctan(e/25\,\mathrm{m})$.
   Elevons get $\delta_e \pm \delta_a$, the rudder $\delta_r$, the drive $f$, the crank $(1 \pm \eta)$ with $\eta = K_\eta(\phi_c - \phi)$ ($K_\eta$ = 0).
5. **Verification in the full flapping model**, always: `design.py verify` runs `robird` and `robird-trim` on the real worker, measures the numbers below, renders the figures of the docs and (with `--expected`) writes `expected.json`.

## Measured (real worker, reltol 1e-4)

| quantity | value |
| --- | --- |
| figure | x from -110.0 to 110.2 m, y from -42.4 to 41.5 m; 2 sign changes of x and 4 of y after convergence; 1.2 laps in 60 s |
| cross-track error (8 to 60 s) | RMS 0.42 m, peak 0.85 m |
| altitude | 22.9 to 26.9 m (reference 23.5 to 26.5 m); error RMS 0.46 m, peak 0.86 m |
| speed | 11.3 to 12.8 m/s (command 12) |
| flapping | 3.69 to 4.50 Hz commanded (mean 4.05 Hz, 4.5 Hz = the upper limit is reached in the turns); stroke amplitude 0.51 rad; motor-speed ripple 10.6 rad/s RMS about the command |
| aeroelasticity | root torsion up to 0.17 rad, outer bend up to 0.07 rad |
| bank | peak 31.4 deg (limit 34 deg) |
| tail | elevons +-0.36 rad (the start-up transient, 0.25 rad in flight), rudder 0.02 rad |
| drive | motor voltage peak 11.3 V (limit 21.8 V), current peak 6.4 A, mean 2.4 A; electrical 23.0 W, aerodynamic 16.2 W |
| cost | 60 s of flight in 44 s wall time (compile included), 12 001 recorded rows of 4 093 signals; `run_checks.py --only robird` about 2 minutes |

**Honesty.** The closed-loop flapping flight along the figure is feasible with this model; nothing is faked with a kinematic body. What it is *not*: a validated model of the real Robird. The aerodynamic and structural numbers are assumed (the thesis gives none),
the stall and the unsteady effects are not modelled, the controller uses ideal state feedback, and the 3.7 to 4.5 Hz flapping frequency is a little above the thesis' range of 2 to 4 Hz because the assumed aerodynamics need it
(the drag slope $D_a$ is the most sensitive aerodynamic parameter for the thrust: lowering it from 0.5 to 0.2 raised the net axial acceleration at fixed attitude by about 0.5 m/s$^2$ in the open-loop runs).

## Why some things look the way they do

* **Elastic shafts between the crank and the wing joints.** A rigid gear into a multibond joint rate makes the motor inertia derivative-causal (W201); the shafts (and the compliant joint, the aeroelastic wing) keep every storage element integral.
* **Wing incidence.** A flapping wing needs a positive angle of attack on the *down*stroke; the thesis' phase-lagged rear rod provides the pitching, here the root torsion spring has the rest angle $\Theta\sin(\psi + \psi_s) - \theta_{inc}$ with a rigging incidence of 0.12 rad
  (an early version without it trimmed at a nose-down attitude and sank).
* **The scene is drawn 20 times larger than the bird.** The figure is 220 m wide and the viewer camera does not follow the bird: a 1.1 m bird would be a dot. All joint offsets of the drawn bird are scaled the same way, the pose binding is in true metres.
  `design/check_scene.py` drives the SDF kinematic tree (scale 1) from the bound joint signals and compares the world poses of every wing segment and flap with the multibond pose chain (position 8 mm, rotation 0.03: the sweep deflection and the Gibbs chart of the torsion have no scene joint).
* **Output size.** Every 10 ms tick of the 100 Hz controller is recorded as a left/right event pair, and every port variable is recorded: the 60 s run writes 12 001 rows of 4 093 signals (about 390 MB of `columns.f64`); the motor regulator is therefore continuous, not a 1 kHz firmware block.

## Files

* `models/robird.bgmodel.json`, `models/robird-trim.bgmodel.json` (generated), `bgsim.project.json`
* `library/` `StripAero`, `FuselageAero`, `WingJoint`, `Crank`, `TailServo`, `FlapMotorCtrl`, `Guidance`, `FlightCtrl`, `Metrics`, `AirMass`, `SumPa`, `Truth`
* `design/params.py` (physical data, thesis vs assumed), `design/design.py` (sizing, trim, identification, controller data), `design/path.py` (the figure), `design/build_model.py` (model and scene generator),
  `design/verify.py` (verification run, figures), `design/expected_json.py`, `design/build_docs.py`, `design/check_scene.py`, `design/sim.py` (real-worker harness); results `design/trim.json`, `design/identify.json`, `design/results.json`
* `scenes/robird.sdf`: link `fuselage` (pose binding `Truth/q[1..4]`, `x`, `y`, `z`), joints `flap_L/R`, `torsion_L/R`, `bend_L/R`, `torsion2_L/R`, `elevon_L/R`, `rudder` (12 bindings), a ground plane and orange path markers
* `models/robird.docs/` (overview, structure, aerodynamics, flapping drive and wing, controller design, results)
* `expected.json`: 28 checks on the `robird` model and 4 on `robird-trim` (cross-track error, altitude band, figure extents and zero crossings, flapping frequency, actuator ranges, power, scene bindings, diagnostics)
* `web/tests/e2e/robird.spec.ts` (port 8816)

## Regenerate

```
uv run examples/robird/design/design.py trim        # trim.json (about 1 minute)
uv run examples/robird/design/design.py identify    # identify.json
uv run examples/robird/design/build_model.py        # models and scene
uv run examples/robird/design/design.py verify --expected    # results.json, expected.json, figures
uv run examples/robird/design/build_docs.py         # docs pages
uv run examples/run_checks.py --only robird
```
