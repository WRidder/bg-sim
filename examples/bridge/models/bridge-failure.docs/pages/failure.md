# Member failure

Every bar of `Truss2D` has its force

$$N = (1 - b)\,\frac{E A}{L_0}\,\left(L - L_0 + \beta \dot L\right),$$

with $L$ the current distance between its nodes, $L_0$ the distance at the start and $b$ the held failure flag. Two events per bar (a `for` loop around `@events`) set $b = 1$:

- tension: $N > F_t = f_y A$
- compression: $-N > P_{cr} = \pi^2 E I / (K L_0)^2$ (Euler buckling)

A failed bar carries no force for the rest of the run: the model is **elastic-brittle, also in compression**. The strain energy the bar held at that instant is booked in `Elost`, so

$$E_{bal} = E_k + E_e + E_g + E_{dis} + E_{lost} - W_{ext}$$

stays constant through every failure. The utilisation `util` is $N/F_t$ in tension and $N/P_{cr}$ in compression, so the failure is at $\pm 1$.

For bar 13: $F_t$ = 355 MPa × 6.7786 cm² = 240.64 kN, and the energy it holds at failure is $F_t^2 L_0 / (2 E A)$ = 959.4 J.

The truss is statically determinate (26 joint equations, 23 bars and 3 reactions), so losing one bar makes its panel a mechanism. The other bars take the load for a short time while the panel shears, until the bottom chord fails too.
