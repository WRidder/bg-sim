# Results

![alpha, q and the growth rates|900](assets/56307e312d81.png)

| quantity | bg-sim | reference |
| --- | --- | --- |
| alpha, q of all three aircraft at 1, 3, 5 s | within 1e-4 deg, deg/s | scipy (`design/scenarios.py`) |
| [GrowA38/lambda](signal:GrowA38/lambda) at 1 s | 0.65723 1/s | linear: +0.65724 |
| [GrowA35/lambda](signal:GrowA35/lambda) at 3 s | 0.1020 1/s | linear: +0.1021 |
| A38 airspeed at 0.5 s | 153.0 m/s | trim 502 ft/s |
| energy E - work of the wrench (A30) | constant to 1e-7 | |

The forward-CG aircraft keeps a stable short period ($-1.2038 \pm 1.4922j$; book $-1.2039 \pm 1.4922j$) and a slow phugoid. At 0.35 the 6-state linearisation already has a slow unstable real pole (+0.102 1/s): the short-period pair has split into two real poles, so the stable case of this example is 0.30. At 0.38 the unstable pole is +0.657 1/s, a time to double of 1.05 s: no pilot could fly that without the fly-by-wire of `f16-fbw`.
