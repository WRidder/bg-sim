# Gyrover: a single wheel that balances with a flywheel

The **Gyrover** (Carnegie Mellon) is a robot that is nothing but a wheel. Inside the tyre a drive unit hangs from the axle like a pendulum, and it carries a **flywheel spinning at about 15 000 rpm** in a gimbal. Three motors act:

- the **drive motor** turns the wheel against the hanging pendulum (speed);
- the **tilt motor** turns the flywheel gimbal about the forward axis; the gyroscopic reaction leans the wheel, and a leaning wheel turns (steering and balance);
- the **flywheel motor** keeps the spin speed.

This example rebuilds the robot after

> S.-J. Tsai, E. D. Ferreira and C. J. J. Paredis, *Control of the Gyrover: a single-wheel gyroscopically stabilized robot*, IEEE/RSJ IROS 1999.

as a physical bond graph from library blocks, checks it against an independent equation-based model, and closes the paper's balance loops plus speed and heading loops around it. In the showcase run the robot starts at rest, speeds up to 1.2 m/s and drives a rounded square of four 90-degree turns on the 10 m floor.

![The 3D view at 9 s, in the first turn: the wheel leans into the turn, the gimbal is tilted|900](assets/ad96c9d84c11.png)

![Path of the wheel centre|500](assets/01e12b5e2765.png)

## Run it

Press **Run** (30 s, about 25 s of solving). The **3D View** tab replays the run: tyre with tread and spokes, translucent side covers, the drive unit (hub motor, battery, fork, red tilt motor), the gimbal ring and the brass flywheel (drawn 200 times slower than it turns). The orange discs on the floor are the path of the run, every 0.5 m.

The **dashboard** has sliders for the cruise speed ([Plan](block:Plan) `v_cruise`) and the heading change of each turn (`dpsi`), gauges for the lean and the tilt and the heading against its set-point. Change a slider and press **Run** again.

Default plots: lean and tilt, heading, wheel rate and speed, flywheel speed, the x-y path, the three motor torques and the energy book.

## Models of the project

| model | what it shows |
| --- | --- |
| `gyrover` | the showcase: bond graph, all loops closed, 30 s mission (this page) |
| `gyrover-ref` | the same mission on the equation-based reference model |
| `free`, `reference` | uncontrolled rolling, bond graph and reference, energy book |
| `steady-turn`, `steady-turn-ref` | a steady turn against its exact solution |
| `spin`, `no-spin` | standing on the rim: the flywheel keeps the robot up, without it it falls |
| `fig3`, `fig3-ref` | the paper's figure 3 (recovery with the paper's gains) |
| `fig3-drill` | figure 3 with tyre drilling damping: the slow mode turns unstable |

Pages: [model and bond graph](page:model), [the rolling contact](page:rolling), [parameters](page:parameters), [validation](page:validation), [control design](page:control).
