# Results and checks

The table compares the bond graph (Rodas5P, rtol 1e-6) with the Python twin of `design/actilink_lib.py`. The twin has the same physics, but with the 16 kHz digital current loop, integrated by RK4 at 32 kHz.

| quantity | bond graph | Python twin |
| --- | --- | --- |
| free swing over 3 s (arm / link 1 / link 2) | 0.86 / 0.15 / 0.27 mrad max difference | |
| swing-up: catch | 4.00 s | 4.00 s |
| swing-up: largest arm angle | 2.98 rad | 2.98 rad |
| swing-up: peak torque target / $i_q$ / $u_q$ | 12.0 N·m (clamp) / 8.3 A (limit 44.2) / 7.4 V (limit 26.3) | 12.0 / 8.3 / 8.5 |
| swing-up: band from catch + 1.5 s; final deviation | 0.41°; 0.012° | 0.33°; 0.017° |
| swing-up: peak gear deflection | 6.3 mrad | 6.3 mrad |
| balance (AS5048A): band after 1.5 s; arm limit cycle | 0.33°; 1.2° p-p | 0.37°; 1.7° p-p |
| push 0.3 N, 50 ms: link 2 peak; arm; back inside 1° | 4.7°; 55°; 1.40 s | 4.5°; 53°; 1.40 s |
| balance with AS5048B (I2C) | | 0.32°; arm 1.4° p-p |

**Energy.** `ALEnergy` computes $H = E_{mech} + E_{drive} + W_{loss} - W_{in}$. In the free swing it stays constant to $2.4\cdot10^{-4}$ of the throughput.

In closed loop, $H$ falls by the energy the three `Revolute3D` joints absorb in their compliance regularisation ($10^6$ with damping, excited by the drive's torque ripple). In the balance run that is 0.161 J of 3.5 J; the integral of the joints' port powers matches the drift to $2\cdot10^{-4}$ J. The `energy_ledger` check closes the balance over every element to $10^{-6}$.

**Checks** (`expected.json`, written by `design/actilink_finish.py`):

- no diagnostics, and the scene bindings;
- the twin samples of the free swing;
- the q current, the torque target and $u_q$ inside their limits, and the gear deflection bounded;
- the controller mode at the catch and the upright band, on the quantised encoders;
- the push deflection and the recovery;
- the energy invariant and the Tellegen ledger;
- one sanity check per identification experiment.

**Hardware notes:**

- **Cabling.** The arm stays within ±3 rad (171°) during swing-up, balance and push, so a cable loop to the AS5048 boards suffices. The friction staircase and the encoder bench turn continuously: run them with the arm cables unplugged (the links are locked anyway) or through a slip ring.
- **Calibration.** Calibrate the AS5048 zeros upright, not hanging, to remove the INL bias.
- **JD08.** It needs an external bearing for the tilting moment.
