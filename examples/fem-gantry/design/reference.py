# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""The settling reference of fem-gantry: a linear modal model of the gantry in scipy, no BGSim.

    uv run examples/fem-gantry/design/reference.py      (writes design/reference.json)

The model is the gantry linearised about rest, built from the reduced-model file alone:

* the two X carriages x1 and x2, each with its own AxisServo (the same equations; X2's force
  scaled by kf2 for racking);
* the yaw psi1 of the X1 carriage on its guide (KR_X) and the yaw psi_R of the beam's frame R,
  held against the X1 carriage by the A weld (KW): the welded end is only as stiff in yaw as
  the weld and the guide in series; R moves along x with X1;
* the beam's modal coordinates eta, with the B end held by the pivot against translation and
  against rotation about x and y (rotation about z is free, with its bearing friction): the
  x row ties psi_R to x1 - x2, the other four make eta = N xi (N their null space);
* the Y carriage rigidly on the rail at s = y_c (the rail tables PT(s), PR(s)), its mass and
  inertia added through the rail point's motion (rigid frame motion included);
* the floating-frame coupling of the beam (first moments S0, St, Sr) and of the carriage;
* modal damping 2 zeta sqrt(k m) per file mode, as ModalBody3D.

Left out against the BGSim model: the translational compliance of the guides, the end
brackets and the slide coupling (all far stiffer than the beam), the Y servo (the carriage
holds its place on the rail) and every nonlinear term.

It writes the tool's dominant vibration after a plain move (the shaper's f_s and zeta_s, from
the closed-loop eigenvalues), the settling times and residual vibration over a sweep of
accelerations, plain and shaped, and the time histories of the default move.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import expm
from scipy.linalg import eig, null_space

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402

HERE = Path(__file__).resolve().parent
M = B.MODAL
NM = B.NM
mk, kk = np.array(M["modal_mass"]), np.array(M["modal_stiffness"])
St = np.array(M["St"])
RAIL = M["rail"]
RR = np.array(RAIL["rotation_matrix"])          # rail frame axes (columns) in R


def skew(r):
    return np.array([[0, -r[2], r[1]], [r[2], 0, -r[0]], [-r[1], r[0], 0]])


def cheb(x, n):
    T = np.zeros(n)
    T[0] = 1.0
    if n > 1:
        T[1] = x
    for k in range(2, n):
        T[k] = 2 * x * T[k - 1] - T[k - 2]
    return T


def von_mises(s):
    """von Mises of the components (xx, yy, zz, xy, xz, yz) along axis 0."""
    xx, yy, zz, xy, xz, yz = s
    return np.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy**2 + xz**2 + yz**2))


def rail_tables(s):
    """PT(s) (3 x nm, R) and PR(s) (3 x nm, rail frame) at the rail coordinate s."""
    T = cheb(2 * s / RAIL["length"] - 1, RAIL["chebyshev"])
    PT = np.array([np.array(RAIL["translation"][a]) @ T for a in range(3)])
    PR = np.array([np.array(RAIL["rotation"][a]) @ T for a in range(3)])
    return PT, PR


def scurve(t, q0, q1, t0, vmax, amax, jmax):
    """stdlib:motion/SCurveProfile: q, v, a of the seven-segment jerk-limited move."""
    dist, d = abs(q1 - q0), np.sign(q1 - q0)
    t = np.asarray(t, dtype=float)
    if dist == 0:
        z = np.zeros_like(t)
        return z + q0, z, z
    a_v = min(amax, math.sqrt(vmax * jmax))
    cruise = dist >= vmax * (a_v / jmax + vmax / a_v)
    ap = a_v if cruise else min(amax, (dist * jmax**2 / 2) ** (1 / 3))
    Tj = ap / jmax
    vp = vmax if cruise else ap * (math.sqrt(Tj**2 + 4 * dist / ap) - Tj) / 2
    Ta = Tj + vp / ap
    Tc = max(dist / vmax - Ta, 0.0) if cruise else 0.0
    b = t0 + np.array([Tj, Ta - Tj, Ta, Ta + Tc, Ta + Tc + Tj, 2 * Ta + Tc - Tj, 2 * Ta + Tc])
    jerk = np.select([t < t0, t < b[0], t < b[1], t < b[2], t < b[3], t < b[4], t < b[5], t < b[6]],
                     [0, jmax, 0, -jmax, 0, -jmax, 0, jmax], 0) * d
    # integrate the piecewise-constant jerk exactly segment by segment
    knots = np.concatenate([[t0], b])
    a_k, v_k, q_k = [0.0], [0.0], [q0]
    js = np.array([jmax, 0, -jmax, 0, -jmax, 0, jmax]) * d
    for i in range(7):
        h = knots[i + 1] - knots[i]
        a, v, q = a_k[-1], v_k[-1], q_k[-1]
        q_k.append(q + v * h + a * h**2 / 2 + js[i] * h**3 / 6)
        v_k.append(v + a * h + js[i] * h**2 / 2)
        a_k.append(a + js[i] * h)
    seg = np.clip(np.searchsorted(knots, t, side="right") - 1, 0, 7)
    h = t - knots[np.minimum(seg, 7)]
    jj = np.where(seg < 7, js[np.minimum(seg, 6)], 0.0)
    a0, v0, qq = np.array(a_k)[seg], np.array(v_k)[seg], np.array(q_k)[seg]
    q = qq + v0 * h + a0 * h**2 / 2 + jj * h**3 / 6
    v = v0 + a0 * h + jj * h**2 / 2
    a = a0 + jj * h
    before, after = t < t0, t >= b[6]
    q = np.where(before, q0, np.where(after, q1, q))
    v = np.where(before | after, 0.0, v)
    a = np.where(before | after, 0.0, a)
    del jerk
    return q, v, a


def shaper(shaping: int, f_s: float, zeta_s: float):
    K = math.exp(-zeta_s * math.pi / math.sqrt(1 - zeta_s**2))
    Td = 1 / (f_s * math.sqrt(1 - zeta_s**2))
    if shaping == 0:
        return [(1.0, 0.0)]
    if shaping == 1:
        return [(1 / (1 + K), 0.0), (K / (1 + K), Td / 2)]
    s = (1 + K) ** 2
    return [(1 / s, 0.0), (2 * K / s, Td / 2), (K**2 / s, Td)]


def reference_signal(t, a_max, v_max, j_max, shaping, f_s, zeta_s):
    q = np.zeros_like(t)
    v = np.zeros_like(t)
    a = np.zeros_like(t)
    for sign, t0 in ((1.0, B.T1), (-1.0, B.T2)):
        for w, d in shaper(shaping, f_s, zeta_s):
            qq, vv, aa = scurve(t, 0.0, sign * B.DX * w, t0 + d, v_max * w, a_max * w, j_max * w)
            q, v, a = q + qq, v + vv, a + aa
    return q, v, a


class Gantry:
    """The linearised gantry. Coordinates q = (x1, x2, psi1, xi): the two X carriages, the yaw
    of the X1 carriage (held by its guide, KR_X) and the beam's free modal coordinates xi
    (eta = N xi). The beam's frame R moves with X1 (x_R = x1) and yaws by psi_R, held by the
    A weld spring KW against the X1 carriage; the B pivot is rigid in x, so
    x2 = x1 - L_AB psi_R + PT_B,x eta fixes psi_R. B's other translations and its rotations
    about x and y are held (the five stiff pivot directions): eta = N xi with N the null space
    of those four rows (the fifth, x, gives psi_R)."""

    def __init__(self, s0: float = B.RAIL_L / 2, zeta: float = B.ZETA, kf2: float = 1.0):
        self.kf2 = kf2
        PT, PR = rail_tables(s0)
        ib = M["interfaces"][1]
        PTb, PRb = np.array(ib["translation"]), np.array(ib["rotation"])
        L = ib["position"][1]
        N = null_space(np.vstack([PTb[1:3], PRb[:2]]))
        n = N.shape[1]
        self.N, self.n = N, n
        n1 = 3 + n
        # psi_R and eta as rows over q'
        psi = np.zeros(n1)
        psi[0], psi[1] = 1.0 / L, -1.0 / L
        psi[3:] = (PTb[0] @ N) / L
        Eta = np.zeros((NM, n1))
        Eta[:, 3:] = N
        # the beam's generalized velocity w = (v_x, w_z, eta') = G q'
        G = np.vstack([np.eye(1, n1, 0), psi[None, :], Eta])
        S0, J0 = np.array(M["first_moment"]), np.array(M["inertia"])
        Sr = np.array(M["Sr"])
        Mb = np.zeros((2 + NM, 2 + NM))
        Mb[0, 0] = B.M_BEAM
        Mb[0, 1] = Mb[1, 0] = -S0[1]                       # v . (w x S0), w = w_z z
        Mb[1, 1] = J0[2, 2]
        Mb[0, 2:] = Mb[2:, 0] = St[0]
        Mb[1, 2:] = Mb[2:, 1] = Sr[2]
        Mb[2:, 2:] = np.diag(mk)
        # the Y carriage rigidly at the rail point s0 (centre of mass r_c in R)
        Tw = RR @ PR
        r_off = RR @ np.array([B.CX, B.CY, 0.0])
        r_c = np.array(RAIL["start"]) + s0 * RR[:, 2] + r_off
        Tv = PT - skew(r_off) @ Tw
        z = np.array([0.0, 0.0, 1.0])
        Lv = np.column_stack([np.array([1.0, 0.0, 0.0]), np.cross(z, r_c), Tv])
        Lw = np.column_stack([np.zeros(3), z, Tw])
        J_R = RR @ np.diag(B.J_YC) @ RR.T
        Mw = Mb + B.M_YC * Lv.T @ Lv + Lw.T @ J_R @ Lw
        Mq = G.T @ Mw @ G
        Mq[0, 0] += B.M_XC
        Mq[1, 1] += B.M_XC
        Mq[2, 2] += B.J_XC[2]
        # springs and dampers: the modes, the X1 guide's yaw, the A weld, the B pivot's friction
        e_psi1 = np.eye(1, n1, 2)[0]
        rel = psi - e_psi1
        Kq = Eta.T @ np.diag(kk) @ Eta + B.KR_X * np.outer(e_psi1, e_psi1) + B.KW * np.outer(rel, rel)
        Cq = (Eta.T @ np.diag(2 * zeta * np.sqrt(kk * mk)) @ Eta
              + B.damping(B.KR_X, B.J_XC[2]) * np.outer(e_psi1, e_psi1)
              + B.damping(B.KW, 1.0) * np.outer(rel, rel) + B.D_PIVOT * np.outer(psi, psi))
        self.Mq, self.Kq, self.Cq = Mq, Kq, Cq
        self.Minv = np.linalg.inv(Mq)
        # the tool's world x: x_R - y_t psi_R + (its rail-point motion) eta
        r_toff = RR @ np.array([B.CX + B.TX, B.CY + B.TY, 0.0])
        r_t = np.array(RAIL["start"]) + s0 * RR[:, 2] + r_toff
        self.tool = np.eye(1, n1, 0)[0] - r_t[1] * psi + (PT[0] - (skew(r_toff) @ Tw)[0]) @ Eta
        self.psi = psi

    def servo_params(self, notch=1.0, f_n=50.0):
        return dict(M=B.M_X, wp=2 * math.pi * B.FP_X, wv=2 * math.pi * B.FV_X, wi=2 * math.pi * B.FI,
                    wn=2 * math.pi * f_n, wb=2 * math.pi * f_n / 2, dn=notch)

    def rhs(self, t, y, ref, sp):
        n1 = self.n + 3
        q, qd = y[:n1], y[n1:2 * n1]
        xr, vr, ar = ref(t)
        f = np.zeros(n1)
        dservo = []
        for k, kf in ((0, 1.0), (1, self.kf2)):
            xi, z1, z2, F = y[2 * n1 + 4 * k:2 * n1 + 4 * k + 4]
            vc = sp["wp"] * (xr - q[k]) + vr
            ev = vc - qd[k]
            u = sp["M"] * sp["wv"] * (ev + sp["wv"] / 4 * xi) + sp["M"] * ar
            Fc = u + (sp["dn"] - 1) * sp["wb"] * z2
            f[k] = F
            dservo += [ev, z2, u - sp["wn"] ** 2 * z1 - sp["wb"] * z2, sp["wi"] * (kf * Fc - F)]
        qdd = self.Minv @ (f - self.Kq @ q - self.Cq @ qd)
        return np.concatenate([qd, qdd, dservo])

    def nx(self):
        return 2 * (self.n + 3) + 8

    def state_matrix(self, sp):
        """The closed loop's A (reference zero)."""
        nx = self.nx()
        A = np.zeros((nx, nx))
        for j in range(nx):
            e = np.zeros(nx)
            e[j] = 1.0
            A[:, j] = self.rhs(0.0, e, lambda t: (0.0, 0.0, 0.0), sp)
        return A

    def input_matrix(self, sp):
        """The closed loop's B for the reference (x_ref, v_ref, a_ref)."""
        nx = self.nx()
        cols = []
        for j in range(3):
            r = [0.0, 0.0, 0.0]
            r[j] = 1.0
            cols.append(self.rhs(0.0, np.zeros(nx), lambda t, r=r: tuple(r), sp))
        return np.column_stack(cols)

    def run(self, a_max, v_max, j_max, shaping, f_s, zeta_s, t_end=B.T_END, dt=2e-5, notch=1.0, f_n=50.0,
            full=False):
        """The linear closed loop, discretised exactly (matrix exponential, the reference
        linear between samples): no step-size limit from the stiff modes. Returns t, the
        tool error, v_ref, x1 and the X1 force (and, with full, a dict with x2 and F2)."""
        sp = self.servo_params(notch, f_n)
        A, Bm = self.state_matrix(sp), self.input_matrix(sp)
        n1 = self.n + 3
        nx = self.nx()
        t = np.arange(0.0, t_end + dt / 2, dt)
        xr, vr, ar = reference_signal(t, a_max, v_max, j_max, shaping, f_s, zeta_s)
        U = np.vstack([xr, vr, ar])
        # first-order hold: expm of [[A, B, 0], [0, 0, I/dt], [0, 0, 0]] dt
        Z = np.zeros((nx + 6, nx + 6))
        Z[:nx, :nx] = A * dt
        Z[:nx, nx:nx + 3] = Bm * dt
        Z[nx:nx + 3, nx + 3:] = np.eye(3)
        E = expm(Z)
        Ad, G1, G2 = E[:nx, :nx], E[:nx, nx:nx + 3], E[:nx, nx + 3:]
        X = np.zeros((nx, len(t)))
        for k in range(len(t) - 1):
            X[:, k + 1] = Ad @ X[:, k] + G1 @ U[:, k] + G2 @ (U[:, k + 1] - U[:, k])
        q = X[:n1]
        ex = self.tool @ q - xr
        if full:
            # the stress: every point's six components superpose over the modes (ModalStress3D)
            eta = self.N @ q[3:]
            vm = np.array([von_mises(np.array(p["sigma"]) @ eta) for p in M["stress"]["points"]])
            return t, ex, vr, q[0], X[2 * n1 + 3], {"x2": q[1], "F2": X[2 * n1 + 7], "xr": xr, "vm": vm}
        return t, ex, vr, q[0], X[2 * n1 + 3]


def settle(t, e, vr, t_from, t_to, band=B.BAND):
    """From the end of the reference motion in [t_from, t_to) to the last sample outside the band."""
    w = (t >= t_from) & (t < t_to)
    moving = w & (np.abs(vr) > 1e-5)
    t_ref = t[moving].max()
    out = w & (np.abs(e) > band)
    t_out = t[out].max() if out.any() else t_ref
    return max(t_out - t_ref, 0.0), t_ref


def residual(t, e, t_ref, t_to, skip=0.0):
    w = (t > t_ref + skip) & (t < t_to)
    return float(np.abs(e[w]).max())


def dominant_mode(g: Gantry):
    """The closed-loop mode that dominates the tool error after a plain move: the residue of each
    oscillatory eigenvalue in the tool error of the default move's residual vibration."""
    sp = g.servo_params()
    A = g.state_matrix(sp)
    lam, V = eig(A)
    t, ex, vr, _, _ = g.run(**B.MOVE, shaping=0, f_s=50.0, zeta_s=0.02, t_end=B.T2)
    s, t_ref = settle(t, ex, vr, B.T1, B.T2)
    w = t > t_ref
    tt, ee = t[w] - t_ref, ex[w]
    # least squares fit of the residual vibration on the oscillatory closed-loop modes below 1 kHz
    modes = [l for l in lam if l.imag > 2 * math.pi * 2 and l.imag < 2 * math.pi * 1000]
    basis = np.column_stack([np.exp(l.real * tt) * np.cos(l.imag * tt) for l in modes] +
                            [np.exp(l.real * tt) * np.sin(l.imag * tt) for l in modes])
    coef, *_ = np.linalg.lstsq(basis, ee, rcond=None)
    k = len(modes)
    amp = np.hypot(coef[:k], coef[k:])
    i = int(np.argmax(amp))
    l = modes[i]
    f = abs(l) / 2 / math.pi
    zeta = -l.real / abs(l)
    table = sorted([(float(abs(m) / 2 / math.pi), float(-m.real / abs(m)), float(a)) for m, a in zip(modes, amp)],
                   key=lambda r: -r[2])[:6]
    return f, zeta, table, s


def main() -> None:
    g = Gantry()
    f_s, zeta_s, table, s_plain = dominant_mode(g)
    print(f"dominant closed-loop mode of the tool error: {f_s:.2f} Hz, zeta {zeta_s:.4f}")
    for f, z, a in table:
        print(f"   {f:9.2f} Hz  zeta {z:.4f}  amplitude {a * 1e6:.3f} um")
    zeta_s = round(zeta_s, 3)
    f_s = round(f_s, 2)
    sweep = []
    for a in (5.0, 10.0, 15.0, 20.0, 30.0):
        row = {"a_max": a}
        for shaping in (0, 1, 2):
            t, ex, vr, x, F = g.run(a, B.MOVE["v_max"], B.MOVE["j_max"], shaping, f_s, zeta_s, t_end=B.T2)
            s, t_ref = settle(t, ex, vr, B.T1, B.T2)
            row[f"s{shaping}"] = {"settle": s, "t_ref": t_ref, "move_end": t_ref, "residual": residual(t, ex, t_ref, B.T2),
                                  "residual_20ms": residual(t, ex, t_ref, B.T2, 0.02), "peak": float(np.abs(ex).max()),
                                  "F_peak": float(np.abs(F).max())}
        print(f"a = {a:5.1f}: settle plain {row['s0']['settle'] * 1e3:6.1f} ms, ZV {row['s1']['settle'] * 1e3:6.1f} ms, "
              f"ZVD {row['s2']['settle'] * 1e3:6.1f} ms; residual plain {row['s0']['residual'] * 1e6:6.2f} um, "
              f"ZV {row['s1']['residual'] * 1e6:6.2f}, ZVD {row['s2']['residual'] * 1e6:6.2f}; motor peak {row['s0']['F_peak']:.0f} N")
        sweep.append(row)
    # the dashboard's scenarios at the default move: settling of the move out, the residual
    # vibration after it, the largest racking x1 - x2 and the motor force peaks
    scenarios = {}
    for name, kw, mk_kw in (("plain", {}, {}), ("zv", {"shaping": 1}, {}), ("zvd", {"shaping": 2}, {}),
                            ("notch", {"notch": 0.0, "f_n": B.F_NOTCH}, {}), ("kf2_0.9", {}, {"kf2": 0.9}),
                            ("y_c_0.15", {}, {"s0": 0.15})):
        gg = Gantry(**mk_kw) if mk_kw else g
        args = dict(shaping=0, f_s=f_s, zeta_s=zeta_s)
        args.update(kw)
        t, ex, vr, x1, F1, extra = gg.run(B.MOVE["a_max"], B.MOVE["v_max"], B.MOVE["j_max"], t_end=B.T_END, full=True, **args)
        s, t_ref = settle(t, ex, vr, B.T1, B.T2)
        rack = x1 - extra["x2"]
        scenarios[name] = {"settle": s, "t_ref": t_ref, "in_band": t_ref + s - B.T1,
                           "residual": residual(t, ex, t_ref, B.T2), "peak": float(np.abs(ex).max()),
                           "rack_peak": float(np.abs(rack).max()), "rack_end_out": float(rack[np.searchsorted(t, B.T2) - 1]),
                           "F1_peak": float(np.abs(F1).max()), "F2_peak": float(np.abs(extra["F2"]).max()),
                           "x1_at_t2": float(x1[np.searchsorted(t, B.T2) - 1]), "x1_end": float(x1[-1]),
                           "vm_peak": [float(v) for v in extra["vm"][:3].max(axis=1)],
                           "sigma_max_peak": float(extra["vm"].max())}
        r = scenarios[name]
        print(f"{name:10s}: settle {r['settle'] * 1e3:6.1f} ms (move ends {r['t_ref']:.4f} s, in band {r['in_band'] * 1e3:.1f} ms after t1), "
              f"residual {r['residual'] * 1e6:7.2f} um, peak {r['peak'] * 1e6:7.1f} um, rack peak {r['rack_peak'] * 1e6:6.2f} um, "
              f"F {r['F1_peak']:.0f}/{r['F2_peak']:.0f} N, vm " + "/".join(f"{v / 1e6:.3f}" for v in r['vm_peak']) + f" MPa, max {r['sigma_max_peak'] / 1e6:.3f} MPa")
    out = {"f_s": f_s, "zeta_s": zeta_s, "modes": table, "sweep": sweep, "scenarios": scenarios,
           "note": "design/reference.py: linear modal model of the gantry from data/beam.modal.json"}
    old = json.loads((HERE / "reference.json").read_text(encoding="utf-8")) if (HERE / "reference.json").exists() else {}
    for k in ("checks", "bgsim"):
        if k in old:
            out[k] = old[k]
    with open(HERE / "reference.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
