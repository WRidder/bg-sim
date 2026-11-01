@@ figures vdp-tunnel-diode
{
  "diagram": {"kind": "diagram", "model": "vdp-tunnel-diode"},
  "run": {
    "kind": "plot", "model": "vdp-tunnel-diode", "xlim": [0, 3.2e-6], "xlabel": "t [s]",
    "rows": [
      {"ylabel": "tank voltage v [V]", "series": [{"signal": "Vm/y", "label": "Vm/y"}],
       "hlines": [{"y": 0.29125, "label": "A x_max = 291.2 mV"}, {"y": -0.29125}], "legend": true},
      {"ylabel": "scaled x = v/A", "series": [{"signal": "Xc/y", "label": "Xc/y (circuit)", "lw": 3.0}, {"signal": "Ref/x", "label": "Ref/x (textbook equation)", "style": "--", "color": "#222222"}], "legend": true},
      {"ylabel": "diode power [W]", "series": [{"signal": "Diode/P", "label": "Diode/P (negative: supplies the tank)"}], "hlines": [{"y": 0.0}], "legend": true}
    ]
  },
  "phase": {
    "kind": "plot", "model": "vdp-tunnel-diode", "width": 620, "row_height": 4.6,
    "rows": [
      {"x": "Xc/y", "xlabel": "x = v/A", "ylabel": "x' = i_C/(w0 C A)", "series": [{"signal": "Yc/y", "label": "circuit, from x = 0.5"}],
       "vlines": [{"x": 1.7320508, "label": "|x| = sqrt(3): the diode power changes sign"}, {"x": -1.7320508}], "legend": true, "legend_loc": "lower right"}
    ]
  },
  "energy": {
    "kind": "plot", "model": "vdp-tunnel-diode", "xlim": [2.5e-6, 3.2e-6],
    "rows": [
      {"ylabel": "energy [J]", "series": [{"signal": "Tank/E", "label": "Tank/E (C v^2/2 + L i^2/2)"}, {"signal": "Split/W_sup", "label": "Split/W_sup", "scale": 1.0}, {"signal": "Split/W_abs", "label": "Split/W_abs", "style": "--"}], "legend": true},
      {"ylabel": "per cycle [J]", "series": [{"signal": "Meter/dw1", "label": "Meter/dw1 (supplied per cycle)"}, {"signal": "Meter/dw2", "label": "Meter/dw2 (dissipated per cycle)", "style": "--"}], "legend": true}
    ]
  },
  "mu5": {
    "kind": "plot", "model": "vdp-tunnel-diode", "overrides": {"global:mu": 5.0}, "xlim": [0, 3.2e-6],
    "rows": [
      {"ylabel": "v [V] at mu = 5", "series": [{"signal": "Vm/y", "label": "Vm/y"}]},
      {"ylabel": "i_L [A] at mu = 5", "series": [{"signal": "Il/y", "label": "Il/y"}]}
    ]
  }
}
@@ page vdp-tunnel-diode overview - | Overview
# Van der Pol in electronics: a tunnel-diode oscillator

Balthasar van der Pol found his equation in 1920 in a triode oscillator. The same equation describes any LC tank on an element with a **negative differential resistance**: at small amplitude the element feeds energy into the tank and the oscillation grows, and at large amplitude it takes energy out. The amplitude settles where the two balance, on a **limit cycle**. A tunnel diode biased between its peak and its valley is the cleanest modern case. It oscillates up to the GHz range with a single active component.

This model is that oscillator as a bond graph, with the textbook equation running alongside in the circuit's own seconds.

![The model canvas|900](@fig:diagram)

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
@@ page vdp-tunnel-diode circuit overview | Circuit and scaling
# Circuit and scaling to the Van der Pol form

## The diode

A tunnel diode's static curve rises to a peak $(V_p, I_p)$, falls to a valley $(V_v, I_v)$ and rises again. The DC supply biases it in the middle of the falling branch, at $V_0 = (V_p + V_v)/2$. About that point the curve is fitted by an odd cubic in the voltage deviation $v$:

$$i_D(v) = -a\,v + b\,v^3 .$$

Its maximum and minimum fall on the real peak and valley when

$$A = \tfrac12 (V_v - V_p), \qquad a = \frac{3 (I_p - I_v)}{4 A}, \qquad b = \frac{a}{3 A^2}.$$

With a germanium diode of the 4.7 mA class (rounded values: peak 4.7 mA at 65 mV, valley 0.6 mA at 355 mV):

| quantity | value |
| --- | --- |
| bias point $V_0$, $I_0$ | 210 mV, 2.65 mA |
| amplitude scale $A$ | 145 mV |
| negative conductance $a$ | 21.207 mS (the diode is $-1/a = -47.15\ \Omega$ at the bias point) |
| cubic coefficient $b$ | 0.33622 A/V³ |

The cubic is the classic simplification. The real curve departs from it beyond the valley and in reverse. The bond graph models the AC deviations only. The bias source and the DC current through the inductor are not part of it.

## The bond graph

All elements share the voltage $v$, so they hang on one 0-junction. The capacitor is a C element and the inductor an I element. Both are in integral causality. The diode is a nonlinear R in conductance causality: the capacitor sets the voltage and the diode answers with a current. Its library block declares `@causality p => :flow_out` for this. The junction's flow balance and the two stores give

$$C \dot v = -i_L + a v - b v^3, \qquad L \dot i_L = v .$$

## Scaling

Differentiate the first equation and use the second:

$$\ddot v - \frac{1}{C}\,(a - 3 b v^2)\,\dot v + \frac{v}{L C} = 0 .$$

With $\omega_0 = 1/\sqrt{L C}$, $\tau = \omega_0 t$ and $v = A x$, where $A = \sqrt{a/(3b)}$:

$$x'' - \mu\,(1 - x^2)\,x' + x = 0, \qquad \mu = \frac{a}{\omega_0 C} = a\sqrt{\frac{L}{C}} .$$

So $\mu$ is the diode's negative conductance times the tank's characteristic impedance $Z_0 = \sqrt{L/C}$. For a fixed diode and resonance, the dashboard's mu slider changes $Z_0 = \mu/a$, and $L = Z_0/\omega_0$, $C = 1/(Z_0\omega_0)$ follow:

| $\mu$ | $Z_0$ | $L$ | $C$ | frequency |
| --- | --- | --- | --- | --- |
| 0.2 | 9.43 Ω | 150.10 nH | 1687.6 pF | 9.9751 MHz |
| 1 (default) | 47.15 Ω | 750.49 nH | 337.52 pF | 9.4296 MHz |
| 5 | 235.77 Ω | 3752.4 nH | 67.50 pF | 5.4108 MHz |

The tank resonance is $f_0$ = 10 MHz. The oscillation runs at $f_0 \cdot 2\pi/T(\mu)$, where $T(\mu)$ is the textbook period in $\tau$.

The scaled velocity is the capacitor current: $x' = \dot v/(\omega_0 A) = i_C/(\omega_0 C A)$. [Yc](block:Yc) computes it from the detector [Ic](block:Ic).

## Start

The run starts at $v(0) = A x_0$ with the inductor current equal to the diode current, $i_L(0) = a v_0 - b v_0^3$. The capacitor current is then 0, so the circuit starts at $(x, x') = (x_0, 0)$, exactly like [Ref](block:Ref).

## Energy

The tank stores $E = C v^2/2 + L i_L^2/2$ and loses exactly what the diode absorbs:

$$\dot E = -P_D, \qquad P_D = v\,i_D = -a A^2 \left(x^2 - \tfrac13 x^4\right).$$

The diode supplies energy ($P_D < 0$) while $|v| < \sqrt{a/b} = \sqrt3 A$ = 251 mV and dissipates it beyond. On the limit cycle the two parts cancel over each cycle. [Split](block:Split) integrates them separately.
@@ page vdp-tunnel-diode results circuit | Results
# Results

![Tank voltage, scaled state against the textbook equation, diode power (mu = 1)|900](@fig:run)

The circuit's scaled voltage and the textbook equation lie on top of each other from the first instant. The oscillation grows from 72.5 mV onto the limit cycle within three periods.

![Phase portrait of the circuit, from x = 0.5 to the limit cycle|560](@fig:phase)

## Energy per cycle

![Tank energy, energy supplied and dissipated by the diode, and their per-cycle increments|900](@fig:energy)

On the limit cycle the diode supplies 13.418 pJ per cycle on the inner part ($|x| < \sqrt3$) and dissipates the same 13.418 pJ near the voltage peaks. The tank energy returns to the same value every cycle.

## Relaxation at mu = 5

![Tank voltage and inductor current at mu = 5|900](@fig:mu5)

At $\mu = 5$ ($Z_0$ = 236 Ω) the voltage jumps between the branches and the current ramps slowly: the frequency falls to 5.41 MHz.

## Checks (`expected.json`)

| check | bgsim | reference (scipy) |
| --- | --- | --- |
| period of the tank voltage, last cycle | 106.04950 ns | 106.04950 ns |
| frequency (cycle meter) | 9.429558 MHz | 9.429558 MHz |
| amplitude $x_{max}$ | 2.008620 | 2.0086199 (averaging theory: 2) |
| $\max\lvert Xc - Ref/x\rvert$, $\max\lvert Yc - Ref/y\rvert$ | 1.4e-12, 2.4e-12 | 1.9e-11, 3.1e-11 (scipy circuit against scipy textbook) |
| energy invariant $E + \int P_D\,dt$ | drift 4.4e-13 of the energy scale | exact |
| supplied and dissipated per cycle | 13.41840 pJ each | 13.41840 pJ each |
| period vs $2\pi(1 + \mu^2/16)$ | +0.19 % | |

Two more runs set the dashboard's mu to 0.2 and 5 and check the same quantities: 9.975089 MHz and 5.410834 MHz.
@@ figures vdp-belt
{
  "diagram": {"kind": "diagram", "model": "vdp-belt"},
  "scene": {"kind": "scene", "model": "vdp-belt", "t": 30.0, "zoom": 4},
  "run": {
    "kind": "plot", "model": "vdp-belt", "xlim": [0, 10],
    "rows": [
      {"ylabel": "block velocity [m/s]", "series": [{"signal": "Vel/y", "label": "Vel/y", "lw": 3.0}, {"signal": "RefV/y", "label": "RefV/y (textbook, V x)", "style": "--", "color": "#222222"}, {"signal": "Stribeck/Vel/y", "label": "Stribeck/Vel/y (full curve)", "style": ":"}], "legend": true},
      {"ylabel": "block position [m]", "series": [{"signal": "Pos/y", "label": "Pos/y"}, {"signal": "Stribeck/Pos/y", "label": "Stribeck/Pos/y", "style": ":"}], "legend": true},
      {"ylabel": "slip [m/s]", "series": [{"signal": "Fric/w", "label": "Fric/w"}, {"signal": "Stribeck/Fric/w", "label": "Stribeck/Fric/w", "style": ":"}], "hlines": [{"y": 0.0707107, "label": "belt speed"}], "legend": true}
    ]
  },
  "curve": {
    "kind": "plot", "model": "vdp-belt", "width": 620, "row_height": 3.2,
    "rows": [
      {"x": "Fric/w", "xlabel": "slip w [m/s]", "ylabel": "F [N], cubic fit",
       "series": [{"signal": "Fric/F", "label": "Cubic: F(w) along the run"}],
       "vlines": [{"x": 0.0707107, "label": "belt speed v_b (inflection)"}], "legend": true},
      {"x": "Stribeck/Fric/w", "xlabel": "slip w [m/s]", "ylabel": "F [N], Stribeck",
       "series": [{"signal": "Stribeck/Fric/F", "label": "Stribeck: F(w) along the run", "color": "#d95f02"}],
       "vlines": [{"x": 0.0707107}], "legend": true}
    ]
  },
  "phase": {
    "kind": "plot", "model": "vdp-belt", "width": 620, "row_height": 4.6,
    "rows": [
      {"x": "Xm/y", "xlabel": "x = x'_block / V", "ylabel": "x' = x''_block / (w0 V)", "series": [{"signal": "Ym/y", "label": "cubic rig"}, {"signal": "Ref/y", "label": "textbook (against Ref/x)", "style": "--", "color": "#222222"}], "legend": true}
    ]
  }
}
@@ page vdp-belt overview - | Overview
# Van der Pol in mechanics: a block on a moving belt

A block on a spring rides a belt that runs at a constant speed $v_b$. Friction drags the block along until the spring holds it at $x_s = F_0/k$. With a friction force that **falls** as the slip velocity rises (the Stribeck effect), this equilibrium is unstable. When the block moves with the belt the slip drops and the friction rises, so the belt pushes harder. When it moves back, the friction falls. The contact acts as a negative damper and the block starts to oscillate. Squealing brakes, chattering machine slides and the bowed violin string work the same way.

![The model canvas|900](@fig:diagram)

The model has the same rig twice:

- the root diagram: the friction curve replaced by its third-order Taylor fit about the belt speed (block `BeltFriction` in [Fric](block:Fric)). This rig obeys Rayleigh's equation exactly, and its velocity obeys Van der Pol.
- [Stribeck](block:Stribeck): the full curve (block `StribeckFriction`), to show what the fit leaves out.
- [Ref](block:Ref): the textbook equation in the rig's seconds, and [RefV](block:RefV) $= V x$ in m/s.

Inside each rig: the belt is a flow source Sf on a 0-junction, whose effort is the friction force $F$. The slip $w = v_b - \dot x$ goes to the friction contact Fric, a nonlinear R in resistance causality (`@causality p => :effort_out`). The rest of the belt's flow is the block's 1-junction: mass, spring, a velocity detector and a position sensor.

## What to try

1. Plot [Vel/y](signal:Vel/y) and [RefV/y](signal:RefV/y): the same curve.
2. Plot [Fric/w](signal:Fric/w): the slip swings between 26.6 and 114.8 mm/s and never reaches 0, so the block never sticks.
3. Open the 3D view: the block (coloured by the slip) shakes by ±4.5 mm on the running belt, and the spring's rings follow.
4. Set the global `mu` to 2. The viscous coefficient $\sigma$ drops and the velocity swing exceeds the belt speed. The cubic fit then has no physical meaning: the real block would stick and slip.

Continue with [the physics and the scaling](page:physics) and [the results](page:results).

## 3D view

`scenes/vdp-belt.sdf` is the rig: a belt over two pulleys, a wall, the spring as eight rings and the block. The prismatic joint `block` follows [Pos/y](signal:Pos/y). The rings follow the same signal with gains $k/9$, and the belt's stripes move with the belt phase [BeltPhase/y](signal:BeltPhase/y), a sawtooth over one stripe pitch. The stripes tile the belt, so when the phase wraps only the end stripes change, under the guard hoods over the pulleys. Picture at 30 s:

![3D view at t = 30 s|500](@fig:scene)
@@ page vdp-belt physics overview | Physics and scaling
# Physics and scaling

## Friction curve

On the belt the slip is $w = v_b - \dot x > 0$. The friction force on the block is the Gaussian Stribeck curve plus viscous friction:

$$F(w) = F_n\left(\mu_c + (\mu_s - \mu_c)\,e^{-(w/v_s)^2}\right) + \sigma w .$$

| quantity | value |
| --- | --- |
| block mass $m$, spring $k$ | 1 kg, 100 N/m ($\omega_0$ = 10 rad/s, 1.59 Hz) |
| normal force $F_n$ | 40 N (the block's weight and a spring-loaded pressure pad) |
| $\mu_s$, $\mu_c$, $v_s$ | 0.45, 0.30, 0.1 m/s |
| belt speed $v_b = v_s/\sqrt2$ | 70.71 mm/s, the inflection point of the Gaussian drop |
| Stribeck slope $\alpha_f = -\,dF_{Stribeck}/dw$ at $v_b$ | 51.466 N s/m |
| viscous coefficient $\sigma = \alpha_f - \alpha$ | 46.466 N s/m |
| net falling slope $\alpha = \mu\sqrt{k m}$ | 5 N s/m |
| cubic coefficient $\beta = F'''(v_b)/6$ | 3431.06 N s³/m³ |
| $F_0 = F(v_b)$, $x_s = F_0/k$ | 18.925 N, 189.25 mm |

## Rayleigh, then Van der Pol

At an inflection point the Taylor series has no quadratic term. With $w - v_b = -\dot x$:

$$F = F_0 + \alpha\,\dot x - \beta\,\dot x^3 .$$

Newton's law for the block, with $y = x - x_s$, is **Rayleigh's equation**:

$$m\ddot y - \alpha\,\dot y + \beta\,\dot y^3 + k y = 0 .$$

Differentiate it and write $z = \dot y$: $m\ddot z - (\alpha - 3\beta z^2)\,\dot z + k z = 0$. This is Van der Pol in the **velocity**. With $\omega_0 = \sqrt{k/m}$, $\tau = \omega_0 t$ and $z = V x$, where $V = \sqrt{\alpha/(3\beta)}$:

$$x'' - \mu\,(1 - x^2)\,x' + x = 0, \qquad \mu = \frac{\alpha}{\sqrt{k m}} = 0.5, \qquad V = 22.04\ \mathrm{mm/s}.$$

The scaled rate is $x' = \ddot x_{block}/(\omega_0 V) = (F - k x)/(m\omega_0 V)$. [Ym](block:Ym) computes it from the force detector and the position sensor.

## Why the viscous term is needed

$V^2 = \alpha/(3\beta)$ and $v_b^2 = \alpha_f/(3\beta)$ give $V/v_b = \sqrt{\alpha/\alpha_f}$. The velocity swing is about $2V$. Without viscous friction ($\alpha = \alpha_f$) it would be $2 v_b$, so the slip would reach zero and the block would stick: that is stick-slip, a different relaxation oscillation. The viscous term keeps $\alpha/\alpha_f$ = 0.097, a swing of 62 % of the belt speed. A belt-driven oscillator is Van der Pol only near the onset of instability. The passive system, with $\sigma$ alone, would be overdamped ($\zeta$ = 2.3).

## Energy

The oscillation energy about the force balance, $E = m\dot x^2/2 + k(x - x_s)^2/2$, changes by $\dot E = (F - F_0)\,\dot x = (\alpha\dot x^2 - \beta\dot x^4)$. [Split](block:Split) integrates $-(F - F_0)\dot x$, the power the contact takes out of the oscillation. The contact feeds the oscillation while $|\dot x| < \sqrt3 V$ and takes energy back above that. The energy the belt drive dissipates in the slip, $F w$, is far larger and always positive. Only the variation of $F$ with the block's velocity matters for the oscillation.
@@ page vdp-belt results physics | Results
# Results

![Block velocity (cubic rig, textbook, full Stribeck curve), position and slip, first 10 s|900](@fig:run)

![Phase portrait of the cubic rig in Van der Pol units, against the textbook equation|560](@fig:phase)

![The friction force along the run against the slip: the cubic fit and the full curve|560](@fig:curve)

| quantity | cubic fit | full Stribeck curve |
| --- | --- | --- |
| period | 0.638068 s ($= T(0.5)/\omega_0$) | 0.638438 s (+0.058 %) |
| velocity amplitude | 44.135 mm/s (2.00249 V) | 44.959 mm/s (+1.87 %) |
| smallest slip | 26.58 mm/s | 25.75 mm/s |
| position swing | 184.74 ... 193.75 mm | 184.40 ... 193.67 mm |
| energy fed and taken back per cycle | 0.4309 mJ each | |

The fit is close because the swing stays within $\pm 0.62\,v_b$ of the inflection point. The fifth-order term of the Gaussian makes the real curve fall a little further, so the full-curve oscillation is 1.9 % larger.

## Checks (`expected.json`)

- the cubic rig's scaled velocity and acceleration against [Ref](block:Ref): maximum difference 1.5e-11 (the check allows 1e-6);
- both periods and amplitudes against scipy (SI units, the same friction laws), rtol 1e-6;
- the slip stays positive in both rigs;
- the energy invariant $E + \int -(F - F_0)\dot x\,dt$ drifts by 4.0e-11 of the energy scale (the check allows 1e-7);
- energy fed and taken back per cycle, 0.43090 mJ each;
- the 3D bindings match the scene.
@@ figures vdp-textbook
{
  "diagram": {"kind": "diagram", "model": "vdp-textbook"},
  "run": {
    "kind": "plot", "model": "vdp-textbook", "xlim": [0, 100], "xlabel": "tau",
    "rows": [
      {"ylabel": "x, mu = 0.1", "series": [{"signal": "Mu01/X/y", "label": "Mu01/X/y"}]},
      {"ylabel": "x, mu = 1", "series": [{"signal": "Mu1/X/y", "label": "Mu1/X/y"}]},
      {"ylabel": "x, mu = 5", "series": [{"signal": "Mu5/X/y", "label": "Mu5/X/y"}]},
      {"ylabel": "x, mu = 20", "series": [{"signal": "Mu20/X/y", "label": "Mu20/X/y"}]}
    ]
  },
  "phase": {
    "kind": "plot", "model": "vdp-textbook", "width": 1000, "row_height": 2.9,
    "rows": [
      {"x": "Mu01/X/y", "xlabel": "x", "ylabel": "x', mu = 0.1", "series": [{"signal": "Mu01/Y/y", "label": "mu = 0.1"}]},
      {"x": "Mu1/X/y", "xlabel": "x", "ylabel": "x', mu = 1", "series": [{"signal": "Mu1/Y/y", "label": "mu = 1"}]},
      {"x": "Mu5/X/y", "xlabel": "x", "ylabel": "x', mu = 5", "series": [{"signal": "Mu5/Y/y", "label": "mu = 5"}]},
      {"x": "Mu20/X/y", "xlabel": "x", "ylabel": "x', mu = 20", "series": [{"signal": "Mu20/Y/y", "label": "mu = 20"}]}
    ]
  }
}
@@ page vdp-textbook overview - | Overview
# The textbook Van der Pol equation

$$x'' - \mu\,(1 - x^2)\,x' + x = 0$$

The term $-\mu(1 - x^2)x'$ is a damping that is negative for $|x| < 1$ and positive beyond. Every motion except the rest point $x = 0$ ends on one closed orbit, the limit cycle. The two physical models in this project reduce to this equation: the tunnel-diode oscillator (model `vdp-tunnel-diode`) in its capacitor voltage, and the belt-driven block (model `vdp-belt`) in its velocity.

![Root diagram: four subsystems|700](@fig:diagram)

The four subsystems [Mu01](block:Mu01), [Mu1](block:Mu1), [Mu5](block:Mu5) and [Mu20](block:Mu20) run the equation at $\mu$ = 0.1, 1, 5 and 20, all from $x = 0.5$, $x' = 0$. The run time is $\tau$. Each subsystem holds:

- the **block diagram**: [Mu1/Sq](block:Mu1/Sq) forms $1 - x^2$, [Mu1/Prod](block:Mu1/Prod) multiplies by $x'$, [Mu1/Mu](block:Mu1/Mu) by $\mu$, and [Mu1/Acc](block:Mu1/Acc) subtracts $x$. The integrators [Mu1/Y](block:Mu1/Y) and [Mu1/X](block:Mu1/X) give $x'$ and $x$;
- the same equation as an **equation block**, [Mu1/Eq](block:Mu1/Eq) (`VanDerPol`);
- the cycle meter [Mu1/Meter](block:Mu1/Meter), which reads the period and the amplitude from events.

The phase portraits are XY plots: open **Phase portrait at mu = 1** or **at mu = 5** from **Saved** in the Plots toolbar, or plot [Mu1/Y/y](signal:Mu1/Y/y) and set the panel's **x** to [Mu1/X/y](signal:Mu1/X/y). The phase portraits on the [results page](page:results) are drawn by the docs build from the same run.

Continue with [the theory](page:theory) and [the results](page:results).
@@ page vdp-textbook theory overview | Theory: amplitude and period
# Amplitude and period

## Small mu: averaging

For $\mu \ll 1$ the motion is nearly $x = r\cos(\tau + \varphi)$, with a slowly varying amplitude. Averaging the energy balance over one cycle gives

$$\frac{dr}{d\tau} = \frac{\mu}{2}\,r\left(1 - \frac{r^2}{4}\right),$$

so the amplitude grows (or shrinks) to $r = 2$ at a rate $\mu/2$. Whatever the start, the limit cycle has amplitude 2. Second-order perturbation theory (Lindstedt-Poincaré) gives the period

$$T = 2\pi\left(1 + \frac{\mu^2}{16} - \frac{5\mu^4}{3072} + \dots\right).$$

## Large mu: relaxation oscillations

For $\mu \gg 1$, write the equation in Liénard form, $x' = \mu\,(w - (x^3/3 - x))$. The state creeps along the two outer branches of the cubic $w = x^3/3 - x$ (for $|x| > 1$). At the knees $x = \pm 1$ it jumps to the other branch in a time of order $1/\mu$. The creep from $x = 2$ to $x = 1$ takes $\mu\,(3/2 - \ln 2)$, so the leading period is $(3 - 2\ln 2)\,\mu$. The corrections from the jumps near the knees give (Dorodnitsyn)

$$T \approx (3 - 2\ln 2)\,\mu + 3 a\,\mu^{-1/3}, \qquad a = 2.33811 \ \text{(the first zero of } \mathrm{Ai}(-z)\text{)},$$

so $3a$ = 7.0143. The next terms are of order $\ln\mu/\mu$, so the estimate improves slowly with $\mu$.

| $\mu$ | limit-cycle period (scipy) | $2\pi(1 + \mu^2/16)$ | relaxation estimate | amplitude |
| --- | --- | --- | --- | --- |
| 0.1 | 6.28711127 | 6.287112 (+1.6e-7) | | 2.0001040 |
| 1 | 6.66328686 | 6.675884 (+0.19 %) | 8.628 | 2.0086199 |
| 5 | 11.61223067 | 16.10 | 12.1705 (+4.81 %) | 2.0215081 |
| 20 | 34.68232331 | 163.4 | 34.8582 (+0.51 %) | 2.0077900 |

The reference periods come from `design/design.py`. It solves the equation with scipy (DOP853, or Radau for $\mu \ge 5$, tolerance 1e-13) and finds the limit cycle by shooting on the section $x = 0$, $x' > 0$.
@@ page vdp-textbook results theory | Results
# Results

![x(tau) at mu = 0.1, 1, 5 and 20|900](@fig:run)

At $\mu$ = 0.1 the amplitude takes about 60 time units to grow from 0.5 to 2: its rate is $\mu/2$. At $\mu$ = 5 and 20 the cycle is reached within one period, and the waveform is a square-ish relaxation wave.

![Phase portraits: the near-circle of radius 2 at small mu, the relaxation cycle at large mu|900](@fig:phase)

## Checks (`expected.json`)

For each $\mu$:

| check | tolerance |
| --- | --- |
| block diagram against the equation block, $x$ and $x'$ | 1e-6 (scaled by the peak $x'$) |
| period of the last full cycle, from the zero crossings of $x$ | rtol 1e-6 against the scipy limit cycle |
| the cycle meter's period and amplitude at the end | rtol 1e-7 |
| the sampled peak of $x$ in the second half | 1e-4 |
| $x$ at $\tau$ = 200 against scipy from the same start | 1e-5 |
| $\mu \le 1$: period against $2\pi(1 + \mu^2/16)$, amplitude against 2 | twice the theory's own error |
| $\mu \ge 5$: period against the relaxation estimate | twice its error (4.8 % at 5, 0.5 % at 20) |
