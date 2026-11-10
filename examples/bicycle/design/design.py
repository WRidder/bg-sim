# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Reference numbers of the `bicycle` example, written to ``design.json``.

    uv run examples/bicycle/design/design.py

1. The linearised benchmark matrices from the paper's appendix A (``benchmark.matrices``)
   against the printed equations (6.1)-(6.4), and the eigenvalues against table 2.
2. The weave and capsize speeds by root finding on the eigenvalues (table 2 a).
3. Reference time responses of the linear model (scipy ``expm``) for the cursor checks of the
   models ``linear`` and ``balance-linear``.
4. The low-speed balance controller: LQR on the linear model at 3 m/s (scipy
   ``solve_continuous_are``) with a reference gain for a lean set-point, and the steady turn it
   produces (steer angle, steer torque and heading rate) from the linear equations.
5. The static tyre loads and deflections of the 3D model's compliant contacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import expm, solve_continuous_are
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b  # noqa: E402

HERE = Path(__file__).resolve().parent
P = b.PARAMS

# contact of the 3D model (RollingDisk, knife edge): Hertz-type stiffness, friction
CONTACT = {"k": 1.0e6, "xref": 1.0e-3, "c": 2.0, "mu": 0.9, "vs": 1.0e-3}

# balance controller (model `balance`)
V_BAL = 3.0
LEAN_REF = 0.1
Q_BAL = np.diag([100.0, 10.0, 10.0, 1.0])     # phi, delta, phid, deltad
R_BAL = np.array([[1.0]])                      # steer torque, (N m)^-2

# the paper's figure 4 run (model `whipple`)
V_FIG4, PHID_FIG4 = 4.6, 0.5


def weave_pair(v):
    ev = b.eigenvalues(v)
    return ev[np.argmax(ev.imag)]


def response(v, x0, t, u=None, B=None):
    """x(t) of x' = A x (+ B u, constant) from x0, exact (matrix exponential)."""
    A, Bm = b.state_matrices(v)
    out = []
    for tk in t:
        if u is None:
            out.append(expm(A * tk) @ x0)
        else:
            # augmented system with the constant input as a state
            n = A.shape[0]
            Aa = np.zeros((n + 1, n + 1))
            Aa[:n, :n] = A
            Aa[:n, n] = (B if B is not None else Bm[:, 1]) * u
            xa = expm(Aa * tk) @ np.concatenate([x0, [1.0]])
            out.append(xa[:n])
    return np.array(out)


def lqr(v):
    A, B = b.state_matrices(v)
    Bs = B[:, 1:2]
    S = solve_continuous_are(A, Bs, Q_BAL, R_BAL)
    K = np.linalg.solve(R_BAL, Bs.T @ S).ravel()
    # steady turn at lean phi: the lean equation without torque gives delta, the steer equation T
    m = b.matrices()
    Kv = P["g"] * m["K0"] + v * v * m["K2"]
    d_per_phi = -Kv[0, 0] / Kv[0, 1]
    T_per_phi = Kv[1, 0] + Kv[1, 1] * d_per_phi
    # u = -K x + N phi_ref holds the steady turn x_ss = (1, d, 0, 0) phi_ref
    N = K[0] + K[1] * d_per_phi + T_per_phi
    Acl = A - Bs @ K[None, :]
    return {"K": K.tolist(), "N": float(N), "d_per_phi": float(d_per_phi), "T_per_phi": float(T_per_phi),
            "closed_loop_poles": [[float(z.real), float(z.imag)] for z in np.linalg.eigvals(Acl)]}


def main():
    out: dict = {"$comment": "Written by design.py: reference numbers of the bicycle example (see design.py)."}
    m = b.matrices()
    out["matrices"] = {k: np.asarray(m[k]).tolist() for k in ("M", "C1", "K0", "K2")}
    out["matrix_error_vs_paper"] = {k: float(np.max(np.abs(np.asarray(m[k]) - np.array(v))))
                                    for k, v in b.PAPER_MATRICES.items()}
    t2 = b.load_table2()
    errs = []
    for row in t2["weave"]:
        z = weave_pair(row["v"])
        errs.append(max(abs(z.real - row["re"]), abs(z.imag - row["im"])))
    for row in t2["real"]:
        ev = np.sort(b.eigenvalues(row["v"]).real)
        # sorted real parts: castering first; capsize second below 5 m/s (the weave pair is
        # unstable there), the largest from 5 m/s on
        caps, cast = (ev[-1] if row["v"] >= 5 else ev[1]), ev[0]
        errs.append(max(abs(cast - row["castering"]), abs(caps - row["capsize"])))
    out["eigen_error_vs_table2"] = float(max(errs))
    vw = brentq(lambda v: weave_pair(v).real, 3.0, 5.5)
    vc = brentq(lambda v: np.max(b.eigenvalues(v).real), 5.5, 7.0)
    out["v_w"], out["v_c"] = vw, vc
    out["v_w_error"] = vw - t2["special"]["v_w"]
    out["v_c_error"] = vc - t2["special"]["v_c"]
    modes = {}
    for v in (3.0, 4.0, 4.6, 5.0, 6.0):
        z = weave_pair(v)
        wn = abs(z)
        real = sorted(e.real for e in b.eigenvalues(v) if abs(e.imag) < 1e-9)
        modes[f"{v:g}"] = {"weave": [float(z.real), float(z.imag)], "weave_wn": float(wn),
                           "weave_zeta": float(-z.real / wn), "real": real}
    out["modes"] = modes
    # linear responses from a lean rate (the paper's figure 4 start, and small starts)
    resp = {}
    for v, phid0, t_end in ((V_FIG4, PHID_FIG4, 5.0), (5.0, 0.05, 6.0), (8.0, 0.05, 12.0)):
        tt = np.arange(0.0, t_end + 1e-9, 0.5)
        X = response(v, np.array([0.0, 0.0, phid0, 0.0]), tt)
        resp[f"v{v:g}_phid{phid0:g}"] = {"t": tt.tolist(), "phi": X[:, 0].tolist(), "delta": X[:, 1].tolist(),
                                          "phid": X[:, 2].tolist(), "deltad": X[:, 3].tolist()}
    out["responses"] = resp
    out["balance"] = {"v": V_BAL, "lean_ref": LEAN_REF, "Q": np.diag(Q_BAL).tolist(), "R": float(R_BAL[0, 0]),
                      **lqr(V_BAL)}
    bal = out["balance"]
    d_ss = bal["d_per_phi"] * LEAN_REF
    bal["steady"] = {"phi": LEAN_REF, "delta": d_ss, "T": bal["T_per_phi"] * LEAN_REF,
                     "psid": V_BAL * d_ss * np.cos(P["lam"]) / P["w"],
                     "radius": P["w"] / (d_ss * np.cos(P["lam"]))}
    # static tyre loads and deflections (Hertz law F = k x (x/xref)^(1/2))
    mT, xT = m["mT"], m["xT"]
    NF = mT * P["g"] * xT / P["w"]
    NR = mT * P["g"] - NF
    defl = lambda N: (N * np.sqrt(CONTACT["xref"]) / CONTACT["k"]) ** (2.0 / 3.0)  # noqa: E731
    out["contact"] = {**CONTACT, "N_rear": NR, "N_front": NF, "delta_rear": defl(NR), "delta_front": defl(NF)}
    (HERE / "design.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"matrices vs paper (max abs error): {out['matrix_error_vs_paper']}")
    print(f"eigenvalues vs table 2: max error {out['eigen_error_vs_table2']:.2e}")
    print(f"weave speed {vw:.12f} (paper {t2['special']['v_w']}), capsize speed {vc:.12f} (paper {t2['special']['v_c']})")
    for k, md in modes.items():
        print(f"v = {k}: weave {md['weave'][0]:+.4f} +- {md['weave'][1]:.4f} i (wn {md['weave_wn']:.4f}, "
              f"zeta {md['weave_zeta']:+.4f}), real {np.round(md['real'], 4)}")
    print("LQR at 3 m/s: K", np.round(bal["K"], 3), "N", round(bal["N"], 3))
    print("closed-loop poles", np.round([complex(*z) for z in bal["closed_loop_poles"]], 3))
    print("steady turn", bal["steady"])
    print("static loads", out["contact"])


if __name__ == "__main__":
    main()
