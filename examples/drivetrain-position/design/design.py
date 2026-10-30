# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `drivetrain-position` sample: a load-position servo on a compliant drivetrain.

Plant (the bond graph of `models/`, numbers repeated here and checked against the documents)
-------------------------------------------------------------------------------------------
DC motor (R = 1 ohm, L = 1 mH, k_t = 0.1), rotor J_m = 5e-5 with damping R_d = 1e-4, a 10:1 gear, wheel 1
(J1 = 1e-3), a **compliant shaft** (k = 1.2 N m/rad, c = 1e-3 N m s/rad) and the load wheel
J2 = 2e-3 with a load torque.  The shaft is 40 times softer than the 50 N m/rad of `drivetrain-kalman`.
Truth states ``x = [theta_m, w_m, i, theta_L, w_L]`` (the ideal gear welds wheel 1 to the rotor, so
J_eq = J_m + J1/n^2)::

    L i'     = V - R i - k_t w_m
    J_eq w_m' = k_t i - R_d w_m - tau/n,         tau = k delta + c delta',  delta = theta_m/n - theta_L
    J2  w_L'  = tau - T_load

The first torsional mode is the load wheel on the shaft spring against a motor that the back-EMF holds
nearly still: sqrt(k/J2)/2pi = 3.9 Hz, damping about 0.04 (the printed open-loop poles).

The task: 1 rad of the load wheel at 0.2 s, a 0.2 N m load torque at 2.2 s, |V| <= 24 V.

Controller 1, `naive`: a textbook PID on the motor-side position (reference n*r), tuned for the rigid
plant J_tot = J_m + (J1 + J2)/n^2 (a first-order lag in w_m, tau = 7.9 ms): zero-pole cancellation
``Td = tau``, crossover ``wc = 30 rad/s`` (about 5 Hz, above the mode), ``Ti = 4/wc``.  The rigid-body view
is blind to the mode, so the load rings.

Controller 2, `drivetrain-position`: an observer-based state-feedback servo that treats the mode as a
state instead of an enemy.

* Trajectory.  The command step goes through a septic smoothstep (zero velocity, acceleration and jerk
  at both ends) of T = 0.8 s.  Its spectrum has hardly any energy at 3.9 Hz (a rounded step spreads
  over about 1/T = 1.25 Hz), so the mode is not excited by the command.  A linear prefilter would
  do too but its derivatives are not exact; the smoothstep gives r, r', r'', r''' in closed form,
  which the feedforward needs.
* Feedforward by model inversion.  The shaft torque for the trajectory is ``tau_r = J2 r'' + c J2 r'''/k + T_hat``,
  the twist ``delta_r = tau_r/k``, the motor speed ``w_m,r = n (r' + J2 r'''/k)``, the motor torque
  ``J_eq n r'' + R_d w_m,r + tau_r/n`` and the voltage ``R/k_t`` times that plus the back-EMF ``k_t w_m,r``.
* Feedback.  LQR with integral action on ``[delta - delta_r, w_m - w_m,r, w_L - r', theta_L - r, z]``
  (the plant seen through the electrics' quasi-static limit, ZOH at 1 ms, dare).  The LQR sees the twist
  and both speeds, so the loop damps the shaft mode actively (closed-loop poles printed).
* Observer.  A steady-state Kalman filter on ``[theta_m, w_m, theta_L, w_L, T_load]`` (T_load a random walk)
  with *both* encoders.  Sensor choice: the load angle is the controlled variable and the shaft is soft, so the
  motor encoder alone gives the load position only through the model, which makes the disturbance
  torque and the twist indistinguishable for slow changes; a cheap 14-bit load encoder fixes that
  (dual-loop servo practice).  The motor encoder (12 bit) supplies the fast, collocated information
  for the damping.  Ths load torque estimate also enters the feedforward (``tau_r``) so a torque step
  is cancelled before the integrator has to learn it.

Run it with ``uv run examples/drivetrain-position/design/design.py``.  It prints the plant modes, the
design, the predicted closed loop (exact ZOH discretization of the 5-state truth including the
inductance, 12/14-bit encoders, voltage clamp) of both controllers and the open-loop plant, writes the
gains between the ``GAINS`` markers of `library/PositionController.jl` and `library/PositionPID.jl`, and writes
`expected.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.linalg import expm, solve_continuous_are, solve_discrete_are

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ plant (as in build_model.py)
R, L, KT, JM, RD = 1.0, 1e-3, 0.1, 5e-5, 1e-4
N, J1, J2 = 10.0, 1e-3, 2e-3
K, D = 1.2, 1e-3
JEQ = JM + J1 / N**2
TS, UMAX = 1e-3, 24.0
ENC_M, ENC_L = 2 * np.pi / 4096, 2 * np.pi / 16384
T_STEP, R_STEP, T_TRAJ = 0.2, 1.0, 0.8
T_DIST, TORQUE, T_END = 2.2, 0.2, 3.2
SENSOR_DELAY_TICKS = 0     # 1 if the Julia run shows the encoders one tick late

# ------------------------------------------------------------------ weights (Bryson, q = 1/sigma^2)
SIGMA = dict(delta=0.15, w_m=100.0, w_l=0.5, theta=0.05, z=0.03, u=UMAX)
Q_TORQUE, Q_WM, Q_WL = 3e-8, 1e-6, 1e-7     # Kalman process noise, per sample
# naive PID
NAIVE_WC, NAIVE_N = 30.0, 10.0


def zoh(a, b, dt):
    n, m = a.shape[0], b.shape[1]
    block = np.zeros((n + m, n + m))
    block[:n, :n], block[:n, n:] = a, b
    e = expm(block * dt)
    return e[:n, :n], e[:n, n:]


def truth():
    a = np.zeros((5, 5))
    a[0, 1] = 1
    a[1, 0], a[1, 1] = -K / N**2 / JEQ, -(RD + D / N**2) / JEQ
    a[1, 2], a[1, 3], a[1, 4] = KT / JEQ, K / N / JEQ, D / N / JEQ
    a[2, 1], a[2, 2] = -KT / L, -R / L
    a[3, 4] = 1
    a[4, 0], a[4, 1], a[4, 3], a[4, 4] = K / N / J2, D / N / J2, -K / J2, -D / J2
    b = np.zeros((5, 2))
    b[2, 0], b[4, 1] = 1 / L, -1 / J2
    return a, b


def check_models() -> None:
    """The plant numbers above must be the ones of the three model documents."""
    want = {"R": R, "IL": L, "GY": KT, "IJm": JM, "Rd": RD, "TFb": 1 / N, "IW1": J1, "IW2": J2, "C": 1 / K, "D": D}
    for name in ("drivetrain-position", "naive", "drivetrain-position-open-loop"):
        doc = json.loads((ROOT / "models" / f"{name}.bgmodel.json").read_text(encoding="utf-8"))
        params = {n["name"]: n["params"] for n in doc["diagram"]["nodes"]}
        for node, value in want.items():
            got = float(next(iter(params[node].values())))
            if abs(got - value) > 1e-12 * max(1, abs(value)):
                raise SystemExit(f"{name}: {node} = {got}, design.py has {value}; run build_model.py or fix the header")


def modes(a):
    poles = np.linalg.eigvals(a)
    pair = next(p for p in poles if p.imag > 0 and abs(p) < 300)
    wn = abs(pair)
    jb = N**2 * JM + J1
    wc, wf = np.sqrt(K / J2), np.sqrt(K * (1 / jb + 1 / J2))
    return dict(poles=poles, f_ol=wn / 2 / np.pi, zeta_ol=-pair.real / wn, f_clamped=wc / 2 / np.pi,
                f_free=wf / 2 / np.pi, zeta_free=D * (1 / jb + 1 / J2) / (2 * wf))


# ------------------------------------------------------------------ the showcase design
def design_lqr():
    a = np.zeros((5, 5))
    b = np.zeros((5, 1))
    # [delta, w_m, w_L, theta_err, z]; electrics quasi-static
    a[0, 1], a[0, 2] = 1 / N, -1
    a[1, 0], a[1, 1], a[1, 2] = -K / (N * JEQ), -(KT**2 / R + RD + D / N**2) / JEQ, D / (N * JEQ)
    a[2, 0], a[2, 1], a[2, 2] = K / J2, D / (N * J2), -D / J2
    a[3, 2], a[4, 3] = 1, 1
    b[1, 0] = KT / (R * JEQ)
    ad, bd = zoh(a, b, TS)
    q = np.diag([1 / SIGMA["delta"] ** 2, 1 / SIGMA["w_m"] ** 2, 1 / SIGMA["w_l"] ** 2,
                 1 / SIGMA["theta"] ** 2, 1 / SIGMA["z"] ** 2])
    rw = np.array([[1 / SIGMA["u"] ** 2]])
    p = solve_discrete_are(ad, bd, q, rw)
    kd = np.linalg.solve(rw + bd.T @ p @ bd, bd.T @ p @ ad).ravel()
    return ad, bd, kd


def design_observer():
    a = np.zeros((5, 5))
    a[0, 1] = 1
    a[1, 0], a[1, 1] = -K / (N**2 * JEQ), -(KT**2 / R + RD + D / N**2) / JEQ
    a[1, 2], a[1, 3] = K / (N * JEQ), D / (N * JEQ)
    a[2, 3] = 1
    a[3, 0], a[3, 1], a[3, 2], a[3, 3], a[3, 4] = K / (N * J2), D / (N * J2), -K / J2, -D / J2, -1 / J2
    b = np.zeros((5, 1))
    b[1, 0] = KT / (R * JEQ)
    phi, bd = zoh(a, b, TS)
    cm = np.array([1.0, 0, 0, 0, 0])
    cl = np.array([0, 0, 1.0, 0, 0])
    c = np.vstack([cm, cl])
    qn = np.diag([1e-12, Q_WM, 1e-12, Q_WL, Q_TORQUE])
    rn = np.diag([ENC_M**2 / 12, ENC_L**2 / 12])
    p = solve_discrete_are(phi.T, c.T, qn, rn)
    gain = p @ c.T @ np.linalg.inv(c @ p @ c.T + rn)
    return phi, bd.ravel(), cm, cl, gain[:, 0], gain[:, 1]


def septic(tau):
    t = np.clip(tau, 0, 1)
    return (35 * t**4 - 84 * t**5 + 70 * t**6 - 20 * t**7,
            140 * t**3 - 420 * t**4 + 420 * t**5 - 140 * t**6,
            420 * t**2 - 1680 * t**3 + 2100 * t**4 - 840 * t**5,
            840 * t - 5040 * t**2 + 8400 * t**3 - 4200 * t**4)


def trajectory(tk, r0, r1):
    s, s1, s2, s3 = septic(tk * TS / T_TRAJ)
    d = r1 - r0
    return r0 + d * s, d * s1 / T_TRAJ, d * s2 / T_TRAJ**2, d * s3 / T_TRAJ**3


def quantize(x, step):
    return step * np.floor(abs(x) / step + 0.5) * np.sign(x)      # half away from zero, like the Quantizer


def simulate_showcase(g, delay=SENSOR_DELAY_TICKS, tend=T_END):
    """The 1 kHz firmware against the exact ZOH 5-state truth (the same algorithm as the Julia block)."""
    a, b = truth()
    ad, bd = zoh(a, b, TS)
    x, xh, z = np.zeros(5), np.zeros(5), 0.0
    r0 = r1 = rr = 0.0
    tk = 0.0
    pending = np.zeros(2)
    cols = {k: [] for k in ("t", "thL", "thm", "u", "r", "Th", "thLh", "i", "delta")}
    for k in range(int(round(tend / TS))):
        t = k * TS
        cmd = R_STEP if t >= T_STEP - 1e-12 else 0.0
        if cmd != r1:
            r0, r1, tk = rr, cmd, 0.0
        rr, rd, rdd, rddd = trajectory(tk, r0, r1)
        y = np.array([quantize(x[0], ENC_M), quantize(x[3], ENC_L)])
        if delay:
            y, pending = pending, y
        xh = xh + g["Lm"] * (y[0] - g["Cm"] @ xh) + g["Ll"] * (y[1] - g["Cl"] @ xh)
        z += TS * (xh[2] - rr)
        tau_r = J2 * rdd + D * J2 * rddd / K + xh[4]
        wm_r = N * (rd + J2 * rddd / K)
        uff = R / KT * (JEQ * N * rdd + RD * wm_r + tau_r / N) + KT * wm_r
        e = np.array([xh[0] / N - xh[2] - tau_r / K, xh[1] - wm_r, xh[3] - rd, xh[2] - rr, z])
        v = uff - g["K"] @ e
        u = float(np.clip(v, -UMAX, UMAX))
        if abs(v) > UMAX:
            z -= TS * (xh[2] - rr)
        xh = g["Phi"] @ xh + g["Bd"] * u
        for key, val in zip(cols, (t, x[3], x[0], u, rr, xh[4], xh[2], x[2], x[0] / N - x[3])):
            cols[key].append(val)
        x = ad @ x + bd @ np.array([u, TORQUE if t >= T_DIST - 1e-12 else 0.0])
        tk += 1
    return {k: np.array(v) for k, v in cols.items()}


def design_naive():
    jtot = JM + (J1 + J2) / N**2
    damping = KT**2 / R + RD
    kg, tau = (KT / R) / damping, jtot / damping
    kp = NAIVE_WC / kg
    return dict(Kp=kp, Ti=4 / NAIVE_WC, Td=tau, N=NAIVE_N, kg=kg, tau=tau)


def simulate_naive(p, tend=T_END):
    a, b = truth()
    ad, bd = zoh(a, b, TS)
    x = np.zeros(5)
    xi = xd = 0.0
    tt = np.sqrt(p["Ti"] * p["Td"])
    alpha = 1 - np.exp(-p["N"] * TS / p["Td"])
    cols = {k: [] for k in ("t", "thL", "thm", "u", "delta")}
    for k in range(int(round(tend / TS))):
        t = k * TS
        ref = N * R_STEP if t >= T_STEP - 1e-12 else 0.0
        y = x[0]
        e = ref - y
        xd += alpha * (y - xd)
        v = p["Kp"] * e + xi - p["Kp"] * p["Td"] * p["N"] * (y - xd)
        u = float(np.clip(v, -UMAX, UMAX))
        xi += TS * (p["Kp"] / p["Ti"] * e + (u - v) / tt)
        for key, val in zip(cols, (t, x[3], x[0], u, x[0] / N - x[3])):
            cols[key].append(val)
        x = ad @ x + bd @ np.array([u, TORQUE if t >= T_DIST - 1e-12 else 0.0])
    return {k: np.array(v) for k, v in cols.items()}


def simulate_open_loop():
    a, b = truth()
    ad, bd = zoh(a, b, TS)
    x = np.zeros(5)
    out = []
    for k in range(1001):
        t = k * TS
        out.append((t, *x))
        x = ad @ x + bd @ np.array([2.0 if t >= 0.05 - 1e-12 else 0.0, TORQUE if t >= 0.6 - 1e-12 else 0.0])
    return np.array(out)


# ------------------------------------------------------------------ metrics
def metrics(o):
    t, y = o["t"], o["thL"]
    over = max(0.0, (y.max() - R_STEP) / R_STEP)
    band = 0.02 * R_STEP
    m = (t > T_STEP) & (t < T_DIST)
    out = np.nonzero((np.abs(y - R_STEP) > band) & m)[0]
    settle = (t[out[-1]] - T_STEP) if len(out) else 0.0
    calm = (t >= 1.4) & (t < T_DIST)
    d = t >= T_DIST
    dist_peak = np.abs(y[d] - R_STEP).max()
    rec_out = np.nonzero((np.abs(y - R_STEP) > band) & d)[0]
    recovery = (t[rec_out[-1]] - T_DIST) if len(rec_out) else 0.0
    return dict(overshoot=over, settle=settle, ripple_pp=float(np.ptp(y[calm])), dist_peak=float(dist_peak),
                dist_min=float(y[d].min()), recovery=recovery, umax=float(np.abs(o["u"]).max()),
                final=float(y[-1]), twist_max=float(np.abs(o["delta"]).max()))


# ------------------------------------------------------------------ writing
def fmt(x):
    text = f"{float(x):.12g}"
    return text if any(c in text for c in ".en") else text + ".0"


def vec(v):
    return "[" + ", ".join(fmt(x) for x in np.ravel(v)) + "]"


def mat(m):
    return "[" + "; ".join(" ".join(fmt(x) for x in row) for row in m) + "]"


def write_block(path, lines):
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(        # ---- GAINS \(written by design/design.py\) ----\n).*?(        # ---- END GAINS ----\n)", re.S)
    body = "".join(f"        {line}\n" for line in lines)
    new, count = pattern.subn(lambda m: m.group(1) + body + m.group(2), text)
    if count != 1:
        raise SystemExit(f"no GAINS block in {path}")
    path.write_text(new, encoding="utf-8", newline="\n")


def write_gains(g, naive):
    write_block(ROOT / "library" / "PositionController.jl", [
        f'Phi::Mat{{nx,nx}} = {mat(g["Phi"])}, [description = "Discrete state matrix of the design model [theta_m, w_m, theta_L, w_L, T_load] at 1 ms"]',
        f'Bd::Vec{{nx}} = {vec(g["Bd"])}, [description = "Discrete input vector (volts)"]',
        'Cm::Vec{nx} = [1.0, 0.0, 0.0, 0.0, 0.0], [description = "Motor encoder measurement vector"]',
        'Cl::Vec{nx} = [0.0, 0.0, 1.0, 0.0, 0.0], [description = "Load encoder measurement vector"]',
        f'Lm::Vec{{nx}} = {vec(g["Lm"])}, [description = "Kalman gain column of the motor encoder"]',
        f'Ll::Vec{{nx}} = {vec(g["Ll"])}, [description = "Kalman gain column of the load encoder"]',
        f'K::Vec{{5}} = {vec(g["K"])}, [description = "LQR gain on [delta, w_m, w_L, theta_L error, z]"]',
        f'gear::Real = {fmt(N)}, [description = "Gear ratio n"]',
        f'J2::Real = {fmt(J2)}, [unit = "kg*m^2", description = "Load wheel inertia"]',
        f'Jeq::Real = {fmt(JEQ)}, [unit = "kg*m^2", description = "Motor-side inertia (rotor plus wheel 1 reflected)"]',
        f'Rd::Real = {fmt(RD)}, [description = "Motor viscous damping"]',
        f'Ksh::Real = {fmt(K)}, [unit = "N*m/rad", description = "Shaft stiffness"]',
        f'Dsh::Real = {fmt(D)}, [unit = "N*m*s/rad", description = "Shaft damping"]',
        f'Rm::Real = {fmt(R)}, [unit = "Ohm", description = "Armature resistance"]',
        f'kt::Real = {fmt(KT)}, [description = "Motor constant"]',
        f'Ttraj::Real = {fmt(T_TRAJ)}, [unit = "s", min = 1e-3, description = "Duration of the smoothstep trajectory"]',
        f'umax::Real = {fmt(UMAX)}, [unit = "V", min = 0.0, description = "Voltage limit"]',
    ])
    write_block(ROOT / "library" / "PositionPID.jl", [
        f'Kp::Real = {fmt(naive["Kp"])}, [unit = "V/rad", description = "Proportional gain"]',
        f'Ti::Real = {fmt(naive["Ti"])}, [unit = "s", min = 1e-6, description = "Integral time"]',
        f'Td::Real = {fmt(naive["Td"])}, [unit = "s", min = 1e-6, description = "Derivative time"]',
        f'N::Real = {fmt(naive["N"])}, [min = 1e-6, description = "Derivative filter ratio"]',
        f'umax::Real = {fmt(UMAX)}, [unit = "V", min = 0.0, description = "Voltage limit"]',
    ])


def expected(sc, nv, ol, ms, mn):
    """expected.json from the predictions.  Tolerances are justified in each note."""
    t = sc["t"]
    at = lambda arr, tt: float(np.interp(tt, t, arr))
    diag = ["E003", "E006", "E102", "E106", "E303", "E901", "W206"]
    first = int(np.argmax(nv["thL"]))
    t_pk, v_pk = float(nv["t"][first]), float(nv["thL"][first])
    late = (nv["t"] >= 1.8) & (nv["t"] < T_DIST)
    j = int(np.argmax(nv["thL"][late]))
    t_late, v_late = float(nv["t"][late][j]), float(nv["thL"][late][j])
    peak_floor = round(1 + 0.8 * (v_pk - 1), 3)
    late_floor = round(1 + 0.6 * (v_late - 1), 3)
    show = [
        {"kind": "scene_bindings"},
        {"kind": "max_abs", "signal": "ThetaL/y", "from_t": 0.0, "to_t": 0.19, "value": 0.0, "abs": 1e-6,
         "note": "rest before the step: the load angle stays at zero (the reference and the estimator start at zero, so nothing moves)"},
        {"kind": "max_abs", "signal": "IW2/p.f", "from_t": 0.0, "to_t": 0.19, "value": 0.0, "abs": 1e-6,
         "note": "rest before the step: the load speed stays at zero"},
        {"kind": "step_response", "signal": "ThetaL/y", "from_t": 0.15, "to_t": 2.15, "step_t": 0.2, "initial": 0.0,
         "value": R_STEP, "settle_abs": 0.02, "max_overshoot": 0.02, "max_settling_time": 0.9,
         "note": f"load position settles in the 0.02 rad (2 %) band by 0.9 s after the step (predicted {ms['settle']:.3f} s: the {T_TRAJ} s trajectory plus the tail) with overshoot below 2 % (predicted {100 * ms['overshoot']:.2f} %); limits are about 1.3 times the prediction"},
        {"kind": "final_value", "signal": "ThetaL/y", "t": 2.15, "value": R_STEP, "abs": 0.005,
         "note": "just before the disturbance the load is at 1 rad within 5 mrad (the load encoder LSB is 0.38 mrad)"},
        {"kind": "ripple", "signal": "ThetaL/y", "from_t": 1.4, "to_t": 2.15, "measure": "pp", "value": 0.004,
         "note": f"residual oscillation after settling: peak-to-peak below 4 mrad (predicted {1000 * ms['ripple_pp']:.2f} mrad, about 10 encoder LSB of the load; the shaft mode is damped, not ringing)"},
        {"kind": "min_ge", "signal": "ThetaL/y", "from_t": T_DIST, "to_t": T_END, "value": round(1 - 1.6 * ms["dist_peak"], 3),
         "note": f"the 0.2 N m load torque (a 0.17 rad static twist) dips the load by at most {1.6 * ms['dist_peak']:.3f} rad (predicted dip {ms['dist_peak']:.3f} rad)"},
        {"kind": "final_value", "signal": "ThetaL/y", "t": T_END, "value": R_STEP, "abs": 0.01,
         "note": f"the disturbance is rejected: the load is back within 10 mrad of 1 rad 1 s after it (predicted recovery into the 20 mrad band after {ms['recovery']:.3f} s)"},
        {"kind": "max_abs_le", "signal": "V/p.e", "from_t": 0.0, "to_t": T_END, "value": UMAX,
         "note": f"the motor voltage stays inside the 24 V supply limit (predicted peak {ms['umax']:.1f} V)"},
        {"kind": "final_value", "signal": "Ctrl/T_hat", "t": T_END, "value": TORQUE, "rtol": 0.05,
         "note": "the Kalman filter has learned the 0.2 N m load torque (5 %)"},
        {"kind": "rms_difference", "signal": "Ctrl/theta_L_hat", "signal_b": "ThetaL/y", "from_t": 0.3, "to_t": T_END,
         "value": 0.003, "note": "the estimate follows the load angle within 3 mrad RMS over the whole move"},
    ]
    for tt in (0.5, 0.7, 0.9, 1.5, 2.3, 2.5, 3.0):
        show.append({"kind": "cursor_value", "signal": "ThetaL/y", "t": tt, "value": round(at(sc["thL"], tt), 6), "abs": 0.004,
                     "note": "closed-loop prediction of design.py (exact 5-state truth with the 1 mH inductance, 12/14-bit encoders); 4 mrad tolerance for the solver and the encoder phase"})
    show.append({"kind": "no_diagnostics", "codes": diag,
                 "note": "no solver failure, causal conflict, event-limit stop or invalid unit. W201 (IW1/IJm in derivative causality: the ideal gear welds the two inertias) and W205 (dimensionless bond island) are expected bond-graph causality"})
    nai = [
        {"kind": "scene_bindings"},
        {"kind": "min_ge", "signal": "ThetaL/y", "from_t": round(t_pk - 0.01, 3), "to_t": round(t_pk + 0.01, 3), "value": peak_floor,
         "note": f"the contrast is real: the first load peak is at least {peak_floor} rad, an overshoot of {100 * (peak_floor - 1):.0f} % or more (predicted {v_pk:.3f} rad at {t_pk:.3f} s; the showcase overshoots by {100 * ms['overshoot']:.2f} %)"},
        {"kind": "min_ge", "signal": "ThetaL/y", "from_t": round(t_late - 0.01, 3), "to_t": round(t_late + 0.01, 3), "value": late_floor,
         "note": f"and it is still ringing 1.6 s later: the peak near {t_late:.2f} s is above {late_floor} rad (predicted {v_late:.3f}); the showcase is still inside 5 mrad"},
        {"kind": "fft_peak", "signal": "ThetaL/y", "from_t": 0.5, "to_t": T_DIST - 0.05, "min_hz": 1.0, "max_hz": 12.0, "value": round(ms["naive_fft"], 2), "rtol": 0.06,
         "note": f"the load rings at the shaft mode, about {ms['naive_fft']:.2f} Hz (open-loop mode {ms['f_ol']:.2f} Hz, motor held {ms['f_clamped']:.2f} Hz)"},
        {"kind": "max_abs_le", "signal": "V/p.e", "from_t": 0.0, "to_t": T_END, "value": UMAX,
         "note": "the naive loop saturates on the step but stays inside 24 V"},
        {"kind": "no_diagnostics", "codes": diag, "note": "same diagnostics policy as the showcase"},
    ]
    olc = [
        {"kind": "scene_bindings"},
    ]
    for tt in (0.1, 0.2, 0.3, 0.45, 0.6, 0.7, 0.9, 1.0):
        i = int(round(tt / 1e-3))
        olc.append({"kind": "cursor_value", "signal": "ThetaL/y", "t": tt, "value": round(float(ol[i, 4]), 9), "abs": 1e-6,
                    "note": "load angle of the plant ODE (5 states: rotor, inductance, load; exact ZOH): the bond-graph plant agrees to 1e-8 rad; the check allows 1 urad (solver reltol 1e-8)"})
        olc.append({"kind": "cursor_value", "signal": "Theta/y", "t": tt, "value": round(float(ol[i, 1]), 9), "abs": 1e-5,
                    "note": "motor angle of the plant ODE, 10 urad absolute (the motor angle is ten times the load angle; the difference is 1e-8 rad)"})
    olc.append({"kind": "no_diagnostics", "codes": diag})
    return {"project": "drivetrain-position",
            "description": "X5.14: load-position servo of a compliant drivetrain (first shaft mode ~3.9 Hz, damping ~0.04). The plant is a pure bond graph (MSe, I, R, GY, TF, C, 0/1-junctions). `drivetrain-position` is a 1 kHz firmware (smooth trajectory, Kalman filter on two encoders, feedforward, LQR with integral action); `naive` is a textbook PID on the motor-side position; `drivetrain-position-open-loop` compares the plant with the ODE of design/design.py.",
            "models": {"drivetrain-position": {"checks": show}, "naive": {"checks": nai},
                       "drivetrain-position-open-loop": {"checks": olc}}}


def main() -> None:
    check_models()
    a, _ = truth()
    md = modes(a)
    print(f"plant: J_eq = {JEQ:.4g} kg m^2 (motor side), shaft k = {K} N m/rad, c = {D} N m s/rad, J2 = {J2}")
    print("open-loop poles [rad/s]:", np.round(np.sort_complex(md["poles"]), 2))
    print(f"first torsional mode, voltage-driven plant: {md['f_ol']:.3f} Hz, zeta = {md['zeta_ol']:.4f}")
    print(f"  motor held: {md['f_clamped']:.3f} Hz;  motor free (rod damping only): {md['f_free']:.3f} Hz, zeta = {md['zeta_free']:.4f}")

    ad, bd, kd = design_lqr()
    cl = np.log(np.linalg.eigvals(ad - bd @ kd.reshape(1, -1)).astype(complex)) / TS
    print("LQR gain [delta, w_m, w_L, theta_err, z] =", np.round(kd, 4))
    print("closed-loop poles [rad/s]:", np.round(np.sort_complex(cl), 2))
    ordered = sorted(cl, key=abs)
    mode = [p for p in ordered if p.imag > 1][0]
    print(f"  shaft mode closed loop: {abs(mode) / 2 / np.pi:.2f} Hz, zeta = {-mode.real / abs(mode):.3f}")
    phi, bdo, cm, cl_vec, lm, ll = design_observer()
    lt = np.column_stack([lm, ll])
    obs = np.log(np.linalg.eigvals(phi @ (np.eye(5) - lt @ np.vstack([cm, cl_vec]))).astype(complex)) / TS
    print("observer poles [rad/s]:", np.round(np.sort_complex(obs), 1))
    g = dict(Phi=phi, Bd=bdo, Cm=cm, Cl=cl_vec, Lm=lm, Ll=ll, K=kd)
    sc = simulate_showcase(g)
    ms = metrics(sc)
    naive = design_naive()
    nv = simulate_naive(naive)
    mn = metrics(nv)
    print(f"\nnaive PID (motor side): Kp = {naive['Kp']:.3f} V/rad, Ti = {naive['Ti']:.4f} s, Td = {naive['Td']:.4f} s, N = {naive['N']:g}")
    for name, m in (("showcase", ms), ("naive", mn)):
        print(f"{name:9s} overshoot {100 * m['overshoot']:.2f} %  settle(2 %) {m['settle']:.3f} s  ripple pp {1000 * m['ripple_pp']:.2f} mrad  "
              f"dist dip {m['dist_peak']:.3f} rad  recovery {m['recovery']:.3f} s  final {m['final']:.4f}  peak V {m['umax']:.2f}  max twist {m['twist_max']:.3f} rad")
    # dominant frequency of the naive ringing between 0.5 s and the disturbance
    w = (nv["t"] >= 0.5) & (nv["t"] < T_DIST - 0.05)
    y = nv["thL"][w] - np.polyval(np.polyfit(nv["t"][w], nv["thL"][w], 1), nv["t"][w])
    spec = np.abs(np.fft.rfft(y * np.hanning(y.size), 1 << 16))
    freqs = np.fft.rfftfreq(1 << 16, TS)
    band = (freqs > 1) & (freqs < 12)
    ms["naive_fft"] = float(freqs[band][np.argmax(spec[band])])
    ms.update(f_ol=md["f_ol"], f_clamped=md["f_clamped"])
    print(f"naive ringing frequency {ms['naive_fft']:.2f} Hz")

    ol = simulate_open_loop()
    write_gains(g, naive)
    exp = expected(sc, nv, ol, ms, mn)
    (ROOT / "expected.json").write_text(json.dumps(exp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote library/PositionController.jl, library/PositionPID.jl, expected.json")


if __name__ == "__main__":
    main()
