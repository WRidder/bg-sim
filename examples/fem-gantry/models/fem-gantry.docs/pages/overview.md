# An H-gantry with a flexible crossbeam

Two parallel X linear motors carry the ends of a 1.4 m aluminium box crossbeam; a 12 kg Y carriage with a Z head rides on a rail on the beam's front wall. The beam [Beam](block:Beam) is a **FEM flexible body**: a `ModalBody3D` reduced by Craig–Bampton from a 291 576-DOF tetrahedral model of the extrusion. It has three interfaces: the welded end A on X1, the pivoted end B on X2, and the **rail**, a moving interface that follows the Y carriage along the beam.

![The gantry accelerating at 10 m/s² (deflection drawn x100, colour: von Mises 0 to 2 MPa)|900](assets/e1b27521511a.png)

![Diagram|900](assets/d60658bbbe31.png)

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
