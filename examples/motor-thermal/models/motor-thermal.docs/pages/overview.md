# Motor thermal: copper loss into a heat network

A 24 V DC motor drives a fan while its copper loss heats the winding. The winding conducts heat through the insulation into the housing, and the housing cools to the ambient air by convection. The motor is a [DCMotorThermal](block:Motor): the DC motor with its winding resistance replaced by a heated resistor, so the resistance follows the winding temperature and the whole copper loss leaves the `winding` port as heat flow.

![The model canvas|900](assets/a2282efb1e5a.png)

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
