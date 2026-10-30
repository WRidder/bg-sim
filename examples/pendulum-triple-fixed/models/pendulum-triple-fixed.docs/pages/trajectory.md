# Trajectory optimisation

`design/design.py` computes the swing-up offline by **direct collocation** on the design model, including the motor and its voltage limit. The problem is to move from all links hanging at rest to all links upright at rest in the fixed time $T_s = 3.5$ s:

$$\min_{x(\cdot),\,u(\cdot)} \int_0^{T_s} \Big(\frac{u}{u_{lim}}\Big)^2 + \epsilon\,\lVert \dot q \rVert^2 \, dt \quad \text{s.t.} \quad \dot x = f(x, u),\ \ x(0) = x_{down},\ \ x(T_s) = x_{up},\ \ \lvert u \rvert \le u_{lim},$$

with $x = (q, \dot q)$, $x_{down} = (-\pi/2, 0, \dots, 0)$, $x_{up} = (\pi/2, 0, \dots, 0)$, $u_{lim} = 11$ V (the rest of the 12 V supply is margin for the feedback) and $\epsilon = 10^{-4}$.

**Discretisation.** 140 intervals of $h = 25$ ms. The voltage is piecewise linear between the knots. Each interval carries the Hermite–Simpson defect

$$x_{k+1} - x_k = \tfrac{h}{6}\big(f_k + 4 f_m + f_{k+1}\big), \qquad x_m = \tfrac12 (x_k + x_{k+1}) + \tfrac{h}{8}(f_k - f_{k+1}),\quad u_m = \tfrac12 (u_k + u_{k+1}),$$

which is fourth order in $h$. CasADi builds the exact derivatives of the Lagrangian dynamics; IPOPT solves the resulting nonlinear program (141 knots, 6 states and one input each) in about ten seconds from a sinusoidal voltage guess.

**Result.** The optimum uses a peak voltage of 11.00 V (the limit of the problem). The nominal states are the collocation knots, interpolated with a cubic Hermite spline at 1 kHz, not a forward integration: the swing-up is open-loop unstable (poles up to 15.4 s$^{-1}$ amplify a 1e-10 integration error by $e^{54}$ over the trajectory), so only the feedback can follow it.

The trajectory is written into `TriplePendCtrl` as constant tables of 351 rows at 10 ms spacing: the nominal voltage `u_ff`, the nominal states `xr_*` and the time-varying gains `k_*`.
