# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Independent references of the `cars` example, written to design/design.json.

    uv run examples/cars/design/reference.py

Nothing here is shared with the bond graph: these are the textbook vehicle models the 3D
multibond model must agree with, built from the same parameter tables (`vehicles.py`) and the
same steady-state tyre formulas (`tyre.py`, a numpy rewrite of the stdlib `Tyre`).

* statics     exact static corner loads, spring preloads, ride heights;
* ride        a 7-DOF vertical model (sprung heave/roll/pitch, four wheel hops) with the
              same asymmetric dampers, stops and tyre springs, integrated for the drop test,
              and its linear modes;
* cornering   the linear bicycle model (understeer gradient) and a nonlinear four-wheel
              steady-state solver (combined-slip tyres, lateral and longitudinal load
              transfer from a static 7-DOF solve, aero, open differential with viscous LSD,
              free-rolling front wheels with rolling resistance);
* top speed   the algebraic equilibrium of the electric motor on its power limit, the rotor
              drag, the reduction, tyre slip, rolling resistance and aero drag/downforce;
* launch and  a 1-D longitudinal model (vehicle, front and rear wheel spins, rotor, the
  braking     elastic shaft, battery charge; motor torque/power envelope, regeneration
              blended with the friction brakes, tyres, quasi-static load transfer), integrated;
* grade       the buggy holding a constant speed up a plane slope: the accelerator it needs
              and the axle loads (one motor per axle at the same torque).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import fsolve

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tyre as TY  # noqa: E402
from vehicles import CORNERS, G0, RHO, vehicles  # noqa: E402

K_RPM = 30.0 / math.pi


# ---------------------------------------------------------------------------------------
# Geometry and the vertical (7-DOF) model
# ---------------------------------------------------------------------------------------

class Vert:
    """The 7-DOF vertical model: q = [z, phi, theta, zu_FL, zu_FR, zu_RL, zu_RR], displacements
    from the static design point (chassis heave up, roll about x, pitch about y (nose down),
    wheel-centre heights). Strut travel s = zu - (z + y phi - x theta) (bump +)."""

    def __init__(self, v: dict):
        self.v = v
        ty = v["tyre"]
        c = [v["corners"][k] for k in CORNERS]
        self.x = np.array([k["x"] for k in c])
        self.y = np.array([k["y"] for k in c])
        self.zrel = np.array([k["z"] for k in c])          # wheel centre below the sprung CG
        self.mu = np.array([k["m_u"] for k in c])
        self.k = np.array([k["k"] for k in c])
        self.cb = np.array([k["c_bump"] for k in c])
        self.cr = np.array([k["c_reb"] for k in c])
        self.bump = np.array([k["bump"] for k in c])
        self.droop = np.array([k["droop"] for k in c])
        self.F0 = np.array([k["spring"] for k in c])
        self.Fz0 = np.array([k["Fz"] for k in c])
        self.defl0 = np.array([k["defl"] for k in c])
        self.kz = ty["kz"]
        self.cz = ty["cz"]
        self.karb = list(v["k_arb"])
        # travel rows: s = A q
        A = np.zeros((4, 7))
        for i in range(4):
            A[i, :3] = [-1.0, -self.y[i], self.x[i]]
            A[i, 3 + i] = 1.0
        self.A = A
        # unsprung inertia that turns with the chassis (sliders hold the rotations)
        Ju = []
        for i, kk in enumerate(c):
            J = np.array(v["J_carrier"], dtype=float)
            if kk["front"]:
                J = J + np.array(v["J_upright"], dtype=float)
            Ju.append(J)
        Ju = np.array(Ju)
        self.Jx = v["J_s"][0] + float(np.sum(Ju[:, 0] + self.mu * self.zrel ** 2))
        self.Jy = v["J_s"][1] + float(np.sum(Ju[:, 1] + self.mu * self.zrel ** 2))
        self.M = np.diag([v["m_s"], self.Jx, self.Jy, *self.mu])
        K = A.T @ np.diag(self.k) @ A
        for ax, (l, r) in enumerate(((0, 1), (2, 3))):
            dvec = A[l] - A[r]
            K += self.karb[ax] * np.outer(dvec, dvec)
        for i in range(4):
            K[3 + i, 3 + i] += self.kz
        self.K = K
        self.Kinv = np.linalg.inv(K)
        C = A.T @ np.diag(0.5 * (self.cb + self.cr)) @ A
        for i in range(4):
            C[3 + i, 3 + i] += self.cz
        self.C = C

    def static(self, Fs=0.0, Mx=0.0, My=0.0, Fu=(0.0, 0.0, 0.0, 0.0)):
        """Incremental static solve for extra loads on the sprung mass (vertical force, moments
        about the CG) and on the wheels; returns (q, tyre loads, travels)."""
        Q = np.array([Fs, Mx, My, *Fu], dtype=float)
        q = self.Kinv @ Q
        Fz = self.Fz0 - self.kz * q[3:]
        return q, Fz, self.A @ q

    def modes(self):
        """Undamped natural frequencies (Hz) with the dominant coordinate of each mode, and the
        damped modes (mean of bump and rebound damping): (wn rad/s, zeta)."""
        names = ["heave", "roll", "pitch", "hop FL", "hop FR", "hop RL", "hop RR"]
        n = 7
        # mass-normalised coordinates, so the dominant coordinate of a shape is meaningful
        scale = np.sqrt(np.diag(self.M))
        w2, V = np.linalg.eig(np.linalg.solve(self.M, self.K))
        undamped = []
        for j in np.argsort(w2.real):
            vec = V[:, j].real * scale
            undamped.append((names[int(np.argmax(np.abs(vec)))], math.sqrt(w2[j].real)))
        Asys = np.zeros((2 * n, 2 * n))
        Asys[:n, n:] = np.eye(n)
        Minv = np.linalg.inv(self.M)
        Asys[n:, :n] = -Minv @ self.K
        Asys[n:, n:] = -Minv @ self.C
        lam, LV = np.linalg.eig(Asys)
        out = []
        for i in np.argsort(np.abs(lam)):
            lm = lam[i]
            if lm.imag <= 0:
                continue
            shape = np.abs(LV[:n, i]) * scale
            name = names[int(np.argmax(shape))]
            f0 = next((w for nm, w in undamped if nm == name), None)
            out.append({"mode": name, "f_undamped_hz": f0 / (2 * math.pi) if f0 else None,
                        "wn": float(abs(lm)), "zeta": float(-lm.real / abs(lm)),
                        "f_damped_hz": float(lm.imag / (2 * math.pi))})
        return out

    # -- the nonlinear drop test (same strut, ARB and tyre laws as the library blocks)
    def strut_force(self, s, sd):
        eps = 1e-4
        ys = s + self.F0 / self.k
        rs = np.sqrt(ys * ys + eps * eps)
        ss = 0.5 * (ys + rs)
        yb = s - self.bump
        rb = np.sqrt(yb * yb + eps * eps)
        sb = 0.5 * (yb + rb)
        yd = -s - self.droop
        rd = np.sqrt(yd * yd + eps * eps)
        sdp = 0.5 * (yd + rd)
        ve = 0.01
        Fv = 0.5 * (self.cb + self.cr) * sd + 0.5 * (self.cb - self.cr) * (np.sqrt(sd * sd + ve * ve) - ve)
        ks = self.v["k_stop"]
        return self.k * ss * ss / rs + ks * sb ** 3 / rb - ks * sdp ** 3 / rd + Fv

    def rhs(self, t, y, extra=None):
        q = y[:7]
        qd = y[7:]
        s = self.A @ q
        sd = self.A @ qd
        F = self.strut_force(s, sd)
        for ax, (l, r) in enumerate(((0, 1), (2, 3))):
            Fa = self.karb[ax] * (s[l] - s[r])
            F[l] += Fa
            F[r] -= Fa
        Q = -self.A.T @ F
        # tyres: penetration x = defl0 - zu, smooth positive force with damping
        x = self.defl0 - q[3:]
        xd = -qd[3:]
        Fh = self.kz * x + self.cz * xd
        Ft = 0.5 * (Fh + np.sqrt(Fh * Fh + 1.0))
        Q[3:] += Ft
        Q[0] -= self.v["m_s"] * G0
        Q[3:] -= self.mu * G0
        if extra is not None:
            Q += extra(t)
        qdd = np.linalg.solve(self.M, Q)
        return np.concatenate([qd, qdd])

    def drop(self, dz: float, t_end: float, times):
        y0 = np.zeros(14)
        y0[0] = dz
        sol = solve_ivp(self.rhs, (0.0, t_end), y0, method="Radau", rtol=1e-9, atol=1e-12,
                        t_eval=np.asarray(times), max_step=0.002)
        return sol


# ---------------------------------------------------------------------------------------
# Tyre helpers: steady state of the stdlib Tyre
# ---------------------------------------------------------------------------------------

_VERT: dict = {}


def vert(v) -> Vert:
    """The 7-DOF model of a vehicle, built once."""
    if v["name"] not in _VERT:
        _VERT[v["name"]] = Vert(v)
    return _VERT[v["name"]]


def loaded_radius(v, Fz):
    return v["tyre"]["R0"] - np.asarray(Fz) / v["tyre"]["kz"]


def tyre_force(v, Fz, kappa, sy, mus=1.0):
    return TY.forces(v["tyre"], Fz, kappa, sy, mus)


def rr_moment(v, Fz, omega):
    ty = v["tyre"]
    return ty["frr"] * Fz * ty["R0"] * np.tanh(omega / ty["wrr"])


def motor_limit(v, w):
    """Torque envelope of one motor at rotor speed w (as EMotorControl)."""
    m = v["motor"]
    aw = math.sqrt(w * w + 1.0)
    return min(m["T_max"], m["P_max"] / aw) * 0.5 * (1.0 - math.tanh((aw - m["w_max"]) / m["w_cut"]))


TC = {"kappa": 0.1, "v0": 1.0, "band": 0.5}      # traction control (EMotorControl defaults)


def motor_command(v, w, thr, brk, soc, axle, V):
    """Motor torque and the regenerative torque at the wheels of `axle` ('F' or 'R') for the
    pedals thr, brk at vehicle speed V (EMotorControl, written out independently)."""
    m = v["motor"]
    aw = math.sqrt(w * w + 1.0)
    Rw = v["tyre"]["R0"] - v["corners"]["FL" if axle == "F" else "RL"]["defl"]
    tc = min(max(((1 + TC["kappa"]) * abs(V) + TC["v0"] - aw * Rw / m["n"]) / TC["band"], 0.0), 1.0)
    tdrv = min(max(thr, 0.0), 1.0) * motor_limit(v, w) * min(max(soc / 0.02, 0.0), 1.0) * tc
    tb_axle = 2.0 * v["brake_max"][0 if axle == "F" else 1]
    treg = min(min(max(brk, 0.0), 1.0) * tb_axle / m["n"], min(m["T_regen"], m["P_regen"] / aw))
    treg *= min(max((1.0 - soc) / 0.02, 0.0), 1.0)
    th = math.tanh(w / m["w_fade"])
    return tdrv - treg * th, m["n"] * treg * abs(th)


def battery_current(v, P_bus, soc):
    """Discharge current and terminal voltage at the bus power P_bus (ocv - R i = V, V i = P)."""
    b = v["battery"]
    ocv = b["V_empty"] + (b["V_full"] - b["V_empty"]) * soc
    V = 0.5 * (ocv + math.sqrt(ocv * ocv - 4.0 * b["R"] * P_bus))
    return P_bus / V, V, ocv


def aero(v, u):
    drag = 0.5 * RHO * v["CdA"] * u * abs(u)
    down = 0.5 * RHO * v["ClA"] * u * u
    My = down * (v["aero_front"] * v["a"] - (1 - v["aero_front"]) * v["b"]) - (v["h_drag"] - v["h_s"]) * drag
    return drag, down, My


def horizontal_moments(v, Fx, Fy, ax=0.0, ay=0.0, gx=0.0, dz=0.0):
    """Roll and pitch moments about the sprung CG from the tyre forces at the ground (vehicle
    frame) and the d'Alembert/gravity forces of the unsprung masses (the sliders carry them to
    the chassis): returns (Mx, My). `dz` is the chassis heave from the design height (the
    downforce squats the car: the CG comes closer to the ground, the wheel centres do not)."""
    V = vert(v)
    hs = v["h_s"] + dz
    zrel = V.zrel - dz
    Mx = float(np.sum(hs * np.asarray(Fy)) + np.sum(zrel * V.mu * ay))
    My = float(np.sum(-hs * np.asarray(Fx)) + np.sum(zrel * V.mu * (-ax + gx)))
    return Mx, My


# ---------------------------------------------------------------------------------------
# Cornering
# ---------------------------------------------------------------------------------------

def steering_angles(v, steer):
    dm = -max(min(steer, 1.0), -1.0) * v["steer_max"]
    td = math.tan(dm)
    L, t, A = v["L"], v["track"][0], v["ackermann"]
    dl = (1 - A) * dm + A * math.atan(L * td / (L - 0.5 * t * td))
    dr = (1 - A) * dm + A * math.atan(L * td / (L + 0.5 * t * td))
    return dl, dr, dm


def bicycle(v, V, steer):
    """Linear bicycle model at speed V: axle cornering stiffnesses at the static loads plus the
    aero downforce; returns the understeer gradient and the steady lateral acceleration."""
    drag, down, My = aero(v, V)
    W = v["m_tot"] * G0
    Vt = vert(v)
    _, Fz, _ = Vt.static(Fs=-down, My=My)
    Cf = 2 * TY.cornering_stiffness(v["tyre"], Fz[0])
    Cr = 2 * TY.cornering_stiffness(v["tyre"], Fz[2])
    mf = (Fz[0] + Fz[1]) / G0
    mr = (Fz[2] + Fz[3]) / G0
    Kus = mf / Cf - mr / Cr                                   # rad per (m/s^2)
    _, _, dm = steering_angles(v, steer)
    ay = dm / (v["L"] / V ** 2 + Kus)
    r = ay / V
    return {"Cf": Cf, "Cr": Cr, "K_us_deg_per_g": math.degrees(Kus * G0), "ay": ay, "r": r,
            "delta": dm, "char_speed": math.sqrt(v["L"] / Kus) if Kus > 0 else None}


def steady_corner(v, V, steer, guess=None):
    """Nonlinear four-wheel steady state at speed V and steering input `steer`.

    Unknowns: beta, r, the drive torque at the differential carrier Tc, the four wheel spins
    and the four tyre loads. Equations: the longitudinal and lateral force balances and the
    yaw moment (steady circular motion: a = r x v), the four wheel spin balances (tyre, rolling
    resistance, drive torque split by the open differential and the viscous LSD) and the four
    loads of the static 7-DOF solve under the lateral/longitudinal load transfer and aero."""
    Vt = vert(v)
    dl, dr, _ = steering_angles(v, steer)
    delta = np.array([dl, dr, 0.0, 0.0])
    ty = v["tyre"]
    m = v["m_tot"]
    driven = np.array([v["corners"][c]["driven"] for c in CORNERS])
    lsd = v["lsd"]

    def forces(xv):
        beta, r, Tc = xv[0], xv[1], xv[2]
        om = xv[3:7]
        Fz = xv[7:11]
        u = V * math.cos(beta)
        w = V * math.sin(beta)
        vx = u - r * Vt.y
        vy = w + r * Vt.x
        c, s = np.cos(delta), np.sin(delta)
        Vx = c * vx + s * vy
        Vsy_carrier = -s * vx + c * vy
        Rl = loaded_radius(v, Fz)
        Vr = np.sqrt(Vx ** 2 + ty["vN"] ** 2)
        kappa = (om * Rl - Vx) / Vr
        sy = -Vsy_carrier / Vr
        Fx, Fy = tyre_force(v, Fz, kappa, sy)
        FX = c * Fx - s * Fy
        FY = s * Fx + c * Fy
        return u, w, Fx, Fy, FX, FY, Rl, om, Fz, Tc, beta, r, kappa, sy

    heave = [0.0]

    def resid(xv):
        u, w, Fx, Fy, FX, FY, Rl, om, Fz, Tc, beta, r, kappa, sy = forces(xv)
        drag, down, My_aero = aero(v, u)
        side = 0.5 * RHO * v["CyA"] * w * math.sqrt(u * u + w * w + 1e-6)
        ax = -r * w
        ay = r * u
        # the corner masses sit at (x_i, y_i) from the sprung CG (the chassis origin): steady
        # circular motion gives each a = r x v_i, so they add r^2 terms to the force balances
        # and the moment r sum m_i (x_i u + y_i w) to the yaw balance about the origin
        Sx = float(np.sum(Vt.mu * Vt.x))
        Sy = float(np.sum(Vt.mu * Vt.y))
        res = np.zeros(11)
        res[0] = np.sum(FX) - drag - (m * ax - r * r * Sx)
        res[1] = np.sum(FY) - side - (m * ay - r * r * Sy)
        res[2] = np.sum(Vt.x * FY - Vt.y * FX) - r * (Sx * u + Sy * w)
        # wheel spins: drive - Fx Rl - rolling resistance = 0
        T = np.zeros(4)
        if driven[0]:
            raise NotImplementedError("front drive in the cornering reference")
        T[2] = 0.5 * Tc - lsd * (om[2] - om[3])
        T[3] = 0.5 * Tc + lsd * (om[2] - om[3])
        res[3:7] = (T - Fx * Rl - rr_moment(v, Fz, om)) / 100.0
        Mx, My = horizontal_moments(v, FX, FY, ax=ax, ay=ay, dz=heave[0])
        My -= float(np.sum(rr_moment(v, Fz, om)))   # rolling resistance moments about the axles
        # the spinning wheels (spin axis +y, H = Jw om) turned at the yaw rate r need the moment
        # dH/dt = -r Jw om about x from the chassis: the chassis gets +r Jw sum(om)
        Mx += r * v["Jw"] * float(np.sum(om))
        _, Fz_s, _ = Vt.static(Fs=-down, Mx=Mx, My=My + My_aero)
        res[7:11] = (Fz - Fz_s) / 100.0
        return res

    if guess is None:
        b = bicycle(v, V, steer)
        Re = ty["R0"] - np.array([v["corners"][c]["defl"] for c in CORNERS])
        guess = np.concatenate([[0.0, b["r"], 200.0], V / Re, [v["corners"][c]["Fz"] for c in CORNERS]])
    for _ in range(2):         # two passes: the second with the heave of the first (CG height)
        sol, info, ier, msg = fsolve(resid, guess, full_output=True, xtol=1e-12)
        if ier != 1:
            raise RuntimeError(f"steady_corner did not converge: {msg}")
        guess = sol
        u, w, Fx, Fy, FX, FY, Rl, om, Fz, Tc, beta, r, kappa, sy = forces(sol)
        heave[0] = float(Vt.static(Fs=-aero(v, u)[1])[0][0])
    ax = -r * w
    ay = r * u
    Mx, My = horizontal_moments(v, FX, FY, ax=ax, ay=ay, dz=heave[0])
    My -= float(np.sum(rr_moment(v, Fz, om)))
    Mx += r * v["Jw"] * float(np.sum(om))
    drag, down, My_aero = aero(v, u)
    qq, _, travel = Vt.static(Fs=-down, Mx=Mx, My=My + My_aero)
    return {"V": V, "steer": steer, "beta": beta, "r": r, "ay": ay, "ax": ax, "ay_g": ay / G0,
            "Tc": Tc, "omega": om.tolist(), "Fz": Fz.tolist(), "Fx": Fx.tolist(), "Fy": Fy.tolist(),
            "kappa": kappa.tolist(), "alpha": np.arctan(sy).tolist(), "roll": float(qq[1]),
            "pitch": float(qq[2]), "travel": travel.tolist(), "delta": delta.tolist(),
            "radius": V * V / ay if abs(ay) > 1e-9 else None, "x": sol.tolist()}


# ---------------------------------------------------------------------------------------
# Straight line: top speed and braking
# ---------------------------------------------------------------------------------------

def straight_loads(v, u, Fx_axle_f, Fx_axle_r, ax=0.0, gx=0.0, cos_g=1.0):
    """Tyre loads on a straight line: aero, longitudinal tyre forces (per axle, split equally),
    the d'Alembert/gravity forces along x and, on a slope, the normal share of the weight."""
    Vt = vert(v)
    drag, down, My_aero = aero(v, u)
    Fx = np.array([Fx_axle_f / 2, Fx_axle_f / 2, Fx_axle_r / 2, Fx_axle_r / 2])
    ty = v["tyre"]
    Fs = -down - v["m_s"] * G0 * (cos_g - 1.0)
    Fu = -Vt.mu * G0 * (cos_g - 1.0)
    dz = 0.0
    for _ in range(4):         # fixed point on the heave (the CG height under the downforce)
        Mx, My = horizontal_moments(v, Fx, np.zeros(4), ax=ax, gx=gx, dz=dz)
        # the rolling resistance moments about the axles (-y on the car): their sum needs only
        # the total load, which the vertical balance fixes (weight normal share plus downforce)
        My -= ty["frr"] * ty["R0"] * math.tanh(u / ty["R0"] / ty["wrr"]) * (v["m_tot"] * G0 * cos_g + down)
        q, Fz, travel = Vt.static(Fs=Fs, Mx=Mx, My=My + My_aero, Fu=Fu)
        dz = float(q[0])
    return Fz, travel


def top_speed(v):
    """Full accelerator equilibrium of the rear-drive race car: the motor on its envelope (the
    power limit), the rotor drag, the open differential, tyre slip, rolling resistance and the
    aero drag and downforce. The shaft carries the steady torque: twist = T_shaft / k."""
    m = v["motor"]
    n = m["n"]

    def state(xv):
        V, kf, kr = xv
        Fz, _ = straight_loads(v, V, 0.0, 0.0)
        for _ in range(4):
            Fxf, _ = tyre_force(v, Fz[0], kf, 0.0)
            Fxr, _ = tyre_force(v, Fz[2], kr, 0.0)
            Fz, travel = straight_loads(v, V, 2 * Fxf, 2 * Fxr)
        Rl = loaded_radius(v, Fz)
        Fxf, _ = tyre_force(v, Fz[0], kf, 0.0)
        Fxr, _ = tyre_force(v, Fz[2], kr, 0.0)
        om_f = V * (1 + kf) / Rl[0]
        om_r = V * (1 + kr) / Rl[2]
        wm = n * om_r
        tau = motor_limit(v, wm)
        Ts = tau - m["b"] * wm
        return V, kf, kr, Fz, travel, Rl, Fxf, Fxr, om_f, om_r, wm, tau, Ts

    def resid(xv):
        V, kf, kr, Fz, travel, Rl, Fxf, Fxr, om_f, om_r, wm, tau, Ts = state(xv)
        drag, _, _ = aero(v, V)
        return [2 * Fxf + 2 * Fxr - drag,
                (-Fxf * Rl[0] - rr_moment(v, Fz[0], om_f)) / 10.0,
                (0.5 * n * Ts - Fxr * Rl[2] - rr_moment(v, Fz[2], om_r)) / 10.0]

    sol = fsolve(resid, [70.0, -0.001, 0.02], xtol=1e-13)
    V, kf, kr, Fz, travel, Rl, Fxf, Fxr, om_f, om_r, wm, tau, Ts = state(sol)
    drag, down, _ = aero(v, V)
    i, Vb, ocv = battery_current(v, tau * wm, v["battery"]["soc0"])
    return {"V": float(V), "kmh": float(V * 3.6), "kappa_f": float(kf), "kappa_r": float(kr),
            "Fz": [float(f) for f in Fz], "travel": [float(s) for s in travel], "omega_f": float(om_f),
            "omega_r": float(om_r), "motor_w": float(wm), "motor_rpm": float(wm * K_RPM), "motor_torque": float(tau),
            "shaft_torque": float(Ts), "twist": float(Ts / m["k_shaft"]), "drag": float(drag),
            "downforce": float(down), "power_kw": float(tau * wm / 1000.0), "battery_current": float(i),
            "battery_voltage": float(Vb)}


def longitudinal(v, segments, y0, times):
    """1-D longitudinal model of the rear-drive race car, integrated: the vehicle speed V, the
    front and rear wheel spins (the axles symmetric), the rotor speed, the shaft twist and the
    battery charge; quasi-static tyre loads (aero, load transfer), steady-state tyre slip,
    rolling resistance, friction brakes blended with the regeneration. `segments` is a list of
    (t_end, throttle, brake) with constant pedals; y0 = [V, om_f, om_r, w_m, twist, soc]."""
    ty = v["tyre"]
    m = v["motor"]
    n = m["n"]
    M = v["m_tot"]
    Jw = v["Jw"]
    weps = v["brake_w_eps"]
    Q = v["battery"]["Q"] * 3600.0
    Tf, Tr = v["brake_max"]
    state = {"Fz": None}

    def rhs(t, y, thr, brk):
        V, omf, omr, wm, phi, soc = y
        Fz = state["Fz"]
        if Fz is None:
            Fz, _ = straight_loads(v, V, 0.0, 0.0)
        for _ in range(2):
            Rl = loaded_radius(v, Fz)
            Vr = math.sqrt(V * V + ty["vN"] ** 2)
            kf = (omf * Rl[0] - V) / Vr
            kr = (omr * Rl[2] - V) / Vr
            Fxf, _ = tyre_force(v, Fz[0], kf, 0.0)
            Fxr, _ = tyre_force(v, Fz[2], kr, 0.0)
            drag, _, _ = aero(v, V)
            ax = (2 * Fxf + 2 * Fxr - drag) / M
            Fz, _ = straight_loads(v, V, 2 * Fxf, 2 * Fxr, ax=ax)
        state["Fz"] = Fz
        tau, regen = motor_command(v, wm, thr, brk, soc, "R", V)
        Ts = m["k_shaft"] * phi + m["d_shaft"] * (wm - n * omr)
        bf = Tf * min(max(brk, 0.0), 1.0)
        br = max(Tr * min(max(brk, 0.0), 1.0) - 0.5 * regen, 0.0)
        i, _, _ = battery_current(v, tau * wm, soc)
        return [ax,
                (-Fxf * Rl[0] - rr_moment(v, Fz[0], omf) - bf * math.tanh(omf / weps)) / Jw,
                (0.5 * n * Ts - Fxr * Rl[2] - rr_moment(v, Fz[2], omr) - br * math.tanh(omr / weps)) / Jw,
                (tau - m["b"] * wm - Ts) / m["J"],
                wm - n * omr,
                -i / Q]

    t0 = 0.0
    y = list(y0)
    ts, ys = [], []
    for t_end, thr, brk in segments:
        want = [t for t in times if t0 <= t <= t_end and not (ts and t <= ts[-1])]
        te = sorted(set(want) | {t_end})
        sol = solve_ivp(rhs, (t0, t_end), y, method="LSODA", rtol=1e-9, atol=1e-9, t_eval=te,
                        max_step=0.001, args=(thr, brk))
        for k, t in enumerate(sol.t):
            if t in want:
                ts.append(float(t))
                ys.append(sol.y[:, k])
        y = list(sol.y[:, -1])
        state["Fz"] = None
        t0 = t_end
    Y = np.array(ys).T
    out = {"t": [float(t) for t in ts], "V": Y[0].tolist(), "omega_f": Y[1].tolist(), "omega_r": Y[2].tolist(),
           "motor_w": Y[3].tolist(), "motor_rpm": (Y[3] * K_RPM).tolist(), "twist": Y[4].tolist(),
           "soc": Y[5].tolist()}
    # the motor torque and the battery current at the sample times (pedals of the segment)
    taus, cur = [], []
    for k, t in enumerate(ts):
        thr, brk = next((s[1], s[2]) for s in segments if t <= s[0] + 1e-12)
        tau, _ = motor_command(v, Y[3][k], thr, brk, Y[5][k], "R", Y[0][k])
        taus.append(tau)
        cur.append(battery_current(v, tau * Y[3][k], Y[5][k])[0])
    out["motor_torque"] = taus
    out["battery_current"] = cur
    return out


# ---------------------------------------------------------------------------------------
# Buggy on a grade (four-wheel drive)
# ---------------------------------------------------------------------------------------

def grade(v, slope: float, V: float):
    """Constant speed V straight up a plane of gradient `slope` (rise per run). One motor per
    axle on the same accelerator (equal motor torque, both below the base speed), open axle
    differentials (symmetric). Returns the accelerator position the speed hold needs at the
    equilibrium, the motor torque and the tyre loads."""
    gam = math.atan(slope)
    m = v["motor"]
    n = m["n"]
    M = v["m_tot"]

    def solve_slips(Fz, tau):
        Rl = loaded_radius(v, Fz)

        def r(k):
            kf, kr = k
            Fxf, _ = tyre_force(v, Fz[0], kf, 0.0)
            Fxr, _ = tyre_force(v, Fz[2], kr, 0.0)
            omf = V * (1 + kf) / Rl[0]
            omr = V * (1 + kr) / Rl[2]
            Tf = 0.5 * n * (tau - m["b"] * n * omf)
            Tr = 0.5 * n * (tau - m["b"] * n * omr)
            return [(Tf - Fxf * Rl[0] - rr_moment(v, Fz[0], omf)) / 10.0,
                    (Tr - Fxr * Rl[2] - rr_moment(v, Fz[2], omr)) / 10.0]

        kf, kr = fsolve(r, [0.02, 0.02], xtol=1e-13)
        Fxf, _ = tyre_force(v, Fz[0], kf, 0.0)
        Fxr, _ = tyre_force(v, Fz[2], kr, 0.0)
        return kf, kr, Fxf, Fxr

    def loads(tau):
        Fz, travel = straight_loads(v, V, 0.0, 0.0, gx=-G0 * math.sin(gam), cos_g=math.cos(gam))
        for _ in range(8):
            kf, kr, Fxf, Fxr = solve_slips(Fz, tau)
            Fz, travel = straight_loads(v, V, 2 * Fxf, 2 * Fxr, gx=-G0 * math.sin(gam), cos_g=math.cos(gam))
        return Fz, travel, kf, kr, Fxf, Fxr

    def resid(xv):
        Fz, travel, kf, kr, Fxf, Fxr = loads(xv[0])
        drag, _, _ = aero(v, V)
        return [(2 * Fxf + 2 * Fxr - drag - M * G0 * math.sin(gam)) / 100.0]

    tau = float(fsolve(resid, [60.0], xtol=1e-13)[0])
    Fz, travel, kf, kr, Fxf, Fxr = loads(tau)
    Rl = loaded_radius(v, Fz)
    omf = V * (1 + kf) / Rl[0]
    omr = V * (1 + kr) / Rl[2]
    thr = tau / motor_limit(v, n * omr)
    P = tau * n * (omf + omr)
    i, Vb, _ = battery_current(v, P, v["battery"]["soc0"])
    return {"slope": slope, "angle_deg": math.degrees(gam), "V": V, "motor_torque": tau, "Fz": [float(f) for f in Fz],
            "travel": [float(s) for s in travel], "kappa_f": float(kf), "kappa_r": float(kr),
            "Fx_f": float(Fxf), "Fx_r": float(Fxr), "motor_rpm_f": float(n * omf * K_RPM),
            "motor_rpm_r": float(n * omr * K_RPM), "throttle": float(thr), "omega_f": float(omf),
            "omega_r": float(omr), "power_kw": float(P / 1000.0), "battery_current": float(i)}


# ---------------------------------------------------------------------------------------

def main() -> int:
    V = vehicles()
    out: dict = {"$comment": "Independent references of the cars example (design/reference.py)."}
    drop_times = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 1.0, 2.0, 3.0]
    for name, v in V.items():
        Vt = vert(v)
        r: dict = {"m_tot": v["m_tot"], "a": v["a"], "b": v["b"], "h_s": v["h_s"],
                   "corners": {c: {k: v["corners"][c][k] for k in ("x", "y", "z", "z_world", "spring", "Fz", "defl")}
                               for c in CORNERS}}
        r["roll_stiffness"] = {
            "front": v["k"][0] * v["track"][0] ** 2 / 2 + v["k_arb"][0] * v["track"][0] ** 2,
            "rear": v["k"][1] * v["track"][1] ** 2 / 2 + v["k_arb"][1] * v["track"][1] ** 2,
        }
        r["modes"] = Vt.modes()
        sol = Vt.drop(0.03, 3.0, drop_times)
        r["drop"] = {"dz": 0.03, "t": drop_times, "z": (v["h_s"] + sol.y[0]).tolist(),
                     "pitch": sol.y[2].tolist(),
                     "travel_FL": (Vt.A @ sol.y[:7])[0].tolist(), "travel_RL": (Vt.A @ sol.y[:7])[2].tolist(),
                     "Fz_FL": (Vt.Fz0[0] - Vt.kz * sol.y[3]).tolist(), "Fz_RL": (Vt.Fz0[2] - Vt.kz * sol.y[5]).tolist()}
        out[name] = r
        print(f"{name}: m {v['m_tot']:.1f} kg, corner loads {[round(v['corners'][c]['Fz'], 1) for c in CORNERS]}")
        for md in r["modes"]:
            print(f"   mode {md['mode']:8s} f {md['f_undamped_hz']:.3f} Hz, damped wn {md['wn']:.2f} rad/s zeta {md['zeta']:.3f}")
        print("   drop z", [round(z, 5) for z in r["drop"]["z"]])
        print("   drop pitch", [round(p, 6) for p in r["drop"]["pitch"]])

    # race car: cornering at 25 m/s, top speed in 6th, braking from there
    rc = V["racecar"]
    corner = []
    guess = None
    for s in (-0.04, -0.08, -0.12):
        b = bicycle(rc, 25.0, s)
        st = steady_corner(rc, 25.0, s, guess)
        guess = np.array(st["x"])
        st["bicycle"] = b
        corner.append(st)
        print(f"racecar corner steer {s}: ay {st['ay_g']:.4f} g (bicycle {b['ay'] / G0:.4f} g), r {st['r']:.4f}, "
              f"beta {math.degrees(st['beta']):.3f} deg, roll {math.degrees(st['roll']):.3f} deg, "
              f"Fz {[round(f, 1) for f in st['Fz']]}, Tc {st['Tc']:.1f}")
    out["racecar"]["corner"] = corner
    out["racecar"]["bicycle_25"] = bicycle(rc, 25.0, -0.04)
    ts = top_speed(rc)
    out["racecar"]["top_speed"] = ts
    print(f"racecar top speed {ts['V']:.3f} m/s ({ts['kmh']:.1f} km/h), motor {ts['motor_rpm']:.0f} rpm "
          f"{ts['motor_torque']:.1f} N m {ts['power_kw']:.1f} kW, battery {ts['battery_current']:.0f} A, "
          f"Fz {[round(f, 1) for f in ts['Fz']]}")
    soc0 = rc["battery"]["soc0"]
    # launch: full accelerator from standstill for 12 s
    la_times = [round(0.25 * k, 2) for k in range(49)]
    la = longitudinal(rc, [(12.0, 1.0, 0.0)], [0.0, 0.0, 0.0, 0.0, 0.0, soc0], la_times)
    out["racecar"]["launch"] = la
    print("racecar launch V", [round(x, 3) for x in la["V"][::4]])
    print("racecar launch soc", [round(x, 6) for x in la["soc"][::8]])
    # flat out from the top speed for 10 s, then brake pedal 0.5 (regen + friction) for 4 s; the
    # model ramps the pedals over 55 ms (build_model.RAMP), here a step at the middle of that ramp
    st_times = [0.0, 2.0, 5.0, 9.9] + [round(10.0 + 0.25 * k, 2) for k in range(17)]
    y0 = [ts["V"], ts["omega_f"], ts["omega_r"], ts["motor_w"], ts["twist"], soc0]
    sd = longitudinal(rc, [(10.0275, 1.0, 0.0), (14.0, 0.0, 0.5)], y0, st_times)
    out["racecar"]["straight"] = sd
    print("racecar straight V", [round(x, 3) for x in sd["V"]])
    print("racecar straight motor torque", [round(x, 2) for x in sd["motor_torque"]])
    # buggy on a 25 % grade at 5 m/s
    bg = V["buggy"]
    gr = grade(bg, 0.25, 5.0)
    out["buggy"]["grade"] = gr
    print(f"buggy grade {gr['angle_deg']:.2f} deg: throttle {gr['throttle']:.4f}, motor {gr['motor_torque']:.2f} N m "
          f"at {gr['motor_rpm_r']:.0f} rpm, {gr['power_kw']:.2f} kW, Fz {[round(f, 1) for f in gr['Fz']]}, "
          f"kappa f/r {gr['kappa_f']:.4f}/{gr['kappa_r']:.4f}")
    (HERE / "design.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote design.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
