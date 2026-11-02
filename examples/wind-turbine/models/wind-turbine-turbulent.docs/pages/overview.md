# Turbulent wind at 18 m/s

Ten minutes of seeded turbulence at 18 m/s, with the IEC class-B standard deviation of 2.67 m/s. The turbulence is band-limited white noise ([WhiteNoise](block:WhiteNoise)) through a first-order filter ([Turbulence](block:Turbulence)). Its time constant is the Kaimal length scale over the wind speed, 18.9 s. It is one point of wind, a simple stand-in for a full turbulence field.

![Ten minutes of turbulence|900](assets/50c42abf958a.png)

## What you see

- The pitch ([Aero/beta_deg](signal:Aero/beta_deg)) works all the time to hold 12.1 rpm.
- The power follows the rotor speed within a few percent.
- The tower-top deflection ([TowerSpring/q](signal:TowerSpring/q)) follows the thrust with its 0.32 Hz mode on top. The shaft twist ([ShaftC/q](signal:ShaftC/q)) rings at the 2.22 Hz drivetrain mode. The checks find both peaks in the spectra.

## What to try

- Change the global `seed` for another realisation, or `v_mean` for another wind.
