# Debug tour

A small model with a **planted bug**, made to show off the debugger. A 1 kg cart on a spring and a damper is positioned by a sampled PID controller [Ctrl](block:Ctrl) whose drive force saturates at ±15 N. The reference [XRef](block:XRef) steps from 0 to 1 m at $t = 0.5$ s. Something goes wrong: the cart overshoots, hits the end-of-travel switch [Limit](block:Limit) at 1.2 m, the drive is cut and the cart falls back to 0.

![The model canvas|900](assets/cf303a2e703a.png)

The [walkthrough](page:walkthrough) finds the cause with the debugger and fixes it while the run is paused. A blue sticky note on the canvas repeats the steps in short. On the way it uses:

- **Break on events**: pause at the instant an `@events` condition fires (the switch);
- **watch expressions** that are re-evaluated at every pause;
- a **line breakpoint** with a **condition** in the `@discrete` controller code;
- **Step statement**, **Step tick** and **Continue**, with the **Variables** section showing locals and held outputs;
- **Rewind to here**: a branch run that replays the model to an earlier time and pauses;
- a **live parameter edit** in the inspector, listed under **Edits**, then **Replay** and **Save parameters to model**;
- and, as extras, **Break when…** on a signal, **Explain signal**, **Run to time**, **Step event** and hit counts.

## The symptom

Press **Run** (Ctrl+Enter). The oscilloscope probe **Scope**, part of the model, has a plot window on the canvas: the cart position [Pos/y](signal:Pos/y) against the reference [XRef/y](signal:XRef/y), and the force command [Ctrl/F](signal:Ctrl/F) against the force that reaches the drive, [Limit/F](signal:Limit/F). Click [Ctrl/u](signal:Ctrl/u) (the PID force before the ±15 N limit), [Ctrl/z](signal:Ctrl/z) (the integrator) and [Limit/tripped](signal:Limit/tripped) to add them to the **Plots** tab. The switch trips at $t = 1.0937$ s and the cart drifts back to 0 while the controller keeps asking for full force.

![The shipped run: overshoot, trip at 1.0937 s, fall-back|900](assets/5fd0af2246d8.png)

## 3D view

`scenes/debug-tour.sdf` has a rail, a blue cart on the prismatic joint `slide` (bound to [Pos/y](signal:Pos/y)), a green post at the 1 m target and a red post at the 1.2 m switch. At a pause the 3D view follows the inspect time, so it shows the cart where the run stopped.

![3D view at t = 1.09 s, just before the trip|500](assets/8893e8a22755.png)

Start the [walkthrough](page:walkthrough), or read about the [model and checks](page:model).
