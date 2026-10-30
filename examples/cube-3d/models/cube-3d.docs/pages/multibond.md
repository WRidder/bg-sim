# The multibond counterpart (DEC-M5-3)

`cube-3d-mb` builds the same cube from the M3 spatial stdlib in the structure of `reaction-wheel-3d`: `World` (`GroundSpatial`) to `Pivot` (`Spherical3D`, compliant) to `Link` (`FixedTransform3DNeutral`, the structure centre in the corner frame) to `Body` (`RigidBody3D` structure). The multibond models are documented in their own docs; this page records what is compared with the equation block.

| signal | window | $k_t = 10^8$ | $k_t = 10^6$ |
| --- | --- | --- | --- |
| tilt | whole run | 4.2e-7 rad | 2.4e-5 rad |
| body rates | from 0.05 s | 8.3e-8 / 2.7e-8 / 5.6e-8 rad/s | 4.3e-5 / 2.4e-5 / 2.0e-5 |
| body rates | from 0.5 s | 9.8e-9 / 2.7e-9 / 7.2e-9 | 7.4e-7 / 3.2e-7 / 4.3e-7 |
| wheel rates | from 0.05 s | 1.0e-5 / 2.3e-6 / 7.6e-6 rad/s | 3.8e-3 / 1.9e-3 / 1.8e-3 |

The soft-to-stiff ratio of the body-rate difference from 0.5 s is 75 / 122 / 59 for a stiffness ratio of 100; `compare_scaling` accepts a band of 50 to 150. The wheel rates are not a clean $1/k_t$ signal and are not used for the scaling check. The vertical momentum of body plus wheels is conserved to 5.7e-10 ($k_t = 10^8$) and 6.8e-7 ($k_t = 10^6$) of the 1.6e-4 N·m·s the wheels exchange.
