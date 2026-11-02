@@ figures fem-gantry
{
  "diagram": {"kind": "diagram", "model": "fem-gantry"},
  "scene-accel": {"kind": "scene", "model": "fem-gantry", "t": 0.16},
  "scene-ring": {"kind": "scene", "model": "fem-gantry", "t": 0.712},
  "moves": {
    "kind": "plot", "model": "fem-gantry", "xlim": [0, 1.8],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Ref/q", "label": "reference", "color": "#444444"}, {"signal": "X1/qout", "label": "X1"}, {"signal": "X2/qout", "label": "X2", "style": "--"}], "legend": true},
      {"ylabel": "motor force [N]", "series": [{"signal": "X1Servo/F", "label": "X1 (welded end)"}, {"signal": "X2Servo/F", "label": "X2 (pivot end)"}], "legend": true},
      {"ylabel": "peak von Mises [MPa]", "series": [{"signal": "Mon/sigma_MPa", "label": "beam"}]},
      {"ylabel": "racking x1 - x2 [um]", "series": [{"signal": "Mon/rack", "label": "rack"}]}
    ]
  },
  "settle-plain": {
    "kind": "plot", "model": "fem-gantry", "xlim": [0.6, 0.8], "xlabel": "t [s] (the move out ends at 0.70 s)",
    "rows": [
      {"ylabel": "tool error x [um]", "ylim": [-150, 150], "series": [{"signal": "Mon/ex", "label": "plain move"}],
       "hlines": [{"y": 10, "label": "+-10 um band"}, {"y": -10}], "legend": true},
      {"ylabel": "settle [ms]", "series": [{"signal": "Mon/settle", "label": "settling time", "scale": 1000}]}
    ]
  },
  "settle-zvd": {
    "kind": "plot", "model": "fem-gantry", "overrides": {"global:shaping": 2.0},
    "xlim": [0.6, 0.8], "xlabel": "t [s] (the ZVD move out ends at 0.73 s)",
    "rows": [
      {"ylabel": "tool error x [um]", "ylim": [-150, 150], "series": [{"signal": "Mon/ex", "label": "ZVD-shaped move", "color": "#1b9e77"}],
       "hlines": [{"y": 10, "label": "+-10 um band"}, {"y": -10}], "legend": true},
      {"ylabel": "settle [ms]", "series": [{"signal": "Mon/settle", "label": "settling time", "scale": 1000, "color": "#1b9e77"}]}
    ]
  }
}
@@ page fem-gantry overview - | Overview
# An H-gantry with a flexible crossbeam

Two parallel X linear motors carry the ends of a 1.4 m aluminium box crossbeam; a 12 kg Y carriage with a Z head rides on a rail on the beam's front wall. The beam [Beam](block:Beam) is a **FEM flexible body**: a `ModalBody3D` reduced by Craig–Bampton from a 291 576-DOF tetrahedral model of the extrusion. It has three interfaces: the welded end A on X1, the pivoted end B on X2, and the **rail**, a moving interface that follows the Y carriage along the beam.

![The gantry accelerating at 10 m/s² (deflection drawn x100, colour: von Mises 0 to 2 MPa)|900](@fig:scene-accel)

![Diagram|900](@fig:diagram)

- [X1](block:X1) and [X2](block:X2) are the X axes (Prismatic3D), driven by [X1Motor](block:X1Motor) and [X2Motor](block:X2Motor) under [X1Servo](block:X1Servo) and [X2Servo](block:X2Servo): a P position loop of 15 Hz, a PI velocity loop of 60 Hz with acceleration feedforward and a 1 kHz current loop.
- [WeldA](block:WeldA) holds the beam's yaw to X1 (a stiff revolute spring); [PivotB](block:PivotB) lets it turn freely on X2. This is the usual fixed/floating pair.
- [YGuide](block:YGuide) is the Y carriage's guide on the rail port E of the beam; [YMotor](block:YMotor) drives the slide S.
- [Ref](block:Ref) sums six S-curve moves: the input shaper's impulses for the move out (0.5 m at 0.1 s) and back (at 1.0 s).
- [Mon](block:Mon) computes the tool error, the racking, the stress against the allowable and the settling time.

## What it shows

- **Settling is set by the servo-structure modes.** The move out (1 m/s, 10 m/s²) leaves the tool ringing at 47 Hz with ±127 µm ([Mon/ex](signal:Mon/ex)); it is inside ±10 µm 35 ms after the reference stops ([Mon/settle](signal:Mon/settle)).
- **Input shaping removes it.** A ZVD shaper tuned at that mode (46.8 Hz, ζ 0.47) lengthens the move by 25 ms and cuts the residual to 18 µm, the settling time to 11 ms. What is left is the carriage rocking on the twisting beam at 167 Hz.
- **A notch does not help.** The ringing mode is part of the servo loop; a notch at the beam's lightly damped 167 Hz mode only adds phase lag (settle 44 ms).
- **The welded end pushes harder.** The beam acts as a clamped-pinned beam: X1 needs 243 N, X2 168 N. The axes rack by 43 µm ([Mon/rack](signal:Mon/rack)).
- **The beam is lightly stressed.** The peak von Mises during the move is 2.4 MPa, 6 % of the 40 MPa fatigue allowable ([Mon/util](signal:Mon/util)).

## Try it

Open the **Dashboard**, change a slider and press **Run** (a run takes about 2 minutes):

- **shaping** 1 (ZV) or 2 (ZVD), and watch the tool error;
- **a_max** from 5 to 30 m/s²: the plain move's residual grows with the acceleration, the shaped one stays small;
- **y_c**, the carriage's place on the rail (0.15 to 1.25 m): off-centre the carriage loads one end more and racks the axes;
- **kf2** 0.9: the X2 motor 10 % weaker than its drive assumes;
- **notch** 0: a full notch in both X velocity loops.

The 3D view draws the deflection x100, marked exaggerated; the colours are the true von Mises stress.
@@ page fem-gantry model overview | Model
# Model

## The machine

| part | value |
| --- | --- |
| crossbeam | EN AW-6063 T6 box, 1400 × 60 × 100 mm, 4 mm walls, a 10 mm front wall (the rail seat); 6.91 kg |
| X carriages | 7 kg each (ironcore forcer, plate, two size-20 guide blocks, end bracket) |
| X guides | 4·10⁸ N/m across, 1.5·10⁶ N·m/rad in yaw |
| end A | welded (bolted) to X1: 10⁶ N·m/rad about the vertical |
| end B | a pivot on X2, bearing friction 1 N·m·s/rad |
| Y carriage | 12 kg with a Z axis and a process head; the tool 350 mm below and 100 mm in front of the rail |
| servos | P 15 Hz, PI 60 Hz with acceleration feedforward, current 1 kHz; X tuned for 16.5 kg |
| allowable | 40 MPa (fatigue of the parent material for 10⁸ cycles); yield 170 MPa |

## The reduced beam

The beam was meshed with quadratic tetrahedra (8 mm, 291 576 DOFs) and reduced to 21 coordinates: 6 fixed-interface modes, the 6 constraint modes of end B and 9 load modes of the rail. End A is the reference frame. Clamped at A, against Euler–Bernoulli beam theory (with the end cap as a tip mass and a Timoshenko shear correction):

| mode | beam theory | full FE | reduced |
| --- | --- | --- | --- |
| 1st bending along X | 35.11 Hz | 35.509 Hz | 35.510 Hz |
| 1st vertical bending | 51.90 Hz | 52.490 Hz | 52.492 Hz |
| 2nd bending along X | 216.1 Hz | 212.30 Hz | 212.36 Hz |
| 2nd vertical bending | 320.7 Hz | 316.98 Hz | 317.07 Hz |
| 1st torsion (Bredt) | 449.4 Hz | 454.08 Hz | 455.34 Hz |

## The moving carriage

The rail port **E** is the frame of the guide block at the rail coordinate s on the deformed beam. For every mode the reduction stores the rigid fit of the mode over the 100 mm block footprint at 45 stations, as a Chebyshev series in s. The carriage therefore rides on the real deflection and rotation under it, and its weight and inertia load the beam where it is. A force on the block is exact at the three load-mode stations (0.275, 0.55 and 0.825 m) and within 1.4 % between them; a torque about the rail is exact at the stations and up to 27 % low between them. The default carriage position, 0.55 m, is a station.

## The closed loop

Ground, X1, the beam and X2 close a kinematic loop. Every joint is a penalty spring, so the loop needs no constraint equations, and `ModalBody3D` takes part like any body. The ground sits on port **b** of each X mount (`FixedTransform3DNeutral` with the inverse pose): there the transform's equations are explicit, while the ground on port a would make each axis's flows and efforts a linear algebraic loop (24 algebraic unknowns).

## Stress

[Beam](block:Beam) outputs the von Mises stress at 27 points (three hotspots and 24 peak candidates from the static load cases) as the superposition of its modal stress table, and their maximum [Beam/sigma_max](signal:Beam/sigma_max). The 3D view colours the whole surface with it.
@@ page fem-gantry results overview | Results and checks
# Results and checks

## The plain move

![The default run: axes, motor forces, the beam's peak stress and the racking|900](@fig:moves)

![Just after the move out (x100): the beam and the carriage still ring|900](@fig:scene-ring)

| plain move, 0.5 m at 10 m/s² | BGSim | scipy modal model |
| --- | --- | --- |
| settling into ±10 µm | 35.5 ms | 31.5 ms |
| residual after the move | 127.1 µm | 121.3 µm |
| peak tool error | 253.0 µm | 247.8 µm |
| racking | 42.8 µm | 42.2 µm |
| motor peaks X1 / X2 | 243 / 168 N | 237 / 167 N |
| peak von Mises over the beam | 2.37 MPa | 2.55 MPa |

The scipy model (`design/reference.py`) is an independent linear model of the two servos, the X1 carriage's yaw, the beam's modal coordinates and the Y carriage, built from the reduced-model file alone, with rigid joints. Its closed-loop poles (46.8 Hz ζ 0.47, 62.2 Hz ζ 0.45, 95.4 Hz ζ 0.10, 192.4 Hz ζ 0.008) agree with BGSim's linearisation within 2 % when BGSim's joints are made rigid; the real guides lower the last two to 84 and 167 Hz.

## Shaping

![The plain move into its end position: 47 Hz ringing|900](@fig:settle-plain)

![The ZVD-shaped move: the 47 Hz ringing is gone, the 167 Hz carriage rocking remains|900](@fig:settle-zvd)

| move | settling | residual | peak | racking | peak stress |
| --- | --- | --- | --- | --- | --- |
| plain | 35.5 ms | 127 µm | 253 µm | 43 µm | 2.37 MPa |
| ZVD at 46.8 Hz | 11.6 ms | 17.6 µm | 179 µm | 30 µm | 1.68 MPa |
| notch at 167 Hz | 44.1 ms | 134 µm | 267 µm | 45 µm | 2.49 MPa |

## Statics

`gantry-static` checks the beam alone, clamped at both ends, against beam theory: the deflection within 5 %, the hotspots 100 mm from A within 2 %. See that model's docs.

## Checks

`expected.json` runs the plain move and four scenarios (ZVD, notch, X2 10 % weak, carriage at 0.15 m) against the scipy model: the axes' end positions, the peak tool error, the racking, the motor forces, the stresses at the hotspots, the residual and the settling time; the ZVD move against bounds (residual below 25 µm, settling below 15 ms). The static model is checked against beam theory, with and without the carriage.
@@ figures gantry-static
{
  "scene": {"kind": "scene", "model": "gantry-static", "t": 0.5},
  "static": {
    "kind": "plot", "model": "gantry-static", "xlim": [0, 0.5],
    "rows": [
      {"ylabel": "von Mises [MPa]", "series": [{"signal": "Beam/sigma_vm[1]", "label": "front wall, 100 mm from A", "scale": 1e-6}, {"signal": "Beam/sigma_vm[2]", "label": "back wall, 100 mm from A", "scale": 1e-6}, {"signal": "Beam/sigma_vm[3]", "label": "back wall, mid-span", "scale": 1e-6}], "legend": true}
    ]
  }
}
@@ page gantry-static overview - | Overview
# The crossbeam under 1 g

The beam alone, clamped at both end brackets, with the 12 kg Y carriage at mid-span on the rail, under 1 g along X: the inertia load of a 9.81 m/s² move. It checks the reduced beam's deflection and stress against beam theory. Set the global `g_y` to 0 to leave only the beam's own weight.

![Settled (deflection drawn x1000, colour: von Mises)|900](@fig:scene)

![The three hotspots settle to their static stress|900](@fig:static)

Beam theory: clamped-clamped over the elastic span of 1.24 m (between the rigid interface regions), with shear deformation; σ = M c / I plus the Bredt shear of the carriage's offset weight, combined into von Mises.

| quantity | beam theory | simulation | difference |
| --- | --- | --- | --- |
| **beam and 12 kg carriage** | | | |
| deflection under the carriage | 26.50 µm | 27.79 µm | +4.9 % |
| front wall, 100 mm from A | 400.1 kPa | 407.1 kPa | +1.7 % |
| back wall, 100 mm from A | 679.0 kPa | 686.2 kPa | +1.1 % |
| back wall, mid-span | 890.4 kPa | 722.5 kPa | −19 % |
| **beam weight only** (`g_y` = 0) | | | |
| deflection at mid-span | 5.24 µm | 5.42 µm | +3.4 % |
| front wall, 100 mm from A | 82.2 kPa | 82.7 kPa | +0.5 % |
| back wall, 100 mm from A | 134.0 kPa | 140.2 kPa | +4.6 % |
| back wall, mid-span | 120.7 kPa | 115.4 kPa | −4.4 % |

The mid-span hotspot sits under the carriage: the guide blocks spread its load over 100 mm and the box's walls carry it with shear lag, so elementary beam theory overestimates the stress there. Under the distributed own weight the same point agrees within 4.4 %.
