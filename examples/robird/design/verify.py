"""Verification run of the Robird example: the full closed-loop flapping model on the real worker.

Runs `models/robird.bgmodel.json` and `models/robird-trim.bgmodel.json` as committed, measures the acceptance metrics
(cross-track error, altitude band, figure extents, actuator ranges, flapping frequency, power), saves them to
`design/results.json`, renders the result figures of the docs (`models/robird.docs/assets/<12 hex>.png`) and, with
`--expected`, writes `expected.json` from the measurements with justified tolerances.

    uv run examples/robird/design/design.py verify [--expected]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402
import params as P  # noqa: E402
import sim  # noqa: E402

ASSETS = ROOT / "models" / "robird.docs" / "assets"
RESULTS = HERE / "results.json"
NPZ = HERE / "_runs" / "robird.npz"

KEYS = [
    "Truth/x", "Truth/y", "Truth/z", "Truth/q[1]", "Fctl/speed", "Fctl/theta", "Fctl/theta_cmd", "Fctl/phi", "Fctl/phi_cmd", "Fctl/psi",
    "Guide/e_ct", "Guide/e_z", "Guide/s_prog", "Guide/x_ref", "Guide/y_ref", "Guide/z_ref", "Fctl/f_cmd", "Fctl/de", "Fctl/da", "Fctl/dr",
    "Drv/source/u", "Drv/isense/y", "Drv/wsense/y", "FlapCtl/w_cmd", "JTL/qout", "JTR/qout", "JTV/qout", "JL1/qout", "JR1/qout", "JL2/qout",
    "JL1/dang[1]", "JL2/dang[1]", "PaSum/Pavg", "PaSum/P", "Meas/rms_ct", "Meas/rms_z", "Meas/x_max", "Meas/x_min", "Meas/y_max", "Meas/y_min",
    "Meas/nx", "Meas/ny", "AeroL1/alpha1", "AeroL2/alphaN", "Truth/wb[1]", "Truth/wb[2]", "Truth/wb[3]", "Truth/tilt", "Truth/qerr", "Truth/vw[1]",
]


def _fft_peak(t, x, lo=2.0, hi=6.0):
    fs = 100.0
    g = np.arange(t[0], t[-1], 1 / fs)
    y = np.interp(g, t, x)
    y = y - np.polyval(np.polyfit(g, y, 1), g)
    w = np.hanning(len(y))
    n = 1 << 16
    sp = np.abs(np.fft.rfft(y * w, n))
    fr = np.fft.rfftfreq(n, 1 / fs)
    k = np.where((fr >= lo) & (fr <= hi))[0]
    return float(fr[k[np.argmax(sp[k])]])


def measure(r) -> dict:
    t, S = r.time, r.signals
    m = t >= d.SIZE["t_stat"]
    e, ez = S["Guide/e_ct"][m], S["Guide/e_z"][m]
    z = S["Truth/z"][m]
    flap = S["JL1/qout"][m]
    tt = t[m]
    # flapping frequency from the zero crossings of the flap angle about its mean (collapsed event rows)
    keep = np.concatenate([[True], np.diff(tt) > 0])
    t1, f1 = tt[keep], flap[keep]
    mid = np.convolve(f1, np.ones(41) / 41, mode="same")
    up = np.where((f1[:-1] - mid[:-1] < 0) & (f1[1:] - mid[1:] >= 0))[0]
    up = up[(up > 25) & (up < len(t1) - 25)]
    per = np.diff(t1[up])
    u, i_m = S["Drv/source/u"][m], S["Drv/isense/y"][m]
    out = dict(
        cross_rms=float(np.sqrt(np.mean(e**2))), cross_max=float(np.abs(e).max()),
        alt_rms=float(np.sqrt(np.mean(ez**2))), alt_err_max=float(np.abs(ez).max()),
        z_min=float(z.min()), z_max=float(z.max()),
        x_max=float(S["Meas/x_max"][-1]), x_min=float(S["Meas/x_min"][-1]), y_max=float(S["Meas/y_max"][-1]), y_min=float(S["Meas/y_min"][-1]),
        nx=float(S["Meas/nx"][-1]), ny=float(S["Meas/ny"][-1]),
        speed_min=float(S["Fctl/speed"][m].min()), speed_max=float(S["Fctl/speed"][m].max()), speed_mean=float(S["Fctl/speed"][m].mean()),
        phi_max=float(np.abs(S["Fctl/phi"][m]).max()), theta_min=float(S["Fctl/theta"][m].min()), theta_max=float(S["Fctl/theta"][m].max()),
        f_min=float(S["Fctl/f_cmd"][m].min()), f_max=float(S["Fctl/f_cmd"][m].max()), f_mean=float(S["Fctl/f_cmd"][m].mean()),
        flap_period_mean=float(per.mean()) if per.size else float("nan"), flap_freq_mean=float(1 / per.mean()) if per.size else float("nan"),
        flap_amp=float(0.5 * (flap.max() - flap.min())),
        tail_max=float(max(np.abs(S[k][m]).max() for k in ("JTL/qout", "JTR/qout"))), rudder_max=float(np.abs(S["JTV/qout"][m]).max()),
        de_min=float(S["Fctl/de"][m].min()), de_max=float(S["Fctl/de"][m].max()), da_max=float(np.abs(S["Fctl/da"][m]).max()),
        u_max=float(u.max()), i_max=float(i_m.max()), i_mean=float(i_m.mean()), p_el_mean=float(np.mean(u * i_m)),
        p_air_mean=float(S["PaSum/P"][m].mean()),
        tors_max=float(np.abs(S["JL1/dang[1]"][m]).max()), bend_max=float(np.abs(S["JL2/qout"][m]).max()),
        qerr_max=float(np.abs(S["Truth/qerr"]).max()),
        v0x=float(S["Truth/vw[1]"][0]), w_track_rms=float(np.sqrt(np.mean((S["Drv/wsense/y"][t >= 3.0] - S["FlapCtl/w_cmd"][t >= 3.0]) ** 2))),
        fft_flap=_fft_peak(t1, f1),
        rows=int(t.size), wall=float(getattr(r, "wall", float("nan"))),
    )
    return out


def figures(r, tab: dict, res: dict) -> dict[str, Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "figure.dpi": 130, "savefig.dpi": 130, "axes.titlesize": 10.5, "axes.titleweight": "semibold"})
    c1, c2, c3, c4 = "#2a6fb0", "#d9731a", "#3a8f5c", "#7a4fa3"
    keep = r.time > 0.03      # the first samples hold the initial values of the discrete blocks
    t = r.time[keep]
    S = {k: v[keep] for k, v in r.signals.items()}
    stat = d.SIZE["t_stat"]
    files: dict[str, Path] = {}
    ASSETS.mkdir(parents=True, exist_ok=True)
    for old in ASSETS.glob("*.png"):
        old.unlink()

    def save(fig, name):
        tmp = HERE / "_runs" / f"{name}.png"
        tmp.parent.mkdir(exist_ok=True)
        fig.savefig(tmp, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        h = hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]
        dest = ASSETS / f"{h}.png"
        dest.write_bytes(tmp.read_bytes())
        files[name] = dest

    # 1 top view
    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.5, 1]})
    a = ax[0]
    ref = tab["lap"]
    lap_mask = tab["s"] <= tab["lap"]
    a.plot(tab["x"][lap_mask], tab["y"][lap_mask], color="#999999", lw=3.5, alpha=0.6, label="Lissajous reference")
    a.plot(S["Truth/x"], S["Truth/y"], color=c1, lw=1.4, label="flown path")
    a.plot(S["Truth/x"][0], S["Truth/y"][0], "o", color=c3, ms=7, label="start")
    a.set_aspect("equal")
    a.set_xlabel("x (m)"), a.set_ylabel("y (m)")
    a.set_title("Top view: the flown figure of eight against the Lissajous reference")
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, fontsize=8, frameon=False)
    b = ax[1]
    b.plot(t, S["Guide/e_ct"], color=c1, lw=1.1, label="cross-track error (m)")
    b.plot(t, S["Guide/e_z"], color=c2, lw=1.1, label="altitude error (m)")
    b.axvline(stat, color="#777", lw=0.8, ls="--")
    b.text(stat + 0.5, b.get_ylim()[1] * 0.85, "statistics start", fontsize=7.5, color="#555")
    b.set_xlabel("t (s)"), b.set_ylabel("error (m)")
    b.set_title("Tracking error")
    b.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    save(fig, "path")

    # 2 altitude / speed / bank
    fig, ax = plt.subplots(3, 1, figsize=(8.5, 6.2), sharex=True)
    ax[0].plot(t, S["Truth/z"], color=c1, lw=1.3, label="altitude")
    ax[0].plot(t, S["Guide/z_ref"], color="#888", lw=1.0, ls="--", label="reference z0 + Cz sin(th)")
    ax[0].set_ylabel("z (m)"), ax[0].legend(fontsize=8, frameon=False, ncol=2)
    ax[0].set_title("Altitude, speed and bank angle along the figure")
    ax[1].plot(t, S["Fctl/speed"], color=c3, lw=1.2)
    ax[1].axhline(d.SIZE["U"], color="#888", lw=0.8, ls="--")
    ax[1].set_ylabel("speed (m/s)")
    ax[2].plot(t, np.degrees(S["Fctl/phi"]), color=c4, lw=1.2, label="roll angle")
    ax[2].plot(t, np.degrees(S["Fctl/phi_cmd"]), color="#888", lw=1.0, ls="--", label="command")
    ax[2].set_ylabel("roll (deg)"), ax[2].set_xlabel("t (s)"), ax[2].legend(fontsize=8, frameon=False, ncol=2)
    fig.tight_layout()
    save(fig, "altitude")

    # 3 flapping
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 5.2))
    t0 = 20.0
    mm = (t >= t0) & (t <= t0 + 1.5)
    ax[0].plot(t[mm], S["JL1/qout"][mm], color=c1, lw=1.5, label="left wing flap angle")
    ax[0].plot(t[mm], S["JR1/qout"][mm], color=c2, lw=1.0, ls="--", label="right wing flap angle")
    ax[0].plot(t[mm], S["JL2/qout"][mm], color=c3, lw=1.1, label="left outer-segment bend")
    ax[0].plot(t[mm], S["JL1/dang[1]"][mm], color=c4, lw=1.1, label="left root torsion (aeroelastic pitch)")
    ax[0].set_ylabel("angle (rad)"), ax[0].set_xlabel("t (s)")
    ax[0].set_title("Flapping, 1.5 s of the run: stroke, aeroelastic bending and twist")
    ax[0].legend(fontsize=8, frameon=False, ncol=2)
    ax[1].plot(t, S["Fctl/f_cmd"], color=c1, lw=1.0, label="commanded flapping frequency (Hz)")
    ax[1].plot(t, S["Drv/wsense/y"] / (2 * np.pi * P.N_GEAR), color=c2, lw=1.0, ls="--", label="motor speed / (2 pi N) (Hz)")
    ax[1].set_ylabel("Hz"), ax[1].set_xlabel("t (s)")
    ax[1].legend(fontsize=8, frameon=False, ncol=2)
    ax[1].set_title("Flapping frequency over the run")
    fig.tight_layout()
    save(fig, "flapping")

    # 4 tail and drive
    fig, ax = plt.subplots(3, 1, figsize=(8.5, 6.6), sharex=True)
    ax[0].plot(t, S["JTL/qout"], color=c1, lw=1.1, label="left elevon")
    ax[0].plot(t, S["JTR/qout"], color=c2, lw=1.1, label="right elevon")
    ax[0].plot(t, S["JTV/qout"], color=c3, lw=1.1, label="rudder")
    ax[0].axhline(P.FLAP_LIM, color="#c33", lw=0.7, ls=":"), ax[0].axhline(-P.FLAP_LIM, color="#c33", lw=0.7, ls=":")
    ax[0].set_ylabel("deflection (rad)"), ax[0].legend(fontsize=8, frameon=False, ncol=3)
    ax[0].set_title("Tail deflections (dotted: usable range) and the flapping drive")
    ax[1].plot(t, S["Drv/source/u"], color=c1, lw=0.9, label="motor voltage (V)")
    ax[1].plot(t, S["Drv/isense/y"], color=c2, lw=0.9, label="motor current (A)")
    ax[1].set_ylabel("V, A"), ax[1].legend(fontsize=8, frameon=False, ncol=2)
    ax[2].plot(t, S["PaSum/Pavg"], color=c3, lw=1.3, label="average aerodynamic power (W, 1 s low-pass)")
    ax[2].set_ylabel("W"), ax[2].set_xlabel("t (s)"), ax[2].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    save(fig, "tail_drive")
    return files


def main() -> None:
    expected = "--expected" in sys.argv
    model = json.loads((ROOT / "models" / "robird.bgmodel.json").read_text(encoding="utf-8"))
    trim_model = json.loads((ROOT / "models" / "robird-trim.bgmodel.json").read_text(encoding="utf-8"))
    NPZ.parent.mkdir(exist_ok=True)
    s = sim.Sim()
    try:
        r = s.run(model, timeout=7200)
        print(f"robird: wall {r.wall:.0f} s, {r.time.size} rows, {len(r.signals)} signals", flush=True)
        res = measure(r)
        np.savez_compressed(NPZ, t=r.time, **{k.replace("/", "__"): r.signals[k] for k in KEYS if k in r.signals})
        rt = s.run(trim_model)
        tt, TS = rt.time, rt.signals
        res["trim_wall"] = float(rt.wall)
        res["trim_p_air"] = float(np.mean(TS["PaSum/P"][tt > 0.5]))
        res["trim_flap_amp"] = float(0.5 * (TS["JL1/qout"][tt > 0.5].max() - TS["JL1/qout"][tt > 0.5].min()))
    finally:
        s.close()
    res["sizing"] = d.sizing()
    res["trim"] = d.TRIM
    RESULTS.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items() if not isinstance(v, dict)}, indent=1))
    tab = d.PATH.table(d.SIZE["A"], d.SIZE["B"], d.SIZE["Cz"], d.SIZE["z0"], ds=2.0)
    files = figures(r, tab, res)
    (HERE / "_runs" / "figures.json").write_text(json.dumps({k: v.name for k, v in files.items()}, indent=1))
    print("figures:", {k: v.name for k, v in files.items()})
    if expected:
        import expected_json
        expected_json.write(res)
