"""Performance of the reference model at the POH's conditions (`poh.py`): stall speeds, climb,
cruise, glide and the takeoff ground roll (a simulation with the gear)."""

from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, least_squares, minimize_scalar

import c172_data as D
import c172_lin as L
import c172_ref as M
import c172_si as S

KT = 0.514444444
FT = 0.3048


def best_power_fa():
    """The fuel/air ratio of the most power: FGPiston's indicated power is fuel flow x
    efficiency, so the maximum of fa * efficiency(fa) (about 0.101, rich of the plateau)."""
    fas = np.linspace(0.06, 0.12, 6001)
    return float(fas[np.argmax([fa * M.lookup1(fa, D.MIXTURE_EFFICIENCY) for fa in fas])])


FA_BEST = best_power_fa()


def best_power_mixture(h):
    """The mixture lever that gives the best-power fuel/air ratio at altitude h: the POH's
    "leaned for maximum RPM" (full rich at sea level gives fa = 1.3 / 14.7 = 0.088)."""
    _, pa, _, _ = S.atmosphere(h)
    return min(1.0, FA_BEST * 14.7 / (1.3 * 101325.0 / pa))


def cas_to_tas(cas, h):
    """TAS from CAS (subsonic, isentropic)."""
    T, pa, rho, a = S.atmosphere(h)
    qc = S.P0 * ((1.0 + 0.2 * (cas / S.A0) ** 2) ** 3.5 - 1.0)
    mach = math.sqrt(5.0 * ((qc / pa + 1.0) ** (2.0 / 7.0) - 1.0))
    return mach * a


def trim_cas(cas, h, **kw):
    return L.trim(cas_to_tas(cas, h), h, **kw)


# --------------------------------------------------------------------------- stall
def glide_at_alpha(alpha, h, flap_deg, par=None, guess=None):
    """Power-off (throttle 0) steady wings-level glide at a given angle of attack: unknowns the
    speed, beta, the yoke, the pedals, the flight-path angle and the engine speed."""
    par = M.Params(gear=False, ground_z=L.FREE_AIR) if par is None else par

    def build(z):
        V, beta, ep, ea, er, gam, omega = z
        theta = alpha + math.asin(max(-1.0, min(1.0, math.sin(gam) / math.cos(beta))))
        T, pa, rho, a = S.atmosphere(h)
        MAP = M.map_target(omega, 0.0, pa * (1.0 + 0.2 * (V / a) ** 2) ** 3.5)
        x = L.make_state(V, h, alpha, beta, theta, omega=omega, MAP=MAP, flap=flap_deg)
        return x, M.Controls(yoke_pitch=ep, yoke_roll=ea, pedals=er, throttle=0.0, flaps=flap_deg / 10.0)

    def res(z):
        x, c = build(z)
        dx = M.deriv(0.0, x, c, par)
        return np.concatenate([dx[M.I_V:M.I_V + 3], dx[M.I_W:M.I_W + 3] * 10.0, [dx[M.I_H] / 10.0]])

    z0 = guess if guess is not None else [30.0, 0.0, 0.5, 0.0, 0.0, -0.1, 100.0]
    sol = least_squares(res, z0, bounds=([10.0, -0.3, -1.5, -1.5, -1.5, -0.5, 10.0], [80.0, 0.3, 1.5, 1.5, 1.5, 0.3, 400.0]),
                        xtol=1e-14, ftol=1e-14, gtol=1e-14)
    x, c = build(sol.x)
    return sol.x, x, c, float(np.max(np.abs(sol.fun)))


def stall_speed(flap_deg, h=0.0):
    """Power-off wings-level 1-g stall: the lowest steady glide speed over the angle of attack
    (the trimmed CL maximum, the elevator's lift included). `elevator_limited` says the full aft
    yoke ran out before the lift maximum (the search stops at the last trimmable alpha)."""
    z = None
    best = None
    limited = False
    for alpha in np.arange(0.10, 0.36, 0.005):
        zz, x, c, r = glide_at_alpha(alpha, h, flap_deg, guess=z)
        if r > 1e-7:
            limited = True
            break
        z = zz
        if best is None or z[0] < best[1][0]:
            best = (alpha, z.copy())

    def v_of(alpha):
        return glide_at_alpha(alpha, h, flap_deg, guess=best[1])[0][0]
    a_hi = best[0] if limited and best[0] >= alpha - 0.0051 else best[0] + 0.005
    res = minimize_scalar(v_of, bounds=(best[0] - 0.005, a_hi), method="bounded", options={"xatol": 1e-6})
    z, x, c, r = glide_at_alpha(res.x, h, flap_deg, guess=best[1])
    out = M.outputs(x, c, M.Params(gear=False, ground_z=L.FREE_AIR))
    return {"vt": float(z[0]), "kcas": float(out["cas"] / KT), "alpha": float(res.x), "yoke": float(z[2]),
            "gamma_deg": float(z[5] / S.DEG), "CL": float(out["CL"]), "residual": r,
            "elevator_limited": bool(limited and best[0] >= alpha - 0.0051)}


# --------------------------------------------------------------------------- climb, cruise, glide
def best_climb(h, mixture=None):
    """Full throttle, flaps up: the climb speed with the highest rate of climb."""
    mix = best_power_mixture(h) if mixture is None else mixture

    def roc(cas):
        x, c, info = trim_cas(cas, h, throttle=1.0, mixture=mix, guess=[0.08, 0, -0.2, 0, 0, 0.05, 240.0])
        return info["vt"] * math.sin(info["gamma"]), info

    res = minimize_scalar(lambda v: -roc(v)[0], bounds=(30.0, 50.0), method="bounded", options={"xatol": 1e-4})
    r, info = roc(res.x)
    return {"kcas": res.x / KT, "roc_fpm": r / FT * 60.0, "rpm": info["rpm"], "hp": info["hp"], "mixture": mix,
            "gamma": info["gamma"], "ktas": info["vt"] / KT}


def level_full_throttle(h, mixture=None):
    """Maximum level speed (full throttle)."""
    mix = best_power_mixture(h) if mixture is None else mixture

    def gam(v):
        return L.trim(v, h, throttle=1.0, mixture=mix, guess=[0.01, 0, -0.2, 0, 0, 0.0, 260.0])[2]["gamma"]
    v = brentq(gam, 45.0, 80.0, xtol=1e-6)
    x, c, info = L.trim(v, h, gamma=0.0, mixture=mix, guess=[0.01, 0, -0.2, 0, 0, 0.99, 260.0])
    return {"ktas": v / KT, "rpm": info["rpm"], "hp": info["hp"], "throttle": info["throttle"], "mixture": mix}


def cruise_at_power(h, frac, mixture=None):
    """Level flight at `frac` of the rated 160 hp: the speed and the engine state."""
    mix = best_power_mixture(h) if mixture is None else mixture

    def dp(v):
        return L.trim(v, h, gamma=0.0, mixture=mix, guess=[0.02, 0, -0.2, 0, 0, 0.7, 250.0])[2]["hp"] - frac * S.E["maxhp"]
    v = brentq(dp, 40.0, 70.0, xtol=1e-6)
    x, c, info = L.trim(v, h, gamma=0.0, mixture=mix, guess=[0.02, 0, -0.2, 0, 0, 0.7, 250.0])
    return {"ktas": v / KT, "kcas": info["cas"] / KT, "rpm": info["rpm"], "hp": info["hp"],
            "throttle": info["throttle"], "MAP_inhg": info["MAP"] / S.INHG, "mixture": mix}


def best_glide(h=1524.0):
    """Engine dead (mixture cut-off: the windmilling propeller), flaps up: the best glide ratio."""
    def ratio(cas):
        x, c, info = trim_cas(cas, h, throttle=0.0, mixture=0.0, guess=[0.06, 0, -0.2, 0, 0, -0.1, 100.0])
        return -1.0 / math.tan(info["gamma"]), info

    res = minimize_scalar(lambda v: -ratio(v)[0], bounds=(25.0, 45.0), method="bounded", options={"xatol": 1e-4})
    r, info = ratio(res.x)
    return {"kcas": res.x / KT, "ratio": r, "rpm": info["rpm"], "gamma_deg": info["gamma"] / S.DEG}


# --------------------------------------------------------------------------- on the ground
def ground_state(throttle=0.0, flap_deg=0.0, psi=0.0, pos=(0.0, 0.0), ground_z=0.0, par=None):
    """Static equilibrium on the gear at rest: CG height, pitch and engine speed (the engine at
    its steady speed for the throttle; the thrust's creep along the runway is ignored)."""
    par = M.Params() if par is None else par
    c = M.Controls(throttle=throttle, flaps=flap_deg / 10.0)

    def build(z):
        h, theta, omega = z
        x = L.make_state(0.0, h, 0.0, 0.0, theta, psi=psi, omega=omega, flap=flap_deg, pos_xy=pos,
                         throttle=throttle, ground_z=ground_z)
        x[M.I_AD] = 0.0
        return x

    def res(z):
        dx = M.deriv(0.0, build(z), c, par)
        return [dx[M.I_V + 2], dx[M.I_W + 1] * 10.0, dx[M.I_H] / 10.0]

    sol = least_squares(res, [ground_z + 1.2, 0.0, 60.0 + 200.0 * throttle], xtol=1e-15, ftol=1e-15, gtol=1e-15)
    x = build(sol.x)
    return x, c, {"h_cg": sol.x[0] - ground_z, "theta": sol.x[1], "omega": sol.x[2],
                  "q": [x[M.I_STRUT + k] for k in range(3)], "residual": float(np.max(np.abs(sol.fun)))}


def takeoff(vr_kcas=45.0, theta_rot=0.17, flap_deg=10.0, t_end=60.0, par=None, record=False, v50_kcas=58.0):
    """Short-field takeoff at sea level (POH Figure 5-5 conditions): engine at full throttle on
    the brakes, released at t = 0; the yoke neutral until `vr_kcas`, then a pitch-attitude
    controller rotates to `theta_rot`; pedals hold the runway heading. Ground roll = distance to
    the instant every wheel has left the runway."""
    par = M.Params() if par is None else par
    x0, _, g0 = ground_state(throttle=1.0, flap_deg=flap_deg, par=par)
    st = {"rot": False}

    def ctrl(t, x):
        out = M.outputs(x, M.Controls(throttle=1.0, flaps=flap_deg / 10.0), par)
        if out["cas"] >= vr_kcas * KT:
            st["rot"] = True
        yoke = 0.0
        if st["rot"]:
            th_c = theta_rot
            if st.get("air"):   # after lift-off: pitch for the 50-ft speed (POH: 56 KIAS)
                th_c = min(0.25, max(0.0, theta_rot + 0.04 * (out["cas"] - v50_kcas * KT)))
            yoke = max(-1.0, min(1.0, 10.0 * (th_c - out["theta"]) - 2.0 * (-x[M.I_W + 1])))
        ped = max(-1.0, min(1.0, -3.0 * out["psi"] - 1.5 * out["r"] + 0.05 * x[1]))
        roll = max(-1.0, min(1.0, -2.0 * out["phi"] - 0.3 * out["p"]))
        return M.Controls(yoke_pitch=yoke, yoke_roll=roll, pedals=ped, throttle=1.0, flaps=flap_deg / 10.0), out

    x = x0.copy()
    dt = 0.005
    t = 0.0
    lift = None
    rec = []
    while t < t_end:
        c, out = ctrl(t, x)
        if record and int(round(t / dt)) % 10 == 0:
            rec.append((t, x[0], out["cas"], out["theta"], out["h"], [x[M.I_STRUT + k] for k in range(3)]))
        legs = out["legs"]
        if lift is None and t > 1.0 and all(l["Fn"] < 1.0 for l in legs.values()):
            lift = {"t": t, "x": x[0], "kcas": out["cas"] / KT, "theta": out["theta"]}
            st["air"] = True
        if lift is not None and out["h"] - g0["h_cg"] > 50.0 * FT:
            lift["t50"] = t
            lift["x50"] = x[0]
            lift["kcas50"] = out["cas"] / KT
            break

        def f(tt, xx):
            return M.deriv(tt, xx, c, par)
        k1 = f(t, x)
        k2 = f(t + dt / 2, x + dt / 2 * k1)
        k3 = f(t + dt / 2, x + dt / 2 * k2)
        k4 = f(t + dt, x + dt * k3)
        x = x + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t += dt
    if record:
        lift = lift or {}
        lift["rec"] = rec
    return lift
