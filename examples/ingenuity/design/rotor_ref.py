"""Reference blade-element/momentum (BEMT) rotor model in numpy: the same law as `library/RotorBEMT.jl`.

Every annulus of the blade balances blade-element lift against annulus momentum (Leishman, *Principles
of Helicopter Aerodynamics*, ch. 3.3), with an induced-velocity factor ``kappa``:

    dT = rho * b * y * (theta_e * Omega * y - vc - vi) * dy           (blade element, b = Nb c a Omega / 2)
    dT = 4 pi rho y vi (vi + kappa vc) / kappa^2 * dy                  (annulus momentum, scaled by kappa)

so ``vi`` is the positive root of ``A2 vi^2 + A1 vi + A0 = 0`` with ``A2 = 4 pi / kappa^2``,
``A1 = 4 pi vc / kappa + b`` and ``A0 = -b (theta_e Omega y - vc)``. ``theta_e`` is the blade pitch above the
zero-lift angle. The torque adds the induced part ``v dT / Omega`` and the profile drag
``1/2 rho Nb c (Omega y)^2 cd(cl) y dy`` with ``cd = d0 + d2 (cl - clm)^2``. Everything is written without a
division by Omega, so the law is smooth through a standstill.

The coaxial pair follows Grip et al. (ERF 2017): the lower rotor sees the uniform (area-mean) induced
velocity of the upper rotor as extra climb inflow; the upper rotor does not see the lower one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import ingenuity_data as D

N_STATIONS = 16
D_EPS = 1.0          # (m/s)^2 smoothing of the discriminant (as `Deps` of the Julia block)


@dataclass(frozen=True)
class Blade:
    y: np.ndarray        # m   station radius
    c: np.ndarray        # m   chord
    tw: np.ndarray       # rad twist relative to the 0.75 R pitch (theta = theta_75 + tw)
    wl: np.ndarray       # m   lift weight (trapezoid dy, zero outboard of the tip-loss radius)
    wd: np.ndarray       # m   drag weight (trapezoid dy)
    a: float             # 1/rad lift slope
    alpha0: float        # rad zero-lift angle


def blade(n: int = N_STATIONS) -> Blade:
    r_tab = np.array(D.BLADE_R)
    c_tab = np.array(D.BLADE_C) * D.RADIUS
    tw_tab = np.radians(np.array(D.BLADE_TWIST_DEG))
    tw75 = float(np.interp(0.75, r_tab, tw_tab))
    r = np.linspace(r_tab[0], 1.0, n)
    dr = np.gradient(r) * 0.0
    dr[1:-1] = 0.5 * (r[2:] - r[:-2])
    dr[0] = 0.5 * (r[1] - r[0])
    dr[-1] = 0.5 * (r[-1] - r[-2])
    y = r * D.RADIUS
    wd = dr * D.RADIUS
    # tip loss: lift only inboard of B R (the station weight is cut at B R)
    lo = r - np.where(np.arange(n) > 0, 0.5 * np.diff(r, prepend=r[0]), 0.0)
    hi = r + np.where(np.arange(n) < n - 1, 0.5 * np.diff(r, append=r[-1]), 0.0)
    wl = np.clip(np.minimum(hi, D.TIP_LOSS_B) - lo, 0.0, None) * D.RADIUS
    return Blade(y=y, c=np.interp(r, r_tab, c_tab), tw=np.interp(r, r_tab, tw_tab) - tw75, wl=wl, wd=wd,
                 a=D.CL_ALPHA, alpha0=math.radians(D.ALPHA_0_DEG))


def solidity(b: Blade) -> tuple[float, float]:
    """Geometric solidity (chord-area) and thrust-weighted solidity 3 int sigma(r) r^2 dr."""
    sig = D.NB * b.c / (math.pi * D.RADIUS)
    r = b.y / D.RADIUS
    geo = float(np.sum(sig * b.wd) / D.RADIUS)
    tw = float(3.0 * np.sum(sig * r * r * b.wd) / D.RADIUS)
    return geo, tw


@dataclass(frozen=True)
class Polar:
    d0: float
    d2: float
    clm: float


def rotor(b: Blade, pol: Polar, theta75: float, omega: float, vc: float, rho: float, kappa: float = D.KAPPA):
    """Thrust (N), torque (N m, aerodynamic, >= 0 for omega > 0), area-mean induced velocity (m/s)."""
    th_e = theta75 + b.tw - b.alpha0
    bh = D.NB * b.c * b.a / 2.0
    bb = bh * omega * (b.wl / np.maximum(b.wd, 1e-12))    # zero outboard of the tip-loss radius
    a2 = 4.0 * math.pi / kappa**2
    a1 = 4.0 * math.pi * vc / kappa + bb
    a0 = -bb * (th_e * omega * b.y - vc)
    dd = a1 * a1 - 4.0 * a2 * a0
    # smooth positive part of the discriminant (negative only where a station makes negative lift)
    vi = (-a1 + np.sqrt(0.5 * (dd + np.sqrt(dd * dd + D_EPS * D_EPS)))) / (2.0 * a2)
    v = vc + vi
    u = th_e * omega * b.y - v                      # (Omega y) * alpha
    dT = rho * bh * omega * b.y * u * b.wl
    # cl (Omega y)^2 = a (Omega y) u ;  cd (Omega y)^2 = d0 (Omega y)^2 + d2 (a u - clm Omega y)^2
    cdq = pol.d0 * (omega * b.y) ** 2 + pol.d2 * (b.a * u - pol.clm * omega * b.y) ** 2
    dQ = rho * bh * b.y * u * v * b.wl + 0.5 * rho * D.NB * b.c * cdq * b.y * b.wd
    v0 = float(np.sum(2.0 * b.y * vi * b.wd) / D.RADIUS**2)
    return float(np.sum(dT)), float(np.sum(dQ)), v0


def coax(b: Blade, pol: Polar, th_u: float, th_l: float, omega: float, vc: float, rho: float, kappa: float = D.KAPPA):
    tu, qu, vu = rotor(b, pol, th_u, omega, vc, rho, kappa)
    tl, ql, vl = rotor(b, pol, th_l, omega, vc + vu, rho, kappa)
    return tu, qu, tl, ql, vu


def trim(b: Blade, pol: Polar, thrust: float, omega: float, rho: float, vc: float = 0.0, kappa: float = D.KAPPA):
    """Upper and lower collective for a total thrust with zero net torque (Newton on two unknowns)."""
    x = np.radians([8.0, 9.0])
    for _ in range(60):
        def f(z):
            tu, qu, tl, ql, _ = coax(b, pol, z[0], z[1], omega, vc, rho, kappa)
            return np.array([tu + tl - thrust, qu - ql])
        f0 = f(x)
        J = np.zeros((2, 2))
        for k in range(2):
            dz = np.zeros(2); dz[k] = 1e-6
            J[:, k] = (f(x + dz) - f0) / 1e-6
        step = np.linalg.solve(J, -f0)
        x = x + step
        if np.max(np.abs(step)) < 1e-12:
            break
    tu, qu, tl, ql, vu = coax(b, pol, x[0], x[1], omega, vc, rho, kappa)
    return {"theta_u": float(x[0]), "theta_l": float(x[1]), "T_u": tu, "T_l": tl, "Q_u": qu, "Q_l": ql,
            "P_shaft": (qu + ql) * omega, "v_u": vu}


def cyclic_moment_gain(b: Blade, rho: float, omega: float) -> float:
    """Hub moment per radian of cyclic pitch for one rotor (stiff hingeless rotor, quasi-steady):
    the 1/rev lift asymmetry, averaged over a revolution, M = Nb/2 * int 1/2 rho c a (Omega y)^2 y dy."""
    return float(D.NB / 2.0 * np.sum(0.5 * rho * b.c * b.a * (omega * b.y) ** 2 * b.y * b.wl))


def edgewise_moment_gain(b: Blade, rho: float, omega: float) -> float:
    """Hub moment per m/s of edgewise airspeed for one rotor from the Pitt-Peters longitudinal inflow
    gradient (small skew: dv = 15 pi/64 V (y/R) cos psi), before Grip's amplification factor."""
    return float(D.NB / 2.0 * np.sum(0.5 * rho * b.c * b.a * omega * b.y * (15.0 * math.pi / 64.0) * (b.y / D.RADIUS)
                                    * b.y * b.wl))
