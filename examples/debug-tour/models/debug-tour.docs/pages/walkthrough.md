# Walkthrough: find and fix the windup

Breakpoints and watch expressions belong to the editor, not to the model file (they are saved per model in your browser), so the tour sets them up by hand. Each step names the control to use; the debug buttons are in the top bar next to **Run**, and their tooltips give the shortcuts.

## 1. Pause at the symptom: Break on events

1. Make sure the **Plots** tab has a plot of [Pos/y](signal:Pos/y) (click the link, or double-click `Pos/y` in the **Signals** tab); step 4 needs it.
2. Open the **Debug** tab of the bottom dock. In **Breakpoints**, tick **Break on: Events**.
3. Press **Debug** (F5). The run pauses at $t = 1.0937$ s with the status *Paused at t = 1.0937 s*, and the **Code** tab opens `LimitSwitch` at line 24, the event condition `x > x_limit`.
4. Look around while it is paused:
   - the **Plots** and the Scope window end at the pause, with a vertical *paused* marker in the Plots tab, and the inspect time jumps to the pause;
   - the **3D View** shows the cart at the red post;
   - in **Watch expressions**, type `s"Ctrl/z"` and press **Add**, then add `s"XRef/y" - s"Pos/y"` (the position error). They are evaluated now and again at every later pause.
5. Press **Continue** (F5): the run finishes.

The integrator is at 0.275 m·s when the switch trips, more than twice the 0.125 m·s that holds the cart at 1 m against the spring ($k \cdot 1\,\mathrm{m} / K_i = 10/80$). Where did that come from?

## 2. Look inside the controller: a conditional line breakpoint

1. Open the **Code** tab and choose the source `project:CartPID`.
2. Click the gutter left of line 30, `F = clamp(u, -umax, umax)`. A breakpoint marker appears.
3. Right-click the marker. Set **Condition** to `abs(u) > umax` and press **Apply**. The breakpoint now only pauses on ticks where the PID asks for more than the drive can give.
4. Press **Debug** (F5). The run pauses at $t = 0.5$ s, line 30 is highlighted and the status names `CartPID line 30 (Ctrl)`.
5. Open the **Debug** tab, **Variables**: under *Locals*, `err = 1`; under *Held outputs*, `k = 50`, `z = 0.01` and `u = 40.8`. The PID asks for 40.8 N, the drive gives 15 N.

## 3. Step through the code

1. Press **Step statement** (F10): line 30 runs, `F` becomes 15 and the highlight moves to line 31, the anti-windup `if`.
2. Press **Step statement** again: `aw` is 0, so the `if` body (line 32) is skipped and the debugger stops at the first statement of the next tick, line 26 at $t = 0.51$ s.
3. Press **Step tick** (F11) or **Continue** (F5) a few times: the run pauses on every saturated tick, and `z` (in Variables and in the watch) grows by `Ts * err` each time. Nothing undoes it while the drive is saturated: that is **integrator windup**, and it is what pushes the cart past the switch later.

Try **More step commands → Step solver step** too: it advances one integrator step instead of one statement.

## 4. Go back in time: Rewind to here

1. Click the line 30 marker once more to remove the breakpoint (keep *Break on: Events*).
2. Open the **Plots** tab, move the cursor over the position plot to about $t = 0.45$ s, before the step, right-click and choose **Rewind to here**.
3. A new branch run replays the model up to that time and pauses there, with the status reason *time breakpoint*. The parent run's data stays on disk.

## 5. Fix it live

1. Open the **Diagram** tab and click [Ctrl](block:Ctrl). The inspector shows the *Live* banner: changes apply to the paused run.
2. Set `aw` to `1` and press Enter. **Debug → Edits** lists `Ctrl/aw = 1` with the time of the edit.
3. Press **Continue** (F5). This time there is no event pause: the switch never trips. The cart overshoots only to 1.044 m and settles at 1 m, and `Ctrl/z` levels off at 0.125 m·s.

## 6. Make it permanent

- **Edits → Replay** runs the model again as a normal run with the edit applied at its time. Because the edit was made at a time pause, the replay is bit-identical to the session.
- **Edits → Save parameters to model** writes `aw = 1` into the model document (one undo step, Ctrl+Z).

## Extras

- **Break when…**: in the **Signals** tab, right-click [Pos/y](signal:Pos/y), choose **Break when…**, pick `>` and `1.1`, and press **Add watch breakpoint**. With the bug in place, **Debug** pauses at $t \approx 1.023$ s, as the cart passes 1.1 m and before the trip. The **Breakpoints** section shows the watch and how many of the 16 watch slots are used.
- **Explain signal**: right-click [Spring/p.e](signal:Spring/p.e) and choose **Explain signal**. The spring force is an *observed* signal, `Spring/q / Spring/c`; the popover lists its source equations with links into the code.
- **Run to time**: while paused, type a time into the **Run to time** field and press Enter.
- **Hit count**: right-click a line breakpoint and set **Hit count** to 10 to pause on the tenth saturated tick only.
- **Pause** (F6) interrupts a running debug run, and **Stop** (Shift+F5) ends it.
- **Break on** also offers solver failure (**E901**) and the event limit (**W206**): the run pauses before it ends on those, so the state at the failure can be inspected.

Back to the [overview](page:overview), or on to the [model and checks](page:model).
