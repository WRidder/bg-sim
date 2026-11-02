"""The NREL 5 MW reference wind turbine: the published properties the example uses.

Source: J. Jonkman, S. Butterfield, W. Musial and G. Scott, "Definition of a 5-MW Reference Wind
Turbine for Offshore System Development", NREL/TP-500-38060, National Renewable Energy
Laboratory, Golden, CO, February 2009 (public, https://www.nrel.gov/docs/fy09osti/38060.pdf).
Section numbers below refer to that report.

The airfoil polars in `airfoils/*.csv` are the report's AeroDyn tables (Appendix B), taken from the
OpenFAST regression-test repository (github.com/OpenFAST/r-test, `5MW_Baseline/Airfoils`,
Apache-2.0), converted to CSV (alpha, cl, cd) without changing a number.
"""

from __future__ import annotations

import math

RPM = 2.0 * math.pi / 60.0

# --------------------------------------------------------------------------- Table 1-1, chapters 2-6
RHO = 1.225                 # kg/m^3, the report's air density (sections 3 and 9)
B = 3                       # blades
R_TIP = 63.0                # m (126 m diameter)
R_HUB = 1.5                 # m (3 m hub diameter)
HUB_HEIGHT = 90.0           # m
TOWER_HEIGHT = 87.6         # m above ground (chapter 6: tower top at 87.6 m)
OVERHANG = 5.0              # m, hub upwind of the tower axis (Table 1-1)
SHAFT_TILT_DEG = 5.0        # not modelled (the rotor axis is horizontal here)
PRECONE_DEG = 2.5           # not modelled
V_CUT_IN = 3.0              # m/s
V_RATED = 11.4              # m/s
V_CUT_OUT = 25.0            # m/s
RPM_CUT_IN = 6.9            # rotor rpm
RPM_RATED = 12.1            # rotor rpm
GEAR = 97.0                 # gearbox ratio (chapter 5)
J_ROTOR = 38_759_228.0      # kg m^2: rotor about the LSS = I_drivetrain - GEAR^2 I_gen (section 7.3)
J_GEN = 534.116             # kg m^2 on the HSS (chapter 5)
J_DRIVETRAIN = 43_784_725.0  # kg m^2, the drivetrain inertia cast to the LSS (section 7.3)
K_SHAFT = 867_637_000.0     # N m/rad, equivalent LSS torsional stiffness (chapter 5)
C_SHAFT = 6_215_000.0       # N m s/rad, equivalent LSS torsional damping (chapter 5)
ETA_GEN = 0.944             # electrical generator efficiency (chapter 5)
P_RATED_ELEC = 5.0e6        # W
M_ROTOR = 110_000.0         # kg (Table 1-1)
M_NACELLE = 240_000.0       # kg (Table 1-1)
M_TOWER = 347_460.0         # kg (chapter 6)

# --------------------------------------------------------------------------- chapter 6: the tower
TOWER = {
    "base_diameter": 6.0, "base_thickness": 0.0351,  # m, at the ground
    "top_diameter": 3.87, "top_thickness": 0.0247,   # m, at 87.6 m (both taper linearly)
    "E": 210e9, "density": 8500.0,                   # Pa, kg/m^3 (8500: steel plus paint, bolts, welds, flanges)
    "damping_ratio": 0.01,                           # 1 % of critical for every tower mode
    "f1_fore_aft_fast": 0.3240,                      # Hz, Table 9-1 (FAST, full system)
    "f1_fore_aft_adams": 0.3195,                     # Hz, Table 9-1 (ADAMS)
}

# --------------------------------------------------------------------------- chapter 3: Table 3-1, blade aerodynamics
# (RNodes from the rotor centre [m], AeroTwst [deg], DRNodes [m], Chord [m], airfoil)
BLADE = [
    (2.8667, 13.308, 2.7333, 3.542, "Cylinder1"),
    (5.6000, 13.308, 2.7333, 3.854, "Cylinder1"),
    (8.3333, 13.308, 2.7333, 4.167, "Cylinder2"),
    (11.7500, 13.308, 4.1000, 4.557, "DU40_A17"),
    (15.8500, 11.480, 4.1000, 4.652, "DU35_A17"),
    (19.9500, 10.162, 4.1000, 4.458, "DU35_A17"),
    (24.0500, 9.011, 4.1000, 4.249, "DU30_A17"),
    (28.1500, 7.795, 4.1000, 4.007, "DU25_A17"),
    (32.2500, 6.544, 4.1000, 3.748, "DU25_A17"),
    (36.3500, 5.361, 4.1000, 3.502, "DU21_A17"),
    (40.4500, 4.188, 4.1000, 3.256, "DU21_A17"),
    (44.5500, 3.125, 4.1000, 3.010, "NACA64_A17"),
    (48.6500, 2.319, 4.1000, 2.764, "NACA64_A17"),
    (52.7500, 1.526, 4.1000, 2.518, "NACA64_A17"),
    (56.1667, 0.863, 2.7333, 2.313, "NACA64_A17"),
    (58.9000, 0.370, 2.7333, 2.086, "NACA64_A17"),
    (61.6333, 0.106, 2.7333, 1.419, "NACA64_A17"),
]

# --------------------------------------------------------------------------- chapter 7 and Appendix C (DISCON)
CTRL = {
    "corner_hz": 0.25,              # generator-speed low-pass filter (section 7.1)
    "vs_ctinsp": 70.16224,          # rad/s HSS (670 rpm): region 1 / 1.5 boundary
    "vs_rgn2sp": 91.21091,          # rad/s HSS (871 rpm): region 1.5 / 2 boundary
    "vs_rgn2k": 2.332287,           # N m/(rad/s)^2 = 0.0255764 N m/rpm^2 (region 2)
    "vs_rtgnsp": 121.6805,          # rad/s HSS (1161.963 rpm, 99 % of rated): region 2.5 / 3
    "vs_rtpwr": 5_296_610.0,        # W, rated mechanical power (5 MW / 0.944)
    "vs_slpc": 10.0,                # % generator slip of the region 2.5 line
    "vs_maxtq": 47_402.91,          # N m, maximum generator torque (10 % above rated)
    "vs_maxrat": 15_000.0,          # N m/s, generator torque rate limit
    "vs_rgn3mp": 0.01745329,        # rad (1 deg): pitch above which the torque law stays in region 3
    "pc_refspd": 122.9096,          # rad/s HSS (1173.7 rpm), rated generator speed
    "pc_kp": 0.01882681,            # s, proportional gain at zero pitch (section 7.3)
    "pc_ki": 0.008068634,           # -, integral gain at zero pitch
    "pc_kk": 0.1099965,             # rad (6.302336 deg), pitch at which the sensitivity has doubled
    "pc_minpit": 0.0,               # rad
    "pc_maxpit": 1.570796,          # rad (90 deg)
    "pc_maxrat": 0.1396263,         # rad/s (8 deg/s), pitch rate limit
}
RATED_GEN_RPM = 1173.7
RATED_GEN_TORQUE = 43_093.55        # N m, rated generator torque (vs_rtpwr / pc_refspd)

# Table 7-1: region 3 steady states (wind m/s, rotor rpm, pitch deg, dP/dtheta W/rad)
TABLE_7_1 = [
    (11.4, 12.1, 0.00, -28.24e6), (12.0, 12.1, 3.83, -43.73e6), (13.0, 12.1, 6.60, -51.66e6),
    (14.0, 12.1, 8.70, -58.44e6), (15.0, 12.1, 10.45, -64.44e6), (16.0, 12.1, 12.06, -70.46e6),
    (17.0, 12.1, 13.54, -76.53e6), (18.0, 12.1, 14.92, -83.94e6), (19.0, 12.1, 16.23, -90.67e6),
    (20.0, 12.1, 17.47, -94.71e6), (21.0, 12.1, 18.68, -99.04e6), (22.0, 12.1, 19.94, -105.90e6),
    (23.0, 12.1, 21.18, -114.30e6), (24.0, 12.1, 22.35, -120.20e6), (25.0, 12.1, 23.47, -125.30e6),
]
CP_MAX_REPORT = 0.482               # section 7.3: peak power coefficient ...
TSR_OPT_REPORT = 7.55               # ... at this tip-speed ratio and zero pitch


def ctrl_derived() -> dict:
    """The derived torque-law constants of DISCON (Appendix C)."""
    c = CTRL
    sysp = c["vs_rtgnsp"] / (1.0 + 0.01 * c["vs_slpc"])
    slope15 = c["vs_rgn2k"] * c["vs_rgn2sp"] ** 2 / (c["vs_rgn2sp"] - c["vs_ctinsp"])
    slope25 = (c["vs_rtpwr"] / c["vs_rtgnsp"]) / (c["vs_rtgnsp"] - sysp)
    if c["vs_rgn2k"] == 0.0:
        trgnsp = sysp
    else:
        trgnsp = (slope25 - math.sqrt(slope25 * (slope25 - 4.0 * c["vs_rgn2k"] * sysp))) / (2.0 * c["vs_rgn2k"])
    return {"vs_sysp": sysp, "vs_slope15": slope15, "vs_slope25": slope25, "vs_trgnsp": trgnsp}
