# fem-gantry — an H-gantry with a FEM crossbeam

A pick-and-place or dispensing H-gantry. Two parallel X axes carry the ends of a 1.4 m aluminium box crossbeam, and a Y carriage with a tool runs along the beam. Each X axis has an ironcore linear motor on a profile-rail guide. The crossbeam is a **FEM flexible body** (`ModalBody3D`) reduced from a finite element model built with CSG. It has three interfaces: the two end brackets, A and B, and a **rail** on its front wall that carries the Y carriage (a moving interface). The example shows:

- point-to-point moves;
- the tool's vibration and its settling against the acceleration;
- plain moves against input-shaped moves (ZV, ZVD) and a notch;
- racking of the two X axes;
- the beam's von Mises stress against the allowable, in 3D and on the dashboard.

```
WorldX1 ─ X1Mount ─ X1 (Prismatic3D, motor) ─ X1Turn ─ X1Car ─ WeldA (Revolute3D + spring) ─ BracketA ─┐
                                                                                                        Beam (ModalBody3D)  A … B, rail E/S
WorldX2 ─ X2Mount ─ X2 (Prismatic3D, motor) ─ X2Turn ─ X2Car ─ PivotB (Revolute3D, friction) ─ BracketB ┘   │
                                                       YGuide (Prismatic3D on E) ─ YOffset ─ YCar ─ (tool)  ┘   YMotor on S
```

The ground, the two X axes and the beam close a kinematic loop (X1 → beam → X2 → ground). `ModalBody3D` takes part in the loop like any body. Every joint is compliant (penalty stiffness), so the loop needs no constraint equations.

## The machine

| part | value | why |
| --- | --- | --- |
| crossbeam | EN AW-6063 T6 box, 1400 × 60 × 100 mm (length × depth along X × height); 4 mm walls, a 10 mm front wall (the rail seat) and 10 mm end caps | a typical extruded gantry beam for a 1.3 m span; with a 4 mm front wall the rail's torque dents the wall locally, a response far softer than the beam's |
| beam mass | 6.91 kg (FE) | A = 1768 mm², 4.77 kg/m |
| X carriage | 7 kg each: forcer 2.5 kg, plate and two size-20 guide blocks 3 kg, end bracket 1.5 kg | an ironcore forcer of about 250 N peak |
| X guide | 4·10⁸ N/m across, 1.5·10⁶ N·m/rad (the yaw of two blocks 120 mm apart) | size-20 profile rail, medium preload |
| end brackets | A welded (bolted) to X1: a Revolute3D held by 10⁶ N·m/rad about z; B on a pivot on X2 (free yaw, bearing friction 1 N·m·s/rad) | the usual fixed/floating pair: two rigidly clamped ends would make the X axes fight each other through the beam |
| Y carriage | 12 kg: plate, a ball-screw Z axis with its motor and a process head, 160 × 300 × 180 mm; centre of mass 80 mm in front of and 100 mm below the rail line | a Z-head carriage |
| tool point | 350 mm below the rail line, 100 mm in front of it | the end of the Z axis |
| Y guide | two size-15 blocks: 3·10⁸ N/m, 10⁶ N·m/rad; slide coupling 2·10⁸ N/m | |
| servos (each axis) | P position loop 15 Hz, PI velocity loop 60 Hz with acceleration feedforward, current loop 1 kHz; X tuned for M_x = 16.5 kg (a carriage plus half of the beam and the Y carriage) | ordinary industrial drive settings |
| moves | 0.5 m out at 0.1 s and back at 1.0 s; 1 m/s, 10 m/s², 5000 m/s³ | |
| stress allowable | 40 MPa | fatigue of the extruded parent material for 10⁸ move cycles (EN 1999-1-3, detail category 71, extrapolated and rounded down); yield 170 MPa |

## The reduced crossbeam

`design/beam.fem.json` builds the beam from two boxes: the outer box minus the hole, which is offset to the back so that the front wall is 10 mm. It names the interfaces and the rail:

- **A** is every surface node of the first 80 mm, held in the X1 end bracket. This is the reference frame R, at the beam axis.
- **B** is the same at the X2 end.
- The **Y rail** runs on the front wall from 150 to 1250 mm, with a 100 mm guide-block footprint, 45 stations, Chebyshev degree 20, and load modes at 25, 50 and 75 % of its length.

The section is front-heavy: its centroid is 7.2 mm in front of the middle, I_z = 9.245·10⁻⁷ m⁴ (bending along X), I_x = 2.015·10⁻⁶ m⁴ (vertical bending), and the Bredt torsion constant is J_t = 1.723·10⁻⁶ m⁴.

`julia/BGSimFEM` meshes the beam with quadratic tetrahedra (8 mm: 97 192 nodes, 291 576 DOFs) and reduces it by Craig–Bampton to 21 coordinates:

- 6 fixed-interface modes;
- the 6 constraint modes of B;
- 9 load modes of the rail (modal truncation augmentation).

It writes `data/beam.modal.json` and `meshes/beam.glb` (3381 vertices, one morph target per mode). It takes 3 minutes, most of it the full-model validation.

Modes, clamped at A (a cantilever), against beam theory. Beam theory here is Euler–Bernoulli with the end cap as a tip mass, a Timoshenko shear correction, and St Venant torsion with the Bredt constant:

| mode | beam theory | full FE model | reduced model |
| --- | --- | --- | --- |
| 1st bending along X | 35.11 Hz | 35.509 Hz | 35.510 Hz |
| 1st vertical bending | 51.90 Hz | 52.490 Hz | 52.492 Hz |
| 2nd bending along X | 216.1 Hz | 212.30 Hz | 212.36 Hz |
| 2nd vertical bending | 320.7 Hz | 316.98 Hz | 317.07 Hz |
| 1st torsion | 449.4 Hz | 454.08 Hz | 455.34 Hz |

- **Beam theory against FE:** within 1.8 %.
- **Clamped, reduced against full:** the first 7 modes agree within 0.3 %, the 8th within 4 %.
- **Free-free, reduced against full:** the first 6 modes agree within 0.08 % (193.1, 284.8, 506.7 Hz, …), except the 5th at 2.9 %.

The accuracy band is 1041 Hz, 80 % of the first fixed-interface mode that was left out.

## The rail: a carriage that moves along the beam

The Y carriage does not sit on a fixed node. `ModalBody3D`'s port **E** is the frame of the guide block at the rail coordinate `s` on the deformed rail, and port **S** is the slide. The reduction stores, for every mode, how the rail frame moves along the rail:

1. A rigid fit of each mode over the 100 mm block footprint at 45 stations gives the translation and rotation at each station.
2. A Chebyshev series in s (`translation`, `rotation`) fits those values.

The block evaluates the series and its derivative at `s` (the rail velocity has a convective term `ṡ ∂Φ/∂s η`). Port S takes the drive force; the slide's equation of motion includes the generalized force of E along the rail.

The carriage (`YGuide`, a Prismatic3D on E whose axis is held by a stiff drive spring) therefore rides on the real deflection and rotation of the beam under it. Its weight and inertia load the beam where it actually is.

Accuracy, from `validation.rail` (the beam clamped at A, the full FE model loaded through the same footprint):

| load at the guide block | at a load-mode station (0.275, 0.55, 0.825 m) | between stations (0.45, 0.65 m) | near the clamp (0.1 m) |
| --- | --- | --- | --- |
| force along X | exact (−0.03 %) | −1.4 %, −0.6 % | −26 % of a deflection that is 0.2 % of the largest |
| vertical force | exact (−0.01 %) | −0.8 %, −0.3 % | −27 %, likewise 0.2 % of the largest |
| torque about the rail | −0.09 % | −27 %, −22 % | −74 % |

- **Forces:** the static response to a force on the block is exact at the load-mode stations and within 1.4 % between them. Near the clamp the deflection is tiny, so its relative error does not matter.
- **Torque about the rail axis:** this is the carriage's offset weight, or its inertia under an X acceleration. It is exact only at the stations: the wall's local twist under the block is the stiff part of the response, and the global modes do not span it between stations.

The default carriage position, y_c = 0.55 m (mid-span), is a station. For the default moves the torque is small: the inertia load on the carriage is along X, about 100 mm above its centre of mass.

## The closed loop

- **The weld at A** holds the beam's yaw to the X1 carriage, which its guide holds in turn: 10⁶ and 1.5·10⁶ N·m/rad in series. The welded end is therefore semi-rigid. The beam's own end stiffness, 4EI/L, is 2·10⁵ N·m/rad. Under an X acceleration the beam acts as a clamped-pinned beam, so the X1 motor pushes more than X2: 243 against 168 N.
- **The X mounts:** the ground is on port **b** of each X mount (`FixedTransform3DNeutral`, given the inverse of the joint frame's pose). The transform computes a.f from b.f and b.e from a.e. With the ground (a flow source) on b, every equation is explicit. With the ground on a, each axis's six flows and efforts form a linear algebraic loop: 24 algebraic unknowns, a DAE that the solver crawls through.
- **The motor signs:** each motor's port b is on the axis (the drive of the Prismatic3D, the slide S of the rail) and port a is on the stator, so a positive force moves the axis to +q.

## Models

- **fem-gantry**: the moves, gravity off. In this linear model the weight only adds a constant sag, which `gantry-static` checks. Globals (the dashboard's sliders):

  | global | meaning |
  | --- | --- |
  | `a_max`, `j_max` | the move's acceleration and jerk |
  | `shaping` | the input shaper: 0 none, 1 ZV, 2 ZVD, tuned at `f_s`, `zeta_s` |
  | `notch` | the notch depth at `f_n` in both X velocity loops |
  | `y_c` | the Y carriage on the rail |
  | `kf2` | the X2 motor's force constant relative to what its drive assumes |

  The reference is six SCurveProfiles (three impulses out, three back) summed by `library/MoveSum.jl`. The drives are `library/AxisServo.jl`. `library/GantryMonitor.jl` computes:

  | output | meaning |
  | --- | --- |
  | `ex`, `ey`, `ez` | the tool error against where the tool belongs (µm) |
  | `rack` | the racking, x1 − x2 |
  | `sigma_MPa`, `util` | the peak stress, and the stress against the allowable |
  | `settle` | the settling time of the last move into ±10 µm, tracked without events |

  A run takes about 2 minutes, plus about 1.5 minutes of compile once per session.
- **gantry-static**: the beam alone, clamped at both ends, with the Y carriage at mid-span, under 1 g along X (the inertia load of a 9.81 m/s² move). It checks the deflection and the stresses against beam theory. The global `g_y` = 0 leaves only the beam's own weight.

## Validation

### Statics against beam theory (`gantry-static`)

Beam theory here: the beam clamped-clamped over its elastic span of 1.24 m (between the rigid interface regions), with shear deformation (Timoshenko, shear area of the top and bottom walls). The hotspot stress is σ = M c / I plus the Bredt shear of the carriage's offset weight, combined into von Mises.

| quantity | beam theory | simulation | difference |
| --- | --- | --- | --- |
| **beam and 12 kg carriage** | | | |
| deflection under the carriage | 26.50 µm | 27.79 µm | +4.9 % |
| front wall, 100 mm from A | 400.1 kPa | 407.1 kPa | +1.7 % |
| back wall, 100 mm from A | 679.0 kPa | 686.2 kPa | +1.1 % |
| back wall, mid-span (under the carriage) | 890.4 kPa | 722.5 kPa | −19 % |
| **beam weight only** (`g_y` = 0) | | | |
| deflection at mid-span | 5.24 µm | 5.42 µm | +3.4 % |
| front wall, 100 mm from A | 82.2 kPa | 82.7 kPa | +0.5 % |
| back wall, 100 mm from A | 134.0 kPa | 140.2 kPa | +4.6 % |
| back wall, mid-span | 120.7 kPa | 115.4 kPa | −4.4 % |

The mid-span hotspot sits right under the carriage. There, elementary beam theory overestimates the stress:

- the guide blocks spread the load over 100 mm;
- the box's walls carry a concentrated load with shear lag.

With the beam's own weight alone (distributed), the same hotspot agrees within 4.4 %.

### Dynamics against a scipy modal model

`design/reference.py` is an independent linear model of the gantry, built in scipy from the reduced-model file alone. Its coordinates are:

- both X carriages, each with its own servo (the same equations);
- the X1 carriage's yaw on its guide, and the beam's yaw through the A weld;
- the beam's modal coordinates, with the B pivot's constraints eliminated;
- the Y carriage rigidly at the rail point, with the floating-frame coupling of the beam and the carriage.

It is discretised exactly (matrix exponential) at 20 µs. It leaves out the translational compliance of the guides and the joints, the Y servo, and every nonlinear term.

Closed-loop poles (the eigenvalues of the linearised BGSim model at rest, against the reference):

| pole | reference (rigid joints) | BGSim, joints rigid (k × 25 to 1000) | BGSim, the real joints |
| --- | --- | --- | --- |
| servo/beam bending | 46.8 Hz, ζ 0.47 | 45.7 Hz, ζ 0.50 | 46.9 Hz, ζ 0.44 |
| servo/beam bending | 62.2 Hz, ζ 0.45 | 63.5 Hz, ζ 0.38 | 62.6 Hz, ζ 0.49 |
| beam bending | 95.4 Hz, ζ 0.10 | 96.1 Hz, ζ 0.14 | 84.0 Hz, ζ 0.11 |
| carriage rocking on the twisting beam | 192.4 Hz, ζ 0.008 | 190.4 Hz, ζ 0.010 | 166.8 Hz, ζ 0.016 |

With rigid joints the two models agree within 2 % in frequency. The real guides' rotational compliance (1.5·10⁶ N·m/rad) lowers the two higher poles.

The plain move, 0.5 m at 10 m/s² (`fem-gantry`):

| quantity | BGSim | reference | difference |
| --- | --- | --- | --- |
| the move out ends (reference at rest) | 0.7015 s | 0.7015 s | |
| settling into ±10 µm | 35.5 ms | 31.5 ms | +4 ms |
| residual tool error after the move | 127.1 µm | 121.3 µm | +4.9 % |
| peak tool error (along X) | 253.0 µm | 247.8 µm | +2.1 % |
| peak racking x1 − x2 | 42.8 µm | 42.2 µm | +1.4 % |
| peak motor force X1 / X2 | 243.0 / 168.2 N | 237.3 / 167.2 N | +2.4 / +0.6 % |
| peak von Mises: front 100 mm from A / back 100 mm from A / back mid-span | 0.63 / 1.12 / 1.70 MPa | 0.60 / 1.16 / 1.56 MPa | +6 / −3 / +9 % |
| peak von Mises over the 27 points | 2.38 MPa | 2.55 MPa | −7 % |

- **Settling time:** a band crossing of the decaying 47 Hz oscillation, so a 5 % larger residual moves it by a half period. Its check allows 12 ms.
- **Other tool errors:** the vertical tool error peaks at 50 µm (the beam's vertical bending under the carriage's inertia), the error along the beam at 4.3 µm.
- **Tolerances:** the results are the same at reltol 10⁻⁶ and 10⁻⁷.

### Settling against acceleration

The move out, 0.5 m, 1 m/s, jerk 5000 m/s³, plain and shaped (BGSim sweep in one process, and the reference). Each cell is the settling time into ±10 µm / the largest residual tool error after the reference stops:

| a_max | plain, BGSim | plain, reference | ZV, reference | ZVD, BGSim | ZVD, reference |
| --- | --- | --- | --- | --- | --- |
| 5 m/s² | 21.5 ms / 65.5 µm | 19.4 ms / 63 µm | 5.8 ms / 15 µm | 0.4 ms / 11.9 µm | 0 / 3.4 µm |
| 10 m/s² | 35.5 ms / 127.1 µm | 31.5 ms / 121 µm | 6.2 ms / 28 µm (BGSim 22.6 ms / 32.3 µm) | 11.6 ms / 17.6 µm | 0 / 6.0 µm |
| 20 m/s² | 35.5 ms / 223.0 µm | 31.5 ms / 224 µm | 18 ms / 51 µm | 22.2 ms / 18.0 µm | 2.2 ms / 10 µm |
| 30 m/s² | 39.5 ms / 322.7 µm | 31.6 ms / 295 µm | 9.4 ms / 62 µm | 10.5 ms / 22.2 µm | 0 / 8.6 µm |

The X1 motor's peak force is 122, 243, 479 and 706 N at 5, 10, 20 and 30 m/s². The drives have no force limit: above 10 m/s² the sweep stands for a larger forcer with the same carriage mass.

- **The plain move:** its residual grows almost linearly with the acceleration. Its settling time grows only logarithmically: the ringing decays with ζω ≈ 0.45 · 2π · 47 Hz = 133 s⁻¹, so each doubling of the residual adds ln 2 / 133 s⁻¹ ≈ 5 ms. On top of that come the half-period steps of the band crossing.
- **The shaped moves:** they cut the 47 Hz part by a factor of 4 (ZV) and 10 or more (ZVD).
- **What remains in BGSim:** the carriage rocking on the twisting beam, 167 Hz and ζ 0.016. The shaper does not touch it, and it is the larger part of the shaped residual.
  - It grows with the jerk content of the move and needs a few tens of ms to decay below ±10 µm. Hence the scatter of the ZVD settling times (0.4 to 22 ms).
  - The reference has this mode at 192 Hz, with rigid joints, and with less amplitude.

## Shaping, the notch and racking

The default move (0.5 m at 10 m/s²). Each cell is BGSim / reference:

| case | settling | residual | peak tool error | peak racking | X1 force | X2 force | peak von Mises |
| --- | --- | --- | --- | --- | --- | --- | --- |
| plain | 35.5 / 31.5 ms | 127 / 121 µm | 253 / 248 µm | 42.8 / 42.2 µm | 243 / 237 N | 168 / 167 N | 2.37 / 2.55 MPa |
| ZV (`shaping` 1) | 22.6 / 6.2 ms | 32.3 / 28.1 µm | 213 / 208 µm | 36.0 / 35.5 µm | 210 / 215 N | 153 / 160 N | 2.00 / 2.14 MPa |
| ZVD (`shaping` 2) | 11.6 / 0 ms | 17.6 / 6.0 µm | 179 / 175 µm | 30.3 / 30.0 µm | 208 / 205 N | 152 / 152 N | 1.68 / 1.80 MPa |
| notch at 167 Hz (`notch` 0) | 44.1 / 35.0 ms | 134 / 136 µm | 267 / 264 µm | 44.8 / 43.5 µm | 265 / 260 N | 187 / 184 N | 2.49 / 2.70 MPa |
| X2 10 % weak (`kf2` 0.9) | 35.5 / 31.4 ms | 127 / 122 µm | 257 / 251 µm | 31.6 / 31.0 µm | 243 / 237 N | 169 / 167 N | 2.36 / 2.53 MPa |
| Y carriage at 0.15 m on the rail (`y_c`) | 39.7 / 26.9 ms | 48.6 / 46.9 µm | 89 / 84 µm | 83.2 / 81.8 µm | 267 / 273 N | 122 / 126 N | 1.45 / 1.59 MPa |

- **Agreement:** BGSim and the reference agree within a few % on the peaks, the racking and the forces in every case. The plain-move residuals agree within 5 %.
- **The settling times differ** by up to 13 ms. A settling time is a band crossing, and BGSim's tool also carries the 167 Hz carriage rocking that the reference has at 192 Hz and weaker. When the residual is only a few times the band (the off-centre carriage, the shaped moves), that rocking decides the last crossing.
- **The off-centre carriage** sits between the rail's start and its first load-mode station (0.275 m), 120 mm from the hotspot "back wall 100 mm from A". There the peak tool error is 6 % and that hotspot's stress 16 % apart, and its checks are looser (see "Checks").

**Input shaping**

- **The shaper and its tuning:** the shaper is tuned at the closed loop's dominant pole, which the reference's eigenvalues give: f_s = 46.8 Hz, ζ_s = 0.47. It is a heavily damped servo-structure mode: the beam's first bending along X, held by the two position loops.
- **ZVD:** it lengthens the move by one damped period (25 ms), lowers the motor peaks by 15 % and the stress by 30 %.
- **Sensitivity:** with its zero derivative, ZVD is insensitive to the tuning. In the reference, a ZVD at 44 or 50 Hz leaves 4.9 and 7.9 µm (6.0 µm when tuned), with ζ_s 0.35 or 0.6 it leaves 10.1 and 5.7 µm; ZV leaves 22 to 35 µm over the same range. Only far off (55 Hz) does the ZVD residual rise, to 16.5 µm.

**The notch does not help**

- **At f_s:** a notch at 46.8 Hz in the velocity loop sits inside the velocity bandwidth of 60 Hz and destabilises the loop.
- **At the lightly damped beam mode (167 Hz, `f_n`):** the closed loop is stable, but the notch adds phase lag near the velocity loop's crossover. The residual grows by 5 to 12 % and the settling time by 3.5 to 9 ms (reference and BGSim), and the motor peaks by 9 %.
- **Why:** the ringing that limits the settling time is a servo-structure mode of the closed loop. Nothing in the loop feeds it at a frequency a notch could remove. Shaping the reference is the right tool.

**Racking.** The welded end A with the pivoted end B makes the beam a clamped-pinned beam along X, so X1 pushes 59 % of the total force. Its axis lags more, and the axes rack by up to 43 µm during the acceleration, 3·10⁻⁵ rad over the 1.4 m between them. At rest the racking vanishes: both axes reach 0.5 m within 2 µm (checked).

- **A 10 % weaker X2** (`kf2` 0.9, the drive does not know) lags more too and so partly cancels the racking: 31 µm.
- **The Y carriage near the A end** (`y_c` 0.15 m) loads X1 even more: 273 against 126 N, and 82 µm of racking. The tool then sits near the stiff end: its residual drops to 47 µm.

**A stiffer section.**

The example has no stiffer variant; this is a discussion, not a result.

- **What a stiffer section changes:** the poles that limit settling are servo-structure modes, the beam's bending along X held by the two position loops. A deeper section (more I_z) raises the beam's part of them as √(EI/m).
- **What it does not change:** the servo's part, which is set by the 60 Hz velocity loop. A stiffer beam therefore helps less than its frequency ratio suggests, until the drives are retuned.
- **Torsion:** the carriage-rocking mode (167 Hz) depends on the beam's torsion and on the guides. More torsion stiffness (a closed second cell, or thicker side walls) raises it, and with it the floor of the shaped residual.
- **To try it:** edit the outer box in `design/beam.fem.json` and rerun the four rebuild commands. The reduction takes 3 minutes.

## Stress

[Beam](block:Beam) superposes its modal stress table at 27 points:

- the three named hotspots of `design/beam.fem.json`;
- 24 peak candidates from the static load cases of the reduction.

Its outputs are `Beam/sigma_vm[1..27]` and their maximum `Beam/sigma_max`. During the plain move the largest von Mises is 2.4 MPa. Against the 40 MPa fatigue allowable that is a utilisation of 5.9 % (`Mon/util`), and it falls to 4.2 % with ZVD.

- **Where it peaks** (the reference's superposition at all 27 points):
  - The largest stress, 2.5 MPa, is in the front wall (the rail seat) next to the Y carriage's guide block, where the carriage's inertia force enters the wall.
  - Next come the bottom of the back wall at mid-span (2.3 MPa) and the edges of the A interface region (2.0 MPa), where the beam leaves its rigid end bracket.
- **The stress is low:** the beam is sized for stiffness (10 µm settling), not for strength.
- **In 3D:** the view colours the whole surface with the same modal superposition (the `heat` colour map from 0 to 2 MPa). The dashboard's gauge shows `Mon/util` against 100 %.

## Dashboard and 3D view

The **Dashboard** has sliders for:

- the acceleration and the jerk;
- the shaper (0, 1, 2);
- the notch depth;
- the Y carriage's place on the rail;
- the X2 motor's force constant.

It shows the settling time, a gauge of the peak stress against the allowable, the peak von Mises, the racking, and plots of the tool error, the axes and the motor forces.

| binding | signal |
| --- | --- |
| `link:x1car`, `link:x2car` pose | `PX1Car/g`, `PX2Car/g` |
| `link:beam` pose | `Beam/pose` (interface A) |
| `link:ycar`, `link:tool` pose | `PYCar/g`, `PTool/g` (the deformed rail frame E, the guide, the offsets) |
| `visual:beam_mesh` mode-shapes, stress colouring | `Beam/eta[1..21]`, von Mises 0 to 2 MPa (heat) |

The deflections are tens of micrometres, so the 3D view opens with the deformation drawn ×100 (marked exaggerated). The colours come from the true modal coordinates. `gantry-static` opens at ×1000, rotated so that the load points down.

## Checks (`expected.json`)

- **fem-gantry**, and four scenarios with overrides (ZVD, a full notch, X2 10 % weak, the Y carriage at 0.15 m). In each:
  - no E101/E102/E108/W201/W202;
  - the scene bindings resolve;
  - both X axes reach 0.5 m and return to 0;
  - against the reference: the peak tool error (6 %), the racking (12 %), the motor force peaks (6 %), and the peak von Mises at the three hotspots and over the part (15 %);
  - the stress stays below the allowable.

  The unshaped runs also check the residual vibration after the move (12 %) and the settling time (12 ms, half a period of the 47 Hz mode) against the reference. The ZVD run checks bounds: a residual below 25 µm and a settling time below 15 ms. The off-centre carriage (`y_c` 0.15) allows 8 % on the peak tool error, 20 % on the hotspot stresses and 15 ms on the settling time (see "Shaping, the notch and racking").
- **gantry-static**: the deflection (7 %) and the two hotspots 100 mm from A (5 %) against beam theory. The mid-span hotspot under the carriage must stay below the beam-theory value.
- **gantry-static-self-weight**: the deflection (6 %) and all three hotspots (6 %) against beam theory.

## Limits

- **Linear elasticity, small deformations.** No geometric stiffening (the stiffening terms are off).
- **Gravity is off in the moving model.** The rail's static sag (`gantry-static`) adds to the tool error as a constant.
- **The rail's torque response** is exact only at the load-mode stations (see the rail table). For an off-centre carriage, the torsion of the beam under it is underestimated between stations by up to about 25 %.
- **The penalty joints** need fast states. The stiffest pole is the slide's coupling, an overdamped −6·10⁵ s⁻¹. The integrator is implicit (Rodas5P), and the run's cost comes from the beam's lightly damped high modes (up to 7 kHz, ζ = 0.01).
- **The stress** is the elastic modal superposition: the peak over 27 points (3 hotspots and 24 peak candidates), within a few % of the surface peak. The interface regions are rigid (RBE2), so there is no stress at the clamps themselves. Model a real bracket if its fillet matters.

## Files

| file | content |
| --- | --- |
| `design/beam.fem.json` | the part spec for BGSimFEM (CSG geometry, material, mesh, interfaces, rail, modes, stress points) |
| `design/build.py` | uv script: the models, the scenes and `expected.json`; beam theory |
| `design/reference.py` | uv script: the scipy modal model of the gantry; writes `design/reference.json` (the shaper's f_s and ζ_s, the sweep, the scenarios the checks compare with) |
| `data/beam.modal.json`, `meshes/beam.glb` | the reduced model and the beam's surface (written by BGSimFEM) |
| `library/AxisServo.jl`, `MoveSum.jl`, `GantryMonitor.jl` | the drive, the summed shaped reference, the dashboard's readouts |
| `models/*.bgmodel.json`, `models/*.docs` | the models and their documentation |
| `scenes/*.sdf` | the scenes |

Rebuild:

```
julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-gantry/design/beam.fem.json
uv run examples/fem-gantry/design/reference.py
uv run examples/fem-gantry/design/build.py
uv run examples/run_checks.py --only fem-gantry
```
