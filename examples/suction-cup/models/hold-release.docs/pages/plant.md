# Cup, tool and box

## Mechanics

The tool is a prescribed motion. [Tool](block:Tool) turns three S-curve profiles ([Lift](block:Lift), [Lower](block:Lower), [Retract](block:Retract)) and the excitation of the chosen motion into the tool pose and twist. [Grip](block:Grip), an `SfSpatial` on the 1-junction `TJ`, imposes that twist.

The cup sits between two `FixedTransform3DNeutral` mounts. [GMount](block:GMount) carries the cup frame on the tool, and [PMount](block:PMount) carries the attach point on the top of the box. The cup axis is the −z axis of the mount frame. The start state is `rz = -L0`.

[Pose](block:Pose) integrates the box pose. [Mon](block:Mon) draws the bellows and the lip in the 3D view, computes the box tilt relative to the tool ([Mon/sway](signal:Mon/sway)) and clears [Mon/held](signal:Mon/held) when the lip has moved 20 mm away from the box before the release.

## The cup and its nonlinear bellows

The cup is the linear `SuctionCup` (holding capacity $F_{cap} = A_{eff}\Delta p$, Kelvin bellows, lip friction, peeling and seal loss) with the optional nonlinear bellows terms:

| term | law | value |
| --- | --- | --- |
| bellows force | $F_s = k_{ax}\,ext + A_{fold}\,\Delta p - F_{bot} - d_{ax}\,\dot{ext}$ | $k_{ax}$ 2500 N/m, $d_{ax}$ 8 N·s/m |
| vacuum lift | $A_{fold}\,\Delta p$ pulls the folds shut | $A_{fold}$ 1.7 cm² |
| bottoming | $F_{bot} = k_{bot}\,x_b\,(x_b/x_{bot})^{n_{bot}-1}$, $x_b$ = compression beyond $s_{bot}$ | $s_{bot}$ 6 mm, $k_{bot}$ 25 kN/m, $n_{bot}$ 3, $x_{bot}$ 1 mm |
| side stiffness factor | $k_f = (1 + c_{vac}\Delta p/p_{atm})\,e^{-c_{ext}\,ext/L_0}$ on $k_{lat}$ and $k_{tilt}$ | $c_{vac}$ 1, $c_{ext}$ 3 |

`ext` is the stretch of the bellows (negative is compressed). The utilisation combines pull, peel and slip:

$$U = \frac{T + 4\lvert M_{xy}\rvert / D_{lip} + \lvert F_{lat}\rvert/\mu}{F_{cap}}$$

The other cup values are those of `fanuc-pick`: $A_{eff}$ 5 cm², $D_{lip}$ 32 mm, $k_{lat}$ 1500 N/m, $k_{tilt}$ 1 N·m/rad, μ 0.5, chamber 8 cm³. The nonlinear values are estimates for a 1.5-fold cup, not datasheet values.

The `linear-vs-nonlinear` model has a second cup (`CupL`) with $k_{bot}$, $A_{fold}$, $c_{vac}$ and $c_{ext}$ at 0. That is exactly the linear cup.

## Air

The ejector curve is $Q = Q_{max}(1 - \Delta p/\Delta p_{max})$ with 60 kPa end vacuum and 12 l/min free air. The box surface is sealed, so the only leak is past the lip. The [Valve](block:Valve) step switches the ejector off at the release, and the cup vents.

## Motion

The vacuum is on from t = 0. The lift (60 mm S-curve, 3 m/s², 60 m/s³) starts at 0.4 s, and the excitation starts at 0.937 s. After the excitation the tool lowers the box onto the table, presses 3 mm, releases and retracts 50 mm.
