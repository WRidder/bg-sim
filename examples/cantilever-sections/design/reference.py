# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Independent references of the cantilever-sections example (numpy/scipy, no BG-Sim code).

Three steel cantilevers, L = 2 m, clamped at x = 0, with a downward tip force F(t):

* an I-beam: IPE 100 (h 100, b 55, tw 4.1, tf 5.7 mm) without its root fillets, bent about
  its strong axis (web vertical);
* a solid round bar and a solid square bar with the same area as the I-beam, so all three
  weigh the same per metre.

What it computes, each from first principles:

1. section properties: the I-beam's area, second moment and section modulus from its three
   rectangles with the parallel-axis theorem; round and square bars from their formulas;
2. Euler-Bernoulli statics: tip deflection F L^3/(3 E I) (+ q L^4/(8 E I) of the own weight),
   root moment F L (+ q L^2/2), bending stress M c / I = M / W, utilisation sigma / fy;
3. eigenfrequencies: the roots of 1 + cos(bL) cosh(bL) = 0 (brentq), f = (b^2/2 pi) sqrt(E I/(rho A));
4. a finite element model (60 Hermite beam elements, consistent mass, numpy/scipy eigh) with
   modal damping zeta on every mode: the step response maximum of the tip, the steady-state
   tip and root-moment amplitude of a sine force (frequency response) and the largest root
   moment after the step (exact discretisation of every mode), against which the
   three-mode model of the example is checked;
5. the three-mode assumed-modes numbers (mode tables by quadrature of the closed-form mode
   shapes), so the README can state the truncation error.

It writes `reference.json` next to it; `build.py` reads that file for `expected.json`.

    uv run examples/cantilever-sections/design/reference.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.linalg import eigh, expm
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- data (also the model defaults)
E = 210.0e9  # Pa, steel
RHO = 7850.0  # kg/m^3
FY = 235.0e6  # Pa, S235 yield strength
L = 2.0  # m
ZETA = 0.02  # modal damping ratio, every mode
G0 = 9.81  # m/s^2 (the self-weight scenario)
# IPE 100 (EN 10365) without root fillets
IPE = {"h": 0.100, "b": 0.055, "tw": 0.0041, "tf": 0.0057}
# load cases
F0 = 250.0  # N, constant tip force (step at T0)
T0 = 0.2  # s
FA_OFF, F_OFF = 50.0, 4.0  # N, Hz: sine well below every resonance
FA_RES = 10.0  # N: sine at the round bar's first eigenfrequency
N_EL = 60  # finite elements per beam


# ---------------------------------------------------------------- 1. sections
def ibeam_section(h: float, b: float, tw: float, tf: float) -> dict:
    """Area, strong-axis I and W of an I-section from its three rectangles (parallel axis)."""
    hw = h - 2 * tf
    parts = [  # (area, centroid z, own I)
        (b * tf, +(h - tf) / 2, b * tf**3 / 12),  # top flange
        (b * tf, -(h - tf) / 2, b * tf**3 / 12),  # bottom flange
        (tw * hw, 0.0, tw * hw**3 / 12),  # web
    ]
    area = sum(a for a, _, _ in parts)
    zc = sum(a * z for a, z, _ in parts) / area
    inertia = sum(i0 + a * (z - zc) ** 2 for a, z, i0 in parts)
    c = h / 2
    return {"A": area, "I": inertia, "c": c, "W": inertia / c}


def round_section(area: float) -> dict:
    d = math.sqrt(4 * area / math.pi)
    inertia = math.pi * d**4 / 64
    return {"d": d, "A": math.pi * d**2 / 4, "I": inertia, "c": d / 2, "W": inertia / (d / 2)}


def square_section(area: float) -> dict:
    a = math.sqrt(area)
    inertia = a**4 / 12
    return {"a": a, "A": a * a, "I": inertia, "c": a / 2, "W": inertia / (a / 2)}


# ---------------------------------------------------------------- 3. eigenvalues
def cantilever_lambdas(n: int = 3) -> list[float]:
    """The first n roots of 1 + cos(l) cosh(l) = 0 (scaled form, no overflow)."""
    g = lambda x: math.cos(x) + 1.0 / math.cosh(x)  # noqa: E731 (same roots)
    roots = []
    for k in range(n):
        lo, hi = (2 * k + 1) * math.pi / 2 - 1.2, (2 * k + 1) * math.pi / 2 + 1.2
        roots.append(brentq(g, max(lo, 0.5), hi, xtol=1e-14))
    return roots


# ---------------------------------------------------------------- 5. assumed modes
def phi(lam: float, xi: float) -> float:
    """Clamped-free mode shape at xi = s/L, normalised (1/L) int phi^2 = 1."""
    sg = (math.sinh(lam) - math.sin(lam)) / (math.cosh(lam) + math.cos(lam))
    x = lam * xi
    return math.cosh(x) - math.cos(x) - sg * (math.sinh(x) - math.sin(x))


def mode_tables(lams: list[float]) -> dict:
    out = {"lambda": lams, "norm": [], "phiL": [], "ta": [], "tb": [], "d2phi0": []}
    for lam in lams:
        out["norm"].append(quad(lambda x: phi(lam, x) ** 2, 0, 1, limit=200)[0])
        out["phiL"].append(phi(lam, 1.0))
        out["ta"].append(quad(lambda x: phi(lam, x), 0, 1, limit=200)[0])
        out["tb"].append(quad(lambda x: x * phi(lam, x), 0, 1, limit=200)[0])
        h = 1e-4  # second derivative at the root by a one-sided stencil, in units of 1/L^2
        out["d2phi0"].append((2 * phi(lam, 0) - 5 * phi(lam, h) + 4 * phi(lam, 2 * h) - phi(lam, 3 * h)) / h**2)
    return out


# ---------------------------------------------------------------- 4. finite elements
def fe_beam(EI: float, rhoA: float, length: float, n_el: int):
    """Clamped-free Euler-Bernoulli beam of Hermite elements: K, M (free DOFs), the tip
    deflection DOF index and the vector r with r.u = int s rhoA w ds (s-weighted mass)."""
    le = length / n_el
    k_e = EI / le**3 * np.array([[12, 6 * le, -12, 6 * le], [6 * le, 4 * le**2, -6 * le, 2 * le**2],
                                 [-12, -6 * le, 12, -6 * le], [6 * le, 2 * le**2, -6 * le, 4 * le**2]])
    m_e = rhoA * le / 420 * np.array([[156, 22 * le, 54, -13 * le], [22 * le, 4 * le**2, 13 * le, -3 * le**2],
                                      [54, 13 * le, 156, -22 * le], [-13 * le, -3 * le**2, -22 * le, 4 * le**2]])
    ndof = 2 * (n_el + 1)
    K = np.zeros((ndof, ndof))
    M = np.zeros((ndof, ndof))
    r = np.zeros(ndof)
    gx, gw = np.polynomial.legendre.leggauss(6)
    for e in range(n_el):
        idx = slice(2 * e, 2 * e + 4)
        K[idx, idx] += k_e
        M[idx, idx] += m_e
        for x, w in zip(gx, gw):
            xi = (x + 1) / 2
            n = np.array([1 - 3 * xi**2 + 2 * xi**3, le * (xi - 2 * xi**2 + xi**3), 3 * xi**2 - 2 * xi**3, le * (-xi**2 + xi**3)])
            s = (e + xi) * le
            r[idx] += w * le / 2 * rhoA * s * n
    free = np.arange(2, ndof)  # clamp: w(0) = w'(0) = 0
    return K[np.ix_(free, free)], M[np.ix_(free, free)], ndof - 4, r[free]


def fe_modes(K, M):
    w2, V = eigh(K, M)  # mass-normalised: V.T M V = I
    return np.sqrt(w2), V


def fe_frf(omega_n, V, tip: int, r, F: float, w: float, zeta: float, length: float):
    """Steady-state complex tip deflection and root moment for F sin(w t) (modal damping)."""
    q = V[tip, :] * F / (omega_n**2 - w**2 + 2j * zeta * omega_n * w)
    u = V @ q
    tip_w = u[tip]
    # M(0) = F L - int s rhoA w'' ds = F L + w^2 r.u (harmonic)
    m_root = F * length + w**2 * (r @ u)
    return tip_w, m_root


def fe_step_moment_max(omega_n, V, tip: int, r, F: float, zeta: float, length: float,
                       dt: float = 2e-5, t_end: float = 1.0) -> float:
    """Largest |root moment| of the step response (all FE modes): each modal oscillator is
    discretised exactly (matrix exponential, the step is constant between samples), and
    M(0) = F L - int s rhoA w'' ds = F L - r . u''."""
    n = len(omega_n)
    b = V[tip, :]
    phi = np.zeros((n, 2, 2))
    gam = np.zeros((n, 2))
    for i, om in enumerate(omega_n):
        aug = np.zeros((3, 3))
        aug[:2, :2] = np.array([[0.0, 1.0], [-om**2, -2 * zeta * om]]) * dt
        aug[:2, 2] = np.array([0.0, b[i]]) * dt
        e = expm(aug)
        phi[i], gam[i] = e[:2, :2], e[:2, 2]
    rv = r @ V
    x = np.zeros((n, 2))
    m_max = 0.0
    for _ in range(int(round(t_end / dt))):
        x = np.einsum("kij,kj->ki", phi, x) + gam * F
        qdd = b * F - omega_n**2 * x[:, 0] - 2 * zeta * omega_n * x[:, 1]
        m_max = max(m_max, abs(F * length - rv @ qdd))
    return m_max


def fe_step_max(omega_n, V, tip: int, F: float, zeta: float, t_end: float) -> tuple[float, float]:
    """Largest tip deflection of the damped step response (all FE modes) and the static value."""
    t = np.linspace(0.0, t_end, 400001)
    wd = omega_n * math.sqrt(1 - zeta**2)
    amp = V[tip, :] ** 2 * F / omega_n**2
    y = np.zeros_like(t)
    for a, wn, wdn in zip(amp, omega_n, wd):
        y += a * (1 - np.exp(-zeta * wn * t) * (np.cos(wdn * t) + zeta / math.sqrt(1 - zeta**2) * np.sin(wdn * t)))
    return float(np.max(y)), float(np.sum(amp))


def main() -> None:
    ib = ibeam_section(**IPE)
    sections = {"ipe": ib, "round": round_section(ib["A"]), "square": square_section(ib["A"])}
    lams = cantilever_lambdas(3)
    tables = mode_tables(lams)
    q_weight = RHO * ib["A"] * G0  # N/m, the same for all three
    out: dict = {"inputs": {"E": E, "rho": RHO, "fy": FY, "L": L, "zeta": ZETA, "g0": G0, "ipe": IPE,
                            "F0": F0, "t0": T0, "Fa_off": FA_OFF, "f_off": F_OFF, "Fa_res": FA_RES, "n_el": N_EL},
                 "modes": tables, "beams": {}}
    sum4 = sum(p * p / lam**4 for p, lam in zip(tables["phiL"], lams))
    for name, sec in sections.items():
        EI, rhoA = E * sec["I"], RHO * sec["A"]
        f_eb = [lam**2 / (2 * math.pi) * math.sqrt(EI / (rhoA * L**4)) for lam in lams]
        K, M, tip, r = fe_beam(EI, rhoA, L, N_EL)
        wn, V = fe_modes(K, M)
        f_fe = (wn[:3] / (2 * math.pi)).tolist()
        static = F0 * L**3 / (3 * EI)
        m_root = F0 * L
        sigma = m_root / sec["W"]
        step_max, step_static = fe_step_max(wn, V, tip, F0, ZETA, 9.8)
        step_m_max = fe_step_moment_max(wn, V, tip, r, F0, ZETA, L)
        f_res = f_eb[0] if name == "round" else None
        b: dict = {
            "section": sec, "EI": EI, "rhoA": rhoA, "mass": rhoA * L,
            "f_eb": f_eb, "f_fe": f_fe,
            "static": {"w_tip": static, "M_root": m_root, "sigma": sigma, "util": sigma / FY,
                       "w_tip_fe": step_static, "w_tip_3modes": F0 * L**3 / EI * sum4,
                       "M_modal_3modes": 2 * F0 * L * sum(p / lam**2 for p, lam in zip(tables["phiL"], lams))},
            "step": {"w_max_fe": step_max, "overshoot": step_max / step_static, "M_max_fe": step_m_max,
                     "sigma_max_fe": step_m_max / sec["W"], "util_max_fe": step_m_max / sec["W"] / FY},
            "weight": {"q": q_weight, "w_tip": F0 * L**3 / (3 * EI) + q_weight * L**4 / (8 * EI),
                       "M_root": F0 * L + q_weight * L**2 / 2,
                       "sigma": (F0 * L + q_weight * L**2 / 2) / sec["W"],
                       "w_tip_3modes": F0 * L**3 / EI * sum4 + q_weight * L**4 / EI * sum(
                           p * ta / lam**4 for p, ta, lam in zip(tables["phiL"], tables["ta"], lams))},
        }
        for key, fa, fhz in (("sine_off", FA_OFF, F_OFF), ("sine_res", FA_RES, None)):
            fhz = fhz if fhz is not None else sections_f_res(lams, sections["round"])
            tw, mr = fe_frf(wn, V, tip, r, fa, 2 * math.pi * fhz, ZETA, L)
            b[key] = {"Fa": fa, "f": fhz, "w_amp": abs(tw), "M_amp": abs(mr), "sigma_amp": abs(mr) / sec["W"],
                      "dyn_factor": abs(tw) / (fa * L**3 / (3 * EI))}
        del f_res
        out["beams"][name] = b
    with open(HERE / "reference.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    # report
    print(f"lambda {lams}")
    print(f"modes: norm {tables['norm']}, phiL {tables['phiL']}, ta {tables['ta']}, tb {tables['tb']}, phi''(0) L^2/lambda^2 {[d / l**2 for d, l in zip(tables['d2phi0'], lams)]}")
    print(f"3-mode static tip fraction {3 * sum4:.5f}, root moment fraction {out['beams']['ipe']['static']['M_modal_3modes'] / (F0 * L):.5f}")
    for name, b in out["beams"].items():
        s = b["section"]
        print(f"{name:7s} A {s['A'] * 1e4:.4f} cm2  I {s['I'] * 1e8:.3f} cm4  W {s['W'] * 1e6:.3f} cm3  m/L {b['rhoA']:.3f} kg/m")
        print(f"        f_eb {['%.4f' % v for v in b['f_eb']]} Hz   f_fe {['%.4f' % v for v in b['f_fe']]} Hz")
        st = b["static"]
        print(f"        static w {st['w_tip'] * 1e3:.4f} mm (FE {st['w_tip_fe'] * 1e3:.4f}, 3 modes {st['w_tip_3modes'] * 1e3:.4f})  M {st['M_root']:.1f} N m  sigma {st['sigma'] / 1e6:.3f} MPa  util {st['util']:.4f}")
        print(f"        step max {b['step']['w_max_fe'] * 1e3:.4f} mm (overshoot {b['step']['overshoot']:.4f}), M max {b['step']['M_max_fe']:.2f} N m, util max {b['step']['util_max_fe']:.4f}")
        print(f"        weight w {b['weight']['w_tip'] * 1e3:.4f} mm (3 modes {b['weight']['w_tip_3modes'] * 1e3:.4f}) M {b['weight']['M_root']:.2f}")
        for key in ("sine_off", "sine_res"):
            v = b[key]
            print(f"        {key}: {v['Fa']} N @ {v['f']:.4f} Hz  w_amp {v['w_amp'] * 1e3:.4f} mm  (x{v['dyn_factor']:.3f})  M_amp {v['M_amp']:.2f} N m  sigma {v['sigma_amp'] / 1e6:.3f} MPa")


def sections_f_res(lams: list[float], rnd: dict) -> float:
    """The resonance case drives at the round bar's first Euler-Bernoulli eigenfrequency."""
    return lams[0] ** 2 / (2 * math.pi) * math.sqrt(E * rnd["I"] / (RHO * rnd["A"] * L**4))


if __name__ == "__main__":
    main()
