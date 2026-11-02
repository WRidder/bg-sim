"""The Heffley & Mnich dynamics subroutine in the report's units (ft, slug, lb, rad): the reference.

A line-by-line transcription of the BASIC listings (Appendix A, and the A109 revisions of
Appendix D, pp. D-20 .. D-24), independent of the bg-sim model. Body axes are the report's: x
forward, y right, z down (FRD); D.* are positive aft of the CG, H.* positive above it.

Two things are not taken literally, both flagged in the README:

* The thrust / induced-velocity recursion (5 passes per frame, started from the previous frame's
  value) is solved to convergence here; at a trim the report's recursion converges to the same
  value.
* `rigid_body="report"` uses the report's simplified body equations (no gyroscopic terms in roll,
  Ixz only partly coupled); `rigid_body="full"` (the default) the complete Newton-Euler equations
  of a rigid body with Ixz, which is what the bg-sim spatial rigid body integrates. Trims (zero
  rates) are the same with both.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from heli_data import GRAV, HP, RHO_SL

# State vector (14): u v w p q r (body, FRD) phi theta psi (Euler) xn ye zd (earth, NED) a1 b1
IU, IV, IW, IP, IQ, IR, IPHI, ITH, IPSI, IXN, IYE, IZD, IA1, IB1 = range(14)


def sgn(x):
    return (x > 0) - (x < 0)


class Heli:
    def __init__(self, d: dict, rigid_body: str = "full", rho: float = RHO_SL):
        self.d = d
        self.rigid_body = rigid_body
        self.a109 = d["variant"] == "a109"
        self.rho = rho
        self.r2 = rho / 2.0
        self.m = d["WT"] / GRAV
        self.omega0 = d["RPM_MR"] * 2 * math.pi / 60
        self.omega_tr0 = d["RPM_TR"] * 2 * math.pi / 60
        self.prelim(self.omega0)
        # geometry (ft): D positive aft of the CG, H positive above it (lines 1730 .. 1780)
        cg_fs, cg_wl = d["FS_CG"], d["WL_CG"]
        for k in ("HUB", "FUS", "WN", "HT", "VT", "TR"):
            setattr(self, "h_" + k.lower(), (d["WL_" + k] - cg_wl) / 12.0)
            setattr(self, "d_" + k.lower(), (d["FS_" + k] - cg_fs) / 12.0)

    def prelim(self, omega):
        """Preliminary calculations (lines 1580 .. 1700). The flapping constants depend on the rotor
        speed; CT and the dihedral derivative are the report's constants at the nominal speed."""
        d = self.d
        R, e = d["R_MR"], d["E_MR"]
        self.vtip0 = R * self.omega0
        self.fr_mr = d["CDO"] * R * d["B_MR"] * d["C_MR"]
        gam16 = self.rho * d["A_MR"] * d["C_MR"] * R ** 4 / d["I_B"] * omega / 16 * (1 + 8 / 3 * e / R)
        self.gam16 = gam16
        self.kc = 0.75 * omega * e / R / gam16 + d["K1"]
        if self.a109:     # line 1693: decoupled first-order flapping
            self.itb2 = 0.0
            self.itb = gam16
        else:
            self.itb2 = omega / (1 + (omega / gam16) ** 2)
            self.itb = self.itb2 * omega / gam16
        self.dl_db1 = d["B_MR"] / 2 * (1.5 * d["I_B"] * e / R * omega * omega)
        self.dl_da1 = 0.0      # line 1696 is commented out (DL.DA1 = 0)
        ct = d["WT"] / (self.rho * math.pi * R * R * self.vtip0 * self.vtip0)
        a_sigma = d["A_MR"] * d["B_MR"] * d["C_MR"] / R / math.pi
        self.db1dv = 2 / self.omega0 / R * (8 * ct / a_sigma + math.sqrt(ct / 2))
        self.da1du = -self.db1dv
        self.ct = ct

    # ------------------------------------------------------------------ inflow
    @staticmethod
    def _inflow(k_t, rho_a, wb, wr, u2, guess=None):
        """Converged solution of T = (WB - vi) k_t, vi^2 = sqrt((vh^2/2)^2 + (T/(2 rho A))^2) - vh^2/2,
        vh^2 = u^2 + v^2 + WR (WR - 2 vi) (lines 6540 .. 6610)."""
        def g(vi):
            t = (wb - vi) * k_t
            vh2 = u2 + wr * (wr - 2 * vi)
            vi2 = math.sqrt((vh2 / 2) ** 2 + (t / (2 * rho_a)) ** 2) - vh2 / 2
            return math.sqrt(abs(vi2))
        f = lambda vi: g(vi) - vi
        hi = 10.0
        while f(hi) > 0:
            hi *= 2
        vi = brentq(f, 0.0, hi, xtol=1e-14, rtol=1e-15, maxiter=500)
        return vi, (wb - vi) * k_t

    # ------------------------------------------------------------------ the dynamics subroutine
    def components(self, x, c, omega=None, omega_tr=None, hdot=None):
        """Forces and moments (lb, ft lb, body FRD about the CG) and every intermediate value.
        c = (theta0, B1, A1, theta_tr) in rad: DC(1..4)."""
        d = self.d
        om = self.omega0 if omega is None else omega
        omt = self.omega_tr0 if omega_tr is None else omega_tr
        if omega is not None:
            self.prelim(om)
        u, v, w, p, q, r = x[IU], x[IV], x[IW], x[IP], x[IQ], x[IR]
        phi, th = x[IPHI], x[ITH]
        a1, b1 = x[IA1], x[IB1]
        th0, B1, A1, thtr = c
        R = d["R_MR"]
        r2, rho = self.r2, self.rho
        o = {}
        # ---- rotor tip-path-plane dynamics (lines 6341 .. 6360)
        wake = 1.0 if (self.a109 and u < d["VTRANS"]) else 0.0
        a_sum = b1 - A1 + self.kc * a1 + self.db1dv * v * (1 + wake)
        b_sum = a1 + B1 - self.kc * b1 + self.da1du * u * (1 + 2 * wake)
        o["a1dot"] = -self.itb * b_sum - self.itb2 * a_sum - q
        o["b1dot"] = -self.itb * a_sum + self.itb2 * b_sum - p
        o["wake"] = wake
        # ---- main rotor thrust and induced velocity (lines 6490 .. 6610)
        wr = w + (a1 - d["IS"]) * u - b1 * v
        wb = wr + 2 / 3 * om * R * (th0 + 0.75 * d["TWST_MR"])
        k_t = om * R * rho * d["A_MR"] * d["B_MR"] * d["C_MR"] * R / 4
        vi, T = self._inflow(k_t, rho * math.pi * R * R, wb, wr, u * u + v * v)
        o.update(wr=wr, wb=wb, vi=vi, T=T)
        # ---- fuselage (lines 6650 .. 6720)
        wa_fus = w - vi
        d_fw = (u / (-wa_fus)) * (self.h_hub - self.h_fus) - (self.d_fus - self.d_hub)
        if self.a109:
            d_fw = 3 * d_fw
        x_fus = r2 * d["XUU_FUS"] * abs(u) * u
        y_fus = r2 * d["YVV_FUS"] * abs(v) * v
        z_fus = r2 * d["ZWW_FUS"] * abs(wa_fus) * wa_fus
        l_fus = y_fus * self.h_fus
        m_fus = z_fus * d_fw - x_fus * self.h_fus
        o.update(x_fus=x_fus, y_fus=y_fus, z_fus=z_fus, l_fus=l_fus, m_fus=m_fus, d_fw=d_fw, wa_fus=wa_fus)
        # ---- power and torque (lines 6780 .. 6850)
        if hdot is None:
            hdot = climb_rate(x)
        p_ind = T * vi
        p_climb = d["WT"] * hdot
        p_para = -x_fus * u - y_fus * v - z_fus * wa_fus
        p_prof = r2 * (self.fr_mr / 4) * om * R * (om * om * R * R + 4.6 * (u * u + v * v))
        power_mr = p_ind + p_climb + p_para + p_prof
        torque = power_mr / om
        o.update(p_ind=p_ind, p_climb=p_climb, p_para=p_para, p_prof=p_prof, power_mr=power_mr, torque=torque)
        # ---- main rotor forces and moments (lines 6890 .. 6980)
        x_mr = -T * (a1 - d["IS"])
        y_mr = T * b1
        z_mr = -T
        l_mr = y_mr * self.h_hub + self.dl_db1 * b1 + self.dl_da1 * (a1 + A1 - d["K1"] * b1)
        m_mr = z_mr * self.d_hub - x_mr * self.h_hub + self.dl_db1 * a1 + self.dl_da1 * (-b1 + B1 - d["K1"] * a1)
        n_mr = torque
        o.update(x_mr=x_mr, y_mr=y_mr, z_mr=z_mr, l_mr=l_mr, m_mr=m_mr, n_mr=n_mr)
        # ---- tail rotor (lines 7060 .. 7330)
        Rt = d["R_TR"]
        vr_tr = -(v - r * self.d_tr + p * self.h_tr)
        vb_tr = vr_tr + 2 / 3 * omt * Rt * (thtr + 0.75 * d["TWST_TR"])
        k_tt = omt * Rt * rho * d["A_TR"] * d["SOL_TR"] * math.pi * Rt * Rt / 4
        vi_tr, T_tr = self._inflow(k_tt, rho * math.pi * Rt * Rt, vb_tr, vr_tr, (w + q * self.d_tr) ** 2 + u * u)
        p_tr = T_tr * vi_tr
        y_tr = T_tr
        l_tr = y_tr * self.h_tr
        n_tr = -y_tr * self.d_tr
        o.update(vi_tr=vi_tr, T_tr=T_tr, p_tr=p_tr, y_tr=y_tr, l_tr=l_tr, n_tr=n_tr, vr_tr=vr_tr)
        # ---- horizontal tail (lines 7410 .. 7560)
        d_dw = (u / (vi - w)) * (self.h_hub - self.h_ht) - (self.d_ht - self.d_hub - R)
        if self.a109:
            d_dw = d_dw + 1
        eps = 2 * (1 - d_dw / R) if (0 < d_dw < R) else 0.0
        wa_ht = w - eps * vi + self.d_ht * q
        vta_ht = math.sqrt(u * u + v * v + wa_ht * wa_ht)
        z_ht = r2 * (d["ZUU_HT"] * abs(u) * u + d["ZUW_HT"] * abs(u) * wa_ht)
        ht_stall = abs(wa_ht) > 0.3 * abs(u)
        if ht_stall:
            z_ht = r2 * d["ZMAX_HT"] * abs(vta_ht) * wa_ht
        m_ht = z_ht * self.d_ht
        o.update(eps_ht=eps, d_dw=d_dw, wa_ht=wa_ht, z_ht=z_ht, m_ht=m_ht, ht_stall=ht_stall)
        # ---- wing (lines 7640 .. 7840); the induced drag divides by B.WN^2 (see the README)
        wa_wn = w - vi
        vta_wn = math.sqrt(u * u + wa_wn * wa_wn)
        lift_q = d["ZUU_WN"] * u * u + d["ZUW_WN"] * u * wa_wn
        z_wn = r2 * lift_q
        x_wn = -r2 / math.pi / (vta_wn * vta_wn) * lift_q ** 2 / d["B_WN"] ** 2 if vta_wn > 0 else 0.0
        if abs(wa_wn) > 0.3 * abs(u):
            z_wn = r2 * d["ZMAX_WN"] * abs(vta_wn) * wa_wn
        p_wn = abs(x_wn * u)
        o.update(x_wn=x_wn, z_wn=z_wn, p_wn=p_wn)
        # ---- vertical tail (lines 7895 .. 8010)
        va_vt = v + vi_tr - self.d_vt * r
        vta_vt = math.sqrt(u * u + va_vt * va_vt)
        y_vt = r2 * (d["YUU_VT"] * abs(u) * u + d["YUV_VT"] * abs(u) * va_vt)
        vt_stall = abs(va_vt) > 0.3 * abs(u)
        if vt_stall:
            y_vt = r2 * d["YMAX_VT"] * abs(vta_vt) * va_vt
        l_vt = y_vt * self.h_vt
        n_vt = -y_vt * self.d_vt
        o.update(va_vt=va_vt, y_vt=y_vt, l_vt=l_vt, n_vt=n_vt, vt_stall=vt_stall)
        # ---- totals (lines 8050 .. 8180)
        mg = self.m * GRAV
        X = -mg * math.sin(th) + x_mr + x_fus + x_wn
        Y = mg * math.sin(phi) * math.cos(th) + y_mr + y_fus + y_tr + y_vt
        Z = mg * math.cos(th) * math.cos(phi) + z_mr + z_fus + z_ht + z_wn
        L = l_mr + l_fus + l_tr + l_vt
        M = m_mr + m_fus + m_ht
        N = n_mr + n_tr + n_vt
        power = power_mr + p_tr + p_wn + d["HP_LOSS"] * HP
        o.update(X=X, Y=Y, Z=Z, L=L, M=M, N=N, power=power, hp=power / HP)
        return o

    def deriv(self, x, c, **kw):
        o = self.components(x, c, **kw)
        return self.rigid(x, o), o

    def rigid(self, x, o):
        d = self.d
        u, v, w, p, q, r = x[IU:IR + 1]
        phi, th, psi = x[IPHI], x[ITH], x[IPSI]
        m = self.m
        Ix, Iy, Iz, Ixz = d["IX"], d["IY"], d["IZ"], d["IXZ"]
        xd = np.zeros(14)
        xd[IU] = -(q * w - r * v) + o["X"] / m
        xd[IV] = (p * w - u * r) + o["Y"] / m
        xd[IW] = (u * q - p * v) + o["Z"] / m
        L, M, N = o["L"], o["M"], o["N"]
        if self.rigid_body == "report":       # lines 8320 .. 8370
            pd = L / Ix
            qd = M / Iy - p * r * (Ix - Iz) / Iy + (r * r - p * p) * Ixz / Iy
            rd = N / Iz + Ixz * pd / Iz
        else:                                 # Newton-Euler with Ixz (FRD)
            gam = Ix * Iz - Ixz * Ixz
            Lt = L + Ixz * p * q - (Iz - Iy) * q * r
            Nt = N - Ixz * q * r - (Iy - Ix) * p * q
            pd = (Iz * Lt + Ixz * Nt) / gam
            rd = (Ixz * Lt + Ix * Nt) / gam
            qd = (M - (Ix - Iz) * p * r - Ixz * (p * p - r * r)) / Iy
        xd[IP], xd[IQ], xd[IR] = pd, qd, rd
        cf, sf, ct, st = math.cos(phi), math.sin(phi), math.cos(th), math.sin(th)
        xd[IPHI] = p + (q * sf + r * cf) * st / ct
        xd[ITH] = q * cf - r * sf
        xd[IPSI] = (q * sf + r * cf) / ct
        Rm = dcm(phi, th, psi)
        xd[IXN:IZD + 1] = Rm @ np.array([u, v, w])
        xd[IA1] = o["a1dot"]
        xd[IB1] = o["b1dot"]
        return xd


def dcm(phi, th, psi):
    """Body (FRD) to earth (NED)."""
    cf, sf, ct, st, cp, sp = math.cos(phi), math.sin(phi), math.cos(th), math.sin(th), math.cos(psi), math.sin(psi)
    return np.array([[ct * cp, sf * st * cp - cf * sp, cf * st * cp + sf * sp],
                     [ct * sp, sf * st * sp + cf * cp, cf * st * sp - sf * cp],
                     [-st, sf * ct, cf * ct]])


def climb_rate(x):
    """Rate of climb (ft/s, up) from the body velocity and attitude."""
    u, v, w = x[IU], x[IV], x[IW]
    phi, th = x[IPHI], x[ITH]
    return u * math.sin(th) - v * math.sin(phi) * math.cos(th) - w * math.cos(phi) * math.cos(th)


def body_velocity(vn, ve, vd, phi, th, psi=0.0):
    return dcm(phi, th, psi).T @ np.array([vn, ve, vd])


def trim(h: Heli, vn=0.0, ve=0.0, vd=0.0, psi=0.0, guess=None, **kw):
    """Steady straight flight with the earth velocity (vn, ve, vd) (ft/s, NED) at heading psi:
    solve the 8 unknowns (theta0, B1, A1, theta_tr, theta, phi, a1, b1) so that the 8 rates
    (u v w p q r a1 b1) vanish. Returns (x, c, outputs)."""
    from scipy.optimize import fsolve

    def unpack(z):
        c = z[0:4]
        th, phi, a1, b1 = z[4:8]
        x = np.zeros(14)
        x[IU:IW + 1] = body_velocity(vn, ve, vd, phi, th, psi)
        x[IPHI], x[ITH], x[IPSI], x[IA1], x[IB1] = phi, th, psi, a1, b1
        return x, c

    def res(z):
        x, c = unpack(z)
        xd, _ = h.deriv(x, c, **kw)
        return np.r_[xd[IU:IR + 1] * np.array([1, 1, 1, 10, 10, 10]), xd[IA1], xd[IB1]]

    z0 = np.array(guess) if guess is not None else np.radians([12, 0, 0, 10, 3, -2, 0, 0])
    z, info, ier, msg = fsolve(res, z0, xtol=1e-13, full_output=True)
    if ier != 1 or np.max(np.abs(res(z))) > 1e-7:
        raise RuntimeError(f"trim failed at ({vn}, {ve}, {vd}): {msg}, res {np.max(np.abs(res(z)))}")
    x, c = unpack(z)
    return x, np.array(c), h.components(x, c, **kw)


def simulate_report(h: Heli, x0, controls, n, st=0.025):
    """The report's discrete-time integration (lines 6340 .. 8690): flapping first by the
    trapezoid of the current and past rates (A2 = B2 = 0.5), then the forces with the updated
    flapping, the body velocities by second-order Adams-Bashforth (A1 = 1.5, B1 = -0.5) and the
    earth positions and Euler angles by the trapezoid. Past values start at zero (a trim).
    controls(t) -> (theta0, B1, A1, theta_tr) rad. Returns the list of states at t = 0, st, .."""
    x = np.array(x0, dtype=float)
    gp = np.zeros(2)          # past flapping rates
    ap = np.zeros(6)          # past body accelerations
    vp = np.zeros(6)          # past earth rates (xn ye zd phi theta psi)
    out = [x.copy()]
    for k in range(n):
        t = k * st
        c = controls(t)
        o = h.components(x, c)
        gr = np.array([o["a1dot"], o["b1dot"]])
        x[IA1] += st * (0.5 * gr[0] + 0.5 * gp[0])
        x[IB1] += st * (0.5 * gr[1] + 0.5 * gp[1])
        gp = gr
        o = h.components(x, c)
        xd = h.rigid(x, o)
        ab = xd[IU:IR + 1]
        x[IU:IR + 1] += st * (1.5 * ab - 0.5 * ap)
        ap = ab
        xd = h.rigid(x, o)     # earth rates with the updated body velocities
        ve = np.r_[xd[IXN:IZD + 1], xd[IPHI:IPSI + 1]]
        x[IXN:IZD + 1] += st * (0.5 * ve[0:3] + 0.5 * vp[0:3])
        x[IPHI:IPSI + 1] += st * (0.5 * ve[3:6] + 0.5 * vp[3:6])
        vp = ve
        out.append(x.copy())
    return out
