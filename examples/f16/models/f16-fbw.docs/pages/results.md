# Results

![Pitch rate, stabilator and alpha|900](assets/6b03c4266d7e.png)

| quantity | Sched | Frozen |
| --- | --- | --- |
| q at 1.2 s | 2.8 deg/s | 0.37 deg/s |
| q at 1.5 s | 5.3 deg/s | 1.8 deg/s |
| peak q | 5.37 deg/s | 7.09 deg/s |

bg-sim matches the nonlinear scipy reference (`design/closedloop.py`) to 3e-5 deg/s. The frozen gains are a quarter of what this flight condition needs: the loop is slow, then overshoots while the integrator unwinds. The scheduled gains give the same 0.2 s response as at the design points.
