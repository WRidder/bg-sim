# Horizontal steps: sway, tilt and peel

The tool makes three moves along x with alternating direction. Each move is an acceleration pulse of 0.15 s, a coast of 0.6 s and a deceleration pulse, at 1.5, 3 and 4.5 m/s². The pulses have 8 ms edges, so they are close to steps.

The box lags behind, the bellows shears ([Cup/ex](signal:Cup/ex)) and the box tilts ([Mon/sway](signal:Mon/sway)). The lateral load and the tilting moment raise the lip load on one side. Each pulse rings both lateral modes: the FFT of the coast after the first pulse gives 6.59 Hz (sway) and 13.13 Hz (tilt), against 6.55 and 13.20 Hz from the linearised model.

![Tool acceleration, lateral deflection, box tilt and U|900](assets/7cc68b572bde.png)

The peak U is 0.90 at the 4.5 m/s² pulse. The quasi-static value is 0.61: a sudden pulse overshoots the static deflection. The lip never lifts, and the box is held.

![Lateral force against the lateral deflection: the bellows spring with its damping loops|700](assets/d9308e7e31ec.png)
