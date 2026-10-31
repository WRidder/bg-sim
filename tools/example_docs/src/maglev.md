@@ figures maglev-current-driven
{
  "diagram": {"kind": "diagram", "model": "maglev-current-driven"},
  "scene": {"kind": "scene", "model": "maglev-current-driven", "t": 0.35},
  "run": {
    "kind": "plot", "model": "maglev-current-driven", "xlim": [0, 1.4],
    "rows": [
      {"ylabel": "gap [m]", "series": [{"signal": "Ball/h", "label": "Ball/h"}, {"signal": "Pre/y", "label": "Pre/y (prefiltered setpoint)", "style": "--"}, {"signal": "Ideal/y", "label": "Ideal/y (900/(s^2+42s+900))", "style": ":"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "PID/u", "label": "PID/u (coil current)"}, {"signal": "Trim/y", "label": "Trim/y (feedforward c h)", "style": "--"}], "legend": true},
      {"ylabel": "Kp [A/m]", "series": [{"signal": "KpTab/y", "label": "KpTab/y"}]}
    ]
  },
  "statics": {
    "kind": "plot", "model": "maglev-current-driven", "xlim": [0, 1.4],
    "rows": [
      {"ylabel": "current [A]", "series": [{"signal": "Statics/PID05/u", "label": "0.05 m"}, {"signal": "Statics/PID15/u", "label": "0.15 m"}, {"signal": "Statics/PID25/u", "label": "0.25 m"}],
       "hlines": [{"y": 4.444405292281731}, {"y": 13.333215876845191}, {"y": 22.222026461408653, "label": "sqrt(m g/alpha) p"}], "legend": true}
    ]
  }
}
@@ page maglev-current-driven overview - | Overview
# Maglev: current-driven loop

A steel ball of 20 g hangs below an electromagnet. Gravity pulls it down and the magnet pulls it up with a force that grows as the ball comes closer, so the ball cannot hang still on its own: the controller has to keep adjusting the coil current. This model repeats the scenario of the MathWorks example [LPV Model of Magnetic Levitation Model from Batch Linearization Results](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-batch-linearization.html) and its companion [LPV Model of Magnetic Levitation System](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-equations.html): the same plant, the same operating points and the same step. The PID gains are designed here from scratch, in closed form ([controller design](page:controller)).

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Ball](block:Ball) | the plant $m\ddot h = m g - \alpha i^2/h^2$, with soft stops at 0.01 m (magnet face) and 0.3 m (pedestal) |
| [Ref](block:Ref), [Pre](block:Pre) | the setpoint step 0.15 → 0.1875 m at 0.2 s and the prefilter $10/(s+10)$ |
| [Ideal](block:Ideal) | the reference response $900/(s^2 + 42 s + 900)$ for comparison |
| [Trim](block:Trim) | feedforward of the trim current $c\,h$ with $c = \sqrt{m g/\alpha}$, on the measured gap |
| [KpTab](block:KpTab), [KiTab](block:KiTab), [KdTab](block:KdTab) | the PID gains at 0.05, 0.15 and 0.25 m, interpolated over the measured gap |
| [PID](block:PID) | PID with a filtered derivative ($T_f$ = 1 ms) and scheduled gains |
| [Statics](block:Statics) | three extra loops holding the ball at 0.05, 0.15 and 0.25 m without feedforward: the integrator has to find the trim current itself |

The current is the input: the coil is assumed to be driven by an ideal current source. The bond-graph model (`maglev-bondgraph`) drops that assumption.

## What to try

1. Press **Run** and plot [Ball/h](signal:Ball/h) with [Pre/y](signal:Pre/y): the ball follows the filtered setpoint without overshoot.
2. Plot [PID/u](signal:PID/u): to move the ball down, the controller first cuts the current to about 1.2 A, then catches the ball at 18.4 A.
3. Open the 3D view: the coil glows with the current and the translucent disc marks the setpoint.
4. Set the `final` value of [Ref](block:Ref) to 0.09 m or 0.24 m: the scheduled gains keep the response nearly the same over the whole range.

## 3D view

`scenes/maglev.sdf` is a tabletop rig: a base plate and column, an arm holding an iron-core electromagnet with copper windings, the polished ball, an IR sensor head with a faint beam and a pedestal 0.3 m below the magnet face. The prismatic joint `gap` follows [Ball/h](signal:Ball/h), the setpoint disc follows [Ref/y](signal:Ref/y), and the winding colour follows the current [PID/u](signal:PID/u) (heat colormap, 0 to 30 A). Picture at 0.35 s:

![3D view at t = 0.35 s|500](@fig:scene)

Continue with [the plant and its LPV model](page:plant), [the controller design](page:controller) and [the results](page:results).
@@ page maglev-current-driven plant overview | Plant and LPV model
# Plant and LPV model

## The equation

With $h$ the gap from the magnet face down to the ball centre (positive down) and $i$ the coil current:

$$m\,\ddot h = m g - \alpha\,\frac{i^2}{h^2}, \qquad m = 0.02\ \mathrm{kg},\quad g = 9.81\ \mathrm{m/s^2},\quad \alpha = 2.4832\cdot10^{-5}\ \mathrm{N\,m^2/A^2}.$$

These are the reference's numbers. The force depends on $i^2$: the magnet only pulls, whatever the sign of the current. [Ball](block:Ball) adds two stiff stops (10⁴ N/m, 10 N·s/m) at 0.01 m and 0.3 m; in this model the ball never reaches them ([Ball/F_c](signal:Ball/F_c) stays 0).

## Trim

At rest ($\ddot h = 0$) the magnet carries the weight: $\alpha\bar\imath^2/\bar h^2 = m g$, so

$$\bar\imath = c\,\bar h, \qquad c = \sqrt{\frac{m g}{\alpha}} = 88.888\ \mathrm{A/m}.$$

The trim current is 4.444 A at 0.05 m, 13.333 A at 0.15 m and 22.222 A at 0.25 m.

## Linearisation (the LPV model)

Write $h = p + \delta h$, $i = c p + \delta i$ around the operating gap $p$. The derivatives of the force at the trim point are $\partial/\partial h\,(\alpha i^2/h^2) = -2 m g/p$ and $\partial/\partial i\,(\alpha i^2/h^2) = 2 m g/(c p) = 2 m \sqrt{g\alpha/m}/p$. So

$$\frac{d}{dt}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix} = \underbrace{\begin{bmatrix}0 & 1\\ 2g/p & 0\end{bmatrix}}_{A(p)}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix} + \underbrace{\begin{bmatrix}0\\ -2\sqrt{g\alpha/m}/p\end{bmatrix}}_{B(p)}\delta i, \qquad y = \begin{bmatrix}1 & 0\end{bmatrix}\begin{bmatrix}\delta h\\ \delta v\end{bmatrix}.$$

This is the reference's LPV model, with the gap $p$ as the scheduling parameter. Its transfer function is

$$G_p(s) = \frac{\delta h}{\delta i} = \frac{-b_0}{s^2 - a_0}, \qquad a_0 = \frac{2g}{p},\quad b_0 = \frac{2\sqrt{g\alpha/m}}{p} = \frac{0.2207}{p}.$$

| $p$ [m] | $a_0$ [1/s²] | $b_0$ [m/(A s²)] | unstable pole $\sqrt{a_0}$ [1/s] |
| --- | --- | --- | --- |
| 0.05 | 392.4 | 4.4145 | 19.81 |
| 0.15 | 130.8 | 1.4715 | 11.44 |
| 0.25 | 78.48 | 0.8829 | 8.86 |

The pole at $+\sqrt{2g/p}$ is the instability: a ball slightly too close is pulled harder and comes closer still. The open-loop model (`maglev-open-loop-and-linear`) measures it.

## The trim feedforward cancels the negative stiffness

The controller adds $c\,h_{measured}$ to the PID output. Linearised, $\delta i = c\,\delta h + u_{PID}$, and $b_0 c = 2g/p = a_0$, so the $a_0\,\delta h$ term cancels exactly: the PID sees the double integrator

$$\frac{\delta h}{u_{PID}} = \frac{-b_0}{s^2}.$$

The sign is negative (more current lifts the ball, so the gap shrinks); [PID](block:PID) therefore works on $e = h - r$.
@@ page maglev-current-driven controller plant | Controller design
# Controller design

## Structure

[PID](block:PID) (the project block `ScheduledPID`) computes

$$u = f_{ff} + K_p e + K_i\!\int e\,dt + K_d\,\frac{s}{T_f s + 1}\,e, \qquad e = h - r,\quad T_f = 1\ \mathrm{ms},$$

with $f_{ff}$ = [Trim/y](signal:Trim/y). The reference uses a crossover of 50 rad/s and $T_f$ = 1 ms; we keep both and choose a phase margin of 60°.

## Gains in closed form

Write the PID in series form with a double real zero:

$$C(s) = K\,\frac{(s + z)^2}{s\,(T_f s + 1)}.$$

The design plant is the frozen linearisation $b_0/(s^2 - a_0)$ (without the feedforward). Its phase is −180° at every frequency, so the phase margin is the phase of $C$ at the crossover $\omega_c$:

$$\mathrm{PM} = 2\arctan\frac{\omega_c}{z} - 90^\circ - \arctan(\omega_c T_f) \;\Rightarrow\; z = \frac{\omega_c}{\tan\theta}, \quad \theta = \frac{\mathrm{PM} + 90^\circ + \arctan(\omega_c T_f)}{2}.$$

This gives $z$ = 12.07 rad/s, the same for every $p$. The magnitude condition $|C(j\omega_c)|\,b_0/(\omega_c^2 + a_0) = 1$ gives

$$K = \frac{\omega_c^2 + a_0}{b_0}\cdot\frac{\omega_c\sqrt{1 + (\omega_c T_f)^2}}{\omega_c^2 + z^2}.$$

The parallel gains follow by matching numerators, $K_i = K z^2$, $K_p = 2 K z - K_i T_f$, $K_d = K - K_p T_f$:

| $p$ [m] | $K_p$ [A/m] | $K_i$ [A/(m s)] | $K_d$ [A s/m] | crossover / PM, design plant | crossover / PM, with feedforward |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 297.42 | 1805.46 | 12.101 | 50.0 rad/s / 60.0° | 57.1 rad/s / 62.9° |
| 0.15 | 811.57 | 4926.51 | 33.019 | 50.0 rad/s / 60.0° | 52.4 rad/s / 61.0° |
| 0.25 | 1325.71 | 8047.55 | 53.937 | 50.0 rad/s / 60.0° | 51.4 rad/s / 60.6° |

`design/design.py` computes these numbers and checks them on a frequency grid. With the feedforward the plant is $b_0/s^2$, so the loop crosses a little higher and keeps slightly more phase. The closed-loop poles at 0.15 m are −948.9, −21.3 ± 21.0j and −8.5 (1/s).

## Scheduling: tables, not formulas

$K$ is affine in $p$: $(\omega_c^2 + 2g/p)/b_0 = (\omega_c^2 p + 2g)/(2\sqrt{g\alpha/m})$, and $z$ does not depend on $p$. So $K_p$, $K_i$ and $K_d$ are straight lines in $p$, and linear interpolation between the three design points is exact (the midpoint check in `design.json` agrees to 2·10⁻¹⁶). The model uses three `Lookup1D` blocks ([KpTab](block:KpTab), [KiTab](block:KiTab), [KdTab](block:KdTab)) on the measured gap, as the reference does with its gain tables: the design points stay visible, and a design that is not affine in $p$ fits the same blocks. Outside 0.05 … 0.25 m the tables hold the end values.

## Prefilter and ideal response

[Pre](block:Pre) is the reference's optional prefilter $10/(s + 10)$ ($\tau$ = 0.1 s). It removes the overshoot that the two PID zeros would cause on a raw step. [Ideal](block:Ideal) is the reference's target response $900/(s^2 + 42 s + 900)$ (30 rad/s, damping 0.7) on the same prefiltered setpoint.
@@ page maglev-current-driven results controller | Results
# Results

![Gap, current and scheduled gain|900](@fig:run)

| quantity | bgsim | scipy design (`design.json`) |
| --- | --- | --- |
| rise time 10–90 % | 0.1671 s | 0.1671 s |
| overshoot | 0 % | 0 % |
| settling time (2 % band), from the step | 0.4085 s | 0.4086 s |
| gap at 1.4 s | 0.187498994108 m | 0.187498994108 m |
| current, min / max | 1.1846 / 18.4099 A | 1.1824 / 18.4099 A |
| contact force [Ball/F_c](signal:Ball/F_c) | 0 (always levitated) | – |

The scipy simulation (`design/design.py`) integrates the same closed loop independently; the gap at 1.4 s agrees to 2·10⁻¹⁴ m. [Ball/h](signal:Ball/h) follows [Pre/y](signal:Pre/y) more slowly than [Ideal/y](signal:Ideal/y) at first (the loop crosses at about 50 rad/s, but the slow PID zero at 12 rad/s leaves a tail), then settles within 0.41 s.

## Statics

The [Statics](block:Statics) subsystem holds three balls at 0.05, 0.15 and 0.25 m with the scheduled PID but **no** feedforward; the integrators start at 98 % of the trim value. At 1.4 s the currents are

| gap | [Statics/PID05/u](signal:Statics/PID05/u), … | $c\,p$ | relative difference |
| --- | --- | --- | --- |
| 0.05 m | 4.44440527 A | 4.44440529 A | 5·10⁻⁹ |
| 0.15 m | 13.33321588 A | 13.33321588 A | 9·10⁻¹² |
| 0.25 m | 22.22202644 A | 22.22202646 A | 8·10⁻¹⁰ |

![The integrators find the trim currents|900](@fig:statics)

The checks in `expected.json` require 10⁻⁶.
@@ figures maglev-open-loop-and-linear
{
  "diagram": {"kind": "diagram", "model": "maglev-open-loop-and-linear"},
  "scene": {"kind": "scene", "model": "maglev-open-loop-and-linear", "t": 1.0},
  "open": {
    "kind": "plot", "model": "maglev-open-loop-and-linear", "xlim": [0, 1.0],
    "rows": [
      {"ylabel": "gap [m]", "series": [{"signal": "Ball05/h", "label": "Ball05/h"}, {"signal": "Ball15/h", "label": "Ball15/h"}, {"signal": "Ball25/h", "label": "Ball25/h"}], "legend": true},
      {"ylabel": "v/(h - p) [1/s]", "ylim": [0, 22], "series": [{"signal": "Grow05/lambda", "label": "0.05 m"}, {"signal": "Grow15/lambda", "label": "0.15 m"}, {"signal": "Grow25/lambda", "label": "0.25 m"}],
       "hlines": [{"y": 19.809088823063014}, {"y": 11.436782764396638}, {"y": 8.858893836140041, "label": "sqrt(2 g/p)"}], "legend": true}
    ]
  },
  "steps": {
    "kind": "plot", "model": "maglev-open-loop-and-linear", "xlim": [0, 1.0],
    "rows": [
      {"ylabel": "small step [m]", "series": [{"signal": "BallS/h", "label": "nonlinear BallS/h"}, {"signal": "LinS/h", "label": "frozen linear LinS/h", "style": "--"}], "legend": true},
      {"ylabel": "large step [m]", "series": [{"signal": "BallL/h", "label": "nonlinear BallL/h"}, {"signal": "LinL/h", "label": "frozen linear LinL/h", "style": "--"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "PIDL/u", "label": "PIDL/u"}, {"signal": "PIDLinL/u", "label": "PIDLinL/u", "style": "--"}], "hlines": [{"y": 0.0}], "legend": true}
    ]
  }
}
@@ page maglev-open-loop-and-linear overview - | Overview
# Maglev: open loop and the frozen linear model

Two questions about the LPV model (derived on the *Plant and LPV model* page of `maglev-current-driven`): how fast does the uncontrolled ball fall or jump, and how far can a linearisation frozen at one gap be trusted?

![The model canvas|900](@fig:diagram)

**Open loop (top row).** Three balls, at 0.05, 0.15 and 0.25 m, each get exactly the trim current of their gap ([I05](block:I05), [I15](block:I15), [I25](block:I25) = $c\,p$) and start at rest 10 nm too low. The deviation then grows as $\delta h_0\cosh(\sqrt{a_0}\,t)$, and [Grow05](block:Grow05), [Grow15](block:Grow15), [Grow25](block:Grow25) compute the growth rate $\lambda = v/(h - p)$, which tends to the unstable pole $\sqrt{2g/p}$.

**Closed loop (middle and bottom).** One fixed PID (the 0.15 m gains from the controller design of `maglev-current-driven`, in the constant blocks [Kp](block:Kp), [Ki](block:Ki), [Kd](block:Kd)) with the trim feedforward closes the loop twice per row: around the nonlinear ball ([BallS](block:BallS), [BallL](block:BallL)) and around the LPV model frozen at 0.15 m ([LinS](block:LinS), [LinL](block:LinL), the project block `LinearBall`: $A(0.15)$, $B(0.15)$, absolute current in, absolute gap out). The small row steps from 0.15 to 0.155 m, the large row to 0.21 m. [DiffS](block:DiffS) and [DiffL](block:DiffL) subtract the two gaps.

## 3D view

`scenes/maglev-open-loop.sdf` shows the three open-loop rigs side by side, the dark discs marking their trim gaps. At 1.0 s the 0.05 m ball (the fastest pole) has almost reached the pedestal, the 0.15 m ball has just started to fall (0.5 mm) and the 0.25 m ball has not visibly moved:

![The three released balls at t = 1.0 s|700](@fig:scene)

Continue with [the results](page:results).
@@ page maglev-open-loop-and-linear results overview | Results
# Results

## The unstable pole

![Released balls and their growth rate|900](@fig:open)

The growth rate is read at $t = 7/\sqrt{a_0}$, where $\tanh = 1 - 1.7\cdot10^{-6}$ and the deviation is still only 5.5 µm:

| $p$ | $t$ | [Grow05/lambda](signal:Grow05/lambda) … at $t$ | scipy, same equation | $\sqrt{2g/p}$ |
| --- | --- | --- | --- | --- |
| 0.05 m | 0.353 s | 19.807977 1/s | 19.807977 1/s | 19.809089 1/s |
| 0.15 m | 0.612 s | 11.436555 1/s | 11.436555 1/s | 11.436783 1/s |
| 0.25 m | 0.790 s | 8.858782 1/s | 8.858782 1/s | 8.858894 1/s |

bgsim and scipy agree to 10⁻¹¹ (relative). Both stay within 6·10⁻⁵ of the LPV pole; the remainder is the nonlinearity (the force is $1/h^2$, not linear in $h$), which grows as the ball leaves the trim point. After the growth phase the balls hit a stop: the 0.05 m ball falls onto the pedestal (0.3 m), the 0.25 m ball has not yet reached it at 1.5 s.

## Frozen linear vs nonlinear

![Small and large steps, nonlinear and linear|900](@fig:steps)

| | small step (+5 mm) | large step (+60 mm) |
| --- | --- | --- |
| max \|nonlinear − linear\| | 2.45·10⁻⁵ m = 0.49 % of the step | 1.057·10⁻² m = 17.6 % of the step |
| scipy | 0.49 % | 17.6 % |
| current, nonlinear / linear | 11.77 … 13.95 A / 11.78 … 13.94 A | −6.95 … 23.03 A / −5.36 … 20.65 A |

For a small step the frozen model is as good as the nonlinear one. For the large step two things break the approximation: the gain $b_0$ is 29 % smaller at 0.21 m than at 0.15 m, and the controller asks for a **negative** current. The linear model treats the negative current as a strong push downward. The real magnet cannot push: it pulls with $\alpha i^2/h^2$ whatever the sign, so at best the ball falls freely. The nonlinear ball therefore lags behind the linear one by up to 10.6 mm at 0.26 s, and then overshoots it by up to 5.2 mm while the current is high. That is the reason for scheduling the gains and for the trim feedforward on the measured gap.
@@ figures maglev-bondgraph
{
  "diagram": {"kind": "diagram", "model": "maglev-bondgraph"},
  "scene": {"kind": "scene", "model": "maglev-bondgraph", "t": 0.3},
  "run": {
    "kind": "plot", "model": "maglev-bondgraph", "xlim": [0, 1.4],
    "rows": [
      {"ylabel": "gap [m]", "series": [{"signal": "BallPos/y", "label": "BallPos/y"}, {"signal": "Pre/y", "label": "Pre/y", "style": "--"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "EM/i", "label": "EM/i"}, {"signal": "PID/u", "label": "PID/u (setpoint)", "style": "--"}], "legend": true},
      {"ylabel": "voltage [V]", "ylim": [-65, 65], "series": [{"signal": "Sat/y", "label": "Sat/y"}], "hlines": [{"y": 60.0}, {"y": -60.0, "label": "rail"}], "legend": true}
    ]
  },
  "energy": {
    "kind": "plot", "model": "maglev-bondgraph", "xlim": [0, 1.4],
    "rows": [
      {"ylabel": "energy [J]", "series": [{"signal": "EM/W", "label": "EM/W (stored)"}, {"signal": "Eel/y", "label": "Eel/y = int v i dt"}, {"signal": "Emech/y", "label": "Emech/y = int F dh/dt dt"}], "legend": true},
      {"ylabel": "power [W]", "series": [{"signal": "Pel/y", "label": "Pel/y"}, {"signal": "Pmech/y", "label": "Pmech/y"}], "legend": true}
    ]
  },
  "noise": {
    "kind": "plot", "model": "maglev-bondgraph", "xlim": [0, 0.2],
    "rows": [
      {"ylabel": "gap [m]", "series": [{"signal": "IR/Back/y", "label": "IR/Back/y (measured)"}, {"signal": "BallPos/y", "label": "BallPos/y (true)"}], "legend": true},
      {"ylabel": "voltage [V]", "series": [{"signal": "Sat/y", "label": "Sat/y"}]}
    ]
  }
}
@@ page maglev-bondgraph overview - | Overview
# Maglev as a bond graph

The current-driven model (`maglev-current-driven`) assumes an ideal current source. Here the coil is a real circuit: a voltage amplifier with a ±60 V rail, the coil resistance, and an inductance that changes with the gap. The magnet itself is the stdlib block `converters/Electromagnet`, a two-port field that stores magnetic energy and is the only link between the circuit and the ball. The position comes from an IR sensor with noise and a 16-bit ADC at 1 kHz, and a cascade controller closes the loop.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Amp](block:Amp), [Sat](block:Sat) | modulated effort source: the amplifier voltage, clipped at ±60 V |
| [Jc](block:Jc), [Rc](block:Rc), [Imeas](block:Imeas) | electrical 1-junction (one current), coil resistance 2 Ω, flow detector for the current |
| [Jv](block:Jv), [Vcoil](block:Vcoil) | 0-junction at the field's coil port and its effort detector (the field voltage) |
| [EM](block:EM) | the electromagnet: an IC-field between the coil and the gap ([physics](page:physics)) |
| [Jb](block:Jb), [Ball](block:Ball), [Grav](block:Grav) | mechanical 1-junction (ball velocity, down positive), the 20 g mass, gravity |
| [Jf](block:Jf), [Fmag](block:Fmag), [Vball](block:Vball) | 0-junction at the field's gap port, force and velocity detectors |
| [BallPos](block:BallPos), [IR](block:IR) | gap, and the IR sensor subsystem (gain, noise, ADC) |
| [Pel](block:Pel), [Pmech](block:Pmech), [Eel](block:Eel), [Emech](block:Emech) | port powers of the field and their integrals |
| [Ref](block:Ref), [Pre](block:Pre), [Trim](block:Trim), [PID](block:PID), [Ipi](block:Ipi) | outer scheduled PID → current setpoint, inner PI → voltage ([controller](page:control)) |

## What to try

1. Open the **Dashboard** tab and move the setpoint slider: the model runs again, and the gauges show the gap and the coil current.
2. Plot [EM/W](signal:EM/W), [Eel/y](signal:Eel/y) and [Emech/y](signal:Emech/y): the stored energy is exactly what flowed in through the two ports.
3. Plot [Sat/y](signal:Sat/y): the noise keeps the amplifier busy (about 2 V rms), and the step drives it into the +60 V rail.
4. Set the `std` of `IR/Noise` to 0: the loop becomes quiet and matches the scipy design.

## 3D view

The same tabletop rig as the current-driven model. The gap follows [BallPos/y](signal:BallPos/y), the setpoint disc [Ref/y](signal:Ref/y) and the winding colour the field current [EM/i](signal:EM/i). Picture at 0.3 s:

![3D view at t = 0.3 s|500](@fig:scene)
@@ page maglev-bondgraph physics overview | Physics: the electromagnet as an IC-field
# The electromagnet as an IC-field

## One energy, two ports

A magnetic circuit with a moving armature stores energy in its field. With flux linkage $\lambda$ and gap $h$ as the energy variables,

$$W(\lambda, h) = \frac{\lambda^2}{2 L(h)}, \qquad L(h) = L_\infty + \frac{2\alpha}{h + h_0}.$$

The port laws are the partial derivatives of $W$; this is what makes a two-port field:

$$i = \frac{\partial W}{\partial\lambda} = \frac{\lambda}{L(h)}, \qquad F = \frac{\partial W}{\partial h}\Big|_\lambda = -\frac{\lambda^2 L'(h)}{2 L^2} = -\tfrac12 i^2 L'(h) = \frac{\alpha i^2}{(h + h_0)^2}.$$

The electrical port is integral in $\lambda$ ($\dot\lambda = v$, an I-type port: voltage in, current out), the mechanical port integral in $h$ ($\dot h$ = velocity, a C-type port: velocity in, force out), hence **IC-field**. The power into the field is then

$$v\,i + F\,\dot h = \frac{\partial W}{\partial\lambda}\dot\lambda + \frac{\partial W}{\partial h}\dot h = \frac{dW}{dt},$$

exactly: the field conserves energy, and the coil resistance is a separate R.

## Why the co-energy gives the force

We know the current, not the flux linkage, so it is natural to work with the **co-energy**, the Legendre transform of $W$ in $\lambda$:

$$W'(i, h) = \lambda i - W = \tfrac12 L(h)\, i^2.$$

From $dW' = \lambda\,di - F\,dh$ the force is $F = -\partial W'/\partial h|_i = -\tfrac12 i^2 L'(h)$: the same value as from $W$ at constant flux. Moving the armature toward the magnet ($dh < 0$) at constant current raises the co-energy, so the force pulls the armature in. With $L'(h) = -2\alpha/(h + h_0)^2$ the force is $\alpha i^2/(h + h_0)^2$, which for $h_0 = 0$ is the reference's inverse-square law. This is why the stdlib block takes the reference's $\alpha$ directly, and why $L(h)$ has the form $L_\infty + 2\alpha/h$: it is the only inductance (up to the constant $L_\infty$) whose co-energy gives that force. $L_\infty$ (0.03 H here, our choice) is the inductance with the ball far away; the reference has no coil model, so it is an assumption.

## The coil equation

Differentiating $\lambda = L(h)\,i$:

$$v = L(h)\,\frac{di}{dt} + L'(h)\,\dot h\, i = L(h)\,\frac{di}{dt} - \frac{2\alpha\, i\,\dot h}{(h + h_0)^2}.$$

The second term is the back-EMF of the moving ball. [EM](block:EM) uses $i$ and $h$ as its states and writes this equation for $di/dt$. At 0.15 m, $L$ = 30.33 mH.

## The bond graph

- Electrical 1-junction [Jc](block:Jc) (common current): $v_{Amp} = R\,i + v_{field}$, with [Rc](block:Rc) = 2 Ω. [Imeas](block:Imeas) is a flow detector (zero effort) that reads $i$.
- [Jv](block:Jv) is a 0-junction in front of the coil port: [Vcoil](block:Vcoil) (an effort detector, zero flow) reads the field voltage $v$ without disturbing it.
- Mechanical 1-junction [Jb](block:Jb) (common ball velocity $\dot h$, down positive): $m\ddot h = m g - F$, with [Grav](block:Grav) = $m g$ and [Ball](block:Ball) = $m$.
- [Jf](block:Jf) is the 0-junction at the gap port: [Fmag](block:Fmag) reads $F$; [Vball](block:Vball) on Jb reads $\dot h$.
- The stator side `a` of [EM](block:EM) is wired to [Frame](block:Frame) (fixed), the coil return `n` to [Gnd](block:Gnd).

The causality is integral everywhere: Amp and Grav impose effort, the field gives the current at the coil and the force at the gap, the mass gives the velocity. No algebraic loop or derivative causality is reported.

## Energy check

[Pel](block:Pel) = $v\,i$ and [Pmech](block:Pmech) = $F\,\dot h$ are the two port powers; [Eel](block:Eel) and [Emech](block:Emech) integrate them. The field must satisfy

$$W(t) - \int_0^t v\,i\,d\tau - \int_0^t F\,\dot h\,d\tau = W(0) = \tfrac12 L(0.15)\,(13.333\ \mathrm{A})^2 = 2.69605\ \mathrm{J}.$$

The run keeps this within 6.2·10⁻⁹ J over the whole step (2.3·10⁻⁹ of $W(0)$). The golden test `test/golden/converters/test_Electromagnet.jl` checks the same balance with a free armature to 10⁻⁷ of the throughput.
@@ page maglev-bondgraph control physics | Cascade controller and sensor
# Cascade controller and IR sensor

## Inner current loop

[Ipi](block:Ipi) (project block `CurrentPI`) turns the current setpoint into the amplifier voltage. The coil seen from the amplifier is $R + s L_0$ with $L_0 = L(0.15)$ = 30.33 mH. A PI whose zero cancels the coil pole,

$$C_i(s) = K_{p,i}\,\frac{1 + s T_i}{s T_i}, \qquad T_i = \frac{L_0}{R} = 15.2\ \mathrm{ms}, \quad K_{p,i} = L_0\,\omega_i = 30.33\ \mathrm{V/A},$$

makes the current loop a first-order lag $1/(s/\omega_i + 1)$ with $\omega_i$ = 1000 rad/s, twenty times the outer crossover. The PI integrator is preloaded with the trim voltage (26.67 V) and has back-calculation anti-windup against the ±60 V rail of [Sat](block:Sat). The inductance changes with the gap (30.33 mH at 0.15 m, 30.26 mH at 0.1875 m, 30.20 … 30.99 mH over 0.05 … 0.25 m), which moves $\omega_i$ by at most 2.6 %.

## IR sensor

The [IR](block:IR) subsystem models the measurement chain:

| block | what it does |
| --- | --- |
| `IR/Zero`, `IR/Gain` | the sensor is zeroed at 0.15 m and gives 30 V/m |
| `IR/Noise`, `IR/Add` | white noise, 0.3 mV rms (10 µm of gap), a new sample every 1 ms, seed 7 |
| `IR/ADC` | 16-bit ADC over −5 … +5 V at 1 kHz (one step = 5.1 µm of gap), held between samples |
| `IR/Scale`, `IR/Back` | back to metres |

## Outer position loop

The outer loop is the current-driven design with two changes forced by the sensor:

1. **Derivative filter $T_f$ = 5 ms** instead of 1 ms. With 1 ms the derivative gain at high frequency, $K_d/T_f \approx 33\,000$ A/m, turns the 10 µm noise and the 5 µm ADC steps into about 0.3 A of current noise, and the inner loop turns that into a voltage that jumps from rail to rail. With 5 ms the amplifier noise drops to about 2 V rms.
2. **The extra phase lag in the budget.** The sample-and-hold delays the measurement by half a sample, $\omega_c T/2$ = 1.4° at 50 rad/s, and the current loop adds $\arctan(\omega_c/\omega_i)$ = 2.9°. Both, plus the slower filter, go into the same closed-form design as in the current-driven model (`maglev-current-driven`, *Controller design*): $2\arctan(\omega_c/z) = \mathrm{PM} + 90^\circ + \arctan(\omega_c T_f) + 4.3^\circ$.

| $p$ [m] | $K_p$ [A/m] | $K_i$ [A/(m s)] | $K_d$ [A s/m] | crossover / PM of the sampled loop |
| --- | --- | --- | --- | --- |
| 0.05 | 135.02 | 349.39 | 12.709 | 57.2 rad/s / 58.9° |
| 0.15 | 368.43 | 953.36 | 34.679 | 52.4 rad/s / 59.7° |
| 0.25 | 601.83 | 1557.34 | 56.650 | 51.4 rad/s / 59.8° |

The double zero moves down to $z$ = 5.1 rad/s, so the integral action is slower: the last 20 µm of the step settle with a time constant of a few tenths of a second. The trim feedforward [Trim](block:Trim) and the gain tables [KpTab](block:KpTab), [KiTab](block:KiTab), [KdTab](block:KdTab) use the measured gap `IR/Back/y`.
@@ page maglev-bondgraph results control | Results
# Results

![Gap, coil current and amplifier voltage|900](@fig:run)

| quantity | bgsim, noisy sensor | bgsim, ideal sensor | scipy design (continuous, no noise) |
| --- | --- | --- | --- |
| rise time 10–90 % | 0.1641 s | 0.1642 s | 0.1650 s |
| overshoot | 0.12 % | 0.13 % | 0.14 % |
| settling time (2 % band) | 0.286 s | 0.286 s | 0.287 s |
| gap error at 1.4 s | 2.16·10⁻⁵ m | 2.24·10⁻⁵ m | 2.20·10⁻⁵ m |
| coil current, min | 2.43 A | 2.43 A | 2.62 A |
| amplifier voltage | −34 … +60 V (rail) | −35 … +60 V (rail) | −35 … +35 V |

The ideal-sensor run is the same model with `IR/Noise/std` = 0 and a 52-bit ADC (run-parameter overrides, as the dashboard uses them); it is still sampled at 1 kHz. The sample-and-hold explains the small differences to the continuous scipy design. It also explains the voltage. While the ball moves at about 0.2 m/s, the held measurement climbs in 0.2 mm stairs, and every stair kicks the derivative term by $K_d\,\Delta h/T_f \approx$ 1.4 A. The 1000 rad/s current loop turns these kicks into voltage spikes, which touch the +60 V rail for 41 ms in total between 0.23 and 0.34 s. The continuous design stays within ±35 V. The anti-windup of [Ipi](block:Ipi) keeps the rail from upsetting the current loop.

## Energy

![Stored energy and the integrated port powers|900](@fig:energy)

$W - E_{el} - E_{mech}$ stays at $W(0)$ = 2.69605 J to 6.2·10⁻⁹ J. Most of the electrical energy that flows in is stored (the field energy rises with $i^2$ as the ball moves down); the mechanical port takes only 7 mJ.

## Statics

Run for 6 s with the ideal sensor, the loop comes fully to rest at 0.1875 m with

| quantity | value | expected |
| --- | --- | --- |
| [EM/i](signal:EM/i) / [EM/h](signal:EM/h) | 88.8881058457 A/m | $c = \sqrt{m g/\alpha}$ = 88.8881058456 A/m |
| [EM/F](signal:EM/F) | 0.1962 N | $m g$ = 0.1962 N |

the same statics as the current-driven model.

## Noise

![Measured and true gap, amplifier voltage, before the step|900](@fig:noise)

Before the step the true gap moves by 2.9 µm rms, the current by 44 mA rms and the amplifier voltage by 2 V rms. The noise sequence is seeded, so every run repeats exactly.

## Checks

`expected.json` checks this model twice (noisy and ideal sensor): the step bounds, the energy invariant (10⁻⁷ of $W(0)$), $W(0)$, the ±60 V rail, a positive current, $EM/h$ = $BallPos/y$ and $EM/F$ = $Fmag/y$, the statics above to 10⁻⁶, no W201/W202/E106/W206, and the cascade against the current-driven model (within 3 mm over the whole run).
