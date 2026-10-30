"""Write the model docs (W5.6 format) of `pendulum-triple-rotary` from its runs (X5.13).

Adapted from `examples/pendulum-double-rotary/design/rotary_docs.py` (same plots; the pages describe
the triple's drive, its collocation and the discrete TVLQR).

Plots are made with matplotlib from the saved bond-graph runs in `design/_runs/`; every asset is
named by the first 12 hex digits of its SHA-256. Run through `finish.py --docs`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import runner
import triple_build as tb
import triple_lib as tl

COLORS = ["#2a7de1", "#d9534f", "#e6a817", "#3a9d5d"]


def _save(fig, docs: Path, store: dict[str, str], key: str) -> str:
    tmp = docs / "assets" / f"{key}.tmp.png"
    fig.savefig(tmp, dpi=110, bbox_inches="tight")
    plt.close(fig)
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]
    final = docs / "assets" / f"{digest}.png"
    tmp.replace(final)
    store[key] = f"assets/{digest}.png"
    return store[key]


def plots(dz: dict, plant: tl.Plant, example_dir: Path, docs: Path) -> dict[str, str]:
    n = plant.n_links
    name = dz["example"]
    runs = example_dir / "design" / "_runs"
    t, s = runner.load(runs / f"{name}.npz")
    tf, sf = runner.load(runs / f"{name}-free.npz")
    t_on, t_s, t_dist = dz["t_on"], dz["t_s"], dz["t_dist"]
    out: dict[str, str] = {}
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    phi = [np.degrees(s[f"Angles/phi{k + 1}"]) for k in range(n)]

    fig, ax = plt.subplots(4, 1, sharex=True, figsize=(9, 8))
    for k in range(n):
        ax[0].plot(t, phi[k], color=COLORS[k], label=f"link {k + 1}")
    ax[0].set_ylabel("link angle from upright [deg]")
    ax[0].legend(loc="upper right", ncol=n)
    ax[1].plot(t, np.degrees(s["J1/qout"]), color=COLORS[0])
    ax[1].set_ylabel("arm angle [deg]")
    ax[2].plot(t, s["Ctrl/u"], color=COLORS[1])
    ax[2].axhline(dz["vmax"], color="k", lw=0.6, ls="--")
    ax[2].axhline(-dz["vmax"], color="k", lw=0.6, ls="--")
    ax[2].set_ylabel("motor voltage [V]")
    ax[3].plot(t, s["Ctrl/phase"], color=COLORS[3], drawstyle="steps-post")
    ax[3].set_ylabel("phase (0 idle, 1 swing-up, 2 LQR)")
    ax[3].set_xlabel("t [s]")
    for a in ax:
        a.grid(alpha=0.3)
        a.axvline(t_on, color="gray", lw=0.6)
        a.axvline(t_on + t_s, color="gray", lw=0.6)
        a.axvline(t_dist, color="gray", lw=0.6)
    fig.suptitle(f"{name}: the whole run (bond graph)")
    _save(fig, docs, out, "full")

    fig, ax = plt.subplots(3, 1, sharex=True, figsize=(9, 6.5))
    m = (t >= t_on - 0.2) & (t <= t_on + t_s + 1.5)
    for k in range(n):
        ax[0].plot(t[m], phi[k][m], color=COLORS[k], label=f"link {k + 1}")
    ax[0].legend(ncol=n)
    ax[0].set_ylabel("link angle [deg]")
    ax[1].plot(t[m], s["Ctrl/u"][m], color=COLORS[1])
    ax[1].set_ylabel("voltage [V]")
    ax[2].plot(t[m], np.degrees(s["J1/qout"][m]), color=COLORS[0])
    ax[2].set_ylabel("arm [deg]")
    ax[2].set_xlabel("t [s]")
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("Swing-up (TVLQR along the optimised trajectory) and catch")
    _save(fig, docs, out, "swingup")

    fig, ax = plt.subplots(3, 1, sharex=True, figsize=(9, 6.5))
    m = (t >= t_dist - 0.5) & (t <= t_dist + 3.5)
    for k in range(n):
        ax[0].plot(t[m], phi[k][m], color=COLORS[k], label=f"link {k + 1}")
    ax[0].legend(ncol=n)
    ax[0].set_ylabel("link angle [deg]")
    ax[1].plot(t[m], s["Ctrl/u"][m], color=COLORS[1])
    ax[1].set_ylabel("voltage [V]")
    ax[2].plot(t[m], np.degrees(s["J1/qout"][m]), color=COLORS[0])
    ax[2].set_ylabel("arm [deg]")
    ax[2].set_xlabel("t [s]")
    for a in ax:
        a.grid(alpha=0.3)
        a.axvspan(t_dist, t_dist + dz["dist_duration"], color="orange", alpha=0.4)
    fig.suptitle("Disturbance on the tip link and recovery (LQR)")
    _save(fig, docs, out, "disturbance")

    tn, xf, phif = tl.free_swing(plant, np.array(dz["free_start"]), dz["t_free"])
    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9, 5.5))
    for k in range(n):
        ax[0].plot(tn, np.degrees(phif[:, k]), color=COLORS[k], label=f"design, link {k + 1}")
        ax[0].plot(tf, np.degrees(sf[f"Angles/phi{k + 1}"]), color=COLORS[k], ls="--", label=f"bond graph, link {k + 1}")
        ax[1].plot(tn, 1000 * (np.interp(tn, tf, sf[f"Angles/phi{k + 1}"]) - phif[:, k]), color=COLORS[k])
    ax[0].set_ylabel("link angle [deg]")
    ax[0].legend(ncol=2, fontsize=7)
    ax[1].set_ylabel("difference [mrad]")
    ax[1].set_xlabel("t [s]")
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("Free swing: Lagrangian design model against the bond graph")
    _save(fig, docs, out, "free")
    return out


def pages(dz: dict, plant: tl.Plant, meas: dict, img: dict[str, str], shot: str | None) -> dict[str, str]:
    n = plant.n_links
    name = dz["example"]
    bg = meas["bond_graph"]
    fd = meas["free_diff"]
    dm = dz["metrics"]
    dr = dz["drive"]
    fe = dz["feasibility"]
    co = dz["collocation"]
    L = plant.lengths
    M = plant.masses
    vmax = dz["vmax"]
    links_txt = ", ".join(f"link {k + 1}: $l = {L[k]*100:.2f}$ cm, $m = {M[k]:.3f}$ kg" for k in range(n))
    shot_md = f"\n![3D view during the swing-up|600]({shot})\n" if shot else ""
    solves = ", ".join(
        f"{e['nk']} intervals, {e['vmax']:g} V, link-rate weight {e['w_rate']:g} ({e['iters']} iterations, {e['seconds']:.0f} s)" for e in co["log"]
    )
    last = co["log"][-1]
    ov = f"""# Rotary triple inverted pendulum

A Quanser-style **rotary arm** turns about the vertical axis; a chain of {n} pendulum links hangs from the arm tip and swings in the plane **perpendicular to the arm**. A single input drives the arm: the voltage of an SRV02-like DC servo with a 70:1 gearbox, limited to $\\pm {vmax:g}$ V. The arm, the servo and the links are those of the Quanser rotary double inverted pendulum, chained short + short + medium: **this triple is not a Quanser product**, and its amplifier limit is raised from 10 V to {vmax:g} V (see [structure](page:structure)).

![The whole run|700]({img['full']})

## Scenario

1. $t < {dz['t_on']:g}$ s: the chain hangs straight down at rest, the motor voltage is 0 (phase 0). Nothing moves.
2. $t = {dz['t_on']:g}$ s: the swing-up starts (phase 1): a feed-forward trajectory from offline direct collocation, tracked by a discrete time-varying LQR. It takes $T_s = {dz['t_s']:g}$ s; all links are within 3 deg of upright at $t = {bg['t_upright']:.2f}$ s.
3. Catch at $t = {bg['t_catch']:.2f}$ s: the infinite-horizon LQR takes over (phase 2, latched) and balances all {n} links upright (inside {bg['band_pre_deg']:.3f} deg before the disturbance).
4. $t = {dz['t_dist']:g}$ s ({dz['t_dist'] - bg['t_catch']:.1f} s after the catch): a {dz['dist_force']:g} N force pulse of {dz['dist_duration'] * 1000:.0f} ms hits the tip of link {n}. The tip link deflects by {bg['peak_defl_deg']:.1f} deg (the lower links more, the controller moves them first) and the LQR recovers within {bg['t_recover']:.1f} s (to 0.5 deg).
5. The run ends at $t = {dz['t_end']:g}$ s.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Angles/phi{n}](signal:Angles/phi{n})), "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) and "Controller phase" ([Ctrl/phase](signal:Ctrl/phase)).
- Open the **3D View**: the arm and the links follow [J1/qout](signal:J1/qout), [J2/qout](signal:J2/qout), [J3/qout](signal:J3/qout) and [J4/qout](signal:J4/qout).
- Raise the disturbance amplitude ([DistPulse](block:DistPulse)): on the design model the balance loop recovers pulses up to {dz['max_pulse']:.3f} N ({dz['dist_duration'] * 1000:.0f} ms); beyond that the {vmax:g} V limit is reached for too long and the chain falls.
- Run `{name}-free`: the design check, the plant released from a non-trivial pose with the controller off.
{shot_md}
The pages: [multibond structure](page:structure), [equations of motion](page:equations), [trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control), [results](page:results).
"""
    st = f"""# Multibond structure

The plant is a **spatial multibond bond graph** (`stdlib:spatial/*`, `stdlib:multibond/*Spatial`); every power bond between the joints and the bodies is a `Power{{Spatial}}` bundle of six components.

```
World -- Mount -- J1 (Revolute3D, world z) -- Link1 -- BJ1 -- Arm (RigidBody3D)
 Motor (ElectricDrive) -- Shaft (ElasticShaft) -- Gear (IdealGear 70) -- J1.drive
 BJ1 -- T2 -- J2 (Revolute3D, arm axis) -- Link2 -- BJ2 -- Rod1 (RigidBody3D)
 BJ2 -- T3 -- J3 -- Link3 -- BJ3 -- Rod2
 BJ3 -- T4 -- J4 -- Link4 -- BJ4 -- Rod3
 Dist (ExternalWrenchSpatial) -- TipPoint -- BJ4
```

| part | block | note |
| --- | --- | --- |
| arm joint | [J1](block:J1), `Revolute3D` | rotates about the world $z$ axis; the held directions are compliant ($k_t = k_r = {dz['k_joint']:.0e}$ N/m, N·m/rad, damped near critically) so every state is integral |
| arm | [Arm](block:Arm), `RigidBody3D` | bar of {plant.arm_l * 100:.2f} cm and {plant.arm_m:.4f} kg, centre of mass at the middle |
| pendulum joints | [J2](block:J2), [J3](block:J3), [J4](block:J4) | `Revolute3D` about the arm axis: the joint frame of J2 is the arm frame rotated by $180^\\circ$ about $(1,0,1)/\\sqrt2$, so its $z$ axis is the arm axis and its $x$ axis is world up. Angle 0 is **upright**, $\\pi$ hanging; J3 and J4 are relative to the link below |
| bearings | [Bearing2](block:Bearing2) ... | `RotationalDamper` on each pendulum joint's drive port, {dz['jfric']:.0e} N·m·s/rad |
| links | [Rod1](block:Rod1), [Rod2](block:Rod2), [Rod3](block:Rod3) | `RigidBody3D`, centre of mass at the rod middle, thin-bar inertias; {links_txt} |
| servo | [Motor](block:Motor) | `drives/ElectricDrive`: $R_m = {dr['rm']:g}\\ \\Omega$, $L_m = {dr['lm'] * 1000:g}$ mH, $k_t = {dr['kt']:g}$ N·m/A, rotor {dr["jm"]:.3g} kg·m² |
| gearbox | [Shaft](block:Shaft), [Gear](block:Gear) | `ElasticShaft` ({dz['k_shaft']:.0e} N·m/rad and {dz['d_shaft']:g} N·m·s/rad at the load) and `IdealGear` {dr['ng']:g}:1. The elastic shaft keeps the rotor inertia integral: a rotor rigidly on a rate-imposing joint is derivative causal (W201) |
| poses | `ComposePose3D` chain | the body poses are composed from the joint poses and feed the gravity of every body |
| disturbance | [Dist](block:Dist) | `ExternalWrenchSpatial` on the tip of the top link through a `FixedTransform3DNeutral`; force along the body $y$ axis (perpendicular to the rod, in the pendulum plane), driven by [DistPulse](block:DistPulse) |
| firmware | [Ctrl](block:Ctrl) | project block `RotaryCtrl`, 1 kHz discrete, reads the joint coordinates and rates ([Clock](block:Clock) is the time) |
| measurement | [Angles](block:Angles) | project block `LinkAngles`: the absolute link angles $\\varphi_k = q_2 + \\dots + q_{{k+1}}$ and their largest deviation `dev` |

The joints are 100 times stiffer than in the double (1e6 there), and the gear shaft (1000 N·m/rad in the double) is a stand-in for a rigid gearbox: it only keeps the rotor inertia integral, and it is damped near critically. The triple's swing-up is chaotic, so the design model has to match the bond graph closely for the feed-forward to stay useful (see [equations](page:equations)); the stiff shaft also integrates three times faster than the 1e5 N·m/rad one.

## Parameters and their source

| quantity | value | source |
| --- | --- | --- |
| arm length / mass | 0.2159 m / 0.2570 kg | Quanser product page |
| links | {links_txt} | Quanser short pendulum (20.0 cm, 0.097 kg) twice and the medium pendulum (33.65 cm, 0.127 kg) on top; the chain itself is assumed (not a Quanser product) |
| servo | $R_m$ 8.4 Ω, $L_m$ 1.16 mH, $k_t = k_m$ 0.0333, $J_m$ 3.87e-7, total gear ratio 70, load friction 0.015 N·m·s/rad | Quanser SRV02 manual (as in the double; recalled, not re-read) |
| amplifier limit | $\\pm {vmax:g}$ V | assumed: raised from the double's 10 V, see below |
| assumed | centre of mass at the bar middle, bar radii (6 mm arm, 8 mm links), gear stiffness, pendulum bearing friction, motor and gearbox efficiency folded into the viscous load friction | not published |

## Why {vmax:g} V: the feasibility estimate

Raising the chain from hanging to upright takes $\\Delta E = {fe['dE']:.2f}$ J, on average {fe['p_mean_needed']:.2f} W over $T_s = {dz['t_s']:g}$ s. Energy is not the limit: the winding delivers at most $V^2/(4R_m)$ = {fe['p_max']:.1f} W at {vmax:g} V (3.0 W at 10 V). **Speed** is: the back-EMF of the 70:1 servo caps the arm rate at the no-load value $n k_t V / (n^2 k_t^2 + R_m b)$ = {fe['noload_rate_10V']:.1f} rad/s at 10 V and {fe['noload_rate']:.1f} rad/s at {vmax:g} V. The smooth triple swing-up found here needs an arm rate of {last['max_arm_rate']:.1f} rad/s, more than 10 V allows; at 10 V the optimiser only finds whip-like trajectories (link rates of 40–60 rad/s) that no feedback can track. At {vmax:g} V the trajectory keeps the link rates below {last['max_link_rate']:.0f} rad/s. The stall torque at the arm is {fe['stall_torque']:.1f} N·m. The run's RMS winding current is {dm['i_rms']:.2f} A (design model), so the short over-voltage is thermally harmless.
"""
    eq = f"""# Equations of motion

The generalised coordinates are the joint coordinates of the bond graph, $q = (q_1, \\dots, q_{{{n + 1}}})$: the arm angle $q_1$ and, for each link, its angle relative to the link below ($q_2$ from upright for the first link). With the bar poses $R_i(q)$, centres $p_i(q)$, masses $m_i$ and principal inertias $J_i$ the kinetic and potential energies are

$$T = \\tfrac12 J_r \\dot q_1^2 + \\sum_i \\tfrac12 m_i |\\dot p_i|^2 + \\tfrac12 \\omega_i^T J_i \\omega_i, \\qquad V = \\sum_i m_i g\\, p_{{i,z}},$$

with $\\hat\\omega_i = R_i^T \\dot R_i$ and the arm-axis inertia of the drive $J_r = n^2 J_m - L_m n^2 k_t^2 / R_m^2 = {plant.drive.jrot:.3e}$ kg·m² (the second term is the winding, see below). Lagrange's equations give the manipulator form

$$M(q)\\,\\ddot q = \\frac{{\\partial T}}{{\\partial q}} - \\dot M\\,\\dot q - \\frac{{\\partial V}}{{\\partial q}} + Q, \\qquad Q = \\begin{{pmatrix}} \\tau_m - b_{{load}} \\dot q_1 \\\\ -b_j \\dot q_2 \\\\ \\vdots \\end{{pmatrix}}.$$

The servo delivers at the arm axis

$$\\tau_m = \\frac{{n k_t}}{{R_m}} \\left(u - n k_t \\dot q_1\\right)$$

with $u$ the clamped voltage ([Ctrl/u](signal:Ctrl/u)). `design/triple_lib.py` builds $M$ and the right-hand side with CasADi from these energies; the simulation solves $M \\ddot q = \\dots$ numerically, the trajectory optimisation keeps it as an implicit constraint.

## Design model against the bond graph

Released from rest at $q = {dz['free_start']}$ rad with the motor terminals at 0 V, the Lagrangian model and the bond graph (model `{name}-free`) stay within **{fd['max'] * 1000:.3f} mrad** over {dz['t_free']:g} s (arm {fd['J1/qout'] * 1000:.3f} mrad, links {', '.join(f"{fd[f'Angles/phi{k + 1}'] * 1000:.3f}" for k in range(n))} mrad). The remaining difference is what the design model neglects: the joint compliance ($10^8$) and the gear elasticity.

**The winding.** The design model has no current state. The winding lag $\\tau_e = L_m/R_m$ = {dr['lm'] / dr['rm'] * 1000:.2f} ms delays the back-EMF torque $-c_e \\dot q_1$, $c_e = n^2 k_t^2/R_m$ = {dr['ng'] ** 2 * dr['kt'] ** 2 / dr['rm']:.3f} N·m·s/rad; to first order in $\\tau_e$ that is $-c_e \\dot q_1 + c_e \\tau_e \\ddot q_1$, an inertia of $-c_e \\tau_e$ = {-dr['ng'] ** 2 * dr['kt'] ** 2 / dr['rm'] * dr['lm'] / dr['rm']:.2e} kg·m² at the arm axis (1.5 % of the arm), which is the second term of $J_r$. Without it the free swing differed by 1.5 mrad over the same 2 s: the winding was by far the largest mismatch, larger than the joint compliance and the gear.

![Free swing, design against bond graph|700]({img['free']})
"""
    tr = f"""# Trajectory optimisation

The swing-up trajectory is computed offline by **direct collocation** (`design/triple_lib.py:collocate`, CasADi with IPOPT) on the same Lagrangian model, including the motor and its voltage limit. State $x = (q, \\dot q)$, input $u$ (volts, piecewise linear between the knots).

$$\\min \\int_0^{{T_s}} u^2 + {co['w_du']:g}\\,\\dot u^2 + {co['w_rate']:g}\\,|\\dot q_{{2:4}}|^2\\, dt$$

subject to, on every interval $[t_k, t_{{k+1}}]$ of length $h$ (separated **Hermite-Simpson**):

- the dynamics as implicit constraints at every knot and midpoint, $M(q_k)\\,a_k = \\mathrm{{rhs}}(q_k, \\dot q_k, u_k)$ with the accelerations $a_k$ as decision variables (no symbolic inverse of $M$: the problem stays sparse and small);
- $x_c = \\tfrac12 (x_k + x_{{k+1}}) + \\tfrac h8 (f_k - f_{{k+1}})$ and $x_{{k+1}} - x_k = \\tfrac h6 (f_k + 4 f_c + f_{{k+1}})$, $f = (\\dot q, a)$;
- hanging at rest at the start, $x(0) = (0, \\pi, 0, 0; 0)$, **upright at rest** at the end, $x(T_s) = 0$, $u = 0$ at both ends;
- $|u| \\le u_{{max}}$ and $|q_1| \\le {co['theta_max']:g}$ rad (arm travel).

The $\\dot u^2$ term (input-rate regularisation) and the link-rate term select a smooth, slow trajectory among the many local optima; without them IPOPT returns bang-bang, whip-like solutions with link rates of 30–60 rad/s that no feedback tracks. Even with them the basin depends on the start: the first solve therefore uses a heavy link-rate weight (1.0) to pick a smooth basin, and the next solves relax it to the {co['w_rate']:g} of the cost above.

**Continuation and mesh refinement**, each solve warm-started from the previous one: {solves}; {co['seconds']:.0f} s in all. The first guess is link 1 turned linearly from hanging to upright. The last solve tightens the feed-forward voltage to {last['vmax']:g} V, so the feedback keeps {vmax - last['vmax']:g} V of the {vmax:g} V amplifier. The result: $T_s = {dz['t_s']:g}$ s, link rates up to {last['max_link_rate']:.1f} rad/s, arm rate up to {last['max_arm_rate']:.1f} rad/s, arm angle up to {last['max_arm']:.2f} rad.

The trajectory, its voltage and the gain schedule are written into [Ctrl](block:Ctrl) as the constant table `Tab` (one row every {dz['dt_tab'] * 1000:.0f} ms, {len(dz['tab_u'])} rows: $x^*$, $u^*$ and $K$), generated by `design/build_model.py`.
"""
    poles = sorted(complex(p[0], p[1]).real for p in dz["poles"])
    ct = f"""# TVLQR and LQR

The [Ctrl](block:Ctrl) firmware runs at 1 kHz with a zero-order hold (`@discrete Ts = 1e-3`) and has three phases, recorded in [Ctrl/phase](signal:Ctrl/phase):

| phase | when | law |
| --- | --- | --- |
| 0 | $t < t_{{on}} = {dz['t_on']:g}$ s | $u = 0$ (hanging at rest) |
| 1 | swing-up | $u = u^*(t) - K(t)\\,(x - x^*(t))$, table interpolation, clamped to $\\pm {vmax:g}$ V |
| 2 | balance, latched | $u = -K_{{lqr}}\\, x$, clamped to $\\pm {vmax:g}$ V |

**Discrete time-varying LQR.** The design model sampled at 1 kHz with a zero-order hold is $x_{{k+1}} = F(x_k, u_k)$ (RK4, two steps per sample). Along the nominal, $A_k = \\partial F/\\partial x$ and $B_k = \\partial F/\\partial u$ are the exact Jacobians of that step, and the discrete Riccati recursion runs backwards from the infinite-horizon cost-to-go:

$$K_k = (R + B_k^T P_{{k+1}} B_k)^{{-1}} B_k^T P_{{k+1}} A_k, \\qquad P_k = Q + A_k^T P_{{k+1}} (A_k - B_k K_k), \\qquad P_N = P_{{lqr}}.$$

The recursion is numerically stable for any weights (the continuous Riccati ODE of a fast, chaotic trajectory overflows). The collocation solution is first tracked once by the sampled model under its own TVLQR; that roll-out, consistent with the 1 kHz model, is the nominal $(x^*, u^*)$ of the table and the gains are recomputed along it. It ends {dz['tvlqr']['rollout_end_err']:.1e} from the upright. $Q = \\mathrm{{diag}}({', '.join(f'{v:g}' for v in dz['qdiag'])})$ (angles in rad, rates in rad/s), $R = {dz['r']:g}$ V$^{{-2}}$.

**Infinite-horizon LQR** of the same sampled model at the upright, same weights: $K_{{lqr}}$ = ({', '.join(f'{v:.2f}' for v in dz['k_lqr'])}); the TVLQR ends exactly in this gain. Equivalent closed-loop poles {', '.join(f'{p:.1f}' for p in poles)} 1/s.

**Catch.** Phase 2 starts once $t - t_{{on}} \\ge T_s$ and the LQR cost-to-go $V = x^T P_{{lqr}}\\, x$ ([Ctrl/vcost](signal:Ctrl/vcost)) is below {dz['catch_tol']:.0e} (about 1.5 deg on the top link alone); it is latched. Because the last table row is the LQR gain at the upright, the switch is seamless. The catch happened at $t = {bg['t_catch']:.2f}$ s.

**Validation before the bond graph.** `design.py` runs the whole scenario with this firmware logic (1 kHz, table interpolation, clamp, catch) on the design model, and on six perturbed models (link masses ±3 %, link lengths +1 %, bearing friction ×3, motor $k_t$ −3 %, load friction ×1.5): all swing up, are caught at {dz['t_on'] + dz['t_s']:g} s and recover the pulse.
"""
    rs = f"""# Results and checks

Numbers of the bond-graph run (real worker, `Rodas5P`, rtol 1e-6, atol 1e-8) against the design closed loop:

| quantity | bond graph | design.py (rigid model) |
| --- | --- | --- |
| upright (all links within 3 deg) | {bg['t_upright']:.3f} s | {dm['t_upright']:.3f} s |
| catch (phase 2) | {bg['t_catch']:.3f} s | {dm['t_catch']:.3f} s |
| upright band before the disturbance | {bg['band_pre_deg']:.3f} deg | {dm['band_pre_deg']:.3f} deg |
| tip deflection after the disturbance | {bg['peak_defl_deg']:.2f} deg | {dm['peak_defl_deg']:.2f} deg |
| recovery (inside 0.5 deg) | {bg['t_recover']:.2f} s after the pulse | {dm['t_recover']:.2f} s |
| peak motor voltage | {bg['peak_v']:.2f} V (limit {vmax:g} V) | {dm['peak_v']:.2f} V |
| largest arm angle | {bg['max_arm']:.3f} rad | {dm['max_arm']:.3f} rad |
| design against bond graph, free swing | {fd['max'] * 1000:.3f} mrad | |

![Swing-up and catch|700]({img['swingup']})

![Disturbance and recovery|700]({img['disturbance']})

`expected.json` holds the checks (with the tolerance of each in its note): at rest before $t_{{on}}$, upright by $t_{{on}} + T_s + 0.5$ s, the upright band before the disturbance, the disturbance peak, the recovery band, the voltage limit, the arm travel, no W201/W206/E901 diagnostics, the scene bindings, and (model `{name}-free`) the free swing against `design.py`.

Back to the [overview](page:overview).
"""
    return {"overview": ov, "structure": st, "equations": eq, "trajectory": tr, "control": ct, "results": rs}


def write(example_dir: Path, n_links: int, shot: Path | None = None) -> None:
    dz = json.loads((example_dir / "design" / "design.json").read_text(encoding="utf-8"))
    meas = json.loads((example_dir / "design" / "measured.json").read_text(encoding="utf-8"))
    plant = tb.plant_from(dz)
    name = dz["example"]
    docs = example_dir / "models" / f"{name}.docs"
    (docs / "pages").mkdir(parents=True, exist_ok=True)
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    for old in (docs / "assets").glob("*"):
        old.unlink()
    img = plots(dz, plant, example_dir, docs)
    shot_ref = None
    if shot is not None and shot.is_file():
        digest = hashlib.sha256(shot.read_bytes()).hexdigest()[:12]
        (docs / "assets" / f"{digest}.png").write_bytes(shot.read_bytes())
        shot_ref = f"assets/{digest}.png"
    texts = pages(dz, plant, meas, img, shot_ref)
    for pid, text in texts.items():
        (docs / "pages" / f"{pid}.md").write_text(text, encoding="utf-8", newline="\n")
    tree = {
        "format": "bgsim.docs",
        "version": 1,
        "pages": [
            {
                "id": "overview",
                "title": "Overview",
                "file": "pages/overview.md",
                "children": [
                    {"id": pid, "title": title, "file": f"pages/{pid}.md", "children": []}
                    for pid, title in (
                        ("structure", "Multibond structure"),
                        ("equations", "Equations of motion"),
                        ("trajectory", "Trajectory optimisation"),
                        ("control", "TVLQR and LQR"),
                        ("results", "Results and checks"),
                    )
                ],
            }
        ],
    }
    (docs / "docs.json").write_text(json.dumps(tree, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {docs}")
