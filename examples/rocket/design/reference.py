"""Independent scipy integration of the rocket equations (the reference for expected.json).

The bg-sim models are 3D bond graphs (a Free3D joint, a modulated spatial inertia, MR elements
for the momentum that leaves with the exhaust and the jettisoned stages, and wrench sources).
Their motion stays in the vertical x-z plane of the launch, so the reference integrates the same
physics as a planar point mass with a pitch degree of freedom, in plain world-frame form:

    m dv/dt = T (cos d xb + sin d zb) + F_grav + F_drag      (the outflow terms cancel: m dv/dt = F)
    dtheta/dt = -w,   J dw/dt = l T sin d                       (J = m rg^2; the J-dot terms cancel)
    dm/dt = -(mdot + j),   dmdot/dt = (mdot_cmd - mdot) / tau,  d(rg^2)/dt = jettison ramp

with xb = (cos theta, sin theta), zb = (-sin theta, cos theta) in (x, z), theta the elevation of the
body x axis in the launch frame (90 deg = vertical). The schedule, the atmosphere table, the drag
table and the attitude law are the same numbers the model uses (data.py), written again here in
numpy, so a disagreement points at the model, not at shared code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp

import data as d

TAU_JET = 0.2          # s, duration of the mass ramp of a jettison (the model uses the same)
T_MIN = 1000.0         # N, floor of the thrust in the gimbal law (no division by zero in a coast)


@dataclass
class Vehicle:
    m0: float
    phases: list            # (t_start, mdot_cmd, c, Ae)
    jettisons: list         # (t, dm, what)
    configs: list           # (name, rg_pitch, rg_roll, l)
    S: float
    cd_mach: list
    cd: list
    v0: float = 0.0         # start velocity along +x (the pad's speed in the launch plane)
    omega: float = 0.0      # rotation rate of the air in the plane (v0 / RE)
    pitch_t: list = field(default_factory=list)    # pitch program knots (s)
    pitch_deg: list = field(default_factory=list)  # elevation (deg)
    wn: float = 1.5
    zeta: float = 0.8
    delta_max_deg: float = 6.0
    tvc: bool = False
    gravity: float = 1.0    # multipliers for the vacuum (Tsiolkovsky) variant
    drag: float = 1.0
    ambient: float = 1.0
    ideal_attitude: bool = False   # theta = theta_cmd exactly (only for fitting the pitch program)


ATM = d.atmosphere_table()
_AH = np.array(ATM["h"])
_AT = np.array(ATM["T"])
_ALP = np.array(ATM["lnp"])
_ALR = np.array(ATM["lnrho"])


def atmosphere(h: float) -> tuple[float, float, float]:
    """p (Pa), rho (kg/m^3), a (m/s) from the table, interpolated as in the model."""
    p = math.exp(np.interp(h, _AH, _ALP))
    rho = math.exp(np.interp(h, _AH, _ALR))
    temp = float(np.interp(h, _AH, _AT))
    return p, rho, math.sqrt(1.4 * 287.0528 * temp)


def _step(table: list, t: float, k: int) -> float:
    value = table[0][k]
    for row in table:
        if t >= row[0]:
            value = row[k]
    return value


def _jet(v: Vehicle, t: float) -> tuple[float, float, float]:
    """Jettison mass flow and the rates of rg_pitch^2, rg_roll^2."""
    j = dp = dr = 0.0
    for k, (tj, dm, _) in enumerate(v.jettisons):
        if tj <= t < tj + TAU_JET:
            j += dm / TAU_JET
            dp += (v.configs[k + 1][1] ** 2 - v.configs[k][1] ** 2) / TAU_JET
            dr += (v.configs[k + 1][2] ** 2 - v.configs[k][2] ** 2) / TAU_JET
    return j, dp, dr


def _gimbal_arm(v: Vehicle, t: float) -> float:
    k = sum(1 for tj, _, _ in v.jettisons if t >= tj)
    return v.configs[k][3]


def theta_cmd(v: Vehicle, t: float) -> float:
    return math.radians(float(np.interp(t, v.pitch_t, v.pitch_deg))) if v.pitch_t else math.pi / 2


def forces(v: Vehicle, t: float, y: np.ndarray) -> dict:
    x, z, vx, vz, th, w, m, mdot, rgp2 = y
    rc = np.array([x, z + d.RE])
    r = float(np.hypot(*rc))
    h = r - d.RE
    p, rho, a = atmosphere(h)
    c = _step(v.phases, t, 2)
    ae = _step(v.phases, t, 3)
    thrust = max(mdot * c - v.ambient * p * ae, 0.0)
    if v.ideal_attitude:
        th = theta_cmd(v, t)
    xb = np.array([math.cos(th), math.sin(th)])
    zb = np.array([-math.sin(th), math.cos(th)])
    jy = m * rgp2
    arm = _gimbal_arm(v, t)
    if v.tvc and not v.ideal_attitude:
        wdot_d = -v.wn ** 2 * (theta_cmd(v, t) - th) - 2.0 * v.zeta * v.wn * w
        s_max = math.sin(math.radians(v.delta_max_deg))
        sd = min(max(jy * wdot_d / (arm * max(thrust, T_MIN)), -s_max), s_max)
        delta = math.asin(sd)
    else:
        delta = 0.0
    f_thrust = thrust * (math.cos(delta) * xb + math.sin(delta) * zb)
    f_grav = -v.gravity * d.MU * m * rc / r ** 3
    vel = np.array([vx, vz])
    v_air = vel - v.omega * np.array([rc[1], -rc[0]])     # omega x rc with omega along +y
    speed_air = float(np.hypot(*v_air))
    mach = speed_air / a
    qbar = 0.5 * rho * speed_air ** 2
    cd = float(np.interp(mach, v.cd_mach, v.cd))
    f_drag = -v.drag * qbar * v.S * cd * v_air / max(speed_air, 1e-9)
    return dict(h=h, p=p, rho=rho, a=a, mach=mach, qbar=qbar, thrust=thrust, delta=delta, jy=jy, arm=arm,
                f_thrust=f_thrust, f_grav=f_grav, f_drag=f_drag, xb=xb, th=th, rc=rc, r=r)


def rhs(t: float, y: np.ndarray, v: Vehicle) -> np.ndarray:
    x, z, vx, vz, th, w, m, mdot, rgp2 = y
    f = forces(v, t, y)
    acc = (f["f_thrust"] + f["f_grav"] + f["f_drag"]) / m
    wdot = f["arm"] * f["thrust"] * math.sin(f["delta"]) / f["jy"]
    j, dp, _ = _jet(v, t)
    mcmd = _step(v.phases, t, 1)
    return np.array([vx, vz, acc[0], acc[1], -w, wdot, -(mdot + j), (mcmd - mdot) / d.TAU_ENGINE, dp])


def breakpoints(v: Vehicle, t_end: float) -> list:
    ts = {0.0, t_end}
    ts |= {row[0] for row in v.phases}
    for tj, _, _ in v.jettisons:
        ts |= {tj, tj + TAU_JET}
    ts |= set(v.pitch_t)
    return sorted(t for t in ts if 0.0 <= t <= t_end)


def simulate(v: Vehicle, t_end: float, dt_out: float = 0.1, rtol: float = 1e-10, atol: float = 1e-9,
             stop_at_ground: bool = False) -> dict:
    y = np.array([0.0, 0.0, v.v0, 0.0, math.pi / 2, 0.0, v.m0, v.phases[0][1], v.configs[0][1] ** 2])
    ts_all, ys_all = [], []
    grid = breakpoints(v, t_end)
    for a, b in zip(grid[:-1], grid[1:]):
        if b - a < 1e-12:
            continue
        t_eval = np.arange(math.ceil(a / dt_out) * dt_out, b, dt_out)
        t_eval = t_eval[(t_eval >= a) & (t_eval < b)]
        sol = solve_ivp(rhs, (a, b), y, method="DOP853", rtol=rtol, atol=atol, args=(v,),
                        t_eval=np.append(t_eval, b), dense_output=False)
        ts_all.append(sol.t[:-1]), ys_all.append(sol.y[:, :-1])
        y = sol.y[:, -1]
    ts_all.append(np.array([t_end])), ys_all.append(y[:, None])
    t = np.concatenate(ts_all)
    Y = np.concatenate(ys_all, axis=1)
    return {"t": t, "y": Y, "v": v}


def derived(run: dict) -> dict:
    """Signals the checks compare: altitude, range, speed, flight-path angle, Mach, q, ..."""
    v, t, Y = run["v"], run["t"], run["y"]
    out = {k: [] for k in ("h", "s", "speed", "fpa", "mach", "qbar", "thrust", "m", "acc", "theta", "delta", "dv")}
    dv = 0.0
    prev = None
    for k, tk in enumerate(t):
        y = Y[:, k]
        f = forces(v, tk, y)
        rc = f["rc"]
        vel = np.array([y[2], y[3]])
        speed = float(np.hypot(*vel))
        out["h"].append(f["h"])
        out["s"].append(d.RE * (math.atan2(rc[0], rc[1]) - v.omega * tk))   # Earth-fixed surface range
        out["speed"].append(speed)
        out["fpa"].append(math.degrees(math.asin(float(rc @ vel) / (f["r"] * max(speed, 1e-9)))))
        out["mach"].append(f["mach"])
        out["qbar"].append(f["qbar"])
        out["thrust"].append(f["thrust"])
        out["m"].append(y[6])
        out["acc"].append(float(np.hypot(*(f["f_thrust"] + f["f_drag"]))) / y[6])
        out["theta"].append(math.degrees(f["th"]))
        out["delta"].append(math.degrees(f["delta"]))
        if prev is not None:
            dv += 0.5 * (prev + f["thrust"] / y[6]) * (tk - t[k - 1])
        prev = f["thrust"] / y[6]
        out["dv"].append(dv)
    return {k: np.array(val) for k, val in out.items()} | {"t": t}


def at(sig: dict, name: str, t: float) -> float:
    return float(np.interp(t, sig["t"], sig[name]))


def crossing(sig: dict, name: str, level: float) -> float:
    y = sig[name] - level
    k = int(np.argmax((y[:-1] < 0) & (y[1:] >= 0)))
    return float(sig["t"][k] + (sig["t"][k + 1] - sig["t"][k]) * (-y[k]) / (y[k + 1] - y[k]))


# ----------------------------------------------------------------------------------- vehicles
def v2(**kw) -> Vehicle:
    s = d.v2_schedule()
    return Vehicle(m0=s["m0"], phases=s["phases"], jettisons=s["jettisons"], configs=s["configs"],
                   S=d.V2["S"], cd_mach=d.V2_CD_MACH, cd=d.V2_CD, **kw)


def saturn(pitch_t: list, pitch_deg: list, **kw) -> Vehicle:
    s = d.sv_schedule()
    return Vehicle(m0=s["m0"], phases=s["phases"], jettisons=s["jettisons"], configs=s["configs"],
                   S=d.S_SV, cd_mach=d.SV_CD_MACH, cd=d.SV_CD, v0=d.V0_PLANE, omega=d.V0_PLANE / d.RE,
                   pitch_t=pitch_t, pitch_deg=pitch_deg, wn=d.SV_WN, zeta=d.SV_ZETA,
                   delta_max_deg=d.SV_DELTA_MAX, tvc=True, **kw)
