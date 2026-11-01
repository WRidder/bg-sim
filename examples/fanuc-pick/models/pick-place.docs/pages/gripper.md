# Gripper, cups and vacuum

## The five zones

The gripper is estimated from the reference video. Every dimension is a global parameter.

| part | value | global |
| --- | --- | --- |
| zone layout | centre, and four at a pitch radius of 40 mm on the gripper axes | `r_p`, `lay_deg` |
| cylinder | 16 mm bore, stroke 75 mm, 120 N extend and 100 N retract force, 0.5 m/s free speed | `stroke`, `F_ext`, `F_ret`, `v_ext`, `v_ret` |
| end stops | 2e5 N/m with 300 N·s/m cushions | `k_stop`, `b_stop` |
| rod | 60 g moving mass, 5e4 N/m lateral and 200 N·m/rad bending stiffness in its guide | `m_rod`, `kt_rod`, `kr_rod` |
| cup | 1.5-fold bellows, lip 32 mm, A_eff 5 cm², L0 30 mm, axial 2500 N/m, lateral 1500 N/m, tilt 1 N·m/rad, µ 0.5 | `D_lip`, `A_eff`, `L0`, `k_ax`, `k_lat`, `k_tilt`, `mu` |
| ejector | one per zone, 60 kPa end vacuum, 12 l/min free air | `dp_max`, `Q_max` |
| carton | permeance 4e-7 m/(s·Pa) (cardboard) | `perm` |

**The cylinder** ([Cyl1](block:Cyl1), `library/PneumaticCylinder.jl`) is a force law on the rod joint's drive port. Its force is

$$F = \tfrac{1}{2}(1+u)F_{ext} - \tfrac{1}{2}(1-u)F_{ret} - b(u)\,v, \qquad b(u) = \tfrac{1}{2}(1+u)\frac{F_{ext}}{v_{ext}} + \tfrac{1}{2}(1-u)\frac{F_{ret}}{v_{ret}}.$$

The meter-out flow control acts as a damper that sets the free speed. A rod at its end stop presses with the full force. The port is power-in, so the rod speed is $v = -f$.

**Why one ejector per zone.** A zone whose cup leaks or peels does not pull down the vacuum of the others. With a common ejector, the leak of the worst cup loads all of them. The zones can also be switched off one by one (`zone1`..`zone5`), so a smaller parcel uses only the cups that land on it.

## Vacuum

The chamber of each cup is isothermal, with free-air flows. The vacuum level is $\Delta p$.

$$\dot p = \frac{p_{atm}}{V}\left(Q_{leak} + Q_{por} - Q_{gen}\right), \qquad Q_{gen} = Q_{max}\left(1 - \frac{\Delta p}{\Delta p_{max}}\right),$$

The steady state is the operating vacuum. There the ejector curve meets the lip leak plus the Darcy flow through the cardboard: **55.83 kPa** (`reference.py`; the simulation reads 55.83 kPa). From the lip contact the vacuum rises with a time constant of about 24 ms. In the default run it is at 55.76 kPa at the lift.

## The holding margin

`SuctionCup` reports the utilisation of each cup:

$$U = \frac{T + 4 M_{tilt}/D_{lip} + F_{lat}/\mu}{A_{eff}\,\Delta p}.$$

$T$ is the axial pull, $M_{tilt}$ the bending moment carried by the bellows and $F_{lat}$ the shear. At $U = 1$ the lip pulls off, peels or slips. [Monitor](block:Monitor) samples every cup each millisecond while the carton is carried. It keeps the peak $U_k$ of every active zone and the margin $1 - U_k$, with `M_tot` the smallest. The requirement `M_req` is 0.5, a safety factor of 2 (0.3 for the loose contents). A drop is the carton centre moving more than `d_drop` = 20 mm from where it sat in the gripper at the lift. It latches `held_ok` to 0.
