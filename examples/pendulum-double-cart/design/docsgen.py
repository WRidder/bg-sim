"""Model docs of the cart pendulums (W5.6 format): `models/<model>.docs/{docs.json,pages,assets}`.

The pages are generated from the same `Scenario`/`Plant` that generated the model and the tables, plus the
numbers measured on real bond-graph runs, so the text cannot drift from the example. Result plots are PNGs
of those runs, named by the first 12 hex digits of their SHA-256. Used by `build_docs.py` of each example.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import cartpend as cp  # noqa: E402

NAMES = {2: "double", 3: "triple"}
COLORS = ["#d9822b", "#3fa05a", "#3a78c9"]


class Docs:
    def __init__(self, out: Path):
        self.out = out
        if out.exists():
            shutil.rmtree(out)
        (out / "pages").mkdir(parents=True)
        (out / "assets").mkdir()
        self.pages: dict[str, tuple[str, str]] = {}

    def figure(self, fig, alt: str, width: int = 900) -> str:
        tmp = self.out / "assets" / "tmp.png"
        fig.savefig(tmp, dpi=100, metadata={"Software": None})
        plt.close(fig)
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]
        tmp.replace(self.out / "assets" / f"{digest}.png")
        return f"![{alt}|{width}](assets/{digest}.png)"

    def page(self, pid: str, title: str, text: str) -> None:
        self.pages[pid] = (title, text.strip("\n") + "\n")
        with open(self.out / "pages" / f"{pid}.md", "w", newline="\n", encoding="utf-8") as fh:
            fh.write(self.pages[pid][1])

    def manifest(self, tree: list) -> None:
        def node(spec):
            pid, children = spec
            return {"id": pid, "title": self.pages[pid][0], "file": f"pages/{pid}.md",
                    "children": [node(c) for c in children]}
        doc = {"format": "bgsim.docs", "version": 1, "pages": [node(t) for t in tree]}
        with open(self.out / "docs.json", "w", newline="\n") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")


def _shade(ax, sc, t_catch):
    ax.axvspan(sc.t_on, t_catch, color="#f2e3c9", alpha=0.6, lw=0)
    ax.axvspan(t_catch, sc.t_dist, color="#d6ead9", alpha=0.6, lw=0)
    ax.axvline(sc.t_dist, color="#b03030", lw=1.0, ls="--")


def fig_overview(sc, t, S):
    P = sc.plant
    n = P.n
    t_catch = float(t[np.argmax(S["Ctrl/phase"] > 1.5)])
    fig, ax = plt.subplots(3, 1, figsize=(10, 7.2), sharex=True)
    for i in range(n):
        ax[0].plot(t, np.degrees(S[f"Ctrl/th{i + 1}"]), color=COLORS[i], lw=1.4, label=f"link {i + 1}")
    ax[0].set_ylabel("angle from upright (deg)")
    ax[1].plot(t, S["Rail/qout"], color="#3a78c9", lw=1.4, label="cart position")
    for v in (-P.x_rail, P.x_rail):
        ax[1].axhline(v, color="#b03030", lw=1.0, ls=":")
    ax[1].set_ylabel("cart x (m), rail limit dotted")
    ax[2].plot(t, S["Ctrl/u"], color="#444444", lw=1.0)
    for v in (-P.u_max, P.u_max):
        ax[2].axhline(v, color="#b03030", lw=1.0, ls=":")
    ax[2].set_ylabel("motor voltage (V)")
    ax[2].set_xlabel("t (s)")
    for a in ax:
        _shade(a, sc, t_catch)
        a.grid(alpha=0.25)
    ax[0].legend(loc="upper right", ncols=n)
    ax[0].set_title("swing-up (orange), balance (green), pulse (dashed)")
    fig.tight_layout()
    return fig


def fig_swingup(sc, t, S, tab, nom_t, nom_z, nom_u):
    n = sc.plant.n
    m = (t >= sc.t_on) & (t <= sc.t_on + sc.t_s + 0.3)
    fig, ax = plt.subplots(3, 1, figsize=(10, 7.2), sharex=True)
    for i in range(n):
        ax[0].plot(t[m] - sc.t_on, np.degrees(S[f"Ctrl/th{i + 1}"][m]), color=COLORS[i], lw=1.6, label=f"link {i + 1}, bond graph")
        ax[0].plot(nom_t, np.degrees(nom_z[:, 1 + i]), color="k", lw=0.8, ls="--")
    ax[0].plot([], [], color="k", lw=0.8, ls="--", label="optimised trajectory")
    ax[0].set_ylabel("angle (deg)")
    ax[0].legend(loc="upper left", ncols=2, fontsize=8)
    ax[1].plot(t[m] - sc.t_on, S["Rail/qout"][m], color="#3a78c9", lw=1.6, label="bond graph")
    ax[1].plot(nom_t, nom_z[:, 0], color="k", lw=0.8, ls="--", label="trajectory")
    ax[1].axhline(sc.x_lim, color="#b03030", lw=1.0, ls=":")
    ax[1].axhline(-sc.x_lim, color="#b03030", lw=1.0, ls=":")
    ax[1].set_ylabel("cart x (m), optimisation bound dotted")
    ax[1].legend(loc="upper left", fontsize=8)
    ax[2].plot(t[m] - sc.t_on, S["Ctrl/u"][m], color="#444444", lw=1.0, label="applied voltage")
    ax[2].plot(nom_t, nom_u, color="#d9822b", lw=1.4, label="feed-forward")
    ax[2].set_ylabel("voltage (V)")
    ax[2].set_xlabel("t - t_on (s)")
    ax[2].legend(loc="upper right", fontsize=8)
    for a in ax:
        a.grid(alpha=0.25)
    fig.tight_layout()
    return fig


def fig_gains(sc, tab):
    n = sc.plant.n
    names = ["x"] + [f"θ{i + 1}" for i in range(n)] + ["v"] + [f"ω{i + 1}" for i in range(n)]
    fig, ax = plt.subplots(1, 1, figsize=(10, 3.6))
    cmap = plt.get_cmap("tab10")
    for i in range(len(names)):
        ax.plot(tab.tk, tab.Ks[:, i], color=cmap(i % 10), lw=1.2, ls="-" if i <= n else "--", label=names[i])
    ax.set_xlabel("τ = t − t_on (s)")
    ax.set_ylabel("TVLQR gain (V per unit)")
    ax.legend(ncols=len(names), fontsize=7, loc="upper center")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return fig


def fig_pulse(sc, t, S):
    n = sc.plant.n
    m = (t >= sc.t_dist - 0.5) & (t <= sc.t_dist + 4.0)
    fig, ax = plt.subplots(3, 1, figsize=(10, 6.6), sharex=True)
    for i in range(n):
        ax[0].plot(t[m] - sc.t_dist, np.degrees(S[f"Ctrl/th{i + 1}"][m]), color=COLORS[i], lw=1.5, label=f"link {i + 1}")
    ax[0].axhspan(-0.5, 0.5, color="#d6ead9", alpha=0.7, lw=0)
    ax[0].set_ylabel("angle (deg), ±0.5° band")
    ax[0].legend(ncols=n, fontsize=8)
    ax[1].plot(t[m] - sc.t_dist, S["Rail/qout"][m], color="#3a78c9", lw=1.5)
    ax[1].set_ylabel("cart x (m)")
    ax[2].plot(t[m] - sc.t_dist, S["Ctrl/u"][m], color="#444444", lw=1.0)
    ax[2].set_ylabel("voltage (V)")
    ax[2].set_xlabel("t - t_pulse (s)")
    for a in ax:
        a.axvspan(0, sc.dist_dur, color="#b03030", alpha=0.35, lw=0)
        a.grid(alpha=0.25)
    fig.tight_layout()
    return fig


def fig_free(sc, tf, F, ref):
    P = sc.plant
    n = P.n
    th = np.cumsum(np.stack([F[f"Joint{i + 1}/qout"] for i in range(n)], 1), axis=1) - np.pi / 2
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.4), sharex=True)
    for i in range(n):
        ax[0].plot(tf, th[:, i], color=COLORS[i], lw=1.6, label=f"link {i + 1}, bond graph")
        ax[0].plot(tf, ref[:, 1 + i], color="k", lw=0.8, ls="--")
        ax[1].semilogy(tf, np.abs(th[:, i] - ref[:, 1 + i]) + 1e-12, color=COLORS[i], lw=1.2)
    ax[0].plot([], [], color="k", lw=0.8, ls="--", label="design ODE")
    ax[0].set_ylabel("angle from upright (rad)")
    ax[0].legend(ncols=2, fontsize=8)
    ax[1].set_ylabel("|bond graph − design| (rad)")
    ax[1].set_xlabel("t (s)")
    for a in ax:
        a.grid(alpha=0.25)
    fig.tight_layout()
    return fig


def build(sc: cp.Scenario, dyn, tab, traj, full_dir, free_dir, out: Path, readme_numbers: dict):
    """Write `out` (a `<model>.docs` folder)."""
    P = sc.plant
    n = P.n
    kind = NAMES[n]
    t, S = cp.read_run(full_dir)
    tf, F = cp.read_run(free_dir)
    M = cp.measure(sc, t, S)
    ref = cp.free_swing(sc, dyn, tf)
    dth, dx = cp.compare_free(sc, dyn, free_dir)
    nom = cp.Nominal(traj)
    nom_t = np.linspace(0, sc.t_s, 400)
    nom_z = np.array([nom.z(x) for x in nom_t])
    nom_u = np.array([nom.u(x) for x in nom_t])
    D = Docs(out)
    figs = {
        "overview": D.figure(fig_overview(sc, t, S), "Link angles, cart position and motor voltage over the whole run"),
        "swingup": D.figure(fig_swingup(sc, t, S, tab, nom_t, nom_z, nom_u), "Swing-up: optimised trajectory against the bond-graph run"),
        "gains": D.figure(fig_gains(sc, tab), "The time-varying LQR gains along the swing-up", 900),
        "pulse": D.figure(fig_pulse(sc, t, S), "The disturbance pulse and the recovery"),
        "free": D.figure(fig_free(sc, tf, F, ref), "Free swing: bond graph against the design ODE"),
    }
    nx = P.nx
    ln = [f"th{i + 1}" for i in range(n)]
    sigs = ", ".join(f"[Ctrl/th{i + 1}](signal:Ctrl/th{i + 1})" for i in range(n))
    link_list = ", ".join(f"[Joint{i + 1}](block:Joint{i + 1})" for i in range(n))
    body_list = ", ".join(f"[Body{i + 1}](block:Body{i + 1})" for i in range(n))
    rows = "\n".join(
        f"| link {i + 1} | {P.L[i]:g} m rod, {P.m[i]:g} kg, centre of mass {P.c[i]:g} m, $J = {P.J[i]:.4g}$ kg m² | joint friction {P.b[i]:g} N m s/rad |"
        for i in range(n)
    )
    tot_m = sum(P.m)

    # ------------------------------------------------------------------ overview
    D.page("overview", f"{kind.capitalize()} pendulum on a belt-driven cart", f"""
# {kind.capitalize()} pendulum on a belt-driven cart

A cart on a rail with a finite travel (±{P.x_rail:g} m) carries a {kind} pendulum. A DC motor drives the cart through a gearbox and a belt on a pulley; the {n} pendulum joints are **passive**. The plant is a planar multibond bond graph: a prismatic joint for the cart, revolute joints for the links, one rigid body per link, gravity inside every body. This is the cart version of the pendulum family (fixed pivot, cart, rotary base), built from the same planar elements as `robot-arm-2d` and the cart scenario of `inverted-pendulum-cart`.

{figs["overview"]}

## The scenario

| time | phase ([Ctrl/phase](signal:Ctrl/phase)) | what happens |
| --- | --- | --- |
| 0 to {sc.t_on:g} s | 0, hold | everything hangs straight down at rest; the motor voltage is 0 (nothing moves, the pivots start at their static deflection) |
| {sc.t_on:g} s | 1, swing-up | the feed-forward trajectory of an offline trajectory optimisation starts, tracked by a time-varying LQR (TVLQR) |
| {sc.t_on + sc.t_s:g} s | 2, balance | after {sc.t_s:g} s the nominal trajectory ends upright at rest and the 1 kHz discrete LQR takes over |
| {sc.t_dist:g} s | 2 | a {sc.dist_dur * 1000:g} ms force pulse of {sc.dist_amp:g} N hits the tip link ([Push](block:Push)) after {sc.t_dist - sc.t_on - sc.t_s:g} s of stable balance |
| to {sc.t_end:g} s | 2 | recovery, then {sc.t_end - sc.t_dist - M["t_rec"]:.1f} s of quiet balance |

The firmware is the pair [Traj](block:Traj) (table lookup) and [Ctrl](block:Ctrl) (1 kHz firmware), and the angles it sees are the joint encoders {link_list}. The absolute link angles from the upward vertical are recorded as {sigs}; [Rail/qout](signal:Rail/qout) is the cart position and [Ctrl/u](signal:Ctrl/u) the motor voltage.

## The rig (assumed values)

No published data exists for a belt-driven {kind} pendulum rig of this size, so the values are assumed and stated here; the motor and gearbox are in the range of a small 90 W brushed servo.

| part | value | note |
| --- | --- | --- |
| cart | {P.m_cart:g} kg, $J = {P.J_cart:g}$ kg m² | carriage with the belt clamp |
| rail | ±{P.x_rail:g} m of travel of the cart centre | the swing-up is optimised inside ±{sc.x_lim:g} m |
{rows}
| motor | {P.u_max:g} V supply limit, $R = {P.R_m:g}\\ \\Omega$, $L = {P.L_m * 1000:g}$ mH, $k_t = k_e = {P.k_t:g}$ N m/A | rotor $J_m = {P.J_m:g}$ kg m², bearing loss {P.b_m:g} N m s/rad |
| transmission | gearbox {P.N:g}:1, pulley radius {P.r * 1000:g} mm, belt {P.k_belt:g} N/m, {P.d_belt:g} N s/m | force per volt $\\alpha = {P.alpha:.3g}$ N/V, stall force {P.alpha * P.u_max:.0f} N, rotor inertia reflected to the cart {P.J_m * (P.N / P.r) ** 2:.2f} kg |

## What to try

- Open the **Plots** tab: the link angles ({sigs}), the cart ([Rail/qout](signal:Rail/qout)) and the voltage ([Ctrl/u](signal:Ctrl/u)) tell the story of the run.
- In the 3D view the cart rides on its rail between the two red end stops and the links swing up; the joints follow `Rail/qout` and `Joint1/qout` to `Joint{n}/qout`.
- Raise the `amplitude` of [PushPulse](block:PushPulse) (the pulse force) until the balance controller loses the pendulum: the limit is about {sc.dist_amp / 0.8:.2f} N for a 40 ms pulse in the design model.
- Run `pendulum-{kind}-cart-free`: the same plant with the motor shorted, released from a non-trivial pose; it is the design-model check (see [the results](page:results)).

Continue with [the multibond structure](page:structure), [the equations of motion](page:dynamics), [the trajectory optimisation](page:trajectory), [TVLQR and LQR](page:control) and [the results](page:results).
""")

    # ------------------------------------------------------------------ structure
    D.page("structure", "The multibond structure", f"""
# The multibond structure

```
Ground -- Rail(Prismatic2D) -- CartJ(1) -- Cart(RigidBody2D)
                |                 `-- Joint1 -- Link1 -- N1(1) -- Body1(RigidBody2D)
           drive (Translation)                      `-- Joint2 -- Link2 -- N2(1) -- Body2 ...
Motor(ElectricDrive) -- Gear -- Pulley(RackAndPinion) -- Belt(SpringDamper) -- Rail.drive
```

Every bond between planar ports is a two-stroke multibond carrying a 3-component twist and wrench $(\\omega, v_x, v_y)$ and $(\\tau, f_x, f_y)$.

| block | element | role |
| --- | --- | --- |
| [Ground](block:Ground) | `GroundPlanar` | world, zero twist |
| [Rail](block:Rail) | `Prismatic2D` | the cart's prismatic joint along $x$; exact translation, compliant in rotation and the perpendicular direction (the rigid limit is $k \\to \\infty$); its drive port is a force/velocity (Translation) |
| [CartJ](block:CartJ) | 1-junction | the cart's twist, shared by the rail's child, the cart body and the first pivot |
| [Cart](block:Cart) | `RigidBody2D` | {P.m_cart:g} kg, $J = {P.J_cart:g}$ kg m²; inertia, Coriolis and gravity wrench in one composite |
| {link_list} | `Revolute2DCompliant` | the pendulum joints; exact angle $q$, pivot translations stiff springs ($k_t = 10^8$ N/m, $b_t = 10^3$ N s/m), viscous friction $b$ on the joint |
| Link1 to Link{n} | `FixedJoint2D` | the constant offset from the pivot to the link's centre of mass |
| N1 to N{n} | 1-junctions | each link's twist, shared by the link body, its fixed joint and the next joint's parent |
| {body_list} | `RigidBody2D` | the rods: mass, inertia about the centre of mass, gravity |
| Passive1 to Passive{n} | `Se` with $e = 0$ | closes the joint drive ports: the joints are not actuated |
| [Push](block:Push) | `ExternalWrenchPlanar` | the disturbance force perpendicular to the tip link and its moment about the centre of mass |

**Why compliant pivots.** A rigid revolute joint on a rigid 3-DOF body is an index-3 constraint problem. `Revolute2DCompliant` keeps the joint angle exact and replaces the two pivot translation constraints by a very stiff spring-damper, so every state stays integral and the model is a plain ODE with a $\\sqrt{{k_t/m}} \\approx 10^4$ rad/s pivot mode that the implicit solver (Rodas5P) handles. The trajectory error is of order $1/k_t$ (measured in [the results](page:results)). The cart's rotation and perpendicular motion are held the same way ($k_r = {P.kr_rail:g}$ N m/rad, $k_d = {P.kd_rail:g}$ N/m).

**Bond directions matter.** A bond's half arrow sets the sign of the junction equations, so every joint's `parent` port is bonded *towards* the junction of the body it hangs from (`Joint.parent → N`), like every other element port. The opposite direction produces a plant whose reaction forces on the cart have the wrong sign.

**Poses.** The poses are composed, never integrated: [Rail](block:Rail) outputs the cart pose, every joint outputs $(q, r_x, r_y)$, `ComposePose2D` chains them and `LocalPose2D` adds the centre-of-mass offsets. The body gravity reads its composed world pose, and the scene bindings of the 3D view read the same joint signals.

**Drive train.** The electrical side is [Motor](block:Motor) (`ElectricDrive`: voltage source, winding resistance and inductance, back-EMF gyrator, rotor inertia, bearing loss), then [Gear](block:Gear) (ideal ratio {P.N:g}), [Pulley](block:Pulley) (`RackAndPinion`, radius {P.r * 1000:g} mm: torque to belt force) and [Belt](block:Belt) (a spring-damper, so the rotor inertia is not a derivative-causal store). The domain-concrete ports of the drive train are joined by wires, the junctions by bonds.

**Firmware.** [Traj](block:Traj) is a continuous block: `interp1` is an equation-scope intrinsic, so the 10 ms tables of the nominal state, the feed-forward voltage and the TVLQR gains are looked up there. [Ctrl](block:Ctrl) is the `@discrete Ts = 1e-3` block: it samples the encoders ($x$, $v$, $q_i$, $\\dot q_i$) and the lookup outputs, forms the absolute angles, and sets the voltage of [Motor](block:Motor).
""")

    # ------------------------------------------------------------------ dynamics
    D.page("dynamics", "Equations of motion", f"""
# Equations of motion

The design model of `design/cartpend.py` is the Lagrangian of the same mechanism. The coordinates are the cart position $x$ and the **absolute** link angles $\\theta_1 \\ldots \\theta_{n}$ from the upward vertical, counter-clockwise; link $i$ points along $u_i = (-\\sin\\theta_i, \\cos\\theta_i)$.

$$p_i = p_{{i-1}} + L_{{i-1}} u_{{i-1}}, \\qquad p_1 = (x, 0), \\qquad c_i = p_i + \\ell_i u_i$$

with link length $L_i$ and centre-of-mass distance $\\ell_i = L_i / 2$. With $m_{{\\mathrm{{eff}}}} = m_{{\\mathrm{{cart}}}} + J_m (N/r)^2$ (the rotor inertia reflected through the {P.N:g}:1 gearbox and the pulley):

$$T = \\tfrac12 m_{{\\mathrm{{eff}}}} \\dot x^2 + \\sum_i \\left( \\tfrac12 m_i \\lvert \\dot c_i \\rvert^2 + \\tfrac12 J_i \\dot\\theta_i^2 \\right), \\qquad V = g \\sum_i m_i\\, c_{{i,y}}$$

The Euler-Lagrange equations $M(q)\\ddot q = Q + \\partial_q L - \\dot M \\dot q$ have the generalised forces

$$Q = \\begin{{bmatrix}} \\alpha V - \\beta \\dot x \\\\ 0 \\end{{bmatrix}} - \\partial_{{\\dot q}} \\left( \\tfrac12 \\sum_i b_i (\\dot\\theta_i - \\dot\\theta_{{i-1}})^2 \\right) + J_{{\\mathrm{{tip}}}}^{{\\top}} F_d\\, n_\\perp$$

where the motor acts on the cart only. With the armature inductance neglected (the electrical time constant is $L/R = {P.L_m / P.R_m * 1e3:.2f}$ ms):

$$\\alpha = \\frac{{k_t N}}{{r R}} = {P.alpha:.4g}\\ \\mathrm{{N/V}}, \\qquad \\beta = \\left( \\frac{{k_t^2}}{{R}} + b_m \\right) \\frac{{N^2}}{{r^2}} = {P.beta:.4g}\\ \\mathrm{{N\\,s/m}}$$

so a shorted motor ($V = 0$) is a viscous damper of {P.beta:.1f} N s/m on the cart. $F_d$ is the disturbance force on the tip link, perpendicular to it ($n_\\perp = (-\\cos\\theta_n, -\\sin\\theta_n)$), applied at the tip.

The state is $z = [x, \\theta_1 \\ldots \\theta_{n}, \\dot x, \\dot\\theta_1 \\ldots \\dot\\theta_{n}]$ ({nx} states) and the input is the motor voltage $V$. The bond graph has the same degrees of freedom but also the stiff pivot, belt and winding states, which the design model replaces by their quasi-static limits. Its joint angles relate to $\\theta$ by $q_1 = \\theta_1 + \\pi/2$ and $q_j = \\theta_j - \\theta_{{j-1}}$ (the quantities [Joint1](block:Joint1) etc. report).

The `{kind}-cart-free` model checks that the two agree: it releases the plant from rest at $\\theta = ({", ".join(f"{v:g}" for v in sc.free_th0)})$ rad, $x = {sc.free_x0:g}$ m with the motor shorted and compares the angles with this ODE (maximum difference {dth:.2e} rad over {sc.free_t:g} s, see [the results](page:results)).
""")

    # ------------------------------------------------------------------ trajectory
    D.page("trajectory", "Trajectory optimisation", f"""
# Trajectory optimisation

`design/design.py` computes the swing-up offline by **direct collocation** on the design model of [the equations of motion](page:dynamics), including the motor and its voltage limit, with CasADi and IPOPT (`uv run`, inline script metadata).

**Problem.** Find the states $z_k$ and voltages $V_k$ at $K = {sc.k_int}$ equal intervals of length $h = T_s / K = {sc.t_s / sc.k_int * 1000:.1f}$ ms, $T_s = {sc.t_s:g}$ s:

$$\\min \\; \\int_0^{{T_s}} V^2\\, dt + w \\sum_k (V_{{k+1}} - V_k)^2$$

subject to

- the **Hermite-Simpson** defect constraints $z_{{k+1}} - z_k - \\tfrac h6 (f_k + 4 f_{{k+1/2}} + f_{{k+1}}) = 0$ with $z_{{k+1/2}} = \\tfrac12 (z_k + z_{{k+1}}) + \\tfrac h8 (f_k - f_{{k+1}})$ and the voltage piecewise linear;
- start: all links hanging ($\\theta_i = -\\pi$), at rest, cart at the rail centre; end: all links upright, everything at rest, $x = 0$;
- the **rail limit** $\\lvert x \\rvert \\le {sc.x_lim:g}$ m (the rail ends at ±{P.x_rail:g} m, so the tracking error has {P.x_rail - sc.x_lim:g} m of room);
- the **voltage limit** $\\lvert V \\rvert \\le {sc.u_lim:g}$ V ({sc.u_lim / P.u_max * 100:.0f} % of the {P.u_max:g} V supply, so the feedback has headroom).

The start guess is a half-cosine blend of every angle from hanging to upright with a small cart oscillation. The solution reaches the upright without ever touching the rail end stops: the cart reaches ±{np.abs(traj["Z"][0]).max():.2f} m of the ±{sc.x_lim:g} m bound and the feed-forward needs at most {np.abs(traj["U"]).max():.1f} V of the {sc.u_lim:g} V bound.

{figs["swingup"]}

The dashed lines are the optimised trajectory and the coloured lines the bond-graph run under TVLQR: they agree to within a few mrad, and the applied voltage (grey) follows the feed-forward (orange) plus the feedback correction. The optimiser pumps energy into the links with a few cart strokes before the final lift.

**Resolution.** Hermite-Simpson needs a fine grid for the fast {kind} pendulum: {sc.k_int} intervals ({sc.t_s / sc.k_int * 1000:.0f} ms) track in the bond graph with the correction of the feedback alone. The tables of the controller hold the nominal state and the feed-forward at every 10 ms and are interpolated linearly.
""")

    # ------------------------------------------------------------------ control
    D.page("control", "TVLQR and LQR", f"""
# TVLQR and LQR

## Time-varying LQR along the swing-up

Linearising the design model along the trajectory gives $A(t) = \\partial_z f$, $B(t) = \\partial_V f$ at $(z^*(t), V^*(t))$. The backward Riccati equation

$$-\\dot P = Q + A^{{\\top}} P + P A - P B R^{{-1}} B^{{\\top}} P, \\qquad P(T_s) = P_{{\\mathrm{{LQR}}}}$$

with the terminal condition of the infinite-horizon problem gives the gain $K(t) = R^{{-1}} B^{{\\top}} P(t)$ and the control law

$$V = V^*(t) - K(t)\\, \\bigl( z - z^*(t) \\bigr), \\qquad t \\in [t_{{\\mathrm{{on}}}},\\, t_{{\\mathrm{{on}}}} + T_s],$$

clamped to ±{P.u_max:g} V. The gains are stored with the trajectory in [Traj](block:Traj) (10 ms knots). Because $K(T_s) = K_{{\\mathrm{{LQR}}}}$ the hand-over to the balance controller is smooth.

{figs["gains"]}

## Balance LQR

At $\\tau = t - t_{{\\mathrm{{on}}}} \\ge T_s$ the firmware latches phase 2 and applies $V = -K_{{\\mathrm{{lqr}}}}\\, z$, the **discrete** infinite-horizon LQR of the linearisation at the upright, sampled with a zero-order hold at 1 ms (`scipy.linalg.solve_discrete_are`). The weights are

$$Q = \\mathrm{{diag}}({", ".join(f"{v:g}" for v in np.diag(sc.Q))}), \\qquad R = {sc.R:g}\\ \\mathrm{{V}}^{{-2}}$$

on $[x, \\theta_1 \\ldots \\theta_{n}, \\dot x, \\dot\\theta_1 \\ldots \\dot\\theta_{n}]$. The cart position and velocity are weighted heavily: this is what widens the basin of attraction against a pulse (in the design study, light cart weights lost the pendulum to much smaller pulses). The largest gain is {np.abs(tab.Klqr).max():.0f} V per rad or per m.

## The switching rule and the phase signal

The mode is latched in the firmware (a discrete variable that only increases):

| mode | condition | law |
| --- | --- | --- |
| 0 | $t < t_{{\\mathrm{{on}}}}$ | $V = 0$ |
| 1 | $t_{{\\mathrm{{on}}}} \\le t < t_{{\\mathrm{{on}}}} + T_s$ | feed-forward plus TVLQR |
| 2 | $t \\ge t_{{\\mathrm{{on}}}} + T_s$ | discrete LQR, until the end |

[Ctrl/phase](signal:Ctrl/phase) records the mode. The catch is time-based, not state-based: the nominal trajectory ends upright at rest, the TVLQR has driven the error to a few $10^{{-4}}$ rad by then, so the switch is bumpless. Every output is clamped to ±{P.u_max:g} V inside the firmware (`clamp` in `@discrete` is generated code, not an event).
""")

    # ------------------------------------------------------------------ results
    defl = ", ".join(f"{v:.1f}" for v in M["defl_deg"])
    D.page("results", "Results and checks", f"""
# Results and checks

All numbers are from the real Julia worker (Rodas5P, `reltol` 1e-8); the design column is the closed loop of the Lagrangian model under the same 1 kHz firmware.

{figs["pulse"]}

| quantity | value |
| --- | --- |
| at rest before $t_{{\\mathrm{{on}}}}$ | max angle change {M["rest_dth"]:.1e} rad, cart {M["rest_dx"]:.1e} m |
| swing-up time (all links inside 2° for good) | {M["t_swingup"]:.2f} s after $t_{{\\mathrm{{on}}}}$ |
| catch (phase 2) | at {M["t_catch"]:.2f} s |
| upright band from 0.1 s after the catch to the pulse | {M["band_deg"]:.3f}° (cart within {M["band_x"] * 1000:.1f} mm) |
| pulse: peak deflection of each link (deg) | {defl} |
| pulse: peak cart travel | {M["defl_x"]:.3f} m |
| recovery (all links inside 1° / 0.5° for good) | {M["t_rec1"]:.2f} s / {M["t_rec"]:.2f} s after the pulse |
| last second | all links within {M["end_deg"]:.3f}° |
| peak motor voltage | {M["u_peak"]:.2f} V of {P.u_max:g} V |
| peak cart travel | {M["x_peak"]:.3f} m of the rail's {P.x_rail:g} m |

## The design model against the bond graph

{figs["free"]}

The free swing of `{sc.model}-free` ({sc.free_t:g} s from rest at a pose far from equilibrium, motor shorted) agrees with the design ODE to **{dth:.2e} rad** (cart: {dx:.1e} m). The residual is the stiff pivot ($O(1/k_t)$), the winding inductance, the belt and the pivot damping. The same design model produces the swing-up trajectory and the gains, which is why the bond-graph run tracks it.

## Acceptance checks (`expected.json`)

- hold: no motion and 0 V before $t_{{\\mathrm{{on}}}}$; the phase signal [Ctrl/phase](signal:Ctrl/phase) is 0, 1, 2 at the three phases;
- swing-up: {sigs} at three times match the design closed loop (tolerance 0.01 rad);
- balance: every link stays within 0.2° of upright from 0.1 s after the catch to the pulse, and the cart within 1 cm of the rail centre;
- disturbance: the peak deflections after the pulse are above the minimum (the pulse is real), the cart travel is bounded;
- recovery: back inside 0.5° after {M["t_rec"]:.1f} s, within 0.2° and 1 cm over the last second;
- actuator and rail: $\\lvert V \\rvert \\le {P.u_max:g}$ V (peak {M["u_peak"]:.1f} V), cart inside ±{P.x_rail:g} m (peak {M["x_peak"]:.3f} m);
- the free-swing model against the design ODE at eight times (angles within 3e-3 rad, cart 2e-4 m);
- the scene bindings of the 3D view, and no diagnostics at all.
""")
    D.manifest([("overview", [("structure", []), ("dynamics", []), ("trajectory", []), ("control", []), ("results", [])])])
    return M, dth, dx
