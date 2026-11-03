# Results

The bg-sim runs match an independent scipy model of the same blocks (`design/heli_si.py`, LSODA 1e-10) to about 1e-5 in every state over the 10 s of the checks.

Collective step in hover:

![Collective step|900](assets/7827408595d7.png)

The thrust rises, the helicopter climbs (13 m after 10 s) and the torque reaction yaws it right (34 deg/s). The rotor droops 0.25 % and the governor brings it back.

The hover phugoid after the cyclic pulse:

![Hover phugoid|900](assets/074d7f817031.png)

The report publishes no eigenvalues. The scipy linearisation gives $+0.211 \pm 0.598j$ (longitudinal) and $+0.051 \pm 0.620j$ (lateral) in hover. The check fits a damped oscillation to the pitch attitude of Lon and reads $\zeta = -0.28$, $\omega_n$ = 0.66 rad/s, against −0.33 and 0.63 rad/s.

The pedal pulse at 100 kt:

![Pedal pulse at 100 kt|900](assets/9c1782bc80f6.png)

With the constant-RPM switch (`rpm_mode = 0`) the collective step yaws further, 189 deg of heading at 10 s against 170 deg:

![Constant rotor speed|900](assets/536cedcca3d3.png)

The trims against the report's fitted model (power, attitudes and the four control positions from hover to 120 kt and in sideward flight) are tabulated in the example's README. Power, pitch, collective, pedals and longitudinal cyclic follow the report's curves. The roll attitude and the lateral cyclic in forward flight do not; the README flags this.
