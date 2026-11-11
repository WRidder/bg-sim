# Short-travel controller (±0.5 m)

The same model has a second controller: set the dashboard's **Controller** select to *short travel*
(`Traj/controller = 1`) and press **Run**. The plant does not change: the rail with its soft end stops at
±1.5 m, the cart, the links and the ±40 N actuator are those of the full-travel model. Only the firmware's
tables and gains differ, and both sets live in [Traj](block:Traj) and [Ctrl](block:Ctrl), so the switch needs
no recompile. The ±0.5 m limit shows as thin green lines in the 3D view (markers, not stops) and as the two
limit lines of the dashboard's cart plot, which follow the selected controller; **Travel used** shows |x| in
percent of the limit.

**Design.** The swing-up is planned again with the travel as a hard collocation constraint, |x| ≤ 0.40 m
(0.1 m left to the feedback), |F| ≤ 35 N, still in 5 s. The time-varying LQR weighs the link rates harder
(Q = diag(100, 400×4, 10, 20×4), R = 0.3): with the full-travel weights the swing-up inside ±0.4 m saturated
the force and fell with three times the joint friction or with quantised encoders.

![Short-travel swing-up: link angles, stacked energy, cart position against ±0.5 m, force|900](assets/08bc5e0b80e6.png)

| | full travel | short travel |
| --- | --- | --- |
| peak cart travel | 0.581 m | **0.401 m** (80 % of ±0.5 m) |
| peak force | 14.13 N | 16.97 N |
| all links within 5° / catch | 3.97 s / 5.50 s | 4.00 s / 5.50 s |
| actuator work, friction losses | 6.99 J, 2.68 J | 7.14 J, 2.83 J |
| balance scenario: push peak, travel | 9.36°, 0.189 m | 9.36°, 0.189 m (38 %) |
| design closed loop: masses ±5 %, lengths +1 %, friction ×3 / ×2, cart +10 %, 1 and 2 ms delay, quantised encoders | all caught | all caught, travel ≤ 0.417 m |

The bond graph matches the design closed loop to the printed digits with both controllers.
`expected.json` runs this model twice: `quad-pendulum-swingup` and `quad-pendulum-swingup-short` (the override
`Traj/controller = 1`), and the same for the balance model; the short entries check the travel against
±0.5 m and the travel used below 100 %.
