# The rotor on the JPL test stand

The coaxial rotor on a fixed stand in the JPL 25-ft Space Simulator: CO2 at 0.0175 kg/m³, 2600 rpm (Koning et al. 2019). [Stand](block:Stand) steps the thrust coefficient through the measured range with a PI law on the symmetric collective and trims the pair torque-free with the differential collective. From 16 s it applies 5 deg cyclic steps on the lower rotor (pitch, then roll), the system-identification sequence of Grip et al. (2017).

![The model canvas|900](assets/39967395766c.png)

![Thrust sweep and cyclic steps|900](assets/1c3cac1f78f6.png)

## What you see

- [Telem/CP](signal:Telem/CP) on each plateau of [Telem/CT](signal:Telem/CT) lies within 5 % of the measured hover test. This is where the profile-drag polar was fitted, so it is a consistency check.
- The 5 deg cyclic steps give 0.634 N m of hub moment ([AeroL/ty](signal:AeroL/ty), [AeroL/tx](signal:AeroL/tx)); the test measured about 0.55 N m. The quasi-steady model has no first-harmonic inflow, which would oppose the cyclic moment.
- The electrical power ([Telem/P_el](signal:Telem/P_el)) reaches 590 W at the highest thrust; the stand's supply is set to 25.2 V, the pack's full-charge voltage.

## What to try

Plot [Telem/CP](signal:Telem/CP) against [Telem/CT](signal:Telem/CT) and compare it with `design/jpl_hover_test.json`. Lower the chamber density on the dashboard: the coefficients stay the same, the forces scale with the density.
