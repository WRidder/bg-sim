# Quad pendulum on a cart: free swing, the twin check

No control (the swing-up never starts). The chain starts from a tilted pose at rest and swings freely for
1.5 s, with the cart free on the rail. `expected.json` compares the cart position and the four link angles
every 0.25 s with the Python twin (the Lagrangian of `design/quadlib.py`, integrated by SciPy DOP853 at
rtol 1e-11): the largest difference is 1.0e-7 m on the cart and 7.0e-4° on the link angles. The energy ledger (mechanical energy plus friction losses)
stays constant to 1e-6 J.

![Free swing: link angles and cart|900](assets/7070d4f77988.png)
