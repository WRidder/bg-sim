# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""LQG design for the `drivetrain-kalman` sample (plan 9.5).

The plant is the two-inertia drivetrain of the model document: a DC motor
(R = 1 ohm, L = 1 mH, k = 0.1, J_m = 5e-5), a 10:1 gearbox, wheel inertia
J1 = 1e-3, a 50 N m/rad flexible rod (three 150 N m/rad segments with two
6.7e-5 mid inertias in the model; one lumped spring here, as plan 9.5 says),
wheel inertia J2 = 2e-3 and a load torque.

Design model
------------
With ``w_ref = 0`` the four plan states are ``[theta_m, omega_m, theta_L,
omega_L]``.  The motor and wheel 1 are rigidly coupled by the ideal gear, so
J1 reflects to the motor side, ``J_eq = J_m + J1/n^2``, and the rod is one
spring to J2::

    J_eq w_m' = k_t (V - k_t w_m)/R - (k delta + d (w_m/n - w_L))/n
    J2   w_L' = k delta + d (w_m/n - w_L) - T_load
    delta'    = w_m/n - w_L,          delta = theta_m/n - theta_L
    theta_m'  = w_m,      theta_L' = w_L

(the electrics are quasi-static, as plan 9.5 prescribes; L is only in the
plant simulation below, where it shows that the 1 ms lag does not upset the
loop).  We design in ``[delta, w_m, w_L, z]`` with ``z' = w_ref - w_L`` rather
than in the absolute angles: ``z = w_ref t - theta_L`` is then an exact linear
combination of the plan's states, so the absolute-angle LQR is not
controllable and ``solve_discrete_are`` returns the anti-stabilizing root.
The gain maps back with ``K = [k_delta/n, k_wm, -k_delta, k_wL]`` and
``Ki = -k_z``, which is exactly feedback on the absolute state (the two
theta terms collapse to ``-k_delta delta``).

Weights (Bryson: Q_ii = 1/sigma_i^2, R = 1/sigma_u^2)
----------------------------------------------------
    sigma_delta = 0.32 rad    q = 10        the rod may twist a few hundredths
                                            of a rad; the flexible mode is not
                                            to be fought with a stiff loop
    sigma_wm    = 100 rad/s   q = 1e-4      the motor runs at n*10 = 100 rad/s
    sigma_wL    = 1 rad/s     q = 1         the controlled variable: a one
                                            rad/s error costs one unit
    sigma_z     = 0.07 rad    q = 200       z is the accumulated speed error
                                            (an angle lag); this sets Ki and
                                            the 0.3 s load recovery
    sigma_u     = 24 V        R = 1/576     the voltage limit

The Kalman filter
-----------------
``y = theta_m`` at 1 ms with an encoder of ``2*pi/4096`` rad, so
``R_n = (2*pi/4096)^2/12``.  A four-state filter with the load torque only as
process noise keeps a steady-state bias of about 1.3 rad/s in ``w_L`` while
the load acts (the model cannot tell a load torque from an input offset), so
``xhat`` has a fifth state: the load torque, a random walk with
``Q_n = 1e-6 (N m)^2`` per sample (a 1 mN m/ms slew, so a 0.5 N m step is
learned in about 0.1 s).  ``w_load_hat = xhat[4]`` is still the load speed, as
in the plan.  The script writes ``Ad, Bd, Cd, L, K, Ki, Kff`` into both model
documents and then integrates the sampled closed loop (3-segment rod, 1 mH
electrics, RK4) to print the acceptance values.

Run it with ``uv run examples/drivetrain-kalman/design/design.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.linalg import expm, solve_continuous_are, solve_discrete_lyapunov
from scipy.signal import place_poles

ROOT = Path(__file__).resolve().parent.parent
MODEL_FILES = (
    ROOT / "models" / "drivetrain-kalman.bgmodel.json",
    ROOT / "models" / "drivetrain-backlash.bgmodel.json",
)

# plant (identical to the model documents)
R_OHM = 1.0       # ohm
L_H = 1e-3        # H
KT = 0.1          # N m/A = V s/rad
J_M = 5e-5        # kg m^2
GEAR = 10.0       # n
J1 = 1e-3         # kg m^2
J2 = 2e-3         # kg m^2
K_SEG = 150.0     # N m/rad per rod segment (3 in series -> 50)
D_SEG = 0.02      # N m s/rad per rod segment (3 in series -> 0.00667)
J_MID = 6.7e-5    # kg m^2 per intermediate inertia
R_D = 1e-4        # N m s/rad motor viscous damping
TS = 1e-3         # s, the firmware sample period
UMAX = 24.0       # V
T_END = 2.0       # s
T_REF = 0.1       # s
W_REF = 10.0      # rad/s
T_STEP = 1.0      # s
T_LOAD = 0.5      # N m resisting load (the model's MSe effort is -0.5)
ENCODER = 2 * np.pi / 4096
Q_TORQUE = 1e-6   # (N m)^2 per sample, the load-torque random walk

K_ROD = K_SEG / 3.0
D_ROD = D_SEG / 3.0
J_EQ = J_M + J1 / GEAR**2
R_N = ENCODER**2 / 12.0

Q = np.diag([10.0, 1e-4, 1.0, 200.0])
R_WEIGHT = np.array([[1.0 / UMAX**2]])


# --------------------------------------------------------------------- linear algebra


def zoh(a: np.ndarray, b: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact zero-order-hold discretization of ``x' = a x + b u``."""
    n, m = a.shape[0], b.shape[1]
    block = np.zeros((n + m, n + m))
    block[:n, :n] = a
    block[:n, n:] = b
    exp = expm(block * dt)
    return exp[:n, :n], exp[:n, n:]


def dare_stabilizing(a, b, q, r, k0):
    """The stabilizing discrete algebraic Riccati solution by Kleinman iteration.

    ``scipy.linalg.solve_discrete_are`` is not used: with the pure integrator
    (``z`` or the two angles) on the unit circle its generalized Schur method
    picks the anti-stabilizing root (closed-loop |eig| > 1 here, verified), so
    the DARE is solved by the Newton-Kleinman iteration from a stabilizing
    ``k0`` instead.  Scale ``q`` and ``r`` together to keep it conditioned; the
    gain does not change.  Returns ``(P, K)``.
    """
    k = np.asarray(k0, dtype=float)
    for _ in range(500):
        s = a - b @ k
        p = solve_discrete_lyapunov(s.T, q + k.T @ r @ k)
        k_new = np.linalg.solve(r + b.T @ p @ b, b.T @ p @ a)
        if np.max(np.abs(k_new - k)) <= 1e-10 * max(1.0, np.max(np.abs(k_new))):
            return p, k_new
        k = k_new
    raise RuntimeError("the Kleinman iteration did not converge")


def lqr_seed(a, b, q, r):
    """A stabilizing gain for the sampled pair, from the continuous problem."""
    p = solve_continuous_are(a, b, q, r)
    k = np.linalg.solve(r, b.T @ p)
    a_d, b_d = zoh(a, b, TS)
    if np.max(np.abs(np.linalg.eigvals(a_d - b_d @ k))) >= 1.0:
        raise RuntimeError("the continuous seed is not stabilizing at Ts")
    return k


def model_absolute():
    """The plan's 4-state model in ``[theta_m, omega_m, theta_L, omega_L]``."""
    a = np.zeros((4, 4))
    a[0, 1] = 1.0
    a[1, 1] = -(KT**2 / R_OHM + D_ROD / GEAR**2 + R_D) / J_EQ
    a[1, 0] = -K_ROD / (GEAR**2 * J_EQ)
    a[1, 2] = K_ROD / (GEAR * J_EQ)
    a[1, 3] = D_ROD / (GEAR * J_EQ)
    a[2, 3] = 1.0
    a[3, 0] = K_ROD / (GEAR * J2)
    a[3, 1] = D_ROD / (GEAR * J2)
    a[3, 2] = -K_ROD / J2
    a[3, 3] = -D_ROD / J2
    b = np.array([[0.0], [KT / (R_OHM * J_EQ)], [0.0], [0.0]])
    e = np.array([[0.0], [0.0], [0.0], [-1.0 / J2]])
    c = np.array([1.0, 0.0, 0.0, 0.0])
    return a, b, e, c


def model_relative():
    """``[delta, omega_m, omega_L, z]`` with ``delta = theta_m/n - theta_L``."""
    a = np.zeros((4, 4))
    a[0, 1] = 1.0 / GEAR
    a[0, 2] = -1.0
    a[1, 0] = -K_ROD / (GEAR * J_EQ)
    a[1, 1] = -(KT**2 / R_OHM + D_ROD / GEAR**2 + R_D) / J_EQ
    a[1, 2] = D_ROD / (GEAR * J_EQ)
    a[2, 0] = K_ROD / J2
    a[2, 1] = D_ROD / (GEAR * J2)
    a[2, 2] = -D_ROD / J2
    a[3, 2] = -1.0
    b = np.array([[0.0], [KT / (R_OHM * J_EQ)], [0.0], [0.0]])
    return a, b


def design_lqr():
    """The LQR gain, the integral gain and the reference feedforward."""
    a_rel, b_rel = model_relative()
    ar, br = zoh(a_rel, b_rel, TS)
    # solve with R = 1 and Q/R (the pair is scale invariant); the weights above
    # are in physical units, R = 1/sigma_u^2
    _, ke = dare_stabilizing(
        ar, br, Q / R_WEIGHT[0, 0], np.array([[1.0]]),
        lqr_seed(a_rel, b_rel, Q, R_WEIGHT),
    )
    ke = ke.ravel()                      # [k_delta, k_wm, k_wL, k_z]
    k = np.array([ke[0] / GEAR, ke[1], -ke[0], ke[2], 0.0])
    ki = -ke[3]
    # At the reference the absolute-state feedback still holds -k_wm*n*w_ref
    # - k_wL*w_ref; the block adds exactly that plus the back-EMF k*n*w_ref,
    # the voltage the motor needs at w_m = n*w_ref.  The integral then only
    # trims the load torque (plan 9.5's law has no feedforward at all; without
    # it 10 rad/s would demand >150 V from the 24 V-limited loop).
    kff = GEAR * k[1] + k[3] + KT * GEAR
    return k, ki, kff, ke, ar, br


def design_kf(a, e, c):
    """The steady-state Kalman filter for ``y = theta_m`` (5 states)."""
    a5 = np.zeros((5, 5))
    a5[:4, :4] = a
    a5[:4, 4] = e.ravel()
    c5 = np.array([c[0], 0.0, 0.0, 0.0, 0.0])
    # the discrete model used by the firmware (5 states, the input on state 2)
    ad5, bd5 = zoh(a5, np.array([[0.0], [KT / (R_OHM * J_EQ)], [0.0], [0.0], [0.0]]), TS)
    # the dual DARE on the *sampled* model: P is the one-step prediction
    # covariance.  Scale Q_n and R_n by 1/R_n (the gain is invariant).  The
    # 1e-12 on the four plant states is a numerical floor: the two angle modes
    # have a pole at +1 and are undetectable from Q_n alone, and the DARE needs
    # a positive weight there to have a unique stabilizing solution.
    a_dual, b_dual = ad5.T, c5.reshape(-1, 1)
    seed = place_poles(a_dual, b_dual, [0.5, 0.6, 0.7, 0.8, 0.9]).gain_matrix
    qn = np.diag([1e-12, 1e-12, 1e-12, 1e-12, Q_TORQUE]) / R_N
    p, _ = dare_stabilizing(a_dual, b_dual, qn, np.array([[1.0]]), seed)
    l = (p @ c5) / (c5 @ p @ c5 + 1.0)
    return ad5, bd5.ravel(), c5, l


# --------------------------------------------------------------------- reference sim


def reference_closed_loop(k, ki, kff, ad5, bd5, cd5, kalman_gain):
    """RK4 of the sampled loop against the 9-state truth, with the encoder.

    Truth states: ``[theta_m, w_m, i_L, theta_1, w_1, theta_2, w_2, theta_L,
    w_L]`` (the three rod segments).  ``u`` is held over each 1 ms tick.
    """
    h = 2e-5

    def derivative(x, u, load):
        thm, wm, i_l, t1, w1, t2, w2, tl, wl = x
        torque = KT * i_l
        s1 = K_SEG * (thm / GEAR - t1) + D_SEG * (wm / GEAR - w1)
        s2 = K_SEG * (t1 - t2) + D_SEG * (w1 - w2)
        s3 = K_SEG * (t2 - tl) + D_SEG * (w2 - wl)
        return np.array([
            wm,
            (torque - s1 / GEAR - R_D * wm) / J_EQ,
            (u - R_OHM * i_l - KT * wm) / L_H,
            w1,
            (s1 - s2) / J_MID,
            w2,
            (s2 - s3) / J_MID,
            wl,
            (s3 - load) / J2,
        ])

    xhat = np.zeros(5)
    z = 0.0
    x = np.zeros(9)
    u = 0.0
    t = 0.0
    next_tick = 0.0
    times: list[float] = []
    speed: list[float] = []
    voltage: list[float] = []
    estimate: list[float] = []
    torque_hat: list[float] = []
    while t <= T_END + 1e-12:
        if t >= next_tick - 1e-12:
            w_ref = W_REF if t >= T_REF else 0.0
            y = ENCODER * round(x[0] / ENCODER)          # 12-bit encoder
            xhat = xhat + kalman_gain * (y - cd5 @ xhat)
            z += TS * (w_ref - xhat[3])
            v = -k @ xhat + ki * z + kff * w_ref
            u = float(np.clip(v, -UMAX, UMAX))
            if abs(v) > UMAX:
                z -= TS * (w_ref - xhat[3])              # anti-windup
            xhat = ad5 @ xhat + bd5 * u
            times.append(t)
            speed.append(x[8])
            voltage.append(u)
            estimate.append(xhat[3])
            torque_hat.append(xhat[4])
            next_tick += TS
        load = T_LOAD if t >= T_STEP else 0.0
        k1 = derivative(x, u, load)
        k2 = derivative(x + 0.5 * h * k1, u, load)
        k3 = derivative(x + 0.5 * h * k2, u, load)
        k4 = derivative(x + h * k3, u, load)
        x = x + h / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += h
    return tuple(np.asarray(column) for column in
                 (times, speed, voltage, estimate, torque_hat))


# --------------------------------------------------------------------- model writing


def _matrix_text(m: np.ndarray) -> str:
    rows = [" ".join(f"{value:.12g}" for value in row) for row in np.atleast_2d(m)]
    return "[" + "; ".join(rows) + "]"


def _vector_text(v: np.ndarray) -> str:
    return "[" + ", ".join(f"{value:.12g}" for value in np.asarray(v).ravel()) + "]"


def write_parameters(path: Path, values: dict[str, str]) -> None:
    """Write the gains into the ``LQG`` node's params, keeping the layout valid."""
    text = path.read_text(encoding="utf-8")
    for name, value in values.items():
        pattern = rf'("{name}":\s*")[^"]*(")'
        text, count = re.subn(pattern, lambda match: f"{match.group(1)}{value}{match.group(2)}", text)
        if count != 1:
            raise SystemExit(f"expected exactly one `{name}` parameter in {path}, found {count}")
    document = json.loads(text)
    if not any(
        node.get("name") == "LQG" for node in document["diagram"]["nodes"]
    ):
        raise SystemExit(f"{path} has no LQG node")
    path.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------- main


def main() -> None:
    a, b, e, c = model_absolute()
    k, ki, kff, ke, ar, br = design_lqr()
    ad5, bd5, cd5, kalman_gain = design_kf(a, e, c)

    closed = np.abs(np.linalg.eigvals(ar - br @ ke.reshape(1, -1)))
    filtered = np.abs(np.linalg.eigvals(ad5 @ (np.eye(5) - np.outer(kalman_gain, cd5))))
    np.set_printoptions(precision=6, suppress=False)

    print(f"plant: J_eq = {J_EQ:.3e} kg m^2, rod k = {K_ROD:.1f} N m/rad, "
          f"d = {D_ROD:.4f} N m s/rad, J2 = {J2} kg m^2")
    print(f"continuous open-loop poles: {np.linalg.eigvals(a)}")
    print(f"Q = diag({np.diag(Q).tolist()}), R = {R_WEIGHT[0, 0]:.6g} (sigma_u = {UMAX:g} V)")
    print(f"LQR (relative coordinates) Ke = {ke}")
    print(f"K (absolute, plan form) = {k}")
    print(f"Ki = {ki:.6f}, Kff = {kff:.6f} V/(rad/s)")
    print(f"discrete closed-loop |eig| (zoh at {TS:g} s): {closed}")
    print(f"RF: R_n = {R_N:.6g} rad^2, Q_torque = {Q_TORQUE:g} (N m)^2")
    print(f"Kalman gain L = {kalman_gain}")
    print(f"estimator |eig| = {filtered}")

    times, speed, voltage, estimate, torque_hat = reference_closed_loop(
        k, ki, kff, ad5, bd5, cd5, kalman_gain
    )
    at = lambda t_query, values: float(np.interp(t_query, times, values))
    window = (times >= 0.5) & (times <= T_END)
    rms = float(np.sqrt(np.mean((estimate[window] - speed[window]) ** 2)))
    print(f"\nreference closed loop (3-segment rod, 1 mH electrics, RK4 h=2e-5, "
          f"encoder {ENCODER:.6g} rad):")
    print(f"  omega_L(0.6) = {at(0.6, speed):.6f} rad/s  (target {W_REF:g} +-2 %)")
    print(f"  omega_L(1.3) = {at(1.3, speed):.6f} rad/s  (after the -{T_LOAD:g} N m step at {T_STEP:g} s)")
    print(f"  omega_L(2.0) = {at(2.0, speed):.6f} rad/s")
    print(f"  max |u|      = {np.max(np.abs(voltage)):.6f} V  (limit {UMAX:g} V)")
    print(f"  peak / dip   = {speed.max():.4f} / {speed.min():.4f} rad/s")
    print(f"  RMS(w_load_hat - omega_L) over [0.5, 2] s = {rms:.6f} rad/s  (limit 0.2)")
    print(f"  T_load_hat(2.0) = {at(2.0, torque_hat):.6f} N m  (applied {T_LOAD:g} N m)")

    values = {
        "Ad": _matrix_text(ad5),
        "Bd": _vector_text(bd5),
        "Cd": _vector_text(cd5),
        "L": _vector_text(kalman_gain),
        "K": _vector_text(k),
        "Ki": f"{ki:.12g}",
        "Kff": f"{kff:.12g}",
        "umax": f"{UMAX:.12g}",
    }
    for path in MODEL_FILES:
        write_parameters(path, values)
        print(f"wrote Ad/Bd/Cd/L/K/Ki/Kff into {path}")


if __name__ == "__main__":
    main()
