# Quad pendulum on a cart: balance only

The model `quad-pendulum-swingup` with the firmware in the balance phase from
the start (`Ctrl/balance_only`). The chain starts leaning 2° per link (globals `th0_1..th0_4`), the LQR
catches it, and a 50 ms push on the tip at 3 s (half of the largest push the design closed loop survives)
tests the recovery.

![Link angles, cart position and force|900](assets/7573bd0aad55.png)

Try the dashboard inputs: the start angles, an actuator delay (whole 1 ms samples), quantised encoders
(16-bit joints, 10 µm cart, filtered difference rates), a heavier or lighter chain (the gains stay nominal)
and a lower force limit.
