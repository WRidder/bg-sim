"""Blade-element momentum (BEM) for the NREL 5 MW rotor: the Cp(lambda, beta) and Ct(lambda, beta) tables.

Steady, axial-flow BEM on the report's 17 blade elements (Table 3-1: radius, twist, element width,
chord, airfoil) with the report's airfoil polars (Appendix B, `airfoils/*.csv`):

* Prandtl tip and hub losses, the Buhl high-induction (empirical) correction, tangential induction,
  and the drag in the induction (as AeroDyn v13 / WT_Perf);
* the inflow angle phi of every element is the root of Ning's one-variable residual (S. A. Ning,
  "A simple solution method for the blade element momentum equations with guaranteed
  convergence", Wind Energy 17, 2014), bracketed and solved with Brent's method, so every
  (lambda, beta) point converges;
* the element loads are summed with the element widths (the midpoint rule of the report's
  discretisation);
* the rotor geometry of the report: the blades are coned 2.5 deg upwind (precone), so an element
  at span r turns on the radius r cos(precone), and the shaft is tilted 5 deg, so the wind normal
  to the cone is V cos(tilt) cos(precone) (WT_Perf's treatment of a rigid coned, tilted rotor);
  Cp and Ct stay referenced to the horizontal hub-height wind V and the rotor radius R, Ct is the
  thrust along the shaft;
* the tower shadow, the wind shear and blade flexibility are not modelled.

Cp and Ct do not depend on the wind speed (no Reynolds or Mach effects): the polars are one table
each.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

import nrel5mw as T

AIRFOILS = Path(__file__).resolve().parent / "airfoils"


def load_polar(name: str):
    a, cl, cd = np.loadtxt(AIRFOILS / f"{name}.csv", delimiter=",", comments="#", unpack=True)
    return np.radians(a), cl, cd


POLARS = {name: load_polar(name) for name in sorted({b[4] for b in T.BLADE})}
R_NODES = np.array([b[0] for b in T.BLADE])
TWIST = np.radians([b[1] for b in T.BLADE])
DR = np.array([b[2] for b in T.BLADE])
CHORD = np.array([b[3] for b in T.BLADE])
FOIL = [b[4] for b in T.BLADE]
COS_PC = math.cos(math.radians(T.PRECONE_DEG))
V_N = math.cos(math.radians(T.SHAFT_TILT_DEG)) * COS_PC   # wind normal to the cone per unit V


def coefficients(name: str, alpha: float) -> tuple[float, float]:
    a, cl, cd = POLARS[name]
    alpha = (alpha + math.pi) % (2.0 * math.pi) - math.pi
    return float(np.interp(alpha, a, cl)), float(np.interp(alpha, a, cd))


def element(k: int, tsr: float, pitch: float):
    """Induction and inflow of element k at tip-speed ratio tsr and collective pitch (rad).

    Returns (phi, a, ap, cn, ct) with V = 1 and Omega R = tsr."""
    r = R_NODES[k] * COS_PC        # radius of the element in the rotor plane
    lam_r = tsr * r / T.R_TIP / V_N  # local speed ratio against the normal wind
    sigma = T.B * CHORD[k] / (2.0 * math.pi * r)
    theta = TWIST[k] + pitch

    def loads(phi):
        cl, cd = coefficients(FOIL[k], phi - theta)
        sp, cp_ = math.sin(phi), math.cos(phi)
        cn = cl * cp_ + cd * sp
        ct = cl * sp - cd * cp_
        ftip = 2.0 / math.pi * math.acos(min(1.0, math.exp(-T.B * (T.R_TIP - R_NODES[k]) / (2.0 * R_NODES[k] * abs(sp)))))
        fhub = 2.0 / math.pi * math.acos(min(1.0, math.exp(-T.B * (R_NODES[k] - T.R_HUB) / (2.0 * T.R_HUB * abs(sp)))))
        F = max(ftip * fhub, 1e-6)
        k_ = sigma * cn / (4.0 * F * sp * sp)
        kp = sigma * ct / (4.0 * F * sp * cp_)
        return cn, ct, F, k_, kp

    def induction(phi):
        cn, ct, F, k_, kp = loads(phi)
        if phi > 0.0:
            if k_ <= 2.0 / 3.0:
                a = k_ / (1.0 + k_)
            else:  # Buhl's empirical (high-induction) branch
                g1 = 2.0 * F * k_ - (10.0 / 9.0 - F)
                g2 = max(2.0 * F * k_ - F * (4.0 / 3.0 - F), 0.0)
                g3 = 2.0 * F * k_ - (25.0 / 9.0 - 2.0 * F)
                a = 1.0 - 1.0 / (2.0 * math.sqrt(g2)) if abs(g3) < 1e-6 else (g1 - math.sqrt(g2)) / g3
        else:      # propeller brake
            a = k_ / (k_ - 1.0) if k_ > 1.0 else 0.0
        ap = kp / (1.0 - kp)
        return a, ap, cn, ct, F, k_, kp

    def residual(phi):
        cn, ct, F, k_, kp = loads(phi)
        sp, cp_ = math.sin(phi), math.cos(phi)
        if phi > 0.0:
            a, *_ = induction(phi)
            return sp / (1.0 - a) - cp_ / lam_r * (1.0 - kp)
        return sp * (1.0 - k_) - cp_ / lam_r * (1.0 - kp)

    eps = 1e-6
    phi = None
    if residual(eps) * residual(math.pi / 2.0) < 0.0:
        phi = brentq(residual, eps, math.pi / 2.0, xtol=1e-12)
    elif residual(-math.pi / 4.0) * residual(-eps) < 0.0:
        phi = brentq(residual, -math.pi / 4.0, -eps, xtol=1e-12)
    else:
        phi = brentq(residual, math.pi / 2.0, math.pi - eps, xtol=1e-12)
    a, ap, cn, ct, *_ = induction(phi)
    return phi, a, ap, cn, ct


def rotor(tsr: float, pitch_deg: float) -> tuple[float, float]:
    """(Cp, Ct) of the rotor at tip-speed ratio tsr and collective pitch pitch_deg."""
    pitch = math.radians(pitch_deg)
    thrust = 0.0
    torque = 0.0
    for k in range(len(R_NODES)):
        phi, a, ap, cn, ct = element(k, tsr, pitch)
        r = R_NODES[k] * COS_PC
        w2 = (V_N * (1.0 - a)) ** 2 + (tsr * r / T.R_TIP * (1.0 + ap)) ** 2   # (W / V)^2
        q = 0.5 * w2 * CHORD[k] * DR[k]                                       # per unit rho V^2
        thrust += T.B * q * cn * COS_PC
        torque += T.B * q * ct * r
    area = math.pi * T.R_TIP ** 2
    ct_rotor = thrust / (0.5 * area)
    cp_rotor = torque * tsr / T.R_TIP / (0.5 * area)
    return cp_rotor, ct_rotor


def tables(tsr: np.ndarray, pitch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """table[i, j] at (tsr[j], pitch[i]): the layout of the stdlib Lookup2D block."""
    cp = np.zeros((len(pitch), len(tsr)))
    ct = np.zeros_like(cp)
    for i, b in enumerate(pitch):
        for j, l in enumerate(tsr):
            cp[i, j], ct[i, j] = rotor(float(l), float(b))
    return cp, ct


if __name__ == "__main__":
    for l in (6.0, 7.0, 7.55, 8.0, 9.0):
        print(l, rotor(l, 0.0))
