"""The first fore-aft tower mode of the NREL 5 MW turbine as one modal mass-spring-damper.

The tower of chapter 6 of the report: a steel tube, 87.6 m high, clamped at the ground, with the
diameter tapering linearly from 6 m to 3.87 m and the wall from 35.1 mm to 24.7 mm (the DOWEC
tower's 27 mm and 19 mm raised by 30 %), E = 210 GPa and an
effective density of 8500 kg/m^3 (the report raises 7850 to account for paint, bolts, welds and
flanges). Its mass is 347,460 kg. The rotor and nacelle (350,000 kg) sit on top.

A 60-element Euler-Bernoulli finite-element model (cubic Hermite elements, consistent mass) gives
the first bending mode. Normalised to a unit tower-top deflection, the mode is one degree of
freedom x (the tower-top fore-aft displacement) with the generalised mass m = phi^T M phi, the
stiffness k = omega^2 m and the report's structural damping of 1 % of critical, c = 2 zeta m omega.
The thrust acts at the tower top, so its generalised force is the thrust itself.

The rotor and nacelle sit on the tower top as one rigid body (`rna_body`: their mass, the height of
their centre of mass above the tower top and their nodding inertia). The report's full-system
first fore-aft frequency is 0.3240 Hz (FAST) and 0.3195 Hz (ADAMS), Table 9-1.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.linalg import eigh

import nrel5mw as T


def rna_body() -> dict:
    """Mass, centre-of-mass height above the tower top and pitch (nodding) inertia of the rotor-nacelle
    assembly, from the report's Table 1-1 and chapter 4: the rotor (110 t) at the hub, 5 m upwind and
    2.4 m above the tower top; the nacelle (240 t) with its centre of mass 1.9 m downwind and 1.75 m
    above the yaw bearing and an inertia of 2,607,890 kg m^2 about the yaw axis (used about the
    pitch axis too); the rotor's inertia about a diameter taken as half the blades' inertia about
    the shaft (35.3e6 kg m^2, chapter 2)."""
    m_r, m_n = T.M_ROTOR, T.M_NACELLE
    xr, zr = -5.0, 2.4
    xn, zn = 1.9, 1.75
    m = m_r + m_n
    xc, zc = (m_r * xr + m_n * xn) / m, (m_r * zr + m_n * zn) / m
    j_rotor = 0.5 * 3 * 11_776_047.0
    j_nac = 2_607_890.0
    j = (j_rotor + m_r * ((xr - xc) ** 2 + (zr - zc) ** 2) + j_nac + m_n * ((xn - xc) ** 2 + (zn - zc) ** 2))
    return {"mass": m, "x_cm": xc, "h_cm": zc, "J_pitch": j}


def tower_mode(n_el: int = 60) -> dict:
    tw = T.TOWER
    L = T.TOWER_HEIGHT
    z = np.linspace(0.0, L, n_el + 1)
    ndof = 2 * (n_el + 1)
    K = np.zeros((ndof, ndof))
    M = np.zeros((ndof, ndof))
    mass = 0.0
    for e in range(n_el):
        zm = 0.5 * (z[e] + z[e + 1])
        s = zm / L
        d = tw["base_diameter"] + s * (tw["top_diameter"] - tw["base_diameter"])
        t = tw["base_thickness"] + s * (tw["top_thickness"] - tw["base_thickness"])
        A = math.pi / 4.0 * (d ** 2 - (d - 2 * t) ** 2)
        I = math.pi / 64.0 * (d ** 4 - (d - 2 * t) ** 4)
        h = z[e + 1] - z[e]
        EI = tw["E"] * I
        mA = tw["density"] * A
        mass += mA * h
        ke = EI / h ** 3 * np.array([[12, 6 * h, -12, 6 * h], [6 * h, 4 * h * h, -6 * h, 2 * h * h],
                                     [-12, -6 * h, 12, -6 * h], [6 * h, 2 * h * h, -6 * h, 4 * h * h]])
        me = mA * h / 420.0 * np.array([[156, 22 * h, 54, -13 * h], [22 * h, 4 * h * h, 13 * h, -3 * h * h],
                                        [54, 13 * h, 156, -22 * h], [-13 * h, -3 * h * h, -22 * h, 4 * h * h]])
        idx = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
        K[np.ix_(idx, idx)] += ke
        M[np.ix_(idx, idx)] += me
    top = 2 * n_el
    rna = rna_body()
    m_rna, h, j = rna["mass"], rna["h_cm"], rna["J_pitch"]
    # the rotor-nacelle assembly as a rigid body on the tower top (deflection w, slope theta):
    # its centre of mass moves by w + h theta, it turns by theta
    M[top, top] += m_rna
    M[top, top + 1] += m_rna * h
    M[top + 1, top] += m_rna * h
    M[top + 1, top + 1] += m_rna * h * h + j
    free = slice(2, ndof)               # clamped at the ground
    w2, V = eigh(K[free, free], M[free, free])
    phi = np.zeros(ndof)
    phi[free] = V[:, 0] / V[top - 2, 0]  # unit tower-top deflection
    m_gen = float(phi @ M @ phi)
    omega = math.sqrt(w2[0])
    k_gen = omega ** 2 * m_gen
    zeta = tw["damping_ratio"]
    return {"f1_hz": omega / (2 * math.pi), "f2_hz": math.sqrt(w2[1]) / (2 * math.pi), "omega": omega,
            "m_gen": m_gen, "k_gen": k_gen, "c_gen": 2.0 * zeta * m_gen * omega, "zeta": zeta,
            "tower_mass_fe": mass, "tower_mass_report": T.M_TOWER, "n_el": n_el,
            "m_gen_tower_share": m_gen - (T.M_ROTOR + T.M_NACELLE)}


if __name__ == "__main__":
    print(tower_mode())
