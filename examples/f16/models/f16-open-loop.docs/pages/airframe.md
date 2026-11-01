# The airframe

## Rigid body

The book's mass is 636.94 slug (9295.4 kg, weight 20 500 lb) with $J_{xx} = 9496$, $J_{yy} = 55\,814$, $J_{zz} = 63\,100$ and $J_{xz} = 982$ slug ft². The product of inertia tilts the principal axes by

$$\varepsilon = \tfrac12 \arctan\frac{2 J_{xz}}{J_{zz} - J_{xx}} = 1.05^\circ$$

about the body y axis. The stdlib `RigidBody3D` takes a diagonal inertia, so it sits on the principal axes; a `FixedTransform3DNeutral` (the Mount) carries the wrench from the geometric body frame (x forward, y left, z up) to them. `Free3D` gives the six degrees of freedom, gravity is part of `RigidBody3D`.

## Air data and coefficients

`F16AirData` turns the principal-axis pose and twist into the book's variables: $V_t$, $\alpha$, $\beta$, the body rates $p, q, r$ (x forward, y right, z down), the Euler angles, the altitude and the book's atmosphere (Mach and $\bar q$). The NASA tables are stdlib `Lookup2D` blocks over ($\alpha$, $\delta_e$) for $C_X$ and $C_m$, over ($\alpha$, $\beta$) for $C_l$, $C_n$ and the aileron and rudder derivatives, and `Lookup1D` over $\alpha$ for $C_Z$ and the nine damping derivatives. Breakpoints were added where the book extrapolates (elevator ±25 deg, a signed $\beta$ axis) so that bilinear interpolation reproduces the book's function exactly.

`F16Forces` builds the coefficients up as the book does,

$$C_{Z,T} = C_Z(\alpha)\Big(1 - (\beta/57.3)^2\Big) - 0.19\,\frac{\delta_e}{25} + \frac{\bar c\, q}{2 V_t} C_{Z_q}(\alpha), \qquad C_{m,T} = C_m + C_{Z,T}(x_{cg,r} - x_{cg}) + \dots$$

and the engine (`F16Engine`) is the F100 model with the throttle gearing, the power-level lag and the thrust tables over altitude and Mach. The engine's angular momentum (160 slug ft²/s) adds a gyroscopic moment.

## Checks against the book

The reference implementation `design/f16_ref.py` reproduces the book's check point (Table 3.5-2) to 3.9e-7 relative in all 13 state derivatives and the trims of Table 3.6-3 to every published digit (the [overview](page:overview) lists them). The bg-sim model matches it in turn (next page).
