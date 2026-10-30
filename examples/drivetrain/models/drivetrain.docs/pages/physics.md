# Physics

## Parameters

| parameter | value | meaning |
| --- | --- | --- |
| `Motor1` $R$, $L$, $k_t$, $J$, $d$ | 1 Ω, 1 mH, 0.1 N·m/A, 5e-5 kg·m², 1e-4 N·m·s/rad | the DC motor |
| `Gear1.n` | 10 | `a.f` = n · `b.f` |
| `Wheel1.J`, `Wheel2.J` | 1e-3, 2e-3 kg·m² | the two inertias |
| `Rod.k`, `RodDamper.d` | 5 N·m/rad, 0.02 N·m·s/rad | the flexible rod |
| `Step1` | 0 to 12 V at 0.01 s | supply |
| `LoadStep`, `Load.T` | 0 to 1 at 1.0 s, 0.5 N·m | load torque |

The run lasts 2 s with 5000 output points (`solver` auto, `reltol` 1e-6).

## Equations

Motor (as in the `dc-motor` example), with speed $\omega_m$ and current $i$:

$$L\,\dot i = V - R\,i - k_t\,\omega_m, \qquad J_m\,\dot\omega_m = k_t\,i - d\,\omega_m - \frac{T_g}{1} .$$

The ideal gear has speed ratio $n = 10$ and conserves power, so $\omega_m = n\,\omega_1$ and the torque on the wheel side is $n\,T_g$. Wheel 1 and wheel 2 with the rod twist $\varphi = \theta_1 - \theta_2$:

$$J_1\,\dot\omega_1 = n\,T_g - k\,\varphi - c\,(\omega_1 - \omega_2), \qquad J_2\,\dot\omega_2 = k\,\varphi + c\,(\omega_1 - \omega_2) - T_L,$$

with $k = 5$ N·m/rad, $c = 0.02$ N·m·s/rad and $T_L = 0.5$ N·m for $t \ge 1$ s.

## Two-inertia mode

Reflecting the motor rotor through the gear, the near side has

$$J_1^{\mathrm{eff}} = J_{wheel1} + n^2 (J_m) = 1\cdot10^{-3} + 100\cdot 5\cdot10^{-5} = 6\cdot10^{-3}\ \mathrm{kg\,m^2}, \qquad J_2 = 2\cdot10^{-3}\ \mathrm{kg\,m^2}.$$


The undamped mode of the rod between the two inertias, with the motor rotor free, would be

$$\omega_n = \sqrt{k\left(\frac{1}{J_1^{\mathrm{eff}}} + \frac{1}{J_2}\right)} = \sqrt{5\,(166.7 + 500)} = 57.7\ \mathrm{rad/s} \approx 9.2\ \mathrm{Hz}.$$

In the model the motor is not free: the voltage source holds the armature, so the back-EMF acts as a viscous damper $k_t^2/R = 0.01$ N·m·s/rad at the motor shaft, which is $n^2 k_t^2/R = 1$ N·m·s/rad at wheel 1. That damps the mode strongly and lowers its frequency. The run shows it directly: the twist peaks at 0.0448, 0.1716, 0.2985 and 0.4253 s with heights 0.1865, 0.0722, 0.0279 and 0.0108 rad, a **period of 0.1268 s (7.9 Hz)** and a decay of 0.39 per period. The README quotes about 29 Hz; that is what an undamped rod of $k = 50$ N·m/rad would give ($\sqrt{50 \cdot 666.7} = 182.6$ rad/s), not the model value ($k = 5$ N·m/rad).

## Steady states

Before the load: $\omega_m = k_t V/(k_t^2 + R d) = 118.8$ rad/s. After the load step the reflected load torque is $T_L/n = 0.05$ N·m at the motor shaft, so $k_t i = d\,\omega_m + 0.05$ with $i = (V - k_t\omega_m)/R$ gives $\omega_m = 113.86$ rad/s, $i = 0.614$ A, and the rod carries the load with $\varphi = T_L/k = 0.1$ rad.
