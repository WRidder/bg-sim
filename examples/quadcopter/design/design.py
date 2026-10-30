# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Parameters and gain derivation for the `quadcopter` sample (X5.7).

Everything the model needs is derived here from physical data, and checked with small linear
models, so the numbers in `models/quadcopter.bgmodel.json` are not hand-tuned guesses:

1. airframe and propulsion data (a 450 mm X quadcopter, 3S pack, 920 kV motors, 10x4.5 in props);
2. the allocation matrix `M` ([F, tx, ty, tz] = M T) and its inverse for the mixer;
3. the ESC speed loop (PI plus motor-model feedforward): linear model of the motor, the propeller
   load and the 1 kHz sampled controller, loop margins;
4. the body-rate loop: gains from the inertia and the desired bandwidth, margins with the
   rotor-speed lag, the low-pass filter and the sampling delays of the real rates;
5. the attitude, velocity and position loops: a linear model of the chain
   position -> velocity -> tilt -> rate loop, margins and closed-loop poles;
6. the navigation filter: the error dynamics of one horizontal axis (position, velocity, tilt,
   gyro bias) as a linear system, its poles;
7. the Butterworth low-pass coefficients of the IMU filters (bilinear transform at 1 kHz).

Running it prints the derivation and the checks, and (with ``--write``) updates the controller
and sensor parameters of the model document. ``build_model.py`` imports `design.PARAMS` to
generate the whole document.

Run: ``uv run examples/quadcopter/design/design.py`` (add ``--write`` through ``build_model.py``).
"""

from __future__ import annotations

import math
import sys

import numpy as np

# ----------------------------------------------------------------------------- plant data
G = 9.81
M_TRUE = 1.35                     # kg   take-off mass (frame 0.55, battery 0.30, 4 motors+ESC 0.34, props, payload)
M_NOM = 1.30                      # kg   what the controller believes (4 % too low: the velocity integrator carries it)
J_BODY = np.array([0.0115, 0.0115, 0.021])   # kg m^2  principal inertia about the CoM (rotors counted as point masses)
ARM = 0.225                       # m    CoM to motor (450 mm motor-to-motor diagonal)
A = ARM / math.sqrt(2.0)          # m    x and y offset of every motor
RX = np.array([A, -A, A, -A])     # rotor 1 front-right, 2 rear-left, 3 front-left, 4 rear-right
RY = np.array([-A, A, A, -A])
SPIN = np.array([1.0, 1.0, -1.0, -1.0])      # +1 counter-clockwise seen from above (diagonal pairs)
N_ROT = 4

# 920 kV motor (2212 class), 10x4.5 in propeller, 3S pack
KV_RPM = 920.0
K_E = 1.0 / (KV_RPM * 2.0 * math.pi / 60.0)  # V s/rad  (= k_t in SI)
K_T = K_E                         # N m/A
R_W = 0.11                        # Ohm  winding resistance (plus ESC and wiring)
L_W = 40e-6                       # H
J_M = 5.0e-5                      # kg m^2  rotor bell 5e-6 + 10 in propeller 4.5e-5
B_M = 2.0e-6                      # N m s/rad bearing friction
KT_PROP = 1.42e-5                 # N/(rad/s)^2   thrust: CT = 0.11 -> 9.1 N at 800 rad/s
KQ_PROP = 2.03e-7                 # N m/(rad/s)^2 drag torque: CP-based, kQ/kT = 0.0143 m
V_FULL, V_EMPTY, R_INT, CAPACITY = 12.6, 9.9, 0.020, 10800.0   # 3S 3 Ah pack

WIND_MEAN = "[0.4, -0.2, 0.0]"   # m/s world mean wind
WIND_SIGMA = 0.5                  # m/s gust standard deviation (new gust every 0.5 s, 1 s lag)
CD = (0.25, 0.25, 0.35)           # N s/m linear drag (body x, y, z)
CDR = 2.0e-3                      # N m s/rad rotational air damping

# landing gear: four feet at (+-0.11, +-0.11) m, 0.085 m below the CoM; Hertz contact against the ground plane
FEET = [(0.11, 0.11), (-0.11, 0.11), (-0.11, -0.11), (0.11, -0.11)]
CONTACT = {"k": 20000.0, "xref": 1.0e-3, "c": 5.0, "mu": 0.6, "vs": 1.0e-3, "eps": 1.0e-6}

# thrust limits per rotor
T_MIN = 0.4                       # N   idle thrust while armed (ω = 168 rad/s)
T_MAX = 8.5                       # N   (ω = 774 rad/s, T/W = 2.6)

# sample times
TS_ESC, TS_IMU, TS_RATE, TS_ATT, TS_POS = 2e-3, 2e-3, 2e-3, 4e-3, 20e-3

# ----------------------------------------------------------------------------- helpers


def butterworth2(fc: float, ts: float) -> tuple[list[float], list[float]]:
    """Second-order Butterworth low-pass by the bilinear transform: ``b0 b1 b2`` and ``a1 a2`` (a0 = 1)."""
    k = math.tan(math.pi * fc * ts)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    b0 = k * k * norm
    return [b0, 2.0 * b0, b0], [2.0 * (k * k - 1.0) * norm, (1.0 - math.sqrt(2.0) * k + k * k) * norm]


def allocation() -> tuple[np.ndarray, np.ndarray]:
    """``M`` with [F, tx, ty, tz]' = M T, and the pseudo-inverse used by the mixer (N x 4)."""
    m = np.vstack([np.ones(N_ROT), RY, -RX, -SPIN * KQ_PROP / KT_PROP])
    return m, np.linalg.pinv(m)


def freq_margins(loop, w: np.ndarray) -> tuple[float, float, float]:
    """Gain crossover (rad/s), phase margin (deg) and gain margin (dB) of a loop ``L(jw)``."""
    ell = np.array([loop(1j * x) for x in w])
    mag = np.abs(ell)
    phase = np.unwrap(np.angle(ell))
    idx = np.where((mag[:-1] >= 1.0) & (mag[1:] < 1.0))[0]
    if idx.size == 0:
        return float("nan"), float("nan"), float("nan")
    i = int(idx[0])
    wc = float(np.interp(1.0, [mag[i + 1], mag[i]], [w[i + 1], w[i]]))
    pm = 180.0 + math.degrees(float(np.interp(wc, w, phase)))
    j = np.where((phase[:-1] > -math.pi) & (phase[1:] <= -math.pi))[0]
    if j.size == 0:
        gm = float("inf")
    else:
        k = int(j[0])
        wpi = float(np.interp(-math.pi, [phase[k + 1], phase[k]], [w[k + 1], w[k]]))
        gm = -20.0 * math.log10(float(np.interp(wpi, w, mag)))
    return wc, pm, gm


def delay(ts: float):
    """Zero-order hold plus computation: the exact ZOH half-sample delay as exp(-s Ts/2) * sinc."""
    return lambda s: (1.0 - np.exp(-s * ts)) / (s * ts) * np.exp(-s * ts / 2.0) if abs(s) > 0 else 1.0


# ----------------------------------------------------------------------------- derivation


def omega_hover() -> float:
    return math.sqrt(M_NOM * G / N_ROT / KT_PROP)


def esc_design(report: list[str]) -> dict[str, float]:
    """Speed loop: u = u_ff + Kp e + I.  Linearised at the hover speed:  J w' = k_t i - d_p w,
    L i' = u - R i - k_e w, with d_p = 2 kQ w_h + b_m (propeller drag slope plus friction)."""
    wh = omega_hover()
    d_p = 2.0 * KQ_PROP * wh + B_M
    kp, ki = 0.06, 3.0

    def plant(s):
        # w/u: i = (u - k_e w)/(L s + R);  J s w = k_t i - d_p w
        return K_T / ((L_W * s + R_W) * (J_M * s + d_p) + K_T * K_E)

    def loop(s):
        return (kp + ki / s) * plant(s) * delay(TS_ESC)(s)

    w = np.logspace(0, 4, 4000)
    wc, pm, gm = freq_margins(loop, w)
    closed = lambda s: loop(s) / (1.0 + loop(s))  # noqa: E731
    w3 = float(np.interp(-3.0, [20 * math.log10(abs(closed(1j * x))) for x in w][::-1], w[::-1]))
    report.append(
        f"ESC speed loop (2 ms, hover w = {wh:.0f} rad/s): Kp {kp}, Ki {ki}: crossover {wc:.0f} rad/s, "
        f"phase margin {pm:.0f} deg, gain margin {gm:.1f} dB, closed-loop -3 dB at {w3:.0f} rad/s"
    )
    return {"Kp": kp, "Ki": ki, "bw": w3, "wc": wc, "pm": pm}


def rate_design(report: list[str], esc_bw: float) -> dict[str, np.ndarray | float]:
    """Rate loop per axis: tau -> rotor thrust differences -> rotor speed (ESC closed loop, a first-order
    lag at esc_bw) -> torque on the airframe; inertia J.  Delays: gyro low-pass (80 Hz Butterworth,
    2nd order), 500 Hz hold, ESC hold.

    Roll and pitch torques come from thrust, T = kT w^2, which follows the speed.  The yaw torque is the
    reaction of the rotors, sum(spin (Q + Jm dw/dt)), so the rotors' acceleration torque Jm s adds a lead
    to the yaw actuator (zero at Q'/Jm = 2 kQ w_h / Jm, about 4 rad/s): above that frequency the yaw
    torque per speed command is Jm s, not Q', and the loop gain is flat at Kp Jm / (Jz Q').  The yaw gain
    is therefore limited by that plateau, and the yaw torque demand gets a first-order low-pass
    (`f_alpha` of RateCtrl)."""
    fc_gyro = 80.0
    wn = 2.0 * math.pi * fc_gyro
    lp = lambda s: wn * wn / (s * s + math.sqrt(2.0) * wn * s + wn * wn)  # noqa: E731
    act = lambda s: 1.0 / (s / esc_bw + 1.0)  # noqa: E731
    qslope = 2.0 * KQ_PROP * omega_hover()
    wf_yaw = 30.0                                   # rad/s, low-pass of the yaw torque demand
    alpha_yaw = 1.0 - math.exp(-TS_RATE * wf_yaw)
    results: dict[str, np.ndarray | float] = {}
    kp = np.zeros(3)
    ki = np.zeros(3)
    kd = np.zeros(3)
    w = np.logspace(-1, 3, 6000)
    dfilt = lambda s: 1.0 / (s * TS_RATE / 0.25 + 1.0)  # noqa: E731  (alpha 0.25 per tick ~ tau = 6 ms)

    def loop_of(axis, kp_a, ki_a, kd_a):
        j = J_BODY[axis]

        def loop(s):
            c = kp_a + ki_a / s + kd_a * s * dfilt(s)
            plant = act(s) * np.exp(-s * 0.5e-3)
            if axis == 2:
                plant = plant * (1.0 + s * J_M / qslope) / (s / wf_yaw + 1.0)
            return c * delay(TS_RATE)(s) * lp(s) * plant / (j * s)

        return loop

    for axis, (name, wr, ti, td) in enumerate([("roll", 38.0, 0.30, 0.006), ("pitch", 38.0, 0.30, 0.006), ("yaw", 0.0, 1.5, 0.0)]):
        if axis < 2:
            kp[axis] = J_BODY[axis] * wr
            ki[axis] = kp[axis] / ti
            kd[axis] = kp[axis] * td
        else:
            best = None
            for k in np.arange(0.01, 0.4, 0.005):
                _, pm_k, gm_k = freq_margins(loop_of(2, k, k / ti, 0.0), w)
                if np.isfinite(pm_k) and pm_k >= 55.0 and gm_k >= 14.0:
                    best = float(k)
            kp[axis] = best if best is not None else 0.03
            ki[axis] = kp[axis] / ti
        wc, pm, gm = freq_margins(loop_of(axis, kp[axis], ki[axis], kd[axis]), w)
        report.append(
            f"rate loop {name:5s}: Kp {kp[axis]:.3f} Ki {ki[axis]:.3f} Kd {kd[axis]:.4f}: crossover {wc:.1f} rad/s, "
            f"phase margin {pm:.0f} deg, gain margin {gm:.1f} dB"
        )
    report.append(
        f"yaw actuator: lead zero Q'/Jm = {qslope / J_M:.1f} rad/s, torque low-pass {wf_yaw:.0f} rad/s "
        f"(f_alpha {alpha_yaw:.3f} per {TS_RATE * 1e3:.0f} ms tick)"
    )
    results.update(Kp=kp, Ki=ki, Kd=kd, alpha_yaw=alpha_yaw)
    return results


def outer_design(report: list[str], esc_bw: float) -> dict[str, float]:
    """Attitude P + velocity PI + position P on the chain (one horizontal axis):
    p -> v_cmd -> a_cmd -> tilt_cmd = a/g -> attitude P -> rate loop (closed loop, 2nd order
    equivalent at the rate crossover) -> tilt -> a = g tilt -> v -> p.  The vertical axis has no
    attitude loop: a_cmd -> thrust -> rotor speed (ESC lag) -> a."""
    k_att, kv, ki, kp = 6.5, 3.0, 1.5, 1.0
    kv_z, ki_z, kp_z = 5.0, 4.0, 1.5
    wr = 38.0                                    # rate-loop crossover (rate_design)
    # closed rate loop ~ first-order lag plus the effective delays of the sampled chain
    t_rate = 1.0 / wr + 0.012                    # s
    w = np.logspace(-2, 2, 4000)

    def att_loop(s):
        return k_att * np.exp(-s * (TS_ATT / 2.0)) / (s * (t_rate * s + 1.0))

    def att_cl(s):
        return att_loop(s) / (1.0 + att_loop(s))

    def vel_loop(s):
        # a_cmd -> tilt command (a/g) -> tilt -> a = g tilt ; PI + 50 Hz ZOH + 1 sample compute delay
        return (kv + ki / s) * att_cl(s) * np.exp(-s * (TS_POS * 1.5)) / s

    def pos_loop(s):
        vcl = vel_loop(s) / (1.0 + vel_loop(s))
        return kp * vcl / s

    def vel_z_loop(s):
        return (kv_z + ki_z / s) * np.exp(-s * (TS_POS * 1.5)) / (s / esc_bw + 1.0) / s

    def pos_z_loop(s):
        vcl = vel_z_loop(s) / (1.0 + vel_z_loop(s))
        return kp_z * vcl / s

    out = {}
    for name, loop in (("attitude", att_loop), ("velocity", vel_loop), ("position", pos_loop),
                       ("vertical velocity", vel_z_loop), ("vertical position", pos_z_loop)):
        wc, pm, gm = freq_margins(loop, w)
        report.append(f"{name:17s} loop: crossover {wc:.2f} rad/s, phase margin {pm:.0f} deg, gain margin {gm:.1f} dB")
        out[name] = pm
    return {"K_rp": k_att, "Kv_xy": kv, "Ki_xy": ki, "Kp_xy": kp, "Kv_z": kv_z, "Ki_z": ki_z, "Kp_z": kp_z,
            "pm_att": out["attitude"], "pm_vel": out["velocity"], "pm_pos": out["position"]}


def nav_design(report: list[str]) -> dict[str, float]:
    """Error dynamics of one horizontal axis of the NavFilter (delta = truth - estimate):

        dp' = dv - L1 dp
        dv' = F dth - L2 dp - L3 dv            (F = |specific force| ~ g in hover)
        dth' = -db - (kth / F) dv              (db = bias error, truth - estimate)
        db' = (kb kth / F) dv
    """
    f = G
    l1, l2, l3, kth, kb, kpsi = 6.0, 9.0, 8.0, 12.0, 0.8, 2.0
    a = np.array(
        [
            [-l1, 1.0, 0.0, 0.0],
            [-l2, -l3, f, 0.0],
            [0.0, -kth / f, 0.0, -1.0],
            [0.0, kb * kth / f, 0.0, 0.0],
        ]
    )
    poles = np.linalg.eigvals(a)
    report.append(
        f"nav filter (L1 {l1}, L2 {l2}, L3 {l3}, kth {kth}, kb {kb}): error poles "
        + ", ".join(f"{p.real:.2f}{p.imag:+.2f}j" for p in sorted(poles, key=lambda z: z.real))
    )
    assert max(p.real for p in poles) < -0.3, "navigation filter error dynamics are not stable enough"
    return {"L1": l1, "L2": l2, "L3": l3, "kth": kth, "kb": kb, "kpsi": kpsi}


def build() -> tuple[dict, list[str]]:
    """All model parameters (strings in the model-document format) and the derivation report."""
    report: list[str] = []
    m_alloc, minv = allocation()
    assert np.allclose(m_alloc @ minv, np.eye(4)), "allocation matrix is not invertible"
    wh = omega_hover()
    report.append(
        f"hover: T = {M_NOM * G / 4:.2f} N per rotor, w = {wh:.0f} rad/s ({wh * 60 / 2 / math.pi:.0f} rpm); "
        f"T_max {T_MAX} N = {math.sqrt(T_MAX / KT_PROP):.0f} rad/s, thrust-to-weight {4 * T_MAX / (M_TRUE * G):.2f}"
    )
    tau_max = np.array([
        # roll torque authority: (T_max - T_hover) on the two rotors of a side, arm A
        2.0 * A * (T_MAX - M_NOM * G / 4.0) * 1.0,
        2.0 * A * (T_MAX - M_NOM * G / 4.0) * 1.0,
        4.0 * KQ_PROP / KT_PROP * (T_MAX - M_NOM * G / 4.0) * 0.5,
    ])
    report.append(f"torque authority at hover: roll/pitch {tau_max[0]:.2f} N m, yaw {tau_max[2]:.3f} N m")
    esc = esc_design(report)
    rate = rate_design(report, esc["bw"])
    outer = outer_design(report, esc["bw"])
    nav = nav_design(report)
    bg, ag = butterworth2(80.0, TS_IMU)
    ba, aa = butterworth2(30.0, TS_IMU)
    report.append(f"IMU low-pass: gyro 80 Hz b {np.round(bg, 6).tolist()} a {np.round(ag, 6).tolist()}; accel 30 Hz")

    def vec(x):
        return "[" + ", ".join(f"{float(v):.9g}" for v in x) + "]"

    def mat(x):
        return "[" + "; ".join(" ".join(f"{float(v):.9g}" for v in row) for row in x) + "]"

    p = {
        "mass": M_TRUE, "J": vec(J_BODY), "rx": vec(RX), "ry": vec(RY), "spin": vec(SPIN),
        "Minv": mat(minv),
        "esc": {"Kp": f"{esc['Kp']:.9g}", "Ki": f"{esc['Ki']:.9g}"},
        "rate": {"Kp": vec(rate["Kp"]), "Ki": vec(rate["Ki"]), "Kd": vec(rate["Kd"]),
                 "f_alpha": vec([1.0, 1.0, rate["alpha_yaw"]]),
                 "tau_max": vec(tau_max * np.array([0.9, 0.9, 0.9])),
                 "i_max": vec(0.35 * tau_max)},
        "outer": {k: f"{v:.9g}" for k, v in outer.items() if not k.startswith("pm")},
        "nav": {k: f"{v:.9g}" for k, v in nav.items()},
        "lp": {"bgc": vec(bg), "agc": vec(ag), "bac": vec(ba), "aac": vec(aa)},
    }
    return p, report


PARAMS, REPORT = build()


def main() -> int:
    print("quadcopter design report")
    print("-" * 24)
    for line in REPORT:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
