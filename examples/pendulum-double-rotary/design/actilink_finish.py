# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6"]
# ///
"""Run the ACTILINK models, measure them, fit the identification experiments, write the checks.

    uv run examples/pendulum-double-rotary/design/actilink_finish.py [--runs DIR] [--no-run]

1. runs every `actilink-*` model through BGSim (`actilink_run.jl`, one Julia process) into
   `<temp>/bgsim-actilink-runs/` (or `--runs DIR`; reuses it with `--no-run`). The runs take a few
   GB and stay outside the example folder, because a project created from the example copies it;
2. exports the identification runs as CSV (`<runs>/csv/<model>.csv`, the layout of
   the run export) and fits them with `actilink_sysid.py`: `design/actilink_sysid_fit.json`;
3. compares the free swing with the Python twin (`actilink_design.json`, `free`) and measures
   balance, push and swing-up: `design/actilink_measured.json`;
4. writes the `actilink-*` entries of `expected.json` (the Quanser entries are kept as they are).

Exits non-zero when an identified parameter is outside its stated tolerance.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actilink_io as aio
import actilink_lib as al
import actilink_sysid as asy
from actilink_models import SYSID

ROOT = HERE.parent
REPO = HERE.parents[2]
CODES = ["W201", "W206", "E901"]
MODELS = ["actilink-free", "actilink-balance", "actilink-push", "actilink-swingup", "actilink-sysid-current",
          "actilink-sysid-friction", "actilink-sysid-gear", "actilink-sysid-swing1", "actilink-sysid-swing2",
          "actilink-sysid-encoder", "actilink-sysid-chirp"]
CSV_COLUMNS = {
    "actilink-sysid-current": ["CurrentLoop/uq", "CurrentLoop/iq", "DriveLoop/iref", "Wm/y"],
    "actilink-sysid-friction": ["Cmd/w_cmd", "DriveLoop/tau_ref", "CurrentLoop/uq", "CurrentLoop/iq", "Wm/y"],
    "actilink-sysid-gear": ["MotorEnc/y", "OutputEnc/y", "DriveLoop/tau_ref"],
    "actilink-sysid-swing1": ["Enc1A/y"],
    "actilink-sysid-swing2": ["Enc2A/y"],
    "actilink-sysid-encoder": ["OutputEnc/y", "EncBench/y"],
    "actilink-sysid-chirp": ["DriveLoop/tau_ref", "OutputEnc/y"],
}


def run_models(out: Path, models: list[str]) -> None:
    cmd = ["julia", f"--project={REPO / 'julia' / 'BGSim'}", str(HERE / "actilink_run.jl"), str(out), *models]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=REPO)


def wrap(a):
    return (np.asarray(a) + math.pi) % (2 * math.pi) - math.pi


def compare_free(dz: dict, t, c) -> dict:
    fr = dz["free"]
    worst = {"J1/qout": 0.0, "Angles/phi1": 0.0, "Angles/phi2": 0.0}
    for i, tt in enumerate(fr["t"]):
        ref = {"J1/qout": fr["q"][i][0], "Angles/phi1": fr["phi"][i][0], "Angles/phi2": fr["phi"][i][1]}
        for k, v in ref.items():
            worst[k] = max(worst[k], abs(aio.at(t, c[k], tt) - v))
    worst["max"] = max(worst.values())
    return worst


def measure_ctrl(t, c, t_push: float | None = None, t_on: float = 0.0) -> dict:
    phi = np.stack([wrap(c["Angles/phi1"]), wrap(c["Angles/phi2"])], axis=1)
    dev = np.max(np.abs(phi), axis=1)
    mode = c["Ctrl/mode"]
    t_catch = float(t[np.argmax(mode >= 1.5)]) if np.any(mode >= 1.5) else math.nan
    settled_from = (t_catch if t_push is None else 0.0) + 1.5
    pre = (t >= settled_from) & (t < (t_push if t_push is not None else t[-1] + 1))
    tail = t >= t[-1] - 1.0
    out = {
        "t_catch": t_catch,
        "band_deg": math.degrees(float(np.max(dev[pre]))) if np.any(pre) else math.nan,
        "final_dev_deg": math.degrees(float(dev[-1])),
        "tail_dev_deg": math.degrees(float(np.max(dev[tail]))),
        "tail_arm_p2p_deg": math.degrees(float(np.ptp(c["J1/qout"][tail]))),
        "arm_max": float(np.max(np.abs(c["J1/qout"]))),
        "tau_peak": float(np.max(np.abs(c["DriveLoop/tau_ref"]))),
        "iq_peak": float(np.max(np.abs(c["CurrentLoop/iq"]))),
        "uq_peak": float(np.max(np.abs(c["CurrentLoop/uq"]))),
        "defl_max": float(np.max(np.abs(c["GearSpring/defl"]))),
    }
    if t_on > 0.0:
        rest = (t > 0.05) & (t < t_on - 0.01)
        out["rest_arm_rate"] = float(np.max(np.abs(c["J1/qdout"][rest])))
    if t_push is not None:
        post = t >= t_push
        out["push_peak_deg"] = math.degrees(float(np.max(np.abs(phi[post, 1]))))
        out["push_arm_max"] = float(np.max(np.abs(c["J1/qout"][post])))
        outside = np.where((dev > math.radians(1.0)) & post)[0]
        out["t_recover"] = float(t[outside[-1]] - t_push) if len(outside) else 0.0
    out.update(energy_terms(t, c, t_push))
    return out


def lim_check(signal, value, note, **kw):
    out = {"kind": "max_abs_le", "signal": signal, "value": value, "note": note}
    out.update(kw)
    return out


def energy_checks(m: dict, to_t: float | None = None) -> list[dict]:
    tol = max(1e-4, 2.0 * m["H_drift"] / m["H_scale"])
    note = (f"energy balance of the whole rig H = E_mech + E_drive + W_loss - W_in (link, arm, rotor and winding energy, gear "
            f"spring, every friction and copper loss) is constant up to the energy the joint-compliance regularisation of the three "
            f"Revolute3D joints absorbs (kr = kt = 1e6 with damping, excited by the drive's torque ripple): measured drift "
            f"{m['H_drift']:.3g} J, joint port work {m['W_joint']:.3g} J, throughput {m['H_scale']:.3g} J; bound 2x the drift, at least 1e-4. "
            f"The energy_ledger check closes the balance exactly, joints included")
    chk = {"kind": "invariant", "terms": [{"signal": "Energy/H", "coeff": 1.0}], "scale": float(f"{m['H_scale']:.4g}"),
           "tol": float(f"{tol:.2g}"), "note": note}
    if to_t is not None:
        chk["to_t"] = to_t
    return [chk, {"kind": "energy_ledger", "tol": 1e-6,
                  "note": "Tellegen: the port powers of every bond sum to zero over the run (joint compliance included)"}]


def ctrl_checks(dz: dict, dr: al.Drive, m: dict, *, t_on: float, t_end: float, t_push: float | None, swing: bool) -> list[dict]:
    band = max(1.0, 2.0 * m["band_deg"])
    checks = [
        {"kind": "scene_bindings"},
        {"kind": "no_diagnostics", "codes": CODES, "note": "no derivative-causality warning, no event-loop warning, no solver failure"},
        lim_check("CurrentLoop/iq", round(dr.iq_peak, 4),
                  f"the q current stays inside the drive's peak current ({dr.iq_peak:.2f} A amplitude: the gear's peak torque "
                  f"{dr.tau_peak:g} N m at the output, inside the Circulo's {dr.I_max_rms:g} A rms); measured {m['iq_peak']:.2f} A"),
        lim_check("DriveLoop/tau_ref", dz["umax"] + 1e-9,
                  f"the torque command stays inside the firmware clamp {dz['umax']:g} N m (rated {dr.tau_rated:g} N m); "
                  f"measured {m['tau_peak']:.2f} N m"),
        lim_check("CurrentLoop/uq", round(dr.uq_max + 1e-6, 6),
                  f"the q voltage stays inside the inverter limit 0.95 V_dc/sqrt(3) = {dr.uq_max:.2f} V; measured {m['uq_peak']:.2f} V"),
        lim_check("GearSpring/defl", float(f"{max(2.0 * m['defl_max'], 1e-3):.3g}"),
                  f"gear deflection (backlash + torsion) bounded: measured {m['defl_max'] * 1e3:.2f} mrad, bound 2x"),
    ]
    if swing:
        t_c = t_on + dz["t_s"]
        checks += [
            {"kind": "cursor_value", "signal": "Ctrl/mode", "t": t_on - 0.05, "value": 0.0, "abs": 1e-9, "note": "idle before t_on"},
            {"kind": "cursor_value", "signal": "J2/qout", "t": t_on - 0.05, "value": math.pi, "abs": 2e-3,
             "note": "link 1 hangs straight down before t_on"},
            {"kind": "max_abs_le", "signal": "J1/qdout", "from_t": 0.05, "to_t": t_on - 0.01,
             "value": float(f"{max(2e-3, 5 * m['rest_arm_rate']):.2g}"),
             "note": "at rest before t_on (drive enabled, zero torque); bound 5x the measured residual"},
            {"kind": "cursor_value", "signal": "Ctrl/mode", "t": t_c + 0.5, "value": 2.0, "abs": 1e-9,
             "note": f"balance controller latched by t_on + T_s + 0.5 s (measured catch at {m['t_catch']:.3f} s)"},
            {"kind": "max_abs_le", "signal": "J1/qout", "value": 3.5,
             "note": f"the arm stays within +-3.5 rad (the trajectory bound is 3 rad; measured {m['arm_max']:.2f} rad)"},
        ]
        settle = t_c + 1.5
    else:
        checks.append({"kind": "cursor_value", "signal": "Ctrl/mode", "t": 0.01, "value": 2.0, "abs": 1e-9,
                       "note": "balance controller active from the first cycle"})
        settle = 1.5
    to_t = t_push - 0.01 if t_push is not None else t_end
    checks.append({"kind": "max_abs_le", "signal": "Angles/dev", "from_t": settle, "to_t": to_t, "value": math.radians(band),
                   "note": f"balancing with the quantised AS5048A readings: every link within {band:.2f} deg of upright from {settle:g} s "
                           f"(measured {m['band_deg']:.2f} deg; bound 2x, at least 1 deg)"})
    if t_push is not None:
        rec = min(t_push + 1.25 * m["t_recover"] + 0.5, t_end - 0.5)
        checks += [
            {"kind": "max_abs", "signal": "Angles/phi2", "from_t": t_push, "to_t": t_end, "value": math.radians(m["push_peak_deg"]),
             "rtol": 0.3, "note": f"the push is real: link 2 deflects {m['push_peak_deg']:.2f} deg; band +-30 %"},
            {"kind": "max_abs_le", "signal": "Angles/dev", "from_t": rec, "to_t": t_end, "value": math.radians(band),
             "note": f"recovered: back inside {band:.2f} deg from {rec:.2f} s (measured: inside 1 deg {m['t_recover']:.2f} s after the push)"},
        ]
    checks += energy_checks(m, to_t if t_push is not None else None)
    return checks


def free_checks(dz: dict, free: dict, m_h: dict) -> list[dict]:
    tol = float(f"{max(1e-3, 2.0 * free['max']):.2g}")
    checks = [{"kind": "scene_bindings"}, {"kind": "no_diagnostics", "codes": CODES}]
    fr = dz["free"]
    note = (f"actilink_design.py twin (9 states: rigid multibody, gear with smooth backlash and hardening, Stribeck friction, "
            f"rotor, winding, 16 kHz current loop) against the bond graph, open loop with a zero torque target; tolerance 2x the "
            f"measured max difference {free['max']:.2g} rad (at least 1 mrad)")
    for i, tt in enumerate(fr["t"]):
        if i % 2 == 0:
            continue
        checks.append({"kind": "cursor_value", "signal": "J1/qout", "t": tt, "value": fr["q"][i][0], "abs": tol, "note": note})
        for k in range(2):
            checks.append({"kind": "cursor_value", "signal": f"Angles/phi{k + 1}", "t": tt, "value": fr["phi"][i][k], "abs": tol, "note": note})
    return checks + energy_checks(m_h)


def sysid_checks(name: str, t, c, dz: dict, tr: dict, dr: al.Drive) -> list[dict]:
    checks = [{"kind": "no_diagnostics", "codes": CODES}]
    if name == "actilink-sysid-current":
        i_ss = SYSID["current_amp"] / (dr.N * dr.kt_q)
        checks.append({"kind": "cursor_value", "signal": "CurrentLoop/iq", "t": 0.035, "value": float(f"{i_ss:.6g}"), "rtol": 0.1,
                       "note": "the current step reaches the commanded i_q = tau/(N kt_q) (5 N m at the output, arm clamped)"})
    elif name in ("actilink-sysid-swing1", "actilink-sysid-swing2"):
        k = 1 if name.endswith("1") else 2
        s = tr[f"swing{k}"]
        a0 = SYSID["swing_amp"]
        # large-amplitude pendulum period (complete elliptic integral) as the reference
        from scipy.special import ellipk

        w0 = math.sqrt(al.G * s["mc"] / s["J_pivot"])
        period = 4.0 / w0 * ellipk(math.sin(a0 / 2) ** 2)
        sig = "J2/qout" if k == 1 else "J3/qout"
        level = math.pi if k == 1 else 0.0
        checks.append({"kind": "period", "signal": sig, "level": level, "direction": "up", "n": 1, "value": float(f"{period:.6g}"),
                       "rtol": 0.01, "note": f"first period of the free swing (released at {math.degrees(a0):.0f} deg) against the "
                                            f"undamped large-amplitude period 4/w0 K(sin^2(a/2)) with J = {s['J_pivot']:.5g} kg m^2"})
    elif name == "actilink-sysid-gear":
        checks.append({"kind": "max_abs", "signal": "GearSpring/defl", "value": float(f"{float(np.max(np.abs(c['GearSpring/defl']))):.4g}"),
                       "rtol": 0.05, "note": "locked-output torque reversal: the gear deflection (backlash + torsion) at the peak torque"})
    elif name == "actilink-sysid-friction":
        checks.append({"kind": "max_abs_le", "signal": "J2/qdout", "value": 1.5,
                       "note": "the clamped pendulum stays (nearly) still while the arm turns: 1.08 rad/s for a few ms at "
                               "the +8 -> -8 rad/s reversal (about 500 rad/s^2 on the arm), 2.3 mrad in the 1e5 Nm/rad "
                               "clamp, otherwise below 1e-4 rad/s"})
    elif name == "actilink-sysid-encoder":
        w = SYSID["enc_speed"]
        checks.append({"kind": "max_abs", "signal": "J1/qdout", "from_t": 0.6, "to_t": 0.1 + SYSID["enc_hold"], "value": w, "rtol": 0.05,
                       "note": f"constant speed {w:g} rad/s (CSV) during the bench turn"})
    elif name == "actilink-sysid-chirp":
        checks.append({"kind": "max_abs", "signal": "J1/qout", "value": float(f"{float(np.max(np.abs(c['J1/qout']))):.4g}"), "rtol": 0.1,
                       "note": "arm amplitude of the chirp"})
    return checks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path(tempfile.gettempdir()) / "bgsim-actilink-runs")
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("models", nargs="*")
    args = ap.parse_args()
    runs = args.runs
    if not args.no_run:
        run_models(runs, args.models or MODELS)
    dz = json.loads((HERE / "actilink_design.json").read_text(encoding="utf-8"))
    dr = al.drive(dz["size"])
    tr = asy.truth(dz["size"])

    # CSV export of the identification runs and the fits
    csv_dir = runs / "csv"
    data = {}
    for name in MODELS:
        if (runs / name / "manifest.json").is_file():
            data[name] = aio.load_run(runs / name)
    for name, cols in CSV_COLUMNS.items():
        if name in data:
            t, c = data[name]
            aio.write_csv(csv_dir / f"{name}.csv", t, c, cols)
    enc = dz["enc"]
    fit = asy.run_all(csv_dir, dz["size"], dz["zcal"], enc["lat_a"], enc["inl1"], enc["sigma"])
    (HERE / "actilink_sysid_fit.json").write_text(json.dumps(fit, indent=2) + "\n", encoding="utf-8", newline="\n")
    bad = [r for r in fit["compare"] if not r["ok"]]
    for r in fit["compare"]:
        print(f"  {r['group']:9s} {r['name']:28s} fit {r['fit']:.6g}  model {r['true']:.6g}  "
              f"error {100 * r['rel_err']:+.2f} % (tol {100 * r['tol']:.0f} %) {'ok' if r['ok'] else 'FAIL'}")

    # measurements and checks
    measured = {}
    entries = {}
    if "actilink-free" in data:
        t, c = data["actilink-free"]
        free = compare_free(dz, t, c)
        m = energy_terms(t, c)
        measured["free"] = {"twin_diff": free, **m}
        entries["actilink-free"] = {"run_timeout": 900.0, "checks": free_checks(dz, free, m)}
    t_on = dz["t_on"]
    for name, kw in (("actilink-balance", {"t_push": None, "swing": False, "t_on": 0.0}),
                     ("actilink-push", {"t_push": 2.0, "swing": False, "t_on": 0.0}),
                     ("actilink-swingup", {"t_push": None, "swing": True, "t_on": t_on})):
        if name not in data:
            continue
        t, c = data[name]
        m = measure_ctrl(t, c, kw["t_push"], kw["t_on"])
        measured[name] = m
        entries[name] = {"run_timeout": 1500.0, "checks": ctrl_checks(dz, dr, m, t_on=kw["t_on"], t_end=float(t[-1]),
                                                                       t_push=kw["t_push"], swing=kw["swing"])}
    for name in CSV_COLUMNS:
        if name in data:
            t, c = data[name]
            entries[name] = {"run_timeout": 900.0, "checks": sysid_checks(name, t, c, dz, tr, dr)}
    for name, m in measured.items():
        print(name, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()})
    (HERE / "actilink_measured.json").write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8", newline="\n")

    path = ROOT / "expected.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key, entry in entries.items():
        doc["models"][key] = entry
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(entries)} ACTILINK entries into {path}")
    if bad:
        print(f"{len(bad)} identified parameter(s) outside tolerance")
        sys.exit(1)


def energy_terms(t, c, t_end: float | None = None) -> dict:
    """Drift of the energy invariant H (before any external work) and the energy the three Revolute3D
    joints take in through their ports (their compliance regularisation: spring + damper), which H
    does not hold."""
    win = t < (t_end if t_end is not None else t[-1] + 1)
    h = c["Energy/H"][win]
    tw = t[win]
    w_joint = 0.0
    for j in ("J1", "J2", "J3"):
        w_joint += float(np.trapezoid((c[f"{j}/parent.P"] + c[f"{j}/child.P"] + c[f"{j}/drive.P"])[win], tw))
    return {"H_drift": float(np.max(np.abs(h - h[0]))), "H_end_change": float(h[-1] - h[0]), "W_joint": w_joint,
            "H_scale": float(max(np.max(np.abs(c["Energy/W_loss"][win])), np.max(np.abs(c["Energy/W_in"][win])), 1e-3))}


if __name__ == "__main__":
    main()
