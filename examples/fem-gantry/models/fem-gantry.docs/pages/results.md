# Results and checks

## The plain move

![The default run: axes, motor forces, the beam's peak stress and the racking|900](assets/0cfb278bf4a4.png)

![Just after the move out (x100): the beam and the carriage still ring|900](assets/fafeb698aee4.png)

| plain move, 0.5 m at 10 m/s² | BGSim | scipy modal model |
| --- | --- | --- |
| settling into ±10 µm | 35.5 ms | 31.5 ms |
| residual after the move | 127.1 µm | 121.3 µm |
| peak tool error | 253.0 µm | 247.8 µm |
| racking | 42.8 µm | 42.2 µm |
| motor peaks X1 / X2 | 243 / 168 N | 237 / 167 N |
| peak von Mises over the beam | 2.37 MPa | 2.55 MPa |

The scipy model (`design/reference.py`) is an independent linear model of the two servos, the X1 carriage's yaw, the beam's modal coordinates and the Y carriage, built from the reduced-model file alone, with rigid joints. Its closed-loop poles (46.8 Hz ζ 0.47, 62.2 Hz ζ 0.45, 95.4 Hz ζ 0.10, 192.4 Hz ζ 0.008) agree with BGSim's linearisation within 2 % when BGSim's joints are made rigid; the real guides lower the last two to 84 and 167 Hz.

## Shaping

![The plain move into its end position: 47 Hz ringing|900](assets/5db27f0eae59.png)

![The ZVD-shaped move: the 47 Hz ringing is gone, the 167 Hz carriage rocking remains|900](assets/f91a5f8e37d4.png)

| move | settling | residual | peak | racking | peak stress |
| --- | --- | --- | --- | --- | --- |
| plain | 35.5 ms | 127 µm | 253 µm | 43 µm | 2.37 MPa |
| ZVD at 46.8 Hz | 11.6 ms | 17.6 µm | 179 µm | 30 µm | 1.68 MPa |
| notch at 167 Hz | 44.1 ms | 134 µm | 267 µm | 45 µm | 2.49 MPa |

## Statics

`gantry-static` checks the beam alone, clamped at both ends, against beam theory: the deflection within 5 %, the hotspots 100 mm from A within 2 %. See that model's docs.

## Checks

`expected.json` runs the plain move and four scenarios (ZVD, notch, X2 10 % weak, carriage at 0.15 m) against the scipy model: the axes' end positions, the peak tool error, the racking, the motor forces, the stresses at the hotspots, the residual and the settling time; the ZVD move against bounds (residual below 25 µm, settling below 15 ms). The static model is checked against beam theory, with and without the carriage.
