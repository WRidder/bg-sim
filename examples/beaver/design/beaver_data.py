"""DHC-2 'Beaver' data, transcribed with attribution.

Sources (every value below names one of these):

[FDC]    M. O. Rauw, *Flight Dynamics and Control toolbox* FDC 1.4 beta 3 (2005), the Matlab/Simulink
         toolbox of the 'Beaver' model, https://dutchroll.sourceforge.net/ . Licensed under the Open
         Software License 2.1 (doc/license.txt, doc/copying.txt). The numbers here are transcribed
         from `aircraft/modbuild.m` (the aerodynamic, engine and mass data), the Simulink library
         blocks `aircraft/fdclib1.mdl` (atmosphere), `fdclib3.mdl` (engine power, dpt),
         `fdclib5.mdl` (equations of motion, beta-dot correction) and `apilot/aplib.mdl` (autopilot
         gains), and the trim/linearisation data files `data/cr4520.lin`, `data/cr4560.lin`. No FDC
         code is used: the bg-sim model and the scipy reference are written from the equations.
[REP]    M. O. Rauw, *FDC 1.2 - A Simulink Toolbox for Flight Dynamics and Control Analysis*, 2nd
         ed., 2001 (the FDC user manual; Apple Common Documentation License): chapter 3 (models),
         chapter 11 (the 'Beaver' autopilot, Table 11.3 gains), appendix C (Tables C.1-C.4).
[THESIS] M. O. Rauw, *A Simulink environment for flight dynamics and control analysis -
         application to the DHC-2 'Beaver'*, MSc thesis, Delft University of Technology, 1993,
         parts I and II (NASA NTRS 19950008401): Table 5-1 (trim), Table 5-2 (linear model),
         Table 5-3 (modes).
[TM88]   R. T. H. Tjee and J. A. Mulder, *Stability and control derivatives of the De Havilland
         DHC-2 'Beaver' aircraft*, report LR-556, Delft University of Technology, 1988: the flight-test
         identification behind every aerodynamic and engine coefficient. Not consulted directly
         (repository.tudelft.nl was unreachable); the coefficients come through [FDC] and [REP], which
         both cite it and agree to every digit.

The aerodynamic and engine polynomials were identified from flight tests at 35-55 m/s true
airspeed [FDC modbuild.m, REP Table C.3/C.4]: the model is valid in that range, in the normal
flight envelope (no stall, no ground effect, no ground contact).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- aerodynamics
# [FDC modbuild.m] = [REP Table C.3], valid 35-55 m/s TAS. Body axes x forward, y right, z down.
# CX = CX0 + CXa a + CXa2 a^2 + CXa3 a^3 + CXq qc/V + CXdr dr + CXdf df + CXadf a df
# CY = CY0 + CYb b + CYp pb/2V + CYr rb/2V + CYda da + CYdr dr + CYdra dr a + CYbdot bdot b/2V
# CZ = CZ0 + CZa a + CZa3 a^3 + CZq qc/V + CZde de + CZdeb2 de b^2 + CZdf df + CZadf a df
# Cl = Cl0 + Clb b + Clp pb/2V + Clr rb/2V + Clda da + Cldr dr + Cldaa da a
# Cm = Cm0 + Cma a + Cma2 a^2 + Cmq qc/V + Cmde de + Cmb2 b^2 + Cmr rb/2V + Cmdf df
# Cn = Cn0 + Cnb b + Cnp pb/2V + Cnr rb/2V + Cnda da + Cndr dr + Cnq qc/V + Cnb3 b^3
AERO = {
    "CX0": -0.03554, "CXa": 0.002920, "CXa2": 5.459, "CXa3": -5.162, "CXq": -0.6748,
    "CXdr": 0.03412, "CXdf": -0.09447, "CXadf": 1.106,
    "CY0": -0.002226, "CYb": -0.7678, "CYp": -0.1240, "CYr": 0.3666, "CYda": -0.02956,
    "CYdr": 0.1158, "CYdra": 0.5238, "CYbdot": -0.1600,
    "CZ0": -0.05504, "CZa": -5.578, "CZa3": 3.442, "CZq": -2.988, "CZde": -0.3980,
    "CZdeb2": -15.93, "CZdf": -1.377, "CZadf": -1.261,
    "Cl0": 0.0005910, "Clb": -0.06180, "Clp": -0.5045, "Clr": 0.1695, "Clda": -0.09917,
    "Cldr": 0.006934, "Cldaa": -0.08269,
    "Cm0": 0.09448, "Cma": -0.6028, "Cma2": -2.140, "Cmq": -15.56, "Cmde": -1.921,
    "Cmb2": 0.6921, "Cmr": -0.3118, "Cmdf": 0.4072,
    "Cn0": -0.003117, "Cnb": 0.006719, "Cnp": -0.1585, "Cnr": -0.1112, "Cnda": -0.003872,
    "Cndr": -0.08265, "Cnq": 0.1595, "Cnb3": 0.1373,
}

# --------------------------------------------------------------------------- propulsion
# [FDC modbuild.m] = [REP Table C.4]: the forces and moments of engine operation (slipstream
# included) as polynomials in dpt, the dimensionless total-pressure increase across the propeller.
# CXp = CXdpt dpt + CXadpt2 a dpt^2;  CZp = CZdpt dpt;  Clp = Cla2dpt a^2 dpt;
# Cmp = Cmdpt dpt;  Cnp = Cndpt3 dpt^3;  CYp = 0.
PROP = {"CXdpt": 0.1161, "CXadpt2": 0.1453, "CZdpt": -0.1563, "Cla2dpt": -0.01406,
        "Cmdpt": -0.07895, "Cndpt3": -0.003026}
# dpt = C1 + C2 P / (rho V^3 / 2), P in kW [FDC fdclib3.mdl 'dpt', REP eq. 3.14, Table C.4].
DPT_C1 = 0.08696
DPT_C2 = 191.18
# P = 0.7355 (-326.5 + 0.00412 (pz + 7.4)(n + 2010) + (408.0 - 0.0965 n)(1 - rho/1.225)) kW,
# pz manifold pressure in inches of mercury, n engine speed in rpm [FDC fdclib3.mdl 'P', REP eq. 3.15].
POWER = {"k": 0.7355, "c0": -326.5, "c1": 0.00412, "pz0": 7.4, "n0": 2010.0, "c2": 408.0,
         "c3": 0.0965, "rho0": 1.225}

# --------------------------------------------------------------------------- mass and geometry
# [FDC modbuild.m] = [REP Table C.2]. Inertia in the body axes (FRD) of the flight-test CG
# (x 0.5996 m, z -0.8851 m in the manufacturer's frame [REP Table C.2]): the aerodynamic moments
# are about this CG, so the model's CG is fixed there.
MASS = 2288.231          # kg
IX, IY, IZ = 5368.39, 6928.93, 11158.75   # kg m^2
JXZ = 117.64             # kg m^2 (Jxy = Jyz = 0)
CBAR = 1.5875            # m, mean aerodynamic chord
SPAN = 14.63             # m
S_WING = 23.23           # m^2

# --------------------------------------------------------------------------- atmosphere
# [FDC fdclib1.mdl]: ISA troposphere with the local gravity in the pressure exponent.
#   T = 288.15 - 0.0065 H;  g = 9.80665 (6371020/(6371020 + H))^2
#   ps = 101325 (T/288.15)^(g/1.86584);  rho = ps/(287.053 T)
ATMO = {"T0": 288.15, "lapse": 0.0065, "g0": 9.80665, "Re": 6371020.0, "p0": 101325.0,
        "Rl": 1.86584, "Rgas": 287.053}

# --------------------------------------------------------------------------- reference results
# [THESIS Table 5-1] (= [FDC data/cr4560.lin], full precision): steady wings-level flight at
# V = 45 m/s, H = 6000 ft, flaps 0, n = 1800 rpm. xinco = [V a b p q r psi theta phi xe ye H].
TRIM_6000 = {"V": 45.0, "H": 1828.8, "n": 1800.0, "df": 0.0,
             "alpha": 0.14438875961, "beta": -0.014713301158, "theta": 0.14438875961,
             "de": -0.0425220828, "da": 0.0091414485, "dr": -0.045971379, "pz": 21.0716255573,
             "thesis": {"alpha": 0.1444, "beta": -0.0147, "theta": 0.1444, "de": -0.0425,
                        "da": 0.0091, "dr": -0.0460, "pz": 21.072}}
# [FDC data/cr4520.lin]: the same flight condition at 2000 ft.
TRIM_2000 = {"V": 45.0, "H": 609.6, "n": 1800.0, "df": 0.0,
             "alpha": 0.12602765888, "beta": -0.013705601171, "theta": 0.12602765888,
             "de": -0.028995591, "da": 0.0092863586, "dr": -0.044154414, "pz": 22.6574913595}
# [THESIS Table 5-3]: modes of the decoupled linear models at the 6000 ft point.
MODES_THESIS = {"phugoid": complex(-0.01614, 0.2631), "short_period": complex(-2.1606, 2.4112),
                "dutch_roll": complex(-0.4770, 0.9763), "roll": -5.1351, "spiral": -0.04573}

# --------------------------------------------------------------------------- autopilot
# [FDC apilot/aplib.mdl] = [REP Table 11.3, 11.2]: gains scheduled on the true airspeed V (m/s).
# FDC 1.4 works in radians with 1 V of actuator command = 1 deg of deflection, so the 'Volt'
# gains of the report are rad/rad here. Signs as in the Simulink library.
AP = {
    # PAH: de = Ktheta (theta_ref - theta) + Ki int(.) - Kq q_c    (rad, 1 V = 1 deg)
    "Ktheta": (-1.375e-3, 0.1575, -4.8031),     # a V^2 + b V + c
    "Kq": (-4.75e-4, 0.0540, -1.5931),          # s
    "Ki_pah": 0.5,                              # 1/s
    "dtheta_lim": (-8.0, 18.0),                 # deg, limiter on theta_ref - theta... (see build)
    "theta_ref_lim": (-20.0, 20.0),             # deg
    "pah_int_lim": 2.0,                         # deg (+-2 V)
    "pah_out_lim": 10.0,                        # deg (+-10 V)
    # turn compensation added to the measured q: r tan(phi) + Ktc'(1/cos(phi + dphi) - 1)
    "Ktc_pah": (5.0e-4, -0.03, 0.9375),         # a V^2 + b V + c, rad/s; dphi = 0
    "Ktc_alh": (0.03, 0.25),                    # a V + b, rad/s; dphi = 0.03491 rad (2 deg)
    "dphi_alh": 0.03491,
    # ALH: theta_ref = KH (H_ref - H) - washout(theta), washout = s/(s + Kd)
    "KH": (-1.0e-4, 0.015, -0.5975),            # deg/m -> times pi/180
    "Kd": (-2.5e-3, 0.2875),                    # 1/s
    # RAH: da = Kphi (phi_ref - phi) + Ki int(.) + turn coordinator
    "Kphi": (9.75e-4, -0.108, 2.335625),
    "Ki_rah": 0.25,
    "Kr": -4.0,                                 # times g/V on the rudder channel
    "dar": 0.165,                               # s, aileron per yaw rate
    "drr": (-7.5e-5, 0.0095, -0.4606),          # s, rudder per yaw rate (FDC: drr - Kr, see build)
    "dphi_lim": 30.0,                           # deg, roll command limit
    "rah_err_lim": 3.75,                        # deg (+-3.75 V) on Kphi (phi_ref - phi)
    "rah_int_lim": 1.0,                         # deg (+-1 V)
    # HH: phi_ref = Kpsi (psi_ref - psi)
    "Kpsi": (0.05, -1.1),
}
