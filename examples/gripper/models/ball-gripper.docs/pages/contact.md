# Contact model: `MovingPlaneContact`

The jaw pads are the stdlib block [JawA](block:JawA) / [JawB](block:JawB) (`stdlib:contact/MovingPlaneContact`): a sphere of radius $r$ (or a point, $r = 0$) of a spatial body against a finite rectangular face that moves. The face is carried by the carriage (inputs `pc`, `vc`) and slides along the jaw axis $a$ by the Translation port `j`; its origin is $p_c + o + a\,x_s$ with the jaw travel $x_s$.

**Normal force.** With the face normal $n$ and the sphere centre $c$, the penetration is $\delta = r - n\cdot(c - p_c - o - a x_s)$. The Hunt-Crossley law (as `ContactPoint`)

$$f_n = G_e\, k\, x \sqrt{x/x_{ref}}\,(1 + c_d\,\dot x)$$

uses a smooth positive part $x$ of $\delta$ and a smooth no-pull clamp. The edge gate $G_e = q_1 q_2$, $q_i = \tfrac14 (1 + \tanh((w_i - u_i)/w_e))(1 + \tanh((w_i + u_i)/w_e))$, fades the force out beyond the face half-widths $w_i$, so a part can slide off the face.

**Friction.** The slip velocity at the contact point is $u = v - r(\omega\times n) - v_p$, $v_p = v_c + a\,\dot x_s$, projected on the two face tangents. The friction is isotropic regularised Coulomb,

$$F_t = -\mu f_n \tanh(|s|/v_s)\, \frac{s}{|s|},$$

so below the slip limit a held part creeps at $|s| = v_s\, \mathrm{atanh}(|F_t|/(\mu f_n))$ (the regularisation error); the output `util` $= |F_t|/(\mu f_n)$ is the share of the friction limit in use.

**Ports.** The wrench on the body goes to `p` in the point frame (torque $r\,(n \times F_t)$ about the centre); the jaw receives $j.e = F\cdot a$; the carriage power is $P_c = F\cdot v_c$. The balance $p.P + j.P + P_c = \dot E_c + P_d$ is checked in the golden test.

Ball pads: polyurethane, $k = 1.2\cdot10^5$ N/m at $x_{ref} = 0.1$ mm (the Hertz constant of the 50 mm ball, $K = 1.2\cdot10^7$ N/m$^{1.5}$), $c_d = 5$ s/m, $\mu = 0.25$, $v_s = 1$ mm/s, 24 × 24 mm faces. The table is the same block with a static carrier ([TableFrame](block:TableFrame)).
