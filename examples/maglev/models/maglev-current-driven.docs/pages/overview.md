# Maglev: current-driven loop

A steel ball of 20 g hangs below an electromagnet. Gravity pulls it down and the magnet pulls it up with a force that grows as the ball comes closer, so the ball cannot hang still on its own: the controller has to keep adjusting the coil current. This model repeats the scenario of the MathWorks example [LPV Model of Magnetic Levitation Model from Batch Linearization Results](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-batch-linearization.html) and its companion [LPV Model of Magnetic Levitation System](https://nl.mathworks.com/help/control/ug/maglev-lpv-model-from-equations.html): the same plant, the same operating points and the same step. The PID gains are designed here from scratch, in closed form ([controller design](page:controller)).

![The model canvas|900](assets/592b4faa4e8c.png)

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

![3D view at t = 0.35 s|500](assets/06cc59ad3093.png)

Continue with [the plant and its LPV model](page:plant), [the controller design](page:controller) and [the results](page:results).
