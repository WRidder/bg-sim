# Block in the gripper: the tilting moment

The same gripper and move as `ball-gripper`, with a **40 × 40 × 80 mm aluminium block** (0.346 kg) gripped 28 mm above its centre of mass. Each flat pad touches the block at four points at ±6 mm ([JawA1](block:JawA1) … [JawB4](block:JawB4), point `MovingPlaneContact`s summed by [PadA](block:PadA) and [PadB](block:PadB)); four more points carry it on the table. The block is gripped at 1 mm/s (its stiff point contacts would lock in a much larger closing force than the soft ball contact).

![The block in the transfer (1.1 s)|600](assets/1197fc500d33.png)

## Sizing with the moment

The transfer acceleration acts at the centre of mass, $e = 28$ mm below the grip line, and turns the block about the jaw axis with $M = m\,a_h\,e = 0.194$ N·m. The four points of each pad carry it by friction at the torsion lever $r = \sqrt2\cdot 6$ mm $= 8.5$ mm. Adding force and moment for the worst point gives the sizing rule

$$F \;\ge\; S\,\frac{m|a - g| + M/r}{2\mu}:\qquad 15.40\ \mathrm{N\ (force\ only)} \;\to\; 61.01\ \mathrm{N\ with\ the\ moment},\ S = 2:\ 123\ \mathrm{N}\ (2.33\ \mathrm{A}).$$

A pad that slides as a whole has a limit surface closer to $\sqrt{F_t^2 + (M/r)^2} \le 2\mu F$, 48.1 N: less conservative, still three times the force-only value. [Grip](block:Grip) adds the moment term with `kM` $= e/r$, and reports the tilt [Grip/tilt](signal:Grip/tilt).

![Sized with the moment: holds, tilts 0.26 deg|900](assets/e96eed571ae4.png)

## Sized for the force only

With the force-only setting (31 N, $S = 2$) the drive holds 36.9 N, below even the limit-surface estimate. In the transfer the block swings by 26° in the grip ([Grip/holds](signal:Grip/holds) drops at 0.976 s). The pad utilisation of the resultant force (`util_res`) stays low: it is the torsion that saturates the points (`util`).

![Sized for the force only: the block tilts in the transfer|900](assets/3865eb0382d3.png)
