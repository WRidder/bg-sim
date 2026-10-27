# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Linear-quadratic design for the `inverted-pendulum-cart` sample (plan 9.6c).

The plant is the standard point-mass cart-pole: a cart of mass ``M`` on a frictionless
rail with viscous friction ``b``, a massless rod of length ``l`` carrying a point mass
``m`` at its tip, so the pendulum inertia about the pivot is ``J_p = m l^2`` and there is
no rod inertia of its own (the bond graph in ``models/`` uses the same model: two
translational ``I(m)`` elements for the tip mass and no ``I(J_rod)`` on the angular
1-junction). With ``theta`` measured from upright, ``x`` the cart position and ``u`` the
force on the cart, the equations of motion are

    (M+m) x'' + m l cos(theta) theta'' - m l sin(theta) theta'^2 = u - b x'
    m l cos(theta) x'' + m l^2 theta'' - m g l sin(theta)            = 0

Linearised at upright (``theta = 0``, ``theta' = 0``) with the state
``[x, x', theta, theta']``:

    A = [[0, 1,            0, 0],
         [0, -b/M, -m g/M,  0],
         [0, 0,            0, 1],
         [0, b/(M l), (M+m) g/(M l), 0]]        B = [0, 1/M, 0, -1/(M l)]'

``scipy.linalg.solve_continuous_are`` solves the continuous DARE for the weights below,
and ``K`` is written into the four ``K_*`` parameters of the ``LQR1`` node of the model
document (``u = clamp(-K [x - x_ref, v, theta, w], -20, 20)``).

Weights. ``Q = diag(q_x, q_v, q_theta, q_omega)`` and ``R`` are chosen with the
Bryson-style normalisation ``q_i = 1/sigma_i^2`` (the cost of each state is 1 when it sits
at its scale) and ``R = 1/sigma_u^2``:

    sigma_x     = 1.1 cm    q_x     = 8e3   - the cart position is the slow, weakly
                                             actuated mode (the force reaches it only
                                             through the pendulum), so it needs the
                                             largest weight to pull the slow pole up;
    sigma_v     = 1 m/s     q_v     = 1
    sigma_theta = 0.1 rad   q_theta = 100   - the angle is cheap: the force couples to it
                                             directly through -1/(M l);
    sigma_omega = 0.32 rad/s q_omega = 10
    sigma_u     = 1 N       R       = 1     - 1 N^2 per newton^2 of force;

The resulting force demand peaks at 17.9 N (at the initial 0.1 rad tilt), inside the
+-20 N clamp of the firmware; the clamp therefore stays inactive in the nominal run, and
the reference integration below includes it anyway so the two agree if K changes.

The script also integrates the *non-linear* closed loop with the same law (RK4, 0.1 ms)
and prints the values the acceptance checks in ``expected.json`` use.

Run it with ``uv run examples/inverted-pendulum-cart/design/design.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.linalg import solve_continuous_are

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "inverted-pendulum-cart.bgmodel.json"

#: Plant parameters, identical to the model document.
M = 1.0      # kg   cart mass
m = 0.2      # kg   pendulum tip mass
l = 0.5      # m    rod length
g = 9.81     # m/s^2
b = 0.1      # N s/m cart friction
THETA0 = 0.1  # rad initial tilt
T_STEP = 1.5  # s    cart reference step
X_STEP = 0.2  # m    reference amplitude
T_END = 4.0   # s    run length
U_MAX = 20.0  # N    force limit

#: Weights (see the module docstring).
Q = np.diag([8.0e3, 1.0, 100.0, 10.0])
R = np.array([[1.0]])


def linear_model() -> tuple[np.ndarray, np.ndarray]:
    """The state matrix and the input vector of the linearised cart-pole."""
    total = M + m
    a = np.array(
        [
            [0.0, 1.0, 0.0, 0.0],
            [0.0, -b / M, -m * g / M, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, b / (M * l), total * g / (M * l), 0.0],
        ]
    )
    b_vec = np.array([0.0, 1.0 / M, 0.0, -1.0 / (M * l)])
    return a, b_vec


def lqr() -> np.ndarray:
    """The Riccati gain vector K (u = -K [x - x_ref, v, theta, w])."""
    a, b_vec = linear_model()
    p = solve_continuous_are(a, b_vec.reshape(4, 1), Q, R)
    return (np.linalg.inv(R) @ b_vec.reshape(4, 1).T @ p).ravel()


def control(K: np.ndarray, state: np.ndarray, t: float) -> float:
    """The continuous state-feedback law `clamp(-K [x - x_ref, v, theta, w], -u_max, u_max)`."""
    x_ref = X_STEP if t >= T_STEP else 0.0
    return float(np.clip(-K @ np.array([state[0] - x_ref, *state[1:]]), -U_MAX, U_MAX))


def reference(K: np.ndarray, h: float = 1e-4) -> np.ndarray:
    """The non-linear closed loop with the +-U_MAX clamp: rows (t, x, v, theta, w, u).

    The controller is evaluated at every RK4 stage, so this is the continuous feedback law
    and not a zero-order hold over the integration step.
    """
    total = M + m

    def f(state: np.ndarray, u: float) -> np.ndarray:
        x, v, th, w = state
        den = total - m * np.cos(th) ** 2
        return np.array(
            [
                v,
                (u + m * l * np.sin(th) * w * w - m * g * np.sin(th) * np.cos(th)
                 - b * v) / den,
                w,
                (g * np.sin(th) * total
                 - np.cos(th) * (u + m * l * w * w * np.sin(th))) / (l * den),
            ]
        )

    state = np.array([0.0, 0.0, THETA0, 0.0])
    steps = int(round(T_END / h))
    out = np.empty((steps + 1, 6))
    for i in range(steps + 1):
        t = i * h
        out[i] = (t, *state, control(K, state, t))
        u1 = control(K, state, t)
        k1 = f(state, u1)
        s2 = state + 0.5 * h * k1
        k2 = f(s2, control(K, s2, t + 0.5 * h))
        s3 = state + 0.5 * h * k2
        k3 = f(s3, control(K, s3, t + 0.5 * h))
        s4 = state + h * k3
        k4 = f(s4, control(K, s4, t + h))
        state = state + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return out


def write_gains(path: Path, K: np.ndarray) -> None:
    """Write K into the four ``K_*`` parameters of the model document, keeping its layout."""
    text = path.read_text(encoding="utf-8")
    names = ("K_x", "K_v", "K_theta", "K_omega")
    for name, value in zip(names, K):
        pattern = rf'("{name}":\s*")[^"]*(")'
        text, count = re.subn(pattern, lambda mm: f"{mm.group(1)}{value:.6f}{mm.group(2)}", text)
        if count != 1:
            raise SystemExit(f"expected exactly one `{name}` parameter in {path}, found {count}")
    json.loads(text)  # the document must still be valid JSON
    path.write_text(text, encoding="utf-8")


def main() -> None:
    a, b_vec = linear_model()
    K = lqr()
    closed = np.linalg.eigvals(a - b_vec.reshape(4, 1) @ K.reshape(1, 4))

    np.set_printoptions(precision=6, suppress=False)
    print(f"plant: M={M} kg, m={m} kg, l={l} m, g={g} m/s^2, b={b} N s/m, J_p={m * l**2} kg m^2")
    print(f"open-loop eigenvalues: {np.linalg.eigvals(a)}")
    print(f"Q = diag({np.diag(Q).tolist()}), R = {R[0, 0]}")
    print(f"K = {K}")
    print(f"closed-loop eigenvalues: {closed}")
    print(f"u at the initial tilt: {-K @ np.array([0.0, 0.0, THETA0, 0.0]):.3f} N "
          f"(limit {U_MAX} N)")

    reference_values = reference(K)
    t, x, v, theta, w, u = (reference_values[:, i] for i in range(6))
    window = lambda values, lo, hi: np.abs(values[(t >= lo) & (t <= hi)]).max()
    peak = int(np.argmax(np.abs(u)))
    print(f"\nnon-linear reference closed loop (RK4, h=1e-4, clamp +-{U_MAX:g} N):")
    print(f"  max |u|            = {np.abs(u).max():.6f} N at t = {t[peak]:.4f} s")
    print(f"  max |theta|        = {np.degrees(np.abs(theta).max()):.4f} deg")
    print(f"  max |x|            = {np.abs(x).max():.6f} m")
    print(f"  |theta| max [2.9, 3.0] = {np.degrees(window(theta, 2.9, 3.0)):.6f} deg")
    print(f"  |theta| max [3.5, 4.0] = {np.degrees(window(theta, 3.5, 4.0)):.6f} deg")
    print(f"  |x|     max [1.3, 1.45] = {window(x, 1.3, 1.45):.6f} m")
    print(f"  |theta| max [1.3, 1.45] = {np.degrees(window(theta, 1.3, 1.45)):.6f} deg")
    print("  cursor values:")
    for t_cursor in (0.2, 1.0, 1.45, 2.0, 3.0, 3.5, 4.0):
        print(f"    t = {t_cursor:4.2f} s  x = {np.interp(t_cursor, t, x):+.6f} m  "
              f"theta = {np.degrees(np.interp(t_cursor, t, theta)):+.6f} deg  "
              f"u = {np.interp(t_cursor, t, u):+.4f} N")

    write_gains(MODEL, K)
    print(f"\nwrote K into {MODEL}")


if __name__ == "__main__":
    main()
