# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Reference data of the hybrid-powersplit example (writes design/design.json).

    uv run examples/hybrid-powersplit/design/design.py

Everything the models and the checks use is computed here, deterministically:

* the Toyota Prius (NHW20, THS-II) data with its sources (see the README for the full list);
* the NEDC drive cycle, generated exactly from its definition (UN ECE R83 / 70/220/EEC as
  amended by 98/69/EC: four ECE-15 urban cycles and one EUDC; piecewise linear, 1180 s);
* the 1NZ-FXE engine: the full-load torque curve through the two published points and a
  Willans-line fuel model (indicated efficiency e(n), friction torque T_f(n)) calibrated to the
  published peak brake efficiency, tabulated as a fuel-rate map; the optimal operating line
  (the minimum-fuel speed for every engine power) from that map;
* the transaxle spin losses, a Coulomb + viscous fit to ORNL's measured gear losses;
* the motor/generator loss model (copper loss c T^2 and iron loss b w^2) calibrated to ORNL's
  measured peak motor/inverter efficiency;
* the references of the checks: NEDC distance, braking energy, regenerative share and on-time
  bounds (from the cycle trace), the EV launch (closed-form quadratic-drag solution and a 1-DOF
  ODE with the losses), the kinematics steady state.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, minimize_scalar

HERE = Path(__file__).resolve().parent
RPM = 2 * math.pi / 60

# --------------------------------------------------------------------------- vehicle data
VEH = {
    # Toyota Prius NHW20 (2004), Toyota specification: curb mass 1310 kg, Cd 0.26,
    # tyres 185/65 R15; plus a 75 kg driver (the NEDC reference mass convention).
    "m_curb": 1310.0, "m_driver": 75.0,
    "Cd": 0.26, "A": 2.2, "rho": 1.2,
    "c_rr": 0.009,                 # rolling resistance coefficient (low rolling resistance tyre, assumed)
    "r_w": 0.30,                   # rolling radius: 185/65 R15 free radius 0.311 m x 0.965
    "J_wheel": 0.8,                # per wheel incl. tyre and brake disc (assumed)
    "g": 9.80665,
}
VEH["m"] = VEH["m_curb"] + VEH["m_driver"]
VEH["m_rot"] = 4 * VEH["J_wheel"] / VEH["r_w"] ** 2
VEH["m_eq"] = VEH["m"] + VEH["m_rot"]

PSD = {
    # THS-II power split device (ORNL/TM-2006/423, Fig. 2.6): sun 30, ring 78 teeth; ring to axle 4.113.
    "Zs": 30.0, "Zr": 78.0, "FD": 4.113,
    "J_e": 0.18,        # engine crankshaft + flywheel/damper (assumed)
    "J_sun": 0.0005,    # sun gear (assumed)
    "J_mg1": 0.0085,    # MG1 rotor (assumed)
    "J_ring": 0.010,    # ring gear + counter drive gear (assumed)
    "J_mg2": 0.0326,    # MG2 rotor: ORNL rotor mass 10.2 kg, J = m r^2/2 with r = 0.08 m
    "k_damper": 1000.0, "d_damper": 3.0,       # transaxle input damper (assumed)
    "k_shaft": 12000.0, "d_shaft": 40.0,       # both half shafts at the wheel (assumed)
}

ENG = {
    # 1NZ-FXE, 1.497 l Atkinson cycle (ORNL/TM-2006/423 Table 2.1: 57 kW at 5000 rpm,
    # 115 N*m at 4200 rpm). Peak brake thermal efficiency: 36.4 % measured by ANL on the
    # first-generation engine (Duoba et al., SAE 2000-01-3096); about 37 % for the THS-II
    # engine (Toyota). The fit below is calibrated to eta_max = 0.37.
    "Vd": 1.497e-3, "LHV": 43.0e6, "rho_fuel": 0.745,
    "n_min": 1000.0, "n_max": 5000.0, "n_fire": 800.0,  # firing speed: fuel and spark fade in around it (MG1 cranks the engine up)
    "eta_max": 0.37,
}
# full-load (WOT) torque, N*m over rpm: through the two published points (115 N*m at 4200 rpm,
# 57 kW = 108.9 N*m at 5000 rpm); the shape below 4200 rpm is a smooth assumed curve
WOT_RPM = [0.0, 800.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 4200.0, 4500.0, 5000.0, 5200.0]
WOT_NM = [60.0, 76.0, 80.0, 92.0, 100.0, 104.0, 108.0, 111.0, 114.0, 115.0, 114.0, 57000.0 / (5000 * RPM), 104.0]


def wot(n_rpm):
    return np.interp(n_rpm, WOT_RPM, WOT_NM)


def friction_torque(n_rpm):
    """Friction + pumping torque of the Willans line, N*m (FMEP 69 kPa at 1000 rpm, 143 kPa at 5000 rpm)."""
    return 7.0 + 1.0e-3 * n_rpm + 2.0e-7 * n_rpm ** 2


def e_shape(n_rpm, T):
    """Relative indicated efficiency: best at 2800 rpm, a mild loss at both speed ends and
    near full load (spark retard)."""
    s = 1.0 - 0.08 * ((n_rpm - 2800.0) / 2800.0) ** 2
    x = np.maximum(T / wot(n_rpm) - 0.88, 0.0)
    return s * (1.0 - 2.0 * x ** 2)


def _eta_b(n, T, e0):
    return e0 * e_shape(n, T) * T / (T + friction_torque(n))


def _calibrate_e0() -> float:
    def best(e0):
        ns = np.linspace(1000, 5000, 401)
        return max(float(np.max(_eta_b(n, np.linspace(1, wot(n), 200), e0))) for n in ns)
    return brentq(lambda e0: best(e0) - ENG["eta_max"], 0.3, 0.6)


E0 = _calibrate_e0()


def fuel_rate(n_rpm, T):
    """Fuel mass flow (kg/s) of the running engine at speed n and brake torque T >= 0."""
    T = np.maximum(T, 0.0)
    w = n_rpm * RPM
    return (T + friction_torque(n_rpm)) * w / (E0 * e_shape(n_rpm, T) * ENG["LHV"])


def bsfc(n_rpm, T):
    return fuel_rate(n_rpm, T) * 3.6e9 / np.maximum(T * n_rpm * RPM, 1e-9)  # g/kWh


# the fuel-rate map table (Lookup2D: breaks row 1 = speed (rad/s), row 2 = torque (N*m))
NF = 12
MAP_W = np.linspace(0.0, 5500.0, NF) * RPM
MAP_T = np.linspace(0.0, 121.0, NF)
MAP_FUEL = np.array([[float(fuel_rate(w / RPM, T)) for w in MAP_W] for T in MAP_T])  # row i: torque i


def map_fuel(w, T):
    """Bilinear interpolation of the table, exactly what interp2 of the models evaluates."""
    from scipy.interpolate import RegularGridInterpolator
    f = RegularGridInterpolator((MAP_T, MAP_W), MAP_FUEL, bounds_error=False, fill_value=None)
    return float(f([[np.clip(T, MAP_T[0], MAP_T[-1]), np.clip(w, MAP_W[0], MAP_W[-1])]])[0])


def ool():
    """Optimal operating line: for each engine power the speed of minimum fuel rate (on the map
    table, so the controllers and the plant agree), torque below 98 % of full load."""
    P = np.linspace(0.0, 56000.0, 15)
    W = []
    for p in P:
        if p <= 0:
            W.append(ENG["n_min"] * RPM)
            continue
        ns = np.linspace(ENG["n_min"], ENG["n_max"], 801)
        best = None
        for n in ns:
            w = n * RPM
            T = p / w
            if T > 0.98 * wot(n):
                continue
            f = map_fuel(w, T)
            if best is None or f < best[0]:
                best = (f, w)
        W.append(best[1] if best else ENG["n_max"] * RPM)
    W = np.maximum.accumulate(np.array(W))  # monotone speed over power
    return P, W


OOL_P, OOL_W = ool()

# --------------------------------------------------------------------------- machines
# ORNL/TM-2006/423, section 3.3.3: the combined motor/inverter efficiency peaks at 92-93 % from
# about 2200 to 3000 rpm at 60-140 N*m; the lowest values are at low speed and high torque.
# Loss model P = c T^2 + b w^2 (copper as the stator R, iron as a viscous R): its best
# efficiency at speed w is 1/(1 + 2 sqrt(b c)) at T* = w sqrt(b/c). MG2: eta* = 0.93 at
# 2500 rpm, 100 N*m. MG1 (no ORNL map): the same eta* at its typical 5000 rpm, 30 N*m.


def loss_coefficients(eta, w, T):
    s = (1.0 / eta - 1.0) / 2.0          # sqrt(b c)
    q = T / w                            # sqrt(b / c)
    return s / q, s * q                  # c, b


C2, B2 = loss_coefficients(0.93, 2500 * RPM, 100.0)
C1, B1 = loss_coefficients(0.93, 5000 * RPM, 30.0)
MG = {
    # MG2: ORNL Table 2.1: 50 kW (1200-1540 rpm), 400 N*m (0-1540 rpm); 6000 rpm (ORNL tests).
    "T2_max": 400.0, "P2_max": 50000.0, "n2_max": 6000.0,
    # MG1: 10000 rpm (ORNL section 2.2.3); torque limit assumed (twice the engine reaction torque).
    "T1_max": 70.0, "n1_max": 10000.0,
    "c2": C2, "b2": B2, "c1": C1, "b1": B1,
    # DC-equivalent torque constants (back EMF 500 V, the boosted bus maximum, at top speed);
    # only R_s / k^2 = c enters the energy.
    "k2": 500.0 / (6000 * RPM), "k1": 500.0 / (10000 * RPM),
    # stator time constant L/R of the DC-equivalent winding (assumed): the current, and so the
    # torque, follows the inverter's feed-forward voltage with this lag
    "tau_el": 0.01,
}
MG["R2"] = MG["c2"] * MG["k2"] ** 2
MG["R1"] = MG["c1"] * MG["k1"] ** 2

# transaxle spin losses, ORNL/TM-2006/423 Table 3.7 (25 C oil, differential blocked): the "gear
# losses" column (reduction gears, drive chain, differential) over the motor-shaft (= ring) speed;
# x 0.8 for warm oil (ORNL: losses fall about 20 % from 27 to 80 C). The motor-rotor and the
# generator/planetary columns are left out: the machines' iron loss is in the MG loss model.
ORNL_N = np.array([494, 1000, 1506, 1991, 2501, 3007, 3501, 3999, 4505, 4999, 5492, 6006.0])
ORNL_GEAR = np.array([74.9, 158.5, 261.8, 369.8, 487.9, 617.2, 745.2, 915.6, 1058.2, 1220.8, 1425.2, 1645.3])
_w = ORNL_N * RPM
_A = np.vstack([_w, _w ** 2]).T
SPIN_C0, SPIN_C1 = np.linalg.lstsq(_A, 0.8 * ORNL_GEAR, rcond=None)[0]

BAT = {
    # NiMH pack: 28 modules x 6 cells x 1.2 V = 201.6 V, 6.5 A*h, 21 kW (ORNL Table 2.1).
    "capacity": 6.5, "cells": 168,
    "R0": 0.30, "R1": 0.10, "C1": 400.0,   # Thevenin model (assumed, pack level)
    "P_dis": 21000.0, "P_chg": 25000.0,    # power limits (21 kW: ORNL; charge assumed)
    "C_dc": 2.0e-3,                        # DC-link capacitor (assumed)
    "soc0": 0.60,
}
# typical NiMH open-circuit voltage per cell over the state of charge (assumed shape)
OCV_SOC = [0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0]
OCV_CELL = [1.10, 1.22, 1.26, 1.29, 1.31, 1.34, 1.37, 1.45]
OCV_V = [BAT["cells"] * v for v in OCV_CELL]


# --------------------------------------------------------------------------- NEDC
def nedc():
    """(t, v km/h) breakpoints of the NEDC (UN ECE R83 Annex 4 Appendix 1, EUDC Appendix 2)."""
    ece = [(0, 0), (11, 0), (15, 15), (23, 15), (25, 10), (28, 0), (49, 0), (54, 15), (56, 15), (61, 32),
           (85, 32), (93, 10), (96, 0), (117, 0), (122, 15), (124, 15), (133, 35), (135, 35), (143, 50),
           (155, 50), (163, 35), (176, 35), (178, 32), (185, 10), (188, 0), (195, 0)]
    eudc = [(0, 0), (20, 0), (25, 15), (27, 15), (36, 35), (38, 35), (46, 50), (48, 50), (61, 70), (111, 70),
            (119, 50), (188, 50), (201, 70), (251, 70), (286, 100), (316, 100), (336, 120), (346, 120),
            (362, 80), (370, 50), (380, 0), (400, 0)]
    pts = []
    for k in range(4):
        for t, v in ece:
            if pts and pts[-1][0] == t + 195 * k:
                continue
            pts.append((t + 195 * k, v))
    for t, v in eudc:
        if pts[-1][0] == t + 780:
            continue
        pts.append((t + 780, v))
    # drop the interior points of straight idle runs (keep the table short)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        if pts[i - 1][1] == pts[i][1] == pts[i + 1][1] == 0:
            continue
        out.append(pts[i])
    out.append(pts[-1])
    return out


NEDC = nedc()


def nedc_stats():
    t = np.array([p[0] for p in NEDC], float)
    v = np.array([p[1] for p in NEDC], float) / 3.6
    dist = float(np.trapezoid(v, t))
    ece_d = float(np.trapezoid(v[t <= 195], t[t <= 195]))
    eudc = t >= 780
    eudc_d = float(np.trapezoid(v[eudc], t[eudc]))
    return {"t_end": float(t[-1]), "distance_m": dist, "ece_m": ece_d, "eudc_m": eudc_d,
            "v_mean_kmh": dist / t[-1] * 3.6, "v_max_kmh": float(v.max() * 3.6), **regen_share(t, v),
            **on_time_bounds(t, v)}


def on_time_bounds(tb, vb):
    """Bounds of the engine on-time from the cycle alone: the engine is off at standstill, and it
    must turn above the speed where MG1 would exceed its limit with the engine at rest,
    w_r = Zs (w1_max - 50 rad/s) / Zr (the margin of the energy manager)."""
    t = np.arange(0.0, tb[-1], 0.01) + 0.005
    v = np.interp(t, tb, vb)
    G = PSD["FD"] / VEH["r_w"]
    w1 = MG["n1_max"] * RPM - 50.0
    v_spin = PSD["Zs"] * w1 / PSD["Zr"] / G
    return {"t_idle": float(np.sum(v <= 1e-9) * 0.01), "v_spin": float(v_spin),
            "t_above_spin": float(np.sum(v > v_spin) * 0.01)}


def regen_share(tb, vb, w_fade=25.0, w_fw=5.0):
    """Braking energy along the NEDC trace (rigid vehicle following the cycle exactly) and the
    share the friction brakes take: the ring torque the driver needs is
    T_rd = (m a + F_road)/G + T_loss(w_r); MG2 takes min(-T_rd, T_lim fade(w_r)) with the MG2 and
    charge-power envelope T_lim = min(400, 50 kW/w, 25 kW/w) and the fade-out
    fade = (1 + tanh((w_r - w_fade)/w_fw))/2 of the HCU; the brakes take the rest."""
    g = VEH
    G = PSD["FD"] / g["r_w"]
    m = ev_launch_mass()
    t = np.arange(0.0, tb[-1], 0.01) + 0.005
    v = np.interp(t, tb, vb)
    seg = np.searchsorted(tb, t) - 1
    a = (vb[seg + 1] - vb[seg]) / (tb[seg + 1] - tb[seg])
    wr = G * v
    k = 0.5 * g["rho"] * g["Cd"] * g["A"]
    F_road = g["c_rr"] * g["m"] * g["g"] * np.tanh(v / 0.05) + k * v * np.sqrt(v * v + 0.01)
    T_loss = (SPIN_C0 * np.tanh(wr / 2.0) + SPIN_C1 * wr + MG["b2"] * wr
              + MG["b1"] * (PSD["Zr"] / PSD["Zs"]) ** 2 * wr)
    T_rd = (m * a + F_road) / G + T_loss
    P_brk = np.maximum(-T_rd * wr, 0.0)
    aw = np.sqrt(wr * wr + 1.0)
    T_lim = np.minimum(np.minimum(400.0, 50000.0 / aw), 25000.0 / aw)
    fade = 0.5 * (1.0 + np.tanh((wr - w_fade) / w_fw))
    T_reg = np.minimum(np.maximum(-T_rd, 0.0), T_lim * fade)
    P_fric = np.maximum(-T_rd - T_reg, 0.0) * wr
    E_brk = float(P_brk.sum() * 0.01)
    E_fric = float(P_fric.sum() * 0.01)
    return {"E_brake_demand": E_brk, "E_friction": E_fric, "regen_share": 1.0 - E_fric / E_brk}


def ev_launch_mass():
    """Vehicle mass plus the reflected ring, MG2, sun and MG1 inertias (engine at rest)."""
    G = PSD["FD"] / VEH["r_w"]
    m_ring = (PSD["J_ring"] + PSD["J_mg2"]) * G ** 2
    m_sun = (PSD["J_sun"] + PSD["J_mg1"]) * (PSD["Zr"] / PSD["Zs"] * G) ** 2
    return VEH["m_eq"] + m_ring + m_sun


# --------------------------------------------------------------------------- references
def ev_launch(T_mg2=150.0, t_step=0.5, v_target_kmh=30.0):
    """Closed form of the EV launch: m_eq' dv/dt = F0 - k v^2 with F0 = T FD/r - c_rr m g,
    k = rho Cd A / 2 and m_eq' including the reflected ring, MG2, sun and MG1 inertias (the
    engine held at rest: w_sun = -(Zr/Zs) w_ring). v(t) = V tanh(t sqrt(F0 k)/m), V = sqrt(F0/k).
    The transaxle spin losses (about 1 % of the force here) are left out of the estimate."""
    g = VEH
    G = PSD["FD"] / g["r_w"]                       # ring speed per m/s
    m_ring = (PSD["J_ring"] + PSD["J_mg2"]) * G ** 2
    m_sun = (PSD["J_sun"] + PSD["J_mg1"]) * (PSD["Zr"] / PSD["Zs"] * G) ** 2
    m = g["m_eq"] + m_ring + m_sun
    F0 = T_mg2 * G - g["c_rr"] * g["m"] * g["g"]
    k = 0.5 * g["rho"] * g["Cd"] * g["A"]
    V = math.sqrt(F0 / k)
    vt = v_target_kmh / 3.6
    t_hit = math.atanh(vt / V) * m / math.sqrt(F0 * k)
    # The same launch with the drag terms the closed form leaves out: the transaxle spin loss
    # c0 tanh(w_r/2) + c1 w_r and the iron losses b2 w_r (MG2) and b1 w_s (MG1, w_s = -(Zr/Zs) w_r)
    # reflected to the wheels, the smoothed rolling resistance and aero drag of the model. A
    # 1-DOF ODE with rigid shafts (RK45), independent of the bond graph.
    from scipy.integrate import solve_ivp

    def rhs(_t, y):
        v = y[0]
        wr = G * v
        T_loss = (SPIN_C0 * math.tanh(wr / 2.0) + SPIN_C1 * wr + MG["b2"] * wr
                  + MG["b1"] * (PSD["Zr"] / PSD["Zs"]) ** 2 * wr)
        F = ((T_mg2 - T_loss) * G - g["c_rr"] * g["m"] * g["g"] * math.tanh(v / 0.05)
             - k * v * math.sqrt(v * v + 0.01))
        return [F / m]

    hit = lambda _t, y: y[0] - vt  # noqa: E731
    hit.terminal = True
    sol = solve_ivp(rhs, (0.0, 30.0), [0.0], events=hit, rtol=1e-10, atol=1e-12)
    t_ode = float(sol.t_events[0][0])
    return {"T_mg2": T_mg2, "t_step": t_step, "m_total": m, "F0": F0, "a0": F0 / m,
            "v_target": vt, "t_target_closed": t_step + t_hit, "t_target": t_step + t_ode,
            "F_demand": T_mg2 * G}


def kinematics():
    """hybrid-kinematics: carrier torque T_c (step), viscous loads b_s on the sun and b_r on the
    ring (each with its inertia). Steady state: T_s = Zs/(Zs+Zr) T_c = b_s w_s,
    T_r = Zr/(Zs+Zr) T_c = b_r w_r, w_c = (Zs w_s + Zr w_r)/(Zs + Zr)."""
    Zs, Zr = PSD["Zs"], PSD["Zr"]
    Tc, bs, br = 60.0, 0.05, 0.4
    Ts = Zs / (Zs + Zr) * Tc
    Tr = Zr / (Zs + Zr) * Tc
    ws, wr = Ts / bs, Tr / br
    wc = (Zs * ws + Zr * wr) / (Zs + Zr)
    return {"T_c": Tc, "b_s": bs, "b_r": br, "J_s": 0.02, "J_r": 0.2, "T_s": Ts, "T_r": Tr,
            "w_s": ws, "w_r": wr, "w_c": wc, "P_c": Tc * wc, "tau_s": 0.02 / bs, "tau_r": 0.2 / br}


def main() -> None:
    ns = np.linspace(1000, 5000, 81)
    best = min(((float(bsfc(n, T)), n, T) for n in ns for T in np.linspace(5, wot(n), 60)))
    design = {
        "vehicle": VEH, "psd": PSD, "engine": {**ENG, "e0": E0, "bsfc_min": best[0], "bsfc_min_rpm": best[1], "f0": 7.0, "f1": 1.0e-3 / RPM, "f2": 2.0e-7 / RPM ** 2,
                                               "bsfc_min_Nm": best[2]},
        "wot": {"w": [n * RPM for n in WOT_RPM], "T": WOT_NM},
        "fuel_map": {"w": MAP_W.tolist(), "T": MAP_T.tolist(), "table": MAP_FUEL.tolist(),
                     "note": "kg/s, row i: torque T[i], column j: speed w[j]"},
        "ool": {"P": OOL_P.tolist(), "w": OOL_W.tolist(),
                "T": [p / w for p, w in zip(OOL_P, OOL_W)]},
        "mg": MG, "spin": {"c0": SPIN_C0, "c1": SPIN_C1,
                           "check_6000rpm_W": SPIN_C0 * 6006 * RPM + SPIN_C1 * (6006 * RPM) ** 2,
                           "ornl_6000rpm_W_warm": 0.8 * 1645.3},
        "battery": {**BAT, "ocv_soc": OCV_SOC, "ocv_v": OCV_V},
        "nedc": {"t": [p[0] for p in NEDC], "v_kmh": [p[1] for p in NEDC], **nedc_stats()},
        "ev": ev_launch(), "kin": kinematics(),
    }
    (HERE / "design.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"e0 = {E0:.4f}, BSFC min {best[0]:.1f} g/kWh at {best[1]:.0f} rpm, {best[2]:.0f} N*m")
    print("OOL rpm:", [round(w / RPM) for w in OOL_W])
    print(f"MG2 c = {C2:.4f} W/(N m)^2, b = {B2:.5f}; MG1 c = {C1:.4f}, b = {B1:.5f}; R2 {MG['R2']:.4f} R1 {MG['R1']:.4f}")
    print(f"spin c0 = {SPIN_C0:.4f} N m, c1 = {SPIN_C1:.6f} N m s/rad")
    print("NEDC", nedc_stats(), len(NEDC), "points")
    print("EV", ev_launch())
    print("KIN", kinematics())


if __name__ == "__main__":
    main()
