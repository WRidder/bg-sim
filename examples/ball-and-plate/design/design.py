# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Control design and reference numbers of the `ball-and-plate` example (writes design/design.json).

    uv run examples/ball-and-plate/design/design.py

1. Servo inner loop: a PD on the encoder angle at 500 Hz, designed on the SRV02 model with the
   plate reflected through the crank (natural frequency 50 rad/s, damping 0.8).
2. Linear axis model (4 states per axis, x, v, theta, omega; input the servo angle command), the
   camera 1 frame late, discretised at the camera rate (30 Hz, ZOH).
3. Cascaded PID (outer loop at 30 Hz on the delayed camera, filtered derivative on the
   measurement, set-point weight, clamped integral): gains from a grid search on the linear
   closed loop (overshoot <= 8 %, then the shortest settling time); the closed-loop poles and the
   step metrics are the reference values of expected.json.
4. LQR with a Kalman filter: the discrete LQR on (x, v, theta, omega, integral of the error) and a
   steady-state Kalman filter on the model augmented with the camera latency (state x_prev), from
   the camera and the encoder; reference feed-forward for tracking (theta_ff = a_d / K_bb plus the
   servo lag).
5. Robustness to the camera delay (0 to 4 frames, the controllers designed for 1) and the
   tracking error on the circle and the figure-8 of the linear loop.
6. References of the open-loop models: the fixed-tilt acceleration (5/7) g sin(alpha) and roll
   time, and the swing model's exact planar rolling equation with the plate's rotation rate and
   acceleration terms against the linearised x'' = (5/7) g sin(alpha).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm, solve_discrete_are

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402

OUT = Path(__file__).resolve().parent / "design.json"
T = rig.CAM_T

# ------------------------------------------------------------------ 1. servo inner loop
WS, ZS = 50.0, 0.8
KP_S = WS**2 * rig.J_SERVO / rig.GAIN_V
KD_S = (2 * ZS * WS * rig.J_SERVO - rig.B_SERVO) / rig.GAIN_V
TAU_F = 2.0e-3                      # derivative filter of the servo PD (s)


def servo_discrete_check():
    """Eigenvalues of the 500 Hz servo loop (exact ZOH of the motor, PD on the sampled angle with
    the filtered difference); returns the spectral radius."""
    Ts = rig.SERVO_T
    # plant states theta, omega (armature inductance neglected: L/R = 69 us); input V
    Ac = np.array([[0, 1], [0, -rig.B_SERVO / rig.J_SERVO]])
    Bc = np.array([[0], [rig.GAIN_V / rig.J_SERVO]])
    M = expm(np.block([[Ac, Bc], [np.zeros((1, 3))]]) * Ts)
    Ad, Bd = M[:2, :2], M[:2, 2:]
    a = TAU_F / (TAU_F + Ts)
    # controller states: th_prev, df; V_k = Kp(ref - th_k) - Kd df_k, df_k = a df + (1-a)(th_k - th_prev)/Ts
    # closed loop on z = [theta, omega, th_prev, df]
    A = np.zeros((4, 4))
    dfrow = np.array([(1 - a) / Ts, 0, -(1 - a) / Ts, a])          # df_k from z_k
    Vrow = -KP_S * np.array([1, 0, 0, 0]) - KD_S * dfrow
    A[:2, :] = np.hstack([Ad, np.zeros((2, 2))]) + Bd @ Vrow[None, :]
    A[2, 0] = 1.0
    A[3, :] = dfrow
    return float(max(abs(np.linalg.eigvals(A))))


# ------------------------------------------------------------------ 2. axis model
CB = rig.RHO_LINK * rig.M_BALL * rig.G0 / rig.J_SERVO      # ball weight on the servo (rad/s^2 per m)
HC = rig.H_BALL * rig.RHO_LINK                              # camera sees x + h alpha


def axis_continuous():
    """x' = v, v' = K_bb theta, theta' = omega, omega' = [G(Kp(th_r - th) - Kd omega) - B omega + rho m g x]/J."""
    J, G, B = rig.J_SERVO, rig.GAIN_V, rig.B_SERVO
    A = np.array([[0, 1, 0, 0],
                  [0, 0, rig.K_BB, 0],
                  [0, 0, 0, 1],
                  [CB, 0, -G * KP_S / J, -(B + G * KD_S) / J]])
    Bm = np.array([[0], [0], [0], [G * KP_S / J]])
    return A, Bm


def c2d(A, B, Ts):
    n, m = B.shape
    M = expm(np.block([[A, B], [np.zeros((m, n + m))]]) * Ts)
    return M[:n, :n], M[:n, n:]


AC, BC = axis_continuous()
PHI, GAM = c2d(AC, BC, T)
CCAM = np.array([1.0, 0, HC, 0])        # camera quantity of the plant state


def plant_with_delay(nd):
    """Discrete plant with nd frames of camera latency: z = [x, v, th, w, c_{k-1}, ..., c_{k-nd}]."""
    n = 4 + nd
    A = np.zeros((n, n))
    A[:4, :4] = PHI
    if nd:
        A[4, :4] = CCAM
        for j in range(1, nd):
            A[4 + j, 3 + j] = 1.0
    B = np.zeros((n, 1))
    B[:4] = GAM
    Cy = np.zeros(n)
    if nd:
        Cy[-1] = 1.0
    else:
        Cy[:4] = CCAM
    return A, B, Cy


# ------------------------------------------------------------------ 3. PID
TH_MAX = rig.THETA_MAX


class PID:
    def __init__(self, Kp, Ki, Kd, tau_d, b=1.0, e_int=0.01):
        self.Kp, self.Ki, self.Kd, self.tau_d, self.b, self.e_int = Kp, Ki, Kd, tau_d, b, e_int

    def params(self):
        return {"Kp": self.Kp, "Ki": self.Ki, "Kd": self.Kd, "tau_d": self.tau_d, "b": self.b, "e_int": self.e_int}


def sim_pid(pid: PID, nd=rig.CAM_DELAY, n=240, ref=None, x0=0.0):
    """Linear closed loop (the model's PlatePID tick, unsaturated) for the reference sequence."""
    A, B, Cy = plant_with_delay(nd)
    z = np.zeros(A.shape[0])
    z[0] = x0
    a = pid.tau_d / (pid.tau_d + T)
    i = d = 0.0
    yp = None
    xs, us = [], []
    for k in range(n):
        r = ref[k] if ref is not None else 0.1
        y = Cy @ z
        if yp is None:
            yp = y
        e = r - y
        if abs(e) < pid.e_int:          # conditional integration (anti-windup)
            i += T * e
        d = a * d + (1 - a) * (y - yp) / T
        yp = y
        u = pid.Kp * (pid.b * r - y) + pid.Ki * i - pid.Kd * d
        u = float(np.clip(u, -TH_MAX, TH_MAX))
        xs.append(z[0])
        us.append(u)
        z = A @ z + B[:, 0] * u
    return np.array(xs), np.array(us)


def pid_closed_loop(pid: PID, nd=rig.CAM_DELAY):
    """Closed-loop state matrix of the linear PID loop (plant, delay line, i, d, y_prev)."""
    A, B, Cy = plant_with_delay(nd)
    n = A.shape[0]
    a = pid.tau_d / (pid.tau_d + T)
    # controller states: i (after update uses y_k), d, yp; u_k = -Kp y - Kd d_k + Ki i_k (r = 0)
    N = n + 3
    M = np.zeros((N, N))
    # i_k = i_{k-1} - T y_k ; d_k = a d_{k-1} + (1-a)(y_k - yp)/T ; yp_k = y_k
    yrow = np.concatenate([Cy, [0, 0, 0]])
    irow = np.concatenate([-T * Cy, [1, 0, 0]])
    drow = np.concatenate([(1 - a) / T * Cy, [0, a, -(1 - a) / T]])
    urow = -pid.Kp * yrow + pid.Ki * irow - pid.Kd * drow
    M[:n, :] = np.hstack([A, np.zeros((n, 3))]) + np.outer(B[:, 0], urow)
    M[n, :] = irow
    M[n + 1, :] = drow
    M[n + 2, :] = yrow
    return M


def step_metrics(t, x, x0, x1, t0=0.0, band=0.02):
    """Rise 10-90 %, overshoot (fraction of the step), settling (2 % band) of x from x0 to x1."""
    s = (x - x0) / (x1 - x0)
    i10 = np.argmax(s >= 0.1)
    i90 = np.argmax(s >= 0.9)
    over = max(0.0, float(s.max() - 1.0))
    out = np.where(abs(s - 1.0) > band)[0]
    ts = float(t[out[-1] + 1] - t0) if len(out) and out[-1] + 1 < len(t) else float("nan")
    return {"rise": float(t[i90] - t[i10]), "overshoot": over, "settling": ts}


PID_TI = 5.0           # integral time (s); integrates only within e_int of the set-point
PID_TAU_D = 0.05       # derivative filter (s)


def design_pid():
    """Grid search: overshoot <= 8 %, still stable with 2 frames of latency, then the shortest
    settling time (2 % band) of the 0.1 m step."""
    best = None
    t = np.arange(240) * T
    for Kp in np.arange(1.0, 4.01, 0.1):
        for kd_over_kp in np.arange(0.5, 1.51, 0.05):
            Kd = Kp * kd_over_kp
            pid = PID(Kp, Kp / PID_TI, Kd, PID_TAU_D, b=1.0)
            if max(abs(np.linalg.eigvals(pid_closed_loop(pid)))) >= 0.999:
                continue
            if max(abs(np.linalg.eigvals(pid_closed_loop(pid, 2)))) >= 0.999:
                continue
            x, _ = sim_pid(pid)
            m = step_metrics(t, x, 0.0, 0.1)
            if m["overshoot"] > 0.08 or not math.isfinite(m["settling"]):
                continue
            if best is None or m["settling"] < best[0]:
                best = (m["settling"], pid, m)
    return best[1], best[2]


# ------------------------------------------------------------------ 4. LQR + Kalman
# LQR weights (Bryson: 1/max^2): x 0.02 m, v 0.05 m/s, theta 0.2 rad, omega 5 rad/s, integral 1 m s; u 0.2 rad
def design_lqr(q=(1 / 0.02**2, 1 / 0.05**2, 1 / 0.2**2, 1 / 5.0**2, 1 / 1.0**2), r=1 / 0.2**2):
    # control model with the integral of the error: s = [x, v, th, w, xi], xi+ = xi + T x
    A = np.zeros((5, 5))
    A[:4, :4] = PHI
    A[4, :4] = [T, 0, 0, 0]
    A[4, 4] = 1.0
    B = np.zeros((5, 1))
    B[:4] = GAM
    Q, R = np.diag(q), np.array([[r]])
    P = solve_discrete_are(A, B, Q, R)
    K = np.linalg.solve(R + B.T @ P @ B, B.T @ P @ A)
    return K[0], A, B


def design_kalman(q_v=0.05**2, q_w=2.0**2):
    """Steady-state Kalman filter (current-estimator form) on z = [x, v, th, w, c_prev] with the
    measurements y = [c_prev (camera, 1 frame late), th (encoder)]."""
    A, B, _ = plant_with_delay(1)
    C = np.zeros((2, 5))
    C[0, 4] = 1.0
    C[1, 2] = 1.0
    Qn = np.zeros((5, 5))
    Qn[1, 1] = q_v * T
    Qn[3, 3] = q_w * T
    Qn[0, 0] = 1e-10
    Qn[2, 2] = 1e-10
    Qn[4, 4] = 1e-10
    Rn = np.diag([rig.CAM_NOISE**2 + rig.CAM_PIX**2 / 12, (2 * math.pi / rig.ENC_CPR) ** 2 / 12])
    P = solve_discrete_are(A.T, C.T, Qn, Rn)                        # prior covariance
    L = P @ C.T @ np.linalg.inv(C @ P @ C.T + Rn)                   # current-estimator gain
    return L, A, B, C


def lqg_closed_loop(K, L, nd=1):
    """Closed loop of the LQG designed for 1 frame of latency on a plant with nd frames (r = 0)."""
    Ap, Bp, Cy = plant_with_delay(nd)
    _, Ae, Be, Ce = design_kalman()
    n = Ap.shape[0]
    # controller states: zhat (5, the prediction z[k|k-1]), xi
    # measurement: y = [camera (nd frames late), theta]
    Cm = np.zeros((2, n))
    Cm[0] = Cy
    Cm[1, 2] = 1.0
    N = n + 6
    M = np.zeros((N, N))
    # zf = zh + L (y - Ce zh) ; u = -Kx zf[0:4] - Ki xi_new ; xi_new = xi + T zf[0]
    # zh+ = Ae zf + Be u
    I5 = np.eye(5)
    Zf_z = L @ Cm                                     # zf from plant state
    Zf_h = I5 - L @ Ce                                # zf from zhat
    Kx, Ki = K[:4], K[4]
    # u = -Kx zf4 - Ki (xi + T zf0)
    u_z = -(Kx @ Zf_z[:4] + Ki * T * Zf_z[0])
    u_h = -(Kx @ Zf_h[:4] + Ki * T * Zf_h[0])
    u_xi = -Ki
    M[:n, :n] = Ap + np.outer(Bp[:, 0], u_z)
    M[:n, n:n + 5] = np.outer(Bp[:, 0], u_h)
    M[:n, n + 5] = Bp[:, 0] * u_xi
    M[n:n + 5, :n] = Ae @ Zf_z + np.outer(Be[:, 0], u_z)
    M[n:n + 5, n:n + 5] = Ae @ Zf_h + np.outer(Be[:, 0], u_h)
    M[n:n + 5, n + 5] = Be[:, 0] * u_xi
    M[n + 5, :n] = T * Zf_z[0]
    M[n + 5, n:n + 5] = T * Zf_h[0]
    M[n + 5, n + 5] = 1.0
    return M


KBB = rig.K_BB
TAU_SERVO = 2 * ZS / WS


def ff_state(xd, vd, ad, jd):
    th = ad / KBB
    w = jd / KBB
    return np.array([xd, vd, th, w]), th + TAU_SERVO * w - CB * xd / WS**2


def sim_lqg(K, L, nd=1, n=240, refs=None, ff=True):
    """Linear LQG loop (the model's PlateLQG tick); refs(k) -> (xd, vd, ad, jd)."""
    Ap, Bp, Cy = plant_with_delay(nd)
    _, Ae, Be, Ce = design_kalman()
    z = np.zeros(Ap.shape[0])
    zh = np.zeros(5)
    xi = 0.0
    xs = []
    for k in range(n):
        xd, vd, ad, jd = refs(k) if refs else (0.1, 0.0, 0.0, 0.0)
        y = np.array([Cy @ z, z[2]])
        zf = zh + L @ (y - Ce @ zh)
        sref, uff = ff_state(xd, vd, ad, jd) if ff else (np.array([xd, 0, 0, 0]), 0.0)
        xi += T * (zf[0] - xd)
        u = uff - K[:4] @ (zf[:4] - sref) - K[4] * xi
        u = float(np.clip(u, -TH_MAX, TH_MAX))
        xs.append(z[0])
        z = Ap @ z + Bp[:, 0] * u
        zh = Ae @ zf + Be[:, 0] * u
    return np.array(xs)


def poles_s(M):
    z = np.linalg.eigvals(M)
    z = z[abs(z) > 1e-9]
    s = np.log(z.astype(complex)) / T
    s = sorted(s, key=lambda v: (-v.real, abs(v.imag)))
    return s


def dominant(M, k=4):
    out = []
    for s in poles_s(M)[: 2 * k]:
        if s.imag < -1e-9:
            continue
        out.append({"re": float(s.real), "im": float(s.imag), "wn": float(abs(s)),
                    "zeta": float(-s.real / abs(s)) if abs(s) > 0 else 1.0})
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------ 5. tasks (the PlateTask block)
TASKS = {
    "circle": {"ax": 0.08, "wx": 2 * math.pi / 6.0, "px": math.pi / 2, "ay": 0.08, "wy": 2 * math.pi / 6.0, "py": 0.0},
    "figure8": {"ax": 0.10, "wx": 2 * math.pi / 8.0, "px": 0.0, "ay": 0.06, "wy": 2 * math.pi / 4.0, "py": 0.0},
}
T_RAMP = 3.0
T0_TRACK = 1.0


def smooth(t):
    """Quintic smoothstep on [0, 1] and its first three derivatives."""
    if t <= 0:
        return 0.0, 0.0, 0.0, 0.0
    if t >= 1:
        return 1.0, 0.0, 0.0, 0.0
    return (10 * t**3 - 15 * t**4 + 6 * t**5, 30 * t**2 - 60 * t**3 + 30 * t**4,
            60 * t - 180 * t**2 + 120 * t**3, 60 - 360 * t + 360 * t**2)


def task_ref(task, t, axis):
    """(p, p', p'', p''') of the PlateTask reference: p = a s(tau/T_ramp) sin(w tau + phi), tau = t - t0."""
    P = TASKS[task]
    a, w, ph = (P["ax"], P["wx"], P["px"]) if axis == 0 else (P["ay"], P["wy"], P["py"])
    tau = t - T0_TRACK
    if tau <= 0:
        return 0.0, 0.0, 0.0, 0.0
    s0, s1, s2, s3 = smooth(tau / T_RAMP)
    s1, s2, s3 = s1 / T_RAMP, s2 / T_RAMP**2, s3 / T_RAMP**3
    c = [math.sin(w * tau + ph + k * math.pi / 2) * w**k for k in range(4)]
    p0 = s0 * c[0]
    p1 = s1 * c[0] + s0 * c[1]
    p2 = s2 * c[0] + 2 * s1 * c[1] + s0 * c[2]
    p3 = s3 * c[0] + 3 * s2 * c[1] + 3 * s1 * c[2] + s0 * c[3]
    return a * p0, a * p1, a * p2, a * p3


def tracking_rms(ctrl, task, K=None, L=None, pid=None, t_from=T0_TRACK + T_RAMP + 6.0, t_end=30.0):
    n = int(t_end / T)
    res = []
    for axis in (0, 1):
        refs = [task_ref(task, k * T, axis) for k in range(n)]
        if ctrl == "pid":
            x, _ = sim_pid(pid, n=n, ref=[r[0] for r in refs])
        else:
            x = sim_lqg(K, L, n=n, refs=lambda k: refs[k])
        res.append((x, np.array([r[0] for r in refs])))
    t = np.arange(n) * T
    sel = t >= t_from
    e2 = (res[0][0] - res[0][1]) ** 2 + (res[1][0] - res[1][1]) ** 2
    return float(np.sqrt(e2[sel].mean()))


# ------------------------------------------------------------------ 6. open-loop references
def free_reference():
    a = rig.K_ROLL * rig.G0 * math.sin(math.radians(1.0))
    return {"alpha_deg": 1.0, "accel": a, "x0": -0.15, "t_cross": math.sqrt(2 * 0.15 / a),
            "x_end": -0.15 + 0.5 * a * 2.0**2, "t_end": 2.0,
            "shell_accel": 0.6 * rig.G0 * math.sin(math.radians(1.0))}


SWING = {"A_deg": 2.0, "f_hz": 2.0, "x0": 0.10, "t_end": 4.0}


def swing_reference():
    A = math.radians(SWING["A_deg"])
    W = 2 * math.pi * SWING["f_hz"]
    h, r, kr = rig.H_BALL, rig.R_BALL, rig.K_ROLL
    jr = rig.J_FACTOR * r      # J/(m r)

    def alpha(t):
        return -A * math.cos(W * t), A * W * math.sin(W * t), A * W * W * math.cos(W * t)

    def full(t, s):
        a, ad, add = alpha(t)
        x, v = s
        return [v, kr * (rig.G0 * math.sin(a) + x * ad * ad - (h + jr) * add)]

    def lin(t, s):
        a, _, _ = alpha(t)
        return [s[1], kr * rig.G0 * math.sin(a)]

    ts = np.linspace(0, SWING["t_end"], 4001)
    f = solve_ivp(full, (0, SWING["t_end"]), [SWING["x0"], 0.0], t_eval=ts, rtol=1e-11, atol=1e-13)
    li = solve_ivp(lin, (0, SWING["t_end"]), [SWING["x0"], 0.0], t_eval=ts, rtol=1e-11, atol=1e-13)
    pick = [0.5, 1.0, 2.0, 3.0, 4.0]
    idx = [int(round(p / SWING["t_end"] * 4000)) for p in pick]
    return {**SWING, "h": h, "lever": h + jr, "ts": pick,
            "x_full": [float(f.y[0][i]) for i in idx], "x_lin": [float(li.y[0][i]) for i in idx],
            "diff_end": float(f.y[0][-1] - li.y[0][-1]),
            "x_full_series": f.y[0][::20].tolist(), "x_lin_series": li.y[0][::20].tolist(),
            "t_series": ts[::20].tolist()}


# ------------------------------------------------------------------ main
def main():
    out = {"rig": rig.summary()}
    out["servo"] = {"Kp": KP_S, "Kd": KD_S, "tau_f": TAU_F, "wn": WS, "zeta": ZS,
                    "discrete_spectral_radius": servo_discrete_check(), "rate": rig.SERVO_RATE}
    out["axis"] = {"K_bb": rig.K_BB, "cb": CB, "hc": HC, "A": AC.tolist(), "B": BC[:, 0].tolist()}

    pid, mpid = design_pid()
    Mp = pid_closed_loop(pid)
    out["pid"] = {**pid.params(), "step": mpid, "poles": dominant(Mp),
                  "spectral_radius": float(max(abs(np.linalg.eigvals(Mp))))}

    K, _, _ = design_lqr()
    L, _, _, _ = design_kalman()
    Ml = lqg_closed_loop(K, L)
    xl = sim_lqg(K, L)
    t = np.arange(240) * T
    out["lqr"] = {"K": K.tolist(), "L": L.tolist(), "step": step_metrics(t, xl, 0.0, 0.1), "poles": dominant(Ml),
                  "spectral_radius": float(max(abs(np.linalg.eigvals(Ml))))}
    _, Ae, Be, Ce = design_kalman()
    out["kalman"] = {"A": Ae.tolist(), "B": Be[:, 0].tolist(), "C": Ce.tolist()}

    rob = []
    for nd in range(0, 7):
        row = {"frames": nd}
        rp = max(abs(np.linalg.eigvals(pid_closed_loop(pid, nd))))
        rl = max(abs(np.linalg.eigvals(lqg_closed_loop(K, L, nd))))
        row["pid_radius"], row["lqr_radius"] = float(rp), float(rl)
        if rp < 1:
            x, _ = sim_pid(pid, nd=nd, n=450)
            row["pid_step"] = step_metrics(np.arange(450) * T, x, 0.0, 0.1)
        if rl < 1:
            x = sim_lqg(K, L, nd=nd, n=450)
            row["lqr_step"] = step_metrics(np.arange(450) * T, x, 0.0, 0.1)
        rob.append(row)
    out["delay_robustness"] = rob

    def margin(f):
        for nd in range(0, 20):
            if max(abs(np.linalg.eigvals(f(nd)))) > 1.0 + 1e-9:
                return nd - 1
        return 20

    out["delay_margin_frames"] = {"pid": margin(lambda nd: pid_closed_loop(pid, nd)),
                                  "lqr": margin(lambda nd: lqg_closed_loop(K, L, nd))}
    out["tracking"] = {
        "circle_pid": tracking_rms("pid", "circle", pid=pid),
        "circle_lqr_ff": tracking_rms("lqr", "circle", K=K, L=L),
        "figure8_pid": tracking_rms("pid", "figure8", pid=pid),
        "figure8_lqr_ff": tracking_rms("lqr", "figure8", K=K, L=L),
        "tasks": TASKS, "t_ramp": T_RAMP, "t0": T0_TRACK,
    }
    out["free"] = free_reference()
    out["swing"] = swing_reference()
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    s = {k: out[k] for k in ("servo", "pid", "lqr", "tracking", "free")}
    s["delay"] = [(r["frames"], round(r["pid_radius"], 4), round(r["lqr_radius"], 4),
                   r.get("pid_step", {}).get("settling"), r.get("lqr_step", {}).get("settling"),
                   r.get("pid_step", {}).get("overshoot"), r.get("lqr_step", {}).get("overshoot")) for r in rob]
    s["swing"] = {k: out["swing"][k] for k in ("x_full", "x_lin", "diff_end")}
    print(json.dumps(s, indent=1, default=str))


if __name__ == "__main__":
    main()
