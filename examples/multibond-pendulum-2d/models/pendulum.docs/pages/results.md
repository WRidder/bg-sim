# Results and checks

![Joint angle, pivot deflection and angular rate over the 4 s run|900](assets/c50ed2378a43.png)

The editor's Run uses `t_end` = 4 s (4001 points, `reltol` 1e-9, `abstol` 1e-11); the checks re-run the same model with a 10 s settings override for the energy budget.

## Measured values (README)

| quantity | value |
| --- | --- |
| period from `Joint/q` up-crossings | 1.41879603183 s |
| amplitude-corrected physical period (with $L_{eff} = 0.5000000981$ m and $q_0^2/16$) | 1.41879603223 s (relative -2.8e-10) |
| simple reference $2\pi\sqrt{L/g}$ | 1.41850335344 s (relative +2.1e-4) |
| energy drift over 10 s | 1.77636e-15 J |
| KE/PE swing $m g L (1 - \cos q_0)$ | 2.4524796e-4 J |
| drift divided by swing | 7.2431e-12 (target 1e-6) |
| states | 6 (P 3, d 2, q 1), all differential |
| adaptive steps | 4072 for 4 s, 10072 for 10 s |

## What `expected.json` checks

1. [Joint/q](signal:Joint/q) = 0.01 rad and the static $d_0$ at $t = 0$ (three `cursor_value` checks);
2. the **period** from the first two upward zero crossings within 1e-5 of the amplitude-corrected physical period, and a second `period` check against the simple $2\pi\sqrt{L/g}$ at relative 1e-3;
3. the amplitude $\max\lvert q\rvert = 0.01$ over 4 s;
4. the **energy** budget $E = \tfrac12 P^T M^{-1} P + m g h + \tfrac12 k_t\lvert d\rvert^2$ with $h = g_y + \sin q\,d_1 + \cos q\,d_2$, normalised by the swing (the runner's `energy` kind);
5. `no_diagnostics` (W201, E101, E102, E103, E106, W206) on both runs.
