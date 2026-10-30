"""Write the model docs (W5.6 format) of a rotary pendulum example from its runs (X5.13).

Plots are made with matplotlib from the saved bond-graph runs in `design/_runs/`; every asset is
named by the first 12 hex digits of its SHA-256. Run through `finish.py --docs`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import rotary_design as rd  # noqa: E402
import rotary_lib as rl  # noqa: E402
import runner  # noqa: E402

NAMES = {2: "double", 3: "triple"}
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


def plots(dz: dict, plant: rl.Plant, example_dir: Path, docs: Path) -> dict[str, str]:
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

    tn, xf, phif = rd.free_swing(plant, np.array(dz["free_start"]), dz["t_free"])
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


def pages(dz: dict, plant: rl.Plant, meas: dict, img: dict[str, str], shot: str | None) -> dict[str, str]:
    n = plant.n_links
    kind = NAMES[n]
    name = dz["example"]
    bg = meas["bond_graph"]
    fd = meas["free_diff"]
    L = plant.lengths
    M = plant.masses
    quanser = n == 2
    tip = f"Angles/phi{n}"
    links_txt = ", ".join(f"link {k + 1}: $l = {L[k]*100:.2f}$ cm, $m = {M[k]:.3f}$ kg" for k in range(n))
    origin = (
        "The arm, the two links and the SRV02 servo follow the Quanser rotary double inverted pendulum "
        "(product page and SRV02 manual, see *Parameters*)."
        if quanser
        else "The arm and the servo are those of the Quanser rotary double inverted pendulum; the third link is added "
        "here (**this is not a Quanser product**): the same construction as the lower link of the double."
    )
    shot_md = f"\n![3D view during the swing-up|600]({shot})\n" if shot else ""
    ov = f"""# Rotary {kind} inverted pendulum

A Quanser-style **rotary arm** turns about the vertical axis; a chain of {n} pendulum links hangs from the arm tip and swings in the plane **perpendicular to the arm**. A single input drives the arm: the voltage of an SRV02-like DC servo with a 70:1 gearbox, limited to $\\pm 10$ V. {origin}

![The whole run|700]({img['full']})

## Scenario

1. $t < 1$ s: the chain hangs straight down at rest, the motor voltage is 0 (phase 0). Nothing moves.
2. $t = 1$ s: the swing-up starts (phase 1): a feed-forward trajectory from offline direct collocation, tracked by a time-varying LQR. It takes $T_s = {dz['t_s']:g}$ s.
3. Catch at $t = {bg['t_catch']:.2f}$ s: the infinite-horizon LQR takes over (phase 2, latched) and balances all {n} links upright.
4. $t = {dz['t_dist']:g}$ s ({dz['t_dist'] - bg['t_catch']:.1f} s after the catch): a {dz['dist_force']:g} N force pulse of {dz['dist_duration'] * 1000:.0f} ms hits the tip of link {n}. The tip link deflects by {bg['peak_defl_deg']:.1f} deg and the LQR recovers within {bg['t_recover']:.1f} s (to 0.5 deg).
5. The run ends at $t = {dz['t_end']:g}$ s.

## What to try

- Open the **Plots** tab: "Link angles from upright" ([Angles/phi{n}](signal:Angles/phi{n})), "Motor voltage" ([Ctrl/u](signal:Ctrl/u)) and "Controller phase" ([Ctrl/phase](signal:Ctrl/phase)).
- Open the **3D View**: the arm and the links follow [J1/qout](signal:J1/qout) and [J2/qout](signal:J2/qout).
- Raise the disturbance amplitude ([DistPulse](block:DistPulse)): the chain is caught up to a limit and falls beyond it, because the 10 V limit of the amplifier is reached.
{shot_md}
The pages: [multibond structure](page:structure), [equations of motion](page:equations), [trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control), [results](page:results).
"""
    st = f"""# Multibond structure

The plant is a proper **spatial multibond bond graph** (`stdlib:spatial/*`, `stdlib:multibond/*Spatial`); every power bond between the joints and the bodies is a `Power{{Spatial}}` bundle of six components.

```
World -- Mount -- J1 (Revolute3D, world z) -- Link1 -- BJ1 -- Arm (RigidBody3D)
 Motor (ElectricDrive) -- Shaft (ElasticShaft) -- Gear (IdealGear 70) -- J1.drive
 BJ1 -- T2 -- J2 (Revolute3D, arm axis) -- Link2 -- BJ2 -- Rod1 (RigidBody3D)  ... one joint and one body per link
 Dist (ExternalWrenchSpatial) -- TipPoint -- BJ{n + 1}
```

| part | block | note |
| --- | --- | --- |
| arm joint | [J1](block:J1), `Revolute3D` | rotates about the world $z$ axis; the held directions are compliant ($k_t = k_r = 10^6$ N/m, N·m/rad) so every state is integral |
| arm | [Arm](block:Arm), `RigidBody3D` | thin bar of {plant.arm_l * 100:.2f} cm and {plant.arm_m:.4f} kg, centre of mass at the middle ($J_z = m l^2/12$) |
| pendulum joints | [J2](block:J2) ... | `Revolute3D` about the arm axis: the joint frame is the arm frame rotated by $180^\\circ$ about $(1,0,1)/\\sqrt2$, so the joint $z$ axis is the arm axis and the joint $x$ axis is world up. Angle 0 is **upright**, $\\pi$ hanging |
| links | [Rod1](block:Rod1) ... | `RigidBody3D`, centre of mass at the rod middle, thin-bar inertias; {links_txt} |
| servo | [Motor](block:Motor) | `drives/ElectricDrive`: $R_m = 8.4\\ \\Omega$, $L_m = 1.16$ mH, $k_t = 0.0333$ N·m/A, rotor $3.87\\cdot10^{{-7}}$ kg·m² |
| gearbox | [Shaft](block:Shaft), [Gear](block:Gear) | `ElasticShaft` (1000 N·m/rad at the load) and `IdealGear` 70:1. The elastic shaft keeps the rotor inertia integral: a rotor rigidly on a rate-imposing joint is derivative causal (W201) |
| poses | `ComposePose3D` chain | the body poses are composed from the joint coordinates and feed the gravity of every body |
| disturbance | [Dist](block:Dist) | `ExternalWrenchSpatial` on the tip of the top link through a `FixedTransform3DNeutral`; force along the body $y$ axis (perpendicular to the rod, in the pendulum plane) |
| firmware | [Ctrl](block:Ctrl) | project block `RotaryCtrl`, 1 kHz discrete, reads the joint coordinates and rates ([Clock](block:Clock) is the time) |
| measurement | [Angles](block:Angles) | project block `LinkAngles`: the absolute link angles $\\varphi_k = q_2 + \\dots + q_{{k+1}}$ and their largest deviation |

## Parameters and their source

{origin}

| quantity | value | source |
| --- | --- | --- |
| arm length / mass | 0.2159 m / 0.2570 kg | Quanser product page |
| links | {links_txt} | Quanser product page (short pendulum 20.0 cm, 0.097 kg; medium pendulum 33.65 cm, 0.127 kg){'' if quanser else '; the third link is assumed (not a Quanser product)'} |
| servo | $R_m$ 8.4 Ω, $L_m$ 1.16 mH, $k_t = k_m$ 0.0333, $J_m$ 3.87e-7, total gear ratio 70, load friction 0.015 N·m·s/rad | Quanser SRV02 manual (recalled from the manual, not re-read) |
| assumed | centre of mass at the bar middle, bar radii (6 mm arm, 8 mm links) for the axial inertia, gear stiffness 1000 N·m/rad, pendulum bearing friction $3\\cdot10^{{-5}}$ N·m·s/rad, 10 V amplifier limit, motor and gearbox efficiency folded into the viscous load friction | not published |
"""
    eq = f"""# Equations of motion

The generalised coordinates are the joint coordinates of the bond graph, $q = (q_1, \\dots, q_{{{n + 1}}})$: the arm angle $q_1$ and, for each link, its angle relative to the link below ($q_2$ from upright for the first link). With the bar poses $R_i(q)$, centres $p_i(q)$, masses $m_i$ and principal inertias $J_i$ the kinetic and potential energies are

$$T = \\tfrac12 J_r \\dot q_1^2 + \\sum_i \\tfrac12 m_i |\\dot p_i|^2 + \\tfrac12 \\omega_i^T J_i \\omega_i, \\qquad V = \\sum_i m_i g\\, p_{{i,z}},$$

with $\\hat\\omega_i = R_i^T \\dot R_i$ and the rotor inertia reflected to the arm axis $J_r = n^2 J_m = {rl.NG**2 * rl.JM:.2e}$ kg·m². Lagrange's equations give

$$M(q)\\,\\ddot q = \\frac{{\\partial T}}{{\\partial q}} - \\dot M\\,\\dot q - \\frac{{\\partial V}}{{\\partial q}} + Q, \\qquad Q = \\begin{{pmatrix}} \\tau_m - c_g \\dot q_1 \\\\ -b_j \\dot q_2 \\\\ \\vdots \\end{{pmatrix}}.$$

The servo (winding inductance neglected in the design model) delivers at the arm axis

$$\\tau_m = \\frac{{n k_t}}{{R_m}} \\left(u - n k_t \\dot q_1\\right), \\qquad c_g = \\frac{{n^2 k_t^2}}{{R_m}} + n^2 b_m,$$

with $u$ the clamped voltage ([Ctrl/u](signal:Ctrl/u)). `design/rotary_lib.py` builds $M$, the Coriolis terms and the gravity with CasADi from these energies, and linearises them for the LQR.

## Design model against the bond graph

Released from rest at $q = {dz['free_start']}$ rad with the motor terminals at 0 V, the Lagrangian model and the bond graph (model `{name}-free`) stay within **{fd['max'] * 1000:.2f} mrad** over {dz['t_free']:g} s (arm {fd['J1/qout'] * 1000:.2f} mrad, links {', '.join(f"{fd[f'Angles/phi{k + 1}'] * 1000:.2f}" for k in range(n))} mrad). The difference is the joint compliance, the winding inductance and the gear elasticity that the design model neglects.

![Free swing, design against bond graph|700]({img['free']})
"""
    tr = f"""# Trajectory optimisation

The swing-up trajectory is computed offline by **direct collocation** (`design/rotary_lib.py:swing_up`, CasADi with IPOPT) on the same Lagrangian model, including the motor and its voltage limit. State $x = (q, \\dot q)$, input $u$ (volts).

$$\\min_{{x,u}} \\int_0^{{T_s}} u^2 + 0.2\\,\\dot u^2 + 0.05\\,|\\dot q_{{2:}}|^2\\, dt$$

subject to

- the Hermite-Simpson collocation constraints $x_{{k+1}} - x_k = \\tfrac{{h}}{{6}}\\,(f_k + 4 f_c + f_{{k+1}})$ on every interval;
- hanging at rest at the start, $x(0) = (0, \\pi, 0, \\dots; 0)$, and **upright at rest** at the end, $x(T_s) = 0$;
- $|u| \\le 9$ V (the amplifier limit is 10 V; the 1 V margin is for the feedback) and $|q_1| \\le 2$ rad (arm travel).

$T_s = {dz['t_s']:g}$ s. The first guess is the forward simulation of a sinusoidal voltage from hanging; the solve is a continuation in the voltage bound (10 V, then 9 V) followed by two refinements of the grid ({'80 to 160 to 320' if n == 2 else '100 to 200 to 400'} intervals). The refinement matters: the swing-up of the {kind} pendulum is chaotic, and on the coarse grid the collocation error alone made the trajectory untrackable. On the final grid the trajectory is dynamically exact to the accuracy that the time-varying LQR corrects.

The trajectory, its voltage and the gain schedule are written into [Ctrl](block:Ctrl) as the constant table `Tab` (one row every {dz['dt_tab'] * 1000:.0f} ms, {len(dz['tab_u'])} rows: $x^*$, $u^*$ and $K$), generated by `design/build_model.py`.
"""
    ct = f"""# TVLQR and LQR

The [Ctrl](block:Ctrl) firmware runs at 1 kHz with a zero-order hold (`@discrete Ts = 1e-3`) and has three phases, recorded in [Ctrl/phase](signal:Ctrl/phase):

| phase | when | law |
| --- | --- | --- |
| 0 | $t < t_{{on}} = {dz['t_on']:g}$ s | $u = 0$ (hanging at rest) |
| 1 | swing-up | $u = u^*(t) - K(t)\\,(x - x^*(t))$, table interpolation, clamped to $\\pm 10$ V |
| 2 | balance, latched | $u = -K_{{lqr}}\\, x$, clamped to $\\pm 10$ V |

**Time-varying LQR.** Along the trajectory the model is linearised, $A(t) = \\partial f/\\partial x$, $B(t) = \\partial f/\\partial u$, and the Riccati differential equation

$$-\\dot P = Q + A^T P + P A - P B R^{{-1}} B^T P, \\qquad P(T_s) = P_{{lqr}}$$

is integrated backwards (RK4, 2 ms). $K(t) = R^{{-1}} B^T P(t)$. $Q = \\mathrm{{diag}}({', '.join(f'{v:g}' for v in dz['qdiag'])})$ (angles in rad, rates in rad/s) and $R = {dz['r']:g}$ V$^{{-2}}$.

**Infinite-horizon LQR** at the upright with the same weights: $K_{{lqr}}$ = {', '.join(f'{v:.2f}' for v in dz['k_lqr'])}.

**Catch.** Phase 2 starts once $t - t_{{on}} \\ge T_s$ and the weighted norm $\\sqrt{{\\sum c_i x_i^2}} < {dz['catch_tol']:g}$ ([Ctrl/enorm](signal:Ctrl/enorm)); it is latched. The catch happened at $t = {bg['t_catch']:.2f}$ s.

Controller and design model use the same linearisation: the gains come from `design/rotary_design.py`.
"""
    rs = f"""# Results and checks

Numbers of the bond-graph run (real worker, `Rodas5P`, rtol 1e-6, atol 1e-8):

| quantity | bond graph | design.py (rigid model) |
| --- | --- | --- |
| upright (all links within 3 deg) | {bg['t_upright']:.3f} s | {dz['metrics']['t_upright']:.3f} s |
| catch (phase 2) | {bg['t_catch']:.3f} s | {dz['metrics']['t_catch']:.3f} s |
| upright band before the disturbance | {bg['band_pre_deg']:.3f} deg | {dz['metrics']['band_pre_deg']:.3f} deg |
| tip deflection after the disturbance | {bg['peak_defl_deg']:.2f} deg | {dz['metrics']['peak_defl_deg']:.2f} deg |
| recovery (inside 0.5 deg) | {bg['t_recover']:.2f} s after the pulse | {dz['metrics']['t_recover']:.2f} s |
| peak motor voltage | {bg['peak_v']:.2f} V (limit 10 V) | {dz['metrics']['peak_v']:.2f} V |
| largest arm angle | {bg['max_arm']:.3f} rad | {dz['metrics']['max_arm']:.3f} rad |
| design against bond graph, free swing | {fd['max'] * 1000:.2f} mrad | |

![Swing-up and catch|700]({img['swingup']})

![Disturbance and recovery|700]({img['disturbance']})

`expected.json` holds the checks (with the tolerance of each in its note): at rest before $t_{{on}}$, upright by $t_{{on}} + T_s + 0.5$ s, the upright band before the disturbance, the disturbance peak, the recovery band, the voltage limit, the arm travel, no W201/W206/E901 diagnostics, the scene bindings, and (model `{name}-free`) the free swing against `design.py`.

Back to the [overview](page:overview).
"""
    return {"overview": ov, "structure": st, "equations": eq, "trajectory": tr, "control": ct, "results": rs}


def write(example_dir: Path, n_links: int, shot: Path | None = None) -> None:
    dz = json.loads((example_dir / "design" / "design.json").read_text(encoding="utf-8"))
    meas = json.loads((example_dir / "design" / "measured.json").read_text(encoding="utf-8"))
    plant = rl.Plant(n_links, *rl.LINKS[n_links])
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
