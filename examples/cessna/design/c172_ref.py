"""The Cessna 172P reference model: an independent numpy implementation of the physics the bg-sim
bond graph is built from (`c172_data.py`, JSBSim's c172p, in SI through `c172_si.py`).

Rigid body: Newton-Euler in the body frame (FLU about the CG), unit quaternion body -> world,
world x north, y west, z up. The engine, the crankshaft and the propeller are the rotational
bond graph of the bg-sim model written out: the crank + propeller is a gyrostat (axial momentum h
about body x, as stdlib `Rotor3D`), driven by the engine torque and braked by the propeller
torque; the propeller thrust and its torque act on the airframe at the hub. The gear legs are
massless struts on the contact points (spring C state q, the integral of the penetration rate),
with the damper R, rolling friction and brakes along the wheel and the magic-formula side force
across it.

Every function mirrors one block of the bg-sim model (named in its docstring); the smoothing
constants are the blocks' parameters.

State vector (NX = 21):
    0..2   position (world, m)          3..6   quaternion (w, x, y, z), body -> world
    7..9   body velocity (FLU, m/s)     10..12 body rates (FLU, rad/s)
    13     h, crank + propeller axial momentum (N m s)
    14     manifold pressure (Pa)       15     alpha-dot filter state (rad)
    16     flap angle (deg)             17..19 strut displacements q (nose, left, right; m)
    20     (spare: the stall-hysteresis flag is a parameter of `deriv`, switched between runs)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import c172_data as D
import c172_si as S

NX = 21
I_POS, I_Q, I_V, I_W, I_H, I_MAP, I_AD, I_FLAP, I_STRUT = 0, 3, 7, 10, 13, 14, 15, 16, 17
GEARS = ("nose", "left", "right")

# ---- smoothing constants (the same values are parameters of the bg-sim blocks)
V_FLOOR = 1.0          # m/s: alpha = atan(w / sqrt(u^2 + V_FLOOR^2)), b/(2 V) with sqrt(V^2 + V_FLOOR^2)
TF_ALPHADOT = 0.02     # s: alpha-dot = filtered derivative of alpha
EPS_ABS = 1.0e-3       # rad: |beta|, |elevator| smoothed as sqrt(x^2 + EPS^2)
CMD_SMOOTH = 0.02      # the zero-centred surface scales switch gains over +-0.02 of the command
W_FLOOR = 1.0          # rad/s: engine torque P / sqrt(w^2 + W_FLOOR^2)
N_FLOOR = 0.1          # rev/s: advance ratio V / (D sqrt(n^2 + N_FLOOR^2))
MPS_FLOOR = 0.1        # ft/s: engine impedance Peak / sqrt(mps^2 + MPS_FLOOR^2)
GEAR_EPS = 1.0e-3      # m: smooth positive part of the strut displacement
GEAR_FEPS = 1.0        # N: smooth no-pull clamp of the damper
V_ROLL = 0.2           # m/s: tanh regularisation of rolling friction and brakes
V_SIDE = 2.0           # m/s: slip angle atan2(v_y, sqrt(v_x^2 + V_SIDE^2))
FLAP_GAIN = 20.0       # 1/s: flap actuator loop gain (rate limited 5 deg/s below 10 deg, 10 above)


def isfc_calibrated() -> float:
    """FGPiston's own ISFC calibration (used when an engine file gives no bsfc): the indicated
    specific fuel consumption that makes MaxHP at MaxRPM and the maximum manifold pressure at sea
    level, net of the pumping and friction losses (FGPiston::FGPiston, `if (ISFC < 0)`)."""
    E, ED = S.E, S.ED
    pmep = (29.92 - E["maxmp_inhg"]) * S.INHG * ED["volumetric_efficiency"]
    fmep = ED["fmep_dynamic_pa"] * S.RATED_MPS_FPS * S.FT + ED["fmep_static_pa"]
    hp_loss = (pmep + fmep) * S.DISPLACEMENT * E["maxrpm"] / (E["cycles"] * 22371.0)
    return (1.1 * E["displacement_in3"] * E["maxrpm"] * ED["volumetric_efficiency"] * (E["maxmp_inhg"] / 29.92)
            / (9411.0 * (E["maxhp"] + hp_loss - ED["static_friction_hp"])))


# The engine's indicated specific fuel consumption (lb/(hp h)). eng_io320.xml gives bsfc 0.32,
# which FGPiston uses as the ISFC: about 205 hp at 2700 rpm at sea level instead of the rated 160
# (design.py, "engine"). The model uses FGPiston's own calibration instead (0.418), which gives
# the rated power; ISFC_FILE keeps the file's value for the comparison.
ISFC_FILE = D.ENGINE["bsfc"]
ISFC = isfc_calibrated()


def lookup1(x, tab):
    xs, ys = zip(*tab)
    return float(np.interp(x, xs, ys))


def lookup2(u, v, us, vs, table):
    """Bilinear in (u along rows-of-data, v across columns), clamped at the edges (as interp2).
    table[i][j] = value at (us[i], vs[j])."""
    u = min(max(u, us[0]), us[-1])
    v = min(max(v, vs[0]), vs[-1])
    i = max(0, min(int(np.searchsorted(us, u, side="right")) - 1, len(us) - 2))
    j = max(0, min(int(np.searchsorted(vs, v, side="right")) - 1, len(vs) - 2)) if len(vs) > 1 else 0
    tu = (u - us[i]) / (us[i + 1] - us[i])
    if len(vs) == 1:
        return table[i][0] + tu * (table[i + 1][0] - table[i][0])
    tv = (v - vs[j]) / (vs[j + 1] - vs[j])
    a = table[i][j] + tv * (table[i][j + 1] - table[i][j])
    b = table[i + 1][j] + tv * (table[i + 1][j + 1] - table[i + 1][j])
    return a + tu * (b - a)


def rows(tab):
    """A JSBSim 2-D table (rows: first axis value then the columns) -> (axis, table)."""
    return [r[0] for r in tab], [list(r[1:]) for r in tab]


CDWBH_A, CDWBH_T = rows(D.CDWBH)
CYB_B, CYB_T = rows(D.CYB)
CYP_A, CYP_T = rows(D.CYP)
CYR_A, CYR_T = rows(D.CYR)
CLWBH_A, CLWBH_T = rows(D.CLWBH)
CLR_A, CLR_T = rows(D.CLR)


def quat_to_R(q):
    w, x, y, z = q
    s = w * w + x * x + y * y + z * z
    return np.array([
        [(w * w + x * x - y * y - z * z) / s, 2 * (x * y - w * z) / s, 2 * (x * z + w * y) / s],
        [2 * (x * y + w * z) / s, (w * w - x * x + y * y - z * z) / s, 2 * (y * z - w * x) / s],
        [2 * (x * z - w * y) / s, 2 * (y * z + w * x) / s, (w * w - x * x - y * y + z * z) / s]])


def quat_dot(q, w_b):
    qw, qx, qy, qz = q
    p, r_, s_ = w_b
    return 0.5 * np.array([-qx * p - qy * r_ - qz * s_, qw * p + qy * s_ - qz * r_,
                           qw * r_ + qz * p - qx * s_, qw * s_ + qx * r_ - qy * p])


def euler_quat(phi, theta, psi):
    """Quaternion of the NED Euler angles (roll phi, pitch theta, heading psi) for the FLU body in
    the x-north / y-west / z-up world: R_WB = Rz(-psi) Ry(-theta) Rx(phi) in FLU terms."""
    def qx(a):
        return np.array([math.cos(a / 2), math.sin(a / 2), 0.0, 0.0])

    def qy(a):
        return np.array([math.cos(a / 2), 0.0, math.sin(a / 2), 0.0])

    def qz(a):
        return np.array([math.cos(a / 2), 0.0, 0.0, math.sin(a / 2)])
    return quat_mul(quat_mul(qz(-psi), qy(-theta)), qx(phi))


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def euler_of_R(R):
    """NED Euler angles from R_WB (C172AirData)."""
    theta = math.asin(max(-1.0, min(1.0, R[2, 0])))
    phi = math.atan2(R[2, 1], R[2, 2])
    psi = math.atan2(-R[1, 0], R[0, 0])
    return phi, theta, psi


# --------------------------------------------------------------------------- inputs
@dataclass
class Controls:
    """The pilot's controls (the inputs of cessna-sim) at one instant."""
    yoke_pitch: float = 0.0      # -1 full forward .. +1 full aft
    yoke_roll: float = 0.0       # -1 left .. +1 right
    pedals: float = 0.0          # -1 left .. +1 right (nose right)
    throttle: float = 0.0        # 0 .. 1
    mixture: float = 1.0         # 0 cut-off .. 1 full rich
    flaps: float = 0.0           # detent 0..3 (0, 10, 20, 30 deg)
    trim: float = 0.0            # elevator trim, -1 nose down .. +1 nose up (added to the yoke)
    brake_l: float = 0.0
    brake_r: float = 0.0
    wind: tuple = (0.0, 0.0, 0.0)  # north, east, down (m/s)


@dataclass
class Params:
    mass: float = S.MASS
    J: tuple = (S.J_FULL[0, 0], S.J_FULL[1, 1], S.J_FULL[2, 2])
    ground_z: float = 0.0
    hyst: float = 0.0            # stall-hysteresis flag (0 or 1), switched by `run`
    gear: bool = True
    extra: dict = field(default_factory=dict)


def surfaces(c: Controls):
    """C172Controls: the FCS of c172p.xml. Returns elevator, left aileron, rudder (rad), all with
    JSBSim's signs: elevator + trailing edge down, aileron + left trailing edge down (roll right),
    rudder + trailing edge left (nose left; right pedal gives a negative rudder)."""
    e = max(-1.0, min(1.0, -(c.yoke_pitch + c.trim)))
    a = max(-1.0, min(1.0, c.yoke_roll))
    r = max(-1.0, min(1.0, -c.pedals))
    # zero-centred scales (JSBSim aerosurface_scale): positive by max, negative by |min|,
    # blended smoothly over +-CMD_SMOOTH of the command
    de = e * (25.5 - 2.5 * math.tanh(e / CMD_SMOOTH)) * S.DEG
    da = a * (17.5 - 2.5 * math.tanh(a / CMD_SMOOTH)) * S.DEG
    dr = 16.0 * r * S.DEG
    return de, da, dr


def flap_rate(flap_deg, cmd_deg):
    """C172Flaps: rate-limited loop, 5 deg/s below 10 deg and 10 deg/s above (the c172p traverse)."""
    rate = 7.5 + 2.5 * math.tanh((flap_deg - 10.0) / 0.5)
    return max(-rate, min(rate, FLAP_GAIN * (cmd_deg - flap_deg)))


# --------------------------------------------------------------------------- engine and propeller
def engine_power(omega, throttle, mixture, MAP, p_amb, T_amb):
    """PistonEngine (FGPiston without starter, magnetos and temperatures): shaft power (W),
    the manifold-pressure target is computed by `map_target`. Returns power, details."""
    E, ED = S.E, S.ED
    rpm = omega * 60.0 / (2.0 * math.pi)
    mps = rpm * ED["stroke_in"] / 360.0                     # mean piston speed, ft/s
    pmep = (MAP - p_amb) * ED["volumetric_efficiency"]
    cr = ED["compression_ratio"]
    gam = 1.3
    mratio = min(p_amb / MAP, cr)
    ve = (gam - 1.0) / gam + (cr - mratio) / (gam * (cr - 1.0))
    swept = S.DISPLACEMENT * (rpm / 60.0) / 2.0
    v_dot = swept * ED["volumetric_efficiency"] * ve
    m_air = v_dot * MAP / (ED["R_air"] * T_amb)
    phi = 1.3 * mixture * 101325.0 / p_amb
    fa = phi / 14.7
    me = lookup1(fa, D.MIXTURE_EFFICIENCY)
    ff_pph = m_air * fa * 2.2046 * 3600.0
    ihp = ff_pph / ISFC * me - ED["static_friction_hp"]
    fmep = -(ED["fmep_dynamic_pa"] * mps * S.FT + ED["fmep_static_pa"])
    pump_hp = (pmep + fmep) * S.DISPLACEMENT * rpm / (E["cycles"] * 22371.0)
    hp = ihp + pump_hp
    return hp * S.HP, {"rpm": rpm, "hp": hp, "ff_pph": ff_pph, "me": me, "ihp": ihp}


def map_target(omega, throttle, p_ram):
    ED = S.ED
    rpm = omega * 60.0 / (2.0 * math.pi)
    mps = rpm * ED["stroke_in"] / 360.0
    ze = ED["peak_piston_speed_fps"] / math.sqrt(mps * mps + MPS_FLOOR ** 2)
    zt = (1.0 - throttle) ** 2 * S.Z_THROTTLE
    return p_ram * ze / (ze + S.Z_AIRBOX + zt)


def propeller(omega, V, rho, a_sound):
    """Propeller: thrust (N), shaft torque (N m), induced velocity (m/s), details."""
    D_ = S.PROP_D
    n = omega / (2.0 * math.pi)
    J = V / (D_ * math.sqrt(n * n + N_FLOOR ** 2))
    vtip = math.pi * D_ * n
    mtip = math.sqrt(vtip * vtip + V * V) / a_sound
    ct = lookup1(J, D.C_THRUST) * lookup1(mtip, D.CT_MACH)
    cp = lookup1(J, D.C_POWER) * lookup1(mtip, D.CP_MACH)
    thrust = ct * rho * n * n * D_ ** 4
    torque = cp * rho * n * n * D_ ** 5 / (2.0 * math.pi)
    area = 0.25 * math.pi * D_ * D_
    arg = V * abs(V) + 2.0 * thrust / (rho * area)
    vi = 0.5 * (-V + math.copysign(math.sqrt(abs(arg)), arg))
    return thrust, torque, vi, {"J": J, "ct": ct, "cp": cp, "mtip": mtip}


# --------------------------------------------------------------------------- aerodynamics
def aero(u, v, w, p, q, r, alphadot, hb, flap_deg, de, da, dr, hyst):
    """C172Aero (the c172p.xml build-up): coefficients in JSBSim's axes. Returns
    (CD, CY, CL, Cl, Cm, Cn, alpha, beta); Cm and Cn without the elevator and rudder terms, which
    act on the propwash dynamic pressure (`deriv` adds them)."""
    alpha = math.atan(w / math.sqrt(u * u + V_FLOOR ** 2))
    beta = math.atan2(v, math.sqrt(u * u + w * w + V_FLOOR ** 2))
    V = math.sqrt(u * u + v * v + w * w)
    vs = math.sqrt(V * V + V_FLOOR ** 2)
    bi2v, ci2v = S.B / (2.0 * vs), S.CBAR / (2.0 * vs)
    kcd = lookup1(hb, D.KCDGE)
    kcl = lookup1(hb, D.KCLGE)
    mag_b = math.sqrt(beta * beta + EPS_ABS ** 2)
    mag_e = math.sqrt(de * de + EPS_ABS ** 2)
    CD = (D.CD0 + kcd * (lookup1(flap_deg, D.CDDF) + lookup2(alpha, flap_deg, CDWBH_A, D.CDWBH_FLAPS, CDWBH_T))
          + D.CDDE * mag_e + D.CDBETA * mag_b)
    CY = (lookup2(beta, flap_deg, CYB_B, D.CYB_FLAPS, CYB_T) + D.CYDR * dr
          + bi2v * (lookup2(alpha, flap_deg, CYP_A, D.CYB_FLAPS, CYP_T) * p
                    + lookup2(alpha, flap_deg, CYR_A, D.CYB_FLAPS, CYR_T) * r))
    CL = (kcl * (lookup2(alpha, hyst, CLWBH_A, D.CLWBH_HYST, CLWBH_T) + lookup1(flap_deg, D.CLDF))
          + D.CLDE * de + ci2v * (D.CLADOT * alphadot + D.CLQ * q))
    Cl = (lookup1(beta, D.CLB) + bi2v * (D.CLP * p + lookup2(alpha, flap_deg, CLR_A, D.CYB_FLAPS, CLR_T) * r)
          + D.CLDA * da + D.CLDR * dr)
    Cm = D.CMO + D.CMALPHA * alpha + ci2v * (D.CMQ * q + D.CMADOT * alphadot) + lookup1(flap_deg, D.CMDF)
    Cn = lookup1(beta, D.CNB) + bi2v * (D.CNP * p + D.CNR * r) + D.CNDA * da
    return CD, CY, CL, Cl, Cm, Cn, alpha, beta


# --------------------------------------------------------------------------- gear
def sp(x, eps):
    """Smooth positive part and its derivative (cancellation-free, as ContactPoint)."""
    r = math.sqrt(x * x + eps * eps)
    xp = 0.5 * eps * eps / (r - x) if x < 0 else 0.5 * (x + r)
    return xp, xp / r


def gear_leg(name, R, pos, v_b, w_b, q, brake, steer, ground_z):
    """GearContact + StrutSpring + StrutDamper + WheelFriction + WheelSide for one leg.
    Returns (force on the body in FLU, moment about the CG, qdot, details)."""
    g = S.GEAR[name]
    r_b = g["r"]
    vc = R @ (v_b + np.cross(w_b, r_b))           # contact point velocity, world
    qdot = -vc[2]                                 # penetration rate
    # strut: spring C (state q) and damper R on a 1-junction
    x, sig = sp(q, GEAR_EPS)
    Fk = g["k_si"] * x
    Fb = g["b_si"] * qdot * sig
    z = -Fk - Fb
    zc, _ = sp(z, GEAR_FEPS)
    Fd = Fb + sig * zc
    Fn = Fk + Fd
    # wheel axes: the body x axis projected on the ground, turned right by the steering angle
    hx, hy = R[0, 0], R[1, 0]
    hn = math.hypot(hx, hy)
    hx, hy = hx / hn, hy / hn
    cs, sn = math.cos(steer), math.sin(steer)
    ex = np.array([cs * hx + sn * hy, -sn * hx + cs * hy, 0.0])
    ey = np.array([-ex[1], ex[0], 0.0])
    vx, vy = float(ex @ vc), float(ey @ vc)
    mu = g["mu_r"] + brake * (g["mu_s"] - g["mu_r"])
    Fx = mu * Fn * math.tanh(vx / V_ROLL)
    slip = math.atan2(vy, math.sqrt(vx * vx + V_SIDE ** 2)) / S.DEG
    bs = D.SIDE_B_PER_DEG * slip
    Fy = Fn * g["mu_s"] * math.sin(D.SIDE_C * math.atan(bs - D.SIDE_E * (bs - math.atan(bs))))
    Fw = np.array([0.0, 0.0, Fn]) - Fx * ex - Fy * ey
    Fb_body = R.T @ Fw
    return Fb_body, np.cross(r_b, Fb_body), qdot, {"Fn": Fn, "vx": vx, "vy": vy, "Fx": Fx, "Fy": Fy}


# --------------------------------------------------------------------------- the whole aircraft
def air_data(x, c: Controls, par: Params):
    """C172AirData: atmosphere, air-relative velocity in FRD, rates, qbar, ground-effect height."""
    R = quat_to_R(x[I_Q:I_Q + 4])
    vb, wb = x[I_V:I_V + 3], x[I_W:I_W + 3]
    wn, we, wd = c.wind
    wind_b = R.T @ np.array([wn, -we, -wd])
    va = vb - wind_b
    u, v, w = va[0], -va[1], -va[2]
    p, q, r = wb[0], -wb[1], -wb[2]
    h = x[I_POS + 2]
    T, pa, rho, a = S.atmosphere(h)
    V = math.sqrt(u * u + v * v + w * w)
    qbar = 0.5 * rho * V * V
    mach = V / a
    p_tot = pa * (1.0 + 0.2 * mach * mach) ** 3.5
    hmac = h - par.ground_z + (R @ S.R_AERO)[2]
    return {"R": R, "u": u, "v": v, "w": w, "p": p, "q": q, "r": r, "h": h, "T": T, "pa": pa,
            "rho": rho, "a": a, "V": V, "qbar": qbar, "mach": mach, "p_tot": p_tot, "hb": hmac / S.B}


def deriv(t, x, c: Controls, par: Params, out: dict | None = None):
    ad = air_data(x, c, par)
    R = ad["R"]
    vb, wb = x[I_V:I_V + 3], x[I_W:I_W + 3]
    de, da, dr = surfaces(c)
    flap = x[I_FLAP]
    # ---- engine, crank + propeller (rotational bond graph)
    Ja = S.PROP_J
    omega = x[I_H] / Ja - wb[0]                    # spin relative to the airframe
    thr = min(max(c.throttle, 0.0), 1.0)
    P_e, eng = engine_power(omega, thr, min(max(c.mixture, 0.0), 1.0), x[I_MAP], ad["pa"], ad["T"])
    tau_e = P_e * omega / (omega * omega + W_FLOOR ** 2)
    T_p, tau_p, vi, prop = propeller(omega, ad["u"], ad["rho"], ad["a"])
    h_dot = tau_e - tau_p
    map_dot = (map_target(omega, thr, ad["p_tot"]) - x[I_MAP]) / S.ED["man_press_lag_s"]
    # ---- aerodynamics
    alpha = math.atan(ad["w"] / math.sqrt(ad["u"] ** 2 + V_FLOOR ** 2))
    alphadot = (alpha - x[I_AD]) / TF_ALPHADOT
    qbar = ad["qbar"]
    qbar_ind = 0.5 * ad["rho"] * (ad["u"] + 2.0 * vi) ** 2
    CD, CY, CL, Cl, Cm, Cn, alpha, beta = aero(ad["u"], ad["v"], ad["w"], ad["p"], ad["q"], ad["r"], alphadot,
                                              ad["hb"], flap, de, da, dr, par.hyst)
    ca, sa, cb, sb = math.cos(alpha), math.sin(alpha), math.cos(beta), math.sin(beta)
    Fw = np.array([-CD, CY, -CL]) * qbar * S.S                  # wind axes (FRD-based)
    F_frd = np.array([ca * cb * Fw[0] - ca * sb * Fw[1] - sa * Fw[2],
                      sb * Fw[0] + cb * Fw[1],
                      sa * cb * Fw[0] - sa * sb * Fw[1] + ca * Fw[2]])
    # the elevator and rudder moments act on the propwash dynamic pressure
    M_frd = np.array([qbar * S.S * S.B * Cl,
                      qbar * S.S * S.CBAR * Cm + qbar_ind * S.S * S.CBAR * D.CMDE * de,
                      qbar * S.S * S.B * Cn + qbar_ind * S.S * S.B * D.CNDR * dr])
    F_aero = np.array([F_frd[0], -F_frd[1], -F_frd[2]])        # FLU, acting at AERORP
    M_aero = np.array([M_frd[0], -M_frd[1], -M_frd[2]]) + np.cross(S.R_AERO, F_aero)
    # ---- propulsion wrench on the airframe: thrust at the hub, the propeller torque, and the
    # gyrostat's reaction (engine torque reaction and the gyroscopic term)
    F_prop = np.array([T_p, 0.0, 0.0])
    M_prop = np.cross(S.R_PROP, F_prop) + np.array([-tau_p, 0.0, 0.0])
    h = x[I_H]
    M_rot = -np.cross(wb, np.array([h, 0.0, 0.0])) - np.array([h_dot, 0.0, 0.0])
    # ---- gear
    F_g, M_g = np.zeros(3), np.zeros(3)
    qdots = np.zeros(3)
    legs = {}
    if par.gear:
        for k, name in enumerate(GEARS):
            brake = {"left": c.brake_l, "right": c.brake_r}.get(name, 0.0)
            steer = S.GEAR[name]["steer"] * S.DEG * max(-1.0, min(1.0, c.pedals))
            f, m, qd, info = gear_leg(name, R, x[I_POS:I_POS + 3], vb, wb, x[I_STRUT + k], brake, steer, par.ground_z)
            F_g += f
            M_g += m
            qdots[k] = qd
            legs[name] = info
    # ---- rigid body
    m = par.mass
    J = np.array(par.J)
    grav = R.T @ np.array([0.0, 0.0, -m * S.G0])
    F = F_aero + F_prop + F_g + grav
    M = M_aero + M_prop + M_rot + M_g
    dx = np.zeros(NX)
    dx[I_POS:I_POS + 3] = R @ vb
    dx[I_Q:I_Q + 4] = quat_dot(x[I_Q:I_Q + 4], wb)
    dx[I_V:I_V + 3] = F / m - np.cross(wb, vb)
    dx[I_W:I_W + 3] = (M - np.cross(wb, J * wb)) / J
    dx[I_H] = h_dot
    dx[I_MAP] = map_dot
    dx[I_AD] = alphadot
    dx[I_FLAP] = flap_rate(flap, 10.0 * min(max(c.flaps, 0.0), 3.0))
    dx[I_STRUT:I_STRUT + 3] = qdots
    if out is not None:
        phi, theta, psi = euler_of_R(R)
        qc = ad["p_tot"] - ad["pa"]
        cas = S.A0 * math.sqrt(5.0 * ((qc / S.P0 + 1.0) ** (2.0 / 7.0) - 1.0))
        vw = R @ vb
        out.update({"alpha": alpha, "beta": beta, "vt": ad["V"], "qbar": qbar, "cas": cas, "phi": phi,
                    "theta": theta, "psi": psi, "h": ad["h"], "hdot": vw[2], "rpm": eng["rpm"], "hp": eng["hp"],
                    "thrust": T_p, "tau_e": tau_e, "tau_p": tau_p, "omega": omega, "MAP": x[I_MAP],
                    "nz": (F_aero + F_prop + F_g)[2] / (m * S.G0), "CL": CL, "CD": CD, "de": de, "da": da, "dr": dr,
                    "J": prop["J"], "vi": vi, "ff_pph": eng["ff_pph"], "legs": legs, "F_g": F_g,
                    "x": x[0], "y": x[1], "hb": ad["hb"], "u": ad["u"], "p": ad["p"], "q": ad["q"], "r": ad["r"],
                    "alphadot": alphadot, "rho": ad["rho"]})
    return dx


def outputs(x, c: Controls, par: Params) -> dict:
    out: dict = {}
    deriv(0.0, x, c, par, out)
    return out
