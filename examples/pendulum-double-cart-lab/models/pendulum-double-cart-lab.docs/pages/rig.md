# The rig

All values are the nominal column of `design/realism.json` (min and max there are the ranges of a built rig).

| part | value |
| --- | --- |
| cart | 0.80 kg carriage with the belt clamp, the joint-1 bearing block and encoder board; rail ±1.0 m to the end stops (2·10⁴ N/m, 200 N s/m) |
| link 1 | 0.35 m: tube 107 g, hub 30 g at the pivot, magnet 1 g, head 105 g and encoder board 3 g at the tip, cable 2 g; **0.248 kg**, centre of mass 0.229 m, $J = 4.68 \cdot 10^{-3}$ kg m² |
| link 2 | 0.35 m: tube 107 g, hub 45 g and magnet 1 g at the pivot, tip cap 47 g; **0.200 kg**, centre of mass 0.176 m, $J = 3.96 \cdot 10^{-3}$ kg m² |
| joints | viscous 2·10⁻⁴ N m s/rad each (plus the cable drag on joint 1); Coulomb 2·10⁻⁴ N m in the realism set only |
| motor | 24 V, $R = 1.5\ \Omega$, $L = 0.5$ mH, $k_t = k_e = 0.0302$ N m/A, rotor $1.4 \cdot 10^{-5}$ kg m² |
| transmission | 3:1, pulley radius 16 mm, belt $4 \cdot 10^5$ N/m, 60 N s/m: 3.78 N/V, rotor reflected 0.49 kg, effective cart 1.29 kg |
| carriage | 0.5 N s/m guide plus 0.2 N s/m cable chain (bond graph: [RailFriction](block:RailFriction)) |

**Centres of mass and inertias.** `design/lablib.py` (`link_props`) lumps the parts of each link: the tube
as a thin-walled cylinder ($J = m (L^2/12 + (r_o^2 + r_i^2)/4)$ about its centre), the hubs, the head and the
tip cap as small cubes, the magnet and board as point masses, the cable as a uniform rod, combined with the
parallel-axis theorem. The heavy head puts link 1's centre of mass at 65 % of its length.

**Linearised poles.** The upright has two unstable poles, **4.55 and 8.92 /s** (uniform 0.25/0.25 kg rods
on the same cart would give 4.66 and 12.3 /s: the head and the tip cap slow link 2 down). Swinging up from
hanging to upright raises the potential energy by **3.18 J**; the design closed loop draws 10.8 J from the
supply for it, 6.8 J of which is copper loss, with a peak mechanical power of 38 W.
