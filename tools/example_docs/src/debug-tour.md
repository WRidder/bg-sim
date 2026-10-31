@@ figures debug-tour
{
  "diagram": {"kind": "diagram", "model": "debug-tour"},
  "scene": {"kind": "scene", "model": "debug-tour", "t": 1.09},
  "run": {
    "kind": "plot", "model": "debug-tour", "xlim": [0, 4],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "Pos/y", "label": "cart Pos/y"}, {"signal": "XRef/y", "label": "reference XRef/y", "style": "--"}],
       "hlines": [{"y": 1.2, "label": "limit switch 1.2 m"}], "vlines": [{"x": 1.0936541918, "label": "trip 1.0937 s"}], "legend": true, "legend_loc": "lower right"},
      {"ylabel": "force [N]", "series": [{"signal": "Ctrl/u", "label": "PID u"}, {"signal": "Ctrl/F", "label": "limited F", "color": "#d95f02"}, {"signal": "Limit/F", "label": "to the drive, Limit/F", "color": "#1b9e77", "style": ":"}],
       "hlines": [{"y": 15, "label": "umax 15 N"}, {"y": -15}], "ylim": [-20, 50], "legend": true},
      {"ylabel": "integrator z [m s]", "series": [{"signal": "Ctrl/z", "label": "Ctrl/z", "color": "#7570b3"}, {"signal": "Limit/tripped", "label": "Limit/tripped", "color": "#e7298a", "style": "--"}], "legend": true, "legend_loc": "upper left"}
    ]
  }
}
@@ page debug-tour overview - | Overview
# Debug tour

A small model with a **planted bug**, made to show off the debugger. A 1 kg cart on a spring and a damper is positioned by a sampled PID controller [Ctrl](block:Ctrl) whose drive force saturates at ±15 N. The reference [XRef](block:XRef) steps from 0 to 1 m at $t = 0.5$ s. Something goes wrong: the cart overshoots, hits the end-of-travel switch [Limit](block:Limit) at 1.2 m, the drive is cut and the cart falls back to 0.

![The model canvas|900](@fig:diagram)

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

![The shipped run: overshoot, trip at 1.0937 s, fall-back|900](@fig:run)

## 3D view

`scenes/debug-tour.sdf` has a rail, a blue cart on the prismatic joint `slide` (bound to [Pos/y](signal:Pos/y)), a green post at the 1 m target and a red post at the 1.2 m switch. At a pause the 3D view follows the inspect time, so it shows the cart where the run stopped.

![3D view at t = 1.09 s, just before the trip|500](@fig:scene)

Start the [walkthrough](page:walkthrough), or read about the [model and checks](page:model).
@@ page debug-tour walkthrough overview | Walkthrough
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
@@ page debug-tour model overview | Model and checks
# Model and checks

## Plant (bond graph)

The modulated effort source [Drive](block:Drive) pushes on the 1-junction [CartJ](block:CartJ), whose flow is the cart speed. On the junction sit the mass [Mass](block:Mass) (`I`, $m = 1$ kg), the damper [Damper](block:Damper) (`R`, $b = 2$ N·s/m) and the spring [Spring](block:Spring) (`C`, compliance 0.1 m/N, so $k = 10$ N/m). [Speed](block:Speed) is a zero-effort flow sensor with a `Translation` port, which gives the bond island its domain and units, and [Pos](block:Pos) integrates the speed into the position:

$$m\,\ddot x = F - b\,\dot x - k\,x .$$

## Controller (`library/CartPID.jl`)

[Ctrl](block:Ctrl) runs every $T_s = 10$ ms:

```julia
25    @discrete Ts = 0.01 begin
26        k += 1                                # tick counter
27        err = x_ref - x                       # position error
28        z += Ts * err                         # integrate the error
29        u = Kp * err + Ki * z - Kd * v        # PID force, not yet limited
30        F = clamp(u, -umax, umax)             # the drive saturates at +-umax
31        if aw > 0.5 && abs(u) > umax
32            z -= Ts * err                     # anti-windup: undo the integration
33        end
34    end
```

| parameter | value | meaning |
| --- | --- | --- |
| `Kp` | 40 | proportional gain, N per m |
| `Ki` | 80 | integral gain, N per m·s |
| `Kd` | 8 | velocity feedback, N per m/s |
| `umax` | 15 | drive force limit, N |
| `aw` | 0 | anti-windup switch: **0 is the bug**, 1 the fix |

`err` is a block-local temporary (it shows under *Locals* at a statement pause); `k`, `z`, `u` and `F` are held between ticks (*Held outputs*).

## Limit switch (`library/LimitSwitch.jl`)

[Limit](block:Limit) is an `@events` block wired into the drive enable, not into the controller software. When $x$ rises past `x_limit` = 1.2 m, the event at line 24 sets the latch to 1 and the force passed to the drive becomes zero:

$$F_\text{drive} = (1 - \text{latch})\,F_\text{cmd} .$$

The latch obeys `ddt(latch) ~ -leak * latch` with `leak = 0`, the same pattern as `stdlib:continuous/Relay`: written as a literal `ddt(latch) ~ 0.0`, the compiler would eliminate it as a constant and the event could not change it.

## Settings

| setting | value |
| --- | --- |
| `t_end` | 4 s |
| output | 4001 points |
| solver | `auto`, reltol 1e-8, abstol 1e-10 |
| `event_limit` | 100 |

## Checks

`expected.json` checks the shipped run (with the bug) through the real Julia worker, `uv run examples/run_checks.py --only debug-tour`:

| check | expected | tolerance |
| --- | --- | --- |
| first upward crossing of 1.1 m by `Pos/y` | 1.0233 s | 1e-3 s |
| first upward crossing of 1.2 m by `Pos/y` (the event) | 1.0936542 s | 1e-5 s |
| final `Limit/tripped` | 1 | 1e-12 |
| largest `Pos/y` | 1.2436 m | relative 2e-3 |
| largest `Ctrl/F` | at most 15 N | |
| diagnostics W201, W205, W206, E900, E901 | absent | |
| scene binding of `slide` to `Pos/y` | valid | |

The debugging flow of the [walkthrough](page:walkthrough) is covered by the real-worker Playwright spec `web/tests/e2e/debug-tour.spec.ts`. With `aw = 1` (the fixed model) the peak is 1.044 m and the switch never trips.

Back to the [overview](page:overview).
