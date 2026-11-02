# The double-cart lab rig: balance and a large push

The model `pendulum-double-cart-lab` with the firmware in the balance phase from the start
([Ctrl](block:Ctrl) `t_on` = −10 s). Both links start leaning 2°, the discrete LQR catches them, and at 2 s
a **0.70 N**, 40 ms push on the tip ([PushPulse](block:PushPulse)) tests the recovery: 78 % of the largest
push the design recovers (0.90 N).

![Link angles, cart, voltage and current|900](assets/3614e0867a78.png)

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| the 2° lean, inside 0.5° before the push | 0.28° | |
| peak deflection link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| back inside 0.5° after the push | 2.29 s | 2.29 s |
| peak voltage, current, travel | 20.7 V, 11.0 A, 0.241 m | 20.6 V, 11.0 A, 0.242 m |
| at the end (6 s) | 0.10°, cart 2 mm | |

The voltage stays below the 24 V supply and the cart well inside the ±0.8 m plan. Raise the
[PushPulse](block:PushPulse) amplitude to find the limit: the design's largest recoverable push is 0.90 N
(0.87 N with 2 ms delay), where the voltage saturates briefly and the cart travels 0.34 m.
