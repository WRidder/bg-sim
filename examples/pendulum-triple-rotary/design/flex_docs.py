"""Write the model docs of the flexible-arm models of `pendulum-triple-rotary` from their runs.

Run through `flex_finish.py --docs` (after `flex_finish.py`, which saves the runs in `design/_runs/`
and the measurements in `design/flex_measured.json`). Plots are matplotlib; every asset is named by
the first 12 hex digits of its SHA-256. The 3D screenshots come from `design/_shots/` when present
(`flex-3d-top.png`, `flex-lowpass-3d-top.png`, views from above; see `tools/video/capture-flexarm.mjs`).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import runner  # noqa: E402

import flex_design as fd  # noqa: E402
import flex_lib as fl  # noqa: E402
import triple_lib as tl  # noqa: E402

NAME = "pendulum-triple-rotary"
FLEX, LOWPASS, FREE = f"{NAME}-flex", f"{NAME}-flex-lowpass", f"{NAME}-flex-free"
C = ["#2a7de1", "#d9534f", "#e6a817", "#3a9d5d", "#7a4fc4"]
RIGID_STYLE = {"color": "#888888", "lw": 1.2, "ls": "--"}


def _save(fig, docs: Path, store: dict, key: str) -> str:
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    tmp = docs / "assets" / f"{key}.tmp.png"
    fig.savefig(tmp, dpi=110, bbox_inches="tight")
    plt.close(fig)
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()[:12]
    final = docs / "assets" / f"{digest}.png"
    tmp.replace(final)
    store[key] = f"assets/{digest}.png"
    return store[key]


def _copy_shot(path: Path, docs: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    (docs / "assets" / f"{digest}.png").write_bytes(path.read_bytes())
    return f"assets/{digest}.png"


def _clean(docs: Path) -> None:
    (docs / "pages").mkdir(parents=True, exist_ok=True)
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    for old in list((docs / "assets").glob("*")) + list((docs / "pages").glob("*.md")):
        old.unlink()


def loop_gain(dz: dict, fz: dict):
    """|L(e^{j w T})| of the sampled loop at the upright (1 kHz, zero-order hold), broken at the motor
    voltage: the rigid firmware on the rigid and on the flexible plant, and the low-pass firmware on
    the flexible plant."""
    rp = tl.Plant(dz["lengths"], dz["masses"], tl.Drive(**dz["drive"]), jfric=dz["jfric"])
    k = np.array(dz["k_lqr"]).reshape(1, -1)
    f = np.logspace(0, np.log10(400), 500)
    zs = np.exp(2j * np.pi * f * fd.TS)
    a, b = (np.array(m) for m in rp.lin_fn(np.zeros(rp.nx), 0.0))
    ar, br = fl.discretise(a, b, fd.TS)
    fp = fl.FlexPlant(rp, fd.beam(2, 0, 0))
    af, bfl, _ = fp.linear()
    ad, bd = fl.discretise(af, bfl, fd.TS)
    c = fp.measured()
    k10 = np.array(fz["lp"]["k_lqr"])
    fa, fb, fcm = fd.lowpass(fz["lp"]["fc"], fz["lp"]["zeta"])
    kx = k10[:8].reshape(1, -1) @ c
    kf = k10[8:].reshape(1, -1)
    lr, lf, lp = [], [], []
    for z in zs:
        lr.append((k @ np.linalg.solve(z * np.eye(ar.shape[0]) - ar, br))[0, 0])
        xr = np.linalg.solve(z * np.eye(ad.shape[0]) - ad, bd)
        lf.append((k @ c @ xr)[0, 0])
        filt = fcm @ np.linalg.solve(z * np.eye(2) - fa + fb @ kf, fb)
        lp.append((filt @ kx @ xr)[0, 0])
    return f, np.array(lr), np.array(lf), np.array(lp)


def frozen(dz: dict, fz: dict):
    """Frozen-time poles along the swing-up: the flexible plant linearised at the nominal state of every
    table row (arm at rest), closed with that row's gains. The fastest-growing pole above 20 Hz, for the
    rigid firmware and the low-pass one."""
    rp = tl.Plant(dz["lengths"], dz["masses"], tl.Drive(**dz["drive"]), jfric=dz["jfric"])
    fp = fl.FlexPlant(rp, fd.beam(2, 0, 0))
    c = fp.measured()
    tab_x, tab_u, tab_k = np.array(dz["tab_x"]), np.array(dz["tab_u"]), np.array(dz["tab_k"])
    tab_k10 = np.array(fz["lp"]["tab_k"])
    fa, fb, fcm = fd.lowpass(fz["lp"]["fc"], fz["lp"]["zeta"])
    ts, rig, low = [], [], []
    for i in range(0, len(tab_k), 5):
        x = np.zeros(fp.nx)
        x[: fp.nr] = tab_x[i][: fp.nr]
        x[fp.nq: fp.nq + fp.nr] = tab_x[i][fp.nr:]
        a, b = (np.array(m) for m in fp.lin_fn(x, float(tab_u[i])))
        ad, bd = fl.discretise(a, b, fd.TS)
        p = np.log(np.linalg.eigvals(ad - bd @ (tab_k[i].reshape(1, -1) @ c)).astype(complex)) / fd.TS
        k = tab_k10[i]
        acl = np.block([[ad, bd @ fcm], [-fb @ (k[:8].reshape(1, -1) @ c), fa - fb @ k[8:].reshape(1, -1)]])
        p2 = np.log(np.linalg.eigvals(acl).astype(complex)) / fd.TS
        ts.append(dz["t_on"] + i * dz["dt_tab"])
        rig.append(float(np.max(p.real)))
        low.append(float(np.max(p2.real)))
    return np.array(ts), np.array(rig), np.array(low)


def design_run(dz: dict, t_end: float):
    """The rigid firmware on the flexible design model (flex_design.py), to t_end."""
    rp = tl.Plant(dz["lengths"], dz["masses"], tl.Drive(**dz["drive"]), jfric=dz["jfric"])
    fw = tl.Firmware(t_on=dz["t_on"], t_s=dz["t_s"], dt_tab=dz["dt_tab"], tab_x=np.array(dz["tab_x"]), tab_u=np.array(dz["tab_u"]),
                     tab_k=np.array(dz["tab_k"]), k_lqr=np.array(dz["k_lqr"]), p_catch=np.array(dz["p_lqr"]),
                     catch_tol=dz["catch_tol"], vmax=dz["vmax"])
    fp = fl.FlexPlant(rp, fd.beam(2, 0, 0))
    ts, xs, us, _, _ = fd.rigid_firmware_run(fw, fp.steps(fd.TS, 4), fp.hanging(), t_end)
    return ts, xs, us


def plots(dz: dict, fz: dict, meas: dict, runs: Path, docs: Path) -> dict:
    img: dict[str, str] = {}
    tr, sr = runner.load(runs / f"{NAME}.npz")
    tf, sf = runner.load(runs / f"{FLEX}.npz")
    tl_, sl = runner.load(runs / f"{LOWPASS}.npz")
    t_on, t_dist = dz["t_on"], dz["t_dist"]

    # 1. the rigid firmware on the flexible arm
    fig, ax = plt.subplots(4, 1, sharex=True, figsize=(9, 9))
    for k in range(3):
        ax[0].plot(tf, np.degrees(sf[f"Angles/phi{k + 1}"]), color=C[k], label=f"link {k + 1}, flexible arm")
    ax[0].plot(tr, np.degrees(sr["Angles/phi3"]), label="link 3, rigid arm", **RIGID_STYLE)
    ax[0].set_ylabel("link angle from upright [deg]")
    ax[0].set_ylim(-400, 400)
    ax[0].legend(loc="upper right", fontsize=8, ncol=2)
    ax[1].plot(tf, sf["Ctrl/u"], color=C[1], lw=0.6, label="flexible arm")
    ax[1].plot(tr, sr["Ctrl/u"], label="rigid arm", **RIGID_STYLE)
    ax[1].set_ylabel("motor voltage [V]")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[2].plot(tf, 1e3 * sf["Arm/dB[2]"], color=C[0], lw=0.6, label="horizontal (dB[2])")
    ax[2].plot(tf, 1e3 * sf["Arm/dB[3]"], color=C[3], lw=0.8, label="vertical (dB[3])")
    ax[2].axhline(0.0, label="rigid arm", **RIGID_STYLE)
    ax[2].set_ylabel("arm tip deflection [mm]")
    ax[2].legend(loc="upper right", fontsize=8)
    ax[3].plot(tf, 1e3 * sf["Arm/eta_y[1]"], color=C[0], lw=0.6, label="eta_y[1]")
    ax[3].plot(tf, 1e3 * sf["Arm/eta_y[2]"], color=C[2], lw=0.6, label="eta_y[2]")
    ax[3].plot(tf, 1e3 * sf["Arm/eta_z[1]"], color=C[3], lw=0.8, label="eta_z[1]")
    ax[3].set_ylabel("modal coordinate [mm]")
    ax[3].set_xlabel("t [s]")
    ax[3].legend(loc="upper right", fontsize=8, ncol=3)
    fig.suptitle("Rigid firmware on the flexible arm (pendulum-triple-rotary-flex) against the rigid arm")
    _save(fig, docs, img, "failure")

    # 1b. the onset: bond graph against the flexible design model, and the frozen-time growth rate
    ts = meas["rigid_ctrl"]["t_first_saturation"]
    a, b = t_on, ts + 0.4
    td, xd, ud = design_run(dz, b)
    m = (tf >= a) & (tf <= b)
    md = (td >= a) & (td <= b)
    fig, ax = plt.subplots(3, 1, sharex=True, figsize=(9, 8))
    ax[0].plot(tf[m], 1e3 * sf["Arm/eta_y[1]"][m], color=C[0], lw=1.0, label="bond graph")
    ax[0].plot(td[md], 1e3 * xd[md, 4], color="k", lw=0.7, ls="--", label="flexible design model (flex_lib)")
    ax[0].set_ylabel("eta_y[1] [mm]")
    ax[0].legend(loc="lower left", fontsize=8)
    ax[1].plot(tf[m], sf["Ctrl/u"][m], color=C[1], lw=1.0, label="flexible arm")
    ax[1].plot(td[md], ud[md], color="k", lw=0.7, ls="--")
    mr = (tr >= a) & (tr <= b)
    ax[1].plot(tr[mr], sr["Ctrl/u"][mr], label="rigid arm", **RIGID_STYLE)
    ax[1].set_ylabel("motor voltage [V]")
    ax[1].legend(loc="lower left", fontsize=8)
    tfz, rig, low = frozen(dz, fz)
    keep = tfz <= b
    ax[2].plot(tfz[keep], rig[keep], color=C[1], label="rigid firmware")
    ax[2].plot(tfz[keep], low[keep], color=C[0], label="low-pass firmware")
    ax[2].axhline(0.0, color="k", lw=0.6)
    ax[2].set_ylabel("largest real part [1/s]")
    ax[2].set_xlabel("t [s]")
    ax[2].legend(loc="upper left", fontsize=8)
    for k in range(3):
        ax[k].axvline(ts, color="k", lw=0.6, ls=":")
    fig.suptitle("Onset: the swing-up rings the arm mode; when the TVLQR gains grow near the top, the loop goes unstable")
    _save(fig, docs, img, "onset")
    # the arm mode, not the slow pendulum poles of the frozen (off-equilibrium) linearisation
    img["_frozen_unstable_t"] = float(tfz[np.argmax(rig > 20.0)]) if np.any(rig > 20.0) else math.nan
    img["_design_diff"] = float(np.max(np.abs(np.interp(td[md & (td < ts - 0.05)], tf, sf["Arm/eta_y[1]"]) - xd[md & (td < ts - 0.05), 4])))

    # 2. the fix
    fig, ax = plt.subplots(4, 1, sharex=True, figsize=(9, 9))
    for k in range(3):
        ax[0].plot(tl_, np.degrees(sl[f"Angles/phi{k + 1}"]), color=C[k], label=f"link {k + 1}, flexible arm, low-pass firmware")
    ax[0].plot(tr, np.degrees(sr["Angles/phi3"]), label="link 3, rigid arm and firmware", **RIGID_STYLE)
    ax[0].set_ylabel("link angle from upright [deg]")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[1].plot(tl_, sl["Ctrl/u"], color=C[1], label="flexible arm, low-pass firmware")
    ax[1].plot(tr, sr["Ctrl/u"], label="rigid arm and firmware", **RIGID_STYLE)
    ax[1].set_ylabel("motor voltage [V]")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[2].plot(tl_, 1e3 * sl["Arm/dB[2]"], color=C[0], label="horizontal (dB[2])")
    ax[2].plot(tl_, 1e3 * sl["Arm/dB[3]"], color=C[3], label="vertical (dB[3])")
    ax[2].axhline(0.0, label="rigid arm", **RIGID_STYLE)
    ax[2].set_ylabel("arm tip deflection [mm]")
    ax[2].legend(loc="upper right", fontsize=8)
    ax[3].plot(tl_, 1e3 * sl["Arm/eta_y[1]"], color=C[0], label="eta_y[1]")
    ax[3].plot(tl_, 1e3 * sl["Arm/eta_y[2]"], color=C[2], label="eta_y[2]")
    ax[3].plot(tl_, 1e3 * sl["Arm/eta_z[1]"], color=C[3], label="eta_z[1]")
    ax[3].plot(tl_, 1e3 * sl["Arm/eta_t[1]"], color=C[4], label="eta_t[1] [mrad]")
    ax[3].set_ylabel("modal coordinate [mm, mrad]")
    ax[3].set_xlabel("t [s]")
    ax[3].legend(loc="upper right", fontsize=8, ncol=4)
    fig.suptitle("Low-pass firmware on the flexible arm (pendulum-triple-rotary-flex-lowpass) against the rigid arm")
    _save(fig, docs, img, "fix")

    # 2b. the disturbance, zoomed
    a, b = t_dist - 0.2, t_dist + 2.5
    m = (tl_ >= a) & (tl_ <= b)
    mr = (tr >= a) & (tr <= b)
    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9, 5))
    ax[0].plot(tl_[m], np.degrees(sl["Angles/phi3"][m]), color=C[0], label="flexible arm, low-pass firmware")
    ax[0].plot(tr[mr], np.degrees(sr["Angles/phi3"][mr]), label="rigid arm and firmware", **RIGID_STYLE)
    ax[0].set_ylabel("link 3 angle [deg]")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[1].plot(tl_[m], 1e6 * sl["Arm/dB[2]"][m], color=C[0])
    ax[1].set_ylabel("tip deflection, horizontal [µm]")
    ax[1].set_xlabel("t [s]")
    fig.suptitle("The 0.1 N push on the tip link: recovery and arm deflection")
    _save(fig, docs, img, "disturbance")

    # 3. the loop gain
    f, lr, lf, lp = loop_gain(dz, fz)
    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9, 6))
    ax[0].loglog(f, np.abs(lr), label="rigid firmware, rigid arm", **RIGID_STYLE)
    ax[0].loglog(f, np.abs(lf), color=C[1], label="rigid firmware, flexible arm")
    ax[0].loglog(f, np.abs(lp), color=C[0], label="low-pass firmware, flexible arm")
    ax[0].axhline(1.0, color="k", lw=0.6)
    ax[0].set_ylabel("|L(j w)|")
    ax[0].legend(loc="lower left", fontsize=8)
    ax[1].semilogx(f, np.degrees(np.unwrap(np.angle(lr))), **RIGID_STYLE)
    ax[1].semilogx(f, np.degrees(np.unwrap(np.angle(lf))), color=C[1])
    ax[1].semilogx(f, np.degrees(np.unwrap(np.angle(lp))), color=C[0])
    ax[1].set_ylabel("phase [deg]")
    ax[1].set_xlabel("f [Hz]")
    fig.suptitle("Loop gain at the upright (1 kHz sampled loop), broken at the motor voltage")
    _save(fig, docs, img, "loop")
    ipk = int(np.argmax(np.where((f > 30) & (f < 150), np.abs(lf), 0.0)))
    above = np.where(np.abs(lr) > 1.0)[0]
    img["_lr_cross"] = float(f[above[-1]])
    img["_lf_peak"], img["_lf_peak_f"] = float(np.abs(lf[ipk])), float(f[ipk])
    img["_lr_at_peak"], img["_lp_at_peak"] = float(np.abs(lr[ipk])), float(np.abs(lp[ipk]))
    img["_lp_cross"] = float(f[np.where(np.abs(lp) > 1.0)[0][-1]])

    # 4. the tap test
    tt, st = runner.load(runs / "flex-tap.npz")
    fig, ax = plt.subplots(2, 1, figsize=(9, 6))
    ax[0].plot(tt, 1e6 * st["Arm/eta_y[1]"], color=C[0], label="eta_y[1]")
    ax[0].plot(tt, 1e6 * (st["Arm/eta_z[1]"] - np.mean(st["Arm/eta_z[1]"][tt > 0.5])), color=C[3], label="eta_z[1] minus its static sag")
    ax[0].set_ylabel("modal coordinate [um]")
    ax[0].set_xlabel("t [s]")
    ax[0].legend(loc="upper right", fontsize=8)
    for sig, col in (("Arm/eta_y[1]", C[0]), ("Arm/eta_z[1]", C[3])):
        mm = tt > 0.06
        y = st[sig][mm] - np.mean(st[sig][mm])
        dt = float(np.median(np.diff(tt[mm])))
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), 8 * len(y)))
        fr = np.fft.rfftfreq(8 * len(y), dt)
        keep = fr < 200
        ax[1].semilogy(fr[keep], spec[keep] / spec[keep].max(), color=col, label=sig)
    fq = fz["freq"]
    ax[1].axvline(fq["exact_h"], color=C[0], lw=0.8, ls=":", label=f"exact, horizontal {fq['exact_h']:.2f} Hz")
    ax[1].axvline(fq["exact_h_lumped"], color="k", lw=0.8, ls=":", label=f"chain as a rigid tip mass {fq['exact_h_lumped']:.1f} Hz")
    ax[1].axvline(fq["exact_v"], color=C[3], lw=0.8, ls=":", label=f"exact, vertical {fq['exact_v']:.1f} Hz")
    ax[1].set_xlabel("f [Hz]")
    ax[1].set_ylabel("spectrum (normalised)")
    ax[1].legend(loc="upper right", fontsize=7)
    fig.suptitle("Tap test: hub clamped, chain hanging on its free hinge, a 2 ms push on the tip link")
    _save(fig, docs, img, "tap")

    # 5. the stiff limit
    tsf, ssf = runner.load(runs / "flex-free-stiff.npz")
    trf, srf = runner.load(runs / f"{NAME}-free.npz")
    tff, sff = runner.load(runs / f"{FREE}.npz")
    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(9, 6))
    for k in range(3):
        ax[0].plot(trf, np.degrees(srf[f"Angles/phi{k + 1}"]), color=C[k], lw=1.6, label=f"link {k + 1}, rigid arm")
        ax[0].plot(tsf, np.degrees(ssf[f"Angles/phi{k + 1}"]), color="k", lw=0.7, ls="--")
        ax[0].plot(tff, np.degrees(sff[f"Angles/phi{k + 1}"]), color=C[k], lw=0.7, ls=":")
    ax[0].plot([], [], color="k", lw=0.7, ls="--", label="flexible arm, E x 1e4")
    ax[0].plot([], [], color="k", lw=0.7, ls=":", label="flexible arm, steel strip")
    ax[0].set_ylabel("link angle [deg]")
    ax[0].legend(loc="upper right", fontsize=7, ncol=2)
    grid = trf[trf <= 2.0]
    for k, sig in enumerate(("J1/qout", "Angles/phi1", "Angles/phi2", "Angles/phi3")):
        d = np.abs(np.interp(grid, tsf, ssf[sig]) - np.interp(grid, trf, srf[sig]))
        ax[1].semilogy(grid, np.maximum(d, 1e-12), color=C[k], label=sig)
    ax[1].set_ylabel("|stiff flexible - rigid| [rad]")
    ax[1].set_xlabel("t [s]")
    ax[1].legend(loc="lower right", fontsize=8, ncol=2)
    fig.suptitle("Free swing: the flexible arm in the stiff limit against the rigid arm")
    _save(fig, docs, img, "stiff")
    g1 = trf[trf <= 1.0]
    img["_steel_1s"] = max(float(np.max(np.abs(np.interp(g1, tff, sff[s]) - np.interp(g1, trf, srf[s]))))
                           for s in ("J1/qout", "Angles/phi1", "Angles/phi2", "Angles/phi3"))
    return img


def pages(dz: dict, fz: dict, meas: dict, img: dict, shots: dict) -> dict:
    arm, fq, lp = fz["arm"], fz["freq"], fz["lp"]
    mf, ml, tap = meas["rigid_ctrl"], meas["lowpass"], meas["tap"]
    worst = fz["rigid_on_flex_poles"][0]
    rigid_m = dz["metrics"]
    stiff = meas["stiff_1s"]
    shot_flex = f"\n![3D view from above at 4.06 s: the chain is lost and the saturated loop whips the arm (tip deflection 7.5 mm, drawn ×10)|600]({shots['flex']})\n" if shots.get("flex") else ""
    shot_lp = f"\n![3D view from above at 2.95 s, in the swing-up: the low-pass firmware bends the strip by 1.6 mm, drawn ×100 (the hinge follows the true tip)|600]({shots['lowpass']})\n" if shots.get("lowpass") else ""
    ov = f"""# Triple rotary pendulum on a flexible arm

The rig of [pendulum-triple-rotary](page:overview), with one change: the horizontal arm that the motor turns is no longer rigid. It is a [FlexibleBeam3D](block:Arm) (assumed modes, clamped at the motor hub): a **{arm['b'] * 1e3:g} x {arm['h'] * 1e3:g} mm stainless-steel strip on edge**, {arm['L']:g} m long, with the density set so it weighs exactly the rigid arm's {arm['mass']:.3f} kg. The pendulum chain, the servo, the swing-up trajectory and the disturbance are the rigid example's.

| model | arm | firmware | result |
| --- | --- | --- | --- |
| `pendulum-triple-rotary` | rigid | `RotaryCtrl` | catches at 5.0 s, recovers from the push |
| `pendulum-triple-rotary-flex` (this model) | flexible | `RotaryCtrl`, unchanged | **fails**: the loop drives the arm's first bending mode unstable near the top of the swing-up (15 V from {mf['t_first_saturation']:.2f} s); it never catches |
| `pendulum-triple-rotary-flex-lowpass` | flexible | `RotaryCtrlLP`: the same weights, a {lp['fc']:g} Hz low-pass in the loop | catches at {ml['t_catch']:.2f} s, recovers from the push |
| `pendulum-triple-rotary-flex-free` | flexible | off | free swing (energy, tap test, stiff limit) |

![The rigid firmware on the flexible arm, against the rigid arm|700]({img['failure']})
{shot_flex}
## In short

- **The arm.** Bending in the horizontal plane (the plane of the motor torque) is soft: {fq['bare_y'][0]:.1f} Hz as a bare cantilever, **{fq['exact_h']:.1f} Hz** clamped with the pendulum on its hinge, about {fq['free_hub_upright']:.0f} Hz in the running rig (the hub is not clamped). Vertical bending ({fq['exact_v']:.0f} Hz) and torsion ({fq['bare_t'][0]:.0f} Hz) are stiff. See [the arm](page:arm).
- **The rigid controller does not survive it.** Its loop gain has no roll-off: on the rigid arm it is still {img['_lr_at_peak']:.2f} at {img['_lf_peak_f']:.0f} Hz, and the arm's resonance lifts that to {img['_lf_peak']:.1f}. At the upright the closed loop has a pole at {worst[0]:+.0f} 1/s, {abs(worst[1]) / 2 / math.pi:.1f} Hz. A notch or a gentler LQR does not help; the gains would need an arm about {fz['rigid_needs_e_scale']:.0f} times stiffer. See [the controller](page:controller).
- **The fix** is roll-off: the LQR and the TVLQR are designed with a second-order {lp['fc']:g} Hz low-pass between the feedback and the motor. The swing-up nominal is unchanged. It catches, holds and recovers on the flexible arm, for an arm half as stiff up to a rigid one. See [results](page:results).

## What to try

- Open the **3D View**: the strip bends ([Arm/eta_y[1]](signal:Arm/eta_y[1])) and twists ([Arm/eta_t[1]](signal:Arm/eta_t[1])) with the deformation bindings; the view opens with exaggeration ×10. The pendulum hinge follows the computed tip (`Arm/poseB`) at true scale, so with exaggeration the drawn strip end moves away from the hinge.
- Open the **Dashboard**: link angles, tip deflection ([Arm/dB[2]](signal:Arm/dB[2])), modal coordinates and the voltage. Set the arm's Young's modulus to 1.93e13 Pa (100 times the steel) and run again: the rigid firmware now catches and recovers exactly as on the rigid arm. At 5e12 Pa (26 times) it still fails: that is enough for the loop at the upright, but not for the larger gains near the top of the swing-up.
- Run `pendulum-triple-rotary-flex-lowpass`, the fixed controller, and compare.

The pages: [the arm](page:arm), [the controller](page:controller), [results and checks](page:results).
"""
    am = f"""# The flexible arm

## Choice of section

The arm is a [FlexibleBeam3D](block:Arm) with `section` = rectangle: `b` = {arm['b'] * 1e3:g} mm along the arm's local y (horizontal) and `h` = {arm['h'] * 1e3:g} mm along local z (vertical), AISI 304 stainless steel (E = {arm['E'] / 1e9:g} GPa, nu = {arm['nu']:g}). The density {arm['rho']:.0f} kg/m³ (the stainless grades lie at 7900 to 8000) makes the strip weigh {arm['mass']:.4f} kg, the rigid arm's mass, and its rigid inertia about the motor axis is the rigid arm's to 0.1 %. So the flexibility is the only difference, and the stiff limit can be checked against the rigid model.

A flat strip on edge is the classic flexible link (the Quanser rotary flexible link is one): it bends easily in the plane of the motor torque and hardly at all under the pendulum's weight. The bending stiffness is EI = {arm['EI_y']:.1f} N·m² horizontally and {arm['EI_z']:.0f} N·m² vertically; the torsion stiffness GJ = {arm['GJ']:.1f} N·m². Modes: `ny` = {arm['ny']}, `nz` = {arm['nz']}, `nt` = {arm['nt']}, clamped-free, modal damping {arm['zeta']:g}.

The first horizontal mode was put a few times above the controller's fastest closed-loop pole (131 1/s, 21 Hz) and the pendulum's fastest unstable pole (23.7 1/s, 3.8 Hz): a real arm can be that flexible, and a controller designed for a rigid arm may or may not live with it. Here it does not.

## Frequencies

| mode | value |
| --- | --- |
| bare strip, clamped-free, horizontal bending | {fq['bare_y'][0]:.2f}, {fq['bare_y'][1]:.1f} Hz |
| bare strip, vertical bending | {fq['bare_z'][0]:.0f} Hz |
| bare strip, torsion | {fq['bare_t'][0]:.1f} Hz |
| hub clamped, chain hanging: horizontal, exact frequency equation | **{fq['exact_h']:.2f} Hz** (assumed modes {fq['am_h']:.2f} Hz, tap test {tap['f_y']:.2f} Hz) |
| the same, Rayleigh with the chain's high-frequency mass | {fq['rayleigh_h']:.2f} Hz |
| the same, the whole chain as a rigid tip mass | {fq['exact_h_lumped']:.2f} Hz (wrong, see below) |
| hub clamped, chain hanging: vertical, exact frequency equation | {fq['exact_v']:.1f} Hz (assumed modes {fq['am_v']:.1f} Hz, tap test {tap['f_z']:.1f} Hz) |
| running rig (hub on the motor, no control), upright or hanging | {fq['free_hub_upright']:.1f} Hz |

The exact values solve the Euler-Bernoulli frequency equation of a clamped beam with a body at the tip, $w(s) = C_1(\\cosh \\beta s - \\cos \\beta s) + C_2(\\sinh \\beta s - \\sin \\beta s)$ with $\\beta^4 = \\rho A \\omega^2 / EI$ and at $s = L$

$$EI\\,w'' = (J \\omega^2 - k_g)\\,w', \\qquad EI\\,w''' = -M(\\omega)\\,\\omega^2\\,w.$$

- **Horizontal.** The pendulum hangs on a hinge that is free about the arm axis. A sideways push of the tip only partly carries the chain along; the rest of it swings. Its effective mass $M(\\omega) = m + \\omega^2 b^T (K - \\omega^2 M_q)^{{-1}} b$ (chain mass $m$ = {fq['chain_mass']:.3f} kg, coupling $b$, chain mass and gravity matrices $M_q$, $K$) falls to {fq['chain_m_inf'] * 1e3:.1f} g well above the pendulum frequencies. Treating the {fq['chain_mass']:.3f} kg as a rigid tip mass gives {fq['exact_h_lumped']:.1f} Hz, half the real value. $J$ is the chain's tiny inertia about the vertical, {fq['chain_j_axial']:.2e} kg·m².
- **Vertical.** In the vertical plane the hinge holds the chain rigidly: the tip carries $M$ = {fq['chain_mass']:.3f} kg and $J$ = {fq['chain_j_perp']:.4f} kg·m² about the tip (the long chain), and the hanging chain's gravity is a small rotational spring $k_g = m g c$. The large tip inertia makes the mode shape differ from the clamped-free modes: two assumed modes are {100 * (fq['am_v'] / fq['exact_v'] - 1):.0f} % high, three 6 %. That is harmless here: this mode is neither driven by the motor nor seen by the encoders.
- **Torsion.** The hinge does not pass a moment about the arm axis to the arm (only its bearing friction), so the pendulum's swing does not twist the strip, although the strip is very soft in torsion. The twist stays at {ml['twist_mrad'] * 1e3:.1f} µrad in the controlled run. Twist would matter for an encoder housing with an offset mass, or for a pendulum fixed to the arm.
- **In the running rig** the hub is not clamped: the motor and gear add only {dz['drive']['ng'] ** 2 * dz['drive']['jm']:.2e} kg·m², and the mode becomes a pinned-free-like mode at about {fq['free_hub_upright']:.0f} Hz, the frequency the controller meets.

The tap test (`flex-tap` in `expected.json`) checks the first two: the free model hanging at rest, the rotor inertia overridden to 1e3 kg·m² (the hub clamped), a 2 ms push on the tip link.

![Tap test: time response and spectrum|700]({img['tap']})

Back to the [overview](page:overview).
"""
    ct = f"""# The controller on the flexible arm

## The rigid firmware

`RotaryCtrl` is the rigid example's firmware, unchanged: a discrete TVLQR along the collocation swing-up and the latched LQR. Near the top its gains reach about 490 V/rad on the link angles and 35 to 200 V·s/rad on the link rates. Its loop gain at the upright, broken at the motor voltage, crosses 1 at {img['_lr_cross']:.0f} Hz on the rigid arm, but then falls only slowly: it is still {img['_lr_at_peak']:.2f} at {img['_lf_peak_f']:.0f} Hz. The design has no roll-off, because a rigid arm needs none.

On the flexible arm the arm's first bending mode (about {fq['free_hub_upright']:.0f} Hz with the hub on the motor) is a resonance in the loop: it lifts the loop gain to {img['_lf_peak']:.1f} at {img['_lf_peak_f']:.0f} Hz, with a phase that feeds the mode. The link encoders sit on the arm tip, so they read the tip's sideways bending as link rotation, and the rate gains turn it into a large voltage at the mode frequency. At the upright the closed loop (1 kHz, zero-order hold, `flex_design.py`) has the pole pair {worst[0]:+.1f} ± {abs(worst[1]):.1f}j 1/s: the mode grows by a factor e every {1000 / worst[0]:.1f} ms.

![Loop gain at the upright|700]({img['loop']})

The run never gets that far. The swing-up's large accelerations ring the arm mode, which the loop keeps at about {mf['f_chatter']:.0f} Hz. Near the top the TVLQR gains grow towards the balance gains, and from {img['_frozen_unstable_t']:.2f} s the frozen-time loop (the plant linearised along the nominal, closed with each table row's gains) has an arm pole that grows at 70 1/s and more. The voltage reaches the 15 V limit at the same moment ({mf['t_first_saturation']:.2f} s). From then on the amplifier is saturated, the swing-up is lost, and the chain is never caught ([Ctrl/phase](signal:Ctrl/phase) never reaches 2). The firmware ends up driving the arm round at full voltage ({mf['max_arm_rad']:.0f} rad by the end of the run).

Up to the first saturation, the bond graph and the flexible design model of `flex_design.py` (Lagrange, two clamped-free modes) agree on the modal coordinate to {img['_design_diff'] * 1e6:.1f} µm.

![Onset of the instability|700]({img['onset']})

What does not help (checked in the design study with the linear loop at the upright):

- **A notch** at the arm mode. The loop gain is 3 to 4 over a wide band around the mode, and the closed-loop mode moves when the notch removes gain. A notch centred anywhere from 55 to 90 Hz left a pole in the right half plane.
- **A gentler LQR.** The gains are set by the three unstable pendulum poles (up to 23.7 1/s). Raising R by up to four orders of magnitude lowers the gains only a little, and the loop stays unstable.
- **A stiffer arm** stabilises the linear loop at the upright from E about {fz['rigid_needs_e_scale']:.0f} times the steel's (bare first mode about {math.sqrt(fz['rigid_needs_e_scale']) * fq['bare_y'][0]:.0f} Hz). The whole scenario needs more, because the gains near the top of the swing-up are larger: on the design model the rigid firmware still fails at 26 times, is marginal at 50 times (it saturates and never latches the balance LQR) and works at 100 times (`flex-e100` in the checks).

## The fix: roll-off in the loop

`RotaryCtrlLP` keeps the rigid design's weights (Q = diag(20, 200, 200, 200, 1, 5, 5, 5), R = 5) and its swing-up nominal, but the LQR and the discrete TVLQR are computed for the rigid model with a second-order low-pass

$$F(s) = \\frac{{1}}{{s^2/\\omega_c^2 + 2 \\zeta s / \\omega_c + 1}}, \\qquad \\omega_c = 2\\pi \\cdot {lp['fc']:g}\\ \\mathrm{{Hz}},\\ \\zeta = {lp['zeta']:g}$$

between the feedback and the motor (the feed-forward $u^*(t)$ bypasses it). The filter state is part of the controller's state, so the optimisation itself compensates the filter's phase lag below the corner. The gains: $K$ = {', '.join(f'{v:.3g}' for v in lp['k_lqr'][:8])}, and {lp['k_lqr'][8]:.3g}, {lp['k_lqr'][9]:.3g} on the filter state. The loop gain now crosses 1 at {img['_lp_cross']:.0f} Hz and is {img['_lp_at_peak']:.2f} at the arm resonance, so the mode is gain-stabilised: it does not matter where exactly it is.

On the flexible design model the low-pass loop is stable for an arm stiffness from 0.5 to 100 times the steel's (the design notes list the worst pole), and the whole scenario succeeds on the rigid and the flexible design model, with the arm half or twice as stiff, and with the rigid design's perturbed links and motor. The price is a slower balance loop: the push deflects the tip link by {ml['peak_defl_deg']:.1f} deg instead of {rigid_m['peak_defl_deg']:.1f} deg, and the recovery takes {ml['t_recover']:.2f} s instead of {rigid_m['t_recover']:.2f} s.

Back to the [overview](page:overview).
"""
    rs = f"""# Results and checks

## Rigid firmware on the flexible arm (this model)

| quantity | value |
| --- | --- |
| first voltage saturation | {mf['t_first_saturation']:.2f} s (the rigid arm never saturates before the push) |
| arm mode under the swing-up loop, before the saturation | {mf['f_chatter']:.1f} Hz |
| largest modal coordinate eta_y[1] | {mf['max_eta_y1_mm']:.2f} mm (sideways tip deflection {mf['max_tip_y_mm']:.2f} mm) |
| catch | never ([Ctrl/phase](signal:Ctrl/phase) stays 1) |
| chain not upright (a link beyond 30 deg after T_s) | from {mf['t_fall']:.2f} s on |
| arm angle at the end | {mf['max_arm_rad']:.0f} rad: the saturated motor drives the arm round |

## Low-pass firmware on the flexible arm (`pendulum-triple-rotary-flex-lowpass`)

| quantity | flexible arm, low-pass firmware | rigid arm, rigid firmware |
| --- | --- | --- |
| catch | {ml['t_catch']:.2f} s | 5.00 s |
| upright band before the push | {ml['band_pre_deg']:.4f} deg | {rigid_m['band_pre_deg']:.4f} deg |
| tip link deflection after the push | {ml['peak_defl_deg']:.2f} deg | {rigid_m['peak_defl_deg']:.2f} deg |
| recovery inside 0.5 deg | {ml['t_recover']:.2f} s | {rigid_m['t_recover']:.2f} s |
| peak voltage | {ml['peak_v']:.2f} V | {rigid_m['peak_v']:.2f} V |
| largest sideways tip deflection: swing-up, balance, after the push | {ml['tip_y_swing_mm']:.3f} mm, {ml['tip_y_balance_mm'] * 1e3:.2f} µm, {ml['tip_y_dist_mm'] * 1e3:.1f} µm | 0 |
| largest vertical tip deflection | {ml['tip_z_mm'] * 1e3:.2f} µm | 0 |

![The low-pass firmware on the flexible arm, against the rigid arm|700]({img['fix']})

![The push: recovery and arm deflection|700]({img['disturbance']})
{shot_lp}
## Stiff limit

The free model with the arm's E overridden to {1e4:g} times the steel's (`flex-free-stiff`) against the rigid free model: the largest difference over the first second is {max(stiff.values()):.2g} rad (J1 {stiff['J1/qout']:.2g}, links {stiff['Angles/phi1']:.2g}, {stiff['Angles/phi2']:.2g}, {stiff['Angles/phi3']:.2g} rad). The free swing is chaotic, so the difference grows afterwards, as it does between any two slightly different models. The real steel strip differs from the rigid arm by up to {img['_steel_1s']:.2g} rad over the same second.

![Stiff limit|700]({img['stiff']})

The controlled model with E overridden to {100:g} times the steel's (`flex-e100`, bare first mode {10 * fq['bare_y'][0]:.0f} Hz): the rigid firmware catches at {meas['e100']['t_catch']:.2f} s, the push deflects the tip link by {meas['e100']['peak_defl_deg']:.3f} deg (rigid arm {rigid_m['peak_defl_deg']:.3f} deg) and the recovery takes {meas['e100']['t_recover']:.3f} s (rigid arm {rigid_m['t_recover']:.3f} s).

## Checks (`expected.json`)

- all three flexible models: scene bindings, no W201/E901 diagnostics, the energy ledger of the whole graph (Tellegen residual below 1e-6 of the throughput, the arm's modal bond graph included);
- `-flex`: the balance phase is never reached, the voltage saturates in the swing-up, the arm mode rings at {mf['f_chatter']:.0f} Hz before that (10 %), the arm tip deflection, the chain is not upright at the end;
- `-flex-lowpass`: caught one second after t_on + T_s, upright band, the push and the recovery, the voltage limit, the arm deflection while balancing and in the swing-up;
- `flex-tap`: the first horizontal arm mode against the exact frequency equation ({fq['exact_h']:.2f} Hz, 1 %) and the first vertical mode against the two-mode model ({fq['am_v']:.1f} Hz, 1 %);
- `flex-free-stiff` against `pendulum-triple-rotary-free`: J1 and the three link angles over the first second;
- `flex-e100`: the rigid firmware on an arm 100 times stiffer catches, holds and sees the rigid arm's deflection after the push.

Back to the [overview](page:overview).
"""
    return {"overview": ov, "arm": am, "controller": ct, "results": rs}


def lowpass_pages(dz: dict, fz: dict, meas: dict, img: dict, shot: str | None) -> dict:
    ml, lp = meas["lowpass"], fz["lp"]
    shot_md = f"\n![3D view, exaggeration x100|600]({shot})\n" if shot else ""
    ov = f"""# Triple rotary pendulum on a flexible arm, low-pass firmware

The flexible-arm rig of `pendulum-triple-rotary-flex` (a {fz['arm']['b'] * 1e3:g} x {fz['arm']['h'] * 1e3:g} mm stainless strip as the [arm](block:Arm)) with the fixed firmware [RotaryCtrlLP](block:Ctrl): the rigid design's weights and swing-up, with the LQR and the TVLQR designed for a {lp['fc']:g} Hz second-order low-pass between the feedback and the motor. The loop rolls off well below the arm's first bending mode (about {fz['freq']['free_hub_upright']:.0f} Hz), which the rigid firmware drives unstable. The docs of `pendulum-triple-rotary-flex` explain the arm, the failure and the design.

It catches at {ml['t_catch']:.2f} s, balances inside {ml['band_pre_deg']:.3f} deg, and recovers from the 0.1 N push within {ml['t_recover']:.2f} s (the rigid example: 1.35 s). The arm bends by up to {ml['tip_y_swing_mm']:.2f} mm sideways in the swing-up, by {ml['tip_y_balance_mm'] * 1e3:.1f} µm while balancing.

![Against the rigid arm|700]({img['fix']})
{shot_md}
## What to try

- **3D View**: the strip's bending and twist are bound to [Arm/eta_y[1]](signal:Arm/eta_y[1]), [Arm/eta_z[1]](signal:Arm/eta_z[1]) and [Arm/eta_t[1]](signal:Arm/eta_t[1]); the view opens with exaggeration ×100. The hinge follows the true-scale tip, so at ×100 the drawn strip end swings well past it.
- **Dashboard**: set the arm's Young's modulus between 1e11 Pa and 2e13 Pa: the low-pass firmware holds over that range.
- Plot [Ctrl/ufb](signal:Ctrl/ufb), the filtered feedback voltage, against [Ctrl/u](signal:Ctrl/u).
"""
    return {"overview": ov}


def free_pages(fz: dict, meas: dict, img: dict) -> dict:
    fq = fz["freq"]
    ov = f"""# Flexible arm, free swing

The flexible-arm rig of `pendulum-triple-rotary-flex` with the controller off: the chain is released at rest from the free-swing pose of `pendulum-triple-rotary-free` (motor terminals at 0 V). The checks run it three ways:

- as it is: the energy ledger of the whole graph, with the [arm](block:Arm)'s kinetic, strain and gravity energy ([Arm/Ek](signal:Arm/Ek), [Arm/Ee](signal:Arm/Ee), [Arm/Eg](signal:Arm/Eg));
- `flex-tap`: hanging at rest, the hub clamped by a rotor inertia of 1e3 kg·m², a 2 ms push on the tip link. The arm rings at {meas['tap']['f_y']:.2f} Hz horizontally (exact frequency equation {fq['exact_h']:.2f} Hz) and {meas['tap']['f_z']:.1f} Hz vertically;
- `flex-free-stiff`: the arm 1e4 times stiffer, against the rigid free model.

![Tap test|700]({img['tap']})

![Stiff limit|700]({img['stiff']})
"""
    return {"overview": ov}


def _tree(entries) -> dict:
    first, *rest = entries
    return {"format": "bgsim.docs", "version": 1, "pages": [
        {"id": first[0], "title": first[1], "file": f"pages/{first[0]}.md",
         "children": [{"id": pid, "title": title, "file": f"pages/{pid}.md", "children": []} for pid, title in rest]}]}


def write(example_dir: Path, dz: dict, fz: dict) -> None:
    meas = json.loads((example_dir / "design" / "flex_measured.json").read_text(encoding="utf-8"))
    runs = example_dir / "design" / "_runs"
    shots = example_dir / "design" / "_shots"
    models = example_dir / "models"
    # the flex model's docs hold all plots
    docs = models / f"{FLEX}.docs"
    _clean(docs)
    img = plots(dz, fz, meas, runs, docs)
    sh = {"flex": _copy_shot(shots / "flex-3d-top.png", docs), "lowpass": _copy_shot(shots / "flex-lowpass-3d-top.png", docs)}
    for pid, text in pages(dz, fz, meas, img, sh).items():
        (docs / "pages" / f"{pid}.md").write_text(text, encoding="utf-8", newline="\n")
    (docs / "docs.json").write_text(json.dumps(_tree([("overview", "Overview"), ("arm", "The flexible arm"), ("controller", "The controller"),
                                                      ("results", "Results and checks")]), indent=2) + "\n", encoding="utf-8", newline="\n")
    # the low-pass and the free model: one page each, with copies of their plots
    for name, keys in ((LOWPASS, ("fix",)), (FREE, ("tap", "stiff"))):
        d = models / f"{name}.docs"
        _clean(d)
        local = {}
        for key in keys:
            src = docs / img[key]
            (d / "assets" / src.name).write_bytes(src.read_bytes())
            local[key] = img[key]
        if name == LOWPASS:
            texts = lowpass_pages(dz, fz, meas, local, _copy_shot(shots / "flex-lowpass-3d-top.png", d))
        else:
            texts = free_pages(fz, meas, local)
        for pid, text in texts.items():
            (d / "pages" / f"{pid}.md").write_text(text, encoding="utf-8", newline="\n")
        (d / "docs.json").write_text(json.dumps(_tree([("overview", "Overview")]), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote the docs of {FLEX}, {LOWPASS} and {FREE}")
