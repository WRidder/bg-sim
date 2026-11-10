# Maglev car on a guideway

A car section of 53 t on **two levitation modules**, each the module of [maglev-module](model:maglev-module) with the masses and the magnet doubled (two chassis pairs, half the car body each). The car body is a 3D rigid body. At 0.1 s the gap reference drops from the skid gap to 10 mm and the car lifts off (it rises 6.7 mm). At 4 s the long stator starts a speed profile: 1 m/s² up to **430 km/h** (119.4 s), 30 s of cruise, and the same deceleration. The guideway is a row of 24.768 m spans that **sag by 3 mm** at mid-span, with one smooth **2 mm bump** (a joint between two beams) at 8.5 km.

![The model canvas|900](assets/fb73f176cdb7.png)

## What to try

- On the Dashboard, change the **cruise speed** (30 to 119.5 m/s), the **sag** and the **bump height**. A bump of 6 mm still keeps the gap above the 8 mm limit that the checks use; read the gap and the body acceleration cards.
- Plot [AccZ/y](signal:AccZ/y), the vertical acceleration of the body's centre of mass, and [PitchRate/y](signal:PitchRate/y): the sag excites the car at $v/L_\mathrm{span}$, up to 4.8 Hz at cruise, and the bump pitches it because the rear module reaches the bump 19 m later.
- Plot [Lsm/p.e](signal:Lsm/p.e) and [Drag/p.e](signal:Drag/p.e): at cruise they are equal (35.6 kN), during braking the LSM pushes back.

## 3D view

`scenes/maglev-train.sdf` shows the car on a T-shaped guideway. The pillars scroll under the car with the span phase ([GwF/ph](signal:GwF/ph)), so the car stays in view for the whole 17.8 km. The gap pads, the heave and the pitch are drawn **100 times larger** than they are (the nominal gap itself is true to scale); the copper coils are coloured by the coil current.

![3D view at t = 135.5 s|700](assets/c7dc9516c198.png)

Continue with [the 3D body](page:body), [the guideway](page:track) and [the results](page:results).
