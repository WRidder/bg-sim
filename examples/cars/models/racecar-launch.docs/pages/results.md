# Results

![Speed, motor torque and battery|900](assets/ac702a260ae9.png)

The reference is a 1-D longitudinal model (`design/reference.py`): the vehicle, the front and rear wheel spins, the rotor and the elastic shaft, the battery charge, the same envelope, traction control and tyre formulas with a quasi-static load transfer, integrated with scipy.

| t [s] | speed bg-sim / reference [m/s] | motor torque [N m] | SOC |
| --- | --- | --- | --- |
| 2 | 16.03 / 16.25 | 300 / 300 | 0.89920 / 0.89918 |
| 4 | 31.54 / 31.74 | 300 / 300 | 0.89670 / 0.89665 |
| 8 | 53.73 / 53.76 | 213.0 / 212.9 | 0.88864 / 0.88858 |
| 12 | 63.92 / 63.84 | 179.2 / 179.4 | 0.88042 / 0.88036 |

The 0.2 m/s lag comes from the first 0.1 s: the model's tyres have a contact-patch deflection, so the wheels spin up briefly before the car moves and the traction control cuts in. The 1-D reference uses steady-state slip. After that, both accelerate at 7.75 m/s² at the torque limit and follow the same power-limited curve.
