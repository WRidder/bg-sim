# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Geometry, target attitudes and controller tuning for the `tetra-3d` example.

A regular tetrahedron (edge ``L``) with one reaction wheel per face, the wheel axis along the
outward face normal. Body frame (origin = centre of mass = centre of the circumscribed sphere):

    apex            v4 = (0, 0, R)
    base vertices   v1 = (0, rho, -r), v2 = (rho cos 210, rho sin 210, -r), v3 = (rho cos 330, rho sin 330, -r)

with ``R = L sqrt(6)/4`` (circumradius), ``r = R/3`` (inradius, the face centroid distance) and
``rho = L/sqrt 3`` (circumradius of the base triangle). The tetrahedron rests on the base face
(z axis up, so ``u = R^T e_z = (0, 0, 1)`` with ``u`` the world vertical seen from the body).
The wheel on the face opposite to base vertex ``v_j`` has the axis ``a_j = -v_j / R``
(j = 1..3) and the base wheel has ``a_4 = (0, 0, -1)``. Then ``sum a_k = 0``, ``A A^T = 4/3 I``
(``A = [a_1 .. a_4]``) and the null direction of ``A`` is ``n = (1, 1, 1, 1)/2``.

Targets (the world vertical seen from the body ``u``):

    face      u = (0, 0, 1)                         CoM height r
    edge      v2-v3, CoM above the edge:  u = -(v2+v3)/|v2+v3|   tilt acos(u_z) = 54.7356 deg, CoM height L/(2 sqrt 2)
    vertex    on v3, CoM above it:        u = -v3/R = a_3        angle to the face normal  acos(1/3) = 70.53 deg, CoM height R

The script prints these, simulates a replica of the closed loop (rigid body on the contact
feature, i.e. a hinge about the edge for t < t2 and a ball joint at v3 after that, wheels with an
ideal current loop, 1 ms zero-order-hold firmware equal to `library/TipSequencer.jl` and
`library/Allocator.jl`) and prints peak wheel speeds, torques and voltages. The numbers it prints
are the starting point for the checks of `expected.json`.

Run it with ``uv run examples/tetra-3d/design/design.py``.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

G0 = 9.81
# ------------------------------------------------------------------ geometry and masses
L = 0.25                      # edge length (m)
R = L * np.sqrt(6) / 4        # circumradius
RIN = R / 3                   # inradius = distance CoM - face centroid
RHO = L / np.sqrt(3)          # circumradius of the base triangle
M_BODY = 0.4                  # shell (kg)
M_WHEEL = 0.25                # each wheel (kg)
M_TOT = M_BODY + 4 * M_WHEEL
J_BODY = M_BODY * L**2 / 20   # solid regular tetrahedron: isotropic
DW = 0.035                    # wheel centre distance from the CoM along the face normal (m)
JA, JT = 2.0e-3, 1.0e-3        # wheel axial / transverse inertia (kg m^2)
KT, RM, VBUS = 0.1, 0.4, 48.0 # motor torque constant (N m/A, = V s/rad), resistance (ohm), bus (V)
TAU_MAX = 1.6                 # allocator torque limit per wheel (N m)

PHI = np.radians([90.0, 210.0, 330.0])
VERT = np.array([[RHO * np.cos(p), RHO * np.sin(p), -RIN] for p in PHI] + [[0, 0, R]])
AXES = np.array([-VERT[j] / R for j in range(3)] + [[0.0, 0.0, -1.0]])   # (4, 3), rows a_k
A = AXES.T                                                                 # 3 x 4

U_FACE = np.array([0.0, 0.0, 1.0])
_m = 0.5 * (VERT[1] + VERT[2])
U_EDGE = -_m / np.linalg.norm(_m)
U_VERT = -VERT[2] / R
R_EDGE = -_m                  # CoM - pivot, body frame
R_VERT = -VERT[2]


def configure(**kw: float) -> None:
    """Change the geometry/mass parameters (L, M_BODY, M_WHEEL, DW, JA, JT, TAU_MAX) and rebuild the derived data."""
    global L, R, RIN, RHO, M_BODY, M_WHEEL, M_TOT, J_BODY, DW, JA, JT, TAU_MAX
    global VERT, AXES, A, U_EDGE, U_VERT, R_EDGE, R_VERT
    for key, value in kw.items():
        globals()[key] = value
    R = L * np.sqrt(6) / 4
    RIN = R / 3
    RHO = L / np.sqrt(3)
    M_TOT = M_BODY + 4 * M_WHEEL
    J_BODY = M_BODY * L**2 / 20
    VERT = np.array([[RHO * np.cos(p), RHO * np.sin(p), -RIN] for p in PHI] + [[0, 0, R]])
    AXES = np.array([-VERT[j] / R for j in range(3)] + [[0.0, 0.0, -1.0]])
    A = AXES.T
    mid = 0.5 * (VERT[1] + VERT[2])
    U_EDGE = -mid / np.linalg.norm(mid)
    U_VERT = -VERT[2] / R
    R_EDGE = -mid
    R_VERT = -VERT[2]


# default firmware (TipSequencer parameters)
FW = dict(t1=0.4, t2=1.9, Tf=0.15, Tr1=0.5, Tr2=0.7, Kp=5.0, Kd=1.2, Ky=0.05, fb_max=0.8, lam=0.005)


def inertia_eff() -> np.ndarray:
    """Inertia about the CoM of the shell and the wheel masses, wheel axial spin excluded."""
    inertia = np.eye(3) * J_BODY
    for a in AXES:
        p = DW * a
        inertia += M_WHEEL * (p @ p * np.eye(3) - np.outer(p, p)) + JT * (np.eye(3) - np.outer(a, a))
    return inertia


def wheel_quats() -> np.ndarray:
    """Quaternion (w x y z) of each wheel frame in the body frame: z axis along a_k."""
    out = []
    for a in AXES:
        axis = np.cross([0.0, 0.0, 1.0], a)
        s = np.linalg.norm(axis)
        if s < 1e-12:
            out.append([0.0, 1.0, 0.0, 0.0] if a[2] < 0 else [1.0, 0.0, 0.0, 0.0])
        else:
            ang = np.arctan2(s, a[2])
            n = axis / s
            out.append([np.cos(ang / 2), *(np.sin(ang / 2) * n)])
    return np.array(out)


def quat_rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x**3 * (10 - 15 * x + 6 * x * x)


def reference(t: float, fw: dict) -> tuple[np.ndarray, np.ndarray, float, float, int]:
    """(u_ref, lever, kff, kb, phase) as in TipSequencer."""
    t1, t2, Tf, Tr1, Tr2 = fw["t1"], fw["t2"], fw["Tf"], fw["Tr1"], fw["Tr2"]
    q0, q1, s, rk, rv, ph = U_FACE, U_FACE, 0.0, 0.0, 0.0, 0
    if t >= t1:
        ph, rk, q1 = 1, min((t - t1) / Tf, 1.0), U_EDGE
        if t >= t1 + Tf:
            s = smooth((t - t1 - Tf) / Tr1)
        if t >= t1 + Tf + Tr1:
            ph = 2
    if t >= t2:
        ph, q0, q1, rk, s = 3, U_EDGE, U_VERT, 1.0, 0.0
        rv = min((t - t2) / Tf, 1.0)
        if t >= t2 + Tf:
            s = smooth((t - t2 - Tf) / Tr2)
        if t >= t2 + Tf + Tr2:
            ph = 4
    b = (1 - s) * q0 + s * q1
    return b / np.linalg.norm(b), (1 - rv) * R_EDGE + rv * R_VERT, rk, rv, ph


def simulate(fw: dict | None = None, t_end: float = 3.8, tau_max: float | None = None, ts: float = 1e-3) -> dict:
    fw = {**FW, **(fw or {})}
    tau_max = TAU_MAX if tau_max is None else tau_max
    ieff = inertia_eff()
    q = np.array([1.0, 0, 0, 0])
    w = np.zeros(3)
    wr = np.zeros(4)
    pu_prev = U_FACE.copy()
    log = []
    n = int(round(t_end / ts))
    for k in range(n + 1):
        t = k * ts
        rot = quat_rot(q / np.linalg.norm(q))
        u = rot.T @ np.array([0, 0, 1.0])
        uref, lever, rk, rv, ph = reference(t, fw)
        wref = np.cross((uref - pu_prev) / ts, uref)
        pu_prev = uref
        ff = rk * M_TOT * G0 * np.cross(lever, u)
        ec = np.cross(uref, u)
        wu = w @ u
        p = fw["Kp"] * ec + fw["Kd"] * (wref - (w - wu * u)) - fw["Ky"] * wu * u
        pn = np.sqrt(p @ p + 1e-18)
        p = p * (fw["fb_max"] / pn if pn > fw["fb_max"] else 1.0)
        h = JA * AXES.T @ wr
        cmd = ff + p + np.cross(w, h)
        base = -(0.75) * A.T @ cmd
        room = tau_max - 0.5 * abs(fw["lam"])
        mx = np.max(np.abs(base))
        sc = room / mx if mx > room else 1.0
        tau = sc * base + 0.5 * fw["lam"] * np.ones(4)
        log.append([t, *u, *w, *wr, *tau, ph, sc])
        if k == n:
            break
        if t < fw["t1"]:
            continue_rest = True
        else:
            continue_rest = False
        hinge = t < fw["t2"]

        def rhs(_t, y, tau=tau, hinge=hinge):
            qq, ww, wrr = y[:4], y[4:7], y[7:11]
            rr = quat_rot(qq / np.linalg.norm(qq))
            uu = rr.T @ np.array([0, 0, 1.0])
            if hinge:
                ww = np.array([ww[0], 0.0, 0.0])
                r_ = R_EDGE
            else:
                r_ = R_VERT
            ieff_p = ieff + M_TOT * (r_ @ r_ * np.eye(3) - np.outer(r_, r_))
            ip = ieff_p + JA * (AXES.T @ AXES)
            hh = ip @ ww + JA * AXES.T @ wrr
            rhs_t = -AXES.T @ tau - np.cross(ww, hh) - M_TOT * G0 * np.cross(r_, uu)
            if hinge:
                dw = np.zeros(3)
                dw[0] = rhs_t[0] / ieff_p[0, 0]
            else:
                dw = np.linalg.solve(ieff_p, rhs_t)
            dwr = tau / JA - AXES @ dw
            dq = 0.5 * np.array([
                -qq[1] * ww[0] - qq[2] * ww[1] - qq[3] * ww[2],
                qq[0] * ww[0] + qq[2] * ww[2] - qq[3] * ww[1],
                qq[0] * ww[1] - qq[1] * ww[2] + qq[3] * ww[0],
                qq[0] * ww[2] + qq[1] * ww[1] - qq[2] * ww[0],
            ])
            return np.concatenate([dq, dw, dwr])

        if continue_rest:
            continue
        sol = solve_ivp(rhs, (t, t + ts), np.concatenate([q, w, wr]), rtol=1e-9, atol=1e-11)
        y = sol.y[:, -1]
        q, w, wr = y[:4] / np.linalg.norm(y[:4]), y[4:7], y[7:11]
        if hinge:
            w = np.array([w[0], 0.0, 0.0])
    return {"log": np.array(log), "fw": fw}


def report(res: dict) -> None:
    lg = res["log"]
    t, u, wr, tau = lg[:, 0], lg[:, 1:4], lg[:, 7:11], lg[:, 11:15]
    fw = res["fw"]
    for name, tt, tgt in (("edge", fw["t2"] - 0.05, U_EDGE), ("vertex", t[-1], U_VERT)):
        i = np.searchsorted(t, tt)
        err = np.degrees(np.arccos(np.clip(u[i] @ tgt, -1, 1)))
        print(f"{name}: u = {u[i].round(4)}  target {tgt.round(4)}  error {err:.3f} deg at t = {t[i]:.2f}")
    print("peak |wheel speed| rad/s:", np.abs(wr).max(axis=0).round(1), " peak torque:", np.abs(tau).max(axis=0).round(3))
    volt = np.abs(RM * tau / KT + KT * wr)
    print("peak voltage per wheel V:", volt.max(axis=0).round(1), " min scale:", lg[:, 16].min().round(3))


if __name__ == "__main__":
    print(f"L = {L} m  R = {R:.5f}  r = {RIN:.5f}  rho = {RHO:.5f}  m_tot = {M_TOT} kg  J_body = {J_BODY:.4e}")
    print("CoM height: face", round(RIN, 5), " edge", round(L / (2 * np.sqrt(2)), 5), " vertex", round(R, 5))
    print("u_edge", U_EDGE.round(5), "tilt", np.degrees(np.arccos(U_EDGE[2])).round(4), "deg")
    print("u_vertex", U_VERT.round(5), "angle to face normal", np.degrees(np.arccos(U_VERT[2])).round(4), "deg")
    print("A A^T =", (A @ A.T).round(12).tolist(), " A n =", (A @ np.ones(4) / 2).round(12))
    print("I_eff diag", np.diag(inertia_eff()).round(6))
    report(simulate())
