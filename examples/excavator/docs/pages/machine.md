# The front of a 20-t hydraulic excavator

This project models the **front of a 20-t class crawler excavator**: the boom (5.70 m), the arm (2.90 m) and the
bucket (1.50 m, 0.93 m³ heaped). The mechanism is planar, with the **real cylinder linkage**: the two boom cylinders
from the upper structure to the boom, the arm cylinder from the boom to the arm tail, and the bucket cylinder
through the rocker and H-link **four-bar** to the bucket. The cylinders are driven by a **load-sensing (LS)
hydraulic system**: a variable pump at constant engine speed with an LS regulator, pressure cut-off and power
limiter, three pre-compensated proportional valve sections, a shuttle network, a main relief and the tank. The
bucket teeth cut **soil** with the fundamental earthmoving equation and fill the bucket.

![The dig cycle in 3D at 5.5 s: the bucket curls out of the cut, full|700](assets/a55d56f40cba.png)

| model | what it shows |
| --- | --- |
| [excavator-kinematics](model:excavator-kinematics) | the linkage alone: prescribed cylinder lengths, the bucket tip from forward kinematics |
| [excavator-lift](model:excavator-lift) | holding 1.5 t, the hydraulic ringing of the boom, then a boom lift through the LS system |
| [excavator-dig-cycle](model:excavator-dig-cycle) | a scripted 16.5 s dig cycle: penetrate, drag, curl, lift, dump, return |
| [excavator-no-ls](model:excavator-no-ls) | the same cycle on a constant-pressure supply (no load sensing), for the energy comparison |

All four share one design: `design/design.py` computes the parameters and the independent references (forward
kinematics, static forces, hydraulic modes, earthmoving factors) in Python, and `design/build_model.py` writes
the models, the 3D scene and `expected.json`. The details: [mechanics](page:mechanics),
[hydraulics](page:hydraulics), [soil](page:soil), and [checks and limits](page:checks).

**Energy.** The LS system costs **0.57 MJ** at the engine shaft for the dig cycle; the same cycle on a
constant-pressure supply (281 bar) costs **1.52 MJ**, 2.7 times as much.

![Engine energy and pump pressure in the dig cycle (load sensing)|900](assets/6b350eb7f0f3.png)

![The same cycle on a constant-pressure supply|900](assets/1025643e7e89.png)
