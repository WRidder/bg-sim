# Trajectory optimisation

`design/design.py` computes the swing-up offline by **direct collocation** on the design model of [the equations of motion](page:dynamics), including the motor and its voltage limit, with CasADi and IPOPT (`uv run`, inline script metadata).

**Problem.** Find the states $z_k$ and voltages $V_k$ at $K = 60$ equal intervals of length $h = T_s / K = 40.0$ ms, $T_s = 2.4$ s:

$$\min \; \int_0^{T_s} V^2\, dt + w \sum_k (V_{k+1} - V_k)^2$$

subject to

- the **Hermite-Simpson** defect constraints $z_{k+1} - z_k - \tfrac h6 (f_k + 4 f_{k+1/2} + f_{k+1}) = 0$ with $z_{k+1/2} = \tfrac12 (z_k + z_{k+1}) + \tfrac h8 (f_k - f_{k+1})$ and the voltage piecewise linear;
- start: all links hanging ($\theta_i = -\pi$), at rest, cart at the rail centre; end: all links upright, everything at rest, $x = 0$;
- the **rail limit** $\lvert x \rvert \le 0.3$ m (the rail ends at ±0.4 m, so the tracking error has 0.1 m of room);
- the **voltage limit** $\lvert V \rvert \le 16$ V (67 % of the 24 V supply, so the feedback has headroom).

The start guess is a half-cosine blend of every angle from hanging to upright with a small cart oscillation. The solution reaches the upright without ever touching the rail end stops and uses at most 12.9 V of feed-forward; the cart bound is active (it swings the cart to ±0.28 m).

![Swing-up: optimised trajectory against the bond-graph run|900](assets/e4e8c456a0e9.png)

The dashed lines are the optimised trajectory and the coloured lines the bond-graph run under TVLQR: they agree to within a few mrad, and the applied voltage (grey) follows the feed-forward (orange) plus the feedback correction. The links first swing the wrong way and pump energy with the cart, as the optimiser finds.

**Resolution.** Hermite-Simpson needs a fine grid for the fast double pendulum: 60 intervals (40 ms) track in the bond graph with the correction of the feedback alone. The tables of the controller hold the nominal state and the feed-forward at every 10 ms and are interpolated linearly.
