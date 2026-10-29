# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Discrete LQR design for the `cube-3d` sample (plan 9.9).

A cube of side ``a`` balances on one corner (the pivot, a ball joint at the world origin)
with its body diagonal vertical. Three reaction wheels spin about the body axes ``x``, ``y``,
``z`` (the cube edges at the pivot); wheel ``i`` is mounted on the inside of the face opposite
the pivot corner along axis ``i`` (face ``x_i = a``), centred on the face, its centre ``D_INSET``
inside it, so the centre of mass stays on the body diagonal. The plant is the equation block
``library/CornerCube.jl``; this script holds an independent numpy replica of it.

States of the replica: the quaternion ``q`` (body to world), the body rates ``w`` and the
wheel rates relative to the body ``wr``; ``T`` is the shaft torque on the wheels (``em`` the motor torque, see ``rates``)

    R(q)  = rotation matrix of q,   g_b = R' [0, 0, -g]
    L     = Thc w + Thw (w + wr)                  (angular momentum about the pivot, body frame)
    w'    = Thc^-1 ( -w x L + r x m g_b - T )
    wr'   = T / Thw - w'
    T     = em - JM wr'      (JM: motor rotor inertia relative to the body, 1e-6)
    q'    = 1/2 q (x) [0, w]

``m`` is the total mass (structure + 3 wheels), ``r`` the CoM, ``Thc`` the inertia about the pivot
(structure, wheel masses by the parallel-axis theorem, wheel transverse inertia) without the wheels'
spin, ``Thw`` the inertia of each wheel about its own axis (rotor included).

Linearisation: central finite differences of the replica at the equilibrium (body diagonal
up, ``w = wr = 0``). The reduced state is

    z = [tilt (2), w (3), wr (3)]       tilt_k = e_k . up_b,   up_b = R' [0, 0, 1]

with ``e_1, e_2`` an orthonormal basis of the plane perpendicular to the equilibrium
diagonal ``n0 = (1, 1, 1)/sqrt 3``. The yaw about the vertical is not in ``z``: it does not
influence the other states. The vertical angular momentum ``n0 . (Thc w + Thw (w + wr))``
(about the pivot, a vertical force has no vertical torque) is conserved, so one mode of
``z`` is uncontrollable at eigenvalue 1 once discretised. The discrete Riccati equation is
solved on ``(Ad / rho, Bd / rho)`` with ``rho = 1.0005`` (the plan's trick), which moves
that mode inside the unit circle; the gain is applied to the true ``(Ad, Bd)``, where the
mode stays at 1 (marginal, never excited because the vertical momentum starts at 0).

The motor is the quasi-static DC motor of the model: ``T = k (u - k wr) / R`` (the winding
inductance ``L / R = 0.1 ms`` is 20 times shorter than the 2 ms sample period; the
non-linear simulation keeps it). ``u`` is clamped to +-``U_MAX``.

The script then simulates the non-linear closed loop (Radau between samples, zero-order
hold, clamp) and prints the numbers the checks in ``expected.json`` use. It writes ``K``
(3 x 8, ``u = -K z``) into the ``K`` parameter of the controller node of the model
documents.

Run it with ``uv run examples/cube-3d/design/design.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm, solve_discrete_are

ROOT = Path(__file__).resolve().parent.parent
MODELS = [ROOT / "models" / f"{name}.bgmodel.json" for name in ("cube-3d", "cube-3d-mb", "cube-3d-mb-soft")]

#: Plant parameters, identical to the model document.
M_S = 0.18                    # kg     cube structure (frame, electronics, motors), wheels excluded
M_W = 0.08                    # kg     one wheel (steel rim wheel, R_W_DISC x H_W_DISC)
A_SIDE = 0.15                 # m      cube side
G = 9.81                      # m/s^2
THS = 1.125e-3               # kg m^2 structure inertia about its centre (thin cubic shell 5/18 m a^2)
THW = 1.9e-4                  # kg m^2 wheel inertia about its axis (rotor included), 0.79 m R^2: rim-heavy
R_WHEEL = 0.055               # m      wheel radius
H_WHEEL = 0.012               # m      wheel thickness
GAP = 0.004                   # m      mounting gap between wheel and inner face
D_INSET = H_WHEEL / 2 + GAP  # m      wheel centre inset from its face = 0.010 m
THWT = 9.6e-5                 # kg m^2 wheel inertia about a diameter, THW/2 + M_W H^2/12 = 9.596e-5 rounded
JM = 1.0e-6                   # kg m^2 rotor inertia of the motor model (relative to the body, see below)
K_T = 0.0335                  # N m/A  motor constant
R_W = 1.0                     # Ohm
L_W = 1.0e-4                  # H
TILT0 = np.radians(2.0)       # rad    initial tilt of the body diagonal
TS = 2.0e-3                   # s      sample period
U_MAX = 12.0                  # V
T_END = 4.0                   # s
RHO = 1.0005

def _mass_model() -> tuple[float, np.ndarray, np.ndarray, list[np.ndarray]]:
    """Total mass, CoM vector r and inertia about the pivot (body frame) with the wheels' spin excluded.

    Built generically (parallel-axis theorem per body), independent of the closed form in
    `CornerCube.jl`. Wheel i is centred on the face x_i = a (opposite the pivot corner along axis i), its centre
    ``D_INSET`` inside the face. Its transverse inertia ``THWT`` acts about the two axes
    perpendicular to e_i; the axial part ``THW`` is `Lw` in the dynamics.
    """
    eye = np.eye(3)
    centre = 0.5 * A_SIDE * np.ones(3)
    pos = [0.5 * A_SIDE * np.ones(3) for _ in range(3)]
    for i in range(3):
        pos[i][i] = A_SIDE - D_INSET
    m_tot = M_S + 3 * M_W
    r = (M_S * centre + M_W * sum(pos)) / m_tot
    thc = THS * eye + M_S * (centre @ centre * eye - np.outer(centre, centre))
    for i, p in enumerate(pos):
        e = np.zeros(3)
        e[i] = 1.0
        thc = thc + M_W * (p @ p * eye - np.outer(p, p)) + THWT * (eye - np.outer(e, e))
    return m_tot, r, thc, pos


M, R_VEC, THC, WHEEL_POS = _mass_model()
THC_INV = np.linalg.inv(THC)
N0 = np.ones(3) / np.sqrt(3.0)

#: Weights (Bryson-style, q_i = 1/sigma_i^2).
SIG_TILT, SIG_W, SIG_WR, SIG_U = 0.02, 0.2, 40.0, U_MAX
Q = np.diag([1 / SIG_TILT**2] * 2 + [1 / SIG_W**2] * 3 + [1 / SIG_WR**2] * 3)
RW = np.eye(3) / SIG_U**2


def rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [w * w + x * x - y * y - z * z, 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), w * w - x * x + y * y - z * z, 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), w * w - x * x - y * y + z * z],
        ]
    )


def qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    return np.concatenate(([np.cos(angle / 2)], np.sin(angle / 2) * axis))


#: Equilibrium: R q_eq maps the body diagonal n0 onto the world z axis.
Q_EQ = axis_angle(np.array([1.0, -1.0, 0.0]), np.arccos(1.0 / np.sqrt(3.0)))
#: Start: the equilibrium tilted by TILT0 about the world x axis.
Q_START = qmul(axis_angle(np.array([1.0, 0.0, 0.0]), TILT0), Q_EQ)


def rates(x: np.ndarray, em: np.ndarray) -> np.ndarray:
    """Derivative of x = [q (4), w (3), wr (3)] for the electromagnetic motor torques ``em``.

    The shaft torque on the wheel is ``T = em - JM wr'`` (the motor rotor, inertia ``JM``, spins
    at the relative rate ``wr``), so ``w'``, ``wr'`` and ``T`` solve one 9 x 9 linear system:

        Thc w' + T = f,   f = -w x L + r x m g_b
        Thw (w' + wr') - T = 0
        JM wr' + T = em
    """
    q, w, wr = x[:4], x[4:7], x[7:10]
    g_b = rot(q).T @ np.array([0.0, 0.0, -G])
    mom = THC @ w + THW * (w + wr)
    f = -np.cross(w, mom) + np.cross(R_VEC, M * g_b)
    eye = np.eye(3)
    lhs = np.block(
        [
            [THC, np.zeros((3, 3)), eye],
            [THW * eye, THW * eye, -eye],
            [np.zeros((3, 3)), JM * eye, eye],
        ]
    )
    sol = np.linalg.solve(lhs, np.concatenate((f, np.zeros(3), em)))
    qdot = 0.5 * qmul(q, np.concatenate(([0.0], w)))
    return np.concatenate((qdot, sol[:3], sol[3:6]))


def _basis() -> np.ndarray:
    e1 = np.cross(N0, [0.0, 0.0, 1.0])
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(N0, e1)
    return np.array([e1, e2])


E_BASIS = _basis()


def reduced(x: np.ndarray) -> np.ndarray:
    """z = [tilt (2), w (3), wr (3)]."""
    up_b = rot(x[:4]).T @ np.array([0.0, 0.0, 1.0])
    return np.concatenate((E_BASIS @ up_b, x[4:10]))


def linearise() -> tuple[np.ndarray, np.ndarray]:
    """(A, B) of z' = A z + B em, from finite differences of the replica."""
    x0 = np.concatenate((Q_EQ, np.zeros(6)))
    eps = 1e-6
    a10 = np.zeros((10, 10))
    for j in range(10):
        d = np.zeros(10)
        d[j] = eps
        a10[:, j] = (rates(x0 + d, np.zeros(3)) - rates(x0 - d, np.zeros(3))) / (2 * eps)
    b10 = np.zeros((10, 3))
    for j in range(3):
        d = np.zeros(3)
        d[j] = eps
        b10[:, j] = (rates(x0, d) - rates(x0, -d)) / (2 * eps)
    jz = np.zeros((8, 10))
    for j in range(10):
        d = np.zeros(10)
        d[j] = eps
        jz[:, j] = (reduced(x0 + d) - reduced(x0 - d)) / (2 * eps)
    lift = np.linalg.pinv(jz)
    assert np.allclose(jz @ lift, np.eye(8), atol=1e-9)
    return jz @ a10 @ lift, jz @ b10


def motor_matrices(a_t: np.ndarray, b_t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fold in the quasi-static motor T = k (u - k wr)/R: z' = A z + B u."""
    sel = np.zeros((3, 8))
    sel[:, 5:8] = np.eye(3)
    return a_t - (K_T**2 / R_W) * b_t @ sel, (K_T / R_W) * b_t


def discretise(a_mat: np.ndarray, b_mat: np.ndarray, ts: float) -> tuple[np.ndarray, np.ndarray]:
    n, m = b_mat.shape
    aug = np.zeros((n + m, n + m))
    aug[:n, :n] = a_mat
    aug[:n, n:] = b_mat
    e = expm(aug * ts)
    return e[:n, :n], e[:n, n:]


def lqr() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(K, Ad, Bd, A) with u[k] = -K z[k]; the DARE is solved on (Ad/rho, Bd/rho)."""
    a_t, b_t = linearise()
    a, b = motor_matrices(a_t, b_t)
    ad, bd = discretise(a, b, TS)
    ar, br = ad / RHO, bd / RHO
    p = solve_discrete_are(ar, br, Q, RW)
    k = np.linalg.solve(RW + br.T @ p @ br, br.T @ p @ ar)
    return k, ad, bd, a


def simulate(k: np.ndarray) -> dict[str, np.ndarray]:
    """Non-linear closed loop with the winding inductance, ZOH and the clamp."""

    def f(_t: float, s: np.ndarray, u: np.ndarray) -> np.ndarray:
        x, i = s[:10], s[10:13]
        di = (u - R_W * i - K_T * x[7:10]) / L_W
        return np.concatenate((rates(x, K_T * i), di))

    state = np.concatenate((Q_START, np.zeros(6), np.zeros(3)))
    rows = []
    n_ticks = int(round(T_END / TS))
    t = 0.0
    u = np.zeros(3)  # the declared 0 V is held until the first sample at t = Ts
    for tick in range(n_ticks + 1):
        rows.append((t, *state, *u))
        if tick == n_ticks:
            break
        sol = solve_ivp(f, (t, t + TS), state, args=(u,), method="Radau", rtol=1e-9,
                        atol=1e-12, t_eval=np.linspace(t, t + TS, 5))
        for j in range(1, sol.t.size - 1):
            rows.append((sol.t[j], *sol.y[:, j], *u))
        state = sol.y[:, -1]
        t += TS
        u = np.clip(-k @ reduced(state[:10]), -U_MAX, U_MAX)
    arr = np.array(rows)
    out = {"t": arr[:, 0], "x": arr[:, 1:11], "i": arr[:, 11:14], "u": arr[:, 14:17]}
    up = np.array([rot(q).T @ np.array([0, 0, 1.0]) for q in out["x"][:, :4]])
    out["tilt"] = np.arccos(np.clip(up @ N0, -1.0, 1.0))
    out["hz"] = np.array([(rot(x[:4]) @ (THC @ x[4:7] + THW * (x[4:7] + x[7:10])))[2] for x in out["x"]])
    return out


def write_gain(path: Path, k: np.ndarray) -> None:
    """Write K (3 x 8, Julia matrix literal) into the `K` parameter of the controller node."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    rows = "; ".join(" ".join(f"{v:.9g}" for v in row) for row in k)
    literal = f"[{rows}]"
    pattern = r'("K":\s*")[^"]*(")'
    text, count = re.subn(pattern, lambda mm: f"{mm.group(1)}{literal}{mm.group(2)}", text)
    if count != 1:
        raise SystemExit(f"expected exactly one `K` parameter in {path}, found {count}")
    json.loads(text)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    k, ad, bd, a = lqr()
    closed = np.linalg.eigvals(ad - bd @ k)
    print(f"m {M:.4f} kg, r {R_VEC}, wheel centres {WHEEL_POS}\n"
          f"Thc diag {np.diag(THC)}, off {THC[0, 1]:.9g}; Q_EQ {Q_EQ}")
    print(f"open-loop eigenvalues (continuous): {np.sort_complex(np.linalg.eigvals(a))}")
    print(f"K (u = -K z, z = [tilt1, tilt2, w1..3, wr1..3]) =\n"
          f"{np.array2string(k, precision=4, max_line_width=140)}")
    print(f"closed-loop eigenvalues (discrete): {np.sort_complex(closed)}")
    mags = np.sort(np.abs(closed))
    print(f"closed-loop |eig| max (excluding the vertical-momentum mode): "
          f"{mags[-2]:.6f}; marginal mode {mags[-1]:.9f}")
    print(f"closed-loop (ln z / Ts): {np.log(closed.astype(complex)) / TS}")
    out = simulate(k)
    t, x, u = out["t"], out["x"], out["u"]
    print(f"\nnon-linear reference closed loop (Radau, ZOH {TS * 1e3:g} ms, clamp +-{U_MAX:g} V):")
    print(f"  initial tilt {np.degrees(out['tilt'][0]):.6f} deg, quaternion norm error max "
          f"{np.abs(np.linalg.norm(x[:, :4], axis=1) - 1).max():.3e}")
    after = t >= 3.0
    print(f"  tilt max t>=3 s = {np.degrees(out['tilt'][after].max()):.6f} deg; tilt(3 s) = "
          f"{np.degrees(np.interp(3.0, t, out['tilt'])):.6f} deg; "
          f"tilt(4 s) = {np.degrees(out['tilt'][-1]):.6e} deg")
    print(f"  max |u| = {np.abs(u).max():.4f} V; max |wr| = {np.abs(x[:, 7:10]).max():.3f} rad/s "
          f"(per wheel {np.abs(x[:, 7:10]).max(axis=0)}); max |w_abs| = "
          f"{np.abs(x[:, 7:10] + x[:, 4:7]).max():.3f}")
    print(f"  vertical momentum H_z: initial {out['hz'][0]:.6e}, max|H_z - H_z(0)| = "
          f"{np.abs(out['hz'] - out['hz'][0]).max():.3e}")
    inside = np.where(np.degrees(out["tilt"]) > 0.5)[0].max() + 1
    print(f"  tilt stays under 0.5 deg from t = {t[inside]:.3f} s")
    for tc in (0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0):
        j = min(int(np.searchsorted(t, tc)), t.size - 1)
        print(f"    t = {tc:4.2f} s  tilt = {np.degrees(out['tilt'][j]):+.5f} deg  wr = "
              f"{np.round(x[j, 7:10], 3)}  u = {np.round(u[j], 3)}")
    for path in MODELS:
        write_gain(path, k)
        print(f"wrote K into {path}" if path.exists() else f"(no {path.name} yet)")


if __name__ == "__main__":
    main()
