# Quad pendulum on a rotary arm: free swing, the twin check

No control: the arm and the chain start tilted at rest and swing freely for 1.5 s. `expected.json` compares
the arm angle and the link angles every 0.25 s with the Python twin (the spatial Lagrangian of
`design/quadlib.py`): the largest difference is 1.7e-6 rad on the arm and 2.6e-3° on the link angles.

![Free swing: link angles and arm|900](assets/df876b8fe318.png)
