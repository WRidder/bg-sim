"""The A109 model as bg-sim builds it, in SI: the reference the bg-sim models are checked against.

`heli_ref.py` is the report's subroutine line by line (ft, lb); this module is the same physics
written the way the bg-sim library blocks compute it, block by block, so that a bg-sim run and a
scipy run of the same scenario agree to the solver tolerance:

* the data converted to SI (`si_data`); every formula of the report is dimensionally homogeneous,
  so only the inputs change (the one hidden dimensional constant, the 1 ft shift of the tail
  downwash edge, D.DW + 1, becomes 0.3048 m);
* the component forces as the blocks `MainRotor`, `TailRotor`, `Fuselage`, `Tailplane` and `Fin`
  compute them, each applied at its own point (the bond graph forms r x F through a
  FixedTransform3DNeutral), plus the few moments the report writes differently from r x F;
* the thrust/inflow balance solved by the same fixed, unrolled Newton iteration as the blocks
  (`inflow`), not by a root finder;
* the full Newton-Euler rigid body (bg-sim's RigidBody3D) instead of the report's simplified one;
* the rotor-speed degree of freedom (ours, not in the report): the rotational bond graph of the
  drivetrain with the governor (`Drive`), and a switch that lets the rotor aerodynamics see the
  nominal speed (`rpm_mode = 0`, the report's constant-RPM model) or the actual one (1);
* ground effect (ours, switchable): the Cheeseman-Bennett factor as an induced-velocity factor.

Body axes in this module are the report's FRD; the bg-sim blocks convert at their boundaries.
"""

from __future__ import annotations

import math

import numpy as np

from heli_data import A109, GRAV, HP, RHO_SL

FT = 0.3048
LBF = 4.4482216152605
SLUG = LBF / FT              # 14.5939 kg
SLUGFT2 = SLUG * FT * FT     # 1.35582 kg m^2
W_PER_HP = HP * LBF * FT     # 745.70 W
G0 = GRAV * FT               # 9.80665 m/s^2 (32.174 ft/s^2)
RHO0 = RHO_SL * SLUG / FT ** 3   # 1.22506 kg/m^3

N_NEWTON = 8                 # unrolled Newton steps of the inflow balance (blocks MainRotor, TailRotor)
EPS_ABS = 1.0e-3             # m/s: |x| x is written x sqrt(x^2 + EPS_ABS^2) (no event at every sign change)
EPS_DIV = 1.0e-6             # (m/s)^2: 1/x is written x/(x^2 + EPS_DIV) where x can pass zero in a descent

# Ours (not in the report); see the README, "Assumptions"
P_MAX_HP = 740.0             # 2 x 370 shp, AEO take-off of the 250-C20B installation (EASA TCDS R.005, A109A II)
J_AUX = 0.10                 # engine, transmission and tail rotor inertia, as a fraction of the main rotor's
GOV_WN = 2.5                 # rad/s, governor + rotor natural frequency (second order, report section V.B)
GOV_ZETA = 0.8
# Smoothed switches (ours, `smooth` = 1, used by the flyable a109-sim): the report's hard switches
# (dihedral magnification below VTRANS, wake edge on the tailplane, tailplane and fin stall at
# |wa| > 0.3 |u|) are discontinuities of the right-hand side, and a closed loop that holds the
# aircraft at one of them slides along it (chatter). With smooth = 1 each switch is a tanh blend of
# the two sides over a narrow band; smooth = 0 is the report's model.
SM_WAKE_W = 1.0              # m/s: dihedral magnification fades over VTRANS +- ~1 m/s
SM_DW_W = 0.3                # m: the wake edge reaches the tailplane over ~ +-0.3 m
SM_STALL_W = 0.01            # stall blend over (wa/u)^2 = 0.09 +- 0.01 (|wa/u| ~ 0.28 .. 0.32)


def si_data(d: dict = A109) -> dict:
    """The report's data in SI: lengths m (stations converted to positions relative to the CG,
    D positive aft, H positive up), areas m^2, inertias kg m^2, speeds m/s, powers W."""
    cg_fs, cg_wl = d["FS_CG"], d["WL_CG"]
    s = {"name": d["name"], "a109": d["variant"] == "a109"}
    s["m"] = d["WT"] / GRAV * SLUG
    s["weight"] = d["WT"] * LBF
    for k in ("IX", "IY", "IZ", "IXZ"):
        s[k] = d[k] * SLUGFT2
    for k in ("HUB", "FUS", "WN", "HT", "VT", "TR"):
        s["D_" + k] = (d["FS_" + k] - cg_fs) / 12.0 * FT
        s["H_" + k] = (d["WL_" + k] - cg_wl) / 12.0 * FT
    s["IS"] = d["IS"]
    s["E"] = d["E_MR"] * FT
    s["I_B"] = d["I_B"] * SLUGFT2
    s["R"] = d["R_MR"] * FT
    s["A"] = d["A_MR"]
    s["OMEGA0"] = d["RPM_MR"] * 2 * math.pi / 60
    s["CDO"] = d["CDO"]
    s["B"] = d["B_MR"]
    s["C"] = d["C_MR"] * FT
    s["TWST"] = d["TWST_MR"]
    s["K1"] = d["K1"]
    for k in ("XUU_FUS", "YVV_FUS", "ZWW_FUS", "ZUU_WN", "ZUW_WN", "ZMAX_WN", "ZUU_HT", "ZUW_HT", "ZMAX_HT",
              "YUU_VT", "YUV_VT", "YMAX_VT"):
        s[k] = d[k] * FT * FT
    s["B_WN"] = d["B_WN"] * FT
    s["R_TR"] = d["R_TR"] * FT
    s["A_TR"] = d["A_TR"]
    s["SOL_TR"] = d["SOL_TR"]
    s["OMEGA_TR0"] = d["RPM_TR"] * 2 * math.pi / 60
    s["TWST_TR"] = d["TWST_TR"]
    s["P_LOSS"] = d["HP_LOSS"] * W_PER_HP
    s["VTRANS"] = d["VTRANS"] * FT
    s["DW_SHIFT"] = 1.0 * FT if s["a109"] else 0.0      # D.DW = D.DW + 1 (ft)
    s["FW_GAIN"] = 3.0 if s["a109"] else 1.0            # D.FW = 3 D.FW
    s["rho0"] = RHO_SL * SLUG / FT ** 3
    # report constants evaluated at the nominal rotor speed (lines 1680 .. 1699)
    om = s["OMEGA0"]
    vtip = s["R"] * om
    s["CT"] = s["weight"] / (s["rho0"] * math.pi * s["R"] ** 2 * vtip ** 2)
    a_sigma = s["A"] * s["B"] * s["C"] / s["R"] / math.pi
    s["DB1DV"] = 2 / (om * s["R"]) * (8 * s["CT"] / a_sigma + math.sqrt(s["CT"] / 2))
    s["DA1DU"] = -s["DB1DV"]
    s["FR"] = s["CDO"] * s["R"] * s["B"] * s["C"]
    # drivetrain (ours)
    s["J_MR"] = s["B"] * s["I_B"]                       # polar inertia of the blades ~ B x flap inertia
    s["J_DT"] = s["J_MR"] * (1 + J_AUX)                 # + engines, transmission, tail rotor (reflected)
    s["N_TR"] = s["OMEGA_TR0"] / s["OMEGA0"]            # tail rotor gear ratio 2080/385
    s["P_MAX"] = P_MAX_HP * W_PER_HP
    s["KI_GOV"] = s["J_DT"] * GOV_WN ** 2
    s["KP_GOV"] = 2 * GOV_ZETA * GOV_WN * s["J_DT"]
    # the airframe carries the report's inertia less the drivetrain's polar inertia (about the
    # body z axis, the report's rotor-torque axis): with the rotor speed frozen relative to the
    # airframe the yaw inertia is the report's
    s["IZ_AF"] = s["IZ"] - s["J_DT"]
    s["vh"] = math.sqrt(s["weight"] / (2 * s["rho0"] * math.pi * s["R"] ** 2))   # hover induced velocity
    return s


def sabs(x: float) -> float:
    return math.sqrt(x * x + EPS_ABS * EPS_ABS)


def sinv(x: float) -> float:
    return x / (x * x + EPS_DIV)


def isa_density(h: float, rho0: float = RHO0) -> float:
    """ISA troposphere: T = 288.15 K - 6.5 K/km h, rho ~ (T/T0)^4.2559 (h in m)."""
    return rho0 * (1.0 - 2.25577e-5 * h) ** 4.25588


def inflow(k_t: float, rho_a: float, wb: float, wr: float, u2: float, kg: float = 1.0):
    """Thrust and induced velocity of an actuator disc: T = k_t (WB - kg vi) (blade element,
    `kg` the ground-effect factor) and vi sqrt(U^2 + (WR - vi)^2) = T / (2 rho A) (momentum, the
    report's lines 6540 .. 6610 solved for vi). The same N_NEWTON-step Newton iteration as the
    bg-sim blocks, from the root of the quadratic with |WR - vi| ~ sqrt(U^2 + WR^2) + vi."""
    c = k_t / (2.0 * rho_a)
    vp = math.sqrt(u2 + wr * wr)
    b = vp + c * kg
    disc = b * b + 4.0 * c * wb
    vi = 2.0 * c * wb / (b + math.sqrt(math.sqrt(disc * disc + 1.0)))
    for _ in range(N_NEWTON):
        dd = wr - vi
        s = math.sqrt(u2 + dd * dd + 1.0e-4)
        f = vi * s - c * (wb - kg * vi)
        fp = s - vi * dd / s + c * kg
        vi = vi - f / fp
    return vi, k_t * (wb - kg * vi)


# State: u v w p q r (FRD, m/s, rad/s) phi theta psi (rad) xn ye zd (m) a1 b1 (rad) Om (rad/s, the
# rotor's absolute speed) xi (N m, the governor integrator)
IU, IV, IW, IP, IQ, IR, IPHI, ITH, IPSI, IXN, IYE, IZD, IA1, IB1, IOM, IXI = range(16)
NX = 16


class Heli:
    def __init__(self, s: dict | None = None, rpm_mode: int = 0, ge: int = 0, governor: bool = True,
                 h_field: float = 0.0, smooth: float = 0.0):
        self.s = si_data() if s is None else s
        self.smooth = smooth
        self.rpm_mode = rpm_mode
        self.ge = ge
        self.governor = governor
        self.h_field = h_field
        s = self.s
        J = np.array([[s["IX"], 0.0, -s["IXZ"]], [0.0, s["IY"], 0.0], [-s["IXZ"], 0.0, s["IZ_AF"]]])
        self.J = J
        self.Jinv = np.linalg.inv(J)
        self.r = {k: np.array([-s["D_" + k], 0.0, -s["H_" + k]]) for k in ("HUB", "FUS", "HT", "VT", "TR")}

    # ------------------------------------------------------------------ blocks
    def main_rotor(self, ua, om, c, a1, b1, rho, hgt):
        """Block MainRotor. ua = air-relative (u v w p q r) FRD; om the rotor speed the
        aerodynamics see; c = (theta0, B1, A1); a1, b1 the flapping states. Returns the
        flapping rates, the hub force (FRD), the hub moment (the flapping spring, FRD), the
        thrust, induced velocity, power and the aerodynamic torque."""
        s = self.s
        u, v, w, p, q, r = ua
        th0, B1, A1 = c
        R, e = s["R"], s["E"]
        gam16 = rho * s["A"] * s["C"] * R ** 4 / s["I_B"] * om / 16 * (1 + 8 / 3 * e / R)
        kc = 0.75 * om * e / R / gam16 + s["K1"]
        if s["a109"]:
            itb2, itb = 0.0, gam16
        else:
            itb2 = om / (1 + (om / gam16) ** 2)
            itb = itb2 * om / gam16
        dl_db1 = s["B"] / 2 * (1.5 * s["I_B"] * e / R * om * om)
        wake = 1.0 if u < s["VTRANS"] else 0.0
        if self.smooth:
            wake = self.smooth * 0.5 * (1 - math.tanh((u - s["VTRANS"]) / SM_WAKE_W)) + (1 - self.smooth) * wake
        wake = wake if s["a109"] else 0.0
        a_sum = b1 - A1 + kc * a1 + s["DB1DV"] * v * (1 + wake)
        b_sum = a1 + B1 - kc * b1 + s["DA1DU"] * u * (1 + 2 * wake)
        a1dot = -itb * b_sum - itb2 * a_sum - q
        b1dot = -itb * a_sum + itb2 * b_sum - p
        wr = w + (a1 - s["IS"]) * u - b1 * v
        wb = wr + 2 / 3 * om * R * (th0 + 0.75 * s["TWST"])
        k_t = om * R * rho * s["A"] * s["B"] * s["C"] * R / 4
        kg = 1.0
        if self.ge:
            zr = math.sqrt(hgt * hgt + 0.25 * R * R)       # ~ max(hgt, R/2), smooth
            kg = 1.0 - (R / (4 * zr)) ** 2 / (1 + (u * u + v * v) / s["vh"] ** 2)
        vi, T = inflow(k_t, rho * math.pi * R * R, wb, wr, u * u + v * v, kg)
        F = np.array([-T * (a1 - s["IS"]), T * b1, -T])
        # report: N.MR has no -D.HUB Y.MR (r x F at the hub has): the block adds it back
        Mh = np.array([dl_db1 * b1, dl_db1 * a1, s["D_HUB"] * T * b1])
        return dict(a1dot=a1dot, b1dot=b1dot, F=F, M=Mh, T=T, vi=vi, vi_eff=kg * vi, wr=wr, kg=kg)

    def rotor_power(self, ua, om, T, vi_eff, fus, hdot, rho):
        """POWER.MR (lines 6780 .. 6850): induced + climb + parasite + profile, and TORQUE.MR."""
        s = self.s
        u, v = ua[0], ua[1]
        R = s["R"]
        p_ind = T * vi_eff
        p_climb = s["weight"] * hdot
        p_para = fus["p_para"]
        p_prof = rho / 2 * (s["FR"] / 4) * om * R * (om * om * R * R + 4.6 * (u * u + v * v))
        pw = p_ind + p_climb + p_para + p_prof
        return pw, pw / om, dict(p_ind=p_ind, p_climb=p_climb, p_para=p_para, p_prof=p_prof)

    def fuselage(self, ua, vi, rho):
        s = self.s
        u, v, w = ua[0], ua[1], ua[2]
        r2 = rho / 2
        wa = w - vi
        d_fw = u * sinv(-wa) * (s["H_HUB"] - s["H_FUS"]) - (s["D_FUS"] - s["D_HUB"])
        d_fw = s["FW_GAIN"] * d_fw
        X = r2 * s["XUU_FUS"] * sabs(u) * u
        Y = r2 * s["YVV_FUS"] * sabs(v) * v
        Z = r2 * s["ZWW_FUS"] * sabs(wa) * wa
        F = np.array([X, Y, Z])
        # report: M = Z D.FW - X H.FUS, N = 0; r x F at the fuselage point gives M = Z D.FUS - X H.FUS,
        # N = -D.FUS Y: the block adds the difference
        Mx = np.array([0.0, Z * (d_fw - s["D_FUS"]), s["D_FUS"] * Y])
        return dict(F=F, M=Mx, p_para=-X * u - Y * v - Z * wa, d_fw=d_fw)

    def tail_rotor(self, ua, omt, thtr, rho):
        s = self.s
        u, v, w, p, q, r = ua
        Rt = s["R_TR"]
        vr = -(v - r * s["D_TR"] + p * s["H_TR"])
        vb = vr + 2 / 3 * omt * Rt * (thtr + 0.75 * s["TWST_TR"])
        k_t = omt * Rt * rho * s["A_TR"] * s["SOL_TR"] * math.pi * Rt * Rt / 4
        vi, T = inflow(k_t, rho * math.pi * Rt * Rt, vb, vr, (w + q * s["D_TR"]) ** 2 + u * u)
        return dict(F=np.array([0.0, T, 0.0]), T=T, vi=vi, P=T * vi)

    def tailplane(self, ua, vi, rho):
        s = self.s
        u, v, w, p, q, r = ua
        r2 = rho / 2
        R = s["R"]
        d_dw = u * sinv(vi - w) * (s["H_HUB"] - s["H_HT"]) - (s["D_HT"] - s["D_HUB"] - R) + s["DW_SHIFT"]
        edge = 1.0 if d_dw > 0 else 0.0
        if self.smooth:
            edge = self.smooth * 0.5 * (1 + math.tanh(d_dw / SM_DW_W)) + (1 - self.smooth) * edge
        eps = edge * (2 * (1 - d_dw / R) if d_dw < R else 0.0)
        wa = w - eps * vi + s["D_HT"] * q
        vta = math.sqrt(u * u + v * v + wa * wa)
        sig = self.stall(wa, u)
        Z = sig * r2 * s["ZMAX_HT"] * vta * wa + (1 - sig) * r2 * (s["ZUU_HT"] * sabs(u) * u + s["ZUW_HT"] * sabs(u) * wa)
        return dict(F=np.array([0.0, 0.0, Z]), eps=eps, stall=sig)

    def stall(self, a, u):
        """1 when the surface is stalled (|a| > 0.3 |u|), a tanh blend with smooth = 1."""
        hard = 1.0 if a * a > 0.09 * u * u else 0.0
        if not self.smooth:
            return hard
        soft = 0.5 * (1 + math.tanh((a * a - 0.09 * u * u) / (SM_STALL_W * (u * u + 1.0))))
        return self.smooth * soft + (1 - self.smooth) * hard

    def fin(self, ua, vi_tr, rho):
        s = self.s
        u, v, w, p, q, r = ua
        r2 = rho / 2
        va = v + vi_tr - s["D_VT"] * r
        vta = math.sqrt(u * u + va * va)
        sig = self.stall(va, u)
        Y = sig * r2 * s["YMAX_VT"] * vta * va + (1 - sig) * r2 * (s["YUU_VT"] * sabs(u) * u + s["YUV_VT"] * sabs(u) * va)
        return dict(F=np.array([0.0, Y, 0.0]), stall=sig)

    # ------------------------------------------------------------------ the drivetrain (ours)
    def drive(self, om_abs, xi, r_frd, q_mr, q_tr, on=1.0):
        """The rotational bond graph: rotor 1-junction (inertia J_DT, absolute speed Om, the
        aerodynamic torque), mast 0-junction (common torque tau; flows Om = Om_rel + w_axis with
        the airframe's rate about the shaft axis w_axis = -r), gearbox 1-junction (relative
        speed Om_rel: engine torque, loss torque P_LOSS/Om_rel, tail rotor drive through the
        gear N_TR). Returns d(Om)/dt, d(xi)/dt, the mast torque and the engine torque."""
        s = self.s
        om_rel = om_abs + r_frd
        e = s["OMEGA0"] - om_rel
        qmax = s["P_MAX"] / om_rel
        qcmd = s["KP_GOV"] * e + xi
        qeng = on * min(max(qcmd, 0.0), qmax) if self.governor else xi
        dxi = s["KI_GOV"] * e if (self.governor and 0.0 < qcmd < qmax) else 0.0
        q_loss = s["P_LOSS"] / om_rel
        tau = qeng - q_loss - s["N_TR"] * q_tr
        dom = (tau - q_mr) / s["J_DT"]
        return dom, dxi, tau, qeng, om_rel

    # ------------------------------------------------------------------ the whole aircraft
    def components(self, x, ctrl, wind=(0.0, 0.0, 0.0), on=1.0):
        s = self.s
        phi, th, psi = x[IPHI], x[ITH], x[IPSI]
        Rm = dcm(phi, th, psi)
        vb = x[IU:IW + 1] - Rm.T @ np.array(wind)
        ua = np.r_[vb, x[IP:IR + 1]]
        h = -x[IZD]
        rho = isa_density(h + self.h_field, s["rho0"])
        om_abs = x[IOM]
        om_rel = om_abs + x[IR]
        om_mr = s["OMEGA0"] if self.rpm_mode == 0 else om_abs
        om_tr = s["OMEGA_TR0"] if self.rpm_mode == 0 else s["N_TR"] * om_rel
        th0, B1, A1, thtr = ctrl
        hub_h = h + s["H_HUB"]     # hub height above the ground (level attitude)
        mr = self.main_rotor(ua, om_mr, (th0, B1, A1), x[IA1], x[IB1], rho, hub_h)
        fus = self.fuselage(ua, mr["vi"], rho)
        tr = self.tail_rotor(ua, om_tr, thtr, rho)
        ht = self.tailplane(ua, mr["vi"], rho)
        vt = self.fin(ua, tr["vi"], rho)
        hdot = climb_rate(x)
        p_mr, q_mr, pw = self.rotor_power(ua, om_mr, mr["T"], mr["vi_eff"], fus, hdot, rho)
        q_tr = tr["P"] / om_tr
        dom, dxi, tau, qeng, _ = self.drive(om_abs, x[IXI], x[IR], q_mr, q_tr, on)
        F = mr["F"] + fus["F"] + tr["F"] + ht["F"] + vt["F"]
        M = (np.cross(self.r["HUB"], mr["F"]) + mr["M"] + np.cross(self.r["FUS"], fus["F"]) + fus["M"]
             + np.cross(self.r["TR"], tr["F"]) + np.cross(self.r["HT"], ht["F"]) + np.cross(self.r["VT"], vt["F"]))
        M = M + np.array([0.0, 0.0, tau])      # the mast reaction (shaft axis = body z, as the report's N.MR)
        power = p_mr + tr["P"] + s["P_LOSS"]
        return dict(F=F, M=M, mr=mr, fus=fus, tr=tr, ht=ht, vt=vt, p_mr=p_mr, q_mr=q_mr, q_tr=q_tr, tau=tau,
                    qeng=qeng, dom=dom, dxi=dxi, power=power, rho=rho, ua=ua, om_rel=om_rel, pw=pw, hdot=hdot)

    def deriv(self, x, ctrl, wind=(0.0, 0.0, 0.0), on=1.0):
        o = self.components(x, ctrl, wind, on)
        s = self.s
        xd = np.zeros(NX)
        phi, th, psi = x[IPHI], x[ITH], x[IPSI]
        Rm = dcm(phi, th, psi)
        vel = x[IU:IW + 1]
        w = x[IP:IR + 1]
        grav = Rm.T @ np.array([0.0, 0.0, s["m"] * G0])
        xd[IU:IW + 1] = (o["F"] + grav) / s["m"] - np.cross(w, vel)
        xd[IP:IR + 1] = self.Jinv @ (o["M"] - np.cross(w, self.J @ w))
        cf, sf, ct, st = math.cos(phi), math.sin(phi), math.cos(th), math.sin(th)
        p, q, r = w
        xd[IPHI] = p + (q * sf + r * cf) * st / ct
        xd[ITH] = q * cf - r * sf
        xd[IPSI] = (q * sf + r * cf) / ct
        xd[IXN:IZD + 1] = Rm @ vel
        xd[IA1] = o["mr"]["a1dot"]
        xd[IB1] = o["mr"]["b1dot"]
        xd[IOM] = o["dom"]
        xd[IXI] = o["dxi"]
        return xd, o


def dcm(phi, th, psi):
    """Body (FRD) to earth (NED)."""
    cf, sf, ct, st, cp, sp = math.cos(phi), math.sin(phi), math.cos(th), math.sin(th), math.cos(psi), math.sin(psi)
    return np.array([[ct * cp, sf * st * cp - cf * sp, cf * st * cp + sf * sp],
                     [ct * sp, sf * st * sp + cf * cp, cf * st * sp - sf * cp],
                     [-st, sf * ct, cf * ct]])


def climb_rate(x):
    Rm = dcm(x[IPHI], x[ITH], x[IPSI])
    return -(Rm @ x[IU:IW + 1])[2]


def trim(h: Heli, vn=0.0, ve=0.0, vd=0.0, psi=0.0, alt=0.0, guess=None):
    """Steady straight flight at the earth velocity (vn, ve, vd) (m/s, NED), altitude alt (m) and
    heading psi; the rotor at its governed speed. Unknowns (theta0, B1, A1, theta_tr, theta, phi,
    a1, b1); returns (x, ctrl, outputs) with the governor integrator set to the engine torque."""
    from scipy.optimize import fsolve
    s = h.s

    def unpack(z):
        c = np.array(z[0:4])
        th, phi, a1, b1 = z[4:8]
        x = np.zeros(NX)
        x[IU:IW + 1] = dcm(phi, th, psi).T @ np.array([vn, ve, vd])
        x[IPHI], x[ITH], x[IPSI], x[IA1], x[IB1] = phi, th, psi, a1, b1
        x[IZD] = -alt
        x[IOM] = s["OMEGA0"]
        return x, c

    def with_xi(x, c):
        o = h.components(x, c)
        x[IXI] = o["q_mr"] + s["P_LOSS"] / s["OMEGA0"] + s["N_TR"] * o["q_tr"]
        return x

    def res(z):
        x, c = unpack(z)
        x = with_xi(x, c)
        xd, _ = h.deriv(x, c)
        return np.r_[xd[IU:IR + 1] * np.array([1, 1, 1, 10, 10, 10]), xd[IA1], xd[IB1]]

    z0 = np.array(guess) if guess is not None else np.radians([12, 0, 0, 20, 4, -2, 1, 0])
    z, info, ier, msg = fsolve(res, z0, xtol=1e-13, full_output=True)
    if ier != 1 or np.max(np.abs(res(z))) > 1e-8:
        raise RuntimeError(f"trim failed at ({vn}, {ve}, {vd}): {msg}, res {np.max(np.abs(res(z)))}")
    x, c = unpack(z)
    x = with_xi(x, c)
    return x, c, h.components(x, c)


# --------------------------------------------------------------------------- bg-sim start values
def principal_axes(s: dict):
    """The airframe inertia (report IX, IY, IZ less the drivetrain, IXZ) in the geometric body
    frame B (FLU: the FRD tensor's -Ixz becomes +Ixz) and its principal axes: B = R_y(eps) P."""
    I_b = np.array([[s["IX"], 0.0, s["IXZ"]], [0.0, s["IY"], 0.0], [s["IXZ"], 0.0, s["IZ_AF"]]])
    eps = 0.5 * math.atan2(2.0 * s["IXZ"], s["IZ_AF"] - s["IX"])
    c, sn = math.cos(eps), math.sin(eps)
    R = np.array([[c, 0.0, sn], [0.0, 1.0, 0.0], [-sn, 0.0, c]])
    Jp = R.T @ I_b @ R
    assert abs(Jp[0, 2]) < 1e-9 * s["IZ"]
    return np.array([Jp[0, 0], Jp[1, 1], Jp[2, 2]]), eps, R


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_from_euler_ned(phi, theta, psi):
    """R_WB for the bg-sim world (x north, y west, z up) and body FLU from NED/FRD Euler angles."""
    cphi, sphi = math.cos(phi / 2), math.sin(phi / 2)
    cth, sth = math.cos(theta / 2), math.sin(theta / 2)
    cpsi, spsi = math.cos(psi / 2), math.sin(psi / 2)
    w = cphi * cth * cpsi + sphi * sth * spsi
    x = sphi * cth * cpsi - cphi * sth * spsi
    y = cphi * sth * cpsi + sphi * cth * spsi
    z = cphi * cth * spsi - sphi * sth * cpsi
    return np.array([w, x, -y, -z])


def bg_start(s: dict, x):
    """Free3D pose starts (principal frame) and RigidBody3D momentum start from a state."""
    Jp, eps, R_BP = principal_axes(s)
    q_wb = quat_from_euler_ned(x[IPHI], x[ITH], x[IPSI])
    q_bp = np.array([math.cos(eps / 2), 0.0, math.sin(eps / 2), 0.0])
    q_wp = quat_mul(q_wb, q_bp)
    v_b = np.array([x[IU], -x[IV], -x[IW]])
    w_b = np.array([x[IP], -x[IQ], -x[IR]])
    P = np.concatenate([Jp * (R_BP.T @ w_b), s["m"] * (R_BP.T @ v_b)])
    pose = {"qw": q_wp[0], "qx": q_wp[1], "qy": q_wp[2], "qz": q_wp[3],
            "px": x[IXN], "py": -x[IYE], "pz": -x[IZD]}
    return pose, P


def read_run(run_dir):
    """Time and signal dict of a bg-sim run folder (manifest.json + columns.f64)."""
    import json
    from pathlib import Path
    man = json.load(open(Path(run_dir) / "manifest.json"))
    ids = [sg["id"] for sg in man["signals"]]
    n = man["time"]["n"]
    raw = np.fromfile(Path(run_dir) / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
    return raw[0], {k: raw[i + 1] for i, k in enumerate(ids)}


def simulate(h: Heli, x0, ctrl_fn, t_end, dt=0.01, on_fn=None, breaks=(), rtol=1e-10, atol=1e-10,
             max_step=0.01):
    """Integrate the model (scipy LSODA, restarted at the input steps `breaks`; the report's
    switches act as discontinuities of the right-hand side). ctrl_fn(t, x) -> (theta0, B1, A1,
    theta_tr) rad. Returns t, X on the grid 0, dt, .. t_end."""
    from scipy.integrate import solve_ivp

    seg = [0.0, t_end]

    def f(t, x):
        tc = min(max(t, seg[0] + 1e-9), seg[1] - 1e-9)     # the inputs of this segment, also at its ends
        on = on_fn(tc) if on_fn else 1.0
        return h.deriv(x, ctrl_fn(tc, x), on=on)[0]
    ts = np.linspace(0.0, t_end, int(round(t_end / dt)) + 1)
    edges = [0.0] + sorted(b for b in breaks if 0.0 < b < t_end) + [t_end]
    X = np.zeros((len(ts), len(x0)))
    x = np.array(x0, dtype=float)
    for a, b in zip(edges[:-1], edges[1:]):
        seg[:] = [a, b]
        sel = (ts >= a - 1e-12) & (ts <= b + 1e-12)
        sol = solve_ivp(f, (a, b), x, method="LSODA", t_eval=ts[sel], rtol=rtol, atol=atol, max_step=max_step)
        if not sol.success:
            raise RuntimeError(sol.message)
        X[sel] = sol.y.T
        x = sol.y[:, -1]
    return ts, X
