# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Run the flexible-arm models of `pendulum-triple-rotary`, measure them and add their checks to
`expected.json` (the rigid entries written by `finish.py` are kept).

    uv run examples/pendulum-triple-rotary/design/flex_finish.py [--no-run]
    uv run examples/pendulum-triple-rotary/design/flex_finish.py --docs

Runs (real backend, saved in `design/_runs/`):

    pendulum-triple-rotary-flex           rigid firmware on the flexible arm (the instructive failure)
    pendulum-triple-rotary-flex-lowpass   the low-pass firmware (the fix)
    pendulum-triple-rotary-flex-free      free swing, controller off
    flex-tap        the free model hanging at rest with the hub clamped (rotor inertia 1e3 kg m^2)
                    and a 2 ms push on the tip link: the arm rings at its first modes
    flex-free-stiff the free model with the arm 1e4 times stiffer, against the rigid free model
    pendulum-triple-rotary, pendulum-triple-rotary-free (the rigid references)
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE.parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "pendulum-double-rotary" / "design"))

import runner  # noqa: E402

NAME = "pendulum-triple-rotary"
FLEX, LOWPASS, FREE = f"{NAME}-flex", f"{NAME}-flex-lowpass", f"{NAME}-flex-free"
CODES = ["W201", "W206", "E901"]
STIFF = 1.0e4  # E scale of the stiff-limit run
T_TAP = 0.05  # start of the push of the tap test [s]


def tap_overrides(fz: dict) -> dict:
    return {
        "J1/q0": 0.0, "J2/q0": math.pi, "J3/q0": 0.0, "J4/q0": 0.0,
        "Motor/J_m": 1.0e3,
        "DistPulse/amplitude": 1.0, "DistPulse/t_start": T_TAP, "DistPulse/duty": 0.002 / 1000.0,
    }


RUNS = {
    # label: (model, settings, overrides)
    NAME: (NAME, None, None),
    f"{NAME}-free": (f"{NAME}-free", None, None),
    FLEX: (FLEX, None, None),
    LOWPASS: (LOWPASS, None, None),
    FREE: (FREE, None, None),
    "flex-tap": (FREE, {"t_end": 1.0, "output": {"points": 20001}}, "tap"),
    "flex-free-stiff": (FREE, None, "stiff"),
    "flex-e100": (FLEX, None, "e100"),
}
E100 = 100.0  # E scale at which the rigid firmware works on the flexible arm (the linear loop at the upright needs about 23)


def run_all(fz: dict, labels: list[str], out_dir: Path) -> dict:
    rc = runner._harness()
    rc._kill_children_with_me()
    root = Path(tempfile.mkdtemp(prefix="bgsim-flex-"))
    log = root / "backend.log"
    process = client = None
    stats = {}
    import httpx

    try:
        process, port = rc._start_backend(root, log)
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(180.0, connect=10.0))
        rc._wait_for_worker(client, process, log)
        project = f"design-{NAME}-flex"
        client.post("/api/projects", json={"name": project, "example": NAME}).raise_for_status()
        project_dir = Path(rc._get_json(client, f"/api/projects/{project}")["path"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for label in labels:
            model, settings, ov = RUNS[label]
            overrides = None
            if ov == "tap":
                overrides = tap_overrides(fz)
            elif ov == "stiff":
                overrides = {"Arm/E": fz["arm"]["E"] * STIFF}
            elif ov == "e100":
                overrides = {"Arm/E": fz["arm"]["E"] * E100}
            started = time.perf_counter()
            run = rc._run_model(client, project, project_dir, model, settings, 3600.0, overrides)
            elapsed = time.perf_counter() - started
            np.savez(out_dir / f"{label}.npz", time=run.time, **{k.replace("/", "__"): v for k, v in run.signals.items()})
            stats[label] = {"seconds": elapsed, "points": int(run.time.size), "diagnostics": run.manifest.get("diagnostics")}
            print(f"{label}: {elapsed:.1f} s, {run.time.size} points, diagnostics {run.manifest.get('diagnostics')}", flush=True)
        client.delete(f"/api/projects/{project}")
    finally:
        if client is not None:
            client.close()
        if process is not None:
            rc._stop_backend(process)
        shutil.rmtree(root, ignore_errors=True)
    return stats


def fft_peak(t, y, t0, t1, fmin, fmax) -> float:
    """The dominant frequency in [fmin, fmax] (Hann, zero padding, parabolic refinement), like run_checks."""
    keep = np.concatenate([np.diff(t) > 0, [True]])
    t, y = t[keep], y[keep]
    m = (t >= t0) & (t <= t1)
    t, y = t[m], y[m]
    dt = float(np.median(np.diff(t)))
    tu = np.arange(t[0], t[-1], dt)
    yu = np.interp(tu, t, y)
    yu = yu - np.polyval(np.polyfit(tu, yu, 1), tu)
    yu = yu * np.hanning(len(yu))
    nfft = 1 << (len(yu) * 8 - 1).bit_length()
    spec = np.abs(np.fft.rfft(yu, nfft))
    f = np.fft.rfftfreq(nfft, dt)
    band = (f >= fmin) & (f <= fmax)
    idx = np.where(band)[0]
    i = idx[np.argmax(spec[idx])]
    a, b, c = spec[i - 1], spec[i], spec[i + 1]
    p = 0.5 * (a - c) / (a - 2 * b + c)
    return float(f[i] + p * (f[1] - f[0]))


def measure_lowpass(dz: dict, t, s) -> dict:
    dev = s["Angles/dev"]
    phase = s["Ctrl/phase"]
    t_on, t_dist = dz["t_on"], dz["t_dist"]
    t_catch = float(t[np.argmax(phase >= 2)]) if np.any(phase >= 2) else math.nan
    pre = (t >= t_catch + 1.5) & (t < t_dist)
    post = (t >= t_dist) & (t <= t_dist + 2.0)
    outside = np.where((dev > math.radians(0.5)) & (t >= t_dist))[0]
    near = np.where((dev < math.radians(3.0)) & (t > t_on))[0]
    swing = (t > t_on) & (t < t_catch)
    bal = (t >= t_catch + 1.5) & (t < t_dist)
    return {
        "t_upright": float(t[near[0]]) if len(near) else math.nan,
        "t_catch": t_catch,
        "band_pre_deg": math.degrees(float(np.max(dev[pre]))),
        "peak_defl_deg": math.degrees(float(np.max(np.abs(s["Angles/phi3"][post])))),
        "t_recover": float(t[outside[-1]]) - t_dist if len(outside) else 0.0,
        "final_dev_deg": math.degrees(float(dev[-1])),
        "peak_v": float(np.max(np.abs(s["Ctrl/u"]))),
        "max_arm": float(np.max(np.abs(s["J1/qout"]))),
        "tip_y_swing_mm": 1e3 * float(np.max(np.abs(s["Arm/dB[2]"][swing]))),
        "tip_y_balance_mm": 1e3 * float(np.max(np.abs(s["Arm/dB[2]"][bal]))),
        "tip_y_dist_mm": 1e3 * float(np.max(np.abs(s["Arm/dB[2]"][post]))),
        "tip_z_mm": 1e3 * float(np.max(np.abs(s["Arm/dB[3]"]))),
        "twist_mrad": 1e3 * float(np.max(np.abs(s["Arm/twist"]))),
        "eta_y1_mm": 1e3 * float(np.max(np.abs(s["Arm/eta_y[1]"]))),
        "eta_y2_mm": 1e3 * float(np.max(np.abs(s["Arm/eta_y[2]"]))),
    }


def measure_failure(dz: dict, t, s) -> dict:
    dev = s["Angles/dev"]
    u = s["Ctrl/u"]
    t_on = dz["t_on"]
    sat = np.where((np.abs(u) >= dz["vmax"] - 1e-6) & (t > t_on))[0]
    big = np.where(np.abs(s["Arm/eta_y[1]"]) > 2e-4)[0]
    fell = np.where((dev > math.radians(30.0)) & (t > t_on + dz["t_s"]))[0]
    return {
        "max_phase": float(np.max(s["Ctrl/phase"])),
        "t_first_saturation": float(t[sat[0]]) if len(sat) else math.nan,
        "t_eta_02mm": float(t[big[0]]) if len(big) else math.nan,
        "max_eta_y1_mm": 1e3 * float(np.max(np.abs(s["Arm/eta_y[1]"]))),
        "max_tip_y_mm": 1e3 * float(np.max(np.abs(s["Arm/dB[2]"]))),
        "max_dev_deg": math.degrees(float(np.max(dev[t > t_on + dz["t_s"]]))),
        "t_fall": float(t[fell[0]]) if len(fell) else math.nan,
        "max_arm_rad": float(np.max(np.abs(s["J1/qout"]))),
        # the arm mode under the swing-up loop, before the voltage first saturates
        "f_chatter": fft_peak(t, s["Arm/eta_y[1]"], t_on + 0.5, float(t[sat[0]]), 40.0, 400.0),
    }


def compare(ta, a, tb_, b, t0, t1) -> float:
    grid = np.union1d(ta[(ta >= t0) & (ta <= t1)], tb_[(tb_ >= t0) & (tb_ <= t1)])
    return float(np.max(np.abs(np.interp(grid, ta, a) - np.interp(grid, tb_, b))))


def main(argv: list[str]) -> None:
    dz = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    fz = json.loads((HERE / "flex_design.json").read_text(encoding="utf-8"))
    runs = HERE / "_runs"
    if "--docs" in argv:
        import flex_docs

        flex_docs.write(EXAMPLE_DIR, dz, fz)
        return
    labels = [a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")]
    labels = labels[0] if labels else list(RUNS)
    if "--no-run" not in argv:
        stats = run_all(fz, labels, runs)
        old = json.loads((HERE / "_flex_run_stats.json").read_text(encoding="utf-8")) if (HERE / "_flex_run_stats.json").is_file() else {}
        old.update(stats)
        (HERE / "_flex_run_stats.json").write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8", newline="\n")
    load = lambda label: runner.load(runs / f"{label}.npz")  # noqa: E731
    t_l, s_l = load(LOWPASS)
    t_f, s_f = load(FLEX)
    t_tap, s_tap = load("flex-tap")
    t_fs, s_fs = load("flex-free-stiff")
    t_rf, s_rf = load(f"{NAME}-free")
    m_lp = measure_lowpass(dz, t_l, s_l)
    m_fail = measure_failure(dz, t_f, s_f)
    freq = fz["freq"]
    f_tap_y = fft_peak(t_tap, s_tap["Arm/eta_y[1]"], T_TAP + 0.01, 1.0, 20.0, 80.0)
    f_tap_z = fft_peak(t_tap, s_tap["Arm/eta_z[1]"], 0.0, 1.0, 60.0, 200.0)
    stiff = {k: compare(t_fs, s_fs[k], t_rf, s_rf[k], 0.0, 1.0) for k in ("J1/qout", "Angles/phi1", "Angles/phi2", "Angles/phi3")}
    stiff2 = {k: compare(t_fs, s_fs[k], t_rf, s_rf[k], 0.0, 2.0) for k in ("J1/qout", "Angles/phi1", "Angles/phi2", "Angles/phi3")}
    meas = {"lowpass": m_lp, "rigid_ctrl": m_fail, "tap": {"f_y": f_tap_y, "f_z": f_tap_z},
            "stiff_1s": stiff, "stiff_2s": stiff2}
    print(json.dumps(meas, indent=2))
    (HERE / "flex_measured.json").write_text(json.dumps(meas, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_expected(dz, fz, meas)


def write_expected(dz: dict, fz: dict, meas: dict) -> None:
    path = EXAMPLE_DIR / "expected.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    m, mf, freq = meas["lowpass"], meas["rigid_ctrl"], fz["freq"]
    t_on, t_s, t_dist, t_end = dz["t_on"], dz["t_s"], dz["t_dist"], dz["t_end"]
    t_catch = t_on + t_s
    band = max(1.0, 2.0 * m["band_pre_deg"])
    t_rec = min(t_dist + 1.25 * m["t_recover"] + 0.3, t_end - 0.5)
    energy = {"kind": "energy_ledger", "tol": 1e-6,
              "note": "power continuity of the whole graph, the flexible arm's modal bond graph included (Tellegen residual)"}
    models = doc["models"]
    models[LOWPASS] = {"run_timeout": 1800.0, "checks": [
        {"kind": "scene_bindings"},
        {"kind": "no_diagnostics", "codes": CODES, "note": "no derivative-causality warning, no event-loop warning, no solver failure"},
        energy,
        {"kind": "cursor_value", "signal": "Ctrl/phase", "t": t_catch + 1.0, "value": 2.0, "abs": 1e-9,
         "note": "the low-pass firmware catches: the balance controller has taken over one second after t_on + T_s"},
        {"kind": "max_abs_le", "signal": "Angles/dev", "from_t": t_catch + 1.5, "to_t": t_dist - 0.01, "value": math.radians(band),
         "note": f"upright on the flexible arm: all links inside {band:.1f} deg between catch + 1.5 s and the disturbance (measured {m['band_pre_deg']:.3f} deg)"},
        {"kind": "max_abs", "signal": "Angles/phi3", "from_t": t_dist, "to_t": t_dist + 2.0, "value": math.radians(m["peak_defl_deg"]), "rtol": 0.3,
         "note": f"the disturbance is real: the tip link deflects by {m['peak_defl_deg']:.1f} deg (rigid arm and firmware: 3.5 deg); band +-30 %"},
        {"kind": "max_abs_le", "signal": "Angles/dev", "from_t": t_rec, "to_t": t_end, "value": math.radians(band),
         "note": f"recovered: inside {band:.1f} deg from {t_rec:.2f} s (measured: inside 0.5 deg {m['t_recover']:.2f} s after the pulse)"},
        {"kind": "max_abs_le", "signal": "Ctrl/u", "value": dz["vmax"] + 1e-9,
         "note": f"the voltage stays inside the +-{dz['vmax']:g} V limit (measured peak {m['peak_v']:.2f} V)"},
        {"kind": "max_abs_le", "signal": "Arm/dB[2]", "from_t": t_catch + 1.5, "to_t": t_dist - 0.01, "value": max(1e-4, 3 * m["tip_y_balance_mm"] * 1e-3),
         "note": f"while balancing, the arm tip deflects by at most {m['tip_y_balance_mm'] * 1e3:.1f} um sideways (bound 3x, at least 0.1 mm): the arm mode is not excited"},
        {"kind": "max_abs", "signal": "Arm/dB[2]", "from_t": t_on, "to_t": t_catch, "value": m["tip_y_swing_mm"] * 1e-3, "rtol": 0.3,
         "note": f"the swing-up bends the arm: largest sideways tip deflection {m['tip_y_swing_mm']:.2f} mm (+-30 %)"},
    ]}
    models[FLEX] = {"run_timeout": 1800.0, "checks": [
        {"kind": "scene_bindings"},
        {"kind": "no_diagnostics", "codes": ["W201", "E901"], "note": "no derivative-causality warning, no solver failure"},
        energy,
        {"kind": "max_abs_le", "signal": "Ctrl/phase", "value": 1.0 + 1e-9,
         "note": "the rigid firmware never catches on the flexible arm: the balance phase (2) is never reached"},
        {"kind": "max_abs", "signal": "Ctrl/u", "from_t": t_on, "to_t": t_catch, "value": dz["vmax"], "rtol": 1e-6,
         "note": f"the loop saturates the amplifier during the swing-up (first at {mf['t_first_saturation']:.2f} s): the arm mode grows until the 15 V limit caps it"},
        {"kind": "fft_peak", "signal": "Arm/eta_y[1]", "from_t": t_on + 0.5, "to_t": round(mf["t_first_saturation"] - 0.02, 2), "min_hz": 40.0, "max_hz": 400.0,
         "value": mf["f_chatter"], "rtol": 0.1,
         "note": (f"the arm's first bending mode rings under the swing-up loop at {mf['f_chatter']:.1f} Hz before the voltage first saturates "
                  f"(the flexible design model of flex_design.py follows the bond graph to a few um up to there); at the upright the linear analysis "
                  f"puts the closed-loop arm pole at {abs(fz['rigid_on_flex_poles'][0][1]) / 2 / math.pi:.1f} Hz, growing at {fz['rigid_on_flex_poles'][0][0]:.0f} 1/s")},
        {"kind": "max_abs", "signal": "Arm/dB[2]", "value": mf["max_tip_y_mm"] * 1e-3, "rtol": 0.3,
         "note": f"the unstable loop shakes the arm: sideways tip deflection up to {mf['max_tip_y_mm']:.2f} mm (+-30 %; the low-pass firmware: {meas['lowpass']['tip_y_swing_mm']:.2f} mm)"},
        {"kind": "min_ge", "signal": "Angles/dev", "from_t": t_end - 1.0, "to_t": t_end, "value": math.radians(30.0),
         "note": f"the chain is not upright at the end (it falls at {mf['t_fall']:.2f} s)"},
    ]}
    models[FREE] = {"run_timeout": 1800.0, "checks": [
        {"kind": "scene_bindings"},
        {"kind": "no_diagnostics", "codes": CODES},
        energy,
    ]}
    models["flex-tap"] = {"model": FREE, "run_timeout": 900.0,
                          "settings": {"t_end": 1.0, "output": {"points": 20001}},
                          "overrides": tap_overrides(fz),
                          "checks": [
        {"kind": "energy_ledger", "tol": 1e-6, "note": "power continuity in the tap test"},
        {"kind": "fft_peak", "signal": "Arm/eta_y[1]", "from_t": T_TAP + 0.01, "to_t": 1.0, "min_hz": 20.0, "max_hz": 80.0,
         "value": freq["exact_h"], "rtol": 0.01,
         "note": (f"first horizontal arm mode, hub clamped (rotor inertia 1e3 kg m^2 at the motor), chain hanging on its free hinge: "
                  f"the exact Euler-Bernoulli frequency equation with the hinged chain as a frequency-dependent tip mass gives "
                  f"{freq['exact_h']:.2f} Hz (Rayleigh with the chain's high-frequency mass {freq['chain_m_inf'] * 1e3:.1f} g: {freq['rayleigh_h']:.2f} Hz; "
                  f"the whole {freq['chain_mass']:.3f} kg as a rigid tip mass would give {freq['exact_h_lumped']:.1f} Hz); measured {meas['tap']['f_y']:.2f} Hz")},
        {"kind": "fft_peak", "signal": "Arm/eta_z[1]", "from_t": 0.0, "to_t": 1.0, "min_hz": 60.0, "max_hz": 200.0,
         "value": freq["am_v"], "rtol": 0.01,
         "note": (f"first vertical arm mode (the arm starts without its gravity sag and rings): the pendulum assembly is a rigid tip mass "
                  f"{freq['chain_mass']:.3f} kg with {freq['chain_j_perp']:.4f} kg m^2 about the tip. Two assumed modes give {freq['am_v']:.2f} Hz; "
                  f"the exact frequency equation {freq['exact_v']:.2f} Hz: the large tip inertia needs more modes (three: 118.4 Hz). Measured {meas['tap']['f_z']:.2f} Hz")},
    ]}
    worst = max(meas["stiff_1s"].values())
    models["flex-free-stiff"] = {"model": FREE, "run_timeout": 1800.0, "overrides": {"Arm/E": fz["arm"]["E"] * STIFF},
                                 "checks": [{"kind": "energy_ledger", "tol": 1e-6}]}
    tol = max(2e-4, 3.0 * worst)
    compare_list = [c for c in doc.get("compare", []) if c.get("a") != "flex-free-stiff"] if isinstance(doc.get("compare"), list) else []
    for sig in ("J1/qout", "Angles/phi1", "Angles/phi2", "Angles/phi3"):
        compare_list.append({"a": "flex-free-stiff", "b": f"{NAME}-free", "signal_a": sig, "signal_b": sig, "from_t": 0.0, "to_t": 1.0,
                             "max_abs": tol,
                             "note": (f"stiff limit: the flexible arm with E x {STIFF:g} swings like the rigid arm (same mass and inertia) over the "
                                      f"first second of the chaotic free swing (measured {meas['stiff_1s'][sig]:.2g} rad; bound 3x, at least 0.2 mrad)")})
    doc["compare"] = compare_list
    doc["description"] = dz["comment"] + (
        " Flexible-arm models (flex_design.py, flex_build.py, flex_finish.py): the arm as a FlexibleBeam3D, a 3 x 50 mm stainless strip on edge; "
        "-flex runs the rigid firmware (it fails: the arm's first bending mode goes unstable), -flex-lowpass the firmware with a 12 Hz low-pass "
        "in the loop (it catches), -flex-free the free swing; flex-tap and flex-free-stiff are parameter-override runs of -flex-free.")
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
