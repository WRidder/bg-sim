# Bracket ring-down: reduced model against the full FE model

The L-bracket of **fem-bracket**, clamped at interface A (a stiff [Clamp](block:Clamp) with [ClampDamping](block:ClampDamping)), with the 0.5 kg payload on interface B (through the stiff [WeldB](block:WeldB) and the 20 mm [Offset](block:Offset)) and no gravity. At t = 0 the [Payload](block:Payload) moves at 0.1 m/s along y (the upright's thin direction) and 0.05 m/s along x. Nothing damps the bracket (`zeta = 0`), so it rings at its natural frequencies.

## The reference

The reduction tool computes the same configuration on the full finite element model: the part clamped at A, the payload's mass and inertia added to the rigid interface B, eigenfrequencies by shift-invert Lanczos on all 39 348 DOFs (the part spec's `validate_attached`). It stores them in the reduced-model file under `validation.attached`:

| mode | full FE model | reduced model (10 coordinates) |
| --- | --- | --- |
| 1, upright bending along y | 18.5719 Hz | 18.5719 Hz |
| 2, bending along x | 30.8750 Hz | 30.8750 Hz |
| 3 | 170.964 Hz | 170.965 Hz |
| 4 | 264.890 Hz | 264.902 Hz |

The agreement is this close because the payload sits on an interface: the constraint modes of B make the static response to a load there exact, and the first modes with a heavy payload are nearly static shapes.

## What the run shows

- [Payload/flow/y[5]](signal:Payload/flow/y[5]) rings at the first mode, [Payload/flow/y[4]](signal:Payload/flow/y[4]) at the second (components of the payload twist [ω; v] in its own frame). Their FFT peaks are checked against the full-model values.
- [Bracket/Ek](signal:Bracket/Ek) and [Bracket/Ee](signal:Bracket/Ee) trade energy. The bracket's own kinetic energy is small next to the payload's.
