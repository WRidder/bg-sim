# Results and checks

![Link angles, motor voltage and controller phase over the whole run|900](assets/cd19bf293776.png)

## Swing-up and catch

![Swing-up from hanging, first seconds|900](assets/01f01d38c1fe.png)

## Disturbance and recovery

![The tip force pulse and the recovery|900](assets/892f93489f8c.png)

## Numbers

The reference numbers are the independent sampled-data integration of `design.py`; the bond-graph run reproduces the link angles to better than 1e-4 rad over the whole scenario.

| quantity | value |
| --- | --- |
| swing-up | starts at 1 s, trajectory time 3.5 s, caught at 4.30 s |
| upright band before the disturbance | 0.0109 deg (all links, from 0.5 s after the catch) |
| disturbance | 0.1 N, 50 ms, at 8 s |
| peak deflection after the pulse | link 1: 15.7 deg, link 2: 7.2 deg, link 3: 2.5 deg |
| recovered (every link inside 1 deg) | from 9.37 s, 1.37 s after the pulse starts |
| peak motor voltage | 12.00 V of 12 V (recovery: 10.24 V) |
| design versus bond graph, free swing | 8.4e-06 rad |

## Acceptance checks (`expected.json`)

- hanging at rest before $t_{on}$: the angles [Upright/a1](signal:Upright/a1)… equal $-\pi$, the joint rates and the voltage [Ctrl/u](signal:Ctrl/u) stay 0, [Ctrl/phase](signal:Ctrl/phase) = 0;
- phase 1 during the swing-up, the catch time from the phase signal, phase 2 before the disturbance; the link angles at a quarter, half and three quarters of the trajectory against `design.py` (2 mrad);
- upright by $t_{on} + T_s = 4.5$ s: every link within 0.2 deg until the disturbance (measured 0.0109 deg);
- the pulse [DistForce/y](signal:DistForce/y) is 0.1 N for 50 ms; the peak deflection of each link after it against `design.py` (5 %), which makes the disturbance a checked, visible event;
- recovered: inside 1 deg from 9.37 s and inside 1e-3 rad over the last second;
- [Ctrl/u](signal:Ctrl/u) within the 12 V supply, [Motor/isense/y](signal:Motor/isense/y) below the stall current 4.8 A;
- model `free`: 3 joint angles at six times against the design ODE (1e-4 rad);
- 3D: every binding resolves and the link poses from the joint bindings equal the composed poses of the model ([PoseB1](block:PoseB1)…, [PoseTip](block:PoseTip)) to 1e-6 m;
- no E901, E106, W201, W202, W205, W206, E101 or E103.

## Reproduce

```
uv run examples/pendulum-triple-fixed/design/design.py          # trajectory, gains, library/TriplePendCtrl.jl, expected.json
uv run examples/pendulum-triple-fixed/design/build_model.py     # models/*.bgmodel.json and the scene
uv run examples/run_checks.py --only pendulum-triple-fixed
```
