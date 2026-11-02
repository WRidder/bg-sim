# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""The A109 example's design and validation: everything the models and the checks use.

    uv run examples/a109/design/design.py          # writes design/design.json
    uv run examples/a109/design/build_model.py     # then the models, scenes and expected.json

1. The reference implementation against the report's own numbers: the AH-1S hover trim printout
   (Fig. 12) and the AH-1S step response of Table 7 (heli_ref.py, the report's subroutine).
2. The A109 trims from 40 kt rearward to 120 kt forward and in sideward flight against the
   report's "fitted model" curves (Appendix D), and the control rigging (percent of travel per
   degree) inferred from them.
3. The SI model as bg-sim builds it (heli_si.py): the parameters of the library blocks, the
   principal axes, the trims the models start from, the linear modes, and the scipy runs of the
   open-loop scenarios the bg-sim checks compare against.
4. The flyable model: the SCAS, the demonstration pilot and the scipy run of the demonstration.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import heli_data as HD  # noqa: E402
import heli_ref as HR  # noqa: E402
import heli_si as HS  # noqa: E402
import heli_sim as SM  # noqa: E402

D = np.degrees
KT = HD.FPS_PER_KNOT * HS.FT          # m/s per knot


def r(x, n=6):
    return float(round(float(x), n))


# --------------------------------------------------------------------------- 1. the report's numbers
def check_ah1s() -> dict:
    h = HR.Heli(HD.AH1S, rigid_body="report")
    x, c, o = HR.trim(h)
    pr = HD.AH1S_HOVER_PRINTOUT
    ours = {"theta0_deg": D(c[0]), "B1_deg": D(c[1]), "A1_deg": D(c[2]), "theta_tr_deg": D(c[3]),
            "theta_deg": D(x[HR.ITH]), "phi_deg": D(x[HR.IPHI]), "a1_deg": D(x[HR.IA1]), "b1_deg": D(x[HR.IB1]),
            "hp": o["hp"], "thrust_lb": o["T"], "thrust_tr_lb": o["T_tr"], "vi_fps": o["vi"], "vi_tr_fps": o["vi_tr"],
            "torque_ftlb": o["torque"]}
    trim = {k: {"report": pr[k], "ours": r(ours[k], 4)} for k in pr}
    # Table 7: a 1 deg step of DC(3) from the trim, the report's discrete integration
    step = np.radians([0.0, 0.0, 1.0, 0.0])
    hist = HR.simulate_report(h, x, lambda t: c + step, len(HD.AH1S_TABLE7) - 1)
    rows = []
    for (t, u, v, p, q, rr), xs in zip(HD.AH1S_TABLE7, hist):
        rows.append({"t": t, "report": [u, v, p, q, rr],
                     "ours": [r(xs[HR.IU], 4), r(xs[HR.IV], 4), r(D(xs[HR.IP]), 4), r(D(xs[HR.IQ]), 4), r(D(xs[HR.IR]), 4)]})
    return {"trim": trim, "table7": rows}


# --------------------------------------------------------------------------- 2. A109 trims and rigging
def sweep(h, kts, key):
    out = {}
    g = None
    for kt in kts:
        try:
            x, c, o = HR.trim(h, guess=g, **{key: kt * HD.FPS_PER_KNOT})
        except RuntimeError:
            continue      # a trim on a switch of the report's model (45 kt: the fin stalls) has no solution
        g = np.r_[c, x[HR.ITH], x[HR.IPHI], x[HR.IA1], x[HR.IB1]]
        out[kt] = {"coll": D(c[0]), "lon": D(c[1]), "lat": D(c[2]), "ped": D(c[3]),
                   "pitch": D(x[HR.ITH]), "roll": D(x[HR.IPHI]), "shp": o["hp"], "a1": D(x[HR.IA1]), "b1": D(x[HR.IB1]),
                   "ht_stall": bool(o["ht_stall"]), "vt_stall": bool(o["vt_stall"]), "wake": o["wake"]}
    return out


def interp(curve, kt):
    xs, ys = zip(*curve)
    if kt < xs[0] or kt > xs[-1]:
        return None
    return float(np.interp(kt, xs, ys))


def a109_trims() -> dict:
    h = HR.Heli(HD.A109)
    fwd = sweep(h, list(range(0, 125, 5)), "vn")
    fwd.update(sweep(h, list(range(0, -45, -5)), "vn"))
    side = sweep(h, list(range(0, 25, 5)), "ve")
    side.update(sweep(h, list(range(0, -25, -5)), "ve"))
    # Rigging: percent of travel = a + b * angle, a least-squares fit per axis against the fitted
    # model's control positions. Collective and pedals: all forward, rearward and sideward points.
    # Longitudinal: forward and rearward flight (the sideward points are where the report's own
    # fitted model and its data disagree most). Lateral: hover and sideward flight, where the
    # lateral cyclic moves by 2.5 deg; in forward flight the model's lateral cyclic hardly moves
    # (-0.4 .. -0.8 deg) while the report's fitted curve runs from 46 to 36 % (see the README).
    axes = {"coll": ("coll_pct", True, True), "lon": ("lon_pct", True, False),
            "lat": ("lat_pct", False, True), "ped": ("ped_pct", True, True)}
    rig = {}
    for ax, (key, use_fwd, use_side) in axes.items():
        pts = []
        if use_fwd:
            pts += [(fwd[kt][ax], pct, "fwd", kt) for kt, pct in HD.FITTED[key] if kt in fwd]
        else:
            pts += [(fwd[0][ax], pct, "fwd", kt) for kt, pct in HD.FITTED[key] if kt == 0]
        if use_side:
            pts += [(side[kt][ax], pct, "side", kt) for kt, pct in HD.FITTED_SIDE[key] if kt in side and kt != 0]
        A = np.c_[np.ones(len(pts)), [p[0] for p in pts]]
        y = np.array([p[1] for p in pts])
        (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
        res = y - A @ np.array([a, b])
        rig[ax] = {"a": r(a, 3), "b": r(b, 4), "rms": r(np.sqrt(np.mean(res ** 2)), 2), "max": r(np.max(np.abs(res)), 2),
                   "n": len(pts), "deg_at_0": r(-a / b, 3), "deg_at_100": r((100 - a) / b, 3)}
    # the trim table against the fitted model
    table = []
    for kt in sorted(fwd):
        t = fwd[kt]
        row = {"kt": kt}
        for k in ("pitch", "roll", "shp", "coll", "lon", "lat", "ped"):
            row[k] = r(t[k], 3 if k != "shp" else 1)
        for k, key in (("pitch", "pitch_deg"), ("roll", "roll_deg"), ("shp", "power_shp")):
            row[k + "_fit"] = interp(HD.FITTED[key], kt) if any(kt == p[0] for p in HD.FITTED[key]) else None
        for ax in ("coll", "lon", "lat", "ped"):
            pct = rig[ax]["a"] + rig[ax]["b"] * t[ax]
            row[ax + "_pct"] = r(pct, 1)
            key = ax + "_pct"
            row[ax + "_pct_fit"] = interp(HD.FITTED[key], kt) if any(kt == p[0] for p in HD.FITTED[key]) else None
        row["ht_stall"], row["vt_stall"], row["wake"] = t["ht_stall"], t["vt_stall"], t["wake"]
        table.append(row)
    side_table = []
    for kt in sorted(side):
        t = side[kt]
        row = {"kt": kt, "pitch": r(t["pitch"], 3), "roll": r(t["roll"], 3), "shp": r(t["shp"], 1)}
        for k, key in (("pitch", "pitch_deg"), ("roll", "roll_deg")):
            row[k + "_fit"] = interp(HD.FITTED_SIDE[key], kt)
        for ax in ("coll", "lon", "lat", "ped"):
            row[ax + "_pct"] = r(rig[ax]["a"] + rig[ax]["b"] * t[ax], 1)
            row[ax + "_pct_fit"] = interp(HD.FITTED_SIDE[ax + "_pct"], kt)
        side_table.append(row)
    return {"rig": rig, "forward": table, "sideward": side_table}


# --------------------------------------------------------------------------- 3. SI, bg-sim parameters
def block_params(s: dict) -> dict:
    """Every number the library blocks take, from heli_si.si_data."""
    Jp, eps, _ = HS.principal_axes(s)
    return {
        "m": s["m"], "J_principal": list(Jp), "eps": eps, "g0": HS.G0, "rho0": s["rho0"],
        "q_bp": [math.cos(eps / 2), 0.0, math.sin(eps / 2), 0.0],
        "weight": s["weight"],
        "pos": {k: [-s["D_" + k], 0.0, s["H_" + k]] for k in ("HUB", "FUS", "HT", "VT", "TR")},   # FLU, m
        "D": {k: s["D_" + k] for k in ("HUB", "FUS", "HT", "VT", "TR")},
        "H": {k: s["H_" + k] for k in ("HUB", "FUS", "HT", "VT", "TR")},
        "mr": {"R": s["R"], "e": s["E"], "I_B": s["I_B"], "a": s["A"], "nb": float(s["B"]), "c": s["C"],
               "twist": s["TWST"], "IS": s["IS"], "K1": s["K1"], "db1dv": s["DB1DV"], "vtrans": s["VTRANS"],
               "wake_on": 1.0 if s["a109"] else 0.0, "coupled": 0.0 if s["a109"] else 1.0, "om0": s["OMEGA0"],
               "vh": s["vh"], "d_hub": s["D_HUB"]},
        "power": {"weight": s["weight"], "FR": s["FR"], "R": s["R"]},
        "fus": {"XUU": s["XUU_FUS"], "YVV": s["YVV_FUS"], "ZWW": s["ZWW_FUS"], "h_hub": s["H_HUB"], "h_fus": s["H_FUS"],
                "d_fus": s["D_FUS"], "d_hub": s["D_HUB"], "fw_gain": s["FW_GAIN"]},
        "tr": {"R": s["R_TR"], "a": s["A_TR"], "sol": s["SOL_TR"], "twist": s["TWST_TR"], "d_tr": s["D_TR"],
               "h_tr": s["H_TR"], "om0": s["OMEGA_TR0"]},
        "ht": {"ZUU": s["ZUU_HT"], "ZUW": s["ZUW_HT"], "ZMAX": s["ZMAX_HT"], "R": s["R"], "h_hub": s["H_HUB"],
               "h_ht": s["H_HT"], "d_ht": s["D_HT"], "d_hub": s["D_HUB"], "dw_shift": s["DW_SHIFT"]},
        "vt": {"YUU": s["YUU_VT"], "YUV": s["YUV_VT"], "YMAX": s["YMAX_VT"], "d_vt": s["D_VT"]},
        "drive": {"J": s["J_DT"], "J_MR": s["J_MR"], "n_tr": s["N_TR"], "p_loss": s["P_LOSS"], "om0": s["OMEGA0"],
                  "Kp": s["KP_GOV"], "Ki": s["KI_GOV"], "p_max": s["P_MAX"]},
        "IZ_AF": s["IZ_AF"], "IX": s["IX"], "IY": s["IY"], "IZ": s["IZ"], "IXZ": s["IXZ"],
    }


def start_values(s: dict, x, c) -> dict:
    pose, P = HS.bg_start(s, x)
    return {"pose": {k: float(v) for k, v in pose.items()}, "P": [float(v) for v in P],
            "ctrl_deg": [float(v) for v in D(c)], "a1": float(x[HS.IA1]), "b1": float(x[HS.IB1]),
            "om": float(x[HS.IOM]), "xi": float(x[HS.IXI])}


# The open-loop scenarios: a hover trim released, three hover steps and pulses, 100 kt with a pedal
# pulse. (label, speed kt, input axis, amplitude deg, on, off (None: a step), description)
OPEN_LOOP = [
    ("Hover", 0.0, None, 0.0, 1.0, None, "hover trim, released"),
    ("Coll", 0.0, "coll", 0.5, 1.0, None, "hover, collective +0.5 deg at 1 s"),
    ("Lon", 0.0, "lon", 0.5, 1.0, 1.5, "hover, longitudinal cyclic 0.5 deg forward from 1 to 1.5 s"),
    ("Fwd", 100.0, "ped", 1.0, 1.0, 2.0, "100 kt, pedals: tail-rotor pitch +1 deg from 1 to 2 s"),
]
AXIS = {"coll": 0, "lon": 1, "lat": 2, "ped": 3}
OL_T_END = 10.0
OL_TIMES = (0.5, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0)


def signals_of(h, ts, X, ctrl_fn) -> dict:
    """The recorded signals of a scipy run, named as the bg-sim checks name them (per helicopter)."""
    out = {k: [] for k in ("u", "v", "w", "p_deg", "q_deg", "r_deg", "phi_deg", "theta_deg", "psi_deg", "h", "x", "y",
                           "a1_deg", "b1_deg", "om", "nr", "T", "q_mr", "tau", "power_hp")}
    for t, x in zip(ts, X):
        o = h.components(x, ctrl_fn(t, x))
        ua = o["ua"]
        out["u"].append(ua[0]); out["v"].append(ua[1]); out["w"].append(ua[2])
        out["p_deg"].append(D(x[HS.IP])); out["q_deg"].append(D(x[HS.IQ])); out["r_deg"].append(D(x[HS.IR]))
        out["phi_deg"].append(D(x[HS.IPHI])); out["theta_deg"].append(D(x[HS.ITH])); out["psi_deg"].append(D(x[HS.IPSI]))
        out["h"].append(-x[HS.IZD]); out["x"].append(x[HS.IXN]); out["y"].append(-x[HS.IYE])
        out["a1_deg"].append(D(x[HS.IA1])); out["b1_deg"].append(D(x[HS.IB1]))
        out["om"].append(x[HS.IOM]); out["nr"].append(100 * o["om_rel"] / h.s["OMEGA0"])
        out["T"].append(o["mr"]["T"]); out["q_mr"].append(o["q_mr"]); out["tau"].append(o["tau"])
        out["power_hp"].append(o["qeng"] * o["om_rel"] / HS.W_PER_HP)
    return {k: [float(v) for v in vals] for k, vals in out.items()}


def open_loop(s: dict, rpm_mode: int) -> list:
    h = HS.Heli(s, rpm_mode=rpm_mode)
    cases = []
    for lab, kt, axis, amp, t_on, t_off, desc in OPEN_LOOP:
        x0, c0, o0 = HS.trim(h, vn=kt * KT)

        def ctrl(t, x, c0=c0, axis=axis, amp=amp, t_on=t_on, t_off=t_off):
            c = np.array(c0)
            if axis and t >= t_on and (t_off is None or t < t_off):
                c[AXIS[axis]] += math.radians(amp)
            return c
        breaks = [t_on] + ([t_off] if t_off else []) if axis else []
        ts, X = HS.simulate(h, x0, ctrl, OL_T_END, dt=0.01, breaks=breaks)
        sig = signals_of(h, ts, X, ctrl)
        k_at = {t: int(round(t / 0.01)) for t in OL_TIMES}
        cases.append({"label": lab, "kt": kt, "axis": axis, "amp": amp, "t_on": t_on, "t_off": t_off, "desc": desc,
                      "start": start_values(s, x0, c0), "trim_power_hp": o0["power"] / HS.W_PER_HP,
                      "at": {k: {str(t): vals[i] for t, i in k_at.items()} for k, vals in sig.items()},
                      "max_abs": {k: float(np.max(np.abs(vals))) for k, vals in sig.items()},
                      "series": {"t": [float(t) for t in ts[::10]], **{k: vals[::10] for k, vals in sig.items()}}})
    return cases


def modes(s: dict) -> dict:
    """Linear modes of the bg-sim model at hover, 60 and 100 kt (constant RPM and with the
    drivetrain); the report publishes none, so these are the scipy reference of the bg-sim model."""
    out = {}
    idx = [HS.IU, HS.IV, HS.IW, HS.IP, HS.IQ, HS.IR, HS.IPHI, HS.ITH, HS.IA1, HS.IB1, HS.IOM, HS.IXI]
    for mode in (0, 1):
        h = HS.Heli(s, rpm_mode=mode)
        for kt in (0, 60, 100):
            x0, c0, _ = HS.trim(h, vn=kt * KT)
            n = len(idx)
            A = np.zeros((n, n))
            for j, k in enumerate(idx):
                d = 1e-6 * max(1.0, abs(x0[k]))
                xp, xm = x0.copy(), x0.copy()
                xp[k] += d
                xm[k] -= d
                A[:, j] = (h.deriv(xp, c0)[0][idx] - h.deriv(xm, c0)[0][idx]) / (2 * d)
            ev = sorted(np.linalg.eigvals(A), key=lambda z: (-z.real, -z.imag))
            out[f"rpm{mode}_{kt}"] = [[r(z.real, 4), r(z.imag, 4)] for z in ev if z.imag >= -1e-9]
    return out


# --------------------------------------------------------------------------- 4. the flyable model
SIM_DT = 0.05
SIM_TIMES = (5.0, 15.0, 25.0, 35.0, 50.0, 64.0, 75.0, 90.0, 100.0, 110.0, 120.0)


def sim_signals(sim, ts, X) -> dict:
    h = sim.h
    out = {k: [] for k in ("u", "v", "h", "phi_deg", "theta_deg", "psi_deg", "r_deg", "nr", "power_hp", "x", "y",
                           "coll", "lon", "lat", "ped", "th0", "B1", "A1", "thtr", "u_cmd", "h_cmd", "ph_turn")}
    for t, x in zip(ts, X):
        c, _, st = sim.controls(t, x)
        o = h.components(x[:HS.NX], c)
        ua = o["ua"]
        out["u"].append(ua[0]); out["v"].append(ua[1]); out["h"].append(-x[HS.IZD])
        out["phi_deg"].append(D(x[HS.IPHI])); out["theta_deg"].append(D(x[HS.ITH]))
        out["psi_deg"].append(D(x[HS.IPSI])); out["r_deg"].append(D(x[HS.IR]))
        out["nr"].append(100 * o["om_rel"] / h.s["OMEGA0"]); out["power_hp"].append(o["qeng"] * o["om_rel"] / HS.W_PER_HP)
        out["x"].append(x[HS.IXN]); out["y"].append(-x[HS.IYE])
        for k, v in zip(("coll", "lon", "lat", "ped"), st):
            out[k].append(v)
        for k, v in zip(("th0", "B1", "A1", "thtr"), D(c)):
            out[k].append(v)
        uc, hc, pc = SM.schedule(t)
        out["u_cmd"].append(uc); out["h_cmd"].append(hc); out["ph_turn"].append(pc)
    return {k: [float(v) for v in vals] for k, vals in out.items()}


# Hands-off hover variants of a109-sim (demo = 0): (label, scas, offsets, t_end, description)
SIM_CASES = [
    ("hold", 1.0, {"lon": 0.1, "t": 1.0}, 15.0, "SCAS on, longitudinal stick 0.1 forward from 1 s: a 1.5 deg nose-down attitude command"),
    ("bare", 0.0, {"lon": 0.02, "t": 1.0}, 12.0, "SCAS off, longitudinal stick 0.02 forward from 1 s: the bare hover diverges"),
]
CASE_TIMES = (2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0)


def sim_cases(s: dict, rig: dict) -> dict:
    out = {}
    for lab, scas, off, t_end, desc in SIM_CASES:
        h = HS.Heli(s, rpm_mode=1, ge=1, smooth=1.0)
        sim = SM.Sim(h, rig, scas=scas, demo=0.0, offsets=off)
        ts, X = sim.run(t_end, dt=SIM_DT, rtol=1e-9, atol=1e-9)
        sig = sim_signals(sim, ts, X)
        k_at = {t: int(round(t / SIM_DT)) for t in CASE_TIMES if t <= t_end + 1e-9}
        out[lab] = {"scas": scas, "offsets": off, "t_end": t_end, "desc": desc,
                    "at": {k: {str(t): vals[i] for t, i in k_at.items()} for k, vals in sig.items()},
                    "max_abs": {k: float(np.max(np.abs(vals))) for k, vals in sig.items()}}
    return out


def sim_demo(s: dict, rig: dict) -> dict:
    """The flyable model (heli_sim.py): its tables and start, and the scipy run of the demonstration."""
    h = HS.Heli(s, rpm_mode=1, ge=1, smooth=1.0)
    sim = SM.Sim(h, rig, scas=1.0, demo=1.0)
    x0 = sim.x0[:HS.NX]
    c0 = sim.controls(0.0, sim.x0)[0]
    ts, X = sim.run(SM.DEMO_T_END, dt=SIM_DT, rtol=1e-8, atol=1e-8)
    sig = sim_signals(sim, ts, X)
    k_at = {t: int(round(t / SIM_DT)) for t in SIM_TIMES}
    return {"alt": 15.0, "start": start_values(s, x0, c0), "ff": {"u": sim.ff.u, **sim.ff.tab},
            "hover_sticks": [float(v) for v in sim.hover_sticks], "gains": SM.GAINS, "pilot": SM.PILOT,
            "stick": {"theta": SM.K_THETA_STICK, "phi": SM.K_PHI_STICK, "r": SM.K_R_STICK}, "v_tc": list(SM.V_TC),
            "schedule": [list(row) for row in SM.DEMO], "t_end": SM.DEMO_T_END, "cases": sim_cases(s, rig),
            "at": {k: {str(t): vals[i] for t, i in k_at.items()} for k, vals in sig.items()},
            "max_abs": {k: float(np.max(np.abs(vals))) for k, vals in sig.items()},
            "series": {"t": [float(t) for t in ts[::4]], **{k: vals[::4] for k, vals in sig.items()}}}


def main() -> int:
    s = HS.si_data()
    a109 = a109_trims()
    design = {"source": "Heffley & Mnich, NASA CR-177476 (1988), Appendix D (A109 II); see README",
              "ah1s": check_ah1s(), "a109": a109, "si": block_params(s),
              "open_loop": open_loop(s, rpm_mode=1),
              "open_loop_rpm0": [c for c in open_loop(s, rpm_mode=0) if c["label"] == "Coll"], "modes": modes(s), "sim": sim_demo(s, a109["rig"])}
    (HERE / "design.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote design.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
