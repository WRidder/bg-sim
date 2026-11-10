# Validation

Published data the checks compare against (`design/validation_data.json`, `design/jpl_hover_test.json`):

| quantity | published | model | check |
| --- | --- | --- | --- |
| Flight One hover rotor power | about 210 W (electrical) | 208 W | ±10 % |
| Flight One collectives, upper / lower | 8.2 / 9.2 deg (JPL pre-flight model: 9.0 / 9.9) | 8.61 / 9.87 deg | ±0.8 deg |
| hover thrust | weight 1.8 x 3.71 = 6.678 N | 6.678 N | 0.5 % |
| cyclic in 4-6 m/s wind | generally below 3 deg | 3.3 deg at a steady 5 m/s | at most 3.5 deg |
| 5 deg cyclic step, lower rotor hub torque | about 0.55 N m (JPL test) | 0.634 N m | ±20 % |
| JPL hover test $C_P(C_T)$ | 20 measured points | within 5 % | ±6 % (a fit check) |

**Not checked.** The CAMRAD II collective sweep of Dull et al. (2022) at Mars condition 2: the model is 4 % below it at 15 deg collective but makes 75 % more thrust at 4 deg, and it has no stall above about 18 deg. Forward-flight trim (2.2 deg pitch at 5 m/s, Dull et al.) is not reproduced: the model's rotor has no H-force from induced drag. Wind changes the hover power very little in the model, because the BEMT inflow only sees the axial airspeed.
