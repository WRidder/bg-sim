"""The Whipple/Carvallo benchmark bicycle of Meijaard, Papadopoulos, Ruina and Schwab (2007).

    J. P. Meijaard, J. M. Papadopoulos, A. Ruina and A. L. Schwab, "Linearized dynamics
    equations for the balance and steer of a bicycle: a benchmark and review",
    Proc. R. Soc. A 463 (2007) 1955-1982, doi:10.1098/rspa.2007.1857.

`PARAMS` is the paper's table 1 (the values are exact), in the paper's frame: origin at the rear
contact P, x forward, y to the right, z DOWN. `matrices()` evaluates the paper's appendix A
(equations A1-A27) from these parameters, independently of the printed matrices (6.1)-(6.4),
which are kept in `PAPER_MATRICES` for the comparison. `TABLE2` is the paper's table 2 (the
eigenvalues the paper offers for benchmark comparisons); the same numbers are in
`meijaard2007_table2.json` with the source.

Imported by design.py and build_model.py; no third-party dependency except numpy.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# Table 1 of the paper (z down, y to the right).
PARAMS = {
    "w": 1.02,              # wheel base, m
    "c": 0.08,              # trail, m
    "lam": np.pi / 10,      # steer axis tilt from the vertical, rad
    "g": 9.81,              # gravity, N/kg
    # rear wheel R
    "rR": 0.3, "mR": 2.0, "IRxx": 0.0603, "IRyy": 0.12,
    # rear body and frame assembly B (the rider is rigidly part of it)
    "xB": 0.3, "zB": -0.9, "mB": 85.0,
    "IBxx": 9.2, "IByy": 11.0, "IBzz": 2.8, "IBxz": 2.4,
    # front handlebar and fork assembly H
    "xH": 0.9, "zH": -0.7, "mH": 4.0,
    "IHxx": 0.05892, "IHyy": 0.06, "IHzz": 0.00708, "IHxz": -0.00756,
    # front wheel F
    "rF": 0.35, "mF": 3.0, "IFxx": 0.1405, "IFyy": 0.28,
}

# Equations (6.1)-(6.4) of the paper, as printed (14 decimals).
PAPER_MATRICES = {
    "M": [[80.81722, 2.31941332208709], [2.31941332208709, 0.29784188199686]],
    "K0": [[-80.95, -2.59951685249872], [-2.59951685249872, -0.80329488458618]],
    "K2": [[0.0, 76.59734589573222], [0.0, 2.65431523794604]],
    "C1": [[0.0, 33.86641391492494], [-0.85035641456978, 1.68540397397560]],
}


def matrices(p: dict = PARAMS) -> dict:
    """M, C1, K0, K2 of M q'' + v C1 q' + (g K0 + v^2 K2) q = f, q = (phi, delta): appendix A."""
    w, c, lam, rR, rF = p["w"], p["c"], p["lam"], p["rR"], p["rF"]
    mR, mB, mH, mF = p["mR"], p["mB"], p["mH"], p["mF"]
    xB, zB, xH, zH = p["xB"], p["zB"], p["xH"], p["zH"]
    mT = mR + mB + mH + mF                                                       # A1
    xT = (xB * mB + xH * mH + w * mF) / mT                                       # A2
    zT = (-rR * mR + zB * mB + zH * mH - rF * mF) / mT                           # A3
    ITxx = (p["IRxx"] + p["IBxx"] + p["IHxx"] + p["IFxx"] + mR * rR**2 + mB * zB**2
            + mH * zH**2 + mF * rF**2)                                           # A4
    ITxz = p["IBxz"] + p["IHxz"] - mB * xB * zB - mH * xH * zH + mF * w * rF     # A5
    IRzz, IFzz = p["IRxx"], p["IFxx"]                                            # A6
    ITzz = IRzz + p["IBzz"] + p["IHzz"] + IFzz + mB * xB**2 + mH * xH**2 + mF * w**2  # A7
    mA = mH + mF                                                                 # A8
    xA = (xH * mH + w * mF) / mA
    zA = (zH * mH - rF * mF) / mA                                                # A9
    IAxx = p["IHxx"] + p["IFxx"] + mH * (zH - zA) ** 2 + mF * (rF + zA) ** 2      # A10
    IAxz = p["IHxz"] - mH * (xH - xA) * (zH - zA) + mF * (w - xA) * (rF + zA)    # A11
    IAzz = p["IHzz"] + IFzz + mH * (xH - xA) ** 2 + mF * (w - xA) ** 2           # A12
    uA = (xA - w - c) * np.cos(lam) - zA * np.sin(lam)                           # A13
    IAll = mA * uA**2 + IAxx * np.sin(lam) ** 2 + 2 * IAxz * np.sin(lam) * np.cos(lam) + IAzz * np.cos(lam) ** 2
    IAlx = -mA * uA * zA + IAxx * np.sin(lam) + IAxz * np.cos(lam)               # A15
    IAlz = mA * uA * xA + IAxz * np.sin(lam) + IAzz * np.cos(lam)                # A16
    mu = c / w * np.cos(lam)                                                     # A17
    SR, SF = p["IRyy"] / rR, p["IFyy"] / rF                                      # A18
    ST = SR + SF
    SA = mA * uA + mu * mT * xT                                                  # A19
    M = np.array([[ITxx, IAlx + mu * ITxz], [IAlx + mu * ITxz, IAll + 2 * mu * IAlz + mu**2 * ITzz]])
    K0 = np.array([[mT * zT, -SA], [-SA, -SA * np.sin(lam)]])
    K2 = np.array([[0.0, (ST - mT * zT) / w * np.cos(lam)], [0.0, (SA + SF * np.sin(lam)) / w * np.cos(lam)]])
    C1 = np.array([
        [0.0, mu * ST + SF * np.cos(lam) + ITxz / w * np.cos(lam) - mu * mT * zT],
        [-(mu * ST + SF * np.cos(lam)), IAlz / w * np.cos(lam) + mu * (SA + ITzz / w * np.cos(lam))],
    ])
    return {"M": M, "C1": C1, "K0": K0, "K2": K2, "mT": mT, "xT": xT, "zT": zT}


def state_matrices(v: float, p: dict = PARAMS):
    """A, B of x' = A x + B f with x = (phi, delta, phid, deltad) and f = (T_phi, T_delta)."""
    m = matrices(p)
    Minv = np.linalg.inv(m["M"])
    K = p["g"] * m["K0"] + v * v * m["K2"]
    A = np.zeros((4, 4))
    A[:2, 2:] = np.eye(2)
    A[2:, :2] = -Minv @ K
    A[2:, 2:] = -v * Minv @ m["C1"]
    B = np.zeros((4, 2))
    B[2:, :] = Minv
    return A, B


def eigenvalues(v: float, p: dict = PARAMS) -> np.ndarray:
    A, _ = state_matrices(v, p)
    return np.linalg.eigvals(A)


def load_table2() -> dict:
    return json.loads((HERE / "meijaard2007_table2.json").read_text(encoding="utf-8"))
