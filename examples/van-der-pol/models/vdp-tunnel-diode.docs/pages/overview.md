# Van der Pol in electronics: a tunnel-diode oscillator

Balthasar van der Pol found his equation in 1920 in a triode oscillator. The same equation describes any LC tank on an element with a **negative differential resistance**: at small amplitude the element feeds energy into the tank and the oscillation grows, and at large amplitude it takes energy out. The amplitude settles where the two balance, on a **limit cycle**. A tunnel diode biased between its peak and its valley is the cleanest modern case. It oscillates up to the GHz range with a single active component.

This model is that oscillator as a bond graph, with the textbook equation running alongside in the circuit's own seconds.

![The model canvas|900](assets/02051b21b888.png)

| block | role |
| --- | --- |
| [J0](block:J0) | the 0-junction: one voltage $v$ across the tank, the diode and the detector |
| [Cap](block:Cap), [Jc](block:Jc), [Ic](block:Ic) | the tank capacitor $C$ (a C element), its branch current $i_C$ |
| [Ind](block:Ind), [Jl](block:Jl), [Il](block:Il) | the tank inductor $L$ (an I element), its current $i_L$ |
| [Diode](block:Diode) | the tunnel diode about its bias point, a nonlinear R: $i = -a v + b v^3$ |
| [Vm](block:Vm) | voltage detector |
| [Xc](block:Xc), [Yc](block:Yc) | the scaled states $x = v/A$ and $x' = i_C/(\omega_0 C A)$ |
| [Ref](block:Ref) | the textbook equation (equation block `VanDerPol`) with $\tau = \omega_0 t$ |
| [Tank](block:Tank), [Split](block:Split) | stored energy and the diode's energy, split into supplied and absorbed |
| [Meter](block:Meter) | the cycle meter: period, frequency, amplitude and energy per cycle, from events |

## What to try

1. Open the **Dashboard**. Move **mu** from 1 to 0.1: the waveform becomes a 9.99 MHz sine of 290 mV. Move it to 5 or 10: relaxation oscillations at 5.4 MHz or lower. The **L** and **C** cards show the components that give this mu at a 10 MHz tank resonance.
2. Change **x0** to 3: the oscillation starts large and shrinks onto the same cycle.
3. Plot [Xc/y](signal:Xc/y) and [Ref/x](signal:Ref/x): the circuit and the textbook equation are the same curve.
4. Plot [Diode/P](signal:Diode/P): it is negative (the diode supplies energy) for most of the cycle and positive near the voltage peaks.

The phase portrait is an XY plot: open **Phase portrait: x' against x (circuit, scaled)** from **Saved** in the Plots toolbar, or plot [Yc/y](signal:Yc/y) and set the panel's **x** to [Xc/y](signal:Xc/y). The dashboard shows it next to the diode's operating curve, its current against the tank voltage. The phase portraits in these pages come from the same runs, drawn by the docs build.

Continue with [the circuit and the scaling](page:circuit) and [the results](page:results).
