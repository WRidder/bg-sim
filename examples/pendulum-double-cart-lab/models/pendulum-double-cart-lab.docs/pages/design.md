# Design and margins

`design/design.py` reuses the design code of `pendulum-double-cart` (`cartpend.py`: the Lagrangian design
model, Hermite-Simpson collocation with IPOPT, the continuous TVLQR, the discrete LQR; `cartmodel.py`: the
bond graph). The design model and the Python twin are the same equations (checked to 1e-15).

1. **Swing-up plan with margins.** Hanging to upright at rest in $T_s = 3.0$ s (75 intervals), minimum
   $\int V^2 dt$, with the voltage bounded to **16.8 V (70 % of 24 V)** and the cart to **±0.8 m**. The plan
   needs 14.8 V (62 %) and ±0.39 m: neither bound is active, a shorter 2.4 s plan would hit both.
2. **TVLQR** along the plan and the **discrete LQR** (1 ms, ZOH) at the upright with
   $Q = \mathrm{diag}(300, 400, 400, 10, 8, 8)$, $R = 0.3\ \mathrm{V}^{-2}$; largest gain 329.
3. **Catch** at $\tau = T_s$ (4.0 s), time-based as in `pendulum-double-cart`.

![Swing-up: the bond graph against the plan|900](assets/2b75a3c5958a.png)

**Robustness** (firmware replica on the twin; every case caught, balanced and recovered from the push):

| case | swing-up: peak V, peak x | balance push (0.70 N): peak deflection |
| --- | --- | --- |
| nominal | 15.0 V, 0.387 m | 17.3° |
| link masses −5 % / +5 % | 14.9 / 15.1 V | 18.4° / 16.4° |
| link lengths +1 % / −1 % | 14.8 / 15.3 V | 17.1° / 17.5° |
| joint friction ×3 | 15.8 V | 17.6° |
| carriage friction ×3 | 15.3 V | 17.3° |
| cart mass +10 % | 15.1 V | 17.6° |
| delay 1 ms / 2 ms | 15.0 / 15.0 V | 17.5° / 17.6° |
| quantised encoders (14 bit, 8.4 µm) / with 2 ms delay | 18.5 / 17.4 V | 17.5° / 17.8° |
| all of the above at once (+5 %, +1 %, ×3, 2 ms, quantised) | 16.6 V, 0.385 m | 16.9° |

The largest 40 ms tip push the balance recovers from upright is **0.90 N** (0.87 N with 2 ms delay; the
voltage saturates briefly, the cart travels 0.34 m). The belt mode (177 Hz, 124 Hz with the softest belt)
stays damped in closed loop with 0 to 2 ms of delay.
