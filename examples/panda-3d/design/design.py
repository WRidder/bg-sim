# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Designed numbers of the `panda-3d` models (the given ones live in `panda.py`).

* the Cartesian TCP waypoints and their quintic rest-to-rest timing;
* the joint path that the analytical IK makes of it (checked against the joint position, rate
  and torque limits: rigid-body torque + reflected rotor inertia + Gaz friction);
* the PD gains;
* the start state of the drives (the spring preload that holds the arm at the ready pose);
* the generated gravity code of the controller (`gravity_code`), checked against the
  Newton-Euler of `panda.py` before it is written into `library/PandaPD.jl`.

    uv run examples/panda-3d/design/design.py      # prints the design report
"""

from __future__ import annotations

import math

import numpy as np

import panda as pz

# ------------------------------------------------------------------ plant settings
K_HELD = 1.0e7  # stiffness of the five held directions of every Revolute3D [N/m, N m/rad]
TS = 1e-3  # controller and sensor period [s]

# ------------------------------------------------------------------ panda-free
Q_FREE = pz.Q_READY.copy()  # released at rest from Franka's "ready" pose
T_FREE = 1.0
FREE_CHECK_TIMES = (0.1, 0.25, 0.5, 0.75, 1.0)

# gravity-torque comparison poses (validate.py)
NAMED_POSES = {
    "ready": pz.Q_READY,
    "zero_q4_bent": np.array([0.0, 0.0, 0.0, -math.pi / 2, 0.0, math.pi / 2, 0.0]),
    "stretched": np.array([0.3, 0.6, -0.4, -1.2, 0.5, 1.8, -0.6]),
    "random_a": np.array([-1.1, -0.9, 1.4, -2.0, -1.3, 2.6, 1.2]),
}

# ------------------------------------------------------------------ the task (panda)
T_HOME = pz.fk_flange(pz.Q_READY)  # flange pose at the ready pose: the orientation is kept
P_HOME = T_HOME[:3, 3].copy()
Q_HOME = pz.quat_of(T_HOME[:3, :3])
Q7_REF = pz.Q_READY[6]  # the IK's redundancy parameter, held at its ready value
# TCP (flange) waypoints [m]: a box-like tour in front of the robot and back home
WAYPOINTS = np.array(
    [
        P_HOME,
        [0.45, 0.20, 0.42],
        [0.45, -0.20, 0.42],
        [0.35, -0.12, 0.65],
        P_HOME,
    ]
)
T_START = 0.2  # first move starts [s]
T_MOVE = 0.9  # duration of each rest-to-rest segment [s]
T_DWELL = 0.25  # rest at each waypoint [s]
N_SEG = len(WAYPOINTS) - 1
T_END = T_START + N_SEG * (T_MOVE + T_DWELL) + 0.35
WAYPOINT_TIMES = tuple(T_START + k * (T_MOVE + T_DWELL) + T_MOVE for k in range(N_SEG))

# ------------------------------------------------------------------ controller
WN = np.array([15.0, 15.0, 15.0, 15.0, 20.0, 20.0, 20.0])  # closed-loop natural frequency [rad/s]


def target(t: float) -> np.ndarray:
    """The flange position of the trajectory block at time t (quintic rest-to-rest segments)."""
    for k in range(N_SEG):
        t0 = T_START + k * (T_MOVE + T_DWELL)
        if t < t0:
            return WAYPOINTS[k].copy()
        if t < t0 + T_MOVE:
            tau = (t - t0) / T_MOVE
            s = tau**3 * (10 - 15 * tau + 6 * tau**2)
            return WAYPOINTS[k] + (WAYPOINTS[k + 1] - WAYPOINTS[k]) * s
    return WAYPOINTS[-1].copy()


# the flange keeps pointing down and turns about the vertical with the azimuth of the waypoint
# (a slerp about z between the waypoint orientations, on the same quintic timing)
YAW = np.array([math.atan2(p[1], p[0]) for p in WAYPOINTS])


def target_yaw(t: float) -> float:
    for k in range(N_SEG):
        t0 = T_START + k * (T_MOVE + T_DWELL)
        if t < t0:
            return float(YAW[k])
        if t < t0 + T_MOVE:
            tau = (t - t0) / T_MOVE
            s = tau**3 * (10 - 15 * tau + 6 * tau**2)
            return float(YAW[k] + (YAW[k + 1] - YAW[k]) * s)
    return float(YAW[-1])


def target_pose(t: float) -> np.ndarray:
    return pz.hom(pz.rotz(target_yaw(t)) @ T_HOME[:3, :3], target(t))


def joint_path(dt: float = TS) -> tuple[np.ndarray, np.ndarray]:
    """IK of the trajectory every tick, the branch taken from the previous solution."""
    ts = np.arange(0.0, T_END + dt / 2, dt)
    qs = np.zeros((len(ts), pz.NJ))
    q = pz.Q_READY.copy()
    for j, t in enumerate(ts):
        sol, code = pz.ik_flange(target_pose(t), Q7_REF, q)
        if sol is None:
            raise RuntimeError(f"IK fails at t = {t:.3f} (code {code})")
        q = sol
        qs[j] = q
    return ts, qs


def path_report() -> dict:
    ts, qs = joint_path()
    qd = np.gradient(qs, ts, axis=0)
    qdd = np.gradient(qd, ts, axis=0)
    tau = np.array([pz.rnea(q, v, a) for q, v, a in zip(qs, qd, qdd, strict=True)])
    tau_drive = tau + (pz.N_GEAR**2 * pz.J_ROTOR) * qdd + pz.friction(qd)
    return {
        "q_min": qs.min(axis=0), "q_max": qs.max(axis=0),
        "margin_low": (qs.min(axis=0) - pz.Q_MIN), "margin_high": (pz.Q_MAX - qs.max(axis=0)),
        "qd_peak": np.abs(qd).max(axis=0), "qd_limit": pz.QD_MAX,
        "tau_peak": np.abs(tau_drive).max(axis=0), "tau_limit": pz.TAU_MAX,
        "q_waypoints": [qs[int(round(t / TS))] for t in WAYPOINT_TIMES],
    }  # fmt: skip


def gains() -> tuple[np.ndarray, np.ndarray]:
    """Kp = B wn^2, Kd = 2 B wn with B the largest M_ii + N^2 J_m along the joint path."""
    _, qs = joint_path(0.02)
    b = np.max([np.diag(pz.mass_matrix(q)) for q in qs], axis=0) + pz.N_GEAR**2 * pz.J_ROTOR
    return b * WN**2, 2 * b * WN


def drive_start(q0) -> dict:
    """The drive state that holds the arm at rest at q0: spring preload G/k, rotor at rest."""
    g = pz.gravity(q0)
    return {"tau": g, "spring": g / pz.K_GEAR}


def gear_damping() -> np.ndarray:
    """Spring damper of each elastic joint: ZETA of the rotor-on-spring mode (link held)."""
    jr = pz.N_GEAR**2 * pz.J_ROTOR
    return 2 * pz.ZETA_GEAR * np.sqrt(pz.K_GEAR * jr)


# ------------------------------------------------------------------ generated gravity code
def num(x: float) -> str:
    return repr(float(x))


def clean_num(x: float, tol: float = 1e-12) -> float:
    return 0.0 if abs(x) < tol else float(x)


def fk_code(upto: int = 7, indent: str = "        ") -> list[str]:
    """Scalar statements (valid Julia and Python) of the modified-DH forward kinematics of joints
    1..upto from q1..q<upto>: `R<i>_<rc>` the world rotation of link frame i, `o<i>_<c>` its origin."""
    out = []

    def emit(s: str) -> None:
        out.append(indent + s)

    prev = None  # R_{i-1}, None = identity
    for i in range(upto):
        k = i + 1
        a, d, alpha = pz.DH[i]
        ca, sa = round(math.cos(alpha)), round(math.sin(alpha))  # alpha in {0, +-pi/2}
        emit(f"c{k} = cos(q{k})")
        emit(f"s{k} = sin(q{k})")
        # A = R_{i-1} Rx(alpha): columns x, y, z
        cols = {}
        for r in range(3):
            def pr(rr, cc):
                if prev is None:
                    return "1.0" if rr == cc else "0.0"
                return f"R{k - 1}_{rr + 1}{cc + 1}"
            # Rx(alpha) = [[1,0,0],[0,ca,-sa],[0,sa,ca]]
            cols[(r, 0)] = pr(r, 0)
            cols[(r, 1)] = f"({num(ca)} * {pr(r, 1)} + {num(sa)} * {pr(r, 2)})"
            cols[(r, 2)] = f"({num(-sa)} * {pr(r, 1)} + {num(ca)} * {pr(r, 2)})"
        for r in range(3):
            emit(f"A{k}_{r + 1}1 = {cols[(r, 0)]}")
            emit(f"A{k}_{r + 1}2 = {cols[(r, 1)]}")
            emit(f"A{k}_{r + 1}3 = {cols[(r, 2)]}")
        # origin: o_i = o_{i-1} + R_{i-1} (a, -sa d, ca d)
        loc = (a, -sa * d, ca * d)
        for r in range(3):
            base = "0.0" if prev is None else f"o{k - 1}_{r + 1}"
            terms = [base]
            for c in range(3):
                if loc[c] != 0.0:
                    rc = ("1.0" if r == c else "0.0") if prev is None else f"R{k - 1}_{r + 1}{c + 1}"
                    terms.append(f"{num(loc[c])} * {rc}")
            emit(f"o{k}_{r + 1} = " + " + ".join(terms))
        # R_i = A Rz(q): x = c A_x + s A_y, y = -s A_x + c A_y, z = A_z
        for r in range(3):
            emit(f"R{k}_{r + 1}1 = c{k} * A{k}_{r + 1}1 + s{k} * A{k}_{r + 1}2")
            emit(f"R{k}_{r + 1}2 = -s{k} * A{k}_{r + 1}1 + c{k} * A{k}_{r + 1}2")
            emit(f"R{k}_{r + 1}3 = A{k}_{r + 1}3")
        prev = k
    return out


def gravity_code(indent: str = "        ") -> list[str]:
    """Scalar statements (valid Julia and Python) that compute G1..G7 from q1..q7 and g0.

    `fk_code`, then the mass-weighted centres of mass w<i> = m_i (o_i + R_i c_i), their sums
    S<i>_<c> = sum_{j>=i} w_j, and G_i = g0 (z_i,x (S_i,y - M_i o_i,y) - z_i,y (S_i,x - M_i o_i,x)),
    the torque that holds the weights of links i..7 about axis i (M_i = sum_{j>=i} m_j; the Gaz
    parameters are numbers in the code, from panda.py)."""
    out = fk_code(pz.NJ, indent)

    def emit(s: str) -> None:
        out.append(indent + s)

    for i in range(pz.NJ):
        k = i + 1
        c = pz.COM[i]
        for r in range(2):  # only x and y enter the torque about a vertical weight
            emit(f"w{k}_{r + 1} = {num(pz.MASS[i])} * (o{k}_{r + 1} + {num(c[0])} * R{k}_{r + 1}1 + "
                 f"{num(c[1])} * R{k}_{r + 1}2 + {num(c[2])} * R{k}_{r + 1}3)")  # fmt: skip
    for i in reversed(range(pz.NJ)):
        k = i + 1
        for r in range(2):
            nxt = "" if k == pz.NJ else f" + S{k + 1}_{r + 1}"
            emit(f"S{k}_{r + 1} = w{k}_{r + 1}{nxt}")
        mk = float(pz.MASS[i:].sum())
        emit(f"G{k} = g0 * (R{k}_13 * (S{k}_2 - {num(mk)} * o{k}_2) - R{k}_23 * (S{k}_1 - {num(mk)} * o{k}_1))")
    return out


def check_gravity_code(n: int = 500) -> float:
    code = "\n".join(s.strip() for s in gravity_code())
    rng = np.random.default_rng(11)
    worst = 0.0
    for _ in range(n):
        q = rng.uniform(pz.Q_MIN, pz.Q_MAX)
        env = {"cos": math.cos, "sin": math.sin, "g0": pz.G0} | {f"q{k + 1}": float(q[k]) for k in range(7)}
        exec(code, env)  # noqa: S102 - our own generated arithmetic
        g = np.array([env[f"G{k + 1}"] for k in range(7)])
        worst = max(worst, float(np.abs(g - pz.gravity(q)).max()))
    return worst


def main() -> None:
    np.set_printoptions(precision=5, suppress=True, linewidth=140)
    print("free swing start", Q_FREE, "G =", pz.gravity(Q_FREE))
    print("home flange", P_HOME, "quaternion", Q_HOME, "T_END", T_END, "waypoint times", WAYPOINT_TIMES)
    rep = path_report()
    for key, val in rep.items():
        print(f"{key:12s}", np.array(val))
    kp, kd = gains()
    print("Kp", kp)
    print("Kd", kd)
    print("gear damping", gear_damping())
    print("drive start at ready", drive_start(pz.Q_READY))
    print(f"generated gravity code vs Newton-Euler, 500 random poses: {check_gravity_code():.2e} N m")


if __name__ == "__main__":
    main()
