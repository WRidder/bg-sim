"""The cessna-sim demo pilot and autopilot (the `DemoPilot` and `C172Autopilot` blocks), and the
nonlinear reference runs of the cessna-sim model: the demo takeoff, climb and turn, and the
autopilot's heading and altitude hold.

Every function mirrors a block of the bg-sim model; the constants are its parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import c172_ref as M
import c172_si as S
import perf as P

KT = P.KT


def sig(x):
    """Smooth step 0 -> 1 (DemoPilot uses it for every phase switch)."""
    return 0.5 * (1.0 + math.tanh(x))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


@dataclass
class Demo:
    """DemoPilot parameters: runway heading north (psi 0), along world x from x = 0."""
    t_thr: float = 1.0            # s, throttle opens from idle
    t_thr_ramp: float = 2.0       # s, idle to full
    vr: float = 45.0 * KT         # m/s CAS, rotation
    dv_rot: float = 0.5           # m/s, width of the rotation switch
    theta_rot: float = 0.17       # rad, rotation attitude
    h_air: float = 3.0            # m above the static CG height: airborne
    theta_climb: float = 0.13     # rad, climb attitude at the climb speed
    kv: float = 0.03              # rad per m/s of speed error
    v_lift: float = 30.0          # m/s CAS, speed target just after lift-off
    v_climb: float = 75.0 * KT    # m/s CAS, climb speed
    dvdh: float = 0.5             # 1/s, the speed target rises with height
    k_theta: float = 10.0
    k_q: float = 2.0
    h_flaps_up: float = 20.0      # m AGL (after the 50-ft obstacle)
    t_turn: float = 75.0          # s, start of the turn
    psi_turn: float = 90.0 * S.DEG
    k_psi: float = 1.2            # bank per heading error
    phi_max: float = 20.0 * S.DEG
    k_phi: float = 2.0
    k_p: float = 0.3
    k_ped_psi: float = 3.0
    k_ped_r: float = 1.5
    k_ped_y: float = 0.05
    k_yd: float = 0.5             # pedals per rad/s of yaw rate in the air (yaw damping)
    h_cg0: float = 1.2546         # m, static CG height above the runway


def demo_controls(t, out, d: Demo):
    """DemoPilot: (yoke_pitch, yoke_roll, pedals, throttle, flaps) from the airframe outputs."""
    agl = out["h"] - d.h_cg0
    rot = sig((out["cas"] - d.vr) / d.dv_rot)
    air = sig((agl - d.h_air) / 0.5)
    v_cmd = min(d.v_climb, d.v_lift + d.dvdh * max(agl, 0.0))
    th_climb = min(0.22, max(0.0, d.theta_climb + d.kv * (out["cas"] - v_cmd)))
    th_c = (1.0 - air) * d.theta_rot + air * th_climb
    yoke = rot * max(-1.0, min(1.0, d.k_theta * (th_c - out["theta"]) - d.k_q * out["q"]))
    turn = sig((t - d.t_turn) / 0.5)
    phi_c = air * max(-d.phi_max, min(d.phi_max, d.k_psi * wrap(turn * d.psi_turn - out["psi"])))
    roll = max(-1.0, min(1.0, d.k_phi * (phi_c - out["phi"]) - d.k_p * out["p"]))
    ground = 1.0 - air
    ped = max(-1.0, min(1.0, ground * (-d.k_ped_psi * wrap(out["psi"]) - d.k_ped_r * out["r"] + d.k_ped_y * out["y"])
                        - air * d.k_yd * out["r"]))
    thr = max(0.0, min(1.0, (t - d.t_thr) / d.t_thr_ramp))
    flaps = 1.0 if agl < d.h_flaps_up else 0.0
    return yoke, roll, ped, thr, flaps


@dataclass
class AP:
    """C172Autopilot parameters (modes and references are inputs of the block)."""
    k_psi: float = 1.0            # bank command per rad of heading error
    phi_max: float = 20.0 * S.DEG
    k_phi: float = 1.5            # yoke per rad of bank error
    k_p: float = 0.3              # yoke per rad/s of roll rate
    roll_max: float = 0.5         # authority of the roll channel
    k_h: float = 0.01             # yoke per m of altitude error
    k_hd: float = 0.04            # yoke per m/s of climb rate
    k_hi: float = 0.002           # yoke per m s of integrated error
    k_q: float = 0.5              # yoke per rad/s of pitch rate
    h_err_max: float = 30.0       # m, error clamp (and integrator input clamp)
    pitch_max: float = 0.6        # authority of the pitch channel
    tau_reset: float = 0.5        # s, the integrator decays with the mode off


def ap_rates(out, xi, roll_mode, alt_mode, hdg_ref, alt_ref, a: AP):
    """C172Autopilot: (yoke pitch added, yoke roll added, d(xi)/dt). roll_mode 0 off,
    1 wing leveller, 2 heading hold; alt_mode 0 off, 1 altitude hold."""
    hold = 1.0 if roll_mode >= 1.5 else 0.0
    on_r = 1.0 if roll_mode >= 0.5 else 0.0
    phi_c = hold * max(-a.phi_max, min(a.phi_max, a.k_psi * wrap(hdg_ref - out["psi"])))
    roll = on_r * max(-a.roll_max, min(a.roll_max, a.k_phi * (phi_c - out["phi"]) - a.k_p * out["p"]))
    on_a = 1.0 if alt_mode >= 0.5 else 0.0
    e = max(-a.h_err_max, min(a.h_err_max, alt_ref - out["h"]))
    pitch = on_a * max(-a.pitch_max, min(a.pitch_max, a.k_h * e - a.k_hd * out["hdot"] + a.k_hi * xi - a.k_q * out["q"]))
    xi_dot = on_a * e - (1.0 - on_a) * xi / a.tau_reset
    return pitch, roll, xi_dot


def run(x0, t_end, controls, dt=0.005, par=None, every=0.1, extra=None):
    """Fixed-step RK4 of the reference with controls(t, x, out) -> (Controls, extra state rates);
    the extra states (the autopilot's integrator) ride along. Returns a dict of time series."""
    par = M.Params() if par is None else par
    n_ex = 0 if extra is None else len(extra)
    z = np.concatenate([x0, np.zeros(n_ex) if extra is None else np.array(extra, float)])

    def f(t, z):
        x = z[:M.NX]
        out = M.outputs(x, M.Controls(), par)
        c, exd = controls(t, x, z[M.NX:], out)
        dx = M.deriv(t, x, c, par)
        return np.concatenate([dx, exd])

    rec = {k: [] for k in ("t", "x", "y", "h", "cas", "vt", "alpha", "theta", "phi", "psi", "hdot", "rpm", "flap",
                           "fn_nose", "fn_left", "fn_right", "yoke", "roll", "ped", "thr", "q", "p", "r", "beta", "nz")}
    t = 0.0
    k_every = int(round(every / dt))
    k = 0
    while t <= t_end + 1e-9:
        if k % k_every == 0:
            x = z[:M.NX]
            out = M.outputs(x, M.Controls(), par)
            c, _ = controls(t, x, z[M.NX:], out)
            out = M.outputs(x, c, par)
            legs = out["legs"]
            for key, val in (("t", t), ("x", x[0]), ("y", x[1]), ("h", out["h"]), ("cas", out["cas"]), ("vt", out["vt"]),
                             ("alpha", out["alpha"]), ("theta", out["theta"]), ("phi", out["phi"]), ("psi", out["psi"]),
                             ("hdot", out["hdot"]), ("rpm", out["rpm"]), ("flap", x[M.I_FLAP]),
                             ("fn_nose", legs.get("nose", {}).get("Fn", 0.0)), ("fn_left", legs.get("left", {}).get("Fn", 0.0)),
                             ("fn_right", legs.get("right", {}).get("Fn", 0.0)), ("yoke", c.yoke_pitch), ("roll", c.yoke_roll),
                             ("ped", c.pedals), ("thr", c.throttle), ("q", out["q"]), ("p", out["p"]), ("r", out["r"]),
                             ("beta", out["beta"]), ("nz", out["nz"])):
                rec[key].append(float(val))
        if t >= t_end - 1e-9:
            break
        k1 = f(t, z)
        k2 = f(t + dt / 2, z + dt / 2 * k1)
        k3 = f(t + dt / 2, z + dt / 2 * k2)
        k4 = f(t + dt, z + dt * k3)
        z = z + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
        k += 1
    return rec, z


def runway_start(flap_deg=10.0, par=None):
    """At rest on the runway, engine at idle (throttle 0), flaps at `flap_deg`: the static
    equilibrium of perf.ground_state."""
    x, _, g = P.ground_state(throttle=0.0, flap_deg=flap_deg, par=par)
    return x, g


def demo_run(t_end=100.0, d: Demo | None = None, dt=0.005):
    d = Demo() if d is None else d
    x0, g = runway_start(10.0)
    d.h_cg0 = g["h_cg"]

    def controls(t, x, ex, out):
        yoke, roll, ped, thr, flaps = demo_controls(t, out, d)
        return M.Controls(yoke_pitch=yoke, yoke_roll=roll, pedals=ped, throttle=thr, flaps=flaps), np.zeros(0)
    rec, z = run(x0, t_end, controls, dt=dt)
    return rec, x0, g


def milestones(rec, h_cg0):
    t = np.array(rec["t"])
    fn = np.array(rec["fn_nose"]) + np.array(rec["fn_left"]) + np.array(rec["fn_right"])
    k_lo = next(i for i in range(len(t)) if t[i] > 2.0 and fn[i] < 1.0)
    h = np.array(rec["h"]) - h_cg0
    k50 = next(i for i in range(len(t)) if h[i] > 50.0 * P.FT)
    return {"t_liftoff": float(t[k_lo]), "x_liftoff": float(rec["x"][k_lo]), "kcas_liftoff": rec["cas"][k_lo] / KT,
            "t_50ft": float(t[k50]), "x_50ft": float(rec["x"][k50])}
