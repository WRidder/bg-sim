# Results and energy balance

![Temperatures, heat flows and the hot resistance|900](assets/0712a58714fa.png)

## Steady state

At steady state every heat flow is equal, and the loop closes through the resistance:

$$R = R_0\,(1 + \alpha\,(T_w - T_{ref})),\quad \omega = \frac{k\,V}{k^2 + R\,d},\quad i = \frac{d\,\omega}{k},\quad P = R\,i^2$$

$$T_h = T_a + \frac{P}{h\,A},\qquad T_w = T_h + \frac{P}{G_{ins}}$$

The fixed point is $T_w$ = 322.95 K (49.8 °C), $T_h$ = 311.03 K, $R$ = 2.234 Ω, $P$ = 17.88 W and $\omega$ = 353.6 rad/s. The run reaches it within 1e-6 after 2400 s; `expected.json` checks all five values.

## First law, at every sample

![Heat energies and fan speed|900](assets/933674ea012c.png)

The three integrators turn the sensed heat flows into energies, so the first law of each heat capacity is a linear combination of recorded signals:

$$E_{loss}(t) - E_{ins}(t) - C_w\,T_w(t) = \text{const},\qquad E_{ins}(t) - E_{conv}(t) - C_h\,T_h(t) = \text{const}$$

Both hold to 1e-6 of the 40 kJ that pass through the network. The heat flow leaving the winding port equals the electrical power dissipated in the winding, $v \cdot i$, to 1e-9 W: the heated resistor converts its loss into heat exactly. On the electrical and rotational side the port-power ledger closes (Tellegen) with the heated resistor counted as dissipation; the thermal ports are left out of that ledger because their $T \cdot Q$ is not a power.
