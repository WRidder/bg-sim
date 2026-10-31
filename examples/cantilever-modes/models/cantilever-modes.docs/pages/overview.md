# A cantilever in two modes, as a bond graph

A clamped steel rod (E = 210 GPa, ρ = 7850 kg/m³, d = 10 mm, L = 1 m) is loaded by a 1 N tip force step at t = 0.05 s. The rod is described by the **assumed-modes method**: the deflection is a sum of the first two cantilever eigenmodes,

$$w(s,t) = \phi_1(s)\,\eta_1(t) + \phi_2(s)\,\eta_2(t),$$

with the clamped-free shapes normalised to $\frac{1}{L}\int_0^L \phi_n^2\,ds = 1$. With that normalisation every mode has the modal mass $m = \rho A L$, the modal stiffness $k_n = \lambda_n^4 E I / L^3$ ($\lambda_1 = 1.8751$, $\lambda_2 = 4.6941$) and the tip value $|\phi_n(L)| = 2$.

## The modal bond graph

Each mode is a 1-junction (the modal velocity $\dot\eta_n$) with an I (modal mass), a C (compliance $1/k_n$) and an R (modal damping $2\zeta\sqrt{k_n m}$):

- [Mode1](block:Mode1) with [I1](block:I1), [C1](block:C1), [R1](block:R1);
- [Mode2](block:Mode2) with [I2](block:I2), [C2](block:C2), [R2](block:R2).

A transformer with modulus $\phi_n(L) = 2$ turns the modal velocity into its share of the tip velocity and the tip force into the modal force: [TF1](block:TF1), [TF2](block:TF2). The tip is a 0-junction, [Tip](block:Tip): one force, and the flows of the two modes add,

$$v_{tip} = \phi_1(L)\,\dot\eta_1 + \phi_2(L)\,\dot\eta_2 .$$

The force comes from [Force](block:Force) (an MSe driven by [Step](block:Step)). The bond graph gives, mode by mode,

$$m\,\ddot\eta_n + c_n\,\dot\eta_n + k_n\,\eta_n = \phi_n(L)\,F .$$

The real second mode has $\phi_2(L) = -2$. A TF modulus is positive in the library, so the graph uses $+2$ for both modes; the second modal coordinate of this graph is therefore $-\eta_2$ of the mode-shape convention, and the tip deflection is $2(\eta_1 + \eta_2)$ in the graph's coordinates.

## Global parameters

Everything is derived from the model's global parameters (Model > Global parameters): `E`, `rho`, `d`, `L`, `F0`, `zeta`, the eigenvalues `lam1`, `lam2` and `phiL`; then `A = Pi*d^2/4`, `I = Pi*d^4/64`, `m = rho*A*L`, `k1 = lam1^4*E*I/L^3`, `c1 = 2*zeta*sqrt(k1*m)` and so on. Change `d` or `L` and every element follows. (A global expression cannot use the built-in `pi`, so the model declares `Pi`.)

## Run it and the checks

- [C1/q](signal:C1/q) and [C2/q](signal:C2/q) are the modal coordinates $\eta_1$, $\eta_2$. Their ring-down frequencies are the analytic eigenfrequencies $f_n = \frac{\lambda_n^2}{2\pi}\sqrt{EI/(\rho A L^4)}$ = 7.236 Hz and 45.35 Hz (damped by $\sqrt{1-\zeta^2}$, $\zeta = 0.05$).
- Settled, $\eta_n = \phi_n(L) F / k_n$. The tip deflection $2(\eta_1 + \eta_2) = 3.2188$ mm is 99.54 % of the Euler-Bernoulli value $F L^3/(3EI) = 3.2336$ mm: one mode gives 97.07 %, three modes 99.86 %.
- [Force/p.f](signal:Force/p.f) is the tip velocity.
