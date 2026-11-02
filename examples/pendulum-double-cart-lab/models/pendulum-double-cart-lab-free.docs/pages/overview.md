# The double-cart lab rig: free swing, the twin check

No control: the motor is shorted (the firmware never starts), the plant is released from rest at
θ = (−2.2, −1.2) rad, x = 0.05 m and swings for 2 s. `expected.json` compares the cart position and the joint
angles every 0.25 s with the design ODE, which is the Python twin of `design/lablib.py`.

The bond graph agrees with the twin to **4.3e-4 rad** on the joints and **4.3e-5 m** on the cart over the
2 s, so the design model, the twin of the realism screen and the bond graph are the same plant. The swing
includes the viscous joint, cable and carriage drag and the belt; the motor is shorted, so the back-EMF
drags the cart (β = 22.1 N s/m).

![Joint angles and cart|900](assets/1535f88b0a3a.png)

![Free swing: joint angles and cart|900](assets/1535f88b0a3a.png)
