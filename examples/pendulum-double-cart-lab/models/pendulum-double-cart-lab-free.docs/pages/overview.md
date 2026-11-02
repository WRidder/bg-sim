# Free swing: the twin check

**Scenario.** No control: the motor is shorted (the firmware [Ctrl](block:Ctrl) has `t_on` = 10⁹ s and never
starts, phase 0). The plant is released from rest at θ = (−2.2, −1.2) rad from upright (−126° and −69°),
the cart at x = 0.05 m, and swings for **2 s**.

**What it checks.** `expected.json` compares the cart position and the joint angles every 0.25 s with the design
ODE, which is the Python twin of `design/lablib.py`. The bond graph agrees to **4.3e-4 rad** on the joints and
**4.3e-5 m** on the cart, so the design model, the twin of the robustness studies and the bond graph are the
same plant. The swing includes the viscous joint, cable and carriage drag and the belt; the shorted motor's
back-EMF drags the cart.

**Dashboard.** The same layout as the other models: the phase (0), the peak cart travel, the link angles in
degrees, voltage (0) and the current that the back-EMF drives through the shorted winding; the fourth plot
shows the joint encoder angles that the check compares. Sliders: the mass of link 2 and the joint-2 friction
(the check then fails, of course). **3D view:** the double pendulum swinging freely.

![Free swing: joint angles and cart|900](assets/1535f88b0a3a.png)

The rig and its models: [the double-cart lab rig](project:rig).
