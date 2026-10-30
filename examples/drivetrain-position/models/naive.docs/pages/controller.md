# The textbook PID

The design looks at the plant as a **rigid body**. With everything welded together, the motor-side inertia is $J_{tot} = J_m + (J_1 + J_2)/n^2 = 8\cdot10^{-5}$ kg·m² and the motor angle follows the voltage through the first-order lag

$$\frac{\dot\theta_m}{V} = \frac{K_g}{\tau s + 1}, \qquad K_g = \frac{k_t/R}{k_t^2/R + R_d} = 9.9\ \frac{\text{rad/s}}{\text{V}},\quad \tau = \frac{J_{tot}}{k_t^2/R + R_d} = 7.9\ \text{ms}.$$

The textbook recipe for such a plant: cancel the lag with the derivative time, $T_d = \tau$, choose the crossover $\omega_c$ and put the integral time at four times the crossover period, $T_i = 4/\omega_c$:

$$K_p = \frac{\omega_c}{K_g}, \qquad T_i = \frac{4}{\omega_c}, \qquad T_d = \tau.$$

With $\omega_c = 30$ rad/s (about 5 Hz, a modest bandwidth for a servo) this gives $K_p$ = 3.03 V/rad (of the motor angle), $T_i$ = 0.133 s, $T_d$ = 7.9 ms, a derivative filter $N = 10$ and back-calculation anti-windup against the 24 V clamp. [PID](block:PID) implements

$$v = K_p\,e + x_i - K_p T_d N\,(y - x_d), \quad u = \operatorname{clamp}(v, -24, 24), \quad \dot x_i = \frac{K_p}{T_i}\,e + \frac{u - v}{\sqrt{T_i T_d}}$$

(with the stdlib `PID` the integral gain would be $K_p/T_i^2$ and the derivative gain $T_d$, so the textbook form is a small project block).

## Why the load rings

The motor-side loop is collocated, hence stable, and it holds the motor tightly: the load wheel then hangs on the shaft spring against a stiff base and rings at $\sqrt{k/J_2}$ = 3.9 Hz with the damping of the shaft alone. The loop does not see the load, so it cannot damp it. The step of 1 rad (10 rad on the motor) saturates the supply and throws the load past the target.
