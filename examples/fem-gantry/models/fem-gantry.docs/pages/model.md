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
