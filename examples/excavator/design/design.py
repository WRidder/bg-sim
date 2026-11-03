# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Parameters and independent reference numbers of the excavator example -> design.json.

    uv run examples/excavator/design/design.py        # first
    uv run examples/excavator/design/build_model.py   # then (models, scene, expected.json)

Everything here is computed in Python from the geometry of exc_geom.py, independently of
bg-sim: the joint ranges that correspond to the cylinder strokes, the forward kinematics of
the bucket tip from the cylinder lengths (root finding on the cylinder length of each joint
and of the four-bar), the static cylinder forces from a moment balance, the hydraulic natural
frequency of the boom, the flow-regulated cylinder speeds and the earthmoving-equation factors.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, minimize_scalar

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exc_geom as G  # noqa: E402

D = math.radians
G0 = 9.81

# --------------------------------------------------------------------------- joint ranges
# The cylinder end stops: the joint angles where each cylinder is fully retracted / extended.
# Boom: q1 in [-40, 62] deg; arm: q2 in [-158, -52] deg (relative to the boom line); bucket:
# q3 in [-125, 45] deg (relative to the arm line). Strokes and closed lengths follow.
LIMITS = {"boom": (D(-40.0), D(62.0)), "arm": (D(-158.0), D(-52.0)), "bucket": (D(-125.0), D(45.0))}
REF = (D(30.0), D(-110.0), D(-40.0))        # the other joints while one range is evaluated

# --------------------------------------------------------------------------- mass properties
# A documented, consistent set for a 20-t class front. The total of boom, arm and bucket,
# 3606 kg, is the "mass of boom, arm and bucket" of the 20-ton excavator of Jin et al. (2024);
# the split and the centres of mass are ours (boom and arm include their share of the
# cylinders and pins, the bucket its linkage). Centre-of-mass inertias of slender links,
# J ~ m (l^2 + h^2)/12, rounded.
BODIES = {
    "boom": {"m": 1650.0, "c": (2.75, 0.40), "J": 4600.0},
    "arm": {"m": 1000.0, "c": (1.05, 0.08), "J": 820.0},
    "bucket": {"m": 956.0, "c": (0.62, 0.22), "J": 260.0},
}
PAYLOAD = {"m": 1500.0, "c": (0.70, 0.25), "J": 150.0}    # 0.93 m^3 heaped, loose soil 1.6 t/m^3

# --------------------------------------------------------------------------- hydraulics
# Boom: two cylinders bore 120 / rod 85 mm (Jin et al. 2024: A1 = 11310 mm^2, A2 = 5635 mm^2
# per cylinder), modelled as one cylinder with twice the areas. Arm 140/100 and bucket
# 120/85 mm are typical 20-t sizes (assumed).
def areas(bore, rod, n=1):
    a = math.pi / 4 * bore ** 2
    return n * a, n * (a - math.pi / 4 * rod ** 2)


CYL = {
    "boom": {"bore": 0.120, "rod": 0.085, "n": 2, "V0": 2.0e-3, "Fc": 3000.0, "Fv": 2.0e4},
    "arm": {"bore": 0.140, "rod": 0.100, "n": 1, "V0": 1.2e-3, "Fc": 2000.0, "Fv": 1.0e4},
    "bucket": {"bore": 0.120, "rod": 0.085, "n": 1, "V0": 1.0e-3, "Fc": 1500.0, "Fv": 8.0e3},
}
HYD = {
    "beta": 1.2e9,          # effective bulk modulus (oil with hoses), Pa
    "rho": 870.0,           # oil density, kg/m^3
    "p_tank": 1.0e5,        # tank / return line, Pa
    "w_engine": 1800 * 2 * math.pi / 60,    # constant engine speed, rad/s
    "D_pump": 220e-6 / (2 * math.pi),       # 220 cm^3/rev at full stroke, m^3/rad
    "eta_v": 0.95, "eta_m": 0.92, "p_nom": 3.0e7,
    "dp_ls": 2.5e6,         # LS margin
    "dp_reg": 2.0e5,        # regulation range of the LS regulator
    "p_cut": 3.2e7,         # pressure cut-off
    "P_max": 100e3,         # pump power limit at the engine speed (torque limiter), W
    "p_relief": 3.43e7,     # main relief
    "V_pump": 3.0e-3,       # pump line (pump, hoses, valve inlet gallery)
    "V_sec": 3.0e-4,        # between a section's compensator and its spool
    "dp_c": 1.0e6,          # compensator setting of the pre-compensated sections
    "dp_spool": 8.0e5,      # meter-in drop of the spool at the nominal flow (sizes A_max)
    "tau_spool": 0.08,      # spool / pilot lag
    "A_ls": 2.0e-6,         # LS gallery edge of each spool
    "V_ls_sec": 1.0e-5, "V_ls": 5.0e-5,
    "R_bleed": 3.6e12,      # LS line bleed to tank (laminar), Pa s/m^3
}
Q_NOM = {"boom": 300 / 60e3, "arm": 280 / 60e3, "bucket": 200 / 60e3}   # m^3/s at full joystick

# --------------------------------------------------------------------------- soil
SOIL = {"gamma": 1.8e4, "rho": 1835.0, "c": 1.5e4, "phi": D(30.0), "delta": D(20.0),
        "rake": D(45.0), "w": 1.2, "swell": 1.25, "V_max": 0.93}


def fee_factors(rake, phi, delta):
    """N_gamma and N_c of the fundamental earthmoving equation on flat ground (McKyes; the
    form of Wagner 2025, eq. 15 with alpha = 0), the failure angle beta minimising N_gamma."""
    def n_gamma(beta):
        return (1 / math.tan(rake) + 1 / math.tan(beta)) * math.sin(phi + beta) / (
            2 * math.sin(delta + rake + phi + beta))
    res = minimize_scalar(n_gamma, bounds=(D(5.0), D(85.0)), method="bounded")
    beta = float(res.x)
    n_c = math.cos(phi) / (math.sin(beta) * math.sin(delta + rake + phi + beta))
    return float(res.fun), n_c, beta


# --------------------------------------------------------------------------- kinematics
def cyl_lengths(q):
    return G.cylinders(*q)["L"]


def joint_from_length(i, L, q):
    """Joint angle i whose cylinder length is L (the other angles from q)."""
    lo, hi = LIMITS[("boom", "arm", "bucket")[i]]
    def f(a):
        qq = list(q)
        qq[i] = a
        return cyl_lengths(qq)[i] - L
    return brentq(f, lo - D(3.0), hi + D(3.0), xtol=1e-14)


def fk_from_lengths(Ls, q_guess=REF):
    """Bucket tip (x, y) and joint angles from the three cylinder lengths: each length depends
    on its own joint only, so the three roots are independent."""
    q = [joint_from_length(i, Ls[i], q_guess) for i in range(3)]
    f = G.frames(*q)
    return f["T"], q


def static_forces(q, payload: bool):
    """Cylinder forces (extending positive) that hold the front at q: the gravity torques
    about each joint divided by the moment arms dL/dq (virtual work)."""
    f = G.frames(*q)
    bodies = [("boom", f["O"], f["a1"]), ("arm", f["C"], f["a2"]), ("bucket", f["Q"], f["a3"])]
    pts = []
    for name, o, a in bodies:
        b = BODIES[name]
        pts.append((b["m"], G.world(o, a, b["c"]), name))
    if payload:
        pts.append((PAYLOAD["m"], G.world(f["Q"], f["a3"], PAYLOAD["c"]), "bucket"))
    pivots = [f["O"], f["C"], f["Q"]]
    which = {"boom": 0, "arm": 1, "bucket": 2}
    tau = [0.0, 0.0, 0.0]
    for m, p, owner in pts:
        for j in range(3):
            if which[owner] >= j:         # the body is outboard of joint j
                tau[j] += -m * G0 * (p[0] - pivots[j][0])   # gravity torque (counter-clockwise +)
    r = G.cylinders(*q)["r"]
    # equilibrium: cylinder torque r F + gravity torque = 0
    return [-tau[j] / r[j] for j in range(3)], tau, list(r)


def inertia_about(q, j, payload: bool):
    """Moment of inertia of everything outboard of joint j about its pivot, the outer joints
    locked (rigid)."""
    f = G.frames(*q)
    piv = [f["O"], f["C"], f["Q"]][j]
    items = [("boom", f["O"], f["a1"]), ("arm", f["C"], f["a2"]), ("bucket", f["Q"], f["a3"])]
    J = 0.0
    for k, (name, o, a) in enumerate(items):
        if k < j:
            continue
        b = BODIES[name]
        p = G.world(o, a, b["c"])
        J += b["J"] + b["m"] * float(np.sum((p - piv) ** 2))
    if payload:
        p = G.world(f["Q"], f["a3"], PAYLOAD["c"])
        J += PAYLOAD["J"] + PAYLOAD["m"] * float(np.sum((p - piv) ** 2))
    return J


def mass_matrix(q, payload: bool) -> np.ndarray:
    """3x3 joint-space mass matrix of the front (boom, arm, bucket and the payload): the
    centre-of-mass Jacobians of the planar chain, M = sum m Jv^T Jv + J Jw^T Jw."""
    f = G.frames(*q)
    pivots = [f["O"], f["C"], f["Q"]]
    items = [("boom", 0, f["O"], f["a1"], BODIES["boom"]), ("arm", 1, f["C"], f["a2"], BODIES["arm"]),
             ("bucket", 2, f["Q"], f["a3"], BODIES["bucket"])]
    if payload:
        items.append(("payload", 2, f["Q"], f["a3"], PAYLOAD))
    M = np.zeros((3, 3))
    for _, k, o, a, b in items:
        p = G.world(o, a, b["c"])
        Jv = np.zeros((2, 3))
        Jw = np.zeros(3)
        for j in range(k + 1):
            d = p - pivots[j]
            Jv[:, j] = (-d[1], d[0])
            Jw[j] = 1.0
        M += b["m"] * Jv.T @ Jv + b["J"] * np.outer(Jw, Jw)
    return M


def chamber_stiffness(c, x):
    """Hydraulic stiffness of a cylinder (design entry c) with both chambers closed, at the
    rod extension x: beta (Ap^2/VA + Ar^2/VB)."""
    VA = c["V0"] + c["Ap"] * x
    VB = c["V0"] + c["Ar"] * (c["stroke"] - x)
    return HYD["beta"] * (c["Ap"] ** 2 / VA + c["Ar"] ** 2 / VB)


def combined_bucket():
    """Bucket plus payload as one rigid body (the lift model)."""
    b, p = BODIES["bucket"], PAYLOAD
    m = b["m"] + p["m"]
    c = (np.array(b["c"]) * b["m"] + np.array(p["c"]) * p["m"]) / m
    J = b["J"] + b["m"] * float(np.sum((np.array(b["c"]) - c) ** 2)) + p["J"] + p["m"] * float(
        np.sum((np.array(p["c"]) - c) ** 2))
    return {"m": m, "c": (float(c[0]), float(c[1])), "J": J}


def main() -> int:
    out: dict = {"geometry": {"L1": G.L1, "L2": G.L2, "L3": G.L3, "y_ground": G.Y_GROUND,
                              **{k: list(v) if isinstance(v, tuple) else v for k, v in G.GEOM.items()},
                              "branch": G.FOUR_BAR_BRANCH}}
    # ---- cylinders: closed length and stroke from the joint ranges
    cyl = {}
    for i, name in enumerate(("boom", "arm", "bucket")):
        lo, hi = LIMITS[name]
        Ls = []
        for a in (lo, hi):
            q = list(REF)
            q[i] = a
            Ls.append(cyl_lengths(q)[i])
        grid = np.linspace(lo, hi, 201)
        rs = []
        for a in grid:
            q = list(REF)
            q[i] = a
            rs.append(G.cylinders(*q)["r"][i])
        Ap, Ar = areas(CYL[name]["bore"], CYL[name]["rod"], CYL[name]["n"])
        cyl[name] = {**CYL[name], "Ap": Ap, "Ar": Ar, "L_closed": min(Ls), "stroke": abs(Ls[1] - Ls[0]),
                     "q_lower": lo, "q_upper": hi, "r_min": float(min(rs, key=abs)), "r_max": float(max(rs, key=abs)),
                     "extends_with_q": bool(Ls[1] > Ls[0])}
    out["cylinders"] = cyl
    out["bodies"] = BODIES
    out["payload"] = PAYLOAD
    out["bucket_with_payload"] = combined_bucket()
    hyd = dict(HYD)
    hyd["T_max"] = HYD["P_max"] / HYD["w_engine"]
    hyd["Q_pump_max"] = HYD["D_pump"] * HYD["w_engine"]
    hyd["Q_nom"] = Q_NOM
    hyd["A_spool"] = {k: q / (0.62 * math.sqrt(2 * HYD["dp_spool"] / HYD["rho"])) for k, q in Q_NOM.items()}
    out["hydraulics"] = hyd
    ng, nc, beta = fee_factors(SOIL["rake"], SOIL["phi"], SOIL["delta"])
    out["soil"] = {**SOIL, "N_gamma": ng, "N_c": nc, "beta": beta}
    out["mass_total"] = sum(b["m"] for b in BODIES.values())

    # ---- kinematics model: cylinder-length set points and the tip from them
    q0 = (D(15.0), D(-105.0), D(-60.0))
    L0 = cyl_lengths(q0)
    moves = [  # (t0, t1, dL per cylinder): constant-speed moves between holds
        (1.0, 4.0, (0.45, -0.40, -0.35)),
        (7.0, 10.0, (-0.70, 0.60, 0.50)),
    ]
    holds = [0.5, 6.5, 12.5]
    Lset = []
    L = list(L0)
    pts = []
    for th in holds:
        Lh = list(L0)
        for t0, t1, dL in moves:
            frac = min(max((th - t0) / (t1 - t0), 0.0), 1.0)
            Lh = [a + frac * b for a, b in zip(Lh, dL)]
        T, q = fk_from_lengths(Lh)
        pts.append({"t": th, "L": Lh, "q": q, "tip": [float(T[0]), float(T[1])]})
    out["kinematics"] = {"q0": list(q0), "L0": list(L0), "moves": moves, "holds": pts,
                         "t_end": 13.0, "k_servo": 1.0e8, "d_servo": 2.0e7}
    del L, Lset

    # ---- lift model: hold pose, static forces, natural frequency, regulated speed
    ql = (D(10.0), D(-95.0), D(-95.0))
    F, tau, r = static_forces(ql, payload=True)
    c = cyl["boom"]
    Lb = cyl_lengths(ql)[0]
    x = Lb - c["L_closed"]
    VA = c["V0"] + c["Ap"] * x
    VB = c["V0"] + c["Ar"] * (c["stroke"] - x)
    p_B0 = 10e5
    p_A0 = (F[0] + p_B0 * c["Ar"]) / c["Ap"]
    k_h = HYD["beta"] * (c["Ap"] ** 2 / VA + c["Ar"] ** 2 / VB)
    J1 = inertia_about(ql, 0, payload=True)
    m_eq = J1 / r[0] ** 2
    w_h = math.sqrt(k_h / m_eq)
    # the other cylinders' static pressures (rod side at p_B0)
    starts = {}
    for i, name in enumerate(("boom", "arm", "bucket")):
        cc = cyl[name]
        Li = cyl_lengths(ql)[i]
        pA = (F[i] + p_B0 * cc["Ar"]) / cc["Ap"]
        if pA < p_B0:   # a pulling cylinder: rod side carries the load
            pA = p_B0
            pB = (pA * cc["Ap"] - F[i]) / cc["Ar"]
        else:
            pB = p_B0
        starts[name] = {"x": Li - cc["L_closed"], "pA": pA, "pB": pB, "L": Li}
    v_boom = 0.5 * Q_NOM["boom"] / c["Ap"]
    # all three cylinders compliant (valves closed): eig(M^-1 K), K = diag(k_i r_i^2)
    M = mass_matrix(ql, payload=True)
    Kq = np.diag([chamber_stiffness(cyl[n], starts[n]["x"]) * r[i] ** 2 for i, n in enumerate(("boom", "arm", "bucket"))])
    lam, vecs = np.linalg.eig(np.linalg.solve(M, Kq))
    order = np.argsort(lam.real)
    modes = [{"f": float(math.sqrt(lam[k].real) / (2 * math.pi)),
              "shape": [float(v) for v in vecs[:, k].real / np.max(np.abs(vecs[:, k].real))]} for k in order]
    boom_mode = max(modes, key=lambda m: abs(m["shape"][0]) / (sum(abs(s) for s in m["shape"]) + 1e-30))
    out["lift"] = {"q0": list(ql), "F": F, "tau": tau, "r": r, "starts": starts, "x_boom": x,
                   "VA": VA, "VB": VB, "k_h": k_h, "J1": J1, "m_eq": m_eq, "w_h": w_h, "f_h": w_h / (2 * math.pi),
                   "modes": modes, "f_boom_mode": boom_mode["f"], "M": M.tolist(),
                   "sag": 0.85, "u_lift": 0.5, "v_boom": v_boom, "t_lift": (3.0, 6.0), "t_end": 9.0}
    # Jin et al. (2024): J of the whole front about the boom pivot, 79 720 kg m^2
    out["jin_check"] = {"J1_front_ref_pose_no_payload": inertia_about((D(30.0), D(-110.0), D(-40.0)), 0, False),
                        "J1_jin": 79720.0}

    # ---- dig cycle start pose
    out["dig"] = {"q0": [D(30.0), D(-85.0), D(-25.0)]}
    out["dig"]["starts"] = {}
    Fd, _, _ = static_forces(tuple(out["dig"]["q0"]), payload=False)
    for i, name in enumerate(("boom", "arm", "bucket")):
        cc = cyl[name]
        Li = cyl_lengths(out["dig"]["q0"])[i]
        pA = (Fd[i] + p_B0 * cc["Ar"]) / cc["Ap"]
        pB = p_B0
        if pA < p_B0:
            pA = p_B0
            pB = (pA * cc["Ap"] - Fd[i]) / cc["Ar"]
        out["dig"]["starts"][name] = {"x": Li - cc["L_closed"], "pA": pA, "pB": pB, "L": Li}

    (HERE / "design.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in ("cylinders", "lift", "soil", "jin_check")}, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
