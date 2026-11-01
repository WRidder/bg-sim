# Physics

## Sections

The IPE 100 has h = 100, b = 55, tw = 4.1 and tf = 5.7 mm; the model leaves out the root fillets (7 mm radius), so it has 96 % of the catalogue area and 95.5 % of the catalogue I. Bent about the strong axis (web vertical):

$$A = 2 b t_f + (h - 2t_f)\,t_w = 9.903\ \mathrm{cm^2}, \qquad I = \frac{b h^3 - (b - t_w)(h - 2t_f)^3}{12} = 163.32\ \mathrm{cm^4}, \qquad W = \frac{I}{h/2} = 32.67\ \mathrm{cm^3}.$$

The bars have the same area: $d = \sqrt{4A/\pi} = 35.51$ mm with $I = \pi d^4/64 = 7.803$ cm⁴, and $a = \sqrt{A} = 31.47$ mm with $I = a^4/12 = 8.172$ cm⁴. Steel: $E = 210$ GPa, $\rho = 7850$ kg/m³, $f_y = 235$ MPa.

## Modes

The deflection is $w(s,t) = \sum_{n=1}^{3} \phi_n(s)\,\eta_n(t)$ with the clamped-free Euler–Bernoulli shapes

$$\phi_n = \cosh\beta_n s - \cos\beta_n s - \sigma_n(\sinh\beta_n s - \sin\beta_n s), \qquad \beta_n = \lambda_n / L, \qquad 1 + \cos\lambda_n\cosh\lambda_n = 0,$$

$\lambda_n = 1.8751,\ 4.6941,\ 7.8548$, normalised to $\frac{1}{L}\int_0^L \phi_n^2\,ds = 1$, so $\phi_n(L) = 2, -2, 2$. Every mode has the modal mass $m = \rho A L$ and

$$m\,\ddot\eta_n + 2\zeta\omega_n m\,\dot\eta_n + k_n\eta_n = \phi_n(L)\,F + m g_0 a_n, \qquad k_n = \frac{\lambda_n^4 E I}{L^3}, \qquad f_n = \frac{\lambda_n^2}{2\pi}\sqrt{\frac{E I}{\rho A L^4}},$$

with $a_n = \frac1L\int\phi_n\,ds$. As a bond graph, each mode is a 1-junction with I = m, C = 1/k_n and R = 2ζω_n m, joined to the tip 0-junction by a TF of modulus φ_n(L) (example **cantilever-modes**).

## Readouts

- Tip deflection $w = \sum \phi_n(L)\eta_n$; statically $12\sum\lambda_n^{-4} = 99.86\,\%$ of $F L^3/(3EI)$.
- Root moment from the equilibrium of the beam, $M(0) = F L + \rho A g_0 L^2/2 - \rho A\int_0^L s\,\ddot w\,ds = F L + m g_0 L/2 - m L\sum b_n\ddot\eta_n$ with $b_n = \frac{1}{L^2}\int s\,\phi_n\,ds$: exact statically.
- From the curvature instead, $E I w''(0) = \frac{2EI}{L^2}\sum\lambda_n^2\eta_n$ ([Round/M_modal](signal:Round/M_modal)) converges slowly: $4FL(\lambda_1^{-2} - \lambda_2^{-2} + \lambda_3^{-2}) = 1.0210\,FL$. The 3D strain colours use this curvature.
- Stress $\sigma = M c / I$, utilisation $|\sigma|/f_y$.

## Step and sine

A step of F swings a damped mode to $1 + e^{-\zeta\pi/\sqrt{1-\zeta^2}} = 1.939$ times its static deflection (all modes together: 1.904). The root moment overshoots more, to $2.21\,FL$: at the wall the inertia of the higher modes adds to the first mode's swing (three modes and the finite element model with all modes agree to 0.1 %). A sine $F_a\sin 2\pi f t$ settles at the amplitude

$$|w| = \Bigl|\sum_n \frac{\phi_n(L)^2 F_a / k_n}{1 - r_n^2 + 2 i\zeta r_n}\Bigr|, \qquad r_n = f/f_n,$$

$1/(2\zeta) = 25$ times the static deflection at resonance.

## Limits

Linear Euler–Bernoulli beams with small deflections: no shear deformation (about 1 % on the I-beam's deflection), no lateral-torsional buckling of the I-beam (about 5 kN here), no plasticity, bending in the vertical plane only.
