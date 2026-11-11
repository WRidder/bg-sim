# Levitation module

One EMS magnet module carries a quarter of a car section: a **levitation chassis** of 1.5 t under the rail and a **body share** of 11.75 t hanging from it on the secondary suspension (spring and damper, 1 Hz). Everything starts at rest on the **skids**, with the gap at 16.7 mm. The coil is energised from zero at the start. At 0.1 s the gap reference drops to 10 mm (through a 0.15 s lag), the magnet lifts the module off the skids at about 0.45 s and the controller holds 10 mm. At 2 s the guideway sinks by 1 mm (smoothed over about 10 ms), and at 4 s a payload of 2 t is added to the body share.

![The model canvas|900](assets/aca26edbdc76.png)

## What to try

- Open the **Dashboard**. Move **Guideway step** to −3 mm or +3 mm, or the **Payload step** to 4000 kg: the plots re-run. The gap returns to 10 mm in both cases because of the integral action; only the **current** changes with the weight, as $i = c_\mathrm{trim}\, h\,\sqrt{W'/W}$.
- Plot [EM/i](signal:EM/i) and [Ctl/v](signal:Ctl/v) during the lift-off: the chopper saturates at +800 V for about 25 ms while the coil is magnetised, the current overshoots to 241 A, and the module leaves the skids at 0.45 s.
- Open [maglev-module-open-loop](model:maglev-module-open-loop) to see the instability that the controller removes.

## 3D view

`scenes/maglev-module.sdf` is a side view: the rail on pillars, the magnet pad with its copper coil (coloured by [EM/i](signal:EM/i)) under it, and the body hanging on the secondary suspension. The gap deviation from 10 mm is drawn 20 times larger and the spring stretch 5 times larger than it is.

![3D view at t = 0.9 s|500](assets/eeb3bd2ca619.png)

Continue with [the plant and the controller](page:design) and [the results](page:results).
