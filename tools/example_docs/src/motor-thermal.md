@@ figures motor-thermal
{
  "diagram": {"kind": "diagram", "model": "motor-thermal"},
  "temperatures": {
    "kind": "plot", "model": "motor-thermal", "xlim": [0, 2400],
    "rows": [
      {"ylabel": "temperature [K]", "series": [{"signal": "TWinding/y", "label": "TWinding/y (winding)"}, {"signal": "THousing/y", "label": "THousing/y (housing)"}],
       "hlines": [{"y": 322.947, "label": "steady winding 322.95 K"}, {"y": 293.15, "label": "ambient 293.15 K"}], "legend": true},
      {"ylabel": "heat flow [W]", "series": [{"signal": "Loss/y", "label": "Loss/y (copper loss)"}, {"signal": "QIns/y", "label": "QIns/y (insulation)"}, {"signal": "QConv/y", "label": "QConv/y (convection)"}], "legend": true},
      {"ylabel": "R [Ohm]", "series": [{"signal": "Motor/R_hot", "label": "Motor/R_hot", "color": "#1b9e77"}]}
    ]
  },
  "energies": {
    "kind": "plot", "model": "motor-thermal", "xlim": [0, 2400],
    "rows": [
      {"ylabel": "energy [kJ]", "series": [{"signal": "ELoss/y", "label": "ELoss/y (copper loss)", "scale": 0.001}, {"signal": "EIns/y", "label": "EIns/y (through insulation)", "scale": 0.001}, {"signal": "EConv/y", "label": "EConv/y (to ambient)", "scale": 0.001}], "legend": true},
      {"ylabel": "speed [rad/s]", "series": [{"signal": "Speed/y", "label": "Speed/y", "color": "#7570b3"}]}
    ]
  }
}
@@ page motor-thermal overview - | Overview
# Motor thermal: copper loss into a heat network

A 24 V DC motor drives a fan while its copper loss heats the winding. The winding conducts heat through the insulation into the housing, and the housing cools to the ambient air by convection. The motor is a [DCMotorThermal](block:Motor): the DC motor with its winding resistance replaced by a heated resistor, so the resistance follows the winding temperature and the whole copper loss leaves the `winding` port as heat flow.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Supply](block:Supply), [Gnd](block:Gnd) | 24 V source (driven by the constant `One`) and ground |
| [Motor](block:Motor) | DC motor, R = 2 Ω at 293.15 K, copper `alpha` = 0.00393 1/K, `k_t` = 0.05 N·m/A |
| [Fan](block:Fan), [Drag](block:Drag), [Frame](block:Frame) | fan inertia 2e-4 kg·m², viscous drag 4e-4 N·m·s/rad, the fixed frame |
| [Winding](block:Winding), [Housing](block:Housing) | heat capacities 30 J/K (copper) and 150 J/K (aluminium) |
| [Insulation](block:Insulation) | thermal conductance 1.5 W/K from winding to housing |
| [Film](block:Film), [Ambient](block:Ambient) | convection, h = 20 W/(m²·K) on 0.05 m², to 293.15 K |
| [Loss](block:Loss), [QIns](block:QIns), [QConv](block:QConv) | series heat flow sensors; [ELoss](block:ELoss), [EIns](block:EIns), [EConv](block:EConv) integrate them |

Thermal ports carry the absolute temperature (K) and the heat flow into the block (W). Their product is not a power: the thermal domain is a pseudo bond graph, as in Modelica and Simscape. That is why a thermal port only connects to thermal ports, and why the heated resistor is the only bridge from the electrical side.

## What to try

1. Press **Run** and open the plot "Winding and housing temperature": the winding heats quickly (time constant about 20 s), then both rise together with the slow housing (about 3 minutes).
2. Plot [Motor/R_hot](signal:Motor/R_hot) and [Speed/y](signal:Speed/y): the resistance rises 11.7 %, the current falls and the fan slows from 368 to 353.6 rad/s.
3. Set `alpha` of the motor to 0: the loop opens, the winding gets hotter (the loss no longer falls), and the speed stays at its cold value.
4. Double `h` of [Film](block:Film) (a fan blowing on the housing): both temperatures drop, the winding by more than the housing.

Next: [results and energy balance](page:results).
@@ page motor-thermal results overview | Results and energy balance
# Results and energy balance

![Temperatures, heat flows and the hot resistance|900](@fig:temperatures)

## Steady state

At steady state every heat flow is equal, and the loop closes through the resistance:

$$R = R_0\,(1 + \alpha\,(T_w - T_{ref})),\quad \omega = \frac{k\,V}{k^2 + R\,d},\quad i = \frac{d\,\omega}{k},\quad P = R\,i^2$$

$$T_h = T_a + \frac{P}{h\,A},\qquad T_w = T_h + \frac{P}{G_{ins}}$$

The fixed point is $T_w$ = 322.95 K (49.8 °C), $T_h$ = 311.03 K, $R$ = 2.234 Ω, $P$ = 17.88 W and $\omega$ = 353.6 rad/s. The run reaches it within 1e-6 after 2400 s; `expected.json` checks all five values.

## First law, at every sample

![Heat energies and fan speed|900](@fig:energies)

The three integrators turn the sensed heat flows into energies, so the first law of each heat capacity is a linear combination of recorded signals:

$$E_{loss}(t) - E_{ins}(t) - C_w\,T_w(t) = \text{const},\qquad E_{ins}(t) - E_{conv}(t) - C_h\,T_h(t) = \text{const}$$

Both hold to 1e-6 of the 40 kJ that pass through the network. The heat flow leaving the winding port equals the electrical power dissipated in the winding, $v \cdot i$, to 1e-9 W: the heated resistor converts its loss into heat exactly. On the electrical and rotational side the port-power ledger closes (Tellegen) with the heated resistor counted as dissipation; the thermal ports are left out of that ledger because their $T \cdot Q$ is not a power.
