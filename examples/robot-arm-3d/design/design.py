# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Design data for the RRR arm of `robot-arm-3d` (plan 9.8, X5.3).

The plant is `ArmDynamics3R` (three point-mass joints in Hamiltonian form) behind three
DC motors and 50:1 gears.  This script owns every number that is *designed* rather than
given by the plan:

* the **minimum-jerk reference tables** of the three `TimeTable` blocks (point-to-point
  moves, `q(t) = q0 + (q1 - q0) (10 s^3 - 15 s^4 + 6 s^5)`, `s = (t - t0)/T`), sampled every
  `TABLE_DT` = 50 ms and interpolated linearly by the block;
* the **PD gains**: critical damping of the decoupled joint at the largest effective inertia
  `M_ii + n^2 J_m` over a grid of the workspace the moves visit (`Kp = M wn^2`, `Kd = 2 M wn`);
* the free-motion start `(q0, p0 = M(q0) qd0)` of the energy-conservation model.

It also integrates a numpy replica of the whole sampled closed loop (RK4, 0.1 ms, the 1 ms
controller as a zero-order hold, the motor electrics included).  The replica is an
independent implementation of the block's equations: the example's checks and the README
compare it with the Julia run.  `build_models.py` imports this module and writes the model
documents; run this file on its own to print the design report.

    uv run examples/robot-arm-3d/design/design.py
"""

from __future__ import annotations

import numpy as np

# ------------------------------------------------------------------ plant (plan 9.8)
L2, L3 = 0.4, 0.3  # link lengths [m]
M2, M3 = 2.0, 1.0  # point masses at the elbow and the tip [kg]
JB = 0.05  # base yaw inertia [kg m^2]
G = 9.81  # gravity [m/s^2]

# ------------------------------------------------------------------ drives
N_GEAR = 50.0
R_W, L_W, K_T, J_M = (
    1.0,
    5e-4,
    0.1,
    1e-5,
)  # winding R [Ohm], L [H], k_t [N m/A], rotor J [kg m^2]
UMAX = 48.0  # voltage limit [V]
TS = 1e-3  # controller period [s]

# ------------------------------------------------------------------ references
Q_START = np.array([0.0, 0.6, -0.9])
# (joint targets, start time, duration)
MOVES = [
    (np.array([1.2, 1.0, -0.4]), 0.2, 1.0),
    (np.array([-0.6, 0.3, -1.3]), 1.8, 1.2),
]
TABLE_DT = 0.05
TABLE_END = (
    3.2  # the last move ends at 3.0 s; the table holds its last value afterwards
)
T_END = 5.0

# ------------------------------------------------------------------ free-motion start
Q_FREE = np.array([0.3, 0.6, -0.9])
QD_FREE = np.array([2.0, -1.5, 2.5])

WN = np.array([20.0, 20.0, 20.0])  # closed-loop natural frequency per joint [rad/s]


def mass_matrix(q: np.ndarray) -> np.ndarray:
    re = L2 * np.cos(q[1])
    rt = re + L3 * np.cos(q[1] + q[2])
    c3 = np.cos(q[2])
    m = np.zeros((3, 3))
    m[0, 0] = JB + M2 * re**2 + M3 * rt**2
    m[1, 1] = M2 * L2**2 + M3 * (L2**2 + L3**2 + 2 * L2 * L3 * c3)
    m[1, 2] = m[2, 1] = M3 * (L3**2 + L2 * L3 * c3)
    m[2, 2] = M3 * L3**2
    return m


def dmass(q: np.ndarray) -> np.ndarray:
    """dM/dq_k as a (3, 3, 3) array, [k, i, j] (only M11, M22, M23 depend on q)."""
    re = L2 * np.cos(q[1])
    ze = L2 * np.sin(q[1])
    rt = re + L3 * np.cos(q[1] + q[2])
    zt = ze + L3 * np.sin(q[1] + q[2])
    d = np.zeros((3, 3, 3))
    d[1, 0, 0] = -2 * (M2 * re * ze + M3 * rt * zt)
    d[2, 0, 0] = -2 * M3 * rt * L3 * np.sin(q[1] + q[2])
    d[2, 1, 1] = -2 * M3 * L2 * L3 * np.sin(q[2])
    d[2, 1, 2] = d[2, 2, 1] = -M3 * L2 * L3 * np.sin(q[2])
    return d


def gravity(q: np.ndarray) -> np.ndarray:
    """dV/dq for V = g (m2 z_e + m3 z_t)."""
    re = L2 * np.cos(q[1])
    rt = re + L3 * np.cos(q[1] + q[2])
    return np.array([0.0, G * (M2 * re + M3 * rt), G * M3 * L3 * np.cos(q[1] + q[2])])


def energy(q: np.ndarray, qd: np.ndarray, g: float = G) -> float:
    ze = L2 * np.sin(q[1])
    zt = ze + L3 * np.sin(q[1] + q[2])
    return 0.5 * qd @ mass_matrix(q) @ qd + g * (M2 * ze + M3 * zt)


def min_jerk(t: float, t0: float, duration: float, a: float, b: float) -> float:
    s = min(max((t - t0) / duration, 0.0), 1.0)
    return a + (b - a) * s**3 * (10.0 - 15.0 * s + 6.0 * s**2)


def reference_exact(t: float) -> np.ndarray:
    """The ideal minimum-jerk reference of the three joints (before table sampling)."""
    previous = Q_START.copy()
    for target, t0, duration in MOVES:
        if t >= t0 + duration:
            previous = target.copy()
            continue
        return np.array(
            [min_jerk(t, t0, duration, previous[i], target[i]) for i in range(3)]
        )
    return previous


def table_times() -> np.ndarray:
    count = round(TABLE_END / TABLE_DT) + 1
    return np.arange(count) * TABLE_DT


def table_values() -> np.ndarray:
    """(N, 3): the reference at the table instants."""
    return np.array([reference_exact(t) for t in table_times()])


def reference_table(t: float) -> np.ndarray:
    """What the linear-interpolating TimeTables output (held after the last sample)."""
    times = table_times()
    values = table_values()
    return np.array([np.interp(t, times, values[:, i]) for i in range(3)])


def gains() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kp, Kd (critical damping at the largest effective inertia) and that inertia."""
    peak = np.zeros(3)
    grid = np.linspace
    for q2 in grid(-0.8, 1.4, 23):
        for q3 in grid(-2.0, 0.2, 23):
            m = mass_matrix(np.array([0.0, q2, q3]))
            peak = np.maximum(peak, np.diag(m))
    effective = peak + N_GEAR**2 * J_M
    kp = effective * WN**2
    kd = 2.0 * effective * WN
    return kp, kd, effective


def _round(values: np.ndarray, digits: int = 3) -> np.ndarray:
    return np.array([float(f"{value:.{digits}g}") for value in values])


def design() -> dict[str, np.ndarray]:
    kp, kd, effective = gains()
    return {
        "Kp": _round(kp),
        "Kd": _round(kd),
        "inertia": effective,
        "table": table_values(),
    }


# ------------------------------------------------------------------ closed-loop replica


def simulate(
    kp: np.ndarray,
    kd: np.ndarray,
    t_end: float = T_END,
    h: float = 1e-4,
    motors: bool = True,
    g: float = G,
    q0: np.ndarray | None = None,
    qd0: np.ndarray | None = None,
    first_tick: int = 1,
) -> dict[str, np.ndarray]:
    """RK4 of the plant behind its motors and gears with the sampled PD controller.

    With ``motors=False`` the arm is torque-free (the energy-conservation model).
    ``first_tick`` is the index of the first controller tick that reaches the plant: the Julia
    run holds the output default (0 V) through the first period (the clock's first tick is at
    Ts), so the first command, with a zero reference rate, lands at 1 ms.
    State: q, qd (joint level) and the three winding currents.
    """
    q = (Q_START if q0 is None else q0).astype(float).copy()
    qd = np.zeros(3) if qd0 is None else qd0.astype(float).copy()
    current = np.zeros(3)
    jr = N_GEAR**2 * J_M

    def derivative(state: np.ndarray, voltage: np.ndarray) -> np.ndarray:
        q_, qd_, i_ = state[:3], state[3:6], state[6:]
        m = mass_matrix(q_)
        dm = dmass(q_)
        mdot = sum(dm[k] * qd_[k] for k in range(3))
        dtdq = np.array([0.5 * qd_ @ dm[k] @ qd_ for k in range(3)])
        grav = gravity(q_) if g == G else gravity(q_) * (g / G)
        if motors:
            drive = N_GEAR * K_T * i_
            accel = np.linalg.solve(
                m + jr * np.eye(3), drive + dtdq - grav - mdot @ qd_
            )
            di = (voltage - R_W * i_ - K_T * N_GEAR * qd_) / L_W
        else:
            accel = np.linalg.solve(m, dtdq - grav - mdot @ qd_)
            di = np.zeros(3)
        return np.concatenate([qd_, accel, di])

    steps = round(t_end / h)
    per_tick = round(TS / h)
    times = np.arange(steps + 1) * h
    log_q = np.zeros((steps + 1, 3))
    log_qd = np.zeros((steps + 1, 3))
    log_u = np.zeros((steps + 1, 3))
    log_e = np.zeros((steps + 1, 3))
    log_energy = np.zeros(steps + 1)
    voltage = np.zeros(3)
    error = np.zeros(3)
    previous_ref = np.zeros(3)
    started = False
    state = np.concatenate([q, qd, current])
    for k in range(steps + 1):
        t = k * h
        if motors and k % per_tick == 0 and k >= first_tick * per_tick:
            ref = reference_table(t)
            q_, qd_ = state[:3], state[3:6]
            error = ref - q_
            rate = (ref - previous_ref) / TS if started else np.zeros(3)
            started = True
            previous_ref = ref
            torque = kp * error + kd * (rate - qd_) + gravity(q_)
            voltage = np.clip(
                R_W * torque / (N_GEAR * K_T) + N_GEAR * K_T * qd_, -UMAX, UMAX
            )
        log_q[k], log_qd[k], log_u[k], log_e[k] = state[:3], state[3:6], voltage, error
        log_energy[k] = energy(state[:3], state[3:6], g)
        if k == steps:
            break
        k1 = derivative(state, voltage)
        k2 = derivative(state + 0.5 * h * k1, voltage)
        k3 = derivative(state + 0.5 * h * k2, voltage)
        k4 = derivative(state + h * k3, voltage)
        state = state + h / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
    return {
        "t": times,
        "q": log_q,
        "qd": log_qd,
        "u": log_u,
        "e": log_e,
        "E": log_energy,
    }


def free_start() -> tuple[np.ndarray, np.ndarray]:
    """The free-motion initial state (q0, p0 = M(q0) qd0)."""
    return Q_FREE.copy(), mass_matrix(Q_FREE) @ QD_FREE


def main() -> None:
    result = design()
    kp, kd = result["Kp"], result["Kd"]
    np.set_printoptions(precision=4, suppress=True)
    print(f"largest effective inertia M_ii + n^2 Jm [kg m^2]: {result['inertia']}")
    print(f"Kp [N m/rad] = {kp}   Kd [N m s/rad] = {kd}   (wn = {WN} rad/s)")
    print(
        f"table: {result['table'].shape[0]} samples every {TABLE_DT:g} s up to {TABLE_END:g} s"
    )
    run = simulate(kp, kd)
    settled = run["t"] >= 4.0
    print(
        f"replica closed loop: max|e| after 4 s = {np.abs(run['e'][settled]).max():.3e} rad"
    )
    print(
        f"                     max|e| during the moves = {np.abs(run['e']).max(axis=0)}"
    )
    print(
        f"                     max|u| = {np.abs(run['u']).max(axis=0)} V (limit {UMAX:g})"
    )
    q0, p0 = free_start()
    free = simulate(kp, kd, motors=False, g=0.0, q0=q0, qd0=QD_FREE, t_end=5.0, h=1e-4)
    e0 = free["E"][0]
    print(
        f"replica free motion (g = 0): E0 = {e0:.6f} J, "
        f"max|E - E0|/E0 over 5 s = {np.abs(free['E'] - e0).max() / e0:.3e} (RK4 h = 0.1 ms)"
    )
    print(f"free start q0 = {q0}, p0 = {p0}")


if __name__ == "__main__":
    main()
