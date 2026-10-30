# DC motor, bond graph model

The same motor as in `iconic`, written as a bond graph (plan 9.1). The chain is

$$S_e \to 1_{J1}\,(R,\ I) \to GY \to 1_{J2}\,(I,\ R)$$

- [Se1](block:Se1): constant effort source, $e = 12\ \mathrm{V}$ (no step, unlike the iconic model);
- [J1](block:J1): 1-junction, common current $i$, with [R1](block:R1) (`r` = 2 Ω) and [IL](block:IL) (`i` = 5e-4 H, the winding inductance);
- [GY1](block:GY1): gyrator with `r` = 0.05 (the torque constant $k_t$);
- [J2](block:J2): 1-junction, common speed $\omega$, with [IJ](block:IJ) (`i` = 1e-5 kg·m², the rotor inertia) and [Rd](block:Rd) (`r` = 1e-6, the viscous damping).

![Diagram of the bond graph model|800](assets/4502c7fb031f.png)

## Equations

On a 1-junction the flows are equal and the efforts sum to zero; the gyrator exchanges efforts and flows with the ratio $k_t$:

$$e_{GY,1} = k_t\,\omega, \qquad e_{GY,2} = k_t\,i .$$

$$L\,\dot i = 12 - R\,i - k_t\,\omega, \qquad J\,\dot\omega = k_t\,i - d\,\omega .$$

These are the equations of the `iconic` model with $d = 10^{-6}$ taken at the rotor junction. Both models therefore settle at the same $\omega_\infty = 239.808\ \mathrm{rad/s}$. The `Se` is a constant 12 V from $t = 0$, so only the settled part is comparable with the iconic run: from $t = 0.5$ s the two speeds (`IJ/p.f` and `Motor1/shaft.f`) agree to better than 1e-6 rad/s (the acceptance threshold in `expected.json`).

## Run it and the checks

Plot [IJ/p.f](signal:IJ/p.f) (the rotor speed) and [Rd/p.f](signal:Rd/p.f) (the same flow seen at the damper). The check `final_value` expects $\omega(1\,\mathrm{s}) = 239.80815347721824\ \mathrm{rad/s}$ within relative 1e-4.

## 3D view

The bond graph has no angle signal, so the rotor disc of the scene is coloured by the rotor speed [IJ/p.f](signal:IJ/p.f) (heat map from 0 to 240 rad/s).

![3D view at t = 0.5 s|500](assets/29b3cca6738d.png)
