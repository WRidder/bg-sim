# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Design of `pendulum-triple-rotary-flex`: the triple rotary pendulum on a flexible arm.

    uv run examples/pendulum-triple-rotary/design/flex_design.py

Reads the rigid design (`design/design.json`, `design/_swingup.npz`; run `design.py` first) and

1. defines the flexible arm: a 3 x 50 mm stainless-steel strip on edge (bending soft in the
   horizontal plane of the motor torque, stiff vertically), 0.2159 m long, with the density set so
   it weighs exactly the rigid arm's 0.257 kg;
2. computes its frequencies: the bare clamped-free values, the hub-clamped arm with the pendulum
   assembly at the tip by the exact Euler-Bernoulli frequency equation (horizontal: the hinged chain
   as a frequency-dependent tip mass; vertical: the chain as a rigid tip mass and rotary inertia),
   the Rayleigh estimate, and the assumed-modes values of the design model (`flex_lib.FlexPlant`);
3. closes the rigid firmware (the gains of `design.json`, unchanged) around the flexible design
   model: the linear poles at the upright and the whole scenario at 1 kHz;
4. designs the fix: the same weights, but the LQR and the TVLQR see a second-order low-pass filter
   (corner `fc`) in the feedback path, so the loop rolls off below the arm mode. The swing-up
   nominal is the rigid one, unchanged. Validated on the rigid and the flexible design models
   (nominal, arm stiffness x0.5 and x2, the rigid design's perturbed plants);
5. writes `design/flex_design.json` (the arm, the frequencies, the gain tables of `RotaryCtrlLP`).

`flex_build.py` turns it into the models, `flex_finish.py` runs them and writes the checks.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.linalg import expm, solve_discrete_are

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flex_lib as fl  # noqa: E402
import triple_lib as tl  # noqa: E402

# the arm: AISI 304 stainless steel strip 3 x 50 mm on edge (E 193 GPa, nu 0.29); the density
# (7936 kg/m^3, inside the 7900-8000 of the stainless grades) makes it weigh the rigid arm's 0.257 kg
ARM_B = 0.003  # along the arm's local y: horizontal, the plane of the motor torque
ARM_H = 0.050  # along local z: vertical
ARM_E = 193.0e9
ARM_NU = 0.29
ARM_RHO = tl.ARM_M / (ARM_B * ARM_H * tl.ARM_L)
ARM_ZETA = 0.01  # modal damping of a bolted steel strip
MODES = {"ny": 2, "nz": 2, "nt": 1}
FC = 12.0  # corner of the low-pass filter in the fixed controller [Hz]
ZF = 0.7071  # its damping (Butterworth)
TS = tl.TS


def beam(ny=2, nz=2, nt=1, e_scale=1.0) -> fl.Beam:
    return fl.Beam(L=tl.ARM_L, b=ARM_B, h=ARM_H, E=ARM_E * e_scale, rho=ARM_RHO, nu=ARM_NU, zeta=ARM_ZETA, ny=ny, nz=nz, nt=nt)


# ---------------------------------------------------------------- frequencies
def frequencies(rp: tl.Plant) -> dict:
    bm = beam()
    rho_a = bm.rho * bm.A
    ei_h, ei_v = bm.E * bm.Iz, bm.E * bm.Iy
    ct = fl.chain_tip(rp)
    imp = fl.chain_impedance(rp)
    m_inf = imp[0] - float(imp[1] @ np.linalg.solve(imp[2], imp[1]))
    k_g = ct.mass * tl.G * ct.com
    f_h = fl.first_root(lambda w: fl.cantilever_det(w, ei_h, rho_a, bm.L, lambda ww: fl.m_eff(imp, ww), ct.j_tip_axial), 60.0, 5000.0) / (2 * math.pi)
    f_h_lumped = fl.first_root(lambda w: fl.cantilever_det(w, ei_h, rho_a, bm.L, ct.mass, ct.j_tip_axial), 10.0, 5000.0) / (2 * math.pi)
    f_v = fl.first_root(lambda w: fl.cantilever_det(w, ei_v, rho_a, bm.L, ct.mass, ct.j_tip_perp, -k_g), 10.0, 20000.0) / (2 * math.pi)
    ray_h = math.sqrt(3 * ei_h / bm.L**3 / (m_inf + 33 / 140 * bm.m)) / (2 * math.pi)
    ray_lumped = math.sqrt(3 * ei_h / bm.L**3 / (ct.mass + 33 / 140 * bm.m)) / (2 * math.pi)
    fp = fl.FlexPlant(rp, bm)
    f_am, vec = fl.clamped_hub_frequencies(fp, [0.0, math.pi, 0.0, 0.0])
    nr = fp.nr - 1  # q0 removed
    def mode_of(index):  # the lowest elastic mode (> 10 Hz) whose largest modal coordinate is `index`
        for i in range(len(f_am)):
            v = np.abs(vec[:, i])
            if f_am[i] > 10.0 and int(np.argmax(v[nr:])) == index:
                return float(f_am[i])
        return math.nan
    # the running rig: hub free (motor and gear), upright, open loop; and the hanging rig
    out = {
        "bare_y": [bm.f_bending(n, True) for n in (1, 2, 3)],
        "bare_z": [bm.f_bending(n, False) for n in (1, 2, 3)],
        "bare_t": [bm.f_torsion(n) for n in (1, 2, 3)],
        "chain_mass": ct.mass,
        "chain_com": ct.com,
        "chain_j_perp": ct.j_tip_perp,
        "chain_j_axial": ct.j_tip_axial,
        "chain_m_inf": m_inf,
        "exact_h": f_h,
        "exact_h_lumped": f_h_lumped,
        "rayleigh_h": ray_h,
        "rayleigh_h_lumped": ray_lumped,
        "exact_v": f_v,
        "am_h": mode_of(0),
        "am_v": mode_of(MODES["ny"]),
        "am_t": mode_of(MODES["ny"] + MODES["nz"]),
        "am_all": [float(v) for v in f_am],
    }
    for label, rq in (("upright", [0.0] * fp.nr), ("hanging", [0.0, math.pi, 0.0, 0.0])):
        a, _, _ = fp.linear(rq)
        ev = np.linalg.eigvals(a)
        osc = sorted(abs(e.imag) / (2 * math.pi) for e in ev if abs(e.imag) / (2 * math.pi) > 10)
        out[f"free_hub_{label}"] = osc[0] if osc else math.nan
    return out


# ---------------------------------------------------------------- the low-pass augmented controller
def lowpass(fc: float = FC, zeta: float = ZF):
    """ZOH discretisation of 1 / (s^2/wc^2 + 2 zeta s/wc + 1): (Af, Bf, Cf), x = (y, y')."""
    wc = 2 * math.pi * fc
    a = np.array([[0.0, 1.0], [-wc * wc, -2 * zeta * wc]])
    b = np.array([[0.0], [wc * wc]])
    mm = expm(np.block([[a, b], [np.zeros((1, 3))]]) * TS)
    return mm[:2, :2], mm[:2, 2:], np.array([[1.0, 0.0]])


def augment(a, b, filt):
    af, bf, cf = filt
    n = a.shape[0]
    return np.block([[a, b @ cf], [np.zeros((2, n)), af]]), np.vstack([np.zeros((n, 1)), bf])


def lqr_lp(rp: tl.Plant, qdiag, r: float, filt):
    a, b = (np.array(m) for m in rp.lin_fn(np.zeros(rp.nx), 0.0))
    ad, bd = fl.discretise(a, b, TS)
    aa, ba = augment(ad, bd, filt)
    q = np.diag(list(qdiag) + [0.0, 0.0])
    p = solve_discrete_are(aa, ba, q, np.array([[r]]))
    k = np.linalg.solve(r + ba.T @ p @ ba, ba.T @ p @ aa)
    poles = np.log(np.linalg.eigvals(aa - ba @ k).astype(complex)) / TS
    return k.ravel(), p, poles


def tvlqr_lp(rp: tl.Plant, xs, us, qdiag, r: float, p_end, filt):
    """Backward discrete Riccati recursion of the filter-augmented sampled model along the rigid
    nominal (xs, us) of the 1 kHz grid."""
    _, jac = rp.steps(TS)
    q = np.diag(list(qdiag) + [0.0, 0.0])
    n = len(us) - 1
    ks = np.zeros((n + 1, rp.nx + 2))
    p = p_end.copy()
    for k in range(n - 1, -1, -1):
        a, b = (np.array(m) for m in jac(xs[k], us[k], 0.0))
        aa, ba = augment(a, b, filt)
        bp = ba.T @ p
        kk = np.linalg.solve(r + bp @ ba, bp @ aa)
        p = q + aa.T @ p @ (aa - ba @ kk)
        p = 0.5 * (p + p.T)
        ks[k] = kk.ravel()
    return ks


def flex_poles(fp: fl.FlexPlant, k, filt=None):
    """Equivalent continuous poles of the sampled loop on the flexible plant at the upright: the
    rigid firmware (filt None, k the 8 gains) or the low-pass one (k the 10 gains)."""
    a, b, _ = fp.linear()
    ad, bd = fl.discretise(a, b, TS)
    c = fp.measured()
    if filt is None:
        acl = ad - bd @ (np.asarray(k).reshape(1, -1) @ c)
    else:
        af, bf, cf = filt
        kx = np.asarray(k[: c.shape[0]]).reshape(1, -1) @ c
        kf = np.asarray(k[c.shape[0]:]).reshape(1, -1)
        acl = np.block([[ad, bd @ cf], [-bf @ kx, af - bf @ kf]])
    return np.log(np.linalg.eigvals(acl).astype(complex)) / TS


# ---------------------------------------------------------------- firmware and closed loop
class LPFirmware:
    """`library/RotaryCtrlLP.jl` line by line: the rigid firmware's phases, table and catch rule, the
    feedback through the low-pass filter: w = -K_x (x - x*) - K_f xf, xf+ = Af xf + Bf w,
    u = clamp(u* + Cf xf)."""

    def __init__(self, base: tl.Firmware, tab_k10, k_lqr10, filt):
        self.b = base
        self.tab_k = tab_k10
        self.k_lqr = k_lqr10
        self.af, self.bf, self.cf = filt

    def run(self, step, x0, t_end: float, force=None, nr: int = 4):
        fw = self.b
        n = int(round(t_end / TS))
        x = np.array(x0, float)
        nq = len(x) // 2
        sel = list(range(nr)) + list(range(nq, nq + nr))
        xf = np.zeros(2)
        st = {"latched": 0}
        ts = np.arange(n + 1) * TS
        xs = np.full((n + 1, len(x)), np.nan)
        us = np.zeros(n + 1)
        ph = np.zeros(n + 1)
        xs[0] = x
        for i in range(n):
            t = ts[i]
            xm = x[sel]
            if t < fw.t_on:
                u, phase = 0.0, 0
            else:
                tau = t - fw.t_on
                v = float(xm @ fw.p_catch @ xm)
                if st["latched"] < 0.5 and tau >= fw.t_s and v < fw.catch_tol:
                    st["latched"] = 1
                    st["t_catch"] = t
                if st["latched"] > 0.5:
                    phase = 2
                    w = -float(self.k_lqr[:8] @ xm) - float(self.k_lqr[8:] @ xf)
                    ustar = 0.0
                else:
                    phase = 1
                    s = min(max(tau / fw.dt_tab, 0.0), fw.tab_x.shape[0] - 1)
                    j = min(int(math.floor(s)), fw.tab_x.shape[0] - 2)
                    a = s - j
                    xr = (1 - a) * fw.tab_x[j] + a * fw.tab_x[j + 1]
                    ustar = (1 - a) * fw.tab_u[j] + a * fw.tab_u[j + 1]
                    kk = (1 - a) * self.tab_k[j] + a * self.tab_k[j + 1]
                    w = -float(kk[:8] @ (xm - xr)) - float(kk[8:] @ xf)
                u = float(np.clip(ustar + float((self.cf @ xf)[0]), -fw.vmax, fw.vmax))
                xf = self.af @ xf + self.bf.ravel() * w
            us[i] = u
            ph[i] = phase
            x = np.array(step(x, u, force(t + 0.5 * TS) if force else 0.0)).ravel()
            if not np.all(np.isfinite(x)) or np.max(np.abs(x[nq:])) > 1e4:
                break
            xs[i + 1] = x
        us[n] = us[n - 1]
        ph[n] = ph[n - 1]
        return ts, xs, us, ph, st


def rigid_firmware_run(fw: tl.Firmware, step, x0, t_end: float, force=None, nr: int = 4):
    """The rigid firmware (`RotaryCtrl.jl`) on a plant whose state has more than the measured coordinates."""
    n = int(round(t_end / TS))
    x = np.array(x0, float)
    nq = len(x) // 2
    sel = list(range(nr)) + list(range(nq, nq + nr))
    st = {"phase": 0}
    ts = np.arange(n + 1) * TS
    xs = np.full((n + 1, len(x)), np.nan)
    us = np.zeros(n + 1)
    ph = np.zeros(n + 1)
    xs[0] = x
    for i in range(n):
        u = tl.tick(fw, ts[i], x[sel], st)
        us[i] = u
        ph[i] = st["phase"]
        x = np.array(step(x, u, force(ts[i] + 0.5 * TS) if force else 0.0)).ravel()
        if not np.all(np.isfinite(x)) or np.max(np.abs(x[nq:])) > 1e4:
            break
        xs[i + 1] = x
    us[n] = us[n - 1]
    ph[n] = ph[n - 1]
    return ts, xs, us, ph, st


def summary(ts, xs, us, ph, st, dz: dict, nr: int = 4) -> dict:
    ok_rows = np.all(np.isfinite(xs), axis=1)
    last = int(np.max(np.where(ok_rows)[0]))
    phi = np.cumsum(xs[: last + 1, 1:nr], axis=1)
    dev = np.max(np.abs(phi), axis=1)
    tt = ts[: last + 1]
    t_dist = dz["t_dist"]
    pre = (tt >= dz["t_on"] + dz["t_s"] + 1.5) & (tt < t_dist)
    post = (tt >= t_dist) & (tt <= t_dist + 2.0)
    outside = np.where((dev > math.radians(0.5)) & (tt >= t_dist))[0]
    fell = np.where((dev > math.radians(30.0)) & (tt > dz["t_on"] + dz["t_s"]))[0]
    sat = np.where((np.abs(us[: last + 1]) >= dz["vmax"] - 1e-9) & (tt > dz["t_on"]))[0]
    return {
        "ok": bool(last == len(ts) - 1 and dev[-1] < math.radians(0.5)),
        "t_last": float(tt[-1]),
        "t_catch": float(st.get("t_catch", math.nan)),
        "band_pre_deg": math.degrees(float(np.max(dev[pre]))) if np.any(pre) else math.nan,
        "peak_defl_deg": math.degrees(float(np.max(np.abs(phi[post, -1])))) if np.any(post) else math.nan,
        "t_recover": (float(tt[outside[-1]]) - t_dist) if len(outside) else 0.0,
        "final_dev_deg": math.degrees(float(dev[-1])),
        "peak_v": float(np.max(np.abs(us[: last + 1]))),
        "t_first_saturation": float(tt[sat[0]]) if len(sat) else math.nan,
        "t_fall": float(tt[fell[0]]) if len(fell) else math.nan,
        "max_arm": float(np.max(np.abs(xs[: last + 1, 0]))),
    }


def tip_force(dz: dict, force: float | None = None):
    f = dz["dist_force"] if force is None else force
    t0, dur = dz["t_dist"], dz["dist_duration"]
    return lambda t: f if t0 <= t < t0 + dur else 0.0


def main() -> None:
    dz = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    rp = tl.Plant(dz["lengths"], dz["masses"], tl.Drive(**dz["drive"]), jfric=dz["jfric"])
    out: dict = {"arm": {"L": tl.ARM_L, "b": ARM_B, "h": ARM_H, "E": ARM_E, "nu": ARM_NU, "rho": ARM_RHO,
                         "zeta": ARM_ZETA, **MODES, "mass": beam().m, "EI_y": ARM_E * beam().Iz, "EI_z": ARM_E * beam().Iy,
                         "GJ": beam().G * beam().Jt}}
    started = time.time()
    fr = frequencies(rp)
    out["freq"] = fr
    print("frequencies (Hz):", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in fr.items() if k != "am_all"})

    # ---- the rigid firmware on the flexible arm
    fp_lin = fl.FlexPlant(rp, beam(ny=2, nz=0, nt=0))
    k_rigid = np.array(dz["k_lqr"])
    pl = flex_poles(fp_lin, k_rigid)
    pl = pl[np.argsort(-pl.real)]
    out["rigid_on_flex_poles"] = [[float(p.real), float(p.imag)] for p in pl[:6]]
    print(f"rigid LQR on the flexible arm: worst pole {pl[0].real:+.1f} {pl[0].imag:+.1f}j 1/s ({abs(pl[0].imag) / 2 / math.pi:.1f} Hz)")
    # the stiffness the rigid gains need: bisection on the E scale
    lo, hi = 1.0, 100.0
    for _ in range(20):
        mid = math.sqrt(lo * hi)
        p = flex_poles(fl.FlexPlant(rp, beam(2, 0, 0, mid)), k_rigid)
        lo, hi = (mid, hi) if np.max(p.real) > 0 else (lo, mid)
    out["rigid_needs_e_scale"] = hi
    print(f"  the rigid gains need E x {hi:.1f} (bare f_y1 {beam(e_scale=hi).f_bending(1, True):.0f} Hz)")
    fw = tl.Firmware(t_on=dz["t_on"], t_s=dz["t_s"], dt_tab=dz["dt_tab"], tab_x=np.array(dz["tab_x"]), tab_u=np.array(dz["tab_u"]),
                     tab_k=np.array(dz["tab_k"]), k_lqr=k_rigid, p_catch=np.array(dz["p_lqr"]), catch_tol=dz["catch_tol"], vmax=dz["vmax"])
    step_flex = fp_lin.steps(TS, 4)
    x0f = fp_lin.hanging()
    run = rigid_firmware_run(fw, step_flex, x0f, dz["t_end"], tip_force(dz))
    m_rigid_flex = summary(*run, dz)
    out["rigid_on_flex_run"] = m_rigid_flex
    print("  rigid firmware on the flexible design model:", {k: round(v, 3) if isinstance(v, float) else v for k, v in m_rigid_flex.items()})

    # ---- the fix: low-pass in the loop
    filt = lowpass()
    k10, p10, poles10 = lqr_lp(rp, dz["qdiag"], dz["r"], filt)
    traj = np.load(HERE / "_swingup.npz", allow_pickle=False)
    tr = {"x": traj["x"], "u": traj["u"], "t_s": dz["t_s"]}
    xs, us, _, end_err = tl.tvlqr(rp, tr, dz["qdiag"], dz["r"], np.array(dz["k_lqr"]), np.array(dz["p_lqr"]))
    ks10 = tvlqr_lp(rp, xs, us, dz["qdiag"], dz["r"], p10, filt)
    stride = int(round(dz["dt_tab"] / TS))
    tab_k10 = ks10[::stride].copy()
    tab_k10[-1] = k10
    # the nominal rows are the rigid design's (the same roll-out); the catch rule reads the x block of P
    base = tl.Firmware(t_on=dz["t_on"], t_s=dz["t_s"], dt_tab=dz["dt_tab"], tab_x=np.array(dz["tab_x"]), tab_u=np.array(dz["tab_u"]),
                       tab_k=tab_k10, k_lqr=k10, p_catch=p10[:8, :8], catch_tol=dz["catch_tol"], vmax=dz["vmax"])
    lp = LPFirmware(base, tab_k10, k10, filt)
    pf = flex_poles(fp_lin, k10, filt)
    pf = pf[np.argsort(-pf.real)]
    out["lp"] = {"fc": FC, "zeta": ZF, "k_lqr": k10.tolist(), "p_x": p10[:8, :8].tolist(),
                 "poles_rigid": [[float(p.real), float(p.imag)] for p in poles10],
                 "poles_flex_worst": [[float(p.real), float(p.imag)] for p in pf[:6]],
                 "max_gain": float(np.abs(ks10).max()), "rollout_end_err": end_err,
                 "af": filt[0].tolist(), "bf": filt[1].ravel().tolist()}
    print(f"low-pass LQR (fc {FC} Hz): K {np.round(k10, 3)}; rigid poles {np.round(np.sort(poles10.real), 2)}")
    print(f"  on the flexible arm: worst pole {pf[0].real:+.2f} 1/s; arm modes: "
          + ", ".join(f"{p.real:.1f}{p.imag:+.1f}j" for p in pf if abs(p.imag) / 2 / math.pi > 20)[:200])
    robust_e = {}
    for scale in (0.5, 2.0, 10.0, 100.0):
        p = flex_poles(fl.FlexPlant(rp, beam(2, 0, 0, scale)), k10, filt)
        robust_e[str(scale)] = float(np.max(p.real))
    out["lp"]["worst_pole_vs_e_scale"] = robust_e
    print("  worst pole vs arm stiffness scale:", robust_e)

    runs = {}
    step_rigid, _ = rp.steps()
    runs["lp on rigid"] = summary(*lp.run(step_rigid, rp.hanging(), dz["t_end"], tip_force(dz)), dz)
    runs["lp on flex"] = summary(*lp.run(step_flex, x0f, dz["t_end"], tip_force(dz)), dz)
    for scale in (0.5, 2.0):
        fps = fl.FlexPlant(rp, beam(2, 0, 0, scale))
        runs[f"lp on flex E x{scale}"] = summary(*lp.run(fps.steps(TS, 4), fps.hanging(), dz["t_end"], tip_force(dz)), dz)
    lengths, masses = tl.LINKS
    for name, plant in {
        "link masses +3 %": tl.Plant(lengths, [m * 1.03 for m in masses], tl.Drive()),
        "link masses -3 %": tl.Plant(lengths, [m * 0.97 for m in masses], tl.Drive()),
        "bearing friction x3": tl.Plant(lengths, masses, tl.Drive(), jfric=3 * tl.JFRIC),
        "motor kt -3 %": tl.Plant(lengths, masses, tl.Drive(kt=0.97 * 0.0333)),
    }.items():
        fps = fl.FlexPlant(plant, beam(2, 0, 0))
        runs[f"lp on flex, {name}"] = summary(*lp.run(fps.steps(TS, 4), fps.hanging(), dz["t_end"], tip_force(dz)), dz)
    for name, m in runs.items():
        print(f"  {name}:", {k: round(v, 3) if isinstance(v, float) else v for k, v in m.items()})
    out["lp_runs"] = runs
    if not all(m["ok"] for m in runs.values()):
        raise SystemExit("the low-pass firmware does not recover in every case: not writing flex_design.json")
    out["lp"]["tab_k"] = tab_k10.tolist()
    out["seconds"] = time.time() - started
    path = HERE / "flex_design.json"
    path.write_text(json.dumps(out) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path} ({out['seconds']:.0f} s)")


if __name__ == "__main__":
    main()
