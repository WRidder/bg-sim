# Results and checks

The real worker runs the three models (Rodas5P, reltol 1e-8; `design/measured.json`):

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| free swing 2 s against the design ODE (angles / cart) | **4.3e-4 rad** / 4.3e-5 m | — |
| swing-up time / catch | 2.55 s after the start / 4.00 s | 2.55 s / 4.00 s |
| swing-up against the design closed loop (angles / cart) | 1.5e-3 rad / 0.3 mm | |
| upright band before the push | 0.0023° (cart 0.04 mm) | 0.0017° |
| push 0.45 N: link 1 / link 2; back inside 0.5° | 10.71° / 3.98°; 2.12 s | 10.70° / 3.98°; 2.12 s |
| peak voltage, current, travel | **15.01 V** of 24 V, 5.97 A, **0.387 m** of ±0.8 m | 15.02 V, 5.98 A, 0.387 m |
| balance model: push 0.70 N, link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| balance model: peak voltage, current, travel; recovery | 20.7 V, 11.0 A, 0.241 m; 2.29 s | 20.6 V, 11.0 A, 0.242 m; 2.29 s |
| run time (swing-up 12.5 s / balance 6 s / free 2 s) | 56 s / 11 s / 4 s | |

`expected.json` (written by `design/finish.py`) checks: the rest before 1 s, the phases, the link angles
during the swing-up against the design closed loop, the upright band, the push deflection and the recovery,
**the swing-up within the planned 16.8 V and the cart within the planned ±0.8 m**, the peak voltage, current
and travel, the scene bindings and no diagnostics; the balance model's catch, push and recovery; the free
model's cart and joint angles against the twin every 0.25 s. Run them with
`uv run examples/run_checks.py --only pendulum-double-cart-lab`.
