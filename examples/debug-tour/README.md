# debug-tour — a guided tour of the debugger: find and fix an integrator windup

A small model with a planted bug, made to show off the debugger. A 1 kg cart on a
spring and a damper (a bond-graph plant) is positioned by a sampled PID controller
whose drive force saturates at ±15 N. The reference steps from 0 to 1 m at 0.5 s.
Anti-windup is switched off (`Ctrl/aw = 0`), so the integrator keeps integrating
while the drive is saturated, the cart overshoots and, at t = 1.0937 s, trips an
end-of-travel limit switch at 1.2 m that cuts the drive. The walkthrough finds the
cause with breakpoints and stepping and fixes it live.

The model's **Docs** tab (`models/debug-tour.docs/`) has the full step-by-step
walkthrough with pictures; this README is the short version.

## The model

| block | what it is |
| --- | --- |
| `XRef` | `stdlib:sources/Step`, 0 → 1 m at 0.5 s |
| `Ctrl` | `project:CartPID` (`library/CartPID.jl`), the **@discrete** controller, `Ts = 10 ms`: `Kp = 40`, `Ki = 80`, `Kd = 8`, `umax = 15 N`, `aw = 0` (the bug) |
| `Limit` | `project:LimitSwitch` (`library/LimitSwitch.jl`), an **@events** latch at `x_limit = 1.2 m`, wired into the drive enable |
| `Drive`, `CartJ`, `Mass`, `Damper`, `Spring` | the bond-graph plant: `MSe` on a 1-junction with `I` (m = 1 kg), `R` (b = 2 N·s/m) and `C` (k = 10 N/m) |
| `Speed`, `Pos` | a zero-effort flow sensor (`library/FlowSensor.jl`) and an integrator for the position |

The controller, with the line numbers the walkthrough uses:

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

An oscilloscope probe, `Scope`, is part of the model: its window on the canvas plots
the cart position against the reference and the force command `Ctrl/F` against the
force that reaches the drive `Limit/F`, and it follows every pause. The 3D view shows
the cart on a rail with a green post at the 1 m target and a red one at the 1.2 m
switch.

## The tour in short

Breakpoints and watch expressions are editor state (saved per model in the browser,
decision D26), not part of the model file, so the tour sets them up by hand:

1. **Run** (Ctrl+Enter): the cart overshoots to 1.24 m, the switch trips at 1.0937 s
   and the cart falls back to 0 (watch the Scope window). In the **Signals** tab,
   double-click `Pos/y` and `Ctrl/z` to plot them in the **Plots** tab too.
2. **Debug tab → Breakpoints → Break on: Events**, then **Debug** (F5). The run pauses
   at t = 1.0937 s on line 24 of `LimitSwitch` (`x > x_limit`). The plots stop at a
   *paused* marker and the 3D cart stands at the red post. Under **Watch expressions**
   add `s"Ctrl/z"` and `s"XRef/y" - s"Pos/y"`. Press **Continue** (F5) to finish.
3. **Code tab**, source `project:CartPID`: click the gutter of line 30 to set a line
   breakpoint, right-click the marker and set the **Condition** `abs(u) > umax`
   (pause only while the drive is saturated). **Debug** again: the pause is at
   t = 0.5 s on line 30, and **Variables** shows `err = 1` under Locals and `u = 40.8`,
   `z = 0.01` under Held outputs: the PID asks for 40.8 N, the drive gives 15 N.
4. **Step statement** (F10) to line 31: the anti-windup `if` is false (`aw = 0`), so
   the next step jumps to the next tick (line 26, t = 0.51 s). **Step tick** (F11) and
   **Continue** show `z` growing every saturated tick: integrator windup.
5. Remove the line breakpoint (click the marker). **Plots tab**: right-click the
   position plot before the step (about t = 0.45 s) and choose **Rewind to here**. A
   branch run replays the model to that time and pauses ("time breakpoint").
6. **Diagram tab**: select `Ctrl`; the inspector is in **live** mode. Set `aw` to 1
   and press Enter. **Debug tab → Edits** lists `Ctrl/aw = 1`.
7. **Continue** (F5): no event pause any more. The switch never trips; the cart
   overshoots only to 1.044 m and settles at 1 m.
8. **Edits → Replay** reruns the model as a normal run with the edit applied at its
   time: the result is bit-identical to the session. **Save parameters to model**
   writes `aw = 1` into the model (Ctrl+Z undoes it).

Also try: **Signals tab**, right-click `Pos/y` → **Break when…** `> 1.1` (pauses at
t ≈ 1.023 s, before the trip); right-click `Spring/p.e` → **Explain signal** (an
observed signal, `Spring/q / Spring/c`); the **Run to time** field (type a time and
press Enter while paused); **More step commands → Step event / Step solver step**;
a **Hit count** on the line breakpoint (for example 10 for the tenth saturated tick);
and the **Break on** switches for solver failure (E901) and the event limit (W206).

## Checks

`expected.json` checks the shipped (buggy) run through the real Julia worker
(`uv run examples/run_checks.py --only debug-tour`): `Pos/y` crosses 1.1 m at about
1.023 s and 1.2 m at 1.0936542 s (the event), the switch ends latched, the peak is
1.2436 m, `Ctrl/F` never exceeds 15 N, the scene binding is valid and there are no
W201, W205, W206, E900 or E901 diagnostics. The live-debug flow itself (event pause,
conditional line breakpoint, stepping, Rewind to here, live edit, Replay) is covered
by the real-worker Playwright spec `web/tests/e2e/debug-tour.spec.ts`.
