# Hardware and the choice of size

`design/actilink_hardware.json` holds every number together with its source:

- the Synapticon datasheet and product PDF (S1, S3);
- the Circulo brochure (S4);
- the firmware and EtherCAT docs (S6, S7);
- the ams AS5048 datasheet (A1).

Numbers the datasheets do not give are marked `est`. The identification experiments measure them.

| | JD08 | **JD10** | JD12 |
| --- | --- | --- | --- |
| ratio, rated / peak torque | 7.75, 7 / 17 N·m | **9, 21 / 68 N·m** | 9, 29 / 102 N·m |
| no-load speed, backlash | 400 rpm, < 22′ | **210 rpm, < 13′** | 200 rpm, < 11′ |
| rotor inertia at the output | 0.0042 kg·m² | **0.020 kg·m²** | 0.040 kg·m² |
| motor: pole pairs, k_t, R, L | 14, 0.156 N·m/A, 0.27 Ω, 167 µH | **20, 0.242 N·m/A, 0.195 Ω, 110 µH** | 21, 0.234 N·m/A, 0.085 Ω, 90 µH |
| drive | Circulo 7 (8 / 24 A_rms) | **Circulo 9 (20 / 60 A_rms)** | Circulo 9 |
| permissible bearing tilting moment | K × 3.2 N·m | **K × 24.5 N·m** | K × 30.6 N·m |
| gear stiffness (est) | 1500 / 4000 N·m/rad | **3500 / 9000 N·m/rad** | 5000 / 13000 N·m/rad |

**Estimates (est):** the gear stiffness below and above the knee, and the friction in the gear and the bearing. The friction is Coulomb, breakaway and viscous; for the JD10 it is 0.20 / 0.30 N·m with 0.01 N·m·s/rad, plus 0.06 N·m in the output bearing. The rig itself is also estimated: aluminium tubes, bearing blocks and the masses of the AS5048 boards.

## Sizing

`actilink_design.py` optimises the swing-up for each size: collocation over 3 s, 6 N·m bound, arm within ±3 rad. Along the trajectory it computes the moment that tilts the output bearing, the horizontal part of $\dot L - \sum r \times m g$ about the flange.

| | JD08 | **JD10** | JD12 |
| --- | --- | --- | --- |
| swing-up peak torque | 2.77 N·m | **2.38 N·m** | 2.63 N·m |
| bearing tilting moment, peak | 35.0 N·m | **32.6 N·m** | 24.9 N·m |
| permissible, static K | **7.1 N·m (exceeded)** | 47.0 N·m | 52.6 N·m |
| LQR phase margin, delay margin | 73°, 18.3 ms | **70°, 22.5 ms** | 68°, 26.4 ms |
| rotor share of the axis inertia | 5 % | **20 %** | 33 % |

**Torque does not decide the size.** All three sizes swing the pendulum up with less than 3 N·m.

**The output bearing does.** The links swing 0.3 m from the axis, and their centrifugal and inertial loads tilt the flange with more than 30 N·m. That is five times what the JD08 bearing permits, so the JD08 would need an external support bearing.

**JD10:**
- carries the tilting moment within its static rating;
- has 13′ backlash instead of the JD08's 22′;
- costs 20 % extra axis inertia.

The **JD12** adds mass and rotor inertia without a gain.
