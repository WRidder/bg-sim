# Physics of the DC motor

The `DCMotor` block couples the electrical winding to the shaft through the torque constant $k_t$. With winding current $i$, shaft speed $\omega$ and supply voltage $V$ the two energy storages (winding inductance and rotor inertia) give

$$L\,\frac{di}{dt} = V - R\,i - k_t\,\omega, \qquad J\,\frac{d\omega}{dt} = k_t\,i - d\,\omega .$$

The coupling is a gyrator: the same constant $k_t$ converts current to torque and speed to back-EMF, so no power is created or lost in the conversion. The viscous damping $d$ of the rotor is modelled in a separate `RotationalDamper` (`Damp1`), because the `DCMotor` of this model has `d = 0`.

## Parameters

| quantity | symbol | value | unit |
| --- | --- | --- | --- |
| winding resistance | $R$ | 2 | Ω |
| winding inductance | $L$ | 5e-4 (0.5 mH) | H |
| torque constant | $k_t$ | 0.05 | N·m/A |
| rotor inertia | $J$ | 1e-5 | kg·m² |
| damping in `DCMotor` | $d$ | 0 | N·m·s/rad |
| damper `Damp1` | $d$ | 1e-6 | N·m·s/rad |
| supply | $V$ | 12 V step at $t = 0.01$ s (Step1: 0 to 12) | V |
| `t_end` | | 1 | s |

## Steady state

Setting both derivatives to zero gives $i = (V - k_t \omega)/R$ and $k_t i = d\,\omega$, so

$$\omega_\infty = \frac{k_t V}{k_t^2 + R\,d} = \frac{0.05 \cdot 12}{0.05^2 + 2 \cdot 10^{-6}} = 239.808\ \mathrm{rad/s}, \qquad i_\infty = \frac{d\,\omega_\infty}{k_t} = 4.796\ \mathrm{mA}.$$

The electrical time constant $L/R = 0.25\ \mathrm{ms}$ is much faster than the mechanical one, about $J R/k_t^2 = 8\ \mathrm{ms}$ (the back-EMF acts as a damper of $k_t^2/R$), so the speed reaches 240 rad/s within about 40 ms of the step.
