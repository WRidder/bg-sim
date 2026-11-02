# Design and margins

The nominal controller of [pendulum-double-cart-lab](model:pendulum-double-cart-lab) and
[-balance](model:pendulum-double-cart-lab-balance). `design/design.py` reuses the design code of
`pendulum-double-cart`: the Lagrangian design model (the same equations as the twin, checked to 1e-15),
Hermite-Simpson collocation with IPOPT, the continuous TVLQR and the discrete LQR.

1. **Swing-up plan with margins.** Hanging to upright at rest in $T_s = 3.0$ s, minimum $\int V^2 dt$, with
   the voltage bounded to **16.8 V (70 % of 24 V)** and the cart to **±0.8 m**. The plan needs 14.8 V and
   ±0.39 m: neither bound is active (a 2.4 s plan hits both).
2. **TVLQR** along the plan and the **discrete LQR** (1 ms, ZOH) at the upright, both with
   $Q = \mathrm{diag}(300, 400, 400, 10, 8, 8)$, $R = 0.3\ \mathrm{V}^{-2}$; largest gain 329.
3. **Firmware** (`library/DoubleCartLabCtrl.jl`, tables in `DoubleCartLabTraj.jl`): phase 0 holds 0 V until
   1 s, phase 1 is the swing-up (feed-forward plus TVLQR), phase 2 the LQR from the timed catch at 4.0 s.

![Swing-up: the bond graph against the plan|900](assets/2b75a3c5958a.png)

| margin | value |
| --- | --- |
| peak voltage in the swing-up | **15.0 V** of 24 V (the plan bound 16.8 V is never reached) |
| peak current | 5.3 A in the swing-up, 6.0 A over the run (stall 16 A) |
| peak travel | **0.387 m** of the ±0.8 m plan and the ±1.0 m rail |
| largest 40 ms tip push recovered (from upright) | **0.90 N** (0.87 N with 2 ms delay): 27.6° on link 1, 0.34 m |
| belt mode in closed loop (0 to 2 ms delay) | 177 Hz, ζ 0.07 to 0.13: stable (softest belt 124 Hz) |

**Robustness on the twin** (the firmware replica). Every case catches, balances and recovers from the push:
link masses ±5 %, lengths ±1 %, joint and carriage friction ×3, cart mass +10 %, 1 and 2 ms delay, quantised
encoders, and all of them at once (16.6 V, 0.385 m, 16.9° after the 0.70 N push). The bond graph matches the
design closed loop to 1.5e-3 rad and 0.3 mm in the swing-up and to 0.01° after the push.
