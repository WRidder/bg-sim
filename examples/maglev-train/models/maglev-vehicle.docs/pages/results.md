# Results

![Speed, thrust, drag and the gaps over the whole run|900](assets/3bc7b0a2fb6a.png)

![Lift-off|700](assets/3845fb346689.png)

![The bump at 134.8 s|900](assets/a4e8d4332fce.png)

- **Levitation at rest.** After lift-off each module draws the trim current 150.0 A, carries $(m_b + m_c)g = 260$ kN (half the body and its chassis), and the body has risen by $h_\mathrm{rest} - h_0 = 6.7$ mm.
- **Speed.** $v = a(t - t_\mathrm{go})$ during the acceleration (56 m/s at 60 s), 119.44 m/s at cruise. The thrust is 35.6 kN at cruise and equals the aerodynamic drag $k_\mathrm{aero} v^2$. The aerodynamic power at 400 km/h is 3.42 MW; Wikipedia quotes 3.53 MW (with the same Cd and area, so this is a consistency check and not a validation).
- **Gaps.** Within 9.5 mm and 10.5 mm over the whole run, the skids carry nothing after the lift-off.
- **Ride.** The sag and the bump keep the body acceleration below 0.5 m/s² (peak, unweighted) and the pitch below 0.2 mrad. The bump is passed by the front module first and by the rear module 0.16 s later at cruise.
- **Reference.** A planar scipy simulation of the same car (heave, pitch, two modules, LSM, guideway; `design/design.py`) agrees with this model within 15 µm in the position of the body's centre and within about 70 µm in the gap during the bump, the checks give the tolerances.
