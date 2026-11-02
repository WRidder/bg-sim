# The airframe

## Rigid body

The mass is 2288.231 kg, with $I_x = 5368.39$, $I_y = 6928.93$, $I_z = 11\,158.75$ and $J_{xz} = 117.64$ kg m². The product of inertia tilts the principal axes by 1.16° about y. The stdlib `RigidBody3D` sits on the principal axes, and a `FixedTransform3DNeutral` (the Mount) carries the wrench from the geometric body frame to them.

## Coefficients and wrench

`BeaverAirData` gives the airspeed, $\alpha$, $\beta$, the body rates, the Euler angles and the FDC atmosphere, with the gravity falling off with altitude. `BeaverAero` holds the polynomial model of Tjee & Mulder. For example:

$$C_Z = C_{Z_0} + C_{Z_\alpha}\alpha + C_{Z_{\alpha^3}}\alpha^3 + C_{Z_q}\frac{q\bar c}{V} + C_{Z_{\delta_e}}\delta_e + C_{Z_{\delta_e\beta^2}}\delta_e\beta^2 + C_{Z_{\delta_f}}\delta_f + C_{Z_{\alpha\delta_f}}\alpha\delta_f$$

`BeaverPropulsion` adds the forces and moments of engine operation. They are polynomials in the dimensionless pressure rise over the propeller,

$$\Delta p_t = 0.08696 + 191.18\,\frac{P}{\tfrac12\rho V^3}.$$

`BeaverWrench` turns them into the six inputs of the wrench source on the body. It also applies FDC's two corrections: the gravity at altitude, and the side force of $\dot\beta$.

## Drivetrain

The engine and the propeller are a rotational bond graph on a 1-junction, the crank:

| element | role |
| --- | --- |
| an MSe | the engine torque $P(p_z, n, \rho)/\omega$ |
| an I | the crank and propeller inertia |
| a second MSe | the torque of the constant-speed propeller, from its governor |
| a speed sensor | the shaft speed |

The global `drivetrain` selects the thrust power: 0 is the source's algebraic power at the prescribed rpm (exact FDC), 1 is the shaft power of the bond graph.
