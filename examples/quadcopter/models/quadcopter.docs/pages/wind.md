# Wind, gusts and the dashboard

The wind acts through the linear air drag of `RotorWrench`, $-c_d (v - R^T w)$ per body axis ($c_{d,x} = c_{d,y} = 0.25$, $c_{d,z} = 0.35$ N s/m). It has three parts, all set by global parameters:

- the **mean wind** `wind_x`, `wind_y` (0.4, -0.2 m/s);
- the **turbulence** of `Wind`: a new Gaussian gust every 0.5 s with standard deviation `wind_sigma` (0.5 m/s), smoothed by the 1 s lag `Gust`;
- a **discrete gust** of `GustPulse`, the 1-cos shape of the gust load standards, $g(t) = \tfrac{A}{2}\,(1 - \cos(2\pi (t - t_0)/T))$ for $t_0 < t < t_0 + T$. It blows towards the heading `gust_dir` and is off (`gust_speed` = 0) by default.

The **Dashboard** tab has a slider for each of these, readouts of the wind speed, the distance to the set-point, the tilt, the altitude, a rotor speed and the battery, and plots. Press **Run** after a change: the mission takes about a minute to simulate. In the 3D view, the wind vane beside the pads turns to the wind's heading and is coloured by its speed.

![Wind at the airframe during the mission (default settings)|900](assets/b8a50b5fddb7.png)

**Checks.** `quadcopter-wind-hover` validates the drag against statics (below). A 4 m/s gust towards +y from 6 to 8 s, flown in `run_checks.py` as an override, takes the quadcopter at most 19.1 cm off its set-point. Its tilt peaks at 0.254 rad, inside the 25 degree limit, and it still lands.
