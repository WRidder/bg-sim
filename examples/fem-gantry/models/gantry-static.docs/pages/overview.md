# The crossbeam under 1 g

The beam alone, clamped at both end brackets, with the 12 kg Y carriage at mid-span on the rail, under 1 g along X: the inertia load of a 9.81 m/s² move. It checks the reduced beam's deflection and stress against beam theory. Set the global `g_y` to 0 to leave only the beam's own weight.

![Settled (deflection drawn x1000, colour: von Mises)|900](assets/b40a1f732b34.png)

![The three hotspots settle to their static stress|900](assets/ca827e9bd368.png)

Beam theory: clamped-clamped over the elastic span of 1.24 m (between the rigid interface regions), with shear deformation; σ = M c / I plus the Bredt shear of the carriage's offset weight, combined into von Mises.

| quantity | beam theory | simulation | difference |
| --- | --- | --- | --- |
| **beam and 12 kg carriage** | | | |
| deflection under the carriage | 26.50 µm | 27.79 µm | +4.9 % |
| front wall, 100 mm from A | 400.1 kPa | 407.1 kPa | +1.7 % |
| back wall, 100 mm from A | 679.0 kPa | 686.2 kPa | +1.1 % |
| back wall, mid-span | 890.4 kPa | 722.5 kPa | −19 % |
| **beam weight only** (`g_y` = 0) | | | |
| deflection at mid-span | 5.24 µm | 5.42 µm | +3.4 % |
| front wall, 100 mm from A | 82.2 kPa | 82.7 kPa | +0.5 % |
| back wall, 100 mm from A | 134.0 kPa | 140.2 kPa | +4.6 % |
| back wall, mid-span | 120.7 kPa | 115.4 kPa | −4.4 % |

The mid-span hotspot sits under the carriage: the guide blocks spread its load over 100 mm and the box's walls carry it with shear lag, so elementary beam theory overestimates the stress there. Under the distributed own weight the same point agrees within 4.4 %.
