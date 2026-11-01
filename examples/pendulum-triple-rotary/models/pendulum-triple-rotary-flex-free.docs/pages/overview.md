# Flexible arm, free swing

The flexible-arm rig of `pendulum-triple-rotary-flex` with the controller off: the chain is released at rest from the free-swing pose of `pendulum-triple-rotary-free` (motor terminals at 0 V). The checks run it three ways:

- as it is: the energy ledger of the whole graph, with the [arm](block:Arm)'s kinetic, strain and gravity energy ([Arm/Ek](signal:Arm/Ek), [Arm/Ee](signal:Arm/Ee), [Arm/Eg](signal:Arm/Eg));
- `flex-tap`: hanging at rest, the hub clamped by a rotor inertia of 1e3 kg·m², a 2 ms push on the tip link. The arm rings at 42.66 Hz horizontally (exact frequency equation 42.68 Hz) and 121.9 Hz vertically;
- `flex-free-stiff`: the arm 1e4 times stiffer, against the rigid free model.

![Tap test|700](assets/669cbdce1a56.png)

![Stiff limit|700](assets/e9cf86df05d9.png)
