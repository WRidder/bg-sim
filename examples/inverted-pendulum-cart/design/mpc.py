# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the constrained MPC for the `inverted-pendulum-cart` sample.

The MPC uses the same linearised cart-pole as `design/design.py`, the same state and
input weights, a 25-sample (25 ms) horizon and the terminal Riccati cost.  It minimises

    sum_{k=0}^{N-1} (x_k' Q x_k + u_k' R u_k) + x_N' P x_N

subject to the actuator magnitude |u_k| <= 20 N and the slew rate |u_k - u_{k-1}| <= 0.2 N
per 1 ms tick (200 N/s).  The decision variable is the increment sequence dU; the
absolute force is U = u_prev*1 + L*dU.  The box-constrained QP is solved online by ADMM,

    Uc = (Hd + rho I)^-1 (rho (z - y) - fd)
    z  = clamp(Uc + y, -du_max, du_max)
    y  = y + Uc - z

with a warm start from the previous tick.  The script writes the scaled QP matrices
(Hinv, F, c_prev, rho) into `design/mpc.json`; `design/build_mpc.py` puts them into the
model.

It also runs the nonlinear closed loop of the MPC and of the rate-limited LQR at 1 ms,
and prints the values used by `expected.json`.

Run it with ``uv run examples/inverted-pendulum-cart/design/mpc.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.linalg import expm, solve_continuous_are, solve_discrete_are

HERE = Path(__file__).resolve().parent
OUT = HERE / "mpc.json"

M, M_TIP, L, G, B = 1.0, 0.2, 0.5, 9.81, 0.1
TS = 1e-3
U_MAX = 20.0
DU_MAX = 0.2
N = 20
ITERATIONS = 20
Q = np.diag([8.0e3, 1.0, 100.0, 10.0])
R = np.array([[1.0]])
THETA0 = 0.1
X_STEP = 0.3
T_STEP = 1.5
T_END = 5.0


def linear_model() -> tuple[np.ndarray, np.ndarray]:
    total = M + M_TIP
    a = np.array([
        [0.0, 1.0, 0.0, 0.0],
        [0.0, -B / M, -M_TIP * G / M, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [0.0, B / (M * L), total * G / (M * L), 0.0],
    ])
    b = np.array([0.0, 1.0 / M, 0.0, -1.0 / (M * L)])
    return a, b


def discrete_model() -> tuple[np.ndarray, np.ndarray]:
    a, b = linear_model()
    aug = np.zeros((5, 5))
    aug[:4, :4] = a
    aug[:4, 4] = b
    aug = expm(aug * TS)
    return aug[:4, :4], aug[:4, 4]


def qp_matrices() -> dict[str, np.ndarray | float]:
    ad, bd = discrete_model()
    p = solve_discrete_are(ad, bd.reshape(4, 1), Q, R)
    phi = np.zeros((N * 4, 4))
    gamma = np.zeros((N * 4, N))
    for k in range(N):
        phi[k * 4:(k + 1) * 4, :] = np.linalg.matrix_power(ad, k + 1)
        for j in range(k + 1):
            gamma[k * 4:(k + 1) * 4, j] = np.linalg.matrix_power(ad, k - j) @ bd
    qbar = np.kron(np.eye(N), Q)
    qbar[-4:, -4:] = p
    rbar = np.eye(N) * R[0, 0]
    h = gamma.T @ qbar @ gamma + rbar
    f = gamma.T @ qbar @ phi
    lower = np.tril(np.ones((N, N)))
    hd = lower.T @ h @ lower
    fd = lower.T @ f
    c_prev = lower.T @ (h @ np.ones(N))
    scale = float(np.max(np.diag(hd)))
    hs = hd / scale
    rho = float(np.trace(hs) / N)
    h_inv = np.linalg.inv(hs + rho * np.eye(N))
    return {
        "Ad": ad, "Bd": bd, "P": p, "H": h, "F": f, "L": lower, "Hd": hd,
        "Fd": fd / scale, "c_prev": c_prev / scale, "rho": rho, "Hinv": h_inv,
        "scale": scale,
    }


def simulate(controller: str, matrices: dict, t_end: float = T_END,
             u_limit: float = U_MAX, du_limit: float = DU_MAX) -> dict[str, float]:
    fd_mat, c_prev = matrices["Fd"], matrices["c_prev"]
    h_inv, rho = matrices["Hinv"], matrices["rho"]
    # The reference LQR is the continuous Riccati gain of design/design.py, sampled at 1 ms.
    a, b = linear_model()
    k_lqr = (np.linalg.inv(R) @ b.reshape(4, 1).T
             @ solve_continuous_are(a, b.reshape(4, 1), Q, R)).ravel()
    state = np.array([0.0, 0.0, THETA0, 0.0])
    z = np.zeros(N)
    y = np.zeros(N)
    u_prev = 0.0
    steps = int(t_end / TS)
    out = np.zeros((steps + 1, 6))
    for i in range(steps):
        t = i * TS
        x_ref = X_STEP if t >= T_STEP else 0.0
        e = np.array([state[0] - x_ref, state[1], state[2], state[3]])
        if controller == "lqr":
            u_cmd = float(np.clip(-k_lqr @ e, -u_limit, u_limit))
            u = float(np.clip(u_prev + np.clip(u_cmd - u_prev, -du_limit, du_limit), -u_limit, u_limit))
        else:
            fd = fd_mat @ e + c_prev * u_prev
            for _ in range(ITERATIONS):
                uc = h_inv @ (rho * (z - y) - fd)
                z = np.clip(uc + y, -DU_MAX, DU_MAX)
                y = y + uc - z
            u = float(np.clip(u_prev + z[0], -u_limit, u_limit))
        u_prev = u
        out[i] = (t, *state, u)
        k1 = f_plant(state, u)
        k2 = f_plant(state + 0.5 * TS * k1, u)
        k3 = f_plant(state + 0.5 * TS * k2, u)
        k4 = f_plant(state + TS * k3, u)
        state = state + TS / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
    out[steps] = (t_end, *state, u)
    t, x, _v, th, _w, u = out.T
    window = lambda lo, hi: (t >= lo) & (t <= hi)
    return {
        "x_end": float(x[-1]),
        "x_max": float(np.abs(x).max()),
        "theta_max_deg": float(np.degrees(np.abs(th).max())),
        "u_max": float(np.abs(u).max()),
        "u_end": float(u[-1]),
        "theta_2p9_3p0_deg": float(np.degrees(np.abs(th[window(2.9, 3.0)]).max())),
        "theta_4p5_5p0_deg": float(np.degrees(np.abs(th[window(4.5, 5.0)]).max())),
    }


def f_plant(state: np.ndarray, u: float) -> np.ndarray:
    _x, v, th, w = state
    total = M + M_TIP
    den = total - M_TIP * np.cos(th) ** 2
    return np.array([
        v,
        (u + M_TIP * L * np.sin(th) * w * w - M_TIP * G * np.sin(th) * np.cos(th) - B * v) / den,
        w,
        (G * np.sin(th) * total - np.cos(th) * (u + M_TIP * L * w * w * np.sin(th))) / (L * den),
    ])


def main() -> None:
    m = qp_matrices()
    lqr = simulate("lqr", m)
    lqr_unlimited = simulate("lqr", m, u_limit=1.0e6, du_limit=1.0e6)
    mpc = simulate("mpc", m)
    data = {
        "description": "Constrained MPC on the cart-pole: 25 ms horizon, |u| <= 20 N, |du| <= 0.2 N per 1 ms tick.",
        "plant": {"M": M, "m": M_TIP, "l": L, "g": G, "b": B, "theta0": THETA0,
                  "x_step": X_STEP, "t_step": T_STEP, "t_end": T_END},
        "mpc": {"N": N, "Ts": TS, "iterations": ITERATIONS, "u_max": U_MAX, "du_max": DU_MAX,
                "Q": np.diag(Q).tolist(), "R": float(R[0, 0]),
                "rho": m["rho"], "scale": m["scale"]},
        "matrices": {
            "Hinv": m["Hinv"].tolist(),
            "F": m["Fd"].tolist(),
            "c_prev": m["c_prev"].tolist(),
        },
        "reference": {"lqr_unlimited": lqr_unlimited,
                      "lqr_rate_limited": lqr, "mpc": mpc},
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"MPC: N={N}, Ts={TS}, iterations={ITERATIONS}, u_max={U_MAX} N, du_max={DU_MAX} N/tick")
    print(f"QP scale {m['scale']:.6g}, rho {m['rho']:.6g}")
    print("reference (1 ms, nonlinear plant, 0.1 rad start, 0.3 m step at 1.5 s):")
    for name, values in (("LQR, no limit", lqr_unlimited),
                         ("LQR + 200 N/s rate limit", lqr), ("MPC", mpc)):
        print(f"  {name}:")
        for key, value in values.items():
            print(f"    {key:22s} {value:.9g}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
