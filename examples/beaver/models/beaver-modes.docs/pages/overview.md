# Beaver modes

The de Havilland DHC-2 'Beaver' of the TU Delft *Flight Dynamics and Control* toolbox (FDC, M. O. Rauw), on the aerodynamic and engine model that Tjee & Mulder identified from flight tests. Five aircraft are trimmed at the thesis' point, 45 m/s at 6000 ft with the flaps up and the engine at 1800 rpm. Each is released on one eigenvector of the coupled linear model.

![The model canvas|900](assets/b183fc61a76c.png)

| block | role |
| --- | --- |
| [Phugoid](block:Phugoid), [ShortPeriod](block:ShortPeriod), [DutchRoll](block:DutchRoll), [Roll](block:Roll), [Spiral](block:Spiral) | one airframe each (a subsystem): rigid body, air data, aerodynamics, propulsion, wrench, drivetrain |
| [Trim_de](block:Trim_de) ... [Trim_pz](block:Trim_pz) | the FDC trim: elevator, ailerons, rudder, flaps, rpm, manifold pressure |
| [GrowRoll](block:GrowRoll), [GrowSpiral](block:GrowSpiral) | $\lambda = \dot\phi/\phi$: on a real mode this is the eigenvalue |

## What to try

1. Press **Run**. The phugoid swings with a 23.7 s period, the short period dies out within 2 s, and the Dutch roll within about 6 s.
2. Plot [GrowRoll/lambda](signal:GrowRoll/lambda) and [GrowSpiral/lambda](signal:GrowSpiral/lambda): they read $-5.133$ and $-0.0429$ 1/s.
3. Switch the **drivetrain** on with the dashboard slider. The modes hardly change: the shaft dynamics are fast and well damped.

## 3D view

The view keeps the phugoid aircraft (yellow) framed; the others fly 25 m to the sides. The floor is a reference plane 150 m below. The dots behind each aircraft are its path over the last few seconds, and the propellers turn at 1/20 of their speed.

![3D view at t = 4 s|600](assets/310cf61e8625.png)

Continue with [the airframe](page:airframe) and [the results](page:results).
