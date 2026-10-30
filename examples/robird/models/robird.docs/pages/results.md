# Results

![Top view and tracking error|900](assets/6ed3ee4c5d1f.png)

![Altitude, speed and bank angle along the figure|900](assets/0c044c281079.png)

![Tail deflections, motor voltage and current, average aerodynamic power|900](assets/e8b855d48932.png)

## Measured (real worker, reltol 1e-4, 60 s, statistics after 8 s)

| quantity | value |
| --- | --- |
| figure completed | $x$ from -110.0 to 110.3 m ($A$ = 110), $y$ from -42.4 to 41.5 m ($B$ = 42); 2 sign changes of $x$ and 4 of $y$ in the rest of the lap |
| cross-track error | RMS 0.42 m, peak 0.85 m ([Guide/e_ct](signal:Guide/e_ct)) |
| altitude | 22.86 to 26.94 m (reference 23.5 to 26.5 m); error RMS 0.46 m, peak 0.86 m ([Guide/e_z](signal:Guide/e_z)) |
| speed | 11.29 to 12.78 m/s (command 12) |
| flapping | 3.69 to 4.50 Hz, stroke amplitude 0.51 rad ([JL1/qout](signal:JL1/qout)) |
| tail | elevons up to 0.25 rad (the start-up transient), rudder 0.011 rad; bank peak 31.4 deg |
| drive | motor voltage peak 10.6 V, current peak 6.4 A, mean 2.4 A; electrical 23.0 W, aerodynamic 16.2 W |
| cost | 44 s wall time for 60 s of flight (compile included), 12001 recorded rows |

## Checks (`expected.json`)

- the start: [Truth/z](signal:Truth/z) = 25 m at $t = 0$ and the start velocity along the tangent of the figure;
- periodic flapping: the dominant frequency of the flap angle and the motor-speed tracking of the commanded frequency;
- cross-track error at most 1.5 m and its RMS; altitude error at most 1.5 m, altitude band 21.5 to 28.5 m;
- the figure-eight completed: the extents $\pm A$, $\pm B$ within 3 m and the number of zero crossings of $x$ and $y$;
- actuators: elevons and rudder within $\pm 0.5$ rad, motor voltage below the duty limit, current below 12 A, bank below 0.6 rad, speed between 10 and 14 m/s;
- energy sanity: the average aerodynamic power ([PaSum/Pavg](signal:PaSum/Pavg)) about 16 W and positive;
- `scene_bindings`, and no error diagnostics. The `robird-trim` model (open loop at the trim command, 3 s) checks the flapping frequency and the stroke.
