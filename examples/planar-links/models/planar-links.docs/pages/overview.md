# Planar Links: three planar arms against a robotics toolbox

The 1-, 2- and 3-link planar robot arms of the script `reference/planar_robot.py` (closed-form inverse dynamics, checked there against Peter Corke's *Robotics Toolbox*), built here **three times, side by side, from proper planar (2D) bond-graph elements** and compared with the reference through CSV files.

![Torque of the 3-link arm: bond graph against the Robotics Toolbox|760](assets/cc1f6022f7c4.png)

## What is in the model

| arm | joints | gravity | CSV file |
| --- | --- | --- | --- |
| `A1` | 1 | none (as in the script) | `data/arm1.csv` |
| `A2` | 2 | 9.81 m/s² along $-y$ | `data/arm2.csv` |
| `A3` | 3 | 9.81 m/s² along $-y$ | `data/arm3.csv` |

Every arm is the chain *ground → joint → link frame → rigid body* per link, with the drive train of the reference at every joint: motor inertia $J_m$ and viscous friction $B$ on the motor side, an ideal gear of ratio $G$ to the joint. See [the planar bond-graph structure](page:structure).

Three models share the project:

- **`planar-links`** (this one) is the *inverse dynamics* comparison: the CSV prescribes each joint speed, the model outputs the torque the joint needs, e.g. [A3_Torque1/y](signal:A3_Torque1/y), and the error signals against the Robotics Toolbox ([A3_TauErr1/e_rtb](signal:A3_TauErr1/e_rtb)) and against the analytical model ([A3_TauErr1/e_an](signal:A3_TauErr1/e_an)).
- **`planar-links-fwd`** is the *forward dynamics* comparison: the CSV torque drives the joint and the model integrates the motion; the angle error against the CSV is the open-loop drift.
- **`planar-links-payload`** is the 3-link arm with the 1 kg payload against the 4-link Robotics Toolbox robot.

## Result in one paragraph

Over the 1 s trajectories the torque the bond-graph arms need agrees with the Robotics Toolbox and with the analytical model to **0.13 N·m or better in the first millisecond** (a one-off ring of the compliant pivots) and **1.4e-3 N·m afterwards**, on peak torques up to 131 N·m. Driven open loop by the CSV torques, the arms follow the CSV angles within **5e-6 rad** over 1 s. The analytical class and the Robotics Toolbox agree with each other to **8.5e-14 N·m**. Details and tolerances: [results](page:results).

## How it was made

1. `reference/generate.py` evaluates the user's analytical classes and the Robotics Toolbox on the trajectories of the script, sampled at 1 kHz, and writes `data/arm*.csv` ([the conventions](page:convention)).
2. `reference/build_model.py` generates the model documents and the 3D scene from the same parameters.
3. The `CsvSource` blocks ([A3_Csv](block:A3_Csv) for the 3-link arm) read the CSV files at compile time ([how](page:csv)).

## What to try

- Select [A3_Csv](block:A3_Csv) and look at the data-file section of the inspector: the file picker, the preview and the 12 columns it outputs.
- Open the **3D View**: the three arms swing from hanging ($q_1 = -\pi/2$) while the angles come from the model.
- Change `method` of a CsvSource to `linear`: the solver then stops at every data row and the torque error grows with the interpolation error of the linear speed.
