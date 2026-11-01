# Results and checks

## Rigid firmware on the flexible arm (this model)

| quantity | value |
| --- | --- |
| first voltage saturation | 2.88 s (the rigid arm never saturates before the push) |
| arm mode under the swing-up loop, before the saturation | 105.7 Hz |
| largest modal coordinate eta_y[1] | 3.47 mm (sideways tip deflection 7.46 mm) |
| catch | never ([Ctrl/phase](signal:Ctrl/phase) stays 1) |
| chain not upright (a link beyond 30 deg after T_s) | from 5.00 s on |
| arm angle at the end | 49 rad: the saturated motor drives the arm round |

## Low-pass firmware on the flexible arm (`pendulum-triple-rotary-flex-lowpass`)

| quantity | flexible arm, low-pass firmware | rigid arm, rigid firmware |
| --- | --- | --- |
| catch | 5.00 s | 5.00 s |
| upright band before the push | 0.0014 deg | 0.0008 deg |
| tip link deflection after the push | 5.72 deg | 3.55 deg |
| recovery inside 0.5 deg | 2.24 s | 1.35 s |
| peak voltage | 14.92 V | 14.15 V |
| largest sideways tip deflection: swing-up, balance, after the push | 1.624 mm, 0.01 µm, 651.5 µm | 0 |
| largest vertical tip deflection | 18.88 µm | 0 |

![The low-pass firmware on the flexible arm, against the rigid arm|700](assets/0a222c0fa24a.png)

![The push: recovery and arm deflection|700](assets/3597df47b65b.png)

## Stiff limit

The free model with the arm's E overridden to 10000 times the steel's (`flex-free-stiff`) against the rigid free model: the largest difference over the first second is 1.6e-05 rad (J1 2.1e-06, links 1.1e-05, 1.6e-05, 1.2e-05 rad). The free swing is chaotic, so the difference grows afterwards, as it does between any two slightly different models. With the real strip the swing departs from the rigid one within a second.

![Stiff limit|700](assets/e9cf86df05d9.png)

## Checks (`expected.json`)

- all three flexible models: scene bindings, no W201/E901 diagnostics, the energy ledger of the whole graph (Tellegen residual below 1e-6 of the throughput, the arm's modal bond graph included);
- `-flex`: the balance phase is never reached, the voltage saturates in the swing-up, the arm mode rings at 106 Hz before that (10 %), the arm tip deflection, the chain is not upright at the end;
- `-flex-lowpass`: caught one second after t_on + T_s, upright band, the push and the recovery, the voltage limit, the arm deflection while balancing and in the swing-up;
- `flex-tap`: the first horizontal arm mode against the exact frequency equation (42.68 Hz, 1 %) and the first vertical mode against the two-mode model (122.3 Hz, 1 %);
- `flex-free-stiff` against `pendulum-triple-rotary-free`: J1 and the three link angles over the first second.

Back to the [overview](page:overview).
