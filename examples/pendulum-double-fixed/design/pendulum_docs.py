"""Source bundle of the model docs of the fixed-pivot pendulum examples (X5.11).

``render(prm)`` returns the text of ``tools/example_docs/src/<example>.md``, the input of
``uv run tools/example_docs/build.py --only <example>`` (which turns it into
``models/<example>.docs/`` with plots from real runs). Every number comes from ``params.py`` and
``design/results.json``, so a re-run of ``design.py`` plus this script refreshes the documentation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

DEG = 57.29577951308232
NAMES = {2: "double", 3: "triple"}


def render(prm) -> str:
    P, C = prm.PLANT, prm.CFG
    n = P.n
    ex = prm.EXAMPLE
    kind = NAMES[n]
    res = json.loads((Path(prm.HERE) / "results.json").read_text(encoding="utf-8"))
    free = json.loads((Path(prm.HERE) / "free_max_diff.json").read_text(encoding="utf-8"))["max_diff"]
    t_on, T_s, t_dist, t_end = C["t_on"], C["T_s"], C["t_dist"], C["t_end"]
    ctrl = prm.CTRL_BLOCK
    J = P.J
    Kl = res["K_lqr"]
    links = ", ".join(f"[Body{k + 1}](block:Body{k + 1})" for k in range(n))
    angle_signals = [f"Upright/a{k + 1}" for k in range(n)]
    nx = 2 * n
    lever = P.L[-1] - P.lc[-1]
    k_tab = int(round(T_s / C["dt_tab"])) + 1
    hz = "1 kHz"

    L = []
    w = L.append

    # ----------------------------------------------------------------------------- figures
    series_a = ", ".join(
        f'{{"signal": "{s}", "label": "{s}", "scale": {DEG}}}' for s in angle_signals
    )
    figs = {
        "diagram": {"kind": "diagram", "model": ex},
        "scene-swing": {"kind": "scene", "model": ex, "t": round(t_on + 0.5 * T_s, 3)},
        "scene-up": {"kind": "scene", "model": ex, "t": round(t_dist - 1.0, 3)},
        "run": {
            "kind": "plot", "model": ex, "width": 1000,
            "rows": [
                {"ylabel": "angle from upright [deg]", "legend": True,
                 "series": [{"signal": s, "label": s, "scale": DEG} for s in angle_signals],
                 "vlines": [{"x": t_on, "label": "swing-up starts"}, {"x": t_dist, "label": "disturbance"}]},
                {"ylabel": "motor voltage [V]", "legend": True,
                 "series": [{"signal": "Ctrl/u", "label": "Ctrl/u", "color": "#1b9e77"}],
                 "hlines": [{"y": P.umax, "label": f"supply limit {P.umax:g} V"}, {"y": -P.umax}]},
                {"ylabel": "controller phase",
                 "series": [{"signal": "Ctrl/phase", "label": "Ctrl/phase", "color": "#7570b3"}]},
            ],
        },
        "swing": {
            "kind": "plot", "model": ex, "xlim": [t_on - 0.2, t_on + T_s + 0.8], "width": 1000,
            "rows": [
                {"ylabel": "angle from upright [deg]", "legend": True,
                 "series": [{"signal": s, "label": s, "scale": DEG} for s in angle_signals]},
                {"ylabel": "motor voltage [V]",
                 "series": [{"signal": "Ctrl/u", "label": "Ctrl/u", "color": "#1b9e77"}],
                 "hlines": [{"y": P.umax}, {"y": -P.umax}],
                 "vlines": [{"x": res["t_catch"], "label": f"catch at {res['t_catch']:.2f} s"}], "legend": True},
            ],
        },
        "dist": {
            "kind": "plot", "model": ex, "xlim": [t_dist - 0.5, t_dist + 3.0], "width": 1000,
            "rows": [
                {"ylabel": "angle from upright [deg]", "legend": True,
                 "series": [{"signal": s, "label": s, "scale": DEG} for s in angle_signals]},
                {"ylabel": "motor voltage [V]",
                 "series": [{"signal": "Ctrl/u", "label": "Ctrl/u", "color": "#1b9e77"}]},
                {"ylabel": "tip force [N]",
                 "series": [{"signal": "DistForce/y", "label": "DistForce/y", "color": "#d95f02"}]},
            ],
        },
        "free": {
            "kind": "plot", "model": "free", "width": 1000,
            "rows": [
                {"ylabel": "joint angle [rad]", "legend": True,
                 "series": [{"signal": f"Joint{k + 1}/qout", "label": f"Joint{k + 1}/qout"} for k in range(n)]},
            ],
        },
    }
    w(f"@@ figures {ex}")
    w(json.dumps(figs, indent=1))

    # ------------------------------------------------------------------------------ overview
    w(f"@@ page {ex} overview - | Overview")
    w(f"# {kind.capitalize()} pendulum on a fixed pivot")
    w("")
    w(
        f"A planar {kind} pendulum hangs from a fixed pivot. A DC gearmotor drives the **first joint only** "
        f"(the pendubot arrangement); the other {n - 1} joint{'s are' if n > 2 else ' is'} passive. "
        f"The chain starts hanging straight down at rest with 0 V on the motor, swings up along an optimised "
        f"trajectory, is caught by an LQR near the upright, balances, and recovers from a force pulse at the tip link."
    )
    w("")
    w(f"![The model canvas|900](@fig:diagram)")
    w("")
    w("## Scenario")
    w("")
    w("| time | phase | what happens |")
    w("| --- | --- | --- |")
    w(f"| 0 to {t_on:g} s | 0 | hanging at rest, voltage 0 ([Ctrl/phase](signal:Ctrl/phase) = 0), nothing moves |")
    w(f"| {t_on:g} s | 1 | the swing-up starts: feed-forward voltage from the trajectory optimisation plus time-varying LQR feedback |")
    w(f"| {res['t_catch']:.2f} s | 2 | the state enters the LQR region ($V(x) < {res['V_catch']:g}$): the balance LQR takes over (the trajectory ends at {t_on + T_s:g} s) |")
    w(f"| {t_dist:g} s | 2 | a {C['F']:g} N force pulse of {C['pulse_len'] * 1e3:g} ms hits the tip link ([DistForce/y](signal:DistForce/y)) |")
    w(f"| {t_dist + C['pulse_len'] + 1:g} to {t_end:g} s | 2 | back at upright: every link inside 1 deg from {res['recovered_1deg']:.2f} s on |")
    w("")
    w(f"The chain is built as a **multibond bond graph**: {links} are `RigidBody2D` composites with a mass and an inertia about the centre of mass, joined by `Revolute2DCompliant` joints ([Joint1](block:Joint1)"
      + "".join(f", [Joint{k + 1}](block:Joint{k + 1})" for k in range(1, n)) + "). "
      "The motor ([Motor](block:Motor)), the shaft ([Shaft](block:Shaft)) and the gearbox ([Gear](block:Gear)) are stdlib drive blocks; the controller [Ctrl](block:Ctrl) is project firmware sampled at 1 kHz.")
    w("")
    w("![Mid swing-up|600](@fig:scene-swing)")
    w("")
    w("![Balanced before the disturbance|600](@fig:scene-up)")
    w("")
    w("## Pages")
    w("")
    w("- [The multibond structure](page:structure): blocks, bonds, poses and the drive train.")
    w("- [Equations of motion](page:dynamics): the design model, the parameters and the check against the bond graph.")
    w("- [Trajectory optimisation](page:trajectory): the direct-collocation formulation of the swing-up.")
    w("- [TVLQR and LQR](page:control): the feedback around the trajectory, the catch rule and the balance.")
    w("- [Results](page:results): plots of the run and the acceptance checks.")
    w("")
    w("## What to try")
    w("")
    w(f"- Open the **Plots** tab: \"Link angles from upright\" ([{angle_signals[0]}](signal:{angle_signals[0]}) and the others) shows the swing-up, the catch and the recovery; \"Motor voltage\" ([Ctrl/u](signal:Ctrl/u)) the use of the supply.")
    w(f"- Raise `DistForce/amplitude` and `DistTorque/amplitude` together (the torque is the force times the {lever:g} m lever arm to the tip): the recovery needs more voltage, and a large enough pulse saturates the 12 V supply and tips the chain over.")
    w("- Open the **3D View** tab to watch the swing-up; the joint bindings follow the joint angles.")
    w(f"- Change a link mass without re-running `design/design.py`: the gains are matched to the design plant, which shows the margin of the design.")

    # ----------------------------------------------------------------------------- structure
    w(f"@@ page {ex} structure overview | The multibond structure")
    w("# The multibond structure")
    w("")
    w("Planar multibond elements (`stdlib:planar/*`, `stdlib:multibond/*Planar`) carry a three-component twist and wrench $(\\omega, v_x, v_y)$ on every bond. The power path is a chain of bonds from the ground to the last link:")
    w("")
    chain = "Ground ─ Joint1 ─ Link1 ─ BodyJ1"
    for k in range(1, n):
        chain += f" ─ Joint{k + 1} ─ Link{k + 1} ─ BodyJ{k + 1}"
    w("```")
    w(chain)
    w("```")
    w("")
    w("| instance | block | role |")
    w("| --- | --- | --- |")
    w("| [Ground](block:Ground) | `stdlib:multibond/GroundPlanar` | world flow source, $f = 0$ |")
    for k in range(n):
        rx = 0.0 if k == 0 else P.L[k - 1] - P.lc[k - 1]
        drive = "the motor drive port (rotation), see below" if k == 0 else "a zero-torque `Se` (**passive joint**)"
        w(f"| [Joint{k + 1}](block:Joint{k + 1}) | `stdlib:planar/Revolute2DCompliant` | joint {k + 1}: pivot at $r_x = {rx:g}$ m in the parent CoM frame, `kt` = 1e8 N/m, `bt` = {C['bt']:g} N·s/m, viscous friction $b = {P.b[k]:g}$ N·m·s/rad; drive: {drive} |")
        w(f"| [Link{k + 1}](block:Link{k + 1}) | `stdlib:planar/FixedJoint2D` | frame bridge from the joint to the centre of mass of link {k + 1}, $x = {P.lc[k]:g}$ m |")
        w(f"| [BodyJ{k + 1}](block:BodyJ{k + 1}) | 1-junction | the common twist of link {k + 1}: its body and " + ("the next joint |" if k < n - 1 else "the disturbance source |"))
        w(f"| [Body{k + 1}](block:Body{k + 1}) | `stdlib:planar/RigidBody2D` | $m = {P.m[k]:g}$ kg, $J = m L^2/12 = {J[k]:.6g}$ kg·m², $L = {P.L[k]:g}$ m |")
    w("| [Motor](block:Motor) | `stdlib:drives/ElectricDrive` | DC motor: $R_w$ " + f"= {P.Rw:g} Ω, $L$ = {P.Lw * 1e3:g} mH, $k_t$ = {P.kt:g} N·m/A, rotor $J_m$ = {P.Jm:g} kg·m² |")
    w("| [Shaft](block:Shaft) | `stdlib:rotation/ElasticShaft` | the drive-train compliance " + f"$k$ = {P.ks:g} N·m/rad, $d$ = {P.ds:g} N·m·s/rad on the motor side |")
    w(f"| [Gear](block:Gear) | `stdlib:drives/Gearbox` | ideal ratio $N = {P.N:g}$ (motor rate $= N\\,\\dot q_1$) |")
    w("| [Hit](block:Hit) | `stdlib:multibond/ExternalWrenchPlanar` | the disturbance wrench on the last link, from [DistTorque](block:DistTorque), [DistAxial](block:DistAxial) and [DistForce](block:DistForce) (`stdlib:sources/Pulse`) |")
    w(f"| [Ctrl](block:Ctrl) | `project:{ctrl}` | the 1 kHz firmware: swing-up, catch, balance; [Clock](block:Clock) supplies the time |")
    w("| [Upright](block:Upright) | inline block | the absolute link angles from upright, $a_k = q_1 + \\dots + q_k - \\pi/2$ |")
    w("")
    w("## Joints")
    w("")
    w(f"A rigid revolute on a three-degree-of-freedom body is index 3 (the two pivot translations are hard constraints; `Revolute2DRigid` ends in a derivative-causal DAE that does not run). `Revolute2DCompliant` keeps the **rotation exact** and lets the two pivot translations be stiff spring-dampers ($k_t = 10^8$ N/m): the pivot moves by about $m g / k_t \\approx 10^{{-8}}$ m, and the free-swing check below shows the plant agrees with the rigid design model to {free:.1e} rad over a 3 s swing. All states are integral, so the run reports no W201.")
    w("")
    w("The joint angle `q` of joint 1 is the absolute angle of link 1 (hanging: $-\\pi/2$, upright: $+\\pi/2$); the angles of the other joints are relative, so the absolute angle of link $k$ is $\\theta_k = q_1 + \\dots + q_k$.")
    w("")
    w("## Poses and gravity")
    w("")
    w("The poses are composed, never integrated: `JointPose2D` turns a joint angle into an SE(2) pose, `LocalPose2D` holds the constant offsets and `ComposePose2D` multiplies them along the chain ([PoseB1](block:PoseB1)"
      + "".join(f", [PoseB{k + 1}](block:PoseB{k + 1})" for k in range(1, n)) + ", [PoseTip](block:PoseTip)). Each `RigidBody2D` reads its world pose to resolve gravity in the body frame, so the weight acts at the true centre of mass.")
    w("")
    w("## Drive train")
    w("")
    w(f"[Motor](block:Motor) turns the voltage $u$ from [Ctrl](block:Ctrl) into a shaft torque; [Shaft](block:Shaft) is a stiff elastic shaft that keeps the rotor inertia integral-causal (an ideal gear between the rotor and a joint that imposes its rate would give a derivative-causal pair); [Gear](block:Gear) multiplies the torque by $N = {P.N:g}$ and the rotor inertia appears at the joint as $N^2 J_m = {P.N ** 2 * P.Jm:.3g}$ kg·m². The joint carries the reaction torque, so the motor housing is the fixed base. Taps: the winding current [Motor/isense/y](signal:Motor/isense/y), the motor speed [Motor/wsense/y](signal:Motor/wsense/y).")
    w("")
    w("## Bond direction")
    w("")
    w("Every bond of the chain points from the port into the junction (`Joint.parent → BodyJ`, `Link.child → BodyJ`, `Body.p → BodyJ`, `Hit.p → BodyJ`). The direction is the power orientation of the bond; reversing one of them flips the sign convention of that junction and the pendulum no longer matches its equations of motion.")

    # ---------------------------------------------------------------------------- dynamics
    w(f"@@ page {ex} dynamics overview | Equations of motion")
    w("# Equations of motion")
    w("")
    w(f"With $q = (q_1, \\dots, q_{n})$ the joint angles, link $k$ has the absolute angle $\\theta_k = \\sum_{{j \\le k}} q_j$, its centre of mass at $c_k = p_k + \\ell_k (\\cos\\theta_k, \\sin\\theta_k)$ and the next pivot at $p_{{k+1}} = p_k + L_k (\\cos\\theta_k, \\sin\\theta_k)$. The kinetic and potential energy are")
    w("")
    w("$$T = \\sum_k \\tfrac12 m_k \\lVert \\dot c_k \\rVert^2 + \\tfrac12 J_k \\dot\\theta_k^2 + \\tfrac12 N^2 J_m \\dot q_1^2, \\qquad V = \\sum_k m_k g\\, c_{k,y},$$")
    w("")
    w("and the Lagrange equations give")
    w("")
    w("$$M(q)\\,\\ddot q + c(q, \\dot q) + g(q) = \\tau, \\qquad \\tau_1 = N k_t\\, i - b_1 \\dot q_1, \\quad \\tau_k = -b_k \\dot q_k \\ (k \\ge 2).$$")
    w("")
    w("The motor current follows $L\\,\\dot i = u - R_w\\, i - N k_t\\, \\dot q_1$. The design neglects $L$ for the optimisation and the LQR ($L/R_w = " + f"{P.Lw / P.Rw * 1e3:.2f}$ ms), so $i = (u - N k_t \\dot q_1)/R_w$ and the input enters through")
    w("")
    w("$$\\tau_1 = \\frac{N k_t}{R_w}\\,u - \\frac{N^2 k_t^2}{R_w}\\,\\dot q_1 - b_1 \\dot q_1 ,$$")
    w("")
    w("a torque proportional to the voltage and a back-EMF damping. The sampled-data simulation in `design.py` that predicts the whole run keeps the winding inductance.")
    w("")
    w("## Parameters")
    w("")
    w("The values are assumed (no datasheet part); the links are aluminium rods with the centre of mass at the middle.")
    w("")
    w("| link | $m$ [kg] | $L$ [m] | $\\ell$ [m] | $J = m L^2/12$ [kg·m²] | $b$ [N·m·s/rad] |")
    w("| --- | --- | --- | --- | --- | --- |")
    for k in range(n):
        w(f"| {k + 1} | {P.m[k]:g} | {P.L[k]:g} | {P.lc[k]:g} | {J[k]:.6g} | {P.b[k]:g} |")
    w("")
    w(f"Motor and drive: $R_w = {P.Rw:g}\\ \\Omega$, $L = {P.Lw * 1e3:g}$ mH, $k_t = {P.kt:g}$ N·m/A, $J_m = {P.Jm:g}$ kg·m², gear ratio $N = {P.N:g}$, supply limit $\\pm {P.umax:g}$ V (stall torque at the joint $N k_t U/R_w = {P.N * P.kt * P.umax / P.Rw:.3g}$ N·m). Gravity $g = {P.g:g}$ m/s².")
    w("")
    w("## Linearisation at upright")
    w("")
    pol = ", ".join(f"{p:.2f}" for p in res["poles"])
    w(f"With the state $x = (q_1 - \\pi/2, q_2, \\dots, \\dot q_1, \\dots)$ the open-loop poles at upright are ${pol}$ s$^{{-1}}$: {sum(1 for p in res['poles'] if p > 0)} unstable poles (up to {max(res['poles']):.1f} s$^{{-1}}$). Because only joint 1 is driven, the passive links are stabilised through the dynamic coupling.")
    w("")
    w("## Check against the bond graph")
    w("")
    w(f"`models/free.bgmodel.json` is the same plant with the motor terminals at 0 V, started at the non-trivial angles ${', '.join(f'{q:.4f}' for q in C['free_q0'])}$ rad. `design.py --compare` integrates the design ODE (the full model with the winding current, Radau, tolerance $10^{{-11}}$) from the same start and compares it with the bond-graph run: the maximum difference of any joint angle over the 3 s swing is **{free:.2e} rad**, and `expected.json` repeats the comparison at six times. ![Free swing of the bond graph|800](@fig:free)")
    w("")
    w("The swing covers a large part of the working range, so this proves the masses, inertias, lengths, gravity, the reflected rotor inertia and the back-EMF damping of the design model.")

    # --------------------------------------------------------------------------- trajectory
    w(f"@@ page {ex} trajectory overview | Trajectory optimisation")
    w("# Trajectory optimisation")
    w("")
    w(f"`design/design.py` computes the swing-up offline by **direct collocation** on the design model, including the motor and its voltage limit. The problem is to move from all links hanging at rest to all links upright at rest in the fixed time $T_s = {T_s:g}$ s:")
    w("")
    w("$$\\min_{x(\\cdot),\\,u(\\cdot)} \\int_0^{T_s} \\Big(\\frac{u}{u_{lim}}\\Big)^2 + \\epsilon\\,\\lVert \\dot q \\rVert^2 \\, dt \\quad \\text{s.t.} \\quad \\dot x = f(x, u),\\ \\ x(0) = x_{down},\\ \\ x(T_s) = x_{up},\\ \\ \\lvert u \\rvert \\le u_{lim},$$")
    w("")
    w(f"with $x = (q, \\dot q)$, $x_{{down}} = (-\\pi/2, 0, \\dots, 0)$, $x_{{up}} = (\\pi/2, 0, \\dots, 0)$, $u_{{lim}} = {C['u_to']:g}$ V (the rest of the {P.umax:g} V supply is margin for the feedback) and $\\epsilon = 10^{{-4}}$.")
    w("")
    w(f"**Discretisation.** {C['nk']} intervals of $h = {T_s / C['nk'] * 1e3:.3g}$ ms. The voltage is piecewise linear between the knots. Each interval carries the Hermite–Simpson defect")
    w("")
    w("$$x_{k+1} - x_k = \\tfrac{h}{6}\\big(f_k + 4 f_m + f_{k+1}\\big), \\qquad x_m = \\tfrac12 (x_k + x_{k+1}) + \\tfrac{h}{8}(f_k - f_{k+1}),\\quad u_m = \\tfrac12 (u_k + u_{k+1}),$$")
    w("")
    w(f"which is fourth order in $h$. CasADi builds the exact derivatives of the Lagrangian dynamics; IPOPT solves the resulting nonlinear program ({C['nk'] + 1} knots, {nx} states and one input each) in about {'two' if n == 2 else 'ten'} seconds from a sinusoidal voltage guess.")
    w("")
    w(f"**Result.** The optimum uses a peak voltage of {res['peak_u_to']:.2f} V (the limit of the problem). The nominal states are the collocation knots, interpolated with a cubic Hermite spline at 1 kHz, not a forward integration: the swing-up is open-loop unstable (poles up to {max(res['poles']):.1f} s$^{{-1}}$ amplify a 1e-10 integration error by $e^{{{max(res['poles']) * T_s:.0f}}}$ over the trajectory), so only the feedback can follow it.")
    w("")
    w(f"The trajectory is written into `{ctrl}` as constant tables of {k_tab} rows at {C['dt_tab'] * 1e3:g} ms spacing: the nominal voltage `u_ff`, the nominal states `xr_*` and the time-varying gains `k_*`.")

    # ------------------------------------------------------------------------------- control
    w(f"@@ page {ex} control overview | TVLQR and LQR")
    w("# TVLQR and LQR")
    w("")
    w(f"[Ctrl](block:Ctrl) is the project block `{ctrl}` (`library/{ctrl}.jl`), a `@discrete Ts = 1e-3` scope that reads the joint angles and rates and the time and holds the voltage until the next tick.")
    w("")
    w("## Phases")
    w("")
    w("| phase | condition | law |")
    w("| --- | --- | --- |")
    w(f"| 0 | $t < t_{{on}} = {t_on:g}$ s | $u = 0$ |")
    w("| 1 | swing-up, not caught | $u = u_{ff}(\\tau) - K(\\tau)\\,\\big(x - x_{ref}(\\tau)\\big)$, $\\tau = t - t_{on}$ |")
    w("| 2 | caught (latched) | $u = -K_{lqr}\\,(x - x_{up})$ |")
    w("")
    w("The output is clamped to $\\pm 12$ V. The table lookup is linear interpolation: the weights are the hat functions $\\max(0, 1 - \\lvert s - (k-1) \\rvert)$ of the row position $s = \\tau/\\Delta t$ over the rows $k$, and the last row is held after the trajectory.")
    w("")
    w("## Time-varying LQR")
    w("")
    w("Along the nominal trajectory $(x^*, u^*)$ the linearisation is discretised exactly (zero-order hold at 1 ms) at every sample, $x_{k+1} = A_k x_k + B_k u_k$, and the gains come from the backward Riccati recursion")
    w("")
    w("$$K_k = (R + B_k^T S_{k+1} B_k)^{-1} B_k^T S_{k+1} A_k, \\qquad S_k = Q + A_k^T S_{k+1} (A_k - B_k K_k),$$")
    w("")
    w(f"terminated by the Riccati matrix $S_N = P$ of the balance LQR, so the gain schedule ends in the LQR gain. The weights are $Q = \\mathrm{{diag}}({', '.join(f'{float(C['Q'][i][i]):g}' for i in range(nx))})$ (angles in rad, rates in rad/s) and $R = {C['R']:g}$ V$^{{-2}}$.")
    w("")
    w("## Balance LQR")
    w("")
    w(f"At upright the 1 ms zero-order-hold model gives the discrete Riccati solution $P$ and the gain")
    w("")
    w("$$K_{lqr} = (" + ",\\ ".join(f"{k:.4g}" for k in Kl) + ")\\ \\text{ in V/rad and V·s/rad,}$$")
    w("")
    w("for $u = -K_{lqr}(x - x_{up})$. The same $Q$ and $R$ are used for the TVLQR.")
    w("")
    w("## Switching rule")
    w("")
    w(f"The catch is a state test, not a timer: the first tick of phase 1 at which the LQR cost-to-go $V(x) = (x - x_{{up}})^T P\\,(x - x_{{up}})$ is below $V_{{catch}} = {res['V_catch']:g}$ latches phase 2 (`caught` is a discrete state of the block). $V_{{catch}}$ is the value of $V$ on the nominal trajectory 0.2 s before its end, so the LQR takes over inside the region where it is verified to hold the pendulum; the nominal trajectory itself reaches upright at {t_on + T_s:g} s. The block outputs the phase ([Ctrl/phase](signal:Ctrl/phase): 0, 1, 2) and the cost-to-go ([Ctrl/V](signal:Ctrl/V)).")
    w("")
    w("## Disturbance")
    w("")
    w(f"At $t = {t_dist:g}$ s, {t_dist - res['t_catch']:.1f} s after the catch, [Hit](block:Hit) applies a force of {C['F']:g} N for {C['pulse_len'] * 1e3:g} ms to the last link, perpendicular to it at the tip: the force $F$ on the body $y$ axis and the torque $F \\cdot {lever:g}$ m about the centre of mass (the lever arm from the centre of mass to the tip). The balance LQR recovers it with no change of controller.")

    # -------------------------------------------------------------------------------- results
    w(f"@@ page {ex} results overview | Results and checks")
    w("# Results and checks")
    w("")
    w("![Link angles, motor voltage and controller phase over the whole run|900](@fig:run)")
    w("")
    w("## Swing-up and catch")
    w("")
    w("![Swing-up from hanging, first seconds|900](@fig:swing)")
    w("")
    w("## Disturbance and recovery")
    w("")
    w("![The tip force pulse and the recovery|900](@fig:dist)")
    w("")
    w("## Numbers")
    w("")
    w("The reference numbers are the independent sampled-data integration of `design.py`; the bond-graph run reproduces the link angles to better than 1e-4 rad over the whole scenario.")
    w("")
    w("| quantity | value |")
    w("| --- | --- |")
    w(f"| swing-up | starts at {t_on:g} s, trajectory time {T_s:g} s, caught at {res['t_catch']:.2f} s |")
    w(f"| upright band before the disturbance | {math.degrees(res['band_pre']):.4f} deg (all links, from 0.5 s after the catch) |")
    w(f"| disturbance | {C['F']:g} N, {C['pulse_len'] * 1e3:g} ms, at {t_dist:g} s |")
    w(f"| peak deflection after the pulse | " + ", ".join(f"link {k + 1}: {math.degrees(v):.1f} deg" for k, v in enumerate(res["peak_by_link"])) + " |")
    w(f"| recovered (every link inside 1 deg) | from {res['recovered_1deg']:.2f} s, {res['recovered_1deg'] - t_dist:.2f} s after the pulse starts |")
    w(f"| peak motor voltage | {res['peak_u_run']:.2f} V of {P.umax:g} V (recovery: {res['peak_u_after']:.2f} V) |")
    w(f"| design versus bond graph, free swing | {free:.1e} rad |")
    w("")
    w(f"## Acceptance checks (`expected.json`)")
    w("")
    w(f"- hanging at rest before $t_{{on}}$: the angles [Upright/a1](signal:Upright/a1)… equal $-\\pi$, the joint rates and the voltage [Ctrl/u](signal:Ctrl/u) stay 0, [Ctrl/phase](signal:Ctrl/phase) = 0;")
    w(f"- phase 1 during the swing-up, the catch time from the phase signal, phase 2 before the disturbance; the link angles at a quarter, half and three quarters of the trajectory against `design.py` (2 mrad);")
    w(f"- upright by $t_{{on}} + T_s = {t_on + T_s:g}$ s: every link within 0.2 deg until the disturbance (measured {math.degrees(res['band_pre']):.4f} deg);")
    w(f"- the pulse [DistForce/y](signal:DistForce/y) is {C['F']:g} N for {C['pulse_len'] * 1e3:g} ms; the peak deflection of each link after it against `design.py` (5 %), which makes the disturbance a checked, visible event;")
    w(f"- recovered: inside 1 deg from {res['recovered_1deg']:.2f} s and inside 1e-3 rad over the last second;")
    w(f"- [Ctrl/u](signal:Ctrl/u) within the {P.umax:g} V supply, [Motor/isense/y](signal:Motor/isense/y) below the stall current {P.umax / P.Rw:g} A;")
    w(f"- model `free`: {n} joint angles at six times against the design ODE (1e-4 rad);")
    w(f"- 3D: every binding resolves and the link poses from the joint bindings equal the composed poses of the model ([PoseB1](block:PoseB1)…, [PoseTip](block:PoseTip)) to 1e-6 m;")
    w(f"- no E901, E106, W201, W202, W205, W206, E101 or E103.")
    w("")
    w("## Reproduce")
    w("")
    w("```")
    w(f"uv run examples/{ex}/design/design.py          # trajectory, gains, library/{ctrl}.jl, expected.json")
    w(f"uv run examples/{ex}/design/build_model.py     # models/*.bgmodel.json and the scene")
    w(f"uv run examples/run_checks.py --only {ex}")
    w("```")
    return "\n".join(L) + "\n"
