# Balance and a large push (nominal firmware)

**Scenario.** Both links start leaning **2°** from upright, the cart at rest at the centre. The firmware is in
balance from the first tick. At **2 s** a **0.70 N, 40 ms** push on the tip ([PushPulse](block:PushPulse))
tests the recovery: 78 % of the largest push the design recovers (0.90 N). The run ends at **6 s**.

**Controller.** [Ctrl](block:Ctrl), the nominal firmware `library/DoubleCartLabCtrl.jl` with `t_on` = −10 s,
so the discrete LQR runs from the start (phase 2). See [design and margins](project:design).

**Dashboard.** The phase (2 throughout), the peak cart travel, the link angles in degrees, voltage and current,
with the plots of the angles, the cart with the end stops and the test limit, voltage and current, and the
push. The sliders set the push, its time and the mass of link 2. **3D view:** the links lean, are caught, then
swing out after the push.

![Link angles, cart, voltage and current|900](assets/be62c187c272.png)

**Expected outcome:**

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| the 2° lean, inside 0.5° before the push | 0.28° | |
| push: link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| back inside 0.5° after the push | 2.29 s | 2.29 s |
| peak voltage, current, travel | 20.7 V, 11.0 A, 0.241 m | 20.6 V, 11.0 A, 0.242 m |
| at the end (6 s) | 0.10°, cart 2 mm | |

**Try:** raise the push slider above **0.9 N**. The voltage saturates longer and the LQR loses the pendulum (or
the cart reaches the end stops). With 2 ms of delay the limit is 0.87 N.
