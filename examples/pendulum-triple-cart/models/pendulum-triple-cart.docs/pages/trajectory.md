# Trajectory optimisation

`design/design.py` computes the swing-up offline by **direct collocation** on the design model of [the equations of motion](page:dynamics), including the motor and its voltage limit, with CasADi and IPOPT (`uv run`, inline script metadata).

**Problem.** Find the states $z_k$ and voltages $V_k$ at $K = 350$ equal intervals of length $h = T_s / K = 10.0$ ms, $T_s = 3.5$ s:

$$\min \; \int_0^{T_s} V^2\, dt + w \sum_k (V_{k+1} - V_k)^2$$

subject to

- the **Hermite-Simpson** defect constraints $z_{k+1} - z_k - \tfrac h6 (f_k + 4 f_{k+1/2} + f_{k+1}) = 0$ with $z_{k+1/2} = \tfrac12 (z_k + z_{k+1}) + \tfrac h8 (f_k - f_{k+1})$ and the voltage piecewise linear;
- start: all links hanging ($\theta_i = -\pi$), at rest, cart at the rail centre; end: all links upright, everything at rest, $x = 0$;
- the **rail limit** $\lvert x \rvert \le 0.3$ m (the rail ends at ±0.4 m, so the tracking error has 0.1 m of room);
- the **voltage limit** $\lvert V \rvert \le 16$ V (67 % of the 24 V supply, so the feedback has headroom).

The start guess is a half-cosine blend of every angle from hanging to upright with a small cart oscillation. The solution reaches the upright without ever touching the rail end stops: the cart reaches ±0.30 m of the ±0.3 m bound and the feed-forward needs at most 13.0 V of the 16 V bound.

![Swing-up: optimised trajectory against the bond-graph run|900](assets/274a57580d9a.png)

The dashed lines are the optimised trajectory and the coloured lines the bond-graph run under TVLQR: they agree to within a few mrad, and the applied voltage (grey) follows the feed-forward (orange) plus the feedback correction. The optimiser pumps energy into the links with a few cart strokes before the final lift.

**Resolution.** Hermite-Simpson needs a fine grid for the fast triple pendulum: 350 intervals (10 ms) track in the bond graph with the correction of the feedback alone. The tables of the controller hold the nominal state and the feed-forward at every 10 ms and are interpolated linearly.
