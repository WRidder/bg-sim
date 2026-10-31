# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `maglev` example: trim, LPV model, gain-scheduled PID, cascade loop.

    uv run examples/maglev/design/design.py

Writes `design/design.json` (every number the models, the checks and the docs use). Then
`uv run examples/maglev/design/build_model.py` writes the three models and the scenes.

Plant (MathWorks maglev example): m h'' = m g - alpha i^2 / h^2, h the gap from the magnet
face down to the ball, i the coil current. Everything below is derived in closed form and then
verified numerically (frequency response, closed-loop poles, time simulations).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- plant
M_B = 0.02          # kg, ball mass (reference)
G0 = 9.81           # m/s^2
ALPHA = 2.4832e-5   # H*m = N*m^2/A^2 (reference)
BETA = np.sqrt(G0 * ALPHA / M_B)   # sqrt(g*alpha/m): B(p) = -2*BETA/p
C_TRIM = np.sqrt(M_B * G0 / ALPHA)  # A/m: i_bar = C_TRIM * h_bar
P_GRID = [0.05, 0.15, 0.25]        # m, controller design points (reference)

# --------------------------------------------------------------------------- controller
WC = 50.0           # rad/s, target crossover (reference)
TF = 0.001          # s, derivative filter (reference)
PM = 60.0           # deg, our phase-margin target (pidtune's default target)
PREFILTER_TAU = 0.1  # s, the reference's optional prefilter 10/(s + 10)

# --------------------------------------------------------------------------- scenario
H_START = 0.15
H_STEP = 0.1875
T_STEP = 0.2
T_END = 1.4
DH0 = 1.0e-8        # m, open-loop release offset below the trim gap (model 2)
T_END_OPEN = 1.5    # s, model 2

# --------------------------------------------------------------------------- bond-graph coil
L_INF = 0.03        # H, inductance at an infinite gap (our choice)
R_COIL = 2.0        # Ohm, coil resistance (our choice)
V_MAX = 60.0        # V, amplifier rail
W_I = 1000.0        # rad/s, inner current-loop bandwidth (20 x the outer crossover)
# IR sensor
K_S = 30.0          # V/m, sensor gain around the zero at h_start (+-5 V = +-0.167 m)
NOISE_STD = 3.0e-4  # V, white noise on the sensor voltage (10 um of gap)
ADC_BITS = 16
ADC_RANGE = (-5.0, 5.0)  # V, around the sensor zero at h_start: +-0.167 m of gap
T_SAMPLE = 1.0e-3   # s, sensor/ADC sample period
TF_IR = 0.005       # s, derivative filter of the cascade's PID: the sampled, noisy IR signal
                    # through Kd/Tf = 33/0.001 A/m would swing the amplifier rail to rail


def lpv(p: float) -> dict:
    a0 = 2 * G0 / p
    b0 = 2 * BETA / p
    return {"p": p, "A": [[0.0, 1.0], [a0, 0.0]], "B": [0.0, -b0], "C": [1.0, 0.0],
            "a0": a0, "b0": b0, "pole": float(np.sqrt(a0)), "i_trim": C_TRIM * p}


def pid_gains(p: float, tf: float = TF, lag: float = 0.0, gain: float = 1.0) -> dict:
    """Series PID with a double real zero, C(s) = K (s + z)^2 / (s (Tf s + 1)).

    The frozen plant b0/(s^2 - a0) has phase -180 deg at every frequency, so the phase margin
    is the controller phase at the crossover: 2 atan(wc/z) - 90 deg - atan(wc Tf) = PM fixes z
    (the same for every p), and |C(j wc)| = (wc^2 + a0)/b0 fixes K. `lag` (rad) and `gain` are
    the phase and magnitude at wc of anything else in the loop (the cascade: the ADC's
    sample-and-hold delay T/2 and the inner current loop).
    """
    TF = tf
    a0 = 2 * G0 / p
    b0 = 2 * BETA / p
    M = (WC**2 + a0) / b0
    theta = (np.radians(PM) + np.pi / 2 + np.arctan(WC * TF) + lag) / 2
    z = WC / np.tan(theta)
    K = M / gain * WC * np.sqrt(1 + (WC * TF) ** 2) / (WC**2 + z**2)
    # parallel form Kp + Ki/s + Kd s/(Tf s + 1) with the same numerator
    Ki = K * z**2
    Kp = 2 * K * z - Ki * TF
    Kd = K - Kp * TF
    return {"Kp": Kp, "Ki": Ki, "Kd": Kd, "z": z, "K": K, "M": M}


def loop_tf(p: float, ff_measured: bool) -> tuple[np.ndarray, np.ndarray]:
    """Open loop b0 C(s)/(s^2 - a0); with the trim feedforward on the measured gap the
    negative stiffness cancels and the plant seen by the PID is b0/s^2."""
    gp = pid_gains(p)
    a0 = 2 * G0 / p
    b0 = 2 * BETA / p
    numc = np.array([gp["Kp"] * TF + gp["Kd"], gp["Kp"] + gp["Ki"] * TF, gp["Ki"]])
    denc = np.array([TF, 1.0, 0.0])
    plant_den = [1.0, 0.0, 0.0] if ff_measured else [1.0, 0.0, -a0]
    return b0 * numc, np.polymul(denc, plant_den)


def cascade_lag() -> tuple[float, float]:
    """Phase lag (rad) and gain at wc of the cascade's extra loop elements: the zero-order hold
    of the 1 kHz ADC (a T/2 delay) and the inner current loop, closed at w_i."""
    lag = WC * T_SAMPLE / 2 + np.arctan(WC / W_I)
    gain = 1.0 / np.sqrt(1.0 + (WC / W_I) ** 2)
    return float(lag), float(gain)


def cascade_margins(p: float) -> dict:
    """Crossover and phase margin of the cascade's outer loop at the frozen p, with the trim
    feedforward (plant b0/s^2), the PID of `pid_gains(p, TF_IR, *cascade_lag())`, the T/2
    delay and the inner loop 1/(s/w_i + 1)."""
    lag, gain = cascade_lag()
    gp = pid_gains(p, TF_IR, lag, gain)
    b0 = 2 * BETA / p
    w = np.logspace(0, 4, 200001)
    s = 1j * w
    C = gp["Kp"] + gp["Ki"] / s + gp["Kd"] * s / (TF_IR * s + 1)
    H = b0 * C / s**2 * np.exp(-s * T_SAMPLE / 2) / (s / W_I + 1)
    mag = np.abs(H)
    k = np.where((mag[:-1] >= 1) & (mag[1:] < 1))[0][-1]
    return {"wc": float(w[k]), "pm": float(180 + np.degrees(np.angle(H[k])))}


def margins(num, den) -> dict:
    w = np.logspace(0, 4, 200001)
    _, H = signal.freqs(num, den, w)
    mag = np.abs(H)
    k = np.where((mag[:-1] >= 1) & (mag[1:] < 1))[0][-1]
    wc = float(w[k])
    pm = float(180 + np.degrees(np.angle(H[k])))
    poles = np.roots(np.polyadd(den, num))
    return {"wc": wc, "pm": pm, "poles": [[float(z.real), float(z.imag)] for z in sorted(poles, key=lambda z: z.real)]}


def step_metrics(t, y, y0, y1, t0, band=0.02) -> dict:
    k = t >= t0
    t, y = t[k], y[k]
    s = (y - y0) / (y1 - y0)
    i10 = int(np.argmax(s >= 0.1))
    i90 = int(np.argmax(s >= 0.9))
    out = np.where(np.abs(s - 1) > band)[0]
    return {
        "rise": float(t[i90] - t[i10]),
        "overshoot": float(max(0.0, s.max() - 1)),
        "settling": float(t[out[-1]] - t0) if len(out) else 0.0,
        "final_error": float(y[-1] - y1),
    }


def gains_at(h: float) -> tuple[float, float, float]:
    """Linear interpolation of the three design points, clamped at the ends (Lookup1D)."""
    tab = [pid_gains(p) for p in P_GRID]
    return tuple(float(np.interp(h, P_GRID, [g[k] for g in tab])) for k in ("Kp", "Ki", "Kd"))


def sim_current_driven(h1: float, plant: str = "nl", schedule: bool = True, p_lin: float = 0.15,
                       h0: float = H_START, t_end: float = T_END) -> dict:
    """The current-driven closed loop: prefilter, trim feedforward on the measured gap,
    scheduled (or frozen) PID. plant: 'nl' (the MathWorks equation) or 'lin' (frozen LTI at p_lin)."""
    fixed = gains_at(p_lin)
    a0 = 2 * G0 / p_lin
    b0 = 2 * BETA / p_lin

    def current(x):
        h, v, xi, xf, rf = x
        e = h - rf
        Kp, Ki, Kd = gains_at(h) if schedule else fixed
        return C_TRIM * h + Kp * e + xi + Kd * (e - xf) / TF, Ki * e, (e - xf) / TF

    def f(t, x):
        h, v, xi, xf, rf = x
        r = h1 if t >= T_STEP else h0
        i, dxi, dxf = current(x)
        if plant == "nl":
            acc = G0 - ALPHA / M_B * i * i / (h * h)
        else:
            acc = a0 * (h - p_lin) - b0 * (i - C_TRIM * p_lin)
        return [v, acc, dxi, dxf, (r - rf) / PREFILTER_TAU]

    t = np.linspace(0.0, t_end, int(round(t_end / 1e-4)) + 1)
    sol = solve_ivp(f, (0, T_STEP), [h0, 0, 0, 0, h0], method="Radau", rtol=1e-11, atol=1e-14,
                    dense_output=True)
    sol2 = solve_ivp(f, (T_STEP, t_end), sol.y[:, -1], method="Radau", rtol=1e-11, atol=1e-14,
                     max_step=2e-3, dense_output=True)
    X = np.where(t < T_STEP, sol.sol(np.minimum(t, T_STEP)), sol2.sol(np.maximum(t, T_STEP)))
    i = np.array([current(X[:, k])[0] for k in range(len(t))])
    out = step_metrics(t, X[0], h0, h1, T_STEP)
    out.update({"h_min": float(X[0].min()), "h_max": float(X[0].max()), "i_min": float(i.min()),
                "i_max": float(i.max())})
    return {"t": t, "h": X[0], "i": i, "metrics": out}


def growth(p: float, dh0: float, t: np.ndarray) -> np.ndarray:
    """Nonlinear open-loop release from rest at p + dh0 with the trim current of p:
    returns the instantaneous growth rate v/(h - p)."""
    i = C_TRIM * p

    def f(_t, x):
        return [x[1], G0 - ALPHA / M_B * i * i / (x[0] * x[0])]

    sol = solve_ivp(f, (0, t[-1]), [p + dh0, 0.0], t_eval=t, method="DOP853", rtol=1e-12, atol=1e-16)
    return sol.y[1] / (sol.y[0] - p)


def sim_cascade(h1: float, t_end: float = T_END) -> dict:
    """Bond-graph model without noise and quantisation: amplifier with rail, coil R + L(h),
    the electromagnet force, outer scheduled PID -> current setpoint, inner PI -> voltage."""
    L0 = L_INF + 2 * ALPHA / H_START
    Kpi, Ti = L0 * W_I, L0 / R_COIL
    i0 = C_TRIM * H_START

    lag, gain = cascade_lag()
    tab = [pid_gains(p, TF_IR, lag, gain) for p in P_GRID]

    def parts(x):
        h, v, i, xi, xf, rf, xpi = x
        e = h - rf
        Kp, Ki, Kd = (float(np.interp(h, P_GRID, [g[k] for g in tab])) for k in ("Kp", "Ki", "Kd"))
        iref = C_TRIM * h + Kp * e + xi + Kd * (e - xf) / TF_IR
        vu = Kpi * (iref - i + xpi)
        u = min(max(vu, -V_MAX), V_MAX)
        return iref, vu, u, Ki * e, (e - xf) / TF_IR

    def f(t, x):
        h, v, i, xi, xf, rf, xpi = x
        r = h1 if t >= T_STEP else H_START
        iref, vu, u, dxi, dxf = parts(x)
        L = L_INF + 2 * ALPHA / h
        di = (u - R_COIL * i + 2 * ALPHA * i * v / h**2) / L
        acc = G0 - ALPHA / M_B * i * i / (h * h)
        dxpi = (iref - i) / Ti + (u - vu) / (Kpi * Ti)
        return [v, acc, di, dxi, dxf, (r - rf) / PREFILTER_TAU, dxpi]

    x0 = [H_START, 0, i0, 0, 0, H_START, R_COIL * i0 / Kpi]
    t = np.linspace(0.0, t_end, int(round(t_end / 1e-4)) + 1)
    sol = solve_ivp(f, (0, T_STEP), x0, method="Radau", rtol=1e-10, atol=1e-13, dense_output=True)
    sol2 = solve_ivp(f, (T_STEP, t_end), sol.y[:, -1], method="Radau", rtol=1e-10, atol=1e-13,
                     max_step=1e-3, dense_output=True)
    X = np.where(t < T_STEP, sol.sol(np.minimum(t, T_STEP)), sol2.sol(np.maximum(t, T_STEP)))
    u = np.array([parts(X[:, k])[2] for k in range(len(t))])
    out = step_metrics(t, X[0], H_START, h1, T_STEP)
    out.update({"h_min": float(X[0].min()), "h_max": float(X[0].max()), "i_min": float(X[2].min()),
                "i_max": float(X[2].max()), "v_min": float(u.min()), "v_max": float(u.max())})
    return {"metrics": out, "Kp_i": Kpi, "Ti_i": Ti, "L0": L0, "x0_pi": R_COIL * i0 / Kpi}


def main() -> None:
    design: dict = {
        "plant": {"m_b": M_B, "g": G0, "alpha": ALPHA, "beta": BETA, "c_trim": C_TRIM},
        "lpv": [lpv(p) for p in P_GRID],
        "controller": {"wc": WC, "Tf": TF, "pm_target": PM, "prefilter_tau": PREFILTER_TAU},
        "scenario": {"h_start": H_START, "h_step": H_STEP, "t_step": T_STEP, "t_end": T_END},
    }
    gains = []
    for p in P_GRID:
        g = pid_gains(p)
        g["p"] = p
        g["design_loop"] = margins(*loop_tf(p, ff_measured=False))
        g["actual_loop"] = margins(*loop_tf(p, ff_measured=True))
        gains.append(g)
    design["gains"] = gains
    # The gains are affine in p: K = (wc^2 p + 2 g)/(2 beta) * wc sqrt(1 + (wc Tf)^2)/(wc^2 + z^2).
    slope = [(gains[2][k] - gains[0][k]) / (P_GRID[2] - P_GRID[0]) for k in ("Kp", "Ki", "Kd")]
    mid = [gains[0][k] + s * (P_GRID[1] - P_GRID[0]) for k, s in zip(("Kp", "Ki", "Kd"), slope)]
    design["gains_affine_check"] = [float(m / gains[1][k] - 1) for m, k in zip(mid, ("Kp", "Ki", "Kd"))]

    # Model 1: the MathWorks scenario, scheduled, nonlinear; and the frozen-linear prediction.
    nl = sim_current_driven(H_STEP)
    lin = sim_current_driven(H_STEP, plant="lin", schedule=False)
    nopf = None
    design["model1"] = {"nonlinear": nl["metrics"], "linear_frozen_0.15": lin["metrics"]}

    # Model 2: growth rates and linear vs nonlinear closed-loop steps (frozen gains at 0.15).
    t = np.linspace(0, 1.0, 10001)
    dh0 = DH0
    rates = []
    for p in P_GRID:
        lam = growth(p, dh0, t)
        s = np.sqrt(2 * G0 / p)
        t_chk = round(7.0 / s, 3)   # tanh(7) = 1 - 1.7e-6; dh = dh0 cosh(7) = 5.5e-6 m
        rates.append({"p": p, "pole": s, "t_check": t_chk,
                      "lambda_at_check": float(lam[int(np.argmin(np.abs(t - t_chk)))]),
                      "linear_at_check": float(s * np.tanh(s * t_chk)),
                      "dh_at_check": float(dh0 * np.cosh(s * t_chk))})
    design["model2"] = {"dh0": dh0, "growth": rates}
    for name, h1 in (("small", 0.155), ("large", 0.21)):
        a = sim_current_driven(h1, plant="nl", schedule=False)
        b = sim_current_driven(h1, plant="lin", schedule=False)
        diff = float(np.max(np.abs(a["h"] - b["h"])) / abs(h1 - H_START))
        design["model2"][name] = {"h1": h1, "nonlinear": a["metrics"], "linear": b["metrics"],
                                  "max_diff_over_step": diff}

    # Model 3: the cascade (no noise).
    cas = sim_cascade(H_STEP)
    lag, gain = cascade_lag()
    gains3 = []
    for p in P_GRID:
        g = pid_gains(p, TF_IR, lag, gain)
        g["p"] = p
        g["loop"] = cascade_margins(p)
        gains3.append(g)
    design["model3"] = {
        "Tf": TF_IR, "lag_deg": float(np.degrees(lag)), "inner_gain_at_wc": gain, "gains": gains3,
        "L_inf": L_INF, "R": R_COIL, "V_max": V_MAX, "w_i": W_I, "Kp_i": cas["Kp_i"], "Ti_i": cas["Ti_i"],
        "L0": cas["L0"], "x0_pi": cas["x0_pi"], "i0": C_TRIM * H_START,
        "v0": R_COIL * C_TRIM * H_START,
        "W0": 0.5 * cas["L0"] * (C_TRIM * H_START) ** 2,
        "sensor": {"k_s": K_S, "noise_std": NOISE_STD, "adc_bits": ADC_BITS, "adc_range": list(ADC_RANGE),
                   "t_sample": T_SAMPLE, "lsb_m": (ADC_RANGE[1] - ADC_RANGE[0]) / (2**ADC_BITS - 1) / K_S,
                   "noise_m": NOISE_STD / K_S},
        "noise_free": cas["metrics"],
    }

    path = HERE / "design.json"
    path.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(design, indent=2))


if __name__ == "__main__":
    main()
