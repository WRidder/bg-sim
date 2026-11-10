# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `maglev-train` example: trim, linearisation, state feedback, reference runs.

    uv run examples/maglev-train/design/design.py

Writes `design/design.json` (every number the models, the checks and the docs use). Then
`uv run examples/maglev-train/design/build_model.py` writes the models, the scene and expected.json.

One levitation module (an EMS magnet carrying a quarter of a car section), gap h positive downward
from the rail to the magnet face (the gap opens when the bogie sinks):

    h'   = vb - vg                                    (vg: guideway velocity, down positive)
    mb vb' = mb g + k e + c (vc - vb) - alpha i^2/h^2 (+ skid contact)
    mc vc' = mc g - k e - c (vc - vb) + F_load
    e'   = vc - vb                                    (secondary spring extension)
    L(h) i' = v - R i + 2 alpha i (vb - vg)/h^2       L(h) = L_inf + 2 alpha/h

The controller is full state feedback on the measured gap, its filtered derivative and the coil
current, with an integrator on the gap error (the gains come from an LQR design of the bogie plant):

    v = R i_ff - K1 (h - h_ref) - K2 hdot_f - K3 (i - i_ff) - K4 xi,    i_ff = c_trim h_ref

Everything is verified against the full linearisation (poles) and an independent nonlinear scipy
simulation (the numbers the expected.json checks use).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import linalg
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
G0 = 9.81
TT = 0.05   # s, anti-windup tracking time of the controller
MU0 = 4e-7 * np.pi

# --------------------------------------------------------------------------- parameters
# value, unit, status ("literature" with source key, or "estimate" with how it was chosen)
SOURCES = {
    "wiki": "Wikipedia 'Transrapid' (nominal gap 10 mm, acceleration ~1 m/s^2, Cd ~0.26, 16 m^2 frontal area (uncited there), 1.7 kW/t levitation power)",
    "brochure": "Transrapid vehicle brochure quoted in the TR literature: end section 27.0 m, 3.7 m wide, 4.2 m high, empty passenger section ~53 t",
    "stuttgart": "Schneider et al. 2022, 'Coupled vehicle-guideway dynamics simulations of the Transrapid with discretized levitation magnet forces' (TR08: 4 levitation chassis per section, 12-pole magnets)",
    "shanghai": "Shanghai Transrapid commercial speed 430 km/h",
}

# Module (one quarter of a section: one levitation chassis pair carrying a quarter of the car body)
P = {
    "h0": 0.010,          # m   nominal gap                       [literature: wiki, TR]
    "h_skid": 0.016,      # m   gap when resting on the skids     [estimate]
    "h_stop": 0.004,      # m   touch-down stop (pole face)       [estimate]
    "m_c": 11750.0,       # kg  car-body share (47 t / 4)         [section 53 t (brochure) less 4 chassis of 1.5 t: estimate split]
    "m_b": 1500.0,        # kg  levitation chassis                [estimate]
    "f_s": 1.0,           # Hz  body heave frequency              [estimate, typical air spring ride]
    "zeta_s": 0.3,        #     secondary damping ratio           [estimate]
    "i0": 150.0,          # A   trim current at 10 mm             [estimate]
    "R": 0.55,            # Ohm coil resistance                   [estimate: 12 kW per quarter = 0.9 kW/t, below the 1.7 kW/t of the TR]
    "L_inf": 0.03,        # H   leakage inductance                [estimate]
    "V_max": 800.0,       # V   chopper rail                      [estimate]
    "Tf": 0.001,          # s   derivative filter                 [estimate]
    "k_c": 2.0e8,         # N/m skid / stop contact stiffness     [estimate]
    "d_c": 1.0e6,         # N*s/m contact damping                 [estimate]
}


def derived(p: dict) -> dict:
    d = dict(p)
    m_tot = p["m_b"] + p["m_c"]
    d["m_tot"] = m_tot
    d["W"] = m_tot * G0
    d["F0"] = d["W"]
    d["alpha"] = d["W"] * p["h0"] ** 2 / p["i0"] ** 2      # F = alpha i^2/h^2 equals the weight at (h0, i0)
    d["c_trim"] = np.sqrt(d["W"] / d["alpha"])              # i_trim = c_trim * h
    d["k_s"] = p["m_c"] * (2 * np.pi * p["f_s"]) ** 2
    d["c_s"] = 2 * p["zeta_s"] * np.sqrt(d["k_s"] * p["m_c"])
    d["L0"] = p["L_inf"] + 2 * d["alpha"] / p["h0"]
    d["Ke"] = 2 * d["alpha"] * p["i0"] / p["h0"] ** 2       # back-EMF coefficient dL/dh * i
    d["V0"] = p["R"] * p["i0"]
    d["e0"] = p["m_c"] * G0 / d["k_s"]
    d["h_rest"] = p["h_skid"] + d["W"] / p["k_c"]            # gap while resting on the skids
    # equivalent magnet (N = 100 turns): pole area and flux density, only to make the numbers tangible
    N = 100
    d["N_equiv"] = N
    d["A_pole"] = 4 * d["alpha"] / (MU0 * N ** 2)
    d["B_gap"] = MU0 * N * p["i0"] / (2 * p["h0"])
    return d


# --------------------------------------------------------------------------- linear models
def open_loop(d: dict):
    """x = [h, vb, e, vc, i], input v; disturbance vg (guideway velocity)."""
    h0, i0, F0, a = d["h0"], d["i0"], d["F0"], d["alpha"]
    k, c, mb, mc, L0, R, Ke = d["k_s"], d["c_s"], d["m_b"], d["m_c"], d["L0"], d["R"], d["Ke"]
    A = np.array([
        [0, 1, 0, 0, 0],
        [2 * F0 / h0 / mb, -c / mb, k / mb, c / mb, -2 * F0 / i0 / mb],
        [0, -1, 0, 1, 0],
        [0, c / mc, -k / mc, -c / mc, 0],
        [0, Ke / L0, 0, 0, -R / L0],
    ])
    B = np.array([0, 0, 0, 0, 1 / L0])
    E = np.array([-1, 0, 0, 0, -Ke / L0])      # guideway velocity
    return A, B, E


def reduced(d: dict):
    """Bogie plant for the LQR: x = [dh, dhdot, di, xi]."""
    h0, i0, F0 = d["h0"], d["i0"], d["F0"]
    mb, L0, R, Ke = d["m_b"], d["L0"], d["R"], d["Ke"]
    A = np.array([
        [0, 1, 0, 0],
        [(2 * F0 / h0 - d["k_s"]) / mb, 0, -2 * F0 / i0 / mb, 0],
        [0, Ke / L0, -R / L0, 0],
        [1, 0, 0, 0],
    ])
    B = np.array([[0], [0], [1 / L0], [0]])
    return A, B


def lqr(d: dict, q_h=1e-3, q_v=0.05, q_i=20.0, q_xi=2e-3, v_scale=200.0):
    A, B = reduced(d)
    Q = np.diag([1 / q_h ** 2, 1 / q_v ** 2, 1 / q_i ** 2, 1 / (q_xi) ** 2])
    Rr = np.array([[1 / v_scale ** 2]])
    Pm = linalg.solve_continuous_are(A, B, Q, Rr)
    K = np.linalg.solve(Rr, B.T @ Pm)
    return K.ravel()


def closed_loop(d: dict, K):
    """Full linear closed loop. x = [h, vb, e, vc, i, xf, xi]; inputs vg and href deviation."""
    A5, B5, E5 = open_loop(d)
    Tf = d["Tf"]
    n = 7
    A = np.zeros((n, n))
    A[:5, :5] = A5
    # hdot_f = (h - xf)/Tf, xf' = (h - xf)/Tf, xi' = h - href
    hd_row = np.zeros(n)
    hd_row[0] = 1 / Tf
    hd_row[5] = -1 / Tf
    A[5] = hd_row
    A[6, 0] = 1
    ctrl = np.zeros(n)
    ctrl[0] = -K[0]
    ctrl += -K[1] * hd_row
    ctrl[4] += -K[2]
    ctrl[6] += -K[3]
    A[:5, :] += np.outer(np.r_[B5], ctrl)
    return A


# --------------------------------------------------------------------------- nonlinear reference
def skid_force(d, h, vh):
    """Force on the bogie from the skids / touch-down stop (up positive in the down frame: reduces h)."""
    kc, dc = d["k_c"], d["d_c"]
    if h > d["h_skid"]:
        return max(kc * (h - d["h_skid"]) + dc * vh, 0.0)
    if h < d["h_stop"]:
        return min(kc * (h - d["h_stop"]) + dc * vh, 0.0)
    return 0.0


def simulate(d, K, t_end, vg_fn, load_fn=lambda t: 0.0, href_fn=lambda t: d["h0"], x0=None, dt_out=1e-3,
             tau_ref=0.0):
    """Nonlinear module with the controller. x = [h, vb, e, vc, i, xf, xi, hr]; hr is the prefiltered reference."""
    a, mb, mc, k, c, R, Linf = d["alpha"], d["m_b"], d["m_c"], d["k_s"], d["c_s"], d["R"], d["L_inf"]
    ct, Vm, Tf = d["c_trim"], d["V_max"], d["Tf"]

    def f(t, x):
        h, vb, e, vc, i, xf, xi, hr = x
        vg = vg_fn(t)
        vh = vb - vg
        ref = href_fn(t)
        dhr = (ref - hr) / tau_ref if tau_ref > 0 else 0.0
        i_ff = ct * hr
        hdot = (h - xf) / Tf
        v = R * i_ff - K[0] * (h - hr) - K[1] * hdot - K[2] * (i - i_ff) - K[3] * xi
        v_u = v
        v = min(max(v_u, -Vm), Vm)
        L = Linf + 2 * a / h
        Fm = a * i * i / (h * h)
        Fs = skid_force(d, h, vh)
        ss = k * e + c * (vc - vb)
        dvb = (mb * G0 + ss - Fm - Fs) / mb
        dvc = (mc * G0 - ss + load_fn(t)) / mc
        di = (v - R * i + 2 * a * i * vh / (h * h)) / L
        return [vh, dvb, vc - vb, dvc, di, (h - xf) / Tf, (h - hr) + (v - v_u) / (-K[3] * TT), dhr]

    ts = np.arange(0.0, t_end + 1e-12, dt_out)
    sol = solve_ivp(f, (0, t_end), x0, t_eval=ts, method="Radau", rtol=1e-9, atol=1e-12, max_step=2e-3)
    return sol


def metrics_step(t, y, t_step, y0, y1, tol=0.02):
    """Rise (10-90 %), overshoot, settling time (2 % of the step) of a gap response after t_step."""
    span = y1 - y0
    m = t >= t_step
    tt, yy = t[m] - t_step, (y[m] - y0) / span
    r10 = tt[np.argmax(yy >= 0.1)]
    r90 = tt[np.argmax(yy >= 0.9)]
    over = max(0.0, yy.max() - 1.0)
    out = np.abs(yy - 1.0) > tol
    ts = tt[np.where(out)[0][-1] + 1] if out.any() else 0.0
    return {"rise": float(r90 - r10), "overshoot": float(over), "settling": float(ts)}


# --------------------------------------------------------------------------- scenario (model 1)
T_REF, TAU_REF = 0.1, 0.15      # s: gap reference steps from the skid gap to the nominal gap, prefiltered
T_RAIL, DZ_RAIL, W_RAIL = 2.0, 0.001, 150.0   # s, m, rad/s: guideway step (rail sinks 1 mm, the gap closes), critically damped
T_LOAD, DM_LOAD = 4.0, 2000.0   # s, kg: payload step on the body share
T_END = 8.0


def rail_velocity(t, dz=DZ_RAIL, w=W_RAIL, t0=T_RAIL):
    """Velocity of the guideway (down positive) for a step dz smoothed by 1/(1 + s/w)^2."""
    if t < t0:
        return 0.0
    s = t - t0
    return dz * w * w * s * np.exp(-w * s)


def scenario(d, K, with_rail=True, with_load=True, t_end=T_END):
    x0 = [d["h_rest"], 0.0, d["e0"], 0.0, 0.0, d["h_rest"], 0.0, d["h_skid"]]
    return simulate(
        d, K, t_end,
        vg_fn=(lambda t: rail_velocity(t)) if with_rail else (lambda t: 0.0),
        load_fn=(lambda t: DM_LOAD * G0 if t >= T_LOAD else 0.0) if with_load else (lambda t: 0.0),
        href_fn=lambda t: d["h0"] if t >= T_REF else d["h_skid"],
        x0=x0, tau_ref=TAU_REF)


def module_design(scale: int = 1, q_xi: float = 1e-4) -> dict:
    """Parameters, gains and linear analysis of a module that is `scale` quarter modules in parallel
    (the vehicle model uses scale = 2: front and rear chassis pairs, each carrying half the car)."""
    p = dict(P)
    for key in ("m_c", "m_b"):
        p[key] = P[key] * scale
    p["R"] = P["R"] * scale
    p["L_inf"] = P["L_inf"] * scale
    p["V_max"] = P["V_max"] * scale
    p["k_c"] = P["k_c"] * scale
    p["d_c"] = P["d_c"] * scale
    d = derived(p)
    K = lqr(d, q_xi=q_xi, v_scale=200.0 * scale)
    A5, B5, E5 = open_loop(d)
    d["K"] = [float(k) for k in K]
    d["a"] = [float(-K[0]), float(-K[1]), float(-K[2]), float(-K[3])]
    d["ol_poles"] = [[float(z.real), float(z.imag)] for z in np.linalg.eigvals(A5)]
    d["p_unstable"] = float(max(np.linalg.eigvals(A5).real))
    cl = np.linalg.eigvals(closed_loop(d, K))
    d["cl_poles"] = [[float(z.real), float(z.imag)] for z in cl]
    return d



# --------------------------------------------------------------------------- vehicle (model 2)
L_CAR, W_CAR, H_CAR = 27.0, 3.7, 4.2        # m, end section of a TR (brochure)
M_BODY = 2 * 2 * P["m_c"]                    # kg, car body (4 quarter shares)
VEH = {
    "L_car": L_CAR, "m_body": M_BODY,
    "J": [M_BODY * (W_CAR ** 2 + H_CAR ** 2) / 12, M_BODY * (L_CAR ** 2 + H_CAR ** 2) / 12,
          M_BODY * (L_CAR ** 2 + W_CAR ** 2) / 12],   # kg m^2: homogeneous box, roll, pitch, yaw
    "x_m": 9.5,                                 # m, module positions (front +, rear -)
    "rho": 1.2, "Cd": 0.26, "A_front": 16.0,
    "v_cruise": 430.0 / 3.6, "a_acc": 1.0, "T_cruise": 30.0, "t_go": 4.0,
    "tau_lsm": 0.05, "F_max": 1.5e5, "Kp_v": 3.0e4, "Ti_v": 4.0,
    "L_span": 24.768, "A_sag": 0.003, "s_bump": 8500.0, "A_bump": 0.002, "lam_bump": 12.0,
    "k_guide": 5.0e7, "c_guide": 1.0e6, "kr_guide": 5.0e9, "cr_guide": 5.0e6,
}
VEH["k_aero"] = 0.5 * VEH["rho"] * VEH["Cd"] * VEH["A_front"]
VEH["m_tot"] = M_BODY    # kg moving along the track in the model: the car body (the bogies are vertical-only masses)
VEH["q_end"] = VEH["v_cruise"] ** 2 / VEH["a_acc"] + VEH["v_cruise"] * VEH["T_cruise"]
VEH["t_end"] = VEH["t_go"] + 2 * VEH["v_cruise"] / VEH["a_acc"] + VEH["T_cruise"] + 3.0


def track_profile(veh, t):
    """Speed profile of the trapezoidal move: (v_ref, a_ref) at time t."""
    a, vc = veh["a_acc"], veh["v_cruise"]
    t0 = veh["t_go"]
    Ta = vc / a
    Tc = veh["T_cruise"]
    if t < t0:
        return 0.0, 0.0
    if t < t0 + Ta:
        return a * (t - t0), a
    if t < t0 + Ta + Tc:
        return vc, 0.0
    if t < t0 + 2 * Ta + Tc:
        return vc - a * (t - (t0 + Ta + Tc)), -a
    return 0.0, 0.0


def guideway(veh, s):
    """Deflection (down positive) and slope dz/ds of the guideway at track coordinate s."""
    L, A = veh["L_span"], veh["A_sag"]
    z = A * np.sin(np.pi * s / L) ** 2
    dz = A * (np.pi / L) * np.sin(2 * np.pi * s / L)
    sb, Ab, lam = veh["s_bump"], veh["A_bump"], veh["lam_bump"]
    if sb < s < sb + lam:
        z += 0.5 * Ab * (1 - np.cos(2 * np.pi * (s - sb) / lam))
        dz += Ab * (np.pi / lam) * np.sin(2 * np.pi * (s - sb) / lam)
    return z, dz


def vehicle_sim(t_end, dt_out=0.02, method="LSODA"):
    """Independent planar simulation of the vehicle: car body heave and pitch on two modules, the long
    stator with the speed profile and drag, the sagging guideway with a bump. Down positive for the
    modules, theta positive nose down. x = [z, vz, th, w, s, v, Fl, xp, hr, (h, vb, e, i, xf, xi) x 2]."""
    d = module_design(2)
    veh = VEH
    xs = (veh["x_m"], -veh["x_m"])
    a_, mb, mc, k, c, R, Linf = d["alpha"], d["m_b"], d["m_c"], d["k_s"], d["c_s"], d["R"], d["L_inf"]
    K = d["K"]
    ct, Vm, Tf = d["c_trim"], d["V_max"], d["Tf"]
    mbody, Jp = veh["m_body"], veh["J"][1]
    mtot, kaero = veh["m_tot"], veh["k_aero"]

    def f(t, y):
        z, vz, th, w, s, v, Fl, xp, hr = y[:9]
        vref, aref = track_profile(veh, t)
        Fu = mtot * aref + kaero * vref ** 2 + veh["Kp_v"] * ((vref - v) + xp)
        Fc = min(max(Fu, -veh["F_max"]), veh["F_max"])
        dxp = 0.0 if abs(Fu) > veh["F_max"] else (vref - v) / veh["Ti_v"]
        dy = np.zeros_like(y)
        dy[0], dy[2] = vz, w
        dy[4], dy[5] = v, (Fl - kaero * abs(v) * v) / mtot
        dy[6] = (Fc - Fl) / veh["tau_lsm"]
        dy[7] = dxp
        ref = d["h0"] if t >= 0.1 else d["h_skid"]
        dy[8] = (ref - hr) / 0.15
        Fsum, Msum = 0.0, 0.0
        for j in range(2):
            h, vb, e, i, xf, xi = y[9 + 6 * j: 15 + 6 * j]
            sj = s + xs[j]
            _, dz = guideway(veh, sj)
            vg = v * dz
            vh = vb - vg
            vp = vz + xs[j] * w
            i_ff = ct * hr
            hdot = (h - xf) / Tf
            vu = R * i_ff - K[0] * (h - hr) - K[1] * hdot - K[2] * (i - i_ff) - K[3] * xi
            vv = min(max(vu, -Vm), Vm)
            L = Linf + 2 * a_ / h
            Fm = a_ * i * i / (h * h)
            Fs = skid_force(d, h, vh)
            Fsp = k * e + c * (vp - vb)
            dy[9 + 6 * j] = vh
            dy[10 + 6 * j] = (mb * G0 + Fsp - Fm - Fs) / mb
            dy[11 + 6 * j] = vp - vb
            dy[12 + 6 * j] = (vv - R * i + 2 * a_ * i * vh / (h * h)) / L
            dy[13 + 6 * j] = (h - xf) / Tf
            dy[14 + 6 * j] = (h - hr) + (vv - vu) / (-K[3] * TT)
            Fsum += Fsp
            Msum += xs[j] * Fsp
        dy[1] = G0 - Fsum / mbody
        dy[3] = -Msum / Jp
        return dy

    y0 = np.zeros(21)
    y0[8] = d["h_skid"]
    for j in range(2):
        y0[9 + 6 * j: 15 + 6 * j] = [d["h_rest"], 0.0, d["e0"], 0.0, d["h_rest"], 0.0]
    # the right-hand side jumps where the reference steps and where the speed profile changes its phase:
    # integrate the segments between those instants one after the other
    Ta = veh["v_cruise"] / veh["a_acc"]
    t0 = veh["t_go"]
    edges = [0.0, 0.1, t0, t0 + Ta, t0 + Ta + veh["T_cruise"], t0 + 2 * Ta + veh["T_cruise"], t_end]
    edges = sorted({e for e in edges if 0.0 <= e <= t_end})
    ts_all = np.arange(0.0, t_end + 1e-9, dt_out)
    T, Y = [], []
    y = y0
    for seg in range(len(edges) - 1):
        lo, hi = edges[seg], edges[seg + 1]
        sel = ts_all[(ts_all >= lo - 1e-12) & (ts_all < hi - 1e-12)] if hi < edges[-1] else ts_all[(ts_all >= lo - 1e-12) & (ts_all <= hi)]
        # nudge the evaluation inside the segment so that the first call sees the new phase
        sol = solve_ivp(lambda t, yy: f(min(max(t, lo + 1e-9), hi - 1e-9), yy), (lo, hi), y, t_eval=sel, method=method,
                        rtol=1e-10, atol=1e-13, max_step=0.01)
        T.append(sol.t)
        Y.append(sol.y)
        y = sol.y[:, -1] if sel.size and sel[-1] == hi else solve_ivp(
            lambda t, yy: f(min(max(t, lo + 1e-9), hi - 1e-9), yy), (lo, hi), y, method=method, rtol=1e-10, atol=1e-13,
            max_step=0.01).y[:, -1]
    class _Sol:
        pass
    out = _Sol()
    out.t = np.concatenate(T)
    out.y = np.concatenate(Y, axis=1)
    return out


def reference_module(d: dict) -> dict:
    """Numbers of the module scenario from the nonlinear scipy simulation (the checks compare bgsim with them)."""
    K = np.array(d["K"])
    sol = scenario(d, K)
    t, h, i = sol.t, sol.y[0], sol.y[4]

    def at(tq, row):
        return float(np.interp(tq, t, row))

    h0 = d["h0"]
    samples = [0.3, 0.5, 1.0, 1.9, 2.1, 2.2, 3.0, 4.1, 4.2, 5.0, 7.9]
    ref = {
        "samples": [{"t": tq, "h": at(tq, h), "i": at(tq, i)} for tq in samples],
        "i_lift_max": float(i.max()),
        "t_lift": float(t[np.argmax(h < 0.0125)]),
        "h_min_lift": float(h[t < 1.5].min()),
        "rail_dev_max": float(np.abs(h[(t >= T_RAIL) & (t <= T_RAIL + 1.0)] - h0).max()),
        "load_dev_max": float(np.abs(h[(t >= T_LOAD) & (t <= T_LOAD + 1.0)] - h0).max()),
        "h_final": float(h[-1]),
        "i_final": float(i[-1]),
        "i_trim": float(d["c_trim"] * h0),
        "i_loaded": float(d["c_trim"] * h0 * np.sqrt((d["W"] + DM_LOAD * G0) / d["W"])),
        "v_max_used": None,
    }
    return ref


def reference_vehicle(d: dict, veh: dict) -> dict:
    sol = vehicle_sim(veh["t_end"] - 0.01, dt_out=0.005, method="Radau")
    t, y = sol.t, sol.y

    def at(tq, row):
        return float(np.interp(tq, t, y[row]))

    # front-module bump entry: s + x_m = s_bump
    s_front = y[4] + veh["x_m"]
    t_b = float(t[np.argmax(s_front >= veh["s_bump"])])
    w = (t >= t_b - 0.5) & (t <= t_b + 3.0)
    cruise = (t >= veh["t_go"] + veh["v_cruise"] / veh["a_acc"] + 5.0) & (t <= veh["t_go"] + veh["v_cruise"] / veh["a_acc"] + veh["T_cruise"] - 1.0)
    ref = {
        "t_bump": t_b,
        "samples": [],
        "bump_pitch_max": float(np.abs(0.5 * y[2][w]).max()),       # |q_y| ~ theta/2
        "bump_gap_dev_max_front": float(np.abs(y[9][w] - d["h0"]).max()),
        "bump_gap_dev_max_rear": float(np.abs(y[15][w] - d["h0"]).max()),
        "cruise_v": float(y[5][cruise].mean()),
        "s_end": float(y[4][-1]),
    }
    for tq in (3.0, 60.0, 130.0, 140.0, 200.0, 270.0):
        ref["samples"].append({
            "t": float(tq), "px": at(tq, 4), "v": at(tq, 5), "h_f": at(tq, 9), "h_r": at(tq, 15),
            "i_f": at(tq, 12), "i_r": at(tq, 18), "pz": -at(tq, 0), "qy": 0.5 * at(tq, 2),
        })
    return ref


def open_loop_check(d: dict) -> dict:
    """Open-loop module released 10 nm from its trim gap: growth rate of the gap deviation at t_check."""
    A5, B5, E5 = open_loop(d)
    ev, vec = np.linalg.eig(A5)
    k = int(np.argmax(ev.real))
    return {"pole": float(ev[k].real), "dh0": 1.0e-8, "t_check": 0.15}


def write_design(vehicle: bool = True) -> None:
    mod = module_design(1)
    veh_d = module_design(2)
    data = {
        "module": mod,
        "vehicle": veh_d,
        "scenario": {"t_ref": T_REF, "tau_ref": TAU_REF, "t_rail": T_RAIL, "dz_rail": DZ_RAIL, "w_rail": W_RAIL,
                     "t_load": T_LOAD, "dm_load": DM_LOAD, "t_end": T_END},
        "veh": VEH,
        "ref_module": reference_module(mod),
        "open_loop": open_loop_check(mod),
        "sources": SOURCES,
    }
    cache = HERE / "vehicle_ref.json"
    if vehicle or not cache.exists():
        cache.write_text(json.dumps(reference_vehicle(veh_d, VEH), indent=2) + "\n", encoding="utf-8")
    data["ref_vehicle"] = json.loads(cache.read_text(encoding="utf-8"))
    (HERE / "design.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("wrote design.json; unstable pole", mod["p_unstable"], "rad/s; closed-loop poles",
          sorted(round(p[0], 2) for p in mod["cl_poles"])[-3:])


if __name__ == "__main__":
    import sys

    write_design(vehicle="--fast" not in sys.argv)
