# The guideway and the speed profile

The block [GwF](block:GwF) (and [GwR](block:GwR)), `Guideway` in `library/`, gives the rail deflection under a module at the track coordinate $s$ (the body $x$ plus or minus 9.5 m):

$$ z(s) = A_\mathrm{sag}\sin^2\!\frac{\pi s}{L_\mathrm{span}} + \frac{A_b}{2}\Bigl(1 - \cos\frac{2\pi (s - s_b)}{\lambda_b}\Bigr)\ \ (s_b \le s \le s_b + \lambda_b), $$

positive towards the vehicle, and the rail velocity $-v\,\mathrm{d}z/\mathrm{d}s$ that drives the flow source [ModF/Rail](block:ModF/Rail) of the module. A guideway with $z(s)$ at a joint is a lookup law, which is why this one block is a library block. The same function is in `design/design.py`.

The speed profile is the stdlib `TrapezoidalProfile` [Profile](block:Profile); the block [LsmCtl](block:LsmCtl) (`LsmController`) adds the acceleration and the drag as feedforward to a PI on the speed error and limits the thrust to 150 kN.

## Excitation

The sag has the wavelength $L_\mathrm{span} = 24.768$ m, so the excitation frequency is $v/L_\mathrm{span}$: 2.4 Hz at 215 km/h and 4.8 Hz at 430 km/h, close to the secondary suspension at 1 Hz and its harmonics only at low speed. The gap loop (poles around 130 to 1000 1/s) follows the rail; what reaches the body is the filtered remainder.
