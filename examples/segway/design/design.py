# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Parameters, linear-quadratic design and independent reference simulation of the `segway`
example (a two-wheeled self-balancing personal transporter with a rider).

Run it with ``uv run examples/segway/design/design.py``: it prints the open-loop pole, the
Riccati gains, the closed-loop poles and the reference values the checks in ``expected.json``
use, and writes them to ``design.json`` (which ``build_model.py`` reads).

Plant (Lagrange, pitch plane, no slip, ``x`` = axle position, ``theta`` = body pitch from
upright, positive forward). Body mass ``m_b`` with its centre of mass ``l`` above the axle, wheels
of total mass ``2 m_w`` and spin inertia ``J_w = 2 J_wa`` rolling with ``phi = x / r``, motor
rotors (reflected through the gear ratio ``n``) of total inertia ``J_r = 2 n^2 J_m`` turning
with the rate of the wheel relative to the body ``phi' - theta'``:

    T = 1/2 (m_b + 2 m_w) x'^2 + m_b l cos(theta) x' theta' + 1/2 (J_b + m_b l^2) theta'^2
        + 1/2 J_w phi'^2 + 1/2 J_r (phi' - theta')^2
    V = m_b g l cos(theta)

    (M_t + (J_w + J_r)/r^2) x'' + (m_b l cos(theta) - J_r/r) theta'' - m_b l sin(theta) theta'^2
                                                         = tau / r + F cos(theta)
    (m_b l cos(theta) - J_r/r) x'' + (J_b + m_b l^2 + J_r) theta'' - m_b g l sin(theta)
                                                         = -tau + F l

``tau`` is the torque of both motors on the wheels (the reaction ``-tau`` acts on the body). Each
motor is current controlled (``tau_i = n k_t i_i``, ideal current loop as in a real personal
transporter's drive), and the voltage it needs is ``V = R i + k_t n (phi' - theta')`` (checked against
the 72 V bus). ``F`` is a horizontal push in the body x direction at the centre of mass.

Yaw: the wheels turn ``phi_R - phi_L = b psi / r`` and a differential torque ``tau_d`` (+ on the right wheel, - on the left) gives

    I_eff psi'' = (b / r) tau_d,     I_eff = I_z + (J_wa + n^2 J_m) b^2 / (2 r^2).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import solve_continuous_are

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------- parameters
# P = published (source in README), E = estimate (README says how it was chosen)
PARAMS = dict(
    g=9.81,                 # P standard gravity
    m_b=105.0,              # E rider 75 kg (Moore 2015: person + platform 75 kg) + frame/batteries 30 kg
    l=0.52,                 # E body centre of mass above the axle (rider 0.71 m, low batteries)
    J_bx=12.0,              # E roll inertia of the body about its centre of mass
    J_by=16.0,              # E pitch inertia (Moore 2015: 14 kg m^2 person + platform)
    J_bz=3.0,               # E yaw inertia
    r=0.24,                 # E wheel radius (Segway PT: about 19 inch tyre, 0.48 m diameter)
    m_w=5.0,                # E one wheel with tyre
    J_wa=0.15,              # E wheel inertia about the axle
    J_wt=0.08,              # E wheel inertia about a diameter
    b=0.45,                 # E distance between the two wheel centres (PT is 0.635 m wide overall)
    n=24.0,                 # E gear ratio motor : wheel
    k_t=0.12,               # E motor torque constant, N m / A at the motor
    R=0.15,                 # E winding resistance per motor
    L=4.0e-4,               # E winding inductance per motor
    J_m=0.0,                # E rotor inertia neglected (reflected n^2 J_m of both motors would be 0.1 kg m^2, 2 % of the translational mass); a rotor inertia on the joint rate is a derivative-causal store
    U_max=72.0,             # P Segway PT battery bus 72 V (nominal)
    tau_max=80.0,           # E peak torque per wheel
    v_max=5.56,             # P Segway i2 top speed 20 km/h
)
# initial state and scenario of the `balance` model
THETA0 = 0.03
T_END = 14.0
V_STEP = 1.5      # m/s speed set-point (ramped)
T_RAMP0, T_RAMP = 3.0, 1.5
PUSH_F, PUSH_T0, PUSH_W = 150.0, 9.0, 0.15
#: the `top-speed` run: ramp up to the published top speed of the Segway i2 (20 km/h)
TOP = dict(v_step=20 / 3.6, t_ramp0=2.0, t_ramp=9.0, t_end=17.0)

#: the `open-loop` run: released 0.002 rad off upright with no control
OPEN = dict(theta0=0.002, t_end=1.0)

#: weights of the LQR, Bryson normalisation q = 1/sigma^2 (state order xi, v, theta, theta')
SIGMA = dict(xi=0.4, v=0.4, theta=0.15, w=0.6, u=150.0)
#: yaw loop: wanted natural frequency and damping ratio of the heading loop
YAW_WN, YAW_ZETA = 6.0, 0.9


def derived(p=PARAMS):
    d = dict(p)
    d["K"] = p["n"] * p["k_t"]                       # N m / A at the wheel
    d["J_w"] = 2 * p["J_wa"]
    d["J_r"] = 2 * p["n"] ** 2 * p["J_m"]
    d["M_t"] = p["m_b"] + 2 * p["m_w"]
    d["I_z"] = p["J_bz"] + p["m_w"] * p["b"] ** 2 / 2 + 2 * p["J_wt"]
    d["I_eff"] = d["I_z"] + (p["J_wa"] + p["n"] ** 2 * p["J_m"]) * p["b"] ** 2 / (2 * p["r"] ** 2)
    return d


D = derived()


def mass_matrix(theta):
    a11 = D["M_t"] + (D["J_w"] + D["J_r"]) / D["r"] ** 2
    a12 = D["m_b"] * D["l"] * np.cos(theta) - D["J_r"] / D["r"]
    a22 = D["J_by"] + D["m_b"] * D["l"] ** 2 + D["J_r"]
    return np.array([[a11, a12], [a12, a22]])


def linear_model():
    """States [x, v, theta, theta'], input the total wheel torque (current loops ideal)."""
    r, g = D["r"], D["g"]
    Mi = np.linalg.inv(mass_matrix(0.0))
    A = np.zeros((4, 4))
    A[0, 1] = 1.0
    A[2, 3] = 1.0
    A[1, 2], A[3, 2] = (Mi @ np.array([[0.0], [D["m_b"] * g * D["l"]]]))[:, 0]
    B = np.zeros(4)
    B[1], B[3] = Mi @ np.array([1.0 / r, -1.0])
    return A, B


def lqr():
    A, B = linear_model()
    Q = np.diag([1 / SIGMA["xi"] ** 2, 1 / SIGMA["v"] ** 2, 1 / SIGMA["theta"] ** 2, 1 / SIGMA["w"] ** 2])
    R = np.array([[1 / SIGMA["u"] ** 2]])
    P = solve_continuous_are(A, B.reshape(4, 1), Q, R)
    K = (np.linalg.inv(R) @ B.reshape(1, 4) @ P).ravel()
    return A, B, K


def yaw_gains():
    """PD heading gains for I_eff psi'' = (b/r) tau_d: tau_d = kp (psi_ref - psi) - kd psi'."""
    k = D["I_eff"] * D["r"] / D["b"]
    return YAW_WN ** 2 * k, 2 * YAW_ZETA * YAW_WN * k


# ---------------------------------------------------------------------------- reference simulation
def v_ref_fn(t):
    return V_STEP * np.clip((t - T_RAMP0) / T_RAMP, 0.0, 1.0)


def push_fn(t):
    return PUSH_F if PUSH_T0 <= t < PUSH_T0 + PUSH_W else 0.0


def simulate(K, t_end=T_END, theta0=THETA0, h=2e-4, push=True, vref=True, vref_fn=None):
    """Non-linear pitch-plane closed loop (RK4): rows t, x, v, theta, w, tau, xi, V_req.

    The torque command is clamped to +-2 tau_max (both wheels) and is delivered at once (ideal
    current loops, no winding dynamics)."""
    r, g = D["r"], D["g"]
    mb, l = D["m_b"], D["l"]
    tmax = 2 * D["tau_max"]

    def ctrl(s, t):
        xi, v, th, w = s[4], s[1], s[2], s[3]
        vr = (vref_fn or v_ref_fn)(t) if vref else 0.0
        return float(np.clip(-(K[0] * xi + K[1] * (v - vr) + K[2] * th + K[3] * w), -tmax, tmax))

    def f(s, t, tau):
        x, v, th, w, xi = s
        vr = (vref_fn or v_ref_fn)(t) if vref else 0.0
        Fp = push_fn(t) if push else 0.0
        M = mass_matrix(th)
        rhs = np.array([tau / r + Fp * np.cos(th) + mb * l * np.sin(th) * w * w,
                        -tau + Fp * l + mb * g * l * np.sin(th)])
        acc = np.linalg.solve(M, rhs)
        return np.array([v, acc[0], w, acc[1], v - vr])

    s = np.array([0.0, 0.0, theta0, 0.0, 0.0])
    n = int(round(t_end / h))
    out = np.empty((n + 1, 8))
    for k in range(n + 1):
        t = k * h
        tau = ctrl(s, t)
        i = tau / 2 / (D["n"] * D["k_t"])
        vreq = D["R"] * i + D["k_t"] * D["n"] * (s[1] / r - s[3])
        out[k] = (t, s[0], s[1], s[2], s[3], tau, s[4], vreq)
        k1 = f(s, t, tau)
        k2 = f(s + 0.5 * h * k1, t + 0.5 * h, ctrl(s + 0.5 * h * k1, t + 0.5 * h))
        k3 = f(s + 0.5 * h * k2, t + 0.5 * h, ctrl(s + 0.5 * h * k2, t + 0.5 * h))
        k4 = f(s + h * k3, t + h, ctrl(s + h * k3, t + h))
        s = s + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return out


# ---------------------------------------------------------------------------- figure of eight
EIGHT = dict(v_cruise=1.5, t_go=1.0, tau_v=0.8, t_turn=4.0, t_loop=11.0, dpsi=2 * np.pi, tau_psi=0.4, t_end=28.0)


def _G(x, tau):
    """Integral of the smooth unit step 0.5 (1 + tanh(x / tau))."""
    return 0.5 * (x + tau * np.log(2 * np.cosh(x / tau)))


def eight_refs(t, p=EIGHT):
    v = p["v_cruise"] * 0.5 * (1 + np.tanh((t - p["t_go"]) / p["tau_v"]))
    tp, T = p["tau_psi"], p["t_loop"]
    psi = p["dpsi"] / T * (_G(t - p["t_turn"], tp) - 2 * _G(t - p["t_turn"] - T, tp) + _G(t - p["t_turn"] - 2 * T, tp))
    return v, psi


EIGHT_START = (-4.4, 0.0)


def simulate_eight(K, start=EIGHT_START, h=2e-4):
    """Pitch plane (non-linear, as `simulate`, upright start) plus the linear yaw loop and the
    kinematic path: rows t, v, psi, psi', x, y, tau_d, theta."""
    p = EIGHT
    kp, kd = yaw_gains()
    gain = D["b"] / D["r"] / D["I_eff"]
    pitch = simulate(K, t_end=p["t_end"], theta0=0.0, h=h, push=False, vref_fn=lambda t: eight_refs(t)[0])
    t = pitch[:, 0]
    v = pitch[:, 2]
    n = len(t)
    psi = np.zeros(n)
    dpsi = np.zeros(n)
    x = np.zeros(n)
    y = np.zeros(n)
    tau_d = np.zeros(n)
    x[0], y[0] = start

    def accel(tk, ps, dps):
        pr = eight_refs(tk)[1]
        td = kp * (pr - ps) - kd * dps
        return gain * td, td

    for k in range(n - 1):
        # semi-implicit Euler on the yaw loop is not accurate enough: use RK4 with v, psi held on the grid
        tk = t[k]
        a1, td = accel(tk, psi[k], dpsi[k])
        tau_d[k] = td
        hh = t[k + 1] - tk
        k1p, k1d = dpsi[k], a1
        a2, _ = accel(tk + hh / 2, psi[k] + hh / 2 * k1p, dpsi[k] + hh / 2 * k1d)
        k2p, k2d = dpsi[k] + hh / 2 * k1d, a2
        a3, _ = accel(tk + hh / 2, psi[k] + hh / 2 * k2p, dpsi[k] + hh / 2 * k2d)
        k3p, k3d = dpsi[k] + hh / 2 * k2d, a3
        a4, _ = accel(tk + hh, psi[k] + hh * k3p, dpsi[k] + hh * k3d)
        k4p, k4d = dpsi[k] + hh * k3d, a4
        psi[k + 1] = psi[k] + hh / 6 * (k1p + 2 * k2p + 2 * k3p + k4p)
        dpsi[k + 1] = dpsi[k] + hh / 6 * (k1d + 2 * k2d + 2 * k3d + k4d)
        x[k + 1] = x[k] + hh * 0.5 * (v[k] * np.cos(psi[k]) + v[k + 1] * np.cos(psi[k + 1]))
        y[k + 1] = y[k] + hh * 0.5 * (v[k] * np.sin(psi[k]) + v[k + 1] * np.sin(psi[k + 1]))
    return np.column_stack([t, v, psi, dpsi, x, y, tau_d, pitch[:, 3], pitch[:, 5] / 2])


def main():
    A, B, K = lqr()
    ol = np.linalg.eigvals(A)
    cl = np.linalg.eigvals(A - np.outer(B, K))
    kp, kd = yaw_gains()
    print("derived:", {k: round(float(v), 5) for k, v in D.items() if k in ("K", "J_w", "J_r", "M_t", "I_z", "I_eff")})
    print("open-loop eigenvalues:", np.sort_complex(ol))
    print("K =", K)
    print("closed-loop eigenvalues:", np.sort_complex(cl))
    print(f"yaw: kp={kp:.4f} kd={kd:.4f}")
    ref = simulate(K)
    t = ref[:, 0]
    imax = np.abs(ref[:, 5]).max() / 2 / D["K"]
    print("peak |tau| per wheel =", np.abs(ref[:, 5]).max() / 2, "i =", imax, "peak |V| =", np.abs(ref[:, 7]).max())
    cursors = {}
    for tc in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.5, 9.1, 9.4, 10.0, 12.0, 14.0):
        row = [float(np.interp(tc, t, ref[:, j])) for j in (1, 2, 3, 4, 5, 7)]
        cursors[str(tc)] = dict(zip(("x", "v", "theta", "w", "tau", "V"), row))
        print(tc, [round(v, 5) for v in row])
    top = simulate(K, t_end=TOP["t_end"], theta0=0.0, push=False,
                   vref_fn=lambda t: TOP["v_step"] * float(np.clip((t - TOP["t_ramp0"]) / TOP["t_ramp"], 0, 1)))
    tt = top[:, 0]
    tcur = {}
    for tc in (2.0, 4.0, 6.0, 8.0, 10.0, 11.0, 12.0, 14.0, 17.0):
        tcur[str(tc)] = dict(zip(("x", "v", "theta", "w", "tau", "V"), [float(np.interp(tc, tt, top[:, j])) for j in (1, 2, 3, 4, 5, 7)]))
        print("top", tc, {k: round(v_, 4) for k, v_ in tcur[str(tc)].items()})
    print("top peaks: tau/wheel", np.abs(top[:, 5]).max() / 2, "V", np.abs(top[:, 7]).max(), "theta", np.abs(top[:, 3]).max())
    op = simulate(np.zeros(4), t_end=OPEN["t_end"], theta0=OPEN["theta0"], push=False, vref=False)
    ocur = {}
    for tc in (0.2, 0.4, 0.6, 0.8, 1.0):
        ocur[str(tc)] = float(np.interp(tc, op[:, 0], op[:, 3]))
    print("open-loop theta", ocur)
    eight = simulate_eight(K)
    te = eight[:, 0]
    ecur = {}
    for tc in (6.0, 9.5, 12.0, 15.0, 20.0, 24.0, 28.0):
        ecur[str(tc)] = dict(zip(("v", "psi", "dpsi", "x", "y", "tau_d"), [float(np.interp(tc, te, eight[:, j])) for j in range(1, 7)]))
        print("eight", tc, {k: round(v_, 4) for k, v_ in ecur[str(tc)].items()})
    print("eight extents x", eight[:, 4].min(), eight[:, 4].max(), "y", eight[:, 5].min(), eight[:, 5].max(),
          "peak |tau_d|", np.abs(eight[:, 6]).max(), "max |dpsi|", np.abs(eight[:, 3]).max())
    win = lambda col, lo, hi: float(np.abs(ref[(t >= lo) & (t <= hi), col]).max())
    out = dict(
        params={k: float(v) for k, v in D.items()},
        K=[float(x) for x in K],
        open_loop=sorted(float(z.real) for z in ol),
        closed_loop=sorted((float(z.real), float(z.imag)) for z in cl),
        yaw=dict(kp=float(kp), kd=float(kd)),
        scenario=dict(theta0=THETA0, v_step=V_STEP, t_ramp0=T_RAMP0, t_ramp=T_RAMP,
                      push_f=PUSH_F, push_t0=PUSH_T0, push_w=PUSH_W, t_end=T_END),
        cursors=cursors,
        open=dict(cursors=ocur, **OPEN),
        top=dict(cursors=tcur, peak_tau=float(np.abs(top[:, 5]).max() / 2), peak_v=float(np.abs(top[:, 7]).max()),
                 peak_theta=float(np.abs(top[:, 3]).max()), **TOP),
        eight=dict(cursors=ecur, x_min=float(eight[:, 4].min()), x_max=float(eight[:, 4].max()),
                   y_min=float(eight[:, 5].min()), y_max=float(eight[:, 5].max()),
                   peak_tau_d=float(np.abs(eight[:, 6]).max()), peak_theta=float(np.abs(eight[:, 7]).max()), peak_tau=float(np.abs(eight[:, 8]).max()), peak_rate=float(np.abs(eight[:, 3]).max())),
        peaks=dict(tau=win(5, 0, T_END) / 2, i=float(imax), v_req=win(7, 0, T_END), theta=win(3, 0, T_END),
                   theta_push=win(3, PUSH_T0, PUSH_T0 + 2.0)),
    )
    text = json.dumps(out, indent=2) + chr(10)
    (ROOT / "design" / "design.json").write_text(text, encoding="utf-8", newline=chr(10))
    print("wrote design.json")


if __name__ == "__main__":
    main()
