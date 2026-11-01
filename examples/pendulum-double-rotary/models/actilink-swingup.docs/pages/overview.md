# ACTILINK-JD10 rotary double pendulum

This is the rotary double pendulum of this project built from purchasable hardware:

- A **Synapticon ACTILINK-JD10** stands on the vertical axis and turns a **0.3 m arm**.
- A passive joint at the arm tip carries **link 1 (0.6 m)**, and **link 2 (0.6 m)** hangs from the tip of link 1.
- Each passive joint has an **ams AS5048** 14-bit magnetic encoder: A over SPI, or B over I2C.
- A **1 kHz EtherCAT master** reads the drive's 20-bit output encoder and the two AS5048, estimates the states, swings the pendulum up and balances it. The drive runs CST (cyclic synchronous torque).

The scenario of this model (8 s):

1. 0 to 1 s: hanging at rest, drive enabled with zero torque.
2. 1 to 4 s: swing-up along a collocation trajectory, tracked by a time-varying LQR.
3. Catch: the 1 kHz firmware latches the balance LQR.
4. Balance until the end.

![The model canvas|900](assets/47e58866ac8d.png)

Every block is either datasheet hardware or an explicit estimate. [Hardware and size](page:hardware) lists the numbers and explains why the JD10 was chosen over the JD08 and the JD12.

The other models of the project are:

| model | |
| --- | --- |
| `actilink-balance` | balance from a disturbed upright |
| `actilink-push` | a push on the link-2 tip while balancing |
| `actilink-free` | the zero-torque free swing, compared with the Python twin |
| `actilink-sysid-*` | seven identification experiments, see [System identification](page:sysid) |

## Dashboard

- **Readouts:** the controller mode and a balancing lamp; the deviation from upright; the q current as a gauge against the drive's 44 A peak; and the gear deflection.
- **Controls:**
  - the **A/B toggle** (AS5048B over I2C with 0.44 ms latency, instead of AS5048A over SPI with 0.19 ms);
  - a slider for the **AS5048 read interval** in EtherCAT cycles (a slower bus);
  - a slider for the **gear backlash**.
- **Plots:**
  - the link angles and the arm;
  - the torque target and the drive reference;
  - the current;
  - link 1 as true, quantised and estimated angle;
  - the gear deflection;
  - the energy.

## 3D view

The actuator is a Ø106 × 86 mm cylinder on a column, with an orange output flange. On top sit the clamp hub, the 30 × 30 mm arm tube and the joint-1 bearing block with its AS5048 board. The two link tubes and the joint-2 housing follow; link 2 runs 40 mm beside link 1.

![3D view at t = 7.5 s, balancing|500](assets/e67bd1355cd4.png)

Continue with [Hardware and size](page:hardware), [Model](page:model), [Control](page:control), [System identification](page:sysid) and [Results](page:results).
