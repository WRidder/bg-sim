# Robird: a robotic peregrine falcon flying a figure of eight

A multibond and bond-graph model of the **Robird**, the flapping-wing robotic peregrine falcon of Clear Flight Solutions, built after

> B. A. van der Grinten, G. A. Folkertsma, N. Nijenhuis, S. Stramigioli, *The bird is the word: port based Hamiltonian modelling of
> flapping wing aeroelasticity using vacuum chamber and wind tunnel measurements*, MSc thesis, University of Twente (RaM), 2015.

The thesis models the wing as a small number of rigid bodies (4, 11 and 24) connected by 6D spring-damper elements, with quasi-steady
strip-theory aerodynamics, and it leaves open whether such a model can fly a simulated bird. This example closes that loop with
the 4-body class of wing: the bird **flaps at 3.97 Hz and flies a 220 m x 84 m horizontal 1:2
Lissajous figure of eight at 12 m/s with a gentle altitude Lissajous component**, completing the whole figure in 50 s,
under a discrete cycle-averaged flight controller. Nothing is kinematic: the fuselage is a 6-DOF free body, the wings are flexible multibody chains
and every force on the bird comes from the strip aerodynamics of its surfaces.

![Top view of the flown path against the Lissajous reference and the tracking error|900](assets/6ed3ee4c5d1f.png)

| quantity | value |
| --- | --- |
| mass, span, wing area | 0.70 kg, 1.10 m, 0.135 m$^2$ |
| flapping | 2 wings, stroke $\pm 0.50$ rad, 3.69 to 4.50 Hz, mean 4.05 Hz |
| figure | $x = A\sin\vartheta$, $y = B\sin 2\vartheta$, $z = z_0 + C_z \sin\vartheta$ with $A$ = 110 m, $B$ = 42 m, $C_z$ = 1.50 m, $z_0$ = 25 m |
| length, period at 12 m/s | 596 m, 49.67 s; smallest turn radius 26.50 m (bank 29.0 deg) |
| tracking after 8 s | cross-track RMS 0.42 m, peak 0.85 m; altitude band 22.9 to 26.9 m |

Pages: [the multibond structure](page:structure), [the aerodynamic model](page:aero), [the flapping drive and the aeroelastic wing](page:wing),
[the controller design](page:controller) and [the results](page:results). The README of the example lists which parameters come from the thesis and which are assumed.
