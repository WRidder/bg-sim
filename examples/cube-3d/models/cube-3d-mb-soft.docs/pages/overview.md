# Cube corner balancer, soft pivot

The `cube-3d-mb` model with a 100 times softer pivot: [Pivot](block:Pivot) has $k_t = 10^6$ N/m and $b_t = 158$ N·s/m (against $10^8$ and 1581). Everything else, including the controller and the gain $K$, is identical. The pivot sags by $m g/k_t = 4.1\cdot10^{-6}$ m (the check allows at most 1e-5 m).

![The model canvas|900](assets/ca1688e9d795.png)

Its purpose is the scaling measurement of DEC-M5-3: the difference between the equation block and the multibond cube is a $1/k_t$ effect, so softening the pivot by 100 makes the difference grow by about the same factor (75 / 122 / 59 for the body rates from 0.5 s; tilt difference 2.4e-5 rad against 4.2e-7 rad). Plot [Tilt/tilt](signal:Tilt/tilt). The model has no 3D scene.
