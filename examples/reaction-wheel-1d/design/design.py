# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Discrete LQR design for the `reaction-wheel-1d` sample (plan 9.7).

The plant is a cube balanced on one edge (inertia ``J`` about the edge, centre of mass a
distance ``l`` from it, wheel excluded) with a brushed DC motor whose housing sits on the
cube and whose shaft drives a wheel (``J_w`` about its own axis, rotor included): the
stdlib ``drives/ReactionWheel``, which delivers the reaction torque to the housing and
puts the back-EMF on the *relative* rate (the stdlib ``DCMotor`` has no stator reaction,
see the README). With ``theta`` the cube angle from
upright, ``w_rel`` the wheel speed relative to the cube and ``tau`` the motor torque on the
wheel (the reaction ``-tau`` acts on the cube), the equations of the model are

    J theta''                  = m g l sin(theta) - tau
    J_w (theta'' + w_rel')     = tau
    L i' + R i + k w_rel       = u            tau = k i

The wheel carries no gravity term of its own (its mass is part of ``m``). Because the
electrical time constant ``L/R`` = 0.1 ms is 20 times shorter than the 2 ms sample
period, the design uses the quasi-static current ``i = (u - k w_rel) / R``; the
non-linear simulation below keeps ``L``.

Linearised at upright (``sin(theta) = theta``) with ``x = [theta, theta', w_rel]``:

    a = m g l
    A = [[0,    1,  0                          ],
         [a/J,  0,  k^2/(R J)                  ],
         [-a/J, 0, -(k^2/R)(1/J_w + 1/J)       ]]
    B = [0, -k/(R J), (k/R)(1/J_w + 1/J)]'

``A`` and ``B`` are discretised exactly with a zero-order hold (matrix exponential of the
augmented matrix) at ``Ts = 2 ms``, and ``scipy.linalg.solve_discrete_are`` gives
``K = (R + B'PB)^-1 B'PA`` for ``u[k] = -K x[k]``, the law the firmware ``LQR`` block
(`library/LQR.jl`) applies, clamped to +-12 V. The controller reads the sampled state at
each tick and holds ``u`` until the next one, which is exactly the ZOH of the design.

Weights, with the Bryson normalisation ``q_i = 1/sigma_i^2``:

    sigma_theta  = 0.02 rad     q_theta  = 2.5e3 - the angle is the thing to hold
    sigma_thetad = 0.2 rad/s    q_thetad = 25
    sigma_w      = 10 rad/s     q_w      = 1e-2 - the wheel speed is cheap to hold small
                                                  so the slow wheel pole is pulled up
    sigma_u      = 12 V         r        = 1/144

The script then simulates the *non-linear* closed loop (sin(theta), the winding
inductance, the ZOH sampling, the +-12 V clamp) and prints the numbers the checks in
``expected.json`` use. It writes ``K`` into the three ``K_*`` parameters of the model
document (the committed literals are its output).

Run it with ``uv run examples/reaction-wheel-1d/design/design.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm, solve_discrete_are

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "reaction-wheel-1d.bgmodel.json"

#: Plant parameters, identical to the model document.
J = 4.0e-3      # kg m^2  cube inertia about the edge
M = 0.6         # kg      cube mass
L_CG = 0.085    # m       edge to centre of mass
G = 9.81        # m/s^2
J_W = 6.0e-4    # kg m^2  wheel inertia about its axis
K_T = 0.0335    # N m/A   motor constant (= V s/rad)
R_W = 1.0       # Ohm     winding resistance
L_W = 1.0e-4    # H       winding inductance
THETA0 = 0.05   # rad     initial tilt
TS = 2.0e-3     # s       sample period
U_MAX = 12.0    # V       voltage limit
T_END = 4.0     # s       run length

#: Weights (see the module docstring).
Q = np.diag([2.5e3, 25.0, 1.0e-2])
R = np.array([[1.0 / U_MAX**2]])


def linear_model() -> tuple[np.ndarray, np.ndarray]:
    """The continuous state matrix and input vector at upright (quasi-static current)."""
    a = M * G * L_CG
    inv = 1.0 / J_W + 1.0 / J
    a_mat = np.array(
        [
            [0.0, 1.0, 0.0],
            [a / J, 0.0, K_T**2 / (R_W * J)],
            [-a / J, 0.0, -(K_T**2 / R_W) * inv],
        ]
    )
    b_vec = np.array([0.0, -K_T / (R_W * J), (K_T / R_W) * inv])
    return a_mat, b_vec


def discretise(a_mat: np.ndarray, b_vec: np.ndarray, ts: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact zero-order-hold discretisation."""
    n = a_mat.shape[0]
    aug = np.zeros((n + 1, n + 1))
    aug[:n, :n] = a_mat
    aug[:n, n] = b_vec
    e = expm(aug * ts)
    return e[:n, :n], e[:n, n]


def lqr() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (K, Ad, Bd) with u[k] = -K x[k]."""
    a_mat, b_vec = linear_model()
    ad, bd = discretise(a_mat, b_vec, TS)
    bcol = bd.reshape(-1, 1)
    p = solve_discrete_are(ad, bcol, Q, R)
    k = np.linalg.solve(R + bcol.T @ p @ bcol, bcol.T @ p @ ad).ravel()
    return k, ad, bd


def simulate(k: np.ndarray) -> np.ndarray:
    """Non-linear closed loop: rows (t, theta, theta', w_rel, i, u). ZOH, clamp, winding L."""
    a = M * G * L_CG
    inv = 1.0 / J_W + 1.0 / J

    def f(_t: float, s: np.ndarray, u: float) -> list[float]:
        th, thd, w, i = s
        tau = K_T * i
        thdd = (a * np.sin(th) - tau) / J
        wd = tau * inv - a * np.sin(th) / J
        di = (u - R_W * i - K_T * w) / L_W
        return [thd, thdd, wd, di]

    state = np.array([THETA0, 0.0, 0.0, 0.0])
    # The firmware's declared 0 V output is held over the first sample period, like the
    # model (the first tick is at t = Ts).
    rows = []
    n_ticks = int(round(T_END / TS))
    t = 0.0
    u = 0.0
    for tick in range(n_ticks + 1):
        rows.append((t, *state, u))
        if tick == n_ticks:
            break
        sol = solve_ivp(f, (t, t + TS), state, args=(u,), method="Radau",
                        rtol=1e-9, atol=1e-12, t_eval=np.linspace(t, t + TS, 11))
        for j in range(1, sol.t.size - 1):
            rows.append((sol.t[j], *sol.y[:, j], u))
        state = sol.y[:, -1]
        t += TS
        u = float(np.clip(-k @ state[:3], -U_MAX, U_MAX))
    return np.array(rows)


def write_gains(path: Path, k: np.ndarray) -> None:
    """Write K into the three ``K_*`` parameters of the model document."""
    text = path.read_text(encoding="utf-8")
    for name, value in zip(("K_theta", "K_thetadot", "K_wheel"), k):
        pattern = rf'("{name}":\s*")[^"]*(")'
        text, count = re.subn(pattern, lambda mm: f"{mm.group(1)}{value:.6f}{mm.group(2)}", text)
        if count != 1:
            raise SystemExit(f"expected exactly one `{name}` parameter in {path}, found {count}")
    json.loads(text)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    a_mat, b_vec = linear_model()
    k, ad, bd = lqr()
    closed = np.linalg.eigvals(ad - np.outer(bd, k))
    print(f"plant: J={J} kg m^2, m={M} kg, l={L_CG} m, J_w={J_W} kg m^2, k={K_T}, "
          f"R={R_W} Ohm, L={L_W} H, Ts={TS} s")
    print(f"open-loop eigenvalues (continuous): {np.linalg.eigvals(a_mat)}")
    print(f"Q = diag({np.diag(Q).tolist()}), R = {R[0, 0]:.6g}")
    print(f"K = {k}   (u = -K [theta, theta', w_rel])")
    print(f"closed-loop poles (discrete):   {closed}")
    print(f"closed-loop poles (ln z / Ts):  {np.log(closed.astype(complex)) / TS}")
    print(f"u at the initial tilt: {-k @ np.array([THETA0, 0.0, 0.0]):.3f} V (limit {U_MAX} V)")

    out = simulate(k)
    t, th, thd, w, _i, u = (out[:, c] for c in range(6))
    after = t >= 2.0
    w_abs = w + thd
    phi = np.concatenate(([0.0], np.cumsum(0.5 * (w[1:] + w[:-1]) * np.diff(t))))
    outside = np.where(np.abs(th) > np.radians(0.2))[0].max() + 1
    print(f"\nnon-linear reference closed loop (Radau, ZOH {TS * 1e3:g} ms, clamp +-{U_MAX:g} V):")
    print(f"  max |u|             = {np.abs(u).max():.6f} V")
    print(f"  max |w_rel|         = {np.abs(w).max():.4f} rad/s")
    print(f"  max |w_abs|         = {np.abs(w_abs).max():.4f} rad/s (limit 300)")
    print(f"  max |theta|         = {np.abs(th).max():.6f} rad = {np.degrees(np.abs(th).max()):.5f} deg")
    print(f"  |theta| max t>=2 s  = {np.abs(th[after]).max():.6e} rad = "
          f"{np.degrees(np.abs(th[after]).max()):.6f} deg (limit 0.2)")
    print(f"  |theta| stays under 0.2 deg from t = {t[outside]:.3f} s")
    print(f"  theta(4 s)          = {th[-1]:+.6e} rad, w_rel(4 s) = {w[-1]:+.4f} rad/s, "
          f"wheel angle(4 s) = {phi[-1]:+.4f} rad")
    print("  cursor values:")
    for tc in (0.1, 0.25, 0.5, 1.0, 2.0, 4.0):
        print(f"    t = {tc:4.2f} s  theta = {np.interp(tc, t, th):+.6f} rad  "
              f"w_rel = {np.interp(tc, t, w):+.4f} rad/s  u = {np.interp(tc, t, u):+.4f} V")

    if MODEL.exists():
        write_gains(MODEL, k)
        print(f"\nwrote K into {MODEL}")


if __name__ == "__main__":
    main()
