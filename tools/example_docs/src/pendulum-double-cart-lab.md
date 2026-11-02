@@ figures pendulum-double-cart-lab
{
  "diagram": {"kind": "diagram", "model": "pendulum-double-cart-lab"},
  "scene": {"kind": "scene", "model": "pendulum-double-cart-lab", "t": 12.5},
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab", "xlim": [0, 12.5],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Ctrl/th1", "label": "θ1", "scale": 57.29577951308232}, {"signal": "Ctrl/th2", "label": "θ2", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "hlines": [{"y": 0.8, "label": "plan ±0.8 m"}, {"y": -0.8}], "ylim": [-1.05, 1.05], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "hlines": [{"y": 16.8, "label": "plan ±16.8 V (70 %)"}, {"y": -16.8}], "ylim": [-25, 25], "legend": true, "legend_loc": "right"},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "i"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "phase", "series": [{"signal": "Ctrl/phase", "label": "0 hold, 1 swing-up, 2 balance"}], "legend": true, "legend_loc": "right"}
    ]
  },
  "swingup": {
    "kind": "plot", "model": "pendulum-double-cart-lab", "xlim": [0.8, 4.6],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Ctrl/th1", "label": "θ1", "scale": 57.29577951308232}, {"signal": "Ctrl/th2", "label": "θ2", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}, {"signal": "Traj/xs[1]", "label": "planned x", "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "applied"}, {"signal": "Traj/ff", "label": "feed-forward", "style": "--"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab overview - | Overview
# The double-cart lab rig: swing-up, balance and a push

A cart on a ±1.0 m rail with soft end stops carries a double pendulum of two **0.35 m** links. The motor, the
3:1 gearbox, the 16 mm belt pulley, the belt and the cart carriage are those of `pendulum-double-cart`; the
links are built the way a lab would build them: aluminium tubes 20 × 2 mm with a clamp hub at the pivot, on
link 1 a bearing head at the tip (the joint-2 bearings and encoder board), the encoder magnets and the
joint-2 cable. This example is the shared platform of the RL work and the robust classical work
(`plan/RL_PLAN.md`, `plan/ROBUST_CLASSICAL_PLAN.md`): every value comes from `design/realism.json`, which
also holds the ranges the robustness studies randomise over.

- The plant is the planar multibond bond graph of `pendulum-double-cart` ([Rail](block:Rail),
  [Joint1](block:Joint1), [Joint2](block:Joint2), [Body1](block:Body1), [Body2](block:Body2), the
  [Motor](block:Motor), [Gear](block:Gear), [Pulley](block:Pulley) and [Belt](block:Belt)), plus the
  carriage friction [RailFriction](block:RailFriction) and the rubber [EndStops](block:EndStops) at ±1.0 m.
- [Ctrl](block:Ctrl) (`DoubleCartLabCtrl`) is the 1 kHz firmware: 0 V until 1 s, the swing-up (feed-forward
  plus time-varying LQR from the tables of [Traj](block:Traj)), the discrete LQR from 4.0 s, and a 0.45 N,
  40 ms tip push ([PushPulse](block:PushPulse)) at 7.5 s.

![The model canvas|900](@fig:diagram)

![3D view at the end of the run: balanced upright, the green posts mark the ±0.8 m plan|500](@fig:scene)

![Link angles, cart, voltage, current and phase over the run|900](@fig:run)

Continue with [the rig](page:rig), [the design](page:design), [the realism screen](page:realism) and
[the results](page:results).
@@ page pendulum-double-cart-lab rig overview | The rig
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
@@ page pendulum-double-cart-lab design overview | Design and margins
# Design and margins

`design/design.py` reuses the design code of `pendulum-double-cart` (`cartpend.py`: the Lagrangian design
model, Hermite-Simpson collocation with IPOPT, the continuous TVLQR, the discrete LQR; `cartmodel.py`: the
bond graph). The design model and the Python twin are the same equations (checked to 1e-15).

1. **Swing-up plan with margins.** Hanging to upright at rest in $T_s = 3.0$ s (75 intervals), minimum
   $\int V^2 dt$, with the voltage bounded to **16.8 V (70 % of 24 V)** and the cart to **±0.8 m**. The plan
   needs 14.8 V (62 %) and ±0.39 m: neither bound is active, a shorter 2.4 s plan would hit both.
2. **TVLQR** along the plan and the **discrete LQR** (1 ms, ZOH) at the upright with
   $Q = \mathrm{diag}(300, 400, 400, 10, 8, 8)$, $R = 0.3\ \mathrm{V}^{-2}$; largest gain 329.
3. **Catch** at $\tau = T_s$ (4.0 s), time-based as in `pendulum-double-cart`.

![Swing-up: the bond graph against the plan|900](@fig:swingup)

**Robustness** (firmware replica on the twin; every case caught, balanced and recovered from the push):

| case | swing-up: peak V, peak x | balance push (0.70 N): peak deflection |
| --- | --- | --- |
| nominal | 15.0 V, 0.387 m | 17.3° |
| link masses −5 % / +5 % | 14.9 / 15.1 V | 18.4° / 16.4° |
| link lengths +1 % / −1 % | 14.8 / 15.3 V | 17.1° / 17.5° |
| joint friction ×3 | 15.8 V | 17.6° |
| carriage friction ×3 | 15.3 V | 17.3° |
| cart mass +10 % | 15.1 V | 17.6° |
| delay 1 ms / 2 ms | 15.0 / 15.0 V | 17.5° / 17.6° |
| quantised encoders (14 bit, 8.4 µm) / with 2 ms delay | 18.5 / 17.4 V | 17.5° / 17.8° |
| all of the above at once (+5 %, +1 %, ×3, 2 ms, quantised) | 16.6 V, 0.385 m | 16.9° |

The largest 40 ms tip push the balance recovers from upright is **0.90 N** (0.87 N with 2 ms delay; the
voltage saturates briefly, the cart travels 0.34 m). The belt mode (177 Hz, 124 Hz with the softest belt)
stays damped in closed loop with 0 to 2 ms of delay.
@@ page pendulum-double-cart-lab realism overview | Realism screen
# Realism screen

`design/realism.json` holds every parameter of the rig with nominal, min, max, unit and a description:
the link parts, lengths and centres of mass, viscous and Coulomb friction of both joints, the carriage and
the motor, the cable springs and drag, the motor and belt constants, the encoder resolution and noise, the
loop delay, the armature current lag and the commutation ripple and cogging. `lablib.setup` builds the truth
twin and the firmware replica for any parameter set (the counterpart of the quad pendulum's
`quadlib.realistic_setup`, reusing its EKF, firmware replica and closed loop). `design/screen.py` runs the
classical controller against it; the summary is `design/screen_results.json`.

The truth is the twin with every effect (RK4, 8 substeps per 1 ms sample), the firmware has the design's
tables and gains unchanged. Scenarios: the swing-up and the balance from a 2° lean with the 0.45 N push;
"ok" means off the end stops and every link within 2° of upright over the last 2 s. Rates come from
filtered differences (`diff`, the baseline) or an EKF on the nominal twin.

| study (all effects nominal unless noted) | filtered differences (`diff`, τ_f 2 ms) | EKF (q_acc (1, 10)) |
| --- | --- | --- |
| all effects together, tail deviation swing-up / balance | ok **0.61° / 0.37°**, but 9 V rms chatter, 24 V peaks, 17 A | ok **0.13° / 0.21°**, 15.1 / 16.3 V, 5.8 / 8.9 A |
| the effect that matters | the joint encoders (noise alone: 0.5°, 24 V, 20 A) | joint and carriage friction (≈0.1° each) |
| mass spread, drive, cable, loop delay, ripple and cogging | negligible | negligible |
| joint-2 Coulomb friction (nominal 2e-4 N m) | 1e-3 ok 0.69°, 2e-3 ok 0.87°, 5e-3 fails (3.6°) | 1e-3 ok 0.41°, 2e-3 marginal 1.7°, 5e-3 fails (3.9°) |
| joint-1 Coulomb friction | 5e-3 ok 0.93°, 1e-2 ok 1.5°, 2e-2 fails (3.3°) | 5e-3 ok 0.87°, 1e-2 ok 1.8°, 2e-2 fails (3.6°) |
| both joints | 1e-3 ok 0.73°, 2e-3 ok 1.5°, 5e-3 fails | 1e-3 ok 0.86°, 2e-3 marginal 1.9°, 5e-3 fails |
| encoders 12 bit 0.08° / 14 bit 0.08° / 16 bit 0.005° / 18 bit | **fail** / **fail** / ok 0.13° (15.7 V) / ok | ok 0.34° / ok 0.41° / ok 0.14° / ok |
| rate filter τ_f 1 / 5 / 10 ms | 1.4° (24 V) / 0.22° (22 V) / 0.21° (21 V) | — |
| EKF process noise (0.3, 3) … (10, 100) | — | all ok 0.13–0.21°; (10, 100) raises u to 20 V |
| cart Coulomb compensation 0 / 0.5 / 1 | 0.63° / 0.55° / 0.61° | 0.44° / 0.14° / 0.13° (carriage at 2 N: 0.44° / 0.19° / 0.15°) |
| **Monte Carlo, 48 draws over every range** | **36/48** (failures: 2.0–3.7° limit cycles, all with joint noise ≥ 0.055° rms; 24 V, 21 A) | **48/48 swing-up and 48/48 balance**: tail median 0.22°, max 0.41° / 0.48°; worst 18.2 V, 8.5 A, 0.39 m |

**Verdict: feasible with margin.** The unchanged classical controller passes every effect at its nominal
value and all 48 Monte Carlo draws over the ranges of `realism.json`, provided the rates come from an
**EKF** on the nominal model (or the joint encoders are 16-bit class). Filtered differences with the
AS5048-class 14-bit encoders are only marginal (the voltage chatters to the 24 V limit, a quarter of the
draws limit-cycle at 2–4°). The **joint Coulomb friction budget** is about **1e-3 N m on joint 2** and
**5e-3 N m on joint 1**, 5–25× the assumed 2e-4 N m of small ball bearings, so the 0.35 m links take
ordinary bearings (the cart quad needs 5e-5 N m). The cart Coulomb compensation helps (0.44° → 0.13°) but is
not required. The recommendations (EKF tuning, encoder grade, bearing budget) are in `design/screen_results.json`.
@@ page pendulum-double-cart-lab results overview | Results and checks
# Results and checks

The real worker runs the three models (Rodas5P, reltol 1e-8; `design/measured.json`):

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| free swing 2 s against the design ODE (angles / cart) | **4.3e-4 rad** / 4.3e-5 m | — |
| swing-up time / catch | 2.55 s after the start / 4.00 s | 2.55 s / 4.00 s |
| swing-up against the design closed loop (angles / cart) | 1.5e-3 rad / 0.3 mm | |
| upright band before the push | 0.0023° (cart 0.04 mm) | 0.0017° |
| push 0.45 N: link 1 / link 2; back inside 0.5° | 10.71° / 3.98°; 2.12 s | 10.70° / 3.98°; 2.12 s |
| peak voltage, current, travel | **15.01 V** of 24 V, 5.97 A, **0.387 m** of ±0.8 m | 15.02 V, 5.98 A, 0.387 m |
| balance model: push 0.70 N, link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| balance model: peak voltage, current, travel; recovery | 20.7 V, 11.0 A, 0.241 m; 2.29 s | 20.6 V, 11.0 A, 0.242 m; 2.29 s |
| run time (swing-up 12.5 s / balance 6 s / free 2 s) | 56 s / 11 s / 4 s | |

`expected.json` (written by `design/finish.py`) checks: the rest before 1 s, the phases, the link angles
during the swing-up against the design closed loop, the upright band, the push deflection and the recovery,
**the swing-up within the planned 16.8 V and the cart within the planned ±0.8 m**, the peak voltage, current
and travel, the scene bindings and no diagnostics; the balance model's catch, push and recovery; the free
model's cart and joint angles against the twin every 0.25 s. Run them with
`uv run examples/run_checks.py --only pendulum-double-cart-lab`.
@@ figures pendulum-double-cart-lab-balance
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-balance", "xlim": [0, 6],
    "rows": [
      {"ylabel": "angle from upright [deg]", "series": [{"signal": "Ctrl/th1", "label": "θ1", "scale": 57.29577951308232}, {"signal": "Ctrl/th2", "label": "θ2", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "voltage [V]", "series": [{"signal": "Ctrl/u", "label": "u"}], "hlines": [{"y": 24, "label": "supply ±24 V"}, {"y": -24}], "legend": true, "legend_loc": "right"},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "i"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-balance overview - | Overview
# The double-cart lab rig: balance and a large push

The model `pendulum-double-cart-lab` with the firmware in the balance phase from the start
([Ctrl](block:Ctrl) `t_on` = −10 s). Both links start leaning 2°, the discrete LQR catches them, and at 2 s
a **0.70 N**, 40 ms push on the tip ([PushPulse](block:PushPulse)) tests the recovery: 78 % of the largest
push the design recovers (0.90 N).

![Link angles, cart, voltage and current|900](@fig:run)

| quantity | bond graph | design closed loop |
| --- | --- | --- |
| the 2° lean, inside 0.5° before the push | 0.28° | |
| peak deflection link 1 / link 2 | 17.35° / 5.79° | 17.32° / 5.80° |
| back inside 0.5° after the push | 2.29 s | 2.29 s |
| peak voltage, current, travel | 20.7 V, 11.0 A, 0.241 m | 20.6 V, 11.0 A, 0.242 m |
| at the end (6 s) | 0.10°, cart 2 mm | |

The voltage stays below the 24 V supply and the cart well inside the ±0.8 m plan. Raise the
[PushPulse](block:PushPulse) amplitude to find the limit: the design's largest recoverable push is 0.90 N
(0.87 N with 2 ms delay), where the voltage saturates briefly and the cart travels 0.34 m.
@@ figures pendulum-double-cart-lab-free
{
  "run": {
    "kind": "plot", "model": "pendulum-double-cart-lab-free", "xlim": [0, 2],
    "rows": [
      {"ylabel": "joint angle [rad]", "series": [{"signal": "Joint1/qout", "label": "q1"}, {"signal": "Joint2/qout", "label": "q2"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "cart x [m]", "series": [{"signal": "Rail/qout", "label": "x"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page pendulum-double-cart-lab-free overview - | Overview
# The double-cart lab rig: free swing, the twin check

No control: the motor is shorted (the firmware never starts), the plant is released from rest at
θ = (−2.2, −1.2) rad, x = 0.05 m and swings for 2 s. `expected.json` compares the cart position and the joint
angles every 0.25 s with the design ODE, which is the Python twin of `design/lablib.py`.

The bond graph agrees with the twin to **4.3e-4 rad** on the joints and **4.3e-5 m** on the cart over the
2 s, so the design model, the twin of the realism screen and the bond graph are the same plant. The swing
includes the viscous joint, cable and carriage drag and the belt; the motor is shorted, so the back-EMF
drags the cart (β = 22.1 N s/m).

![Joint angles and cart|900](@fig:run)

![Free swing: joint angles and cart|900](@fig:run)
