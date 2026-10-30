# Notes

## Pivot damping

$k_t = 10^8$ N/m puts the pivot's translational mode at $\sqrt{k_t/m} \approx 1.6$ kHz, above the 1 ms controller. Without damping the drive's torque steps pump that undamped mode: $d$ grows from 3e-7 m to 1e-4 m and the run ends in **E901 (MaxIters) at $t = 2.54$ s**. The driven model therefore uses $b_t = 10^3$ N·s/m ($\zeta = 0.027$). The torque-free model keeps $b_t = 0$ so its energy budget is conservative.

## J-MB6 limitation found while building this example

A `FixedJoint2D` with a lever arm ($x \ne 0$) on a body's 1-junction leaves two algebraic unknowns in the compiled mass-matrix DAE whose initial values are NaN, so the run dies at $t = 0$ with E901. The same topology with the offset in the joint's `rx` parameter compiles to 12 differential states and runs; this model therefore uses `rx` for the elbow. The 1 ms controller turning the undamped 1.6 kHz pivot mode unstable is a physical, sampled-data effect, not a compiler bug.
