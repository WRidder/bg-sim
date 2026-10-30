# The controller design

## Structure: cycle-averaged, discrete, ideal state feedback

The flapping makes every signal of the bird oscillate at the flapping frequency; the controllers work on the **cycle average**. The design is done in four steps (`design/design.py`):

1. **Sizing of the figure from a turn-radius estimate.** The figure $x = A\sin\vartheta$, $y = B\sin 2\vartheta$ has a smallest radius of curvature $r_{min}$ at the crossing; at the cruise speed $U$ a coordinated turn needs the bank
   $\phi = \arctan(U^2/(g\,r_{min}))$. With $A$ = 110 m and $B$ = 42 m: lap 596 m, $r_{min}$ = 26.50 m, **bank 29.0 deg**, period 49.7 s at 12 m/s
   (measured peak bank 31.4 deg, limit 34 deg). For comparison a smaller figure with $A$ = 60 m, $B$ = 25 m has $r_{min}$ = 13.9 m and would need 47 deg of bank at this speed.
2. **Trim from the full flapping model** (`design.py trim`): the closed loop with the path following switched off flies straight for 34 s; the cycle averages over the last 10 s are the trim:
   $f_0$ = 3.968 Hz, pitch $\theta_0$ = 7.37 deg, elevator $\delta_{e0}$ = -0.126 rad, speed 11.94 m/s, vertical speed 0.012 m/s,
   electrical power 21.8 W, aerodynamic power 15.6 W.
3. **Sensitivities from the full model** (`design.py identify`): short open-loop runs around the trim (two flapping cycles after a 0.3 s settling window; table in the README) give the cycle-averaged acceleration per unit of every input
   (flapping frequency $f$, pitch attitude, elevator $\delta_e$, differential tail $\delta_a$, rudder $\delta_r$, amplitude asymmetry $\eta$). They fix the signs and the order of magnitude of each loop; the short window contains the strong aerodynamic damping of the flapping wings, so the
   gains were then **tuned by iterating in the full closed-loop flapping model**, not computed from a linear model. No loop margins are claimed.
4. **Verification in the full flapping model**, always (this page's results).

## Blocks

| block | rate | role |
| --- | --- | --- |
| [Guide](block:Guide) `Guidance` | 50 Hz | path table (2 m spacing); nearest point, along-track and cross-track error $e$; heading law $\dot\psi = U\kappa(s + t_{lead}U) + k_\chi(\chi_{des} - \chi)$, $\chi_{des} = -\arctan(e/L)$ ($L$ = 25.0 m look-ahead, $k_\chi$ = 1 /s, $t_{lead}$ = 0.6 s to cancel the roll lag); altitude reference with climb-rate feed-forward |
| [Fctl](block:Fctl) `FlightCtrl` | 100 Hz | the inner loops below, with notch filters at $f$ and $2f$ (pole radius 0.95, unit DC gain) on every feedback signal for the cycle average |
| [FlapCtl](block:FlapCtl) | analogue | motor speed PI, see [the drive](page:wing) |
| [ServoTL](block:ServoTL) | servo | first-order command lag 40 ms, PD torque, stall 0.3 N m |

Inner loops (`FlightCtrl`; nose-up pitch $\theta$, roll $\phi$ with left wing up positive, $n = 1/\cos\phi$):

$$f = f_0 + K_{pu}(U_c - U) + I_u + K_{fn}(n - 1), \qquad \theta_c = \theta_0 + K_{\theta n}(n-1) + K_{pv}(v_{z,c} - v_z) + I_{vz},\quad v_{z,c} = K_z(z_c - z) + v_{z,ff}$$
$$\delta_e = \delta_{e0} - K_\theta(\theta_c - \theta) + K_q\,q_{up}, \qquad \phi_c = -\arctan\frac{U\dot\psi}{g}, \qquad \delta_a = K_\phi(\phi_c - \phi) - K_p p + I_\phi, \qquad \delta_r = -K_r(\dot\psi\cos\phi - r)$$

The elevons get $\delta_e \pm \delta_a$, the rudder $\delta_r$, the flapping drive $f$ and the amplitude asymmetry $\eta = K_\eta(\phi_c - \phi)$ ($K_\eta$ = 0 here: the tail has enough roll authority at this size).
Gains: $K_\theta$ = 1.2, $K_q$ = 0.12 s, $K_{pu}$ = 0.3 Hz s/m, $K_{iu}$ = 0.15 Hz/m, $K_z$ = 0.25 /s, $K_{pv}$ = 0.06 rad s/m, $K_\phi$ = 0.8, $K_p$ = 0.05 s, $K_r$ = 0.15 s (defaults of `library/FlightCtrl.jl`, listed in the README).
All commands are limited (flapping frequency 2.0 to 4.5 Hz, tail deflection $\pm 0.45$ rad, bank 0.6 rad) and the integrators are clamped.

**Honesty notes.** The controller feeds back the ideal truth (`Truth`: attitude, rates, ground velocity, position), not sensor models: the example is about the flapping flight dynamics, not about estimation (see `quadcopter` for a full sensor chain). The loop is **speed-controlled flapping, not torque-controlled**:
the within-stroke ripple of the motor speed is a result of the model. The measured flapping frequency saturates at the upper limit of 4.5 Hz for a short time in the turns.
