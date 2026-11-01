"""Steady-state tyre forces of the stdlib `Tyre` block, written again in numpy (the reference
the design scripts use: no code is shared with the Julia block).

    F_x, F_y = forces(ty, Fz, kappa, tan_alpha, mus=1)

Magic Formula per direction with load sensitivity, combined by normalised slip so that each
pure-slip curve is the Magic Formula and the saturated resultant lies on the friction ellipse.
"""

from __future__ import annotations

import numpy as np


def coefficients(ty: dict, Fz, mus=1.0):
    Fz = np.asarray(Fz, dtype=float)
    dfz = (Fz - ty["Fz0"]) / ty["Fz0"]
    scale = np.maximum(1.0 + ty["dmu"] * dfz, 0.1)
    mx = mus * ty["mux"] * scale
    my = mus * ty["muy"] * scale
    Tx = np.tan(np.pi / (2.0 * ty["Cx"]))
    Ty = np.tan(np.pi / (2.0 * ty["Cy"]))
    Bx = ty["Kx"] / (ty["Cx"] * mx)
    BCDy = ty["Ky"] * ty["Fz0"] * np.sin(2.0 * np.arctan(Fz / (ty["Ky2"] * ty["Fz0"])))
    By = BCDy / (ty["Cy"] * my * Fz)
    return {"mx": mx, "my": my, "Tx": Tx, "Ty": Ty, "Bx": Bx, "By": By, "sxm": Tx / Bx, "sym": Ty / By,
            "Cx_slip": ty["Kx"] * Fz, "Cy_slip": BCDy}


def forces(ty: dict, Fz, kappa, tan_alpha, mus=1.0, seps=1e-3):
    c = coefficients(ty, Fz, mus)
    nx = np.asarray(kappa) / c["sxm"]
    ny = np.asarray(tan_alpha) / c["sym"]
    S = np.sqrt(nx * nx + ny * ny + seps * seps)
    X = c["Tx"] * S
    Y = c["Ty"] * S
    Fx0 = c["mx"] * Fz * np.sin(ty["Cx"] * np.arctan(X - ty["Ex"] * (X - np.arctan(X))))
    Fy0 = c["my"] * Fz * np.sin(ty["Cy"] * np.arctan(Y - ty["Ey"] * (Y - np.arctan(Y))))
    return Fx0 * nx / S, Fy0 * ny / S


def cornering_stiffness(ty: dict, Fz) -> float:
    """dFy/d(tan alpha) at zero slip (the regularisation seps is negligible)."""
    return float(coefficients(ty, Fz)["Cy_slip"])


def peak_lateral(ty: dict, Fz, mus=1.0) -> float:
    """The largest pure lateral force (on a fine grid of slip angles)."""
    t = np.linspace(0.0, 1.0, 20001)
    _, fy = forces(ty, Fz, 0.0, t, mus)
    return float(np.max(fy))
