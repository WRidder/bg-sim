# Debugging

The debugger pauses a simulation at breakpoints, lets you step through block code, inspect values, change parameters while paused, and replay the result.

**Try it:** open the **Debug tour** example from the start page. Its Docs tab walks you through finding and fixing a planted integrator-windup bug.

## Start, step and stop

Click **Debug** (`F5`) next to **Run**. While a debug run is active, icon buttons replace the run settings:

| Button | Key | Does |
| --- | --- | --- |
| **Continue** | `F5` | runs to the next breakpoint |
| **Pause** | `F6` | pauses the running simulation |
| **Step statement** | `F10` | runs one statement of discrete code |
| **Step tick** | `F11` | runs to the next clock tick |
| **More step commands** | | **Step event** and **Step solver step** |
| **Stop** | `Shift+F5` | ends the debug run |

`F10` with nothing running starts a debug run paused at its start. `F11` is a debugger key only during a debug run; otherwise it switches the browser to full screen as usual. While paused, type a time in **Run to time** and press `Enter` to run on to that time and pause again.

While paused, the plots end at a *paused* marker, the 3D view shows the paused state, and the status shows where and why the run paused.

## Breakpoints

- **Line breakpoint:** in the [Code tab](page:code-and-docs), click the gutter next to a line of block code, or press `F9`. A breakpoint that cannot be hit is shown as not verified, with the reason in its tooltip. Right-click the marker to set a **Condition** (for example `k == 5`) or a **Hit count**, or to disable or remove it.
- **Signal breakpoint:** right-click a signal (in the Signals tab, a bond or a block) and choose **Break when…**, then pick a comparison and a value.
- **Break on:** in the **Debug** tab under **Breakpoints**, pause on every event, on a solver failure (E901) or when the event limit is reached (W206).

A filled marker is verified, a hollow one is not (yet); a dashed marker is disabled.

## Inspect

The **Debug** tab in the bottom dock has:

- **Variables:** locals of the paused code, held outputs, previous values, the signals of the selected block and watched signals.
- **Watch expressions:** add an expression such as `s"Motor1/i"` or `t` to see its value at every pause.
- **Breakpoints:** all breakpoints, with enable switches and the **Break on** options.
- **Edits:** the live edits of this session.

**Explain signal** (right-click a signal) shows how a signal is computed: its kind, unit and equations. It works without a run.

## Live edits and replay

While paused, the inspector is in **live** mode: a parameter change applies to the paused run from that moment on and is listed under **Edits**. The model itself does not change.

- **Rewind to here:** right-click a plot at an earlier time. The run is replayed up to that time and pauses there, so you can try a change from that point.
- **Replay** (after the run has finished or stopped) runs the model again as a normal run with the edits applied at the same moments.
- **Save parameters to model** writes the parameter edits into the model as one undo step (`Ctrl+Z` undoes it).
