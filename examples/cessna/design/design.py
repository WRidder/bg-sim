# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design and reference numbers of the `cessna` example.

    uv run examples/cessna/design/design.py

Writes `design/design.json`: every number the models, the checks and the docs use. Then
`uv run examples/cessna/design/build_model.py` writes the models, the scenes and `expected.json`.

1. The data (`c172_data.py`, transcribed from JSBSim's c172p) in SI (`c172_si.py`): mass,
   inertia, geometry, gear, engine and propeller; the tables in the layout of the bg-sim blocks.
2. The engine: FGPiston's power with the engine file's bsfc (0.32, used by FGPiston as the
   ISFC) and with FGPiston's own ISFC calibration (0.418, the model's choice).
3. Performance against the POH (`poh.py`, `perf.py`) with both ISFC values: stall speeds, climb,
   maximum and cruise speed, glide, static rpm and the takeoff ground roll.
4. The open-loop model: the trim at 100 KTAS, 5000 ft, the linearised modes (`c172_lin.py`) and
   the nonlinear reference runs released on each mode's eigenvector.
5. cessna-sim: the runway start, the demo takeoff-climb-turn (`demo.py`), the autopilot hold and
   two trimmed POH points (best-rate climb at sea level, full throttle at 8000 ft).
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import c172_data as D  # noqa: E402
import c172_lin as L  # noqa: E402
import c172_ref as M  # noqa: E402
import c172_si as S  # noqa: E402
import demo as Dm  # noqa: E402
import perf as P  # noqa: E402
import poh  # noqa: E402

KT = P.KT
FT = P.FT


def f(x):
    return float(x)


def rounded(obj, digits: int = 10):
    """Every float of a JSON tree to ``digits`` significant digits: the reference runs need about
    seven (the tightest check is 2e-5 absolute on a bank of 0.01 rad), and full precision would
    double the file."""
    if isinstance(obj, float):
        return float(f"{obj:.{digits}g}")
    if isinstance(obj, dict):
        return {k: rounded(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v, digits) for v in obj]
    return obj


def write_design(design: dict) -> None:
    """design.json with the floats rounded and every array of plain numbers on one line."""
    text = json.dumps(rounded(design), indent=1, separators=(",", ":"))
    text = re.sub(r"\[\s+([-+0-9.eE,\s]+?)\s+\]", lambda m: "[" + re.sub(r"\s+", "", m.group(1)) + "]", text)
    (HERE / "design.json").write_text(text + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- 1. data
def si() -> dict:
    gear = {k: {"r": [f(v) for v in g["r"]], "k": f(g["k_si"]), "b": f(g["b_si"]), "mu_s": g["mu_s"],
                "mu_r": g["mu_r"], "steer": g["steer"]} for k, g in S.GEAR.items()}
    return {"mass": f(S.MASS), "J": [f(S.J_FULL[k, k]) for k in range(3)], "Jxz": f(S.J_FULL[0, 2]),
            "eps_deg": f(S.EPS / S.DEG), "cg_in": [f(v) for v in S.CG_IN], "S": f(S.S), "b": f(S.B), "cbar": f(S.CBAR),
            "r_aero": [f(v) for v in S.R_AERO], "r_prop": [f(v) for v in S.R_PROP], "r_eye": [f(v) for v in S.R_EYE],
            "struct": {k: [f(x) for x in v] for k, v in S.STRUCT.items()}, "gear": gear,
            "prop_D": f(S.PROP_D), "prop_J": f(S.PROP_J), "g0": S.G0,
            "engine": {"displacement": f(S.DISPLACEMENT), "isfc": f(M.ISFC), "isfc_file": f(M.ISFC_FILE),
                       "z_airbox": f(S.Z_AIRBOX), "z_thr": f(S.Z_THROTTLE), "stroke_in": S.ED["stroke_in"],
                       "cr": S.ED["compression_ratio"], "VE": S.ED["volumetric_efficiency"], "R_air": S.ED["R_air"],
                       "fric_hp": S.ED["static_friction_hp"], "fmep_dyn": S.ED["fmep_dynamic_pa"],
                       "fmep_static": S.ED["fmep_static_pa"], "cycles": S.E["cycles"],
                       "peak_mps": S.ED["peak_piston_speed_fps"], "lag": S.ED["man_press_lag_s"]},
            "smoothing": {"V_FLOOR": M.V_FLOOR, "TF_ALPHADOT": M.TF_ALPHADOT, "EPS_ABS": M.EPS_ABS,
                          "CMD_SMOOTH": M.CMD_SMOOTH, "W_FLOOR": M.W_FLOOR, "N_FLOOR": M.N_FLOOR,
                          "MPS_FLOOR": M.MPS_FLOOR, "GEAR_EPS": M.GEAR_EPS, "GEAR_FEPS": M.GEAR_FEPS,
                          "V_ROLL": M.V_ROLL, "V_SIDE": M.V_SIDE, "FLAP_GAIN": M.FLAP_GAIN}}


def col(tab, k):
    return [f(r[k]) for r in tab]


def tables() -> dict:
    """The aerodynamic tables as the Lookup1D blocks of the model take them: name -> (x, y)."""
    t = {}
    for nm in ("KCDGE", "KCLGE", "CDDF", "CLDF", "CMDF", "CLB", "CNB"):
        tab = getattr(D, nm)
        t[nm] = {"x": col(tab, 0), "y": col(tab, 1)}
    for k in range(2):
        t[f"CLWBH{k}"] = {"x": col(D.CLWBH, 0), "y": col(D.CLWBH, 1 + k)}
    for k in range(4):
        t[f"CDWBH{k}"] = {"x": col(D.CDWBH, 0), "y": col(D.CDWBH, 1 + k)}
    for nm in ("CYB", "CYP", "CYR", "CLR"):
        tab = getattr(D, nm)
        for k, fl in enumerate((0, 30)):
            t[f"{nm}{fl}"] = {"x": col(tab, 0), "y": col(tab, 1 + k)}
    t["C_THRUST"] = {"x": col(D.C_THRUST, 0), "y": col(D.C_THRUST, 1)}
    t["C_POWER"] = {"x": col(D.C_POWER, 0), "y": col(D.C_POWER, 1)}
    # the JSBSim tables the POH fit starts from (not used by the models), and the fit
    t["C_THRUST_JSBSIM"] = {"x": col(D.C_THRUST_JSBSIM, 0), "y": col(D.C_THRUST_JSBSIM, 1)}
    t["C_POWER_JSBSIM"] = {"x": col(D.C_POWER_JSBSIM, 0), "y": col(D.C_POWER_JSBSIM, 1)}
    t["PROP_FIT"] = dict(zip(("kT", "J1T", "kP", "J1P"), (f(v) for v in D.PROP_FIT)))
    t["MIXTURE_EFFICIENCY"] = {"x": col(D.MIXTURE_EFFICIENCY, 0), "y": col(D.MIXTURE_EFFICIENCY, 1)}
    return t


def coefficients() -> dict:
    names = ("CD0", "CDDE", "CDBETA", "CYDR", "CLDE", "CLADOT", "CLQ", "CLP", "CLDA", "CLDR", "CMO", "CMALPHA", "CMQ",
             "CMADOT", "CMDE", "CNP", "CNR", "CNDA", "CNDR")
    return {n: f(getattr(D, n)) for n in names}


# --------------------------------------------------------------------------- 2. engine
def engine() -> dict:
    out = {}
    T, pa, rho, a = S.atmosphere(0.0)
    for label, isfc in (("file", M.ISFC_FILE), ("calibrated", M.ISFC)):
        M.ISFC = isfc
        rows = []
        for rpm in (2300.0, 2400.0, 2500.0, 2700.0):
            w = rpm * 2 * math.pi / 60.0
            MAP = M.map_target(w, 1.0, pa)
            P_, info = M.engine_power(w, 1.0, 1.0, MAP, pa, T)
            rows.append({"rpm": rpm, "hp": f(info["hp"]), "MAP_inhg": f(MAP / S.INHG), "ff_gph": f(info["ff_pph"] / 6.0)})
        out[label] = {"isfc": f(isfc), "full_throttle_sl": rows}
    M.ISFC = out["calibrated"]["isfc"]
    return out


# --------------------------------------------------------------------------- 3. performance
def performance() -> dict:
    """Three cases: the model (ISFC 0.418, the POH-fitted propeller), the same engine with the
    JSBSim propeller tables (the fit's starting point), and the engine file's bsfc 0.32 with the
    JSBSim propeller (the over-powered engine that hides the weak static thrust)."""
    out = {}
    cal = M.ISFC
    fitted = (D.C_THRUST, D.C_POWER)
    jsbsim = (D.C_THRUST_JSBSIM, D.C_POWER_JSBSIM)
    for label, isfc, prop in (("calibrated", cal, fitted), ("jsbsim_prop", cal, jsbsim), ("file", M.ISFC_FILE, jsbsim)):
        M.ISFC = isfc
        D.C_THRUST, D.C_POWER = prop
        t0 = time.time()
        rec = {"isfc": f(isfc)}
        rec["stall"] = {str(fl): P.stall_speed(fl) for fl in (0.0, 10.0, 30.0)}
        rec["climb_sl"] = {k: f(v) for k, v in P.best_climb(0.0).items()}
        rec["climb_8000"] = {k: f(v) for k, v in P.best_climb(8000 * FT).items()}
        rec["roc_at_vy_sl"] = roc_at(76.0, 0.0)
        rec["roc_at_vy_8000"] = roc_at(72.0, 8000 * FT)
        rec["vmax_sl"] = {k: f(v) for k, v in P.level_full_throttle(0.0).items()}
        rec["vmax_8000"] = {k: f(v) for k, v in P.level_full_throttle(8000 * FT).items()}
        rec["glide"] = {k: f(v) for k, v in P.best_glide().items()}
        rec["glide_at_65"] = glide_at(65.0)
        x, c, g = P.ground_state(throttle=1.0, flap_deg=10.0)
        rec["static"] = {"rpm": f(M.outputs(x, c, M.Params())["rpm"]), "thrust_n": f(M.outputs(x, c, M.Params())["thrust"]),
                         "hp": f(M.outputs(x, c, M.Params())["hp"])}
        to = P.takeoff()
        rec["takeoff"] = {"roll_ft": f(to["x"] / FT), "t_liftoff": f(to["t"]), "kcas_liftoff": f(to["kcas"]),
                          "d50_ft": f(to["x50"] / FT), "kcas50": f(to["kcas50"])}
        print(f"  performance ({label}): {time.time() - t0:.0f} s")
        out[label] = rec
    M.ISFC = cal
    D.C_THRUST, D.C_POWER = fitted
    return out


def roc_at(kcas, h):
    x, c, info = P.trim_cas(kcas * KT, h, throttle=1.0, mixture=P.best_power_mixture(h),
                            guess=[0.08, 0, -0.2, 0, 0, 0.05, 240.0])
    return {"kcas": kcas, "roc_fpm": f(info["vt"] * math.sin(info["gamma"]) / FT * 60.0), "rpm": f(info["rpm"])}


def glide_at(kcas, h=1524.0):
    x, c, info = P.trim_cas(kcas * KT, h, throttle=0.0, mixture=0.0, guess=[0.06, 0, -0.2, 0, 0, -0.1, 100.0])
    return {"kcas": kcas, "ratio": f(-1.0 / math.tan(info["gamma"]))}


# --------------------------------------------------------------------------- 4. open loop
OL_V = 100.0 * KT
OL_H = 5000.0 * FT
OL_T_END = 120.0
OL_DT = 0.05
MODES = {  # mode: (amplitude, the state it scales (LIN index), unit factor)
    "short_period": (1.0 * S.DEG, 12, None),     # alpha-dot filter state ~ alpha: 1 deg of alpha
    "phugoid": (2.0, 0, None),                   # 2 m/s of u
    "dutch_roll": (1.0 * S.DEG, 1, "beta"),      # 1 deg of beta (v = V beta)
    "roll": (2.0 * S.DEG, 6, None),              # 2 deg of bank
    "spiral": (5.0 * S.DEG, 6, None),            # 5 deg of bank
}


def lin_trim():
    mix = P.best_power_mixture(OL_H)
    x, c, info = L.trim(OL_V, OL_H, gamma=0.0, mixture=mix, guess=[0.03, 0, -0.2, 0, 0, 0.6, 230.0])
    assert info["ok"], info
    return x, c, info


def eig_start(x0, A, mode_rec, name):
    amp, idx, kind = MODES[name]
    v = mode_rec["vec"]
    z0 = L.to_lin(x0)
    if abs(mode_rec["lam"].imag) > 1e-9:
        # the oscillatory modes: scale the complex eigenvector so the nominated state starts at
        # its amplitude (real part), and take the real part
        sc = amp / (v[idx] if kind is None else v[idx] / OL_V)
        dz = np.real(sc * v)
    else:
        dz = np.real(v / v[idx] * amp)
    if name == "short_period":   # nominate alpha through w (w = V alpha), not the filter state
        sc = amp * OL_V / v[2]
        dz = np.real(sc * v)
    return L.from_lin(z0 + dz, x0), dz


def ol_run(x_start, c, par):
    ts = np.arange(0.0, OL_T_END + 1e-9, OL_DT)
    sol = solve_ivp(lambda t, x: M.deriv(t, x, c, par), (0.0, OL_T_END), x_start, method="DOP853",
                    t_eval=ts, rtol=1e-11, atol=1e-11)
    rec = {k: [] for k in ("t", "alpha_deg", "beta_deg", "vt", "h", "theta_deg", "phi_deg", "q_deg", "p_deg", "r_deg",
                           "rpm", "lambda")}
    for k, t in enumerate(sol.t):
        x = sol.y[:, k]
        o = M.outputs(x, c, par)
        rec["t"].append(f(t))
        rec["alpha_deg"].append(f(o["alpha"] / S.DEG))
        rec["beta_deg"].append(f(o["beta"] / S.DEG))
        rec["vt"].append(f(o["vt"]))
        rec["h"].append(f(o["h"]))
        rec["theta_deg"].append(f(o["theta"] / S.DEG))
        rec["phi_deg"].append(f(o["phi"] / S.DEG))
        rec["q_deg"].append(f(o["q"] / S.DEG))
        rec["p_deg"].append(f(o["p"] / S.DEG))
        rec["r_deg"].append(f(o["r"] / S.DEG))
        rec["rpm"].append(f(o["rpm"]))
        phidot = o["p"] + math.tan(o["theta"]) * (o["q"] * math.sin(o["phi"]) + o["r"] * math.cos(o["phi"]))
        rec["lambda"].append(f(phidot / o["phi"]) if abs(o["phi"]) > 1e-12 else 0.0)
    return rec


def state_starts(x, c):
    """The bg-sim start values of a reference state: Free3D pose, RigidBody3D momentum
    [J w; m v] (FLU), the rotor's axial momentum, the manifold pressure, the alpha-dot filter,
    the flap angle and the strut compressions."""
    J = np.array([S.J_FULL[k, k] for k in range(3)])
    return {"pose": [f(v) for v in list(x[M.I_Q:M.I_Q + 4]) + list(x[M.I_POS:M.I_POS + 3])],
            "P": [f(v) for v in list(J * x[M.I_W:M.I_W + 3]) + list(S.MASS * x[M.I_V:M.I_V + 3])],
            "h_rotor": f(x[M.I_H]), "MAP": f(x[M.I_MAP]), "xad": f(x[M.I_AD]), "flap": f(x[M.I_FLAP]),
            "strut": [f(x[M.I_STRUT + k]) for k in range(3)],
            "controls": {"yoke_pitch": f(c.yoke_pitch), "yoke_roll": f(c.yoke_roll), "pedals": f(c.pedals),
                         "throttle": f(c.throttle), "mixture": f(c.mixture), "flaps": f(c.flaps), "trim": f(c.trim)}}


def open_loop() -> dict:
    x0, c, info = lin_trim()
    par = M.Params(gear=False)
    A, z0 = L.linearise(x0, c, par)
    md = L.classify(A)
    out = {"trim": {k: (f(v) if isinstance(v, (float, int, np.floating)) else v) for k, v in info.items()},
           "trim_state": state_starts(x0, c), "modes": {}, "eig_all": [[f(m["lam"].real), f(m["lam"].imag)] for m in md["all"]]}
    for name in MODES:
        xs, dz = eig_start(x0, A, md[name], name)
        rec = ol_run(xs, c, par)
        out["modes"][name] = {**L.mode_numbers(md[name]), "start": state_starts(xs, c), "run": rec,
                              "dz": [f(v) for v in dz]}
        print(f"  {name}: {L.mode_numbers(md[name])}")
    return out


# --------------------------------------------------------------------------- 5. cessna-sim
SIM_DT = 0.005


def sim() -> dict:
    out = {}
    # ---- the runway start (engine at idle, flaps 10)
    x0, g = Dm.runway_start(10.0)
    out["runway"] = {"start": state_starts(x0, M.Controls(flaps=1.0)), "h_cg": f(g["h_cg"]), "theta": f(g["theta"]),
                     "omega": f(g["omega"]), "residual": f(g["residual"])}
    # ---- the demo
    t0 = time.time()
    d = Dm.Demo()
    d.h_cg0 = g["h_cg"]

    def ctl_demo(t, x, ex, o):
        yoke, roll, ped, thr, flaps = Dm.demo_controls(t, o, d)
        return M.Controls(yoke_pitch=yoke, yoke_roll=roll, pedals=ped, throttle=thr, flaps=flaps), np.zeros(0)
    rec, _ = Dm.run(x0, 120.0, ctl_demo, dt=SIM_DT)
    out["demo"] = {"run": rec, "milestones": Dm.milestones(rec, g["h_cg"]), "t_end": 120.0,
                   "params": {k: f(v) for k, v in vars(d).items()}}
    print(f"  demo: {time.time() - t0:.0f} s {out['demo']['milestones']}")
    # ---- trimmed airborne starts: autopilot hold, best-rate climb, full throttle at 8000 ft
    for name, (kcas, h, mode) in {"ap": (95.0, 1000.0, "level"), "climb": (76.0, 0.0 + 300.0, "climb"),
                                  "cruise": (None, 8000 * FT, "vmax")}.items():
        t0 = time.time()
        mix = P.best_power_mixture(h)
        if mode == "level":
            x, c, info = P.trim_cas(kcas * KT, h, gamma=0.0, mixture=mix, guess=[0.03, 0, -0.2, 0, 0, 0.6, 230.0])
        elif mode == "climb":   # at the model's best-rate speed there (the POH's Vy is 76 KIAS)
            kcas = P.best_climb(h, mixture=mix)["kcas"]
            x, c, info = P.trim_cas(kcas * KT, h, throttle=1.0, mixture=mix, guess=[0.08, 0, -0.2, 0, 0, 0.05, 240.0])
        else:
            vm = P.level_full_throttle(h, mixture=mix)
            x, c, info = L.trim(vm["ktas"] * KT, h, gamma=0.0, mixture=mix, guess=[0.01, 0, -0.2, 0, 0, 0.99, 260.0])
        assert info["ok"], (name, info)
        for k in range(3):   # the struts far above the runway: their geometric penetration
            x[M.I_STRUT + k] = L.penetration(x, M.GEARS[k])
        rec_t = {"trim": {k: (f(v) if isinstance(v, (float, int, np.floating)) else v) for k, v in info.items()},
                 "start": state_starts(x, c)}
        if name == "ap":
            a = Dm.AP()
            hdg = 60.0 * S.DEG

            def ctl_ap(t, xx, ex, o, c=c, a=a, hdg=hdg, h=h):
                pitch, roll, xid = Dm.ap_rates(o, ex[0], 2.0, 1.0, hdg, h, a)
                cc = M.Controls(yoke_pitch=max(-1.0, min(1.0, c.yoke_pitch + pitch)),
                                yoke_roll=max(-1.0, min(1.0, c.yoke_roll + roll)), pedals=c.pedals,
                                throttle=c.throttle, mixture=c.mixture, flaps=c.flaps)
                return cc, np.array([xid])
            r, _ = Dm.run(x, 60.0, ctl_ap, dt=SIM_DT, extra=[0.0])
            rec_t.update({"run": r, "hdg_ref_deg": 60.0, "alt_ref": h, "t_end": 60.0})
        else:
            def ctl_c(t, xx, ex, o, c=c):
                return c, np.zeros(0)
            r, _ = Dm.run(x, 20.0, ctl_c, dt=SIM_DT)
            rec_t.update({"run": r, "t_end": 20.0})
        out[name] = rec_t
        print(f"  {name}: {time.time() - t0:.0f} s")
    return out


def main() -> int:
    t0 = time.time()
    design = {"si": si(), "tables": tables(), "coef": coefficients(), "engine": engine()}
    print("engine:", {k: v["full_throttle_sl"][-1]["hp"] for k, v in design["engine"].items()})
    design["poh"] = {"geometry": poh.GEOMETRY, "performance": poh.PERFORMANCE}
    design["performance"] = performance()
    design["open_loop"] = open_loop()
    design["sim"] = sim()
    write_design(design)
    print(f"wrote design.json ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
