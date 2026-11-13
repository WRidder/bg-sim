# Results

![The five modes|900](assets/a82f3492f46f.png)

| mode | bg-sim (fit or growth rate) | coupled linear model | THESIS Table 5-3 (decoupled) |
| --- | --- | --- | --- |
| phugoid | damping fit of [Phugoid/Air/V](signal:Phugoid/Air/V) | $-0.01757 \pm 0.2651j$ | $-0.01614 \pm 0.2631j$ |
| short period | fit of [ShortPeriod/Air/alpha_deg](signal:ShortPeriod/Air/alpha_deg) | $-2.1584 \pm 2.4207j$ | $-2.1606 \pm 2.4112j$ |
| Dutch roll | fit of [DutchRoll/Air/beta_deg](signal:DutchRoll/Air/beta_deg) | $-0.4791 \pm 0.9662j$ | $-0.4770 \pm 0.9763j$ |
| roll | [GrowRoll/lambda](signal:GrowRoll/lambda) | $-5.1332$ | $-5.1351$ |
| spiral | [GrowSpiral/lambda](signal:GrowSpiral/lambda) | $-0.04289$ | $-0.04573$ |

The decoupled 4-state modes of the reference reproduce Table 5-3 and FDC's own linear model. The coupled model includes the strong longitudinal-lateral cross-coupling of the Beaver, which comes from the propeller's slipstream; that is what the nonlinear aircraft does. The thesis' lateral modes differ in the third digit because the 1993 model applied the $\dot\beta$ correction with the opposite sign (the README explains it). The README also lists the trim against Table 5-1 and the linearisation against FDC's A and B matrices.
