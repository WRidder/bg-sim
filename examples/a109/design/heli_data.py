"""The data of the Heffley & Mnich minimum-complexity helicopter model, in the report's units.

R. K. Heffley and M. A. Mnich, "Minimum-Complexity Helicopter Simulation Math Model",
NASA CR-177476 / USAAVSCOM TR 87-A-7, April 1988 (https://ntrs.nasa.gov/citations/19880020435).

Units are the report's: ft, slug, lb, rad, rpm; stations (FS, WL) in inches. Every value carries
the place in the report it comes from.

* `A109` is the Agusta A109 II data file of Appendix D (p. D-19, "HEL302.DAT", the file after the
  model matching: IX reduced to 1300, IXZ raised to 800, K1 = 0) together with the A109 revisions
  of the listings (pp. D-20 .. D-24): decoupled first-order flapping (ITB = GAM.OM.16,
  ITB2.OM = 0), the low-speed dihedral magnification (WAKE.FN below VTRANS), the fuselage downwash
  centre of pressure magnified 3x (D.FW = 3 D.FW), the tail downwash edge shifted 1 ft (D.DW + 1).
* `AH1S` is the Bell AH-1S data file of Appendix C (p. C-1) with the base listing of Appendix A
  (coupled flapping, no A109 revisions). It is used to check the reference implementation
  against the report's own numbers (the hover trim printout, Fig. 12 / p. 47, and the state
  transition table, Table 7 / p. 49).

Constants that the listing uses but does not print (GRAV, RHO.SEA.LEVEL) are the standard values.
"""

from __future__ import annotations

GRAV = 32.174            # ft/s^2 (standard; not printed in the report)
RHO_SL = 0.002377        # slug/ft^3 (standard sea level; not printed in the report)
FPS_PER_KNOT = 1.6878099 # ft/s per kt
HP = 550.0               # ft lb/s per hp

A109 = {
    "name": "A109 II",
    "variant": "a109",           # the Appendix D revisions of the listing
    # (CONFIGURATION, AIRCRAFT NAME, FS.CG, WL.CG, WT, IX, IY, IZ, IXZ), p. D-19
    "FS_CG": 132.7, "WL_CG": 38.5, "WT": 5401.0,
    "IX": 1300.0, "IY": 6760.0, "IZ": 6407.0, "IXZ": 800.0,
    # (FS.HUB, WL.HUB, IS, E.MR, I.B, R.MR, A.MR, RPM.MR, CDO, B.MR, C.MR, TWST.MR, K1), p. D-19
    "FS_HUB": 132.4, "WL_HUB": 98.2, "IS": 0.11, "E_MR": 0.50, "I_B": 212.0, "R_MR": 18.0,
    "A_MR": 6.0, "RPM_MR": 385.0, "CDO": 0.010, "B_MR": 4, "C_MR": 1.10, "TWST_MR": -0.105, "K1": 0.0,
    # (FS.FUS, WL.FUS, XUU.FUS, YVV.FUS, ZWW.FUS), p. D-19
    "FS_FUS": 132.0, "WL_FUS": 38.0, "XUU_FUS": -10.8, "YVV_FUS": -167.0, "ZWW_FUS": -85.0,
    # (FS.WN, WL.WN, ZUU.WN, ZUW.WN, ZMAX.WN, B.WN), p. D-19: no wing (B.WN = 1 avoids a division by zero)
    "FS_WN": 0.0, "WL_WN": 0.0, "ZUU_WN": 0.0, "ZUW_WN": 0.0, "ZMAX_WN": 0.0, "B_WN": 1.0,
    # (FS.HT, WL.HT, ZUU.HT, ZUW.HT, ZMAX.HT), p. D-19
    "FS_HT": 330.0, "WL_HT": 54.0, "ZUU_HT": 0.4, "ZUW_HT": -34.0, "ZMAX_HT": -22.0,
    # (FS.VT, WL.VT, YUU.VT, YUV.VT, YMAX.VT), p. D-19
    "FS_VT": 380.0, "WL_VT": 80.0, "YUU_VT": 3.3, "YUV_VT": -47.0, "YMAX_VT": -17.0,
    # (FS.TR, WL.TR, R.TR, A.TR, SOL.TR, RPM.TR, TWST.TR), p. D-19 (A.TR halved from 6 in the matching, p. D-6)
    "FS_TR": 391.0, "WL_TR": 70.0, "R_TR": 3.1, "A_TR": 3.0, "SOL_TR": 0.134, "RPM_TR": 2080.0, "TWST_TR": -0.137,
    # Preliminary calculations, p. D-20
    "HP_LOSS": 90.0,     # hp, transmission, accessories (line 1630)
    "VTRANS": 50.0,      # ft/s, end of the low-speed dihedral magnification (line 1640; "30 kt", p. D-7)
}

AH1S = {
    "name": "AH-1S",
    "variant": "base",           # the Appendix A listing
    # Appendix C, p. C-1
    "FS_CG": 196.0, "WL_CG": 75.0, "WT": 9000.0,
    "IX": 2593.0, "IY": 14320.0, "IZ": 12330.0, "IXZ": 0.0,
    "FS_HUB": 200.0, "WL_HUB": 153.0, "IS": 0.0, "E_MR": 0.0, "I_B": 1382.0, "R_MR": 22.0,
    "A_MR": 6.0, "RPM_MR": 324.0, "CDO": 0.010, "B_MR": 2, "C_MR": 2.25, "TWST_MR": -0.175, "K1": 0.0,
    "FS_FUS": 200.0, "WL_FUS": 65.0, "XUU_FUS": -30.0, "YVV_FUS": -275.0, "ZWW_FUS": -41.0,
    "FS_WN": 200.0, "WL_WN": 65.0, "ZUU_WN": -39.0, "ZUW_WN": -161.0, "ZMAX_WN": -65.0, "B_WN": 10.75,
    "FS_HT": 400.0, "WL_HT": 65.0, "ZUU_HT": 0.0, "ZUW_HT": -80.0, "ZMAX_HT": -32.0,
    "FS_VT": 490.0, "WL_VT": 80.0, "YUU_VT": 0.0, "YUV_VT": -62.0, "YMAX_VT": -50.0,
    "FS_TR": 521.5, "WL_TR": 119.0, "R_TR": 4.25, "A_TR": 6.0, "SOL_TR": 0.105, "RPM_TR": 1660.0, "TWST_TR": 0.0,
    "HP_LOSS": 90.0,     # Appendix A, line 1630
    "VTRANS": 50.0,      # set (line 1640) but not used by the Appendix A listing
}

# The report's hover trim printout for the AH-1S (Fig. 12, p. 47; configuration 102, 05-25-1987).
AH1S_HOVER_PRINTOUT = {
    "theta0_deg": 15.7, "a1_deg": 1.3, "b1_deg": -2.1, "theta_tr_deg": 10.2, "theta_deg": -1.3,
    "phi_deg": -1.02, "B1_deg": -1.30, "A1_deg": -2.05, "hp": 973.0, "thrust_lb": 9256.0,
    "thrust_tr_lb": 618.0, "vi_fps": 35.8, "vi_tr_fps": 47.9, "torque_ftlb": 1.34e4,
}
# Table 7 (p. 49): AH-1S in hover, a 1 deg step of the lateral cyclic DC(3), ST = 0.025 s
# (second-order Adams-Bashforth). Trim controls of the run, deg: DC(1..4).
AH1S_TABLE7_CONTROLS_DEG = (15.6852, -1.0532, -1.2974, 10.1515)
# time (s), VB(1) u, VB(2) v (ft/s), VB(4) p, VB(5) q, VB(6) r (deg/s)
AH1S_TABLE7 = [
    (0.000, 0.000, 0.000, 0.000, 0.000, 0.000),
    (0.025, -0.002, 0.002, 0.141, 0.003, 0.000),
    (0.050, -0.006, 0.008, 0.455, 0.016, 0.000),
    (0.075, -0.009, 0.017, 0.868, 0.031, 0.001),
    (0.100, -0.013, 0.028, 1.341, 0.046, 0.002),
    (0.125, -0.017, 0.039, 1.847, 0.058, 0.003),
    (0.150, -0.020, 0.052, 2.364, 0.067, 0.005),
    (0.175, -0.022, 0.066, 2.880, 0.074, 0.007),
]

# The A109 trim curves of Appendix D (pp. D-9 .. D-14): the report's "Fitted Model" line, read
# off the scanned charts (TAS in kt, + forward / + right; reading accuracy about +-0.3 deg,
# +-1.5 % and +-10 shp). G.W. 2450 kg; the charts name the helicopter "A109K, S/N 7310".
FITTED = {
    "pitch_deg": [(-30, 2.2), (-20, 2.3), (-10, 4.5), (0, 5.0), (10, 5.1), (20, 4.9), (30, 4.5), (40, 4.0),
                  (50, 3.3), (60, 2.6), (70, 2.0), (80, 1.4), (90, 0.8), (100, 0.3)],
    "roll_deg": [(-30, -2.9), (-20, -2.8), (-10, -2.6), (0, -2.2), (10, -1.7), (20, -1.3), (30, -1.3),
                 (40, -1.0), (60, -0.9), (80, -0.8), (100, -0.8)],
    "power_shp": [(-40, 440), (-30, 480), (-20, 545), (-10, 610), (0, 640), (10, 610), (20, 545), (30, 480),
                  (40, 435), (50, 410), (60, 400), (70, 402), (80, 415), (90, 435), (100, 460), (110, 500),
                  (120, 550)],
    "lon_pct": [(-30, 17), (-20, 24), (-10, 36), (0, 45), (10, 50), (20, 53), (40, 47), (50, 46.5), (60, 47),
                (70, 49), (80, 51), (90, 52.5), (100, 53.5)],
    "lat_pct": [(-30, 60), (-20, 57), (-10, 52), (0, 46), (10, 43), (20, 41), (30, 45.5), (40, 44.5),
                (60, 43), (80, 41), (100, 36)],
    "coll_pct": [(-40, 45), (-30, 49), (-20, 54), (-10, 58.5), (0, 60.5), (10, 59), (20, 55), (30, 49),
                 (40, 45), (50, 42), (60, 40.5), (70, 40.5), (80, 41.5), (90, 43), (100, 45), (110, 48),
                 (120, 50.5)],
    "ped_pct": [(-40, 36), (-30, 43), (-20, 51), (-10, 57), (0, 61), (10, 59), (20, 51), (30, 43), (40, 37),
                (50, 34.5), (60, 33), (70, 31.5), (80, 29.5), (90, 28), (100, 27.5), (110, 27), (120, 27.5)],
}
# Sideward flight (p. D-13, D-14), fitted model; + right.
FITTED_SIDE = {
    "pitch_deg": [(-20, 4.3), (-10, 5.0), (0, 5.2), (10, 5.4), (20, 5.5)],
    "roll_deg": [(-20, -4.6), (-10, -3.6), (0, -2.3), (10, -0.9), (20, 0.6)],
    "lon_pct": [(-20, 41), (-10, 44), (0, 46), (10, 47), (20, 47)],
    "lat_pct": [(-20, 37), (-10, 41), (0, 46), (10, 52), (20, 58)],
    "ped_pct": [(-20, 47), (-10, 56), (0, 61), (10, 66), (20, 71)],
    "coll_pct": [(-20, 54), (-10, 58), (0, 60), (10, 59), (20, 54)],
}
# Flight-test points of the forward-flight power chart (p. D-12), CG 3.370 m (circles), for orientation.
FLIGHT_POWER = [(-30, 425), (-20, 520), (-10, 620), (0, 650), (20, 545), (30, 465), (35, 395), (45, 390),
                (55, 325), (58, 352), (67, 380), (79, 395), (87, 393), (95, 425)]
