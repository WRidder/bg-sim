# Control laws

Angles are in deg, rates in deg/s, surfaces in deg. The book's signs apply: a positive aileron rolls left and a positive rudder yaws left.

## Pitch

The stick commands a load factor: 10 g per unit aft and 4 g per unit forward. A turn compensation $tc = 1/\cos\phi - 1$ (faded out beyond 60 deg of bank) adds the load factor of a level turn, so a centred stick holds the altitude in a bank:

$$n_{cmd} = 1 + 10\,\delta_{stick} + tc, \qquad q_{stick} = \frac{g_0}{V_t}\Big(\Delta n_{cmd} + 2\,\mathrm{clamp}\big(\Delta n_{cmd} - \Delta n, \pm 0.5\big)\Big)$$

where $\Delta n_{cmd} = n_{cmd} - \cos\gamma\cos\phi$ and $\Delta n = n_z - \cos\theta\cos\phi$ (zero in steady straight flight and in a steady level turn). The first term is the pitch rate of the steady manoeuvre. The g-error term builds the load factor in about half a second instead of the airframe's path time constant. In the 60 deg turn below it cuts the altitude loss over 30 s from about 160 m to 45 m. The clamp keeps a full-stick pull from overdriving the alpha limiter. The limiter of `f16-envelope` follows, with a −3 g floor: $q_{cmd} = \max(\min(q_{stick}, q_\alpha, q_g), q_{neg})$. The law is the scheduled `PitchFBW` of `f16-fbw`.

### The stabilator's rate limit

The pitch gains fall as $1/\bar q$, so they are large at the low end of the schedule: below about 150 KEAS a small pitch rate already asks for more than the servo's 60 deg/s. A plain rate limit only turns round when the command crosses its output, so it lags, and the loop settles in a limit cycle: after a tap on the stick the stabilator keeps swinging ±20 deg at 60 deg/s. [StabComp](block:StabComp), the compensator of `f16-pio`, sits between the law and the servo. With $e = u - y$:

$$\dot y = \mathrm{clamp}\Big(\dot u_f + (0.5 + 20\,w)\,e + 6\,\big(e - \mathrm{clamp}(e, \pm 12)\big),\ \pm 60\Big)$$

The output turns round as soon as the command does ($\dot u_f$, the command's filtered derivative), and a slow pull-back brings it onto the command again. The pull-back must stay slow, or the limit cycle returns. A stick reversal at full rate can leave the output 20 deg off the command, so the part of the error beyond 12 deg is pulled back at 6 1/s. On the wheels ($w$) it is a plain rate limit, because the stick commands the stabilator directly there.

## Roll

The stick commands the stability-axis roll rate $p_s = p\cos\alpha + r\sin\alpha$, a roll about the velocity vector:

$$p_{cmd} = p_{lim}\,\delta_{roll}, \qquad p_{lim} = 240\ \mathrm{clamp}\Big(\frac{\bar q}{12\ \mathrm{kPa}}, 0.3, 1\Big)\ \mathrm{clamp}\big(1 - 0.075 (n_z - 1), 0.4, 1\big)$$

$$\delta_a = K_p (p_s - 0.5\,p_{cmd}) + \xi_p, \qquad \dot\xi_p = K_{ip} (p_s - p_{cmd}) + \frac{\mathrm{sat}(\delta_a) - \delta_a}{0.1}$$

so the limit is 210 deg/s at 1 g and 500 ft/s and falls with the load factor and at low dynamic pressure. $K_p$ and $K_{ip}$ place the roll loop at 4 rad/s with damping 0.8 on the roll-subsidence model $\dot p = L_p p + L_{\delta a}\delta_a$ of each grid point (`design/lateral.py`).

## Yaw

$$\delta_r = K_{ari}\,\delta_a + K_r\, r_{wo} + K_\beta (\beta - \beta_{cmd}) + \xi_\beta, \qquad \dot\xi_\beta = K_{i\beta} (\beta - \beta_{cmd}) + \frac{\mathrm{sat}(\delta_r) - \delta_r}{0.1}$$

- $r_{wo}$ is the stability-axis yaw rate through a 1 s washout, so the yaw damper does not fight a steady turn.
- The sideslip integral holds $\beta = \beta_{cmd} = -6\,\delta_{pedal}$ deg, so a turn with the pedals centred is coordinated.
- The aileron-rudder interconnect $K_{ari}(\alpha) = (\tan\alpha\, L'_{\delta a} - N'_{\delta a}) / (N'_{\delta r} - \tan\alpha\, L'_{\delta r})$ cancels the yaw that the ailerons cause about the velocity vector. It runs from −0.53 at 0 deg alpha to 1.9 at 20 deg, clamped to [−1, 2].

$K_r$, $K_\beta$ and $K_{i\beta}$ come from a joint optimisation at each grid point: the integrated error of a sideslip step, plus the sideslip of a roll, with a penalty when the dutch-roll damping falls below 0.6. Over the 5 × 5 grid (qbar 80..1400 psf, Mach 0.2..1.0) the full law gives a dutch-roll damping of at least 0.6, and a roll-rate step rises in 0.35..0.55 s.
