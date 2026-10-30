# The aerodynamic model

Quasi-steady **modified strip theory** as in the thesis (section III-E): the lift and the drag of every strip follow from the speed relative to the air and the angle of attack,

$$F_L = \tfrac12 \rho v^2 S\, C_L(\alpha), \qquad F_D = \tfrac12 \rho v^2 S\, C_D(\alpha),$$
$$C_L(\alpha) = L_a \alpha + L_b, \qquad C_D(\alpha) = D_b + D_a |\alpha| .$$

The coefficients are affine in $\alpha$ (thesis eq. 10-11; for the drag mirrored in $\alpha$, smoothed at 0), valid up to about 15 degrees; beyond a stall limit $\alpha_{max}$ = 0.45 rad the angle is limited smoothly by
$\alpha_{max} \tanh(\alpha/\alpha_{max})$. The example-local block `StripAero` computes, for each strip $i$ of a segment with position $r_i$ in the body frame,

$$w_i = v + \omega \times r_i - R^\top v_{wind}, \qquad \alpha_i = \operatorname{atan2}(-w_i\cdot e_n,\; w_i \cdot e_{le}),$$
$$F_i = \tfrac12\rho\,|w_i|^2 S_i\left[C_L\,\hat l_i + C_D\,\hat d_i\right], \qquad \hat d_i = -\frac{w_{p}}{|w_{p}|},\quad \hat l_i = \frac{(w\cdot e_{le})\,e_n - (w\cdot e_n)\,e_{le}}{|w_p|},$$

with $e_{le}$ the unit chord vector towards the leading edge, $e_n$ the surface normal, $w_p$ the part of $w_i$ in the chord-normal plane. The wrench about the body origin is $\sum_i (F_i,\; r_i \times F_i)$ and goes to
`stdlib:multibond/ExternalWrenchSpatial`, whose port effort is the negative of the wrench, so the power is exact. The centre of pressure sits at 25 % chord and the torsion axis at 10 % chord, so a wing under lift is twisted nose-down by its own
lift moment - the aeroelastic pitch that turns the plunging motion of the flapping stroke into thrust.

| block | what it loads | strips | area (m$^2$) |
| --- | --- | --- | --- |
| [AeroL1](block:AeroL1), [AeroR1](block:AeroR1) | inner wing segments, 0.20 m | 3 | 0.0305 each |
| [AeroL2](block:AeroL2), [AeroR2](block:AeroR2) | outer wing segments, 0.30 m | 3 | 0.0367 each |
| [AeroTL](block:AeroTL), [AeroTR](block:AeroTR), [AeroTV](block:AeroTV) | elevon halves and rudder | 2 | 0.0195, 0.0195, 0.0117 |
| [FusAero](block:FusAero) | `FuselageAero`: quadratic drag per body axis (drag areas 0.003, 0.03, 0.02 m$^2$) and rotational damping | - | - |

Parameters: $L_a$ = 4.4 /rad, $L_b$ = 0.25, $D_a$ = 0.2 /rad, $D_b$ = 0.04 (assumed; the thesis estimates them with a genetic algorithm but its fitted values are not in the paper), tail $L_a$ = 3.2.
`Air` ([Air](block:Air)) is a constant wind vector (zero for the nominal runs). Limits of the model, as in the thesis: the lift depends only on the *current* angle of attack (no unsteady or dynamic-stall effects) and there is no induced downwash; the model is
good for forces and moments to the 10 to 20 % level, which is enough for the controller design but not for a quantitative power claim.
