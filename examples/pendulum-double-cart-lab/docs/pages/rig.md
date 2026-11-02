# The double-cart lab rig

A cart on a **±1.0 m** rail carries a double pendulum of two **0.35 m** links, built the way a lab would build
them: aluminium tubes with clamp hubs, a bearing head at the tip of link 1, 14-bit encoders and a cable. The
cart runs on a toothed belt from a 24 V DC motor through a 3:1 gearbox and a 16 mm pulley, with a
voltage-mode drive and a 1 kHz firmware. The motor, gearbox, belt and cart are those of example
`pendulum-double-cart`. The rig is the shared platform of the robust classical work
(`plan/ROBUST_CLASSICAL_PLAN.md`) and the RL work (`plan/RL_PLAN.md`). Every value comes from
`design/realism.json`, which also holds the ranges the robustness studies draw from.

![The rig: cart, rail with end stops, the two links, belt drive and motor|760](assets/99a4a593e23d.svg)

| part | nominal (realism.json) |
| --- | --- |
| cart | 0.80 kg carriage (belt clamp, joint-1 bearing block, encoder board), carriage friction 0.5 + 0.2 N s/m |
| rail | ±1.0 m to rubber end stops (2·10⁴ N/m, 200 N s/m) |
| link 1 | 0.35 m: tube 107 g, hub, magnet, head 105 g, encoder board, cable: **0.248 kg**, COM 0.229 m (65 % of L), $J = 4.68 \cdot 10^{-3}$ kg m² |
| link 2 | 0.35 m: tube 107 g, hub 45 g, magnet, tip cap 47 g: **0.200 kg**, COM 0.176 m, $J = 3.96 \cdot 10^{-3}$ kg m² |
| motor and drive | 24 V, $R = 1.5\ \Omega$, $L = 0.5$ mH, $k_t = 0.0302$ N m/A; 3:1, 16 mm pulley, belt $4 \cdot 10^5$ N/m: 3.78 N/V, stall 90 N (16 A), effective cart 1.29 kg |
| sensors and loop | 14-bit joint encoders (0.03° rms noise), 1000-line motor encoder (8.4 µm at the cart), 1 kHz loop with a 2 ms delay |
| upright | unstable poles **4.55 and 8.92 /s**; hanging to upright takes **3.18 J** |

The bond graph is the planar multibond model of `pendulum-double-cart` (`Prismatic2D` rail, two
`Revolute2DCompliant` joints, `RigidBody2D` cart and links, `ElectricDrive` → `Gearbox` → `RackAndPinion` →
belt `SpringDamper`, `ExternalWrenchPlanar` tip push), plus the carriage friction `RailFriction` and the
`EndStops` at ±1.0 m. `design/lablib.py` builds the design model, the bond graph, the Python twin and the
firmware replica for any parameter set.

![3D view: the cart on the 2 m rail between the red rubber stops; the green posts mark the ±0.8 m swing-up plan|500](assets/1a846c8ae419.png)

## The models

Every model has a **Dashboard** with the same layout (readouts, the link angles in degrees, the cart with the
end stops, voltage and current, the controller's phase, sliders for the next run) and its own docs page.

| model | what it shows |
| --- | --- |
| [pendulum-double-cart-lab](model:pendulum-double-cart-lab) | the nominal firmware: hanging until 1 s, the planned swing-up, the LQR catch at 4.0 s, a 0.45 N push at 7.5 s |
| [-balance](model:pendulum-double-cart-lab-balance) | balance only: a 2° lean and a large 0.70 N push at 2 s |
| [-free](model:pendulum-double-cart-lab-free) | no control: the free swing, checked against the twin |
| [-plant](model:pendulum-double-cart-lab-plant) | the plant alone (voltage and push in, encoders out): the source of the FMU for RL |
| [-rl](model:pendulum-double-cart-lab-rl) | a learned controller (R0.7) on the ideal plant, the nominal scenario |
| [-rl-robust](model:pendulum-double-cart-lab-rl-robust) | the robust learned controller (R1) on the realistic plant with noise and delay |
| [-robust](model:pendulum-double-cart-lab-robust) | the robust classical firmware (C1 balance, C2 swing-up) in the nominal scenario |
| [-recover](model:pendulum-double-cart-lab-recover) | the state-driven firmware (C3): a knock-down at 7 s, the re-armed swing-up and the re-catch |

Read on: [design and margins](page:design), [realism and the robustness test](page:realism),
[robust classical control](page:robust), [learned controllers](page:learned) and
[the comparison](page:comparison). The example's `README.md` has every command and table.
