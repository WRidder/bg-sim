# Plant: a PMSM as a bond graph

```
Vd(MSe) -> DJ(1) -- Rd(R_s) -- Id(L_d) -- IdSens -- MGY(u = w_e L_q)
Vq(MSe) -> QJ(1) -- Rq(R_s) -- Iq(L_q) -- IqSens -- Bemf(MSe, +k_e w_m)
                    |                                '-- GY(r = k_t) -> MJ(1)
Iq(IqSens) -- IqSrc(MSf, -1) -- GY.p1
MJ(1) -- Jm(I) -- Bm(R) -- WmSens -- Theta(integrator)
```

The dq equations are exactly plan 9.6b, with electrical speed $\omega_e = p\,\omega_m$:

$$v_d = R_s\,i_d + L_d\,\frac{di_d}{dt} - \omega_e L_q\,i_q, \qquad v_q = R_s\,i_q + L_q\,\frac{di_q}{dt} + \omega_e\,(L_d\,i_d + \psi_m),$$

$$T_e = \tfrac32\,p\,\psi_m\,i_q, \qquad J\,\frac{d\omega_m}{dt} = T_e - B\,\omega_m - T_{load}.$$

## Elements and signs

- [DJ](block:DJ) and [QJ](block:QJ) are the d and q 1-junctions; [Rd](block:Rd)/[Id](block:Id) and [Rq](block:Rq)/[Iq](block:Iq) are stator resistance and inductance; [IdSens](block:IdSens), [IqSens](block:IqSens) are flow sensors.
- [MGY](block:MGY) (`p1` on `DJ`, `p2` on `QJ`) has the signal modulus $\omega_e L_q$ from the gain [WeL](block:WeL) ($p\,L = 0.024$) of the measured speed. It produces the cross terms $-\omega_e L_q i_q$ and $+\omega_e L_d i_d$ (the surface-mount assumption $L_d = L_q = L$ makes one gyrator exact).
- [Bemf](block:Bemf) is an `MSe` on `QJ` with gain $k_e$ = 0.32 and input $\omega_m$; the junction sees $-k_e\omega_m$, i.e. the $+\omega_e\psi_m$ back-EMF of the q equation.
- [GY](block:GY) has $r = k_t = 1.5\,p\,\psi_m = 0.48$ N·m/A; its p2 torque is $+k_t i_q$ into [MJ](block:MJ). The measured $i_q$ drives its p1 through [IqSrc](block:IqSrc), an `MSf` with gain -1. This `MSf` is the **dq 3/2 power-scale interface**: the per-axis dq electrical bond carries $v_d i_d + v_q i_q$ while the shaft carries $T_e\,\omega_m = 1.5\,k_e\,i_q\,\omega_m$; the gyrator supplies the torque and the `MSf` absorbs the difference.
- `MJ` carries the rotor inertia [Jm](block:Jm), viscous [Bm](block:Bm), the speed sensor [WmSens](block:WmSens) and the load torque source [Load](block:Load) (driven by [LoadStep](block:LoadStep): 0 to -2 at 0.9 s, a 2 N·m resisting torque). [Theta](block:Theta) is a kinematic integrator of the measured speed (the D28 sensor exception) used by the controller.

## Parameters

| quantity | value |
| --- | --- |
| DC bus, voltage limit | $V_{dc} = 300$ V, $V_{dc}/\sqrt3 = 173.205$ V |
| stator | $R_s = 0.5\ \Omega$, $L_d = L_q = 6$ mH |
| magnet, pole pairs | $\psi_m = 0.08$ Wb, $p = 4$ ($k_t = 0.48$ N·m/A, $k_e = 0.32$ V·s/rad) |
| rotor | $J_m = 0.44\cdot10^{-3}$ kg·m², $B_m = 10^{-4}$ N·m·s/rad |
| current | rated 5 A peak, limit 15 A peak (7.2 N·m) |
| run | 1.2 s, `solver` auto, 6001 points, `reltol` 1e-8, `event_limit` 200000 |

The only code nodes of the plant are sensors (allowed by D28): the flow sensors, the `Theta` integrator and the recording sensor `Iphase`, the peak phase-current amplitude $\sqrt{i_d^2 + i_q^2}$ (amplitude-invariant Park transform), which is not part of the plant.
