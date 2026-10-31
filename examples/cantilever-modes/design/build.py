# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the cantilever-modes example: model, expected checks.

A cantilever (steel rod) by the assumed-modes method with two bending modes, drawn as a
plain scalar bond graph (Karnopp/Margolis/Rosenberg's modal bond graph): each mode is a
1-junction with I (modal mass), C (1/modal stiffness) and R (modal damping), and a TF with
modulus phi_i(L) = 2 maps the modal velocity to its share of the tip velocity. The tip is a
0-junction (one force, the flows add). Every number comes from global parameters derived
from E, rho, d and L.

    uv run examples/cantilever-modes/design/build.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Base data (also the global parameter defaults) -------------------------------------------
E = 2.1e11  # Pa
RHO = 7850.0  # kg/m^3
D = 0.01  # m
L = 1.0  # m
F0 = 1.0  # N
ZETA = 0.05
LAM = (1.87510407, 4.69409113)
PHI_L = 2.0  # |phi_n(L)| of the clamped-free modes ((1/L) int phi^2 = 1)

A = math.pi * D**2 / 4
I = math.pi * D**4 / 64
M = RHO * A * L
K = [lam**4 * E * I / L**3 for lam in LAM]
F_HZ = [math.sqrt(k / M) / (2 * math.pi) for k in K]
TIP_MODAL = F0 * sum(PHI_L**2 / k for k in K)
TIP_EB = F0 * L**3 / (3 * E * I)
T_STEP = 0.05


def node(nid, name, block, x, y, params=None):
    return {
        "id": nid,
        "name": name,
        "block": block,
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": {},
        "starts": {},
        "ui": {"showLabel": True, "color": None},
    }


def ref(r):
    return {"ref": f"stdlib:{r}"}


def end(nid, port=None):
    return {"node": nid} if port is None else {"node": nid, "port": port}


def conn(cid, kind, a, b):
    return {"id": cid, "kind": kind, "from": a, "to": b, "route": [], "label": None}


def model() -> dict:
    nodes = [
        node("n1", "Step", ref("sources/Step"), 40, 60, {"t_step": str(T_STEP), "initial": "0.0", "final": "F0"}),
        node("n2", "Force", ref("bondgraph/MSe"), 40, 220),
        node("n6", "Tip", {"junction": "0"}, 300, 220),
        # mode 1
        node("n7", "TF1", ref("bondgraph/TF"), 560, 140, {"n": "phiL"}),
        node("n8", "Mode1", {"junction": "1"}, 720, 140),
        node("n9", "I1", ref("bondgraph/I"), 720, 20, {"i": "m"}),
        node("n10", "C1", ref("bondgraph/C"), 880, 100, {"c": "1/k1"}),
        node("n11", "R1", ref("bondgraph/R"), 880, 180, {"r": "c1"}),
        # mode 2
        node("n12", "TF2", ref("bondgraph/TF"), 560, 320, {"n": "phiL"}),
        node("n13", "Mode2", {"junction": "1"}, 720, 320),
        node("n14", "I2", ref("bondgraph/I"), 720, 440, {"i": "m"}),
        node("n15", "C2", ref("bondgraph/C"), 880, 280, {"c": "1/k2"}),
        node("n16", "R2", ref("bondgraph/R"), 880, 360, {"r": "c2"}),
    ]
    conns = [
        conn("c1", "signal", end("n1", "y"), end("n2", "u")),
        conn("c2", "bond", end("n2", "p"), end("n6")),
        conn("c6", "bond", end("n6"), end("n7", "p2")),
        conn("c7", "bond", end("n7", "p1"), end("n8")),
        conn("c8", "bond", end("n8"), end("n9", "p")),
        conn("c9", "bond", end("n8"), end("n10", "p")),
        conn("c10", "bond", end("n8"), end("n11", "p")),
        conn("c11", "bond", end("n6"), end("n12", "p2")),
        conn("c12", "bond", end("n12", "p1"), end("n13")),
        conn("c13", "bond", end("n13"), end("n14", "p")),
        conn("c14", "bond", end("n13"), end("n15", "p")),
        conn("c15", "bond", end("n13"), end("n16", "p")),
    ]
    g = [
        ("E", repr(E), "Pa", "Young's modulus (steel)"),
        ("rho", repr(RHO), "kg/m^3", "Density"),
        ("d", repr(D), "m", "Rod diameter"),
        ("L", repr(L), "m", "Length"),
        ("F0", repr(F0), "N", "Tip force step"),
        ("zeta", repr(ZETA), None, "Modal damping ratio"),
        ("lam1", repr(LAM[0]), None, "First clamped-free eigenvalue lambda_1"),
        ("lam2", repr(LAM[1]), None, "Second clamped-free eigenvalue lambda_2"),
        ("phiL", "2", None, "|phi_n(L)|: tip value of a normalised cantilever mode"),
        ("Pi", "3.141592653589793", None, "pi (a global expression cannot use the built-in constant)"),
        ("A", "Pi*d^2/4", "m^2", "Cross-section area"),
        ("I", "Pi*d^4/64", "m^4", "Second moment of area"),
        ("m", "rho*A*L", "kg", "Modal mass of every mode (= beam mass)"),
        ("k1", "lam1^4*E*I/L^3", "N/m", "Modal stiffness, mode 1"),
        ("k2", "lam2^4*E*I/L^3", "N/m", "Modal stiffness, mode 2"),
        ("c1", "2*zeta*sqrt(k1*m)", "N*s/m", "Modal damping, mode 1"),
        ("c2", "2*zeta*sqrt(k2*m)", "N*s/m", "Modal damping, mode 2"),
    ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": "cantilever-modes",
        "parameters": [{"name": n, "value": v, "unit": u, "description": d} for (n, v, u, d) in g],
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {
            "t_start": 0.0,
            "t_end": 6.0,
            "solver": "auto",
            "reltol": 1e-08,
            "abstol": 1e-10,
            "max_step": None,
            "output": {"mode": "points", "points": 12001},
            "event_limit": 10000,
        },
        "plots": [
            {"id": "p1", "title": "Modal coordinates eta1, eta2 (C displacement, m)", "signals": ["C1/q", "C2/q"]},
            {"id": "p2", "title": "Tip velocity (m/s) and tip force (N)", "signals": ["Force/p.f", "Force/p.e"]},
            {"id": "p3", "title": "Modal momenta (N s)", "signals": ["I1/P", "I2/P"]},
        ],
    }


def expected() -> dict:
    return {
        "project": "cantilever-modes",
        "description": "Assumed-modes cantilever (2 bending modes) as a scalar bond graph: the ring-down frequencies are the analytic Euler-Bernoulli eigenfrequencies, the settled tip deflection is the 2-mode modal sum F (4/k1 + 4/k2) = 0.9954 F L^3 / (3 E I).",
        "models": {
            "cantilever-modes": {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "W201", "W202"]},
                    {
                        "kind": "fft_peak", "signal": "C1/q", "from_t": T_STEP, "to_t": 3.0,
                        "min_hz": 2.0, "max_hz": 20.0, "value": F_HZ[0], "rtol": 0.01,
                        "note": "f1 = lambda1^2/(2 pi) sqrt(E I/(rho A L^4)), damped by zeta = 0.05 (sqrt(1 - zeta^2) = 0.9987)",
                    },
                    {
                        "kind": "fft_peak", "signal": "C2/q", "from_t": T_STEP, "to_t": 0.6,
                        "min_hz": 20.0, "max_hz": 100.0, "value": F_HZ[1], "rtol": 0.01,
                        "note": "f2 = lambda2^2/(2 pi) sqrt(E I/(rho A L^4))",
                    },
                    {
                        "kind": "final_value", "signal": "C1/q", "t": 6.0, "value": PHI_L * F0 / K[0],
                        "rtol": 1e-4, "note": "static modal coordinate eta1 = phi1(L) F / k1",
                    },
                    {
                        "kind": "final_value", "signal": "C2/q", "t": 6.0, "value": PHI_L * F0 / K[1],
                        "rtol": 1e-3,
                        "note": f"static modal coordinate eta2 = |phi2(L)| F / k2; the tip deflection 2 (eta1 + eta2) = {TIP_MODAL:.6e} m is {TIP_MODAL / TIP_EB:.4f} of Euler-Bernoulli F L^3/(3 E I) = {TIP_EB:.6e} m",
                    },
                    {
                        "kind": "max_abs", "signal": "Force/p.e", "value": F0, "rtol": 1e-9,
                        "note": "the tip force step",
                    },
                ]
            }
        },
    }


def main() -> None:
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "models" / "cantilever-modes.bgmodel.json", "w", newline="\n") as f:
        json.dump(model(), f, indent=2)
        f.write("\n")
    with open(ROOT / "expected.json", "w", newline="\n") as f:
        json.dump(expected(), f, indent=2)
        f.write("\n")
    print(f"f1 = {F_HZ[0]:.6f} Hz, f2 = {F_HZ[1]:.6f} Hz, tip modal {TIP_MODAL:.6e} m, EB {TIP_EB:.6e} m")


if __name__ == "__main__":
    main()
