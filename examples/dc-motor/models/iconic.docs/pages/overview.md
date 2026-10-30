# DC motor, iconic model

The walking skeleton of bg-sim (plan 9.1, milestone M1): a permanent-magnet DC motor driven by a 12 V step, built **twice**. This model is the *iconic* version, made of ready-made components; the bond graph version is documented in the model `bondgraph` and must give the same rotor speed. A third variant, `speed-control`, closes a sampled PI loop around the same plant.

The diagram contains a [step source](block:Step1), a [voltage source](block:V1), the [DC motor](block:Motor1) with its housing fixed by [FixHousing](block:FixHousing), a [damper](block:Damp1) to a [fixed shaft](block:FixShaft) and the electrical [ground](block:Ground1).

![Diagram of the iconic model|800](assets/1078c8343b4c.png)

## Run it

1. Press **Run** (Ctrl+Enter) and plot [Motor1/shaft.f](signal:Motor1/shaft.f). The speed settles at $\omega_\infty = 239.808\ \mathrm{rad/s}$ (see [Results](page:results)).
2. Change `R` of `Motor1` and run again. A parameter-only re-run reuses the compiled system, so it takes a few tens of milliseconds: a good place to feel the edit/run loop.
3. Raise the damper's `d` and watch the steady speed drop.
4. Zoom the plot: the UI re-requests the data for the new window.

## 3D view

`scenes/dc-motor.sdf` shows the motor housing and a rotor disc with a stripe. The joint `shaft` follows the rotor angle `Motor1/rotor/phi`, so the stripe turns at the simulated speed (about 240 rad/s: use a slow playback speed).

![3D view at t = 0.2 s|500](assets/b71e7a1c63c1.png)
