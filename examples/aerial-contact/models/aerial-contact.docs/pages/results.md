# Results and checks

Every number is measured on the real worker (reltol 1e-4); `expected.json` holds the checks.

![Wall force|720](assets/96f289b57db5.png)

**Normal force against the prediction.** The wall force follows $m g \tan\theta_{sp}$ of the paper while $\theta_{sp}$ ramps and the end-effector climbs:

| $\theta_{sp}$ | measured $N$ | $m g \tan\theta_{sp}$ |
| --- | --- | --- |
| 17 deg (t = 7 s) | 6.74 N | 6.99 N |
| 20 deg (t = 8.5 s) | 8.29 N | 8.32 N |
| 23.5 deg (t = 10 s) | 9.53 N | 9.94 N |
| 27 deg (t = 12 to 28 s) | 11.4 to 11.6 N | 11.65 N |

The two differ by at most 0.68 N (6 %) between 8.5 and 28.4 s. The formula ignores the 0.38 kg of arm and end-effector and the geometry of the wheels, as the paper notes; the wheels share the force unevenly (2.2 to 5.5 N each) because the end-effector is tilted a little by the rubber mount. The normal force of every wheel stays positive through the contact phase (minimum 1.55 N).

**The impact.** The engage reference 12 degrees accelerates the multirotor over the last 20 cm: it meets the wall at 0.85 m/s at $t = 5.08$ s. The wheel contact is stiff (the brush spring of the real end-effector is not modelled), so the first impact peaks at 180 N for a few milliseconds and the multirotor bounces three times (the peaks of 75 N, 40 N and 25 N in the plot, the axis is clipped at 20 N); the damping of the contact ($c = 4$ s/m) and the angular engage controller let the bouncing die out within 1 s, and the contact phase starts at 6.12 s once the multirotor has been at rest at the wall for 0.3 s.

![Roll and yaw|720](assets/658fd7d9e24b.png)

**Roll and yaw** stay below 0.9 degrees in contact (the paper reports below 7.5 degrees).

![Locomotion|720](assets/ab5d475c3669.png)

**Locomotion.** At the command 0.125 the end-effector climbs 0.294 m in 6 s (the ideal is $0.125 \cdot 0.4 \cdot 6 = 0.30$ m) and returns 0.305 m after the 2 s pause; the multirotor follows within 0.7 cm with no change of any set-point: [TruthE/z](signal:TruthE/z) and [Truth/z](signal:Truth/z) are on top of each other. The driven slip of the wheels stays near 1 mm/s.

**Disengage.** The multirotor backs off to $x_b(t_d) - C$: 0.1872 m against the latched 0.1943 m (7 mm), the wheel plane is 0.7497 m from the wall, and the hover is quiet.

**Cost.** Compile 1 to 3 s, solve about 20 s for 34 s (300 000 solver steps) on the development machine; 17 001 rows $\times$ 2 566 signals, a 349 MB `columns.f64`.

Back to [the overview](page:overview).
